"""
app/models/tanggapan_temuan.py
Model SQLAlchemy: TanggapanTemuan
[US-49, FR-HRM-11, Issue #71] Penandaan dan tanggapan analis terhadap temuan harmonisasi.
"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class TanggapanTemuan(Base):
    """
    Tabel: tanggapan_temuan
    Menyimpan penilaian analis (valid / tidak_relevan) beserta catatan untuk setiap temuan harmonisasi.
    Menggunakan kunci_temuan stabil berbasis hash substansi temuan.
    """

    __tablename__ = "tanggapan_temuan"
    __table_args__ = (
        UniqueConstraint("document_id", "kunci_temuan", name="uq_tanggapan_temuan_doc_kunci"),
        Index("ix_tanggapan_temuan_doc_id", "document_id"),
        Index("ix_tanggapan_temuan_kunci", "kunci_temuan"),
    )

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID draft kajian yang diharmonisasi",
    )
    kunci_temuan = Column(
        String(64),
        nullable=False,
        index=True,
        comment="Hash penanda stabil temuan (SHA-256)",
    )
    run_id = Column(
        Integer,
        ForeignKey("analysis_runs.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID eksekusi harmonisasi tempat temuan dinilai",
    )
    temuan_id_ml = Column(
        String(100),
        nullable=True,
        comment="ID temuan dari respons layanan ML",
    )
    penilaian = Column(
        String(20),
        nullable=False,
        comment="Penilaian analis: valid atau tidak_relevan",
    )
    catatan = Column(
        Text,
        nullable=True,
        comment="Catatan analis terhadap temuan (maks 2000 karakter)",
    )
    ringkasan_temuan = Column(
        JSONB,
        nullable=False,
        comment="Salinan ringkas temuan saat dinilai (tanpa teks pasal panjang)",
    )
    dinilai_oleh = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID user yang menilai",
    )
    dinilai_oleh_nama = Column(
        String(255),
        nullable=True,
        comment="Nama/username penilai",
    )
    dibuat = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Waktu penilaian dibuat",
    )
    diperbarui = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Waktu penilaian terakhir diperbarui",
    )

    document = relationship("Document", backref="tanggapan_temuan_list")
    run = relationship("AnalysisRun", backref="tanggapan_temuan_list")
    user = relationship("User", backref="tanggapan_temuan_list")

