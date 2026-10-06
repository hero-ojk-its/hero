"""Request/response models — the contract the frontend is built against.

Every badge in the design is a ``Badge``: the backend owns the value, the
Indonesian label and the tone (success / warning / danger / info / neutral),
so the frontend maps *tone → colour* once and never re-implements
"berlaku means Aktif means green".

Generate TypeScript types from ``docs/openapi.json`` (e.g. openapi-typescript)
instead of hand-writing them.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class Badge(BaseModel):
    value: Optional[str] = None
    label: str
    tone: Literal["success", "warning", "danger", "info", "neutral"] = "neutral"


class Option(BaseModel):
    value: Optional[str] = None
    label: Optional[str] = None


# ---------------------------------------------------------------- Knowledge Base
class KbListItem(BaseModel):
    id: str
    judul: str
    jenis: Optional[str]
    nomor: Optional[str] = Field(None, description='Nomor lengkap, mis. "11/POJK.03/2024"')
    nomor_singkat: Optional[str] = Field(None, description='Bentuk tabel, mis. "POJK-11/2024"')
    kategori: Option
    topik: str
    tahun: Optional[int]
    status: Badge
    sumber: Option
    cocok: Optional[dict] = Field(None, description="Hanya pada mode semantic/hybrid: pasal yang paling cocok")


class KbListResponse(BaseModel):
    items: list[KbListItem]
    total: int
    page: int
    page_size: int
    pages: int
    mode: str = "lexical"
    pencarian: Optional[str] = Field(
        None, description="semua_kata | sebagian_kata — bila sebagian_kata, tampilkan "
                          "'Tidak ada yang cocok persis; menampilkan hasil yang cocok sebagian'")
    waktu_ms: float


class FacetValue(BaseModel):
    value: str | int
    label: str
    count: int


class PoinKunci(BaseModel):
    kategori: Optional[str]
    pasal: Optional[str]
    halaman: Optional[int]
    teks: str


class Validasi(BaseModel):
    value: Optional[str]
    label: str
    tone: str
    alasan: Optional[str]
    tampil: Optional[str] = None


class KbDetail(KbListItem):
    judul_asli: Optional[str]
    tentang: Optional[str]
    topik_semua: list[str]
    topik_alasan: list[dict]
    tanggal_terbit: dict
    sumber_detail: Optional[str]
    akses: Option
    ringkasan: Optional[str]
    poin_kunci: list[PoinKunci]
    validasi: dict[str, Validasi]
    jumlah_pasal: int
    jumlah_halaman: Optional[int]
    dasar_hukum: list[str]
    pdf: dict


# ---------------------------------------------------------------- Ingest
class UrlScanRequest(BaseModel):
    url: HttpUrl
    kedalaman: int = Field(2, ge=0, le=3, description="Level penelusuran tautan dari halaman sumber")
    kategori: Optional[str] = Field(None, description="Kategori target Knowledge Base (slug dari /api/kb/facets)")
    sektor: Optional[list[str]] = Field(None, description="Khusus JDIH: kode sektor, mis. ['01']")
    jenis: Optional[list[str]] = Field(None, description="Khusus JDIH: kode jenis, mis. ['06']")
    maks_item: int = Field(50, ge=1, le=300)


class SyncScanRequest(BaseModel):
    sumber: Literal["onedrive", "folder"]
    sumber_nama: Optional[str] = Field(None, description="Nama sumber OneDrive terdaftar (dari /api/sync/sources)")
    share_url: Optional[str] = None
    subfolder: Optional[str] = None
    path: Optional[str] = Field(None, description="Folder lokal (hanya bila sumber='folder')")
    klasifikasi_akses: Literal["publik", "internal", "rahasia"] = "internal"
    kategori: Optional[str] = None
    maks_item: int = Field(200, ge=1, le=3000)


class StartedResponse(BaseModel):
    id: str
    status_url: str


class IngestJobRequest(BaseModel):
    scan_id: str
    item_ids: list[str] = Field(..., min_length=1)
    kategori: Optional[str] = None


# ---------------------------------------------------------------- Search
SearchMethod = Literal["lexical", "lsa", "semantic", "hybrid"]
