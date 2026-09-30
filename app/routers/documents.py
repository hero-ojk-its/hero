"""
Router: /api/v1/documents
Endpoint untuk membaca daftar dokumen regulasi, detail pasal-pasal,
unduhan PDF, pembacaan teks, koreksi metadata, serta antrean koreksi (needs-review).
"""
from datetime import date, datetime, timezone
import logging
import re
from typing import Optional, List, Dict, Any
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import or_, and_, desc
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.category import Category
from app.models.article import Article, LegalReference
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
    JenisRujukan,
)
from app.schemas.article import UpdateDocumentStatusIn, UpdateDocumentStatusResponse
from app.routers.auth import get_current_user
from app.services.audit_service import (
    record_audit,
    UPDATE_DOCUMENT_STATUS,
    OPEN_PDF,
    DOWNLOAD_PDF,
    UPDATE_METADATA,
)
from app.services.storage_service import StorageService, get_storage_service
from app.services.category_service import CategoryService
from app.services.placement_service import PlacementService
from app.services.naming_service import (
    NamingInput,
    is_metadata_sufficient,
    normalize_regulation_type,
)
from app.services.search_service import SearchService, SearchParams, SearchMode, SearchSort

logger = logging.getLogger("hero")
router = APIRouter()


class UpdateMetadataIn(BaseModel):
    title: Optional[str] = None
    regulation_number: Optional[str] = None
    regulation_type: Optional[str] = None
    release_date: Optional[date] = None
    bidang: Optional[str] = None
    category_id: Optional[int] = None
    access_classification: Optional[KlasifikasiAkses] = None
    document_role: Optional[PeranDokumen] = None


@router.get("/", summary="Daftar & pencarian dokumen regulasi")
def list_documents(
    q: Optional[str] = Query(None, description="Kata kunci pencarian"),
    mode: SearchMode = Query(SearchMode.phrase, description="Mode pencarian teks: phrase, all, web"),
    regulation_number: Optional[str] = Query(None, description="Filter nomor regulasi"),
    regulation_type: Optional[str] = Query(None, description="Filter jenis regulasi"),
    category_id: Optional[int] = Query(None, description="Filter ID kategori folder KB"),
    include_subcategories: bool = Query(True, description="Sertakan subkategori jika category_id diisi"),
    status_keberlakuan: Optional[List[StatusKeberlakuan]] = Query(None, description="Filter status keberlakuan (bisa berulang)"),
    document_role: Optional[PeranDokumen] = Query(None, description="Filter peran dokumen"),
    access_classification: Optional[KlasifikasiAkses] = Query(None, description="Filter klasifikasi akses"),
    processing_status: Optional[StatusPemrosesan] = Query(None, description="Filter status pemrosesan"),
    date_from: Optional[date] = Query(None, description="Filter tanggal rilis awal (inklusif)"),
    date_to: Optional[date] = Query(None, description="Filter tanggal rilis akhir (inklusif)"),
    year: Optional[int] = Query(None, description="Filter tahun rilis"),
    bidang: Optional[str] = Query(None, description="Filter sektor atau bidang regulasi (misal: Perbankan, BMKS)"),
    sort: Optional[SearchSort] = Query(None, description="Pengurutan hasil pencarian"),
    skip: int = Query(0, ge=0, description="Offset pagination"),
    limit: int = Query(20, ge=1, description="Batas dokumen per halaman (maks 100)"),
    db: Session = Depends(get_db),
):
    """
    Mengembalikan daftar dokumen regulasi dengan pagination dan pencarian full-text / multi-filter.
    """
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from tidak boleh lebih besar dari date_to")

    effective_sort = sort
    if effective_sort is None:
        effective_sort = SearchSort.relevance if (q and q.strip()) else SearchSort.release_date_desc

    clamped_limit = min(max(1, limit), 100)

    params = SearchParams(
        q=q,
        mode=mode,
        regulation_number=regulation_number,
        regulation_type=regulation_type,
        category_id=category_id,
        include_subcategories=include_subcategories,
        status_keberlakuan=status_keberlakuan,
        document_role=document_role,
        access_classification=access_classification,
        processing_status=processing_status,
        date_from=date_from,
        date_to=date_to,
        year=year,
        bidang=bidang,
        sort=sort,
        skip=skip,
        limit=clamped_limit,
    )

    search_svc = SearchService(db)
    try:
        total, items = search_svc.search(params)
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))

    return {
        "total": total,
        "items": items,
        "query": {
            "q": q,
            "mode": mode.value if hasattr(mode, "value") else str(mode),
            "regulation_number": regulation_number,
            "regulation_type": regulation_type,
            "category_id": category_id,
            "include_subcategories": include_subcategories,
            "status_keberlakuan": [s.value if hasattr(s, "value") else str(s) for s in status_keberlakuan] if status_keberlakuan else None,
            "document_role": document_role.value if document_role and hasattr(document_role, "value") else document_role,
            "access_classification": access_classification.value if access_classification and hasattr(access_classification, "value") else access_classification,
            "processing_status": processing_status.value if processing_status and hasattr(processing_status, "value") else processing_status,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "year": year,
            "bidang": bidang,
            "sort": effective_sort.value if hasattr(effective_sort, "value") else str(effective_sort),
            "skip": skip,
            "limit": clamped_limit,
        },
    }


@router.post("/place-pending", summary="Tempatkan semua dokumen yang belum berada di kb/")
def place_pending_documents(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user=Depends(get_current_user),
):
    """
    Menjalankan penempatan berkas untuk dokumen-dokumen yang belum ditempatkan di kb/.
    """
    cat_svc = CategoryService(db)
    place_svc = PlacementService(db, storage, cat_svc, settings)

    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None

    results = place_svc.place_pending(limit=limit, actor_user_id=actor_user_id, ip_address=client_ip)

    placed_cnt = sum(1 for r in results if r.placed and r.reason in ("ditempatkan", "sudah_ditempatkan"))
    skipped_cnt = sum(1 for r in results if not r.placed and r.reason in ("metadata_belum_cukup", "sudah_ditempatkan"))
    failed_cnt = sum(1 for r in results if r.reason.startswith("gagal"))

    return {
        "processed": len(results),
        "placed": placed_cnt,
        "skipped": skipped_cnt,
        "failed": failed_cnt,
        "results": [
            {
                "document_id": r.document_id,
                "placed": r.placed,
                "reason": r.reason,
                "old_path": r.old_path,
                "new_path": r.new_path,
                "category_id": r.category_id,
                "category_path": r.category_path,
            }
            for r in results
        ],
    }


@router.get("/needs-review", summary="Antrean dokumen yang memerlukan koreksi metadata manual")
def get_documents_needing_review(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Mengembalikan dokumen berstatus `perlu_koreksi`, ditambah dokumen berstatus `terindeks`
    yang memiliki field hasil ekstraksi dengan confidence di bawah threshold dan belum dikoreksi manual.
    """
    # Ambil dokumen dengan status perlu_koreksi ATAU (terindeks + metadata_corrected_at IS NULL + extraction_confidence IS NOT NULL)
    candidates = (
        db.query(Document)
        .filter(
            or_(
                Document.processing_status == StatusPemrosesan.perlu_koreksi,
                and_(
                    Document.processing_status == StatusPemrosesan.terindeks,
                    Document.metadata_corrected_at.is_(None),
                    Document.extraction_confidence.isnot(None),
                ),
            )
        )
        .order_by(desc(Document.id))
        .all()
    )

    filtered_items = []
    for doc in candidates:
        low_conf = []
        if doc.extraction_confidence and isinstance(doc.extraction_confidence, dict):
            low_conf = [
                k for k, v in doc.extraction_confidence.items()
                if isinstance(v, (int, float)) and v < settings.metadata_confidence_threshold
            ]

        if doc.processing_status == StatusPemrosesan.perlu_koreksi or (doc.processing_status == StatusPemrosesan.terindeks and low_conf):
            filtered_items.append({
                "id": doc.id,
                "title": doc.title,
                "regulation_number": doc.regulation_number,
                "low_confidence_fields": low_conf,
                "extraction_confidence": doc.extraction_confidence,
                "pdf_url": f"/api/v1/documents/{doc.id}/pdf",
                "processing_status": doc.processing_status,
                "created_at": doc.created_at,
            })

    total = len(filtered_items)
    paginated = filtered_items[skip : skip + limit]

    return {
        "total": total,
        "items": paginated,
    }


def _format_single_document_response(doc: Document, db: Session) -> Dict[str, Any]:
    """Helper untuk memformat detail dokumen tunggal dengan seluruh metadata Step 5."""
    top_articles = (
        db.query(Article)
        .filter(Article.document_id == doc.id, Article.parent_id.is_(None))
        .order_by(Article.order_index)
        .all()
    )

    legal_refs = (
        db.query(LegalReference)
        .filter(LegalReference.document_id == doc.id)
        .all()
    )

    cat_path = None
    if doc.category_id:
        cat = db.query(Category).filter(Category.id == doc.category_id).first()
        if cat:
            cat_svc = CategoryService(db)
            cat_path = cat_svc.path_of(cat)

    is_placed = bool(doc.file_path_pdf and doc.file_path_pdf.replace("\\", "/").startswith("kb/"))

    low_conf = []
    if doc.extraction_confidence and isinstance(doc.extraction_confidence, dict):
        low_conf = [
            k for k, v in doc.extraction_confidence.items()
            if isinstance(v, (int, float)) and v < settings.metadata_confidence_threshold
        ]

    return {
        "id": doc.id,
        "title": doc.title,
        "regulation_number": doc.regulation_number,
        "regulation_type": getattr(doc, "regulation_type", None),
        "release_date": doc.release_date,
        "bidang": getattr(doc, "bidang", None),
        "naming_format": getattr(doc, "naming_format", None),
        "naming_separator": getattr(doc, "naming_separator", None),
        "source_url": doc.source_url,
        "original_filename": getattr(doc, "original_filename", None),
        "file_path_pdf": doc.file_path_pdf,
        "standardized_filename": doc.standardized_filename,
        "access_classification": doc.access_classification,
        "document_role": doc.document_role,
        "status_keberlakuan": doc.status_keberlakuan,
        "processing_status": doc.processing_status,
        "extraction_method": getattr(doc, "extraction_method", None),
        "extraction_engine": getattr(doc, "extraction_engine", None),
        "category_id": doc.category_id,
        "category_path": cat_path,
        "is_placed": is_placed,
        "job_id": doc.job_id,
        "pdf_url": f"/api/v1/documents/{doc.id}/pdf",
        "text_url": f"/api/v1/documents/{doc.id}/text",
        "full_text_length": len(doc.full_text) if doc.full_text else 0,
        "extraction_confidence": doc.extraction_confidence,
        "low_confidence_fields": low_conf,
        "metadata_corrected_at": doc.metadata_corrected_at,
        "extracted_at": doc.extracted_at,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
        "articles": [
            {
                "id": a.id,
                "level": a.level,
                "chapter_title": a.chapter_title,
                "article_number": a.article_number,
                "content_text": a.content_text[:300] + "..." if a.content_text and len(a.content_text) > 300 else a.content_text,
                "order_index": a.order_index,
            }
            for a in top_articles
        ],
        "legal_references": [
            {
                "id": lr.id,
                "cited_text": lr.cited_text,
                "reference_type": lr.reference_type,
                "referenced_document_id": lr.referenced_document_id,
                "referenced_document_status": lr.referenced_document_status,
                "created_at": lr.created_at,
            }
            for lr in legal_refs
        ],
    }


@router.get(
    "/{document_id}",
    summary="Detail satu dokumen beserta pasalnya",
    responses={
        404: {"description": "Dokumen tidak ditemukan"},
    },
)
def get_document(document_id: int, db: Session = Depends(get_db)):
    """Mengembalikan detail lengkap dokumen beserta pasal level teratas, rujukan hukum, dan status penempatan KB."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")

    return _format_single_document_response(doc, db)


@router.get(
    "/{document_id}/pdf",
    summary="Buka atau unduh berkas PDF asli",
    responses={
        403: {"description": "Dokumen non-publik memerlukan autentikasi aktif"},
        404: {"description": "Dokumen atau berkas fisik PDF tidak ditemukan"},
    },
)
def get_document_pdf(
    document_id: int,
    request: Request,
    download: bool = Query(False, description="Jika true, set Content-Disposition ke attachment"),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user=Depends(get_current_user),
):
    """
    Mengembalikan berkas PDF asli dari penyimpanan.
    Mencatat audit OPEN_PDF atau DOWNLOAD_PDF.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")

    if settings.protect_non_public_when_auth_disabled and not settings.auth_enabled:
        if doc.access_classification == KlasifikasiAkses.non_publik:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Dokumen non-publik hanya dapat dibuka setelah login diaktifkan.",
            )

    if not doc.file_path_pdf or not storage.exists(doc.file_path_pdf):
        logger.error("Berkas PDF asli tidak ditemukan di penyimpanan untuk dokumen id=%s, path=%s", doc.id, doc.file_path_pdf)
        raise HTTPException(status_code=404, detail="Berkas PDF asli tidak ditemukan di penyimpanan.")

    abs_path = storage.absolute_path(doc.file_path_pdf)

    # Nama berkas
    fname = doc.standardized_filename or (f"{doc.title}.pdf" if doc.title else "dokumen.pdf")
    if not fname.lower().endswith(".pdf"):
        fname = f"{fname}.pdf"

    disp_type = "attachment" if download else "inline"
    encoded_fname = urllib.parse.quote(fname.encode("utf-8"))
    ascii_fname = re.sub(r"[^\x20-\x7E]", "_", fname)
    content_disp = f'{disp_type}; filename="{ascii_fname}"; filename*=UTF-8\'\'{encoded_fname}'

    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None

    action_type = DOWNLOAD_PDF if download else OPEN_PDF
    record_audit(
        db,
        action=action_type,
        user_id=actor_user_id,
        target_resource=f"document:{doc.id}",
        ip_address=client_ip,
        commit=True,
    )

    return FileResponse(
        path=abs_path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disp,
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get(
    "/{document_id}/text",
    summary="Membaca teks mentah dokumen",
    responses={
        403: {"description": "Dokumen non-publik memerlukan autentikasi aktif"},
        404: {"description": "Dokumen tidak ditemukan"},
    },
)
def get_document_text(
    document_id: int,
    offset: int = Query(0, ge=0, description="Offset karakter teks"),
    limit: int = Query(20000, ge=1, le=100000, description="Batas karakter yang diambil"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Mengembalikan potongan teks mentah hasil ekstraksi dokumen lengkap.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")

    if settings.protect_non_public_when_auth_disabled and not settings.auth_enabled:
        if doc.access_classification == KlasifikasiAkses.non_publik:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Dokumen non-publik hanya dapat dibuka setelah login diaktifkan.",
            )

    full_text = doc.full_text or ""
    total_len = len(full_text)
    sliced_text = full_text[offset : offset + limit]

    return {
        "document_id": doc.id,
        "total_length": total_len,
        "offset": offset,
        "limit": limit,
        "text": sliced_text,
        "extraction_method": doc.extraction_method,
        "extraction_engine": doc.extraction_engine,
        "extracted_at": doc.extracted_at,
    }


@router.patch("/{document_id}/metadata", summary="Koreksi metadata dokumen manual")
def patch_document_metadata(
    document_id: int,
    payload: UpdateMetadataIn,
    request: Request,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user=Depends(get_current_user),
):
    """
    Melakukan koreksi metadata dokumen manual (US-21).
    Perubahan dicatat di audit log dan memicu relokasi/penamaan ulang berkas bila diperlukan.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Dokumen dengan ID {document_id} tidak ditemukan.")

    fields_set = payload.model_fields_set
    if not fields_set:
        raise HTTPException(status_code=422, detail="Minimal satu field metadata harus dikirim.")

    # Validasi
    if "title" in fields_set:
        if payload.title is None or not payload.title.strip():
            raise HTTPException(status_code=422, detail="Judul dokumen tidak boleh kosong atau null.")

    if "access_classification" in fields_set:
        if payload.access_classification is None:
            raise HTTPException(status_code=422, detail="Klasifikasi akses tidak boleh null.")

    if "release_date" in fields_set and payload.release_date is not None:
        if payload.release_date > date.today():
            raise HTTPException(status_code=422, detail="Tanggal rilis tidak boleh melebihi hari ini.")

    if "category_id" in fields_set and payload.category_id is not None:
        cat = db.query(Category).filter(Category.id == payload.category_id).first()
        if not cat:
            raise HTTPException(status_code=404, detail=f"Kategori dengan ID {payload.category_id} tidak ditemukan.")

    # Catat perubahan diff
    before_dict = {}
    after_dict = {}
    changed_fields = []

    for field in fields_set:
        current_val = getattr(doc, field)
        new_val = getattr(payload, field)

        if field == "regulation_type" and new_val is not None:
            new_val = normalize_regulation_type(new_val)
        if field == "title" and new_val is not None:
            new_val = new_val.strip()
        if field == "regulation_number" and new_val is not None:
            new_val = new_val.strip()
        if field == "bidang" and new_val is not None:
            new_val = new_val.strip()

        if current_val != new_val:
            changed_fields.append(field)
            before_dict[field] = current_val.isoformat() if isinstance(current_val, (date, datetime)) else (current_val.value if hasattr(current_val, "value") else current_val)
            after_dict[field] = new_val.isoformat() if isinstance(new_val, (date, datetime)) else (new_val.value if hasattr(new_val, "value") else new_val)
            setattr(doc, field, new_val)

    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None

    doc.metadata_corrected_at = datetime.now(timezone.utc)
    doc.metadata_corrected_by = actor_user_id

    # Cek kecukupan metadata
    naming_inp = NamingInput(
        regulation_number=doc.regulation_number,
        title=doc.title,
        regulation_type=doc.regulation_type,
        release_date=doc.release_date,
        bidang=doc.bidang,
        original_filename=doc.original_filename,
    )
    is_suff = is_metadata_sufficient(naming_inp)

    # Transisi status pemrosesan
    if doc.processing_status in (StatusPemrosesan.perlu_koreksi, StatusPemrosesan.diterima):
        if doc.full_text and doc.full_text.strip() and is_suff:
            doc.processing_status = StatusPemrosesan.terindeks

    # Placement / Relokasi jika field penamaan/kategori berubah
    placement_fields = {"title", "regulation_number", "regulation_type", "release_date", "category_id", "document_role", "bidang"}
    placement_info = None

    if any(f in changed_fields for f in placement_fields) and is_suff:
        cat_svc = CategoryService(db)
        place_svc = PlacementService(db, storage, cat_svc, settings)
        place_res = place_svc.place(doc, force=True, actor_user_id=actor_user_id, ip_address=client_ip)
        placement_info = {
            "document_id": place_res.document_id,
            "placed": place_res.placed,
            "reason": place_res.reason,
            "old_path": place_res.old_path,
            "new_path": place_res.new_path,
            "category_id": place_res.category_id,
            "category_path": place_res.category_path,
        }

    # Audit log
    if changed_fields:
        record_audit(
            db,
            action=UPDATE_METADATA,
            user_id=actor_user_id,
            target_resource=f"document:{doc.id}",
            detail={"before": before_dict, "after": after_dict},
            ip_address=client_ip,
            commit=False,
        )

    db.commit()
    db.refresh(doc)

    formatted = _format_single_document_response(doc, db)
    formatted["changed_fields"] = changed_fields
    formatted["placement"] = placement_info
    return formatted


@router.post("/{document_id}/place", summary="Pemicu penempatan folder KB dokumen")
def place_document(
    document_id: int,
    request: Request,
    force: bool = Query(False, description="Paksa tempatkan ulang meski sudah di bawah kb/"),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user=Depends(get_current_user),
):
    """
    Memicu proses penamaan baku dan pemindahan dokumen ke folder kategori KB.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dokumen dengan ID {document_id} tidak ditemukan.",
        )

    cat_svc = CategoryService(db)
    place_svc = PlacementService(db, storage, cat_svc, settings)

    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None

    res = place_svc.place(doc, force=force, actor_user_id=actor_user_id, ip_address=client_ip)

    return {
        "document_id": res.document_id,
        "placed": res.placed,
        "reason": res.reason,
        "old_path": res.old_path,
        "new_path": res.new_path,
        "category_id": res.category_id,
        "category_path": res.category_path,
    }


@router.put(
    "/{document_id}/status",
    response_model=UpdateDocumentStatusResponse,
    summary="Update status keberlakuan dokumen regulasi",
    description=(
        "Memperbarui kolom `status_keberlakuan` pada dokumen yang dipilih. "
        "Jika status diubah menjadi **`dicabut`** atau **`diubah`** dan "
        "`revoking_document_id` disertakan, endpoint akan otomatis membuat "
        "entri baru di tabel `legal_references` yang mencatat hubungan "
        "pencabutan/perubahan antar dokumen."
    ),
)
def update_document_status(
    document_id: int,
    payload: UpdateDocumentStatusIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> UpdateDocumentStatusResponse:
    """
    Langkah:
    1. Cari dokumen; 404 jika tidak ada.
    2. Jika revoking_document_id disertakan, validasi dokumen pencabut ada.
    3. Update status_keberlakuan.
    4. Jika status dicabut/diubah + revoking_document_id ada → buat LegalReference.
    5. db.commit() dan kembalikan detail.
    """
    # 1. Cari dokumen target
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Dokumen dengan id={document_id} tidak ditemukan")

    # 2. Validasi dokumen pencabut jika diberikan
    revoking_doc = None
    if payload.revoking_document_id is not None:
        revoking_doc = db.query(Document).filter(
            Document.id == payload.revoking_document_id
        ).first()
        if not revoking_doc:
            raise HTTPException(
                status_code=404,
                detail=f"Dokumen pencabut/pengubah dengan id={payload.revoking_document_id} tidak ditemukan",
            )

    try:
        # 3. Update status keberlakuan
        doc.status_keberlakuan = payload.status_keberlakuan

        # 4. Buat LegalReference jika status dicabut/diubah dan revoking_document_id ada
        legal_ref: LegalReference | None = None
        statuses_needing_ref = {StatusKeberlakuan.dicabut, StatusKeberlakuan.diubah}

        if payload.status_keberlakuan in statuses_needing_ref and revoking_doc is not None:
            ref_type = (
                JenisRujukan.pencabutan
                if payload.status_keberlakuan == StatusKeberlakuan.dicabut
                else JenisRujukan.perubahan
            )

            revoking_label = revoking_doc.regulation_number or revoking_doc.title
            target_label = doc.regulation_number or doc.title
            action_word = "mencabut" if ref_type == JenisRujukan.pencabutan else "mengubah"
            cited_text = f"{revoking_label} {action_word} {target_label}"

            legal_ref = LegalReference(
                document_id=document_id,
                cited_text=cited_text,
                referenced_document_id=payload.revoking_document_id,
                referenced_document_status=payload.status_keberlakuan,
                reference_type=ref_type,
            )
            db.add(legal_ref)

        actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
        client_ip = request.client.host if request.client else None
        record_audit(
            db,
            action=UPDATE_DOCUMENT_STATUS,
            user_id=actor_user_id,
            target_resource=f"document:{doc.id}",
            ip_address=client_ip,
            commit=False,
        )

        db.commit()
        db.refresh(doc)
        if legal_ref is not None:
            db.refresh(legal_ref)

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Gagal memperbarui status dokumen: {str(exc)}",
        )

    ref_created = legal_ref is not None
    status_label = payload.status_keberlakuan.value
    doc_label = doc.regulation_number or doc.title

    if ref_created:
        revoking_label = revoking_doc.regulation_number or revoking_doc.title  # type: ignore[union-attr]
        action_word = "dicabut" if payload.status_keberlakuan == StatusKeberlakuan.dicabut else "diubah"
        message = (
            f"Dokumen '{doc_label}' berhasil ditandai sebagai '{status_label}' "
            f"oleh '{revoking_label}'. LegalReference id={legal_ref.id} dibuat."
        )
    else:
        message = f"Status dokumen '{doc_label}' berhasil diperbarui menjadi '{status_label}'."

    return UpdateDocumentStatusResponse(
        status="ok",
        document_id=doc.id,
        status_keberlakuan=status_label,
        legal_reference_created=ref_created,
        legal_reference_id=legal_ref.id if legal_ref else None,
        message=message,
    )