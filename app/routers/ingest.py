"""
app/routers/ingest.py
Endpoint untuk menerima upload dokumen PDF, screening deduplikasi,
pemantauan job, dan antrian penanganan kegagalan / retry (Langkah 2 & 3).
"""
from datetime import date
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.enums import (
    JenisJobIngest,
    KlasifikasiAkses,
    PeranDokumen,
    StatusJobIngest,
    StatusKeberlakuan,
    JenisKegagalan,
    StatusTindakLanjut,
)
from app.models.job_ingest import JobIngest
from app.models.ingest_failure import IngestFailure
from app.routers.auth import get_current_user
from app.schemas.ingest import (
    DuplicateCheckResponse,
    IngestStatusResponse,
    IngestUploadResponse,
    JobDetailResponse,
    FailureResponse,
    FailureListResponse,
    FailureStatusUpdateRequest,
    FailureRetryRequest,
    FailureBatchRetryRequest,
    FailureRetryResponse,
    BatchRetryResponse,
    JobFailureSummary,
    JobDocumentSummary,
    DuplicateDocumentInfo,
    JobSourceInfo,
)
from app.services.ingest_service import (
    DocumentMetadataInput,
    IngestItem,
    IngestOptions,
    IngestService,
    ItemOutcome,
)
from app.services.failure_service import (
    FailureService,
    FailureNotRetryableError,
    RetryOverrides,
)
from app.services.naming_service import validate_naming_format, validate_naming_separator
from app.services.storage_service import StorageService, get_storage_service

router = APIRouter()


def _format_failure_response(f: IngestFailure) -> FailureResponse:
    """Helper untuk format IngestFailure model ke FailureResponse schema."""
    dup_doc = None
    if f.duplicate_of_document:
        dup_doc = DuplicateDocumentInfo(
            id=f.duplicate_of_document.id,
            title=f.duplicate_of_document.title,
            regulation_number=f.duplicate_of_document.regulation_number,
        )

    return FailureResponse(
        id=f.id,
        job_id=f.job_id,
        original_filename=f.original_filename,
        source_url=f.source_url,
        failure_type=f.failure_type.value if hasattr(f.failure_type, "value") else str(f.failure_type),
        reason_code=f.reason_code,
        message=f.message,
        is_retryable=f.is_retryable,
        quarantine_path=f.quarantine_path,
        file_hash=f.file_hash,
        file_size_bytes=f.file_size_bytes,
        duplicate_of_document_id=f.duplicate_of_document_id,
        duplicate_of_document=dup_doc,
        ingest_options=f.ingest_options or {},
        follow_up_status=f.follow_up_status.value if hasattr(f.follow_up_status, "value") else str(f.follow_up_status),
        attempt_count=f.attempt_count,
        last_retry_at=f.last_retry_at,
        last_retry_job_id=f.last_retry_job_id,
        resolved_document_id=f.resolved_document_id,
        handled_by_user_id=f.handled_by_user_id,
        handling_note=f.handling_note,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


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
    bidang: Optional[str] = Form(
        None,
        description="Sektor atau bidang regulasi, misal: Perbankan, BMKS (hanya untuk unggahan 1 berkas)",
    ),
    naming_format: Optional[str] = Form(
        None,
        description="Urutan komponen nama berkas dipisah koma (misal: 'nama,jenis,tahun')",
    ),
    naming_separator: Optional[str] = Form(
        None,
        description="Pemisah komponen nama (' ', '_', '-')",
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
    [US-15, US-20c] Endpoint sinkron untuk upload PDF regulasi / draft kajian.
    Mendukung unggahan tunggal dan jamak (multiple files) serta format penamaan dinamis.
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
        bidang and bidang.strip(),
    ])
    if len(files) > 1 and has_single_doc_meta:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Metadata per-dokumen (judul, nomor, tanggal, bidang) hanya boleh diisi untuk unggahan "
                "satu berkas. Untuk unggahan jamak, metadata diisi dari hasil ekstraksi atau koreksi manual."
            ),
        )

    # 2. Validasi naming_format & naming_separator
    parsed_naming_format: Optional[List[str]] = None
    if naming_format is not None and naming_format.strip():
        raw_items = [k.strip() for k in naming_format.split(",") if k.strip()]
        parsed_naming_format = validate_naming_format(raw_items)

    parsed_naming_separator: Optional[str] = None
    if naming_separator is not None:
        parsed_naming_separator = validate_naming_separator(naming_separator)

    # 3. Validasi release_date
    parsed_release_date: Optional[date] = None
    if release_date and release_date.strip():
        try:
            parsed_release_date = date.fromisoformat(release_date.strip())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Format tanggal rilis tidak valid. Gunakan format YYYY-MM-DD.",
            )

    # 4. Parse category_id
    parsed_category_id: Optional[int] = None
    if category_id and str(category_id).strip():
        val = str(category_id).strip()
        if val.isdigit():
            parsed_category_id = int(val)
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="category_id harus berupa bilangan bulat.",
            )

    # 5. Tentukan triggered_by
    if current_user and getattr(current_user, "username", None):
        triggered_by = current_user.username
    elif job_type == JenisJobIngest.unggah_manual:
        triggered_by = "manual_upload"
    else:
        triggered_by = job_type.value

    # 6. Tentukan source_ref
    if len(files) == 1:
        source_ref = files[0].filename or "unggah_tunggal.pdf"
    else:
        source_ref = f"batch_upload_{len(files)}_files"

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

    # 7. Susun metadata input
    meta_input: Optional[DocumentMetadataInput] = None
    if len(files) == 1:
        meta_input = DocumentMetadataInput(
            title=title.strip() if title and title.strip() else None,
            regulation_number=regulation_number.strip() if regulation_number and regulation_number.strip() else None,
            regulation_type=regulation_type.strip() if regulation_type and regulation_type.strip() else None,
            release_date=parsed_release_date,
            bidang=bidang.strip() if bidang and bidang.strip() else None,
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
        naming_format=parsed_naming_format,
        naming_separator=parsed_naming_separator,
    )

    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None

    # 8. Eksekusi batch melalui IngestService
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

    # Simpan ingest_options di job
    batch_res.job.ingest_options = {
        "naming_format": parsed_naming_format,
        "naming_separator": parsed_naming_separator,
        "access_classification": access_classification.value,
        "document_role": document_role.value,
    }
    db.commit()

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
                "placement": r.extra.get("placement"),
            })
        elif r.outcome == ItemOutcome.duplicate:
            details_output.append({
                "filename": r.filename,
                "status": "duplicate",
                "message": r.message,
                "document_id": r.document_id,
                "duplicate_of_document_id": r.duplicate_of_document_id,
                "failure_id": r.extra.get("failure_id"),
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
                "failure_id": r.extra.get("failure_id"),
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
    source_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Mengembalikan riwayat JobIngest dengan pagination dan filter opsional."""
    query = db.query(JobIngest)
    if status:
        query = query.filter(JobIngest.status == status)
    if job_type:
        query = query.filter(JobIngest.job_type == job_type)
    if source_id is not None:
        query = query.filter(JobIngest.source_id == source_id)

    total = query.count()
    jobs = query.order_by(JobIngest.id.desc()).offset(skip).limit(limit).all()

    items = []
    for j in jobs:
        open_fails = (
            db.query(IngestFailure)
            .filter(
                IngestFailure.job_id == j.id,
                IngestFailure.follow_up_status == StatusTindakLanjut.belum_ditangani,
                IngestFailure.failure_type != JenisKegagalan.duplikat,
            )
            .count()
        )
        source_info = None
        if j.source:
            source_info = {
                "id": j.source.id,
                "name": j.source.name,
                "source_type": j.source.source_type.value if hasattr(j.source.source_type, "value") else str(j.source.source_type),
            }
        items.append({
            "id": j.id,
            "job_type": j.job_type.value if hasattr(j.job_type, "value") else str(j.job_type),
            "source_ref": j.source_ref,
            "source_id": j.source_id,
            "source": source_info,
            "triggered_by": j.triggered_by,
            "started_at": j.started_at,
            "finished_at": j.finished_at,
            "status": j.status.value if hasattr(j.status, "value") else str(j.status),
            "success_count": j.success_count,
            "duplicate_count": j.duplicate_count,
            "failed_count": j.failed_count,
            "total_found": j.total_found,
            "processed_count": j.processed_count,
            "skipped_count": j.skipped_count,
            "open_failures_count": open_fails,
        })

    return {
        "total": total,
        "items": items,
    }


@router.get("/jobs/{job_id}", response_model=JobDetailResponse, summary="Detail job ingest")
def get_job_detail(
    job_id: int,
    db: Session = Depends(get_db),
):
    """
    [US-14] Mengembalikan detail lengkap job ingest termasuk daftar dokumen dan kegagalan/duplikat.
    """
    job = db.query(JobIngest).filter(JobIngest.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job ingest dengan ID {job_id} tidak ditemukan.",
        )

    duration = None
    if job.started_at and job.finished_at:
        duration = (job.finished_at - job.started_at).total_seconds()

    doc_summaries = [
        JobDocumentSummary(
            id=d.id,
            title=d.title,
            regulation_number=d.regulation_number,
            file_path_pdf=d.file_path_pdf,
        )
        for d in job.documents
    ]

    failure_summaries = []
    for f in job.failures:
        dup_doc = None
        if f.duplicate_of_document:
            dup_doc = DuplicateDocumentInfo(
                id=f.duplicate_of_document.id,
                title=f.duplicate_of_document.title,
                regulation_number=f.duplicate_of_document.regulation_number,
            )
        failure_summaries.append(
            JobFailureSummary(
                id=f.id,
                original_filename=f.original_filename,
                failure_type=f.failure_type.value if hasattr(f.failure_type, "value") else str(f.failure_type),
                reason_code=f.reason_code,
                message=f.message,
                is_retryable=f.is_retryable,
                quarantine_path=f.quarantine_path,
                attempt_count=f.attempt_count,
                follow_up_status=f.follow_up_status.value if hasattr(f.follow_up_status, "value") else str(f.follow_up_status),
                duplicate_of_document_id=f.duplicate_of_document_id,
                duplicate_of_document=dup_doc,
            )
        )

    source_info = None
    if job.source:
        source_info = JobSourceInfo(
            id=job.source.id,
            name=job.source.name,
            source_type=job.source.source_type.value if hasattr(job.source.source_type, "value") else str(job.source.source_type),
        )

    progress_pct = None
    if job.total_found is not None:
        if job.total_found > 0:
            progress_pct = min(100.0, round((job.processed_count / job.total_found) * 100, 1))
        else:
            progress_pct = 100.0

    return JobDetailResponse(
        id=job.id,
        job_type=job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type),
        source_ref=job.source_ref,
        source_id=job.source_id,
        source=source_info,
        retry_of_failure_id=job.retry_of_failure_id,
        triggered_by=job.triggered_by,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        started_at=job.started_at,
        finished_at=job.finished_at,
        duration_seconds=duration,
        success_count=job.success_count,
        duplicate_count=job.duplicate_count,
        failed_count=job.failed_count,
        total_found=job.total_found,
        processed_count=job.processed_count,
        skipped_count=job.skipped_count,
        progress_percent=progress_pct,
        documents=doc_summaries,
        failures=failure_summaries,
    )


@router.get("/failures", response_model=FailureListResponse, summary="Daftar kegagalan ingest")
def list_failures(
    job_id: Optional[int] = None,
    failure_type: Optional[JenisKegagalan] = None,
    follow_up_status: Optional[str] = Query("belum_ditangani", description="belum_ditangani | diproses_ulang | diabaikan | all"),
    include_duplicates: bool = Query(False, description="Tampilkan juga duplikat (default: false)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
):
    """
    [US-23 / S-04] Mengambil daftar log kegagalan dan antrian retry.
    """
    svc = FailureService(db=db, storage=storage)
    total, items = svc.list_failures(
        job_id=job_id,
        failure_type=failure_type,
        follow_up_status=follow_up_status,
        include_duplicates=include_duplicates,
        skip=skip,
        limit=limit,
    )
    return FailureListResponse(
        total=total,
        items=[_format_failure_response(f) for f in items],
    )


@router.get("/failures/{failure_id}", response_model=FailureResponse, summary="Detail satu kegagalan ingest")
def get_failure_detail(
    failure_id: int,
    db: Session = Depends(get_db),
):
    """Mengambil detail satu baris kegagalan ingest."""
    failure = db.query(IngestFailure).filter(IngestFailure.id == failure_id).first()
    if not failure:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Data kegagalan ID {failure_id} tidak ditemukan.",
        )
    return _format_failure_response(failure)


@router.patch("/failures/{failure_id}", response_model=FailureResponse, summary="Update status kegagalan")
def update_failure_status(
    failure_id: int,
    body: FailureStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user=Depends(get_current_user),
):
    """
    Mengubah status tindak lanjut kegagalan (hanya 'belum_ditangani' atau 'diabaikan').
    """
    svc = FailureService(db=db, storage=storage)
    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None

    stat_enum = StatusTindakLanjut(body.follow_up_status)
    updated = svc.update_status(
        failure_id=failure_id,
        status=stat_enum,
        note=body.handling_note,
        actor_user_id=actor_user_id,
        ip_address=client_ip,
    )
    return _format_failure_response(updated)


@router.post(
    "/failures/{failure_id}/retry",
    response_model=FailureRetryResponse,
    summary="Retry satu kegagalan",
    responses={
        404: {"description": "Data kegagalan tidak ditemukan"},
        409: {"description": "Kegagalan tidak dapat diulang (non-retryable / sudah terselesaikan)"},
    },
)
def retry_failure(
    failure_id: int,
    request: Request,
    body: Optional[FailureRetryRequest] = None,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user=Depends(get_current_user),
):
    """
    Memproses ulang dokumen dari karantina.
    """
    svc = FailureService(db=db, storage=storage)
    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None

    overrides = None
    if body:
        acc_enum = KlasifikasiAkses(body.access_classification) if body.access_classification else None
        role_enum = PeranDokumen(body.document_role) if body.document_role else None
        overrides = RetryOverrides(
            category_id=body.category_id,
            access_classification=acc_enum,
            document_role=role_enum,
        )

    try:
        retry_res = svc.retry(
            failure_id=failure_id,
            overrides=overrides,
            actor_user_id=actor_user_id,
            ip_address=client_ip,
        )
    except FailureNotRetryableError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        )

    job_id_val = retry_res.job.id if retry_res.job else retry_res.failure.job_id
    return FailureRetryResponse(
        failure=_format_failure_response(retry_res.failure),
        outcome=retry_res.item_result.outcome.value,
        document_id=retry_res.item_result.document_id,
        job_id=job_id_val,
        message=retry_res.item_result.message,
    )


@router.post("/failures/retry", response_model=BatchRetryResponse, summary="Batch retry kegagalan")
def batch_retry_failures(
    body: FailureBatchRetryRequest,
    request: Request,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    current_user=Depends(get_current_user),
):
    """
    Memproses ulang beberapa kegagalan sekaligus (satu per satu, kegagalan satu tidak membatalkan yang lain).
    """
    svc = FailureService(db=db, storage=storage)
    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None

    results: List[FailureRetryResponse] = []
    success_count = 0
    duplicate_count = 0
    failed_count = 0
    skipped_count = 0

    for fid in body.failure_ids:
        failure = db.query(IngestFailure).filter(IngestFailure.id == fid).first()
        if not failure or not failure.is_retryable or failure.follow_up_status == StatusTindakLanjut.diproses_ulang:
            skipped_count += 1
            if failure:
                results.append(
                    FailureRetryResponse(
                        failure=_format_failure_response(failure),
                        outcome="skipped",
                        document_id=None,
                        job_id=failure.job_id,
                        message="Item tidak dapat di-retry (non-retryable atau sudah diproses ulang).",
                    )
                )
            continue

        try:
            retry_res = svc.retry(
                failure_id=fid,
                actor_user_id=actor_user_id,
                ip_address=client_ip,
            )
            if retry_res.item_result.outcome == ItemOutcome.success:
                success_count += 1
            elif retry_res.item_result.outcome == ItemOutcome.duplicate:
                duplicate_count += 1
            else:
                failed_count += 1

            results.append(
                FailureRetryResponse(
                    failure=_format_failure_response(retry_res.failure),
                    outcome=retry_res.item_result.outcome.value,
                    document_id=retry_res.item_result.document_id,
                    job_id=retry_res.job.id,
                    message=retry_res.item_result.message,
                )
            )
        except Exception as exc:
            failed_count += 1
            db.refresh(failure)
            results.append(
                FailureRetryResponse(
                    failure=_format_failure_response(failure),
                    outcome="failed",
                    document_id=None,
                    job_id=failure.job_id,
                    message=f"Kesalahan saat retry: {str(exc)}",
                )
            )

    return BatchRetryResponse(
        results=results,
        success_count=success_count,
        duplicate_count=duplicate_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
    )


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
    open_failures = (
        db.query(IngestFailure)
        .filter(
            IngestFailure.follow_up_status == StatusTindakLanjut.belum_ditangani,
            IngestFailure.failure_type != JenisKegagalan.duplikat,
        )
        .count()
    )

    return {
        "total_documents": total_docs,
        "berlaku_documents": berlaku_docs,
        "dicabut_documents": dicabut_docs,
        "total_draft_kajian": draft_docs,
        "total_jobs": total_jobs,
        "open_failures": open_failures,
        "storage_path": settings.storage_path,
    }