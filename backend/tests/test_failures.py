"""
tests/test_failures.py
Pengujian otomatis untuk log kegagalan, penanganan duplikat, dan antrian retry (Langkah 2: F01-F12).
"""
import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.category import Category
from app.models.document import Document
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.models.audit_log import AuditLog
from app.models.enums import JenisKegagalan, StatusTindakLanjut, StatusJobIngest
from app.services.storage_service import StorageService
from app.services.file_validation import fingerprint
from tests.conftest import make_pdf


def test_f01_upload_txt_non_pdf(client: TestClient, db_session: Session):
    """F01: Unggah .txt -> ingest_failures: format_tidak_didukung, is_retryable=False, quarantine_path=None; respons punya failure_id."""
    txt_content = b"Ini file teks biasa, bukan PDF."
    files = [("files", ("dokumen.txt", io.BytesIO(txt_content), "text/plain"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["failed_count"] == 1
    assert len(res_data["details"]) == 1
    detail = res_data["details"][0]
    assert detail["status"] == "failed"
    assert detail["failure_id"] is not None

    failure = db_session.query(IngestFailure).filter(IngestFailure.id == detail["failure_id"]).first()
    assert failure is not None
    assert failure.failure_type == JenisKegagalan.format_tidak_didukung
    assert failure.reason_code == "format_tidak_didukung"
    assert failure.is_retryable is False
    assert failure.quarantine_path is None
    assert failure.follow_up_status == StatusTindakLanjut.belum_ditangani


def test_f02_upload_duplicate_pdf(client: TestClient, db_session: Session):
    """F02: Unggah PDF sama dua kali -> duplikat dicatat, follow_up_status=diabaikan, filter default tidak memuatnya."""
    pdf_bytes = make_pdf("Dokumen regulasi unik F02")
    files1 = [("files", ("pojk_f02.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "title": "Peraturan F02 Pertama",
    }
    res1 = client.post("/api/v1/ingest/upload-pdf", files=files1, data=data)
    assert res1.status_code == 200
    doc_id_1 = res1.json()["details"][0]["document_id"]

    # Unggah kedua dengan isi identik
    files2 = [("files", ("pojk_f02_copy.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    res2 = client.post("/api/v1/ingest/upload-pdf", files=files2, data=data)
    assert res2.status_code == 200
    res2_data = res2.json()
    assert res2_data["duplicate_count"] == 1
    dup_detail = res2_data["details"][0]
    assert dup_detail["status"] == "duplicate"
    assert dup_detail["failure_id"] is not None

    failure = db_session.query(IngestFailure).filter(IngestFailure.id == dup_detail["failure_id"]).first()
    assert failure is not None
    assert failure.failure_type == JenisKegagalan.duplikat
    assert failure.follow_up_status == StatusTindakLanjut.diabaikan
    assert failure.duplicate_of_document_id == doc_id_1

    # GET /failures default tidak memuat duplikat
    res_fails_default = client.get("/api/v1/ingest/failures")
    assert res_fails_default.status_code == 200
    items_default = res_fails_default.json()["items"]
    assert not any(item["id"] == failure.id for item in items_default)

    # GET /failures dengan include_duplicates=true&follow_up_status=all memuatnya
    res_fails_all = client.get("/api/v1/ingest/failures?include_duplicates=true&follow_up_status=all")
    assert res_fails_all.status_code == 200
    items_all = res_fails_all.json()["items"]
    assert any(item["id"] == failure.id for item in items_all)


def test_f03_internal_error_saves_to_quarantine(client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch):
    """F03: Simulasi error saat commit dokumen -> baris kesalahan_internal, is_retryable=True, karantina ada & hash cocok."""
    pdf_bytes = make_pdf("Dokumen regulasi F03 untuk simulasi error")
    fp = fingerprint(pdf_bytes)

    # Monkeypatch session commit agar me-raise exception saat simpan document
    original_commit = db_session.commit
    call_count = {"val": 0}

    def failing_commit():
        call_count["val"] += 1
        if call_count["val"] == 2:  # commit ke-2 (saat doc disimpan setelah job dibuat)
            raise Exception("Database commit error terduga")
        return original_commit()

    monkeypatch.setattr(db_session, "commit", failing_commit)

    files = [("files", ("error_doc.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    detail = res.json()["details"][0]
    assert detail["status"] == "failed"
    fail_id = detail["failure_id"]
    assert fail_id is not None

    failure = db_session.query(IngestFailure).filter(IngestFailure.id == fail_id).first()
    assert failure.failure_type == JenisKegagalan.kesalahan_internal
    assert failure.is_retryable is True
    assert failure.quarantine_path is not None
    assert test_storage.exists(failure.quarantine_path)
    quarantine_content = test_storage.read_pdf(failure.quarantine_path)
    assert fingerprint(quarantine_content).sha256 == fp.sha256


def test_f04_retry_f03_success(client: TestClient, db_session: Session, test_storage: StorageService):
    """F04: Retry kegagalan F03 setelah gangguan dihapus -> 200, diproses_ulang, karantina terhapus, audit tercatat."""
    pdf_bytes = make_pdf("Dokumen regulasi F04 retryable")
    fp = fingerprint(pdf_bytes)
    quarantine_path = test_storage.save_pdf(pdf_bytes, filename_hint=f"{fp.sha256[:12]}_doc_f04.pdf", subdir="quarantine")

    # Buat job asal
    parent_job = JobIngest(
        job_type="unggah_manual",
        status=StatusJobIngest.gagal,
        failed_count=1,
    )
    db_session.add(parent_job)
    db_session.commit()
    db_session.refresh(parent_job)

    # Buat baris kegagalan retryable
    failure = IngestFailure(
        job_id=parent_job.id,
        original_filename="doc_f04.pdf",
        failure_type=JenisKegagalan.kesalahan_internal,
        reason_code="kesalahan_internal",
        message="Simulasi error sebelumnya",
        is_retryable=True,
        quarantine_path=quarantine_path,
        file_hash=fp.sha256,
        file_size_bytes=fp.size_bytes,
        ingest_options={"access_classification": "publik", "document_role": "corpus_eksisting", "category_id": None},
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    db_session.add(failure)
    db_session.commit()
    db_session.refresh(failure)

    res = client.post(f"/api/v1/ingest/failures/{failure.id}/retry")
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["outcome"] == "success"
    assert res_data["document_id"] is not None

    db_session.refresh(failure)
    assert failure.follow_up_status == StatusTindakLanjut.diproses_ulang
    assert failure.resolved_document_id == res_data["document_id"]
    assert failure.attempt_count == 1
    assert failure.quarantine_path is None
    assert not test_storage.exists(quarantine_path)

    # Cek job retry
    retry_job = db_session.query(JobIngest).filter(JobIngest.id == failure.last_retry_job_id).first()
    assert retry_job is not None
    assert retry_job.triggered_by == "retry"
    assert retry_job.retry_of_failure_id == failure.id

    # Cek audit log
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "RETRY_FAILURE", AuditLog.target_resource == f"ingest_failure:{failure.id}")
        .first()
    )
    assert audit is not None


def test_f05_retry_non_retryable_rejected(client: TestClient, db_session: Session):
    """F05: Retry baris non-retryable (F01) -> 409 Conflict."""
    parent_job = JobIngest(job_type="unggah_manual", status=StatusJobIngest.gagal)
    db_session.add(parent_job)
    db_session.commit()

    failure = IngestFailure(
        job_id=parent_job.id,
        original_filename="invalid.txt",
        failure_type=JenisKegagalan.format_tidak_didukung,
        reason_code="format_tidak_didukung",
        message="Format tidak didukung",
        is_retryable=False,
        quarantine_path=None,
        ingest_options={},
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    db_session.add(failure)
    db_session.commit()

    res = client.post(f"/api/v1/ingest/failures/{failure.id}/retry")
    assert res.status_code == 409


def test_f06_retry_content_already_in_kb(client: TestClient, db_session: Session, test_storage: StorageService):
    """F06: Retry baris yang isinya ternyata sudah ada di KB -> outcome=duplicate, follow_up_status=diabaikan."""
    pdf_bytes = make_pdf("Dokumen regulasi F06 duplikat saat retry")
    fp = fingerprint(pdf_bytes)

    # Masukkan dokumen ke database terlebih dahulu
    existing_doc = Document(
        title="Dokumen Eksisting F06",
        file_path_pdf="pdf/_inbox/f06.pdf",
        file_hash=fp.sha256,
        file_size_bytes=fp.size_bytes,
        access_classification="publik",
        document_role="corpus_eksisting",
    )
    db_session.add(existing_doc)

    parent_job = JobIngest(job_type="unggah_manual", status=StatusJobIngest.gagal)
    db_session.add(parent_job)
    db_session.commit()

    quarantine_path = test_storage.save_pdf(pdf_bytes, filename_hint=f"{fp.sha256[:12]}_doc_f06.pdf", subdir="quarantine")
    failure = IngestFailure(
        job_id=parent_job.id,
        original_filename="doc_f06.pdf",
        failure_type=JenisKegagalan.kesalahan_internal,
        reason_code="kesalahan_internal",
        message="Gagal sebelumnya",
        is_retryable=True,
        quarantine_path=quarantine_path,
        file_hash=fp.sha256,
        file_size_bytes=fp.size_bytes,
        ingest_options={"access_classification": "publik", "document_role": "corpus_eksisting"},
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    db_session.add(failure)
    db_session.commit()

    res = client.post(f"/api/v1/ingest/failures/{failure.id}/retry")
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["outcome"] == "duplicate"

    db_session.refresh(failure)
    assert failure.follow_up_status == StatusTindakLanjut.diabaikan
    assert failure.failure_type == JenisKegagalan.duplikat
    assert failure.duplicate_of_document_id == existing_doc.id


def test_f07_category_not_found_retry_with_override(client: TestClient, db_session: Session, test_storage: StorageService):
    """F07: Unggah dengan category_id invalid -> metadata_tidak_lengkap retryable; retry dengan valid category_id sukses."""
    pdf_bytes = make_pdf("Dokumen regulasi F07 kategori")
    files = [("files", ("pojk_f07.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "category_id": "99999",  # Kategori tidak ada
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    fail_id = res.json()["details"][0]["failure_id"]

    failure = db_session.query(IngestFailure).filter(IngestFailure.id == fail_id).first()
    assert failure.reason_code == "kategori_tidak_ditemukan"
    assert failure.failure_type == JenisKegagalan.metadata_tidak_lengkap
    assert failure.is_retryable is True

    # Ambil category ID yang valid (mis. POJK)
    pojk_cat = db_session.query(Category).filter(Category.name == "POJK").first()
    assert pojk_cat is not None

    # Retry dengan override category_id yang valid
    res_retry = client.post(
        f"/api/v1/ingest/failures/{fail_id}/retry",
        json={"category_id": pojk_cat.id},
    )
    assert res_retry.status_code == 200
    doc_id = res_retry.json()["document_id"]
    doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert doc.category_id == pojk_cat.id


def test_f08_patch_failure_status_validation(client: TestClient, db_session: Session):
    """F08: PATCH -> diabaikan -> belum_ditangani -> 200; PATCH -> diproses_ulang -> 422; audit UPDATE_FAILURE."""
    parent_job = JobIngest(job_type="unggah_manual", status=StatusJobIngest.selesai)
    db_session.add(parent_job)
    db_session.commit()

    failure = IngestFailure(
        job_id=parent_job.id,
        original_filename="doc_f08.pdf",
        failure_type=JenisKegagalan.kesalahan_internal,
        reason_code="kesalahan_internal",
        message="Error",
        is_retryable=False,
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    db_session.add(failure)
    db_session.commit()

    # 1. Update ke diabaikan -> 200
    res1 = client.patch(
        f"/api/v1/ingest/failures/{failure.id}",
        json={"follow_up_status": "diabaikan", "handling_note": "Abaikan untuk sementara"},
    )
    assert res1.status_code == 200
    assert res1.json()["follow_up_status"] == "diabaikan"
    assert res1.json()["handling_note"] == "Abaikan untuk sementara"

    # 2. Update balik ke belum_ditangani -> 200
    res2 = client.patch(
        f"/api/v1/ingest/failures/{failure.id}",
        json={"follow_up_status": "belum_ditangani"},
    )
    assert res2.status_code == 200
    assert res2.json()["follow_up_status"] == "belum_ditangani"

    # 3. Update ke diproses_ulang -> 422
    res3 = client.patch(
        f"/api/v1/ingest/failures/{failure.id}",
        json={"follow_up_status": "diproses_ulang"},
    )
    assert res3.status_code == 422


def test_f09_get_job_detail_mixed_batch(client: TestClient, db_session: Session):
    """F09: GET /ingest/jobs/{id} untuk batch campuran -> 200; documents & failures lengkap + judul pembanding; 404 jika tak ada."""
    pdf1 = make_pdf("Dokumen batch campuran sukses F09")
    pdf2 = make_pdf("Dokumen batch campuran duplikat F09")
    txt_invalid = b"Bukan pdf"

    # Ingest pdf2 duluan agar jadi duplikat
    client.post(
        "/api/v1/ingest/upload-pdf",
        files=[("files", ("prev.pdf", io.BytesIO(pdf2), "application/pdf"))],
        data={"access_classification": "publik", "document_role": "corpus_eksisting", "title": "Dokumen Pembanding F09"},
    )

    # Batch upload campuran
    batch_files = [
        ("files", ("valid.pdf", io.BytesIO(pdf1), "application/pdf")),
        ("files", ("dup.pdf", io.BytesIO(pdf2), "application/pdf")),
        ("files", ("invalid.txt", io.BytesIO(txt_invalid), "text/plain")),
    ]
    res_batch = client.post(
        "/api/v1/ingest/upload-pdf",
        files=batch_files,
        data={"access_classification": "publik", "document_role": "corpus_eksisting"},
    )
    assert res_batch.status_code == 200
    job_id = res_batch.json()["job_id"]

    # Detail job
    res_job = client.get(f"/api/v1/ingest/jobs/{job_id}")
    assert res_job.status_code == 200
    job_data = res_job.json()
    assert job_data["success_count"] == 1
    assert job_data["duplicate_count"] == 1
    assert job_data["failed_count"] == 1
    assert len(job_data["documents"]) == 1
    assert len(job_data["failures"]) == 2

    dup_failure = next(f for f in job_data["failures"] if f["failure_type"] == "duplikat")
    assert dup_failure["duplicate_of_document"] is not None
    assert dup_failure["duplicate_of_document"]["title"] == "Dokumen Pembanding F09"

    # ID tidak dikenal -> 404
    assert client.get("/api/v1/ingest/jobs/999999").status_code == 404


def test_f10_batch_retry_endpoint(client: TestClient, db_session: Session, test_storage: StorageService):
    """F10: POST /ingest/failures/retry dengan 3 id (1 retryable, 1 non-retryable, 1 tak ada) -> 200 hasil per id."""
    pdf_bytes = make_pdf("Dokumen batch retry F10")
    fp = fingerprint(pdf_bytes)
    quarantine_path = test_storage.save_pdf(pdf_bytes, filename_hint=f"{fp.sha256[:12]}_doc_f10.pdf", subdir="quarantine")

    parent_job = JobIngest(job_type="unggah_manual", status=StatusJobIngest.gagal)
    db_session.add(parent_job)
    db_session.commit()

    f1 = IngestFailure(
        job_id=parent_job.id,
        original_filename="doc_f10.pdf",
        failure_type=JenisKegagalan.kesalahan_internal,
        reason_code="kesalahan_internal",
        message="Retryable",
        is_retryable=True,
        quarantine_path=quarantine_path,
        file_hash=fp.sha256,
        file_size_bytes=fp.size_bytes,
        ingest_options={"access_classification": "publik", "document_role": "corpus_eksisting"},
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    f2 = IngestFailure(
        job_id=parent_job.id,
        original_filename="non_retry.txt",
        failure_type=JenisKegagalan.format_tidak_didukung,
        reason_code="format_tidak_didukung",
        message="Non retryable",
        is_retryable=False,
        quarantine_path=None,
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    db_session.add_all([f1, f2])
    db_session.commit()

    res = client.post(
        "/api/v1/ingest/failures/retry",
        json={"failure_ids": [f1.id, f2.id, 999999]},
    )
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success_count"] == 1
    assert res_data["skipped_count"] >= 1
    assert len(res_data["results"]) == 2  # f1 sukses, f2 skipped


def test_f11_open_failures_metrics(client: TestClient, db_session: Session):
    """F11: GET /ingest/status & GET /ingest/jobs -> open_failures dan open_failures_count benar (duplikat tidak dihitung)."""
    parent_job = JobIngest(job_type="unggah_manual", status=StatusJobIngest.selesai)
    db_session.add(parent_job)
    db_session.commit()

    # Buat dokumen acuan untuk duplikat
    doc = Document(
        title="Dokumen Acuan",
        file_path_pdf="pdf/_inbox/ref.pdf",
        file_hash="dummyhash_f11",
        file_size_bytes=100,
        access_classification="publik",
        document_role="corpus_eksisting",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    # 1 failure belum_ditangani (bukan duplikat)
    f1 = IngestFailure(
        job_id=parent_job.id,
        original_filename="err1.pdf",
        failure_type=JenisKegagalan.kesalahan_internal,
        reason_code="kesalahan_internal",
        message="Error",
        is_retryable=True,
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    # 1 failure duplikat (diabaikan)
    f2 = IngestFailure(
        job_id=parent_job.id,
        original_filename="dup.pdf",
        failure_type=JenisKegagalan.duplikat,
        reason_code="duplikat",
        message="Dup",
        is_retryable=False,
        duplicate_of_document_id=doc.id,
        follow_up_status=StatusTindakLanjut.diabaikan,
    )
    db_session.add_all([f1, f2])
    db_session.commit()

    res_status = client.get("/api/v1/ingest/status")
    assert res_status.status_code == 200
    assert res_status.json()["open_failures"] == 1

    res_jobs = client.get("/api/v1/ingest/jobs")
    assert res_jobs.status_code == 200
    job_item = next(j for j in res_jobs.json()["items"] if j["id"] == parent_job.id)
    assert job_item["open_failures_count"] == 1


def test_f12_quarantine_write_failure_handled_gracefully(client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch):
    """F12: Kegagalan saat menulis karantina (monkeypatch storage) -> Baris kegagalan tetap tercatat, is_retryable=False, batch tetap selesai."""
    pdf_bytes = make_pdf("Dokumen F12 simulasi kegagalan karantina")

    # Kategori tidak ditemukan memicu penulisan karantina
    # Monkeypatch save_pdf hanya untuk subdir='quarantine'
    orig_save = test_storage.save_pdf

    def failing_save_pdf(content, filename_hint, subdir="pdf"):
        if subdir == "quarantine":
            raise IOError("Disk penyimpanan karantina penuh")
        return orig_save(content, filename_hint, subdir)

    monkeypatch.setattr(test_storage, "save_pdf", failing_save_pdf)

    files = [("files", ("doc_f12.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "category_id": "99999",  # Trigger kategori_tidak_ditemukan
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    fail_id = res.json()["details"][0]["failure_id"]
    assert fail_id is not None

    failure = db_session.query(IngestFailure).filter(IngestFailure.id == fail_id).first()
    assert failure is not None
    assert failure.quarantine_path is None
    assert failure.is_retryable is False
    assert "karantina" in failure.message.lower()
