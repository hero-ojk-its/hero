"""
Pydantic schemas untuk endpoint internal artikel.
Dipakai oleh pipeline ML (chunking/embedding) untuk bulk insert ke tabel articles.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ArticleChunkIn(BaseModel):
    """
    Schema untuk satu buah chunk pasal dari hasil ekstraksi ML pipeline.
    Seluruh field wajib ada kecuali embedding (boleh None jika belum di-embed).
    """

    document_id: int = Field(
        ...,
        description="FK ke tabel documents — dokumen sumber pasal ini",
        examples=[42],
    )
    level: str = Field(
        ...,
        description="Level hierarki: bab | pasal | ayat | huruf",
        examples=["pasal"],
    )
    chapter_title: Optional[str] = Field(
        None,
        max_length=255,
        description="Judul bab pemilik pasal ini, misal: 'BAB II RUANG LINGKUP'",
        examples=["BAB II RUANG LINGKUP"],
    )
    article_number: str = Field(
        ...,
        max_length=50,
        description="Nomor pasal/ayat, misal: 'Pasal 5', 'Ayat (1)', 'a.'",
        examples=["Pasal 5"],
    )
    content_text: str = Field(
        ...,
        description="Isi teks mentah pasal / ayat",
        examples=["Setiap orang yang melakukan ..."],
    )
    order_index: Optional[int] = Field(
        None,
        ge=0,
        description="Urutan tampil dalam dokumen (0-based, untuk sort yang benar)",
        examples=[4],
    )
    page: Optional[int] = Field(
        None,
        ge=1,
        description="Halaman PDF tempat pasal ini dimulai (1-indexed)",
        examples=[1],
    )
    parent_order_index: Optional[int] = Field(
        None,
        ge=0,
        description="order_index pasal induk dalam dokumen yang sama (0-based)",
        examples=[0],
    )
    embedding: Optional[List[float]] = Field(
        None,
        description=(
            "Vektor embedding dimensi 1536 (pgvector). "
            "Kirimkan null / omit jika embedding belum tersedia."
        ),
    )

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        allowed = {"bab", "bagian", "paragraf", "pasal", "ayat", "huruf"}
        if v.lower() not in allowed:
            raise ValueError(f"level harus salah satu dari: {allowed}")
        return v.lower()

    @field_validator("embedding")
    @classmethod
    def validate_embedding_dim(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None and len(v) != 1536:
            raise ValueError(
                f"embedding harus memiliki tepat 1536 dimensi, diterima: {len(v)}"
            )
        return v

    model_config = {"json_schema_extra": {"example": {
        "document_id": 1,
        "level": "pasal",
        "chapter_title": "BAB II RUANG LINGKUP",
        "article_number": "Pasal 5",
        "content_text": "Ketentuan ini berlaku bagi seluruh lembaga keuangan...",
        "order_index": 4,
        "page": 1,
        "parent_order_index": None,
        "embedding": None,
    }}}


class BulkArticleIn(BaseModel):
    """Payload untuk bulk insert: list chunk pasal dari satu batch ML pipeline."""

    articles: List[ArticleChunkIn] = Field(
        ...,
        min_length=1,
        description="Daftar chunk pasal yang akan dimasukkan ke database (min. 1 item)",
    )
    replace_document_ids: Optional[List[int]] = Field(
        None,
        description="Daftar ID dokumen yang seluruh pasalnya akan dihapus terlebih dahulu sebelum upsert dalam transaksi yang sama",
    )


class BulkArticleResponse(BaseModel):
    """Response setelah bulk insert/upsert berhasil."""

    status: str = Field("ok", description="Status operasi")
    inserted_count: int = Field(..., description="Jumlah pasal baru yang berhasil disimpan")
    updated_count: int = Field(0, description="Jumlah pasal yang berhasil diperbarui (upsert)")
    deleted_count: int = Field(0, description="Jumlah pasal yang dihapus (dari replace_document_ids)")
    message: str = Field(..., description="Pesan ringkasan")


# Schemas untuk PUT /api/v1/documents/{document_id}/status
from app.models.enums import StatusKeberlakuan  # noqa: E402 (import di bawah karena satu file)


class UpdateDocumentStatusIn(BaseModel):
    """
    Payload untuk memperbarui status keberlakuan dokumen regulasi.
    Jika status menjadi 'dicabut' atau 'diubah', sertakan revoking_document_id
    agar relasi LegalReference otomatis dibuat.
    """

    status_keberlakuan: StatusKeberlakuan = Field(
        ...,
        description="Status keberlakuan baru: berlaku | diubah | dicabut | tidak_diketahui",
    )
    revoking_document_id: Optional[int] = Field(
        None,
        description=(
            "ID dokumen yang mencabut/mengubah dokumen ini. "
            "Wajib diisi jika status_keberlakuan adalah 'dicabut' atau 'diubah' "
            "agar entri LegalReference otomatis terbuat."
        ),
        examples=[7],
    )

    model_config = {"json_schema_extra": {"example": {
        "status_keberlakuan": "dicabut",
        "revoking_document_id": 7,
    }}}


class UpdateDocumentStatusResponse(BaseModel):
    """Response setelah status dokumen berhasil diperbarui."""

    status: str = Field("ok", description="Status operasi")
    document_id: int
    status_keberlakuan: str
    legal_reference_created: bool = Field(
        False,
        description="True jika entri LegalReference baru berhasil dibuat",
    )
    legal_reference_id: Optional[int] = Field(
        None,
        description="ID entri LegalReference yang baru dibuat (jika ada)",
    )
    message: str
