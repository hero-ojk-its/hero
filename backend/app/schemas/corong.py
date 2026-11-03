"""
app/schemas/corong.py
Model skema Pydantic untuk respons statistik corong per sumber.
"""
from typing import Dict, List
from pydantic import BaseModel, ConfigDict


class CorongScanMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")
    ditemukan: int = 0
    sudah_ada_di_kb: int = 0
    ditarik: int = 0
    duplikat: int = 0
    gagal_unduh: int = 0
    belum_ditarik: int = 0


class CorongDokumenMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")
    di_kb: int = 0
    tersimpan_di_kb: int = 0
    menunggu_ekstraksi: int = 0
    terbaca: int = 0
    terbaca_teks_langsung: int = 0
    terbaca_ocr: int = 0
    perlu_koreksi: int = 0
    gagal_baca: int = 0
    lainnya: int = 0
    terpecah_pasal: int = 0
    tervektor: int = 0


class CorongPdfMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")
    terproteksi: int = 0
    terproteksi_terbaca: int = 0
    hasil_pindai_ocr: int = 0
    ocr_gagal: int = 0
    belum_diperiksa: int = 0


class CorongSumberItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    source_id: int
    nama: str
    jenis: str
    scan: CorongScanMetrics
    dokumen: CorongDokumenMetrics
    pdf: CorongPdfMetrics
    gagal_per_alasan: Dict[str, int] = {}
    persen_terbaca: float = 0.0


class CorongUnggahManualItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    dokumen: CorongDokumenMetrics
    pdf: CorongPdfMetrics
    gagal_per_alasan: Dict[str, int] = {}
    persen_terbaca: float = 0.0


class CorongTotalMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")
    scan: CorongScanMetrics
    dokumen: CorongDokumenMetrics
    pdf: CorongPdfMetrics
    gagal_per_alasan: Dict[str, int] = {}
    persen_terbaca: float = 0.0


class CorongResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    dihitung_pada: str
    sumber: List[CorongSumberItem] = []
    unggah_manual: CorongUnggahManualItem
    total: CorongTotalMetrics

