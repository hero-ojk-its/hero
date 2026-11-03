"""
scripts/relokasi_kategori.py
Skrip perbaikan relokasi kategori otomatis untuk dokumen aktif di KB.
Mencari dokumen aktif dengan kategori_manual=false, sudah di kb/, dan metadata cukup
(is_metadata_sufficient), yang path kategori sekarang != hasil category_segments_for.

Aturan:
- Default --dry-run (mencetak id | path_kategori_lama -> path_kategori_baru dan jumlahnya, tanpa mencetak isi dokumen).
- --apply: memanggil place(doc, force=True) per dokumen, commit per dokumen, mencatat yang gagal, dan meringkas dipindah / gagal / dilewati.
- --limit N: urutkan berdasarkan id.
"""
import argparse
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple, List

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
from app.models.category import Category
from app.models.document import Document
from app.services.category_service import CategoryService
from app.services.naming_service import NamingInput, is_metadata_sufficient
from app.services.placement_service import PlacementService
from app.services.storage_service import StorageService


def run_relokasi(
    db: Session,
    storage: StorageService,
    apply: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, int]:
    mode_str = "APPLY" if apply else "DRY-RUN (bawaan - tanpa perubahan DB)"
    print(f"=== Menjalankan Relokasi Kategori [{mode_str}] ===")

    cat_svc = CategoryService(db)
    place_svc = PlacementService(db, storage, cat_svc, settings)

    query = (
        db.query(Document)
        .filter(
            Document.is_active == True,  # noqa: E712
            Document.kategori_manual == False,  # noqa: E712
            Document.file_path_pdf.isnot(None),
        )
        .order_by(Document.id.asc())
    )

    all_docs = query.all()

    candidates: List[Tuple[Document, str, str]] = []
    dilewati = 0

    for doc in all_docs:
        # Hanya dokumen yang sudah di kb/
        clean_path = doc.file_path_pdf.replace("\\", "/") if doc.file_path_pdf else ""
        if not clean_path.startswith("kb/"):
            dilewati += 1
            continue

        # Cek kecukupan metadata
        inp = NamingInput(
            regulation_number=doc.regulation_number,
            title=doc.title,
            regulation_type=doc.regulation_type,
            release_date=doc.release_date,
            bidang=doc.bidang,
            original_filename=doc.original_filename,
            regulation_year=doc.regulation_year,
        )
        if not is_metadata_sufficient(inp):
            dilewati += 1
            continue

        target_segs = cat_svc.category_segments_for(doc)
        target_path = "/".join(target_segs)

        current_cat = (
            db.query(Category).filter(Category.id == doc.category_id).first()
            if doc.category_id
            else None
        )
        current_path = "/".join(cat_svc.path_of(current_cat)) if current_cat else "(tanpa kategori)"

        if current_path != target_path:
            candidates.append((doc, current_path, target_path))
        else:
            dilewati += 1

    if limit is not None and limit > 0:
        candidates = candidates[:limit]

    total_candidates = len(candidates)
    print(f"Kandidat dokumen perlu relokasi: {total_candidates}")

    dipindah = 0
    gagal = 0

    for doc, current_path, target_path in candidates:
        if not apply:
            print(f"Dokumen {doc.id} | {current_path} -> {target_path}")
        else:
            try:
                res = place_svc.place(doc, force=True)
                if res.placed:
                    dipindah += 1
                    print(f"Dokumen {doc.id} | {current_path} -> {target_path} | DIPINDAH")
                else:
                    gagal += 1
                    print(f"Dokumen {doc.id} | {current_path} -> {target_path} | GAGAL: {res.reason}")
            except Exception as exc:
                gagal += 1
                print(f"Dokumen {doc.id} | {current_path} -> {target_path} | GAGAL: {exc}")

    print("=== Ringkasan Hasil Relokasi ===")
    print(f"Mode                : {mode_str}")
    print(f"Kandidat ditemukan  : {total_candidates}")
    print(f"Dipindah            : {dipindah}")
    print(f"Gagal               : {gagal}")
    print(f"Dilewati            : {dilewati}")

    return {
        "kandidat": total_candidates,
        "dipindah": dipindah,
        "gagal": gagal,
        "dilewati": dilewati,
    }


def main():
    parser = argparse.ArgumentParser(description="Relokasi otomatis folder kategori dokumen KB.")
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Simpan perubahan dan pindahkan berkas fisik (default: dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Hanya periksa tanpa mengubah data (bawaan jika --apply tidak diberikan)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Batasi jumlah dokumen kandidat yang diproses",
    )
    args = parser.parse_args()

    apply = args.apply
    if args.dry_run and not args.apply:
        apply = False

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine)
    storage = StorageService(base_path=settings.storage_path)

    with session_factory() as db:
        run_relokasi(db=db, storage=storage, apply=apply, limit=args.limit)


if __name__ == "__main__":
    main()

