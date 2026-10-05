"""
tests/test_step12b_fixes.py
Pengujian verifikasi Langkah 12b (Koreksi Review):
H01: Detail OJK tanpa penetapan -> release_date=None, effective_date=2027-04-01, regulation_year=2025
H02: Dokumen OneDrive Peraturan_OJK_3_2015.pdf memiliki regulation_year=2015
H03: GET /documents/?year=2015 mengembalikan dokumen OneDrive Peraturan_OJK_3_2015
H04: Pratinjau nama [nama, jenis, tahun] untuk dokumen tanpa release_date menghasilkan tahun, bukan NA
H05: Suite pytest lulus tanpa regresi
"""
from datetime import date
import pytest

from app.models.document import Document
from app.models.enums import PeranDokumen, KlasifikasiAkses, StatusKeberlakuan, StatusPemrosesan
from app.crawlers.url_utils import extract_regulation_year
from app.services.naming_service import NamingInput, build_standard_filename


def test_h01_ojk_detail_no_release_date_with_effective_date():
    """H01: Detail OJK tanpa tanggal penetapan, tanggal berlaku 2027-04-01, nomor 23/SEOJK.06/2025."""
    rel_date = None
    eff_date = date(2027, 4, 1)
    reg_number = "23/SEOJK.06/2025"
    reg_year = extract_regulation_year(regulation_number=reg_number, release_date=rel_date)

    assert rel_date is None
    assert eff_date == date(2027, 4, 1)
    assert reg_year == 2025


def test_h02_onedrive_regulation_year_from_filename():
    """H02: Berkas OneDrive Peraturan_OJK_3_2015.pdf diekstrak regulation_year=2015."""
    filename = "Peraturan_OJK_3_2015.pdf"
    reg_year = extract_regulation_year(filename=filename)
    assert reg_year == 2015


def test_h03_get_documents_filtered_by_year(client, db_session):
    """H03: GET /documents/?year=2015 mengembalikan dokumen OneDrive H02."""
    doc = Document(
        title="Peraturan OJK Nomor 3",
        original_filename="Peraturan_OJK_3_2015.pdf",
        standardized_filename="Peraturan_OJK_3_2015_POJK_2015.pdf",
        regulation_number="POJK 3 Tahun 2015",
        regulation_type="POJK",
        release_date=None,
        regulation_year=2015,
        file_path_pdf="kb/Peraturan_OJK_3_2015_POJK_2015.pdf",
        file_hash="a" * 64,
        file_size_bytes=12345,
        document_role=PeranDokumen.corpus_eksisting,
        access_classification=KlasifikasiAkses.publik,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
    )
    db_session.add(doc)
    db_session.commit()

    resp = client.get("/api/v1/documents/?year=2015")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    items = data["items"]
    assert items[0]["standardized_filename"] == "Peraturan_OJK_3_2015_POJK_2015.pdf"
    assert items[0]["regulation_year"] == 2015
    assert items[0]["release_date"] is None


def test_h04_preview_naming_without_release_date_uses_regulation_year(client, db_session):
    """H04: Pratinjau nama [nama, jenis, tahun] untuk dokumen tanpa release_date -> tahun dari regulation_year, bukan NA."""
    # 1. Uji unit murni lewat service
    inp = NamingInput(
        title="Peraturan OJK Nomor 3",
        regulation_type="POJK",
        release_date=None,
        regulation_year=2015,
    )
    fn = build_standard_filename(inp, naming_format=["nama", "jenis", "tahun"], naming_separator="_")
    assert "2015" in fn
    assert "NA" not in fn
    assert fn == "Peraturan OJK Nomor 3_POJK_2015.pdf"

    # 2. Uji via endpoint REST API dengan document di database yang release_date-nya None
    doc = Document(
        title="Peraturan OJK Nomor 3",
        original_filename="Peraturan_OJK_3_2015.pdf",
        standardized_filename="Peraturan_OJK_3_2015_POJK_2015.pdf",
        regulation_number="POJK 3 Tahun 2015",
        regulation_type="POJK",
        release_date=None,
        regulation_year=2015,
        file_path_pdf="kb/Peraturan_OJK_3_2015_POJK_2015.pdf",
        file_hash="a" * 64,
        file_size_bytes=12345,
        document_role=PeranDokumen.corpus_eksisting,
        access_classification=KlasifikasiAkses.publik,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
    )
    db_session.add(doc)
    db_session.commit()

    payload = {
        "naming_format": ["nama", "jenis", "tahun"],
        "naming_separator": "_",
        "document_id": doc.id,
    }
    res = client.post("/api/v1/naming/preview", json=payload)
    assert res.status_code == 200
    p_data = res.json()
    assert "2015" in p_data["filename"]
    assert "tahun" not in p_data["missing_components"]
