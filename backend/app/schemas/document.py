"""
app/schemas/document.py
Model skema Pydantic untuk dokumen dan respons PATCH metadata dokumen.
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class PersetujuanPublikIn(BaseModel):
    disetujui_oleh: Optional[str] = None
    alasan: Optional[str] = None


class PersetujuanPublikOut(BaseModel):
    disetujui_oleh: Optional[str] = None
    alasan: Optional[str] = None
    pada: Optional[datetime] = None


class DocumentMetadataPatchResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    title: Optional[str] = None
    regulation_number: Optional[str] = None
    regulation_type: Optional[str] = None
    release_date: Optional[date] = None
    effective_date: Optional[date] = None
    regulation_year: Optional[int] = None
    bidang: Optional[str] = None
    naming_format: Optional[Any] = None
    naming_separator: Optional[str] = None
    source_url: Optional[str] = None
    original_filename: Optional[str] = None
    file_path_pdf: Optional[str] = None
    standardized_filename: Optional[str] = None
    access_classification: Optional[str] = None
    document_role: Optional[str] = None
    status_keberlakuan: Optional[str] = None
    status_source: Optional[str] = None
    is_attachment: bool = False
    parent_document_id: Optional[int] = None
    parent_identity_key: Optional[str] = None
    attachment_label: Optional[str] = None
    lampiran: Optional[List[Dict[str, Any]]] = None
    induk: Optional[Dict[str, Any]] = None
    processing_status: Optional[str] = None
    extraction_method: Optional[str] = None
    extraction_engine: Optional[str] = None
    category_id: Optional[int] = None
    category_path: Optional[List[str]] = None
    is_placed: bool = False
    kategori_manual: bool = False
    job_id: Optional[int] = None
    pdf_url: Optional[str] = None
    text_url: Optional[str] = None
    full_text_length: int = 0
    extraction_confidence: Optional[Any] = None
    low_confidence_fields: Optional[List[str]] = None
    metadata_corrected_at: Optional[datetime] = None
    extracted_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_active: bool = True
    deactivated_at: Optional[datetime] = None
    deactivated_reason: Optional[str] = None
    identity_key: Optional[str] = None
    page_count: Optional[int] = None
    duplicate_of_id: Optional[int] = None
    changed_fields: List[str] = []
    placement: Optional[Dict[str, Any]] = None
    duplikat: Optional[Dict[str, Any]] = None
    persetujuan_publik: Optional[Dict[str, Any]] = None

