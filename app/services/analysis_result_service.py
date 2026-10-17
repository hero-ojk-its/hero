"""
app/services/analysis_result_service.py
Layanan penyimpanan, caching, dan perbandingan hasil analisa ML (Langkah 20, US-05 #49).
"""
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.analysis_result import AnalysisResult
from app.models.document import Document
from app.models.enums import JenisAnalisa, ModeAnalisa

logger = logging.getLogger("hero")


def get_document_fingerprint(doc: Document) -> str:
    """
    Menghasilkan sidik jari dokumen: '{file_hash}:{extracted_at ISO atau '-'}' saat hasil dibuat.
    Bila dokumen diekstraksi ulang (extracted_at berubah) atau berkas berubah (file_hash berubah),
    sidik jari akan berbeda sehingga cache lama dianggap basi.
    """
    file_hash_str = doc.file_hash or "-"
    extracted_at_str = doc.extracted_at.isoformat() if doc.extracted_at else "-"
    return f"{file_hash_str}:{extracted_at_str}"


def compute_params_hash(kind: JenisAnalisa, extra: Any = None) -> str:
    """
    Menghitung hash parameter penentu hasil analisa:
    - kind=analisa: sha256("analisa") karena mode disimpan terpisah di kolom tabel.
    - kind=harmonisasi: sha256(json.dumps(sorted(forward_body))) daftar pembanding korpus yang diizinkan.
    """
    if kind == JenisAnalisa.analisa:
        return hashlib.sha256(b"analisa").hexdigest()
    elif kind == JenisAnalisa.harmonisasi:
        body_list = sorted(list(extra)) if extra is not None else []
        encoded = json.dumps(body_list).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
    return hashlib.sha256(str(kind.value if hasattr(kind, "value") else kind).encode("utf-8")).hexdigest()


def get_cached_result(
    db: Session,
    document_id: int,
    kind: JenisAnalisa,
    mode: ModeAnalisa,
    params_hash: str,
    expected_fingerprint: Optional[str] = None,
) -> Optional[AnalysisResult]:
    """
    Mencari hasil analisa tersimpan di database:
    - Bila expected_fingerprint diberikan, hanya mengembalikan hasil bila fingerprint cocok (cache hit segar).
    - Bila expected_fingerprint None, mengembalikan hasil tersimpan terbaru apa pun fingerprint-nya (fallback saat ML mati).
    """
    query = (
        db.query(AnalysisResult)
        .filter(
            AnalysisResult.document_id == document_id,
            AnalysisResult.kind == kind,
            AnalysisResult.mode == mode,
            AnalysisResult.params_hash == params_hash,
        )
    )
    if expected_fingerprint is not None:
        query = query.filter(AnalysisResult.source_fingerprint == expected_fingerprint)

    return query.order_by(AnalysisResult.created_at.desc()).first()


def save_analysis_result(
    db: Session,
    document_id: int,
    kind: JenisAnalisa,
    mode: ModeAnalisa,
    params_hash: str,
    source_fingerprint: str,
    raw_result: dict,
    ml_version: Optional[str] = None,
    duration_ms: Optional[int] = None,
    user_id: Optional[int] = None,
) -> AnalysisResult:
    """
    Menyimpan atau memperbarui (upsert) hasil mentah layanan ML.
    Batasan unik: (document_id, kind, mode, params_hash).
    """
    existing = (
        db.query(AnalysisResult)
        .filter(
            AnalysisResult.document_id == document_id,
            AnalysisResult.kind == kind,
            AnalysisResult.mode == mode,
            AnalysisResult.params_hash == params_hash,
        )
        .first()
    )

    now_utc = datetime.now(timezone.utc)
    if existing:
        existing.source_fingerprint = source_fingerprint
        existing.result = raw_result
        existing.ml_version = ml_version
        existing.duration_ms = duration_ms
        existing.created_at = now_utc
        existing.created_by = user_id
        db.commit()
        db.refresh(existing)
        logger.info(
            "Cache analisa diperbarui: doc_id=%s kind=%s mode=%s",
            document_id,
            kind.value,
            mode.value,
        )
        return existing
    else:
        new_row = AnalysisResult(
            document_id=document_id,
            kind=kind,
            mode=mode,
            params_hash=params_hash,
            source_fingerprint=source_fingerprint,
            result=raw_result,
            ml_version=ml_version,
            duration_ms=duration_ms,
            created_at=now_utc,
            created_by=user_id,
        )
        db.add(new_row)
        db.commit()
        db.refresh(new_row)
        logger.info(
            "Cache analisa baru disimpan: doc_id=%s kind=%s mode=%s",
            document_id,
            kind.value,
            mode.value,
        )
        return new_row


def get_analysis_comparison(
    db: Session,
    doc: Document,
    allowed_ids: set[int],
    saring_func: Any,
) -> dict:
    """
    Mengambil data perbandingan hasil analisa deterministik vs AI untuk sebuah dokumen.
    Data hanya dibaca dari penyimpanan lokal (tanpa memanggil ML).
    """
    params_hash = compute_params_hash(JenisAnalisa.analisa)
    curr_fingerprint = get_document_fingerprint(doc)

    row_det = (
        db.query(AnalysisResult)
        .filter(
            AnalysisResult.document_id == doc.id,
            AnalysisResult.kind == JenisAnalisa.analisa,
            AnalysisResult.mode == ModeAnalisa.deterministik,
            AnalysisResult.params_hash == params_hash,
        )
        .order_by(AnalysisResult.created_at.desc())
        .first()
    )

    row_ai = (
        db.query(AnalysisResult)
        .filter(
            AnalysisResult.document_id == doc.id,
            AnalysisResult.kind == JenisAnalisa.analisa,
            AnalysisResult.mode == ModeAnalisa.ai,
            AnalysisResult.params_hash == params_hash,
        )
        .order_by(AnalysisResult.created_at.desc())
        .first()
    )

    def _format_entry(row: Optional[AnalysisResult]) -> Optional[dict]:
        if not row:
            return None
        is_basi = row.source_fingerprint != curr_fingerprint
        filtered_res, discarded = saring_func(row.result, allowed_ids)
        if isinstance(filtered_res, dict):
            filtered_res["disaring_backend"] = discarded
        return {
            "dibuat": row.created_at.isoformat() if row.created_at else None,
            "basi": is_basi,
            "ml_version": row.ml_version,
            "hasil": filtered_res,
        }

    return {
        "document_id": doc.id,
        "deterministik": _format_entry(row_det),
        "ai": _format_entry(row_ai),
        "catatan": "Draft / Rekomendasi — hasil AI tidak menggantikan hasil deterministik; bandingkan keduanya.",
    }
