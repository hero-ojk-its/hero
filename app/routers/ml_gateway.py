"""
app/routers/ml_gateway.py
Gerbang terpadu untuk layanan Analisa dan Harmonisasi Regulasi (ML Layer).

Tanggung jawab gerbang:
1. Memvalidasi hak akses dokumen sebelum meneruskan ke ML (proteksi dokumen nonaktif & dokumen non-publik).
2. Menyaring secara rekursif hasil analisa, temuan, referensi, dan korpus harmonisasi agar data dokumen yang tidak diizinkan tidak bocor.
3. Menyeragamkan kode dan format galat (503 bila belum dikonfigurasi / tidak tersedia, 504 saat timeout, 422 bila pembanding kosong).
4. Mencatat jejak audit ringkas RUN_HARMONIZATION saat harmonisasi dijalankan.
"""
import logging
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.enums import JenisAnalisa, KlasifikasiAkses, ModeAnalisa, StatusPemrosesan
from app.routers.auth import get_current_user
from app.services.analysis_result_service import (
    compute_params_hash,
    get_cached_result,
    get_document_fingerprint,
    save_analysis_result,
)
from app.services.audit_service import RUN_HARMONIZATION, record_audit

logger = logging.getLogger("hero")

router = APIRouter(tags=["Analisa (ML)"])

SENSITIVE_REF_KEYS = {"kutipan", "pdf", "halaman", "pasal", "pasal_mirip", "skor"}


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


def saring_rujukan(
    obj: Any,
    allowed_ids: set[int],
    parent_key: Optional[str] = None,
) -> tuple[Any, int]:
    """
    Penyaring rekursif untuk respons ML:
    - Elemen list berupa dict dengan kunci `document_id` bernilai int yang tidak ada di `allowed_ids` -> dibuang.
      (Kecuali dalam list 'rujukan', di mana elemen dinetralkan dengan document_id=None dan kunci sensitif dihapus).
    - Elemen list berupa dict yang memiliki sub-dict `pembanding` dengan `document_id` tidak diizinkan -> dibuang (temuan[]).
    - Dict bukan elemen list dengan `document_id` tidak diizinkan -> set document_id = null, hapus kunci sensitif
      (kutipan, pdf, halaman, pasal, pasal_mirip, skor), teks rujukan tetap dipertahankan.
    - document_id = null (register belum diunduh) dibiarkan.
    - Objek level atas 'draft' pada harmonisasi dikecualikan.
    """
    if isinstance(obj, dict):
        new_dict = {}
        total_dibuang = 0
        for k, v in obj.items():
            # Pengecualian objek draft level atas pada respons harmonisasi
            if k == "draft" and parent_key is None:
                new_dict[k] = v
                continue

            # Dict bukan elemen list dengan document_id tidak diizinkan
            if isinstance(v, dict):
                doc_id = v.get("document_id")
                if isinstance(doc_id, int) and doc_id not in allowed_ids:
                    v_copy = dict(v)
                    v_copy["document_id"] = None
                    for sk in SENSITIVE_REF_KEYS:
                        v_copy.pop(sk, None)
                    total_dibuang += 1
                    rec_val, rec_count = saring_rujukan(v_copy, allowed_ids, parent_key=k)
                    total_dibuang += rec_count
                    new_dict[k] = rec_val
                    continue

            filtered_v, count_v = saring_rujukan(v, allowed_ids, parent_key=k)
            total_dibuang += count_v
            new_dict[k] = filtered_v

        # Sesuaikan total jika ada list items
        if "items" in new_dict and isinstance(new_dict["items"], list) and "total" in new_dict:
            new_dict["total"] = len(new_dict["items"])

        return new_dict, total_dibuang

    elif isinstance(obj, list):
        new_list = []
        total_dibuang = 0
        for item in obj:
            if isinstance(item, dict):
                # Penanganan khusus elemen list rujukan: netralkan dokumen_id, jangan buang seluruh rujukan
                if parent_key == "rujukan":
                    doc_id = item.get("document_id")
                    if isinstance(doc_id, int) and doc_id not in allowed_ids:
                        item_copy = dict(item)
                        item_copy["document_id"] = None
                        for sk in SENSITIVE_REF_KEYS:
                            item_copy.pop(sk, None)
                        total_dibuang += 1
                        rec_item, rec_count = saring_rujukan(item_copy, allowed_ids, parent_key="rujukan_item")
                        total_dibuang += rec_count
                        new_list.append(rec_item)
                    else:
                        rec_item, rec_count = saring_rujukan(item, allowed_ids, parent_key="rujukan_item")
                        total_dibuang += rec_count
                        new_list.append(rec_item)
                    continue

                # Aturan 1: Elemen list dengan document_id int yang tidak diizinkan -> DIBUANG
                doc_id = item.get("document_id")
                if isinstance(doc_id, int) and doc_id not in allowed_ids:
                    total_dibuang += 1
                    continue

                # Aturan 2: Elemen list dengan pembanding.document_id tidak diizinkan -> DIBUANG
                pembanding = item.get("pembanding")
                if isinstance(pembanding, dict):
                    p_doc_id = pembanding.get("document_id")
                    if isinstance(p_doc_id, int) and p_doc_id not in allowed_ids:
                        total_dibuang += 1
                        continue

                rec_item, rec_count = saring_rujukan(item, allowed_ids, parent_key=parent_key)
                total_dibuang += rec_count
                new_list.append(rec_item)
            else:
                rec_item, rec_count = saring_rujukan(item, allowed_ids, parent_key=parent_key)
                total_dibuang += rec_count
                new_list.append(rec_item)

        return new_list, total_dibuang

    else:
        return obj, 0


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

    allowed_ids = allowed_document_ids(db)
    filtered_data, discarded = saring_rujukan(data, allowed_ids)
    if isinstance(filtered_data, dict):
        filtered_data["disaring_backend"] = discarded
    return filtered_data


@router.get("/analisa/{document_id}", summary="Analisa Regulasi")
async def get_ml_analisa(
    document_id: int,
    mode: Optional[Literal["deterministik", "ai"]] = Query("deterministik"),
    segar: bool = Query(False, description="Paksa hitung ulang tanpa cache"),
    db: Session = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_ml_client),
    current_user=Depends(get_current_user),
):
    """Ringkasan terstruktur dan poin kunci berbasis pasal."""
    doc = check_document_access(db, document_id)
    allowed_ids = allowed_document_ids(db)

    req_mode = ModeAnalisa.ai if mode == "ai" else ModeAnalisa.deterministik
    params_hash = compute_params_hash(JenisAnalisa.analisa)
    curr_fingerprint = get_document_fingerprint(doc)

    # 1. Cek Cache Hit
    if settings.ml_cache_enabled and not segar:
        cached = get_cached_result(
            db,
            document_id=document_id,
            kind=JenisAnalisa.analisa,
            mode=req_mode,
            params_hash=params_hash,
            expected_fingerprint=curr_fingerprint,
        )
        if cached:
            filtered_data, discarded = saring_rujukan(cached.result, allowed_ids)
            if isinstance(filtered_data, dict):
                filtered_data["disaring_backend"] = discarded
                filtered_data["cache"] = {
                    "hit": True,
                    "dibuat": cached.created_at.isoformat() if cached.created_at else None,
                    "basi": False,
                    "mode_tersimpan": cached.mode.value if hasattr(cached.mode, "value") else str(cached.mode),
                }
            return filtered_data

    # 2. Panggil Layanan ML
    params = {"mode": mode} if mode else {}
    start_time = time.perf_counter()
    status_code = None
    data = None
    ml_exc = None

    try:
        status_code, data = await forward_ml_request(client, "GET", f"/analisa/{document_id}", params=params)
    except HTTPException as exc:
        ml_exc = exc

    # 3. Tangani kegagalan ML (503/504 fallback ke cache basi jika ada)
    if ml_exc is not None:
        if ml_exc.status_code in (status.HTTP_503_SERVICE_UNAVAILABLE, status.HTTP_504_GATEWAY_TIMEOUT):
            fallback = get_cached_result(
                db,
                document_id=document_id,
                kind=JenisAnalisa.analisa,
                mode=req_mode,
                params_hash=params_hash,
                expected_fingerprint=None,
            )
            if fallback:
                filtered_data, discarded = saring_rujukan(fallback.result, allowed_ids)
                if isinstance(filtered_data, dict):
                    filtered_data["disaring_backend"] = discarded
                    filtered_data["cache"] = {
                        "hit": True,
                        "dibuat": fallback.created_at.isoformat() if fallback.created_at else None,
                        "basi": True,
                        "mode_tersimpan": fallback.mode.value if hasattr(fallback.mode, "value") else str(fallback.mode),
                    }
                return filtered_data
        raise ml_exc

    if status_code is not None and status_code >= 400:
        return JSONResponse(status_code=status_code, content=data)

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    # 4. Tentukan mode yang benar-benar dipakai dan simpan ke cache jika diaktifkan
    actual_mode_str = data.get("mode_dipakai") if isinstance(data, dict) else None
    if not actual_mode_str:
        actual_mode_str = "deterministik"
    save_mode = ModeAnalisa.ai if actual_mode_str == "ai" else ModeAnalisa.deterministik

    saved_row = None
    actor_user_id = getattr(current_user, "id", None) if current_user else None
    if settings.ml_cache_enabled and isinstance(data, dict):
        saved_row = save_analysis_result(
            db=db,
            document_id=document_id,
            kind=JenisAnalisa.analisa,
            mode=save_mode,
            params_hash=params_hash,
            source_fingerprint=curr_fingerprint,
            raw_result=data,
            ml_version=data.get("versi"),
            duration_ms=duration_ms,
            user_id=actor_user_id,
        )

    # 5. Saring rujukan dan kembalikan dengan metadata cache
    filtered_data, discarded = saring_rujukan(data, allowed_ids)
    if isinstance(filtered_data, dict):
        filtered_data["disaring_backend"] = discarded
        dibuat_str = (
            saved_row.created_at.isoformat()
            if saved_row and saved_row.created_at
            else datetime.now(timezone.utc).isoformat()
        )
        filtered_data["cache"] = {
            "hit": False,
            "dibuat": dibuat_str,
            "basi": False,
            "mode_tersimpan": save_mode.value,
        }
    return filtered_data


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

    allowed_ids = allowed_document_ids(db)
    filtered_data, discarded = saring_rujukan(data, allowed_ids)
    if isinstance(filtered_data, dict):
        filtered_data["disaring_backend"] = discarded
    return filtered_data


@router.post("/harmonisasi/{document_id}", summary="Harmonisasi Draft Regulasi")
async def post_ml_harmonisasi(
    document_id: int,
    request: Request,
    segar: bool = Query(False, description="Paksa hitung ulang tanpa cache"),
    body: Optional[list[int]] = Body(None),
    db: Session = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_ml_client),
    current_user=Depends(get_current_user),
):
    """
    Analisa harmonisasi draft terhadap korpus dokumen regulasi.
    Body opsional berisi daftar document_id pembatas korpus (null = seluruh korpus yang diizinkan).
    """
    doc = check_document_access(db, document_id)
    allowed_ids = allowed_document_ids(db)

    if body is None:
        forward_body = sorted(list(allowed_ids - {document_id}))
    else:
        forward_body = sorted(list((set(body) & allowed_ids) - {document_id}))

    if not forward_body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "pembanding_kosong",
                "message": "Tidak ada dokumen pembanding yang dapat diakses.",
            },
        )

    curr_fingerprint = get_document_fingerprint(doc)
    params_hash = compute_params_hash(JenisAnalisa.harmonisasi, extra=forward_body)
    kind = JenisAnalisa.harmonisasi
    mode = ModeAnalisa.deterministik
    actor_user_id = getattr(current_user, "id", None) if current_user else None
    client_ip = request.client.host if request and request.client else None

    # 1. Cek Cache Hit
    if settings.ml_cache_enabled and not segar:
        cached = get_cached_result(
            db,
            document_id=document_id,
            kind=kind,
            mode=mode,
            params_hash=params_hash,
            expected_fingerprint=curr_fingerprint,
        )
        if cached:
            filtered_data, discarded = saring_rujukan(cached.result, allowed_ids)
            if isinstance(filtered_data, dict):
                filtered_data["disaring_backend"] = discarded
                filtered_data["cache"] = {
                    "hit": True,
                    "dibuat": cached.created_at.isoformat() if cached.created_at else None,
                    "basi": False,
                    "mode_tersimpan": "deterministik",
                }
            record_audit(
                db,
                action=RUN_HARMONIZATION,
                user_id=actor_user_id,
                target_resource=f"document:{document_id}",
                detail={
                    "document_id": document_id,
                    "jumlah_temuan": len(filtered_data.get("temuan", [])) if isinstance(filtered_data, dict) else 0,
                    "jumlah_korpus": len(forward_body),
                    "korpus_dibatasi_pengguna": body is not None,
                    "cache_hit": True,
                },
                ip_address=client_ip,
                commit=True,
            )
            return filtered_data

    # 2. Panggil Layanan ML
    start_time = time.perf_counter()
    status_code = None
    data = None
    ml_exc = None

    try:
        status_code, data = await forward_ml_request(
            client,
            "POST",
            f"/harmonisasi/{document_id}",
            json_data=forward_body,
        )
    except HTTPException as exc:
        ml_exc = exc

    # 3. Tangani kegagalan ML (503/504 fallback ke cache basi jika ada)
    if ml_exc is not None:
        if ml_exc.status_code in (status.HTTP_503_SERVICE_UNAVAILABLE, status.HTTP_504_GATEWAY_TIMEOUT):
            fallback = get_cached_result(
                db,
                document_id=document_id,
                kind=kind,
                mode=mode,
                params_hash=params_hash,
                expected_fingerprint=None,
            )
            if fallback:
                filtered_data, discarded = saring_rujukan(fallback.result, allowed_ids)
                if isinstance(filtered_data, dict):
                    filtered_data["disaring_backend"] = discarded
                    filtered_data["cache"] = {
                        "hit": True,
                        "dibuat": fallback.created_at.isoformat() if fallback.created_at else None,
                        "basi": True,
                        "mode_tersimpan": "deterministik",
                    }
                record_audit(
                    db,
                    action=RUN_HARMONIZATION,
                    user_id=actor_user_id,
                    target_resource=f"document:{document_id}",
                    detail={
                        "document_id": document_id,
                        "jumlah_temuan": len(filtered_data.get("temuan", [])) if isinstance(filtered_data, dict) else 0,
                        "jumlah_korpus": len(forward_body),
                        "korpus_dibatasi_pengguna": body is not None,
                        "cache_hit": True,
                    },
                    ip_address=client_ip,
                    commit=True,
                )
                return filtered_data
        raise ml_exc

    if status_code is not None and status_code >= 400:
        return JSONResponse(status_code=status_code, content=data)

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    # 4. Simpan ke cache jika diaktifkan
    saved_row = None
    if settings.ml_cache_enabled and isinstance(data, dict):
        saved_row = save_analysis_result(
            db=db,
            document_id=document_id,
            kind=kind,
            mode=mode,
            params_hash=params_hash,
            source_fingerprint=curr_fingerprint,
            raw_result=data,
            ml_version=data.get("versi"),
            duration_ms=duration_ms,
            user_id=actor_user_id,
        )

    # 5. Saring rujukan dan catat audit
    filtered_data, discarded = saring_rujukan(data, allowed_ids)
    if isinstance(filtered_data, dict):
        filtered_data["disaring_backend"] = discarded
        dibuat_str = (
            saved_row.created_at.isoformat()
            if saved_row and saved_row.created_at
            else datetime.now(timezone.utc).isoformat()
        )
        filtered_data["cache"] = {
            "hit": False,
            "dibuat": dibuat_str,
            "basi": False,
            "mode_tersimpan": "deterministik",
        }

    record_audit(
        db,
        action=RUN_HARMONIZATION,
        user_id=actor_user_id,
        target_resource=f"document:{document_id}",
        detail={
            "document_id": document_id,
            "jumlah_temuan": len(filtered_data.get("temuan", [])) if isinstance(filtered_data, dict) else 0,
            "jumlah_korpus": len(forward_body),
            "korpus_dibatasi_pengguna": body is not None,
            "cache_hit": False,
        },
        ip_address=client_ip,
        commit=True,
    )

    return filtered_data


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

    allowed_ids = allowed_document_ids(db)
    filtered_data, discarded = saring_rujukan(data, allowed_ids)
    if isinstance(filtered_data, dict):
        filtered_data["disaring_backend"] = discarded
    return filtered_data


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

    allowed_ids = allowed_document_ids(db)
    filtered_data, discarded = saring_rujukan(data, allowed_ids)
    if isinstance(filtered_data, dict):
        filtered_data["disaring_backend"] = discarded
    return filtered_data
