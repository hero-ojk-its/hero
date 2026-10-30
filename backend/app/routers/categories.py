"""
app/routers/categories.py
Endpoint manajemen hierarki kategori Knowledge Base.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.category import Category
from app.models.document import Document
from app.core.permissions import perlu_izin, Izin
from app.services.category_service import CategoryService
from app.services.storage_service import StorageService, get_storage_service

router = APIRouter()


class CategoryCreateRequest(BaseModel):
    name: str
    parent_id: Optional[int] = None
    classification_rule: Optional[str] = None


class CategoryUpdateRequest(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    classification_rule: Optional[str] = None


class CategoryDetailResponse(BaseModel):
    id: int
    name: str
    parent_id: Optional[int] = None
    auto_created: bool
    path: List[str]
    document_count: int
    jumlah_dokumen: int
    classification_rule: Optional[str] = None


@router.get("/", summary="Daftar Kategori Datar")
def list_categories(
    db: Session = Depends(get_db),
    _user=Depends(perlu_izin(Izin.KB_BACA)),
):
    """Mengembalikan daftar datar seluruh kategori."""
    return db.query(Category).order_by(Category.id).all()


@router.get("/tree", summary="Pohon Hierarki Kategori KB")
def get_category_tree(
    db: Session = Depends(get_db),
    _user=Depends(perlu_izin(Izin.KB_BACA)),
):
    """
    Mengembalikan seluruh hierarki kategori berbentuk pohon bersarang
    dengan document_count (langsung) dan total_document_count (termasuk turunan).
    """
    svc = CategoryService(db)
    return svc.tree()


@router.get("/{category_id}", response_model=CategoryDetailResponse, summary="Detail Kategori dan Jalur Hierarki")
def get_category_detail(
    category_id: int,
    db: Session = Depends(get_db),
    _user=Depends(perlu_izin(Izin.KB_BACA)),
):
    """Mengembalikan detail satu kategori beserta jalur root->leaf dan jumlah dokumen."""
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kategori dengan ID {category_id} tidak ditemukan.",
        )

    svc = CategoryService(db)
    cat_path = svc.path_of(cat)
    doc_count = (
        db.query(Document)
        .filter(Document.category_id == cat.id, Document.is_active == True)  # noqa: E712
        .count()
    )

    return CategoryDetailResponse(
        id=cat.id,
        name=cat.name,
        parent_id=cat.parent_id,
        auto_created=cat.auto_created,
        path=cat_path,
        document_count=doc_count,
        jumlah_dokumen=doc_count,
        classification_rule=cat.classification_rule,
    )


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Buat Kategori Baru")
def create_category(
    body: CategoryCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(perlu_izin(Izin.KB_KELOLA)),
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
        classification_rule=body.classification_rule,
        actor_user_id=actor_user_id,
        ip_address=client_ip,
    )
    return cat


@router.patch("/{category_id}", summary="Ubah Kategori (Nama, Induk, Aturan Klasifikasi)")
def update_category(
    category_id: int,
    body: CategoryUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user=Depends(perlu_izin(Izin.KB_KELOLA)),
):
    """
    Memperbarui nama, induk (parent_id), dan/atau classification_rule kategori.
    Jika nama atau parent_id berubah, seluruh berkas dokumen terkait dipindahkan.
    """
    svc = CategoryService(db)
    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None

    fields_set = body.model_fields_set if hasattr(body, "model_fields_set") else getattr(body, "__fields_set__", set())

    return svc.update(
        category_id=category_id,
        name=body.name,
        name_provided="name" in fields_set,
        parent_id=body.parent_id,
        parent_id_provided="parent_id" in fields_set,
        classification_rule=body.classification_rule,
        classification_rule_provided="classification_rule" in fields_set,
        actor_user_id=actor_user_id,
        ip_address=client_ip,
        storage=storage,
    )


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Hapus Kategori")
def delete_category(
    category_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(perlu_izin(Izin.KB_KELOLA)),
):
    """
    Menghapus kategori kosong. Menolak jika masih memiliki subkategori atau dokumen.
    """
    svc = CategoryService(db)
    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None

    svc.delete(
        category_id=category_id,
        actor_user_id=actor_user_id,
        ip_address=client_ip,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)