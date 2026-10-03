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
    KlasifikasiAkses,
    PeranDokumen,
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


def test_g03_scan_folder_lokal_deduplication(client: TestClient, db_session: Session, tmp_path, monkeypatch):
    """
    G03: Scan sumber folder_lokal berisi 3 PDF (1 sudah ada di KB).
    Ekspektasi: 3 kandidat ditemukan, 1 berstatus sudah_ada (hash + ukuran), 2 baru.
    """
    from app.config import settings
    from app.models.document import Document
    from app.services.scan_service import ScanService
    from app.services.file_validation import fingerprint

    root_dir = tmp_path / "g03_root"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    # Buat 3 dummy PDF
    pdf_header = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    content1 = pdf_header + b"Dokumen Satu Unique 11111"
    content2 = pdf_header + b"Dokumen Dua Unique 22222"
    content3 = pdf_header + b"Dokumen Tiga Unique 33333"

    p1 = root_dir / "doc1.pdf"
    p2 = root_dir / "doc2.pdf"
    p3 = root_dir / "doc3.pdf"
    p1.write_bytes(content1)
    p2.write_bytes(content2)
    p3.write_bytes(content3)

    # Masukkan doc1 ke KB
    fp1 = fingerprint(content1)
    doc_existing = Document(
        title="Dokumen Eksisting Satu",
        original_filename="doc1.pdf",
        standardized_filename="doc1.pdf",
        file_hash=fp1.sha256,
        file_size_bytes=fp1.size_bytes,
        file_path_pdf="pdf/_inbox/doc1.pdf",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
    )
    db_session.add(doc_existing)
    db_session.commit()

    # Daftarkan sumber folder_lokal
    resp_src = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Sumber G03", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    assert resp_src.status_code == 201, resp_src.text
    src_id = resp_src.json()["id"]

    # Buat dan eksekusi sesi pemindaian secara sinkron (wait=true)
    resp_scan = client.post("/api/v1/scans/?wait=true", json={"source_id": src_id})
    assert resp_scan.status_code == 200, resp_scan.text
    scan_id = resp_scan.json()["id"]

    # Ambil kandidat
    resp_cand = client.get(f"/api/v1/scans/{scan_id}/candidates")
    assert resp_cand.status_code == 200
    cands = resp_cand.json()["items"]
    assert len(cands) == 3

    sudah_ada_list = [c for c in cands if c["match_status"] == "sudah_ada"]
    baru_list = [c for c in cands if c["match_status"] == "baru"]
    assert len(sudah_ada_list) == 1
    assert len(baru_list) == 2
    assert sudah_ada_list[0]["match_document_id"] == doc_existing.id
    assert sudah_ada_list[0]["match_reason"] == "hash_dan_ukuran_sama"
    assert sudah_ada_list[0]["selected"] is False


def test_g04_and_g08_pull_folder_lokal_with_naming_format_and_category(client: TestClient, db_session: Session, tmp_path, monkeypatch):
    """
    G04: Pull folder lokal ke KB dengan naming_format -> nama sesuai format.
    G08: Pull dengan category_id valid -> dokumen berada di kategori itu.
    """
    from app.config import settings
    from app.models.category import Category
    from app.models.document import Document

    root_dir = tmp_path / "g04_root"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    # Buat kategori baru
    cat = Category(name="Perbankan Syariah G04")
    db_session.add(cat)
    db_session.commit()
    db_session.refresh(cat)

    pdf_header = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    content = pdf_header + b"Konten Uji G04 POJK_5_2022"
    fpath = root_dir / "Peraturan_OJK_5_2022.pdf"
    fpath.write_bytes(content)

    resp_src = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Sumber G04", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    src_id = resp_src.json()["id"]

    resp_scan = client.post("/api/v1/scans/?wait=true", json={"source_id": src_id})
    assert resp_scan.status_code == 200, resp_scan.text
    scan_id = resp_scan.json()["id"]

    # Pull kandidat ke KB dengan naming_format dan category_id
    resp_pull = client.post(
        f"/api/v1/scans/{scan_id}/pull?wait=true",
        json={
            "destination": "knowledge_base",
            "naming_format": ["jenis", "nomor", "tahun"],
            "naming_separator": "-",
            "category_id": cat.id,
        },
    )
    assert resp_pull.status_code == 200, resp_pull.text

    cands_res = client.get(f"/api/v1/scans/{scan_id}/candidates").json()
    print("DEBUG PULL RESP:", resp_pull.json())
    print("DEBUG CANDIDATES:", cands_res)

    db_session.expire_all()
    # Cek dokumen yang tersimpan di DB
    doc = db_session.query(Document).filter(Document.original_filename == "Peraturan_OJK_5_2022.pdf").first()
    assert doc is not None
    assert doc.category_id == cat.id
    # Verifikasi nama baku sesuai format [jenis, nomor, tahun] dengan separator '-'
    assert "POJK" in doc.standardized_filename
    assert "2022" in doc.standardized_filename


def test_g05_pull_folder_lokal_unduh_folder_rejected(client: TestClient, db_session: Session, tmp_path, monkeypatch):
    """
    G05: Pull folder lokal dengan unduh_folder -> 422 dengan pesan yang jelas.
    """
    from app.config import settings

    root_dir = tmp_path / "g05_root"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    pdf_header = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    (root_dir / "sample.pdf").write_bytes(pdf_header + b"Sample")

    resp_src = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Sumber G05", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    src_id = resp_src.json()["id"]

    resp_scan = client.post("/api/v1/scans/?wait=true", json={"source_id": src_id})
    assert resp_scan.status_code == 200, resp_scan.text
    scan_id = resp_scan.json()["id"]

    resp_pull = client.post(
        f"/api/v1/scans/{scan_id}/pull",
        json={"destination": "unduh_folder"},
    )
    assert resp_pull.status_code == 422
    assert "unduh_folder" in resp_pull.json()["detail"].lower()
    assert "folder lokal" in resp_pull.json()["detail"].lower()


def test_g06_folder_options_security_and_symlink(client: TestClient, db_session: Session, tmp_path, monkeypatch):
    """
    G06: folder-options dengan symlink keluar root tidak boleh bocor.
    """
    from app.config import settings
    from pathlib import Path

    root_dir = tmp_path / "allowed_root"
    outside_dir = tmp_path / "forbidden_outside"
    root_dir.mkdir(parents=True, exist_ok=True)
    outside_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    # Buat subfolder sah
    valid_sub = root_dir / "valid_subfolder"
    valid_sub.mkdir()
    (valid_sub / "test1.pdf").write_bytes(b"%PDF-1.4 sample")

    # Buat file di luar
    (outside_dir / "secret.pdf").write_bytes(b"%PDF-1.4 secret")

    # Buat symlink keluar root (jika OS mengizinkan)
    symlink_path = root_dir / "leak_link"
    try:
        os.symlink(outside_dir, symlink_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pass

    resp = client.get("/api/v1/scraping-sources/folder-options")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]

    # Pastikan valid_subfolder ada di daftar
    paths = [it["path"] for it in items]
    names = [it["name"] for it in items]
    assert any("valid_subfolder" in n for n in names)

    # Pastikan tidak ada path yang merujuk ke luar root_dir
    for it in items:
        p = Path(it["path"])
        assert p.is_relative_to(root_dir.resolve()), f"Path bocor di luar root: {p}"
        assert "forbidden_outside" not in it["path"]


def test_g07_pull_category_id_invalid(client: TestClient, db_session: Session, tmp_path, monkeypatch):
    """
    G07: Pull dengan category_id tidak ada -> 422.
    """
    from app.config import settings
    from app.services.scan_service import ScanService

    root_dir = tmp_path / "g07_root"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    (root_dir / "doc.pdf").write_bytes(b"%PDF-1.4 content")

    resp_src = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Sumber G07", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    src_id = resp_src.json()["id"]

    resp_scan = client.post("/api/v1/scans/?wait=true", json={"source_id": src_id})
    assert resp_scan.status_code == 200, resp_scan.text
    scan_id = resp_scan.json()["id"]

    resp_pull = client.post(
        f"/api/v1/scans/{scan_id}/pull",
        json={"destination": "knowledge_base", "category_id": 999999},
    )
    assert resp_pull.status_code == 422
    assert "999999" in resp_pull.json()["detail"]


def test_g09_bidang_normalization():
    """
    G09: Bidang 'Penjaminan , dan' -> tersimpan 'Penjaminan, dan'.
    """
    from app.crawlers.url_utils import normalize_bidang

    raw = "Perasuransian, Penjaminan , dan Dana Pensiun"
    normalized = normalize_bidang(raw)
    assert normalized == "Perasuransian, Penjaminan, dan Dana Pensiun"

    raw2 = "  Pasar Modal  ,  Keuangan Derivatif , dan Bursa Karbon   "
    assert normalize_bidang(raw2) == "Pasar Modal, Keuangan Derivatif, dan Bursa Karbon"


def test_g10_onedrive_filename_format():
    """
    G10: OneDrive Peraturan_OJK_3_2015.pdf -> POJK 3 Tahun 2015
    """
    from app.crawlers.url_utils import parse_onedrive_filename_metadata

    res = parse_onedrive_filename_metadata("Peraturan_OJK_3_2015.pdf")
    assert res.get("regulation_number") == "POJK 3 Tahun 2015"
    assert res.get("regulation_type") == "POJK"
    assert res.get("release_year") == 2015
