"""
tests/test_step26_qa_ingest.py
Pengujian Langkah 26: Validasi PDF rusak/terenkripsi, ekstraksi teks kosong, status belum_berlaku,
judul placeholder, audit IP mask saat auth mati, dan recompute status.
Kasus R01 s.d. R22.
"""
from datetime import date, timedelta
import io
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy.orm import Session

from app.config import settings
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.document_relation import DocumentRelation
from app.models.enums import (
    JenisJobIngest,
    JenisKegagalan,
    JenisRelasi,
    KlasifikasiAkses,
    PeranDokumen,
    StatusJobIngest,
    StatusKeberlakuan,
    StatusPemrosesan,
    StatusTindakLanjut,
)
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.services.failure_service import FailureService
from app.services.file_validation import (
    FileRejectCode,
    FileValidationError,
    validate_pdf,
)
from app.services.version_service import recompute_status
from tests.conftest import make_pdf


def create_valid_pdf(page_count: int = 1) -> bytes:
    """Helper membuat berkas PDF valid dengan pypdf."""
    w = PdfWriter()
    for _ in range(page_count):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def create_empty_pages_pdf() -> bytes:
    """Helper membuat PDF valid tanpa halaman."""
    w = PdfWriter()
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def create_user_encrypted_pdf(user_pass: str = "rahasia", owner_pass: str = "pemilik") -> bytes:
    """Helper membuat PDF terenkripsi dengan user password."""
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.encrypt(user_password=user_pass, owner_password=owner_pass)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def create_owner_encrypted_pdf(owner_pass: str = "pemilik") -> bytes:
    """Helper membuat PDF terenkripsi dengan owner password saja (user pass kosong)."""
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.encrypt(user_password="", owner_password=owner_pass)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


# ============================================================================
# R01 - R05: Unit Test Validasi PDF
# ============================================================================

def test_r01_corrupt_stream_65_bytes():
    """R01: 65 byte PDF rusak melempar FileValidationError pdf_rusak."""
    corrupt_65 = b"%PDF-1.4\n1 0 obj\n<<>>\nstream\nabc"
    with pytest.raises(FileValidationError) as exc_info:
        validate_pdf("batch_05_rusak.pdf", corrupt_65, 10 * 1024 * 1024)

    assert exc_info.value.code == FileRejectCode.pdf_rusak
    assert "PDF rusak atau tidak bisa dibuka" in exc_info.value.message
    assert len(exc_info.value.message) <= 200


def test_r02_valid_pdf_no_pages():
    """R02: PDF valid tanpa halaman melempar pdf_rusak ('tidak memiliki halaman')."""
    empty_pdf = create_empty_pages_pdf()
    with pytest.raises(FileValidationError) as exc_info:
        validate_pdf("tanpa_halaman.pdf", empty_pdf, 10 * 1024 * 1024)

    assert exc_info.value.code == FileRejectCode.pdf_rusak
    assert "tidak memiliki halaman" in exc_info.value.message


def test_r03_user_password_encrypted_pdf():
    """R03: PDF dengan user password melempar pdf_terenkripsi."""
    locked_pdf = create_user_encrypted_pdf()
    with pytest.raises(FileValidationError) as exc_info:
        validate_pdf("terkunci.pdf", locked_pdf, 10 * 1024 * 1024)

    assert exc_info.value.code == FileRejectCode.pdf_terenkripsi
    assert "PDF terenkripsi (butuh kata sandi untuk dibuka)." in exc_info.value.message


def test_r04_owner_password_only_passes_validation():
    """R04: PDF dengan owner password saja (user password kosong) lolos validasi."""
    owner_locked = create_owner_encrypted_pdf()
    # Harus lolos tanpa exception
    validate_pdf("owner_only.pdf", owner_locked, 10 * 1024 * 1024)


def test_r05_valid_one_page_pdf():
    """R05: PDF valid 1 halaman lolos validasi."""
    valid_pdf = create_valid_pdf(1)
    validate_pdf("dokumen_valid.pdf", valid_pdf, 10 * 1024 * 1024)


# ============================================================================
# R06 - R07: Upload Ingest Batch & Password Handling
# ============================================================================

def test_r06_upload_batch_5_files_4_valid_1_corrupt(client: TestClient, db_session: Session):
    """R06: Unggah batch 5 berkas (4 valid + 1 rusak) -> 4 sukses, 1 gagal (pdf_rusak)."""
    corrupt_content = b"%PDF-1.4\n1 0 obj\n<<>>\nstream\nabc"

    files = [
        ("files", ("dok1.pdf", make_pdf("dokumen 1 konten unik"), "application/pdf")),
        ("files", ("dok2.pdf", make_pdf("dokumen 2 konten unik"), "application/pdf")),
        ("files", ("dok3.pdf", make_pdf("dokumen 3 konten unik"), "application/pdf")),
        ("files", ("dok4.pdf", make_pdf("dokumen 4 konten unik"), "application/pdf")),
        ("files", ("dok_rusak.pdf", corrupt_content, "application/pdf")),
    ]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    resp = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert resp.status_code == 200, resp.text
    res = resp.json()

    assert res["success_count"] == 4
    assert res["failed_count"] == 1
    job_id = res["job_id"]

    # Periksa antrean kegagalan memuat 1 entri pdf_rusak
    fail_resp = client.get(f"/api/v1/ingest/failures?job_id={job_id}")
    assert fail_resp.status_code == 200
    fails = fail_resp.json()["items"]
    assert len(fails) == 1
    assert fails[0]["reason_code"] == "pdf_rusak"
    assert fails[0]["failure_type"] == "format_tidak_didukung"


def test_r07_upload_user_password_encrypted(client: TestClient, db_session: Session):
    """R07: Unggah PDF ber-user-password -> gagal, antrean pdf_terenkripsi."""
    locked_content = create_user_encrypted_pdf()
    files = [
        ("files", ("terkunci.pdf", locked_content, "application/pdf")),
    ]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    resp = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["failed_count"] == 1
    job_id = res["job_id"]

    fail_resp = client.get(f"/api/v1/ingest/failures?job_id={job_id}")
    fails = fail_resp.json()["items"]
    assert len(fails) == 1
    assert fails[0]["reason_code"] == "pdf_terenkripsi"
    assert fails[0]["failure_type"] == "format_tidak_didukung"


# ============================================================================
# R08: Fallback failure_service dengan PDF Valid
# ============================================================================

def test_r08_failure_service_fallback_with_valid_pdf(db_session: Session, test_storage):
    """R08: failure_service fallback dengan PDF valid berhasil memeriksa PDF."""
    from collections import namedtuple

    svc = FailureService(db=db_session, storage=test_storage)

    job = JobIngest(
        job_type="unggah_manual",
        triggered_by="system",
        status="selesai",
    )
    db_session.add(job)
    db_session.flush()

    valid_pdf = create_valid_pdf(1)
    ItemMock = namedtuple("ItemMock", ["filename", "content", "source_url"])
    ResultMock = namedtuple("ResultMock", ["reason_code", "message", "duplicate_of_document_id"])
    OptionsMock = namedtuple("OptionsMock", ["access_classification", "document_role", "category_id", "metadata"])

    item = ItemMock(filename="fallback_valid.pdf", content=valid_pdf, source_url=None)
    result = ResultMock(reason_code="alasan_tidak_dikenal_khusus", message="Galat uji", duplicate_of_document_id=None)
    options = OptionsMock(
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        category_id=None,
        metadata=None,
    )

    failure = svc.record_failure(job, item, result, options)
    assert failure is not None
    # Karena PDF valid, fallback harus menetapkan is_valid_pdf=True -> is_retryable=True
    assert failure.is_retryable is True
    assert failure.quarantine_path is not None


# ============================================================================
# R09 - R11: Ekstraksi Teks Kosong & Idempotensi
# ============================================================================

def test_r09_patch_extraction_empty_text_direct(client: TestClient, db_session: Session, test_storage):
    """R09: PATCH ekstraksi, full_text="", teks_langsung -> status gagal, failure teks_kosong, metadata tersimpan, tidak ke kb/."""
    pdf_bytes = make_pdf("Dokumen Awal R09")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint="test09.pdf", subdir="pdf/_inbox")

    doc = Document(
        title="Dokumen Awal",
        regulation_number="POJK-TEST-09",
        regulation_type="POJK",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
        processing_status=StatusPemrosesan.diproses,
        file_path_pdf=rel_path,
        file_hash="hash09",
        file_size_bytes=len(pdf_bytes),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers={"X-Internal-API-Key": settings.internal_api_key},
        json={
            "judul": "POJK 09 Tahun 2026",
            "nomor_peraturan": "09/POJK.03/2026",
            "full_text": "   ",
            "metode_ekstraksi": "teks_langsung",
        },
    )
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["status"] == "gagal_dicatat"

    db_session.expire_all()
    updated_doc = db_session.query(Document).filter(Document.id == doc.id).first()
    assert updated_doc.processing_status == StatusPemrosesan.gagal
    # Metadata payload tetap tersimpan
    assert updated_doc.title == "POJK 09 Tahun 2026"
    assert updated_doc.regulation_number == "09/POJK.03/2026"
    # Tidak dipindah ke kb/
    assert not updated_doc.file_path_pdf.startswith("kb/")

    failure = db_session.query(IngestFailure).filter(IngestFailure.document_id == doc.id).first()
    assert failure is not None
    assert failure.reason_code == "teks_kosong"
    assert failure.failure_type == JenisKegagalan.ekstraksi_gagal
    assert failure.is_retryable is True


def test_r10_patch_extraction_empty_text_ocr(client: TestClient, db_session: Session, test_storage):
    """R10: PATCH ekstraksi, full_text="", metode ocr -> failure ocr_gagal / teks_kosong_ocr."""
    pdf_bytes = make_pdf("Dokumen Awal R10")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint="test10.pdf", subdir="pdf/_inbox")

    doc = Document(
        title="Dokumen OCR",
        regulation_number="POJK-OCR-10",
        regulation_type="POJK",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
        processing_status=StatusPemrosesan.diproses,
        file_path_pdf=rel_path,
        file_hash="hash10",
        file_size_bytes=len(pdf_bytes),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers={"X-Internal-API-Key": settings.internal_api_key},
        json={
            "full_text": "",
            "metode_ekstraksi": "ocr",
        },
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    failure = db_session.query(IngestFailure).filter(IngestFailure.document_id == doc.id).first()
    assert failure is not None
    assert failure.reason_code == "teks_kosong_ocr"
    assert failure.failure_type == JenisKegagalan.ocr_gagal
    assert "OCR tidak menghasilkan teks" in failure.message


def test_r11_patch_extraction_empty_text_twice_force(client: TestClient, db_session: Session, test_storage):
    """R11: PATCH ekstraksi teks kosong dua kali (force=true) -> hanya 1 kegagalan terbuka."""
    pdf_bytes = make_pdf("Dokumen Awal R11")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint="test11.pdf", subdir="pdf/_inbox")

    doc = Document(
        title="Dokumen R11",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
        processing_status=StatusPemrosesan.diproses,
        file_path_pdf=rel_path,
        file_hash="hash11",
        file_size_bytes=len(pdf_bytes),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    # Panggilan pertama
    r1 = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers={"X-Internal-API-Key": settings.internal_api_key},
        json={"full_text": "", "metode_ekstraksi": "teks_langsung"},
    )
    assert r1.status_code == 200

    # Panggilan kedua dengan force=true
    r2 = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction?force=true",
        headers={"X-Internal-API-Key": settings.internal_api_key},
        json={"full_text": "", "metode_ekstraksi": "teks_langsung"},
    )
    assert r2.status_code == 200

    db_session.expire_all()
    open_failures = (
        db_session.query(IngestFailure)
        .filter(
            IngestFailure.document_id == doc.id,
            IngestFailure.follow_up_status == StatusTindakLanjut.belum_ditangani,
        )
        .all()
    )
    assert len(open_failures) == 1


# ============================================================================
# R12 - R15: Aturan Status Keberlakuan & Versioning
# ============================================================================

def test_r12_effective_date_tomorrow_without_relation(db_session: Session):
    """R12: effective_date = besok, tanpa relasi -> belum_berlaku."""
    doc = Document(
        title="POJK Berlaku Besok",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
        processing_status=StatusPemrosesan.terindeks,
        file_path_pdf="kb/test12.pdf",
        file_hash="hash12",
        file_size_bytes=1000,
        effective_date=date.today() + timedelta(days=1),
    )
    db_session.add(doc)
    db_session.commit()

    recompute_status(db_session, doc)
    assert doc.status_keberlakuan == StatusKeberlakuan.belum_berlaku
    assert doc.status_source == "tanggal_berlaku"


def test_r13_effective_date_yesterday(db_session: Session):
    """R13: effective_date = kemarin -> berlaku."""
    doc = Document(
        title="POJK Berlaku Kemarin",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
        processing_status=StatusPemrosesan.terindeks,
        file_path_pdf="kb/test13.pdf",
        file_hash="hash13",
        file_size_bytes=1000,
        effective_date=date.today() - timedelta(days=1),
    )
    db_session.add(doc)
    db_session.commit()

    recompute_status(db_session, doc)
    assert doc.status_keberlakuan == StatusKeberlakuan.berlaku
    assert doc.status_source == "tanggal_berlaku"


def test_r14_effective_date_tomorrow_with_repeal_relation(db_session: Session):
    """R14: effective_date besok + relasi masuk mencabut penuh -> dicabut (relasi menang)."""
    target_key = "POJK|91|2026"
    doc = Document(
        title="POJK 91 2026",
        identity_key=target_key,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
        processing_status=StatusPemrosesan.terindeks,
        file_path_pdf="kb/test14.pdf",
        file_hash="hash14",
        file_size_bytes=1000,
        effective_date=date.today() + timedelta(days=1),
    )
    db_session.add(doc)

    rel = DocumentRelation(
        source_key="POJK|1|2027",
        target_key=target_key,
        relation=JenisRelasi.mencabut,
        partial=False,
    )
    db_session.add(rel)
    db_session.commit()

    recompute_status(db_session, doc)
    assert doc.status_keberlakuan == StatusKeberlakuan.dicabut
    assert doc.status_source == "relasi"


def test_r15_status_source_manual_not_overwritten(db_session: Session):
    """R15: status_source='manual' + effective_date besok -> tidak berubah."""
    doc = Document(
        title="POJK Manual",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        status_source="manual",
        processing_status=StatusPemrosesan.terindeks,
        file_path_pdf="kb/test15.pdf",
        file_hash="hash15",
        file_size_bytes=1000,
        effective_date=date.today() + timedelta(days=1),
    )
    db_session.add(doc)
    db_session.commit()

    changed = recompute_status(db_session, doc)
    assert changed == 0
    assert doc.status_keberlakuan == StatusKeberlakuan.berlaku
    assert doc.status_source == "manual"


# ============================================================================
# R16: Recompute Endpoint
# ============================================================================

def test_r16_recompute_endpoint(client: TestClient, db_session: Session):
    """R16: Dokumen belum_berlaku, tanggal bergeser ke kemarin, POST status/recompute -> berubah jadi berlaku."""
    # 1. Dokumen dibuat dengan status_source tanggal_berlaku dan status belum_berlaku
    doc = Document(
        title="POJK Recompute R16",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.belum_berlaku,
        status_source="tanggal_berlaku",
        processing_status=StatusPemrosesan.terindeks,
        file_path_pdf="kb/test16.pdf",
        file_hash="hash16",
        file_size_bytes=1000,
        effective_date=date.today() - timedelta(days=1),  # sudah tiba
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    # Uji tanpa auth
    r_no_auth = client.post("/api/v1/internal/documents/status/recompute")
    assert r_no_auth.status_code == 401

    # Uji kunci salah
    r_bad_auth = client.post(
        "/api/v1/internal/documents/status/recompute",
        headers={"X-Internal-API-Key": "kunci_ngawur"},
    )
    assert r_bad_auth.status_code == 401

    # Uji dengan kunci valid
    r_ok = client.post(
        "/api/v1/internal/documents/status/recompute",
        headers={"X-Internal-API-Key": settings.internal_api_key},
    )
    assert r_ok.status_code == 200, r_ok.text
    res = r_ok.json()
    assert res["diperiksa"] >= 1
    assert res["berubah"] >= 1

    db_session.expire_all()
    updated = db_session.query(Document).filter(Document.id == doc.id).first()
    assert updated.status_keberlakuan == StatusKeberlakuan.berlaku


# ============================================================================
# R17: Judul Placeholder
# ============================================================================

def test_r17_placeholder_title_ignored(client: TestClient, db_session: Session, test_storage):
    """R17: Judul 'untitled' pada dokumen tanpa judul -> judul tetap kosong, status perlu_koreksi."""
    pdf_bytes = make_pdf("Dokumen Uji R17")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint="test17.pdf", subdir="pdf/_inbox")

    doc = Document(
        title="",
        regulation_number="POJK-R17",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
        processing_status=StatusPemrosesan.diproses,
        file_path_pdf=rel_path,
        file_hash="hash17",
        file_size_bytes=len(pdf_bytes),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers={"X-Internal-API-Key": settings.internal_api_key},
        json={
            "judul": "untitled",
            "full_text": "Isi lengkap peraturan pasal 1 sampai 10...",
            "metode_ekstraksi": "teks_langsung",
        },
    )
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["status"] == "perlu_koreksi"

    db_session.expire_all()
    updated = db_session.query(Document).filter(Document.id == doc.id).first()
    assert updated.title == ""
    assert updated.processing_status == StatusPemrosesan.perlu_koreksi


# ============================================================================
# R18: IP di Audit Log Saat Auth Mati
# ============================================================================

def test_r18_audit_logs_ip_mask_when_auth_disabled(client: TestClient, db_session: Session, monkeypatch):
    """R18: GET /audit-logs/ dengan auth mati -> ip_address null di respons, DB tetap simpan IP."""
    # Pastikan auth_enabled False
    monkeypatch.setattr(settings, "auth_enabled", False)

    log = AuditLog(
        action="LOGIN",
        user_id=None,
        target_resource="system",
        detail={"info": "uji r18"},
        ip_address="192.168.1.100",
    )
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)

    resp = client.get("/api/v1/audit-logs/")
    assert resp.status_code == 200, resp.text
    items = resp.json()

    # Cari entri yang kita buat
    matching = [it for it in items if it["id"] == log.id]
    assert len(matching) == 1
    assert matching[0]["ip_address"] is None

    # DB tetap menyimpan IP asli
    db_session.expire_all()
    db_log = db_session.query(AuditLog).filter(AuditLog.id == log.id).first()
    assert db_log.ip_address == "192.168.1.100"


# ============================================================================
# R19: Dashboard Summary Memuat belum_berlaku
# ============================================================================

def test_r19_dashboard_summary_has_belum_berlaku(client: TestClient):
    """R19: GET /dashboard/summary memuat by_status_keberlakuan.belum_berlaku."""
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "kb" in data
    assert "by_status_keberlakuan" in data["kb"]
    by_sk = data["kb"]["by_status_keberlakuan"]
    assert "belum_berlaku" in by_sk
    assert isinstance(by_sk["belum_berlaku"], int)
    assert by_sk["belum_berlaku"] >= 0


# ============================================================================
# R20: Worker Error Berulang Menandai Dokumen Gagal
# ============================================================================

def test_r20_worker_error_repeated_keeps_status_gagal(client: TestClient, db_session: Session, test_storage):
    """R20: Worker ocr_gagal, requeue, klaim (status diproses), worker ocr_gagal lagi
    -> status gagal; tetap satu kegagalan terbuka; pesan memuat kedua laporan;
       2 entri audit EXTRACTION_FAILED (yang kedua berulang=true).
    """
    pdf_bytes = make_pdf("Dokumen Awal R20")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint="test20.pdf", subdir="pdf/_inbox")

    doc = Document(
        title="Dokumen R20",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
        processing_status=StatusPemrosesan.diproses,
        file_path_pdf=rel_path,
        file_hash="hash20",
        file_size_bytes=len(pdf_bytes),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    # 1. Worker lapor ocr_gagal pertama
    r1 = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers={"X-Internal-API-Key": settings.internal_api_key},
        json={
            "error": {
                "code": "ocr_gagal",
                "message": "Laporan pertama: OCR timeout",
            }
        },
    )
    assert r1.status_code == 200
    res1 = r1.json()
    assert res1["status"] == "gagal_dicatat"
    failure_id_1 = res1["failure_id"]

    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.gagal

    # 2. Requeue dokumen ke diterima
    r_req = client.post(
        f"/api/v1/internal/extraction/requeue/{doc.id}",
        headers={"X-Internal-API-Key": settings.internal_api_key},
    )
    assert r_req.status_code == 200
    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.diterima

    # 3. Worker klaim dokumen (status menjadi diproses)
    r_claim = client.post(
        "/api/v1/internal/extraction/claim?limit=10",
        headers={"X-Internal-API-Key": settings.internal_api_key},
    )
    assert r_claim.status_code == 200
    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.diproses

    # 4. Worker lapor ocr_gagal lagi
    r2 = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers={"X-Internal-API-Key": settings.internal_api_key},
        json={
            "error": {
                "code": "ocr_gagal",
                "message": "Laporan kedua: OCR model OOM",
            }
        },
    )
    assert r2.status_code == 200
    res2 = r2.json()
    assert res2["status"] == "gagal_dicatat"
    assert res2["failure_id"] == failure_id_1

    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.gagal

    # Verifikasi IngestFailure: tetap satu kegagalan terbuka
    open_failures = (
        db_session.query(IngestFailure)
        .filter(
            IngestFailure.document_id == doc.id,
            IngestFailure.follow_up_status == StatusTindakLanjut.belum_ditangani,
        )
        .all()
    )
    assert len(open_failures) == 1
    assert open_failures[0].id == failure_id_1
    assert "Laporan pertama: OCR timeout" in open_failures[0].message
    assert "Laporan kedua: OCR model OOM" in open_failures[0].message

    # Verifikasi jejak audit EXTRACTION_FAILED ada 2 entri
    audits = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.target_resource == f"document:{doc.id}",
            AuditLog.action == "EXTRACTION_FAILED",
        )
        .order_by(AuditLog.id.asc())
        .all()
    )
    assert len(audits) == 2
    assert audits[0].detail.get("failure_id") == failure_id_1
    assert not audits[0].detail.get("berulang")
    assert audits[1].detail.get("failure_id") == failure_id_1
    assert audits[1].detail.get("berulang") is True


# ============================================================================
# R21: Kegagalan Terbuka penempatan_gagal Tetap Mempertahankan perlu_koreksi
# ============================================================================

def test_r21_existing_penempatan_gagal_preserves_perlu_koreksi(client: TestClient, db_session: Session, test_storage):
    """R21: Ada kegagalan terbuka penempatan_gagal dan dokumen perlu_koreksi;
    worker lalu melapor error -> status tetap perlu_koreksi (perilaku lama).
    """
    pdf_bytes = make_pdf("Dokumen Awal R21")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint="test21.pdf", subdir="pdf/_inbox")

    doc = Document(
        title="Dokumen R21",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
        processing_status=StatusPemrosesan.perlu_koreksi,
        file_path_pdf=rel_path,
        file_hash="hash21",
        file_size_bytes=len(pdf_bytes),
    )
    db_session.add(doc)
    db_session.flush()

    job = JobIngest(
        job_type=JenisJobIngest.unggah_manual,
        status=StatusJobIngest.berjalan,
    )
    db_session.add(job)
    db_session.flush()

    fail = IngestFailure(
        job_id=job.id,
        original_filename="test21.pdf",
        failure_type=JenisKegagalan.kesalahan_internal,
        reason_code="penempatan_gagal",
        message="Simulasi disk full saat penempatan",
        is_retryable=True,
        file_hash=doc.file_hash,
        file_size_bytes=doc.file_size_bytes,
        document_id=doc.id,
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    db_session.add(fail)
    db_session.commit()
    db_session.refresh(doc)
    db_session.refresh(fail)

    # Worker melapor error ekstraksi dengan force=true
    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction?force=true",
        headers={"X-Internal-API-Key": settings.internal_api_key},
        json={
            "error": {
                "code": "ekstraksi_gagal",
                "message": "Worker lapor ekstraksi gagal",
            }
        },
    )
    assert resp.status_code == 200
    res = resp.json()
    assert res["status"] == "gagal_dicatat"
    assert res["failure_id"] == fail.id

    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.perlu_koreksi

    db_session.refresh(fail)
    assert "Worker lapor ekstraksi gagal" in fail.message


# ============================================================================
# R22: Teks Kosong Berulang Menandai Dokumen Gagal
# ============================================================================

def test_r22_empty_text_repeated_keeps_status_gagal(client: TestClient, db_session: Session, test_storage):
    """R22: Teks kosong, requeue, klaim, teks kosong lagi
    -> status gagal; satu kegagalan terbuka.
    """
    pdf_bytes = make_pdf("Dokumen Awal R22")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint="test22.pdf", subdir="pdf/_inbox")

    doc = Document(
        title="Dokumen R22",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
        processing_status=StatusPemrosesan.diproses,
        file_path_pdf=rel_path,
        file_hash="hash22",
        file_size_bytes=len(pdf_bytes),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    # 1. Ekstraksi pertama: teks kosong
    r1 = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers={"X-Internal-API-Key": settings.internal_api_key},
        json={"full_text": "", "metode_ekstraksi": "teks_langsung"},
    )
    assert r1.status_code == 200
    res1 = r1.json()
    assert res1["status"] == "gagal_dicatat"
    failure_id_1 = res1["failure_id"]

    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.gagal

    # 2. Requeue
    r_req = client.post(
        f"/api/v1/internal/extraction/requeue/{doc.id}",
        headers={"X-Internal-API-Key": settings.internal_api_key},
    )
    assert r_req.status_code == 200
    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.diterima

    # 3. Klaim
    r_claim = client.post(
        "/api/v1/internal/extraction/claim?limit=10",
        headers={"X-Internal-API-Key": settings.internal_api_key},
    )
    assert r_claim.status_code == 200
    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.diproses

    # 4. Ekstraksi kedua: teks kosong lagi
    r2 = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers={"X-Internal-API-Key": settings.internal_api_key},
        json={"full_text": "   ", "metode_ekstraksi": "teks_langsung"},
    )
    assert r2.status_code == 200
    res2 = r2.json()
    assert res2["status"] == "gagal_dicatat"
    assert res2["failure_id"] == failure_id_1

    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.gagal

    # Verifikasi hanya ada 1 kegagalan terbuka
    open_failures = (
        db_session.query(IngestFailure)
        .filter(
            IngestFailure.document_id == doc.id,
            IngestFailure.follow_up_status == StatusTindakLanjut.belum_ditangani,
        )
        .all()
    )
    assert len(open_failures) == 1
    assert open_failures[0].id == failure_id_1

