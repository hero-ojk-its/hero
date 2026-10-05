"""
Model SQLAlchemy: SourceFile
[Langkah 6] Indeks berkas per sumber dokumen untuk melacak status sinkronisasi & idempotensi hash.
"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class SourceFile(Base):
    """
    Tabel: source_files
    Menyimpan rekam jejak berkas pada sumber folder/situs, ukuran, mtime, dan hasil ingest terakhir.
    """

    __tablename__ = "source_files"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(
        Integer,
        ForeignKey("scraping_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID sumber dokumen pemilik berkas"
    )
    relative_path = Column(
        Text,
        nullable=False,
        comment="Jalur relatif berkas terhadap akar sumber (pemisah /)"
    )
    size_bytes = Column(
        BigInteger,
        nullable=False,
        comment="Ukuran berkas dalam bytes saat terakhir dipindai"
    )
    mtime = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Waktu modifikasi berkas (mtime) saat terakhir dipindai"
    )
    file_hash = Column(
        String(64),
        nullable=True,
        comment="SHA-256 hash dari konten berkas"
    )
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID dokumen regulasi yang dihasilkan (jika berhasil/duplikat)"
    )
    last_outcome = Column(
        String(20),
        nullable=False,
        comment="Hasil pemrosesan terakhir: success | duplicate | failed | skipped_unchanged"
    )
    last_seen_job_id = Column(
        Integer,
        ForeignKey("job_ingest.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID job terakhir yang memindai/melihat berkas ini"
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Waktu pertama kali berkas terdeteksi"
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Waktu pembaruan status berkas terakhir"
    )

    __table_args__ = (
        UniqueConstraint("source_id", "relative_path", name="uq_source_files_source_path"),
    )

    # Relationships
    source = relationship("ScrapingSource", back_populates="files")
    document = relationship("Document")
    last_seen_job = relationship("JobIngest", foreign_keys=[last_seen_job_id])

    def __repr__(self):
        return f"<SourceFile id={self.id} source_id={self.source_id} path='{self.relative_path}' outcome='{self.last_outcome}'>"
