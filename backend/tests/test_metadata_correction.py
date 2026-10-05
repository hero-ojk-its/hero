"""
tests/test_metadata_correction.py
Pengujian koreksi metadata dokumen manual (M01 - M07).
"""
from datetime import date, timedelta
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
def seed_inbox_doc(db_session, test_storage):
    """Dokumen yang berada di folder staging _inbox."""
    pdf_bytes = make_pdf("PDF Dokumen Ingest Awal")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint="doc_inbox_01.pdf", subdir="pdf/_inbox")

    cat = db_session.query(Category).filter(Category.name == "POJK").first()

    doc = Document(
        title="Dokumen Ingest Awal",
        regulation_number=None,
        regulation_type=None,
        release_date=None,
        file_path_pdf=rel_path,
        file_hash="hash_inbox_01",
        file_size_bytes=len(pdf_bytes),
        standardized_filename=None,
        access_classification=KlasifikasiAkses.non_publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.diterima,
        category_id=None,
        full_text="Isi lengkap peraturan tentang perbankan digital.",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return {"doc_id": doc.id, "rel_path": rel_path}


def test_m01_patch_metadata_inbox_placement(client, seed_inbox_doc, db_session, test_storage):
    """M01: PATCH regulation_number, regulation_type, release_date -> dokumen dipindah ke kb/ dengan nama baku & audit UPDATE_METADATA."""
    doc_id = seed_inbox_doc["doc_id"]
    payload = {
        "regulation_number": "15/POJK.03/2023",
        "regulation_type": "POJK",
        "release_date": "2023-08-20",
    }
    resp = client.patch(f"/api/v1/documents/{doc_id}/metadata", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert "regulation_number" in data["changed_fields"]
    assert "regulation_type" in data["changed_fields"]
    assert "release_date" in data["changed_fields"]
    assert data["is_placed"] is True
    assert data["file_path_pdf"].startswith("kb/POJK/2023/")

    # Berkas di penyimpanan baru ada, di inbox lama sudah dipindah
    assert test_storage.exists(data["file_path_pdf"])
    assert not test_storage.exists(seed_inbox_doc["rel_path"])

    # Audit log
    audit = db_session.query(AuditLog).filter(AuditLog.action == "UPDATE_METADATA", AuditLog.target_resource == f"document:{doc_id}").first()
    assert audit is not None
    assert audit.detail is not None
    assert "before" in audit.detail and "after" in audit.detail


def test_m02_patch_title_renames_file_in_kb(client, seed_inbox_doc, db_session, test_storage):
    """M02: PATCH title pada dokumen yang sudah di kb/ -> berkas di-rename ke path baru."""
    doc_id = seed_inbox_doc["doc_id"]
    # 1. Pindah dulu ke KB
    client.patch(f"/api/v1/documents/{doc_id}/metadata", json={
        "regulation_number": "20/POJK.03/2023",
        "regulation_type": "POJK",
        "release_date": "2023-01-10",
    })
    doc_before = db_session.query(Document).filter(Document.id == doc_id).first()
    old_kb_path = doc_before.file_path_pdf

    # 2. PATCH judul
    resp = client.patch(f"/api/v1/documents/{doc_id}/metadata", json={
        "title": "Judul Baru Peraturan Perbankan Modern",
    })
    assert resp.status_code == 200
    data = resp.json()
    new_kb_path = data["file_path_pdf"]

    assert new_kb_path != old_kb_path
    assert "Judul Baru Peraturan Perbankan Modern" in new_kb_path
    assert test_storage.exists(new_kb_path)
    assert not test_storage.exists(old_kb_path)


def test_m03_release_date_in_future_422(client, seed_inbox_doc):
    """M03: release_date di masa depan -> 422."""
    doc_id = seed_inbox_doc["doc_id"]
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp = client.patch(f"/api/v1/documents/{doc_id}/metadata", json={"release_date": tomorrow})
    assert resp.status_code == 422


def test_m04_invalid_title_or_access_class_422(client, seed_inbox_doc):
    """M04: title kosong/null atau access_classification null -> 422."""
    doc_id = seed_inbox_doc["doc_id"]
    resp1 = client.patch(f"/api/v1/documents/{doc_id}/metadata", json={"title": "   "})
    assert resp1.status_code == 422

    resp2 = client.patch(f"/api/v1/documents/{doc_id}/metadata", json={"title": None})
    assert resp2.status_code == 422

    resp3 = client.patch(f"/api/v1/documents/{doc_id}/metadata", json={"access_classification": None})
    assert resp3.status_code == 422


def test_m05_explicit_null_clears_optional_field(client, seed_inbox_doc, db_session):
    """M05: regulation_number: null secara eksplisit mengosongkan field."""
    doc_id = seed_inbox_doc["doc_id"]
    # Isi nomor dulu
    client.patch(f"/api/v1/documents/{doc_id}/metadata", json={"regulation_number": "99/POJK.03/2023"})

    # Kosongkan dengan null
    resp = client.patch(f"/api/v1/documents/{doc_id}/metadata", json={"regulation_number": None})
    assert resp.status_code == 200
    assert resp.json()["regulation_number"] is None


def test_m06_perlu_koreksi_to_terindeks_when_fixed(client, db_session, test_storage):
    """M06: Dokumen berstatus perlu_koreksi menjadi terindeks setelah nomor dan metadata dilengkapi."""
    pdf_bytes = make_pdf("PDF untuk koreksi status")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint="doc_koreksi.pdf", subdir="pdf/_inbox")

    doc = Document(
        title="Dokumen Perlu Koreksi",
        regulation_number=None,  # belum lengkap
        regulation_type="POJK",
        release_date=date(2023, 5, 5),
        file_path_pdf=rel_path,
        file_hash="hash_koreksi_01",
        file_size_bytes=len(pdf_bytes),
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.perlu_koreksi,
        full_text="Isi lengkap dokumen ada di sini.",
    )
    db_session.add(doc)
    db_session.commit()

    resp = client.patch(f"/api/v1/documents/{doc.id}/metadata", json={"regulation_number": "55/POJK.03/2023"})
    assert resp.status_code == 200
    assert resp.json()["processing_status"] == "terindeks"


def test_m07_empty_payload_422(client, seed_inbox_doc):
    """M07: Body kosong {} -> 422."""
    doc_id = seed_inbox_doc["doc_id"]
    resp = client.patch(f"/api/v1/documents/{doc_id}/metadata", json={})
    assert resp.status_code == 422
