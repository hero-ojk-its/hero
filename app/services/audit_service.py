"""
app/services/audit_service.py
Fungsi helper untuk mencatat AuditLog dari router manapun.

Penggunaan:
    from app.services.audit_service import create_audit_log

    create_audit_log(
        db=db,
        action="LOGIN",
        user_id=user.id,          # opsional
        target_resource="user:5", # opsional
        ip_address=request.client.host,  # opsional
    )
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def create_audit_log(
    db: Session,
    action: str,
    user_id: Optional[int] = None,
    target_resource: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Optional[AuditLog]:
    """
    Catat satu entri audit log ke database.

    Args:
        db              : SQLAlchemy Session aktif.
        action          : Kode aksi wajib, contoh: 'LOGIN', 'DOWNLOAD_PDF'.
        user_id         : ID pengguna yang melakukan aksi (None untuk aksi anonim/sistem).
        target_resource : Nama/ID resource yang dikenai aksi, misal: 'document:42'.
        ip_address      : Alamat IP klien.

    Returns:
        Instance AuditLog yang sudah tersimpan di database, atau None bila pencatatan gagal.

    Note:
        Fungsi ini melakukan commit sendiri agar log tercatat meskipun
        transaksi utama di caller-nya nanti di-rollback.
        Jika pencatatan log gagal, exception ditelan (logged ke stderr)
        supaya alur bisnis utama tidak terganggu.
    """
    try:
        log_entry = AuditLog(
            user_id=user_id,
            action=action,
            target_resource=target_resource,
            ip_address=ip_address,
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        # Ditelan (tidak di-raise ulang) sesuai dokumentasi di atas: kegagalan
        # mencatat audit log tidak boleh menggagalkan alur bisnis utama caller.
        import sys
        print(f"[AuditLog] Gagal mencatat log '{action}': {exc}", file=sys.stderr)
        return None
