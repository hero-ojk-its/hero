#!/usr/bin/env python3
"""
scripts/backfill_status_source.py
Backfill status_source="sumber" untuk dokumen berstatus keberlakuan terisi tanpa status_source (Langkah 38).

Pemakaian:
    python scripts/backfill_status_source.py          # Dry-run default
    python scripts/backfill_status_source.py --apply  # Terapkan perubahan ke database
"""
import argparse
from pathlib import Path
import sys
from typing import Any, Dict, List

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
from app.models.enums import StatusKeberlakuan
from app.services.audit_service import UPDATE_DOCUMENT_STATUS, record_audit


def backfill_status_source(db: Session, apply: bool = False) -> Dict[str, Any]:
    """
    Mencari dokumen yang memiliki status_keberlakuan selain 'tidak_diketahui'
    namun status_source masih NULL, lalu mengisinya dengan 'sumber'.
    """
    query = (
        db.query(Document)
        .filter(
            Document.status_keberlakuan.isnot(None),
            Document.status_keberlakuan != StatusKeberlakuan.tidak_diketahui,
            Document.status_source.is_(None),
        )
        .order_by(Document.id.asc())
    )
    docs: List[Document] = query.all()

    print("\n" + "=" * 95)
    print("           BACKFILL STATUS_SOURCE KE 'sumber' (Langkah 38)")
    print("=" * 95)
    print(f"Total dokumen ditemukan: {len(docs)}")

    if docs:
        print(f"{'ID':<6} | {'Status Keberlakuan':<20} | {'Status Source Lama':<20} | {'Judul (45 Karakter)'}")
        print("-" * 95)
        for doc in docs[:20]:
            st = doc.status_keberlakuan.value if hasattr(doc.status_keberlakuan, "value") else str(doc.status_keberlakuan)
            print(f"{doc.id:<6} | {st:<20} | {str(doc.status_source):<20} | {(doc.title or '-')[:45]}")
        if len(docs) > 20:
            print(f"... dan {len(docs) - 20} dokumen lainnya.")

    updated_count = 0
    if apply and docs:
        print("\n[APPLY] Menerapkan pembaruan status_source='sumber' dan mencatat audit log...")
        for doc in docs:
            before_status = (
                doc.status_keberlakuan.value
                if hasattr(doc.status_keberlakuan, "value")
                else str(doc.status_keberlakuan)
            )
            before_source = doc.status_source
            doc.status_source = "sumber"

            record_audit(
                db,
                action=UPDATE_DOCUMENT_STATUS,
                target_resource=f"document:{doc.id}",
                detail={
                    "document_id": doc.id,
                    "alasan": "langkah38_backfill_status_source",
                    "before": {
                        "status_keberlakuan": before_status,
                        "status_source": before_source,
                    },
                    "after": {
                        "status_keberlakuan": before_status,
                        "status_source": "sumber",
                    },
                },
                commit=False,
            )
            updated_count += 1
        db.commit()
        print(f"SUKSES: {updated_count} dokumen berhasil diperbarui.")
    elif not apply:
        print("\n[DRY-RUN] Mode tinjauan saja. Tidak ada perubahan basis data yang disimpan.")
        print("Gunakan flag --apply untuk mengeksekusi pembaruan.")

    print("=" * 95 + "\n")
    return {
        "found_count": len(docs),
        "updated_count": updated_count,
        "doc_ids": [d.id for d in docs],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill status_source='sumber' untuk dokumen berstatus keberlakuan tanpa status_source.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Terapkan pembaruan ke database dan catat audit log",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        backfill_status_source(db=db, apply=args.apply)
        return 0
    except Exception as exc:
        print(f"FATAL: Terjadi galat saat backfill status_source: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

