"""
app/services/corong_service.py
Layanan komputasi agregat statistik corong per sumber (Langkah 27).
Semua metrik dihitung melalui agregat SQL tanpa memuat baris dokumen penuh (zero full_text).
"""
from datetime import datetime, timezone
import io
import csv
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy import func, case, or_, and_, select, exists
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.article import Article
from app.models.scraping_source import ScrapingSource
from app.models.scan_session import ScanSession
from app.models.scan_candidate import ScanCandidate
from app.models.job_ingest import JobIngest
from app.models.ingest_failure import IngestFailure
from app.models.enums import (
    StatusPemrosesan,
    MetodeEkstraksi,
    StatusTindakLanjut,
    StatusKandidat,
)


def _compute_document_metrics(db: Session, doc_ids_query) -> Tuple[Dict[str, int], Dict[str, int]]:
    """
    Menghitung agregat metrik dokumen dan PDF untuk kumpulan document_id tertentu.
    Tidak ada pembacaan kolom full_text.
    """
    subq = doc_ids_query.subquery()

    row = (
        db.query(
            func.count(Document.id).label("di_kb"),
            func.count(case((Document.file_path_pdf.like("kb/%"), 1))).label("tersimpan_di_kb"),
            func.count(
                case((Document.processing_status.in_([StatusPemrosesan.diterima, StatusPemrosesan.diproses]), 1))
            ).label("menunggu_ekstraksi"),
            func.count(
                case(
                    (
                        and_(
                            Document.processing_status.in_([StatusPemrosesan.terindeks, StatusPemrosesan.perlu_koreksi]),
                            or_(
                                Document.extraction_method == MetodeEkstraksi.teks_langsung,
                                Document.extraction_method.is_(None),
                            ),
                        ),
                        1,
                    )
                )
            ).label("terbaca_teks_langsung"),
            func.count(
                case(
                    (
                        and_(
                            Document.processing_status.in_([StatusPemrosesan.terindeks, StatusPemrosesan.perlu_koreksi]),
                            Document.extraction_method == MetodeEkstraksi.ocr,
                        ),
                        1,
                    )
                )
            ).label("terbaca_ocr"),
            func.count(case((Document.processing_status == StatusPemrosesan.perlu_koreksi, 1))).label("perlu_koreksi"),
            func.count(case((Document.processing_status == StatusPemrosesan.gagal, 1))).label("gagal_baca"),
            func.count(
                case((Document.pdf_terproteksi.is_(True), 1))
            ).label("pdf_terproteksi"),
            func.count(
                case(
                    (
                        and_(
                            Document.pdf_terproteksi.is_(True),
                            Document.processing_status.in_([StatusPemrosesan.terindeks, StatusPemrosesan.perlu_koreksi]),
                        ),
                        1,
                    )
                )
            ).label("pdf_terproteksi_terbaca"),
            func.count(
                case((Document.pdf_terproteksi.is_(None), 1))
            ).label("pdf_belum_diperiksa"),
            func.count(
                case(
                    (
                        exists().where(Article.document_id == Document.id),
                        1,
                    )
                )
            ).label("terpecah_pasal"),
            func.count(
                case(
                    (
                        exists().where(
                            and_(
                                Article.document_id == Document.id,
                                Article.embedding.isnot(None),
                            )
                        ),
                        1,
                    )
                )
            ).label("tervektor"),
        )
        .filter(Document.id.in_(select(subq.c.id)))
        .one()
    )

    di_kb = row.di_kb or 0
    tersimpan_di_kb = row.tersimpan_di_kb or 0
    menunggu_ekstraksi = row.menunggu_ekstraksi or 0
    terbaca_teks_langsung = row.terbaca_teks_langsung or 0
    terbaca_ocr = row.terbaca_ocr or 0
    terbaca = terbaca_teks_langsung + terbaca_ocr
    perlu_koreksi = row.perlu_koreksi or 0
    gagal_baca = row.gagal_baca or 0
    lainnya = di_kb - (menunggu_ekstraksi + terbaca + gagal_baca)
    if lainnya < 0:
        lainnya = 0
    terpecah_pasal = row.terpecah_pasal or 0
    tervektor = row.tervektor or 0

    dokumen_data = {
        "di_kb": di_kb,
        "tersimpan_di_kb": tersimpan_di_kb,
        "menunggu_ekstraksi": menunggu_ekstraksi,
        "terbaca": terbaca,
        "terbaca_teks_langsung": terbaca_teks_langsung,
        "terbaca_ocr": terbaca_ocr,
        "perlu_koreksi": perlu_koreksi,
        "gagal_baca": gagal_baca,
        "lainnya": lainnya,
        "terpecah_pasal": terpecah_pasal,
        "tervektor": tervektor,
    }

    pdf_data = {
        "terproteksi": row.pdf_terproteksi or 0,
        "terproteksi_terbaca": row.pdf_terproteksi_terbaca or 0,
        "hasil_pindai_ocr": terbaca_ocr,
        "ocr_gagal": 0,  # diisi dari gagal_per_alasan
        "belum_diperiksa": row.pdf_belum_diperiksa or 0,
    }

    return dokumen_data, pdf_data


def get_corong_data(db: Session, source_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Menghitung seluruh statistik corong untuk semua sumber (atau satu sumber),
    unggah manual, dan total gabungan dengan deduplikasi dokumen unik.
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Ambil daftar sumber
    query_sources = db.query(ScrapingSource).order_by(ScrapingSource.id.asc())
    if source_id is not None:
        query_sources = query_sources.filter(ScrapingSource.id == source_id)
    sources = query_sources.all()

    sumber_list: List[Dict[str, Any]] = []

    for s in sources:
        s_id = s.id

        # 1. SCAN: Kandidat dari semua sesi scan sumber itu, unik per url_hash (ambil kandidat terbaru)
        latest_cands_subq = (
            db.query(func.max(ScanCandidate.id).label("id"))
            .join(ScanSession, ScanCandidate.scan_id == ScanSession.id)
            .filter(ScanSession.source_id == s_id)
            .group_by(ScanCandidate.url_hash)
            .subquery()
        )

        is_ditarik = and_(
            ScanCandidate.pull_outcome.in_(["success", "downloaded", "berhasil", "diunduh"]),
            ScanCandidate.document_id.isnot(None),
        )
        is_duplikat = and_(
            ScanCandidate.pull_outcome.in_(["duplicate", "duplikat"]),
            ~is_ditarik,
        )
        is_gagal = and_(
            or_(
                ScanCandidate.pull_outcome.in_(["failed", "gagal"]),
                ScanCandidate.failure_id.isnot(None),
            ),
            ~is_ditarik,
            or_(
                ScanCandidate.pull_outcome.is_(None),
                ~ScanCandidate.pull_outcome.in_(["duplicate", "duplikat"]),
            ),
        )
        is_sudah_ada = and_(
            ScanCandidate.document_id.is_(None),
            ScanCandidate.failure_id.is_(None),
            or_(
                ScanCandidate.pull_outcome.is_(None),
                ~ScanCandidate.pull_outcome.in_(["duplicate", "duplikat", "failed", "gagal", "success", "downloaded", "berhasil", "diunduh"]),
            ),
            or_(
                ScanCandidate.match_status.in_([StatusKandidat.sudah_ada, "sudah_ada", "match_found"]),
                ScanCandidate.match_document_id.isnot(None),
            ),
        )

        scan_row = (
            db.query(
                func.count(ScanCandidate.id).label("ditemukan"),
                func.count(case((is_ditarik, 1))).label("ditarik"),
                func.count(case((is_duplikat, 1))).label("duplikat"),
                func.count(case((is_gagal, 1))).label("gagal_unduh"),
                func.count(case((is_sudah_ada, 1))).label("sudah_ada_di_kb"),
            )
            .filter(ScanCandidate.id.in_(select(latest_cands_subq.c.id)))
            .one()
        )

        ditemukan = scan_row.ditemukan or 0
        ditarik = scan_row.ditarik or 0
        duplikat = scan_row.duplikat or 0
        gagal_unduh = scan_row.gagal_unduh or 0
        sudah_ada_di_kb = scan_row.sudah_ada_di_kb or 0
        belum_ditarik = ditemukan - (ditarik + duplikat + gagal_unduh + sudah_ada_di_kb)
        if belum_ditarik < 0:
            belum_ditarik = 0

        scan_dict = {
            "ditemukan": ditemukan,
            "sudah_ada_di_kb": sudah_ada_di_kb,
            "ditarik": ditarik,
            "duplikat": duplikat,
            "gagal_unduh": gagal_unduh,
            "belum_ditarik": belum_ditarik,
        }

        # 2. DOKUMEN & PDF: Dokumen aktif terkait sumber s_id
        doc_ids_query = (
            select(Document.id)
            .where(Document.is_active == True)  # noqa: E712
            .where(
                or_(
                    Document.job_id.in_(
                        select(JobIngest.id).where(JobIngest.source_id == s_id)
                    ),
                    Document.id.in_(
                        select(ScanCandidate.document_id)
                        .join(ScanSession, ScanCandidate.scan_id == ScanSession.id)
                        .where(ScanSession.source_id == s_id, ScanCandidate.document_id.isnot(None))
                    ),
                    Document.id.in_(
                        select(ScanCandidate.match_document_id)
                        .join(ScanSession, ScanCandidate.scan_id == ScanSession.id)
                        .where(ScanSession.source_id == s_id, ScanCandidate.match_document_id.isnot(None))
                    ),
                )
            )
        )
        dokumen_dict, pdf_dict = _compute_document_metrics(db, doc_ids_query)

        # 3. GAGAL PER ALASAN: IngestFailure terkait sumber, follow_up_status != diabaikan, bukan duplikat
        fail_subq = (
            select(IngestFailure.id)
            .where(
                or_(
                    IngestFailure.job_id.in_(
                        select(JobIngest.id).where(JobIngest.source_id == s_id)
                    ),
                    IngestFailure.id.in_(
                        select(ScanCandidate.failure_id)
                        .join(ScanSession, ScanCandidate.scan_id == ScanSession.id)
                        .where(ScanSession.source_id == s_id, ScanCandidate.failure_id.isnot(None))
                    ),
                )
            )
            .where(IngestFailure.follow_up_status != StatusTindakLanjut.diabaikan)
            .where(~IngestFailure.reason_code.in_(["duplikat", "duplicate"]))
        ).subquery()

        fail_rows = (
            db.query(IngestFailure.reason_code, func.count(IngestFailure.id))
            .filter(IngestFailure.id.in_(select(fail_subq.c.id)))
            .group_by(IngestFailure.reason_code)
            .all()
        )
        gagal_per_alasan: Dict[str, int] = {r[0]: r[1] for r in fail_rows if r[0]}

        pdf_dict["ocr_gagal"] = sum(
            count for reason, count in gagal_per_alasan.items() if reason in ("teks_kosong_ocr", "ocr_gagal")
        )

        persen_terbaca = (
            round((dokumen_dict["terbaca"] / dokumen_dict["di_kb"]) * 100.0, 1)
            if dokumen_dict["di_kb"] > 0
            else 0.0
        )

        jenis_str = s.source_type.value if hasattr(s.source_type, "value") else str(s.source_type)
        sumber_list.append({
            "source_id": s.id,
            "nama": s.name,
            "jenis": jenis_str,
            "scan": scan_dict,
            "dokumen": dokumen_dict,
            "pdf": pdf_dict,
            "gagal_per_alasan": gagal_per_alasan,
            "persen_terbaca": persen_terbaca,
        })

    # 4. UNGGAH MANUAL: Dokumen dan kegagalan yang job-nya tanpa source_id dan bukan kandidat scan
    manual_doc_ids_query = (
        select(Document.id)
        .where(Document.is_active == True)  # noqa: E712
        .where(
            or_(
                Document.job_id.is_(None),
                Document.job_id.in_(
                    select(JobIngest.id).where(JobIngest.source_id.is_(None))
                ),
            )
        )
        .where(
            ~Document.id.in_(
                select(ScanCandidate.document_id).where(ScanCandidate.document_id.isnot(None))
            )
        )
        .where(
            ~Document.id.in_(
                select(ScanCandidate.match_document_id).where(ScanCandidate.match_document_id.isnot(None))
            )
        )
    )
    manual_dokumen, manual_pdf = _compute_document_metrics(db, manual_doc_ids_query)

    manual_fail_subq = (
        select(IngestFailure.id)
        .where(
            or_(
                IngestFailure.job_id.is_(None),
                IngestFailure.job_id.in_(
                    select(JobIngest.id).where(JobIngest.source_id.is_(None))
                ),
            )
        )
        .where(
            ~IngestFailure.id.in_(
                select(ScanCandidate.failure_id).where(ScanCandidate.failure_id.isnot(None))
            )
        )
        .where(IngestFailure.follow_up_status != StatusTindakLanjut.diabaikan)
        .where(~IngestFailure.reason_code.in_(["duplikat", "duplicate"]))
    ).subquery()

    manual_fail_rows = (
        db.query(IngestFailure.reason_code, func.count(IngestFailure.id))
        .filter(IngestFailure.id.in_(select(manual_fail_subq.c.id)))
        .group_by(IngestFailure.reason_code)
        .all()
    )
    manual_gagal_per_alasan: Dict[str, int] = {r[0]: r[1] for r in manual_fail_rows if r[0]}
    manual_pdf["ocr_gagal"] = sum(
        count for reason, count in manual_gagal_per_alasan.items() if reason in ("teks_kosong_ocr", "ocr_gagal")
    )
    manual_persen_terbaca = (
        round((manual_dokumen["terbaca"] / manual_dokumen["di_kb"]) * 100.0, 1)
        if manual_dokumen["di_kb"] > 0
        else 0.0
    )

    unggah_manual = {
        "dokumen": manual_dokumen,
        "pdf": manual_pdf,
        "gagal_per_alasan": manual_gagal_per_alasan,
        "persen_terbaca": manual_persen_terbaca,
    }

    # 5. TOTAL: Seluruh sumber + manual upload. Dokumen dihitung unik via query seluruh Dokumen aktif
    total_scan = {
        "ditemukan": sum(s["scan"]["ditemukan"] for s in sumber_list),
        "sudah_ada_di_kb": sum(s["scan"]["sudah_ada_di_kb"] for s in sumber_list),
        "ditarik": sum(s["scan"]["ditarik"] for s in sumber_list),
        "duplikat": sum(s["scan"]["duplikat"] for s in sumber_list),
        "gagal_unduh": sum(s["scan"]["gagal_unduh"] for s in sumber_list),
        "belum_ditarik": sum(s["scan"]["belum_ditarik"] for s in sumber_list),
    }

    if source_id is not None:
        # Jika difilter per satu sumber, total dokumen menghitung unik dokumen sumber tersebut
        total_doc_ids_query = doc_ids_query
        total_fail_subq = fail_subq
    else:
        # Seluruh dokumen aktif di KB dihitung sekali secara unik
        total_doc_ids_query = select(Document.id).where(Document.is_active == True)  # noqa: E712
        total_fail_subq = (
            select(IngestFailure.id)
            .where(IngestFailure.follow_up_status != StatusTindakLanjut.diabaikan)
            .where(~IngestFailure.reason_code.in_(["duplikat", "duplicate"]))
        ).subquery()

    total_dokumen, total_pdf = _compute_document_metrics(db, total_doc_ids_query)

    total_fail_rows = (
        db.query(IngestFailure.reason_code, func.count(IngestFailure.id))
        .filter(IngestFailure.id.in_(select(total_fail_subq.c.id)))
        .group_by(IngestFailure.reason_code)
        .all()
    )
    total_gagal_per_alasan: Dict[str, int] = {r[0]: r[1] for r in total_fail_rows if r[0]}
    total_pdf["ocr_gagal"] = sum(
        count for reason, count in total_gagal_per_alasan.items() if reason in ("teks_kosong_ocr", "ocr_gagal")
    )
    total_persen_terbaca = (
        round((total_dokumen["terbaca"] / total_dokumen["di_kb"]) * 100.0, 1)
        if total_dokumen["di_kb"] > 0
        else 0.0
    )

    total_dict = {
        "scan": total_scan,
        "dokumen": total_dokumen,
        "pdf": total_pdf,
        "gagal_per_alasan": total_gagal_per_alasan,
        "persen_terbaca": total_persen_terbaca,
    }

    return {
        "dihitung_pada": now_utc,
        "sumber": sumber_list,
        "unggah_manual": unggah_manual,
        "total": total_dict,
    }


def generate_corong_csv(data: Dict[str, Any]) -> Tuple[bytes, Dict[str, str]]:
    """
    Menghasilkan file CSV statistik corong bertanda BOM (UTF-8 with BOM / utf-8-sig).
    Memiliki satu baris per sumber, ditambah baris 'Unggah manual' dan baris 'TOTAL'.
    """
    # Kumpulkan semua reason_code kegagalan yang muncul
    all_reasons = set()
    for s in data.get("sumber", []):
        all_reasons.update(s.get("gagal_per_alasan", {}).keys())
    all_reasons.update(data.get("unggah_manual", {}).get("gagal_per_alasan", {}).keys())
    all_reasons.update(data.get("total", {}).get("gagal_per_alasan", {}).keys())
    sorted_reasons = sorted(list(all_reasons))

    headers = [
        "sumber_id",
        "sumber_nama",
        "sumber_jenis",
        "scan_ditemukan",
        "scan_sudah_ada_di_kb",
        "scan_ditarik",
        "scan_duplikat",
        "scan_gagal_unduh",
        "scan_belum_ditarik",
        "dokumen_di_kb",
        "dokumen_tersimpan_di_kb",
        "dokumen_menunggu_ekstraksi",
        "dokumen_terbaca",
        "dokumen_terbaca_teks_langsung",
        "dokumen_terbaca_ocr",
        "dokumen_perlu_koreksi",
        "dokumen_gagal_baca",
        "dokumen_lainnya",
        "dokumen_terpecah_pasal",
        "dokumen_tervektor",
        "pdf_terproteksi",
        "pdf_terproteksi_terbaca",
        "pdf_hasil_pindai_ocr",
        "pdf_ocr_gagal",
        "pdf_belum_diperiksa",
    ]
    for r in sorted_reasons:
        headers.append(f"gagal_{r}")
    headers.append("persen_terbaca")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    # Baris per sumber
    for s in data.get("sumber", []):
        sc = s.get("scan", {})
        dk = s.get("dokumen", {})
        pf = s.get("pdf", {})
        gf = s.get("gagal_per_alasan", {})
        row = [
            s.get("source_id", ""),
            s.get("nama", ""),
            s.get("jenis", ""),
            sc.get("ditemukan", 0),
            sc.get("sudah_ada_di_kb", 0),
            sc.get("ditarik", 0),
            sc.get("duplikat", 0),
            sc.get("gagal_unduh", 0),
            sc.get("belum_ditarik", 0),
            dk.get("di_kb", 0),
            dk.get("tersimpan_di_kb", 0),
            dk.get("menunggu_ekstraksi", 0),
            dk.get("terbaca", 0),
            dk.get("terbaca_teks_langsung", 0),
            dk.get("terbaca_ocr", 0),
            dk.get("perlu_koreksi", 0),
            dk.get("gagal_baca", 0),
            dk.get("lainnya", 0),
            dk.get("terpecah_pasal", 0),
            dk.get("tervektor", 0),
            pf.get("terproteksi", 0),
            pf.get("terproteksi_terbaca", 0),
            pf.get("hasil_pindai_ocr", 0),
            pf.get("ocr_gagal", 0),
            pf.get("belum_diperiksa", 0),
        ]
        for r in sorted_reasons:
            row.append(gf.get(r, 0))
        row.append(s.get("persen_terbaca", 0.0))
        writer.writerow(row)

    # Baris Unggah manual
    man = data.get("unggah_manual", {})
    mdk = man.get("dokumen", {})
    mpf = man.get("pdf", {})
    mgf = man.get("gagal_per_alasan", {})
    manual_row = [
        "",
        "Unggah manual",
        "manual",
        0, 0, 0, 0, 0, 0,
        mdk.get("di_kb", 0),
        mdk.get("tersimpan_di_kb", 0),
        mdk.get("menunggu_ekstraksi", 0),
        mdk.get("terbaca", 0),
        mdk.get("terbaca_teks_langsung", 0),
        mdk.get("terbaca_ocr", 0),
        mdk.get("perlu_koreksi", 0),
        mdk.get("gagal_baca", 0),
        mdk.get("lainnya", 0),
        mdk.get("terpecah_pasal", 0),
        mdk.get("tervektor", 0),
        mpf.get("terproteksi", 0),
        mpf.get("terproteksi_terbaca", 0),
        mpf.get("hasil_pindai_ocr", 0),
        mpf.get("ocr_gagal", 0),
        mpf.get("belum_diperiksa", 0),
    ]
    for r in sorted_reasons:
        manual_row.append(mgf.get(r, 0))
    manual_row.append(man.get("persen_terbaca", 0.0))
    writer.writerow(manual_row)

    # Baris TOTAL
    tot = data.get("total", {})
    tsc = tot.get("scan", {})
    tdk = tot.get("dokumen", {})
    tpf = tot.get("pdf", {})
    tgf = tot.get("gagal_per_alasan", {})
    total_row = [
        "",
        "TOTAL",
        "",
        tsc.get("ditemukan", 0),
        tsc.get("sudah_ada_di_kb", 0),
        tsc.get("ditarik", 0),
        tsc.get("duplikat", 0),
        tsc.get("gagal_unduh", 0),
        tsc.get("belum_ditarik", 0),
        tdk.get("di_kb", 0),
        tdk.get("tersimpan_di_kb", 0),
        tdk.get("menunggu_ekstraksi", 0),
        tdk.get("terbaca", 0),
        tdk.get("terbaca_teks_langsung", 0),
        tdk.get("terbaca_ocr", 0),
        tdk.get("perlu_koreksi", 0),
        tdk.get("gagal_baca", 0),
        tdk.get("lainnya", 0),
        tdk.get("terpecah_pasal", 0),
        tdk.get("tervektor", 0),
        tpf.get("terproteksi", 0),
        tpf.get("terproteksi_terbaca", 0),
        tpf.get("hasil_pindai_ocr", 0),
        tpf.get("ocr_gagal", 0),
        tpf.get("belum_diperiksa", 0),
    ]
    for r in sorted_reasons:
        total_row.append(tgf.get(r, 0))
    total_row.append(tot.get("persen_terbaca", 0.0))
    writer.writerow(total_row)

    csv_text = output.getvalue()
    csv_bytes = csv_text.encode("utf-8-sig")

    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename_ascii = f"corong-hero-{today_str}.csv"
    encoded_filename = urllib.parse.quote(filename_ascii)
    headers_dict = {
        "Content-Disposition": f'attachment; filename="{filename_ascii}"; filename*=UTF-8\'\'{encoded_filename}'
    }

    return csv_bytes, headers_dict
