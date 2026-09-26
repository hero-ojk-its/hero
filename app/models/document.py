from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, BigInteger, ForeignKey, Enum as SQLEnum
)
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
    - file_path_pdf  → path file PDF asli (untuk validasi manual DPEA)
    - Blok teks ada di tabel Article (untuk indexing & semantic search)
    """

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, comment="Judul lengkap dokumen regulasi")
    regulation_number = Column(
        String(100),
        unique=True,
        nullable=True,
        index=True,
        comment="Nomor regulasi unik, misal: PP-24-2005"
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
        comment="Path relatif file PDF asli, misal: /storage/pdf/PP-24-2005.pdf"
    )
    file_hash = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="SHA-256 hash file untuk deduplikasi (sesuai instruksi mitra)"
    )
    file_size_bytes = Column(BigInteger, nullable=True, comment="Ukuran file PDF dalam bytes")
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
        default=PeranDokumen.corpus_eksisting,
        comment="Peran dokumen: corpus_eksisting | draft_kajian"
    )
    status_keberlakuan = Column(
        SQLEnum(StatusKeberlakuan, native_enum=False),
        default=StatusKeberlakuan.tidak_diketahui,
        nullable=False,
        comment="Status keberlakuan: berlaku | diubah | dicabut | tidak_diketahui"
    )
    processing_status = Column(
        SQLEnum(StatusPemrosesan, native_enum=False),
        default=StatusPemrosesan.diterima,
        nullable=False,
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

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relasi
    category = relationship("Category", back_populates="documents")
    job = relationship("JobIngest", back_populates="documents")
    articles = relationship("Article", back_populates="document", cascade="all, delete-orphan")
    legal_references = relationship(
        "LegalReference",
        foreign_keys="LegalReference.document_id",
        back_populates="document",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Document id={self.id} reg={self.regulation_number} status={self.status_keberlakuan} access={self.access_classification}>"
