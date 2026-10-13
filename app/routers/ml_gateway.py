"""
app/routers/ml_gateway.py
Gerbang terpadu untuk layanan Analisa dan Harmonisasi Regulasi (ML Layer).

Tanggung jawab gerbang:
1. Memvalidasi hak akses dokumen sebelum meneruskan ke ML (proteksi dokumen nonaktif & dokumen non-publik).
2. Menyaring hasil pencarian, daftar dokumen, dan korpus harmonisasi agar dokumen yang tidak diizinkan tidak bocor.
3. Menyeragamkan kode dan format galat (503 bila belum dikonfigurasi / tidak tersedia, 504 saat timeout).
4. Mencatat jejak audit RUN_HARMONIZATION saat harmonisasi dijalankan.
"""
import logging
from collections.abc import AsyncIterator
from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.enums import KlasifikasiAkses, StatusPemrosesan
from app.routers.auth import get_current_user
from app.services.audit_service import RUN_HARMONIZATION, record_audit

logger = logging.getLogger("hero")

router = APIRouter(tags=["Analisa (ML)"])


async def get_ml_client() -> AsyncIterator[httpx.AsyncClient]:
    """Dependency klien HTTP untuk komunikasi dengan layanan analisa ML."""
    async with httpx.AsyncClient(timeout=settings.ml_timeout_seconds) as client:
        yield client


def allowed_document_ids(db: Session) -> set[int]:
    """
    Himpunan ID dokumen yang diizinkan untuk diakses melalui layanan analisa:
    - is_active = true
    - processing_status in {terindeks, perlu_koreksi} (SYNCABLE)
    - jika protect_non_public_when_auth_disabled and not auth_enabled: hanya access_classification = publik
    """
    query = (
        db.query(Document.id)
        .filter(
            Document.is_active == True,  # noqa: E712
            Document.processing_status.in_([
                StatusPemrosesan.terindeks,
                StatusPemrosesan.perlu_koreksi,
            ]),
        )
    )
    if settings.protect_non_public_when_auth_disabled and not settings.auth_enabled:
        query = query.filter(Document.access_classification == KlasifikasiAkses.publik)
    return {row[0] for row in query.all()}


def check_document_access(db: Session, document_id: int) -> Document:
    """
    Pemeriksaan status dan akses sebuah dokumen sebelum permintaan diteruskan ke ML:
    - Tidak ditemukan -> 404
    - Nonaktif -> 404 dokumen_nonaktif
    - Non-publik saat login nonaktif -> 403
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dokumen tidak ditemukan")
    if not doc.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "dokumen_nonaktif", "message": "Dokumen tidak aktif / telah dinonaktifkan."},
        )
    if settings.protect_non_public_when_auth_disabled and not settings.auth_enabled:
        if doc.access_classification != KlasifikasiAkses.publik:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Dokumen non-publik hanya dapat dibuka setelah login diaktifkan.",
            )
    return doc


async def forward_ml_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    params: Optional[dict[str, Any]] = None,
    json_data: Any = None,
) -> tuple[int, Any]:
    """Meneruskan permintaan HTTP ke layanan analisa ML."""
    base_url = (settings.ml_service_url or "").strip().rstrip("/")
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "layanan_analisa_belum_dikonfigurasi",
                "message": "Layanan analisa belum dikonfigurasi (ML_SERVICE_URL kosong).",
            },
        )

    target_url = f"{base_url}{path}"
    try:
        resp = await client.request(
            method=method,
            url=target_url,
            params=params,
            json=json_data,
        )
    except httpx.ConnectError as exc:
        logger.warning("Gagal terhubung ke layanan analisa: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "layanan_analisa_tidak_tersedia",
                "message": "Layanan analisa tidak dapat dihubungi.",
            },
        ) from exc
    except httpx.TimeoutException as exc:
        logger.warning("Layanan analisa timeout: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "code": "layanan_analisa_timeout",
                "message": "Permintaan ke layanan analisa melebihi batas waktu.",
            },
        ) from exc
    except httpx.RequestError as exc:
        logger.warning("Galat permintaan ke layanan analisa: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "layanan_analisa_tidak_tersedia",
                "message": f"Galat komunikasi dengan layanan analisa: {exc}",
            },
        ) from exc

    try:
        data = resp.json()
    except Exception as exc:
        logger.warning("Respon layanan analisa bukan JSON: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "layanan_analisa_jawaban_tidak_valid",
                "message": "Jawaban dari layanan analisa bukan format JSON valid.",
            },
        ) from exc

    return resp.status_code, data


@router.get("/health", summary="Kesiapan Layanan Analisa ML")
async def get_ml_health(
    client: httpx.AsyncClient = Depends(get_ml_client),
    current_user=Depends(get_current_user),
):
    """Mengecek status kesiapan layanan analisa (indeks vektor, korpus, mode AI)."""
    status_code, data = await forward_ml_request(client, "GET", "/health")
    if status_code >= 400:
        return JSONResponse(status_code=status_code, content=data)
    return data


@router.get("/dokumen", summary="Daftar Dokumen Siap Analisa")
async def get_ml_dokumen(
    peran: Optional[Literal["corpus_eksisting", "draft_kajian"]] = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_ml_client),
    current_user=Depends(get_current_user),
):
    """Dokumen backend yang siap dianalisa, disaring sesuai hak akses."""
    params: dict[str, Any] = {"limit": limit}
    if peran is not None:
        params["peran"] = peran

    status_code, data = await forward_ml_request(client, "GET", "/dokumen", params=params)
    if status_code >= 400:
        return JSONResponse(status_code=status_code, content=data)

    if not isinstance(data, dict):
        return data

    allowed_ids = allowed_document_ids(db)
    items = data.get("items", [])
    filtered_items = [it for it in items if isinstance(it, dict) and it.get("document_id") in allowed_ids]
    discarded = len(items) - len(filtered_items)
    data["items"] = filtered_items
    data["total"] = len(filtered_items)
    data["disaring_backend"] = discarded
    return data


@router.get("/analisa/{document_id}", summary="Analisa Regulasi")
async def get_ml_analisa(
    document_id: int,
    mode: Optional[Literal["deterministik", "ai"]] = Query("deterministik"),
    db: Session = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_ml_client),
    current_user=Depends(get_current_user),
):
    """Ringkasan terstruktur dan poin kunci berbasis pasal."""
    check_document_access(db, document_id)
    params = {"mode": mode} if mode else {}
    status_code, data = await forward_ml_request(client, "GET", f"/analisa/{document_id}", params=params)
    if status_code >= 400:
        return JSONResponse(status_code=status_code, content=data)
    return data


@router.get("/analisa/{document_id}/klausul", summary="Pencarian Klausul Relevan")
async def get_ml_analisa_klausul(
    document_id: int,
    kebutuhan: str = Query(..., min_length=3),
    k: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_ml_client),
    current_user=Depends(get_current_user),
):
    """Pasal yang relevan dengan kebutuhan pengguna dalam dokumen."""
    check_document_access(db, document_id)
    params = {"kebutuhan": kebutuhan, "k": k}
    status_code, data = await forward_ml_request(client, "GET", f"/analisa/{document_id}/klausul", params=params)
    if status_code >= 400:
        return JSONResponse(status_code=status_code, content=data)
    return data


@router.post("/harmonisasi/{document_id}", summary="Harmonisasi Draft Regulasi")
async def post_ml_harmonisasi(
    document_id: int,
    request: Request,
    body: Optional[list[int]] = Body(None),
    db: Session = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_ml_client),
    current_user=Depends(get_current_user),
):
    """
    Analisa harmonisasi draft terhadap korpus dokumen regulasi.
    Body opsional berisi daftar document_id pembatas korpus (null = seluruh korpus yang diizinkan).
    """
    check_document_access(db, document_id)
    allowed_ids = allowed_document_ids(db)

    if body is None:
        forward_body = sorted(list(allowed_ids - {document_id}))
    else:
        forward_body = sorted(list((set(body) & allowed_ids) - {document_id}))

    status_code, data = await forward_ml_request(
        client,
        "POST",
        f"/harmonisasi/{document_id}",
        json_data=forward_body,
    )
    if status_code >= 400:
        return JSONResponse(status_code=status_code, content=data)

    if not isinstance(data, dict):
        return data

    orig_kandidat = data.get("kandidat", [])
    orig_temuan = data.get("temuan", [])
    orig_rujukan = data.get("rujukan", [])

    filtered_kandidat = []
    if isinstance(orig_kandidat, list):
        for k_item in orig_kandidat:
            if isinstance(k_item, dict) and k_item.get("document_id") in allowed_ids:
                filtered_kandidat.append(k_item)

    filtered_temuan = []
    if isinstance(orig_temuan, list):
        for t_item in orig_temuan:
            if not isinstance(t_item, dict):
                continue
            pembanding = t_item.get("pembanding")
            p_doc_id = pembanding.get("document_id") if isinstance(pembanding, dict) else None
            t_doc_id = t_item.get("document_id")
            if p_doc_id is not None and p_doc_id not in allowed_ids:
                continue
            if t_doc_id is not None and t_doc_id not in allowed_ids:
                continue
            filtered_temuan.append(t_item)

    if isinstance(orig_rujukan, list):
        for r_item in orig_rujukan:
            if isinstance(r_item, dict):
                r_doc_id = r_item.get("document_id")
                if r_doc_id is not None and r_doc_id not in allowed_ids:
                    r_item["document_id"] = None

    discarded_count = (len(orig_kandidat) - len(filtered_kandidat)) + (len(orig_temuan) - len(filtered_temuan))
    data["kandidat"] = filtered_kandidat
    data["temuan"] = filtered_temuan
    data["rujukan"] = orig_rujukan
    data["disaring_backend"] = discarded_count

    actor_user_id = getattr(current_user, "id", None) if current_user else None
    client_ip = request.client.host if request and request.client else None
    record_audit(
        db,
        action=RUN_HARMONIZATION,
        user_id=actor_user_id,
        target_resource=f"document:{document_id}",
        detail={
            "document_id": document_id,
            "jumlah_temuan": len(filtered_temuan),
            "korpus_dokumen": forward_body,
        },
        ip_address=client_ip,
        commit=True,
    )

    return data


@router.get("/cari", summary="Pencarian Semantik Regulasi")
async def get_ml_cari(
    q: str = Query(..., min_length=2),
    metode: Optional[Literal["lexical", "lsa", "semantic", "hybrid", "pgvector"]] = None,
    k: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_ml_client),
    current_user=Depends(get_current_user),
):
    """Pencarian pasal semantik/leksikal dengan penyesuaian metode default."""
    chosen_method = metode or settings.ml_default_search_method
    params = {"q": q, "metode": chosen_method, "k": k}

    status_code, data = await forward_ml_request(client, "GET", "/cari", params=params)
    if status_code >= 400:
        return JSONResponse(status_code=status_code, content=data)

    if not isinstance(data, dict):
        return data

    allowed_ids = allowed_document_ids(db)
    items = data.get("items", [])
    filtered_items = [it for it in items if isinstance(it, dict) and it.get("document_id") in allowed_ids]
    discarded = len(items) - len(filtered_items)
    data["items"] = filtered_items
    data["total"] = len(filtered_items)
    data["disaring_backend"] = discarded
    return data


@router.get("/pasal-mirip", summary="Pencarian Pasal Mirip Korpus")
async def get_ml_pasal_mirip(
    teks: str = Query(..., min_length=20),
    k: int = Query(10, ge=1, le=50),
    kecuali_dokumen: Optional[int] = Query(None),
    hanya_publik: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_ml_client),
    current_user=Depends(get_current_user),
):
    """Pencarian pasal termirip di korpus backend untuk sepotong teks."""
    if settings.protect_non_public_when_auth_disabled and not settings.auth_enabled:
        effective_hanya_publik = True
    else:
        effective_hanya_publik = hanya_publik

    params: dict[str, Any] = {"teks": teks, "k": k}
    if kecuali_dokumen is not None:
        params["kecuali_dokumen"] = kecuali_dokumen
    if effective_hanya_publik is not None:
        params["hanya_publik"] = "true" if effective_hanya_publik else "false"

    status_code, data = await forward_ml_request(client, "GET", "/pasal-mirip", params=params)
    if status_code >= 400:
        return JSONResponse(status_code=status_code, content=data)

    if not isinstance(data, dict):
        return data

    allowed_ids = allowed_document_ids(db)
    items = data.get("items", [])
    filtered_items = [it for it in items if isinstance(it, dict) and it.get("document_id") in allowed_ids]
    discarded = len(items) - len(filtered_items)
    data["items"] = filtered_items
    data["total"] = len(filtered_items)
    data["disaring_backend"] = discarded
    return data
