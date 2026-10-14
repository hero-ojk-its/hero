"""
scripts/backfill_identity.py
Skrip CLI untuk mengisi identity_key dengan cadangan (fallback_identity_key)
untuk dokumen yang belum memiliki kunci identitas, serta melaporkan dan menangani
pasangan duplikat identitas.

Penggunaan:
  python scripts/backfill_identity.py [--dry-run | --apply]
"""
import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

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
from app.models.enums import PeranDokumen, StatusPemrosesan
from app.services.duplicate_service import check_identity_duplicate, compare_docs
from app.services.identity_service import fallback_identity_key

DATABASE_URL = settings.database_url
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def run_backfill(db: Session, apply: bool = False) -> Dict[str, int]:
    dry_run = not apply
    mode_str = "APPLY" if apply else "DRY-RUN (bawaan - tanpa perubahan DB)"
    print(f"=== Menjalankan Backfill Identitas Dokumen [{mode_str}] ===")

    # 1. Ambil seluruh dokumen
    docs = db.query(Document).order_by(Document.id.asc()).all()
    total_docs = len(docs)
    print(f"Total dokumen di database: {total_docs}")

    # 2. Isi cadangan identity_key untuk dokumen yang belum memiliki kunci
    filled_keys = 0
    doc_keys: Dict[int, str] = {}

    for doc in docs:
        if doc.identity_key:
            doc_keys[doc.id] = doc.identity_key
        else:
            fb_key = fallback_identity_key(
                regulation_type=doc.regulation_type,
                regulation_number=doc.regulation_number,
                regulation_year=doc.regulation_year,
            )
            if fb_key:
                doc_keys[doc.id] = fb_key
                filled_keys += 1
                if not dry_run:
                    doc.identity_key = fb_key
            else:
                doc_keys[doc.id] = ""

    if not dry_run and filled_keys > 0:
        db.commit()

    print(f"Identity key terisi (atau kandidat terisi): {filled_keys}")

    # 3. Kelompokkan dokumen aktif corpus_eksisting berdasarkan identity_key
    grouped: Dict[str, List[Document]] = defaultdict(list)
    for doc in docs:
        eff_key = doc_keys.get(doc.id) or doc.identity_key
        role_val = doc.document_role.value if hasattr(doc.document_role, "value") else str(doc.document_role)
        proc_val = doc.processing_status.value if hasattr(doc.processing_status, "value") else str(doc.processing_status)

        if (
            eff_key
            and doc.is_active
            and role_val == PeranDokumen.corpus_eksisting.value
            and proc_val in (StatusPemrosesan.terindeks.value, StatusPemrosesan.perlu_koreksi.value)
        ):
            grouped[eff_key].append(doc)

    duplicate_groups = {k: v for k, v in grouped.items() if len(v) > 1}
    print(f"Kelompok duplikat terdeteksi: {len(duplicate_groups)}")

    total_deactivated = 0

    for key, group in duplicate_groups.items():
        print(f"\n[DUPLIKAT] Kunci: {key} ({len(group)} dokumen)")
        for d in group:
            print(f"  - ID #{d.id}: {d.title or '-'} | {d.regulation_number or '-'} | "
                  f"Halaman: {d.page_count or 'N/A'}, Ukuran: {d.file_size_bytes}B")

        if not dry_run:
            # Jalankan check_identity_duplicate untuk dokumen-dokumen dalam grup
            for d in group:
                if d.is_active:
                    dup_res = check_identity_duplicate(db, d)
                    if dup_res:
                        db.commit()
                        total_deactivated += len(dup_res.deactivated_document_ids)
                        print(f"  -> Pemenang: ID #{dup_res.kept_document_id} | "
                              f"Dinonaktifkan: {dup_res.deactivated_document_ids} | Aturan: {dup_res.rule}")
                        break
        else:
            # Simulasi siapa pemenang dan siapa kalah
            from functools import cmp_to_key
            sorted_sim = sorted(group, key=cmp_to_key(lambda a, b: compare_docs(a, b)[0]))
            win = sorted_sim[0]
            los = sorted_sim[1:]
            sim_deact = []
            applied_rule = None
            for loser in los:
                if loser.duplicate_of_id is not None and loser.is_active:
                    print(f"  -> [SIMULASI] ID #{loser.id} dilewati karena pernah diaktifkan manual")
                    continue
                _, rname = compare_docs(win, loser)
                if applied_rule is None:
                    applied_rule = rname
                sim_deact.append(loser.id)

            total_deactivated += len(sim_deact)
            print(f"  -> [SIMULASI] Pemenang: ID #{win.id} | "
                  f"Akan dinonaktifkan: {sim_deact} | Aturan: {applied_rule or 'older'}")

    print("\n=== Ringkasan ===")
    print(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")
    print(f"Dokumen diperiksa: {total_docs}")
    print(f"Identity key cadangan diisi: {filled_keys}")
    print(f"Kelompok duplikat: {len(duplicate_groups)}")
    print(f"Dokumen dinonaktifkan: {total_deactivated}")

    return {
        "total_docs": total_docs,
        "filled_keys": filled_keys,
        "duplicate_groups": len(duplicate_groups),
        "total_deactivated": total_deactivated,
    }


def main():
    parser = argparse.ArgumentParser(description="Backfill identity_key dan pengecekan duplikat identitas")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True, help="Hanya laporkan tanpa mengubah DB (bawaan)")
    group.add_argument("--apply", action="store_true", default=False, help="Terapkan perubahan ke DB")

    args = parser.parse_args()
    apply = args.apply

    db = SessionLocal()
    try:
        run_backfill(db, apply=apply)
    finally:
        db.close()


if __name__ == "__main__":
    main()
