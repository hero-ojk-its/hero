"""
app/schemas/scan.py
Skema Pydantic untuk modul Alur Pindai Situs (Scan -> Bandingkan -> Centang -> Tarik).
"""
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import StatusPindai, TujuanTarik, StatusKandidat


class ScanCreate(BaseModel):
    """Payload untuk memulai pemindaian situs baru."""
    source_id: int = Field(..., description="ID sumber scraping situs_web atau onedrive_public")
    crawl_depth: Optional[int] = Field(None, ge=1, le=5, description="Override kedalaman crawling (1-5)")
    max_pages: Optional[int] = Field(None, ge=1, description="Override batas halaman yang dikunjungi")
    crawler_adapter: Optional[str] = Field(None, description="Override crawler adapter (sharepoint_postback, jdih_api, onedrive_share, generic_html)")


class ScanSummaryCount(BaseModel):
    """Ringkasan angka kandidat berkas."""
    total: int = 0
    baru: int = 0
    sudah_ada: int = 0
    mungkin_ada: int = 0
    terpilih: int = 0


class CandidateMatchDocument(BaseModel):
    """Informasi ringkas dokumen KB yang cocok dengan kandidat."""
    id: int
    title: str
    regulation_number: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CandidateResponse(BaseModel):
    """Detail satu kandidat PDF hasil pemindaian."""
    id: int
    scan_id: int
    url: str
    filename: str
    size_bytes: Optional[int] = None
    found_on_page: Optional[str] = None
    document_title: Optional[str] = None
    detail_url: Optional[str] = None
    final_url: Optional[str] = None
    doc_kind: Optional[str] = "utama"
    regulation_number: Optional[str] = None
    regulation_type: Optional[str] = None
    bidang: Optional[str] = None
    sub_bidang: Optional[str] = None
    release_date: Optional[date] = None
    effective_date: Optional[date] = None
    regulation_year: Optional[int] = None
    match_warning: Optional[str] = None
    status_keberlakuan: Optional[str] = "tidak_diketahui"
    size_source: Optional[str] = "unknown"
    source_path: Optional[str] = None
    depth: int
    match_status: StatusKandidat
    match_reason: Optional[str] = None
    match_document_id: Optional[int] = None
    match_document: Optional[CandidateMatchDocument] = None
    selected: bool
    pull_outcome: Optional[str] = None
    document_id: Optional[int] = None
    failure_id: Optional[int] = None
    export_path: Optional[str] = None
    message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CandidateListResponse(BaseModel):
    """Daftar kandidat dengan paginasi."""
    items: List[CandidateResponse]
    total: int
    skip: int
    limit: int


class PullProgress(BaseModel):
    """Progres penarikan dokumen dari job terkait."""
    job_id: int
    status: str
    processed_count: int
    total_found: Optional[int]
    progress_percent: Optional[int]


class ScanSessionResponse(BaseModel):
    """Detail lengkap sesi pemindaian situs."""
    id: int
    source_id: Optional[int] = None
    start_url: str
    crawl_depth: int
    mode: str
    crawler_name: Optional[str] = None
    crawler_adapter: Optional[str] = None
    status: StatusPindai
    cancel_requested: bool
    blocked: bool = False
    pages_visited: int
    candidates_summary: ScanSummaryCount
    truncated: bool
    stats: Optional[Dict[str, Any]] = None
    errors: List[str] = []
    error_message: Optional[str] = None
    destination: Optional[TujuanTarik] = None
    naming_format: Optional[List[str]] = None
    naming_separator: Optional[str] = None
    pull_job_id: Optional[int] = None
    category_id: Optional[int] = None
    pull_progress: Optional[PullProgress] = None
    download_url: Optional[str] = None
    claimed_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    scanned_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ScanListResponse(BaseModel):
    """Daftar sesi pemindaian dengan paginasi."""
    items: List[ScanSessionResponse]
    total: int
    skip: int
    limit: int


class ScanSelectionUpdate(BaseModel):
    """Payload untuk memperbarui pilihan centang kandidat."""
    action: str = Field(
        ...,
        description="Aksi seleksi: 'select_all_new' | 'select_none' | 'set'",
    )
    candidate_ids: Optional[List[int]] = Field(
        default=None,
        description="Daftar ID kandidat (wajib jika action='set')",
    )
    selected: Optional[bool] = Field(
        default=None,
        description="Nilai seleksi (true/false) jika action='set'",
    )


class RejectedSelection(BaseModel):
    """Informasi kandidat yang ditolak centangnya (misal: status sudah_ada)."""
    id: int
    reason: str


class ScanSelectionResponse(BaseModel):
    """Hasil pembaruan centang kandidat."""
    scan_id: int
    summary: ScanSummaryCount
    rejected_ids: List[RejectedSelection] = []


class ScanPullRequest(BaseModel):
    """Payload untuk mengeksekusi penarikan berkas kandidat terpilih."""
    destination: TujuanTarik = Field(
        ...,
        description="Tujuan penarikan: 'knowledge_base' atau 'unduh_folder'",
    )
    category_id: Optional[int] = Field(
        default=None,
        description="ID kategori target di Knowledge Base",
    )
    naming_format: Optional[List[str]] = Field(
        default=None,
        description="Daftar urutan komponen penamaan file standar",
    )
    naming_separator: Optional[str] = Field(
        default=None,
        description="Pemisah komponen penamaan (spasi, _, atau -)",
    )


class InternalScanClaimItem(BaseModel):
    """Detail sesi pemindaian yang diklaim oleh worker push eksternal."""
    scan_id: int
    start_url: str
    crawl_depth: int
    max_pages: int
    max_candidates: int


class InternalCandidateIn(BaseModel):
    """Satu kandidat PDF yang dikirimkan oleh crawler eksternal."""
    url: str
    filename: str
    size_bytes: Optional[int] = None
    found_on_page: Optional[str] = None
    depth: int = 1
    document_title: Optional[str] = None
    detail_url: Optional[str] = None
    final_url: Optional[str] = None
    doc_kind: Optional[str] = "utama"
    regulation_number: Optional[str] = None
    regulation_type: Optional[str] = None
    bidang: Optional[str] = None
    sub_bidang: Optional[str] = None
    release_date: Optional[date] = None
    effective_date: Optional[date] = None
    regulation_year: Optional[int] = None
    match_warning: Optional[str] = None
    status_keberlakuan: Optional[str] = "tidak_diketahui"
    size_source: Optional[str] = "unknown"
    source_path: Optional[str] = None


class InternalCandidatesBatchIn(BaseModel):
    """Batch hasil pemindaian yang di-push oleh crawler eksternal."""
    candidates: List[InternalCandidateIn] = []
    pages_visited: int = 0
    done: bool = False
    truncated: Optional[bool] = False
    errors: Optional[List[str]] = []
    error: Optional[str] = None
