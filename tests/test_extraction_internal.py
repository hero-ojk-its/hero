"""
tests/test_extraction_internal.py
Pengujian endpoint integrasi ekstraksi Data/ML (E01 - E12).
"""
from datetime import datetime, date, timedelta, timezone
import pytest

from app.config import settings
from app.models.document import Document
from app.models.category import Category
from app.models.ingest_failure import IngestFailure
from app.models.audit_log import AuditLog
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
    MetodeEkstraksi,
    JenisKegagalan,
    StatusTindakLanjut,
)
from tests.conftest import make_pdf

INTERNAL_HEADERS = {"X-Internal-API-Key": settings.internal_api_key}


@pytest.fixture
def seed_claimable_docs(db_session, test_storage):
    """Seed 3 dokumen berstatus diterima."""
    cat = db_session.query(Category).filter(Category.name == "POJK").first()
    docs = []
    for i in range(1, 4):
        pdf_bytes = make_pdf(f"Dokumen Claim {i}")
        rel_path = test_storage.save_pdf(pdf_bytes, filename_hint=f"doc_claim_{i}.pdf", subdir="pdf/_inbox")

        doc = Document(
            title=f"Dokumen Antrian {i}",
            regulation_number=f"{i}/POJK.03/2023",
            file_path_pdf=rel_path,
            file_hash=f"hash_claim_{i}",
            file_size_bytes=len(pdf_bytes),
            access_classification=KlasifikasiAkses.publik,
            document_role=PeranDokumen.corpus_eksisting,
            status_keberlakuan=StatusKeberlakuan.berlaku,
            processing_status=StatusPemrosesan.diterima,
            extraction_attempts=0,
            category_id=cat.id if cat else None,
        )
        db_session.add(doc)
        docs.append(doc)

    db_session.commit()
    for d in docs:
        db_session.refresh(d)
    return [d.id for d in docs]


def test_e01_claim_batch_limit(client, seed_claimable_docs, db_session):
    """E01: claim?limit=2 dari 3 dokumen diterima -> 2 dokumen menjadi 'diproses' dengan attempt=1."""
    resp = client.post("/api/v1/internal/extraction/claim?limit=2", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["attempt"] == 1
    assert data[1]["attempt"] == 1

    # Verifikasi status di DB
    d1 = db_session.query(Document).filter(Document.id == data[0]["document_id"]).first()
    assert d1.processing_status == StatusPemrosesan.diproses
    assert d1.extraction_claimed_at is not None


def test_e02_consecutive_claims_no_overlap(client, seed_claimable_docs):
    """E02: Dua klaim berturut-turut tidak mengambil dokumen yang sama."""
    resp1 = client.post("/api/v1/internal/extraction/claim?limit=2", headers=INTERNAL_HEADERS)
    data1 = resp1.json()
    claimed_ids_1 = {item["document_id"] for item in data1}

    resp2 = client.post("/api/v1/internal/extraction/claim?limit=2", headers=INTERNAL_HEADERS)
    data2 = resp2.json()
    claimed_ids_2 = {item["document_id"] for item in data2}

    assert len(data2) == 1
    assert claimed_ids_1.isdisjoint(claimed_ids_2)


def test_e03_expired_claim_can_be_reclaimed(client, seed_claimable_docs, db_session):
    """E03: Klaim yang melewati batas waktu timeout (31 menit lalu) dapat diklaim ulang dengan attempt bertambah."""
    # Klaim pertama
    client.post("/api/v1/internal/extraction/claim?limit=1", headers=INTERNAL_HEADERS)
    d1 = db_session.query(Document).filter(Document.id == seed_claimable_docs[0]).first()

    # Mundurkan waktu klaim 31 menit
    d1.extraction_claimed_at = datetime.now(timezone.utc) - timedelta(minutes=31)
    db_session.commit()

    # Klaim ulang
    resp = client.post("/api/v1/internal/extraction/claim?limit=1", headers=INTERNAL_HEADERS)
    data = resp.json()
    assert len(data) == 1
    assert data[0]["document_id"] == d1.id
    assert data[0]["attempt"] == 2


def test_e04_max_attempts_exceeded_not_claimed(client, seed_claimable_docs, db_session):
    """E04: Dokumen dengan extraction_attempts >= max_attempts tidak dapat diklaim."""
    for doc_id in seed_claimable_docs:
        d = db_session.query(Document).filter(Document.id == doc_id).first()
        d.extraction_attempts = settings.extraction_max_attempts
    db_session.commit()

    resp = client.post("/api/v1/internal/extraction/claim?limit=5", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    assert len(resp.json()) == 0


def test_e05_successful_extraction_patch(client, seed_claimable_docs, db_session, test_storage):
    """E05: PATCH hasil ekstraksi sukses lengkap -> status terindeks, metadata terisi, pindah ke KB, audit EXTRACTION_RESULT."""
    # Klaim dokumen
    resp_claim = client.post("/api/v1/internal/extraction/claim?limit=1", headers=INTERNAL_HEADERS)
    doc_id = resp_claim.json()[0]["document_id"]

    payload = {
        "title": "Peraturan OJK tentang Operasional Perbankan",
        "regulation_number": "12/POJK.03/2023",
        "regulation_type": "POJK",
        "release_date": "2023-09-15",
        "extraction_method": "teks_langsung",
        "full_text": "Isi lengkap ketentuan pasal-pasal perbankan digital.",
        "confidence": {
            "title": 0.95,
            "regulation_number": 0.92,
            "regulation_type": 0.98,
            "release_date": 0.90,
        },
    }

    resp = client.patch(f"/api/v1/internal/documents/{doc_id}/extraction", json=payload, headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "terindeks"
    assert "title" in data["changed_fields"]
    assert data["placement"]["placed"] is True

    # Audit log
    audit = db_session.query(AuditLog).filter(AuditLog.action == "EXTRACTION_RESULT", AuditLog.target_resource == f"document:{doc_id}").first()
    assert audit is not None


def test_e06_low_confidence_results_in_perlu_koreksi(client, seed_claimable_docs, db_session):
    """E06: PATCH dengan confidence regulation_number < threshold -> status perlu_koreksi & muncul di /needs-review."""
    resp_claim = client.post("/api/v1/internal/extraction/claim?limit=1", headers=INTERNAL_HEADERS)
    doc_id = resp_claim.json()[0]["document_id"]

    payload = {
        "title": "Peraturan OJK Nomor Meragukan",
        "regulation_number": "??/POJK.03/2023",
        "regulation_type": "POJK",
        "release_date": "2023-09-15",
        "full_text": "Isi dokumen...",
        "confidence": {
            "title": 0.95,
            "regulation_number": 0.40,  # di bawah threshold 0.7
        },
    }

    resp = client.patch(f"/api/v1/internal/documents/{doc_id}/extraction", json=payload, headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "perlu_koreksi"
    assert "regulation_number" in data["low_confidence_fields"]

    # Cek antrean needs-review
    resp_nr = client.get("/api/v1/documents/needs-review")
    assert resp_nr.status_code == 200
    nr_ids = [item["id"] for item in resp_nr.json()["items"]]
    assert doc_id in nr_ids


def test_e07_indonesian_field_aliases_accepted(client, seed_claimable_docs):
    """E07: PATCH dengan alias Bahasa Indonesia (judul, nomor_peraturan, dll.) diterima setara."""
    resp_claim = client.post("/api/v1/internal/extraction/claim?limit=1", headers=INTERNAL_HEADERS)
    doc_id = resp_claim.json()[0]["document_id"]

    payload = {
        "judul": "Peraturan Aliased OJK",
        "nomor_peraturan": "33/POJK.03/2023",
        "jenis_peraturan": "POJK",
        "tanggal_terbit": "2023-10-01",
        "metode_ekstraksi": "teks_langsung",
        "teks_lengkap": "Teks ekstraksi lengkap.",
        "confidence": {"title": 0.95},
    }

    resp = client.patch(f"/api/v1/internal/documents/{doc_id}/extraction", json=payload, headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "terindeks"


def test_e08_manual_correction_not_overwritten_by_extraction(client, seed_claimable_docs, db_session):
    """E08: Jika dokumen sudah dikoreksi manual, PATCH ekstraksi TIDAK menimpa metadata manual."""
    resp_claim = client.post("/api/v1/internal/extraction/claim?limit=1", headers=INTERNAL_HEADERS)
    doc_id = resp_claim.json()[0]["document_id"]

    # Simulasikan koreksi manual
    client.patch(f"/api/v1/documents/{doc_id}/metadata", json={
        "title": "Judul Hasil Koreksi Manual Valid",
        "regulation_number": "77/POJK.03/2023",
    })

    # Kirim hasil ekstraksi ML
    payload = {
        "title": "Judul Ekstraksi Salah dari OCR",
        "regulation_number": "999/SALAH/2023",
        "full_text": "Teks ekstraksi yang harus tetap tersimpan.",
    }
    resp = client.patch(f"/api/v1/internal/documents/{doc_id}/extraction", json=payload, headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    data = resp.json()

    assert "title" in data["ignored_fields"]
    assert "regulation_number" in data["ignored_fields"]

    # Verifikasi di database
    d = db_session.query(Document).filter(Document.id == doc_id).first()
    assert d.title == "Judul Hasil Koreksi Manual Valid"
    assert d.full_text == "Teks ekstraksi yang harus tetap tersimpan."


def test_e09_extraction_error_recorded_and_requeued_via_retry(client, seed_claimable_docs, db_session):
    """E09: PATCH error={code: 'ocr_gagal'} -> status gagal, dicatat di ingest_failures, dan retry mengembalikan 'requeued'."""
    resp_claim = client.post("/api/v1/internal/extraction/claim?limit=1", headers=INTERNAL_HEADERS)
    doc_id = resp_claim.json()[0]["document_id"]

    payload = {
        "error": {
            "code": "ocr_gagal",
            "message": "Halaman PDF buram dan tidak dapat dibaca oleh OCR engine.",
        }
    }
    resp = client.patch(f"/api/v1/internal/documents/{doc_id}/extraction", json=payload, headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    failure_id = resp.json()["failure_id"]

    # Verifikasi dokumen berstatus gagal
    d = db_session.query(Document).filter(Document.id == doc_id).first()
    assert d.processing_status == StatusPemrosesan.gagal

    # Verifikasi kegagalan di ingest_failures
    f = db_session.query(IngestFailure).filter(IngestFailure.id == failure_id).first()
    assert f.failure_type == JenisKegagalan.ocr_gagal
    assert f.document_id == doc_id

    # Retry kegagalan ekstraksi melalui endpoint retry
    retry_resp = client.post(f"/api/v1/ingest/failures/{failure_id}/retry")
    assert retry_resp.status_code == 200
    retry_data = retry_resp.json()
    assert retry_data["outcome"] == "requeued"
    assert retry_data["document_id"] == doc_id

    # Dokumen kembali ke 'diterima'
    db_session.refresh(d)
    assert d.processing_status == StatusPemrosesan.diterima


def test_e10_patch_unclaimed_doc_conflict_or_force(client, seed_claimable_docs):
    """E10: PATCH pada dokumen yang tidak berstatus 'diproses' menghasilkan 409, kecuali dengan force=true."""
    unclaimed_id = seed_claimable_docs[0]
    payload = {"full_text": "Teks uji"}

    resp_conflict = client.patch(f"/api/v1/internal/documents/{unclaimed_id}/extraction", json=payload, headers=INTERNAL_HEADERS)
    assert resp_conflict.status_code == 409

    resp_forced = client.patch(f"/api/v1/internal/documents/{unclaimed_id}/extraction?force=true", json=payload, headers=INTERNAL_HEADERS)
    assert resp_forced.status_code == 200


def test_e11_missing_or_invalid_api_key_401(client, seed_claimable_docs):
    """E11: Tanpa atau salah header X-Internal-API-Key menghasilkan 401."""
    resp_no_key = client.post("/api/v1/internal/extraction/claim")
    assert resp_no_key.status_code == 401

    resp_wrong_key = client.post("/api/v1/internal/extraction/claim", headers={"X-Internal-API-Key": "wrong-key"})
    assert resp_wrong_key.status_code == 401


def test_e12_get_internal_document_pdf(client, seed_claimable_docs):
    """E12: GET /internal/documents/{id}/pdf -> 200 dengan internal key, 401 tanpa key."""
    doc_id = seed_claimable_docs[0]
    resp_no_key = client.get(f"/api/v1/internal/documents/{doc_id}/pdf")
    assert resp_no_key.status_code == 401

    resp_ok = client.get(f"/api/v1/internal/documents/{doc_id}/pdf", headers=INTERNAL_HEADERS)
    assert resp_ok.status_code == 200
    assert resp_ok.headers["content-type"] == "application/pdf"
