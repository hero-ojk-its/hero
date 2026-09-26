"""
tests/test_dashboard.py
Pengujian ringkasan dashboard dan audit log filtering (B01 - B03, A01).
"""
from datetime import date, datetime, timezone
import pytest
from sqlalchemy import event

from app.models.document import Document
from app.models.category import Category
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.models.scraping_source import ScrapingSource
from app.models.audit_log import AuditLog
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
    JenisKegagalan,
    StatusTindakLanjut,
    JenisJobIngest,
    StatusJobIngest,
)


def test_b01_dashboard_empty_db(client):
    """B01: GET /dashboard/summary pada database bersih -> enum lengkap bernilai 0, target_met=False."""
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()

    assert data["kb"]["corpus_documents"] == 0
    assert data["kb"]["draft_documents"] == 0
    assert data["kb"]["target_fase1"] == 20
    assert data["kb"]["target_met"] is False

    # Semua enum status_keberlakuan ada
    for st in ["berlaku", "diubah", "dicabut", "tidak_diketahui"]:
        assert st in data["kb"]["by_status_keberlakuan"]
        assert data["kb"]["by_status_keberlakuan"][st] == 0

    # Semua enum by_processing_status ada
    for proc in ["diterima", "diproses", "perlu_koreksi", "terindeks", "gagal", "ditolak"]:
        assert proc in data["kb"]["by_processing_status"]
        assert data["kb"]["by_processing_status"][proc] == 0

    assert data["ingest"]["open_failures"] == 0
    assert data["ingest"]["needs_review"] == 0
    assert data["sources"]["total"] == 0


def test_b02_dashboard_populated_metrics(client, db_session):
    """B02: 21 corpus (2 dicabut, 19 berlaku), 1 draft, 1 kegagalan terbuka -> target_met=True."""
    # 1. 21 Dokumen corpus
    for i in range(1, 22):
        keb = StatusKeberlakuan.dicabut if i <= 2 else StatusKeberlakuan.berlaku
        doc = Document(
            title=f"Corpus Doc {i}",
            regulation_number=f"{i}/POJK/2023",
            regulation_type="POJK",
            release_date=date(2023, 1, 1),
            file_path_pdf=f"kb/POJK/2023/doc_{i}.pdf",
            file_hash=f"hash_dash_{i}",
            file_size_bytes=1000,
            access_classification=KlasifikasiAkses.publik,
            document_role=PeranDokumen.corpus_eksisting,
            status_keberlakuan=keb,
            processing_status=StatusPemrosesan.terindeks,
        )
        db_session.add(doc)

    # 2. 1 Dokumen draft
    draft_doc = Document(
        title="Draft Kajian Keuangan",
        file_path_pdf="kb/Draft Kajian/2023/draft_1.pdf",
        file_hash="hash_dash_draft",
        file_size_bytes=2000,
        access_classification=KlasifikasiAkses.non_publik,
        document_role=PeranDokumen.draft_kajian,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
        processing_status=StatusPemrosesan.terindeks,
    )
    db_session.add(draft_doc)

    # 3. 1 Job Ingest & 1 IngestFailure terbuka
    job = JobIngest(
        job_type=JenisJobIngest.unggah_manual,
        triggered_by="admin",
        status=StatusJobIngest.selesai,
        success_count=21,
        duplicate_count=0,
        failed_count=1,
    )
    db_session.add(job)
    db_session.flush()

    failure = IngestFailure(
        job_id=job.id,
        original_filename="corrupt.pdf",
        failure_type=JenisKegagalan.format_tidak_didukung,
        reason_code="format_tidak_didukung",
        message="Format berkas tidak didukung",
        is_retryable=False,
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    db_session.add(failure)
    db_session.commit()

    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()

    assert data["kb"]["corpus_documents"] == 21
    assert data["kb"]["draft_documents"] == 1
    assert data["kb"]["target_met"] is True
    assert data["kb"]["by_status_keberlakuan"]["dicabut"] == 2
    assert data["kb"]["by_status_keberlakuan"]["berlaku"] == 19
    assert data["ingest"]["open_failures"] == 1
    assert len(data["ingest"]["recent_jobs"]) == 1


def test_b03_dashboard_sql_query_count(client, db_session):
    """B03: Jumlah query SQL dashboard <= 10."""
    query_count = 0

    def count_queries(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count_queries)
    try:
        resp = client.get("/api/v1/dashboard/summary")
        assert resp.status_code == 200
        assert query_count <= 10, f"Query SQL dashboard terlalu banyak: {query_count} (harus <= 10)"
    finally:
        event.remove(engine, "before_cursor_execute", count_queries)


def test_a01_audit_log_target_resource_filter(client, db_session):
    """A01: GET /audit-logs/?target_resource=document:12 hanya menampilkan log resource tersebut dan memuat detail."""
    log1 = AuditLog(
        action="UPDATE_METADATA",
        target_resource="document:12",
        detail={"before": {"title": "Lama"}, "after": {"title": "Baru"}},
    )
    log2 = AuditLog(
        action="OPEN_PDF",
        target_resource="document:12",
        detail=None,
    )
    log3 = AuditLog(
        action="LOGIN",
        target_resource="user:99",
        detail=None,
    )
    db_session.add_all([log1, log2, log3])
    db_session.commit()

    resp = client.get("/api/v1/audit-logs/?target_resource=document:12")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    for item in items:
        assert item["target_resource"].startswith("document:12")

    update_log = next(i for i in items if i["action"] == "UPDATE_METADATA")
    assert update_log["detail"] == {"before": {"title": "Lama"}, "after": {"title": "Baru"}}
