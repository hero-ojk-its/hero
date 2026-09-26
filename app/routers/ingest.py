"""
app/routers/ingest.py
Endpoint untuk menerima upload dokumen PDF, screening deduplikasi,
dan memantau riwayat serta status pipeline ingest.
"""
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.enums import (
    JenisJobIngest,
    KlasifikasiAkses,
    PeranDokumen,
    StatusJobIngest,
    StatusKeberlakuan,
)
from app.models.job_ingest import JobIngest
from app.routers.auth import get_current_user
from app.schemas.ingest import (
    DuplicateCheckResponse,
    IngestStatusResponse,
    IngestUploadResponse,
)
from app.services.ingest_service import (
    DocumentMetadataInput,
    IngestItem,
    IngestOptions,
    IngestService,
    ItemOutcome,
)
from app.services.storage_service import StorageService, get_storage_service

router = APIRouter()


@router.post(
    "/upload-pdf",
    response_model=IngestUploadResponse,
    summary="Upload PDF regulasi baru (mendukung berkas tunggal maupun jamak)",
)
def upload_pdf(
    request: Request,
    files: List[UploadFile] = File(
        ...,
        description="Daftar file PDF regulasi yang diunggah (bisa jamak / multiple files)",
    ),
    access_classification: KlasifikasiAkses = Form(
        ...,
        description="Klasifikasi akses (publik / non_publik) - WAJIB untuk kepatuhan NDA",
    ),
    document_role: PeranDokumen = Form(
        ...,
        description="Peran dokumen: corpus_eksisting | draft_kajian (WAJIB dinyatakan)",
    ),
    title: Optional[str] = Form(
        None,
        description="Judul dokumen (hanya untuk unggahan 1 berkas)",
    ),
    regulation_number: Optional[str] = Form(
        None,
        description="Nomor regulasi unik, misal: PP-24-2005 (hanya untuk unggahan 1 berkas)",
    ),
    regulation_type: Optional[str] = Form(
        None,
        description="Jenis regulasi, misal: UU, PP, Permen (opsional)",
    ),
    job_type: JenisJobIngest = Form(
        JenisJobIngest.unggah_manual,
        description="Jenis job ingest: scraping | unggah_manual | sinkron_folder",
    ),
    category_id: Optional[str] = Form(
        None,
        description="ID kategori KB terkait (opsional)",
    ),
    release_date: Optional[str] = Form(
        None,
        description="Tanggal terbit format YYYY-MM-DD (hanya untuk unggahan 1 berkas)",
    ),
    source_url: Optional[str] = Form(
        None,
        description="URL asal dokumen (opsional)",
    ),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user=Depends(get_current_user),
):
    """
    [US-15] Endpoint sinkron untuk upload PDF regulasi / draft kajian.
    Mendukung unggahan tunggal dan jamak (multiple files).
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tidak ada file yang diunggah.",
        )

    # 1. Validasi metadata per-berkas untuk unggahan jamak
    has_single_doc_meta = any([
        title and title.strip(),
        regulation_number and regulation_number.strip(),
        release_date and release_date.strip(),
    ])
    if len(files) > 1 and has_single_doc_meta:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Metadata per-dokumen (judul, nomor, tanggal) hanya boleh diisi untuk unggahan "
                "satu berkas. Untuk unggahan jamak, metadata diisi dari hasil ekstraksi atau koreksi manual."
            ),
        )

    # 2. Validasi release_date
    parsed_release_date: Optional[date] = None
    if release_date and release_date.strip():
        try:
            parsed_release_date = date.fromisoformat(release_date.strip())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Format tanggal rilis tidak valid. Gunakan format YYYY-MM-DD.",
            )

    # 3. Parse category_id
    parsed_category_id: Optional[int] = None
    if category_id and str(category_id).strip():
        val = str(category_id).strip()
        if val.isdigit():
            parsed_category_id = int(val)
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="category_id harus berupa bilangan bulat.",
            )

    # 4. Tentukan triggered_by
    if current_user and getattr(current_user, "username", None):
        triggered_by = current_user.username
    elif job_type == JenisJobIngest.unggah_manual:
        triggered_by = "manual_upload"
    else:
        triggered_by = job_type.value

    # 5. Susun referensi sumber & baca konten berkas secara sinkron
    filenames = [f.filename for f in files if f and f.filename]
    source_ref = ", ".join(filenames)[:250] if filenames else "unggah_manual.pdf"

    ingest_items: List[IngestItem] = []
    for f in files:
        fname = f.filename or "dokumen.pdf"
        content = f.file.read()
        ingest_items.append(
            IngestItem(
                filename=fname,
                content=content,
                source_url=source_url.strip() if source_url and source_url.strip() else None,
            )
        )

    # 6. Susun metadata input
    meta_input: Optional[DocumentMetadataInput] = None
    if len(files) == 1:
        meta_input = DocumentMetadataInput(
            title=title.strip() if title and title.strip() else None,
            regulation_number=regulation_number.strip() if regulation_number and regulation_number.strip() else None,
            regulation_type=regulation_type.strip() if regulation_type and regulation_type.strip() else None,
            release_date=parsed_release_date,
        )
    elif regulation_type and regulation_type.strip():
        meta_input = DocumentMetadataInput(
            regulation_type=regulation_type.strip(),
        )

    options = IngestOptions(
        access_classification=access_classification,
        document_role=document_role,
        category_id=parsed_category_id,
        metadata=meta_input,
    )

    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None

    # 7. Eksekusi batch melalui IngestService
    service = IngestService(db=db, storage=storage, max_upload_bytes=settings.max_upload_bytes)
    batch_res = service.ingest_batch(
        items=ingest_items,
        options=options,
        job_type=job_type,
        source_ref=source_ref,
        triggered_by=triggered_by,
        actor_user_id=actor_user_id,
        ip_address=client_ip,
    )

    # 8. Susun detail respons JSON
    details_output = []
    for r in batch_res.results:
        if r.outcome == ItemOutcome.success:
            details_output.append({
                "filename": r.filename,
                "status": "success",
                "document_id": r.document_id,
                "title": r.extra.get("title"),
                "regulation_number": r.extra.get("regulation_number"),
                "file_size_bytes": r.file_size_bytes,
                "file_hash": r.file_hash,
                "reason_code": None,
            })
        elif r.outcome == ItemOutcome.duplicate:
            details_output.append({
                "filename": r.filename,
                "status": "duplicate",
                "message": r.message,
                "document_id": r.document_id,
                "duplicate_of_document_id": r.duplicate_of_document_id,
                "regulation_number": r.extra.get("regulation_number"),
                "file_hash": r.file_hash,
                "file_size_bytes": r.file_size_bytes,
                "reason_code": r.reason_code or "duplikat",
            })
        else:
            details_output.append({
                "filename": r.filename,
                "status": "failed",
                "error": r.message,
                "reason_code": r.reason_code,
            })

    return {
        "message": (
            f"Proses unggah selesai: {batch_res.success_count} berhasil, "
            f"{batch_res.duplicate_count} duplikat, {batch_res.failed_count} gagal "
            f"dari total {len(files)} file."
        ),
        "job_id": batch_res.job.id,
        "job_status": batch_res.job.status.value,
        "total_files": len(files),
        "success_count": batch_res.success_count,
        "duplicate_count": batch_res.duplicate_count,
        "failed_count": batch_res.failed_count,
        "details": details_output,
    }


@router.get("/jobs", summary="Riwayat job ingest")
def list_jobs(
    skip: int = 0,
    limit: int = 20,
    status: Optional[StatusJobIngest] = None,
    job_type: Optional[JenisJobIngest] = None,
    db: Session = Depends(get_db),
):
    """Mengembalikan riwayat JobIngest dengan pagination dan filter opsional."""
    query = db.query(JobIngest)
    if status:
        query = query.filter(JobIngest.status == status)
    if job_type:
        query = query.filter(JobIngest.job_type == job_type)

    total = query.count()
    jobs = query.order_by(JobIngest.id.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "items": [
            {
                "id": j.id,
                "job_type": j.job_type,
                "source_ref": j.source_ref,
                "triggered_by": j.triggered_by,
                "started_at": j.started_at,
                "finished_at": j.finished_at,
                "status": j.status,
                "success_count": j.success_count,
                "duplicate_count": j.duplicate_count,
                "failed_count": j.failed_count,
            }
            for j in jobs
        ],
    }


@router.get(
    "/check-duplicate",
    response_model=DuplicateCheckResponse,
    summary="Screening dedup sebelum upload (hemat bandwidth scraper)",
)
def check_duplicate(
    file_hash: Optional[str] = None,
    file_size: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Endpoint ringan untuk pengecekan duplikasi sebelum upload penuh.
    """
    if not file_hash and file_size is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Minimal satu parameter harus diisi: 'file_hash' atau 'file_size'.",
        )

    if file_hash and file_size is not None:
        existing = (
            db.query(Document)
            .filter(
                Document.file_hash == file_hash,
                Document.file_size_bytes == file_size,
            )
            .first()
        )
        if existing:
            return {
                "is_duplicate": True,
                "message": (
                    f"Dokumen duplikat terdeteksi (Hash dan ukuran {existing.file_size_bytes} bytes cocok persis). "
                    f"ID: {existing.id}, "
                    f"Nomor regulasi: {existing.regulation_number or 'tidak tersedia'}, "
                    f"Judul: {existing.title}."
                ),
                "existing_document_id": existing.id,
                "regulation_number": existing.regulation_number,
            }
        return {
            "is_duplicate": False,
            "message": "Dokumen dengan hash dan ukuran file tersebut tidak ditemukan di database. Aman untuk diupload.",
            "existing_document_id": None,
            "regulation_number": None,
        }

    if file_hash:
        existing = db.query(Document).filter(Document.file_hash == file_hash).first()
        if existing:
            return {
                "is_duplicate": True,
                "message": (
                    f"Dokumen sudah ada di database (berdasarkan hash). "
                    f"ID: {existing.id}, "
                    f"Nomor regulasi: {existing.regulation_number or 'tidak tersedia'}, "
                    f"Judul: {existing.title}."
                ),
                "existing_document_id": existing.id,
                "regulation_number": existing.regulation_number,
            }
        return {
            "is_duplicate": False,
            "message": "Hash tidak ditemukan di database. Dokumen aman untuk diupload.",
            "existing_document_id": None,
            "regulation_number": None,
        }

    return {
        "is_duplicate": False,
        "message": (
            "Pengecekan berdasarkan ukuran file saja tidak cukup akurat untuk memastikan duplikasi. "
            "Sertakan 'file_hash' (SHA-256) untuk hasil yang tepat."
        ),
        "existing_document_id": None,
        "regulation_number": None,
    }


@router.get(
    "/status",
    response_model=IngestStatusResponse,
    summary="Status ingest pipeline",
)
def ingest_status(db: Session = Depends(get_db)):
    """Cek ringkasan dokumen dan job di pipeline ingest."""
    total_docs = db.query(Document).count()
    berlaku_docs = db.query(Document).filter(Document.status_keberlakuan == StatusKeberlakuan.berlaku).count()
    dicabut_docs = db.query(Document).filter(Document.status_keberlakuan == StatusKeberlakuan.dicabut).count()
    draft_docs = db.query(Document).filter(Document.document_role == PeranDokumen.draft_kajian).count()
    total_jobs = db.query(JobIngest).count()

    return {
        "total_documents": total_docs,
        "berlaku_documents": berlaku_docs,
        "dicabut_documents": dicabut_docs,
        "total_draft_kajian": draft_docs,
        "total_jobs": total_jobs,
        "storage_path": settings.storage_path,
    }