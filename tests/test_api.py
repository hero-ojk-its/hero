import io
from pathlib import Path
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.config import settings
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.enums import StatusKeberlakuan
from tests.conftest import make_pdf


def test_t01_health_and_root(client: TestClient):
    """T01: GET / dan GET /health -> 200; /health -> database: 'ok'."""
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert res_root.json() == {"status": "ok"}

    res_health = client.get("/health")
    assert res_health.status_code == 200
    data = res_health.json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"
    assert "auth_enabled" in data


def test_t02_categories_seeded(client: TestClient):
    """T02: GET /api/v1/categories/ -> 200, berisi 5 kategori seed."""
    res = client.get("/api/v1/categories/")
    assert res.status_code == 200
    categories = res.json()
    assert len(categories) == 5
    names = [c["name"] for c in categories]
    assert "POJK" in names
    assert "SEOJK" in names
    assert "UU" in names
    assert "PP" in names
    assert "Peraturan Internal DPEA" in names


def test_t03_list_endpoints_status_200(client: TestClient):
    """T03: GET /api/v1/documents/, GET /api/v1/ingest/jobs, GET /api/v1/ingest/status -> 200."""
    res_docs = client.get("/api/v1/documents/")
    assert res_docs.status_code == 200
    assert "items" in res_docs.json()

    res_jobs = client.get("/api/v1/ingest/jobs")
    assert res_jobs.status_code == 200
    assert "items" in res_jobs.json()

    res_status = client.get("/api/v1/ingest/status")
    assert res_status.status_code == 200
    data = res_status.json()
    assert "total_documents" in data
    assert "dicabut_documents" in data
    assert "total_draft_kajian" in data


def test_t04_audit_logs_unauthenticated_auth_disabled(client: TestClient):
    """T04: GET /api/v1/audit-logs/ tanpa token saat AUTH_ENABLED=false -> 200."""
    res = client.get("/api/v1/audit-logs/")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_t05_audit_logs_unauthenticated_auth_enabled(auth_client: TestClient):
    """T05: GET /api/v1/audit-logs/ tanpa token saat AUTH_ENABLED=true -> 401."""
    res = auth_client.get("/api/v1/audit-logs/")
    assert res.status_code == 401


def test_t06_admin_login_and_audit_log(auth_client: TestClient, seed_admin_user):
    """T06: Buat admin di DB uji, login, GET /audit-logs/ dengan token saat AUTH_ENABLED=true -> 200, ada entri LOGIN."""
    login_res = auth_client.post(
        "/api/v1/auth/login",
        data={"username": "admin_test", "password": "adminpassword123"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    logs_res = auth_client.get(
        "/api/v1/audit-logs/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logs_res.status_code == 200
    logs = logs_res.json()
    assert any(log["action"] == "LOGIN" for log in logs)


def test_t07_upload_single_valid_pdf(client: TestClient, db_session: Session, test_storage):
    """
    T07: Unggah 1 PDF valid (document_role=draft_kajian).
    Ekspektasi: 200, success_count=1, berkas ada di storage, file_path_pdf relatif, job_status='selesai', ada audit UPLOAD_DOCUMENT.
    """
    pdf_content = make_pdf("Naskah Akademik Draft Kajian Regulasi")
    files = [("files", ("draft_kajian_01.pdf", io.BytesIO(pdf_content), "application/pdf"))]
    data = {
        "access_classification": "non_publik",
        "document_role": "draft_kajian",
        "title": "Draft Kajian AI Perbankan",
    }

    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["success_count"] == 1
    assert body["job_status"] == "selesai"
    assert len(body["details"]) == 1
    detail = body["details"][0]
    assert detail["status"] == "success"
    doc_id = detail["document_id"]

    # Verifikasi di database
    doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert doc is not None
    assert doc.document_role.value == "draft_kajian"
    assert not doc.file_path_pdf.startswith("/")  # Relatif
    assert test_storage.exists(doc.file_path_pdf) is True

    # Verifikasi audit log
    audit = db_session.query(AuditLog).filter(AuditLog.action == "UPLOAD_DOCUMENT").first()
    assert audit is not None
    assert audit.target_resource == f"document:{doc_id}"


def test_t08_upload_duplicate_pdf(client: TestClient, db_session: Session):
    """T08: Unggah PDF yang sama lagi -> duplicate_count=1, duplicate_of_document_id benar, jumlah dokumen di DB tetap 1."""
    pdf_content = make_pdf("Peraturan Duplikasi")
    files1 = [("files", ("peraturan_1.pdf", io.BytesIO(pdf_content), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    res1 = client.post("/api/v1/ingest/upload-pdf", files=files1, data=data)
    assert res1.status_code == 200
    doc_id = res1.json()["details"][0]["document_id"]

    # Unggah ulang berkas yang sama persis
    files2 = [("files", ("peraturan_copy.pdf", io.BytesIO(pdf_content), "application/pdf"))]
    res2 = client.post("/api/v1/ingest/upload-pdf", files=files2, data=data)
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["success_count"] == 0
    assert body2["duplicate_count"] == 1
    assert body2["details"][0]["status"] == "duplicate"
    assert body2["details"][0]["duplicate_of_document_id"] == doc_id
    assert db_session.query(Document).count() == 1


def test_t09_upload_txt_file(client: TestClient):
    """T09: Unggah .txt -> failed_count=1, reason_code='format_tidak_didukung'."""
    files = [("files", ("catatan.txt", io.BytesIO(b"Ini catatan text"), "text/plain"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["failed_count"] == 1
    assert body["details"][0]["status"] == "failed"
    assert body["details"][0]["reason_code"] == "format_tidak_didukung"


def test_t10_upload_invalid_pdf_content(client: TestClient):
    """T10: Unggah berkas .pdf berisi teks biasa tanpa %PDF- -> failed, reason_code='format_tidak_didukung'."""
    files = [("files", ("palsu.pdf", io.BytesIO(b"BUKAN PDF SAMA SEKALI"), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["failed_count"] == 1
    assert body["details"][0]["status"] == "failed"
    assert body["details"][0]["reason_code"] == "format_tidak_didukung"


def test_t11_upload_empty_pdf(client: TestClient):
    """T11: Unggah .pdf kosong (0 byte) -> failed, reason_code='berkas_kosong'."""
    files = [("files", ("kosong.pdf", io.BytesIO(b""), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["failed_count"] == 1
    assert body["details"][0]["status"] == "failed"
    assert body["details"][0]["reason_code"] == "berkas_kosong"


def test_t12_upload_exceed_max_mb(client: TestClient, monkeypatch):
    """T12: Unggah berkas melebihi max_upload_mb -> failed, reason_code='ukuran_melebihi_batas'."""
    # Monkeypatch max_upload_mb jadi 1 MB
    monkeypatch.setattr(settings, "max_upload_mb", 1)

    # Buat konten 2 MB
    big_pdf = make_pdf("X" * (2 * 1024 * 1024))
    files = [("files", ("besar.pdf", io.BytesIO(big_pdf), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["failed_count"] == 1
    assert body["details"][0]["status"] == "failed"
    assert body["details"][0]["reason_code"] == "ukuran_melebihi_batas"


def test_t13_batch_three_files_mixed(client: TestClient):
    """
    T13: Batch 3 berkas: valid baru + duplikat + non-PDF.
    Ekspektasi: 200, 1/1/1, job_status='selesai', tidak ada exception.
    """
    # 1. Simpan dokumen awal untuk dijadikan duplikat
    pdf_dup = make_pdf("Dokumen Duplikat Batch")
    files_init = [("files", ("init.pdf", io.BytesIO(pdf_dup), "application/pdf"))]
    data_init = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    client.post("/api/v1/ingest/upload-pdf", files=files_init, data=data_init)

    # 2. Batch 3 berkas
    pdf_new = make_pdf("Dokumen Baru Batch")
    batch_files = [
        ("files", ("baru.pdf", io.BytesIO(pdf_new), "application/pdf")),
        ("files", ("duplikat.pdf", io.BytesIO(pdf_dup), "application/pdf")),
        ("files", ("salah.txt", io.BytesIO(b"bukan pdf"), "text/plain")),
    ]
    batch_data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=batch_files, data=batch_data)
    assert res.status_code == 200
    body = res.json()
    assert body["total_files"] == 3
    assert body["success_count"] == 1
    assert body["duplicate_count"] == 1
    assert body["failed_count"] == 1
    assert body["job_status"] == "selesai"


def test_t14_batch_with_single_doc_metadata_rejected(client: TestClient):
    """T14: Batch 2 berkas + regulation_number terisi -> 422."""
    pdf1 = make_pdf("Dokumen 1")
    pdf2 = make_pdf("Dokumen 2")
    files = [
        ("files", ("doc1.pdf", io.BytesIO(pdf1), "application/pdf")),
        ("files", ("doc2.pdf", io.BytesIO(pdf2), "application/pdf")),
    ]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "regulation_number": "POJK-12-2026",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 422
    assert "Metadata per-dokumen" in res.json()["detail"]


def test_t15_missing_document_role_rejected(client: TestClient):
    """T15: Tanpa document_role -> 422."""
    pdf = make_pdf("Dokumen Uji")
    files = [("files", ("doc.pdf", io.BytesIO(pdf), "application/pdf"))]
    data = {
        "access_classification": "publik",
        # document_role tidak disertakan
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 422


def test_t16_invalid_release_date_format_rejected(client: TestClient):
    """T16: release_date='31-12-2024' -> 422."""
    pdf = make_pdf("Dokumen Uji")
    files = [("files", ("doc.pdf", io.BytesIO(pdf), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "release_date": "31-12-2024",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 422
    assert "Format tanggal rilis tidak valid" in res.json()["detail"]


def test_t17_pdf_overwrite_regression(client: TestClient, db_session: Session, test_storage):
    """
    T17: Regresi bug timpa PDF: 2 unggahan tunggal, PDF BERBEDA, regulation_number SAMA.
    Ekspektasi: keduanya success; 2 berkas terpisah di storage; SHA-256 tiap berkas di disk == file_hash DB masing-masing.
    """
    pdf1 = make_pdf("Isi Peraturan Versi A")
    pdf2 = make_pdf("Isi Peraturan Versi B (Revisi)")

    reg_num = "POJK-99-2026"

    # Unggah versi 1
    files1 = [("files", ("reg_v1.pdf", io.BytesIO(pdf1), "application/pdf"))]
    data1 = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "regulation_number": reg_num,
    }
    res1 = client.post("/api/v1/ingest/upload-pdf", files=files1, data=data1)
    assert res1.status_code == 200
    doc1_id = res1.json()["details"][0]["document_id"]

    # Unggah versi 2 dengan nomor regulasi yang sama persis
    files2 = [("files", ("reg_v2.pdf", io.BytesIO(pdf2), "application/pdf"))]
    data2 = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "regulation_number": reg_num,
    }
    res2 = client.post("/api/v1/ingest/upload-pdf", files=files2, data=data2)
    assert res2.status_code == 200
    doc2_id = res2.json()["details"][0]["document_id"]

    # Verifikasi keduanya tersimpan di DB
    doc1 = db_session.query(Document).filter(Document.id == doc1_id).first()
    doc2 = db_session.query(Document).filter(Document.id == doc2_id).first()
    assert doc1 is not None and doc2 is not None
    assert doc1.file_path_pdf != doc2.file_path_pdf

    # Verifikasi isi kedua berkas di disk tidak saling menimpa
    file1_bytes = test_storage.absolute_path(doc1.file_path_pdf).read_bytes()
    file2_bytes = test_storage.absolute_path(doc2.file_path_pdf).read_bytes()
    assert file1_bytes == pdf1
    assert file2_bytes == pdf2


def test_t18_batch_all_failed(client: TestClient):
    """T18: Batch hanya non-PDF -> job_status='gagal'."""
    files = [
        ("files", ("file1.txt", io.BytesIO(b"teks"), "text/plain")),
        ("files", ("file2.doc", io.BytesIO(b"dokumen"), "application/msword")),
    ]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["success_count"] == 0
    assert body["failed_count"] == 2
    assert body["job_status"] == "gagal"


def test_t19_scrape_url_endpoint_removed(client: TestClient):
    """T19: POST /api/v1/ingest/scrape-url -> 404 atau 405."""
    res = client.post("/api/v1/ingest/scrape-url", data={"source_url": "https://example.com"})
    assert res.status_code in (404, 405)


def test_t20_scraping_source_crud_and_audit(client: TestClient, db_session: Session):
    """T20: CRUD scraping source: create 201, duplicate URL 400, list 200, patch 200, delete 200; audit tercatat."""
    # 1. Create 201
    payload = {
        "name": "JDIH OJK Pusat",
        "url": "https://jdih.ojk.go.id",
        "is_active": True,
    }
    res_create = client.post("/api/v1/scraping-sources/", json=payload)
    assert res_create.status_code == 201
    source_id = res_create.json()["id"]

    # 2. Duplicate URL 400
    res_dup = client.post("/api/v1/scraping-sources/", json=payload)
    assert res_dup.status_code == 400

    # 3. List 200
    res_list = client.get("/api/v1/scraping-sources/")
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    # 4. Patch 200
    res_patch = client.patch(
        f"/api/v1/scraping-sources/{source_id}",
        json={"name": "JDIH OJK Resmi"},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["name"] == "JDIH OJK Resmi"

    # 5. Delete 200
    res_del = client.delete(f"/api/v1/scraping-sources/{source_id}")
    assert res_del.status_code == 200

    # Verifikasi audit logs untuk ketiga aksi
    actions = [a.action for a in db_session.query(AuditLog).all()]
    assert "CREATE_SOURCE" in actions
    assert "UPDATE_SOURCE" in actions
    assert "DELETE_SOURCE" in actions


def test_t21_update_document_status_with_revocation(client: TestClient, db_session: Session):
    """
    T21: PUT /api/v1/documents/{id}/status -> 'dicabut' dengan revoking_document_id -> 200, legal_reference_created=true.
    """
    # Buat dokumen 1 (yang akan dicabut) dan dokumen 2 (yang mencabut)
    doc1 = Document(
        title="POJK Lama",
        regulation_number="POJK-01-2020",
        file_path_pdf="pdf/doc1.pdf",
        file_hash="hash1",
        file_size_bytes=100,
        access_classification="publik",
        document_role="corpus_eksisting",
        status_keberlakuan=StatusKeberlakuan.berlaku,
    )
    doc2 = Document(
        title="POJK Baru Pencabut",
        regulation_number="POJK-05-2026",
        file_path_pdf="pdf/doc2.pdf",
        file_hash="hash2",
        file_size_bytes=200,
        access_classification="publik",
        document_role="corpus_eksisting",
        status_keberlakuan=StatusKeberlakuan.berlaku,
    )
    db_session.add_all([doc1, doc2])
    db_session.commit()
    db_session.refresh(doc1)
    db_session.refresh(doc2)

    # Lakukan pencabutan
    payload = {
        "status_keberlakuan": "dicabut",
        "revoking_document_id": doc2.id,
    }
    res = client.put(f"/api/v1/documents/{doc1.id}/status", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["status_keberlakuan"] == "dicabut"
    assert body["legal_reference_created"] is True
    assert body["legal_reference_id"] is not None

    # Verifikasi status di DB terupdate
    db_session.refresh(doc1)
    assert doc1.status_keberlakuan == StatusKeberlakuan.dicabut
