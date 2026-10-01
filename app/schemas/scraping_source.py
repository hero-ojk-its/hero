"""
Schema Pydantic: ScrapingSource
[US-12, US-16, FR-SCR-05] Validasi request & response untuk pengelolaan sumber dokumen (situs web, folder lokal, OneDrive).
"""
from datetime import datetime
from typing import Optional, List
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, model_validator

from app.models.enums import JenisSumber, KlasifikasiAkses, PeranDokumen


def validate_http_url(v: str) -> str:
    """
    Validasi string harus berupa URL valid dengan skema http:// atau https://.
    Memastikan format URL memiliki domain (netloc) yang benar.
    Melempar ValueError jika format tidak valid.
    """
    if not v or not isinstance(v, str):
        raise ValueError("URL wajib diisi dan berupa string.")

    trimmed = v.strip()
    if not trimmed:
        raise ValueError("URL tidak boleh kosong.")

    if " " in trimmed:
        raise ValueError("URL tidak boleh mengandung spasi.")

    try:
        parsed = urlparse(trimmed)
    except Exception as exc:
        raise ValueError(f"Format URL tidak valid: {exc}")

    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL harus diawali dengan protokol http:// atau https://.")

    if not parsed.netloc or "." not in parsed.netloc:
        raise ValueError("URL harus memiliki domain yang valid (misal: https://jdih.ojk.go.id).")

    return trimmed


class ScrapingSourceCreate(BaseModel):
    """Schema input untuk penambahan sumber dokumen baru (POST /)"""
    name: str
    url: str
    source_type: JenisSumber = JenisSumber.situs_web
    crawler_adapter: Optional[str] = None
    crawl_depth: Optional[int] = None
    recursive: bool = True
    default_access_classification: Optional[KlasifikasiAkses] = None
    default_document_role: PeranDokumen = PeranDokumen.corpus_eksisting
    default_naming_format: Optional[List[str]] = None
    default_naming_separator: Optional[str] = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_rules(self):
        if self.source_type == JenisSumber.situs_web:
            if self.crawl_depth is None:
                self.crawl_depth = 1
            elif not (1 <= self.crawl_depth <= 5):
                raise ValueError("Kedalaman crawling (crawl_depth) untuk situs web harus bernilai antara 1 dan 5.")
            if self.default_access_classification is None:
                self.default_access_classification = KlasifikasiAkses.publik
        elif self.source_type == JenisSumber.folder_lokal:
            if self.crawl_depth is not None:
                raise ValueError("Kedalaman crawling (crawl_depth) harus bernilai NULL untuk jenis sumber folder lokal.")
            if self.default_access_classification is None:
                self.default_access_classification = KlasifikasiAkses.non_publik
        elif self.source_type == JenisSumber.onedrive_public:
            if self.default_access_classification is None:
                self.default_access_classification = KlasifikasiAkses.non_publik
        return self


class ScrapingSourceUpdate(BaseModel):
    """Schema input untuk pembaruan sumber dokumen (PUT/PATCH /{id})"""
    name: Optional[str] = None
    url: Optional[str] = None
    source_type: Optional[JenisSumber] = None
    crawler_adapter: Optional[str] = None
    crawl_depth: Optional[int] = None
    recursive: Optional[bool] = None
    default_access_classification: Optional[KlasifikasiAkses] = None
    default_document_role: Optional[PeranDokumen] = None
    default_naming_format: Optional[List[str]] = None
    default_naming_separator: Optional[str] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def validate_rules(self):
        if self.source_type == JenisSumber.situs_web:
            if self.crawl_depth is not None and not (1 <= self.crawl_depth <= 5):
                raise ValueError("Kedalaman crawling (crawl_depth) untuk situs web harus bernilai antara 1 dan 5.")
        elif self.source_type == JenisSumber.folder_lokal:
            if self.crawl_depth is not None:
                raise ValueError(f"Kedalaman crawling (crawl_depth) harus bernilai NULL untuk jenis sumber {self.source_type.value}.")
        return self


class ScrapingSourceRunRequest(BaseModel):
    """Schema input opsional saat mengeksekusi run sumber (POST /{id}/run)"""
    naming_format: Optional[List[str]] = None
    naming_separator: Optional[str] = None


class ScrapingSourceResponse(BaseModel):
    """Schema response data situs/folder sumber dokumen"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    address: Optional[str] = None
    source_type: JenisSumber
    crawler_adapter: Optional[str] = None
    crawl_depth: Optional[int] = None
    recursive: bool = True
    default_access_classification: KlasifikasiAkses
    default_document_role: PeranDokumen
    default_naming_format: Optional[List[str]] = None
    default_naming_separator: Optional[str] = None
    is_active: bool
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    last_run_message: Optional[str] = None
    last_job_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="after")
    def populate_address(self):
        if self.address is None:
            self.address = self.url
        return self


class SourceFileItem(BaseModel):
    """Schema item berkas hasil pemindaian sumber"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    relative_path: str
    size_bytes: int
    mtime: datetime
    file_hash: Optional[str] = None
    document_id: Optional[int] = None
    document_title: Optional[str] = None
    last_outcome: str
    last_seen_job_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SourceFileListResponse(BaseModel):
    """Schema daftar berkas pada sumber (pagination)"""
    total: int
    items: List[SourceFileItem]
