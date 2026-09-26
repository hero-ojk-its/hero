"""
tests/test_document_detail.py
Pengujian endpoint detail dokumen, pembacaan PDF, dan pembacaan teks (D01 - D05).
"""
import os
from datetime import date
import pytest

from app.models.document import Document
from app.models.category import Category
from app.models.audit_log import AuditLog
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
    MetodeEkstraksi,
)
from tests.conftest import make_pdf


@pytest.fixture
def seed_detail_doc(db_session, test_storage):
    """Seed dokumen dan berkas PDF nyata di storage."""
    cat = db_session.query(Category).filter(Category.name == "POJK").first()
    pdf_bytes = make_pdf("Ini adalah konten PDF uji regulasi detail dokumen nomor 10.")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint="10-POJK.03-2023 Regulasi Detail 2023.pdf", subdir="kb/POJK/2023")

    doc = Document(
        title="Regulasi Detail Dokumen Nomor 10",
        regulation_number="10/POJK.03/2023",
        regulation_type="POJK",
        release_date=date(2023, 7, 15),
        file_path_pdf=rel_path,
        file_hash="hash_detail_10",
        file_size_bytes=len(pdf_bytes),
        standardized_filename="10-POJK.03-2023 Regulasi Detail 2023.pdf",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        extraction_method=MetodeEkstraksi.teks_langsung,
        full_text="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        category_id=cat.id if cat else None,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return {"doc_id": doc.id, "rel_path": rel_path, "pdf_bytes": pdf_bytes}


def test_d01_get_pdf_inline(client, seed_detail_doc, db_session):
    """D01: GET /documents/{id}/pdf -> 200, application/pdf, Content-Disposition inline, audit OPEN_PDF."""
    doc_id = seed_detail_doc["doc_id"]
    resp = client.get(f"/api/v1/documents/{doc_id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "inline" in resp.headers["content-disposition"]
    assert resp.content == seed_detail_doc["pdf_bytes"]

    # Periksa audit log
    audit = db_session.query(AuditLog).filter(AuditLog.action == "OPEN_PDF", AuditLog.target_resource == f"document:{doc_id}").first()
    assert audit is not None


def test_d02_get_pdf_download(client, seed_detail_doc, db_session):
    """D02: GET /documents/{id}/pdf?download=true -> attachment & audit DOWNLOAD_PDF."""
    doc_id = seed_detail_doc["doc_id"]
    resp = client.get(f"/api/v1/documents/{doc_id}/pdf?download=true")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]

    audit = db_session.query(AuditLog).filter(AuditLog.action == "DOWNLOAD_PDF", AuditLog.target_resource == f"document:{doc_id}").first()
    assert audit is not None


def test_d03_pdf_missing_on_disk(client, seed_detail_doc, test_storage):
    """D03: Berkas PDF dihapus dari disk -> 404 dengan pesan sesuai."""
    doc_id = seed_detail_doc["doc_id"]
    test_storage.delete(seed_detail_doc["rel_path"])

    resp = client.get(f"/api/v1/documents/{doc_id}/pdf")
    assert resp.status_code == 404
    assert "tidak ditemukan" in resp.json()["detail"].lower()


def test_d04_non_ascii_standardized_filename(client, db_session, test_storage):
    """D04: Nama berkas dengan karakter non-ASCII diformat dengan filename*=UTF-8''."""
    pdf_bytes = make_pdf("Non-ascii file content")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint="dokumen_non_ascii.pdf", subdir="kb/POJK/2023")

    doc = Document(
        title="Regulasi Non-ASCII — Peraturan & Pedoman €",
        regulation_number="88/POJK.03/2023",
        regulation_type="POJK",
        release_date=date(2023, 1, 1),
        file_path_pdf=rel_path,
        file_hash="hash_detail_non_ascii",
        file_size_bytes=len(pdf_bytes),
        standardized_filename="88-POJK.03-2023 Regulasi Non-ASCII — Pedoman €.pdf",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
    )
    db_session.add(doc)
    db_session.commit()

    resp = client.get(f"/api/v1/documents/{doc.id}/pdf")
    assert resp.status_code == 200
    disp_header = resp.headers["content-disposition"]
    assert "filename*=UTF-8''" in disp_header


def test_d05_get_document_text(client, seed_detail_doc):
    """D05: GET /documents/{id}/text?offset=10&limit=5 -> Potongan benar & total_length benar."""
    doc_id = seed_detail_doc["doc_id"]
    # full_text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" (len 36)
    resp = client.get(f"/api/v1/documents/{doc_id}/text?offset=10&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["document_id"] == doc_id
    assert data["total_length"] == 36
    assert data["offset"] == 10
    assert data["limit"] == 5
    assert data["text"] == "KLMNO"
