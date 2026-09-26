"""
app/schemas/ingest.py
Pydantic schemas untuk endpoint ingest PDF, status pipeline, jobs, dan penanganan kegagalan (retry queue).
"""
from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator


class IngestItemDetailResponse(BaseModel):
    filename: str
    status: str = Field(..., description="Status hasil: success | duplicate | failed")
    document_id: Optional[int] = None
    duplicate_of_document_id: Optional[int] = None
    failure_id: Optional[int] = None
    title: Optional[str] = None
    regulation_number: Optional[str] = None
    file_size_bytes: Optional[int] = None
    file_hash: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    reason_code: Optional[str] = None
    placement: Optional[Dict[str, Any]] = None


class IngestUploadResponse(BaseModel):
    message: str
    job_id: int
    job_status: str
    total_files: int
    success_count: int
    duplicate_count: int
    failed_count: int
    details: List[IngestItemDetailResponse]


class IngestStatusResponse(BaseModel):
    total_documents: int
    berlaku_documents: int
    dicabut_documents: int
    total_draft_kajian: int
    total_jobs: int
    open_failures: int = 0
    storage_path: str


class DuplicateCheckResponse(BaseModel):
    is_duplicate: bool
    message: str
    existing_document_id: Optional[int] = None
    regulation_number: Optional[str] = None


class JobDocumentSummary(BaseModel):
    id: int
    title: str
    regulation_number: Optional[str] = None
    file_path_pdf: str


class DuplicateDocumentInfo(BaseModel):
    id: int
    title: str
    regulation_number: Optional[str] = None


class JobFailureSummary(BaseModel):
    id: int
    original_filename: str
    failure_type: str
    reason_code: str
    message: str
    is_retryable: bool
    quarantine_path: Optional[str] = None
    attempt_count: int
    follow_up_status: str
    duplicate_of_document_id: Optional[int] = None
    duplicate_of_document: Optional[DuplicateDocumentInfo] = None


class JobDetailResponse(BaseModel):
    id: int
    job_type: str
    source_ref: Optional[str] = None
    source_id: Optional[int] = None
    retry_of_failure_id: Optional[int] = None
    triggered_by: Optional[str] = None
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    success_count: int
    duplicate_count: int
    failed_count: int
    documents: List[JobDocumentSummary] = []
    failures: List[JobFailureSummary] = []


class JobListItemResponse(BaseModel):
    id: int
    job_type: str
    source_ref: Optional[str] = None
    source_id: Optional[int] = None
    triggered_by: Optional[str] = None
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    success_count: int
    duplicate_count: int
    failed_count: int
    open_failures_count: int = 0


class FailureResponse(BaseModel):
    id: int
    job_id: int
    original_filename: str
    source_url: Optional[str] = None
    failure_type: str
    reason_code: str
    message: str
    is_retryable: bool
    quarantine_path: Optional[str] = None
    file_hash: Optional[str] = None
    file_size_bytes: Optional[int] = None
    duplicate_of_document_id: Optional[int] = None
    duplicate_of_document: Optional[DuplicateDocumentInfo] = None
    ingest_options: Dict[str, Any] = {}
    follow_up_status: str
    attempt_count: int
    last_retry_at: Optional[datetime] = None
    last_retry_job_id: Optional[int] = None
    resolved_document_id: Optional[int] = None
    handled_by_user_id: Optional[int] = None
    handling_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class FailureListResponse(BaseModel):
    total: int
    items: List[FailureResponse]


class FailureStatusUpdateRequest(BaseModel):
    follow_up_status: str
    handling_note: Optional[str] = None

    @field_validator("follow_up_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"diabaikan", "belum_ditangani"}
        if v not in allowed:
            raise ValueError("Status hanya boleh 'diabaikan' atau 'belum_ditangani'.")
        return v


class FailureRetryRequest(BaseModel):
    category_id: Optional[int] = None
    access_classification: Optional[str] = None
    document_role: Optional[str] = None


class FailureBatchRetryRequest(BaseModel):
    failure_ids: List[int] = Field(..., min_length=1, max_length=50)


class FailureRetryResponse(BaseModel):
    failure: FailureResponse
    outcome: str
    document_id: Optional[int] = None
    job_id: int
    message: str


class BatchRetryResponse(BaseModel):
    results: List[FailureRetryResponse]
    success_count: int
    duplicate_count: int
    failed_count: int
    skipped_count: int
