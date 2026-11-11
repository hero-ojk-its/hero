"""
tests/test_draft_nonpublik_policy.py
Pengujian Kebijakan Draft Kajian Selalu Non-Publik (Aturan Rapat 10 Nov 2026).
1. Draf yang dikirim 'publik' tersimpan sebagai non_publik.
2. corpus_eksisting + publik tetap tersimpan sebagai publik.
3. Draf non_publik tetap bisa dibuka tanpa login (permissions.py PR #205 dipertahankan).
4. PATCH draf ke publik ditolak (HTTP 422).
5. Jalur retry kegagalan: draft_kajian selalu diproses dan disimpan sebagai non_publik.
"""
import io
from typing import Any
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from pypdf import PdfWriter

from app.config import settings
from app.models.document import Document
from app.models.enums import KlasifikasiAkses, PeranDokumen, JenisJobIngest, StatusJobIngest
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.services.failure_service import FailureService, RetryOverrides
from app.services.ingest_service import IngestService, IngestItem, IngestOptions


@pytest.fixture
def db(db_session: Session):
    return db_session


def make_pdf(text: str = "Dokumen Uji Kebijakan Draft Non Publik") -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_draft_dikirim_publik_tersimpan_non_publik(client: TestClient, db: Session):
    """Setiap dokumen dengan document_role=draft_kajian selalu disimpan access_classification=non_publik."""
    pdf_bytes = make_pdf("Draft Uji Dikirim Publik")
    files = [("files", ("draft_kebijakan.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    data = {
        "access_classification": "publik",  # Klien mengirim publik (misal dari FE)
        "document_role": "draft_kajian",
        "title": "Draft Kajian Uji Kebijakan Non Publik",
    }

    resp = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    doc_id = body["details"][0]["document_id"]

    doc = db.query(Document).filter(Document.id == doc_id).first()
    assert doc is not None
    assert doc.document_role == PeranDokumen.draft_kajian
    assert doc.access_classification == KlasifikasiAkses.non_publik


def test_corpus_eksisting_publik_tetap_publik(client: TestClient, db: Session):
    """Dokumen corpus_eksisting tidak berubah (jika dikirim publik tetap tersimpan publik)."""
    pdf_bytes = make_pdf("Corpus Uji Publik")
    files = [("files", ("corpus_kebijakan.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "title": "POJK Corpus Uji Publik",
    }

    resp = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    doc_id = body["details"][0]["document_id"]

    doc = db.query(Document).filter(Document.id == doc_id).first()
    assert doc is not None
    assert doc.document_role == PeranDokumen.corpus_eksisting
    assert doc.access_classification == KlasifikasiAkses.publik


def test_draft_non_publik_dapat_dibuka_tanpa_login(client: TestClient, db: Session):
    """Draf kajian non-publik tetap bisa dibuka tanpa login (permissions.py)."""
    doc = Document(
        title="Draft Kajian Akses Tanpa Login",
        regulation_number="DRAFT-TEST-NOAUTH-01",
        regulation_type="POJK",
        regulation_year=2026,
        access_classification=KlasifikasiAkses.non_publik,
        document_role=PeranDokumen.draft_kajian,
        file_path_pdf="kb/draft_noauth.pdf",
        file_hash="hash_noauth_01",
        file_size_bytes=512,
        full_text="Isi naskah akademis draf kajian terbuka untuk publikasi tim.",
        is_active=True,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    orig_auth = settings.auth_enabled
    settings.auth_enabled = False
    try:
        resp = client.get(f"/api/v1/documents/{doc.id}/text")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "Isi naskah akademis" in data.get("text", "")
    finally:
        settings.auth_enabled = orig_auth


def test_patch_draft_ke_publik_ditolak(client: TestClient, db: Session):
    """PATCH metadata: draft_kajian tidak boleh diubah menjadi publik (ditolak HTTP 422)."""
    doc = Document(
        title="Draft Kajian Uji Patch",
        regulation_number="DRAFT-PATCH-01",
        regulation_type="POJK",
        regulation_year=2026,
        access_classification=KlasifikasiAkses.non_publik,
        document_role=PeranDokumen.draft_kajian,
        file_path_pdf="kb/draft_patch.pdf",
        file_hash="hash_patch_01",
        file_size_bytes=512,
        is_active=True,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 1. Mencoba ubah access_classification ke publik
    resp1 = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={"access_classification": "publik"},
    )
    assert resp1.status_code == 422, resp1.text
    assert resp1.json().get("detail", {}).get("code") == "draft_publik_tidak_diizinkan"

    # 2. Mencoba ubah access_classification ke publik dengan persetujuan sekalipun
    resp2 = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={
            "access_classification": "publik",
            "persetujuan_publik": {
                "disetujui_oleh": "Pejabat",
                "alasan": "Alasan persetujuan publikasi",
            },
        },
    )
    assert resp2.status_code == 422, resp2.text

    db.refresh(doc)
    assert doc.access_classification == KlasifikasiAkses.non_publik


def test_retry_kegagalan_draft_kajian_selalu_non_publik(db: Session, test_storage: Any):
    """Jalur retry FailureService: draft_kajian selalu disimpan sebagai non_publik walau opsi 'publik'."""
    job = JobIngest(
        job_type=JenisJobIngest.unggah_manual,
        source_ref="test_retry_job",
        status=StatusJobIngest.selesai,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    pdf_bytes = make_pdf("Dokumen Karantina Uji Retry")
    q_path = test_storage.save_pdf(pdf_bytes, filename_hint="q_draft.pdf", subdir="quarantine")

    from app.models.enums import JenisKegagalan

    fail = IngestFailure(
        job_id=job.id,
        original_filename="draft_karantina.pdf",
        quarantine_path=q_path,
        failure_type=JenisKegagalan.kesalahan_internal,
        reason_code="kesalahan_internal",
        message="Gagal diproses sementara",
        is_retryable=True,
        ingest_options={
            "access_classification": "publik",
            "document_role": "draft_kajian",
        },
    )
    db.add(fail)
    db.commit()
    db.refresh(fail)

    fail_svc = FailureService(db=db, storage=test_storage)
    retry_res = fail_svc.retry(
        failure_id=fail.id,
        overrides=RetryOverrides(
            access_classification=KlasifikasiAkses.publik,  # override mencoba meminta publik
            document_role=PeranDokumen.draft_kajian,
        ),
    )

    doc_id = retry_res.item_result.document_id
    doc = db.query(Document).filter(Document.id == doc_id).first()
    assert doc is not None
    assert doc.document_role == PeranDokumen.draft_kajian
    assert doc.access_classification == KlasifikasiAkses.non_publik
