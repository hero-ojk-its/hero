#!/usr/bin/env python3
"""
scripts/demo_reset.py
Skrip untuk mengosongkan data operasional HERO Backend demi keperluan persiapan demo,
dengan mempertahankan struktur kategori awal, tabel users, dan riwayat migrasi Alembic.

Penggunaan:
    python scripts/demo_reset.py --yes
    python scripts/demo_reset.py --yes --i-understand-production  (jika di production)
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

# Pastikan root workspace ada di sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import text
from app.config import settings
from app.database import SessionLocal, seed_initial_categories


OPERATIONAL_TABLES = [
    "article_references",
    "legal_references",
    "articles",
    "ingest_failures",
    "scan_candidates",
    "scan_sessions",
    "source_files",
    "job_ingest",
    "documents",
    "scraping_sources",
    "audit_logs",
]

STORAGE_SUBDIRS = [
    "pdf/_inbox",
    "kb",
    "quarantine",
    "exports",
]


def check_table_counts(db) -> dict:
    counts = {}
    for tbl in OPERATIONAL_TABLES:
        try:
            cnt = db.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            counts[tbl] = cnt
        except Exception:
            counts[tbl] = 0
    return counts


def reset_storage(storage_root: Path):
    for sub in STORAGE_SUBDIRS:
        target = storage_root / sub
        if target.exists():
            for item in target.iterdir():
                if item.name.startswith("."):
                    continue
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception as e:
                    print(f"  [WARN] Gagal menghapus storage {item}: {e}")
        else:
            target.mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Reset data operasional HERO Backend untuk demo.")
    parser.add_argument("--yes", action="store_true", help="Konfirmasi eksekusi reset secara eksplisit.")
    parser.add_argument(
        "--i-understand-production",
        action="store_true",
        help="Flag wajib jika dijalankan pada lingkungan APP_ENV=production.",
    )
    args = parser.parse_args()

    print("=================================================================")
    print("HERO BACKEND - DEMO DATA RESET UTILITY")
    print(f"Environment aktif : {settings.app_env}")
    print(f"Database target   : {settings.postgres_db} @ {settings.postgres_host}")
    print(f"Storage path      : {settings.storage_path}")
    print("=================================================================")

    if settings.app_env.lower() == "production" and not args.i_understand_production:
        print("\n[DITOLAK] Aplikasi terkonfigurasi dalam mode PRODUCTION!")
        print("Untuk mereset database production, sertakan flag: --i-understand-production\n")
        sys.exit(1)

    if not args.yes:
        print("\n[DITOLAK] Reset membutuhkan konfirmasi flag --yes.")
        print("Gunakan: python scripts/demo_reset.py --yes\n")
        sys.exit(1)

    print("\nSaran: Pastikan Anda telah melakukan backup sebelum reset data:")
    print("  bash deploy/backup.sh\n")

    db = SessionLocal()
    try:
        counts_before = check_table_counts(db)
        print("Ringkasan data operasional yang akan dihapus:")
        total_rows = 0
        for tbl, cnt in counts_before.items():
            print(f"  - {tbl:<20}: {cnt:>5} baris")
            total_rows += cnt
        print(f"Total baris data  : {total_rows} baris\n")

        print("--> 1/3 Mengosongkan tabel data operasional (TRUNCATE CASCADE)...")
        # Truncate semua tabel operasional secara bersamaan
        tables_str = ", ".join(OPERATIONAL_TABLES)
        db.execute(text(f"TRUNCATE TABLE {tables_str} RESTART IDENTITY CASCADE;"))
        db.commit()
        print("    Tabel database berhasil dikosongkan.")

        print("--> 2/3 Memastikan seeding kategori awal tetap utuh...")
        seed_initial_categories(db)
        print("    Kategori awal terverifikasi.")

        print("--> 3/3 Membersihkan berkas pada direktori storage...")
        storage_root = Path(settings.storage_path)
        reset_storage(storage_root)
        print("    Direktori storage berhasil dibersihkan.")

        print("\n=================================================================")
        print("RESET DEMO SELESAI DENGAN SUKSES!")
        print("Tabel users, categories, dan alembic_version tetap dipertahankan.")
        print("=================================================================\n")
    except Exception as exc:
        db.rollback()
        print(f"\n[ERROR] Terjadi kesalahan saat reset: {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
