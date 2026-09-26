"""
app/schemas/scan.py
Skema Pydantic untuk modul Alur Pindai Situs (Scan -> Bandingkan -> Centang -> Tarik).
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import StatusPindai, TujuanTarik, StatusKandidat


class ScanCreate(BaseModel):
    """Payload untuk memulai pemindaian situs baru."""
    source_id: int = Field(..., description="ID sumber scraping situs_web")
    crawl_depth: Optional[int] = Field(None, ge=1, le=5, description="Override kedalaman crawling (1-5)")
    max_pages: Optional[int] = Field(None, ge=1, description="Override batas halaman yang dikunjungi")


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
    status: StatusPindai
    cancel_requested: bool
    pages_visited: int
    candidates_summary: ScanSummaryCount
    truncated: bool
    errors: List[str] = []
    error_message: Optional[str] = None
    destination: Optional[TujuanTarik] = None
    pull_job_id: Optional[int] = None
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


class InternalCandidatesBatchIn(BaseModel):
    """Batch hasil pemindaian yang di-push oleh crawler eksternal."""
    candidates: List[InternalCandidateIn] = []
    pages_visited: int = 0
    done: bool = False
    truncated: Optional[bool] = False
    errors: Optional[List[str]] = []
    error: Optional[str] = None
