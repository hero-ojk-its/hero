"""
scripts/fix_document_filenames_step12c.py
Skrip perbaikan nomor regulasi terpotong, nama berkas yang kehilangan garis miring,
dan dokumen dengan nama NA_NA_NA.pdf (Langkah 12c).

Mendukung:
- Mode --dry-run (simulasi tanpa perubahan berkas/database)
- Mode --apply (eksekusi pemindahan berkas fisik, update database, dan pencatatan audit log)

Aturan:
- ID dokumen TIDAK BERUBAH (1-44 tetap utuh).
- Berkas fisik dipindahkan ke path baru yang konsisten.
- Perubahan dicatat ke tabel audit_logs dengan action UPDATE_METADATA.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

# Tambahkan repo root ke sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.config import settings
from app.database import SessionLocal
from app.models.document import Document
from app.models.scan_candidate import ScanCandidate
from app.services.audit_service import record_audit, UPDATE_METADATA
from app.services.naming_service import NamingInput, build_standard_filename


def process_fixes(dry_run: bool = True) -> int:
    storage_dir = Path(settings.storage_path)
    db = SessionLocal()

    print("=" * 80)
    print(f"HERO BACKEND - PERBAIKAN NOMOR REGULASI & NAMA BERKAS (LANGKAH 12c)")
    print(f"Mode         : {'DRY-RUN (Simulasi saja)' if dry_run else 'APPLY (Eksekusi nyata)'}")
    print(f"Storage Path : {storage_dir}")
    print("=" * 80)

    # 1. Dokumen yang menjadi target koreksi
    # Dokumen 43: Nomor terpotong 03/2015 -> 27/POJK.03/2015
    # Dokumen 44: Garis miring hilang 26POJK.042014 -> 26-POJK.04-2014
    # Dokumen 36: NA_NA_NA.pdf -> Judul riil dengan nama terpotong rapi
    # Dokumen 31: NA_PADK_2015.pdf -> Judul riil dengan nama terpotong rapi
    target_doc_ids = [36, 43, 44, 31]

    changes_count = 0

    try:
        for doc_id in target_doc_ids:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                print(f"[LEWAT] Dokumen ID {doc_id} tidak ditemukan.")
                continue

            old_reg_num = doc.regulation_number
            old_std_fn = doc.standardized_filename
            old_rel_path = doc.file_path_pdf
            old_full_path = storage_dir / old_rel_path if old_rel_path else None

            # Hitung nilai perbaikan
            new_reg_num = old_reg_num
            if doc_id == 43:
                new_reg_num = "27/POJK.03/2015"

            # Hitung standardized_filename baru menggunakan naming_service
            naming_fmt = doc.naming_format or ["nama", "jenis", "tahun"]
            naming_sep = doc.naming_separator or "_"

            inp = NamingInput(
                regulation_number=new_reg_num,
                title=doc.title,
                regulation_type=doc.regulation_type,
                release_date=doc.release_date,
                bidang=doc.bidang,
                original_filename=doc.original_filename,
                regulation_year=doc.regulation_year,
            )
            new_std_fn = build_standard_filename(
                inp,
                naming_format=naming_fmt,
                naming_separator=naming_sep,
                wildcard=settings.naming_wildcard,
                max_length=settings.naming_max_length,
            )

            # Hitung path fisik baru
            new_rel_path = old_rel_path
            if old_rel_path:
                old_path_obj = Path(old_rel_path)
                parent_dir = old_path_obj.parent
                if "pdf/_inbox" in str(parent_dir).replace("\\", "/"):
                    # Folder staging inbox mempertahankan suffix hash
                    hash_part = old_path_obj.stem.split("__")[-1] if "__" in old_path_obj.stem else "nohash"
                    new_inbox_stem = Path(new_std_fn).stem
                    new_rel_path = f"{parent_dir.as_posix()}/{new_inbox_stem}__{hash_part}.pdf"
                else:
                    new_rel_path = f"{parent_dir.as_posix()}/{new_std_fn}"

            new_full_path = storage_dir / new_rel_path if new_rel_path else None

            needs_update = (
                new_reg_num != old_reg_num
                or new_std_fn != old_std_fn
                or new_rel_path != old_rel_path
            )

            if not needs_update:
                print(f"[OK] Dokumen ID {doc_id} sudah sesuai (tidak memerlukan perubahan).")
                continue

            changes_count += 1
            print(f"\n[PERUBAHAN] Dokumen ID {doc_id} ({doc.title[:60]}...):")
            if new_reg_num != old_reg_num:
                print(f"  Nomor Regulasi : {old_reg_num} -> {new_reg_num}")
            if new_std_fn != old_std_fn:
                print(f"  Standard Filename: {old_std_fn}")
                print(f"                  -> {new_std_fn}")
            if new_rel_path != old_rel_path:
                print(f"  Path Relatif   : {old_rel_path}")
                print(f"                -> {new_rel_path}")
            if old_full_path:
                print(f"  Berkas fisik ada: {old_full_path.exists()} ({old_full_path})")

            if not dry_run:
                # 1. Pindahkan berkas fisik jika ada
                if old_full_path and old_full_path.exists() and new_full_path:
                    new_full_path.parent.mkdir(parents=True, exist_ok=True)
                    if old_full_path != new_full_path:
                        shutil.move(str(old_full_path), str(new_full_path))
                        print(f"  -> Berkas fisik berhasil dipindahkan ke: {new_full_path}")

                # 2. Update metadata dokumen di database
                doc.regulation_number = new_reg_num
                doc.standardized_filename = new_std_fn
                doc.file_path_pdf = new_rel_path

                # 3. Catat entri audit log
                audit_detail = {
                    "reason": "Langkah 12c perbaikan nomor dan nama berkas",
                    "old_regulation_number": old_reg_num,
                    "new_regulation_number": new_reg_num,
                    "old_standardized_filename": old_std_fn,
                    "new_standardized_filename": new_std_fn,
                    "old_file_path_pdf": old_rel_path,
                    "new_file_path_pdf": new_rel_path,
                }
                record_audit(
                    db,
                    action=UPDATE_METADATA,
                    target_resource=f"document:{doc.id}",
                    detail=audit_detail,
                    commit=False,
                )

        # Perbarui juga nomor kandidat scan yang terpotong di DB
        cand_updates = [
            (522, "27/POJK.03/2015"),
            (523, "27/POJK.03/2015"),
            (524, "27/POJK.03/2015"),
            (514, "56/SEOJK.03/2017"),
        ]
        print("\n--- Pemeriksaan Kandidat Scan Database ---")
        for cid, expected_num in cand_updates:
            cand = db.query(ScanCandidate).filter(ScanCandidate.id == cid).first()
            if cand and cand.regulation_number != expected_num:
                print(f"  Kandidat ID {cid}: {cand.regulation_number} -> {expected_num}")
                if not dry_run:
                    cand.regulation_number = expected_num

        if not dry_run:
            db.commit()
            print("\n[SUKSES] Seluruh perubahan berhasil di-commit ke database.")
        else:
            print("\n[SIMULASI SELESAI] Tidak ada berkas maupun database yang diubah.")

    finally:
        db.close()

    return changes_count


def main():
    parser = argparse.ArgumentParser(description="Perbaikan nama berkas dan nomor regulasi HERO (Langkah 12c).")
    parser.add_argument("--apply", action="store_true", help="Terapkan perubahan (default: dry-run).")
    parser.add_argument("--dry-run", action="store_true", help="Jalankan simulasi tanpa perubahan.")
    args = parser.parse_args()

    is_dry_run = not args.apply or args.dry_run
    process_fixes(dry_run=is_dry_run)


if __name__ == "__main__":
    main()
