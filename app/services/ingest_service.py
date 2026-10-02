"""
app/services/ingest_service.py
Layanan pipeline ingest terpadu untuk pemrosesan berkas PDF regulasi dan draft kajian.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import enum
import logging
from typing import Optional, List
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.category import Category
from app.models.document import Document
from app.models.enums import (
    JenisJobIngest,
    KlasifikasiAkses,
    PeranDokumen,
    StatusJobIngest,
    StatusKeberlakuan,
    StatusPemrosesan,
)
from app.models.job_ingest import JobIngest
from app.services.audit_service import record_audit, UPLOAD_DOCUMENT
from app.services.file_validation import (
    FileFingerprint,
    FileValidationError,
    fingerprint,
    sanitize_filename,
    validate_pdf,
)
from app.services.naming_service import NamingInput, build_standard_filename
from app.services.storage_service import StorageService, get_storage_service

logger = logging.getLogger("hero")


class ItemOutcome(str, enum.Enum):
    success = "success"
    duplicate = "duplicate"
    failed = "failed"
    requeued = "requeued"


@dataclass
class IngestItem:
    filename: str
    content: bytes
    source_url: Optional[str] = None


@dataclass
class DocumentMetadataInput:
    """Metadata spesifik per dokumen (hanya untuk unggahan berkas tunggal)."""
    title: Optional[str] = None
    regulation_number: Optional[str] = None
    regulation_type: Optional[str] = None
    release_date: Optional[date] = None
    bidang: Optional[str] = None
    status_keberlakuan: Optional[StatusKeberlakuan] = None


@dataclass
class IngestOptions:
    access_classification: KlasifikasiAkses
    document_role: PeranDokumen
    category_id: Optional[int] = None
    metadata: Optional[DocumentMetadataInput] = None
    naming_format: Optional[List[str]] = None
    naming_separator: Optional[str] = None


@dataclass
class ItemResult:
    filename: str
    outcome: ItemOutcome
    message: str
    reason_code: Optional[str] = None
    document_id: Optional[int] = None
    duplicate_of_document_id: Optional[int] = None
    file_hash: Optional[str] = None
    file_size_bytes: Optional[int] = None
    extra: dict = field(default_factory=dict)


@dataclass
class BatchResult:
    job: JobIngest
    results: List[ItemResult]

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.outcome == ItemOutcome.success)

    @property
    def duplicate_count(self) -> int:
        return sum(1 for r in self.results if r.outcome == ItemOutcome.duplicate)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if r.outcome == ItemOutcome.failed)


class IngestService:
    def __init__(
        self,
        db: Session,
        storage: StorageService,
        max_upload_bytes: int = settings.max_upload_bytes,
    ):
        self.db = db
        self.storage = storage
        self.max_upload_bytes = max_upload_bytes

    def start_job(
        self,
        job_type: JenisJobIngest,
        source_ref: Optional[str],
        triggered_by: Optional[str],
    ) -> JobIngest:
        """Membuat dan menyimpan record JobIngest baru dengan status 'berjalan'."""
        job = JobIngest(
            job_type=job_type,
            source_ref=source_ref[:255] if source_ref else None,
            triggered_by=triggered_by[:100] if triggered_by else "system",
            status=StatusJobIngest.berjalan,
            total_found=0,
            processed_count=0,
            success_count=0,
            duplicate_count=0,
            failed_count=0,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def finish_job(self, job: JobIngest, results: Optional[List[ItemResult]] = None) -> JobIngest:
        """Menyelesaikan status JobIngest dan menghitung ringkasan eksekusi."""
        if results is not None:
            job.success_count = sum(1 for r in results if r.outcome == ItemOutcome.success)
            job.duplicate_count = sum(1 for r in results if r.outcome == ItemOutcome.duplicate)
            job.failed_count = sum(1 for r in results if r.outcome == ItemOutcome.failed)
            job.processed_count = len(results)
            if (job.total_found or 0) < job.processed_count:
                job.total_found = job.processed_count
        else:
            calc_processed = (job.success_count or 0) + (job.duplicate_count or 0) + (job.failed_count or 0)
            if job.processed_count == 0 and calc_processed > 0:
                job.processed_count = calc_processed
            if (job.total_found or 0) < job.processed_count:
                job.total_found = job.processed_count

        job.finished_at = datetime.now(timezone.utc)

        # Status 'gagal' hanya jika sama sekali tidak ada yang berhasil/duplikat dan ada yang gagal
        if job.success_count == 0 and job.duplicate_count == 0 and job.failed_count > 0:
            job.status = StatusJobIngest.gagal
        else:
            job.status = StatusJobIngest.selesai

        self.db.commit()
        self.db.refresh(job)
        return job

    def _on_item_failed(
        self,
        job: JobIngest,
        item: IngestItem,
        result: ItemResult,
        options: IngestOptions,
    ) -> None:
        """
        Hook untuk pencatatan log kegagalan dan pendaftaran antrian retry pada Langkah 2.
        """
        try:
            from app.services.failure_service import FailureService
            svc = FailureService(self.db, self.storage)
            failure = svc.record_failure(job, item, result, options)
            if failure:
                result.extra["failure_id"] = failure.id
        except Exception as exc:
            logger.exception("Error pada hook _on_item_failed: %s", exc)

    def _on_item_duplicate(
        self,
        job: JobIngest,
        item: IngestItem,
        result: ItemResult,
        options: IngestOptions,
    ) -> None:
        """
        Hook untuk penanganan item duplikat pada Langkah 2.
        """
        try:
            from app.services.failure_service import FailureService
            svc = FailureService(self.db, self.storage)
            failure = svc.record_duplicate(job, item, result, options)
            if failure:
                result.extra["failure_id"] = failure.id
        except Exception as exc:
            logger.exception("Error pada hook _on_item_duplicate: %s", exc)

    def ingest_one(
        self,
        job: JobIngest,
        item: IngestItem,
        options: IngestOptions,
        actor_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        suppress_failure_hooks: bool = False,
    ) -> ItemResult:
        """
        Memproses satu item berkas PDF ke dalam pipeline ingest.
        Fungsi ini TIDAK AKAN me-raise exception; setiap kesalahan ditangkap dan
        dikembalikan dalam bentuk ItemResult dengan outcome 'duplicate' atau 'failed'.
        """
        # 1. Validasi berkas PDF
        try:
            validate_pdf(item.filename, item.content, self.max_upload_bytes)
        except FileValidationError as val_err:
            result = ItemResult(
                filename=item.filename,
                outcome=ItemOutcome.failed,
                message=val_err.message,
                reason_code=val_err.code.value,
            )
            if not suppress_failure_hooks:
                self._on_item_failed(job, item, result, options)
            return result

        # 2. Hitung fingerprint berkas (SHA-256 dan ukuran byte)
        fp: FileFingerprint = fingerprint(item.content)

        # 3. Pengecekan duplikasi di level database (ADR-05 / KEP-06: hash + ukuran)
        existing = (
            self.db.query(Document)
            .filter(
                Document.file_hash == fp.sha256,
                Document.file_size_bytes == fp.size_bytes,
            )
            .first()
        )
        if existing:
            ref_label = existing.regulation_number or existing.title or f"ID {existing.id}"
            msg = (
                f"Dokumen duplikat: hash SHA-256 dan ukuran {fp.size_bytes} byte "
                f"sama dengan dokumen ID {existing.id} ({ref_label})."
            )
            result = ItemResult(
                filename=item.filename,
                outcome=ItemOutcome.duplicate,
                message=msg,
                reason_code="duplikat",
                document_id=existing.id,
                duplicate_of_document_id=existing.id,
                file_hash=fp.sha256,
                file_size_bytes=fp.size_bytes,
                extra={
                    "regulation_number": existing.regulation_number,
                    "title": existing.title,
                },
            )
            if not suppress_failure_hooks:
                self._on_item_duplicate(job, item, result, options)
            return result

        # 4. Simpan PDF ke storage fisik di folder staging pdf/_inbox
        rel_path: Optional[str] = None
        try:
            # Tentukan judul dan metadata dokumen
            doc_title: str
            if options.metadata and options.metadata.title and options.metadata.title.strip():
                doc_title = options.metadata.title.strip()[:255]
            else:
                stem = Path(item.filename).stem if item.filename else "dokumen"
                doc_title = stem[:255]

            doc_reg_number = None
            if options.metadata and options.metadata.regulation_number and options.metadata.regulation_number.strip():
                doc_reg_number = options.metadata.regulation_number.strip()[:100]

            doc_reg_type = None
            if options.metadata and options.metadata.regulation_type and options.metadata.regulation_type.strip():
                doc_reg_type = options.metadata.regulation_type.strip()[:100]

            doc_release_date = options.metadata.release_date if options.metadata else None

            doc_bidang = None
            if options.metadata and options.metadata.bidang and options.metadata.bidang.strip():
                doc_bidang = options.metadata.bidang.strip()[:150]

            doc_status_keberlakuan = StatusKeberlakuan.tidak_diketahui
            if options.metadata and options.metadata.status_keberlakuan:
                raw_sk = options.metadata.status_keberlakuan
                if isinstance(raw_sk, StatusKeberlakuan):
                    doc_status_keberlakuan = raw_sk
                elif isinstance(raw_sk, str):
                    try:
                        doc_status_keberlakuan = StatusKeberlakuan(raw_sk.strip().lower())
                    except ValueError:
                        doc_status_keberlakuan = StatusKeberlakuan.tidak_diketahui

            # 5. Hitung nama baku awal berdasarkan format pilihan pengguna
            naming_inp = NamingInput(
                regulation_number=doc_reg_number,
                title=doc_title,
                regulation_type=doc_reg_type,
                release_date=doc_release_date,
                bidang=doc_bidang,
                original_filename=item.filename,
            )
            std_filename = build_standard_filename(
                naming_inp,
                naming_format=options.naming_format,
                naming_separator=options.naming_separator,
                template=settings.naming_template,
                wildcard=settings.naming_wildcard,
                max_length=settings.naming_max_length,
            )

            # 6. Simpan PDF ke storage fisik di folder staging pdf/_inbox dengan format standard_name__<hash8>.pdf
            std_stem = Path(std_filename).stem
            inbox_filename = f"{std_stem}__{fp.sha256[:8]}.pdf"
            rel_path = self.storage.save_pdf(
                item.content,
                filename_hint=inbox_filename,
                subdir="pdf/_inbox",
            )

            # 7. Validasi kategori jika diberikan
            if options.category_id is not None:
                category = (
                    self.db.query(Category)
                    .filter(Category.id == options.category_id)
                    .first()
                )
                if not category:
                    self.storage.delete(rel_path)
                    result = ItemResult(
                        filename=item.filename,
                        outcome=ItemOutcome.failed,
                        message=f"Kategori dengan ID {options.category_id} tidak ditemukan.",
                        reason_code="kategori_tidak_ditemukan",
                    )
                    if not suppress_failure_hooks:
                        self._on_item_failed(job, item, result, options)
                    return result

            # Buat instance Document
            doc = Document(
                title=doc_title,
                regulation_number=doc_reg_number,
                regulation_type=doc_reg_type,
                release_date=doc_release_date,
                bidang=doc_bidang,
                naming_format=options.naming_format,
                naming_separator=options.naming_separator,
                source_url=item.source_url.strip() if item.source_url else None,
                original_filename=item.filename[:255] if item.filename else None,
                file_path_pdf=rel_path,
                standardized_filename=std_filename,
                file_hash=fp.sha256,
                file_size_bytes=fp.size_bytes,
                access_classification=options.access_classification,
                document_role=options.document_role,
                status_keberlakuan=doc_status_keberlakuan,
                processing_status=StatusPemrosesan.diterima,
                category_id=options.category_id,
                job_id=job.id,
            )
            self.db.add(doc)
            self.db.flush()

            # Catat audit log dalam transaksi yang sama (commit=False)
            record_audit(
                self.db,
                action=UPLOAD_DOCUMENT,
                user_id=actor_user_id,
                target_resource=f"document:{doc.id}",
                ip_address=ip_address,
                commit=False,
            )

            self.db.commit()
            self.db.refresh(doc)

            # 7. Eksekusi Penempatan Folder KB otomatis (Langkah 3)
            placement_extra = {
                "placed": False,
                "reason": "metadata_belum_cukup",
                "category_path": None,
                "standardized_filename": doc.standardized_filename,
            }
            try:
                from app.services.category_service import CategoryService
                from app.services.placement_service import PlacementService
                cat_svc = CategoryService(self.db)
                place_svc = PlacementService(self.db, self.storage, cat_svc, settings)
                placement_res = place_svc.place(doc, actor_user_id=actor_user_id, ip_address=ip_address)
                placement_extra = {
                    "placed": placement_res.placed,
                    "reason": placement_res.reason,
                    "category_path": placement_res.category_path,
                    "standardized_filename": doc.standardized_filename,
                }
            except Exception as place_exc:
                logger.exception("Kesalahan saat penempatan berkas dokumen ID %s: %s", doc.id, place_exc)
                placement_extra = {
                    "placed": False,
                    "reason": f"gagal: {str(place_exc)}",
                    "category_path": None,
                    "standardized_filename": doc.standardized_filename,
                }

            return ItemResult(
                filename=item.filename,
                outcome=ItemOutcome.success,
                message="Dokumen berhasil disimpan ke database.",
                document_id=doc.id,
                file_hash=doc.file_hash,
                file_size_bytes=doc.file_size_bytes,
                extra={
                    "title": doc.title,
                    "regulation_number": doc.regulation_number,
                    "placement": placement_extra,
                },
            )

        except IntegrityError as integ_err:
            self.db.rollback()
            if rel_path:
                self.storage.delete(rel_path)

            # Race condition: cek ulang apakah dokumen duplikat baru masuk
            dup = (
                self.db.query(Document)
                .filter(
                    Document.file_hash == fp.sha256,
                    Document.file_size_bytes == fp.size_bytes,
                )
                .first()
            )
            if dup:
                dup_id = dup.id
                ref_label = dup.regulation_number or dup.title or f"ID {dup_id}"
                msg = (
                    f"Dokumen duplikat (race condition): hash SHA-256 dan ukuran {fp.size_bytes} byte "
                    f"sama dengan dokumen ID {dup_id} ({ref_label})."
                )
                result = ItemResult(
                    filename=item.filename,
                    outcome=ItemOutcome.duplicate,
                    message=msg,
                    reason_code="duplikat",
                    document_id=dup_id,
                    duplicate_of_document_id=dup_id,
                    file_hash=fp.sha256,
                    file_size_bytes=fp.size_bytes,
                    extra={
                        "regulation_number": dup.regulation_number,
                        "title": dup.title,
                    },
                )
                if not suppress_failure_hooks:
                    self._on_item_duplicate(job, item, result, options)
                return result
            else:
                logger.exception("Kesalahan integritas DB pada ingest item '%s'", item.filename)
                result = ItemResult(
                    filename=item.filename,
                    outcome=ItemOutcome.failed,
                    message=f"Gagal memproses file: {str(integ_err)}",
                    reason_code="kesalahan_internal",
                )
                if not suppress_failure_hooks:
                    self._on_item_failed(job, item, result, options)
                return result

        except Exception as exc:
            self.db.rollback()
            if rel_path:
                self.storage.delete(rel_path)
            logger.exception("Kesalahan internal saat memproses ingest item '%s'", item.filename)
            result = ItemResult(
                filename=item.filename,
                outcome=ItemOutcome.failed,
                message=f"Gagal memproses file: {str(exc)}",
                reason_code="kesalahan_internal",
            )
            if not suppress_failure_hooks:
                self._on_item_failed(job, item, result, options)
            return result

    def ingest_batch(
        self,
        items: List[IngestItem],
        options: IngestOptions,
        *,
        job_type: JenisJobIngest = JenisJobIngest.unggah_manual,
        source_ref: Optional[str] = None,
        triggered_by: Optional[str] = None,
        actor_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> BatchResult:
        """
        Memproses batch beberapa berkas PDF sekaligus menggunakan satu JobIngest.
        """
        job = self.start_job(
            job_type=job_type,
            source_ref=source_ref,
            triggered_by=triggered_by,
        )

        results: List[ItemResult] = []
        for item in items:
            res = self.ingest_one(
                job=job,
                item=item,
                options=options,
                actor_user_id=actor_user_id,
                ip_address=ip_address,
            )
            results.append(res)

        self.finish_job(job, results)
        return BatchResult(job=job, results=results)


def get_ingest_service(
    db: Session = get_db,
    storage: StorageService = get_storage_service,
) -> IngestService:
    """Dependency helper."""
    return IngestService(db=db, storage=storage)
