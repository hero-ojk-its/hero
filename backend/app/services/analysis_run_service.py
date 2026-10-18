"""
app/services/analysis_run_service.py
Layanan untuk mencatat dan membaca riwayat eksekusi analisa & harmonisasi regulasi (Langkah 21, US-10 #56, US-08 #34).
"""
import copy
import hashlib
import json
import logging
from typing import Any, Callable, Dict, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun
from app.models.document import Document
from app.models.enums import JenisAnalisa, ModeAnalisa
from app.models.user import User
from app.services.analysis_result_service import get_document_fingerprint

logger = logging.getLogger("hero")


def compute_result_hash(result_dict: Optional[Dict[str, Any]]) -> Optional[str]:
    """Menghitung SHA-256 dari output mentah ML dalam format canonical JSON."""
    if not result_dict:
        return None
    canonical = json.dumps(result_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def extract_ringkasan_output(
    kind: JenisAnalisa,
    result_raw: Optional[Dict[str, Any]],
    duration_ms: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Mengekstrak ringkasan output kecil untuk daftar riwayat tanpa error bila field tidak ada."""
    if not result_raw or not isinstance(result_raw, dict):
        return None

    ro: Dict[str, Any] = {}
    if kind == JenisAnalisa.analisa:
        metrik = result_raw.get("metrik")
        if isinstance(metrik, dict):
            if "jumlah_poin" in metrik:
                ro["jumlah_poin"] = metrik.get("jumlah_poin")
            if "kata_ringkasan" in metrik:
                ro["kata_ringkasan"] = metrik.get("kata_ringkasan")
            if "waktu_ms" in metrik:
                ro["waktu_ms"] = metrik.get("waktu_ms")

        # Fallback jika tidak ada objek metrik
        if "jumlah_poin" not in ro and "poin_kunci" in result_raw:
            poin = result_raw.get("poin_kunci")
            if isinstance(poin, list):
                ro["jumlah_poin"] = len(poin)
        if "kata_ringkasan" not in ro and "ringkasan" in result_raw:
            ringk = result_raw.get("ringkasan")
            if isinstance(ringk, str):
                ro["kata_ringkasan"] = len(ringk.split())
        if "waktu_ms" not in ro and duration_ms is not None:
            ro["waktu_ms"] = duration_ms

    elif kind == JenisAnalisa.harmonisasi:
        if "jumlah_temuan" in result_raw:
            ro["jumlah_temuan"] = result_raw.get("jumlah_temuan")
        elif "temuan" in result_raw and isinstance(result_raw.get("temuan"), list):
            ro["jumlah_temuan"] = len(result_raw["temuan"])
        elif "analisa_harmonisasi" in result_raw and isinstance(result_raw.get("analisa_harmonisasi"), list):
            ro["jumlah_temuan"] = len(result_raw["analisa_harmonisasi"])

    return ro if ro else None


def record_run(
    db: Session,
    document_id: int,
    kind: JenisAnalisa,
    mode_diminta: ModeAnalisa,
    mode_dipakai: Optional[ModeAnalisa],
    sumber: str,  # 'ml' | 'cache' | 'cache_basi' | 'gagal'
    segar: bool,
    params: Dict[str, Any],
    params_hash: str,
    source_fingerprint: str,
    http_status: int,
    duration_ms: Optional[int] = None,
    ml_version: Optional[str] = None,
    result_raw: Optional[Dict[str, Any]] = None,
    error_code: Optional[str] = None,
    created_by: Optional[int] = None,
) -> Optional[int]:
    """
    Mencatat satu eksekusi analisa ke tabel analysis_runs (append-only).
    Keamanan transaksi terjamin: jika pencatatan gagal, tidak akan menggagalkan jawaban ke klien.
    """
    try:
        res_hash = compute_result_hash(result_raw)
        # Hanya simpan output mentah lengkap bila sumber == 'ml'
        stored_result = copy.deepcopy(result_raw) if (sumber == "ml" and result_raw) else None
        ringkasan = extract_ringkasan_output(kind, result_raw, duration_ms)

        run = AnalysisRun(
            document_id=document_id,
            kind=kind,
            mode_diminta=mode_diminta,
            mode_dipakai=mode_dipakai,
            sumber=sumber,
            segar=segar,
            params=params,
            params_hash=params_hash,
            source_fingerprint=source_fingerprint,
            ml_version=ml_version,
            result_hash=res_hash,
            result=stored_result,
            ringkasan_output=ringkasan,
            http_status=http_status,
            error_code=error_code,
            duration_ms=duration_ms,
            created_by=created_by,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run.id
    except Exception as exc:
        db.rollback()
        logger.warning(
            "Gagal mencatat riwayat eksekusi analysis_run untuk dokumen id=%s: %s",
            document_id,
            exc,
            exc_info=True,
        )
        return None


def get_analysis_runs_list(
    db: Session,
    doc: Document,
    kind: Optional[str] = None,
    mode: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
) -> Dict[str, Any]:
    """Mengembalikan daftar riwayat eksekusi analisa untuk dokumen tertentu."""
    query = db.query(AnalysisRun).filter(AnalysisRun.document_id == doc.id)

    if kind:
        query = query.filter(AnalysisRun.kind == kind)
    if mode:
        query = query.filter(AnalysisRun.mode_dipakai == mode)

    total = query.count()
    runs = (
        query.order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    current_fingerprint = get_document_fingerprint(doc)

    # Dapatkan mapping username pembuat
    user_ids = {r.created_by for r in runs if r.created_by}
    user_map = {}
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        user_map = {u.id: u.username for u in users}

    items = []
    for r in runs:
        items.append({
            "run_id": r.id,
            "kind": r.kind.value if hasattr(r.kind, "value") else str(r.kind),
            "dibuat": r.created_at.isoformat() if r.created_at else None,
            "oleh": user_map.get(r.created_by),
            "mode_diminta": r.mode_diminta.value if hasattr(r.mode_diminta, "value") else str(r.mode_diminta),
            "mode_dipakai": (
                r.mode_dipakai.value
                if (r.mode_dipakai and hasattr(r.mode_dipakai, "value"))
                else (str(r.mode_dipakai) if r.mode_dipakai else None)
            ),
            "sumber": r.sumber,
            "segar": r.segar,
            "http_status": r.http_status,
            "error_code": r.error_code,
            "ml_version": r.ml_version,
            "params": r.params,
            "result_hash": r.result_hash,
            "ringkasan_output": r.ringkasan_output,
            "duration_ms": r.duration_ms,
            "fingerprint_sama_dengan_sekarang": (r.source_fingerprint == current_fingerprint),
        })

    return {
        "document_id": doc.id,
        "total": total,
        "items": items,
        "catatan": "Draft / Rekomendasi — riwayat eksekusi analisa untuk penelusuran.",
    }


def get_analysis_run_detail(
    db: Session,
    doc: Document,
    run_id: int,
    allowed_ids: Set[int],
    saring_rujukan_fn: Callable[[Dict[str, Any], Set[int]], Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Mengembalikan detail satu eksekusi analisa beserta jawaban mentah tersaring
    dan cara pengulangan eksekusi (cara_ulang).
    """
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.id == run_id, AnalysisRun.document_id == doc.id)
        .first()
    )
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Riwayat eksekusi analisa tidak ditemukan",
        )

    current_fingerprint = get_document_fingerprint(doc)

    # Ambil hasil mentah
    raw_result = None
    if run.result is not None:
        raw_result = run.result
    elif run.result_hash:
        # Cari dari baris eksekusi ml paling awal yang memiliki result_hash sama
        src_run = (
            db.query(AnalysisRun)
            .filter(
                AnalysisRun.document_id == doc.id,
                AnalysisRun.result_hash == run.result_hash,
                AnalysisRun.result.isnot(None),
            )
            .order_by(AnalysisRun.id.asc())
            .first()
        )
        if src_run:
            raw_result = src_run.result

    # Saring rujukan jika ada hasil
    hasil = None
    if raw_result is not None:
        filtered_res, discarded = saring_rujukan_fn(raw_result, allowed_ids)
        if isinstance(filtered_res, dict):
            filtered_res["disaring_backend"] = discarded
        hasil = filtered_res

    # Bangun petunjuk cara_ulang
    mode_diminta_str = run.mode_diminta.value if hasattr(run.mode_diminta, "value") else str(run.mode_diminta)
    if run.kind == JenisAnalisa.analisa:
        cara_ulang = f"GET /api/v1/ml/analisa/{doc.id}?mode={mode_diminta_str}&segar=true"
    else:
        cara_ulang = f"POST /api/v1/ml/harmonisasi/{doc.id}?segar=true"

    username = None
    if run.created_by:
        user = db.query(User).filter(User.id == run.created_by).first()
        username = user.username if user else None

    return {
        "run_id": run.id,
        "kind": run.kind.value if hasattr(run.kind, "value") else str(run.kind),
        "dibuat": run.created_at.isoformat() if run.created_at else None,
        "oleh": username,
        "mode_diminta": mode_diminta_str,
        "mode_dipakai": (
            run.mode_dipakai.value
            if (run.mode_dipakai and hasattr(run.mode_dipakai, "value"))
            else (str(run.mode_dipakai) if run.mode_dipakai else None)
        ),
        "sumber": run.sumber,
        "segar": run.segar,
        "http_status": run.http_status,
        "error_code": run.error_code,
        "ml_version": run.ml_version,
        "params": run.params,
        "result_hash": run.result_hash,
        "ringkasan_output": run.ringkasan_output,
        "duration_ms": run.duration_ms,
        "fingerprint_sama_dengan_sekarang": (run.source_fingerprint == current_fingerprint),
        "hasil": hasil,
        "cara_ulang": cara_ulang,
        "catatan": "Draft / Rekomendasi — riwayat eksekusi analisa untuk penelusuran.",
    }
