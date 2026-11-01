"""
app/schemas/harmonisasi.py
Model skema Pydantic untuk respons gerbang harmonisasi ML.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class HarmonisasiBadge(BaseModel):
    model_config = ConfigDict(extra="allow")
    tone: Optional[str] = None
    label: Optional[str] = None


class HarmonisasiPembanding(BaseModel):
    model_config = ConfigDict(extra="allow")
    document_id: Optional[int] = None
    key: Optional[str] = None
    nomor: Optional[str] = None
    status: Optional[str] = None
    judul: Optional[str] = None
    pdf: Optional[str] = None
    tautan: Optional[str] = None


class HarmonisasiTemuan(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: Optional[Any] = None
    jenis: Optional[str] = None
    judul: Optional[str] = None
    deskripsi: Optional[str] = None
    pasal_draft: Optional[Any] = None
    pasal_pembanding: Optional[Any] = None
    badge: Optional[HarmonisasiBadge] = None
    pembanding: Optional[HarmonisasiPembanding] = None


class HarmonisasiRingkasan(BaseModel):
    model_config = ConfigDict(extra="allow")
    total_temuan: Optional[int] = 0
    per_jenis: Optional[Dict[str, int]] = None
    rencana_perubahan: Optional[Any] = None


class HarmonisasiCache(BaseModel):
    model_config = ConfigDict(extra="allow")
    hit: bool = False
    dibuat: Optional[str] = None
    basi: bool = False
    mode_tersimpan: Optional[str] = None
    run_id: Optional[int] = None


class HarmonisasiResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    draft: Optional[Dict[str, Any]] = None
    ringkasan: Optional[HarmonisasiRingkasan] = None
    temuan: List[HarmonisasiTemuan] = []
    disaring_backend: Optional[int] = 0
    disaring_rincian: Optional[Dict[str, int]] = None
    cache: Optional[HarmonisasiCache] = None
    versi: Optional[str] = None

