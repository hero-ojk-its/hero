"""
tests/test_step12_ingest_support.py
Pengujian untuk Langkah 12: Dukungan Halaman Ingest + Perbaikan Data Seed
G01: Kandidat JDIH berstatus dicabut di DB -> API candidates mengembalikan dicabut, effective_date, match_warning
G02: Tes anti-regresi generik kesetaraan seluruh kolom ScanCandidate terhadap CandidateResponse
G03: Scan sumber folder_lokal berisi 3 PDF (1 sudah ada di KB)
G04: Pull folder lokal ke KB dengan naming_format
G05: Pull folder lokal dengan unduh_folder -> 422
G06: folder-options dengan symlink keluar root -> tidak bocor
G07: Pull dengan category_id tidak ada -> 422
G08: Pull dengan category_id valid -> dokumen masuk ke kategori itu
G09: Normalisasi bidang spasi dan koma ("Penjaminan , dan" -> "Penjaminan, dan")
G10: OneDrive regulation_number parsing ("POJK 3 Tahun 2015")
G11: pytest -q lulus
"""
import os
import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import (
    StatusKeberlakuan,
    StatusKandidat,
    StatusPindai,
    JenisSumber,
)
from app.models.scan_session import ScanSession
from app.models.scan_candidate import ScanCandidate
from app.models.scraping_source import ScrapingSource
from app.schemas.scan import CandidateResponse


def test_g01_and_g02_generic_candidate_response_regression(client: TestClient, db_session: Session):
    """
    G01 & G02: Tes anti-regresi generik untuk GET /api/v1/scans/{id}/candidates
    Setiap kolom di model ScanCandidate yang ada di CandidateResponse
    HARUS bernilai sama persis antara respons API dan isi database.
    """
    # 1. Buat session dan candidate dengan nilai non-default spesifik
    session = ScanSession(
        start_url="https://jdih.ojk.go.id/test-scan",
        crawl_depth=1,
        status=StatusPindai.siap_dipilih,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    cand = ScanCandidate(
        scan_id=session.id,
        url="https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/guid-123",
        url_hash="hash1234567890abcdef",
        filename="pojk_99_dicabut.pdf",
        size_bytes=987654,
        found_on_page="https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/guid-123",
        document_title="POJK Pengujian Penanganan Krisis",
        detail_url="https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/guid-123",
        final_url="https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/guid-123",
        doc_kind="utama",
        regulation_number="POJK 99/POJK.03/2026",
        regulation_type="POJK",
        bidang="Perbankan",
        sub_bidang="Bank Digital",
        release_date=date(2026, 1, 15),
        effective_date=date(2026, 2, 1),
        match_warning="Peringatan nomor dan tahun tidak sesuai",
        status_keberlakuan=StatusKeberlakuan.dicabut.value,
        size_source="range",
        source_path="regulasi/2026/pojk_99_dicabut.pdf",
        depth=1,
        match_status=StatusKandidat.baru,
        match_reason="Belum pernah ditarik",
        selected=True,
        message="Terverifikasi dari fixture resmi",
    )
    db_session.add(cand)
    db_session.commit()
    db_session.refresh(cand)

    # 2. Panggil API endpoint kandidat
    resp = client.get(f"/api/v1/scans/{session.id}/candidates")
    assert resp.status_code == 200, f"Gagal mendapatkan kandidat: {resp.text}"
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]

    # G01 spesifik: pastikan status_keberlakuan, effective_date, match_warning terisi benar
    assert item["status_keberlakuan"] == "dicabut", f"status_keberlakuan hilang: {item.get('status_keberlakuan')}"
    assert item["effective_date"] == "2026-02-01", f"effective_date hilang: {item.get('effective_date')}"
    assert item["match_warning"] == "Peringatan nomor dan tahun tidak sesuai", f"match_warning hilang: {item.get('match_warning')}"

    # G02 generik: periksa semua kolom model ScanCandidate yang ada di CandidateResponse
    candidate_cols = [c.name for c in ScanCandidate.__table__.columns]
    schema_fields = CandidateResponse.model_fields.keys()
    checked_fields = []

    mismatches = []
    for col in candidate_cols:
        if col in schema_fields:
            checked_fields.append(col)
            db_val = getattr(cand, col)
            api_val = item.get(col)

            # Normalisasi tipe data untuk perbandingan
            if isinstance(db_val, date):
                expected = db_val.isoformat()
            elif hasattr(db_val, "value"):
                expected = db_val.value
            else:
                expected = db_val

            if api_val != expected:
                mismatches.append(
                    f"Field '{col}': di DB={expected!r}, di API response={api_val!r}"
                )

    assert not mismatches, "Ditemukan field ScanCandidate yang hilang/berbeda di respons API:\n" + "\n".join(mismatches)
    assert len(checked_fields) >= 20, f"Terlalu sedikit field yang dicek ({len(checked_fields)})"
