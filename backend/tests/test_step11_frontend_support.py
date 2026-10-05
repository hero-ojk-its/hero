"""
tests/test_step11_frontend_support.py
Pengujian untuk Langkah 11:
F01: Preflight & GET dari origin http://localhost:5173 (CORS expose-headers)
F02: PDF Content-Disposition RFC 5987 (filename* dan fallback filename ASCII)
F03: Pemetaan status keberlakuan JDIH (berlaku, dicabut, diubah)
F04: Penerusan status_keberlakuan saat pull kandidat ke knowledge_base
F05: Deteksi doc_kind variasi tanpa spasi dan underscore
"""
import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import (
    StatusKeberlakuan,
    StatusKandidat,
    TujuanTarik,
    StatusPindai,
    KlasifikasiAkses,
    PeranDokumen,
)
from app.models.document import Document
from app.models.scan_session import ScanSession
from app.models.scan_candidate import ScanCandidate
from app.models.scraping_source import ScrapingSource
from app.crawlers.url_utils import determine_doc_kind
from app.crawlers.jdih_api import map_jdih_status_keberlakuan
from app.services.storage_service import StorageService


def test_f01_cors_preflight_and_get_5173(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    F01: Preflight dan GET dari origin http://localhost:5173
    - allow-origin benar
    - expose-headers memuat Content-Disposition dan Content-Length
    """
    # 1. Preflight OPTIONS
    headers_preflight = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Content-Type",
    }
    resp_options = client.options("/api/v1/documents/", headers=headers_preflight)
    assert resp_options.status_code in (200, 204)
    origin_header = resp_options.headers.get("access-control-allow-origin")
    assert origin_header in ("http://localhost:5173", "*")
    expose_hdr = resp_options.headers.get("access-control-expose-headers", "")
    assert "Content-Disposition" in expose_hdr
    assert "Content-Length" in expose_hdr

    # 2. Simple GET dari origin 5173
    resp_get = client.get("/api/v1/documents/?limit=1", headers={"Origin": "http://localhost:5173"})
    assert resp_get.status_code == 200
    assert resp_get.headers.get("access-control-allow-origin") in ("http://localhost:5173", "*")
    expose_get = resp_get.headers.get("access-control-expose-headers", "")
    assert "Content-Disposition" in expose_get
    assert "Content-Length" in expose_get


def test_f02_pdf_content_disposition_rfc5987(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    F02: PDF dengan nama '99-POJK.03-2025 Sepatu Roda 2025.pdf'
    - filename* ter-encode benar sesuai RFC 5987
    - filename ASCII fallback ada
    - inline default, attachment bila download=true
    """
    # Simpan berkas PDF dummy ke storage
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n165\n%%EOF"
    target_name = "99-POJK.03-2025 Sepatu Roda 2025.pdf"
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint=target_name, subdir="pdf")

    doc = Document(
        title="Uji Sepatu Roda 2025",
        original_filename=target_name,
        standardized_filename=target_name,
        regulation_number="POJK 99/POJK.03/2025",
        regulation_type="POJK",
        release_date=date(2025, 8, 17),
        bidang="Perbankan",
        file_path_pdf=rel_path,
        file_hash="dummy_hash_f02_1234567890abcdef",
        file_size_bytes=len(pdf_bytes),
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    # 1. GET Inline (Default)
    resp_inline = client.get(f"/api/v1/documents/{doc.id}/pdf", headers={"Origin": "http://localhost:5173"})
    assert resp_inline.status_code == 200
    cd_inline = resp_inline.headers.get("content-disposition", "")
    assert cd_inline.startswith("inline")
    assert 'filename="99-POJK.03-2025 Sepatu Roda 2025.pdf"' in cd_inline
    assert "filename*=UTF-8''99-POJK.03-2025%20Sepatu%20Roda%202025.pdf" in cd_inline

    # 2. GET Attachment (download=true)
    resp_att = client.get(f"/api/v1/documents/{doc.id}/pdf?download=true", headers={"Origin": "http://localhost:5173"})
    assert resp_att.status_code == 200
    cd_att = resp_att.headers.get("content-disposition", "")
    assert cd_att.startswith("attachment")
    assert 'filename="99-POJK.03-2025 Sepatu Roda 2025.pdf"' in cd_att
    assert "filename*=UTF-8''99-POJK.03-2025%20Sepatu%20Roda%202025.pdf" in cd_att


def test_f03_jdih_status_mapping_real_fixtures():
    """
    F03: Status JDIH 'Berlaku Sejak…', 'Dicabut…', 'Diubah…' (fixture asli)
    - Memetakan teks detail dan kolom 7 DataTables ke enum yang benar
    """
    # 1. Teks detail asli
    assert map_jdih_status_keberlakuan(detail_status_text="Status Peraturan : Berlaku Sejak Tanggal 07-07-2026") == "berlaku"
    assert map_jdih_status_keberlakuan(detail_status_text="Status Peraturan : Tidak Berlaku Sejak Tanggal 23-06-2025") == "dicabut"
    assert map_jdih_status_keberlakuan(detail_status_text="Dicabut dengan POJK Nomor 14 Tahun 2026") == "dicabut"
    assert map_jdih_status_keberlakuan(detail_status_text="Diubah dengan POJK Nomor 10 Tahun 2026") == "diubah"
    assert map_jdih_status_keberlakuan(detail_status_text="Status Peraturan : Berlaku (Perubahan) (Diubah)") == "diubah"
    assert map_jdih_status_keberlakuan(detail_status_text="Status Peraturan : Berlaku (Dicabut Sebagian)") == "diubah"
    assert map_jdih_status_keberlakuan(detail_status_text="Status Peraturan : Berlaku (Perubahan) (Mengubah) Sejak Tanggal 01-12-2024") == "berlaku"

    # 2. Fallback dari kolom 7 DataTables asli
    assert map_jdih_status_keberlakuan(datatables_label="Berlaku") == "berlaku"
    assert map_jdih_status_keberlakuan(datatables_label="Tidak Berlaku") == "dicabut"
    assert map_jdih_status_keberlakuan(datatables_label="Berlaku (Perubahan) (Diubah)") == "diubah"
    assert map_jdih_status_keberlakuan(datatables_label="Berlaku (Dicabut Sebagian)") == "diubah"
    assert map_jdih_status_keberlakuan(datatables_label="Berlaku (Perubahan) (Mengubah)") == "berlaku"
    assert map_jdih_status_keberlakuan(datatables_label="Unknown Value") == "tidak_diketahui"
    assert map_jdih_status_keberlakuan(None, None) == "tidak_diketahui"


def test_f04_pull_candidate_jdih_dicabut(client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch):
    """
    F04: Pull kandidat JDIH berstatus dicabut -> Dokumen status_keberlakuan=dicabut
    """
    from app.services.scan_service import ScanService
    from app.crawlers.base import FetchedFile

    # Daftarkan sumber JDIH dummy
    src = ScrapingSource(
        name="Sumber Uji JDIH Step 11",
        url="https://jdih.ojk.go.id",
        source_type="situs_web",
        crawler_adapter="jdih_api",
        is_active=True,
    )
    db_session.add(src)
    db_session.commit()
    db_session.refresh(src)

    # Buat sesi pemindaian
    sess = ScanSession(
        source_id=src.id,
        start_url=src.url,
        crawl_depth=1,
        mode="situs_web",
        crawler_adapter="jdih_api",
        status=StatusPindai.siap_dipilih,
        pages_visited=1,
    )
    db_session.add(sess)
    db_session.commit()
    db_session.refresh(sess)

    # Tambahkan kandidat dengan status_keberlakuan 'dicabut'
    cand = ScanCandidate(
        scan_id=sess.id,
        url="https://jdih.ojk.go.id/docs/POJK_Dicabut_2023.pdf",
        url_hash="hash_candidate_dicabut_f04",
        filename="POJK_Dicabut_2023.pdf",
        size_bytes=1024,
        depth=1,
        document_title="POJK Pengawasan Asuransi Lama yang Dicabut",
        regulation_number="POJK 70/POJK.05/2016",
        regulation_type="POJK",
        bidang="Perasuransian",
        release_date=date(2016, 12, 28),
        effective_date=date(2017, 1, 1),
        status_keberlakuan="dicabut",
        match_status=StatusKandidat.baru,
        selected=True,
    )
    db_session.add(cand)
    db_session.commit()
    db_session.refresh(cand)

    # Mock fetch_pdf agar mengembalikan PDF valid
    dummy_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n165\n%%EOF"

    def mock_fetch(self, url, *, max_bytes=100 * 1024 * 1024):
        return FetchedFile(
            content=dummy_pdf,
            filename="POJK_Dicabut_2023.pdf",
            final_url=url,
            content_type="application/pdf",
        )

    monkeypatch.setattr("app.crawlers.jdih_api.JdihApiCrawler.fetch", mock_fetch)

    # Jalankan pull via API dengan wait=true
    resp_pull = client.post(
        f"/api/v1/scans/{sess.id}/pull?wait=true",
        json={
            "destination": "knowledge_base",
            "naming_format": ["nomor", "nama", "tahun"],
            "naming_separator": " ",
        },
    )
    assert resp_pull.status_code == 200
    assert resp_pull.json()["status"] == "selesai"

    # Verifikasi dokumen yang dihasilkan
    db_session.refresh(cand)
    assert cand.pull_outcome in ("berhasil", "success")
    assert cand.document_id is not None

    doc = db_session.query(Document).filter(Document.id == cand.document_id).first()
    assert doc is not None
    assert doc.status_keberlakuan == StatusKeberlakuan.dicabut
    assert doc.bidang == "Perasuransian"
    assert doc.regulation_type == "POJK"


def test_f05_doc_kind_detection_patterns():
    """
    F05: doc_kind faq_pbi_101708.pdf, abs_…, ringkasan_…, dan tanpa spasi
    """
    # Pola dengan underscore
    assert determine_doc_kind("faq_pbi_101708.pdf") == "faq"
    assert determine_doc_kind("abs_pbi_101708.pdf") == "abstrak"
    assert determine_doc_kind("abstrak_pojk_12.pdf") == "abstrak"
    assert determine_doc_kind("ringkasan_pojk_14.pdf") == "abstrak"
    assert determine_doc_kind("summary_pojk_22.pdf") == "abstrak"

    # Pola tanpa spasi / tanpa underscore
    assert determine_doc_kind("faqpbi101708.pdf") == "faq"
    assert determine_doc_kind("abspbi101708.pdf") == "abstrak"
    assert determine_doc_kind("abstrakpojk12.pdf") == "abstrak"
    assert determine_doc_kind("ringkasanpojk14.pdf") == "abstrak"
    assert determine_doc_kind("summarypojk22.pdf") == "abstrak"
    assert determine_doc_kind("2026abspojk008.pdf") == "abstrak"
    assert determine_doc_kind("2024faqseojk020.pdf") == "faq"
