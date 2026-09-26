"""
app/schemas/ingest.py
Pydantic schemas untuk endpoint ingest PDF, status pipeline, dan jobs.
"""
from typing import List, Optional
from pydantic import BaseModel, Field
from app.models.enums import StatusJobIngest


class IngestItemDetailResponse(BaseModel):
    filename: str
    status: str = Field(..., description="Status hasil: success | duplicate | failed")
    document_id: Optional[int] = None
    duplicate_of_document_id: Optional[int] = None
    title: Optional[str] = None
    regulation_number: Optional[str] = None
    file_size_bytes: Optional[int] = None
    file_hash: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    reason_code: Optional[str] = None


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
    storage_path: str


class DuplicateCheckResponse(BaseModel):
    is_duplicate: bool
    message: str
    existing_document_id: Optional[int] = None
    regulation_number: Optional[str] = None
