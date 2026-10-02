"""
Model SQLAlchemy: ScanCandidate
[US-16, FR-SCR-02, FR-SCR-05] Kandidat berkas PDF hasil pemindaian URL situs sumber.
"""
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Boolean,
    Text,
    Date,
    ForeignKey,
    Enum as SQLEnum,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import StatusKandidat, StatusKeberlakuan


class ScanCandidate(Base):
    """
    Tabel: scan_candidates
    Menyimpan rincian berkas kandidat PDF yang ditemukan dalam satu sesi pemindaian.
    """

    __tablename__ = "scan_candidates"
    __table_args__ = (
        UniqueConstraint("scan_id", "url_hash", name="uq_scan_candidates_scan_url_hash"),
    )

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(
        Integer,
        ForeignKey("scan_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID sesi pemindaian pemilik kandidat ini",
    )
    url = Column(
        Text,
        nullable=False,
        comment="URL kandidat PDF yang sudah dinormalisasi",
    )
    url_hash = Column(
        String(64),
        nullable=False,
        comment="SHA-256 hash dari normalized URL untuk pengecekan cepat & constraint unik",
    )
    filename = Column(
        String(255),
        nullable=False,
        comment="Nama berkas dari path URL atau Content-Disposition",
    )
    size_bytes = Column(
        BigInteger,
        nullable=True,
        comment="Ukuran berkas dalam bytes dari Content-Length (jika tersedia)",
    )
    found_on_page = Column(
        Text,
        nullable=True,
        comment="URL halaman tempat tautan PDF ini ditemukan",
    )
    document_title = Column(
        String(500),
        nullable=True,
        comment="Nama dokumen / judul regulasi yang tertera di situs",
    )
    detail_url = Column(
        Text,
        nullable=True,
        comment="Halaman detail tempat lampiran ditemukan",
    )
    final_url = Column(
        Text,
        nullable=True,
        comment="URL akhir setelah mengikuti redirect",
    )
    doc_kind = Column(
        String(30),
        nullable=True,
        default="utama",
        comment="Jenis/peran dokumen: utama | abstrak | faq | lampiran | lainnya",
    )
    regulation_number = Column(
        String(255),
        nullable=True,
        comment="Nomor regulasi yang terbaca tanpa membuka PDF",
    )
    regulation_type = Column(
        String(100),
        nullable=True,
        comment="Jenis regulasi ternormalisasi",
    )
    bidang = Column(
        String(100),
        nullable=True,
        comment="Sektor/bidang regulasi yang terbaca dari situs",
    )
    sub_bidang = Column(
        String(100),
        nullable=True,
        comment="Sub-sektor regulasi yang terbaca dari situs",
    )
    release_date = Column(
        Date,
        nullable=True,
        comment="Tanggal rilis/penetapan regulasi yang terbaca dari situs",
    )
    effective_date = Column(
        Date,
        nullable=True,
        comment="Tanggal mulai berlaku regulasi yang terbaca dari situs",
    )
    match_warning = Column(
        Text,
        nullable=True,
        comment="Peringatan ketidakcocokan metadata regulasi dengan nama berkas",
    )
    status_keberlakuan = Column(
        SQLEnum(StatusKeberlakuan, native_enum=False),
        nullable=True,
        default=StatusKeberlakuan.tidak_diketahui,
        server_default="tidak_diketahui",
        comment="Status keberlakuan: berlaku | diubah | dicabut | tidak_diketahui",
    )
    size_source = Column(
        String(10),
        nullable=True,
        default="unknown",
        comment="Sumber penentuan ukuran berkas: listing | head | range | unknown",
    )
    source_path = Column(
        Text,
        nullable=True,
        comment="Jalur folder relatif sumber, misal untuk OneDrive",
    )
    depth = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Kedalaman halaman tempat tautan ditemukan",
    )
    match_status = Column(
        SQLEnum(StatusKandidat, native_enum=False),
        nullable=False,
        default=StatusKandidat.baru,
        index=True,
        comment="Status kecocokan KB: baru | sudah_ada | mungkin_ada",
    )
    match_reason = Column(
        String(30),
        nullable=True,
        comment="Alasan pencocokan: url_sama | nama_dan_ukuran_sama",
    )
    match_document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID dokumen di KB yang cocok jika match_status sudah_ada atau mungkin_ada",
    )
    selected = Column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        comment="Status centang pengguna untuk ditarik",
    )
    pull_outcome = Column(
        String(20),
        nullable=True,
        comment="Hasil penarikan: success | duplicate | failed | downloaded",
    )
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID dokumen regulasi baru jika ditarik ke knowledge_base",
    )
    failure_id = Column(
        Integer,
        ForeignKey("ingest_failures.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID baris ingest_failures jika penarikan gagal",
    )
    export_path = Column(
        Text,
        nullable=True,
        comment="Jalur penyimpanan relatif untuk tujuan unduh_folder",
    )
    message = Column(
        Text,
        nullable=True,
        comment="Pesan/detail hasil penarikan atau error",
    )

    # Relationships
    scan_session = relationship("ScanSession", back_populates="candidates")
    match_document = relationship("Document", foreign_keys=[match_document_id])
    document = relationship("Document", foreign_keys=[document_id])
    failure = relationship("IngestFailure", foreign_keys=[failure_id])

    def __repr__(self):
        return f"<ScanCandidate id={self.id} scan_id={self.scan_id} filename='{self.filename}' match='{self.match_status}'>"
