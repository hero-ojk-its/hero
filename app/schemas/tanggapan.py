"""
app/schemas/tanggapan.py
Skema Pydantic untuk penandaan dan tanggapan temuan harmonisasi (Langkah 39, US-49 #71).
"""
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TanggapanTemuanIn(BaseModel):
    temuan: Dict[str, Any] = Field(..., description="Objek temuan dari respons harmonisasi")
    penilaian: str = Field(..., description="Penilaian analis: 'valid' atau 'tidak_relevan'")
    catatan: Optional[str] = Field(None, description="Catatan analis (maksimal 2000 karakter)")
    run_id: Optional[int] = Field(None, description="ID eksekusi tempat temuan ditandai")
    dinilai_oleh_nama: Optional[str] = Field(None, max_length=255, description="Nama penilai opsional (terutama mode auth mati)")

    @field_validator("penilaian")
    @classmethod
    def validate_penilaian(cls, v: str) -> str:
        if v not in ("valid", "tidak_relevan"):
            raise ValueError("Penilaian hanya boleh bernilai 'valid' atau 'tidak_relevan'")
        return v

    @field_validator("catatan")
    @classmethod
    def validate_catatan(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 2000:
            raise ValueError("Catatan maksimal 2000 karakter")
        return v


class TanggapanTemuanResponse(BaseModel):
    id: int
    document_id: int
    kunci_temuan: str
    run_id: Optional[int] = None
    temuan_id_ml: Optional[str] = None
    penilaian: str
    catatan: Optional[str] = None
    ringkasan_temuan: Optional[Dict[str, Any]] = None
    dinilai_oleh: Optional[int] = None
    dinilai_oleh_nama: Optional[str] = None
    dibuat: datetime
    diperbarui: datetime

    model_config = ConfigDict(from_attributes=True)


class RekapJumlah(BaseModel):
    valid: int = 0
    tidak_relevan: int = 0
    total: int = 0


class RekapTanggapanResponse(BaseModel):
    total: RekapJumlah
    per_jenis: Dict[str, RekapJumlah]
    filter: Dict[str, Any]
