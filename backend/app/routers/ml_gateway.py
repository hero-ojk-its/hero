"""
app/routers/ml_gateway.py
Gerbang terpadu untuk layanan Analisa dan Harmonisasi Regulasi (ML Layer).

Tanggung jawab gerbang:
1. Memvalidasi hak akses dokumen sebelum meneruskan ke ML (proteksi dokumen nonaktif & dokumen non-publik).
2. Menyaring secara rekursif hasil analisa, temuan, referensi, dan korpus harmonisasi agar data dokumen yang tidak diizinkan tidak bocor.
3. Menyeragamkan kode dan format galat (503 bila belum dikonfigurasi / tidak tersedia, 504 saat timeout, 422 bila pembanding kosong).
4. Mencatat jejak audit ringkas RUN_HARMONIZATION saat harmonisasi dijalankan.
"""
import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from app.responses import Utf8JSONResponse as JSONResponse
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
from app.schemas.harmonisasi import HarmonisasiResponse

logger = logging.getLogger("hero")

router = APIRouter(tags=["Analisa (ML)"])

SENSITIVE_REF_KEYS = {"kutipan", "pdf", "halaman", "pasal", "pasal_mirip", "skor"}


async def get_ml_client() -> AsyncIterator[httpx.AsyncClient]:
    """Dependency klien HTTP untuk komunikasi dengan layanan analisa ML."""
    baca = settings.ml_timeout_seconds if settings.ml_timeout_seconds > 0 else None
    timeout = httpx.Timeout(baca, connect=settings.ml_connect_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
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
    rincian: Optional[dict[str, int]] = None,
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
    if rincian is None:
        rincian = {"temuan": 0, "rujukan": 0, "alternatif": 0, "lainnya": 0}

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
                    cat = "rujukan" if k in ("rujukan", "referensi") else ("alternatif" if k == "alternatif" else ("temuan" if k in ("temuan", "pembanding") else "lainnya"))
                    rincian[cat] = rincian.get(cat, 0) + 1
                    rec_val, rec_count = saring_rujukan(v_copy, allowed_ids, parent_key=k, rincian=rincian)
                    total_dibuang += rec_count
                    new_dict[k] = rec_val
                    continue

            filtered_v, count_v = saring_rujukan(v, allowed_ids, parent_key=k, rincian=rincian)
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
                        rincian["rujukan"] = rincian.get("rujukan", 0) + 1
                        rec_item, rec_count = saring_rujukan(item_copy, allowed_ids, parent_key="rujukan_item", rincian=rincian)
                        total_dibuang += rec_count
                        new_list.append(rec_item)
                    else:
                        rec_item, rec_count = saring_rujukan(item, allowed_ids, parent_key="rujukan_item", rincian=rincian)
                        total_dibuang += rec_count
                        new_list.append(rec_item)
                    continue

                # Aturan 1: Elemen list dengan document_id int yang tidak diizinkan -> DIBUANG
                doc_id = item.get("document_id")
                if isinstance(doc_id, int) and doc_id not in allowed_ids:
                    total_dibuang += 1
                    cat = "temuan" if parent_key in ("temuan", "temuan_item") else ("rujukan" if parent_key in ("rujukan", "rujukan_item") else ("alternatif" if parent_key in ("alternatif", "alternatif_item") else "lainnya"))
                    rincian[cat] = rincian.get(cat, 0) + 1
                    continue

                # Aturan 2: Elemen list dengan pembanding.document_id tidak diizinkan -> DIBUANG
                pembanding = item.get("pembanding")
                if isinstance(pembanding, dict):
                    p_doc_id = pembanding.get("document_id")
                    if isinstance(p_doc_id, int) and p_doc_id not in allowed_ids:
                        total_dibuang += 1
                        rincian["temuan"] = rincian.get("temuan", 0) + 1
                        continue

                rec_item, rec_count = saring_rujukan(item, allowed_ids, parent_key=parent_key, rincian=rincian)
                total_dibuang += rec_count
                new_list.append(rec_item)
            else:
                rec_item, rec_count = saring_rujukan(item, allowed_ids, parent_key=parent_key, rincian=rincian)
                total_dibuang += rec_count
                new_list.append(rec_item)

        return new_list, total_dibuang

    else:
        return obj, 0


def saring_rujukan_lengkap(
    obj: Any,
    allowed_ids: set[int],
) -> tuple[Any, int, dict[str, int]]:
    """Versi saring_rujukan yang mengembalikan tuple (filtered_obj, discarded, rincian)."""
    rincian = {"temuan": 0, "rujukan": 0, "alternatif": 0, "lainnya": 0}
    filtered_obj, discarded = saring_rujukan(obj, allowed_ids, rincian=rincian)
    return filtered_obj, discarded, rincian


def sesuaikan_ringkasan_harmonisasi(
    filtered_data: Any,
    discarded: int,
    rincian: dict[str, int],
) -> Any:
    """
    Menyesuaikan disaring_backend, disaring_rincian, dan menghitung ulang
    ringkasan.per_jenis berdasarkan temuan yang tersisa setelah disaring.
    """
    if isinstance(filtered_data, dict):
        filtered_data["disaring_backend"] = discarded
        filtered_data["disaring_rincian"] = rincian

        # Hitung ulang per_jenis HANYA bila ada temuan yang disaring
        if rincian.get("temuan", 0) > 0:
            ringkasan = filtered_data.get("ringkasan")
            if isinstance(ringkasan, dict) and "per_jenis" in ringkasan and isinstance(ringkasan["per_jenis"], dict):
                per_jenis_asli = ringkasan["per_jenis"]
                per_jenis_baru = {k: 0 for k in per_jenis_asli.keys()}
                temuan_list = filtered_data.get("temuan") or []
                if isinstance(temuan_list, list):
                    for t in temuan_list:
                        if isinstance(t, dict):
                            jenis = t.get("jenis")
                            if jenis:
                                per_jenis_baru[jenis] = per_jenis_baru.get(jenis, 0) + 1
                ringkasan["per_jenis"] = per_jenis_baru
    return filtered_data


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
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
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
    """Ringkasan terstruktur dan poin kunci berbasis pasal.

    Menunggu penuh dalam satu permintaan — cocok untuk mode deterministik
    (cepat). Untuk mode AI gunakan ``POST .../mulai`` + ``GET .../analisa-job/{id}``
    (lihat di bawah): panggilan Gemini bisa lebih lama dari batas proxy
    Cloudflare (~100 d) di depan domain publik, dan permintaan sinkron ini
    akan diputus oleh Cloudflare sebelum model selesai menjawab.
    """
    return await _jalankan_analisa(document_id, request, mode, segar, db, client, current_user)


async def _jalankan_analisa(
    document_id: int,
    request: Request,
    mode: Optional[Literal["deterministik", "ai"]],
    segar: bool,
    db: Session,
    client: httpx.AsyncClient,
    current_user,
):
    """Logika analisa (cache, panggil ML, audit, saring) — dipakai oleh endpoint sinkron dan job latar belakang."""
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


class _AnalisaJobStore:
    """Antrian job analisa di memori — hilang saat restart backend (dapat dipicu ulang oleh pengguna).

    Dibutuhkan karena Cloudflare memutus proxy HTTP sinkron pada ~100 d; mode
    AI yang bisa lebih lama dari itu harus berjalan di latar belakang dan
    dipoll, bukan ditunggu dalam satu permintaan.
    """

    _TTL_DETIK = 3600  # job yang sudah selesai/gagal dibuang setelah 1 jam agar memori tidak bocor

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        # Menyimpan referensi kuat ke task yang sedang berjalan agar tidak dibersihkan garbage collector
        # (Dokumentasi Python asyncio: task tanpa referensi kuat bisa di-GC sebelum selesai).
        self._tasks: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()

    async def mulai(
        self,
        coro_fn,
        document_id: int,
        mode: str,
        pemilik_id: Optional[int] = None,
    ) -> str:
        job_id = uuid.uuid4().hex
        async with self._lock:
            self._jobs[job_id] = {
                "status": "berjalan",
                "mulai": time.time(),
                "hasil": None,
                "error": None,
                "document_id": document_id,
                "mode": mode,
                "pemilik_id": pemilik_id,
            }

        async def runner() -> None:
            try:
                # Bungkus eksekusi dengan batas waktu maksimal jika ml_job_timeout_seconds > 0
                if settings.ml_job_timeout_seconds > 0:
                    coro = asyncio.wait_for(
                        coro_fn(),
                        timeout=settings.ml_job_timeout_seconds + 60.0,
                    )
                else:
                    coro = coro_fn()
                hasil = await coro
                if isinstance(hasil, JSONResponse) and hasil.status_code >= 400:
                    import json
                    body_content = json.loads(hasil.body.decode("utf-8")) if hasil.body else None
                    async with self._lock:
                        self._jobs[job_id]["status"] = "gagal"
                        self._jobs[job_id]["error"] = {
                            "status_code": hasil.status_code,
                            "detail": body_content,
                        }
                    return
                async with self._lock:
                    self._jobs[job_id]["status"] = "selesai"
                    self._jobs[job_id]["hasil"] = hasil
            except asyncio.TimeoutError:
                logger.warning("Job analisa %s melebihi batas waktu total", job_id)
                async with self._lock:
                    self._jobs[job_id]["status"] = "gagal"
                    self._jobs[job_id]["error"] = {
                        "status_code": status.HTTP_504_GATEWAY_TIMEOUT,
                        "detail": {
                            "code": "analisa_terlalu_lama",
                            "message": "Analisa melebihi batas waktu maksimal.",
                        },
                    }
            except HTTPException as exc:
                async with self._lock:
                    self._jobs[job_id]["status"] = "gagal"
                    self._jobs[job_id]["error"] = {"status_code": exc.status_code, "detail": exc.detail}
            except Exception as exc:  # noqa: BLE001
                logger.exception("Job analisa %s gagal tak terduga", job_id)
                async with self._lock:
                    self._jobs[job_id]["status"] = "gagal"
                    self._jobs[job_id]["error"] = {"status_code": 500, "detail": str(exc)}

        task = asyncio.create_task(runner())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        await self._bersihkan()
        return job_id

    async def get(self, job_id: str) -> Optional[dict[str, Any]]:
        await self._bersihkan()
        async with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    async def _bersihkan(self) -> None:
        now = time.time()
        cutoff_selesai = now - self._TTL_DETIK
        job_timeout = settings.ml_job_timeout_seconds
        cutoff_berjalan = (job_timeout + 120.0) if job_timeout > 0 else 0

        async with self._lock:
            # Job berjalan yang melebihi batas waktu maksimal ditandai gagal
            if cutoff_berjalan > 0:
                for j in self._jobs.values():
                    if j.get("status") == "berjalan" and (now - j.get("mulai", now)) > cutoff_berjalan:
                        j["status"] = "gagal"
                        j["error"] = {
                            "status_code": status.HTTP_504_GATEWAY_TIMEOUT,
                            "detail": {
                                "code": "analisa_terlalu_lama",
                                "message": "Analisa melebihi batas waktu maksimal.",
                            },
                        }
            # Job selesai/gagal yang melebihi TTL dibersihkan
            stale = [
                jid for jid, j in self._jobs.items()
                if j.get("status") != "berjalan" and j.get("mulai", now) < cutoff_selesai
            ]
            for jid in stale:
                del self._jobs[jid]


_analisa_jobs = _AnalisaJobStore()


def make_job_ml_client(timeout: httpx.Timeout) -> httpx.AsyncClient:
    """Membuat AsyncClient untuk job latar belakang (dapat di-mock dalam pengujian)."""
    return httpx.AsyncClient(timeout=timeout)


@router.post("/analisa/{document_id}/mulai", summary="Mulai Analisa (job latar belakang)")
async def post_ml_analisa_mulai(
    document_id: int,
    request: Request,
    mode: Optional[Literal["deterministik", "ai"]] = Query("ai"),
    segar: bool = Query(False, description="Paksa hitung ulang tanpa cache"),
    db: Session = Depends(get_db),
    current_user=Depends(perlu_izin(Izin.ANALISA_JALANKAN)),
):
    """Mulai analisa di latar belakang; kembalikan ``job_id`` untuk dipoll via
    ``GET /analisa-job/{job_id}``. Dipakai untuk mode AI agar tidak kena batas
    proxy Cloudflare (~100 d) seperti endpoint sinkron di atas."""
    # 1. Cek konfigurasi layanan analisa
    if not settings.ml_service_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "layanan_analisa_belum_dikonfigurasi",
                "message": "Layanan analisa belum dikonfigurasi (ML_SERVICE_URL kosong).",
            },
        )

    # 2. Cek hak akses dokumen (404 bila tidak ditemukan / nonaktif, 403 bila non-publik tanpa izin)
    check_document_access(db, document_id, user=current_user)

    from app.database import SessionLocal

    mode_str = mode if mode else "ai"
    pemilik_id = getattr(current_user, "id", None)

    async def jalankan() -> Any:
        baca = settings.ml_job_timeout_seconds if settings.ml_job_timeout_seconds > 0 else None
        timeout = httpx.Timeout(baca, connect=settings.ml_connect_timeout_seconds)
        db2 = SessionLocal()
        try:
            async with make_job_ml_client(timeout) as client2:
                return await _jalankan_analisa(document_id, request, mode, segar, db2, client2, current_user)
        finally:
            db2.close()

    job_id = await _analisa_jobs.mulai(
        jalankan,
        document_id=document_id,
        mode=mode_str,
        pemilik_id=pemilik_id,
    )
    return {"job_id": job_id, "status": "berjalan"}


@router.get("/analisa-job/{job_id}", summary="Status Job Analisa")
async def get_ml_analisa_job(
    job_id: str,
    current_user=Depends(perlu_izin(Izin.ANALISA_JALANKAN)),
):
    """Status job yang dimulai lewat ``POST /analisa/{document_id}/mulai``."""
    job = await _analisa_jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "job_tidak_ditemukan",
                "message": f"Job {job_id} tidak ditemukan (sudah dibersihkan setelah 1 jam, atau id salah).",
            },
        )

    # Pemeriksaan kepemilikan job saat auth aktif
    if settings.auth_enabled:
        user_id = getattr(current_user, "id", None)
        if job.get("pemilik_id") != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "job_tidak_ditemukan",
                    "message": f"Job {job_id} tidak ditemukan (sudah dibersihkan setelah 1 jam, atau id salah).",
                },
            )

    out: dict[str, Any] = {
        "job_id": job_id,
        "status": job["status"],
        "document_id": job.get("document_id"),
        "mode": job.get("mode"),
        "berjalan_detik": round(time.time() - job["mulai"], 1),
    }
    if job["status"] == "selesai":
        out["hasil"] = job["hasil"]
    elif job["status"] == "gagal":
        out["error"] = job["error"]
    return out


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


@router.post(
    "/harmonisasi/{document_id}",
    response_model=HarmonisasiResponse,
    response_model_exclude_unset=True,
    summary="Harmonisasi Draft Regulasi",
)
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

            filtered_data, discarded, rincian = saring_rujukan_lengkap(cached.result, allowed_ids)
            sesuaikan_ringkasan_harmonisasi(filtered_data, discarded, rincian)
            if isinstance(filtered_data, dict):
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

                filtered_data, discarded, rincian = saring_rujukan_lengkap(fallback.result, allowed_ids)
                sesuaikan_ringkasan_harmonisasi(filtered_data, discarded, rincian)
                if isinstance(filtered_data, dict):
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
    filtered_data, discarded, rincian = saring_rujukan_lengkap(data, allowed_ids)
    sesuaikan_ringkasan_harmonisasi(filtered_data, discarded, rincian)
    if isinstance(filtered_data, dict):
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
