import pytest
from sqlalchemy.orm import Session
from app.models.category import Category
from app.models.document import Document
from app.models.user import User
from app.models.enums import (
    JenisJobIngest,
    KlasifikasiAkses,
    PeranDokumen,
    StatusJobIngest,
)
from app.services.ingest_service import (
    DocumentMetadataInput,
    IngestItem,
    IngestOptions,
    IngestService,
    ItemOutcome,
)
from app.services.storage_service import StorageService
from tests.conftest import make_pdf


def test_ingest_one_success(db_session: Session, test_storage: StorageService):
    """Ingest berkas tunggal berhasil menyimpan data ke DB dan berkas fisik ke storage."""
    # Buat user agar foreign key audit_logs valid
    user = User(username="user_ingest", hashed_password="hashed_password", role="user", is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    service = IngestService(db=db_session, storage=test_storage, max_upload_bytes=10 * 1024 * 1024)
    job = service.start_job(
        job_type=JenisJobIngest.unggah_manual,
        source_ref="uu_ojk_2026.pdf",
        triggered_by="test_user",
    )

    pdf_content = make_pdf("Isi UU OJK 2026")
    item = IngestItem(filename="uu_ojk_2026.pdf", content=pdf_content)
    options = IngestOptions(
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        metadata=DocumentMetadataInput(
            title="Undang-Undang OJK 2026",
            regulation_number="UU-01-2026",
            regulation_type="UU",
        ),
    )

    result = service.ingest_one(job=job, item=item, options=options, actor_user_id=user.id)

    assert result.outcome == ItemOutcome.success
    assert result.document_id is not None
    assert result.file_hash is not None

    # Cek di database
    doc = db_session.query(Document).filter(Document.id == result.document_id).first()
    assert doc is not None
    assert doc.title == "Undang-Undang OJK 2026"
    assert doc.regulation_number == "UU-01-2026"
    assert doc.document_role == PeranDokumen.corpus_eksisting
    assert doc.access_classification == KlasifikasiAkses.publik

    # Cek file fisik ada di storage
    assert test_storage.exists(doc.file_path_pdf) is True


def test_ingest_one_duplicate(db_session: Session, test_storage: StorageService):
    """Ingest berkas duplikat menghasilkan outcome duplicate dan tidak menambah baris baru di DB."""
    service = IngestService(db=db_session, storage=test_storage, max_upload_bytes=10 * 1024 * 1024)
    job = service.start_job(
        job_type=JenisJobIngest.unggah_manual,
        source_ref="uu_dup.pdf",
        triggered_by="test_user",
    )

    pdf_content = make_pdf("Konten Identik Regulasi")
    item1 = IngestItem(filename="uu_dup.pdf", content=pdf_content)
    options = IngestOptions(
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
    )

    res1 = service.ingest_one(job=job, item=item1, options=options)
    assert res1.outcome == ItemOutcome.success

    # Unggah ulang dengan nama berbeda tapi isi dan ukuran identik
    item2 = IngestItem(filename="uu_dup_copy.pdf", content=pdf_content)
    res2 = service.ingest_one(job=job, item=item2, options=options)

    assert res2.outcome == ItemOutcome.duplicate
    assert res2.reason_code == "duplikat"
    assert res2.duplicate_of_document_id == res1.document_id
    assert db_session.query(Document).count() == 1


def test_ingest_cleanup_on_db_error_t25(db_session: Session, test_storage: StorageService, monkeypatch):
    """
    T25: Simulasi exception saat commit DB di ingest_one.
    Outcome failed, reason_code='kesalahan_internal', dan berkas yang sempat disimpan terhapus dari storage.
    """
    service = IngestService(db=db_session, storage=test_storage, max_upload_bytes=10 * 1024 * 1024)
    job = service.start_job(
        job_type=JenisJobIngest.unggah_manual,
        source_ref="uu_fail.pdf",
        triggered_by="test_user",
    )

    pdf_content = make_pdf("Dokumen yang akan gagal commit")
    item = IngestItem(filename="uu_fail.pdf", content=pdf_content)
    options = IngestOptions(
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
    )

    # Monkeypatch db.commit agar melempar RuntimeError
    def fake_commit():
        raise RuntimeError("Simulasi kegagalan koneksi database saat commit")

    monkeypatch.setattr(db_session, "commit", fake_commit)

    result = service.ingest_one(job=job, item=item, options=options)

    assert result.outcome == ItemOutcome.failed
    assert result.reason_code == "kesalahan_internal"

    # Pastikan tidak ada file yang tersisa di storage
    pdf_files = list((test_storage.base_path / "pdf").glob("*.pdf"))
    assert len(pdf_files) == 0


def test_ingest_batch_all_cases(db_session: Session, test_storage: StorageService):
    """Uji ingest_batch memproses item dengan berbagai outcome dan mengupdate status job."""
    service = IngestService(db=db_session, storage=test_storage, max_upload_bytes=10 * 1024 * 1024)

    pdf1 = make_pdf("Dokumen 1")
    pdf2 = make_pdf("Dokumen 2")
    pdf_dup = pdf1  # Identik dengan pdf1

    items = [
        IngestItem(filename="doc1.pdf", content=pdf1),
        IngestItem(filename="doc2.pdf", content=pdf2),
        IngestItem(filename="doc1_copy.pdf", content=pdf_dup),
        IngestItem(filename="invalid.txt", content=b"bukan pdf"),
    ]

    options = IngestOptions(
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.draft_kajian,
    )

    batch_res = service.ingest_batch(
        items=items,
        options=options,
        job_type=JenisJobIngest.unggah_manual,
        source_ref="batch_test",
        triggered_by="tester",
    )

    assert batch_res.success_count == 2
    assert batch_res.duplicate_count == 1
    assert batch_res.failed_count == 1
    assert batch_res.job.status == StatusJobIngest.selesai
