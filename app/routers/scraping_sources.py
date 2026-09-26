"""
Router: /api/v1/scraping-sources
[US-12] CRUD untuk mengelola daftar URL situs sumber scraping regulasi.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.scraping_source import ScrapingSource
from app.schemas.scraping_source import (
    ScrapingSourceCreate,
    ScrapingSourceUpdate,
    ScrapingSourceResponse,
    validate_http_url,
)

router = APIRouter()


@router.post(
    "/",
    response_model=ScrapingSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Menambah situs sumber scraping baru",
)
def create_scraping_source(
    payload: ScrapingSourceCreate,
    db: Session = Depends(get_db),
):
    """
    [US-12] Menambah situs sumber baru.
    Kembalikan error 400 jika:
    - Format URL salah (tidak valid)
    - URL sudah terdaftar di database
    - Nama situs sumber kosong
    """
    # 1. Validasi nama
    if not payload.name or not payload.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nama situs sumber scraping tidak boleh kosong.",
        )

    # 2. Validasi format URL
    try:
        valid_url = validate_http_url(payload.url)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Format URL salah: {str(err)}",
        )

    # 3. Cek apakah URL sudah terdaftar
    existing = db.query(ScrapingSource).filter(ScrapingSource.url == valid_url).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"URL '{valid_url}' sudah terdaftar pada situs sumber ID {existing.id} ('{existing.name}').",
        )

    # 4. Buat record baru
    source = ScrapingSource(
        name=payload.name.strip(),
        url=valid_url,
        is_active=payload.is_active,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get(
    "/",
    response_model=List[ScrapingSourceResponse],
    summary="Menampilkan daftar semua situs sumber scraping",
)
def list_scraping_sources(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    """
    [US-12] Menampilkan daftar semua situs sumber scraping.
    Mendukung filter opsional `is_active` (true/false).
    """
    query = db.query(ScrapingSource)
    if is_active is not None:
        query = query.filter(ScrapingSource.is_active == is_active)
    return query.order_by(ScrapingSource.id.asc()).all()


@router.get(
    "/{source_id}",
    response_model=ScrapingSourceResponse,
    summary="Detail satu situs sumber scraping",
)
def get_scraping_source(
    source_id: int,
    db: Session = Depends(get_db),
):
    """Mendapatkan detail satu situs sumber scraping berdasarkan ID."""
    source = db.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Situs sumber scraping dengan ID {source_id} tidak ditemukan.",
        )
    return source


def _process_update(
    source_id: int,
    payload: ScrapingSourceUpdate,
    db: Session,
) -> ScrapingSource:
    """Helper untuk update data situs sumber (digunakan oleh PUT dan PATCH)"""
    source = db.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Situs sumber scraping dengan ID {source_id} tidak ditemukan.",
        )

    # Validasi & update nama jika disediakan
    if payload.name is not None:
        trimmed_name = payload.name.strip()
        if not trimmed_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nama situs sumber scraping tidak boleh kosong.",
            )
        source.name = trimmed_name

    # Validasi & update URL jika disediakan
    if payload.url is not None:
        try:
            valid_url = validate_http_url(payload.url)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Format URL salah: {str(err)}",
            )

        # Cek apakah URL digunakan oleh ID lain
        duplicate = (
            db.query(ScrapingSource)
            .filter(ScrapingSource.url == valid_url, ScrapingSource.id != source_id)
            .first()
        )
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"URL '{valid_url}' sudah digunakan oleh situs sumber ID {duplicate.id} ('{duplicate.name}').",
            )
        source.url = valid_url

    # Update status aktif jika disediakan
    if payload.is_active is not None:
        source.is_active = payload.is_active

    db.commit()
    db.refresh(source)
    return source


@router.put(
    "/{source_id}",
    response_model=ScrapingSourceResponse,
    summary="Mengubah nama, URL, atau status situs sumber (PUT)",
)
def update_scraping_source_put(
    source_id: int,
    payload: ScrapingSourceUpdate,
    db: Session = Depends(get_db),
):
    """[US-12] Mengubah nama, URL, atau menonaktifkan situs (is_active = False) via PUT."""
    return _process_update(source_id, payload, db)


@router.patch(
    "/{source_id}",
    response_model=ScrapingSourceResponse,
    summary="Mengubah nama, URL, atau status situs sumber (PATCH)",
)
def update_scraping_source_patch(
    source_id: int,
    payload: ScrapingSourceUpdate,
    db: Session = Depends(get_db),
):
    """[US-12] Mengubah nama, URL, atau menonaktifkan situs (is_active = False) via PATCH."""
    return _process_update(source_id, payload, db)


@router.delete(
    "/{source_id}",
    summary="Menghapus situs sumber scraping",
)
def delete_scraping_source(
    source_id: int,
    db: Session = Depends(get_db),
):
    """
    [US-12] Menghapus situs sumber scraping berdasarkan ID.
    """
    source = db.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Situs sumber scraping dengan ID {source_id} tidak ditemukan.",
        )

    db.delete(source)
    db.commit()
    return {
        "message": f"Situs sumber scraping '{source.name}' berhasil dihapus.",
        "id": source_id,
    }
