"""
app/services/scan_service.py
Layanan utama untuk Alur Pindai Situs (Scan -> Bandingkan -> Centang -> Tarik).
Mengelola sesi pemindaian, perbandingan terhadap basis pengetahuan, pemilihan kandidat,
penarikan dokumen ke KB / ekspor folder ZIP, serta integrasi mode push.
"""
import hashlib
import io
import logging
import time
import zipfile
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from urllib.parse import urlsplit
from urllib.request import url2pathname

from fastapi import HTTPException, status
from sqlalchemy import desc, text, func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, engine
from app.models.category import Category
from app.models.enums import (
    JenisSumber,
    StatusPindai,
    TujuanTarik,
    StatusKandidat,
    JenisJobIngest,
    StatusJobIngest,
    JenisKegagalan,
    KlasifikasiAkses,
    PeranDokumen,
)
from app.models.document import Document
from app.models.job_ingest import JobIngest
from app.models.scraping_source import ScrapingSource
from app.models.scan_session import ScanSession
from app.models.scan_candidate import ScanCandidate
from app.models.ingest_failure import IngestFailure

from app.crawlers.base import BlockedUrlError, FetchTooLargeError, CrawlerError, FetchedFile
from app.crawlers.generic_html import SimpleHttpCrawler
from app.crawlers.registry import get_crawler
from app.crawlers.url_utils import (
    normalize_url,
    guard_url,
    parse_onedrive_filename_metadata,
    determine_doc_kind,
    extract_regulation_year,
)
from app.services.folder_connector import list_pdf_files, FolderAccessError

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
from app.services.ingest_service import IngestService, IngestItem, IngestOptions, DocumentMetadataInput, ItemOutcome
from app.services.naming_service import (
    build_standard_filename,
    NamingInput,
    validate_naming_format,
    validate_naming_separator,
)
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

        if source.source_type not in (JenisSumber.situs_web, JenisSumber.onedrive_public, JenisSumber.folder_lokal):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Sumber bertipe '{source.source_type.value}' bukan merupakan situs_web, onedrive_public, atau folder_lokal.",
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
            # Periksa batas waktu: jika sesi tidak ada aktivitas > scan_stuck_minutes (15 menit)
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.scan_stuck_minutes)
            last_active = active_session.updated_at or active_session.started_at or active_session.created_at
            if last_active and last_active < cutoff:
                logger.warning(
                    f"[Scan] Sesi aktif #{active_session.id} pada sumber '{source.name}' dianggap macet "
                    f"(terakhir aktif: {last_active}). Menandai sesi sebagai gagal."
                )
                active_session.status = StatusPindai.gagal
                active_session.error_message = f"Dihentikan karena server dimulai ulang. Batas waktu aktivitas terlampaui (> {settings.scan_stuck_minutes} menit)."
                active_session.finished_at = datetime.now(timezone.utc)
                if active_session.pull_job_id:
                    job = self.db.query(JobIngest).filter(JobIngest.id == active_session.pull_job_id).first()
                    if job and job.status in (StatusJobIngest.antrian, StatusJobIngest.berjalan):
                        job.status = StatusJobIngest.gagal
                        job.finished_at = datetime.now(timezone.utc)
                self.db.commit()
                active_session = None

        if active_session:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sumber '{source.name}' sedang dalam sesi pemindaian/penarikan aktif (scan_id={active_session.id}, status='{active_session.status.value}').",
            )

        # 3. Validasi kedalaman dan batas halaman
        if source.source_type == JenisSumber.folder_lokal:
            effective_depth = 1
        else:
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

        # 4. Perlindungan SSRF sebelum sesi dibuat (hanya untuk URL situs web/OneDrive)
        if source.source_type in (JenisSumber.situs_web, JenisSumber.onedrive_public):
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
            crawler_adapter=payload.crawler_adapter or source.crawler_adapter,
            status=StatusPindai.antrian,
            requested_by_user_id=actor_user_id,
            errors=[],
            blocked=False,
            stats={"max_pages": effective_max_pages},
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
        Menggunakan database session tersendiri dan advisory lock pada koneksi khusus (engine.connect()).
        """
        lock_conn = None
        lock_acquired = False
        lock_key = None
        lock_ns = 1396924750

        with SessionLocal() as db:
            session = db.query(ScanSession).filter(ScanSession.id == scan_id).first()
            if not session:
                logger.error(f"[Scan] Sesi pemindaian ID {scan_id} tidak ditemukan.")
                return

            source = db.query(ScrapingSource).filter(ScrapingSource.id == session.source_id).first() if session.source_id else None
            lock_key = session.source_id or scan_id

            # Seluruh badan proses pemindaian termasuk perolehan kunci berada di dalam try/finally
            try:
                # 1. Dapatkan advisory lock berbasis source_id untuk mencegah race condition pada koneksi khusus
                try:
                    lock_conn = engine.connect()
                    res = lock_conn.execute(
                        text("SELECT pg_try_advisory_lock(:ns, :key)"),
                        {"ns": lock_ns, "key": lock_key},
                    ).scalar()
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

                # 2. Perbarui status menjadi memindai
                session.status = StatusPindai.memindai
                session.started_at = datetime.now(timezone.utc)
                session.updated_at = datetime.now(timezone.utc)
                db.commit()

                # Jika mode push, biarkan status memindai menunggu push API
                if session.mode == "push":
                    return

                # 3a. Penanganan khusus sumber folder_lokal
                if source and source.source_type == JenisSumber.folder_lokal:
                    session.crawler_name = "local_folder"
                    try:
                        folder_entries = list_pdf_files(
                            Path(source.url),
                            recursive=source.recursive,
                            max_files=settings.local_source_max_files_per_run,
                        )
                    except FolderAccessError as fae:
                        session.status = StatusPindai.gagal
                        session.error_message = str(fae)
                        session.finished_at = datetime.now(timezone.utc)
                        if source:
                            source.last_run_status = "gagal"
                            source.last_run_message = str(fae)
                        db.commit()
                        return

                    c_total = len(folder_entries)
                    c_new = 0
                    c_exist = 0
                    c_uncert = 0

                    for entry in folder_entries:
                        try:
                            f_bytes = entry.absolute_path.read_bytes()
                            f_hash = hashlib.sha256(f_bytes).hexdigest()
                        except Exception as e:
                            logger.warning(f"Gagal membaca file {entry.absolute_path}: {e}")
                            continue

                        f_url = entry.absolute_path.as_uri()
                        u_hash = hashlib.sha256(f_url.encode("utf-8")).hexdigest()

                        meta = parse_onedrive_filename_metadata(entry.absolute_path.name)
                        rel_d = date(meta["release_year"], 1, 1) if meta.get("release_year") else None

                        # Cocokkan terhadap KB:
                        # 1. hash + size sama -> sudah_ada
                        matched_doc = (
                            db.query(Document)
                            .filter(
                                Document.file_hash == f_hash,
                                Document.file_size_bytes == entry.size_bytes,
                            )
                            .first()
                        )

                        if matched_doc:
                            m_status = StatusKandidat.sudah_ada
                            m_reason = "hash_dan_ukuran_sama"
                            m_doc_id = matched_doc.id
                            is_selected = False
                            c_exist += 1
                        else:
                            # 2. Periksa nama (clean) & ukuran sama -> mungkin_ada
                            clean_fname = sanitize_filename(entry.absolute_path.name).lower()
                            size_matches = (
                                db.query(Document)
                                .filter(Document.file_size_bytes == entry.size_bytes)
                                .all()
                            )
                            fuzzy_doc = None
                            for d in size_matches:
                                orig_c = sanitize_filename(d.original_filename or "").lower()
                                std_c = sanitize_filename(d.standardized_filename or "").lower()
                                if clean_fname and (clean_fname == orig_c or clean_fname == std_c):
                                    fuzzy_doc = d
                                    break

                            if fuzzy_doc:
                                m_status = StatusKandidat.mungkin_ada
                                m_reason = "nama_dan_ukuran_sama"
                                m_doc_id = fuzzy_doc.id
                                is_selected = False
                                c_uncert += 1
                            else:
                                m_status = StatusKandidat.baru
                                m_reason = None
                                m_doc_id = None
                                is_selected = True
                                c_new += 1

                        cand_reg_year = meta.get("regulation_year") or extract_regulation_year(
                            regulation_number=meta.get("regulation_number"),
                            title=entry.absolute_path.stem.replace("_", " "),
                            filename=entry.absolute_path.name,
                            release_date=rel_d,
                        )
                        cand_row = ScanCandidate(
                            scan_id=session.id,
                            url=f_url,
                            url_hash=u_hash,
                            filename=entry.absolute_path.name,
                            size_bytes=entry.size_bytes,
                            found_on_page=f"folder://{source.id}",
                            depth=1,
                            document_title=entry.absolute_path.stem.replace("_", " "),
                            detail_url=None,
                            final_url=f_url,
                            doc_kind=determine_doc_kind(entry.absolute_path.name) or "utama",
                            regulation_number=meta.get("regulation_number"),
                            regulation_type=meta.get("regulation_type"),
                            release_date=rel_d,
                            regulation_year=cand_reg_year,
                            size_source="local",
                            source_path=entry.relative_path,
                            match_status=m_status,
                            match_reason=m_reason,
                            match_document_id=m_doc_id,
                            selected=is_selected,
                        )
                        db.add(cand_row)

                    session.candidates_total = c_total
                    session.candidates_new = c_new
                    session.candidates_existing = c_exist
                    session.candidates_uncertain = c_uncert
                    session.pages_visited = 1
                    session.truncated = False
                    session.errors = []
                    session.blocked = False
                    session.stats = {"total_found": c_total}
                    session.scanned_at = datetime.now(timezone.utc)
                    session.status = StatusPindai.siap_dipilih

                    if source:
                        source.last_run_at = datetime.now(timezone.utc)
                        source.last_run_status = "selesai"
                        source.last_run_message = (
                            f"Dipindai folder lokal: {c_total} PDF "
                            f"(baru {c_new}, sudah ada {c_exist}, mungkin ada {c_uncert})."
                        )
                    db.commit()
                    return

                # 3b. Dapatkan crawler aktif untuk situs web / onedrive
                try:
                    crawler = get_crawler(
                        settings,
                        source_url=session.start_url,
                        crawler_adapter=session.crawler_adapter or (source.crawler_adapter if source else None),
                    )
                except TypeError:
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
                scan_max_pages = (session.stats or {}).get("max_pages") or settings.crawl_max_pages
                scan_res = crawler.scan(
                    session.start_url,
                    session.crawl_depth,
                    max_pages=scan_max_pages,
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
                    cand_reg_year = getattr(cand, "regulation_year", None) or extract_regulation_year(
                        regulation_number=cand.regulation_number,
                        title=cand.document_title,
                        filename=cand.filename,
                        release_date=cand.release_date,
                    )
                    candidate_row = ScanCandidate(
                        scan_id=session.id,
                        url=norm_url,
                        url_hash=url_hash,
                        filename=cand.filename,
                        size_bytes=cand.size_bytes,
                        found_on_page=cand.found_on_page,
                        depth=cand.depth,
                        document_title=cand.document_title,
                        detail_url=cand.detail_url,
                        final_url=cand.final_url,
                        doc_kind=cand.doc_kind or "utama",
                        regulation_number=cand.regulation_number,
                        regulation_type=cand.regulation_type,
                        bidang=cand.bidang,
                        sub_bidang=cand.sub_bidang,
                        release_date=cand.release_date,
                        effective_date=cand.effective_date,
                        regulation_year=cand_reg_year,
                        match_warning=cand.match_warning,
                        status_keberlakuan=cand.status_keberlakuan or "tidak_diketahui",
                        size_source=cand.size_source or "unknown",
                        source_path=cand.source_path,
                    )
                    db.add(candidate_row)

                db.flush()

                # 6. Jalankan perbandingan terhadap Knowledge Base (§3.4)
                self._compare_candidates_with_kb(session, db)

                # 7. Selesaikan pemindaian dan ubah status ke siap_dipilih
                session.pages_visited = scan_res.pages_visited
                session.truncated = scan_res.truncated
                session.errors = scan_res.errors
                session.blocked = scan_res.blocked
                session.stats = scan_res.stats
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
                if lock_conn is not None:
                    try:
                        if lock_acquired and lock_key is not None:
                            try:
                                unlocked = lock_conn.execute(
                                    text("SELECT pg_advisory_unlock(:ns, :key)"),
                                    {"ns": lock_ns, "key": lock_key},
                                ).scalar()
                                if not unlocked:
                                    logger.warning(
                                        f"[Scan] pg_advisory_unlock({lock_ns}, {lock_key}) mengembalikan False."
                                    )
                            except Exception as e:
                                logger.warning(f"[Scan] Gagal memanggil pg_advisory_unlock: {e}")
                    finally:
                        try:
                            lock_conn.close()
                        except Exception as e:
                            logger.warning(f"[Scan] Gagal menutup lock_conn: {e}")

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

        if session.status not in (StatusPindai.siap_dipilih, StatusPindai.selesai):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Pilihan kandidat hanya dapat diubah saat status sesi 'siap_dipilih' atau 'selesai' (status saat ini: '{session.status.value}').",
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
        naming_format: Optional[List[str]] = None,
        naming_separator: Optional[str] = None,
        category_id: Optional[int] = None,
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

        if session.status not in (StatusPindai.siap_dipilih, StatusPindai.selesai):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Penarikan hanya dapat dimulai dari status 'siap_dipilih' atau 'selesai' (status saat ini: '{session.status.value}').",
            )

        source = self.db.query(ScrapingSource).filter(ScrapingSource.id == session.source_id).first() if session.source_id else None

        # Tolak tujuan 'unduh_folder' untuk sumber folder lokal (Butir 2)
        if source and source.source_type == JenisSumber.folder_lokal and destination == TujuanTarik.unduh_folder:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Tujuan 'unduh_folder' tidak didukung untuk sumber folder lokal. Berkas folder lokal sudah berada di penyimpanan lokal.",
            )

        # Validasi kategori jika diberikan (Butir 4)
        if category_id is not None:
            cat = self.db.query(Category).filter(Category.id == category_id).first()
            if not cat:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Kategori dengan ID {category_id} tidak ditemukan.",
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

        eff_format = naming_format
        eff_separator = naming_separator
        if eff_format is None and source and source.default_naming_format:
            eff_format = source.default_naming_format
            if eff_separator is None:
                eff_separator = source.default_naming_separator

        if eff_format:
            validate_naming_format(eff_format)
        if eff_separator:
            validate_naming_separator(eff_separator)

        ingest_opts = {}
        if eff_format is not None:
            ingest_opts["naming_format"] = eff_format
        if eff_separator is not None:
            ingest_opts["naming_separator"] = eff_separator

        # Buat JobIngest untuk penarikan
        trigger_name = actor_username or "manual_scan_pull"
        pull_job_type = JenisJobIngest.sinkron_folder if (source and source.source_type == JenisSumber.folder_lokal) else JenisJobIngest.scraping
        job = JobIngest(
            job_type=pull_job_type,
            source_id=session.source_id,
            category_id=category_id,
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
        session.category_id = category_id
        session.naming_format = eff_format
        session.naming_separator = eff_separator

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
                "naming_format": eff_format,
                "naming_separator": eff_separator,
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
        Menggunakan database session tersendiri dan advisory lock pada koneksi khusus (engine.connect()).
        """
        lock_conn = None
        lock_acquired = False
        lock_key = None
        lock_ns = 1396924751

        with SessionLocal() as db:
            session = db.query(ScanSession).filter(ScanSession.id == scan_id).first()
            if not session or not session.pull_job_id:
                logger.error(f"[Pull] Sesi #{scan_id} atau pull_job_id tidak valid.")
                return

            job = db.query(JobIngest).filter(JobIngest.id == session.pull_job_id).first()
            source = db.query(ScrapingSource).filter(ScrapingSource.id == session.source_id).first() if session.source_id else None
            lock_key = session.source_id or scan_id

            # Seluruh badan proses penarikan termasuk perolehan kunci berada di dalam try/finally
            try:
                # Dapatkan advisory lock khusus penarikan (magic: 1396924751) dengan toleransi retry pada koneksi khusus
                try:
                    lock_conn = engine.connect()
                    for _ in range(5):
                        try:
                            res = lock_conn.execute(
                                text("SELECT pg_try_advisory_lock(:ns, :key)"),
                                {"ns": lock_ns, "key": lock_key},
                            ).scalar()
                            lock_acquired = bool(res)
                            if lock_acquired:
                                break
                        except Exception as e:
                            logger.warning(f"[Pull] Gagal memanggil pg_try_advisory_lock: {e}")
                            lock_acquired = True
                            break
                        time.sleep(0.5)
                except Exception as e:
                    logger.warning(f"[Pull] Gagal membuka koneksi dedicated lock: {e}")
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

                job.status = StatusJobIngest.berjalan
                job.started_at = datetime.now(timezone.utc)
                session.updated_at = datetime.now(timezone.utc)
                db.commit()

                # Gunakan crawler untuk mengunduh berkas
                try:
                    crawler = (
                        get_crawler(
                            settings,
                            source_url=session.start_url,
                            crawler_adapter=session.crawler_adapter or (source.crawler_adapter if source else None),
                        )
                        or SimpleHttpCrawler(allow_private=settings.crawl_allow_private_networks)
                    )
                except TypeError:
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

                    # 1. Unduh atau baca berkas
                    fetched = None
                    if (source and source.source_type == JenisSumber.folder_lokal) or cand.size_source == "local":
                        try:
                            local_path = None
                            if cand.url.startswith("file://"):
                                p_clean = urlsplit(cand.url).path
                                local_path = Path(url2pathname(p_clean))
                            elif source and cand.source_path:
                                local_path = Path(source.url) / cand.source_path
                            else:
                                local_path = Path(cand.url)

                            f_bytes = local_path.read_bytes()
                            fetched = FetchedFile(
                                content=f_bytes,
                                filename=cand.filename,
                                content_type="application/pdf",
                                final_url=cand.url,
                            )
                        except Exception as exc:
                            failure = IngestFailure(
                                job_id=job.id,
                                failure_type=JenisKegagalan.sumber_tidak_dapat_diakses,
                                reason_code="sumber_tidak_dapat_diakses",
                                original_filename=cand.filename,
                                source_url=cand.url,
                                message=f"Gagal membaca berkas lokal: {exc}",
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
                            cand.pull_outcome = "gagal"
                            cand.failure_id = failure.id
                            cand.message = str(exc)
                            job.failed_count += 1
                            job.processed_count += 1
                            if job.processed_count % settings.job_progress_commit_every == 0:
                                db.commit()
                            continue
                    else:
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
                            cand.pull_outcome = "gagal"
                            cand.failure_id = failure.id
                            cand.message = str(fle)
                            job.failed_count += 1
                            job.processed_count += 1
                            if job.processed_count % settings.job_progress_commit_every == 0:
                                db.commit()
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
                            cand.pull_outcome = "gagal"
                            cand.failure_id = failure.id
                            cand.message = str(exc)
                            job.failed_count += 1
                            job.processed_count += 1
                            if job.processed_count % settings.job_progress_commit_every == 0:
                                db.commit()
                            continue

                    # 2. Proses berkas sesuai tujuan
                    if session.destination == TujuanTarik.knowledge_base:
                        norm_source_url = cand.url if cand.url.startswith("file://") else normalize_url(cand.url)
                        item = IngestItem(
                            filename=fetched.filename,
                            content=fetched.content,
                            source_url=norm_source_url,
                        )
                        doc_meta = DocumentMetadataInput(
                            title=cand.document_title or cand.filename,
                            regulation_number=cand.regulation_number,
                            regulation_type=cand.regulation_type,
                            release_date=cand.release_date,
                            bidang=cand.bidang,
                            status_keberlakuan=cand.status_keberlakuan,
                        )
                        opts = IngestOptions(
                            access_classification=source.default_access_classification if source else KlasifikasiAkses.publik,
                            document_role=source.default_document_role if source else PeranDokumen.corpus_eksisting,
                            category_id=session.category_id or (job.category_id if job else None),
                            metadata=doc_meta,
                            naming_format=session.naming_format,
                            naming_separator=session.naming_separator,
                        )
                        res = ingest_svc.ingest_one(job, item, opts, suppress_failure_hooks=False)
                        
                        outcome_indonesia_map = {
                            ItemOutcome.success: "berhasil",
                            ItemOutcome.duplicate: "duplikat",
                            ItemOutcome.failed: "gagal",
                            ItemOutcome.requeued: "antrian",
                        }
                        cand.pull_outcome = outcome_indonesia_map.get(res.outcome, res.outcome.value)
                        cand.document_id = res.document_id
                        cand.message = res.message

                        if res.outcome == ItemOutcome.success:
                            job.success_count += 1
                        elif res.outcome == ItemOutcome.duplicate:
                            job.duplicate_count += 1
                        else:
                            job.failed_count += 1
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
                            cand.pull_outcome = "diunduh"
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
                            cand.pull_outcome = "gagal"
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
                elif job.success_count == 0 and job.duplicate_count == 0 and job.failed_count > 0:
                    session.status = StatusPindai.selesai
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
                logger.info(f"[Pull] Sesi #{session.id} penarikan selesai: {job.success_count} success, {job.duplicate_count} duplicate, {job.failed_count} failed.")

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
                if lock_conn is not None:
                    try:
                        if lock_acquired and lock_key is not None:
                            try:
                                unlocked = lock_conn.execute(
                                    text("SELECT pg_advisory_unlock(:ns, :key)"),
                                    {"ns": lock_ns, "key": lock_key},
                                ).scalar()
                                if not unlocked:
                                    logger.warning(
                                        f"[Pull] pg_advisory_unlock({lock_ns}, {lock_key}) mengembalikan False."
                                    )
                            except Exception as e:
                                logger.warning(f"[Pull] Gagal memanggil pg_advisory_unlock: {e}")
                    finally:
                        try:
                            lock_conn.close()
                        except Exception as e:
                            logger.warning(f"[Pull] Gagal menutup lock_conn: {e}")

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
                ScanCandidate.pull_outcome.in_(["diunduh", "downloaded"]),
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
                    if session.naming_format:
                        input_data = NamingInput(
                            title=None,
                            original_filename=cand.filename,
                        )
                        base_name = build_standard_filename(
                            input_data,
                            naming_format=session.naming_format,
                            naming_separator=session.naming_separator or " ",
                        )
                    else:
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
                existing.document_title = cand_in.document_title
                existing.detail_url = cand_in.detail_url
                existing.final_url = cand_in.final_url
                existing.doc_kind = cand_in.doc_kind or "utama"
                existing.regulation_number = cand_in.regulation_number
                existing.regulation_type = cand_in.regulation_type
                existing.bidang = cand_in.bidang
                existing.sub_bidang = cand_in.sub_bidang
                existing.release_date = cand_in.release_date
                existing.regulation_year = getattr(cand_in, "regulation_year", None)
                existing.status_keberlakuan = getattr(cand_in, "status_keberlakuan", "tidak_diketahui") or "tidak_diketahui"
                existing.size_source = cand_in.size_source or "unknown"
                existing.source_path = cand_in.source_path
            else:
                c_yr = getattr(cand_in, "regulation_year", None) or extract_regulation_year(
                    regulation_number=cand_in.regulation_number,
                    title=cand_in.document_title,
                    filename=cand_in.filename,
                    release_date=cand_in.release_date,
                )
                new_cand = ScanCandidate(
                    scan_id=scan_id,
                    url=norm_url,
                    url_hash=url_hash,
                    filename=cand_in.filename,
                    size_bytes=cand_in.size_bytes,
                    found_on_page=cand_in.found_on_page,
                    depth=cand_in.depth,
                    document_title=cand_in.document_title,
                    detail_url=cand_in.detail_url,
                    final_url=cand_in.final_url,
                    doc_kind=cand_in.doc_kind or "utama",
                    regulation_number=cand_in.regulation_number,
                    regulation_type=cand_in.regulation_type,
                    bidang=cand_in.bidang,
                    sub_bidang=cand_in.sub_bidang,
                    release_date=cand_in.release_date,
                    effective_date=getattr(cand_in, "effective_date", None),
                    regulation_year=c_yr,
                    match_warning=getattr(cand_in, "match_warning", None),
                    status_keberlakuan=getattr(cand_in, "status_keberlakuan", "tidak_diketahui") or "tidak_diketahui",
                    size_source=cand_in.size_source or "unknown",
                    source_path=cand_in.source_path,
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


def recover_stuck_scan_sessions(db: Session, stuck_minutes: int = 15, is_startup: bool = False) -> int:
    """
    Memulihkan sesi pemindaian dan job penarikan yang macet saat startup server atau batas waktu terlampaui.
    - is_startup=True: memulihkan semua sesi 'memindai' / 'menarik' yang tidak punya proses hidup.
    - is_startup=False: memulihkan sesi tanpa pembaruan (updated_at) selama > stuck_minutes (default 15 menit).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stuck_minutes)
    query = db.query(ScanSession).filter(
        ScanSession.status.in_([StatusPindai.memindai, StatusPindai.menarik])
    )
    if not is_startup:
        last_active = func.coalesce(ScanSession.updated_at, ScanSession.started_at, ScanSession.created_at)
        query = query.filter(last_active < cutoff)

    stuck_sessions = query.all()

    recovered = 0
    err_msg = (
        "Dihentikan karena server dimulai ulang."
        if is_startup
        else f"Dihentikan karena server dimulai ulang. Batas waktu aktivitas terlampaui (> {stuck_minutes} menit)."
    )

    for s in stuck_sessions:
        s.status = StatusPindai.gagal
        s.error_message = err_msg
        s.finished_at = datetime.now(timezone.utc)

        source = db.query(ScrapingSource).filter(ScrapingSource.id == s.source_id).first() if s.source_id else None
        if source:
            source.last_run_status = "gagal"
            source.last_run_message = err_msg

        if s.pull_job_id:
            job = db.query(JobIngest).filter(JobIngest.id == s.pull_job_id).first()
            if job and job.status in (StatusJobIngest.antrian, StatusJobIngest.berjalan):
                job.status = StatusJobIngest.gagal
                job.finished_at = datetime.now(timezone.utc)

        recovered += 1

    # Jika startup, pulihkan juga job scraping/tarik yang tertinggal di status antrian/berjalan
    if is_startup:
        orphan_jobs = (
            db.query(JobIngest)
            .filter(
                JobIngest.job_type == JenisJobIngest.scraping,
                JobIngest.status.in_([StatusJobIngest.antrian, StatusJobIngest.berjalan]),
            )
            .all()
        )
        for oj in orphan_jobs:
            oj.status = StatusJobIngest.gagal
            oj.finished_at = datetime.now(timezone.utc)

    if recovered > 0:
        db.commit()
        logger.info(f"Berhasil memulihkan {recovered} sesi pemindaian yang macet (is_startup={is_startup}).")

    return recovered
