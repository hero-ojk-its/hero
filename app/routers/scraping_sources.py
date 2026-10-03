"""
Router: /api/v1/scraping-sources
[US-12, US-16, FR-SCR-05] CRUD & eksekutor untuk mengelola sumber dokumen (situs web, folder lokal, OneDrive).
"""
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.category import Category
from app.models.enums import JenisSumber, KlasifikasiAkses, PeranDokumen
from app.models.job_ingest import JobIngest
from app.models.scraping_source import ScrapingSource
from app.models.source_file import SourceFile
from app.schemas.scraping_source import (
    ScrapingSourceCreate,
    ScrapingSourceUpdate,
    ScrapingSourceResponse,
    ScrapingSourceRunRequest,
    FolderOptionItem,
    FolderOptionsResponse,
    SourceFileItem,
    SourceFileListResponse,
    validate_http_url,
)
from app.routers.auth import get_current_user
from app.services.audit_service import (
    record_audit,
    CREATE_SOURCE,
    UPDATE_SOURCE,
    DELETE_SOURCE,
)
from app.services.folder_connector import _is_hidden, _is_temp_file
from app.services.naming_service import validate_naming_format, validate_naming_separator
from app.services.source_runner import SourceRunner

router = APIRouter()


def _get_allowed_source_roots() -> List[Path]:
    """Mendapatkan daftar direktori akar yang diizinkan untuk folder lokal."""
    roots = []
    for r in settings.local_source_roots.split(";"):
        r_str = r.strip()
        if r_str:
            roots.append(Path(r_str).resolve())
    return roots


def _validate_source_url_by_type(url_str: str, source_type: JenisSumber) -> str:
    """Validasi URL / jalur berdasarkan jenis sumber."""
    if not url_str or not url_str.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alamat URL atau jalur folder tidak boleh kosong.",
        )

    trimmed = url_str.strip()

    if source_type == JenisSumber.situs_web:
        try:
            return validate_http_url(trimmed)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Format URL salah: {str(err)}",
            )

    elif source_type == JenisSumber.folder_lokal:
        try:
            resolved_p = Path(trimmed).resolve()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Jalur folder tidak valid: {exc}",
            )

        allowed_roots = _get_allowed_source_roots()
        is_allowed = False
        for root in allowed_roots:
            try:
                if resolved_p.is_relative_to(root):
                    is_allowed = True
                    break
            except (ValueError, AttributeError):
                try:
                    resolved_p.relative_to(root)
                    is_allowed = True
                    break
                except ValueError:
                    pass

        if not is_allowed:
            allowed_str = ", ".join(str(r) for r in allowed_roots)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Folder harus berada di dalam akar yang diizinkan: {allowed_str}",
            )

        if not resolved_p.exists() or not resolved_p.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Folder '{resolved_p}' tidak ditemukan atau bukan sebuah direktori.",
            )

        return str(resolved_p)

    elif source_type == JenisSumber.onedrive_public:
        try:
            valid_url = validate_http_url(trimmed)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Format URL OneDrive salah: {str(err)}",
            )

        parsed = urlparse(valid_url)
        if parsed.scheme != "https":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="URL OneDrive harus menggunakan protokol HTTPS.",
            )

        host = (parsed.netloc or "").lower().split(":")[0]
        if host != "onedrive.live.com" and host != "1drv.ms" and not host.endswith(".sharepoint.com"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Host URL OneDrive tidak valid. Harus berupa onedrive.live.com, 1drv.ms, atau *.sharepoint.com.",
            )

        return valid_url

    return trimmed


@router.post(
    "/",
    response_model=ScrapingSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Menambah situs/folder sumber baru",
)
def create_scraping_source(
    payload: ScrapingSourceCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    [US-12, US-16, FR-SCR-05] Menambah sumber dokumen baru (situs web, folder lokal, OneDrive).
    """
    # 1. Validasi nama
    if not payload.name or not payload.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nama situs/folder sumber tidak boleh kosong.",
        )

    # 2. Validasi URL / Jalur sesuai tipe sumber
    valid_url = _validate_source_url_by_type(payload.url, payload.source_type)

    # 3. Cek keunikan URL / Jalur
    existing = db.query(ScrapingSource).filter(ScrapingSource.url == valid_url).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Alamat '{valid_url}' sudah terdaftar pada situs sumber ID {existing.id} ('{existing.name}').",
        )

    # 4. Buat record sumber baru
    source = ScrapingSource(
        name=payload.name.strip(),
        url=valid_url,
        source_type=payload.source_type,
        crawl_depth=payload.crawl_depth,
        recursive=payload.recursive,
        default_access_classification=payload.default_access_classification or (
            KlasifikasiAkses.publik if payload.source_type == JenisSumber.situs_web else KlasifikasiAkses.non_publik
        ),
        default_document_role=payload.default_document_role,
        default_naming_format=validate_naming_format(payload.default_naming_format) if payload.default_naming_format is not None else None,
        default_naming_separator=validate_naming_separator(payload.default_naming_separator) if payload.default_naming_separator is not None else None,
        is_active=payload.is_active,
    )
    db.add(source)
    db.flush()

    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None
    record_audit(
        db,
        action=CREATE_SOURCE,
        user_id=actor_user_id,
        target_resource=f"scraping_source:{source.id}",
        detail={"name": source.name, "source_type": source.source_type.value, "url": source.url},
        ip_address=client_ip,
        commit=False,
    )

    db.commit()
    db.refresh(source)
    return source


@router.get(
    "/",
    response_model=List[ScrapingSourceResponse],
    summary="Menampilkan daftar semua situs/folder sumber",
)
def list_scraping_sources(
    is_active: Optional[bool] = None,
    source_type: Optional[JenisSumber] = None,
    db: Session = Depends(get_db),
):
    """
    [US-12, US-16] Menampilkan daftar semua sumber dokumen.
    Mendukung filter opsional `is_active` dan `source_type`.
    """
    query = db.query(ScrapingSource)
    if is_active is not None:
        query = query.filter(ScrapingSource.is_active == is_active)
    if source_type is not None:
        query = query.filter(ScrapingSource.source_type == source_type)
    return query.order_by(ScrapingSource.id.asc()).all()


@router.get(
    "/folder-options",
    response_model=FolderOptionsResponse,
    summary="Daftar opsi folder lokal yang tersedia",
)
def get_folder_options(
    db: Session = Depends(get_db),
):
    """
    [US-16] Mengembalikan subfolder di dalam local_source_roots sampai kedalaman 2:
    path, name, pdf_count, already_registered_source_id.
    Path di luar root dan symlink yang keluar dari root tidak boleh bocor.
    """
    allowed_roots = _get_allowed_source_roots()
    registered_sources = (
        db.query(ScrapingSource)
        .filter(ScrapingSource.source_type == JenisSumber.folder_lokal)
        .all()
    )
    reg_map = {}
    for s in registered_sources:
        try:
            reg_map[str(Path(s.url).resolve())] = s.id
        except Exception:
            reg_map[s.url] = s.id

    options: List[FolderOptionItem] = []
    seen_paths = set()

    for root in allowed_roots:
        if not root.exists() or not root.is_dir():
            continue

        try:
            entries = list(root.iterdir())
        except (PermissionError, OSError):
            continue

        for entry in sorted(entries, key=lambda x: x.name.lower()):
            if not entry.is_dir() or _is_hidden(entry):
                continue

            try:
                resolved_entry = entry.resolve()
            except (PermissionError, OSError):
                continue

            try:
                if not resolved_entry.is_relative_to(root):
                    continue
            except (ValueError, AttributeError):
                try:
                    resolved_entry.relative_to(root)
                except ValueError:
                    continue

            p_str = str(resolved_entry)
            if p_str in seen_paths:
                continue
            seen_paths.add(p_str)

            pdf_count = 0
            try:
                pdf_count = sum(
                    1 for f in resolved_entry.glob("*.pdf")
                    if not _is_hidden(f) and not _is_temp_file(f.name)
                )
            except (PermissionError, OSError):
                pass

            options.append(
                FolderOptionItem(
                    path=p_str,
                    name=entry.name,
                    pdf_count=pdf_count,
                    already_registered_source_id=reg_map.get(p_str),
                )
            )

            # Kedalaman 2: subfolder di dalam entry
            try:
                sub_entries = list(resolved_entry.iterdir())
            except (PermissionError, OSError):
                continue

            for sub_entry in sorted(sub_entries, key=lambda x: x.name.lower()):
                if not sub_entry.is_dir() or _is_hidden(sub_entry):
                    continue

                try:
                    resolved_sub = sub_entry.resolve()
                except (PermissionError, OSError):
                    continue

                try:
                    if not resolved_sub.is_relative_to(root):
                        continue
                except (ValueError, AttributeError):
                    try:
                        resolved_sub.relative_to(root)
                    except ValueError:
                        continue

                sub_p_str = str(resolved_sub)
                if sub_p_str in seen_paths:
                    continue
                seen_paths.add(sub_p_str)

                sub_pdf_count = 0
                try:
                    sub_pdf_count = sum(
                        1 for f in resolved_sub.glob("*.pdf")
                        if not _is_hidden(f) and not _is_temp_file(f.name)
                    )
                except (PermissionError, OSError):
                    pass

                options.append(
                    FolderOptionItem(
                        path=sub_p_str,
                        name=f"{entry.name}/{sub_entry.name}",
                        pdf_count=sub_pdf_count,
                        already_registered_source_id=reg_map.get(sub_p_str),
                    )
                )

    return FolderOptionsResponse(items=options)


@router.get(
    "/{source_id}",
    response_model=ScrapingSourceResponse,
    summary="Detail satu situs/folder sumber",
)
def get_scraping_source(
    source_id: int,
    db: Session = Depends(get_db),
):
    """Mendapatkan detail satu situs/folder sumber berdasarkan ID."""
    source = db.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Situs sumber dengan ID {source_id} tidak ditemukan.",
        )
    return source


def _process_update(
    source_id: int,
    payload: ScrapingSourceUpdate,
    request: Request,
    db: Session,
    current_user=None,
) -> ScrapingSource:
    """Helper untuk update data situs/folder sumber (PUT & PATCH)."""
    source = db.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Situs sumber dengan ID {source_id} tidak ditemukan.",
        )

    target_source_type = payload.source_type if payload.source_type is not None else source.source_type

    # Validasi nama
    if payload.name is not None:
        trimmed_name = payload.name.strip()
        if not trimmed_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nama situs sumber tidak boleh kosong.",
            )
        source.name = trimmed_name

    # Validasi URL / Jalur
    if payload.url is not None:
        valid_url = _validate_source_url_by_type(payload.url, target_source_type)
        duplicate = (
            db.query(ScrapingSource)
            .filter(ScrapingSource.url == valid_url, ScrapingSource.id != source_id)
            .first()
        )
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Alamat '{valid_url}' sudah digunakan oleh situs sumber ID {duplicate.id} ('{duplicate.name}').",
            )
        source.url = valid_url

    if payload.source_type is not None:
        source.source_type = payload.source_type

    if payload.crawl_depth is not None or target_source_type != JenisSumber.situs_web:
        if target_source_type != JenisSumber.situs_web:
            source.crawl_depth = None
        else:
            if payload.crawl_depth is not None:
                source.crawl_depth = payload.crawl_depth

    if payload.recursive is not None:
        source.recursive = payload.recursive

    if payload.default_access_classification is not None:
        source.default_access_classification = payload.default_access_classification

    if payload.default_document_role is not None:
        source.default_document_role = payload.default_document_role

    if payload.default_naming_format is not None:
        try:
            validate_naming_format(payload.default_naming_format)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(err),
            )
        source.default_naming_format = payload.default_naming_format

    if payload.default_naming_separator is not None:
        try:
            validate_naming_separator(payload.default_naming_separator)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(err),
            )
        source.default_naming_separator = payload.default_naming_separator

    if payload.is_active is not None:
        source.is_active = payload.is_active

    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None
    record_audit(
        db,
        action=UPDATE_SOURCE,
        user_id=actor_user_id,
        target_resource=f"scraping_source:{source.id}",
        detail={"name": source.name, "source_type": source.source_type.value, "url": source.url},
        ip_address=client_ip,
        commit=False,
    )

    db.commit()
    db.refresh(source)
    return source


@router.put(
    "/{source_id}",
    response_model=ScrapingSourceResponse,
    summary="Mengubah properti situs/folder sumber (PUT)",
)
def update_scraping_source_put(
    source_id: int,
    payload: ScrapingSourceUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return _process_update(source_id, payload, request, db, current_user)


@router.patch(
    "/{source_id}",
    response_model=ScrapingSourceResponse,
    summary="Mengubah properti situs/folder sumber (PATCH)",
)
def update_scraping_source_patch(
    source_id: int,
    payload: ScrapingSourceUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return _process_update(source_id, payload, request, db, current_user)


@router.delete(
    "/{source_id}",
    summary="Menghapus situs/folder sumber",
)
def delete_scraping_source(
    source_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """[US-12, US-16] Menghapus situs/folder sumber berdasarkan ID."""
    source = db.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Situs sumber dengan ID {source_id} tidak ditemukan.",
        )

    source_name = source.name
    db.delete(source)

    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    client_ip = request.client.host if request.client else None
    record_audit(
        db,
        action=DELETE_SOURCE,
        user_id=actor_user_id,
        target_resource=f"scraping_source:{source_id}",
        ip_address=client_ip,
        commit=False,
    )

    db.commit()
    return {
        "message": f"Situs sumber '{source_name}' berhasil dihapus.",
        "id": source_id,
    }


@router.post(
    "/{source_id}/run",
    summary="Menjalankan sinkronisasi / crawling sumber dokumen",
)
def run_scraping_source(
    source_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    response: Response,
    payload: Optional[ScrapingSourceRunRequest] = None,
    wait: bool = Query(False, description="Jika true, tunggu eksekusi selesai secara sinkron"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    [US-16, FR-SCR-05] Menjalankan pemindaian dan sinkronisasi sumber dokumen.
    - default (wait=false) -> 202 Accepted {job_id, status: 'antrian', message}
    - wait=true -> 200 OK dengan detail ringkasan job setelah eksekusi selesai.
    """
    naming_fmt = None
    naming_sep = None
    category_id = None
    if payload:
        if payload.category_id is not None:
            cat = db.query(Category).filter(Category.id == payload.category_id).first()
            if not cat:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Kategori dengan ID {payload.category_id} tidak ditemukan.",
                )
            category_id = payload.category_id

        if payload.naming_format is not None:
            try:
                validate_naming_format(payload.naming_format)
            except ValueError as err:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=str(err),
                )
            naming_fmt = payload.naming_format
        if payload.naming_separator is not None:
            try:
                validate_naming_separator(payload.naming_separator)
            except ValueError as err:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=str(err),
                )
            naming_sep = payload.naming_separator

    actor_user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    actor_username = current_user.username if current_user and getattr(current_user, "username", None) else None
    client_ip = request.client.host if request.client else None

    runner = SourceRunner(db)
    job = runner.start_run(
        source_id=source_id,
        actor_user_id=actor_user_id,
        actor_username=actor_username,
        ip_address=client_ip,
        naming_format=naming_fmt,
        naming_separator=naming_sep,
        category_id=category_id,
    )

    if wait:
        # Eksekusi secara sinkron
        response.status_code = status.HTTP_200_OK
        runner.execute(job.id, naming_format=naming_fmt, naming_separator=naming_sep)

        # Ambil job terbaru
        db.refresh(job)
        source = db.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
        return {
            "message": f"Eksekusi sumber '{source.name if source else source_id}' selesai dengan status '{job.status.value}'.",
            "job_id": job.id,
            "job_status": job.status.value,
            "total_found": job.total_found,
            "success_count": job.success_count,
            "duplicate_count": job.duplicate_count,
            "skipped_count": job.skipped_count,
            "failed_count": job.failed_count,
            "last_run_message": source.last_run_message if source else None,
        }
    else:
        # Eksekusi di BackgroundTasks
        response.status_code = status.HTTP_202_ACCEPTED
        background_tasks.add_task(runner.execute, job.id, naming_fmt, naming_sep)
        return {
            "job_id": job.id,
            "status": "antrian",
            "message": f"Job sinkronisasi folder ID {job.id} telah dijadwalkan.",
        }


@router.get(
    "/{source_id}/files",
    response_model=SourceFileListResponse,
    summary="Daftar berkas yang terindeks pada sumber",
)
def list_source_files(
    source_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    last_outcome: Optional[str] = Query(None, description="Filter: success | duplicate | failed | skipped_unchanged"),
    db: Session = Depends(get_db),
):
    """
    [US-16] Mengambil daftar berkas pada sumber beserta status sinkronisasi terakhir.
    """
    source = db.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Situs sumber dengan ID {source_id} tidak ditemukan.",
        )

    query = db.query(SourceFile).filter(SourceFile.source_id == source_id)
    if last_outcome:
        query = query.filter(SourceFile.last_outcome == last_outcome)

    total = query.count()
    files = query.order_by(SourceFile.relative_path.asc()).offset(skip).limit(limit).all()

    items = []
    for f in files:
        doc_title = f.document.title if f.document else None
        items.append(
            SourceFileItem(
                id=f.id,
                source_id=f.source_id,
                relative_path=f.relative_path,
                size_bytes=f.size_bytes,
                mtime=f.mtime,
                file_hash=f.file_hash,
                document_id=f.document_id,
                document_title=doc_title,
                last_outcome=f.last_outcome,
                last_seen_job_id=f.last_seen_job_id,
                created_at=f.created_at,
                updated_at=f.updated_at,
            )
        )

    return SourceFileListResponse(total=total, items=items)
