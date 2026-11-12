"""
scripts/usangkan_cache_analisa.py
Skrip untuk menandai usang (invalidasi) cache hasil analisa di tabel analysis_results.

Perilaku:
- Default DRY-RUN: cetak jumlah baris analysis_results yang masih segar (usang_sejak IS NULL),
  dikelompokkan per kind dan mode, plus 10 contoh (document_id, kind, mode, ml_version, created_at).
  Tidak mengubah apa pun.
- --apply: set usang_sejak = sekarang (UTC) dan alasan_usang = nilai --alasan untuk baris yang terpilih.
  Jangan menghapus baris.
- --kind analisa|harmonisasi|semua (default: analisa).
- --alasan "teks" (default: "pipeline diperbarui").
- --document-id N (opsional, boleh diulang): hanya dokumen tertentu.
- Cetak ringkasan jumlah baris yang ditandai usang.
- Tidak mencetak isi hasil analisa.
- Catat satu entri audit ANALYSIS_CACHE_INVALIDATED saat --apply.
"""
import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

# Pastikan root proyek masuk ke sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Pastikan output konsol UTF-8 di Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.analysis_result import AnalysisResult
from app.models.enums import JenisAnalisa, ModeAnalisa
from app.services.audit_service import (
    record_audit,
    ANALYSIS_CACHE_INVALIDATED,
)

logger = logging.getLogger("hero")


def run_usangkan_cache_analisa(
    db: Session,
    apply: bool = False,
    kind: Union[str, JenisAnalisa] = "analisa",
    alasan: str = "pipeline diperbarui",
    document_ids: Optional[Union[int, Sequence[int]]] = None,
) -> Dict[str, Any]:
    """
    Menjalankan pemeriksaan (dry-run) atau penandaan usang (--apply) cache analisa.
    """
    # Normalisasi kind
    if isinstance(kind, JenisAnalisa):
        kind_str = kind.value
    else:
        kind_str = str(kind).lower().strip()

    valid_kinds = {"analisa", "harmonisasi", "semua"}
    if kind_str not in valid_kinds:
        raise ValueError(
            f"Kind '{kind}' tidak valid. Pilihan yang diizinkan: analisa, harmonisasi, semua."
        )

    # Normalisasi document_ids
    doc_ids_list: Optional[List[int]] = None
    if document_ids is not None:
        if isinstance(document_ids, int):
            doc_ids_list = [document_ids]
        else:
            doc_ids_list = [int(x) for x in document_ids]

    alasan_str = (alasan or "").strip() or "pipeline diperbarui"

    mode_str = "APPLY (menandai cache usang)" if apply else "DRY-RUN (bawaan - tanpa perubahan DB)"
    print(f"=== Menjalankan Usangkan Cache Analisa [{mode_str}] ===")
    print("Parameter:")
    print(f"  - Kind        : {kind_str}")
    print(f"  - Dokumen ID  : {doc_ids_list if doc_ids_list is not None else 'Semua dokumen'}")
    print(f"  - Alasan      : {alasan_str}")
    print("-" * 80)

    # Query dasar untuk baris yang masih segar
    base_query = db.query(AnalysisResult).filter(AnalysisResult.usang_sejak.is_(None))

    if kind_str == "analisa":
        base_query = base_query.filter(AnalysisResult.kind == JenisAnalisa.analisa)
    elif kind_str == "harmonisasi":
        base_query = base_query.filter(AnalysisResult.kind == JenisAnalisa.harmonisasi)

    if doc_ids_list is not None:
        base_query = base_query.filter(AnalysisResult.document_id.in_(doc_ids_list))

    # Pengelompokan per kind dan mode
    counts_per_group = (
        base_query.with_entities(
            AnalysisResult.kind,
            AnalysisResult.mode,
            func.count(AnalysisResult.id).label("total"),
        )
        .group_by(AnalysisResult.kind, AnalysisResult.mode)
        .order_by(AnalysisResult.kind, AnalysisResult.mode)
        .all()
    )

    total_segar = sum(cnt for _, _, cnt in counts_per_group)

    print(f"Total baris segar (usang_sejak IS NULL) ditemukan: {total_segar}")
    if counts_per_group:
        print("Pengelompokan per kind dan mode:")
        for k_enum, m_enum, cnt in counts_per_group:
            k_name = k_enum.value if hasattr(k_enum, "value") else str(k_enum)
            m_name = m_enum.value if hasattr(m_enum, "value") else str(m_enum)
            print(f"  - kind={k_name:<11} mode={m_name:<13} : {cnt} baris")
    else:
        print("  (tidak ada data yang cocok dengan kriteria)")

    # 10 contoh baris segar
    sample_rows = (
        base_query.order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
        .limit(10)
        .all()
    )

    contoh: List[Dict[str, Any]] = []
    for r in sample_rows:
        k_val = r.kind.value if hasattr(r.kind, "value") else str(r.kind)
        m_val = r.mode.value if hasattr(r.mode, "value") else str(r.mode)
        contoh.append(
            {
                "document_id": r.document_id,
                "kind": k_val,
                "mode": m_val,
                "ml_version": r.ml_version or "-",
                "created_at": r.created_at,
            }
        )

    if contoh:
        print("\nContoh baris segar (maksimal 10):")
        print("-" * 80)
        print(f"{'Doc ID':<8} | {'Kind':<12} | {'Mode':<14} | {'Versi ML':<20} | {'Dibuat'}")
        print("-" * 80)
        for c in contoh:
            dt_str = c["created_at"].strftime("%Y-%m-%d %H:%M:%S") if c["created_at"] else "-"
            print(
                f"{c['document_id']:<8} | {c['kind']:<12} | {c['mode']:<14} | {c['ml_version']:<20} | {dt_str}"
            )
        print("-" * 80)
        if total_segar > len(contoh):
            print(f"... dan {total_segar - len(contoh)} baris segar lainnya.")

    ditandai_count = 0
    if apply:
        now_utc = datetime.now(timezone.utc)
        if total_segar > 0:
            ditandai_count = base_query.update(
                {
                    AnalysisResult.usang_sejak: now_utc,
                    AnalysisResult.alasan_usang: alasan_str,
                },
                synchronize_session=False,
            )

            record_audit(
                db,
                action=ANALYSIS_CACHE_INVALIDATED,
                user_id=None,
                target_resource="analysis_results",
                detail={
                    "kind": kind_str,
                    "alasan": alasan_str,
                    "document_ids": doc_ids_list,
                    "ditandai": ditandai_count,
                },
                commit=False,
            )
            db.commit()
            print(f"\nSUKSES: {ditandai_count} baris cache analisa berhasil ditandai usang.")
            print(f"Audit log tercatat ({ANALYSIS_CACHE_INVALIDATED}).")
        else:
            print("\nTidak ada baris segar yang cocok untuk ditandai usang.")
    else:
        if total_segar > 0:
            print(f"\nGunakan flag --apply untuk menandai {total_segar} baris di atas sebagai usang.")
        else:
            print("\nDRY-RUN selesai. Tidak ada baris yang perlu diubah.")

    return {
        "total_segar": total_segar,
        "ditandai": ditandai_count,
        "breakdown": {
            (
                k.value if hasattr(k, "value") else str(k),
                m.value if hasattr(m, "value") else str(m),
            ): cnt
            for k, m, cnt in counts_per_group
        },
        "contoh": contoh,
    }


def main(db: Optional[Session] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Tandai usang (invalidasi) cache hasil analisa di tabel analysis_results."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Terapkan perubahan (set usang_sejak dan alasan_usang). Bawaan: dry-run.",
    )
    parser.add_argument(
        "--kind",
        choices=["analisa", "harmonisasi", "semua"],
        default="analisa",
        help="Jenis analisa yang akan diusangkan (default: analisa).",
    )
    parser.add_argument(
        "--alasan",
        type=str,
        default="pipeline diperbarui",
        help="Alasan penandaan usang (default: 'pipeline diperbarui').",
    )
    parser.add_argument(
        "--document-id",
        dest="document_ids",
        action="append",
        type=int,
        default=None,
        help="ID dokumen yang akan diusangkan (boleh diulang, misal: --document-id 10 --document-id 20).",
    )
    args = parser.parse_args()

    close_db = False
    if db is None:
        from app.database import SessionLocal
        db = SessionLocal()
        close_db = True

    try:
        run_usangkan_cache_analisa(
            db=db,
            apply=args.apply,
            kind=args.kind,
            alasan=args.alasan,
            document_ids=args.document_ids,
        )
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    main()

