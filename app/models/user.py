"""
Model SQLAlchemy: User
Menyimpan data pengguna sistem HERO beserta hashed password dan role akses.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    """
    Tabel: users

    Kolom:
        id              → Primary key
        username        → Nama pengguna unik (digunakan sebagai login identifier)
        hashed_password → Password yang sudah di-hash menggunakan bcrypt
        role            → Peran akses: 'admin' | 'user'
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
    role = Column(
        String(20),
        nullable=False,
        default="user",
        comment="Peran akses: admin | user",
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Status akun — False berarti akun dinonaktifkan",
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<User id={self.id} username='{self.username}' role='{self.role}' active={self.is_active}>"
