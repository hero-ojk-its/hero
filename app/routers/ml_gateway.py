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
from app.core.permissions import perlu_izin, Izin
from app.services.analysis_result_service import (
    compute_params_hash,
    get_cached_result,
    get_document_fingerprint,
    save_analysis_result,
)
from app.services.audit_service import RUN_ANALYSIS, RUN_HARMONIZATION, record_audit
from app.services.analysis_run_service import record_run

logger = logging.getLogger("hero")

router = APIRouter(tags=["Analisa (ML)"])

SENSITIVE_REF_KEYS = {"kutipan", "pdf", "halaman", "pasal", "pasal_mirip", "skor"}


async def get_ml_client() -> AsyncIterator[httpx.AsyncClient]:
    """Dependency klien HTTP untuk komunikasi dengan layanan analisa ML."""
    async with httpx.AsyncClient(timeout=settings.ml_timeout_seconds) as client:
        yield client


def allowed_document_ids(db: Session, user: Optional[Any] = None) -> set[int]:
    """
    Himpunan ID dokumen yang diizinkan untuk diakses melalui layanan analisa:
    - is_active = true
    - processing_status in {terindeks, perlu_koreksi} (SYNCABLE)
    - disaring sesuai hak akses dokumen non-publik
    """
    from app.core.permissions import boleh_baca_nonpublik

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
    if not boleh_baca_nonpublik(user):
        query = query.filter(Document.access_classification == KlasifikasiAkses.publik)
    return {row[0] for row in query.all()}


def check_document_access(db: Session, document_id: int, user: Optional[Any] = None) -> Document:
    """
    Pemeriksaan status dan akses sebuah dokumen sebelum permintaan diteruskan ke ML:
    - Tidak ditemukan -> 404
    - Nonaktif -> 404 dokumen_nonaktif
    - Non-publik saat pengguna tidak berhak -> 403
    """
    from app.core.permissions import check_non_public_access

    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dokumen tidak ditemukan")
    if not doc.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "dokumen_nonaktif", "message": "Dokumen tidak aktif / telah dinonaktifkan."},
        )
    check_non_public_access(doc, user)
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
    current_user=Depends(perlu_izin(Izin.KB_BACA)),
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
    current_user=Depends(perlu_izin(Izin.KB_BACA)),
):
    """Dokumen backend yang siap dianalisa, disaring sesuai hak akses."""
    params: dict[str, Any] = {"limit": limit}
    if peran is not None:
        params["peran"] = peran

    status_code, data = await forward_ml_request(client, "GET", "/dokumen", params=params)
    if status_code >= 400:
        return JSONResponse(status_code=status_code, content=data)

    allowed_ids = allowed_document_ids(db, user=current_user)
    filtered_data, discarded = saring_rujukan(data, allowed_ids)
    if isinstance(filtered_data, dict):
        filtered_data["disaring_backend"] = discarded
    return filtered_data


@router.get("/analisa/{document_id}", summary="Analisa Regulasi")
async def get_ml_analisa(
    document_id: int,
    request: Request,
    mode: Optional[Literal["deterministik", "ai"]] = Query("deterministik"),
    segar: bool = Query(False, description="Paksa hitung ulang tanpa cache"),
    db: Session = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_ml_client),
    current_user=Depends(perlu_izin(Izin.ANALISA_JALANKAN)),
):
    """Ringkasan terstruktur dan poin kunci berbasis pasal."""
    doc = check_document_access(db, document_id, user=current_user)
    allowed_ids = allowed_document_ids(db, user=current_user)

    req_mode = ModeAnalisa.ai if mode == "ai" else ModeAnalisa.deterministik
    params_hash = compute_params_hash(JenisAnalisa.analisa)
    curr_fingerprint = get_document_fingerprint(doc)
    params_dict = {"mode": mode if mode else "deterministik"}
    actor_user_id = getattr(current_user, "id", None) if current_user else None
    client_ip = request.client.host if request and request.client else None

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
            run_id = None
            try:
                run_id = record_run(
                    db=db,
                    document_id=document_id,
                    kind=JenisAnalisa.analisa,
                    mode_diminta=req_mode,
                    mode_dipakai=cached.mode,
                    sumber="cache",
                    segar=segar,
                    params=params_dict,
                    params_hash=params_hash,
                    source_fingerprint=curr_fingerprint,
                    http_status=200,
                    duration_ms=0,
                    ml_version=cached.ml_version,
                    result_raw=cached.result,
                    created_by=actor_user_id,
                )
            except Exception as exc:
                logger.warning("Gagal memanggil record_run pada cache hit analisa: %s", exc)

            mode_tersimpan_str = cached.mode.value if hasattr(cached.mode, "value") else str(cached.mode)
            try:
                record_audit(
                    db,
                    action=RUN_ANALYSIS,
                    user_id=actor_user_id,
                    target_resource=f"document:{document_id}",
                    detail={
                        "mode_diminta": req_mode.value,
                        "mode_dipakai": mode_tersimpan_str,
                        "sumber": "cache",
                        "http_status": 200,
                        "run_id": run_id,
                    },
                    ip_address=client_ip,
                    commit=True,
                )
            except Exception as exc:
                logger.warning("Gagal mencatat audit RUN_ANALYSIS: %s", exc)

            filtered_data, discarded = saring_rujukan(cached.result, allowed_ids)
            if isinstance(filtered_data, dict):
                filtered_data["disaring_backend"] = discarded
                filtered_data["cache"] = {
                    "hit": True,
                    "dibuat": cached.created_at.isoformat() if cached.created_at else None,
                    "basi": False,
                    "mode_tersimpan": mode_tersimpan_str,
                    "run_id": run_id,
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
        duration_ms = int((time.perf_counter() - start_time) * 1000)
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
                run_id = None
                try:
                    run_id = record_run(
                        db=db,
                        document_id=document_id,
                        kind=JenisAnalisa.analisa,
                        mode_diminta=req_mode,
                        mode_dipakai=fallback.mode,
                        sumber="cache_basi",
                        segar=segar,
                        params=params_dict,
                        params_hash=params_hash,
                        source_fingerprint=curr_fingerprint,
                        http_status=200,
                        duration_ms=duration_ms,
                        ml_version=fallback.ml_version,
                        result_raw=fallback.result,
                        created_by=actor_user_id,
                    )
                except Exception as exc:
                    logger.warning("Gagal memanggil record_run pada cache basi analisa: %s", exc)

                mode_tersimpan_str = fallback.mode.value if hasattr(fallback.mode, "value") else str(fallback.mode)
                try:
                    record_audit(
                        db,
                        action=RUN_ANALYSIS,
                        user_id=actor_user_id,
                        target_resource=f"document:{document_id}",
                        detail={
                            "mode_diminta": req_mode.value,
                            "mode_dipakai": mode_tersimpan_str,
                            "sumber": "cache_basi",
                            "http_status": 200,
                            "run_id": run_id,
                        },
                        ip_address=client_ip,
                        commit=True,
                    )
                except Exception as exc:
                    logger.warning("Gagal mencatat audit RUN_ANALYSIS: %s", exc)

                filtered_data, discarded = saring_rujukan(fallback.result, allowed_ids)
                if isinstance(filtered_data, dict):
                    filtered_data["disaring_backend"] = discarded
                    filtered_data["cache"] = {
                        "hit": True,
                        "dibuat": fallback.created_at.isoformat() if fallback.created_at else None,
                        "basi": True,
                        "mode_tersimpan": mode_tersimpan_str,
                        "run_id": run_id,
                    }
                return filtered_data

        # Tidak ada fallback cache basi, catat riwayat gagal & audit sebelum melempar exception
        error_code = ml_exc.detail.get("code") if isinstance(ml_exc.detail, dict) else None
        run_id = None
        try:
            run_id = record_run(
                db=db,
                document_id=document_id,
                kind=JenisAnalisa.analisa,
                mode_diminta=req_mode,
                mode_dipakai=None,
                sumber="gagal",
                segar=segar,
                params=params_dict,
                params_hash=params_hash,
                source_fingerprint=curr_fingerprint,
                http_status=ml_exc.status_code,
                duration_ms=duration_ms,
                error_code=error_code,
                created_by=actor_user_id,
            )
        except Exception as exc:
            logger.warning("Gagal memanggil record_run pada kegagalan analisa: %s", exc)

        try:
            record_audit(
                db,
                action=RUN_ANALYSIS,
                user_id=actor_user_id,
                target_resource=f"document:{document_id}",
                detail={
                    "mode_diminta": req_mode.value,
                    "mode_dipakai": None,
                    "sumber": "gagal",
                    "http_status": ml_exc.status_code,
                    "run_id": run_id,
                },
                ip_address=client_ip,
                commit=True,
            )
        except Exception as exc:
            logger.warning("Gagal mencatat audit RUN_ANALYSIS: %s", exc)

        raise ml_exc

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    # 4. Tangani respons error HTTP lain dari ML (status_code >= 400)
    if status_code is not None and status_code >= 400:
        error_code = None
        if isinstance(data, dict):
            error_code = data.get("code") or (data.get("detail") if isinstance(data.get("detail"), str) else None)
        run_id = None
        try:
            run_id = record_run(
                db=db,
                document_id=document_id,
                kind=JenisAnalisa.analisa,
                mode_diminta=req_mode,
                mode_dipakai=None,
                sumber="gagal",
                segar=segar,
                params=params_dict,
                params_hash=params_hash,
                source_fingerprint=curr_fingerprint,
                http_status=status_code,
                duration_ms=duration_ms,
                error_code=error_code,
                created_by=actor_user_id,
            )
        except Exception as exc:
            logger.warning("Gagal memanggil record_run pada error response analisa: %s", exc)

        try:
            record_audit(
                db,
                action=RUN_ANALYSIS,
                user_id=actor_user_id,
                target_resource=f"document:{document_id}",
                detail={
                    "mode_diminta": req_mode.value,
                    "mode_dipakai": None,
                    "sumber": "gagal",
                    "http_status": status_code,
                    "run_id": run_id,
                },
                ip_address=client_ip,
                commit=True,
            )
        except Exception as exc:
            logger.warning("Gagal mencatat audit RUN_ANALYSIS: %s", exc)

        return JSONResponse(status_code=status_code, content=data)

    # 5. Tentukan mode yang benar-benar dipakai dan simpan ke cache jika diaktifkan
    actual_mode_str = data.get("mode_dipakai") if isinstance(data, dict) else None
    if not actual_mode_str:
        actual_mode_str = "deterministik"
    save_mode = ModeAnalisa.ai if actual_mode_str == "ai" else ModeAnalisa.deterministik

    saved_row = None
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

    # 6. Catat riwayat eksekusi (sumber=ml)
    run_id = None
    try:
        run_id = record_run(
            db=db,
            document_id=document_id,
            kind=JenisAnalisa.analisa,
            mode_diminta=req_mode,
            mode_dipakai=save_mode,
            sumber="ml",
            segar=segar,
            params=params_dict,
            params_hash=params_hash,
            source_fingerprint=curr_fingerprint,
            http_status=200,
            duration_ms=duration_ms,
            ml_version=data.get("versi") if isinstance(data, dict) else None,
            result_raw=data if isinstance(data, dict) else None,
            created_by=actor_user_id,
        )
    except Exception as exc:
        logger.warning("Gagal memanggil record_run analisa: %s", exc)

    # 7. Catat audit RUN_ANALYSIS
    try:
        record_audit(
            db,
            action=RUN_ANALYSIS,
            user_id=actor_user_id,
            target_resource=f"document:{document_id}",
            detail={
                "mode_diminta": req_mode.value,
                "mode_dipakai": save_mode.value,
                "sumber": "ml",
                "http_status": 200,
                "run_id": run_id,
            },
            ip_address=client_ip,
            commit=True,
        )
    except Exception as exc:
        logger.warning("Gagal mencatat audit RUN_ANALYSIS: %s", exc)

    # 8. Saring rujukan dan kembalikan dengan metadata cache
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
            "run_id": run_id,
        }
    return filtered_data


@router.get("/analisa/{document_id}/klausul", summary="Pencarian Klausul Relevan")
async def get_ml_analisa_klausul(
    document_id: int,
    kebutuhan: str = Query(..., min_length=3),
    k: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_ml_client),
    current_user=Depends(perlu_izin(Izin.ANALISA_JALANKAN)),
):
    """Pasal yang relevan dengan kebutuhan pengguna dalam dokumen."""
    check_document_access(db, document_id, user=current_user)
    params = {"kebutuhan": kebutuhan, "k": k}
    status_code, data = await forward_ml_request(client, "GET", f"/analisa/{document_id}/klausul", params=params)
    if status_code >= 400:
        return JSONResponse(status_code=status_code, content=data)

    allowed_ids = allowed_document_ids(db, user=current_user)
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
    current_user=Depends(perlu_izin(Izin.ANALISA_JALANKAN)),
):
    """
    Analisa harmonisasi draft terhadap korpus dokumen regulasi.
    Body opsional berisi daftar document_id pembatas korpus (null = seluruh korpus yang diizinkan).
    """
    doc = check_document_access(db, document_id, user=current_user)
    allowed_ids = allowed_document_ids(db, user=current_user)

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
    params_dict = {"mode": "deterministik", "pembanding": forward_body}
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
            run_id = None
            try:
                run_id = record_run(
                    db=db,
                    document_id=document_id,
                    kind=kind,
                    mode_diminta=mode,
                    mode_dipakai=mode,
                    sumber="cache",
                    segar=segar,
                    params=params_dict,
                    params_hash=params_hash,
                    source_fingerprint=curr_fingerprint,
                    http_status=200,
                    duration_ms=0,
                    ml_version=cached.ml_version,
                    result_raw=cached.result,
                    created_by=actor_user_id,
                )
            except Exception as exc:
                logger.warning("Gagal memanggil record_run pada cache hit harmonisasi: %s", exc)

            filtered_data, discarded = saring_rujukan(cached.result, allowed_ids)
            if isinstance(filtered_data, dict):
                filtered_data["disaring_backend"] = discarded
                filtered_data["cache"] = {
                    "hit": True,
                    "dibuat": cached.created_at.isoformat() if cached.created_at else None,
                    "basi": False,
                    "mode_tersimpan": "deterministik",
                    "run_id": run_id,
                }
            try:
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
                        "mode_dipakai": "deterministik",
                        "sumber": "cache",
                        "http_status": 200,
                        "run_id": run_id,
                    },
                    ip_address=client_ip,
                    commit=True,
                )
            except Exception as exc:
                logger.warning("Gagal mencatat audit RUN_HARMONIZATION: %s", exc)

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
        duration_ms = int((time.perf_counter() - start_time) * 1000)
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
                run_id = None
                try:
                    run_id = record_run(
                        db=db,
                        document_id=document_id,
                        kind=kind,
                        mode_diminta=mode,
                        mode_dipakai=mode,
                        sumber="cache_basi",
                        segar=segar,
                        params=params_dict,
                        params_hash=params_hash,
                        source_fingerprint=curr_fingerprint,
                        http_status=200,
                        duration_ms=duration_ms,
                        ml_version=fallback.ml_version,
                        result_raw=fallback.result,
                        created_by=actor_user_id,
                    )
                except Exception as exc:
                    logger.warning("Gagal memanggil record_run pada cache basi harmonisasi: %s", exc)

                filtered_data, discarded = saring_rujukan(fallback.result, allowed_ids)
                if isinstance(filtered_data, dict):
                    filtered_data["disaring_backend"] = discarded
                    filtered_data["cache"] = {
                        "hit": True,
                        "dibuat": fallback.created_at.isoformat() if fallback.created_at else None,
                        "basi": True,
                        "mode_tersimpan": "deterministik",
                        "run_id": run_id,
                    }
                try:
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
                            "mode_dipakai": "deterministik",
                            "sumber": "cache_basi",
                            "http_status": 200,
                            "run_id": run_id,
                        },
                        ip_address=client_ip,
                        commit=True,
                    )
                except Exception as exc:
                    logger.warning("Gagal mencatat audit RUN_HARMONIZATION: %s", exc)

                return filtered_data

        # Tidak ada fallback, catat run gagal & audit sebelum melempar exception
        error_code = ml_exc.detail.get("code") if isinstance(ml_exc.detail, dict) else None
        run_id = None
        try:
            run_id = record_run(
                db=db,
                document_id=document_id,
                kind=kind,
                mode_diminta=mode,
                mode_dipakai=None,
                sumber="gagal",
                segar=segar,
                params=params_dict,
                params_hash=params_hash,
                source_fingerprint=curr_fingerprint,
                http_status=ml_exc.status_code,
                duration_ms=duration_ms,
                error_code=error_code,
                created_by=actor_user_id,
            )
        except Exception as exc:
            logger.warning("Gagal memanggil record_run pada kegagalan harmonisasi: %s", exc)

        try:
            record_audit(
                db,
                action=RUN_HARMONIZATION,
                user_id=actor_user_id,
                target_resource=f"document:{document_id}",
                detail={
                    "document_id": document_id,
                    "jumlah_temuan": 0,
                    "jumlah_korpus": len(forward_body),
                    "korpus_dibatasi_pengguna": body is not None,
                    "cache_hit": False,
                    "mode_dipakai": None,
                    "sumber": "gagal",
                    "http_status": ml_exc.status_code,
                    "run_id": run_id,
                },
                ip_address=client_ip,
                commit=True,
            )
        except Exception as exc:
            logger.warning("Gagal mencatat audit RUN_HARMONIZATION: %s", exc)

        raise ml_exc

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    # 4. Tangani respons error HTTP lain dari ML (status_code >= 400)
    if status_code is not None and status_code >= 400:
        error_code = None
        if isinstance(data, dict):
            error_code = data.get("code") or (data.get("detail") if isinstance(data.get("detail"), str) else None)
        run_id = None
        try:
            run_id = record_run(
                db=db,
                document_id=document_id,
                kind=kind,
                mode_diminta=mode,
                mode_dipakai=None,
                sumber="gagal",
                segar=segar,
                params=params_dict,
                params_hash=params_hash,
                source_fingerprint=curr_fingerprint,
                http_status=status_code,
                duration_ms=duration_ms,
                error_code=error_code,
                created_by=actor_user_id,
            )
        except Exception as exc:
            logger.warning("Gagal memanggil record_run pada error response harmonisasi: %s", exc)

        try:
            record_audit(
                db,
                action=RUN_HARMONIZATION,
                user_id=actor_user_id,
                target_resource=f"document:{document_id}",
                detail={
                    "document_id": document_id,
                    "jumlah_temuan": 0,
                    "jumlah_korpus": len(forward_body),
                    "korpus_dibatasi_pengguna": body is not None,
                    "cache_hit": False,
                    "mode_dipakai": None,
                    "sumber": "gagal",
                    "http_status": status_code,
                    "run_id": run_id,
                },
                ip_address=client_ip,
                commit=True,
            )
        except Exception as exc:
            logger.warning("Gagal mencatat audit RUN_HARMONIZATION: %s", exc)

        return JSONResponse(status_code=status_code, content=data)

    # 5. Simpan ke cache jika diaktifkan
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

    # 6. Catat riwayat eksekusi (sumber=ml)
    run_id = None
    try:
        run_id = record_run(
            db=db,
            document_id=document_id,
            kind=kind,
            mode_diminta=mode,
            mode_dipakai=mode,
            sumber="ml",
            segar=segar,
            params=params_dict,
            params_hash=params_hash,
            source_fingerprint=curr_fingerprint,
            http_status=200,
            duration_ms=duration_ms,
            ml_version=data.get("versi") if isinstance(data, dict) else None,
            result_raw=data if isinstance(data, dict) else None,
            created_by=actor_user_id,
        )
    except Exception as exc:
        logger.warning("Gagal memanggil record_run harmonisasi: %s", exc)

    # 7. Saring rujukan dan catat audit
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
            "run_id": run_id,
        }

    try:
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
                "mode_dipakai": "deterministik",
                "sumber": "ml",
                "http_status": 200,
                "run_id": run_id,
            },
            ip_address=client_ip,
            commit=True,
        )
    except Exception as exc:
        logger.warning("Gagal mencatat audit RUN_HARMONIZATION: %s", exc)

    return filtered_data


@router.get("/cari", summary="Pencarian Semantik Regulasi")
async def get_ml_cari(
    q: str = Query(..., min_length=2),
    metode: Optional[Literal["lexical", "lsa", "semantic", "hybrid", "pgvector"]] = None,
    k: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_ml_client),
    current_user=Depends(perlu_izin(Izin.KB_BACA)),
):
    """Pencarian pasal semantik/leksikal dengan penyesuaian metode default."""
    chosen_method = metode or settings.ml_default_search_method
    params = {"q": q, "metode": chosen_method, "k": k}

    status_code, data = await forward_ml_request(client, "GET", "/cari", params=params)
    if status_code >= 400:
        return JSONResponse(status_code=status_code, content=data)

    allowed_ids = allowed_document_ids(db, user=current_user)
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
    current_user=Depends(perlu_izin(Izin.KB_BACA)),
):
    """Pencarian pasal termirip di korpus backend untuk sepotong teks."""
    from app.core.permissions import boleh_baca_nonpublik

    if not boleh_baca_nonpublik(current_user):
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

    allowed_ids = allowed_document_ids(db, user=current_user)
    filtered_data, discarded = saring_rujukan(data, allowed_ids)
    if isinstance(filtered_data, dict):
        filtered_data["disaring_backend"] = discarded
    return filtered_data
