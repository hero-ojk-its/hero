"""
app/schemas/category.py
Model skema Pydantic untuk hierarki kategori dan operasi kategori KB.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class CategoryTreeNode(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    name: str
    parent_id: Optional[int] = None
    auto_created: bool = False
    document_count: int = 0
    total_document_count: int = 0
    jumlah_dokumen: int = 0
    jumlah_dokumen_nonaktif: int = 0
    classification_rule: Optional[str] = None
    children: List["CategoryTreeNode"] = []


class CategoryDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="allow")
    id: int
    name: str
    parent_id: Optional[int] = None
    auto_created: bool = False
    path: List[str] = []
    document_count: int = 0
    jumlah_dokumen: int = 0
    jumlah_dokumen_nonaktif: int = 0
    classification_rule: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CategoryUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    kategori: CategoryDetailResponse
    dokumen_dipindah: int = 0
    dokumen_gagal: List[Dict[str, Any]] = []

