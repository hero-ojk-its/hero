"""
scripts/buat_lembar_sampling.py
Skrip pembuatan lembar kerja Excel (.xlsx) sampling validasi manual temuan harmonisasi (DPEA).

Perilaku:
- Mengambil sampel temuan dari hasil harmonisasi yang tersimpan di tabel analysis_results.
- Tidak memanggil layanan ML.
- Melewati dokumen yang bukan draft_kajian atau belum memiliki hasil harmonisasi tersimpan.
- Mengambil hingga K temuan berpembanding (bukan pasal_baru) per dokumen, dengan pasal draf unik.
- Pengacakan deterministik menggunakan seed yang dapat ditentukan.
- Aman dari formula injection (sel teks diset sebagai string 's', karakter kontrol dibuang).
- Menghasilkan dua sheet: 'Sampel' dan 'Petunjuk'.
- Read-only terhadap database (tidak mengubah apa pun di DB).
- Tidak mencetak judul dokumen atau kutipan ke konsol (menjaga kerahasiaan isi non-publik).
"""
import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import random
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union
import urllib.parse

# Pastikan root proyek backend masuk ke sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Pastikan output konsol UTF-8 di Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.analysis_result import AnalysisResult
from app.models.document import Document
from app.models.enums import JenisAnalisa, PeranDokumen
from app.services.harmonisasi_export_service import (
    JENIS_LABEL_MAP,
    _format_keyakinan,
    _format_nama_pembanding,
    set_safe_text_cell,
)

logger = logging.getLogger("hero")

PESAN_PERINGATAN_NON_PUBLIK = (
    "Berkas ini dapat memuat isi dokumen non-publik. Jangan dibagikan di luar kanal yang disetujui."
)


def jalankan_buat_lembar_sampling(
    db: Session,
    document_ids: Sequence[int],
    per_dokumen: int = 3,
    seed: int = 42,
    keluaran: Optional[Union[str, Path]] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Menjalankan proses pembuatan lembar sampling harmonisasi (read-only ke DB).
    Mengembalikan dictionary ringkasan eksekusi.
    """
    if per_dokumen < 1:
        raise ValueError("Jumlah sampel per dokumen (--per-dokumen) minimal 1.")

    # Deduplikasi ID dokumen dengan mempertahankan urutan input
    seen_ids = set()
    doc_ids_unique: List[int] = []
    for d_id in document_ids:
        if d_id not in seen_ids:
            seen_ids.add(d_id)
            doc_ids_unique.append(d_id)

    wb = openpyxl.Workbook()

    # Sheet 1: Sampel
    ws_sampel = wb.active
    ws_sampel.title = "Sampel"

    # Sheet 2: Petunjuk
    ws_petunjuk = wb.create_sheet(title="Petunjuk")

    # Header Sheet Sampel
    headers_sampel = [
        "No",
        "Dokumen draf",
        "Pasal draf",
        "Kutipan draf",
        "Peraturan pembanding",
        "Pasal pembanding",
        "Jenis",
        "Keyakinan",
        "Kutipan pembanding",
        "Tautan PDF pembanding",
        "Bunyi pasal sesuai? (Ya/Tidak)",
        "Jenis temuan sesuai? (Ya/Tidak)",
        "Catatan validator",
    ]

    for col_idx, h in enumerate(headers_sampel, start=1):
        cell_h = ws_sampel.cell(row=1, column=col_idx, value=h)
        cell_h.font = Font(name="Calibri", size=11, bold=True)
        cell_h.fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
        cell_h.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws_sampel.freeze_panes = "A2"

    dokumen_diproses = 0
    dokumen_dilewati = 0
    temuan_dilewati_pembanding_nonaktif = 0
    sampel_ditulis = 0

    clean_base_url = (base_url or "").strip().rstrip("/") if base_url else None

    # Kumpulkan dokumen valid dan seluruh pembanding.document_id untuk query status aktif batch
    kandidat_dokumen: List[Tuple[Document, List[Dict[str, Any]]]] = []
    pembanding_ids_to_check: set = set()

    for doc_id in doc_ids_unique:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            dokumen_dilewati += 1
            continue

        if doc.document_role != PeranDokumen.draft_kajian:
            dokumen_dilewati += 1
            continue

        # Ambil hasil harmonisasi tersimpan terbaru (cache analysis_results)
        cached = (
            db.query(AnalysisResult)
            .filter(
                AnalysisResult.document_id == doc.id,
                AnalysisResult.kind == JenisAnalisa.harmonisasi,
                AnalysisResult.result.isnot(None),
            )
            .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
            .first()
        )

        if not cached or not isinstance(cached.result, dict):
            dokumen_dilewati += 1
            continue

        raw_temuan = cached.result.get("temuan")
        if not isinstance(raw_temuan, list) or not raw_temuan:
            dokumen_dilewati += 1
            continue

        for t in raw_temuan:
            if isinstance(t, dict):
                p_info = t.get("pembanding")
                if isinstance(p_info, dict):
                    pid = p_info.get("document_id")
                    if pid is not None:
                        try:
                            pembanding_ids_to_check.add(int(pid))
                        except (ValueError, TypeError):
                            pass

        kandidat_dokumen.append((doc, raw_temuan))

    # Satu kueri untuk memeriksa semua ID dokumen pembanding yang aktif di DB
    active_pembanding_ids: set = set()
    if pembanding_ids_to_check:
        active_rows = (
            db.query(Document.id)
            .filter(
                Document.id.in_(pembanding_ids_to_check),
                Document.is_active == True,
            )
            .all()
        )
        active_pembanding_ids = {r[0] for r in active_rows}

    for doc, raw_temuan in kandidat_dokumen:
        # Filter temuan: hanya yang memiliki pembanding (bukan pasal_baru) dan pembandingnya aktif bila ber-document_id
        eligible_temuan: List[Dict[str, Any]] = []
        for t in raw_temuan:
            if not isinstance(t, dict):
                continue
            raw_j = str(t.get("jenis") or "").strip().lower()
            if raw_j == "pasal_baru":
                continue
            p_info = t.get("pembanding")
            if not p_info or not isinstance(p_info, dict):
                continue

            # Periksa pembanding nonaktif / dokumen tidak ditemukan
            pid = p_info.get("document_id")
            if pid is not None:
                try:
                    pid_int = int(pid)
                    if pid_int not in active_pembanding_ids:
                        temuan_dilewati_pembanding_nonaktif += 1
                        continue
                except (ValueError, TypeError):
                    temuan_dilewati_pembanding_nonaktif += 1
                    continue

            eligible_temuan.append(t)

        if not eligible_temuan:
            dokumen_dilewati += 1
            continue

        dokumen_diproses += 1

        # Pengacakan deterministik menggunakan seed + doc.id agar tiap dokumen konsisten
        doc_rng = random.Random(seed * 1000003 + doc.id)
        shuffled_temuan = list(eligible_temuan)
        doc_rng.shuffle(shuffled_temuan)

        # Ambil hingga per_dokumen sampel dengan pasal draf unik
        sampled_doc: List[Dict[str, Any]] = []
        seen_pasal = set()
        for t in shuffled_temuan:
            pasal_raw = t.get("pasal_draft") or t.get("pasal")
            pasal_norm = str(pasal_raw).strip().lower() if pasal_raw else ""
            if pasal_norm and pasal_norm in seen_pasal:
                continue
            if pasal_norm:
                seen_pasal.add(pasal_norm)
            sampled_doc.append(t)
            if len(sampled_doc) >= per_dokumen:
                break

        # Tulis baris sampel ke sheet
        judul_draf = doc.title or f"Dokumen #{doc.id}"

        for t in sampled_doc:
            sampel_ditulis += 1
            row_num = sampel_ditulis + 1

            pasal_d = t.get("pasal_draft") or t.get("pasal") or "-"
            kutipan_d = (
                t.get("kutipan_draft")
                or t.get("teks_draft")
                or t.get("draft_teks")
                or t.get("kutipan")
                or t.get("isi_pasal")
                or "-"
            )

            p_dict = t.get("pembanding") if isinstance(t.get("pembanding"), dict) else {}
            p_nama = _format_nama_pembanding(p_dict, pasal_fallback=t.get("pasal_pembanding")) or "-"
            pasal_p = p_dict.get("pasal") or t.get("pasal_pembanding") or "-"

            raw_j = str(t.get("jenis") or "").strip().lower()
            lbl_jenis = JENIS_LABEL_MAP.get(raw_j, str(t.get("jenis") or "-"))

            keyakinan_str = _format_keyakinan(t.get("tingkat"), t.get("keyakinan"))
            kutipan_p = p_dict.get("kutipan") or t.get("kutipan_pembanding") or "-"

            # Tautan PDF pembanding
            pdf_raw = p_dict.get("pdf") or p_dict.get("pdf_url") or p_dict.get("url")
            pdf_str = str(pdf_raw).strip() if pdf_raw and str(pdf_raw).strip() else ""
            if pdf_str:
                if clean_base_url and not (pdf_str.startswith("http://") or pdf_str.startswith("https://")):
                    pdf_link = f"{clean_base_url}/{pdf_str.lstrip('/')}"
                else:
                    pdf_link = pdf_str
            else:
                pdf_link = ""

            # Kolom 1: No (integer)
            c_no = ws_sampel.cell(row=row_num, column=1, value=sampel_ditulis)
            c_no.alignment = Alignment(horizontal="center", vertical="top")

            # Kolom 2..13: Teks biasa (safe text)
            row_cols = [
                judul_draf,
                pasal_d,
                kutipan_d,
                p_nama,
                pasal_p,
                lbl_jenis,
                keyakinan_str,
                kutipan_p,
                pdf_link,
                "",  # Bunyi pasal sesuai? (Ya/Tidak)
                "",  # Jenis temuan sesuai? (Ya/Tidak)
                "",  # Catatan validator
            ]

            for offset, val in enumerate(row_cols, start=2):
                cell_v = ws_sampel.cell(row=row_num, column=offset)
                set_safe_text_cell(cell_v, val)
                cell_v.alignment = Alignment(vertical="top", wrap_text=True)

    col_widths_sampel = {
        "A": 6,
        "B": 32,
        "C": 15,
        "D": 45,
        "E": 36,
        "F": 18,
        "G": 16,
        "H": 18,
        "I": 45,
        "J": 35,
        "K": 20,
        "L": 20,
        "M": 30,
    }
    for col_letter, width in col_widths_sampel.items():
        ws_sampel.column_dimensions[col_letter].width = width

    # --- Sheet 2: Petunjuk ---
    ws_petunjuk.cell(row=1, column=1, value="Petunjuk Validasi Sampling Harmonisasi Regulasi (DPEA)").font = Font(
        name="Calibri", size=13, bold=True
    )
    ws_petunjuk.cell(row=3, column=1, value="Langkah-Langkah Validasi Manual:").font = Font(
        name="Calibri", size=11, bold=True
    )

    petunjuk_steps = [
        "1. Buka dokumen PDF peraturan pembanding yang tercantum pada kolom 'Tautan PDF pembanding' (atau buka berkas PDF terkait di repositori regulasi HERO).",
        "2. Cocokkan bunyi pasal peraturan pembanding dengan kutipan pembanding, serta bandingkan dengan ketentuan pasal draf regulasi.",
        "3. Isi evaluasi validator pada kolom yang tersedia di lembar 'Sampel':",
        "   a. 'Bunyi pasal sesuai? (Ya/Tidak)': Isi 'Ya' bila bunyi dan nomor pasal pembanding akurat sesuai dokumen resmi, atau 'Tidak' bila tidak sesuai.",
        "   b. 'Jenis temuan sesuai? (Ya/Tidak)': Isi 'Ya' bila relasi regulasi (Sama / Menggantikan / Melengkapi / Konflik) tepat, atau 'Tidak' bila keliru.",
        "   c. 'Catatan validator': Berikan catatan koreksi atau penjelasan temuan bila terdapat ketidaksesuaian.",
    ]

    for idx, step_txt in enumerate(petunjuk_steps, start=4):
        set_safe_text_cell(ws_petunjuk.cell(row=idx, column=1), step_txt)

    ws_petunjuk.cell(row=11, column=1, value="Informasi Parameter Sampling:").font = Font(
        name="Calibri", size=11, bold=True
    )
    set_safe_text_cell(ws_petunjuk.cell(row=12, column=1), f"Seed pengacakan : {seed}")
    set_safe_text_cell(
        ws_petunjuk.cell(row=13, column=1),
        f"Waktu pembuatan : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
    )
    ws_petunjuk.column_dimensions["A"].width = 120

    # Tentukan path keluaran
    if keluaran:
        out_path = Path(keluaran)
    else:
        tanggal_str = datetime.now().strftime("%Y%m%d")
        out_path = Path(f"lembar_sampling_{tanggal_str}.xlsx")

    # Pastikan parent direktori ada
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)

    return {
        "dokumen_diproses": dokumen_diproses,
        "dokumen_dilewati": dokumen_dilewati,
        "temuan_dilewati_pembanding_nonaktif": temuan_dilewati_pembanding_nonaktif,
        "sampel_ditulis": sampel_ditulis,
        "path_keluaran": str(out_path.resolve()),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Membuat lembar kerja Excel (.xlsx) sampling validasi manual DPEA dari hasil harmonisasi tersimpan."
    )
    parser.add_argument(
        "--document-id",
        dest="document_ids",
        type=int,
        action="append",
        required=True,
        help="ID dokumen draf kajian (boleh diulang untuk banyak dokumen)",
    )
    parser.add_argument(
        "--per-dokumen",
        type=int,
        default=3,
        help="Jumlah sampel temuan per dokumen (default: 3)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed bilangan acak untuk reprodusibilitas (default: 42)",
    )
    parser.add_argument(
        "--keluaran",
        type=str,
        default=None,
        help="Path berkas xlsx keluaran (default: lembar_sampling_<YYYYMMDD>.xlsx)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Base URL untuk tautan PDF absolut (opsional)",
    )

    args = parser.parse_args()

    engine = create_engine(str(settings.database_url))
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        hasil = jalankan_buat_lembar_sampling(
            db=db,
            document_ids=args.document_ids,
            per_dokumen=args.per_dokumen,
            seed=args.seed,
            keluaran=args.keluaran,
            base_url=args.base_url,
        )

        print(PESAN_PERINGATAN_NON_PUBLIK)
        print("=== Ringkasan Pembuatan Lembar Sampling ===")
        print(f"Dokumen diproses : {hasil['dokumen_diproses']}")
        print(f"Dokumen dilewati : {hasil['dokumen_dilewati']}")
        print(f"Temuan dilewati (pembanding nonaktif): {hasil['temuan_dilewati_pembanding_nonaktif']}")
        print(f"Sampel ditulis   : {hasil['sampel_ditulis']}")
        print(f"Path keluaran    : {hasil['path_keluaran']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
