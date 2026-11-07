"""
app/services/document_service.py
Helper layanan tingkat rendah untuk operasi dokumen yang dipakai bersama
oleh router dan skrip CLI — agar tidak ada impor sirkular antara scripts dan app.routers.

Fungsi yang diekspor:
  - deactivate_document: Menonaktifkan dokumen dan mencatat audit DEACTIVATE_DOCUMENT.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.document import Document
from app.services.audit_service import DEACTIVATE_DOCUMENT, record_audit


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

