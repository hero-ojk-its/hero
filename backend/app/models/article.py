from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.database import Base
from app.models.enums import StatusKeberlakuan, JenisRujukan


class Article(Base):
    """
    Tabel: articles
    Menyimpan struktur hierarkis pasal (Bab → Pasal → Ayat → Huruf) dari tiap dokumen.

    Hierarki direpresentasikan melalui:
    - chapter_title  → level BAB (misal: "BAB II RUANG LINGKUP")
    - article_number → nomor pasal/ayat (misal: "Pasal 5", "Ayat (1)", "a.")
    - parent_id      → self-referential FK untuk mendukung rekursi hierarki

    Kolom embedding (pgvector) disiapkan untuk Fathir (Data/ML) mengisi
    hasil embedding semantic search nantinya.
    """

    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    parent_id = Column(
        Integer,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="FK ke diri sendiri: mendukung struktur rekursif Bab → Pasal → Ayat → Huruf"
    )

    chapter_title = Column(
        String(255),
        nullable=True,
        comment="Judul bab, misal: BAB II"
    )
    article_number = Column(
        String(50),
        nullable=False,
        comment="Nomor pasal/ayat, misal: Pasal 5 | Ayat (1) | a."
    )
    content_text = Column(
        Text,
        nullable=False,
        comment="Isi teks mentah pasal/ayat ini"
    )
    level = Column(
        String(20),
        nullable=False,
        default="pasal",
        comment="Level hierarki: bab | pasal | ayat | huruf"
    )
    order_index = Column(
        Integer,
        nullable=True,
        comment="Urutan tampil dalam dokumen (untuk sort yang benar)"
    )

    # Kolom vector untuk pgvector — diisi oleh pipeline ML Fathir nanti
    embedding = Column(
        Vector(1536),
        nullable=True,
        comment="Embedding 1536-dim untuk semantic search (diisi pipeline ML)"
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relasi
    document = relationship("Document", back_populates="articles")
    children = relationship("Article", back_populates="parent")
    parent = relationship("Article", back_populates="children", remote_side=[id])

    # Relasi ke rujukan
    source_references = relationship(
        "ArticleReference",
        foreign_keys="ArticleReference.source_article_id",
        back_populates="source_article",
        cascade="all, delete-orphan"
    )
    target_references = relationship(
        "ArticleReference",
        foreign_keys="ArticleReference.target_article_id",
        back_populates="target_article",
    )

    def __repr__(self):
        return f"<Article id={self.id} level={self.level} number={self.article_number}>"


class ArticleReference(Base):
    """
    Tabel: article_references
    Menyimpan relasi antar pasal — mis: Pasal 10 MENGUBAH Pasal 5 PP-24-2005.

    Dipakai untuk:
    - Tracing regulasi mana yang mengamandemen regulasi lain
    - Cross-reference saat pencarian hukum
    """

    __tablename__ = "article_references"

    id = Column(Integer, primary_key=True, index=True)
    source_article_id = Column(
        Integer,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Pasal yang merujuk / mengubah"
    )
    target_article_id = Column(
        Integer,
        ForeignKey("articles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Pasal yang dirujuk / diubah (nullable jika belum ada di KB)"
    )
    target_citation_text = Column(
        String(255),
        nullable=True,
        comment="Teks sitiran target sebagai fallback saat pasal target belum ada di KB"
    )
    relation_type = Column(
        String(50),
        nullable=False,
        comment="Tipe relasi: MENGUBAH | MENCABUT | MERUJUK | MELENGKAPI"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relasi
    source_article = relationship(
        "Article",
        foreign_keys=[source_article_id],
        back_populates="source_references"
    )
    target_article = relationship(
        "Article",
        foreign_keys=[target_article_id],
        back_populates="target_references"
    )

    def __repr__(self):
        return (
            f"<ArticleRef {self.source_article_id} "
            f"--[{self.relation_type}]--> {self.target_article_id or self.target_citation_text}>"
        )


class LegalReference(Base):
    """
    Tabel: legal_references
    Menyimpan rujukan hukum level dokumen (Mengingat / Dasar Hukum / Perubahan / Pencabutan).
    Dapat menghubungkan dokumen ke dokumen lain yang sudah ada di KB, atau mencatat teks sitiran
    jika dokumen yang dirujuk belum masuk ke KB.
    """

    __tablename__ = "legal_references"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Dokumen sumber yang memuat rujukan"
    )
    cited_text = Column(
        Text,
        nullable=False,
        comment="Teks kutipan rujukan dasar hukum"
    )
    referenced_document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="FK ke dokumen yang dirujuk jika sudah ada di KB"
    )
    referenced_document_status = Column(
        SQLEnum(StatusKeberlakuan, native_enum=False),
        nullable=True,
        comment="Status keberlakuan dokumen yang dirujuk saat rujukan dibuat"
    )
    reference_type = Column(
        SQLEnum(JenisRujukan, native_enum=False),
        nullable=False,
        default=JenisRujukan.dasar_hukum,
        comment="Tipe rujukan: dasar_hukum | rujukan_pasal | pencabutan | perubahan"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relasi
    document = relationship(
        "Document",
        foreign_keys=[document_id],
        back_populates="legal_references"
    )
    referenced_document = relationship(
        "Document",
        foreign_keys=[referenced_document_id]
    )

    def __repr__(self):
        return (
            f"<LegalReference id={self.id} doc={self.document_id} "
            f"type={self.reference_type} ref_doc={self.referenced_document_id}>"
        )
