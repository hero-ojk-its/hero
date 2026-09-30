"""
app/routers/scans.py
Router publik untuk Alur Pindai Situs (Scan -> Bandingkan -> Centang -> Tarik).
[US-16, FR-SCR-02, FR-SCR-05]
"""
import io
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.routers.auth import get_current_user
from app.models.enums import StatusPindai, StatusKandidat, TujuanTarik, StatusJobIngest
from app.models.scan_session import ScanSession
from app.models.scan_candidate import ScanCandidate
from app.models.job_ingest import JobIngest
from app.models.document import Document
from app.services.scan_service import ScanService, get_scan_service
from app.schemas.scan import (
    ScanCreate,
    ScanSessionResponse,
    ScanListResponse,
    CandidateListResponse,
    CandidateResponse,
    CandidateMatchDocument,
    ScanSummaryCount,
    PullProgress,
    ScanSelectionUpdate,
    ScanSelectionResponse,
    ScanPullRequest,
)

router = APIRouter(prefix="/api/v1/scans", tags=["Scans"])


def _build_session_response(session: ScanSession, db: Session, request: Optional[Request] = None) -> ScanSessionResponse:
    """Helper untuk menyusun ScanSessionResponse lengkap beserta ringkasan dan progress."""
    candidates = db.query(ScanCandidate).filter(ScanCandidate.scan_id == session.id).all()
    total_cand = len(candidates)
    baru_cand = sum(1 for c in candidates if c.match_status == StatusKandidat.baru)
    exist_cand = sum(1 for c in candidates if c.match_status == StatusKandidat.sudah_ada)
    uncert_cand = sum(1 for c in candidates if c.match_status == StatusKandidat.mungkin_ada)
    selected_cand = sum(1 for c in candidates if c.selected)

    summary = ScanSummaryCount(
        total=total_cand,
        baru=baru_cand,
        sudah_ada=exist_cand,
        mungkin_ada=uncert_cand,
        terpilih=selected_cand,
    )

    pull_prog = None
    if session.pull_job_id:
        job = db.query(JobIngest).filter(JobIngest.id == session.pull_job_id).first()
        if job:
            pct = (
                int(round(job.processed_count / job.total_found * 100))
                if job.total_found and job.total_found > 0
                else (100 if job.status in (StatusJobIngest.selesai, StatusJobIngest.gagal) else 0)
            )
            pull_prog = PullProgress(
                job_id=job.id,
                status=job.status.value,
                processed_count=job.processed_count,
                total_found=job.total_found,
                progress_percent=pct,
            )

    download_url = None
    if session.destination == TujuanTarik.unduh_folder and session.status == StatusPindai.selesai:
        download_url = f"/api/v1/scans/{session.id}/download"

    return ScanSessionResponse(
        id=session.id,
        source_id=session.source_id,
        start_url=session.start_url,
        crawl_depth=session.crawl_depth,
        mode=session.mode,
        crawler_name=session.crawler_name,
        status=session.status,
        cancel_requested=session.cancel_requested,
        pages_visited=session.pages_visited,
        candidates_summary=summary,
        truncated=session.truncated,
        errors=session.errors or [],
        error_message=session.error_message,
        destination=session.destination,
        naming_format=session.naming_format,
        naming_separator=session.naming_separator,
        pull_job_id=session.pull_job_id,
        pull_progress=pull_prog,
        download_url=download_url,
        claimed_at=session.claimed_at,
        started_at=session.started_at,
        scanned_at=session.scanned_at,
        finished_at=session.finished_at,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.post(
    "/",
    response_model=Any,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {"model": ScanSessionResponse, "description": "Pemindaian selesai secara sinkron (wait=true)"},
        202: {"description": "Sesi pemindaian berhasil dijadwalkan (wait=false)"},
    },
)
def create_and_start_scan(
    payload: ScanCreate,
    wait: bool = Query(False, description="Tunggu hingga pemindaian selesai secara sinkron"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    [US-16, FR-SCR-02] Memulai sesi pemindaian situs web.
    - default (wait=false) -> 202 Accepted {scan_id, status: 'antrian', message}
    - wait=true -> 200 OK dengan detail ScanSessionResponse setelah pemindaian selesai.
    """
    actor_user_id = getattr(current_user, "id", None) if current_user else None
    client_ip = request.client.host if request and request.client else None

    svc = ScanService(db)
    session = svc.start_scan(payload, actor_user_id=actor_user_id, ip_address=client_ip)

    if wait and session.mode != "push":
        response.status_code = status.HTTP_200_OK
        svc.execute_scan(session.id)
        db.expire_all()
        db.refresh(session)
        return _build_session_response(session, db, request)

    if session.mode != "push":
        background_tasks.add_task(svc.execute_scan, session.id)

    return {
        "scan_id": session.id,
        "status": session.status.value,
        "message": f"Sesi pemindaian #{session.id} berhasil dijadwalkan.",
    }


@router.get("/", response_model=ScanListResponse)
def list_scan_sessions(
    source_id: Optional[int] = Query(None, description="Filter berdasarkan ID sumber scraping"),
    status_filter: Optional[StatusPindai] = Query(None, alias="status", description="Filter status pemindaian"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    [US-16] Mengambil daftar riwayat sesi pemindaian dengan filter dan paginasi.
    """
    query = db.query(ScanSession)
    if source_id is not None:
        query = query.filter(ScanSession.source_id == source_id)
    if status_filter is not None:
        query = query.filter(ScanSession.status == status_filter)

    total = query.count()
    sessions = query.order_by(desc(ScanSession.id)).offset(skip).limit(limit).all()

    items = [_build_session_response(s, db) for s in sessions]
    return ScanListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get(
    "/{scan_id}",
    response_model=ScanSessionResponse,
    responses={404: {"description": "Sesi pemindaian tidak ditemukan"}},
)
def get_scan_session_detail(
    scan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    [US-16] Mengambil detail lengkap status sesi pemindaian beserta progres penarikan.
    """
    session = db.query(ScanSession).filter(ScanSession.id == scan_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sesi pemindaian dengan ID {scan_id} tidak ditemukan.",
        )
    return _build_session_response(session, db, request)


@router.get(
    "/{scan_id}/candidates",
    response_model=CandidateListResponse,
    responses={404: {"description": "Sesi pemindaian tidak ditemukan"}},
)
def list_scan_candidates(
    scan_id: int,
    match_status: Optional[StatusKandidat] = Query(None, description="Filter status kecocokan KB"),
    selected: Optional[bool] = Query(None, description="Filter status centang"),
    pull_outcome: Optional[str] = Query(None, description="Filter hasil penarikan"),
    q: Optional[str] = Query(None, description="Pencarian nama berkas (case-insensitive)"),
    page: Optional[int] = Query(None, ge=1, description="Nomor halaman (opsional, kompatibilitas)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    [US-16] Mengambil daftar kandidat PDF dalam sesi pemindaian.
    """
    session = db.query(ScanSession).filter(ScanSession.id == scan_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sesi pemindaian dengan ID {scan_id} tidak ditemukan.",
        )

    query = (
        db.query(ScanCandidate)
        .options(joinedload(ScanCandidate.match_document))
        .filter(ScanCandidate.scan_id == scan_id)
    )

    if match_status is not None:
        query = query.filter(ScanCandidate.match_status == match_status)
    if selected is not None:
        query = query.filter(ScanCandidate.selected == selected)
    if pull_outcome is not None and pull_outcome.strip():
        val = pull_outcome.strip().lower()
        outcome_aliases = {
            "success": ["berhasil", "success"],
            "berhasil": ["berhasil", "success"],
            "duplicate": ["duplikat", "duplicate"],
            "duplikat": ["duplikat", "duplicate"],
            "failed": ["gagal", "failed"],
            "gagal": ["gagal", "failed"],
            "downloaded": ["diunduh", "downloaded"],
            "diunduh": ["diunduh", "downloaded"],
        }
        allowed = outcome_aliases.get(val, [val])
        query = query.filter(ScanCandidate.pull_outcome.in_(allowed))
    if q and q.strip():
        query = query.filter(ScanCandidate.filename.ilike(f"%{q.strip()}%"))

    total = query.count()
    effective_skip = (page - 1) * limit if page is not None and page >= 1 else skip
    candidates = query.order_by(ScanCandidate.id.asc()).offset(effective_skip).limit(limit).all()

    items = []
    for c in candidates:
        match_doc_info = None
        if c.match_document:
            match_doc_info = CandidateMatchDocument(
                id=c.match_document.id,
                title=c.match_document.title,
                regulation_number=c.match_document.regulation_number,
            )

        items.append(
            CandidateResponse(
                id=c.id,
                scan_id=c.scan_id,
                url=c.url,
                filename=c.filename,
                size_bytes=c.size_bytes,
                found_on_page=c.found_on_page,
                depth=c.depth,
                match_status=c.match_status,
                match_reason=c.match_reason,
                match_document_id=c.match_document_id,
                match_document=match_doc_info,
                selected=c.selected,
                pull_outcome=c.pull_outcome,
                document_id=c.document_id,
                failure_id=c.failure_id,
                export_path=c.export_path,
                message=c.message,
            )
        )

    return CandidateListResponse(items=items, total=total, skip=effective_skip, limit=limit)


@router.patch(
    "/{scan_id}/selection",
    response_model=ScanSelectionResponse,
    responses={404: {"description": "Sesi pemindaian tidak ditemukan"}},
)
def update_candidate_selection(
    scan_id: int,
    payload: ScanSelectionUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    [US-16] Memperbarui centang pilihan kandidat berkas (select_all_new, select_none, atau set).
    """
    svc = ScanService(db)
    return svc.update_selection(scan_id, payload)


@router.post(
    "/{scan_id}/pull",
    response_model=Any,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {"model": ScanSessionResponse, "description": "Penarikan selesai secara sinkron (wait=true)"},
        202: {"description": "Penarikan berkas berhasil dijadwalkan (wait=false)"},
        404: {"description": "Sesi pemindaian tidak ditemukan"},
    },
)
def start_scan_pull(
    scan_id: int,
    payload: ScanPullRequest,
    wait: bool = Query(False, description="Tunggu hingga penarikan selesai secara sinkron"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    [US-16, FR-SCR-05] Memulai proses penarikan berkas kandidat terpilih.
    - default (wait=false) -> 202 Accepted {job_id, status: 'antrian', message}
    - wait=true -> 200 OK dengan detail ScanSessionResponse setelah penarikan selesai.
    """
    actor_user_id = getattr(current_user, "id", None) if current_user else None
    actor_username = getattr(current_user, "username", None) if current_user else None
    client_ip = request.client.host if request and request.client else None

    svc = ScanService(db)
    session, job = svc.start_pull(
        scan_id=scan_id,
        destination=payload.destination,
        naming_format=payload.naming_format,
        naming_separator=payload.naming_separator,
        actor_user_id=actor_user_id,
        actor_username=actor_username,
        ip_address=client_ip,
    )

    if wait:
        response.status_code = status.HTTP_200_OK
        svc.execute_pull(session.id)
        db.expire_all()
        db.refresh(session)
        return _build_session_response(session, db, request)

    background_tasks.add_task(svc.execute_pull, session.id)
    return {
        "job_id": job.id,
        "status": job.status.value,
        "message": f"Penarikan {job.total_found} berkas untuk sesi #{session.id} ke '{payload.destination.value}' berhasil dijadwalkan.",
    }


@router.post(
    "/{scan_id}/cancel",
    response_model=ScanSessionResponse,
    responses={404: {"description": "Sesi pemindaian tidak ditemukan"}},
)
def cancel_scan_session(
    scan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    [US-16] Membatalkan sesi pemindaian atau penarikan.
    """
    actor_user_id = getattr(current_user, "id", None) if current_user else None
    client_ip = request.client.host if request and request.client else None

    svc = ScanService(db)
    session = svc.cancel_scan(scan_id, actor_user_id=actor_user_id, ip_address=client_ip)
    return _build_session_response(session, db, request)


@router.get("/{scan_id}/download")
def download_scan_export_zip(
    scan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    [US-16] Mengunduh seluruh berkas hasil penarikan tujuan 'unduh_folder' sebagai arsip ZIP.
    """
    actor_user_id = getattr(current_user, "id", None) if current_user else None
    client_ip = request.client.host if request and request.client else None

    svc = ScanService(db)
    zip_buffer = svc.build_export_zip(scan_id, actor_user_id=actor_user_id, ip_address=client_ip)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="hero-scan-{scan_id}.zip"',
        },
    )
