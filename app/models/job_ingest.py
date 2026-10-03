from sqlalchemy import (
    Column, Integer, String, DateTime, Enum as SQLEnum, ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.models.enums import JenisJobIngest, StatusJobIngest


class JobIngest(Base):
    """
    Tabel: job_ingest
    Menyimpan riwayat dan status proses ingest dokumen (scraping, manual upload, sinkronisasi).
    """

    __tablename__ = "job_ingest"

    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(
        SQLEnum(JenisJobIngest, native_enum=False),
        nullable=False,
        comment="Jenis job: scraping | unggah_manual | sinkron_folder"
    )
    source_ref = Column(
        String(255),
        nullable=True,
        comment="Referensi sumber, misal nama file, link, atau folder"
    )
    triggered_by = Column(
        String(100),
        nullable=True,
        comment="Pemicu job, misal user email / system / scraper id"
    )
    source_id = Column(
        Integer,
        ForeignKey("scraping_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="FK ke sumber scraping (Langkah 6-7)",
    )
    retry_of_failure_id = Column(
        Integer,
        ForeignKey("ingest_failures.id", ondelete="SET NULL", use_alter=True, name="fk_job_ingest_retry_failure"),
        nullable=True,
        comment="FK ke baris ingest_failures jika job ini merupakan retry",
    )
    category_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="FK ke kategori target KB",
    )
    started_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Waktu job dimulai"
    )
    finished_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Waktu job selesai dieksekusi"
    )
    status = Column(
        SQLEnum(StatusJobIngest, native_enum=False),
        default=StatusJobIngest.antrian,
        nullable=False,
        comment="Status eksekusi: antrian | berjalan | selesai | gagal"
    )
    success_count = Column(Integer, default=0, nullable=False, comment="Jumlah dokumen berhasil diproses")
    duplicate_count = Column(Integer, default=0, nullable=False, comment="Jumlah dokumen duplikat yang diabaikan")
    failed_count = Column(Integer, default=0, nullable=False, comment="Jumlah dokumen yang gagal diproses")
    total_found = Column(Integer, nullable=True, comment="Total berkas yang ditemukan pada sumber")
    processed_count = Column(Integer, default=0, nullable=False, comment="Jumlah berkas yang telah diproses")
    skipped_count = Column(Integer, default=0, nullable=False, comment="Jumlah berkas yang dilewati tanpa perubahan (skipped_unchanged)")

    # Relasi ke sumber scraping
    source = relationship("ScrapingSource", foreign_keys=[source_id])
    # Relasi ke dokumen yang dihasilkan dari job ini
    documents = relationship("Document", back_populates="job")
    # Relasi ke failures
    failures = relationship("IngestFailure", back_populates="job", foreign_keys="[IngestFailure.job_id]", order_by="IngestFailure.id")

    def __repr__(self):
        return f"<JobIngest id={self.id} type={self.job_type} status={self.status}>"

