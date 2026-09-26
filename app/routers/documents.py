"""
Router: /api/v1/documents
Endpoint untuk membaca daftar dokumen regulasi, detail pasal-pasal,
serta penempatan folder KB (Langkah 3).
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.category import Category
from app.models.article import Article, LegalReference
from app.models.enums import KlasifikasiAkses, PeranDokumen, StatusKeberlakuan, JenisRujukan
from app.schemas.article import UpdateDocumentStatusIn, UpdateDocumentStatusResponse
from app.routers.auth import get_current_user
from app.services.audit_service import record_audit, UPDATE_DOCUMENT_STATUS
from app.services.storage_service import StorageService, get_storage_service
from app.services.category_service import CategoryService
from app.services.placement_service import PlacementService

router = APIRouter()


@router.get("/", summary="Daftar semua dokumen regulasi")
def list_documents(
    skip: int = 0,
    limit: int = 20,
    access_classification: Optional[KlasifikasiAkses] = Query(
        None, description="Filter berdasarkan klasifikasi akses (publik / non_publik)"
    ),
    document_role: Optional[PeranDokumen] = Query(
        None, description="Filter berdasarkan peran dokumen (corpus_eksisting / draft_kajian)"
    ),
    category_id: Optional[int] = Query(
        None, description="Filter berdasarkan ID kategori folder KB"
    ),
    status_keberlakuan: Optional[StatusKeberlakuan] = Query(
        None, description="Filter berdasarkan status keberlakuan regulasi"
    ),
    db: Session = Depends(get_db)
):
    """Mengembalikan daftar dokumen regulasi dengan pagination dan filter opsional."""
    query = db.query(Document)

    if access_classification:
        query = query.filter(Document.access_classification == access_classification)
    if document_role:
        query = query.filter(Document.document_role == document_role)
    if category_id:
        query = query.filter(Document.category_id == category_id)
    if status_keberlakuan:
        query = query.filter(Document.status_keberlakuan == status_keberlakuan)

    total = query.count()
    docs = query.order_by(Document.id.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "items": [
            {
                "id": d.id,
                "title": d.title,
                "regulation_number": d.regulation_number,
                "regulation_type": getattr(d, "regulation_type", None),
                "release_date": d.release_date,
                "access_classification": d.access_classification,
                "document_role": d.document_role,
                "category_id": d.category_id,
                "status_keberlakuan": d.status_keberlakuan,
                "processing_status": d.processing_status,
                "created_at": d.created_at,
            }
            for d in docs
        ]
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


@router.get("/{document_id}", summary="Detail satu dokumen beserta pasalnya")
def get_document(document_id: int, db: Session = Depends(get_db)):
    """Mengembalikan detail lengkap dokumen beserta pasal level teratas, rujukan hukum, dan status penempatan KB."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")

    top_articles = (
        db.query(Article)
        .filter(Article.document_id == document_id, Article.parent_id == None)  # noqa: E711
        .order_by(Article.order_index)
        .all()
    )

    legal_refs = (
        db.query(LegalReference)
        .filter(LegalReference.document_id == document_id)
        .all()
    )

    cat_path = None
    if doc.category_id:
        cat = db.query(Category).filter(Category.id == doc.category_id).first()
        if cat:
            cat_svc = CategoryService(db)
            cat_path = cat_svc.path_of(cat)

    is_placed = bool(doc.file_path_pdf and doc.file_path_pdf.replace("\\", "/").startswith("kb/"))

    return {
        "id": doc.id,
        "title": doc.title,
        "regulation_number": doc.regulation_number,
        "regulation_type": getattr(doc, "regulation_type", None),
        "release_date": doc.release_date,
        "source_url": doc.source_url,
        "file_path_pdf": doc.file_path_pdf,
        "standardized_filename": doc.standardized_filename,
        "access_classification": doc.access_classification,
        "document_role": doc.document_role,
        "status_keberlakuan": doc.status_keberlakuan,
        "processing_status": doc.processing_status,
        "extraction_method": getattr(doc, "extraction_method", None),
        "category_id": doc.category_id,
        "category_path": cat_path,
        "is_placed": is_placed,
        "job_id": doc.job_id,
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