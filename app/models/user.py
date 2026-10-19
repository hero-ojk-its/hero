"""
Model SQLAlchemy: User
Menyimpan data pengguna sistem HERO beserta hashed password dan role akses.
"""
import logging
from sqlalchemy import Column, Integer, String, Boolean, DateTime, CheckConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import validates
from app.database import Base

logger = logging.getLogger("hero")


class User(Base):
    """
    Tabel: users

    Kolom:
        id              → Primary key
        username        → Nama pengguna unik (digunakan sebagai login identifier)
        hashed_password → Password yang sudah di-hash menggunakan bcrypt
        nama_lengkap    → Nama lengkap pengguna (opsional)
        unit_kerja      → Unit kerja / divisi pengguna (opsional)
        role            → Peran akses: 'analis' | 'admin_kb' | 'admin_sistem' | 'pilot_user'
        is_active       → Apakah akun aktif (False = suspended / nonaktif)
        created_at      → Timestamp pembuatan akun
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        comment="Username unik untuk login",
    )
    hashed_password = Column(
        String(255),
        nullable=False,
        comment="Password yang sudah di-hash dengan bcrypt",
    )
    nama_lengkap = Column(
        String(150),
        nullable=True,
        comment="Nama lengkap pengguna",
    )
    unit_kerja = Column(
        String(150),
        nullable=True,
        comment="Unit kerja / divisi pengguna",
    )
    role = Column(
        String(20),
        nullable=False,
        default="analis",
        comment="Peran akses: analis | admin_kb | admin_sistem | pilot_user",
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Status akun — False berarti akun dinonaktifkan",
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "role IN ('analis', 'admin_kb', 'admin_sistem', 'pilot_user')",
            name="ck_users_role",
        ),
    )

    @validates("role")
    def validate_role(self, key: str, value: str) -> str:
        """Memetakan peran lama 'admin' -> 'admin_sistem' dan 'user' -> 'analis' demi kompatibilitas."""
        if value == "admin":
            baru = "admin_sistem"
            logger.warning("Peran lama '%s' dipetakan ke '%s'", value, baru)
            return baru
        if value == "user":
            baru = "analis"
            logger.warning("Peran lama '%s' dipetakan ke '%s'", value, baru)
            return baru
        return value

    def __repr__(self) -> str:
        return f"<User id={self.id} username='{self.username}' role='{self.role}' active={self.is_active}>"
