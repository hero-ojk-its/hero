"""
scripts/periksa_antrean_ekstraksi.py
Skrip perawatan satu kali untuk memeriksa dan menangani dokumen yang tersangkut di antrean ekstraksi.

Perilaku:
- Default DRY-RUN: cetak jumlah dokumen aktif per (processing_status, extraction_attempts) untuk status
  'diterima' dan 'diproses', lalu daftar dokumen yang tersangkut (id, status, attempts, claimed_at, created_at).
  Tidak mengubah apa pun. JANGAN mencetak judul atau isi dokumen (bisa non-publik).
- --apply --reset: untuk dokumen tersangkut, set extraction_attempts = 0, processing_status = diterima,
  extraction_claimed_at = None (dicoba ulang oleh worker).
- --apply --gagalkan: jalankan tandai_ekstraksi_kehabisan_percobaan (ditandai gagal + kegagalan tercatat).
- --document-id N (opsional, boleh diulang): hanya dokumen tertentu.
- --apply tanpa --reset/--gagalkan: tolak dengan pesan jelas.
- Tidak menghapus baris apa pun.
"""
import argparse
import logging
import sys
from datetime import datetime, timezone, timedelta
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

from sqlalchemy import create_engine, func, and_, or_
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.document import Document
from app.models.enums import StatusPemrosesan
from app.services.document_service import tandai_ekstraksi_kehabisan_percobaan
from app.services.audit_service import record_audit, EXTRACTION_REQUEUED

logger = logging.getLogger("hero")


def run_periksa_antrean_ekstraksi(
    db: Session,
    apply: bool = False,
    reset: bool = False,
    gagalkan: bool = False,
    document_ids: Optional[Union[int, Sequence[int]]] = None,
) -> Dict[str, Any]:
    """
    Menjalankan pemeriksaan (dry-run) atau perbaikan (--apply --reset / --apply --gagalkan) antrean ekstraksi.
    """
    if apply:
        if not reset and not gagalkan:
            raise ValueError("Argumen --apply memerlukan salah satu dari --reset atau --gagalkan.")
        if reset and gagalkan:
            raise ValueError("Argumen --reset dan --gagalkan tidak dapat digunakan bersamaan.")

    doc_ids_list: Optional[List[int]] = None
    if document_ids is not None:
        if isinstance(document_ids, int):
            doc_ids_list = [document_ids]
        else:
            doc_ids_list = [int(x) for x in document_ids]

    if apply and reset:
        mode_str = "APPLY --RESET (reset percobaan=0, status=diterima)"
    elif apply and gagalkan:
        mode_str = "APPLY --GAGALKAN (tandai gagal + catat kegagalan)"
    else:
        mode_str = "DRY-RUN (bawaan - tanpa perubahan DB)"

    print(f"=== Menjalankan Periksa Antrean Ekstraksi [{mode_str}] ===")
    print("Parameter:")
    print(f"  - Mode        : {mode_str}")
    print(f"  - Dokumen ID  : {doc_ids_list if doc_ids_list is not None else 'Semua dokumen'}")
    print(f"  - Batas Coba  : {settings.extraction_max_attempts}")
    print(f"  - Timeout Klaim: {settings.extraction_claim_timeout_minutes} menit")
    print("-" * 80)

    # 1. Cetak jumlah dokumen aktif per (processing_status, extraction_attempts) untuk diterima dan diproses
    counts_query = (
        db.query(
            Document.processing_status,
            Document.extraction_attempts,
            func.count(Document.id).label("total"),
        )
        .filter(
            Document.is_active == True,
            Document.processing_status.in_([StatusPemrosesan.diterima, StatusPemrosesan.diproses]),
        )
    )
    if doc_ids_list is not None:
        counts_query = counts_query.filter(Document.id.in_(doc_ids_list))

    counts_grouped = (
        counts_query.group_by(Document.processing_status, Document.extraction_attempts)
        .order_by(Document.processing_status, Document.extraction_attempts)
        .all()
    )

    print("Jumlah dokumen aktif per (status, percobaan):")
    if not counts_grouped:
        print("  (Tidak ada dokumen aktif berstatus 'diterima' atau 'diproses')")
    else:
        for status_enum, attempts, cnt in counts_grouped:
            status_val = status_enum.value if hasattr(status_enum, "value") else str(status_enum)
            print(f"  - Status: {status_val:<10} | Percobaan: {attempts:<3} | Total: {cnt}")
    print("-" * 80)

    # 2. Cari dokumen tersangkut (attempts >= max_attempts, dan diterima atau diproses kedaluwarsa)
    timeout_minutes = settings.extraction_claim_timeout_minutes
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

    stuck_cond = and_(
        Document.is_active == True,  # noqa: E712
        Document.extraction_attempts >= settings.extraction_max_attempts,
        or_(
            Document.processing_status == StatusPemrosesan.diterima,
            and_(
                Document.processing_status == StatusPemrosesan.diproses,
                Document.extraction_claimed_at.isnot(None),
                Document.extraction_claimed_at < cutoff_time,
            ),
        ),
    )

    stuck_query = db.query(Document).filter(stuck_cond)
    if doc_ids_list is not None:
        stuck_query = stuck_query.filter(Document.id.in_(doc_ids_list))

    stuck_docs = stuck_query.order_by(Document.id.asc()).all()
    print(f"Total dokumen tersangkut ditemukan: {len(stuck_docs)}")

    if stuck_docs:
        print("Daftar dokumen tersangkut:")
        for doc in stuck_docs:
            status_val = doc.processing_status.value if hasattr(doc.processing_status, "value") else str(doc.processing_status)
            claimed_str = doc.extraction_claimed_at.isoformat() if doc.extraction_claimed_at else "None"
            created_str = doc.created_at.isoformat() if doc.created_at else "None"
            print(
                f"  - ID: {doc.id:<6} | Status: {status_val:<10} | Percobaan: {doc.extraction_attempts:<3} "
                f"| Claimed At: {claimed_str:<25} | Created At: {created_str}"
            )
    print("-" * 80)

    affected_count = 0
    stuck_ids = [doc.id for doc in stuck_docs]

    if apply and reset:
        for doc in stuck_docs:
            doc.extraction_attempts = 0
            doc.processing_status = StatusPemrosesan.diterima
            doc.extraction_claimed_at = None

            record_audit(
                db,
                action=EXTRACTION_REQUEUED,
                target_resource=f"document:{doc.id}",
                detail={
                    "document_id": doc.id,
                    "attempt": 0,
                    "alasan": "periksa_antrean_ekstraksi_reset",
                },
                commit=False,
            )
        db.commit()
        affected_count = len(stuck_docs)
        print(f"BERHASIL: {affected_count} dokumen tersangkut telah direset (attempts=0, status=diterima).")
    elif apply and gagalkan:
        if stuck_ids:
            failed_ids = tandai_ekstraksi_kehabisan_percobaan(db, document_ids=stuck_ids, commit=True)
            affected_count = len(failed_ids)
        else:
            affected_count = 0
        print(f"BERHASIL: {affected_count} dokumen tersangkut telah ditandai gagal dan kegagalan dicatat.")
    else:
        print("DRY-RUN selesai. Tidak ada perubahan yang disimpan ke basis data.")

    return {
        "apply": apply,
        "mode": "reset" if (apply and reset) else ("gagalkan" if (apply and gagalkan) else "dry-run"),
        "total_stuck": len(stuck_docs),
        "stuck_document_ids": stuck_ids,
        "affected_count": affected_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Periksa dan tangani dokumen tersangkut di antrean ekstraksi."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Eksekusi perubahan ke basis data (harus disertai --reset atau --gagalkan).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help="Reset dokumen tersangkut: attempts=0, status=diterima, claimed_at=None.",
    )
    parser.add_argument(
        "--gagalkan",
        action="store_true",
        default=False,
        help="Tandai dokumen tersangkut sebagai gagal dan catat kegagalan ingest.",
    )
    parser.add_argument(
        "--document-id",
        dest="document_ids",
        type=int,
        action="append",
        help="Filter ID dokumen tertentu (opsional, boleh diulang).",
    )

    args = parser.parse_args()

    if args.apply and not args.reset and not args.gagalkan:
        print("Galat: --apply memerlukan salah satu dari --reset atau --gagalkan.", file=sys.stderr)
        sys.exit(1)

    if args.reset and args.gagalkan:
        print("Galat: --reset dan --gagalkan tidak dapat digunakan bersamaan.", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(str(settings.database_url))
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        run_periksa_antrean_ekstraksi(
            db=db,
            apply=args.apply,
            reset=args.reset,
            gagalkan=args.gagalkan,
            document_ids=args.document_ids,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

