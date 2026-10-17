"""
scripts/recompute_status.py
Skrip CLI untuk menjalankan perhitungan ulang status keberlakuan dokumen aktif (Langkah 19).
Mengevaluasi relasi hukum dan tanggal mulai berlaku (effective_date).

Penggunaan:
  python scripts/recompute_status.py [--dry-run | --apply]
  (Bawaan: --dry-run)
"""
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any

# Pastikan root proyek masuk ke sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Pastikan UTF-8 di Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.document import Document
from app.services.version_service import recompute_status

DATABASE_URL = settings.database_url
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def run_recompute(db: Session, apply: bool = False) -> Dict[str, Any]:
    dry_run = not apply
    mode_str = "APPLY (menerapkan perubahan ke database)" if apply else "DRY-RUN (bawaan - simulasi tanpa perubahan DB)"
    print(f"=== Menjalankan Perhitungan Ulang Status Dokumen [{mode_str}] ===")

    # Ambil semua dokumen aktif
    active_docs = (
        db.query(Document)
        .filter(Document.is_active == True)  # noqa: E712
        .order_by(Document.id.asc())
        .all()
    )
    total_docs = len(active_docs)
    print(f"Total dokumen aktif di database: {total_docs}")

    # Rekam status sebelum recompute untuk pelaporan perubahan
    doc_initial_state: Dict[int, Dict[str, Any]] = {}
    for doc in active_docs:
        doc_initial_state[doc.id] = {
            "title": doc.title,
            "identity_key": doc.identity_key,
            "status_keberlakuan": doc.status_keberlakuan,
            "status_source": doc.status_source,
            "effective_date": doc.effective_date,
        }

    # Jalankan recompute_status tanpa langsung auto-commit
    recompute_status(db, active_docs, commit=False)

    # Identifikasi dokumen mana saja yang berubah
    changed_items: List[Dict[str, Any]] = []
    for doc in active_docs:
        init = doc_initial_state[doc.id]
        if doc.status_keberlakuan != init["status_keberlakuan"] or doc.status_source != init["status_source"]:
            changed_items.append({
                "id": doc.id,
                "title": doc.title,
                "identity_key": doc.identity_key,
                "effective_date": str(doc.effective_date) if doc.effective_date else "-",
                "before_status": init["status_keberlakuan"].value if hasattr(init["status_keberlakuan"], "value") else str(init["status_keberlakuan"]),
                "after_status": doc.status_keberlakuan.value if hasattr(doc.status_keberlakuan, "value") else str(doc.status_keberlakuan),
                "before_source": init["status_source"] or "None",
                "after_source": doc.status_source or "None",
            })

    print(f"Jumlah dokumen yang terpengaruh/kandidat perubahan: {len(changed_items)}")

    if changed_items:
        print("\nRincian perubahan status dokumen:")
        for item in changed_items:
            print(
                f"  - [ID {item['id']}] {item['title'][:40]}... "
                f"({item['identity_key'] or 'tanpa-kunci'} | eff: {item['effective_date']}): "
                f"{item['before_status']} ({item['before_source']}) -> "
                f"{item['after_status']} ({item['after_source']})"
            )
    else:
        print("Tidak ada dokumen yang memerlukan perubahan status.")

    if apply:
        db.commit()
        print("\n[OK] Perubahan berhasil diterapkan dan di-commit ke database.")
    else:
        db.rollback()
        print("\n[DRY-RUN] Database di-rollback. Tidak ada perubahan yang disimpan ke database.")

    return {
        "total_active_docs": total_docs,
        "changed_count": len(changed_items),
        "changed_items": changed_items,
        "dry_run": dry_run,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Hitung ulang status keberlakuan dokumen aktif berdasarkan relasi dan tanggal berlaku."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--apply",
        action="store_true",
        help="Terapkan perubahan status ke database.",
    )
    group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Simulasi perubahan tanpa menyentuh isi database (default).",
    )

    args = parser.parse_args()
    apply = args.apply

    db = SessionLocal()
    try:
        run_recompute(db, apply=apply)
    finally:
        db.close()


if __name__ == "__main__":
    main()
