"""
app/schemas/harmonisasi.py
Model skema Pydantic untuk respons gerbang harmonisasi ML.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class HarmonisasiBadge(BaseModel):
    model_config = ConfigDict(extra="allow")
    tone: Optional[Any] = None
    label: Optional[Any] = None


class HarmonisasiPembanding(BaseModel):
    model_config = ConfigDict(extra="allow")
    document_id: Optional[int] = None
    key: Optional[Any] = None
    nomor: Optional[Any] = None
    status: Optional[Any] = None
    judul: Optional[Any] = None
    pdf: Optional[Any] = None
    tautan: Optional[Any] = None


class HarmonisasiTemuan(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: Optional[Any] = None
    jenis: Optional[Any] = None
    judul: Optional[Any] = None
    deskripsi: Optional[Any] = None
    pasal_draft: Optional[Any] = None
    pasal_pembanding: Optional[Any] = None
    badge: Optional[HarmonisasiBadge] = None
    pembanding: Optional[HarmonisasiPembanding] = None


class HarmonisasiRingkasan(BaseModel):
    model_config = ConfigDict(extra="allow")
    total_temuan: Optional[Any] = None
    per_jenis: Optional[Dict[str, Any]] = None
    rencana_perubahan: Optional[Any] = None


class HarmonisasiCache(BaseModel):
    model_config = ConfigDict(extra="allow")
    hit: Optional[bool] = None
    dibuat: Optional[str] = None
    basi: Optional[bool] = None
    mode_tersimpan: Optional[str] = None
    run_id: Optional[int] = None


class HarmonisasiResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    draft: Optional[Dict[str, Any]] = None
    ringkasan: Optional[HarmonisasiRingkasan] = None
    temuan: Optional[List[HarmonisasiTemuan]] = None
    disaring_backend: Optional[int] = None
    disaring_rincian: Optional[Dict[str, int]] = None
    cache: Optional[HarmonisasiCache] = None
    versi: Optional[str] = None
