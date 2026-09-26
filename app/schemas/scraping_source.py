"""
Schema Pydantic: ScrapingSource
[US-12] Validasi request & response untuk pengelolaan situs sumber scraping.
"""
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict


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


class ScrapingSourceBase(BaseModel):
    name: str
    url: str
    is_active: bool = True


class ScrapingSourceCreate(ScrapingSourceBase):
    """Schema input untuk penambahan situs sumber scraping baru (POST /)"""
    pass


class ScrapingSourceUpdate(BaseModel):
    """Schema input untuk pembaruan situs sumber scraping (PUT/PATCH /{id})"""
    name: Optional[str] = None
    url: Optional[str] = None
    is_active: Optional[bool] = None


class ScrapingSourceResponse(BaseModel):
    """Schema response data situs sumber scraping"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
