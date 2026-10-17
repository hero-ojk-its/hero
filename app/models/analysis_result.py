"""
app/models/analysis_result.py
Model penyimpanan hasil analisa dan harmonisasi regulasi (Langkah 20, US-05 #49).
"""
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SaEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.database import Base
from app.models.enums import JenisAnalisa, ModeAnalisa


class AnalysisResult(Base):
    """
    Menyimpan hasil mentah layanan ML per dokumen, jenis analisa, dan mode komputasi.
    Memungkinkan caching dan perbandingan berdampingan deterministik vs AI.
    """
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind = Column(
        SaEnum(JenisAnalisa, name="jenisanalisa", native_enum=False),
        nullable=False,
        comment="Jenis analisa: analisa | harmonisasi",
    )
    mode = Column(
        SaEnum(ModeAnalisa, name="modeanalisa", native_enum=False),
        nullable=False,
        comment="Mode yang benar-benar dipakai: deterministik | ai",
    )
    params_hash = Column(
        String(64),
        nullable=False,
        comment="SHA-256 dari parameter penentu hasil",
    )
    source_fingerprint = Column(
        String(200),
        nullable=False,
        comment="Fingerprint dokumen '{file_hash}:{extracted_at ISO}' saat hasil dibuat",
    )
    result = Column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
        comment="Jawaban mentah layanan ML, belum disaring",
    )
    ml_version = Column(
        String(100),
        nullable=True,
        comment="Field versi dari jawaban ML bila ada",
    )
    duration_ms = Column(
        Integer,
        nullable=True,
        comment="Durasi panggilan ML dalam milidetik",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "kind",
            "mode",
            "params_hash",
            name="uq_analysis_results_doc_kind_mode_params",
        ),
    )

    document = relationship("Document", back_populates="analysis_results")
    creator = relationship("User")
