"""
app/models/analysis_run.py
Model riwayat eksekusi analisa dan harmonisasi regulasi (Langkah 21, US-10 #56, US-08 #34).
Tabel bersifat append-only.
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    desc,
    func,
)
from sqlalchemy import Enum as SaEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.database import Base
from app.models.enums import JenisAnalisa, ModeAnalisa


class AnalysisRun(Base):
    """
    Menyimpan riwayat setiap eksekusi analisa atau harmonisasi regulasi (append-only).
    Merekam input, mode, versi aturan (ml_version), dan output mentah (bila sumber=ml).
    """
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Dokumen yang dianalisa",
    )
    kind = Column(
        SaEnum(JenisAnalisa, name="jenisanalisa", native_enum=False),
        nullable=False,
        comment="Jenis analisa: analisa | harmonisasi",
    )
    mode_diminta = Column(
        SaEnum(ModeAnalisa, name="modeanalisa", native_enum=False),
        nullable=False,
        comment="Mode yang diminta klien: deterministik | ai",
    )
    mode_dipakai = Column(
        SaEnum(ModeAnalisa, name="modeanalisa", native_enum=False),
        nullable=True,
        comment="Mode yang benar-benar dipakai; NULL bila gagal",
    )
    sumber = Column(
        String(20),
        nullable=False,
        comment="Asal hasil: ml | cache | cache_basi | gagal",
    )
    segar = Column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Nilai parameter segar",
    )
    params = Column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
        comment="Input parameter penentu hasil (JSON)",
    )
    params_hash = Column(
        String(64),
        nullable=False,
        comment="SHA-256 dari parameter penentu hasil",
    )
    source_fingerprint = Column(
        String(200),
        nullable=False,
        comment="Fingerprint dokumen saat eksekusi dijalankan",
    )
    ml_version = Column(
        String(100),
        nullable=True,
        comment="Versi aturan / model ML bila ada",
    )
    result_hash = Column(
        String(64),
        nullable=True,
        index=True,
        comment="SHA-256 dari output mentah ML",
    )
    result = Column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
        comment="Output mentah ML (hanya diisi jika sumber=ml)",
    )
    ringkasan_output = Column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=True,
        comment="Ringkasan kecil untuk daftar riwayat",
    )
    http_status = Column(
        Integer,
        nullable=False,
        comment="HTTP status yang dikembalikan ke klien",
    )
    error_code = Column(
        String(100),
        nullable=True,
        comment="Kode galat jika eksekusi gagal",
    )
    duration_ms = Column(
        Integer,
        nullable=True,
        comment="Lama penanganan di gerbang (ms)",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_analysis_runs_doc_kind_created", "document_id", "kind", desc("created_at")),
    )

    document = relationship("Document", back_populates="analysis_runs")
    creator = relationship("User")
