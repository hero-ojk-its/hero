"""
scripts/periksa_draft_publik.py
Pemeriksaan dan migrasi data dokumen draft kajian dengan akses publik tanpa persetujuan (Langkah 35).

Aturan:
- Default dry-run: cetak 'id | judul (60 karakter) | dibuat | publik_disetujui_pada'
  untuk semua dokumen draft_kajian + publik yang belum memiliki persetujuan.
- --apply: ubah dokumen-dokumen tersebut menjadi non_publik, catat audit UPDATE_METADATA,
  dan tandai usang (invalidasi) cache analisa terkait.
- Tidak mencetak isi teks dokumen.
"""
import argparse
import sys
from datetime import datetime, timezone
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
from app.models.scraping_source import ScrapingSource
from app.models.analysis_result import AnalysisResult
from app.models.enums import KlasifikasiAkses, PeranDokumen
from app.services.audit_service import (
    record_audit,
    UPDATE_METADATA,
    UPDATE_SOURCE,
    ANALYSIS_CACHE_INVALIDATED,
)


def run_periksa_draft_publik(
    db: Session,
    apply: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, int]:
    mode_str = "APPLY (mengubah ke non_publik)" if apply else "DRY-RUN (bawaan - tanpa perubahan DB)"
    print(f"=== Menjalankan Periksa Draft Publik [{mode_str}] ===")

    query = (
        db.query(Document)
        .filter(
            Document.document_role == PeranDokumen.draft_kajian,
            Document.access_classification == KlasifikasiAkses.publik,
            Document.publik_disetujui_pada.is_(None),
        )
        .order_by(Document.id.asc())
    )

    if limit is not None:
        query = query.limit(limit)

    docs: List[Document] = query.all()
    total_ditemukan = len(docs)

    print(f"Total draft kajian publik tanpa persetujuan ditemukan: {total_ditemukan}")
    print("-" * 105)
    print(f"{'ID':<6} | {'Judul (maks 60 kar)':<62} | {'Dibuat':<19} | {'Persetujuan'}")
    print("-" * 105)

    diubah_count = 0
    now_utc = datetime.now(timezone.utc)

    for doc in docs:
        judul_ringkas = (doc.title or doc.original_filename or "(tanpa judul)")[:60]
        dibuat_str = doc.created_at.strftime("%Y-%m-%d %H:%M:%S") if doc.created_at else "-"
        persetujuan_str = str(doc.publik_disetujui_pada) if doc.publik_disetujui_pada else "None"
        print(f"{doc.id:<6} | {judul_ringkas:<62} | {dibuat_str:<19} | {persetujuan_str}")

        if apply:
            doc.access_classification = KlasifikasiAkses.non_publik

            # Catat audit UPDATE_METADATA
            record_audit(
                db,
                action=UPDATE_METADATA,
                user_id=None,
                target_resource=f"document:{doc.id}",
                detail={
                    "alasan": "langkah35_draft_publik_tanpa_persetujuan",
                    "before": {"access_classification": "publik"},
                    "after": {"access_classification": "non_publik"},
                },
                commit=False,
            )

            # Invalidasi cache analisa terkait dokumen ini (pola Langkah 25)
            stale_updated = (
                db.query(AnalysisResult)
                .filter(
                    AnalysisResult.document_id == doc.id,
                    AnalysisResult.usang_sejak.is_(None),
                )
                .update(
                    {
                        AnalysisResult.usang_sejak: now_utc,
                        AnalysisResult.alasan_usang: "langkah35_draft_publik_tanpa_persetujuan",
                    },
                    synchronize_session=False,
                )
            )

            if stale_updated > 0:
                record_audit(
                    db,
                    action=ANALYSIS_CACHE_INVALIDATED,
                    user_id=None,
                    target_resource=f"document:{doc.id}",
                    detail={
                        "document_id": doc.id,
                        "alasan": "langkah35_draft_publik_tanpa_persetujuan",
                        "ditandai": stale_updated,
                    },
                    commit=False,
                )

            diubah_count += 1

    if apply and diubah_count > 0:
        db.commit()
        print("-" * 105)
        print(f"Sukses mengupdate {diubah_count} dokumen menjadi non_publik.")
    elif not apply and total_ditemukan > 0:
        print("-" * 105)
        print(f"Gunakan flag --apply untuk mengubah {total_ditemukan} dokumen di atas menjadi non_publik.")

    # Bagian 2: Pemeriksaan default sumber scraping (Langkah 35b)
    print("\n=== Pemeriksaan Default Sumber Scraping ===")
    src_query = (
        db.query(ScrapingSource)
        .filter(
            ScrapingSource.default_document_role == PeranDokumen.draft_kajian,
            ScrapingSource.default_access_classification == KlasifikasiAkses.publik,
        )
        .order_by(ScrapingSource.id.asc())
    )
    if limit is not None:
        src_query = src_query.limit(limit)

    sources: List[ScrapingSource] = src_query.all()
    total_sumber = len(sources)

    print(f"Total sumber dengan default draft_kajian + publik: {total_sumber}")
    print("-" * 65)
    print(f"{'ID':<6} | {'Nama':<35} | {'Jenis'}")
    print("-" * 65)

    sumber_diubah = 0
    for src in sources:
        jenis_str = src.source_type.value if hasattr(src.source_type, "value") else str(src.source_type)
        nama_str = (src.name or "")[:35]
        print(f"{src.id:<6} | {nama_str:<35} | {jenis_str}")

        if apply:
            before_val = (
                src.default_access_classification.value
                if hasattr(src.default_access_classification, "value")
                else str(src.default_access_classification)
            )
            src.default_access_classification = KlasifikasiAkses.non_publik
            after_val = (
                src.default_access_classification.value
                if hasattr(src.default_access_classification, "value")
                else str(src.default_access_classification)
            )

            record_audit(
                db,
                action=UPDATE_SOURCE,
                user_id=None,
                target_resource=f"source:{src.id}",
                detail={
                    "alasan": "langkah35_sumber_draft_publik",
                    "before": {"default_access_classification": before_val},
                    "after": {"default_access_classification": after_val},
                },
                commit=False,
            )
            sumber_diubah += 1

    if apply and sumber_diubah > 0:
        db.commit()
        print("-" * 65)
        print(f"Sukses mengupdate {sumber_diubah} sumber menjadi non_publik.")
    elif not apply and total_sumber > 0:
        print("-" * 65)
        print(f"Gunakan flag --apply untuk mengubah {total_sumber} sumber di atas menjadi non_publik.")

    return {
        "total_ditemukan": total_ditemukan,
        "diubah": diubah_count,
        "total_sumber": total_sumber,
        "sumber_diubah": sumber_diubah,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Periksa dan amankan draft kajian berstatus publik tanpa persetujuan."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Terapkan perubahan klasifikasi ke non_publik dan catat audit log.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Batasi jumlah dokumen yang diperiksa/diubah.",
    )
    args = parser.parse_args()

    engine = create_engine(settings.database_url)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()

    try:
        run_periksa_draft_publik(db=db, apply=args.apply, limit=args.limit)
    finally:
        db.close()


if __name__ == "__main__":
    main()

