"""
scripts/backfill_kunci_kategori.py
Memulihkan kunci_otomatis untuk kategori yang pernah diganti nama sebelum Langkah 33
berdasarkan entri audit UPDATE_CATEGORY tertua.
"""
import argparse
import json
from pathlib import Path
import sys
from typing import Set, Tuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

import app.database
from app.models.category import Category
from app.models.audit_log import AuditLog
from app.services.audit_service import UPDATE_CATEGORY


def run_backfill(apply: bool = False, db: Optional[Session] = None) -> None:
    own_db = False
    if db is None:
        db = app.database.SessionLocal()
        own_db = True
    try:
        categories = (
            db.query(Category)
            .order_by(Category.id.asc())
            .all()
        )

        batch_proposed: Set[Tuple[Optional[int], str]] = set()
        header_printed = False
        count = 0

        for cat in categories:
            logs = (
                db.query(AuditLog)
                .filter(
                    AuditLog.action == UPDATE_CATEGORY,
                    AuditLog.target_resource == f"category:{cat.id}",
                )
                .order_by(AuditLog.timestamp.asc(), AuditLog.id.asc())
                .all()
            )

            oldest_name = None
            for log in logs:
                detail = log.detail
                if isinstance(detail, str):
                    try:
                        detail = json.loads(detail)
                    except Exception:
                        detail = {}
                if isinstance(detail, dict):
                    before = detail.get("before")
                    if isinstance(before, dict) and before.get("name"):
                        oldest_name = before["name"]
                        break

            if not oldest_name:
                continue

            if cat.kunci_otomatis == oldest_name:
                continue

            filter_parent = (
                (Category.parent_id == cat.parent_id)
                if cat.parent_id is not None
                else Category.parent_id.is_(None)
            )
            existing_conflict = (
                db.query(Category)
                .filter(
                    filter_parent,
                    Category.kunci_otomatis == oldest_name,
                    Category.id != cat.id,
                )
                .first()
            )

            if existing_conflict or (cat.parent_id, oldest_name) in batch_proposed:
                print(
                    f"[BENTROK - DILEWATI] id={cat.id} | nama sekarang={cat.name} | kunci usulan={oldest_name} bentrok di induk {cat.parent_id}"
                )
                continue

            if not header_printed:
                print("id | nama sekarang | kunci usulan")
                header_printed = True

            print(f"{cat.id} | {cat.name} | {oldest_name}")
            batch_proposed.add((cat.parent_id, oldest_name))
            count += 1

            if apply:
                cat.kunci_otomatis = oldest_name
                db.add(cat)

        if count == 0:
            print("Tidak ada kategori yang perlu di-backfill.")

        if apply:
            db.commit()
    finally:
        if own_db:
            db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Backfill kunci_otomatis kategori berdasarkan riwayat audit UPDATE_CATEGORY"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Terapkan usulan backfill ke database (default: dry-run)",
    )
    args = parser.parse_args()
    run_backfill(apply=args.apply)


if __name__ == "__main__":
    main()
