"""
app/routers/categories.py
Endpoint manajemen hierarki kategori Knowledge Base.
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.category import Category
from app.models.document import Document
from app.routers.auth import get_current_user
from app.services.category_service import CategoryService

router = APIRouter()


class CategoryCreateRequest(BaseModel):
    name: str
    parent_id: Optional[int] = None


class CategoryDetailResponse(BaseModel):
    id: int
    name: str
    parent_id: Optional[int] = None
    auto_created: bool
    path: List[str]
    document_count: int


@router.get("/", summary="Daftar Kategori Datar")
def list_categories(db: Session = Depends(get_db)):
    """Mengembalikan daftar datar seluruh kategori."""
    return db.query(Category).order_by(Category.id).all()


@router.get("/tree", summary="Pohon Hierarki Kategori KB")
def get_category_tree(db: Session = Depends(get_db)):
    """
    Mengembalikan seluruh hierarki kategori berbentuk pohon bersarang
    dengan document_count (langsung) dan total_document_count (termasuk turunan).
    """
    svc = CategoryService(db)
    return svc.tree()


@router.get("/{category_id}", response_model=CategoryDetailResponse, summary="Detail Kategori dan Jalur Hierarki")
def get_category_detail(category_id: int, db: Session = Depends(get_db)):
    """Mengembalikan detail satu kategori beserta jalur root->leaf dan jumlah dokumen."""
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kategori dengan ID {category_id} tidak ditemukan.",
        )

    svc = CategoryService(db)
    cat_path = svc.path_of(cat)
    doc_count = db.query(Document).filter(Document.category_id == cat.id).count()

    return CategoryDetailResponse(
        id=cat.id,
        name=cat.name,
        parent_id=cat.parent_id,
        auto_created=cat.auto_created,
        path=cat_path,
        document_count=doc_count,
    )


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Buat Kategori Baru")
def create_category(
    body: CategoryCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Membuat kategori baru di root atau di bawah kategori induk.
    """
    svc = CategoryService(db)
    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None

    cat = svc.create(
        name=body.name,
        parent_id=body.parent_id,
        actor_user_id=actor_user_id,
        ip_address=client_ip,
    )
    return cat