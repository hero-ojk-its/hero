#!/usr/bin/env python3
"""
scripts/periksa_konsistensi_pasal.py
Pemeriksaan konsistensi dokumen PDF dan data pasal (articles) di basis data (Langkah 37).

Pemakaian:
    python scripts/periksa_konsistensi_pasal.py [--nonaktifkan-tanpa-pdf] [--antrekan-ulang-tanpa-pasal]

Aturan:
- Default adalah DRY-RUN (hanya-baca, tanpa perubahan DB).
- Kelompok A: Dokumen aktif tanpa berkas PDF fisik di storage.
- Kelompok B: Dokumen aktif ber-PDF status terindeks/perlu_koreksi tetapi tanpa pasal (articles = 0).
- Kelompok C: Baris pasal yatim (dokumen tidak ada atau berstatus nonaktif). Hanya dilaporkan.
- Tindakan eksplisit:
  * --nonaktifkan-tanpa-pdf: menonaktifkan dokumen Kelompok A (alasan: "berkas_pdf_hilang", audit DEACTIVATE_DOCUMENT).
  * --antrekan-ulang-tanpa-pasal: mengembalikan dokumen Kelompok B ke antrean ekstraksi (processing_status="diterima", extraction_claimed_at=None, audit EXTRACTION_REQUEUED).
- Tidak ada penghapusan baris DB atau berkas.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

# Pastikan root proyek masuk sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Pastikan output konsol mendukung UTF-8 di Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.article import Article
from app.models.document import Document
from app.models.enums import StatusPemrosesan
from app.services.document_service import deactivate_document
from app.services.audit_service import EXTRACTION_REQUEUED, record_audit
from app.services.storage_service import StorageService


@dataclass
class ItemKonsistensi:
    document_id: int
    status: str
    judul: str
    file_path_pdf: str
    jumlah_pasal: int


def periksa_konsistensi_pasal(
    db: Session,
    storage: Optional[StorageService] = None,
    nonaktifkan_tanpa_pdf: bool = False,
    antrekan_ulang_tanpa_pasal: bool = False,
) -> Dict[str, Any]:
    """
    Memeriksa konsistensi dokumen PDF terhadap data pasal.
    Mendukung injeksi session DB dan storage service untuk keperluan pengujian.
    """
    if storage is None:
        storage = StorageService(base_path=settings.storage_path)

    # 1. Ambil seluruh dokumen aktif
    active_docs = (
        db.query(Document)
        .filter(Document.is_active == True)
        .order_by(Document.id.asc())
        .all()
    )

    # 2. Hitung jumlah pasal per document_id untuk dokumen aktif
    article_counts_raw = (
        db.query(Article.document_id, func.count(Article.id))
        .group_by(Article.document_id)
        .all()
    )
    counts_by_doc_id: Dict[int, int] = {doc_id: cnt for doc_id, cnt in article_counts_raw}

    kelompok_a: List[ItemKonsistensi] = []
    kelompok_b: List[ItemKonsistensi] = []

    for doc in active_docs:
        pasal_count = counts_by_doc_id.get(doc.id, 0)
        has_file = bool(doc.file_path_pdf and storage.exists(doc.file_path_pdf))
        status_str = doc.processing_status.value if hasattr(doc.processing_status, "value") else str(doc.processing_status or "-")
        judul_60 = (doc.title or "-")[:60]
        fp_str = doc.file_path_pdf or "(kosong)"

        # Kelompok A: Dokumen tanpa berkas PDF
        if not has_file:
            kelompok_a.append(
                ItemKonsistensi(
                    document_id=doc.id,
                    status=status_str,
                    judul=judul_60,
                    file_path_pdf=fp_str,
                    jumlah_pasal=pasal_count,
                )
            )
        else:
            # Kelompok B: Dokumen ber-PDF tanpa pasal (status terindeks atau perlu_koreksi)
            is_candidate_b = doc.processing_status in (
                StatusPemrosesan.terindeks,
                StatusPemrosesan.perlu_koreksi,
                "terindeks",
                "perlu_koreksi",
            )
            if is_candidate_b and pasal_count == 0:
                kelompok_b.append(
                    ItemKonsistensi(
                        document_id=doc.id,
                        status=status_str,
                        judul=judul_60,
                        file_path_pdf=fp_str,
                        jumlah_pasal=0,
                    )
                )

    # 3. Kelompok C: Pasal yatim (dokumen tidak ada atau nonaktif)
    orphan_rows = (
        db.query(Article.document_id, func.count(Article.id), Document.is_active)
        .outerjoin(Document, Article.document_id == Document.id)
        .filter(or_(Document.id.is_(None), Document.is_active == False))
        .group_by(Article.document_id, Document.is_active)
        .all()
    )
    kelompok_c: List[Tuple[int, int, str]] = []
    total_pasal_yatim = 0
    for doc_id, cnt, is_act in orphan_rows:
        status_doc = "nonaktif" if is_act is False else "tidak ada di DB"
        kelompok_c.append((doc_id, cnt, status_doc))
        total_pasal_yatim += cnt

    # Cetak laporan
    print("\n" + "=" * 105)
    print("                     LAPORAN PEMERIKSAAN KONSISTENSI PDF - PASAL")
    print("=" * 105)

    # Kelompok A
    print(f"\n[KELOMPOK A] Dokumen Aktif Tanpa Berkas PDF ({len(kelompok_a)} dokumen):")
    if kelompok_a:
        print(f"{'ID':<6} | {'Status':<14} | {'Judul (60 Karakter)':<60} | {'Jumlah Pasal':<12} | {'File Path PDF'}")
        print("-" * 105)
        for it in kelompok_a:
            print(f"{it.document_id:<6} | {it.status:<14} | {it.judul:<60} | {it.jumlah_pasal:<12} | {it.file_path_pdf}")
    else:
        print("  (Nihil - semua dokumen aktif memiliki berkas PDF di penyimpanan)")

    # Kelompok B
    print(f"\n[KELOMPOK B] Dokumen Ber-PDF Tanpa Pasal ({len(kelompok_b)} dokumen):")
    if kelompok_b:
        print(f"{'ID':<6} | {'Status':<14} | {'Judul (60 Karakter)':<60} | {'Jumlah Pasal':<12} | {'File Path PDF'}")
        print("-" * 105)
        for it in kelompok_b:
            print(f"{it.document_id:<6} | {it.status:<14} | {it.judul:<60} | {it.jumlah_pasal:<12} | {it.file_path_pdf}")
    else:
        print("  (Nihil - tidak ada dokumen terindeks/perlu_koreksi tanpa pasal)")

    # Kelompok C
    print(f"\n[KELOMPOK C] Pasal Yatim ({len(kelompok_c)} grup dokumen, total {total_pasal_yatim} pasal):")
    if kelompok_c:
        print(f"{'Document ID':<14} | {'Jumlah Pasal Yatim':<20} | {'Status Dokumen Induk'}")
        print("-" * 60)
        for d_id, c_count, st_doc in kelompok_c:
            print(f"{d_id:<14} | {c_count:<20} | {st_doc}")
    else:
        print("  (Nihil - tidak ada pasal yatim)")

    print("\n" + "-" * 105)
    print("RINGKASAN JUMLAH:")
    print(f"  - Kelompok A (Tanpa PDF)         : {len(kelompok_a)} dokumen")
    print(f"  - Kelompok B (Ber-PDF tanpa pasal): {len(kelompok_b)} dokumen")
    print(f"  - Kelompok C (Pasal Yatim)       : {total_pasal_yatim} pasal pada {len(kelompok_c)} dokumen")
    print("-" * 105)

    # Eksekusi tindakan jika diminta
    a_deactivated = 0
    if nonaktifkan_tanpa_pdf and kelompok_a:
        print("\n[TINDAKAN] Menonaktifkan dokumen Kelompok A...")
        a_ids = [it.document_id for it in kelompok_a]
        target_docs = db.query(Document).filter(Document.id.in_(a_ids)).all()
        for doc in target_docs:
            changed = deactivate_document(
                db=db,
                document=doc,
                reason="berkas_pdf_hilang",
                commit=False,
            )
            if changed:
                a_deactivated += 1
        db.commit()
        print(f"SUKSES: {a_deactivated} dokumen tanpa berkas PDF berhasil dinonaktifkan.")

    b_requeued = 0
    if antrekan_ulang_tanpa_pasal and kelompok_b:
        print("\n[TINDAKAN] Mengantrekan ulang ekstraksi dokumen Kelompok B...")
        b_ids = [it.document_id for it in kelompok_b]
        target_docs = db.query(Document).filter(Document.id.in_(b_ids)).all()
        for doc in target_docs:
            old_attempts = doc.extraction_attempts or 0
            doc.processing_status = StatusPemrosesan.diterima
            doc.extraction_claimed_at = None
            doc.extraction_attempts = 0
            record_audit(
                db,
                action=EXTRACTION_REQUEUED,
                target_resource=f"document:{doc.id}",
                detail={"reason": "antrekan_ulang_tanpa_pasal", "attempt_sebelumnya": old_attempts},
                commit=False,
            )
            b_requeued += 1
        db.commit()
        print(f"SUKSES: {b_requeued} dokumen ber-PDF tanpa pasal berhasil dikembalikan ke status 'diterima' untuk antrean ekstraksi ulang.")

    if not nonaktifkan_tanpa_pdf and not antrekan_ulang_tanpa_pasal:
        print("[DRY-RUN] Mode tinjauan saja. Tidak ada perubahan status atau antrean pada basis data.")

    print("=" * 105 + "\n")

    return {
        "kelompok_a_count": len(kelompok_a),
        "kelompok_b_count": len(kelompok_b),
        "kelompok_c_doc_count": len(kelompok_c),
        "kelompok_c_article_count": total_pasal_yatim,
        "kelompok_a_ids": [it.document_id for it in kelompok_a],
        "kelompok_b_ids": [it.document_id for it in kelompok_b],
        "kelompok_c": kelompok_c,
        "a_deactivated": a_deactivated,
        "b_requeued": b_requeued,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pemeriksaan konsistensi dokumen PDF dan pasal regulasi di basis data",
    )
    parser.add_argument(
        "--nonaktifkan-tanpa-pdf",
        action="store_true",
        default=False,
        help="Nonaktifkan dokumen aktif yang tidak memiliki berkas PDF fisik (Kelompok A)",
    )
    parser.add_argument(
        "--antrekan-ulang-tanpa-pasal",
        action="store_true",
        default=False,
        help="Kembalikan dokumen ber-PDF tanpa pasal ke antrean ekstraksi (Kelompok B)",
    )

    args = parser.parse_args()

    db = SessionLocal()
    try:
        periksa_konsistensi_pasal(
            db=db,
            nonaktifkan_tanpa_pdf=args.nonaktifkan_tanpa_pdf,
            antrekan_ulang_tanpa_pasal=args.antrekan_ulang_tanpa_pasal,
        )
        return 0
    except Exception as exc:
        print(f"FATAL: Terjadi galat saat memeriksa konsistensi PDF - pasal: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

