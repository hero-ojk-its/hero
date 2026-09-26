"""
Model SQLAlchemy: AuditLog
Merekam jejak aktivitas pengguna (siapa melakukan apa, kapan, dari mana).
"""
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base


class AuditLog(Base):
    """
    Tabel: audit_logs

    Kolom:
        id              → Primary key
        user_id         → FK ke users.id (nullable — bisa NULL untuk aksi anonim/sistem)
        action          → Kode aksi singkat: 'LOGIN', 'DOWNLOAD_PDF', 'DELETE_DOC', dsb.
        target_resource → Nama atau ID resource yang dikenai aksi (nullable)
        ip_address      → Alamat IP klien (nullable)_
        timestamp       → Waktu kejadian (UTC, default saat baris dibuat)
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User yang melakukan aksi; NULL jika aksi sistem / anonim",
    )
    action = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Kode aksi: LOGIN | DOWNLOAD_PDF | DELETE_DOC | dsb.",
    )
    target_resource = Column(
        String(255),
        nullable=True,
        comment="Nama atau ID resource yang dikenai aksi, misal: 'document:42'",
    )
    ip_address = Column(
        String(45),  # cukup untuk IPv4 (15) maupun IPv6 (39) + padding
        nullable=True,
        comment="Alamat IP klien saat melakukan aksi",
    )
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Waktu kejadian (UTC)",
    )

    user = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} user_id={self.user_id} "
            f"action='{self.action}' ts={self.timestamp}>"
        )



# FUNGSI HELPER UNTUK MENCATAT LOG
def create_audit_log(db, user_id: int, action: str, target_resource: str = None, ip_address: str = None):
    """Helper untuk mencatat aktivitas ke tabel audit_logs."""
    new_log = AuditLog(
        user_id=user_id,
        action=action,
        target_resource=target_resource,
        ip_address=ip_address
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)
    return new_log