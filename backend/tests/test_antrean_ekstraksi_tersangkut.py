"""
tests/test_antrean_ekstraksi_tersangkut.py
Pengujian penanganan dokumen tersangkut di antrean ekstraksi setelah kehabisan percobaan:
1. Dokumen diterima dengan attempts >= batas diubah menjadi gagal saat claim dipanggil,
   tidak masuk daftar klaim, tercatat IngestFailure dengan alasan percobaan_ekstraksi_habis.
2. Dokumen diproses dengan attempts >= batas dan klaim kedaluwarsa diubah menjadi gagal.
   Dokumen diproses yang klaimnya BELUM kedaluwarsa TIDAK diubah.
3. Dokumen diterima dengan attempts < batas tetap diklaim normal dan attempts bertambah.
4. Pemanggilan claim berulang kali pada kondisi (1) tidak membuat IngestFailure ganda.
5. Requeue pada dokumen dengan attempts >= batas langsung mengubah status menjadi gagal
   dan mencatat kegagalan, sedangkan dengan attempts < batas menjadi diterima.
6. Retry kegagalan dari failure_service mereset extraction_attempts menjadi 0 dan status
   dokumen kembali diterima, sehingga dokumen dapat diklaim lagi oleh worker.
7. Skrip periksa_antrean_ekstraksi.py:
   - dry-run tidak mengubah data;
   - --apply --reset mereset attempts ke 0 dan status diterima;
   - --apply --gagalkan menandai gagal dan mencatat IngestFailure;
   - --apply tanpa salah satu opsi itu menolak;
   - luaran konsol tidak memuat judul dokumen.
8. Dokumen yang tidak aktif (is_active = False) diabaikan oleh klaim, requeue, maupun skrip.
"""
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.document import Document
from app.models.enums import (
    JenisKegagalan,
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
    StatusTindakLanjut,
)
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.services.audit_service import EXTRACTION_FAILED
from app.services.storage_service import StorageService
from scripts.periksa_antrean_ekstraksi import main, run_periksa_antrean_ekstraksi
from tests.conftest import make_pdf

INTERNAL_HEADERS = {"X-Internal-API-Key": settings.internal_api_key}


def _seed_test_doc(
    db_session: Session,
    test_storage: StorageService,
    title: str = "Dokumen Antrean Uji",
    attempts: int = 0,
    status: StatusPemrosesan = StatusPemrosesan.diterima,
    is_active: bool = True,
    claimed_at: Optional[datetime] = None,
    job_id: Optional[int] = None,
) -> Document:
    cat = db_session.query(Category).first()
    uid = uuid.uuid4().hex[:8]
    pdf_bytes = make_pdf(f"Content for {title} {uid}")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint=f"doc_{uid}.pdf", subdir="pdf/_inbox")

    doc = Document(
        title=f"{title} {uid}",
        regulation_number=f"POJK/TEST/{uid}",
        file_path_pdf=rel_path,
        file_hash=f"hash_{uid}",
        file_size_bytes=len(pdf_bytes),
        standardized_filename=f"pojk_{uid}.pdf",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=status,
        extraction_attempts=attempts,
        extraction_claimed_at=claimed_at,
        category_id=cat.id if cat else None,
        job_id=job_id,
        is_active=is_active,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def test_01_stuck_diterima_marked_failed_on_claim(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """1. Dokumen diterima dengan attempts >= batas diubah menjadi gagal saat claim dipanggil, tidak masuk daftar klaim, ada IngestFailure percobaan_ekstraksi_habis."""
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Mentok Percobaan",
        attempts=settings.extraction_max_attempts,
        status=StatusPemrosesan.diterima,
    )

    resp = client.post("/api/v1/internal/extraction/claim?limit=10", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    claimed = resp.json()
    assert all(item["document_id"] != doc.id for item in claimed)

    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.gagal
    assert doc.extraction_claimed_at is None

    # Verifikasi IngestFailure
    failures = (
        db_session.query(IngestFailure)
        .filter(IngestFailure.document_id == doc.id)
        .all()
    )
    assert len(failures) == 1
    fail = failures[0]
    assert fail.failure_type == JenisKegagalan.ekstraksi_gagal
    assert fail.reason_code == "percobaan_ekstraksi_habis"
    assert fail.is_retryable is True
    assert fail.follow_up_status == StatusTindakLanjut.belum_ditangani
    assert str(settings.extraction_max_attempts) in fail.message
    assert "Coba Lagi" in fail.message

    # Verifikasi audit log
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.target_resource == f"document:{doc.id}",
            AuditLog.action == EXTRACTION_FAILED,
        )
        .first()
    )
    assert audit is not None


def test_02_stuck_diproses_claim_expired_marked_failed(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """2. Dokumen diproses dengan attempts >= batas dan klaim kedaluwarsa diubah menjadi gagal. Klaim BELUM kedaluwarsa TIDAK diubah."""
    timeout_mins = settings.extraction_claim_timeout_minutes
    now = datetime.now(timezone.utc)
    expired_time = now - timedelta(minutes=timeout_mins + 5)
    fresh_time = now - timedelta(minutes=2)

    doc_expired = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Klaim Kedaluwarsa",
        attempts=settings.extraction_max_attempts,
        status=StatusPemrosesan.diproses,
        claimed_at=expired_time,
    )
    doc_fresh = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Klaim Masih Aktif",
        attempts=settings.extraction_max_attempts,
        status=StatusPemrosesan.diproses,
        claimed_at=fresh_time,
    )

    resp = client.post("/api/v1/internal/extraction/claim?limit=10", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200

    db_session.refresh(doc_expired)
    db_session.refresh(doc_fresh)

    # doc_expired harus gagal
    assert doc_expired.processing_status == StatusPemrosesan.gagal
    assert doc_expired.extraction_claimed_at is None

    # doc_fresh harus tetap diproses dengan claimed_at tidak berubah
    assert doc_fresh.processing_status == StatusPemrosesan.diproses
    # toleransi perbandingan microsecond bila ada pembulatan DB
    assert abs((doc_fresh.extraction_claimed_at - fresh_time).total_seconds()) < 1.0

    # IngestFailure hanya untuk doc_expired
    fail_expired = (
        db_session.query(IngestFailure)
        .filter(IngestFailure.document_id == doc_expired.id)
        .first()
    )
    assert fail_expired is not None
    assert fail_expired.reason_code == "percobaan_ekstraksi_habis"

    fail_fresh = (
        db_session.query(IngestFailure)
        .filter(IngestFailure.document_id == doc_fresh.id)
        .first()
    )
    assert fail_fresh is None


def test_03_under_limit_claimed_normally(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """3. Dokumen diterima dengan attempts < batas tetap diklaim normal dan attempts bertambah."""
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Normal Di Bawah Batas",
        attempts=1,
        status=StatusPemrosesan.diterima,
    )

    resp = client.post("/api/v1/internal/extraction/claim?limit=10", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    claimed = resp.json()
    claimed_doc = next((item for item in claimed if item["document_id"] == doc.id), None)
    assert claimed_doc is not None
    assert claimed_doc["attempt"] == 2

    db_session.refresh(doc)
    assert doc.processing_status == StatusPemrosesan.diproses
    assert doc.extraction_attempts == 2
    assert doc.extraction_claimed_at is not None

    failures = db_session.query(IngestFailure).filter(IngestFailure.document_id == doc.id).all()
    assert len(failures) == 0


def test_04_no_duplicate_failure_on_repeated_claims(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """4. Pemanggilan claim berulang kali pada kondisi (1) tidak membuat IngestFailure ganda."""
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Klaim Berulang",
        attempts=settings.extraction_max_attempts,
        status=StatusPemrosesan.diterima,
    )

    # Panggilan pertama
    resp1 = client.post("/api/v1/internal/extraction/claim?limit=10", headers=INTERNAL_HEADERS)
    assert resp1.status_code == 200

    # Panggilan kedua
    resp2 = client.post("/api/v1/internal/extraction/claim?limit=10", headers=INTERNAL_HEADERS)
    assert resp2.status_code == 200

    failures = db_session.query(IngestFailure).filter(IngestFailure.document_id == doc.id).all()
    assert len(failures) == 1


def test_05_requeue_at_limit_marked_failed_under_limit_diterima(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """5. Requeue pada dokumen dengan attempts >= batas -> gagal; di bawah batas -> diterima."""
    # Dokumen 1: attempts = batas
    doc_at_limit = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Requeue Batas",
        attempts=settings.extraction_max_attempts,
        status=StatusPemrosesan.diproses,
    )

    # Dokumen 2: attempts < batas
    doc_under_limit = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Requeue Aman",
        attempts=1,
        status=StatusPemrosesan.diproses,
    )

    resp1 = client.post(
        f"/api/v1/internal/extraction/requeue/{doc_at_limit.id}",
        headers=INTERNAL_HEADERS,
    )
    assert resp1.status_code == 200

    resp2 = client.post(
        f"/api/v1/internal/extraction/requeue/{doc_under_limit.id}",
        headers=INTERNAL_HEADERS,
    )
    assert resp2.status_code == 200

    db_session.refresh(doc_at_limit)
    db_session.refresh(doc_under_limit)

    assert doc_at_limit.processing_status == StatusPemrosesan.gagal
    fail1 = db_session.query(IngestFailure).filter(IngestFailure.document_id == doc_at_limit.id).first()
    assert fail1 is not None
    assert fail1.reason_code == "percobaan_ekstraksi_habis"

    assert doc_under_limit.processing_status == StatusPemrosesan.diterima
    assert doc_under_limit.extraction_claimed_at is None
    fail2 = db_session.query(IngestFailure).filter(IngestFailure.document_id == doc_under_limit.id).first()
    assert fail2 is None


def test_06_retry_failure_resets_attempts_to_zero(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """6. Retry kegagalan dari failure_service mereset extraction_attempts menjadi 0 dan status diterima, dokumen bisa diklaim lagi."""
    job = JobIngest(job_type="unggah_manual", status="gagal")
    db_session.add(job)
    db_session.commit()

    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Retry Ulang",
        attempts=settings.extraction_max_attempts,
        status=StatusPemrosesan.gagal,
        job_id=job.id,
    )

    failure = IngestFailure(
        job_id=job.id,
        document_id=doc.id,
        original_filename=doc.standardized_filename or "doc.pdf",
        failure_type=JenisKegagalan.ekstraksi_gagal,
        reason_code="percobaan_ekstraksi_habis",
        message="Ekstraksi dihentikan setelah 3 kali percobaan tanpa hasil.",
        is_retryable=True,
        quarantine_path=doc.file_path_pdf,
        file_hash=doc.file_hash,
        file_size_bytes=doc.file_size_bytes,
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    db_session.add(failure)
    db_session.commit()
    db_session.refresh(failure)

    # Panggil retry endpoint
    resp = client.post(f"/api/v1/ingest/failures/{failure.id}/retry")
    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "requeued"

    db_session.refresh(doc)
    assert doc.extraction_attempts == 0
    assert doc.processing_status == StatusPemrosesan.diterima
    assert doc.extraction_claimed_at is None

    # Sekarang dokumen bisa diklaim ulang oleh worker
    resp_claim = client.post("/api/v1/internal/extraction/claim?limit=10", headers=INTERNAL_HEADERS)
    assert resp_claim.status_code == 200
    claimed = resp_claim.json()
    claimed_item = next((item for item in claimed if item["document_id"] == doc.id), None)
    assert claimed_item is not None
    assert claimed_item["attempt"] == 1


def test_07_script_periksa_antrean_ekstraksi(
    monkeypatch, db_session: Session, test_storage: StorageService, capsys
):
    """7. Skrip periksa_antrean_ekstraksi.py:
    - dry-run tidak mengubah data;
    - --apply --reset mereset attempts ke 0 dan status diterima;
    - --apply --gagalkan menandai gagal dan mencatat IngestFailure;
    - --apply saja ditolak;
    - luaran konsol tidak memuat judul dokumen.
    """
    secret_title = "Rahasia Judul Dokumen Bank XYZ 12345"
    doc1 = _seed_test_doc(
        db_session,
        test_storage,
        title=secret_title,
        attempts=settings.extraction_max_attempts,
        status=StatusPemrosesan.diterima,
    )

    # 7.1 Dry-run
    res_dry = run_periksa_antrean_ekstraksi(db_session, apply=False, document_ids=[doc1.id])
    assert res_dry["total_stuck"] == 1
    assert res_dry["affected_count"] == 0

    db_session.refresh(doc1)
    assert doc1.processing_status == StatusPemrosesan.diterima
    assert doc1.extraction_attempts == settings.extraction_max_attempts

    captured = capsys.readouterr()
    assert secret_title not in captured.out
    assert secret_title not in captured.err

    # 7.2 --apply tanpa --reset/--gagalkan ditolak
    with pytest.raises(ValueError, match="--apply memerlukan salah satu dari --reset atau --gagalkan"):
        run_periksa_antrean_ekstraksi(db_session, apply=True, reset=False, gagalkan=False, document_ids=[doc1.id])

    # 7.3 --apply dengan kedua --reset dan --gagalkan ditolak
    with pytest.raises(ValueError, match="tidak dapat digunakan bersamaan"):
        run_periksa_antrean_ekstraksi(db_session, apply=True, reset=True, gagalkan=True, document_ids=[doc1.id])

    # 7.4 --apply --reset
    res_reset = run_periksa_antrean_ekstraksi(db_session, apply=True, reset=True, document_ids=[doc1.id])
    assert res_reset["affected_count"] == 1

    db_session.refresh(doc1)
    assert doc1.extraction_attempts == 0
    assert doc1.processing_status == StatusPemrosesan.diterima
    assert doc1.extraction_claimed_at is None

    # 7.5 --apply --gagalkan
    doc2 = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Kedua Untuk Gagalkan",
        attempts=settings.extraction_max_attempts,
        status=StatusPemrosesan.diterima,
    )
    res_gagalkan = run_periksa_antrean_ekstraksi(db_session, apply=True, gagalkan=True, document_ids=[doc2.id])
    assert res_gagalkan["affected_count"] == 1

    db_session.refresh(doc2)
    assert doc2.processing_status == StatusPemrosesan.gagal
    fail2 = db_session.query(IngestFailure).filter(IngestFailure.document_id == doc2.id).first()
    assert fail2 is not None
    assert fail2.reason_code == "percobaan_ekstraksi_habis"

    # 7.6 Validasi CLI main() rejection via argparse / sys.exit
    monkeypatch.setattr(sys, "argv", ["periksa_antrean_ekstraksi.py", "--apply"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

    monkeypatch.setattr(sys, "argv", ["periksa_antrean_ekstraksi.py", "--reset", "--gagalkan"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_08_inactive_documents_untouched(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """8. Dokumen nonaktif (is_active = False) tidak disentuh oleh claim, requeue, maupun skrip."""
    doc_inactive = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Nonaktif",
        attempts=settings.extraction_max_attempts,
        status=StatusPemrosesan.diterima,
        is_active=False,
    )

    # 8.1 Claim: dokumen nonaktif tidak disentuh dan tidak diubah menjadi gagal
    resp_claim = client.post("/api/v1/internal/extraction/claim?limit=10", headers=INTERNAL_HEADERS)
    assert resp_claim.status_code == 200

    db_session.refresh(doc_inactive)
    assert doc_inactive.processing_status == StatusPemrosesan.diterima
    assert doc_inactive.is_active is False
    failures_claim = db_session.query(IngestFailure).filter(IngestFailure.document_id == doc_inactive.id).all()
    assert len(failures_claim) == 0

    # 8.2 Requeue: dokumen nonaktif ditolak 404 dan tidak diubah
    resp_requeue = client.post(
        f"/api/v1/internal/extraction/requeue/{doc_inactive.id}",
        headers=INTERNAL_HEADERS,
    )
    assert resp_requeue.status_code == 404
    db_session.refresh(doc_inactive)
    assert doc_inactive.processing_status == StatusPemrosesan.diterima
    failures_requeue = db_session.query(IngestFailure).filter(IngestFailure.document_id == doc_inactive.id).all()
    assert len(failures_requeue) == 0

    # 8.3 Skrip: dokumen nonaktif tidak dideteksi dan tidak diubah
    res_script = run_periksa_antrean_ekstraksi(db_session, apply=True, reset=True, document_ids=[doc_inactive.id])
    assert res_script["total_stuck"] == 0
    assert res_script["affected_count"] == 0

    db_session.refresh(doc_inactive)
    assert doc_inactive.extraction_attempts == settings.extraction_max_attempts
    assert doc_inactive.processing_status == StatusPemrosesan.diterima

