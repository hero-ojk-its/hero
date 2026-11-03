"""
scripts/periksa_judul.py
Pemeriksaan judul hasil ekstraksi yang mencurigakan (mengandung isi peraturan atau berbentuk paragraf)
pada dokumen aktif yang belum dikoreksi manual (Langkah 35, FR-SCR-04a).

Aturan:
- Default dry-run: jalankan periksa_judul ke semua dokumen aktif yang belum dikoreksi manual.
  Cetak 'id | status | alasan | panjang | 80 karakter pertama judul' hanya untuk yang dipotong/ditolak,
  plus ringkasan jumlah.
- --apply: TIDAK MENGUBAH JUDUL. Hanya set processing_status = perlu_koreksi (bila sekarang terindeks),
  tambahkan 'title' ke low_confidence_fields (atau extraction_confidence), dan catat audit UPDATE_METADATA.
"""
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

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
from app.models.enums import StatusPemrosesan
from app.services.judul_service import periksa_judul
from app.services.audit_service import record_audit, UPDATE_METADATA


def run_periksa_judul(
    db: Session,
    apply: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, int]:
    mode_str = "APPLY (set perlu_koreksi)" if apply else "DRY-RUN (bawaan - tanpa perubahan DB)"
    print(f"=== Menjalankan Periksa Judul Ekstraksi [{mode_str}] ===")

    query = (
        db.query(Document)
        .filter(
            Document.is_active == True,  # noqa: E712
            Document.metadata_corrected_at.is_(None),
        )
        .order_by(Document.id.asc())
    )

    if limit is not None:
        query = query.limit(limit)

    docs: List[Document] = query.all()

    total_diperiksa = len(docs)
    count_ok = 0
    count_dipotong = 0
    count_ditolak = 0
    diubah_count = 0

    bermasalah: List[dict] = []

    for doc in docs:
        judul_asli = doc.title or ""
        hasil = periksa_judul(judul_asli)

        if hasil.status == "ok":
            count_ok += 1
        elif hasil.status == "dipotong":
            count_dipotong += 1
            bermasalah.append({
                "doc": doc,
                "status": "dipotong",
                "alasan": hasil.alasan,
                "panjang": len(judul_asli),
                "cuplikan": judul_asli[:80],
            })
        else:  # ditolak
            count_ditolak += 1
            bermasalah.append({
                "doc": doc,
                "status": "ditolak",
                "alasan": hasil.alasan,
                "panjang": len(judul_asli),
                "cuplikan": judul_asli[:80],
            })

    print(f"Total dokumen diperiksa: {total_diperiksa}")
    print(f"Hasil: OK={count_ok}, Dipotong={count_dipotong}, Ditolak={count_ditolak}")
    print("-" * 115)
    print(f"{'ID':<6} | {'Status':<9} | {'Alasan':<26} | {'Panjang':<7} | {'Cuplikan Judul (80 kar)'}")
    print("-" * 115)

    for item in bermasalah:
        doc = item["doc"]
        print(f"{doc.id:<6} | {item['status']:<9} | {item['alasan']:<26} | {item['panjang']:<7} | {item['cuplikan']}")

        if apply:
            status_lama = doc.processing_status.value if hasattr(doc.processing_status, "value") else str(doc.processing_status)
            perlu_update = False

            if doc.processing_status == StatusPemrosesan.terindeks:
                doc.processing_status = StatusPemrosesan.perlu_koreksi
                perlu_update = True

            # Pastikan confidence title ditandai rendah bila ada extraction_confidence
            if doc.extraction_confidence is not None and isinstance(doc.extraction_confidence, dict):
                curr_conf = dict(doc.extraction_confidence)
                if curr_conf.get("title", 1.0) >= settings.metadata_confidence_threshold:
                    curr_conf["title"] = 0.0
                    doc.extraction_confidence = curr_conf
                    perlu_update = True
            elif doc.extraction_confidence is None:
                doc.extraction_confidence = {"title": 0.0}
                perlu_update = True

            # Jika model memiliki atribut low_confidence_fields (fleksibilitas skema)
            if hasattr(doc, "low_confidence_fields"):
                lcf = getattr(doc, "low_confidence_fields") or []
                if "title" not in lcf:
                    setattr(doc, "low_confidence_fields", list(lcf) + ["title"])
                    perlu_update = True

            if perlu_update:
                # Catat audit UPDATE_METADATA
                record_audit(
                    db,
                    action=UPDATE_METADATA,
                    user_id=None,
                    target_resource=f"document:{doc.id}",
                    detail={
                        "alasan": "langkah35_judul_mencurigakan",
                        "document_id": doc.id,
                        "status_sebelumnya": status_lama,
                        "status_baru": StatusPemrosesan.perlu_koreksi.value,
                        "pemeriksaan_judul": {
                            "status": item["status"],
                            "alasan": item["alasan"],
                            "panjang": item["panjang"],
                        },
                    },
                    commit=False,
                )
                diubah_count += 1

    if apply and diubah_count > 0:
        db.commit()
        print("-" * 115)
        print(f"Sukses menandai {diubah_count} dokumen berstatus perlu_koreksi.")
    elif not apply and len(bermasalah) > 0:
        print("-" * 115)
        print(f"Gunakan flag --apply untuk menandai {len(bermasalah)} dokumen di atas sebagai perlu_koreksi.")

    return {
        "total_diperiksa": total_diperiksa,
        "ok": count_ok,
        "dipotong": count_dipotong,
        "ditolak": count_ditolak,
        "diubah": diubah_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Periksa dan tandai dokumen dengan judul hasil ekstraksi mencurigakan."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Terapkan status perlu_koreksi dan catat audit log (tanpa mengubah judul).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Batasi jumlah dokumen yang diperiksa.",
    )
    args = parser.parse_args()

    engine = create_engine(settings.database_url)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()

    try:
        run_periksa_judul(db=db, apply=args.apply, limit=args.limit)
    finally:
        db.close()


if __name__ == "__main__":
    main()

