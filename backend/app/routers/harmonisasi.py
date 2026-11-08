"""
app/routers/harmonisasi.py
Router untuk tanggapan temuan harmonisasi (#71) dan ekspor laporan harmonisasi (#73).
"""
import csv
from datetime import date, datetime, time, timezone
import io
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import Izin, perlu_izin
from app.database import get_db
from app.models.analysis_result import AnalysisResult
from app.models.enums import JenisAnalisa, PeranDokumen
from app.models.tanggapan_temuan import TanggapanTemuan
from app.routers.ml_gateway import (
    allowed_document_ids,
    check_document_access,
    saring_rujukan_lengkap,
    sesuaikan_ringkasan_harmonisasi,
)
from app.schemas.tanggapan import (
    TanggapanTemuanIn,
    TanggapanTemuanResponse,
)
from app.services.audit_service import (
    EXPORT_HARMONIZATION,
    TANGGAPAN_TEMUAN,
    record_audit,
)
from app.services.harmonisasi_export_service import export_harmonisasi
from app.services.tanggapan_service import (
    kunci_temuan,
    tandai_kunci_temuan,
)

logger = logging.getLogger("hero")

router = APIRouter(tags=["Harmonisasi"])


@router.put(
    "/api/v1/documents/{document_id}/harmonisasi/tanggapan",
    response_model=TanggapanTemuanResponse,
    summary="Beri atau perbarui tanggapan analis terhadap temuan harmonisasi (US-49 #71)",
)
def upsert_tanggapan_temuan(
    document_id: int,
    payload: TanggapanTemuanIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(perlu_izin(Izin.TANGGAPAN_TINJAU)),
):
    """
    [US-49, FR-HRM-11] Menyimpan atau memperbarui penilaian analis (valid / tidak_relevan)
    beserta catatan untuk suatu temuan harmonisasi. Kunci temuan dihitung di server secara stabil.

    Catatan: Dua temuan dengan jenis, pasal_draft, pembanding, dan pasal_pembanding yang sama
    akan berbagi satu tanggapan (disengaja, agar penandaan bertahan saat harmonisasi diulang).
    """
    doc = check_document_access(db, document_id, user=current_user)
    if doc.document_role != PeranDokumen.draft_kajian:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "bukan_draft", "message": "Hanya dokumen draft kajian yang dapat diberi tanggapan harmonisasi."},
        )

    kunci = None
    client_kunci = payload.temuan.get("kunci_temuan")
    if (
        isinstance(client_kunci, str)
        and len(client_kunci) == 32
        and all(c in "0123456789abcdefABCDEF" for c in client_kunci)
    ):
        client_kunci_clean = client_kunci.lower()
        latest_ar = (
            db.query(AnalysisResult)
            .filter(
                AnalysisResult.document_id == document_id,
                AnalysisResult.kind == JenisAnalisa.harmonisasi,
            )
            .order_by(AnalysisResult.created_at.desc())
            .first()
        )
        if latest_ar and isinstance(latest_ar.result, dict):
            marked = tandai_kunci_temuan(latest_ar.result)
            valid_keys = {
                item.get("kunci_temuan")
                for item in marked.get("temuan", [])
                if isinstance(item, dict) and item.get("kunci_temuan")
            }
            if client_kunci_clean in valid_keys:
                kunci = client_kunci_clean

    if not kunci:
        kunci = kunci_temuan(payload.temuan)

    pembanding_raw = payload.temuan.get("pembanding")
    p_dict = pembanding_raw if isinstance(pembanding_raw, dict) else None

    # Pasal pembanding: pembanding.pasal -> fallback ke pasal_pembanding
    pasal_p_val = p_dict.get("pasal") if p_dict else None
    if pasal_p_val is None or str(pasal_p_val).strip() == "":
        pasal_p_val = payload.temuan.get("pasal_pembanding")

    # Alasan: temuan.alasan -> fallback temuan.deskripsi
    alasan_val = payload.temuan.get("alasan") or payload.temuan.get("deskripsi")
    alasan_cut = str(alasan_val)[:300] if alasan_val else None

    p_draft = payload.temuan.get("pasal_draft")
    p_draft_cut = str(p_draft)[:300] if isinstance(p_draft, str) else p_draft
    p_pembanding_cut = str(pasal_p_val)[:300] if isinstance(pasal_p_val, str) else pasal_p_val

    pembanding_summary = None
    if p_dict is not None:
        pembanding_summary = {
            "key": p_dict.get("key"),
            "doc_id": p_dict.get("doc_id"),
            "document_id": p_dict.get("document_id"),
            "nomor": p_dict.get("nomor"),
            "judul": (p_dict.get("judul") or "")[:200] if p_dict.get("judul") else None,
        }

    ringkasan_temuan = {
        "jenis": payload.temuan.get("jenis"),
        "pasal_draft": p_draft_cut,
        "pasal_pembanding": p_pembanding_cut,
        "alasan": alasan_cut,
        "keyakinan": payload.temuan.get("keyakinan"),
        "tingkat": payload.temuan.get("tingkat"),
        "pembanding": pembanding_summary,
    }

    if current_user:
        dinilai_oleh = current_user.id
        dinilai_oleh_nama = current_user.username
    else:
        dinilai_oleh = None
        dinilai_oleh_nama = payload.dinilai_oleh_nama[:255] if payload.dinilai_oleh_nama else None

    existing = (
        db.query(TanggapanTemuan)
        .filter(
            TanggapanTemuan.document_id == document_id,
            TanggapanTemuan.kunci_temuan == kunci,
        )
        .first()
    )

    now_utc = datetime.now(timezone.utc)
    if existing:
        before_penilaian = existing.penilaian
        existing.penilaian = payload.penilaian
        existing.catatan = payload.catatan
        existing.run_id = payload.run_id or existing.run_id
        if payload.temuan.get("id") is not None:
            existing.temuan_id_ml = str(payload.temuan.get("id"))
        existing.ringkasan_temuan = ringkasan_temuan
        existing.dinilai_oleh = dinilai_oleh
        existing.dinilai_oleh_nama = dinilai_oleh_nama
        existing.diperbarui = now_utc
        record = existing
    else:
        before_penilaian = None
        record = TanggapanTemuan(
            document_id=document_id,
            kunci_temuan=kunci,
            run_id=payload.run_id,
            temuan_id_ml=str(payload.temuan.get("id")) if payload.temuan.get("id") is not None else None,
            penilaian=payload.penilaian,
            catatan=payload.catatan,
            ringkasan_temuan=ringkasan_temuan,
            dinilai_oleh=dinilai_oleh,
            dinilai_oleh_nama=dinilai_oleh_nama,
            dibuat=now_utc,
            diperbarui=now_utc,
        )
        db.add(record)

    try:
        db.commit()
    except IntegrityError:
        # Penanganan perlombaan PUT bersamaan untuk kunci yang sama
        db.rollback()
        existing = (
            db.query(TanggapanTemuan)
            .filter(
                TanggapanTemuan.document_id == document_id,
                TanggapanTemuan.kunci_temuan == kunci,
            )
            .first()
        )
        if existing:
            before_penilaian = existing.penilaian
            existing.penilaian = payload.penilaian
            existing.catatan = payload.catatan
            existing.run_id = payload.run_id or existing.run_id
            if payload.temuan.get("id") is not None:
                existing.temuan_id_ml = str(payload.temuan.get("id"))
            existing.ringkasan_temuan = ringkasan_temuan
            existing.dinilai_oleh = dinilai_oleh
            existing.dinilai_oleh_nama = dinilai_oleh_nama
            existing.diperbarui = datetime.now(timezone.utc)
            record = existing
            db.commit()
        else:
            raise

    db.refresh(record)

    actor_user_id = getattr(current_user, "id", None) if current_user else None
    client_ip = request.client.host if request.client else None
    record_audit(
        db,
        action=TANGGAPAN_TEMUAN,
        user_id=actor_user_id,
        target_resource=f"document:{document_id}",
        detail={
            "document_id": document_id,
            "kunci_temuan": kunci,
            "penilaian": {
                "before": before_penilaian,
                "after": payload.penilaian,
            },
            "jenis": payload.temuan.get("jenis"),
        },
        ip_address=client_ip,
        commit=True,
    )

    return record


@router.get(
    "/api/v1/documents/{document_id}/harmonisasi/tanggapan",
    response_model=List[TanggapanTemuanResponse],
    summary="Daftar tanggapan analis untuk draft kajian tertentu (US-49 #71)",
)
def list_tanggapan_temuan(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(perlu_izin(Izin.KB_BACA)),
):
    """Mengembalikan seluruh daftar tanggapan analis yang tersimpan untuk dokumen draft tertentu."""
    doc = check_document_access(db, document_id, user=current_user)
    if doc.document_role != PeranDokumen.draft_kajian:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "bukan_draft", "message": "Hanya dokumen draft kajian yang dapat dilihat tanggapan harmonisasinya."},
        )

    records = (
        db.query(TanggapanTemuan)
        .filter(TanggapanTemuan.document_id == document_id)
        .order_by(TanggapanTemuan.dibuat.asc())
        .all()
    )
    return records


@router.delete(
    "/api/v1/documents/{document_id}/harmonisasi/tanggapan/{kunci_temuan}",
    summary="Hapus tanggapan temuan harmonisasi (US-49 #71)",
)
def delete_tanggapan_temuan(
    document_id: int,
    kunci_temuan: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(perlu_izin(Izin.TANGGAPAN_TINJAU)),
):
    """Menghapus penandaan/tanggapan analis sehingga temuan kembali berstatus 'belum dinilai'."""
    doc = check_document_access(db, document_id, user=current_user)
    if doc.document_role != PeranDokumen.draft_kajian:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "bukan_draft", "message": "Hanya dokumen draft kajian yang dapat dihapus tanggapan harmonisasinya."},
        )

    existing = (
        db.query(TanggapanTemuan)
        .filter(
            TanggapanTemuan.document_id == document_id,
            TanggapanTemuan.kunci_temuan == kunci_temuan,
        )
        .first()
    )
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tanggapan temuan tidak ditemukan")

    old_penilaian = existing.penilaian
    old_jenis = existing.ringkasan_temuan.get("jenis") if existing.ringkasan_temuan else None

    db.delete(existing)
    db.commit()

    actor_user_id = getattr(current_user, "id", None) if current_user else None
    client_ip = request.client.host if request.client else None
    record_audit(
        db,
        action=TANGGAPAN_TEMUAN,
        user_id=actor_user_id,
        target_resource=f"document:{document_id}",
        detail={
            "document_id": document_id,
            "kunci_temuan": kunci_temuan,
            "penilaian": {
                "before": old_penilaian,
                "after": None,
            },
            "jenis": old_jenis,
            "action": "delete",
        },
        ip_address=client_ip,
        commit=True,
    )

    return {"status": "ok", "message": "Tanggapan temuan berhasil dihapus", "kunci_temuan": kunci_temuan}


@router.get(
    "/api/v1/harmonisasi/tanggapan/rekap",
    summary="Rekap tanggapan analis untuk evaluasi recall (FR-HRM-11, #74)",
)
def rekap_tanggapan(
    dari: Optional[date] = Query(None, description="Tanggal awal penilaian (YYYY-MM-DD)"),
    sampai: Optional[date] = Query(None, description="Tanggal akhir penilaian (YYYY-MM-DD)"),
    document_id: Optional[int] = Query(None, description="Filter dokumen draft tertentu"),
    format: Optional[str] = Query(None, description="Format respons: 'csv' atau default JSON"),
    db: Session = Depends(get_db),
    current_user=Depends(perlu_izin(Izin.KB_BACA)),
):
    """
    [FR-HRM-11, #74] Rekapitulasi tanggapan valid vs tidak relevan per jenis temuan
    untuk bahan evaluasi recall dan umpan balik model.
    """
    query = db.query(TanggapanTemuan)
    allowed_ids = None
    if document_id is not None:
        check_document_access(db, document_id, user=current_user)
        query = query.filter(TanggapanTemuan.document_id == document_id)
    else:
        allowed_ids = allowed_document_ids(db, user=current_user)
        if allowed_ids is not None:
            if not allowed_ids:
                pass
            else:
                query = query.filter(TanggapanTemuan.document_id.in_(allowed_ids))

    if dari is not None:
        dari_dt = datetime.combine(dari, time.min).replace(tzinfo=timezone.utc)
        query = query.filter(TanggapanTemuan.dibuat >= dari_dt)
    if sampai is not None:
        sampai_dt = datetime.combine(sampai, time.max).replace(tzinfo=timezone.utc)
        query = query.filter(TanggapanTemuan.dibuat <= sampai_dt)

    if document_id is None and allowed_ids is not None and not allowed_ids:
        rows = []
    else:
        rows = query.all()

    per_jenis: Dict[str, Dict[str, int]] = {}
    total_valid = 0
    total_tidak_relevan = 0

    for r in rows:
        jenis = "lainnya"
        if r.ringkasan_temuan and r.ringkasan_temuan.get("jenis"):
            jenis = str(r.ringkasan_temuan["jenis"]).strip().lower()

        if jenis not in per_jenis:
            per_jenis[jenis] = {"valid": 0, "tidak_relevan": 0, "total": 0}

        if r.penilaian == "valid":
            per_jenis[jenis]["valid"] += 1
            total_valid += 1
        elif r.penilaian == "tidak_relevan":
            per_jenis[jenis]["tidak_relevan"] += 1
            total_tidak_relevan += 1
        per_jenis[jenis]["total"] += 1

    total_rekap = {
        "valid": total_valid,
        "tidak_relevan": total_tidak_relevan,
        "total": total_valid + total_tidak_relevan,
    }

    if format and format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["jenis", "valid", "tidak_relevan", "total"])
        for j_key, counts in sorted(per_jenis.items()):
            writer.writerow([j_key, counts["valid"], counts["tidak_relevan"], counts["total"]])
        writer.writerow(["TOTAL", total_rekap["valid"], total_rekap["tidak_relevan"], total_rekap["total"]])

        csv_bytes = b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")
        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="rekap_tanggapan_harmonisasi.csv"',
                "Content-Type": "text/csv; charset=utf-8",
            },
        )

    return {
        "total": total_rekap,
        "per_jenis": per_jenis,
        "filter": {
            "dari": dari.isoformat() if dari else None,
            "sampai": sampai.isoformat() if sampai else None,
            "document_id": document_id,
        },
    }


@router.get(
    "/api/v1/documents/{document_id}/harmonisasi/ekspor",
    summary="Ekspor laporan harmonisasi regulasi (DOCX, CSV, JSON) (US-50 #73)",
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {},
                "text/csv": {},
                "application/json": {},
            },
            "description": "Berkas ekspor laporan harmonisasi dalam format DOCX, CSV, atau JSON.",
        },
        403: {"description": "Akses ditolak (dokumen non-publik memerlukan otentikasi)"},
        404: {"description": "Dokumen tidak ditemukan atau belum pernah diharmonisasi"},
        422: {"description": "Bukan dokumen draft kajian atau format tidak didukung"},
    },
)
def export_document_harmonization(
    document_id: int,
    request: Request,
    format: str = Query("docx", description="Format berkas ekspor: docx | csv | json"),
    run_id: Optional[int] = Query(None, description="ID eksekusi tertentu dari riwayat harmonisasi"),
    db: Session = Depends(get_db),
    current_user=Depends(perlu_izin(Izin.ANALISA_EKSPOR)),
):
    """
    [US-50, FR-HRM-13] Mengekspor laporan hasil harmonisasi draft regulasi ke berkas DOCX, CSV, atau JSON
    langsung dari hasil yang tersimpan di basis data (tanpa memanggil layanan ML).
    """
    doc = check_document_access(db, document_id, user=current_user)
    if doc.document_role != PeranDokumen.draft_kajian:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "bukan_draft", "message": "Hanya dokumen draft kajian yang dapat diekspor laporan harmonisasinya."},
        )

    fmt_clean = format.lower().strip()
    if fmt_clean not in ("docx", "csv", "json"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Format '{format}' tidak didukung. Pilihan format: docx, csv, json.",
        )

    allowed_ids = allowed_document_ids(db, user=current_user)
    content_bytes, media_type, headers, temuan_count = export_harmonisasi(
        db=db,
        doc=doc,
        format_type=fmt_clean,
        run_id=run_id,
        current_user=current_user,
        allowed_ids=allowed_ids,
        saring_rujukan_lengkap_fn=saring_rujukan_lengkap,
        sesuaikan_ringkasan_harmonisasi_fn=sesuaikan_ringkasan_harmonisasi,
    )

    actor_user_id = getattr(current_user, "id", None) if current_user else None
    client_ip = request.client.host if request.client else None
    record_audit(
        db,
        action=EXPORT_HARMONIZATION,
        user_id=actor_user_id,
        target_resource=f"document:{doc.id}",
        detail={
            "document_id": doc.id,
            "format": fmt_clean,
            "run_id": run_id,
            "jumlah_temuan": temuan_count,
        },
        ip_address=client_ip,
        commit=True,
    )

    return Response(
        content=content_bytes,
        media_type=media_type,
        headers=headers,
    )
