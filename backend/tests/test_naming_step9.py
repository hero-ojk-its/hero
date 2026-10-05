"""
tests/test_naming_step9.py
Pengujian otomatis untuk Fitur Penamaan Berkas Dinamis & Kontrak API Langkah 9 (N01 - N14 & C01 - C04).
"""
import io
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import Document
from app.models.enums import (
    JenisSumber,
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
    StatusPindai,
    StatusKandidat,
    TujuanTarik,
)
from app.models.scan_session import ScanSession
from app.models.scan_candidate import ScanCandidate
from app.models.scraping_source import ScrapingSource
from app.services.naming_service import (
    NamingInput,
    build_standard_filename,
    validate_naming_format,
    validate_naming_separator,
    VALID_NAMING_COMPONENTS,
    COMPONENT_ORDER_UI,
)
from app.services.storage_service import get_storage_service
from tests.conftest import make_pdf


# ==================== N01 - N06: UNIT TESTING NAMING SERVICE ====================

def test_n01_build_filename_basic_metadata_complete():
    """N01: build_filename(["nama","jenis","tahun"]), metadata lengkap -> Penyelenggaraan Bursa… POJK 2026.pdf"""
    inp = NamingInput(
        title="Penyelenggaraan Bursa Karbon Melalui Bursa Efek",
        regulation_type="Peraturan Otoritas Jasa Keuangan",
        release_date=datetime(2026, 8, 20, tzinfo=timezone.utc),
        regulation_number="POJK 14/2026",
    )
    res = build_standard_filename(inp, naming_format=["nama", "jenis", "tahun"])
    assert res.endswith(".pdf")
    assert "Penyelenggaraan Bursa Karbon Melalui Bursa Efek" in res
    assert "POJK" in res
    assert "2026" in res
    assert res == "Penyelenggaraan Bursa Karbon Melalui Bursa Efek POJK 2026.pdf"


def test_n02_repeated_components():
    """N02: Komponen berulang ["tahun","nama","tahun"] -> Tahun muncul dua kali"""
    inp = NamingInput(
        title="Peraturan Pasar Modal",
        release_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    res = build_standard_filename(inp, naming_format=["tahun", "nama", "tahun"])
    assert res == "2025 Peraturan Pasar Modal 2025.pdf"


def test_n03_empty_bidang_fallback_to_wildcard():
    """N03: bidang kosong -> Diganti NA, rename tidak gagal"""
    inp = NamingInput(
        title="Regulasi Fintech",
        bidang=None,
        release_date=datetime(2024, 5, 1, tzinfo=timezone.utc),
    )
    res = build_standard_filename(inp, naming_format=["nama", "bidang", "tahun"])
    assert res == "Regulasi Fintech NA 2024.pdf"


def test_n04_unknown_naming_keys(client: TestClient):
    """N04: Kunci tidak dikenal ["nama","warna"] -> 422 dengan pesan menyebut warna dan daftar valid"""
    with pytest.raises(HTTPException) as exc:
        validate_naming_format(["nama", "warna"])
    assert exc.value.status_code == 422
    msg = str(exc.value.detail)
    assert "warna" in msg
    assert "nama" in msg
    assert "nomor" in msg
    assert "tahun" in msg

    # Endpoint test via /naming/preview
    resp = client.post("/api/v1/naming/preview", json={"naming_format": ["nama", "warna"]})
    assert resp.status_code == 422
    assert "warna" in resp.json()["detail"]


def test_n05_legacy_template_compatibility():
    """N05: Template lama {nomor} {judul} {tahun} -> Hasil identik sebelum refaktor"""
    inp = NamingInput(
        title="Kesehatan Bank",
        regulation_number="POJK 10/2026",
        release_date=datetime(2026, 3, 15, tzinfo=timezone.utc),
    )
    res = build_standard_filename(inp, template="{nomor} {judul} {tahun}")
    assert res == "POJK 10-2026 Kesehatan Bank 2026.pdf"


def test_n06_separator_and_illegal_character_cleaning():
    """N06: Separator _ dan karakter ilegal di judul (: / ?) -> Dibersihkan, separator dipakai"""
    inp = NamingInput(
        title="Regulasi: Perbankan / Syariah & Keuangan? Modern",
        regulation_type="POJK",
        release_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    res = build_standard_filename(inp, naming_format=["nama", "jenis", "tahun"], naming_separator="_")
    assert "/" not in res
    assert ":" not in res
    assert "?" not in res
    assert res == "Regulasi Perbankan - Syariah Keuangan Modern_POJK_2026.pdf"


# ==================== N07 - N14: INTEGRATION TESTING ====================

def test_n07_upload_pdf_with_naming_format_and_inbox_hash(client: TestClient, db_session: Session):
    """N07: Unggah 1 PDF dengan naming_format=nama,tahun tanpa metadata -> Tersimpan di _inbox dengan nama …NA__<hash>.pdf; documents.naming_format = ["nama","tahun"]"""
    pdf_content = make_pdf("Dokumen Konten Uji N07")
    files = [("files", ("n07_sample.pdf", pdf_content, "application/pdf"))]
    form_data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "naming_format": "nama,tahun",
        "naming_separator": "_",
    }
    resp = client.post("/api/v1/ingest/upload-pdf", files=files, data=form_data)
    assert resp.status_code == 200
    doc_id = resp.json()["details"][0]["document_id"]

    doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert doc is not None
    assert doc.naming_format == ["nama", "tahun"]
    assert doc.naming_separator == "_"
    assert doc.file_path_pdf.startswith("pdf/_inbox/")
    # File in inbox must have __<8hex>.pdf
    assert "__" in doc.file_path_pdf
    assert doc.file_path_pdf.endswith(".pdf")
    assert "NA" in doc.standardized_filename or "n07_sample" in doc.standardized_filename


def test_n08_patch_metadata_triggers_placement_with_custom_format(client: TestClient, db_session: Session):
    """N08: Lanjutan N07: PATCH metadata (jenis, tahun, bidang) -> Pindah ke kb/{jenis}/{tahun}/ dengan nama sesuai format ["nama","tahun"], bukan template default"""
    pdf_content = make_pdf("Dokumen Konten Uji N08")
    files = [("files", ("regulasi_bursa.pdf", pdf_content, "application/pdf"))]
    form_data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "naming_format": "nama,tahun",
        "naming_separator": " ",
    }
    resp = client.post("/api/v1/ingest/upload-pdf", files=files, data=form_data)
    assert resp.status_code == 200
    doc_id = resp.json()["details"][0]["document_id"]

    # Patch metadata to satisfy placement condition (jenis + tahun + nomor)
    patch_payload = {
        "title": "Bursa Karbon Indonesia",
        "regulation_type": "POJK",
        "release_date": "2026-08-15",
        "regulation_number": "POJK 16/2026",
        "bidang": "BMKS",
    }
    resp_patch = client.patch(f"/api/v1/documents/{doc_id}/metadata", json=patch_payload)
    assert resp_patch.status_code == 200

    doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert doc.file_path_pdf.replace("\\", "/").startswith("kb/POJK/2026/")
    assert doc.standardized_filename == "Bursa Karbon Indonesia 2026.pdf"


def test_n09_pull_knowledge_base_stores_naming_format(client: TestClient, db_session: Session, monkeypatch):
    """N09: Pull knowledge_base dengan naming_format -> Format tersimpan di scan_sessions dan di dokumen"""
    # 1. Buat source
    src = ScrapingSource(
        name="Source N09",
        url="https://jdih.ojk.go.id/n09",
        source_type=JenisSumber.situs_web,
        crawl_depth=1,
        default_access_classification=KlasifikasiAkses.publik,
        default_document_role=PeranDokumen.corpus_eksisting,
    )
    db_session.add(src)
    db_session.flush()

    # 2. Buat session scan
    sess = ScanSession(
        source_id=src.id,
        start_url=src.url,
        crawl_depth=1,
        mode="test",
        status=StatusPindai.siap_dipilih,
    )
    db_session.add(sess)
    db_session.flush()

    import hashlib
    url = "https://jdih.ojk.go.id/n09/doc1.pdf"
    cand = ScanCandidate(
        scan_id=sess.id,
        url=url,
        url_hash=hashlib.sha256(url.encode()).hexdigest(),
        filename="doc1.pdf",
        size_bytes=1000,
        match_status=StatusKandidat.baru,
        selected=True,
    )
    db_session.add(cand)
    db_session.commit()

    # Mock crawler fetch
    class MockFetched:
        filename = "doc1.pdf"
        content = make_pdf("Konten doc1 N09")
    monkeypatch.setattr("app.services.scan_service.get_crawler", lambda s: type("MockC", (), {"fetch": lambda self, u, **kw: MockFetched()})())

    # 3. Pull dengan format
    pull_payload = {
        "destination": "knowledge_base",
        "naming_format": ["nama", "bidang", "tahun"],
        "naming_separator": "_",
    }
    resp = client.post(f"/api/v1/scans/{sess.id}/pull?wait=true", json=pull_payload)
    assert resp.status_code == 200

    db_session.refresh(sess)
    assert sess.naming_format == ["nama", "bidang", "tahun"]
    assert sess.naming_separator == "_"


def test_n10_pull_unduh_folder_zip_file_naming(client: TestClient, db_session: Session, monkeypatch):
    """N10: Pull unduh_folder dengan ["nama","tahun"] -> Nama berkas di dalam ZIP mengikuti format"""
    src = ScrapingSource(
        name="Source N10",
        url="https://jdih.ojk.go.id/n10",
        source_type=JenisSumber.situs_web,
        default_access_classification=KlasifikasiAkses.publik,
        default_document_role=PeranDokumen.corpus_eksisting,
    )
    db_session.add(src)
    db_session.flush()

    sess = ScanSession(
        source_id=src.id,
        start_url=src.url,
        crawl_depth=1,
        mode="test",
        status=StatusPindai.siap_dipilih,
    )
    db_session.add(sess)
    db_session.flush()

    import hashlib
    url = "https://jdih.ojk.go.id/n10/peraturan_modal.pdf"
    cand = ScanCandidate(
        scan_id=sess.id,
        url=url,
        url_hash=hashlib.sha256(url.encode()).hexdigest(),
        filename="peraturan_modal.pdf",
        size_bytes=1000,
        match_status=StatusKandidat.baru,
        selected=True,
    )
    db_session.add(cand)
    db_session.commit()

    class MockFetched:
        filename = "peraturan_modal.pdf"
        content = make_pdf("Konten peraturan modal")
    monkeypatch.setattr("app.services.scan_service.get_crawler", lambda s: type("MockC", (), {"fetch": lambda self, u, **kw: MockFetched()})())

    pull_payload = {
        "destination": "unduh_folder",
        "naming_format": ["nama", "tahun"],
        "naming_separator": " ",
    }
    resp = client.post(f"/api/v1/scans/{sess.id}/pull?wait=true", json=pull_payload)
    assert resp.status_code == 200

    # Download ZIP
    resp_dl = client.get(f"/api/v1/scans/{sess.id}/download")
    assert resp_dl.status_code == 200
    zip_bytes = io.BytesIO(resp_dl.content)
    with zipfile.ZipFile(zip_bytes, "r") as z:
        names = z.namelist()
        assert len(names) == 1
        # Component 'nama': peraturan_modal, component 'tahun': NA -> peraturan_modal NA.pdf
        assert names[0] == "peraturan_modal NA.pdf"


def test_n11_local_folder_default_and_override(client: TestClient, db_session: Session, tmp_path):
    """N11: Folder lokal: default_naming_format di sumber + override di run -> Override menang; tanpa override pakai default sumber"""
    allowed_root = tmp_path / "sources"
    allowed_root.mkdir(parents=True, exist_ok=True)
    f1 = allowed_root / "pedoman.pdf"
    f1.write_bytes(make_pdf("Pedoman Operasional"))

    src = ScrapingSource(
        name="Folder N11",
        url=str(allowed_root),
        source_type=JenisSumber.folder_lokal,
        default_access_classification=KlasifikasiAkses.non_publik,
        default_document_role=PeranDokumen.corpus_eksisting,
        default_naming_format=["nama", "jenis"],
        default_naming_separator="_",
    )
    db_session.add(src)
    db_session.commit()

    # 1. Run with override format ["nama", "tahun"]
    resp_run = client.post(
        f"/api/v1/scraping-sources/{src.id}/run?wait=true",
        json={"naming_format": ["nama", "tahun"], "naming_separator": "-"},
    )
    assert resp_run.status_code == 200

    doc = db_session.query(Document).order_by(Document.id.desc()).first()
    assert doc is not None
    assert doc.naming_format == ["nama", "tahun"]
    assert doc.naming_separator == "-"


def test_n12_extraction_bidang_and_ignored_fields(client: TestClient, db_session: Session):
    """N12: Ekstraksi mengirim sektor -> Masuk ke bidang; bila bidang sudah dikoreksi manual -> ignored_fields"""
    pdf_content = make_pdf("Konten Ekstraksi N12")
    files = [("files", ("n12_sample.pdf", pdf_content, "application/pdf"))]
    resp = client.post(
        "/api/v1/ingest/upload-pdf",
        files=files,
        data={"access_classification": "publik", "document_role": "corpus_eksisting"},
    )
    assert resp.status_code == 200
    doc_id = resp.json()["details"][0]["document_id"]

    # 1. Extract with 'sektor'
    payload_extract = {
        "title": "Regulasi Pasar Modal",
        "sektor": "Pasar Modal",
    }
    resp_ext = client.patch(
        f"/api/v1/internal/documents/{doc_id}/extraction?force=true",
        json=payload_extract,
        headers={"X-Internal-API-Key": settings.internal_api_key},
    )
    assert resp_ext.status_code == 200

    doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert doc.bidang == "Pasar Modal"

    # 2. Kurator mengoreksi manual bidang -> Perbankan
    client.patch(f"/api/v1/documents/{doc_id}/metadata", json={"bidang": "Perbankan"})
    db_session.refresh(doc)
    assert doc.metadata_corrected_at is not None

    # 3. Extraction kirim lagi sektor -> IKNB -> harus diabaikan dan masuk ignored_fields
    resp_ext2 = client.patch(
        f"/api/v1/internal/documents/{doc_id}/extraction?force=true",
        json={"title": "Regulasi Baru", "sektor": "IKNB"},
        headers={"X-Internal-API-Key": settings.internal_api_key},
    )
    assert resp_ext2.status_code == 200
    db_session.refresh(doc)
    assert doc.bidang == "Perbankan"
    assert "bidang" in resp_ext2.json().get("ignored_fields", [])


def test_n13_naming_components_and_preview_endpoints(client: TestClient, db_session: Session):
    """N13: GET /naming/components, POST /naming/preview (tanpa sample, dengan sample, dengan document_id)"""
    # 1. GET /naming/components
    resp_comp = client.get("/api/v1/naming/components")
    assert resp_comp.status_code == 200
    data_comp = resp_comp.json()
    keys = [c["key"] for c in data_comp["components"]]
    assert keys == ["nama", "tahun", "jenis", "bidang", "nomor"]

    # 2. POST /naming/preview without sample (uses default POJK 16 2026)
    resp_prev1 = client.post("/api/v1/naming/preview", json={"naming_format": ["nomor", "nama", "tahun"]})
    assert resp_prev1.status_code == 200
    assert "16-POJK.04-2026" in resp_prev1.json()["filename"]
    assert "Penyelenggaraan Bursa Mineral" in resp_prev1.json()["filename"]

    # 3. POST /naming/preview with sample
    resp_prev2 = client.post(
        "/api/v1/naming/preview",
        json={
            "naming_format": ["nama", "bidang", "tahun"],
            "naming_separator": "-",
            "sample": {
                "title": "Uji Pratinjau",
                "bidang": "BMKS",
                "release_date": "2026-05-01",
            },
        },
    )
    assert resp_prev2.status_code == 200
    assert resp_prev2.json()["filename"] == "Uji Pratinjau-BMKS-2026.pdf"


def test_n14_filter_documents_by_bidang(client: TestClient, db_session: Session):
    """N14: GET /documents/?bidang=BMKS -> Terfilter"""
    doc1 = Document(
        title="Regulasi BMKS 1",
        file_hash="hash_bmks_1",
        file_size_bytes=1000,
        file_path_pdf="kb/POJK/2026/bmks1.pdf",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        bidang="BMKS",
    )
    doc2 = Document(
        title="Regulasi Perbankan 1",
        file_hash="hash_bank_1",
        file_size_bytes=1000,
        file_path_pdf="kb/POJK/2026/bank1.pdf",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        bidang="Perbankan",
    )
    db_session.add_all([doc1, doc2])
    db_session.commit()

    resp = client.get("/api/v1/documents/?bidang=BMKS")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(d["title"] == "Regulasi BMKS 1" for d in items)
    assert not any(d["title"] == "Regulasi Perbankan 1" for d in items)


# ==================== C01 - C04: CONTRACT & REQUISITES TESTING ====================

def test_c01_contract_builder_idempotent():
    """C01: scripts/build_api_contract.py dijalankan dua kali -> Tanpa diff (idempoten)"""
    # Run once
    r1 = subprocess.run([sys.executable, "scripts/build_api_contract.py"], capture_output=True, text=True)
    assert r1.returncode == 0
    content1 = Path("docs/api/KONTRAK-API-FASE1.md").read_text(encoding="utf-8")
    openapi1 = Path("docs/api/openapi-fase1.json").read_text(encoding="utf-8")
    http1 = Path("docs/api/hero-fase1.http").read_text(encoding="utf-8")

    # Run second time
    r2 = subprocess.run([sys.executable, "scripts/build_api_contract.py"], capture_output=True, text=True)
    assert r2.returncode == 0
    content2 = Path("docs/api/KONTRAK-API-FASE1.md").read_text(encoding="utf-8")
    openapi2 = Path("docs/api/openapi-fase1.json").read_text(encoding="utf-8")
    http2 = Path("docs/api/hero-fase1.http").read_text(encoding="utf-8")

    assert content1 == content2
    assert openapi1 == openapi2
    assert http1 == http2


def test_c02_docs_enums_scans_contract():
    """C02: test_docs_enums.py memindai kontrak -> Lulus"""
    from tests.test_docs_enums import test_docs_api_enum_validity
    test_docs_api_enum_validity()


def test_c03_get_document_pdf_content_disposition(client: TestClient, db_session: Session):
    """C03: GET /documents/{id}/pdf -> Content-Disposition diawali inline, tipe application/pdf"""
    storage = get_storage_service()
    rel_path = storage.save_pdf(make_pdf("Konten PDF C03"), filename_hint="c03_test.pdf", subdir="kb/POJK/2026")
    doc = Document(
        title="Dokumen C03",
        file_hash="hash_c03_test",
        file_size_bytes=1000,
        file_path_pdf=rel_path,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
    )
    db_session.add(doc)
    db_session.commit()

    resp = client.get(f"/api/v1/documents/{doc.id}/pdf")
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "application/pdf"
    content_disp = resp.headers.get("content-disposition", "")
    assert content_disp.startswith("inline")


def test_c04_cors_preflight_allow_origin(client: TestClient):
    """C04: Preflight CORS dari http://localhost:3000 -> Header access-control-allow-origin sesuai"""
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    }
    resp = client.options("/api/v1/ingest/upload-pdf", headers=headers)
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") in ("http://localhost:3000", "*")
