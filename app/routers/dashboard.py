"""
Router: /api/v1/dashboard
Endpoint ringkasan statistik Knowledge Base dan pipeline ingest (Langkah 5).
Menggunakan query agregat SQL yang dioptimalkan tanpa N+1.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, Depends
from sqlalchemy import func, case, desc, or_, and_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.models.scraping_source import ScrapingSource
from app.models.enums import (
    JenisSumber,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
    StatusTindakLanjut,
)

router = APIRouter()


@router.get("/summary", summary="Ringkasan statistik Knowledge Base & Ingest")
def get_dashboard_summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Mengembalikan ringkasan statistik metrik Knowledge Base, status keberlakuan,
    pipeline ingest, dan sumber scraping dengan query agregat SQL yang efisien.
    """
    target_fase1 = 20

    # 1. Agregat Dokumen KB (Total corpus, draft, placed, inbox)
    doc_stats = (
        db.query(
            func.count(case((Document.document_role == PeranDokumen.corpus_eksisting, 1))).label("corpus"),
            func.count(case((Document.document_role == PeranDokumen.draft_kajian, 1))).label("draft"),
            func.count(case((Document.file_path_pdf.like("kb/%"), 1))).label("placed"),
            func.count(case((~Document.file_path_pdf.like("kb/%"), 1))).label("inbox"),
        )
        .one()
    )
    corpus_docs = doc_stats.corpus or 0
    draft_docs = doc_stats.draft or 0
    placed_docs = doc_stats.placed or 0
    inbox_docs = doc_stats.inbox or 0

    # 3. Status Keberlakuan (Semua enum disertakan dengan default 0)
    by_status_keberlakuan = {s.value: 0 for s in StatusKeberlakuan}
    status_keb_query = (
        db.query(Document.status_keberlakuan, func.count(Document.id))
        .group_by(Document.status_keberlakuan)
        .all()
    )
    for st, cnt in status_keb_query:
        if st is not None:
            key = st.value if hasattr(st, "value") else str(st)
            by_status_keberlakuan[key] = cnt

    # 4. Status Pemrosesan (Semua enum disertakan dengan default 0)
    by_processing_status = {s.value: 0 for s in StatusPemrosesan}
    status_proc_query = (
        db.query(Document.processing_status, func.count(Document.id))
        .group_by(Document.processing_status)
        .all()
    )
    for st, cnt in status_proc_query:
        if st is not None:
            key = st.value if hasattr(st, "value") else str(st)
            by_processing_status[key] = cnt

    # 5. By Regulation Type (Hanya corpus eksisting, max 15)
    reg_type_query = (
        db.query(Document.regulation_type, func.count(Document.id).label("count"))
        .filter(Document.document_role == PeranDokumen.corpus_eksisting, Document.regulation_type.isnot(None))
        .group_by(Document.regulation_type)
        .order_by(desc("count"))
        .limit(15)
        .all()
    )
    by_regulation_type = [
        {"regulation_type": rt, "count": cnt} for rt, cnt in reg_type_query if rt
    ]

    # 6. By Year (Hanya corpus eksisting, max 15, urutan tahun terbaru)
    year_query = (
        db.query(func.extract("year", Document.release_date).label("year"), func.count(Document.id).label("count"))
        .filter(Document.document_role == PeranDokumen.corpus_eksisting, Document.release_date.isnot(None))
        .group_by("year")
        .order_by(desc("year"))
        .limit(15)
        .all()
    )
    by_year = [
        {"year": int(y), "count": cnt} for y, cnt in year_query if y is not None
    ]

    # 7. Ingest metrics: open failures & needs review
    open_failures_cnt = (
        db.query(func.count(IngestFailure.id))
        .filter(IngestFailure.follow_up_status == StatusTindakLanjut.belum_ditangani)
        .scalar()
        or 0
    )

    # Needs review count
    candidates = (
        db.query(Document.id, Document.processing_status, Document.extraction_confidence)
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
        .all()
    )
    needs_review_cnt = 0
    for cid, proc_st, conf in candidates:
        if proc_st == StatusPemrosesan.perlu_koreksi:
            needs_review_cnt += 1
        elif conf and isinstance(conf, dict):
            if any(isinstance(v, (int, float)) and v < settings.metadata_confidence_threshold for v in conf.values()):
                needs_review_cnt += 1

    # Recent jobs (5 terakhir)
    recent_job_objs = db.query(JobIngest).order_by(desc(JobIngest.id)).limit(5).all()
    recent_jobs = [
        {
            "id": j.id,
            "job_type": j.job_type.value if hasattr(j.job_type, "value") else str(j.job_type),
            "status": j.status.value if hasattr(j.status, "value") else str(j.status),
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            "success_count": j.success_count,
            "duplicate_count": j.duplicate_count,
            "failed_count": j.failed_count,
        }
        for j in recent_job_objs
    ]

    # 8. Sources metrics
    by_source_type = {s.value: 0 for s in JenisSumber}
    total_sources = 0
    active_sources = 0
    sources_query = (
        db.query(
            ScrapingSource.source_type,
            func.count(ScrapingSource.id).label("cnt"),
            func.count(case((ScrapingSource.is_active == True, 1))).label("active_cnt"),  # noqa: E712
        )
        .group_by(ScrapingSource.source_type)
        .all()
    )
    for st, cnt, active_cnt in sources_query:
        if st is not None:
            key = st.value if hasattr(st, "value") else str(st)
            by_source_type[key] = cnt
            total_sources += cnt
            active_sources += (active_cnt or 0)

    return {
        "kb": {
            "corpus_documents": corpus_docs,
            "draft_documents": draft_docs,
            "target_fase1": target_fase1,
            "target_met": corpus_docs >= target_fase1,
            "by_status_keberlakuan": by_status_keberlakuan,
            "by_processing_status": by_processing_status,
            "by_regulation_type": by_regulation_type,
            "by_year": by_year,
            "placed_documents": placed_docs,
            "inbox_documents": inbox_docs,
        },
        "ingest": {
            "open_failures": open_failures_cnt,
            "needs_review": needs_review_cnt,
            "recent_jobs": recent_jobs,
        },
        "sources": {
            "total": total_sources,
            "active": active_sources,
            "by_type": by_source_type,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
