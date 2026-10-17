from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    UniqueConstraint,
    Enum as SQLEnum,
)
from sqlalchemy.sql import func
from app.database import Base
from app.models.enums import JenisRelasi


class DocumentRelation(Base):
    """
    Tabel: document_relations
    Menyimpan relasi hukum antar dokumen regulasi (mengubah, mencabut).
    Relasi disimpan berdasarkan kunci kanonik (identity_key), bukan document_id,
    sehingga tetap tertaut otomatis ketika dokumen masuk ke Knowledge Base.
    """

    __tablename__ = "document_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_key",
            "target_key",
            "relation",
            name="uq_document_relations_src_tgt_rel",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    source_key = Column(
        String(120),
        nullable=False,
        index=True,
        comment="Kunci peraturan yang mengubah/mencabut (src)",
    )
    target_key = Column(
        String(120),
        nullable=False,
        index=True,
        comment="Kunci peraturan yang diubah/dicabut (dst)",
    )
    relation = Column(
        SQLEnum(JenisRelasi, native_enum=False),
        nullable=False,
        comment="Jenis relasi hukum: mengubah | mencabut",
    )
    partial = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Pencabutan/perubahan sebagian",
    )
    articles_text = Column(
        Text,
        nullable=True,
        comment="Pasal-pasal terkait",
    )
    origin = Column(
        String(50),
        nullable=True,
        comment="Asal data relasi, mis. jdih-riwayat",
    )
    evidence = Column(
        Text,
        nullable=True,
        comment="Bukti tekstual relasi (maks 2000 karakter)",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
