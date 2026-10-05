"""
scripts/fix_folder_jan1_dates.py
Skrip perbaikan tanggal karangan (1 Januari) untuk dokumen dan kandidat pindaian folder lokal (Langkah 12e).

Mendukung:
- Mode --dry-run (default, simulasi tanpa modifikasi database)
- Mode --apply (eksekusi perubahan database dan pencatatan audit log)

Aturan:
- Target: Dokumen dan ScanCandidate dengan source_url/url diawali 'file://' dan release_date bertanggal 1 Januari.
- release_date diubah menjadi NULL.
- regulation_year dipastikan terisi bila kosong.
- standardized_filename TIDAK diubah.
- Perubahan dokumen dicatat ke tabel audit_logs dengan action UPDATE_METADATA.
"""
import argparse
import sys
from pathlib import Path

# Tambahkan repo root ke sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.database import SessionLocal
from app.models.document import Document
from app.models.scan_candidate import ScanCandidate
from app.services.audit_service import record_audit, UPDATE_METADATA
from app.crawlers.url_utils import extract_regulation_year


def run_fix(dry_run: bool = True) -> int:
    db = SessionLocal()
    print("=" * 80)
    print("HERO BACKEND - PERBAIKAN TANGGAL 1 JANUARI FOLDER LOKAL (LANGKAH 12e)")
    print(f"Mode : {'DRY-RUN (Simulasi saja)' if dry_run else 'APPLY (Eksekusi nyata)'}")
    print("=" * 80)

    total_doc_fixed = 0
    total_cand_fixed = 0

    try:
        # 1. Dokumen sumber folder lokal (file://) dengan release_date 1 Januari
        all_local_docs = db.query(Document).filter(Document.source_url.like("file://%")).all()
        target_docs = [
            d for d in all_local_docs
            if d.release_date and d.release_date.month == 1 and d.release_date.day == 1
        ]

        print(f"\n[DOKUMEN] Ditemukan {len(target_docs)} dokumen ber-source_url 'file://' dengan release_date 1 Januari:")
        for doc in target_docs:
            old_rel_date = doc.release_date
            old_reg_year = doc.regulation_year

            # Pastikan regulation_year terisi bila kosong
            new_reg_year = old_reg_year or (old_rel_date.year if old_rel_date else None) or extract_regulation_year(
                regulation_number=doc.regulation_number,
                title=doc.title,
                filename=doc.original_filename or doc.standardized_filename,
            )

            print(f"  - Dokumen ID {doc.id}:")
            print(f"      Title               : {doc.title}")
            print(f"      Source URL          : {doc.source_url}")
            print(f"      Standard Filename   : {doc.standardized_filename} (TIDAK DIUBAH)")
            print(f"      Release Date        : {old_rel_date} -> None")
            print(f"      Regulation Year     : {old_reg_year} -> {new_reg_year}")

            if not dry_run:
                doc.release_date = None
                doc.regulation_year = new_reg_year

                # Catat ke audit_log
                audit_detail = {
                    "reason": "Langkah 12e pembersihan tanggal karangan 1 Januari folder lokal",
                    "old_release_date": str(old_rel_date),
                    "new_release_date": None,
                    "old_regulation_year": old_reg_year,
                    "new_regulation_year": new_reg_year,
                    "standardized_filename": doc.standardized_filename,
                }
                record_audit(
                    db,
                    action=UPDATE_METADATA,
                    target_resource=f"document:{doc.id}",
                    detail=audit_detail,
                    commit=False,
                )
            total_doc_fixed += 1

        # 2. Kandidat pemindaian (ScanCandidate) folder lokal
        all_cands = (
            db.query(ScanCandidate)
            .filter(
                (ScanCandidate.url.like("file://%")) | (ScanCandidate.found_on_page.like("folder://%"))
            )
            .all()
        )
        target_cands = [
            c for c in all_cands
            if c.release_date and c.release_date.month == 1 and c.release_date.day == 1
        ]

        print(f"\n[KANDIDAT SCAN] Ditemukan {len(target_cands)} kandidat folder lokal dengan release_date 1 Januari:")
        for cand in target_cands:
            old_c_date = cand.release_date
            old_c_year = cand.regulation_year
            new_c_year = old_c_year or (old_c_date.year if old_c_date else None) or extract_regulation_year(
                regulation_number=cand.regulation_number,
                title=cand.document_title,
                filename=cand.filename,
            )

            print(f"  - Kandidat ID {cand.id} (Scan ID {cand.scan_id}):")
            print(f"      Filename        : {cand.filename}")
            print(f"      Release Date    : {old_c_date} -> None")
            print(f"      Regulation Year : {old_c_year} -> {new_c_year}")

            if not dry_run:
                cand.release_date = None
                cand.regulation_year = new_c_year

            total_cand_fixed += 1

        if not dry_run:
            db.commit()
            print("\n" + "=" * 80)
            print(f"[SUKSES] Berhasil menerapkan perbaikan ke database:")
            print(f"  - Dokumen diperbarui : {total_doc_fixed}")
            print(f"  - Kandidat diperbarui: {total_cand_fixed}")
            print("=" * 80)
        else:
            print("\n" + "=" * 80)
            print(f"[SIMULASI SELESAI] Target perbaikan:")
            print(f"  - Dokumen target : {total_doc_fixed}")
            print(f"  - Kandidat target: {total_cand_fixed}")
            print("  Tidak ada data database yang diubah.")
            print("=" * 80)

    finally:
        db.close()

    return total_doc_fixed + total_cand_fixed


def main():
    parser = argparse.ArgumentParser(description="Perbaikan tanggal 1 Januari folder lokal (Langkah 12e).")
    parser.add_argument("--apply", action="store_true", help="Terapkan perubahan ke database (default: dry-run).")
    parser.add_argument("--dry-run", action="store_true", help="Jalankan simulasi tanpa perubahan.")
    args = parser.parse_args()

    is_dry_run = not args.apply or args.dry_run
    run_fix(dry_run=is_dry_run)


if __name__ == "__main__":
    main()
