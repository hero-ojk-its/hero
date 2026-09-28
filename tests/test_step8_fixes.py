"""
tests/test_step8_fixes.py
Pengujian otomatis untuk perbaikan Langkah 8 (R02, R10, R11, R12, R13, R14).
"""
import io
from datetime import date
import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app
from app.models.document import Document
from app.models.enums import KlasifikasiAkses, PeranDokumen, StatusKeberlakuan, StatusPemrosesan, StatusJobIngest
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.models.scan_candidate import ScanCandidate
from app.models.scan_session import ScanSession
from tests.conftest import make_pdf


def test_r02_candidates_pagination_skip_limit_and_page(client, db_session: Session):
    """R02: candidates?skip=0&limit=2 dan ?page=2&limit=2 -> hasil konsisten & total benar."""
    # Buat scan session dengan 5 kandidat
    session = ScanSession(
        start_url="https://example.com/regulasi",
        status="siap_dipilih",
    )
    db_session.add(session)
    db_session.flush()

    for i in range(1, 6):
        c = ScanCandidate(
            scan_id=session.id,
            url=f"https://example.com/doc_{i}.pdf",
            url_hash=f"hash_{i}",
            filename=f"doc_{i}.pdf",
            size_bytes=1000 * i,
            match_status="baru",
            selected=True,
        )
        db_session.add(c)
    db_session.commit()

    # 1. Page 1 via skip=0&limit=2
    res1 = client.get(f"/api/v1/scans/{session.id}/candidates?skip=0&limit=2")
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["total"] == 5
    assert len(d1["items"]) == 2
    assert d1["items"][0]["filename"] == "doc_1.pdf"
    assert d1["items"][1]["filename"] == "doc_2.pdf"

    # 2. Page 2 via skip=2&limit=2
    res2_skip = client.get(f"/api/v1/scans/{session.id}/candidates?skip=2&limit=2")
    assert res2_skip.status_code == 200
    d2_skip = res2_skip.json()
    assert d2_skip["total"] == 5
    assert len(d2_skip["items"]) == 2
    assert d2_skip["items"][0]["filename"] == "doc_3.pdf"

    # 3. Page 2 via page=2&limit=2 (alias kompatibilitas)
    res2_page = client.get(f"/api/v1/scans/{session.id}/candidates?page=2&limit=2")
    assert res2_page.status_code == 200
    d2_page = res2_page.json()
    assert d2_page["total"] == 5
    assert len(d2_page["items"]) == 2
    assert d2_page["items"][0]["filename"] == "doc_3.pdf"
    assert d2_page["items"][1]["filename"] == "doc_4.pdf"


def test_r10_manual_upload_and_pull_job_counts(client, db_session: Session):
    """R10: Job unggah_manual 1 berkas sukses -> success_count=1, processed_count=1."""
    pdf_bytes = make_pdf("Peraturan R10 Manual Upload")
    files = [("files", ("peraturan_r10.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "title": "Peraturan R10",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["success_count"] == 1
    job_id = body["job_id"]

    job = db_session.query(JobIngest).filter(JobIngest.id == job_id).first()
    assert job is not None
    assert job.status == StatusJobIngest.selesai
    assert job.success_count == 1
    assert job.processed_count == 1
    assert job.total_found >= 1


def test_r11_openapi_upload_pdf_binary_format():
    """R11: Skema OpenAPI upload-pdf: item files bertipe berkas (format: binary), bukan sekadar string."""
    openapi_schema = app.openapi()
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    body_schema = schemas.get("Body_upload_pdf_api_v1_ingest_upload_pdf_post", {})
    props = body_schema.get("properties", {})
    files_prop = props.get("files", {})

    assert files_prop.get("type") == "array"
    items = files_prop.get("items", {})
    assert items.get("type") == "string"
    assert items.get("format") == "binary"


def test_r12_failure_original_filename_preservation(client, db_session: Session):
    """R12: Kegagalan untuk 'catatan (v2).md' -> original_filename == 'catatan (v2).md'."""
    md_bytes = b"# Catatan Versi 2\nIsi catatan markdown..."
    files = [("files", ("catatan (v2).md", io.BytesIO(md_bytes), "text/markdown"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    detail = res.json()["details"][0]
    failure_id = detail["failure_id"]

    failure = db_session.query(IngestFailure).filter(IngestFailure.id == failure_id).first()
    assert failure is not None
    assert failure.original_filename == "catatan (v2).md"


def test_r13_dashboard_null_regulation_type_and_year(client, db_session: Session):
    """R13: Dashboard dengan dokumen tanpa jenis/tahun -> jumlah by_regulation_type dan by_year = corpus_documents."""
    # 2 Dokumen lengkap
    d1 = Document(
        title="Dokumen POJK 2023",
        regulation_type="POJK",
        release_date=date(2023, 5, 10),
        file_path_pdf="kb/POJK/2023/d1.pdf",
        file_hash="hash_r13_1",
        file_size_bytes=1000,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.terindeks,
        status_keberlakuan=StatusKeberlakuan.berlaku,
    )
    d2 = Document(
        title="Dokumen UU 2022",
        regulation_type="UU",
        release_date=date(2022, 1, 1),
        file_path_pdf="kb/UU/2022/d2.pdf",
        file_hash="hash_r13_2",
        file_size_bytes=1000,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.terindeks,
        status_keberlakuan=StatusKeberlakuan.berlaku,
    )
    # 2 Dokumen tanpa jenis dan/atau tanpa tanggal
    d3 = Document(
        title="Dokumen Tanpa Jenis 2023",
        regulation_type=None,
        release_date=date(2023, 8, 1),
        file_path_pdf="kb/Lainnya/2023/d3.pdf",
        file_hash="hash_r13_3",
        file_size_bytes=1000,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.terindeks,
        status_keberlakuan=StatusKeberlakuan.berlaku,
    )
    d4 = Document(
        title="Dokumen Tanpa Jenis Dan Tahun",
        regulation_type=None,
        release_date=None,
        file_path_pdf="pdf/_inbox/d4.pdf",
        file_hash="hash_r13_4",
        file_size_bytes=1000,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.diterima,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
    )
    db_session.add_all([d1, d2, d3, d4])
    db_session.commit()

    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    kb = resp.json()["kb"]
    assert kb["corpus_documents"] == 4

    sum_reg_type = sum(item["count"] for item in kb["by_regulation_type"])
    sum_year = sum(item["count"] for item in kb["by_year"])

    assert sum_reg_type == kb["corpus_documents"], f"Total by_regulation_type ({sum_reg_type}) != corpus_documents (4)"
    assert sum_year == kb["corpus_documents"], f"Total by_year ({sum_year}) != corpus_documents (4)"

    # Cek label Belum diketahui
    null_reg = next(item for item in kb["by_regulation_type"] if item["regulation_type"] is None)
    assert null_reg["count"] == 2
    assert null_reg["label"] == "Belum diketahui"

    null_yr = next(item for item in kb["by_year"] if item["year"] is None)
    assert null_yr["count"] == 1
    assert null_yr["label"] == "Belum diketahui"
