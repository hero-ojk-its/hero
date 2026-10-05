"""
app/services/failure_service.py
Layanan pencatatan log kegagalan dan pengelolaan antrian retry ingest dokumen.
"""
from dataclasses import dataclass
from datetime import datetime, timezone, date
import logging
from typing import Optional, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import desc
from fastapi import HTTPException, status

from app.models.enums import (
    JenisKegagalan,
    StatusTindakLanjut,
    JenisJobIngest,
    StatusJobIngest,
    KlasifikasiAkses,
    PeranDokumen,
)
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.services.file_validation import (
    fingerprint,
    sanitize_filename,
    validate_pdf,
)
from app.services.storage_service import StorageService, get_storage_service
from app.services.audit_service import record_audit, RETRY_FAILURE, UPDATE_FAILURE

logger = logging.getLogger("hero")


class FailureNotRetryableError(Exception):
    """Exception yang dilempar ketika item kegagalan tidak dapat di-retry."""
    pass


@dataclass
class RetryOverrides:
    category_id: Optional[int] = None
    access_classification: Optional[KlasifikasiAkses] = None
    document_role: Optional[PeranDokumen] = None


@dataclass
class RetryResult:
    failure: IngestFailure
    item_result: any
    job: JobIngest


# reason_code -> (failure_type, save_quarantine, is_retryable, initial_status)
REASON_CODE_MAP = {
    "format_tidak_didukung": (
        JenisKegagalan.format_tidak_didukung,
        False,
        False,
        StatusTindakLanjut.belum_ditangani,
    ),
    "berkas_kosong": (
        JenisKegagalan.format_tidak_didukung,
        False,
        False,
        StatusTindakLanjut.belum_ditangani,
    ),
    "ukuran_melebihi_batas": (
        JenisKegagalan.format_tidak_didukung,
        False,
        False,
        StatusTindakLanjut.belum_ditangani,
    ),
    "duplikat": (
        JenisKegagalan.duplikat,
        False,
        False,
        StatusTindakLanjut.diabaikan,
    ),
    "kategori_tidak_ditemukan": (
        JenisKegagalan.metadata_tidak_lengkap,
        True,
        True,
        StatusTindakLanjut.belum_ditangani,
    ),
    "kesalahan_internal": (
        JenisKegagalan.kesalahan_internal,
        True,
        True,
        StatusTindakLanjut.belum_ditangani,
    ),
}


class FailureService:
    def __init__(self, db: Session, storage: StorageService):
        self.db = db
        self.storage = storage

    def _serialize_options(self, options) -> dict:
        """Helper untuk serialisasi IngestOptions ke format JSON."""
        opts_dict = {
            "access_classification": (
                options.access_classification.value
                if hasattr(options.access_classification, "value")
                else str(options.access_classification)
            ),
            "document_role": (
                options.document_role.value
                if hasattr(options.document_role, "value")
                else str(options.document_role)
            ),
            "category_id": options.category_id,
        }
        if options.metadata:
            opts_dict["metadata"] = {
                "title": options.metadata.title,
                "regulation_number": options.metadata.regulation_number,
                "regulation_type": options.metadata.regulation_type,
                "release_date": (
                    options.metadata.release_date.isoformat()
                    if options.metadata.release_date
                    else None
                ),
            }
        return opts_dict

    def record_failure(
        self,
        job: JobIngest,
        item,
        result,
        options,
    ) -> Optional[IngestFailure]:
        """
        Mencatat entri kegagalan baru dan menyimpan berkas ke karantina jika retryable.
        Kegagalan pencatatan atau penyimpanan karantina tidak menggagalkan batch.
        """
        try:
            reason = result.reason_code or "kesalahan_internal"
            if reason in REASON_CODE_MAP:
                failure_type, save_quarantine, is_retryable, initial_status = REASON_CODE_MAP[reason]
            else:
                # Pola fallback: jika PDF valid, boleh karantina & retry
                is_valid_pdf = False
                try:
                    if item.content:
                        validate_pdf(item.filename, item.content)
                        is_valid_pdf = True
                except Exception:
                    is_valid_pdf = False
                failure_type = JenisKegagalan.kesalahan_internal
                save_quarantine = is_valid_pdf
                is_retryable = is_valid_pdf
                initial_status = StatusTindakLanjut.belum_ditangani

            clean_name = sanitize_filename(item.filename)
            file_hash = None
            file_size = 0
            if item.content:
                fp = fingerprint(item.content)
                file_hash = fp.sha256
                file_size = fp.size_bytes

            quarantine_path = None
            if save_quarantine and is_retryable and item.content:
                try:
                    hash12 = file_hash[:12] if file_hash else "000000000000"
                    quarantine_path = self.storage.save_pdf(
                        item.content,
                        filename_hint=f"{hash12}_{clean_name}",
                        subdir="quarantine",
                    )
                except Exception as q_exc:
                    logger.exception(
                        "Gagal menulis berkas karantina untuk '%s': %s",
                        item.filename,
                        q_exc,
                    )
                    quarantine_path = None
                    is_retryable = False
                    result.message = f"{result.message} (Gagal menyimpan ke karantina: {str(q_exc)})"

            opts_dict = self._serialize_options(options)

            failure = IngestFailure(
                job_id=job.id,
                original_filename=(item.filename or "dokumen.pdf")[:255],
                source_url=item.source_url,
                failure_type=failure_type,
                reason_code=reason[:50],
                message=result.message,
                is_retryable=is_retryable,
                quarantine_path=quarantine_path,
                file_hash=file_hash,
                file_size_bytes=file_size,
                duplicate_of_document_id=result.duplicate_of_document_id,
                ingest_options=opts_dict,
                follow_up_status=initial_status,
                attempt_count=0,
            )
            self.db.add(failure)
            self.db.commit()
            self.db.refresh(failure)
            return failure
        except Exception as exc:
            logger.exception("Gagal mencatat kegagalan untuk item '%s': %s", getattr(item, "filename", "unknown"), exc)
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def record_duplicate(
        self,
        job: JobIngest,
        item,
        result,
        options,
    ) -> Optional[IngestFailure]:
        """
        Mencatat dokumen duplikat ke tabel ingest_failures dengan status awal 'diabaikan'.
        """
        try:
            clean_name = sanitize_filename(item.filename)
            file_hash = None
            file_size = 0
            if item.content:
                fp = fingerprint(item.content)
                file_hash = fp.sha256
                file_size = fp.size_bytes

            opts_dict = self._serialize_options(options)

            failure = IngestFailure(
                job_id=job.id,
                original_filename=(item.filename or "dokumen.pdf")[:255],
                source_url=item.source_url,
                failure_type=JenisKegagalan.duplikat,
                reason_code="duplikat",
                message=result.message,
                is_retryable=False,
                quarantine_path=None,
                file_hash=file_hash,
                file_size_bytes=file_size,
                duplicate_of_document_id=result.duplicate_of_document_id,
                ingest_options=opts_dict,
                follow_up_status=StatusTindakLanjut.diabaikan,
                attempt_count=0,
            )
            self.db.add(failure)
            self.db.commit()
            self.db.refresh(failure)
            return failure
        except Exception as exc:
            logger.exception("Gagal mencatat duplikat untuk item '%s': %s", getattr(item, "filename", "unknown"), exc)
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def list_failures(
        self,
        *,
        job_id: Optional[int] = None,
        failure_type: Optional[JenisKegagalan] = None,
        follow_up_status: Optional[str] = None,
        include_duplicates: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[int, List[IngestFailure]]:
        """
        Mengambil daftar kegagalan dengan filter dan paginasi.
        """
        query = self.db.query(IngestFailure)

        if job_id is not None:
            query = query.filter(IngestFailure.job_id == job_id)

        if failure_type is not None:
            query = query.filter(IngestFailure.failure_type == failure_type)
        elif not include_duplicates:
            query = query.filter(IngestFailure.failure_type != JenisKegagalan.duplikat)

        if follow_up_status is not None:
            if follow_up_status != "all":
                query = query.filter(IngestFailure.follow_up_status == follow_up_status)
        else:
            # Default belum_ditangani
            query = query.filter(IngestFailure.follow_up_status == StatusTindakLanjut.belum_ditangani)

        total = query.count()
        items = query.order_by(desc(IngestFailure.id)).offset(skip).limit(limit).all()
        return total, items

    def update_status(
        self,
        failure_id: int,
        status: StatusTindakLanjut,
        note: Optional[str] = None,
        actor_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> IngestFailure:
        """
        Mengubah status tindak lanjut kegagalan (hanya belum_ditangani <-> diabaikan).
        """
        failure = self.db.query(IngestFailure).filter(IngestFailure.id == failure_id).first()
        if not failure:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Data kegagalan ID {failure_id} tidak ditemukan.",
            )

        if status not in (StatusTindakLanjut.belum_ditangani, StatusTindakLanjut.diabaikan):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Status hanya boleh diubah menjadi 'belum_ditangani' atau 'diabaikan'. Status 'diproses_ulang' hanya dapat diubah melalui proses retry.",
            )

        failure.follow_up_status = status
        if note is not None:
            failure.handling_note = note
        if actor_user_id is not None:
            failure.handled_by_user_id = actor_user_id

        record_audit(
            self.db,
            action=UPDATE_FAILURE,
            user_id=actor_user_id,
            target_resource=f"ingest_failure:{failure.id}",
            ip_address=ip_address,
            commit=False,
        )
        self.db.commit()
        self.db.refresh(failure)
        return failure

    def retry(
        self,
        failure_id: int,
        overrides: Optional[RetryOverrides] = None,
        actor_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> RetryResult:
        """
        Memproses ulang dokumen dari karantina.
        """
        failure = self.db.query(IngestFailure).filter(IngestFailure.id == failure_id).first()
        if not failure:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Data kegagalan ID {failure_id} tidak ditemukan.",
            )

        if not failure.is_retryable or failure.follow_up_status == StatusTindakLanjut.diproses_ulang:
            raise FailureNotRetryableError(
                "Kegagalan ini tidak dapat diproses ulang (tidak retryable atau sudah diproses ulang)."
            )

        from app.models.document import Document
        from app.models.enums import StatusPemrosesan
        from app.services.ingest_service import (
            IngestService,
            IngestItem,
            IngestOptions,
            DocumentMetadataInput,
            ItemOutcome,
        )

        # Kasus khusus retry kegagalan ekstraksi Data/ML
        if failure.failure_type in (JenisKegagalan.ekstraksi_gagal, JenisKegagalan.ocr_gagal) and failure.document_id is not None:
            doc = self.db.query(Document).filter(Document.id == failure.document_id).first()
            if not doc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Dokumen ID {failure.document_id} terkait kegagalan ini tidak ditemukan.",
                )

            # Requeue dokumen
            doc.processing_status = StatusPemrosesan.diterima
            doc.extraction_claimed_at = None

            failure.follow_up_status = StatusTindakLanjut.diproses_ulang
            failure.attempt_count += 1
            failure.last_retry_at = datetime.now(timezone.utc)
            if actor_user_id is not None:
                failure.handled_by_user_id = actor_user_id

            record_audit(
                self.db,
                action=RETRY_FAILURE,
                user_id=actor_user_id,
                target_resource=f"ingest_failure:{failure.id}",
                detail={"outcome": "requeued", "document_id": doc.id},
                ip_address=ip_address,
                commit=False,
            )
            self.db.commit()
            self.db.refresh(failure)

            @dataclass
            class RequeueResult:
                outcome: ItemOutcome = ItemOutcome.requeued
                document_id: int = doc.id
                message: str = f"Dokumen ID {doc.id} berhasil di-antrekan ulang untuk ekstraksi."

            return RetryResult(
                failure=failure,
                item_result=RequeueResult(),
                job=failure.job,
            )

        opts_raw = failure.ingest_options or {}
        fetch_url = opts_raw.get("fetch_url")

        if fetch_url:
            from app.crawlers.registry import get_crawler
            from app.crawlers.simple_http import SimpleHttpCrawler
            from app.config import settings
            crawler = get_crawler(settings) or SimpleHttpCrawler(allow_private=settings.crawl_allow_private_networks)
            try:
                fetched = crawler.fetch(fetch_url, max_bytes=settings.max_upload_bytes)
                content = fetched.content
            except Exception as e:
                failure.attempt_count += 1
                failure.last_retry_at = datetime.now(timezone.utc)
                self.db.commit()
                raise FailureNotRetryableError(f"Gagal mengunduh ulang berkas dari {fetch_url}: {str(e)}")
        elif not failure.quarantine_path or not self.storage.exists(failure.quarantine_path):
            failure.is_retryable = False
            self.db.commit()
            raise FailureNotRetryableError("Berkas karantina tidak ditemukan di penyimpanan.")
        else:
            try:
                content = self.storage.read_pdf(failure.quarantine_path)
            except Exception as e:
                failure.is_retryable = False
                self.db.commit()
                raise FailureNotRetryableError(f"Gagal membaca berkas karantina: {str(e)}")

        # Import IngestService di dalam method untuk menghindari circular import
        from app.services.ingest_service import (
            IngestService,
            IngestItem,
            IngestOptions,
            DocumentMetadataInput,
            ItemOutcome,
        )

        opts_raw = failure.ingest_options or {}
        acc_class_val = opts_raw.get("access_classification", KlasifikasiAkses.non_publik.value)
        doc_role_val = opts_raw.get("document_role", PeranDokumen.corpus_eksisting.value)
        cat_id = opts_raw.get("category_id")

        meta_dict = opts_raw.get("metadata")
        meta_input = None
        if meta_dict:
            rel_date = None
            if meta_dict.get("release_date"):
                try:
                    rel_date = date.fromisoformat(meta_dict["release_date"])
                except Exception:
                    pass
            meta_input = DocumentMetadataInput(
                title=meta_dict.get("title"),
                regulation_number=meta_dict.get("regulation_number"),
                regulation_type=meta_dict.get("regulation_type"),
                release_date=rel_date,
            )

        # Overrides jika ada
        if overrides:
            if overrides.access_classification:
                acc_class_val = (
                    overrides.access_classification.value
                    if hasattr(overrides.access_classification, "value")
                    else str(overrides.access_classification)
                )
            if overrides.document_role:
                doc_role_val = (
                    overrides.document_role.value
                    if hasattr(overrides.document_role, "value")
                    else str(overrides.document_role)
                )
            if overrides.category_id is not None:
                cat_id = overrides.category_id

        options = IngestOptions(
            access_classification=KlasifikasiAkses(acc_class_val),
            document_role=PeranDokumen(doc_role_val),
            category_id=cat_id,
            metadata=meta_input,
        )
        # Catat opsi efektif (termasuk override) agar riwayat dapat diaudit
        failure.ingest_options = self._serialize_options(options)

        # Buat JobIngest baru untuk retry
        parent_job = failure.job
        job_type = parent_job.job_type if parent_job else JenisJobIngest.unggah_manual
        new_job = JobIngest(
            job_type=job_type,
            triggered_by="retry",
            source_ref=f"retry:failure:{failure.id}",
            retry_of_failure_id=failure.id,
            status=StatusJobIngest.berjalan,
            success_count=0,
            duplicate_count=0,
            failed_count=0,
        )
        self.db.add(new_job)
        self.db.commit()
        self.db.refresh(new_job)

        ingest_svc = IngestService(self.db, self.storage)
        item = IngestItem(
            filename=failure.original_filename,
            content=content,
            source_url=failure.source_url,
        )
        result = ingest_svc.ingest_one(
            job=new_job,
            item=item,
            options=options,
            actor_user_id=actor_user_id,
            ip_address=ip_address,
            suppress_failure_hooks=True,
        )

        failure.attempt_count += 1
        failure.last_retry_at = datetime.now(timezone.utc)
        failure.last_retry_job_id = new_job.id
        failure.handled_by_user_id = actor_user_id

        if result.outcome == ItemOutcome.success:
            failure.follow_up_status = StatusTindakLanjut.diproses_ulang
            failure.resolved_document_id = result.document_id
            if failure.quarantine_path:
                self.storage.delete(failure.quarantine_path)
                failure.quarantine_path = None
        elif result.outcome == ItemOutcome.duplicate:
            failure.follow_up_status = StatusTindakLanjut.diabaikan
            failure.failure_type = JenisKegagalan.duplikat
            failure.duplicate_of_document_id = result.duplicate_of_document_id
            if failure.quarantine_path:
                self.storage.delete(failure.quarantine_path)
                failure.quarantine_path = None
            failure.is_retryable = False
        else:  # failed
            failure.follow_up_status = StatusTindakLanjut.belum_ditangani
            failure.reason_code = result.reason_code or "kesalahan_internal"
            if result.reason_code in REASON_CODE_MAP:
                failure.failure_type = REASON_CODE_MAP[result.reason_code][0]
            else:
                failure.failure_type = JenisKegagalan.kesalahan_internal
            failure.message = result.message

        ingest_svc.finish_job(new_job, [result])

        record_audit(
            self.db,
            action=RETRY_FAILURE,
            user_id=actor_user_id,
            target_resource=f"ingest_failure:{failure.id}",
            ip_address=ip_address,
            commit=False,
        )
        self.db.commit()
        self.db.refresh(failure)

        return RetryResult(failure=failure, item_result=result, job=new_job)


def get_failure_service(
    db: Session,
    storage: StorageService = None,
) -> FailureService:
    if storage is None:
        storage = get_storage_service()
    return FailureService(db=db, storage=storage)
