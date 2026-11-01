"""
app/services/audit_service.py
Helper terpusat untuk mencatat AuditLog dari service atau router manapun.
"""
import logging
from typing import Optional
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog

logger = logging.getLogger("hero")

# Action constants
LOGIN = "LOGIN"
UPLOAD_DOCUMENT = "UPLOAD_DOCUMENT"
UPDATE_DOCUMENT_STATUS = "UPDATE_DOCUMENT_STATUS"
CREATE_SOURCE = "CREATE_SOURCE"
UPDATE_SOURCE = "UPDATE_SOURCE"
DELETE_SOURCE = "DELETE_SOURCE"
RETRY_FAILURE = "RETRY_FAILURE"
UPDATE_FAILURE = "UPDATE_FAILURE"
PLACE_DOCUMENT = "PLACE_DOCUMENT"
PLACE_DOCUMENT_FAILED = "PLACE_DOCUMENT_FAILED"
CREATE_CATEGORY = "CREATE_CATEGORY"
UPDATE_CATEGORY = "UPDATE_CATEGORY"
DELETE_CATEGORY = "DELETE_CATEGORY"
OPEN_PDF = "OPEN_PDF"
DOWNLOAD_PDF = "DOWNLOAD_PDF"
UPDATE_METADATA = "UPDATE_METADATA"
EXTRACTION_RESULT = "EXTRACTION_RESULT"
EXTRACTION_FAILED = "EXTRACTION_FAILED"
EXTRACTION_REQUEUED = "EXTRACTION_REQUEUED"
RUN_SOURCE = "RUN_SOURCE"
START_SCAN = "START_SCAN"
START_PULL = "START_PULL"
CANCEL_SCAN = "CANCEL_SCAN"
DOWNLOAD_SCAN_EXPORT = "DOWNLOAD_SCAN_EXPORT"
DEACTIVATE_DOCUMENT = "DEACTIVATE_DOCUMENT"
ACTIVATE_DOCUMENT = "ACTIVATE_DOCUMENT"
RUN_HARMONIZATION = "RUN_HARMONIZATION"
RUN_ANALYSIS = "RUN_ANALYSIS"
EXPORT_ANALYSIS = "EXPORT_ANALYSIS"
DUPLICATE_IDENTITY_DETECTED = "DUPLICATE_IDENTITY_DETECTED"
STATUS_FROM_RELATION = "STATUS_FROM_RELATION"
CREATE_USER = "CREATE_USER"
UPDATE_USER = "UPDATE_USER"
ANALYSIS_CACHE_INVALIDATED = "ANALYSIS_CACHE_INVALIDATED"
STATUS_RECOMPUTED = "STATUS_RECOMPUTED"
LOGIN_FAILED = "LOGIN_FAILED"
LOGIN_LOCKED = "LOGIN_LOCKED"


def ringkas_dokumen(doc: Optional[object]) -> dict:
    """Helper untuk meringkas dokumen ke dalam format audit detail tanpa teks dokumen."""
    if not doc:
        return {}
    klasifikasi = getattr(doc, "access_classification", None)
    if hasattr(klasifikasi, "value"):
        klasifikasi = klasifikasi.value
    elif klasifikasi is not None:
        klasifikasi = str(klasifikasi)

    return {
        "document_id": getattr(doc, "id", None),
        "nomor": getattr(doc, "regulation_number", None),
        "judul": (getattr(doc, "title", None) or "")[:200] if getattr(doc, "title", None) else None,
        "jenis": getattr(doc, "regulation_type", None),
        "tahun": getattr(doc, "regulation_year", None),
        "klasifikasi": klasifikasi,
    }


def record_audit(
    db: Session,
    action: str,
    *,
    user_id: Optional[int] = None,
    target_resource: Optional[str] = None,
    detail: Optional[dict] = None,
    ip_address: Optional[str] = None,
    commit: bool = True,
) -> Optional[AuditLog]:
    """
    Catat satu entri audit log ke database.

    Args:
        db: SQLAlchemy Session aktif.
        action: Kode aksi wajib (contoh: LOGIN, UPLOAD_DOCUMENT, dsb.).
        user_id: ID pengguna yang melakukan aksi (None untuk aksi anonim/sistem).
        target_resource: Nama/ID resource yang dikenai aksi, misal: 'document:42'.
        detail: Keterangan / metadata / diff perubahan (dict).
        ip_address: Alamat IP klien.
        commit: Jika True, lakukan commit langsung dan telan exception bila gagal.
                Jika False, hanya db.add() agar ikut transaksi pemanggil.

    Returns:
        Instance AuditLog yang tercatat, atau None bila terjadi kesalahan pada commit=True.
    """
    log_entry = AuditLog(
        user_id=user_id,
        action=action,
        target_resource=target_resource,
        detail=detail,
        ip_address=ip_address,
    )

    if not commit:
        db.add(log_entry)
        return log_entry

    try:
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.error("[AuditLog] Gagal mencatat log '%s': %s", action, exc)
        return None


def create_audit_log(
    db: Session,
    action: str,
    user_id: Optional[int] = None,
    target_resource: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Optional[AuditLog]:
    """
    [Deprecated] Gunakan `record_audit(db, action, ...)` sebagai gantinya.
    Alias kompatibilitas yang selalu melakukan commit sendiri.
    """
    return record_audit(
        db,
        action,
        user_id=user_id,
        target_resource=target_resource,
        ip_address=ip_address,
        commit=True,
    )
