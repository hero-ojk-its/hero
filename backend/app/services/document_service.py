"""
app/services/document_service.py
Helper layanan tingkat rendah untuk operasi dokumen yang dipakai bersama
oleh router dan skrip CLI — agar tidak ada impor sirkular antara scripts dan app.routers.

Fungsi yang diekspor:
  - deactivate_document: Menonaktifkan dokumen dan mencatat audit DEACTIVATE_DOCUMENT.
  - tandai_ekstraksi_kehabisan_percobaan: Menandai dokumen yang kehabisan jatah percobaan ekstraksi menjadi gagal.
"""
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Sequence

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import Document
from app.models.enums import (
    JenisKegagalan,
    JenisJobIngest,
    StatusJobIngest,
    StatusPemrosesan,
    StatusTindakLanjut,
)
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.services.audit_service import (
    DEACTIVATE_DOCUMENT,
    EXTRACTION_FAILED,
    record_audit,
)


def deactivate_document(
    db: Session,
    document: Document,
    reason: str,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    commit: bool = True,
) -> bool:
    """
    Helper untuk menonaktifkan dokumen (is_active=False), mengisi deactivated_at,
    deactivated_reason, deactivated_by, serta mencatat audit DEACTIVATE_DOCUMENT (Langkah 14 / US-30).
    Mengembalikan True jika status berubah dari aktif ke nonaktif, False jika sudah nonaktif.
    """
    if not document.is_active:
        return False

    clean_reason = reason.strip() if reason else None
    document.is_active = False
    document.deactivated_at = datetime.now(timezone.utc)
    document.deactivated_reason = clean_reason
    document.deactivated_by = user_id

    record_audit(
        db,
        action=DEACTIVATE_DOCUMENT,
        user_id=user_id,
        target_resource=f"document:{document.id}",
        detail={
            "reason": clean_reason,
            "before": {"is_active": True},
            "after": {"is_active": False},
        },
        ip_address=ip_address,
        commit=commit,
    )
    return True


def tandai_ekstraksi_kehabisan_percobaan(
    db: Session,
    document_ids: Optional[Sequence[int]] = None,
    commit: bool = True,
) -> List[int]:
    """
    Mencari dokumen aktif yang kehabisan jatah percobaan ekstraksi (attempts >= extraction_max_attempts)
    dan berstatus 'diterima' atau 'diproses' yang telah kedaluwarsa (claimed_at < cutoff_time).

    Untuk tiap dokumen tersebut:
    - Set processing_status = gagal, extraction_claimed_at = None
    - Catat satu IngestFailure (jenis ekstraksi_gagal, reason_code="percobaan_ekstraksi_habis", is_retryable=True)
      jika belum ada kegagalan terbuka (belum ditangani) untuk dokumen dan reason_code yang sama.
    - Catat audit log EXTRACTION_FAILED.

    Mengembalikan daftar ID dokumen yang ditandai gagal.
    """
    db.flush()
    timeout_minutes = settings.extraction_claim_timeout_minutes
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

    stuck_cond = and_(
        Document.is_active == True,  # noqa: E712
        Document.extraction_attempts >= settings.extraction_max_attempts,
        or_(
            Document.processing_status == StatusPemrosesan.diterima,
            and_(
                Document.processing_status == StatusPemrosesan.diproses,
                Document.extraction_claimed_at.isnot(None),
                Document.extraction_claimed_at < cutoff_time,
            ),
        ),
    )

    query = db.query(Document).filter(stuck_cond)
    if document_ids is not None:
        query = query.filter(Document.id.in_(document_ids))

    docs = query.order_by(Document.id.asc()).all()

    failed_doc_ids: List[int] = []
    for doc in docs:
        doc.processing_status = StatusPemrosesan.gagal
        doc.extraction_claimed_at = None

        # Cek apakah sudah ada kegagalan terbuka (belum ditangani) untuk dokumen dan reason_code yang sama
        existing_failure = (
            db.query(IngestFailure)
            .filter(
                IngestFailure.document_id == doc.id,
                IngestFailure.follow_up_status == StatusTindakLanjut.belum_ditangani,
                IngestFailure.reason_code == "percobaan_ekstraksi_habis",
            )
            .order_by(IngestFailure.id.desc())
            .first()
        )

        if not existing_failure:
            job_id = doc.job_id
            if not job_id:
                default_job = db.query(JobIngest).filter(JobIngest.source_ref == "system:extraction").first()
                if not default_job:
                    default_job = JobIngest(
                        job_type=JenisJobIngest.unggah_manual,
                        triggered_by="system",
                        source_ref="system:extraction",
                        status=StatusJobIngest.selesai,
                    )
                    db.add(default_job)
                    db.flush()
                job_id = default_job.id

            msg = (
                f"Ekstraksi dihentikan setelah {doc.extraction_attempts} kali percobaan tanpa hasil. "
                "Gunakan Coba Lagi untuk mengulang."
            )

            failure = IngestFailure(
                job_id=job_id,
                original_filename=doc.standardized_filename or doc.title or "dokumen.pdf",
                source_url=doc.source_url,
                failure_type=JenisKegagalan.ekstraksi_gagal,
                reason_code="percobaan_ekstraksi_habis",
                message=msg,
                is_retryable=True,
                quarantine_path=None,
                file_hash=doc.file_hash,
                file_size_bytes=doc.file_size_bytes,
                document_id=doc.id,
                ingest_options={},
                follow_up_status=StatusTindakLanjut.belum_ditangani,
                attempt_count=0,
            )
            db.add(failure)
            db.flush()

            record_audit(
                db,
                action=EXTRACTION_FAILED,
                target_resource=f"document:{doc.id}",
                detail={
                    "document_id": doc.id,
                    "reason_code": "percobaan_ekstraksi_habis",
                    "attempts": doc.extraction_attempts,
                    "failure_id": failure.id,
                    "message": msg,
                },
                commit=False,
            )

        failed_doc_ids.append(doc.id)

    if commit:
        db.commit()

    return failed_doc_ids


