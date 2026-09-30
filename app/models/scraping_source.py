"""
Model SQLAlchemy: ScrapingSource
[US-12] Mengelola daftar URL situs sumber scraping regulasi.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.models.enums import JenisSumber, KlasifikasiAkses, PeranDokumen


class ScrapingSource(Base):
    """
    Tabel: scraping_sources
    Menyimpan daftar sumber dokumen (situs web, folder lokal, atau OneDrive).
    """

    __tablename__ = "scraping_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(
        String(255),
        nullable=False,
        comment="Nama/label situs/folder sumber, misal: JDIH OJK, Folder POJK 2023"
    )
    url = Column(
        String(500),
        unique=True,
        nullable=False,
        index=True,
        comment="Alamat URL atau jalur folder lokal sumber (wajib unik)"
    )
    source_type = Column(
        SQLEnum(JenisSumber, native_enum=False),
        nullable=False,
        default=JenisSumber.situs_web,
        server_default="situs_web",
        index=True,
        comment="Jenis sumber: situs_web | folder_lokal | onedrive_public"
    )
    crawl_depth = Column(
        Integer,
        nullable=True,
        comment="Kedalaman crawling (1-5) khusus untuk situs_web; NULL untuk folder"
    )
    recursive = Column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
        comment="Pindai subfolder secara rekursif (khusus folder_lokal)"
    )
    default_access_classification = Column(
        SQLEnum(KlasifikasiAkses, native_enum=False),
        nullable=False,
        default=KlasifikasiAkses.publik,
        server_default="publik",
        comment="Klasifikasi akses default untuk dokumen dari sumber ini"
    )
    default_document_role = Column(
        SQLEnum(PeranDokumen, native_enum=False),
        nullable=False,
        default=PeranDokumen.corpus_eksisting,
        server_default="corpus_eksisting",
        comment="Peran dokumen default untuk dokumen dari sumber ini"
    )
    default_naming_format = Column(
        JSONB,
        nullable=True,
        comment="Format penamaan berkas default untuk sumber ini"
    )
    default_naming_separator = Column(
        String(1),
        nullable=True,
        comment="Pemisah komponen penamaan berkas default"
    )
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Status aktif/non-aktif situs sumber (default: True)"
    )
    last_run_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Waktu terakhir sumber dijalankan"
    )
    last_run_status = Column(
        String(20),
        nullable=True,
        comment="Status terakhir: selesai | gagal | berjalan"
    )
    last_run_message = Column(
        Text,
        nullable=True,
        comment="Ringkasan atau pesan hasil eksekusi terakhir"
    )
    last_job_id = Column(
        Integer,
        ForeignKey(
            "job_ingest.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_scraping_sources_last_job_id_job_ingest"
        ),
        nullable=True,
        comment="ID job ingest terakhir yang mengeksekusi sumber ini"
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

    # Relationships
    files = relationship("SourceFile", back_populates="source", cascade="all, delete-orphan")
    last_job = relationship("JobIngest", foreign_keys=[last_job_id])

    def __repr__(self):
        return f"<ScrapingSource id={self.id} name='{self.name}' type='{self.source_type}' is_active={self.is_active}>"

