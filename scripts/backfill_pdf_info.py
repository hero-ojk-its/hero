"""
scripts/backfill_pdf_info.py
Skrip pengisian susulan (backfill) atribut pdf_terproteksi dan page_count untuk dokumen
yang tersimpan di StorageService dengan pdf_terproteksi IS NULL.

Aturan:
- Default --dry-run (hanya memeriksa dan mencetak jumlah).
- Flag --apply untuk menyimpan perubahan ke database.
- Flag --limit N untuk membatasi jumlah baris yang diproses.
- Commit per 100 dokumen saat --apply.
- PDF yang rusak / tidak bisa dibuka dilewati dan dihitung, status dokumen tidak diubah.
- Tidak mencetak isi dokumen ke konsol.
"""
import argparse
import sys
from pathlib import Path
from typing import Dict, Optional

# Pastikan root proyek masuk ke sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Pastikan output konsol UTF-8 di Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.document import Document
from app.services.file_validation import validate_pdf, FileValidationError
from app.services.storage_service import StorageService


def run_backfill(
    db: Session,
    storage: StorageService,
    apply: bool = False,
    limit: Optional[int] = None,
    batch_size: int = 100,
) -> Dict[str, int]:
    mode_str = "APPLY" if apply else "DRY-RUN (bawaan - tanpa perubahan DB)"
    print(f"=== Menjalankan Backfill PDF Info [{mode_str}] ===")

    query = (
        db.query(Document)
        .filter(Document.pdf_terproteksi.is_(None))
        .filter(Document.file_path_pdf.isnot(None))
        .order_by(Document.id.asc())
    )
    if limit is not None and limit > 0:
        query = query.limit(limit)

    docs = query.all()
    total_candidates = len(docs)
    print(f"Kandidat dokumen (pdf_terproteksi IS NULL): {total_candidates}")

    stats = {
        "kandidat": total_candidates,
        "diproses": 0,
        "terproteksi": 0,
        "tidak_terproteksi": 0,
        "dilewati_rusak": 0,
        "page_count_diisi": 0,
    }

    pending_commits = 0

    for doc in docs:
        stats["diproses"] += 1
        try:
            if not doc.file_path_pdf or not storage.exists(doc.file_path_pdf):
                stats["dilewati_rusak"] += 1
                continue

            content = storage.read_pdf(doc.file_path_pdf)
            info = validate_pdf(doc.original_filename or "dokumen.pdf", content, settings.max_upload_bytes)

            if info.terproteksi:
                stats["terproteksi"] += 1
            else:
                stats["tidak_terproteksi"] += 1

            if apply:
                doc.pdf_terproteksi = info.terproteksi
                if doc.page_count is None:
                    doc.page_count = info.jumlah_halaman
                    stats["page_count_diisi"] += 1
                pending_commits += 1

                if pending_commits >= batch_size:
                    db.commit()
                    pending_commits = 0
            else:
                if doc.page_count is None:
                    stats["page_count_diisi"] += 1

        except (FileValidationError, Exception):
            # PDF rusak atau tidak bisa dibuka: lewati dan hitung, jangan ubah status dokumen
            stats["dilewati_rusak"] += 1
            continue

    if apply and pending_commits > 0:
        db.commit()

    print("=== Ringkasan Hasil Backfill ===")
    print(f"Mode                : {mode_str}")
    print(f"Kandidat ditemukan  : {stats['kandidat']}")
    print(f"Total diproses      : {stats['diproses']}")
    print(f"PDF terproteksi     : {stats['terproteksi']}")
    print(f"PDF biasa           : {stats['tidak_terproteksi']}")
    print(f"Dilewati (rusak/dll): {stats['dilewati_rusak']}")
    print(f"Page count diisi    : {stats['page_count_diisi']}")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill pdf_terproteksi dan page_count dokumen PDF tersimpan.")
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Simpan perubahan ke database (default: dry-run tanpa mengubah database).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Hanya memeriksa tanpa mengubah database (default).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Batas maksimal dokumen yang diproses.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Jumlah dokumen per commit saat --apply (default: 100).",
    )
    args = parser.parse_args()

    apply = bool(args.apply and not args.dry_run)

    database_url = settings.database_url
    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    storage = StorageService(base_path=settings.storage_path)

    try:
        run_backfill(
            db=db,
            storage=storage,
            apply=apply,
            limit=args.limit,
            batch_size=args.batch_size,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
