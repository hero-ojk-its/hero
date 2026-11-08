"""
app/services/harmonisasi_export_service.py
Layanan untuk mengekspor laporan hasil harmonisasi regulasi ke format DOCX, CSV, dan JSON
(Langkah 39, US-50 #73).
"""
import csv
from datetime import datetime, timezone
import io
import json
import logging
import re
from typing import Any, Dict, Optional, Set, Tuple
import unicodedata
import urllib.parse

import docx
from docx.shared import Pt, RGBColor
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.analysis_result import AnalysisResult
from app.models.analysis_run import AnalysisRun
from app.models.document import Document
from app.models.enums import JenisAnalisa
from app.services.tanggapan_service import (
    gabungkan_tanggapan_ke_harmonisasi,
    tandai_kunci_temuan,
)

logger = logging.getLogger("hero")

FOOTER_URD = "Keputusan final tetap kewenangan Pengawas / unit terkait."


def generate_harmonisasi_export_filename(
    identitas: Optional[Dict[str, Any]],
    document_id: int,
    mode: str,
    ext: str,
) -> Tuple[str, str]:
    """
    Format: harmonisasi_{jenis}_{nomor}_{tahun}_{mode}.{ext}, dari identitas regulasi.
    Bila kosong, gunakan harmonisasi_dokumen_{document_id}_{mode}.{ext}.
    Mengembalikan tuple (filename_ascii, filename_utf8) untuk header Content-Disposition (RFC 5987).
    """
    jenis = None
    nomor = None
    tahun = None
    if isinstance(identitas, dict):
        jenis = identitas.get("jenis")
        nomor = identitas.get("nomor")
        tahun = identitas.get("tahun")

    clean_parts = [str(x).strip() for x in (jenis, nomor, tahun) if x is not None and str(x).strip()]
    if clean_parts:
        raw_name = f"harmonisasi_{'_'.join(clean_parts)}_{mode}.{ext}"
    else:
        raw_name = f"harmonisasi_dokumen_{document_id}_{mode}.{ext}"

    # UTF-8: bersihkan karakter terlarang filesystem
    cleaned_utf8 = re.sub(r'[\s/\\:*?"<>|]+', "_", raw_name)
    cleaned_utf8 = re.sub(r"_+", "_", cleaned_utf8)

    # ASCII: normalisasi NFKD lalu buang karakter non-ASCII
    norm_ascii = unicodedata.normalize("NFKD", raw_name).encode("ascii", "ignore").decode("ascii")
    cleaned_ascii = re.sub(r'[\s/\\:*?"<>|]+', "_", norm_ascii)
    cleaned_ascii = re.sub(r"_+", "_", cleaned_ascii)
    if not cleaned_ascii or cleaned_ascii == f".{ext}":
        cleaned_ascii = f"harmonisasi_dokumen_{document_id}_{mode}.{ext}"

    return cleaned_ascii, cleaned_utf8


def _format_keyakinan(tingkat: Any, keyakinan: Any) -> str:
    """Format tingkat dan keyakinan, mis. 'tinggi (0,82)'."""
    score_str = None
    if keyakinan is not None:
        try:
            score_val = float(keyakinan)
            score_str = f"{score_val:.2f}".replace(".", ",")
        except (ValueError, TypeError):
            score_str = str(keyakinan)

    tingkat_str = str(tingkat).strip() if tingkat is not None and str(tingkat).strip() else None

    if tingkat_str and score_str:
        return f"{tingkat_str} ({score_str})"
    elif tingkat_str:
        return tingkat_str
    elif score_str:
        return score_str
    return "-"


def export_harmonisasi_to_docx(
    doc_model: Document,
    data: Dict[str, Any],
    mode: str,
    dibuat_at: Optional[datetime],
    diekspor_at: datetime,
) -> bytes:
    """Membangun berkas DOCX laporan harmonisasi sesuai spesifikasi #73."""
    document = docx.Document()

    # 1. Judul Laporan
    h_title = document.add_heading("Laporan Harmonisasi", level=1)
    h_title.style.font.size = Pt(18)

    # 2. Identitas Draft
    p_meta = document.add_paragraph()
    p_meta.add_run("Judul Regulasi: ").bold = True
    p_meta.add_run(f"{doc_model.title or f'Dokumen #{doc_model.id}'}\n")

    reg_info = []
    if doc_model.regulation_type:
        reg_info.append(f"Jenis: {doc_model.regulation_type}")
    if doc_model.regulation_number:
        reg_info.append(f"Nomor: {doc_model.regulation_number}")
    if doc_model.regulation_year:
        reg_info.append(f"Tahun: {doc_model.regulation_year}")
    if reg_info:
        p_meta.add_run(f"{' | '.join(reg_info)}\n")

    p_meta.add_run(f"ID Dokumen: #{doc_model.id} | Mode: {mode}\n")
    waktu_harmonisasi = dibuat_at.strftime("%Y-%m-%d %H:%M:%S UTC") if dibuat_at else "-"
    waktu_ekspor = diekspor_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    p_meta.add_run(f"Waktu Harmonisasi: {waktu_harmonisasi} | Waktu Ekspor: {waktu_ekspor}\n")

    # 3. Ringkasan Temuan & Rekap Tanggapan Analis
    document.add_heading("Ringkasan Hasil Harmonisasi", level=2)
    ringkasan = data.get("ringkasan") if isinstance(data.get("ringkasan"), dict) else {}
    temuan_list = data.get("temuan") if isinstance(data.get("temuan"), list) else []

    total_temuan = ringkasan.get("total_temuan", len(temuan_list))
    p_ringkasan = document.add_paragraph()
    p_ringkasan.add_run(f"Total Temuan: {total_temuan}\n").bold = True

    per_jenis = ringkasan.get("per_jenis")
    if isinstance(per_jenis, dict) and per_jenis:
        p_ringkasan.add_run("Rincian per Jenis Temuan:\n").bold = True
        for j_key, j_val in per_jenis.items():
            p_ringkasan.add_run(f"  • {str(j_key).replace('_', ' ').capitalize()}: {j_val}\n")

    tanggapan_rekap = ringkasan.get("tanggapan")
    if isinstance(tanggapan_rekap, dict):
        p_ringkasan.add_run("Rekap Penilaian Analis:\n").bold = True
        valid_n = tanggapan_rekap.get("valid", 0)
        tr_n = tanggapan_rekap.get("tidak_relevan", 0)
        bd_n = tanggapan_rekap.get("belum_dinilai", 0)
        p_ringkasan.add_run(f"  • Valid: {valid_n}\n")
        p_ringkasan.add_run(f"  • Tidak Relevan: {tr_n}\n")
        p_ringkasan.add_run(f"  • Belum Dinilai: {bd_n}\n")

    # 4. Tabel Temuan
    document.add_heading("Daftar Temuan Harmonisasi", level=2)
    tbl = document.add_table(rows=1, cols=9)
    tbl.style = "Table Grid"

    hdr_cells = tbl.rows[0].cells
    headers = [
        "No",
        "Jenis",
        "Pasal Draft",
        "Peraturan Pembanding",
        "Pasal Pembanding",
        "Uraian Temuan",
        "Keyakinan",
        "Penilaian Analis",
        "Catatan",
    ]
    for idx, h in enumerate(headers):
        hdr_cells[idx].text = h
        hdr_cells[idx].paragraphs[0].runs[0].bold = True

    for i, t in enumerate(temuan_list, start=1):
        if not isinstance(t, dict):
            continue
        row_cells = tbl.add_row().cells
        row_cells[0].text = str(i)
        row_cells[1].text = str(t.get("jenis") or "-")
        row_cells[2].text = str(t.get("pasal_draft") or "-")

        p_info = t.get("pembanding")
        p_dict = p_info if isinstance(p_info, dict) else {}
        p_str = p_dict.get("nomor") or p_dict.get("key") or p_dict.get("judul") or "-"
        if p_dict.get("nomor") and p_dict.get("judul") and p_dict.get("nomor") != p_dict.get("judul"):
            p_str = f"{p_dict.get('nomor')} ({p_dict.get('judul')})"
        row_cells[3].text = str(p_str)

        pasal_p = p_dict.get("pasal") or t.get("pasal_pembanding")
        row_cells[4].text = str(pasal_p or "-")

        uraian = t.get("alasan") or t.get("deskripsi") or t.get("judul")
        row_cells[5].text = str(uraian or "-")

        keyakinan_str = _format_keyakinan(t.get("tingkat"), t.get("keyakinan"))
        row_cells[6].text = str(keyakinan_str or "-")

        tg = t.get("tanggapan")
        if isinstance(tg, dict):
            pen = str(tg.get("penilaian") or "-").replace("_", " ").capitalize()
            cat = str(tg.get("catatan") or "-")
        else:
            pen = "Belum dinilai"
            cat = "-"
        row_cells[7].text = pen
        row_cells[8].text = cat

    # 5. Catatan Kaki / Disclaimer (URD)
    document.add_paragraph()
    p_footer = document.add_paragraph()
    run_footer = p_footer.add_run(FOOTER_URD)
    run_footer.italic = True
    run_footer.font.size = Pt(9)
    run_footer.font.color.rgb = RGBColor(120, 120, 120)

    buf = io.BytesIO()
    document.save(buf)
    buf.seek(0)
    return buf.getvalue()


def export_harmonisasi_to_csv(data: Dict[str, Any]) -> bytes:
    """Membangun berkas CSV (UTF-8 dengan BOM) laporan harmonisasi sesuai spesifikasi #73."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "No",
        "Jenis",
        "Pasal Draft",
        "Peraturan Pembanding",
        "Pasal Pembanding",
        "Uraian Temuan",
        "Keyakinan",
        "Penilaian Analis",
        "Catatan Analis",
        "Dinilai Oleh",
        "Kunci Temuan",
    ])

    temuan_list = data.get("temuan") if isinstance(data.get("temuan"), list) else []
    for i, t in enumerate(temuan_list, start=1):
        if not isinstance(t, dict):
            continue
        p_info = t.get("pembanding")
        p_dict = p_info if isinstance(p_info, dict) else {}
        p_str = p_dict.get("nomor") or p_dict.get("key") or p_dict.get("judul") or ""
        if p_dict.get("nomor") and p_dict.get("judul") and p_dict.get("nomor") != p_dict.get("judul"):
            p_str = f"{p_dict.get('nomor')} ({p_dict.get('judul')})"

        pasal_p = p_dict.get("pasal") or t.get("pasal_pembanding")
        uraian = t.get("alasan") or t.get("deskripsi") or t.get("judul")
        keyakinan_str = _format_keyakinan(t.get("tingkat"), t.get("keyakinan"))
        if keyakinan_str == "-":
            keyakinan_str = ""

        tg = t.get("tanggapan")
        if isinstance(tg, dict):
            pen = str(tg.get("penilaian") or "")
            cat = str(tg.get("catatan") or "")
            oleh = str(tg.get("dinilai_oleh_nama") or "")
        else:
            pen = "Belum dinilai"
            cat = ""
            oleh = ""

        writer.writerow([
            i,
            t.get("jenis") or "",
            t.get("pasal_draft") or "",
            p_str,
            pasal_p or "",
            uraian or "",
            keyakinan_str,
            pen,
            cat,
            oleh,
            t.get("kunci_temuan") or "",
        ])

    csv_text = output.getvalue()
    return b"\xef\xbb\xbf" + csv_text.encode("utf-8")


def export_harmonisasi(
    db: Session,
    doc: Document,
    format_type: str,
    run_id: Optional[int] = None,
    current_user: Optional[Any] = None,
    allowed_ids: Optional[Set[int]] = None,
    saring_rujukan_lengkap_fn: Optional[Any] = None,
    sesuaikan_ringkasan_harmonisasi_fn: Optional[Any] = None,
) -> Tuple[bytes, str, Dict[str, str], int]:
    """
    Mengambil hasil harmonisasi tersimpan (cache atau run), menyaring rujukan rahasia/nonaktif,
    menggabungkan tanggapan analis, dan menghasilkan bytes berkas ekspor sesuai format (DOCX/CSV/JSON).
    """
    raw_data: Optional[Dict[str, Any]] = None
    dibuat_at: Optional[datetime] = None
    actual_mode: str = "deterministik"
    resolved_run_id: Optional[int] = run_id

    # 1. Ambil data harmonisasi tersimpan
    if run_id is not None:
        run = (
            db.query(AnalysisRun)
            .filter(
                AnalysisRun.id == run_id,
                AnalysisRun.document_id == doc.id,
                AnalysisRun.kind == JenisAnalisa.harmonisasi,
            )
            .first()
        )
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Riwayat harmonisasi dengan run_id {run_id} tidak ditemukan untuk dokumen ini.",
            )
        if run.sumber == "gagal":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "hasil_tidak_tersedia", "message": "Hasil harmonisasi tidak tersedia untuk eksekusi ini."},
            )

        if run.result is not None:
            raw_data = run.result
        elif run.result_hash:
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
                raw_data = src_run.result

        if raw_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "harmonisasi_belum_ada", "message": "Hasil harmonisasi tidak tersedia untuk dokumen ini."},
            )

        dibuat_at = run.created_at
        actual_mode = (
            run.mode_dipakai.value
            if (run.mode_dipakai and hasattr(run.mode_dipakai, "value"))
            else (str(run.mode_dipakai) if run.mode_dipakai else "deterministik")
        )
        resolved_run_id = run.id
    else:
        cached = (
            db.query(AnalysisResult)
            .filter(
                AnalysisResult.document_id == doc.id,
                AnalysisResult.kind == JenisAnalisa.harmonisasi,
            )
            .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
            .first()
        )
        if cached and cached.result:
            raw_data = cached.result
            dibuat_at = cached.created_at
            actual_mode = (
                cached.mode.value
                if hasattr(cached.mode, "value")
                else str(cached.mode or "deterministik")
            )
            latest_run = (
                db.query(AnalysisRun)
                .filter(
                    AnalysisRun.document_id == doc.id,
                    AnalysisRun.kind == JenisAnalisa.harmonisasi,
                )
                .order_by(AnalysisRun.id.desc())
                .first()
            )
            resolved_run_id = latest_run.id if latest_run else None
        else:
            # Fallback ke run terbaru bila cache tidak ada
            latest_run = (
                db.query(AnalysisRun)
                .filter(
                    AnalysisRun.document_id == doc.id,
                    AnalysisRun.kind == JenisAnalisa.harmonisasi,
                    AnalysisRun.result.isnot(None),
                )
                .order_by(AnalysisRun.id.desc())
                .first()
            )
            if latest_run and latest_run.result:
                raw_data = latest_run.result
                dibuat_at = latest_run.created_at
                actual_mode = (
                    latest_run.mode_dipakai.value
                    if (latest_run.mode_dipakai and hasattr(latest_run.mode_dipakai, "value"))
                    else (str(latest_run.mode_dipakai) if latest_run.mode_dipakai else "deterministik")
                )
                resolved_run_id = latest_run.id
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "code": "harmonisasi_belum_ada",
                        "message": "Dokumen ini belum pernah diharmonisasi.",
                    },
                )

    # 2. Tandai kunci temuan dari data mentah SEBELUM penyaringan rujukan
    marked_data = tandai_kunci_temuan(raw_data)

    # 3. Penyaringan rujukan dokumen nonaktif / non-publik
    if allowed_ids is not None and saring_rujukan_lengkap_fn is not None:
        filtered_data, discarded, rincian = saring_rujukan_lengkap_fn(marked_data, allowed_ids)
        if sesuaikan_ringkasan_harmonisasi_fn is not None:
            sesuaikan_ringkasan_harmonisasi_fn(filtered_data, discarded, rincian)
    else:
        filtered_data = marked_data

    # 4. Gabungkan tanggapan analis
    filtered_data = gabungkan_tanggapan_ke_harmonisasi(db, doc.id, filtered_data)

    temuan_count = len(filtered_data.get("temuan", [])) if isinstance(filtered_data.get("temuan"), list) else 0
    now_utc = datetime.now(timezone.utc)

    # 4. Generate nama berkas
    identitas = {
        "jenis": doc.regulation_type,
        "nomor": doc.regulation_number,
        "tahun": doc.regulation_year,
    }
    ascii_name, utf8_name = generate_harmonisasi_export_filename(identitas, doc.id, actual_mode, format_type)
    encoded_utf8 = urllib.parse.quote(utf8_name)
    content_disp = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_utf8}'

    # 5. Format hasil
    fmt = format_type.lower()
    if fmt == "docx":
        content_bytes = export_harmonisasi_to_docx(doc, filtered_data, actual_mode, dibuat_at, now_utc)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        headers = {
            "Content-Disposition": content_disp,
            "Content-Type": media_type,
        }
    elif fmt == "csv":
        content_bytes = export_harmonisasi_to_csv(filtered_data)
        media_type = "text/csv; charset=utf-8"
        headers = {
            "Content-Disposition": content_disp,
            "Content-Type": media_type,
        }
    elif fmt == "json":
        export_payload = {
            "metadata": {
                "dokumen": {
                    "id": doc.id,
                    "judul": doc.title,
                    "nomor": doc.regulation_number,
                    "tahun": doc.regulation_year,
                },
                "dibuat": dibuat_at.isoformat() if dibuat_at else None,
                "diekspor": now_utc.isoformat(),
                "mode": actual_mode,
                "run_id": resolved_run_id,
            },
            "draft": filtered_data.get("draft"),
            "ringkasan": filtered_data.get("ringkasan"),
            "temuan": filtered_data.get("temuan"),
            "versi": filtered_data.get("versi"),
        }
        content_bytes = json.dumps(export_payload, ensure_ascii=False, indent=2).encode("utf-8")
        media_type = "application/json; charset=utf-8"
        headers = {
            "Content-Disposition": content_disp,
            "Content-Type": media_type,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Format '{format_type}' tidak didukung. Format yang tersedia: docx, csv, json.",
        )

    return content_bytes, media_type, headers, temuan_count
