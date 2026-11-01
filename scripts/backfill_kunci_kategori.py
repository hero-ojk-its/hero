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
from app.models.document import Document
from app.models.audit_log import AuditLog
from app.services.audit_service import UPDATE_CATEGORY


def is_used_in_auto_placement(cat: Category, db: Session) -> bool:
    """
    Aturan 1: kategori dipakai penempatan otomatis bila:
    - auto_created == True, ATAU
    - punya anak dengan auto_created == True, ATAU
    - punya dokumen dengan kategori_manual == False
    """
    if cat.auto_created:
        return True
    has_auto_child = (
        db.query(Category.id)
        .filter(Category.parent_id == cat.id, Category.auto_created.is_(True))
        .first()
        is not None
    )
    if has_auto_child:
        return True
    has_auto_doc = (
        db.query(Document.id)
        .filter(Document.category_id == cat.id, Document.kategori_manual.is_(False))
        .first()
        is not None
    )
    if has_auto_doc:
        return True
    return False


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

            proposed_key = None
            if oldest_name and cat.kunci_otomatis != oldest_name:
                proposed_key = oldest_name
            elif cat.kunci_otomatis is None and is_used_in_auto_placement(cat, db):
                proposed_key = cat.name

            if not proposed_key:
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
                    Category.kunci_otomatis == proposed_key,
                    Category.id != cat.id,
                )
                .first()
            )

            if existing_conflict or (cat.parent_id, proposed_key) in batch_proposed:
                print(
                    f"[BENTROK - DILEWATI] id={cat.id} | nama sekarang={cat.name} | kunci usulan={proposed_key} bentrok di induk {cat.parent_id}"
                )
                continue

            if not header_printed:
                print("id | nama sekarang | kunci usulan")
                header_printed = True

            print(f"{cat.id} | {cat.name} | {proposed_key}")
            batch_proposed.add((cat.parent_id, proposed_key))
            count += 1

            if apply:
                cat.kunci_otomatis = proposed_key
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
