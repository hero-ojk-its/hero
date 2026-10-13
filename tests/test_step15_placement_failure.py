"""
tests/test_step15_placement_failure.py
Pengujian Bug #117: Penempatan Gagal Dijawab 200 -> respons galat, pencatatan antrean kegagalan, dan retry.
Kasus Uji: B01 - B10
"""
from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import Document
from app.models.ingest_failure import IngestFailure
from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
    JenisKegagalan,
    StatusTindakLanjut,
)
from app.services.storage_service import StorageService
from tests.conftest import make_pdf

INTERNAL_HEADERS = {"X-Internal-API-Key": settings.internal_api_key}


def _seed_doc(
    db: Session,
    storage: StorageService,
    title: str = "Dokumen Awal",
    reg_num: str = "01/POJK.03/2026",
    processing_status: StatusPemrosesan = StatusPemrosesan.diproses,
    subdir: str = "pdf/_inbox",
    rel_path: str = None,
) -> Document:
    cat = db.query(Category).filter(Category.name == "POJK").first()
    pdf_bytes = make_pdf(f"Isi {title}")
    if rel_path is None:
        rel_path = storage.save_pdf(pdf_bytes, filename_hint=f"{title.replace(' ', '_').lower()}.pdf", subdir=subdir)

    doc = Document(
        title=title,
        regulation_number=reg_num,
        regulation_type="POJK",
        release_date=date(2026, 1, 1),
        regulation_year=2026,
        file_path_pdf=rel_path,
        file_hash=f"hash_{title.replace(' ', '_').lower()}",
        file_size_bytes=len(pdf_bytes),
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=processing_status,
        category_id=cat.id if cat else None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_b01_patch_extraction_title_too_long(client: TestClient, db_session: Session, test_storage: StorageService):
    """B01: PATCH extraction dengan judul 298 karakter -> 422 menyebut title/judul dan batas 255; dokumen tidak berubah."""
    doc = _seed_doc(db_session, test_storage, title="Judul Dok Asli B01")

    long_title = "A" * 298
    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={"judul": long_title},
    )
    assert resp.status_code == 422
    err_str = str(resp.json()).lower()
    assert ("title" in err_str or "judul" in err_str)
    assert "255" in err_str

    db_session.refresh(doc)
    assert doc.title == "Judul Dok Asli B01"


def test_b02_patch_extraction_valid_move_fails(
    client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch: pytest.MonkeyPatch
):
    """
    B02: PATCH extraction valid, move dipaksa gagal
    -> 422 penempatan_gagal; status perlu_koreksi (bukan diproses); teks dan metadata tersimpan;
       ada IngestFailure dengan document_id dan reason_code=penempatan_gagal; ada audit PLACE_DOCUMENT_FAILED.
    """
    doc = _seed_doc(db_session, test_storage, title="Judul Asli B02", reg_num="02/POJK.03/2026")

    def mock_move_failure(self, rel_src, subdir, filename_hint):
        raise IOError("Disk full atau izin akses ditolak simulasi")

    monkeypatch.setattr(StorageService, "move", mock_move_failure)

    payload = {
        "judul": "POJK Baru Valid B02",
        "nomor_peraturan": "02/POJK.03/2026",
        "jenis_peraturan": "POJK",
        "tanggal_terbit": "2026-02-02",
        "teks_lengkap": "Teks lengkap berhasil diekstrak B02",
    }
    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json=payload,
    )
    assert resp.status_code == 422
    data = resp.json()["detail"]
    assert data["code"] == "penempatan_gagal"
    assert "Disk full atau izin akses ditolak simulasi" in data["message"]
    assert data["processing_status"] == "perlu_koreksi"
    assert "failure_id" in data

    # Verifikasi status dokumen dan data tersimpan
    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.perlu_koreksi
    assert doc.title == "POJK Baru Valid B02"
    assert doc.full_text == "Teks lengkap berhasil diekstrak B02"

    # Verifikasi IngestFailure
    fail = (
        db_session.query(IngestFailure)
        .filter(IngestFailure.document_id == doc.id, IngestFailure.reason_code == "penempatan_gagal")
        .first()
    )
    assert fail is not None
    assert fail.id == data["failure_id"]
    assert fail.failure_type == JenisKegagalan.kesalahan_internal
    assert fail.is_retryable is True
    assert fail.follow_up_status == StatusTindakLanjut.belum_ditangani

    # Verifikasi Audit Log PLACE_DOCUMENT_FAILED
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.target_resource == f"document:{doc.id}", AuditLog.action == "PLACE_DOCUMENT_FAILED")
        .first()
    )
    assert audit is not None
    assert "Disk full" in str(audit.detail)


def test_b03_after_b02_worker_sends_error_payload_no_duplicate_failure(
    client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch: pytest.MonkeyPatch
):
    """
    B03: Setelah B02, worker mengirim payload error (force=true)
    -> Tidak ada IngestFailure kedua; status tetap perlu_koreksi.
    """
    doc = _seed_doc(db_session, test_storage, title="Judul B03", reg_num="03/POJK.03/2026")

    # Picu B02 terlebih dahulu
    def mock_move_failure(self, rel_src, subdir, filename_hint):
        raise IOError("Disk full simulasi B03")

    monkeypatch.setattr(StorageService, "move", mock_move_failure)
    resp_b02 = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={"judul": "POJK B03", "nomor_peraturan": "03/POJK.03/2026", "teks_lengkap": "Teks B03"},
    )
    assert resp_b02.status_code == 422
    b02_failure_id = resp_b02.json()["detail"]["failure_id"]

    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.perlu_koreksi

    # Worker kirim error payload dengan force=true
    error_payload = {
        "error": {
            "code": "ekstraksi_gagal",
            "message": "Worker menerima 422 lalu lapor error",
        }
    }
    resp_err = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction?force=true",
        headers=INTERNAL_HEADERS,
        json=error_payload,
    )
    assert resp_err.status_code == 200
    err_data = resp_err.json()
    assert err_data["status"] == "gagal_dicatat"
    assert err_data["failure_id"] == b02_failure_id

    # Verifikasi jumlah IngestFailure di DB tetap 1
    failures = db_session.query(IngestFailure).filter(IngestFailure.document_id == doc.id).all()
    assert len(failures) == 1
    assert failures[0].id == b02_failure_id
    assert "Worker menerima 422 lalu lapor error" in failures[0].message

    # Status tetap perlu_koreksi (tidak menjadi gagal)
    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.perlu_koreksi


def test_b04_retry_b02_failure_when_move_normal(
    client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch: pytest.MonkeyPatch
):
    """
    B04: Proses ulang kegagalan B02 lewat endpoint retry, move sudah normal
    -> Berkas ditempatkan di kb/; kegagalan selesai; status terindeks.
    """
    doc = _seed_doc(db_session, test_storage, title="Judul B04", reg_num="04/POJK.03/2026")

    # 1. Bikin kegagalan penempatan terlebih dahulu
    def mock_move_failure(self, rel_src, subdir, filename_hint):
        raise IOError("Disk full sementara")

    monkeypatch.setattr(StorageService, "move", mock_move_failure)
    resp_b02 = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={"judul": "POJK B04", "nomor_peraturan": "04/POJK.03/2026", "jenis_peraturan": "POJK", "teks_lengkap": "Teks B04"},
    )
    assert resp_b02.status_code == 422
    failure_id = resp_b02.json()["detail"]["failure_id"]

    # 2. Kembalikan storage.move ke kondisi normal (undo monkeypatch)
    monkeypatch.undo()

    # 3. Jalankan retry
    retry_resp = client.post(f"/api/v1/ingest/failures/{failure_id}/retry")
    assert retry_resp.status_code == 200
    res_data = retry_resp.json()
    assert res_data["outcome"] == "success"
    assert res_data["document_id"] == doc.id

    # 4. Verifikasi status dan lokasi berkas
    db_session.refresh(doc)
    assert doc.file_path_pdf.replace("\\", "/").startswith("kb/")
    assert doc.processing_status == StatusPemrosesan.terindeks

    fail = db_session.query(IngestFailure).filter(IngestFailure.id == failure_id).first()
    assert fail.follow_up_status == StatusTindakLanjut.diproses_ulang
    assert fail.resolved_document_id == doc.id


def test_b05_post_place_document_fails_returns_422(
    client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch: pytest.MonkeyPatch
):
    """B05: POST /documents/{id}/place dengan move gagal -> 422 berisi alasan."""
    doc = _seed_doc(db_session, test_storage, title="Judul B05", reg_num="05/POJK.03/2026")

    def mock_move_failure(self, rel_src, subdir, filename_hint):
        raise PermissionError("Akses penyimpanan ditolak simulasi B05")

    monkeypatch.setattr(StorageService, "move", mock_move_failure)

    resp = client.post(f"/api/v1/documents/{doc.id}/place?force=true")
    assert resp.status_code == 422
    data = resp.json()["detail"]
    assert data["code"] == "penempatan_gagal"
    assert "Akses penyimpanan ditolak" in data["message"]


def test_b06_patch_metadata_changing_reg_num_move_fails_rollback(
    client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch: pytest.MonkeyPatch
):
    """
    B06: PATCH /documents/{id}/metadata mengubah regulation_number, move gagal
    -> 422; nomor di DB tidak berubah; file_path_pdf tidak berubah.
    """
    doc = _seed_doc(db_session, test_storage, title="Judul B06", reg_num="06/POJK.03/2026")
    old_path = doc.file_path_pdf
    old_reg_num = doc.regulation_number

    def mock_move_failure(self, rel_src, subdir, filename_hint):
        raise IOError("Gagal move pada metadata patch")

    monkeypatch.setattr(StorageService, "move", mock_move_failure)

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={"regulation_number": "999/POJK.03/2026"},
    )
    assert resp.status_code == 422
    data = resp.json()["detail"]
    assert data["code"] == "penempatan_gagal"

    db_session.refresh(doc)
    assert doc.regulation_number == old_reg_num
    assert doc.file_path_pdf == old_path


def test_b07_regression_patch_extraction_valid_and_move_normal(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """B07: Regresi: PATCH extraction valid dan move normal -> 200 seperti sebelumnya; placement.placed = true."""
    doc = _seed_doc(db_session, test_storage, title="Judul B07", reg_num="07/POJK.03/2026")

    payload = {
        "judul": "POJK 07 Tahun 2026 Normal",
        "nomor_peraturan": "07/POJK.03/2026",
        "jenis_peraturan": "POJK",
        "tanggal_terbit": "2026-07-07",
        "teks_lengkap": "Teks lengkap regulasi B07",
    }
    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "terindeks"
    assert data["placement"]["placed"] is True
    assert data["placement"]["new_path"].replace("\\", "/").startswith("kb/")

    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.terindeks
    assert doc.file_path_pdf.replace("\\", "/").startswith("kb/")


def test_b08_metadata_belum_cukup_returns_200_no_failure(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """B08: metadata_belum_cukup -> Tetap 200; tidak ada IngestFailure."""
    cat = db_session.query(Category).filter(Category.name == "POJK").first()
    pdf_bytes = make_pdf("Isi Dokumen Belum Lengkap")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint="dok_inbox.pdf", subdir="pdf/_inbox")

    doc = Document(
        title="Dokumen Belum Lengkap",
        regulation_number=None,
        regulation_type=None,
        release_date=None,
        regulation_year=None,
        file_path_pdf=rel_path,
        file_hash="hash_dok_inbox",
        file_size_bytes=len(pdf_bytes),
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
        processing_status=StatusPemrosesan.diproses,
        category_id=cat.id if cat else None,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    payload = {
        "teks_lengkap": "Hanya ada teks mentah tanpa nomor",
    }
    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "perlu_koreksi"
    assert data["placement"]["placed"] is False
    assert data["placement"]["reason"] == "metadata_belum_cukup"

    # Tidak ada IngestFailure
    fail_count = db_session.query(IngestFailure).filter(IngestFailure.document_id == doc.id).count()
    assert fail_count == 0


def test_b09_place_pending_with_one_document_failure(
    client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch: pytest.MonkeyPatch
):
    """B09: place-pending dengan satu dokumen gagal -> 200; failed_count = 1 dan id-nya tercantum."""
    # Seed 1 dokumen dengan metadata cukup yang harusnya dipindah
    doc1 = _seed_doc(db_session, test_storage, title="Dokumen Pending 1", reg_num="09/POJK.03/2026")

    # Paksa StorageService.move gagal
    def mock_move_failure(self, rel_src, subdir, filename_hint):
        raise IOError("Simulasi gagal batch move")

    monkeypatch.setattr(StorageService, "move", mock_move_failure)

    resp = client.post("/api/v1/documents/place-pending?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["failed_count"] == 1
    assert data["failed"] == 1

    # ID tercantum di failed_documents dan results
    failed_doc_ids = [d["document_id"] for d in data.get("failed_documents", [])]
    assert doc1.id in failed_doc_ids

    # Dan id tercantum di results
    result_ids = [r["document_id"] for r in data["results"] if r.get("reason", "").startswith("gagal")]
    assert doc1.id in result_ids


def test_b10_update_metadata_title_too_long_returns_422(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """B10: UpdateMetadataIn dengan title 300 karakter -> 422."""
    doc = _seed_doc(db_session, test_storage, title="Judul Awal B10")

    long_title = "Z" * 300
    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={"title": long_title},
    )
    assert resp.status_code == 422
    err_str = str(resp.json()).lower()
    assert ("title" in err_str or "255" in err_str)

    db_session.refresh(doc)
    assert doc.title == "Judul Awal B10"
