"""
tests/test_step38_qa_uat.py
Pengujian untuk temuan QA Hamdan (7 Nov) dan persiapan UAT (Langkah 38):
- Q01: Ingest dokumen dengan status sumber 'dicabut' -> status_source='sumber'; /versi memuat status_keterangan & jumlah_relasi
- Q02: Dokumen status_source='sumber' lalu relasi mencabut disinkron -> status dari relasi, status_source='relasi'
- Q03: Dokumen status_source='manual' -> tidak ditimpa relasi
- Q04: Dokumen status_source='sumber' tanpa relasi saat recompute -> status sumber tetap (tidak jadi 'tidak_diketahui')
- Q05: backfill_status_source.py dry-run lalu --apply -> dry-run tidak mengubah; apply mengisi + audit
- Q06: /versi dokumen tanpa identity_key -> identity_key_kosong: true, jumlah_relasi: 0
- Q07: Unggah manual 26 MB (default) -> ditolak, pesan menyebut 25 MB, tidak ada dokumen dibuat
- Q08: Unduhan scan 26 MB -> diterima (batas fetch 100 MB)
- Q09: Job dengan 1 dokumen yang kemudian dinonaktifkan karena duplikat identitas -> duplikat_identitas_count = 1
- Q10: Unggah PDF rusak -> pesan Indonesia tanpa teks pustaka; label_alasan = "PDF rusak"; is_retryable = false
- Q11: Respons JSON sembarang endpoint -> header charset=utf-8; "—" utuh saat dibaca sebagai bytes UTF-8
- Q12: periksa_konsistensi_pasal.py dengan dokumen diproses kedaluwarsa (attempts habis & belum) + 1 tanpa PDF
- Q13: --antrekan-ulang-macet -> yang ber-PDF jadi diterima, attempts 0, bisa diklaim; yang tanpa PDF tidak diubah
"""

from datetime import datetime, timezone, timedelta
import hashlib
import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.crawlers.base import FetchedFile
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.enums import (
    JenisJobIngest,
    JenisSumber,
    KlasifikasiAkses,
    PeranDokumen,
    StatusJobIngest,
    StatusKeberlakuan,
    StatusPemrosesan,
    StatusPindai,
    TujuanTarik,
)
from app.models.job_ingest import JobIngest
from app.models.scan_candidate import ScanCandidate
from app.models.scan_session import ScanSession
from app.models.scraping_source import ScrapingSource
from app.services.audit_service import (
    EXTRACTION_REQUEUED,
    UPDATE_DOCUMENT_STATUS,
)
from app.services.ingest_service import (
    DocumentMetadataInput,
    IngestItem,
    IngestOptions,
    IngestService,
    ItemOutcome,
)
from app.services.scan_service import ScanService
from app.services.storage_service import StorageService
from app.services.version_service import recompute_status, sync_relations
from scripts.backfill_status_source import backfill_status_source
from scripts.periksa_konsistensi_pasal import periksa_konsistensi_pasal
from tests.conftest import make_pdf, test_engine


@pytest.fixture(autouse=True)
def patch_scan_engine(monkeypatch):
    monkeypatch.setattr("app.services.scan_service.engine", test_engine)
    monkeypatch.setattr(settings, "max_upload_mb", 25)
    monkeypatch.setattr(settings, "max_fetch_mb", 100)


def create_test_doc(**kwargs) -> Document:
    """Helper membuat instance Document valid dengan kolom NOT NULL terisi default."""
    rnd = uuid.uuid4().hex
    data = {
        "title": "Regulasi Uji",
        "document_role": PeranDokumen.corpus_eksisting,
        "access_classification": KlasifikasiAkses.publik,
        "file_path_pdf": f"storage/test_{rnd[:8]}.pdf",
        "file_hash": (rnd * 2)[:64],
        "file_size_bytes": 1024,
        "processing_status": StatusPemrosesan.diterima,
        "status_keberlakuan": StatusKeberlakuan.berlaku,
        "is_active": True,
    }
    data.update(kwargs)
    return Document(**data)


def test_q01_ingest_status_sumber(client: TestClient, db_session: Session, tmp_path: Path):
    """Q01: Ingest dokumen dengan status sumber 'dicabut' -> status_source='sumber'; /versi memuat status_keterangan & jumlah_relasi."""
    storage = StorageService(base_path=str(tmp_path))
    svc = IngestService(db=db_session, storage=storage)

    job = JobIngest(
        job_type=JenisJobIngest.unggah_manual,
        triggered_by="tester",
        source_ref="test_q01.pdf",
        status=StatusJobIngest.berjalan,
        success_count=0,
        duplicate_count=0,
        failed_count=0,
    )
    db_session.add(job)
    db_session.commit()

    content = make_pdf("Regulasi Dicabut")
    item = IngestItem(filename="pojk_10_2024.pdf", content=content)
    meta = DocumentMetadataInput(
        title="POJK 10 2024",
        regulation_number="10",
        regulation_type="POJK",
        status_keberlakuan=StatusKeberlakuan.dicabut,
    )
    opts = IngestOptions(
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        metadata=meta,
    )

    res = svc.ingest_one(job, item, opts)
    assert res.outcome == ItemOutcome.success
    doc_id = res.document_id

    doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert doc is not None
    assert doc.status_keberlakuan == StatusKeberlakuan.dicabut
    assert doc.status_source == "sumber"

    # Isi identity_key kanonik untuk menguji /versi dengan kunci identitas lengkap
    doc.identity_key = "POJK|10|2024"
    db_session.commit()

    # Periksa endpoint /versi
    resp = client.get(f"/api/v1/documents/{doc_id}/versi")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status_keberlakuan"] == "dicabut"
    assert body["status_source"] == "sumber"
    assert body["status_keterangan"] == "Mengikuti status di situs sumber"
    assert body["jumlah_relasi"] == 0
    assert body["identity_key_kosong"] is False


def test_q02_sumber_overridden_by_relation(db_session: Session):
    """Q02: Dokumen status_source='sumber' lalu relasi mencabut disinkron -> status dari relasi, status_source='relasi'."""
    doc = create_test_doc(
        title="POJK 1 2023",
        regulation_type="POJK",
        regulation_number="1",
        regulation_year=2023,
        identity_key="POJK|1|2023",
        status_keberlakuan=StatusKeberlakuan.berlaku,
        status_source="sumber",
    )
    db_session.add(doc)
    db_session.commit()

    # Lapisan data mengirim relasi bahwa POJK 2 2024 mencabut POJK 1 2023
    rel_data = [{
        "src": "POJK|2|2024",
        "dst": "POJK|1|2023",
        "rel": "mencabut",
        "partial": False,
    }]
    res = sync_relations(db_session, rel_data)
    assert res["documents_status_changed"] == 1

    db_session.refresh(doc)
    assert doc.status_keberlakuan == StatusKeberlakuan.dicabut
    assert doc.status_source == "relasi"


def test_q03_manual_not_overwritten(db_session: Session):
    """Q03: Dokumen status_source='manual' -> tidak ditimpa relasi."""
    doc = create_test_doc(
        title="POJK 5 2023",
        regulation_type="POJK",
        regulation_number="5",
        regulation_year=2023,
        identity_key="POJK|5|2023",
        status_keberlakuan=StatusKeberlakuan.berlaku,
        status_source="manual",
    )
    db_session.add(doc)
    db_session.commit()

    # Relasi mencabut
    rel_data = [{
        "src": "POJK|6|2024",
        "dst": "POJK|5|2023",
        "rel": "mencabut",
        "partial": False,
    }]
    sync_relations(db_session, rel_data)

    changed = recompute_status(db_session, [doc])
    assert changed == 0
    assert doc.status_keberlakuan == StatusKeberlakuan.berlaku
    assert doc.status_source == "manual"


def test_q04_sumber_without_relation_stays(db_session: Session):
    """Q04: Dokumen status_source='sumber' tanpa relasi saat recompute -> status sumber tetap (tidak jadi 'tidak_diketahui')."""
    doc = create_test_doc(
        title="POJK 7 2023",
        regulation_type="POJK",
        regulation_number="7",
        regulation_year=2023,
        identity_key="POJK|7|2023",
        status_keberlakuan=StatusKeberlakuan.dicabut,
        status_source="sumber",
    )
    db_session.add(doc)
    db_session.commit()

    # Recompute tanpa relasi di DB
    changed = recompute_status(db_session, [doc])
    assert changed == 0
    assert doc.status_keberlakuan == StatusKeberlakuan.dicabut
    assert doc.status_source == "sumber"


def test_q05_backfill_status_source_dry_run_and_apply(db_session: Session):
    """Q05: backfill_status_source.py dry-run lalu --apply -> dry-run tidak mengubah; apply mengisi + audit."""
    doc = create_test_doc(
        title="POJK 8 2023",
        regulation_type="POJK",
        regulation_number="8",
        regulation_year=2023,
        identity_key="POJK|8|2023",
        status_keberlakuan=StatusKeberlakuan.berlaku,
        status_source=None,  # Belum diisi
    )
    db_session.add(doc)
    db_session.commit()

    # 1. Dry run
    res_dry = backfill_status_source(db_session, apply=False)
    assert res_dry["found_count"] >= 1
    assert res_dry["updated_count"] == 0
    db_session.refresh(doc)
    assert doc.status_source is None

    # 2. Apply
    res_apply = backfill_status_source(db_session, apply=True)
    assert res_apply["updated_count"] >= 1
    db_session.refresh(doc)
    assert doc.status_source == "sumber"

    # Periksa catatan audit log
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == UPDATE_DOCUMENT_STATUS,
            AuditLog.target_resource == f"document:{doc.id}",
        )
        .first()
    )
    assert audit is not None
    assert audit.detail.get("alasan") == "langkah38_backfill_status_source"
    assert audit.detail["after"]["status_source"] == "sumber"


def test_q06_versi_dokumen_tanpa_identity_key(client: TestClient, db_session: Session):
    """Q06: /versi dokumen tanpa identity_key -> identity_key_kosong: true, jumlah_relasi: 0."""
    doc = create_test_doc(
        title="Lampiran Tanpa Kunci Identitas",
        status_keberlakuan=StatusKeberlakuan.berlaku,
        status_source="sumber",
        identity_key=None,
        is_attachment=True,
    )
    db_session.add(doc)
    db_session.commit()

    resp = client.get(f"/api/v1/documents/{doc.id}/versi")
    assert resp.status_code == 200
    body = resp.json()
    assert body["identity_key"] is None
    assert body["identity_key_kosong"] is True
    assert body["jumlah_relasi"] == 0
    assert body["status_keterangan"] == "Mengikuti status di situs sumber"


def test_q07_upload_manual_26mb_rejected(client: TestClient, db_session: Session):
    """Q07: Unggah manual 26 MB (default) -> ditolak, pesan menyebut 25 MB, tidak ada dokumen dibuat."""
    # 26 MB payload
    big_size = 26 * 1024 * 1024
    content = make_pdf("A" * big_size)

    files = [("files", ("manual_besar_26mb.pdf", io.BytesIO(content), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["success_count"] == 0
    assert body["failed_count"] == 1
    assert body["details"][0]["reason_code"] == "ukuran_melebihi_batas"
    assert "25 MB" in body["details"][0]["error"]

    # Pastikan tidak ada dokumen masuk ke database
    count = db_session.query(Document).filter(Document.original_filename == "manual_besar_26mb.pdf").count()
    assert count == 0


def test_q08_unduhan_scan_26mb_accepted(db_session: Session, tmp_path: Path):
    """Q08: Unduhan scan 26 MB -> diterima (batas fetch 100 MB)."""
    storage = StorageService(base_path=str(tmp_path))

    # Sumber & sesi pemindaian
    source = ScrapingSource(
        name="Sumber Tes Scan 26MB",
        source_type=JenisSumber.situs_web,
        url="https://example.com/scan_source_26mb",
    )
    db_session.add(source)
    db_session.flush()

    session = ScanSession(
        source_id=source.id,
        start_url="https://example.com/scan_source_26mb",
        status=StatusPindai.siap_dipilih,
        destination=TujuanTarik.knowledge_base,
    )
    db_session.add(session)
    db_session.flush()

    cand_url = "https://example.com/dokumen_26mb.pdf"
    cand = ScanCandidate(
        scan_id=session.id,
        url=cand_url,
        url_hash=hashlib.sha256(cand_url.encode()).hexdigest(),
        filename="dokumen_26mb.pdf",
        document_title="Regulasi Besar 26MB",
        selected=True,
    )
    db_session.add(cand)
    db_session.commit()

    # 26 MB PDF
    pdf_26mb = make_pdf("B" * (26 * 1024 * 1024))

    # Mock crawler fetch
    mock_crawler = MagicMock()
    mock_crawler.fetch.return_value = FetchedFile(
        filename="dokumen_26mb.pdf",
        content=pdf_26mb,
        content_type="application/pdf",
        final_url="https://example.com/dokumen_26mb.pdf",
    )

    scan_svc = ScanService(db=db_session)
    scan_svc.start_pull(scan_id=session.id, destination=TujuanTarik.knowledge_base)
    with patch("app.services.scan_service.get_storage_service", return_value=storage), \
         patch("app.services.scan_service.get_crawler", return_value=mock_crawler):
        scan_svc.execute_pull(session.id)

    db_session.refresh(cand)
    assert cand.pull_outcome == "berhasil"
    assert cand.document_id is not None

    doc = db_session.query(Document).filter(Document.id == cand.document_id).first()
    assert doc is not None
    assert doc.original_filename == "dokumen_26mb.pdf"


def test_q09_job_duplikat_identitas_count(client: TestClient, db_session: Session):
    """Q09: Job dengan 1 dokumen yang kemudian dinonaktifkan karena duplikat identitas -> duplikat_identitas_count = 1, duplicate_count lama tidak berubah."""
    job = JobIngest(
        job_type=JenisJobIngest.unggah_manual,
        triggered_by="tester",
        source_ref="batch_dedupe.pdf",
        status=StatusJobIngest.selesai,
        success_count=1,
        duplicate_count=0,
        failed_count=0,
    )
    db_session.add(job)
    db_session.flush()

    winner = create_test_doc(
        title="POJK 11 2024 (Pemenang)",
        regulation_type="POJK",
        regulation_number="11",
        regulation_year=2024,
        identity_key="POJK|11|2024",
    )
    db_session.add(winner)
    db_session.flush()

    loser = create_test_doc(
        job_id=job.id,
        title="POJK 11 2024 (Kalah)",
        regulation_type="POJK",
        regulation_number="11",
        regulation_year=2024,
        identity_key="POJK|11|2024",
        is_active=False,
        duplicate_of_id=winner.id,
        deactivated_reason=f"duplikat_identitas: sama dengan dokumen #{winner.id} (POJK|11|2024)",
    )
    db_session.add(loser)
    db_session.commit()

    # Cek detail job
    resp = client.get(f"/api/v1/ingest/jobs/{job.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["duplicate_count"] == 0  # Duplikat berkas lama tetap 0
    assert body["duplikat_identitas_count"] == 1  # Duplikat identitas terhitung 1

    # Cek daftar jobs
    resp_list = client.get("/api/v1/ingest/jobs")
    assert resp_list.status_code == 200
    items = resp_list.json()["items"]
    target_job = next((j for j in items if j["id"] == job.id), None)
    assert target_job is not None
    assert target_job["duplicate_count"] == 0
    assert target_job["duplikat_identitas_count"] == 1


def test_q10_unggah_pdf_rusak(client: TestClient, db_session: Session):
    """Q10: Unggah PDF rusak -> pesan Indonesia tanpa teks pustaka; label_alasan = 'PDF rusak'; is_retryable = false."""
    corrupt_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nstream\nabc"
    files = [("files", ("rusak_stream.pdf", io.BytesIO(corrupt_bytes), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["failed_count"] == 1
    job_id = body["job_id"]

    # Cek pesan galat pada response upload
    fail_detail = body["details"][0]
    assert fail_detail["reason_code"] == "pdf_rusak"
    assert fail_detail["label_alasan"] == "PDF rusak"
    assert "Berkas PDF rusak atau tidak lengkap sehingga tidak bisa dibuka" in fail_detail["error"]
    assert "Stream has ended unexpectedly" not in fail_detail["error"]

    # Cek respons detail job
    job_res = client.get(f"/api/v1/ingest/jobs/{job_id}")
    assert job_res.status_code == 200
    job_body = job_res.json()
    assert len(job_body["failures"]) == 1
    f_sum = job_body["failures"][0]
    assert f_sum["reason_code"] == "pdf_rusak"
    assert f_sum["label_alasan"] == "PDF rusak"
    assert f_sum["is_retryable"] is False

    # Cek endpoint detail kegagalan
    f_res = client.get(f"/api/v1/ingest/failures/{f_sum['id']}")
    assert f_res.status_code == 200
    f_body = f_res.json()
    assert f_body["reason_code"] == "pdf_rusak"
    assert f_body["label_alasan"] == "PDF rusak"
    assert f_body["is_retryable"] is False


def test_q11_charset_utf8_in_responses(client: TestClient, db_session: Session):
    """Q11: Respons JSON sembarang endpoint -> header charset=utf-8; '—' utuh saat dibaca sebagai bytes UTF-8."""
    # 1. Endpoint /health
    res_health = client.get("/health")
    ct_health = res_health.headers.get("content-type", "")
    assert "application/json" in ct_health
    assert "charset=utf-8" in ct_health.lower()

    # 2. Endpoint /documents/{id}/versi yang memuat em-dash '—'
    doc = create_test_doc(
        title="Dokumen Uji Charset — Em Dash",
        status_keberlakuan=StatusKeberlakuan.berlaku,
        status_source="relasi",
        identity_key="POJK|99|2024",
    )
    db_session.add(doc)
    db_session.commit()

    res_versi = client.get(f"/api/v1/documents/{doc.id}/versi")
    ct_versi = res_versi.headers.get("content-type", "")
    assert "application/json" in ct_versi
    assert "charset=utf-8" in ct_versi.lower()

    # Verifikasi em-dash pada catatan respons
    raw_bytes = res_versi.content
    text_decoded = raw_bytes.decode("utf-8")
    assert "—" in text_decoded
    assert "Draft / Rekomendasi —" in text_decoded


def test_q12_periksa_konsistensi_kelompok_d_dry_run(db_session: Session, tmp_path: Path):
    """Q12: periksa_konsistensi_pasal.py dengan dokumen diproses kedaluwarsa (attempts habis & belum) + 1 tanpa PDF -> kelompok D terhitung benar, dry-run tidak mengubah DB."""
    storage = StorageService(base_path=str(tmp_path))
    pdf_rel = storage.save_pdf(make_pdf("Konten D"), "doc_d.pdf", "test_d")

    now = datetime.now(timezone.utc)
    stuck_time = now - timedelta(minutes=60)

    # Doc 1: diproses, claimed lama, attempts habis (>= settings.extraction_max_attempts), ada PDF
    doc1 = create_test_doc(
        title="Doc 1 Attempts Habis",
        file_path_pdf=pdf_rel,
        processing_status=StatusPemrosesan.diproses,
        extraction_claimed_at=stuck_time,
        extraction_attempts=settings.extraction_max_attempts,
    )
    # Doc 2: diproses, claimed lama, attempts belum habis, ada PDF
    doc2 = create_test_doc(
        title="Doc 2 Attempts Belum Habis",
        file_path_pdf=pdf_rel,
        processing_status=StatusPemrosesan.diproses,
        extraction_claimed_at=stuck_time,
        extraction_attempts=1,
    )
    # Doc 3: diproses, claimed lama, tanpa PDF
    doc3 = create_test_doc(
        title="Doc 3 Tanpa PDF",
        file_path_pdf="tidak_ada.pdf",
        processing_status=StatusPemrosesan.diproses,
        extraction_claimed_at=stuck_time,
        extraction_attempts=1,
    )
    db_session.add_all([doc1, doc2, doc3])
    db_session.commit()

    # Dry-run
    res = periksa_konsistensi_pasal(
        db=db_session,
        storage=storage,
        nonaktifkan_tanpa_pdf=False,
        antrekan_ulang_tanpa_pasal=False,
        antrekan_ulang_macet=False,
    )

    assert res["kelompok_d_count"] == 3
    assert res["kelompok_d_never_claimed_count"] == 1
    assert res["d_requeued"] == 0

    # Pastikan DB tidak berubah
    db_session.refresh(doc1)
    db_session.refresh(doc2)
    db_session.refresh(doc3)
    assert doc1.processing_status == StatusPemrosesan.diproses
    assert doc2.processing_status == StatusPemrosesan.diproses
    assert doc3.processing_status == StatusPemrosesan.diproses


def test_q13_antrekan_ulang_macet(client: TestClient, db_session: Session, test_storage: StorageService):
    """Q13: --antrekan-ulang-macet -> yang ber-PDF jadi diterima, attempts 0, bisa diklaim; yang tanpa PDF tidak diubah."""
    pdf_rel = test_storage.save_pdf(make_pdf("Konten D2"), "doc_d2.pdf", "test_d2")

    now = datetime.now(timezone.utc)
    stuck_time = now - timedelta(minutes=60)

    doc1 = create_test_doc(
        title="Doc 1 Ber-PDF",
        file_path_pdf=pdf_rel,
        processing_status=StatusPemrosesan.diproses,
        extraction_claimed_at=stuck_time,
        extraction_attempts=settings.extraction_max_attempts,
    )
    doc2 = create_test_doc(
        title="Doc 2 Ber-PDF",
        file_path_pdf=pdf_rel,
        processing_status=StatusPemrosesan.diproses,
        extraction_claimed_at=stuck_time,
        extraction_attempts=2,
    )
    doc3 = create_test_doc(
        title="Doc 3 Tanpa PDF",
        file_path_pdf="tidak_ada_di_storage.pdf",
        processing_status=StatusPemrosesan.diproses,
        extraction_claimed_at=stuck_time,
        extraction_attempts=settings.extraction_max_attempts,
    )
    db_session.add_all([doc1, doc2, doc3])
    db_session.commit()

    # Eksekusi antrekan ulang
    res = periksa_konsistensi_pasal(
        db=db_session,
        storage=test_storage,
        antrekan_ulang_macet=True,
    )

    assert res["kelompok_d_count"] == 3
    assert res["d_requeued"] == 2
    assert res["kelompok_d_skipped_no_pdf"] == 1

    db_session.refresh(doc1)
    db_session.refresh(doc2)
    db_session.refresh(doc3)

    assert doc1.processing_status == StatusPemrosesan.diterima
    assert doc1.extraction_attempts == 0
    assert doc1.extraction_claimed_at is None

    assert doc2.processing_status == StatusPemrosesan.diterima
    assert doc2.extraction_attempts == 0
    assert doc2.extraction_claimed_at is None

    # Doc 3 tanpa PDF tidak berubah (tetap diproses, percobaan tetap habis)
    assert doc3.processing_status == StatusPemrosesan.diproses
    assert doc3.extraction_attempts == settings.extraction_max_attempts

    # Verifikasi audit log
    audit1 = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == EXTRACTION_REQUEUED,
            AuditLog.target_resource == f"document:{doc1.id}",
        )
        .first()
    )
    assert audit1 is not None
    assert audit1.detail.get("reason") == "antrekan_ulang_macet"
    assert audit1.detail.get("attempt_sebelumnya") == settings.extraction_max_attempts

    # Verifikasi dapat diklaim kembali oleh endpoint internal claim
    # Internal claim butuh internal key
    headers = {"X-Internal-API-Key": settings.internal_api_key}
    claim_resp = client.post("/api/v1/internal/extraction/claim?limit=10", headers=headers)
    assert claim_resp.status_code == 200
    claimed_ids = [d["document_id"] for d in claim_resp.json()]
    assert doc1.id in claimed_ids
    assert doc2.id in claimed_ids
    assert doc3.id not in claimed_ids
