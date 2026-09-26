from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, BigInteger, ForeignKey, Enum as SQLEnum, UniqueConstraint,
    Computed, Index
)
from sqlalchemy.dialects.postgresql import TSVECTOR, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
    MetodeEkstraksi,
)


class Document(Base):
    """
    Tabel: documents
    Menyimpan metadata dokumen regulasi/peraturan dan path file-nya.

    Strategi penyimpanan ganda:
    - file_path_pdf  → path file PDF asli relatif terhadap STORAGE_PATH
    - Blok teks ada di tabel Article (untuk indexing & semantic search)
    """

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("file_hash", "file_size_bytes", name="uq_documents_hash_size"),
        Index("ix_documents_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_documents_reg_num_trgm", "regulation_number", postgresql_using="gin", postgresql_ops={"regulation_number": "gin_trgm_ops"}),
        Index("ix_documents_title_trgm", "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
        Index("ix_documents_release_date", "release_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, comment="Judul lengkap dokumen regulasi")
    regulation_number = Column(
        String(100),
        unique=False,
        nullable=True,
        index=True,
        comment="Nomor regulasi, misal: PP-24-2005"
    )
    regulation_type = Column(
        String(100),
        nullable=True,
        comment="Jenis regulasi (misal: UU, PP, Permen, Perda)"
    )
    release_date = Column(Date, nullable=True, comment="Tanggal terbit regulasi")
    source_url = Column(Text, nullable=True, comment="URL sumber dokumen di web")
    file_path_pdf = Column(
        Text,
        nullable=False,
        comment="Path relatif file PDF asli terhadap STORAGE_PATH, misal: pdf/3fa1c2d4e5f6_nama.pdf"
    )
    file_hash = Column(
        String(64),
        unique=False,
        nullable=False,
        index=True,
        comment="SHA-256 hash file untuk deduplikasi (sesuai ADR-05 / KEP-06)"
    )
    file_size_bytes = Column(
        BigInteger,
        nullable=False,
        comment="Ukuran file PDF dalam bytes (pasangan pembanding wajib bersama file_hash)"
    )
    standardized_filename = Column(
        String(255),
        nullable=True,
        comment="Nama file yang sudah distandarisasi"
    )
    access_classification = Column(
        SQLEnum(KlasifikasiAkses, native_enum=False),
        nullable=False,
        default=KlasifikasiAkses.non_publik,
        comment="Klasifikasi akses: publik | non_publik (wajib kepatuhan NDA sebelum kirim ke AI eksternal)"
    )
    document_role = Column(
        SQLEnum(PeranDokumen, native_enum=False),
        nullable=False,
        index=True,
        comment="Peran dokumen: corpus_eksisting | draft_kajian (FR-SCR-04a: wajib dinyatakan)"
    )
    status_keberlakuan = Column(
        SQLEnum(StatusKeberlakuan, native_enum=False),
        default=StatusKeberlakuan.tidak_diketahui,
        nullable=False,
        index=True,
        comment="Status keberlakuan: berlaku | diubah | dicabut | tidak_diketahui"
    )
    processing_status = Column(
        SQLEnum(StatusPemrosesan, native_enum=False),
        default=StatusPemrosesan.diterima,
        nullable=False,
        index=True,
        comment="Status pemrosesan pipeline: diterima | diproses | perlu_koreksi | terindeks | gagal | ditolak"
    )
    extraction_method = Column(
        SQLEnum(MetodeEkstraksi, native_enum=False),
        nullable=True,
        comment="Metode ekstraksi teks: teks_langsung | ocr"
    )
    full_text = Column(
        Text,
        nullable=True,
        comment="Teks mentah hasil ekstraksi dokumen lengkap"
    )
    search_vector = Column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('simple'::regconfig, coalesce(regulation_number, '')), 'A') || "
            "setweight(to_tsvector('simple'::regconfig, coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('simple'::regconfig, coalesce(regulation_type, '')), 'B') || "
            "setweight(to_tsvector('simple'::regconfig, left(coalesce(full_text, ''), 300000)), 'C')",
            persisted=True
        ),
        nullable=True,
        comment="TSVector computed untuk full-text search"
    )

    category_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="FK ke kategori / folder KB"
    )
    job_id = Column(
        Integer,
        ForeignKey("job_ingest.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="FK ke job ingest terkait"
    )

    extraction_confidence = Column(
        JSONB,
        nullable=True,
        comment="Keyakinan ekstraksi per field"
    )
    metadata_corrected_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Waktu koreksi metadata manual"
    )
    metadata_corrected_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID pengguna yang melakukan koreksi metadata manual"
    )
    extraction_claimed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Waktu pengambilan klaim ekstraksi ML"
    )
    extraction_attempts = Column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Jumlah upaya pemrosesan ekstraksi ML"
    )
    extracted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Waktu hasil ekstraksi ML diterima"
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relasi
    category = relationship("Category", back_populates="documents")
    job = relationship("JobIngest", back_populates="documents")
    corrected_by_user = relationship("User", foreign_keys=[metadata_corrected_by])
    articles = relationship("Article", back_populates="document", cascade="all, delete-orphan")
    legal_references = relationship(
        "LegalReference",
        foreign_keys="LegalReference.document_id",
        back_populates="document",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Document id={self.id} reg={self.regulation_number} status={self.status_keberlakuan} role={self.document_role}>"
