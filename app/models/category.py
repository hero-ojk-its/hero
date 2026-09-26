from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Category(Base):
    """
    Tabel: categories
    Menyimpan struktur kategori / hierarki folder dalam Knowledge Base.
    Mendukung pengelompokan hierarkis rekursif (parent-child).
    """

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True, comment="Nama kategori")
    parent_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="FK ke kategori induk untuk struktur hierarkis folder KB"
    )
    auto_created = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Apakah kategori ini dibuat secara otomatis oleh sistem klasifikasi"
    )
    classification_rule = Column(
        Text,
        nullable=True,
        comment="Aturan / regex / prompt klasifikasi otomatis"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relasi hierarki kategori
    children = relationship("Category", back_populates="parent", cascade="all")
    parent = relationship("Category", back_populates="children", remote_side=[id])

    # Relasi ke dokumen
    documents = relationship("Document", back_populates="category")

    def __repr__(self):
        return f"<Category id={self.id} name='{self.name}' parent_id={self.parent_id}>"
