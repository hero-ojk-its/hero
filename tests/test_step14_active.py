"""
tests/test_step14_active.py
Pengujian US-30: Nonaktifkan & Pindahkan Dokumen (Langkah 14).
Kasus uji N01 s.d. N11 sesuai spesifikasi.
"""
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import Document
from app.models.category import Category
from app.models.audit_log import AuditLog
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
)
from app.services.audit_service import (
    DEACTIVATE_DOCUMENT,
    ACTIVATE_DOCUMENT,
    UPDATE_METADATA,
)
from app.services.storage_service import StorageService
from tests.conftest import make_pdf

INTERNAL_HEADERS = {"X-Internal-API-Key": settings.internal_api_key}


@pytest.fixture
def sample_active_doc(db_session: Session, test_storage: StorageService) -> Document:
    """Fixture membuat dokumen aktif di Knowledge Base."""
    pdf_bytes = make_pdf("Konten PDF Regulasi Aktif Langkah 14")
    stored_path = test_storage.save_pdf(pdf_bytes, filename_hint="POJK_14_2026.pdf", subdir="kb/Perbankan/2026")

    # Ambil salah satu kategori
    cat = db_session.query(Category).first()
    cat_id = cat.id if cat else None

    import hashlib
    actual_hash = hashlib.sha256(pdf_bytes).hexdigest()

    doc = Document(
        title="POJK Pengujian Langkah 14",
        regulation_number="POJK 14/POJK.03/2026",
        regulation_type="Peraturan OJK",
        regulation_year=2026,
        bidang="Perbankan",
        file_path_pdf=stored_path,
        file_hash=actual_hash,
        file_size_bytes=len(pdf_bytes),
        full_text="Isi lengkap teks regulasi perbankan tahun 2026",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        category_id=cat_id,
        is_active=True,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def test_n01_deactivate_with_reason(client: TestClient, sample_active_doc: Document, db_session: Session):
    """
    N01: Nonaktifkan dengan alasan valid (>= 5 karakter).
    Ekspektasi: 200, changed: true, kolom terisi, audit DEACTIVATE_DOCUMENT berisi alasan.
    """
    reason = "Salah unggah: bukan dokumen regulasi resmi"
    resp = client.put(
        f"/api/v1/documents/{sample_active_doc.id}/active",
        json={"is_active": False, "reason": reason},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["document_id"] == sample_active_doc.id
    assert data["is_active"] is False
    assert data["changed"] is True
    assert data["deactivated_at"] is not None
    assert data["deactivated_reason"] == reason

    # Verifikasi database
    db_session.refresh(sample_active_doc)
    assert sample_active_doc.is_active is False
    assert sample_active_doc.deactivated_reason == reason
    assert sample_active_doc.deactivated_at is not None

    # Verifikasi audit log
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == DEACTIVATE_DOCUMENT,
            AuditLog.target_resource == f"document:{sample_active_doc.id}",
        )
        .first()
    )
    assert audit is not None
    assert audit.detail.get("reason") == reason
    assert audit.detail.get("before", {}).get("is_active") is True
    assert audit.detail.get("after", {}).get("is_active") is False


def test_n02_deactivate_without_reason_or_too_short(client: TestClient, sample_active_doc: Document, db_session: Session):
    """
    N02: Nonaktifkan tanpa alasan atau alasan < 5 karakter setelah di-trim.
    Ekspektasi: 422, data di DB tidak berubah.
    """
    # Tanpa alasan
    resp1 = client.put(
        f"/api/v1/documents/{sample_active_doc.id}/active",
        json={"is_active": False},
    )
    assert resp1.status_code == 422

    # Alasan terlalu pendek
    resp2 = client.put(
        f"/api/v1/documents/{sample_active_doc.id}/active",
        json={"is_active": False, "reason": "ab"},
    )
    assert resp2.status_code == 422

    # Alasan spasi doang
    resp3 = client.put(
        f"/api/v1/documents/{sample_active_doc.id}/active",
        json={"is_active": False, "reason": "   ab   "},
    )
    assert resp3.status_code == 422

    # Verifikasi data tidak berubah
    db_session.refresh(sample_active_doc)
    assert sample_active_doc.is_active is True
    assert sample_active_doc.deactivated_at is None
    assert sample_active_doc.deactivated_reason is None


def test_n03_deactivate_idempotent_twice(client: TestClient, sample_active_doc: Document, db_session: Session):
    """
    N03: Nonaktifkan dua kali.
    Ekspektasi: Panggilan kedua 200 changed: false, hanya 1 entri audit.
    """
    reason = "Dokumen duplikat beda scan"
    resp1 = client.put(
        f"/api/v1/documents/{sample_active_doc.id}/active",
        json={"is_active": False, "reason": reason},
    )
    assert resp1.status_code == 200
    assert resp1.json()["changed"] is True

    # Panggilan kedua dengan status yang sama
    resp2 = client.put(
        f"/api/v1/documents/{sample_active_doc.id}/active",
        json={"is_active": False, "reason": "Alasan kedua sama saja"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["changed"] is False
    assert resp2.json()["is_active"] is False

    # Verifikasi hanya ada 1 entri audit
    audits = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == DEACTIVATE_DOCUMENT,
            AuditLog.target_resource == f"document:{sample_active_doc.id}",
        )
        .all()
    )
    assert len(audits) == 1


def test_n04_get_documents_filtering(client: TestClient, sample_active_doc: Document, db_session: Session):
    """
    N04: GET /documents/ menyaring dokumen nonaktif secara default.
    Muncul jika include_inactive=true.
    """
    # Buat dokumen kedua
    doc2 = Document(
        title="Dokumen Aktif Kedua",
        regulation_number="POJK 99/2026",
        file_path_pdf="kb/doc2.pdf",
        file_hash="hash_doc2_test_step14",
        file_size_bytes=1024,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        is_active=True,
    )
    db_session.add(doc2)
    db_session.commit()

    # Nonaktifkan doc1
    client.put(
        f"/api/v1/documents/{sample_active_doc.id}/active",
        json={"is_active": False, "reason": "Sengaja dinonaktifkan"},
    )

    # 1. Default (include_inactive=False): hanya doc2 yang muncul
    resp_default = client.get("/api/v1/documents/")
    assert resp_default.status_code == 200
    items_default = resp_default.json()["items"]
    ids_default = [item["id"] for item in items_default]
    assert sample_active_doc.id not in ids_default
    assert doc2.id in ids_default

    # 2. include_inactive=true: kedua dokumen muncul
    resp_all = client.get("/api/v1/documents/?include_inactive=true")
    assert resp_all.status_code == 200
    items_all = resp_all.json()["items"]
    ids_all = [item["id"] for item in items_all]
    assert sample_active_doc.id in ids_all
    assert doc2.id in ids_all

    # Pastikan field is_active, deactivated_at, deactivated_reason ada di list item
    deactivated_item = next(it for it in items_all if it["id"] == sample_active_doc.id)
    assert deactivated_item["is_active"] is False
    assert deactivated_item["deactivated_reason"] == "Sengaja dinonaktifkan"
    assert deactivated_item["deactivated_at"] is not None


def test_n05_get_inactive_document_detail_and_pdf(client: TestClient, sample_active_doc: Document):
    """
    N05: GET /documents/{id} dan /pdf dokumen nonaktif tetap bisa diakses (200).
    """
    client.put(
        f"/api/v1/documents/{sample_active_doc.id}/active",
        json={"is_active": False, "reason": "Penonaktifan administratif"},
    )

    # Detail
    resp_detail = client.get(f"/api/v1/documents/{sample_active_doc.id}")
    assert resp_detail.status_code == 200
    data = resp_detail.json()
    assert data["is_active"] is False
    assert data["deactivated_reason"] == "Penonaktifan administratif"
    assert data["deactivated_at"] is not None

    # PDF
    resp_pdf = client.get(f"/api/v1/documents/{sample_active_doc.id}/pdf")
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers.get("content-type") == "application/pdf"


def test_n06_dashboard_and_category_tree(client: TestClient, sample_active_doc: Document, db_session: Session):
    """
    N06: Dashboard summary dan /categories/tree hanya menghitung dokumen aktif.
    Setelah dinonaktifkan: corpus berkurang 1, inactive_documents = 1, tree count berkurang 1.
    """
    # Ambil baseline awal (1 dokumen aktif)
    dash_before = client.get("/api/v1/dashboard/summary").json()
    assert dash_before["kb"]["corpus_documents"] == 1
    assert dash_before["kb"]["inactive_documents"] == 0

    tree_before = client.get("/api/v1/categories/tree").json()
    total_tree_before = sum(node["total_document_count"] for node in tree_before)
    assert total_tree_before == 1

    # Nonaktifkan dokumen
    client.put(
        f"/api/v1/documents/{sample_active_doc.id}/active",
        json={"is_active": False, "reason": "Uji statistik dashboard"},
    )

    # Cek dashboard setelah penonaktifan
    dash_after = client.get("/api/v1/dashboard/summary").json()
    assert dash_after["kb"]["corpus_documents"] == 0
    assert dash_after["kb"]["inactive_documents"] == 1

    # Cek category tree setelah penonaktifan
    tree_after = client.get("/api/v1/categories/tree").json()
    total_tree_after = sum(node["total_document_count"] for node in tree_after)
    assert total_tree_after == 0


def test_n07_duplicate_detection_matches_inactive(client: TestClient, sample_active_doc: Document, db_session: Session):
    """
    N07: Unggah ulang berkas dengan hash sama mendeteksi duplikat dari dokumen nonaktif,
    dengan is_active: false di informasi duplikat.
    """
    # Nonaktifkan sample_active_doc
    client.put(
        f"/api/v1/documents/{sample_active_doc.id}/active",
        json={"is_active": False, "reason": "Dokumen nonaktif untuk uji duplikat"},
    )

    # Unggah berkas yang sama via POST /api/v1/ingest/upload-pdf
    pdf_content = make_pdf("Konten PDF Regulasi Aktif Langkah 14")
    files = [("files", ("POJK_14_2026.pdf", pdf_content, "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "title": "Percobaan Unggah Duplikat",
        "regulation_number": "POJK 14/POJK.03/2026",
    }
    resp = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert resp.status_code == 200
    body = resp.json()
    assert body["duplicate_count"] == 1
    assert body["details"][0]["status"] == "duplicate"
    assert body["details"][0]["duplicate_of_document_id"] == sample_active_doc.id

    # Cek entri kegagalan duplikat di /api/v1/ingest/failures?include_duplicates=true&follow_up_status=all
    resp_failures = client.get("/api/v1/ingest/failures?include_duplicates=true&follow_up_status=all")
    assert resp_failures.status_code == 200
    failures = resp_failures.json()["items"]
    dup_failure = next((f for f in failures if f["failure_type"] == "duplikat"), None)
    assert dup_failure is not None
    assert dup_failure["duplicate_of_document"] is not None
    assert dup_failure["duplicate_of_document"]["id"] == sample_active_doc.id
    assert dup_failure["duplicate_of_document"]["is_active"] is False

    # Cek juga di detail job /api/v1/ingest/jobs/{job_id}
    resp_job = client.get(f"/api/v1/ingest/jobs/{body['job_id']}")
    assert resp_job.status_code == 200
    job_data = resp_job.json()
    job_dup = next((f for f in job_data["failures"] if f["failure_type"] == "duplikat"), None)
    assert job_dup is not None
    assert job_dup["duplicate_of_document"] is not None
    assert job_dup["duplicate_of_document"]["is_active"] is False


def test_n08_reactivate_document(client: TestClient, sample_active_doc: Document, db_session: Session):
    """
    N08: Aktifkan kembali dokumen.
    Ekspektasi: Kolom nonaktif dikosongkan, kembali tampil di daftar dan statistik, audit ACTIVATE_DOCUMENT.
    """
    # Nonaktifkan dulu
    client.put(
        f"/api/v1/documents/{sample_active_doc.id}/active",
        json={"is_active": False, "reason": "Nonaktif sementara"},
    )

    # Aktifkan kembali
    resp = client.put(
        f"/api/v1/documents/{sample_active_doc.id}/active",
        json={"is_active": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_active"] is True
    assert data["changed"] is True
    assert data["deactivated_at"] is None
    assert data["deactivated_reason"] is None

    # Verifikasi DB
    db_session.refresh(sample_active_doc)
    assert sample_active_doc.is_active is True
    assert sample_active_doc.deactivated_at is None
    assert sample_active_doc.deactivated_reason is None

    # Tampil kembali di /documents/ tanpa include_inactive
    resp_list = client.get("/api/v1/documents/")
    items = resp_list.json()["items"]
    assert any(it["id"] == sample_active_doc.id for it in items)

    # Statistik dashboard kembali 1
    dash = client.get("/api/v1/dashboard/summary").json()
    assert dash["kb"]["corpus_documents"] == 1
    assert dash["kb"]["inactive_documents"] == 0

    # Audit ACTIVATE_DOCUMENT tercatat
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == ACTIVATE_DOCUMENT,
            AuditLog.target_resource == f"document:{sample_active_doc.id}",
        )
        .first()
    )
    assert audit is not None
    assert audit.detail.get("before", {}).get("is_active") is False
    assert audit.detail.get("after", {}).get("is_active") is True


def test_n09_move_category_via_patch_metadata(client: TestClient, sample_active_doc: Document, db_session: Session, test_storage: StorageService):
    """
    N09: Pindah kategori lewat PATCH /metadata category_id.
    Berkas berpindah folder dan audit UPDATE_METADATA memuat category_id before/after (bukti TC-15).
    """
    # Buat kategori tujuan baru
    target_cat = Category(name="Perasuransian", auto_created=False)
    db_session.add(target_cat)
    db_session.commit()
    db_session.refresh(target_cat)

    old_cat_id = sample_active_doc.category_id
    old_pdf_path = sample_active_doc.file_path_pdf

    # Patch category_id
    resp = client.patch(
        f"/api/v1/documents/{sample_active_doc.id}/metadata",
        json={"category_id": target_cat.id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["category_id"] == target_cat.id

    # Cek berkas berpindah
    db_session.refresh(sample_active_doc)
    assert sample_active_doc.category_id == target_cat.id
    new_pdf_path = sample_active_doc.file_path_pdf
    assert new_pdf_path != old_pdf_path
    assert "Perasuransian" in new_pdf_path

    # Berkas di lokasi baru benar-benar ada di storage
    assert test_storage.exists(new_pdf_path)

    # Audit log UPDATE_METADATA mencatat before & after category_id
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == UPDATE_METADATA,
            AuditLog.target_resource == f"document:{sample_active_doc.id}",
        )
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.detail.get("before", {}).get("category_id") == old_cat_id
    assert audit.detail.get("after", {}).get("category_id") == target_cat.id


def test_n10_extraction_claim_ignores_inactive(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    N10: Klaim ekstraksi internal tidak mengklaim dokumen nonaktif.
    """
    pdf_bytes = make_pdf("PDF Klaim Ekstraksi")
    stored_path = test_storage.save_pdf(pdf_bytes, filename_hint="test_n10.pdf", subdir="pdf/_inbox")

    # Buat dokumen nonaktif berstatus diterima
    inactive_doc = Document(
        title="Dokumen Diterima Nonaktif",
        regulation_number="POJK 10/2026",
        file_path_pdf=stored_path,
        file_hash="hash_n10_test",
        file_size_bytes=len(pdf_bytes),
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.diterima,
        is_active=False,
        deactivated_reason="Dinonaktifkan sebelum ekstraksi",
    )
    db_session.add(inactive_doc)
    db_session.commit()

    # Panggil claim endpoint
    resp = client.post(
        "/api/v1/internal/extraction/claim?limit=10",
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    claimed_ids = [item["document_id"] for item in resp.json()]
    assert inactive_doc.id not in claimed_ids


def test_n11_deactivate_non_existent_document(client: TestClient):
    """
    N11: Dokumen tidak ada mengembalikan 404.
    """
    resp = client.put(
        "/api/v1/documents/999999/active",
        json={"is_active": False, "reason": "Dokumen tidak ditemukan"},
    )
    assert resp.status_code == 404
