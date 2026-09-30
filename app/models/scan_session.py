"""
Model SQLAlchemy: ScanSession
[US-16, FR-SCR-02, FR-SCR-05] Sesi pemindaian situs web (Scan -> Bandingkan -> Centang -> Tarik).
"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Enum as SQLEnum,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.models.enums import StatusPindai, TujuanTarik


class ScanSession(Base):
    """
    Tabel: scan_sessions
    Mencatat satu sesi pemindaian URL situs sumber scraping regulasi.
    """

    __tablename__ = "scan_sessions"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(
        Integer,
        ForeignKey("scraping_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="ID sumber scraping yang dipindai (NULL jika sumber dihapus)",
    )
    start_url = Column(
        Text,
        nullable=False,
        comment="Salinan URL awal saat sesi pemindaian dimulai",
    )
    crawl_depth = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Kedalaman penelusuran (1-5)",
    )
    mode = Column(
        String(20),
        nullable=False,
        default="simple_http",
        comment="Mode crawler: simple_http | external_module | push",
    )
    crawler_name = Column(
        String(100),
        nullable=True,
        comment="Nama identitas crawler yang mengeksekusi",
    )
    status = Column(
        SQLEnum(StatusPindai, native_enum=False),
        nullable=False,
        default=StatusPindai.antrian,
        server_default="antrian",
        index=True,
        comment="Status sesi: antrian | memindai | siap_dipilih | menarik | selesai | gagal | dibatalkan",
    )
    cancel_requested = Column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        comment="Flag permintaan pembatalan oleh pengguna",
    )
    pages_visited = Column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
        comment="Jumlah halaman HTML yang telah dikunjungi",
    )
    candidates_total = Column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
        comment="Total kandidat PDF yang ditemukan",
    )
    candidates_new = Column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
        comment="Jumlah kandidat berstatus 'baru'",
    )
    candidates_existing = Column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
        comment="Jumlah kandidat berstatus 'sudah_ada'",
    )
    candidates_uncertain = Column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
        comment="Jumlah kandidat berstatus 'mungkin_ada'",
    )
    truncated = Column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        comment="True jika pemindaian terpotong karena mencapai batas halaman/kandidat",
    )
    errors = Column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
        comment="Daftar pesan error/peringatan selama pemindaian",
    )
    error_message = Column(
        Text,
        nullable=True,
        comment="Pesan kesalahan fatal jika status gagal",
    )
    destination = Column(
        SQLEnum(TujuanTarik, native_enum=False),
        nullable=True,
        comment="Tujuan penarikan: knowledge_base | unduh_folder",
    )
    naming_format = Column(
        JSONB,
        nullable=True,
        comment="Format penamaan berkas yang dipilih saat pull",
    )
    naming_separator = Column(
        String(1),
        nullable=True,
        comment="Pemisah komponen penamaan berkas",
    )
    pull_job_id = Column(
        Integer,
        ForeignKey("job_ingest.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID job ingest saat proses penarikan berjalan",
    )
    requested_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID user yang meminta pemindaian",
    )
    claimed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Waktu sesi diklaim oleh worker (untuk mode push)",
    )
    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Waktu pemindaian mulai berjalan",
    )
    scanned_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Waktu pemindaian selesai dan siap dipilih",
    )
    finished_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Waktu penarikan atau sesi selesai",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Waktu pencatatan sesi",
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        comment="Waktu pembaruan sesi terakhir",
    )

    # Relationships
    source = relationship("ScrapingSource", foreign_keys=[source_id])
    pull_job = relationship("JobIngest", foreign_keys=[pull_job_id])
    requested_by = relationship("User", foreign_keys=[requested_by_user_id])
    candidates = relationship(
        "ScanCandidate",
        back_populates="scan_session",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<ScanSession id={self.id} start_url='{self.start_url}' status='{self.status}'>"
