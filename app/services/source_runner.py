"""
app/services/source_runner.py
[US-16, FR-SCR-05] Layanan eksekutor sinkronisasi sumber dokumen folder lokal dan perayap.
"""
from datetime import datetime, timezone, timedelta
import logging
from pathlib import Path
from typing import Optional, List

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, engine
from app.models.enums import (
    JenisJobIngest,
    JenisKegagalan,
    JenisSumber,
    StatusJobIngest,
)
from app.models.category import Category
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.models.scraping_source import ScrapingSource
from app.models.source_file import SourceFile
from app.services.audit_service import record_audit, RUN_SOURCE
from app.services.folder_connector import list_pdf_files, FolderAccessError
from app.services.ingest_service import (
    IngestService,
    IngestItem,
    IngestOptions,
    ItemOutcome,
    ItemResult,
)
from app.services.storage_service import get_storage_service

logger = logging.getLogger("hero")

SOURCE_LOCK_NAMESPACE = 0x534F5552  # 'SOUR' in hex


class SourceRunner:
    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def start_run(
        self,
        source_id: int,
        actor_user_id: Optional[int] = None,
        actor_username: Optional[str] = None,
        ip_address: Optional[str] = None,
        naming_format: Optional[List[str]] = None,
        naming_separator: Optional[str] = None,
        category_id: Optional[int] = None,
    ) -> JobIngest:
        """
        Validasi dan inisialisasi job eksekusi sumber.
        """
        if self.db is None:
            raise RuntimeError("Session database diperlukan untuk start_run.")

        source = self.db.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Situs sumber dengan ID {source_id} tidak ditemukan.",
            )

        if not source.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sumber nonaktif.",
            )

        if source.source_type == JenisSumber.situs_web:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Situs web dijalankan melalui alur pindai: POST /api/v1/scans.",
            )

        if source.source_type == JenisSumber.onedrive_public:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sumber OneDrive publik dijalankan melalui alur pindai: POST /api/v1/scans.",
            )

        # Validasi kategori jika diberikan
        if category_id is not None:
            cat = self.db.query(Category).filter(Category.id == category_id).first()
            if not cat:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Kategori dengan ID {category_id} tidak ditemukan.",
                )

        # Cek apakah ada job yang sedang berjalan/antrian untuk sumber ini
        running_job = (
            self.db.query(JobIngest)
            .filter(
                JobIngest.source_id == source_id,
                JobIngest.status.in_([StatusJobIngest.antrian, StatusJobIngest.berjalan]),
            )
            .first()
        )
        if running_job:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sumber sedang diproses oleh job ID {running_job.id}.",
            )

        # Buat Job baru
        job = JobIngest(
            job_type=JenisJobIngest.sinkron_folder,
            source_id=source.id,
            category_id=category_id,
            source_ref=source.name[:255] if source.name else None,
            triggered_by=actor_username or "manual_run",
            status=StatusJobIngest.antrian,
            success_count=0,
            duplicate_count=0,
            failed_count=0,
            total_found=None,
            processed_count=0,
            skipped_count=0,
        )
        self.db.add(job)
        self.db.flush()

        source.last_run_status = "berjalan"
        source.last_job_id = job.id

        record_audit(
            self.db,
            action=RUN_SOURCE,
            user_id=actor_user_id,
            target_resource=f"scraping_source:{source.id}",
            detail={"job_id": job.id, "source_type": source.source_type.value},
            ip_address=ip_address,
            commit=False,
        )

        self.db.commit()
        self.db.refresh(job)
        return job

    def execute(
        self,
        job_id: int,
        naming_format: Optional[List[str]] = None,
        naming_separator: Optional[str] = None,
    ) -> None:
        """
        Eksekusi pemindaian folder lokal dan ingest berkas-berkasnya.
        Dijalankan di BackgroundTasks atau secara sinkron (wait=true).
        Membuat sesi database sendiri dan memastikan penutupan di blok finally.
        """
        db = SessionLocal()
        lock_conn = None
        lock_acquired = False
        source_id: Optional[int] = None
        try:
            job = db.query(JobIngest).filter(JobIngest.id == job_id).first()
            if not job:
                logger.error("[SourceRunner] Job ID %s tidak ditemukan.", job_id)
                return

            source_id = job.source_id
            if not source_id:
                logger.error("[SourceRunner] Job ID %s tidak memiliki source_id.", job_id)
                job.status = StatusJobIngest.gagal
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                return

            # Coba ambil advisory lock di PostgreSQL pada koneksi khusus
            try:
                lock_conn = engine.connect()
                lock_res = lock_conn.execute(
                    text("SELECT pg_try_advisory_lock(:ns, :sid)"),
                    {"ns": SOURCE_LOCK_NAMESPACE, "sid": source_id},
                ).scalar()
                lock_acquired = bool(lock_res)
            except Exception as e:
                logger.warning("[SourceRunner] Gagal mencoba advisory lock: %s", e)
                lock_acquired = True

            if not lock_acquired:
                logger.warning("[SourceRunner] Lock gagal didapatkan untuk source_id %s.", source_id)
                job.status = StatusJobIngest.gagal
                job.finished_at = datetime.now(timezone.utc)
                source = db.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
                if source:
                    source.last_run_status = "gagal"
                    source.last_run_message = "Sumber sedang diproses oleh eksekusi lain."
                    source.last_run_at = datetime.now(timezone.utc)
                db.commit()
                return

            source = db.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
            if not source:
                job.status = StatusJobIngest.gagal
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                return

            # Update job ke status berjalan
            job.status = StatusJobIngest.berjalan
            job.started_at = datetime.now(timezone.utc)
            db.commit()

            # Pindai direktori folder
            try:
                pdf_files = list_pdf_files(
                    Path(source.url),
                    recursive=source.recursive,
                    max_files=settings.local_source_max_files_per_run,
                )
            except FolderAccessError as fae:
                err_msg = str(fae)
                logger.warning("[SourceRunner] FolderAccessError pada source %s: %s", source_id, err_msg)
                job.status = StatusJobIngest.gagal
                job.finished_at = datetime.now(timezone.utc)

                # Catat ke ingest_failures
                failure = IngestFailure(
                    job_id=job.id,
                    original_filename=source.url,
                    source_url=f"folder://{source.id}",
                    failure_type=JenisKegagalan.sumber_tidak_dapat_diakses,
                    reason_code="sumber_tidak_dapat_diakses",
                    message=err_msg,
                    is_retryable=False,
                )
                db.add(failure)

                source.last_run_status = "gagal"
                source.last_run_message = err_msg
                source.last_run_at = datetime.now(timezone.utc)
                db.commit()
                return

            job.total_found = len(pdf_files)
            db.commit()

            skipped_count = 0
            processed_count = 0
            results: List[ItemResult] = []
            storage = get_storage_service()
            ingest_svc = IngestService(db, storage)

            # Tentukan naming_format dan naming_separator efektif (override di run > default sumber)
            effective_naming_format = naming_format if naming_format is not None else (source.default_naming_format if source else None)
            effective_naming_separator = naming_separator if naming_separator is not None else (source.default_naming_separator if source else None)

            for entry in pdf_files:
                # Cek apakah berkas sudah ada di source_files dan tidak berubah
                src_file = (
                    db.query(SourceFile)
                    .filter(
                        SourceFile.source_id == source.id,
                        SourceFile.relative_path == entry.relative_path,
                    )
                    .first()
                )

                mtime_match = False
                if src_file is not None and src_file.mtime is not None:
                    try:
                        mtime_match = abs(src_file.mtime.timestamp() - entry.mtime.timestamp()) < 1.0
                    except Exception:
                        mtime_match = False

                if (
                    src_file is not None
                    and src_file.size_bytes == entry.size_bytes
                    and mtime_match
                    and src_file.last_outcome in ("success", "duplicate", "skipped_unchanged")
                ):
                    # Berkas tidak berubah: lewati tanpa membaca isi
                    src_file.last_seen_job_id = job.id
                    src_file.last_outcome = "skipped_unchanged"
                    skipped_count += 1
                    processed_count += 1
                    job.processed_count = processed_count
                    job.skipped_count = skipped_count
                    if processed_count % settings.job_progress_commit_every == 0:
                        db.commit()
                    continue

                # Baca isi berkas
                try:
                    content = entry.absolute_path.read_bytes()
                except (PermissionError, OSError) as read_err:
                    err_msg = f"Gagal membaca berkas: {read_err}"
                    logger.warning("[SourceRunner] %s (%s)", err_msg, entry.absolute_path)

                    fail_entry = IngestFailure(
                        job_id=job.id,
                        original_filename=entry.relative_path,
                        source_url=f"folder://{source.id}/{entry.relative_path}",
                        failure_type=JenisKegagalan.sumber_tidak_dapat_diakses,
                        reason_code="sumber_tidak_dapat_diakses",
                        message=err_msg,
                        is_retryable=False,
                    )
                    db.add(fail_entry)

                    # Upsert source_files
                    if src_file is None:
                        src_file = SourceFile(
                            source_id=source.id,
                            relative_path=entry.relative_path,
                            size_bytes=entry.size_bytes,
                            mtime=entry.mtime,
                            file_hash=None,
                            document_id=None,
                            last_outcome="failed",
                            last_seen_job_id=job.id,
                        )
                        db.add(src_file)
                    else:
                        src_file.size_bytes = entry.size_bytes
                        src_file.mtime = entry.mtime
                        src_file.last_outcome = "failed"
                        src_file.last_seen_job_id = job.id

                    res = ItemResult(
                        filename=entry.relative_path,
                        outcome=ItemOutcome.failed,
                        message=err_msg,
                        reason_code="sumber_tidak_dapat_diakses",
                    )
                    results.append(res)
                    processed_count += 1
                    job.processed_count = processed_count
                    if processed_count % settings.job_progress_commit_every == 0:
                        db.commit()
                    continue

                # Ingest berkas
                item = IngestItem(
                    filename=entry.absolute_path.name,
                    content=content,
                    source_url=f"folder://{source.id}/{entry.relative_path}",
                )
                options = IngestOptions(
                    access_classification=source.default_access_classification,
                    document_role=source.default_document_role,
                    naming_format=effective_naming_format,
                    naming_separator=effective_naming_separator,
                    category_id=job.category_id,
                )
                res = ingest_svc.ingest_one(job, item, options)
                results.append(res)

                # Upsert record source_files
                doc_id = res.document_id if res.outcome in (ItemOutcome.success, ItemOutcome.duplicate) else None
                outcome_str = res.outcome.value
                if src_file is None:
                    src_file = SourceFile(
                        source_id=source.id,
                        relative_path=entry.relative_path,
                        size_bytes=entry.size_bytes,
                        mtime=entry.mtime,
                        file_hash=res.file_hash,
                        document_id=doc_id,
                        last_outcome=outcome_str,
                        last_seen_job_id=job.id,
                    )
                    db.add(src_file)
                else:
                    src_file.size_bytes = entry.size_bytes
                    src_file.mtime = entry.mtime
                    src_file.file_hash = res.file_hash
                    src_file.document_id = doc_id
                    src_file.last_outcome = outcome_str
                    src_file.last_seen_job_id = job.id

                processed_count += 1
                job.processed_count = processed_count
                if processed_count % settings.job_progress_commit_every == 0:
                    db.commit()

            # Selesaikan Job
            ingest_svc.finish_job(job, results)
            job.skipped_count = skipped_count
            job.processed_count = processed_count

            # Ringkasan status sumber
            source.last_run_at = datetime.now(timezone.utc)
            source.last_run_status = job.status.value

            trunc_note = ""
            if len(pdf_files) >= settings.local_source_max_files_per_run:
                trunc_note = f" (dipotong ke {settings.local_source_max_files_per_run} berkas)"

            source.last_run_message = (
                f"Ditemukan: {job.total_found}{trunc_note}, "
                f"Berhasil: {job.success_count}, "
                f"Duplikat: {job.duplicate_count}, "
                f"Dilewati: {skipped_count}, "
                f"Gagal: {job.failed_count}"
            )
            db.commit()

        except Exception as exc:
            logger.exception("[SourceRunner] Terjadi kesalahan tak terduga saat sinkronisasi job %s: %s", job_id, exc)
            try:
                job = db.query(JobIngest).filter(JobIngest.id == job_id).first()
                if job:
                    job.status = StatusJobIngest.gagal
                    job.finished_at = datetime.now(timezone.utc)
                if source_id:
                    source = db.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
                    if source:
                        source.last_run_status = "gagal"
                        source.last_run_message = f"Terjadi kesalahan tak terduga: {exc}"
                        source.last_run_at = datetime.now(timezone.utc)
                db.commit()
            except Exception:
                db.rollback()
        finally:
            if lock_conn is not None:
                try:
                    if lock_acquired and source_id:
                        try:
                            unlocked = lock_conn.execute(
                                text("SELECT pg_advisory_unlock(:ns, :sid)"),
                                {"ns": SOURCE_LOCK_NAMESPACE, "sid": source_id},
                            ).scalar()
                            if not unlocked:
                                logger.warning(
                                    f"[SourceRunner] pg_advisory_unlock({SOURCE_LOCK_NAMESPACE}, {source_id}) mengembalikan False."
                                )
                        except Exception as e:
                            logger.warning(f"[SourceRunner] Gagal memanggil pg_advisory_unlock: {e}")
                finally:
                    try:
                        lock_conn.close()
                    except Exception:
                        pass
            db.close()


def recover_stuck_folder_jobs(db: Session) -> int:
    """
    Pemulihan job sinkron_folder yang macet (> 60 menit status berjalan/antrian).
    Dipanggil saat startup aplikasi atau saat pengujian.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)
    stuck_jobs = (
        db.query(JobIngest)
        .filter(
            JobIngest.job_type == JenisJobIngest.sinkron_folder,
            JobIngest.status.in_([StatusJobIngest.berjalan, StatusJobIngest.antrian]),
            JobIngest.started_at < cutoff,
        )
        .all()
    )
    for job in stuck_jobs:
        job.status = StatusJobIngest.gagal
        job.finished_at = datetime.now(timezone.utc)
        if job.source_id:
            source = db.query(ScrapingSource).filter(ScrapingSource.id == job.source_id).first()
            if source and source.last_job_id == job.id:
                source.last_run_status = "gagal"
                source.last_run_message = "Dihentikan karena server dimulai ulang."
                source.last_run_at = datetime.now(timezone.utc)
    if stuck_jobs:
        db.commit()
        logger.info("[SourceRunner] Memulihkan %d job sinkron_folder yang macet.", len(stuck_jobs))
    return len(stuck_jobs)
