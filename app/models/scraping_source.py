"""
Model SQLAlchemy: ScrapingSource
[US-12] Mengelola daftar URL situs sumber scraping regulasi.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class ScrapingSource(Base):
    """
    Tabel: scraping_sources
    Menyimpan daftar URL situs sumber scraping regulasi (misal: JDIH OJK, BPK, Kemenkeu, dll).

    Kolom:
        id         → Primary key
        name       → Nama/label situs sumber (misal: "JDIH OJK", "JDIH BPK")
        url        → URL target scraping (wajib unik)
        is_active  → Status aktif sumber scraping (default: True)
        created_at → Waktu pembuatan data
        updated_at → Waktu pembaruan data terakhir
    """

    __tablename__ = "scraping_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(
        String(255),
        nullable=False,
        comment="Nama/label situs sumber scraping, misal: JDIH OJK"
    )
    url = Column(
        String(500),
        unique=True,
        nullable=False,
        index=True,
        comment="URL situs sumber scraping (wajib unik)"
    )
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Status aktif/non-aktif situs sumber (default: True)"
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Waktu pencatatan situs sumber"
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        comment="Waktu terakhir situs sumber diubah"
    )

    def __repr__(self):
        return f"<ScrapingSource id={self.id} name='{self.name}' is_active={self.is_active}>"
