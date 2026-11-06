#!/usr/bin/env python3
"""
scripts/periksa_dokumen_non_utama.py
Pemeriksaan dan penonaktifan dokumen non-utama (abstrak, faq, lampiran, non_regulasi) yang telanjur masuk KB (Langkah 37).

Pemakaian:
    python scripts/periksa_dokumen_non_utama.py [--apply] [--jenis abstrak,faq,...]

Aturan:
- Default adalah DRY-RUN (hanya-baca, tanpa perubahan DB).
- Dokumen dengan koreksi manual (metadata_corrected_at terisi) dilewati dan dilaporkan terpisah.
- Opsi --apply menonaktifkan dokumen dengan alasan "bukan_dokumen_utama" dan mencatat audit DEACTIVATE_DOCUMENT.
  Dokumen tidak dihapus dari basis data sehingga dapat diaktifkan kembali secara administratif jika diperlukan.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Set

# Pastikan root proyek masuk sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Pastikan output konsol mendukung UTF-8 di Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.document import Document
from app.models.scan_candidate import ScanCandidate
from app.services.scan_service import NON_UTAMA_DOC_KINDS
from app.crawlers.url_utils import determine_doc_kind
from app.services.document_service import deactivate_document


@dataclass
class TemuanNonUtama:
    document: Document
    doc_kind: str
    sumber_deteksi: str  # "kandidat" | "nama berkas" | "judul" | kombinasi
    terkoreksi_manual: bool


def periksa_dokumen_non_utama(
    db: Session,
    apply: bool = False,
    jenis_filter: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Memeriksa dokumen aktif di KB yang tergolong non-utama.
    Mendukung pengujian dengan injeksi session database.
    """
    allowed_kinds = jenis_filter if jenis_filter is not None else set(NON_UTAMA_DOC_KINDS)

    # 1. Ambil seluruh dokumen aktif
    active_docs = (
        db.query(Document)
        .filter(Document.is_active == True)
        .order_by(Document.id.asc())
        .all()
    )

    # 2. Ambil peta kandidat scan yang menautkan dokumen ke kandidat
    candidates = (
        db.query(ScanCandidate)
        .filter(ScanCandidate.document_id.isnot(None))
        .all()
    )
    cand_by_doc_id: Dict[int, List[ScanCandidate]] = {}
    for c in candidates:
        if c.document_id is not None:
            cand_by_doc_id.setdefault(c.document_id, []).append(c)

    temuan_list: List[TemuanNonUtama] = []
    dilewati_manual_list: List[TemuanNonUtama] = []

    for doc in active_docs:
        sumber_list = []
        detected_kind = None

        # A. Cek dari scan_candidates
        cands = cand_by_doc_id.get(doc.id, [])
        for c in cands:
            c_kind = (c.doc_kind or "").strip().lower()
            if c_kind in allowed_kinds:
                detected_kind = c_kind
                sumber_list.append("kandidat")
                break

        # B. Cek dari original_filename
        kind_fn = determine_doc_kind(doc.original_filename)
        if kind_fn in allowed_kinds:
            if not detected_kind:
                detected_kind = kind_fn
            sumber_list.append("nama berkas")

        # C. Cek dari title
        kind_title = determine_doc_kind(doc.title)
        if kind_title in allowed_kinds:
            if not detected_kind:
                detected_kind = kind_title
            sumber_list.append("judul")

        if detected_kind and sumber_list:
            is_manual = doc.metadata_corrected_at is not None
            temuan = TemuanNonUtama(
                document=doc,
                doc_kind=detected_kind,
                sumber_deteksi="/".join(sumber_list),
                terkoreksi_manual=is_manual,
            )
            if is_manual:
                dilewati_manual_list.append(temuan)
            else:
                temuan_list.append(temuan)

    # Hitung jumlah per jenis
    jumlah_per_jenis: Dict[str, int] = {k: 0 for k in sorted(allowed_kinds)}
    for t in temuan_list:
        jumlah_per_jenis[t.doc_kind] = jumlah_per_jenis.get(t.doc_kind, 0) + 1

    # Cetak laporan
    mode_str = "APPLY (Menonaktifkan Dokumen)" if apply else "DRY-RUN (Hanya Tinjauan)"
    print("\n" + "=" * 105)
    print("               PEMERIKSAAN DOKUMEN NON-UTAMA DI KNOWLEDGE BASE (KB)")
    print(f"               Mode: {mode_str}")
    print("=" * 105)

    if temuan_list:
        print(f"{'ID':<6} | {'Jenis':<12} | {'Sumber Deteksi':<20} | {'Judul (60 Karakter)':<60} | {'Nama Berkas'}")
        print("-" * 105)
        for t in temuan_list:
            d = t.document
            title_trunc = (d.title or "-")[:60]
            fn = d.original_filename or "-"
            print(f"{d.id:<6} | {t.doc_kind:<12} | {t.sumber_deteksi:<20} | {title_trunc:<60} | {fn}")
        print("-" * 105)
    else:
        print("Tidak ditemukan dokumen non-utama yang perlu dinonaktifkan.")

    breakdown_str = ", ".join(f"{k}: {v}" for k, v in sorted(jumlah_per_jenis.items()))
    print(f"Total Dokumen Ditemukan : {len(temuan_list)} ({breakdown_str})")

    if dilewati_manual_list:
        print("\n" + "-" * 105)
        print(f"DOKUMEN DILEWATI (Koreksi Manual - Terindikasi Sengaja Dimasukkan Admin): {len(dilewati_manual_list)}")
        print(f"{'ID':<6} | {'Jenis':<12} | {'Sumber Deteksi':<20} | {'Judul (60 Karakter)':<60} | {'Dibuat / Dikoreksi'}")
        print("-" * 105)
        for t in dilewati_manual_list:
            d = t.document
            title_trunc = (d.title or "-")[:60]
            waktu_str = d.metadata_corrected_at.isoformat() if d.metadata_corrected_at else "-"
            print(f"{d.id:<6} | {t.doc_kind:<12} | {t.sumber_deteksi:<20} | {title_trunc:<60} | {waktu_str}")
        print("-" * 105)

    dinonaktifkan_count = 0
    if apply and temuan_list:
        print("\nMenonaktifkan dokumen...")
        for t in temuan_list:
            changed = deactivate_document(
                db=db,
                document=t.document,
                reason="bukan_dokumen_utama",
                commit=False,
            )
            if changed:
                dinonaktifkan_count += 1
        db.commit()
        print(f"SUKSES: {dinonaktifkan_count} dokumen berhasil dinonaktifkan (alasan: 'bukan_dokumen_utama').")
    elif not apply and temuan_list:
        print("\n[DRY-RUN] Tidak ada data dokumen yang diubah. Jalankan dengan --apply untuk menonaktifkan.")

    print("=" * 105 + "\n")

    return {
        "total_target": len(temuan_list),
        "total_dilewati_manual": len(dilewati_manual_list),
        "total_dinonaktifkan": dinonaktifkan_count,
        "jumlah_per_jenis": jumlah_per_jenis,
        "target_ids": [t.document.id for t in temuan_list],
        "manual_ids": [t.document.id for t in dilewati_manual_list],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pemeriksaan dan penonaktifan dokumen non-utama (abstrak, faq, lampiran, non_regulasi) di KB",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Nonaktifkan dokumen non-utama yang ditemukan (default: False / DRY-RUN)",
    )
    parser.add_argument(
        "--jenis",
        type=str,
        default=None,
        help="Batasi jenis dokumen non-utama yang diproses (dipisah koma, contoh: abstrak,faq)",
    )

    args = parser.parse_args()

    jenis_filter = None
    if args.jenis:
        jenis_filter = {j.strip().lower() for j in args.jenis.split(",") if j.strip()}
        invalid = jenis_filter - NON_UTAMA_DOC_KINDS
        if invalid:
            print(f"GALAT: Jenis non-utama tidak dikenal: {', '.join(invalid)}")
            print(f"Pilihan valid: {', '.join(sorted(NON_UTAMA_DOC_KINDS))}")
            return 1

    db = SessionLocal()
    try:
        periksa_dokumen_non_utama(db=db, apply=args.apply, jenis_filter=jenis_filter)
        return 0
    except Exception as exc:
        print(f"FATAL: Terjadi galat saat memeriksa dokumen non-utama: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

