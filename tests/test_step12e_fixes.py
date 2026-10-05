"""
tests/test_step12e_fixes.py
Pengujian verifikasi Langkah 12e (Tanggal Karangan 1 Januari di Folder Lokal):
1. Pindai folder berisi POJK_11_2022_xxx.pdf menghasilkan kandidat dengan release_date null dan regulation_year 2022.
2. _parse_indonesian_date("2022") menghasilkan None.
3. _parse_indonesian_date("12 Oktober 2022") tetap menghasilkan tanggal (date(2022, 10, 12)).
4. Verifikasi penarikan (pull) kandidat folder lokal ke KB menghasilkan Document dengan release_date=None dan regulation_year=2022.
"""
from datetime import date
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.crawlers.sharepoint_postback import _parse_indonesian_date
from app.models.document import Document
from tests.conftest import make_pdf


def test_e01_parse_indonesian_date_year_only_returns_none():
    """Langkah 12e: Bila hanya ada tahun, _parse_indonesian_date mengembalikan None (bukan 1 Januari)."""
    assert _parse_indonesian_date("2022") is None
    assert _parse_indonesian_date("1995") is None
    assert _parse_indonesian_date("2025") is None
    assert _parse_indonesian_date("Tahun 2023") is None


def test_e02_parse_indonesian_date_full_date_returns_date():
    """Langkah 12e: Tanggal lengkap tetap menghasilkan objek date yang valid."""
    assert _parse_indonesian_date("12 Oktober 2022") == date(2022, 10, 12)
    assert _parse_indonesian_date("14 Maret 2024") == date(2024, 3, 14)
    assert _parse_indonesian_date("1 Januari 2023") == date(2023, 1, 1)
    assert _parse_indonesian_date("2024-03-14") == date(2024, 3, 14)
    assert _parse_indonesian_date("10/12/2022") == date(2022, 10, 12)


def test_e03_scan_folder_pojk_2022_release_date_null_and_regulation_year_2022(
    client: TestClient, db_session: Session, tmp_path: Path, monkeypatch
):
    """
    Langkah 12e: Pemindaian folder lokal berisi POJK_11_2022_xxx.pdf
    menghasilkan kandidat dengan release_date null dan regulation_year 2022.
    """
    root_dir = tmp_path / "sources_12e"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    pdf_fname = "POJK_11_2022_Penyelenggaraan_Teknologi_Informasi.pdf"
    (root_dir / pdf_fname).write_bytes(make_pdf("Konten Uji POJK 11 2022"))

    # Daftarkan sumber folder_lokal
    resp_src = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder Uji 12e", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    assert resp_src.status_code == 201, resp_src.text
    src_id = resp_src.json()["id"]

    # Jalankan scan secara sinkron
    resp_scan = client.post("/api/v1/scans/?wait=true", json={"source_id": src_id})
    assert resp_scan.status_code == 200, resp_scan.text
    scan_id = resp_scan.json()["id"]

    # Periksa kandidat
    resp_cand = client.get(f"/api/v1/scans/{scan_id}/candidates")
    assert resp_cand.status_code == 200, resp_cand.text
    items = resp_cand.json()["items"]
    assert len(items) == 1

    cand = items[0]
    assert cand["filename"] == pdf_fname
    assert cand["release_date"] is None, f"Expected release_date None, got {cand['release_date']}"
    assert cand["regulation_year"] == 2022, f"Expected regulation_year 2022, got {cand['regulation_year']}"


def test_e04_pull_folder_candidate_preserves_null_release_date(
    client: TestClient, db_session: Session, tmp_path: Path, monkeypatch
):
    """
    Langkah 12e: Penarikan berkas kandidat folder lokal ke KB
    menghasilkan entri Document dengan release_date None dan regulation_year 2022.
    """
    root_dir = tmp_path / "sources_12e_pull"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    pdf_fname = "POJK_11_2022_Penyelenggaraan_Teknologi_Informasi.pdf"
    (root_dir / pdf_fname).write_bytes(make_pdf("Konten Uji Pull POJK 11 2022"))

    resp_src = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder Uji Pull 12e", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    assert resp_src.status_code == 201
    src_id = resp_src.json()["id"]

    resp_scan = client.post("/api/v1/scans/?wait=true", json={"source_id": src_id})
    assert resp_scan.status_code == 200
    scan_id = resp_scan.json()["id"]

    # Tarik ke KB
    resp_pull = client.post(
        f"/api/v1/scans/{scan_id}/pull?wait=true",
        json={"destination": "knowledge_base"},
    )
    assert resp_pull.status_code == 200, resp_pull.text

    # Verifikasi Dokumen di DB
    doc = db_session.query(Document).filter(Document.original_filename == pdf_fname).first()
    assert doc is not None
    assert doc.release_date is None
    assert doc.regulation_year == 2022
