"""
app/services/scan_service.py
Layanan utama untuk Alur Pindai Situs (Scan -> Bandingkan -> Centang -> Tarik).
Mengelola sesi pemindaian, perbandingan terhadap basis pengetahuan, pemilihan kandidat,
penarikan dokumen ke KB / ekspor folder ZIP, serta integrasi mode push.
"""
import hashlib
import io
import logging
import zipfile
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple, Dict, Any

from fastapi import HTTPException, status
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.enums import (
    JenisSumber,
    StatusPindai,
    TujuanTarik,
    StatusKandidat,
    JenisJobIngest,
    StatusJobIngest,
    JenisKegagalan,
)
from app.models.document import Document
from app.models.job_ingest import JobIngest
from app.models.scraping_source import ScrapingSource
from app.models.scan_session import ScanSession
from app.models.scan_candidate import ScanCandidate
from app.models.ingest_failure import IngestFailure

from app.crawlers.base import BlockedUrlError, FetchTooLargeError, CrawlerError
from app.crawlers.registry import get_crawler
from app.crawlers.simple_http import SimpleHttpCrawler
from app.crawlers.url_utils import normalize_url, guard_url

from app.schemas.scan import (
    ScanCreate,
    ScanSelectionUpdate,
    ScanSelectionResponse,
    RejectedSelection,
    ScanSummaryCount,
    InternalCandidatesBatchIn,
)
from app.services.file_validation import sanitize_filename, validate_pdf, FileValidationError
from app.services.storage_service import get_storage_service, StorageService
from app.services.ingest_service import IngestService, IngestItem, IngestOptions, ItemOutcome
from app.services.audit_service import (
    record_audit,
    START_SCAN,
    START_PULL,
    CANCEL_SCAN,
    DOWNLOAD_SCAN_EXPORT,
)

logger = logging.getLogger("hero.scan")


def get_scan_service(db: Session = None) -> "ScanService":
    """Factory helper untuk ScanService."""
    if db is None:
        db = SessionLocal()
    return ScanService(db)


class ScanService:
    def __init__(self, db: Session):
        self.db = db

    def start_scan(
        self,
        payload: ScanCreate,
        actor_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> ScanSession:
        """
        [US-16, FR-SCR-02, FR-SCR-05] Memvalidasi dan menginisialisasi sesi pemindaian situs web baru.
        """
        # 1. Validasi keberadaan dan tipe sumber
        source = self.db.query(ScrapingSource).filter(ScrapingSource.id == payload.source_id).first()
        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sumber dokumen dengan ID {payload.source_id} tidak ditemukan.",
            )

        if not source.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sumber nonaktif.",
            )

        if source.source_type != JenisSumber.situs_web:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Sumber bertipe '{source.source_type.value}' bukan merupakan situs_web. Pemindaian hanya untuk situs web.",
            )

        # 2. Cek apakah ada sesi pemindaian yang masih aktif untuk sumber ini
        active_session = (
            self.db.query(ScanSession)
            .filter(
                ScanSession.source_id == source.id,
                ScanSession.status.in_([
                    StatusPindai.antrian,
                    StatusPindai.memindai,
                    StatusPindai.menarik,
                ]),
            )
            .first()
        )
        if active_session:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sumber '{source.name}' sedang dalam sesi pemindaian/penarikan aktif (scan_id={active_session.id}, status='{active_session.status.value}').",
            )

        # 3. Validasi kedalaman dan batas halaman
        effective_depth = payload.crawl_depth or source.crawl_depth or 1
        if effective_depth < 1 or effective_depth > 5:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Kedalaman crawling (crawl_depth) harus berada dalam rentang 1-5.",
            )

        effective_max_pages = payload.max_pages or settings.crawl_max_pages
        if effective_max_pages < 1 or effective_max_pages > settings.crawl_max_pages:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Batas halaman (max_pages) harus berada dalam rentang 1-{settings.crawl_max_pages}.",
            )

        # 4. Perlindungan SSRF sebelum sesi dibuat
        try:
            guard_url(source.url, allow_private=settings.crawl_allow_private_networks)
        except BlockedUrlError as bue:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"URL sumber tidak lolos pemeriksaan keamanan SSRF: {bue}",
            )

        # 5. Buat entri ScanSession baru
        session = ScanSession(
            source_id=source.id,
            start_url=source.url,
            crawl_depth=effective_depth,
            mode=settings.crawler_backend,
            status=StatusPindai.antrian,
            requested_by_user_id=actor_user_id,
            errors=[],
        )
        self.db.add(session)
        self.db.flush()

        # Update last_run status pada ScrapingSource
        source.last_run_status = "berjalan"
        source.last_run_message = f"Memulai sesi pemindaian #{session.id} (depth={effective_depth})."

        # Catat Audit Log
        record_audit(
            self.db,
            action=START_SCAN,
            user_id=actor_user_id,
            target_resource=f"scan:{session.id}",
            detail={
                "source_id": source.id,
                "start_url": source.url,
                "crawl_depth": effective_depth,
                "max_pages": effective_max_pages,
            },
            ip_address=ip_address,
            commit=False,
        )

        self.db.commit()
        self.db.refresh(session)
        return session

    def execute_scan(self, scan_id: int) -> None:
        """
        Menjalankan pemindaian URL situs secara asynchronous di background worker.
        Menggunakan database session tersendiri dan advisory lock.
        """
        with SessionLocal() as db:
            session = db.query(ScanSession).filter(ScanSession.id == scan_id).first()
            if not session:
                logger.error(f"[Scan] Sesi pemindaian ID {scan_id} tidak ditemukan.")
                return

            source = db.query(ScrapingSource).filter(ScrapingSource.id == session.source_id).first() if session.source_id else None

            # 1. Dapatkan advisory lock berbasis source_id untuk mencegah race condition
            lock_acquired = False
            lock_key = session.source_id or scan_id
            try:
                res = db.execute(text(f"SELECT pg_try_advisory_lock(1396924750, {lock_key})")).scalar()
                lock_acquired = bool(res)
            except Exception as e:
                logger.warning(f"[Scan] Gagal memanggil pg_try_advisory_lock: {e}")
                lock_acquired = True

            if not lock_acquired:
                session.status = StatusPindai.gagal
                session.error_message = "Pemindaian sumber ini sedang diproses oleh eksekusi lain."
                session.finished_at = datetime.now(timezone.utc)
                if source:
                    source.last_run_status = "gagal"
                    source.last_run_message = session.error_message
                db.commit()
                return

            try:
                # 2. Perbarui status menjadi memindai
                session.status = StatusPindai.memindai
                session.started_at = datetime.now(timezone.utc)
                db.commit()

                # Jika mode push, biarkan status memindai menunggu push API
                if session.mode == "push":
                    return

                # 3. Dapatkan crawler aktif
                crawler = get_crawler(settings)
                if not crawler:
                    session.status = StatusPindai.gagal
                    session.error_message = "Tidak ada crawler aktif yang terkonfigurasi pada sistem."
                    session.finished_at = datetime.now(timezone.utc)
                    if source:
                        source.last_run_status = "gagal"
                        source.last_run_message = session.error_message
                    db.commit()
                    return

                session.crawler_name = crawler.name

                def progress_cb(pages: int, cand_count: int):
                    """Callback progres pemindaian."""
                    session.pages_visited = pages
                    session.candidates_total = cand_count
                    try:
                        db.commit()
                    except Exception:
                        pass

                def cancel_cb() -> bool:
                    """Pemeriksaan apakah pengguna meminta pembatalan."""
                    db.refresh(session)
                    return bool(session.cancel_requested)

                # 4. Eksekusi pemindaian situs
                scan_res = crawler.scan(
                    session.start_url,
                    session.crawl_depth,
                    max_pages=settings.crawl_max_pages,
                    max_candidates=settings.crawl_max_candidates,
                    progress=progress_cb,
                    should_cancel=cancel_cb,
                )

                db.refresh(session)
                if session.cancel_requested:
                    session.status = StatusPindai.dibatalkan
                    session.finished_at = datetime.now(timezone.utc)
                    if source:
                        source.last_run_status = "gagal"
                        source.last_run_message = f"Pemindaian #{session.id} dibatalkan oleh pengguna."
                    db.commit()
                    return

                # 5. Simpan kandidat PDF ke database
                for cand in scan_res.candidates:
                    norm_url = normalize_url(cand.url)
                    url_hash = hashlib.sha256(norm_url.encode("utf-8")).hexdigest()
                    candidate_row = ScanCandidate(
                        scan_id=session.id,
                        url=norm_url,
                        url_hash=url_hash,
                        filename=cand.filename,
                        size_bytes=cand.size_bytes,
                        found_on_page=cand.found_on_page,
                        depth=cand.depth,
                    )
                    db.add(candidate_row)

                db.flush()

                # 6. Jalankan perbandingan terhadap Knowledge Base (§3.4)
                self._compare_candidates_with_kb(session, db)

                # 7. Selesaikan pemindaian dan ubah status ke siap_dipilih
                session.pages_visited = scan_res.pages_visited
                session.truncated = scan_res.truncated
                session.errors = scan_res.errors
                session.scanned_at = datetime.now(timezone.utc)
                session.status = StatusPindai.siap_dipilih

                if source:
                    source.last_run_at = datetime.now(timezone.utc)
                    source.last_run_status = "selesai"
                    source.last_run_message = (
                        f"Dipindai: {session.pages_visited} halaman, {session.candidates_total} PDF "
                        f"(baru {session.candidates_new}, sudah ada {session.candidates_existing}, "
                        f"mungkin ada {session.candidates_uncertain})."
                    )

                db.commit()
                logger.info(f"[Scan] Sesi #{session.id} selesai dipindai: {session.candidates_total} kandidat ditemukan.")

            except Exception as exc:
                logger.exception(f"[Scan] Kesalahan tak terduga saat pemindaian sesi #{session.id}: {exc}")
                session.status = StatusPindai.gagal
                session.error_message = str(exc)
                session.finished_at = datetime.now(timezone.utc)
                if source:
                    source.last_run_status = "gagal"
                    source.last_run_message = f"Gagal: {exc}"
                db.commit()

            finally:
                if lock_acquired:
                    try:
                        db.execute(text(f"SELECT pg_advisory_unlock(1396924750, {lock_key})"))
                        db.commit()
                    except Exception:
                        pass

    def _compare_candidates_with_kb(self, session: ScanSession, db: Session) -> None:
        """
        [US-16, FR-SCR-02] Membandingkan kandidat PDF dengan Knowledge Base menggunakan batch query.
        Aturan:
        1. URL sama persis (setelah normalisasi) -> sudah_ada (url_sama), selected=False (dilarang dicentang).
        2. Nama file (sanitize) sama & ukuran byte sama persis -> mungkin_ada (nama_dan_ukuran_sama), selected=False (boleh dicentang).
        3. Selain itu -> baru, selected=True.
        """
        candidates = db.query(ScanCandidate).filter(ScanCandidate.scan_id == session.id).all()
        if not candidates:
            session.candidates_total = 0
            session.candidates_new = 0
            session.candidates_existing = 0
            session.candidates_uncertain = 0
            return

        # 1. Batch query 1: Ambil dokumen berdasarkan URL
        urls = [c.url for c in candidates]
        matching_url_docs = db.query(Document).filter(Document.source_url.in_(urls)).all()
        url_doc_map = {normalize_url(d.source_url): d for d in matching_url_docs if d.source_url}

        # 2. Batch query 2: Ambil dokumen berdasarkan ukuran file
        sizes = [c.size_bytes for c in candidates if c.size_bytes is not None]
        size_doc_map: Dict[int, List[Tuple[str, str, Document]]] = {}
        if sizes:
            matching_size_docs = db.query(Document).filter(Document.file_size_bytes.in_(sizes)).all()
            for d in matching_size_docs:
                if d.file_size_bytes:
                    orig_clean = sanitize_filename(d.original_filename or "").lower()
                    std_clean = sanitize_filename(d.standardized_filename or "").lower()
                    size_doc_map.setdefault(d.file_size_bytes, []).append((orig_clean, std_clean, d))

        c_total = len(candidates)
        c_new = 0
        c_exist = 0
        c_uncert = 0

        for cand in candidates:
            # Pengecekan 1: URL sama
            norm_cand_url = normalize_url(cand.url)
            matched_by_url = url_doc_map.get(norm_cand_url)
            if matched_by_url:
                cand.match_status = StatusKandidat.sudah_ada
                cand.match_reason = "url_sama"
                cand.match_document_id = matched_by_url.id
                cand.selected = False
                c_exist += 1
                continue

            # Pengecekan 2: Nama dan ukuran sama
            if cand.size_bytes is not None and cand.size_bytes in size_doc_map:
                cand_clean_name = sanitize_filename(cand.filename).lower()
                matched_by_size_name = None
                for orig_n, std_n, doc in size_doc_map[cand.size_bytes]:
                    if cand_clean_name and (cand_clean_name == orig_n or cand_clean_name == std_n):
                        matched_by_size_name = doc
                        break

                if matched_by_size_name:
                    cand.match_status = StatusKandidat.mungkin_ada
                    cand.match_reason = "nama_dan_ukuran_sama"
                    cand.match_document_id = matched_by_size_name.id
                    cand.selected = False
                    c_uncert += 1
                    continue

            # Pengecekan 3: Baru
            cand.match_status = StatusKandidat.baru
            cand.match_reason = None
            cand.match_document_id = None
            cand.selected = True
            c_new += 1

        session.candidates_total = c_total
        session.candidates_new = c_new
        session.candidates_existing = c_exist
        session.candidates_uncertain = c_uncert

    def update_selection(self, scan_id: int, payload: ScanSelectionUpdate) -> ScanSelectionResponse:
        """
        [US-16] Memperbarui pilihan centang kandidat PDF pada status siap_dipilih.
        """
        session = self.db.query(ScanSession).filter(ScanSession.id == scan_id).first()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sesi pemindaian dengan ID {scan_id} tidak ditemukan.",
            )

        if session.status != StatusPindai.siap_dipilih:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Pilihan kandidat hanya dapat diubah saat status sesi 'siap_dipilih' (status saat ini: '{session.status.value}').",
            )

        candidates = self.db.query(ScanCandidate).filter(ScanCandidate.scan_id == scan_id).all()
        cand_map = {c.id: c for c in candidates}
        rejected: List[RejectedSelection] = []

        if payload.action == "select_all_new":
            for c in candidates:
                if c.match_status != StatusKandidat.sudah_ada:
                    c.selected = True
                else:
                    c.selected = False

        elif payload.action == "select_none":
            for c in candidates:
                c.selected = False

        elif payload.action == "set":
            if payload.candidate_ids is None or payload.selected is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Field 'candidate_ids' dan 'selected' wajib diisi jika action='set'.",
                )

            for cid in payload.candidate_ids:
                cand = cand_map.get(cid)
                if not cand:
                    continue
                # Kandidat 'sudah_ada' dilarang dicentang
                if cand.match_status == StatusKandidat.sudah_ada and payload.selected:
                    rejected.append(
                        RejectedSelection(
                            id=cid,
                            reason="Kandidat sudah ada di basis pengetahuan dan tidak dapat dipilih untuk ditarik.",
                        )
                    )
                else:
                    cand.selected = bool(payload.selected)

        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Aksi pemilihan '{payload.action}' tidak valid. Gunakan: 'select_all_new', 'select_none', atau 'set'.",
            )

        self.db.commit()

        # Hitung ringkasan terbaru
        terpilih_count = sum(1 for c in candidates if c.selected)
        summary = ScanSummaryCount(
            total=session.candidates_total,
            baru=session.candidates_new,
            sudah_ada=session.candidates_existing,
            mungkin_ada=session.candidates_uncertain,
            terpilih=terpilih_count,
        )

        return ScanSelectionResponse(
            scan_id=scan_id,
            summary=summary,
            rejected_ids=rejected,
        )

    def start_pull(
        self,
        scan_id: int,
        destination: TujuanTarik,
        actor_user_id: Optional[int] = None,
        actor_username: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[ScanSession, JobIngest]:
        """
        [US-16, FR-SCR-05] Memulai proses penarikan kandidat PDF terpilih ke tujuan yang ditentukan.
        """
        session = self.db.query(ScanSession).filter(ScanSession.id == scan_id).first()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sesi pemindaian dengan ID {scan_id} tidak ditemukan.",
            )

        if session.status != StatusPindai.siap_dipilih:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Penarikan hanya dapat dimulai dari status 'siap_dipilih' (status saat ini: '{session.status.value}').",
            )

        selected_count = (
            self.db.query(ScanCandidate)
            .filter(ScanCandidate.scan_id == scan_id, ScanCandidate.selected == True)
            .count()
        )
        if selected_count < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Tidak ada kandidat PDF yang dipilih untuk ditarik. Silakan pilih minimal 1 berkas.",
            )

        # Buat JobIngest untuk penarikan
        trigger_name = actor_username or "manual_scan_pull"
        job = JobIngest(
            job_type=JenisJobIngest.scraping,
            source_id=session.source_id,
            status=StatusJobIngest.antrian,
            total_found=selected_count,
            processed_count=0,
            skipped_count=0,
            success_count=0,
            duplicate_count=0,
            failed_count=0,
            source_ref=f"scan:{session.id}",
            triggered_by=trigger_name[:100],
        )
        self.db.add(job)
        self.db.flush()

        session.status = StatusPindai.menarik
        session.destination = destination
        session.pull_job_id = job.id

        # Catat Audit Log
        record_audit(
            self.db,
            action=START_PULL,
            user_id=actor_user_id,
            target_resource=f"scan:{session.id}",
            detail={
                "scan_id": session.id,
                "job_id": job.id,
                "destination": destination.value,
                "selected_count": selected_count,
            },
            ip_address=ip_address,
            commit=False,
        )

        self.db.commit()
        self.db.refresh(session)
        self.db.refresh(job)
        return session, job

    def execute_pull(self, scan_id: int) -> None:
        """
        Mengeksekusi penarikan berkas PDF terpilih di background worker.
        """
        with SessionLocal() as db:
            session = db.query(ScanSession).filter(ScanSession.id == scan_id).first()
            if not session or not session.pull_job_id:
                logger.error(f"[Pull] Sesi #{scan_id} atau pull_job_id tidak valid.")
                return

            job = db.query(JobIngest).filter(JobIngest.id == session.pull_job_id).first()
            source = db.query(ScrapingSource).filter(ScrapingSource.id == session.source_id).first() if session.source_id else None

            # Dapatkan advisory lock
            lock_acquired = False
            lock_key = session.source_id or scan_id
            try:
                res = db.execute(text(f"SELECT pg_try_advisory_lock(1396924750, {lock_key})")).scalar()
                lock_acquired = bool(res)
            except Exception as e:
                logger.warning(f"[Pull] Gagal memanggil pg_try_advisory_lock: {e}")
                lock_acquired = True

            if not lock_acquired:
                session.status = StatusPindai.gagal
                session.error_message = "Proses penarikan sedang diproses oleh eksekusi lain."
                session.finished_at = datetime.now(timezone.utc)
                if job:
                    job.status = StatusJobIngest.gagal
                    job.finished_at = datetime.now(timezone.utc)
                db.commit()
                return

            try:
                job.status = StatusJobIngest.berjalan
                job.started_at = datetime.now(timezone.utc)
                db.commit()

                # Gunakan crawler untuk mengunduh berkas
                crawler = get_crawler(settings) or SimpleHttpCrawler(allow_private=settings.crawl_allow_private_networks)
                storage = get_storage_service()
                ingest_svc = IngestService(db, storage)

                candidates = (
                    db.query(ScanCandidate)
                    .filter(ScanCandidate.scan_id == session.id, ScanCandidate.selected == True)
                    .order_by(ScanCandidate.id.asc())
                    .all()
                )

                for cand in candidates:
                    # Cek pembatalan antar berkas
                    db.refresh(session)
                    if session.cancel_requested:
                        break

                    # 1. Unduh berkas dari URL
                    fetched = None
                    try:
                        fetched = crawler.fetch(cand.url, max_bytes=settings.max_upload_bytes)
                    except FetchTooLargeError as fle:
                        failure = IngestFailure(
                            job_id=job.id,
                            failure_type=JenisKegagalan.format_tidak_didukung,
                            reason_code="ukuran_melebihi_batas",
                            original_filename=cand.filename,
                            source_url=cand.url,
                            message=str(fle),
                            is_retryable=False,
                            ingest_options={
                                "fetch_url": cand.url,
                                "scan_id": session.id,
                                "access_classification": source.default_access_classification.value if source else "publik",
                                "document_role": source.default_document_role.value if source else "corpus_eksisting",
                            },
                        )
                        db.add(failure)
                        db.flush()
                        cand.pull_outcome = "failed"
                        cand.failure_id = failure.id
                        cand.message = str(fle)
                        job.failed_count += 1
                        job.processed_count += 1
                        continue

                    except (BlockedUrlError, CrawlerError, Exception) as exc:
                        is_retry = not isinstance(exc, BlockedUrlError)
                        failure = IngestFailure(
                            job_id=job.id,
                            failure_type=JenisKegagalan.sumber_tidak_dapat_diakses,
                            reason_code="sumber_tidak_dapat_diakses",
                            original_filename=cand.filename,
                            source_url=cand.url,
                            message=f"Gagal mengunduh: {exc}",
                            is_retryable=is_retry,
                            ingest_options={
                                "fetch_url": cand.url,
                                "scan_id": session.id,
                                "access_classification": source.default_access_classification.value if source else "publik",
                                "document_role": source.default_document_role.value if source else "corpus_eksisting",
                            },
                        )
                        db.add(failure)
                        db.flush()
                        cand.pull_outcome = "failed"
                        cand.failure_id = failure.id
                        cand.message = str(exc)
                        job.failed_count += 1
                        job.processed_count += 1
                        continue

                    # 2. Proses berkas sesuai tujuan
                    if session.destination == TujuanTarik.knowledge_base:
                        norm_source_url = normalize_url(cand.url)
                        item = IngestItem(
                            filename=fetched.filename,
                            content=fetched.content,
                            source_url=norm_source_url,
                        )
                        opts = IngestOptions(
                            access_classification=source.default_access_classification if source else "publik",
                            document_role=source.default_document_role if source else "corpus_eksisting",
                        )
                        res = ingest_svc.ingest_one(job, item, opts, suppress_failure_hooks=False)
                        cand.pull_outcome = res.outcome.value
                        cand.document_id = res.document_id
                        cand.message = res.message
                        if res.outcome == ItemOutcome.failed:
                            f_row = (
                                db.query(IngestFailure)
                                .filter(IngestFailure.job_id == job.id, IngestFailure.source_url == norm_source_url)
                                .order_by(IngestFailure.id.desc())
                                .first()
                            )
                            if f_row:
                                cand.failure_id = f_row.id

                    elif session.destination == TujuanTarik.unduh_folder:
                        try:
                            validate_pdf(fetched.filename, fetched.content, settings.max_upload_bytes)
                            safe_hint = sanitize_filename(fetched.filename)
                            rel_path = storage.save_pdf(
                                fetched.content,
                                filename_hint=safe_hint,
                                subdir=f"exports/scan_{session.id}",
                            )
                            cand.pull_outcome = "downloaded"
                            cand.export_path = rel_path
                            cand.message = "Berkas berhasil diunduh ke folder ekspor."
                            job.success_count += 1
                        except FileValidationError as fve:
                            failure = IngestFailure(
                                job_id=job.id,
                                failure_type=JenisKegagalan.format_tidak_didukung,
                                reason_code=fve.code.value,
                                original_filename=cand.filename,
                                source_url=cand.url,
                                message=fve.message,
                                is_retryable=False,
                            )
                            db.add(failure)
                            db.flush()
                            cand.pull_outcome = "failed"
                            cand.failure_id = failure.id
                            cand.message = fve.message
                            job.failed_count += 1

                    job.processed_count += 1
                    if job.processed_count % settings.job_progress_commit_every == 0:
                        db.commit()

                # 3. Selesaikan job dan sesi
                db.refresh(session)
                job.finished_at = datetime.now(timezone.utc)
                if session.cancel_requested:
                    session.status = StatusPindai.dibatalkan
                    job.status = StatusJobIngest.gagal
                else:
                    session.status = StatusPindai.selesai
                    job.status = StatusJobIngest.selesai

                session.finished_at = datetime.now(timezone.utc)

                if source:
                    source.last_run_at = datetime.now(timezone.utc)
                    source.last_run_status = "selesai" if session.status == StatusPindai.selesai else "gagal"
                    source.last_run_message = (
                        f"Dipindai: {session.pages_visited} halaman, {session.candidates_total} PDF. "
                        f"Ditarik ({session.destination.value if session.destination else '-'}): "
                        f"{job.success_count} berhasil, {job.duplicate_count} duplikat, {job.failed_count} gagal."
                    )

                db.commit()
                logger.info(f"[Pull] Sesi #{session.id} penarikan selesai: {job.success_count} success, {job.failed_count} failed.")

            except Exception as e:
                logger.exception(f"[Pull] Kesalahan fatal saat eksekusi penarikan sesi #{session.id}: {e}")
                session.status = StatusPindai.gagal
                session.error_message = str(e)
                session.finished_at = datetime.now(timezone.utc)
                if job:
                    job.status = StatusJobIngest.gagal
                    job.finished_at = datetime.now(timezone.utc)
                if source:
                    source.last_run_status = "gagal"
                    source.last_run_message = f"Gagal penarikan: {e}"
                db.commit()

            finally:
                if lock_acquired:
                    try:
                        db.execute(text(f"SELECT pg_advisory_unlock(1396924750, {lock_key})"))
                        db.commit()
                    except Exception:
                        pass

    def cancel_scan(
        self,
        scan_id: int,
        actor_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> ScanSession:
        """
        [US-16] Membatalkan sesi pemindaian atau penarikan yang sedang berjalan atau antrian.
        """
        session = self.db.query(ScanSession).filter(ScanSession.id == scan_id).first()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sesi pemindaian dengan ID {scan_id} tidak ditemukan.",
            )

        if session.status not in (
            StatusPindai.antrian,
            StatusPindai.memindai,
            StatusPindai.siap_dipilih,
            StatusPindai.menarik,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sesi pemindaian dengan status '{session.status.value}' tidak dapat dibatalkan.",
            )

        if session.status in (StatusPindai.antrian, StatusPindai.siap_dipilih):
            session.status = StatusPindai.dibatalkan
            session.finished_at = datetime.now(timezone.utc)
        else:
            session.cancel_requested = True

        record_audit(
            self.db,
            action=CANCEL_SCAN,
            user_id=actor_user_id,
            target_resource=f"scan:{session.id}",
            detail={"status_sebelumnya": session.status.value},
            ip_address=ip_address,
            commit=False,
        )

        self.db.commit()
        self.db.refresh(session)
        return session

    def build_export_zip(
        self,
        scan_id: int,
        actor_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> io.BytesIO:
        """
        [US-16] Membangun berkas arsip ZIP dari hasil penarikan tujuan unduh_folder.
        """
        session = self.db.query(ScanSession).filter(ScanSession.id == scan_id).first()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sesi pemindaian dengan ID {scan_id} tidak ditemukan.",
            )

        if session.destination != TujuanTarik.unduh_folder:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pengunduhan berkas ZIP hanya tersedia untuk sesi dengan tujuan 'unduh_folder'.",
            )

        if session.status != StatusPindai.selesai:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Berkas ZIP hanya dapat diunduh saat sesi berstatus 'selesai' (status saat ini: '{session.status.value}').",
            )

        candidates = (
            self.db.query(ScanCandidate)
            .filter(
                ScanCandidate.scan_id == scan_id,
                ScanCandidate.pull_outcome == "downloaded",
                ScanCandidate.export_path.isnot(None),
            )
            .all()
        )

        storage = get_storage_service()
        zip_buffer = io.BytesIO()
        used_names: Dict[str, int] = {}

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for cand in candidates:
                if not storage.exists(cand.export_path):
                    continue
                try:
                    file_bytes = storage.read_pdf(cand.export_path)
                    base_name = sanitize_filename(cand.filename)
                    if not base_name.lower().endswith(".pdf"):
                        base_name += ".pdf"

                    # Jaga keunikan nama dalam ZIP
                    if base_name in used_names:
                        used_names[base_name] += 1
                        stem, ext = base_name.rsplit(".", 1)
                        zip_name = f"{stem}_{used_names[base_name]}.{ext}"
                    else:
                        used_names[base_name] = 0
                        zip_name = base_name

                    zip_file.writestr(zip_name, file_bytes)
                except Exception as e:
                    logger.warning(f"Gagal memasukkan berkas '{cand.export_path}' ke ZIP: {e}")

        zip_buffer.seek(0)

        record_audit(
            self.db,
            action=DOWNLOAD_SCAN_EXPORT,
            user_id=actor_user_id,
            target_resource=f"scan:{session.id}",
            detail={"files_count": len(candidates)},
            ip_address=ip_address,
            commit=True,
        )

        return zip_buffer

    # ==================== MODE PUSH INTERNAL API ====================

    def claim_push_scans(self, limit: int = 1) -> List[ScanSession]:
        """
        [US-16, Data/ML Push API] Mengklaim sesi antrian bermode push dengan FOR UPDATE SKIP LOCKED.
        """
        limit = max(1, min(limit, 5))
        claimed_sessions = (
            self.db.query(ScanSession)
            .filter(
                ScanSession.mode == "push",
                ScanSession.status == StatusPindai.antrian,
            )
            .with_for_update(skip_locked=True)
            .limit(limit)
            .all()
        )

        now = datetime.now(timezone.utc)
        for s in claimed_sessions:
            s.status = StatusPindai.memindai
            s.claimed_at = now
            s.started_at = now

        self.db.commit()
        for s in claimed_sessions:
            self.db.refresh(s)
        return claimed_sessions

    def push_candidates(self, scan_id: int, payload: InternalCandidatesBatchIn) -> ScanSession:
        """
        [US-16, Data/ML Push API] Menerima batch kandidat hasil crawling dari worker push eksternal.
        """
        session = self.db.query(ScanSession).filter(ScanSession.id == scan_id).first()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sesi pemindaian dengan ID {scan_id} tidak ditemukan.",
            )

        if session.status != StatusPindai.memindai:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sesi pemindaian tidak dalam status 'memindai' (status saat ini: '{session.status.value}').",
            )

        if payload.error:
            session.status = StatusPindai.gagal
            session.error_message = payload.error
            session.finished_at = datetime.now(timezone.utc)
            self.db.commit()
            return session

        session.pages_visited = payload.pages_visited
        if payload.errors:
            current_errors = list(session.errors or [])
            current_errors.extend(payload.errors)
            session.errors = current_errors

        if payload.truncated:
            session.truncated = True

        # Upsert candidates
        for cand_in in payload.candidates:
            norm_url = normalize_url(cand_in.url)
            try:
                guard_url(norm_url, allow_private=settings.crawl_allow_private_networks)
            except BlockedUrlError as bue:
                current_errors = list(session.errors or [])
                current_errors.append(f"Kandidat '{norm_url}' dibuang karena terblokir SSRF: {bue}")
                session.errors = current_errors
                continue

            url_hash = hashlib.sha256(norm_url.encode("utf-8")).hexdigest()
            existing = (
                self.db.query(ScanCandidate)
                .filter(ScanCandidate.scan_id == scan_id, ScanCandidate.url_hash == url_hash)
                .first()
            )
            if existing:
                existing.filename = cand_in.filename
                existing.size_bytes = cand_in.size_bytes
                existing.depth = cand_in.depth
                existing.found_on_page = cand_in.found_on_page
            else:
                new_cand = ScanCandidate(
                    scan_id=scan_id,
                    url=norm_url,
                    url_hash=url_hash,
                    filename=cand_in.filename,
                    size_bytes=cand_in.size_bytes,
                    found_on_page=cand_in.found_on_page,
                    depth=cand_in.depth,
                )
                self.db.add(new_cand)

        self.db.flush()

        if payload.done:
            self._compare_candidates_with_kb(session, self.db)
            session.scanned_at = datetime.now(timezone.utc)
            session.status = StatusPindai.siap_dipilih

            source = self.db.query(ScrapingSource).filter(ScrapingSource.id == session.source_id).first() if session.source_id else None
            if source:
                source.last_run_at = datetime.now(timezone.utc)
                source.last_run_status = "selesai"
                source.last_run_message = (
                    f"Dipindai (push): {session.pages_visited} halaman, {session.candidates_total} PDF "
                    f"(baru {session.candidates_new}, sudah ada {session.candidates_existing}, "
                    f"mungkin ada {session.candidates_uncertain})."
                )

        self.db.commit()
        self.db.refresh(session)
        return session


def recover_stuck_scan_sessions(db: Session, stuck_minutes: int = 60) -> int:
    """
    Memulihkan sesi pemindaian dan job penarikan yang macet saat startup server.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stuck_minutes)
    stuck_sessions = (
        db.query(ScanSession)
        .filter(
            ScanSession.status.in_([StatusPindai.memindai, StatusPindai.menarik]),
            ScanSession.started_at < cutoff,
        )
        .all()
    )

    recovered = 0
    for s in stuck_sessions:
        s.status = StatusPindai.gagal
        s.error_message = "Dihentikan karena server dimulai ulang."
        s.finished_at = datetime.now(timezone.utc)

        source = db.query(ScrapingSource).filter(ScrapingSource.id == s.source_id).first() if s.source_id else None
        if source:
            source.last_run_status = "gagal"
            source.last_run_message = "Dihentikan karena server dimulai ulang."

        if s.pull_job_id:
            job = db.query(JobIngest).filter(JobIngest.id == s.pull_job_id).first()
            if job and job.status in (StatusJobIngest.antrian, StatusJobIngest.berjalan):
                job.status = StatusJobIngest.gagal
                job.finished_at = datetime.now(timezone.utc)

        recovered += 1

    if recovered > 0:
        db.commit()
        logger.info(f"Berhasil memulihkan {recovered} sesi pemindaian yang macet.")

    return recovered
