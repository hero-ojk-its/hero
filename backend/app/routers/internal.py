"""
Router: /api/v1/internal
Endpoint INTERNAL untuk integrasi pipeline Data/ML (Fathir):
- Claim antrean ekstraksi
- Unduh PDF internal
- Kirim hasil ekstraksi / OCR / chunking pasal
- Requeue dokumen
"""
from datetime import datetime, date, timedelta, timezone
import logging
import re
from typing import Optional, List, Dict, Any
import urllib.parse

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict, AliasChoices
from sqlalchemy import or_, and_, desc, select, delete, func, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.article import Article
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusPemrosesan,
    MetodeEkstraksi,
    JenisKegagalan,
    StatusTindakLanjut,
    JenisJobIngest,
    StatusJobIngest,
)
from app.schemas.article import BulkArticleIn, BulkArticleResponse
from app.schemas.scan import InternalCandidatesBatchIn, InternalScanClaimItem
from app.services.audit_service import (
    record_audit,
    EXTRACTION_RESULT,
    EXTRACTION_FAILED,
    EXTRACTION_REQUEUED,
)
from app.services.storage_service import StorageService, get_storage_service
from app.services.category_service import CategoryService
from app.services.placement_service import PlacementService
from app.services.naming_service import normalize_regulation_type

logger = logging.getLogger("hero")
router = APIRouter()


def verify_internal_api_key(x_internal_api_key: Optional[str] = Header(None, alias="X-Internal-API-Key")) -> None:
    """
    Dependency proteksi API key internal untuk komunikasi service-to-service Data/ML.
    """
    if not x_internal_api_key or x_internal_api_key != settings.internal_api_key:
        raise HTTPException(status_code=401, detail="API key internal tidak valid atau tidak disertakan")


class ExtractionErrorIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    code: str  # e.g. "ekstraksi_gagal" | "ocr_gagal"
    message: str


class ExtractionResultIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    title: Optional[str] = Field(None, validation_alias="judul")
    regulation_number: Optional[str] = Field(None, validation_alias="nomor_peraturan")
    regulation_type: Optional[str] = Field(None, validation_alias="jenis_peraturan")
    release_date: Optional[date] = Field(None, validation_alias="tanggal_terbit")
    bidang: Optional[str] = Field(None, validation_alias=AliasChoices("bidang", "sektor", "sector"))
    extraction_method: Optional[str] = Field(None, validation_alias="metode_ekstraksi")
    extraction_engine: Optional[str] = Field(None, validation_alias="mesin_ekstraksi")
    full_text: Optional[str] = Field(None, validation_alias="teks_lengkap")
    confidence: Optional[Dict[str, float]] = None
    error: Optional[ExtractionErrorIn] = None


@router.post(
    "/articles",
    response_model=BulkArticleResponse,
    summary="[Internal] Bulk insert/upsert chunk pasal dari ML pipeline",
    dependencies=[Depends(verify_internal_api_key)],
)
def bulk_insert_articles(
    payload: BulkArticleIn,
    db: Session = Depends(get_db),
) -> BulkArticleResponse:
    """
    Bulk insert / upsert pasal dari pipeline ML (Data).

    Fitur utama kontrak pasal:
    - **Upsert idempoten**: Menggunakan `INSERT ... ON CONFLICT (document_id, order_index) WHERE order_index IS NOT NULL DO UPDATE`.
      Memperbarui kolom `level`, `chapter_title`, `article_number`, `content_text`, `page`, `parent_id`, dan `embedding` (hanya bila embedding baru tidak null).
    - **replace_document_ids**: Opsi untuk menghapus seluruh pasal milik dokumen yang didaftarkan sebelum melakukan upsert,
      dalam transaksi atomik yang sama. Berguna untuk ekstraksi ulang bersih atau saat pasal baru lebih sedikit dari sebelumnya.
    - **page**: Halaman PDF tempat pasal/ayat dimulai (1-indexed).
    - **parent_order_index**: Menyelesaikan hierarki ayat/pasal ke `parent_id`, baik induk ada pada request sebelumnya
      (sudah tersimpan di DB) maupun berada di dalam batch yang sama. Mengembalikan 422 jika induk tidak ditemukan.
    - **Validasi Dokumen**: Memverifikasi semua `document_id` ada di tabel `documents`. Mengembalikan 422 bila ada ID yang tidak dikenal.
    """
    # 1. Validasi keberadaan seluruh document_id
    doc_ids = {chunk.document_id for chunk in payload.articles}
    if payload.replace_document_ids:
        doc_ids.update(payload.replace_document_ids)

    existing_docs = set(db.scalars(select(Document.id).where(Document.id.in_(doc_ids))).all())
    missing_docs = sorted(list(doc_ids - existing_docs))
    if missing_docs:
        raise HTTPException(
            status_code=422,
            detail=f"document_id tidak ditemukan di tabel documents: {missing_docs}",
        )

    # 2. Validasi parent_order_index awal: periksa apakah menunjuk ke diri sendiri
    for chunk in payload.articles:
        if chunk.order_index is not None and chunk.parent_order_index is not None:
            if chunk.order_index == chunk.parent_order_index:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Pasal induk tidak boleh menunjuk ke order_index diri sendiri: "
                        f"document_id={chunk.document_id}, parent_order_index={chunk.parent_order_index}"
                    ),
                )

    # Periksa ketersediaan parent yang tidak ada di dalam batch
    batch_keys = {(c.document_id, c.order_index) for c in payload.articles if c.order_index is not None}
    needed_db_parents = {
        (c.document_id, c.parent_order_index)
        for c in payload.articles
        if c.parent_order_index is not None and (c.document_id, c.parent_order_index) not in batch_keys
    }

    replace_set = set(payload.replace_document_ids or [])
    # Jika parent yang dibutuhkan berada di dokumen yang akan di-replace dan tidak ada di batch, pasti tidak ada
    for d_id, p_ord in needed_db_parents:
        if d_id in replace_set:
            raise HTTPException(
                status_code=422,
                detail=f"Pasal induk tidak ditemukan untuk document_id={d_id} dan parent_order_index={p_ord}",
            )

    found_db_parents: Dict[tuple, int] = {}
    if needed_db_parents:
        conditions = [
            and_(Article.document_id == d_id, Article.order_index == ord_idx)
            for d_id, ord_idx in needed_db_parents
        ]
        db_parents_rows = db.execute(
            select(Article.document_id, Article.order_index, Article.id).where(or_(*conditions))
        ).all()
        found_db_parents = {(r[0], r[1]): r[2] for r in db_parents_rows}

        for d_id, p_ord in needed_db_parents:
            if (d_id, p_ord) not in found_db_parents:
                raise HTTPException(
                    status_code=422,
                    detail=f"Pasal induk tidak ditemukan untuk document_id={d_id} dan parent_order_index={p_ord}",
                )

    inserted_count = 0
    updated_count = 0
    deleted_count = 0

    try:
        # 3. Hapus pasal untuk replace_document_ids bila ada
        if payload.replace_document_ids:
            del_result = db.execute(
                delete(Article)
                .where(Article.document_id.in_(payload.replace_document_ids))
                .returning(Article.id)
            )
            deleted_count = len(del_result.fetchall())

        # 4. Proses upsert bertahap (topological levels) untuk menyelesaikan parent_order_index
        parent_id_map: Dict[tuple, int] = dict(found_db_parents)
        remaining_chunks = list(payload.articles)

        while remaining_chunks:
            # Cari chunk yang siap (tidak punya parent, atau parent-nya sudah ada di parent_id_map)
            ready = [
                c for c in remaining_chunks
                if c.parent_order_index is None or (c.document_id, c.parent_order_index) in parent_id_map
            ]

            if not ready:
                # Terdapat siklus relasi atau induk tidak ditemukan di sisa batch
                first_unresolved = remaining_chunks[0]
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Pasal induk tidak ditemukan atau terdapat siklus relasi untuk "
                        f"document_id={first_unresolved.document_id} dan parent_order_index={first_unresolved.parent_order_index}"
                    ),
                )

            # Pastikan tidak ada duplikat (document_id, order_index) dalam satu statement SQL
            batch_for_stmt = []
            next_remaining = []
            seen_in_batch = set()

            for c in ready:
                key = (c.document_id, c.order_index) if c.order_index is not None else None
                if key is not None and key in seen_in_batch:
                    next_remaining.append(c)
                else:
                    if key is not None:
                        seen_in_batch.add(key)
                    batch_for_stmt.append(c)

            not_ready = [c for c in remaining_chunks if c not in ready]
            remaining_chunks = next_remaining + not_ready

            values_to_insert = []
            for c in batch_for_stmt:
                pid = parent_id_map.get((c.document_id, c.parent_order_index)) if c.parent_order_index is not None else None
                values_to_insert.append({
                    "document_id": c.document_id,
                    "level": c.level,
                    "chapter_title": c.chapter_title,
                    "article_number": c.article_number,
                    "content_text": c.content_text,
                    "order_index": c.order_index,
                    "page": c.page,
                    "parent_id": pid,
                    "embedding": c.embedding,
                })

            stmt = pg_insert(Article).values(values_to_insert)
            stmt = stmt.on_conflict_do_update(
                index_elements=["document_id", "order_index"],
                index_where=Article.order_index.isnot(None),
                set_={
                    "level": stmt.excluded.level,
                    "chapter_title": stmt.excluded.chapter_title,
                    "article_number": stmt.excluded.article_number,
                    "content_text": stmt.excluded.content_text,
                    "page": stmt.excluded.page,
                    "parent_id": stmt.excluded.parent_id,
                    "embedding": func.coalesce(stmt.excluded.embedding, Article.embedding),
                },
            )
            stmt = stmt.returning(
                Article.id,
                Article.document_id,
                Article.order_index,
                literal_column("xmax = 0").label("is_insert"),
            )
            res = db.execute(stmt)
            rows = res.fetchall()
            for art_id, d_id, ord_idx, is_ins in rows:
                if ord_idx is not None:
                    parent_id_map[(d_id, ord_idx)] = art_id
                if is_ins:
                    inserted_count += 1
                else:
                    updated_count += 1

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Gagal menyimpan pasal ke database: {str(exc)}",
        )

    return BulkArticleResponse(
        status="ok",
        inserted_count=inserted_count,
        updated_count=updated_count,
        deleted_count=deleted_count,
        message=f"Berhasil memproses {inserted_count + updated_count} pasal: {inserted_count} baru, {updated_count} diperbarui, {deleted_count} dihapus.",
    )


@router.post(
    "/extraction/claim",
    summary="[Internal] Klaim antrean dokumen untuk diekstraksi oleh Data/ML",
    dependencies=[Depends(verify_internal_api_key)],
)
def claim_extraction_batch(
    limit: int = Query(10, ge=1, le=50, description="Jumlah dokumen yang ingin diklaim"),
    db: Session = Depends(get_db),
):
    """
    Mengambil dan mengunci dokumen dalam antrean ekstraksi (SELECT FOR UPDATE SKIP LOCKED).
    Mencakup status 'diterima' dan status 'diproses' yang telah kedaluwarsa (claim timeout).
    """
    timeout_minutes = settings.extraction_claim_timeout_minutes
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

    # Dokumen yang memenuhi syarat klaim
    claimable_cond = and_(
        Document.extraction_attempts < settings.extraction_max_attempts,
        or_(
            Document.processing_status == StatusPemrosesan.diterima,
            and_(
                Document.processing_status == StatusPemrosesan.diproses,
                Document.extraction_claimed_at.isnot(None),
                Document.extraction_claimed_at < cutoff_time,
            ),
        ),
    )

    docs = (
        db.query(Document)
        .filter(claimable_cond)
        .order_by(Document.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )

    claimed_items = []
    now_utc = datetime.now(timezone.utc)

    for doc in docs:
        doc.processing_status = StatusPemrosesan.diproses
        doc.extraction_claimed_at = now_utc
        doc.extraction_attempts += 1

        claimed_items.append({
            "document_id": doc.id,
            "pdf_url": f"/api/v1/internal/documents/{doc.id}/pdf",
            "original_filename": doc.standardized_filename or doc.title or "dokumen.pdf",
            "file_hash": doc.file_hash,
            "file_size_bytes": doc.file_size_bytes,
            "document_role": doc.document_role,
            "access_classification": doc.access_classification,
            "attempt": doc.extraction_attempts,
        })

    db.commit()
    return claimed_items


@router.get(
    "/documents/{document_id}/pdf",
    summary="[Internal] Unduh berkas PDF untuk ekstraksi",
    dependencies=[Depends(verify_internal_api_key)],
)
def get_internal_document_pdf(
    document_id: int,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
):
    """
    Mengembalikan berkas PDF asli untuk kebutuhan worker ekstraksi Data/ML tanpa audit per unduhan.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Dokumen ID {document_id} tidak ditemukan.")

    if not doc.file_path_pdf or not storage.exists(doc.file_path_pdf):
        logger.error("[Internal] Berkas PDF asli tidak ditemukan di disk untuk dokumen ID %s", doc.id)
        raise HTTPException(status_code=404, detail="Berkas PDF asli tidak ditemukan di penyimpanan.")

    abs_path = storage.absolute_path(doc.file_path_pdf)
    fname = doc.standardized_filename or (f"{doc.title}.pdf" if doc.title else "dokumen.pdf")
    if not fname.lower().endswith(".pdf"):
        fname = f"{fname}.pdf"

    encoded_fname = urllib.parse.quote(fname, safe="")
    ascii_fname = re.sub(r'[^\x20-\x7E]|["\\]', "_", fname)
    content_disp = f'inline; filename="{ascii_fname}"; filename*=UTF-8\'\'{encoded_fname}'

    return FileResponse(
        path=abs_path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disp,
            "Cache-Control": "private, max-age=300",
        },
    )


@router.patch(
    "/documents/{document_id}/extraction",
    summary="[Internal] Kirim hasil ekstraksi metadata dan teks dari Data/ML",
    dependencies=[Depends(verify_internal_api_key)],
)
def patch_extraction_result(
    document_id: int,
    payload: ExtractionResultIn,
    force: bool = Query(False, description="Paksa update meskipun status dokumen bukan 'diproses'"),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
):
    """
    Menerima hasil ekstraksi Data/ML (US-20, US-20a, US-26).
    Mendukung penanganan error ekstraksi, proteksi koreksi manual, dan penempatan otomatis.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Dokumen ID {document_id} tidak ditemukan.")

    if doc.processing_status != StatusPemrosesan.diproses and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Dokumen berstatus '{doc.processing_status.value}', bukan 'diproses'. Gunakan force=true untuk menimpa.",
        )

    # 1. Penanganan jika payload memuat error
    if payload.error is not None:
        err_code = payload.error.code.strip()
        err_msg = payload.error.message.strip()

        doc.processing_status = StatusPemrosesan.gagal

        # Tentukan failure_type enum
        fail_type = JenisKegagalan.ekstraksi_gagal
        if err_code == "ocr_gagal":
            fail_type = JenisKegagalan.ocr_gagal
        elif err_code in JenisKegagalan.__members__:
            fail_type = JenisKegagalan[err_code]

        job_id = doc.job_id
        if not job_id:
            default_job = db.query(JobIngest).filter(JobIngest.source_ref == "system:extraction").first()
            if not default_job:
                default_job = JobIngest(
                    job_type=JenisJobIngest.unggah_manual,
                    triggered_by="system",
                    source_ref="system:extraction",
                    status=StatusJobIngest.selesai,
                )
                db.add(default_job)
                db.flush()
            job_id = default_job.id

        failure = IngestFailure(
            job_id=job_id,
            original_filename=doc.standardized_filename or doc.title or "dokumen.pdf",
            source_url=doc.source_url,
            failure_type=fail_type,
            reason_code=err_code,
            message=err_msg,
            is_retryable=True,
            quarantine_path=None,
            file_hash=doc.file_hash,
            file_size_bytes=doc.file_size_bytes,
            document_id=doc.id,
            ingest_options={},
            follow_up_status=StatusTindakLanjut.belum_ditangani,
        )
        db.add(failure)
        db.flush()

        record_audit(
            db,
            action=EXTRACTION_FAILED,
            target_resource=f"document:{doc.id}",
            detail={"document_id": doc.id, "error": {"code": err_code, "message": err_msg}, "failure_id": failure.id},
            commit=False,
        )

        db.commit()
        return {
            "status": "gagal_dicatat",
            "failure_id": failure.id,
        }

    # 2. Penanganan Sukses
    ignored_fields = []
    changed_fields = []

    if payload.full_text is not None:
        if doc.full_text != payload.full_text:
            doc.full_text = payload.full_text
            changed_fields.append("full_text")

    if payload.extraction_engine:
        doc.extraction_engine = payload.extraction_engine.strip()

    if payload.extraction_method:
        meth_clean = payload.extraction_method.strip()
        if meth_clean in (MetodeEkstraksi.teks_langsung.value, "teks_langsung"):
            doc.extraction_method = MetodeEkstraksi.teks_langsung
        elif meth_clean in (MetodeEkstraksi.ocr.value, "ocr"):
            doc.extraction_method = MetodeEkstraksi.ocr
        else:
            if not doc.extraction_engine:
                doc.extraction_engine = meth_clean
            if "ocr" in meth_clean.lower():
                doc.extraction_method = MetodeEkstraksi.ocr
            else:
                doc.extraction_method = MetodeEkstraksi.teks_langsung

    doc.extraction_confidence = payload.confidence
    doc.extracted_at = datetime.now(timezone.utc)

    # Aturan Metadata: jangan menimpa bila sudah dikoreksi manual
    if doc.metadata_corrected_at is not None:
        for fname in ["title", "regulation_number", "regulation_type", "release_date", "bidang"]:
            if getattr(payload, fname) is not None:
                ignored_fields.append(fname)
    else:
        if payload.title and payload.title.strip():
            clean_title = payload.title.strip()
            if doc.title != clean_title:
                doc.title = clean_title
                changed_fields.append("title")

        if payload.regulation_number and payload.regulation_number.strip():
            clean_num = payload.regulation_number.strip()
            if doc.regulation_number != clean_num:
                doc.regulation_number = clean_num
                changed_fields.append("regulation_number")

        if payload.regulation_type and payload.regulation_type.strip():
            norm_type = normalize_regulation_type(payload.regulation_type)
            if doc.regulation_type != norm_type:
                doc.regulation_type = norm_type
                changed_fields.append("regulation_type")

        if payload.release_date is not None:
            if doc.release_date != payload.release_date:
                doc.release_date = payload.release_date
                changed_fields.append("release_date")

        if payload.bidang and payload.bidang.strip():
            clean_bidang = payload.bidang.strip()
            if doc.bidang != clean_bidang:
                doc.bidang = clean_bidang
                changed_fields.append("bidang")

    # Hitung low confidence fields
    low_confidence_fields = []
    metadata_has_low_conf = False

    if payload.confidence and isinstance(payload.confidence, dict):
        for k, v in payload.confidence.items():
            if isinstance(v, (int, float)) and v < settings.metadata_confidence_threshold:
                low_confidence_fields.append(k)
                if k in ("title", "regulation_number", "regulation_type", "release_date"):
                    metadata_has_low_conf = True

    # Evaluasi status akhir
    has_empty_reg = not doc.regulation_number or not doc.regulation_number.strip()
    has_empty_title = not doc.title or not doc.title.strip()

    if has_empty_reg or has_empty_title or metadata_has_low_conf:
        doc.processing_status = StatusPemrosesan.perlu_koreksi
    else:
        doc.processing_status = StatusPemrosesan.terindeks

    # Penamaan & Penempatan Otomatis
    is_placed_already = bool(doc.file_path_pdf and doc.file_path_pdf.replace("\\", "/").startswith("kb/"))
    force_place = bool(changed_fields and is_placed_already)

    cat_svc = CategoryService(db)
    place_svc = PlacementService(db, storage, cat_svc, settings)
    place_res = place_svc.place(doc, force=force_place)

    placement_info = {
        "document_id": place_res.document_id,
        "placed": place_res.placed,
        "reason": place_res.reason,
        "old_path": place_res.old_path,
        "new_path": place_res.new_path,
        "category_id": place_res.category_id,
        "category_path": place_res.category_path,
    }

    record_audit(
        db,
        action=EXTRACTION_RESULT,
        target_resource=f"document:{doc.id}",
        detail={
            "document_id": doc.id,
            "status": doc.processing_status.value,
            "changed_fields": changed_fields,
            "ignored_fields": ignored_fields,
            "low_confidence_fields": low_confidence_fields,
        },
        commit=False,
    )

    db.commit()
    db.refresh(doc)

    return {
        "status": doc.processing_status.value,
        "changed_fields": changed_fields,
        "ignored_fields": ignored_fields,
        "low_confidence_fields": low_confidence_fields,
        "placement": placement_info,
    }


@router.post(
    "/extraction/requeue/{document_id}",
    summary="[Internal] Mengembalikan dokumen ke antrean ekstraksi",
    dependencies=[Depends(verify_internal_api_key)],
)
def requeue_document_extraction(
    document_id: int,
    db: Session = Depends(get_db),
):
    """
    Mengembalikan dokumen ke status 'diterima' dan mereset claimed_at (tidak mereset attempt count).
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Dokumen ID {document_id} tidak ditemukan.")

    doc.processing_status = StatusPemrosesan.diterima
    doc.extraction_claimed_at = None

    record_audit(
        db,
        action=EXTRACTION_REQUEUED,
        target_resource=f"document:{doc.id}",
        detail={"document_id": doc.id, "attempt": doc.extraction_attempts},
        commit=False,
    )

    db.commit()
    return {
        "status": "requeued",
        "document_id": doc.id,
    }


# ==================== PUSH MODE SCAN ENDPOINTS (Langkah 7) ====================


@router.post(
    "/scans/claim",
    summary="[Internal Data/ML] Mengklaim antrean sesi pemindaian mode push",
    dependencies=[Depends(verify_internal_api_key)],
)
def claim_push_scans_endpoint(
    limit: int = Query(1, ge=1, le=5, description="Jumlah sesi yang ingin diklaim (1-5)"),
    db: Session = Depends(get_db),
):
    """
    [Langkah 7 - Opsi B Data/ML] Mengambil sesi pemindaian antrean dengan mode='push'.
    """
    from app.services.scan_service import ScanService
    from app.schemas.scan import InternalScanClaimItem

    svc = ScanService(db)
    sessions = svc.claim_push_scans(limit=limit)

    return [
        InternalScanClaimItem(
            scan_id=s.id,
            start_url=s.start_url,
            crawl_depth=s.crawl_depth,
            max_pages=settings.crawl_max_pages,
            max_candidates=settings.crawl_max_candidates,
        )
        for s in sessions
    ]


@router.post(
    "/scans/{scan_id}/candidates",
    summary="[Internal Data/ML] Mengirim batch kandidat PDF hasil pemindaian",
    dependencies=[Depends(verify_internal_api_key)],
)
def push_scan_candidates_endpoint(
    scan_id: int,
    payload: "InternalCandidatesBatchIn",
    db: Session = Depends(get_db),
):
    """
    [Langkah 7 - Opsi B Data/ML] Menerima kandidat PDF yang ditemukan oleh crawler eksternal.
    Saat done=true, sistem otomatis menjalankan perbandingan dengan basis pengetahuan.
    """
    from app.services.scan_service import ScanService
    svc = ScanService(db)
    session = svc.push_candidates(scan_id, payload)
    return {
        "scan_id": session.id,
        "status": session.status.value,
        "pages_visited": session.pages_visited,
        "candidates_total": session.candidates_total,
        "candidates_new": session.candidates_new,
        "candidates_existing": session.candidates_existing,
        "candidates_uncertain": session.candidates_uncertain,
        "done": payload.done,
    }
