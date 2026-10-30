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
from typing import Optional, List, Dict, Any, Union
import urllib.parse

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict, AliasChoices, field_validator
from sqlalchemy import or_, and_, select, delete, func, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.article import Article
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.models.analysis_result import AnalysisResult
from app.models.enums import (
    StatusPemrosesan,
    MetodeEkstraksi,
    JenisKegagalan,
    StatusTindakLanjut,
    JenisJobIngest,
    StatusJobIngest,
    JenisAnalisa,
)
from app.schemas.article import BulkArticleIn, BulkArticleResponse
from app.schemas.scan import InternalCandidatesBatchIn
from app.services.audit_service import (
    record_audit,
    EXTRACTION_RESULT,
    EXTRACTION_FAILED,
    EXTRACTION_REQUEUED,
    PLACE_DOCUMENT_FAILED,
    ANALYSIS_CACHE_INVALIDATED,
    STATUS_RECOMPUTED,
)
from app.services.storage_service import StorageService, get_storage_service
from app.services.category_service import CategoryService
from app.services.placement_service import PlacementService
from app.services.naming_service import normalize_regulation_type, split_redundant_year
from app.services.identity_service import fallback_identity_key
from app.services.duplicate_service import check_identity_duplicate
from app.services.version_service import recompute_status, sync_relations
from app.services.attachment_service import detect_attachment_heuristic, link_attachment, link_pending_children

logger = logging.getLogger("hero")
router = APIRouter()

_DOC_TITLE_MAX_LEN = Document.title.type.length or 255
_DOC_REG_NUM_MAX_LEN = Document.regulation_number.type.length or 100
_DOC_REG_TYPE_MAX_LEN = Document.regulation_type.type.length or 100
_DOC_BIDANG_MAX_LEN = Document.bidang.type.length or 150
_DOC_ENGINE_MAX_LEN = Document.extraction_engine.type.length or 100
_DOC_METHOD_MAX_LEN = Document.extraction_method.type.length or 13


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
    title: Optional[str] = Field(None, max_length=_DOC_TITLE_MAX_LEN, validation_alias="judul")
    regulation_number: Optional[str] = Field(None, max_length=_DOC_REG_NUM_MAX_LEN, validation_alias="nomor_peraturan")
    regulation_type: Optional[str] = Field(None, max_length=_DOC_REG_TYPE_MAX_LEN, validation_alias="jenis_peraturan")
    release_date: Optional[date] = Field(None, validation_alias="tanggal_terbit")
    regulation_year: Optional[int] = Field(None, validation_alias=AliasChoices("regulation_year", "tahun_peraturan", "tahun"))
    bidang: Optional[str] = Field(None, max_length=_DOC_BIDANG_MAX_LEN, validation_alias=AliasChoices("bidang", "sektor", "sector"))
    extraction_method: Optional[str] = Field(None, max_length=_DOC_METHOD_MAX_LEN, validation_alias="metode_ekstraksi")
    extraction_engine: Optional[str] = Field(None, max_length=_DOC_ENGINE_MAX_LEN, validation_alias="mesin_ekstraksi")
    full_text: Optional[str] = Field(None, validation_alias="teks_lengkap")
    confidence: Optional[Dict[str, float]] = None
    identity_key: Optional[str] = Field(None, max_length=120, validation_alias=AliasChoices("identity_key", "kunci_identitas"))
    page_count: Optional[int] = Field(None, ge=1, validation_alias=AliasChoices("page_count", "jumlah_halaman"))
    effective_date: Optional[date] = Field(None, validation_alias=AliasChoices("effective_date", "tanggal_berlaku", "mulai_berlaku"))
    lampiran_dari: Optional[str] = Field(None, max_length=120, validation_alias=AliasChoices("lampiran_dari", "parent_identity_key"))
    label_lampiran: Optional[str] = Field(None, max_length=100, validation_alias=AliasChoices("label_lampiran", "attachment_label"))
    error: Optional[ExtractionErrorIn] = None


class DocumentIdentityItemIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    document_id: int
    identity_key: Optional[str] = Field(None, max_length=120, validation_alias=AliasChoices("identity_key", "kunci_identitas"))
    page_count: Optional[int] = Field(None, ge=1, validation_alias=AliasChoices("page_count", "jumlah_halaman"))


class BatchIdentityIn(BaseModel):
    items: List[DocumentIdentityItemIn] = Field(..., max_length=500)


class RelationItemIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    src: str = Field(..., max_length=120, validation_alias=AliasChoices("src", "source_key"))
    dst: str = Field(..., max_length=120, validation_alias=AliasChoices("dst", "target_key"))
    rel: str = Field(..., validation_alias=AliasChoices("rel", "relation"))
    sebagian: Union[bool, int] = Field(default=False, validation_alias=AliasChoices("sebagian", "partial"))
    pasal_terkait: Optional[str] = Field(default=None, validation_alias=AliasChoices("pasal_terkait", "articles_text"))
    asal: Optional[str] = Field(default=None, validation_alias=AliasChoices("asal", "origin"))
    bukti: Optional[str] = Field(default=None, validation_alias=AliasChoices("bukti", "evidence"))


class NodeStatusItemIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    key: str = Field(..., max_length=120, validation_alias=AliasChoices("key", "identity_key"))
    status: str


class SyncRelationsIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    relations: List[RelationItemIn] = Field(default_factory=list, max_length=5000)
    nodes: Optional[Union[Dict[str, str], List[NodeStatusItemIn]]] = Field(
        default=None,
        validation_alias=AliasChoices("nodes", "node_status"),
    )
    replace_all: bool = False



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

    # Dokumen yang memenuhi syarat klaim (hanya dokumen aktif)
    claimable_cond = and_(
        Document.is_active == True,  # noqa: E712
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


def _handle_extraction_failure(
    db: Session,
    doc: Document,
    fail_type: JenisKegagalan,
    reason_code: str,
    message: str,
    is_worker_error: bool = False,
) -> dict:
    """
    Mencatat kegagalan ekstraksi (error dari worker atau teks kosong):
    - Status dokumen diubah menjadi gagal (kecuali jika existing failure penempatan_gagal).
    - Mencegah duplikasi entri kegagalan terbuka untuk dokumen yang sama.
    - Mencatat audit log EXTRACTION_FAILED dengan detail.reason_code.
    """
    existing_failure = (
        db.query(IngestFailure)
        .filter(
            IngestFailure.document_id == doc.id,
            IngestFailure.follow_up_status == StatusTindakLanjut.belum_ditangani,
            IngestFailure.reason_code.in_([
                reason_code,
                "teks_kosong",
                "teks_kosong_ocr",
                "penempatan_gagal",
                "simpan_ekstraksi_gagal",
            ]),
        )
        .order_by(IngestFailure.id.desc())
        .first()
    )

    if existing_failure:
        old_msg = existing_failure.message or ""
        text_to_append = f"laporan worker: {message}" if (is_worker_error and message) else message
        if text_to_append and text_to_append not in old_msg:
            combined = f"{old_msg} | {text_to_append}" if old_msg else text_to_append
            existing_failure.message = combined[:1000]
        if reason_code in ("teks_kosong", "teks_kosong_ocr"):
            doc.processing_status = StatusPemrosesan.gagal
        db.commit()
        return {
            "status": "gagal_dicatat",
            "failure_id": existing_failure.id,
        }

    doc.processing_status = StatusPemrosesan.gagal

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
        reason_code=reason_code,
        message=message,
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
        detail={
            "document_id": doc.id,
            "reason_code": reason_code,
            "error": {"code": reason_code, "message": message},
            "failure_id": failure.id,
        },
        commit=False,
    )

    db.commit()
    return {
        "status": "gagal_dicatat",
        "failure_id": failure.id,
    }


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

        fail_type = JenisKegagalan.ekstraksi_gagal
        if err_code == "ocr_gagal":
            fail_type = JenisKegagalan.ocr_gagal
        elif err_code in JenisKegagalan.__members__:
            fail_type = JenisKegagalan[err_code]

        return _handle_extraction_failure(
            db=db,
            doc=doc,
            fail_type=fail_type,
            reason_code=err_code,
            message=err_msg,
            is_worker_error=True,
        )

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
        for fname in [
            "title",
            "regulation_number",
            "regulation_type",
            "release_date",
            "bidang",
            "regulation_year",
            "effective_date",
            "lampiran_dari",
            "label_lampiran",
        ]:
            if getattr(payload, fname, None) is not None:
                ignored_fields.append(fname)
    else:
        if payload.title and payload.title.strip():
            clean_title = payload.title.strip()
            low_title = clean_title.lower()
            is_placeholder = (
                low_title in ("untitled", "untitled document", "tanpa judul", "dokumen", "document")
                or low_title.startswith("microsoft word - document")
            )
            if not is_placeholder and doc.title != clean_title:
                doc.title = clean_title
                changed_fields.append("title")

        year_from_num = None
        if payload.regulation_number and payload.regulation_number.strip():
            clean_num, year_from_num = split_redundant_year(payload.regulation_number)
            if clean_num and doc.regulation_number != clean_num:
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

        if payload.effective_date is not None:
            if doc.effective_date != payload.effective_date:
                doc.effective_date = payload.effective_date
                changed_fields.append("effective_date")

        if payload.bidang and payload.bidang.strip():
            clean_bidang = payload.bidang.strip()
            if doc.bidang != clean_bidang:
                doc.bidang = clean_bidang
                changed_fields.append("bidang")

        # Pindahkan tahun dari nomor ke regulation_year jika regulation_year kosong
        # dan tidak sedang diisi di payload yang sama
        payload_year = getattr(payload, "regulation_year", None)
        if payload_year is not None:
            if doc.regulation_year != payload_year:
                doc.regulation_year = payload_year
                changed_fields.append("regulation_year")
        elif year_from_num is not None:
            if doc.regulation_year is None:
                doc.regulation_year = year_from_num
                changed_fields.append("regulation_year")
            elif doc.regulation_year != year_from_num:
                logger.warning(
                    "Tahun dari nomor regulasi (%s) berbeda dengan regulation_year dokumen (%s) pada dokumen id %s; regulation_year tidak ditimpa.",
                    year_from_num,
                    doc.regulation_year,
                    doc.id,
                )

        # Deteksi lampiran: eksplisit dari worker atau heuristik backend
        if payload.lampiran_dari and payload.lampiran_dari.strip():
            clean_parent_key = payload.lampiran_dari.strip()
            doc.is_attachment = True
            doc.parent_identity_key = clean_parent_key
            if payload.label_lampiran and payload.label_lampiran.strip():
                doc.attachment_label = payload.label_lampiran.strip()
            changed_fields.append("is_attachment")
        else:
            is_att, att_lbl = detect_attachment_heuristic(title=doc.title, original_filename=doc.original_filename)
            if is_att:
                doc.is_attachment = True
                if not doc.attachment_label:
                    doc.attachment_label = att_lbl
                if not doc.parent_identity_key:
                    if payload.identity_key and payload.identity_key.strip():
                        doc.parent_identity_key = payload.identity_key.strip()
                    else:
                        doc.parent_identity_key = fallback_identity_key(
                            doc.regulation_type,
                            doc.regulation_number,
                            doc.regulation_year,
                        )
                changed_fields.append("is_attachment")

    # Tangani identity_key dan page_count
    if doc.is_attachment:
        # Dokumen lampiran tidak menggunakan identity_key
        doc.identity_key = None
    else:
        if payload.identity_key and payload.identity_key.strip():
            clean_key = payload.identity_key.strip()
            if doc.identity_key != clean_key:
                doc.identity_key = clean_key
                changed_fields.append("identity_key")
        elif not doc.identity_key:
            # Cadangan bila kunci_identitas tidak dikirim dan dokumen belum punya kunci
            fallback_key = fallback_identity_key(
                regulation_type=doc.regulation_type,
                regulation_number=doc.regulation_number,
                regulation_year=doc.regulation_year,
            )
            if fallback_key and doc.identity_key != fallback_key:
                doc.identity_key = fallback_key
                changed_fields.append("identity_key")

    if payload.page_count is not None:
        if doc.page_count != payload.page_count:
            doc.page_count = payload.page_count
            changed_fields.append("page_count")

    # Hitung low confidence fields
    low_confidence_fields = []
    metadata_has_low_conf = False

    if payload.confidence and isinstance(payload.confidence, dict):
        for k, v in payload.confidence.items():
            if isinstance(v, (int, float)) and v < settings.metadata_confidence_threshold:
                low_confidence_fields.append(k)
                if k in ("title", "regulation_number", "regulation_type", "release_date"):
                    metadata_has_low_conf = True

    # Evaluasi teks hasil ekstraksi: bila kosong atau hanya spasi -> gagal
    doc_text = doc.full_text or ""
    if not doc_text.strip():
        is_ocr = (
            doc.extraction_method == MetodeEkstraksi.ocr
            or (payload.extraction_method and "ocr" in payload.extraction_method.lower())
        )
        if is_ocr:
            fail_type = JenisKegagalan.ocr_gagal
            reason_code = "teks_kosong_ocr"
            err_msg = "OCR tidak menghasilkan teks — periksa manual (kemungkinan hasil pindai buram)."
        else:
            fail_type = JenisKegagalan.ekstraksi_gagal
            reason_code = "teks_kosong"
            err_msg = "Ekstraksi tidak menghasilkan teks — periksa manual atau proses ulang dengan OCR."

        return _handle_extraction_failure(
            db=db,
            doc=doc,
            fail_type=fail_type,
            reason_code=reason_code,
            message=err_msg,
        )

    # Evaluasi status akhir
    has_empty_reg = not doc.regulation_number or not doc.regulation_number.strip()
    has_empty_title = not doc.title or not doc.title.strip()

    if has_empty_reg or has_empty_title or metadata_has_low_conf:
        doc.processing_status = StatusPemrosesan.perlu_koreksi
    else:
        doc.processing_status = StatusPemrosesan.terindeks

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

    # Simpan hasil ekstraksi terlebih dahulu secara mandiri
    try:
        db.commit()
        db.refresh(doc)
    except Exception as commit_exc:
        db.rollback()
        logger.exception("Gagal menyimpan hasil ekstraksi dokumen ID %s: %s", doc.id, commit_exc)
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.processing_status = StatusPemrosesan.gagal
        job_id = doc.job_id if doc else None
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
            original_filename=(doc.standardized_filename or doc.title or "dokumen.pdf") if doc else "dokumen.pdf",
            source_url=doc.source_url if doc else None,
            failure_type=JenisKegagalan.kesalahan_internal,
            reason_code="simpan_ekstraksi_gagal",
            message=str(commit_exc)[:500],
            is_retryable=True,
            quarantine_path=None,
            file_hash=doc.file_hash if doc else "",
            file_size_bytes=doc.file_size_bytes if doc else 0,
            document_id=doc.id if doc else document_id,
            ingest_options={},
            follow_up_status=StatusTindakLanjut.belum_ditangani,
        )
        db.add(failure)
        db.commit()
        db.refresh(failure)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "simpan_ekstraksi_gagal",
                "message": str(commit_exc)[:500],
                "failure_id": failure.id,
            },
        )

    # Penamaan & Penempatan Otomatis
    is_placed_already = bool(doc.file_path_pdf and doc.file_path_pdf.replace("\\", "/").startswith("kb/"))
    force_place = bool(changed_fields and is_placed_already)

    cat_svc = CategoryService(db)
    place_svc = PlacementService(db, storage, cat_svc, settings)
    place_res = place_svc.place(doc, force=force_place)

    # Bila penempatan gagal
    if not place_res.placed and place_res.reason and place_res.reason.startswith("gagal"):
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.processing_status = StatusPemrosesan.perlu_koreksi

        job_id = doc.job_id if doc else None
        if not job_id:
            default_job = db.query(JobIngest).filter(JobIngest.source_ref == "system:placement").first()
            if not default_job:
                default_job = JobIngest(
                    job_type=JenisJobIngest.unggah_manual,
                    triggered_by="system",
                    source_ref="system:placement",
                    status=StatusJobIngest.selesai,
                )
                db.add(default_job)
                db.flush()
            job_id = default_job.id

        failure = IngestFailure(
            job_id=job_id,
            original_filename=(doc.standardized_filename or doc.title or "dokumen.pdf") if doc else "dokumen.pdf",
            source_url=doc.source_url if doc else None,
            failure_type=JenisKegagalan.kesalahan_internal,
            reason_code="penempatan_gagal",
            message=place_res.reason,
            is_retryable=True,
            quarantine_path=None,
            file_hash=doc.file_hash if doc else "",
            file_size_bytes=doc.file_size_bytes if doc else 0,
            document_id=doc.id if doc else document_id,
            ingest_options={},
            follow_up_status=StatusTindakLanjut.belum_ditangani,
        )
        db.add(failure)
        db.flush()

        record_audit(
            db,
            action=PLACE_DOCUMENT_FAILED,
            target_resource=f"document:{doc.id}" if doc else f"document:{document_id}",
            detail={
                "document_id": doc.id if doc else document_id,
                "reason": place_res.reason,
                "failure_id": failure.id,
            },
            commit=False,
        )
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "penempatan_gagal",
                "message": place_res.reason,
                "failure_id": failure.id,
                "processing_status": "perlu_koreksi",
            },
        )

    placement_info = {
        "document_id": place_res.document_id,
        "placed": place_res.placed,
        "reason": place_res.reason,
        "old_path": place_res.old_path,
        "new_path": place_res.new_path,
        "category_id": place_res.category_id,
        "category_path": place_res.category_path,
    }

    # Penautan lampiran dalam transaksi mandiri
    try:
        if doc.is_attachment:
            link_attachment(db, doc)
        else:
            link_pending_children(db, doc)
        db.commit()
    except Exception as att_exc:
        db.rollback()
        logger.exception("Galat penautan lampiran untuk dokumen ID %s: %s", doc.id, att_exc)

    # Cek duplikat identitas dalam transaksi mandiri (hanya untuk dokumen non-lampiran)
    duplicate_info = None
    if not doc.is_attachment and doc.identity_key:
        try:
            dup_res = check_identity_duplicate(db, doc)
            if dup_res:
                db.commit()
                duplicate_info = dup_res.model_dump()
        except Exception as dup_exc:
            db.rollback()
            logger.exception("Galat cek duplikat identitas untuk dokumen ID %s: %s", doc.id, dup_exc)
            duplicate_info = None

    # Hitung ulang status versi (selalu dijalankan untuk mengevaluasi relasi maupun tanggal berlaku)
    try:
        recompute_status(db, doc)
    except Exception as rec_exc:
        logger.exception("Galat hitung ulang status untuk dokumen ID %s: %s", doc.id, rec_exc)

    db.refresh(doc)

    return {
        "status": doc.processing_status.value,
        "changed_fields": changed_fields,
        "ignored_fields": ignored_fields,
        "low_confidence_fields": low_confidence_fields,
        "placement": placement_info,
        "duplikat": duplicate_info,
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


@router.patch(
    "/documents/identity",
    summary="[Internal] Isi-ulang identity_key dan page_count dokumen secara massal",
    dependencies=[Depends(verify_internal_api_key)],
)
def batch_update_document_identity(
    payload: Union[List[DocumentIdentityItemIn], BatchIdentityIn] = Body(...),
    db: Session = Depends(get_db),
):
    """
    Endpoint isi-ulang identity_key dan page_count untuk dokumen yang sudah ada (Langkah 17).
    Maksimal 500 item per permintaan. Menjalankan cek duplikat identitas per dokumen yang diperbarui.
    """
    items = payload.items if isinstance(payload, BatchIdentityIn) else payload
    if len(items) > 500:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maksimal 500 item per permintaan.",
        )

    updated_count = 0
    not_found: List[int] = []
    duplicates_summary: List[Dict[str, Any]] = []

    for item in items:
        doc = db.query(Document).filter(Document.id == item.document_id).first()
        if not doc:
            not_found.append(item.document_id)
            continue

        if item.identity_key and item.identity_key.strip():
            doc.identity_key = item.identity_key.strip()
        elif not doc.identity_key:
            fb = fallback_identity_key(doc.regulation_type, doc.regulation_number, doc.regulation_year)
            if fb:
                doc.identity_key = fb

        if item.page_count is not None:
            doc.page_count = item.page_count

        updated_count += 1
        db.commit()

        # Tautkan lampiran bila dokumen ini lampiran atau merupakan calon induk
        try:
            if doc.is_attachment:
                link_attachment(db, doc)
            else:
                link_pending_children(db, doc)
            db.commit()
        except Exception as att_exc:
            db.rollback()
            logger.exception("Galat penautan lampiran saat backfill dokumen ID %s: %s", doc.id, att_exc)

        # Jalankan cek duplikat per dokumen (hanya dokumen non-lampiran)
        if not doc.is_attachment:
            try:
                dup_res = check_identity_duplicate(db, doc)
                if dup_res:
                    db.commit()
                    duplicates_summary.append(dup_res.model_dump())
            except Exception as exc:
                db.rollback()
                logger.exception("Galat cek duplikat saat backfill dokumen ID %s: %s", doc.id, exc)

        # Hitung ulang status versi bila identitas terisi
        if doc.identity_key:
            try:
                recompute_status(db, doc)
            except Exception as rec_exc:
                logger.exception("Galat hitung ulang status relasi saat backfill dokumen ID %s: %s", doc.id, rec_exc)

    return {
        "updated": updated_count,
        "not_found": not_found,
        "duplicates": duplicates_summary,
    }


@router.post(
    "/relations",
    summary="[Internal] Sinkronisasi graf relasi dokumen (mengubah/mencabut) dari lapisan data",
    dependencies=[Depends(verify_internal_api_key)],
)
def sync_document_relations(
    payload: SyncRelationsIn,
    db: Session = Depends(get_db),
):
    """
    Menerima relasi (mengubah, mencabut) dan status node dari lapisan data (Langkah 18).
    Maksimal 5000 relasi dan 5000 node per permintaan.
    """
    rel_dicts = [r.model_dump() for r in payload.relations]
    if payload.nodes is None:
        node_dicts = None
    elif isinstance(payload.nodes, dict):
        node_dicts = payload.nodes
    else:
        node_dicts = [n.model_dump() if hasattr(n, "model_dump") else n for n in payload.nodes]

    result = sync_relations(
        db=db,
        relations_data=rel_dicts,
        nodes_data=node_dicts,
        replace_all=payload.replace_all,
    )
    return result


class InvalidateAnalysisCacheIn(BaseModel):
    versi_mesin: Optional[str] = Field(default=None, max_length=50)
    kind: Optional[str] = None
    document_ids: Optional[List[int]] = None
    alasan: Optional[str] = Field(default=None, max_length=200)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v):
        if v is not None:
            valid_kinds = [k.value for k in JenisAnalisa]
            if v not in valid_kinds:
                raise ValueError(
                    f"kind '{v}' tidak dikenal. Nilai yang sah: {', '.join(valid_kinds)}"
                )
        return v

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, v):
        if v is not None and len(v) == 0:
            raise ValueError("document_ids tidak boleh berupa array kosong")
        return v


@router.post(
    "/analysis-cache/invalidate",
    summary="[Internal] Tandai cache analisa lama sebagai usang (Langkah 25)",
    dependencies=[Depends(verify_internal_api_key)],
)
def invalidate_analysis_cache(
    payload: Optional[InvalidateAnalysisCacheIn] = Body(default=None),
    db: Session = Depends(get_db),
):
    """
    Menandai baris cache analisa yang sesuai kriteria sebagai usang (usang_sejak diisi).
    Dipanggil oleh alur deploy mesin analisa (Fathir) saat versi ML diperbarui.
    """
    if payload is None:
        payload = InvalidateAnalysisCacheIn()

    base_query = db.query(AnalysisResult)

    if payload.kind:
        base_query = base_query.filter(AnalysisResult.kind == JenisAnalisa(payload.kind))

    if payload.document_ids is not None:
        base_query = base_query.filter(AnalysisResult.document_id.in_(payload.document_ids))

    if payload.versi_mesin:
        base_query = base_query.filter(
            or_(
                AnalysisResult.ml_version != payload.versi_mesin,
                AnalysisResult.ml_version.is_(None),
            )
        )

    already_stale_count = base_query.filter(AnalysisResult.usang_sejak.isnot(None)).count()

    alasan = payload.alasan
    if not alasan:
        if payload.versi_mesin:
            alasan = f"mesin {payload.versi_mesin}"
        else:
            alasan = "ditandai lapisan data"

    now_utc = datetime.now(timezone.utc)
    ditandai_count = base_query.filter(AnalysisResult.usang_sejak.is_(None)).update(
        {AnalysisResult.usang_sejak: now_utc, AnalysisResult.alasan_usang: alasan},
        synchronize_session=False,
    )

    db.commit()

    record_audit(
        db,
        action=ANALYSIS_CACHE_INVALIDATED,
        user_id=None,
        target_resource="analysis_results",
        detail={
            "versi_mesin": payload.versi_mesin,
            "kind": payload.kind,
            "document_ids": payload.document_ids,
            "alasan": alasan,
            "ditandai": ditandai_count,
            "sudah_usang_sebelumnya": already_stale_count,
        },
        commit=True,
    )

    return {
        "ditandai": ditandai_count,
        "sudah_usang_sebelumnya": already_stale_count,
        "versi_mesin": payload.versi_mesin,
        "kind": payload.kind,
    }


@router.post(
    "/documents/status/recompute",
    summary="[Internal] Hitung ulang status keberlakuan dokumen berdasarkan tanggal berlaku",
    dependencies=[Depends(verify_internal_api_key)],
)
def recompute_documents_status(
    db: Session = Depends(get_db),
):
    """
    Hitung ulang status_keberlakuan untuk dokumen yang:
    - status_source IN ('tanggal_berlaku', None) atau IS NULL
    - effective_date IS NOT NULL
    Dipanggil harian oleh timer di server (lapisan data/infra).
    """
    query = (
        db.query(Document)
        .filter(
            Document.is_active == True,  # noqa: E712
            Document.effective_date.isnot(None),
            or_(
                Document.status_source.is_(None),
                Document.status_source == "tanggal_berlaku",
            ),
        )
    )
    docs = query.all()
    diperiksa = len(docs)
    berubah = recompute_status(db, documents=docs, commit=False)

    record_audit(
        db,
        action=STATUS_RECOMPUTED,
        target_resource="documents:status",
        detail={
            "diperiksa": diperiksa,
            "berubah": berubah,
        },
        commit=False,
    )
    db.commit()

    return {
        "diperiksa": diperiksa,
        "berubah": berubah,
    }


