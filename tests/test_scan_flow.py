"""
tests/test_scan_flow.py
Pengujian alur lengkap pemindaian situs: Scan -> Bandingkan -> Centang -> Tarik (K05-K13, K16, K20).
"""
import io
import time
import zipfile
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import Document
from app.models.enums import (
    JenisSumber,
    StatusPindai,
    StatusKandidat,
    TujuanTarik,
    StatusPemrosesan,
    KlasifikasiAkses,
    PeranDokumen,
    JenisJobIngest,
    StatusJobIngest,
    StatusKeberlakuan,
)
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.models.scan_session import ScanSession
from app.models.scan_candidate import ScanCandidate
from app.models.scraping_source import ScrapingSource
from app.services.file_validation import fingerprint
from app.services.failure_service import FailureService
from app.services.scan_service import recover_stuck_scan_sessions
from tests.conftest import make_pdf
from tests.test_crawler_simple import mock_http_server


@pytest.fixture
def scan_source(client, mock_http_server) -> int:
    """Fixture untuk membuat ScrapingSource situs_web terhubung ke mock HTTP server."""
    base_url, _ = mock_http_server
    resp = client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "Sumber Regulasi Uji",
            "url": f"{base_url}/regulasi/index.html",
            "source_type": "situs_web",
            "crawl_depth": 1,
            "default_access_classification": "publik",
            "default_document_role": "corpus_eksisting",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_k05_k06_kb_comparison_and_patch_selection(client, db_session: Session, scan_source: int, mock_http_server, monkeypatch):
    """
    K05: Perbandingan KB:
    - doc a sudah ada via source_url -> sudah_ada (url_sama), selected=False
    - doc b nama & ukuran sama tapi URL beda -> mungkin_ada (nama_dan_ukuran_sama), selected=False
    - lainnya -> baru, selected=True
    K06: PATCH selection mencentang a (sudah_ada) -> a ada di rejected_ids dan tidak tercentang.
    """
    base_url, _ = mock_http_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    # 1. Masukkan doc a ke KB dengan source_url sama
    content_a = make_pdf("Unique PDF Content for a.pdf")
    fp_a = fingerprint(content_a)
    doc_a = Document(
        title="Peraturan A Eksisting",
        source_url=f"{base_url}/regulasi/a.pdf",
        original_filename="a.pdf",
        file_path_pdf="kb/a.pdf",
        file_hash=fp_a.sha256,
        file_size_bytes=fp_a.size_bytes,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.diterima,
        status_keberlakuan=StatusKeberlakuan.berlaku,
    )
    db_session.add(doc_a)

    # 2. Masukkan doc b ke KB dengan ukuran sama & original_filename 'b.pdf', tapi URL beda
    content_b = make_pdf("Unique PDF Content for b.pdf")
    fp_b = fingerprint(content_b)
    doc_b = Document(
        title="Peraturan B Dari Sumber Lain",
        source_url="http://external-other-site.com/old_b.pdf",
        original_filename="b.pdf",
        file_path_pdf="kb/b.pdf",
        file_hash=fp_b.sha256,
        file_size_bytes=fp_b.size_bytes,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.diterima,
        status_keberlakuan=StatusKeberlakuan.berlaku,
    )
    db_session.add(doc_b)
    db_session.commit()

    # 3. Jalankan scan secara sinkron (wait=true)
    resp_scan = client.post(f"/api/v1/scans/?wait=true", json={"source_id": scan_source, "crawl_depth": 1})
    assert resp_scan.status_code == 200
    scan_data = resp_scan.json()
    scan_id = scan_data["id"]
    assert scan_data["status"] == "siap_dipilih"

    # Verifikasi kandidat
    resp_cands = client.get(f"/api/v1/scans/{scan_id}/candidates")
    assert resp_cands.status_code == 200
    candidates = resp_cands.json()["items"]

    cand_a = next(c for c in candidates if c["filename"] == "a.pdf")
    cand_b = next(c for c in candidates if c["filename"] == "b.pdf")
    cand_c = next(c for c in candidates if c["filename"] == "c.pdf")

    assert cand_a["match_status"] == "sudah_ada"
    assert cand_a["match_reason"] == "url_sama"
    assert cand_a["match_document_id"] == doc_a.id
    assert cand_a["selected"] is False

    assert cand_b["match_status"] == "mungkin_ada"
    assert cand_b["match_reason"] == "nama_dan_ukuran_sama"
    assert cand_b["match_document_id"] == doc_b.id
    assert cand_b["selected"] is False

    assert cand_c["match_status"] == "baru"
    assert cand_c["match_reason"] is None
    assert cand_c["selected"] is True

    # K06: Coba centang cand_a (sudah_ada) -> Harus ditolak di rejected_ids
    patch_resp = client.patch(
        f"/api/v1/scans/{scan_id}/selection",
        json={"action": "set", "candidate_ids": [cand_a["id"], cand_b["id"]], "selected": True},
    )
    assert patch_resp.status_code == 200
    patch_data = patch_resp.json()
    assert len(patch_data["rejected_ids"]) == 1
    assert patch_data["rejected_ids"][0]["id"] == cand_a["id"]

    # Verifikasi ulang bahwa cand_a tetap False, cand_b menjadi True
    resp_cands_after = client.get(f"/api/v1/scans/{scan_id}/candidates")
    c_after_a = next(c for c in resp_cands_after.json()["items"] if c["id"] == cand_a["id"])
    c_after_b = next(c for c in resp_cands_after.json()["items"] if c["id"] == cand_b["id"])
    assert c_after_a["selected"] is False
    assert c_after_b["selected"] is True


def test_k07_pull_to_knowledge_base(client, scan_source: int, mock_http_server, monkeypatch):
    """K07: Tarik kandidat ke knowledge_base menghasilkan Dokumen regulasi baru, Job scraping, dan status selesai."""
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    # 1. Jalankan scan dengan crawl_depth=2 agar menemukan c.pdf, d.pdf (depth 2), dan e.pdf
    resp_scan = client.post(f"/api/v1/scans/?wait=true", json={"source_id": scan_source, "crawl_depth": 2})
    scan_id = resp_scan.json()["id"]

    # Pilih c.pdf, d.pdf, dan e.pdf untuk ditarik (3 kandidat)
    resp_cands = client.get(f"/api/v1/scans/{scan_id}/candidates")
    cands = resp_cands.json()["items"]
    target_ids = [c["id"] for c in cands if c["filename"] in ("c.pdf", "d.pdf", "e.pdf")]

    client.patch(f"/api/v1/scans/{scan_id}/selection", json={"action": "select_none"})
    client.patch(f"/api/v1/scans/{scan_id}/selection", json={"action": "set", "candidate_ids": target_ids, "selected": True})

    # 2. Tarik ke knowledge_base dengan wait=true
    resp_pull = client.post(
        f"/api/v1/scans/{scan_id}/pull?wait=true",
        json={"destination": "knowledge_base"},
    )
    assert resp_pull.status_code == 200
    pull_data = resp_pull.json()
    assert pull_data["status"] == "selesai"
    assert pull_data["pull_job_id"] is not None
    assert pull_data["pull_progress"] is not None
    assert pull_data["pull_progress"]["status"] == "selesai"
    assert pull_data["pull_progress"]["processed_count"] == 3
    assert pull_data["pull_progress"]["progress_percent"] == 100

    # Verifikasi Job Ingest
    resp_job = client.get(f"/api/v1/ingest/jobs/{pull_data['pull_job_id']}")
    assert resp_job.status_code == 200
    job_data = resp_job.json()
    assert job_data["status"] == "selesai"
    assert job_data["success_count"] == 3
    assert job_data["duplicate_count"] == 0
    assert job_data["failed_count"] == 0
    assert job_data["processed_count"] == 3
    assert job_data["progress_percent"] == 100

    # Verifikasi dokumen baru di database
    resp_cands_final = client.get(f"/api/v1/scans/{scan_id}/candidates")
    pulled_c = next(c for c in resp_cands_final.json()["items"] if c["filename"] == "c.pdf")
    pulled_d = next(c for c in resp_cands_final.json()["items"] if c["filename"] == "d.pdf")
    pulled_e = next(c for c in resp_cands_final.json()["items"] if c["filename"] == "e.pdf")

    assert pulled_c["pull_outcome"] in ("success", "berhasil")
    assert pulled_c["document_id"] is not None
    assert pulled_d["pull_outcome"] in ("success", "berhasil")
    assert pulled_d["document_id"] is not None
    assert pulled_e["pull_outcome"] in ("success", "berhasil")
    assert pulled_e["document_id"] is not None

    # Verifikasi detail dokumen
    resp_doc = client.get(f"/api/v1/documents/{pulled_c['document_id']}")
    assert resp_doc.status_code == 200
    doc_json = resp_doc.json()
    assert doc_json["source_url"].endswith("/regulasi/c.pdf")
    assert doc_json["original_filename"] == "c.pdf"

    # Verifikasi status sumber terisi
    resp_src = client.get(f"/api/v1/scraping-sources/{scan_source}")
    src_data = resp_src.json()
    assert src_data["last_run_status"] == "selesai"
    assert "Ditarik" in src_data["last_run_message"]


def test_k08_k09_k10_pull_failures_and_duplicates(client, db_session: Session, scan_source: int, mock_http_server, monkeypatch):
    """
    K08: hilang.pdf (404) -> failed, failure retryable; setelah server menyediakan berkas -> retry -> success.
    K09: besar.pdf -> failed ukuran_melebihi_batas, tidak retryable.
    K10: Konten sama dengan doc yang sudah ada (beda URL) -> pull_outcome=duplicate.
    """
    base_url, server = mock_http_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)
    
    # Set max upload size 15 KB agar besar.pdf (±60 KB) gagal karena ukuran
    from app.config import Settings
    monkeypatch.setattr(Settings, "max_upload_bytes", property(lambda self: 15000))

    # Pra-isi dokumen di KB yang hash-nya sama dengan a2.pdf
    content_a2 = make_pdf("Unique PDF Content for a2.pdf")
    fp_a2 = fingerprint(content_a2)
    doc_dup = Document(
        title="Dokumen Duplikat Lain",
        source_url="http://other-site.com/duplicate_sample.pdf",
        original_filename="duplicate_sample.pdf",
        file_path_pdf="kb/dup.pdf",
        file_hash=fp_a2.sha256,
        file_size_bytes=fp_a2.size_bytes,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.diterima,
        status_keberlakuan=StatusKeberlakuan.berlaku,
    )
    db_session.add(doc_dup)
    db_session.commit()

    # 1. Jalankan scan
    resp_scan = client.post(f"/api/v1/scans/?wait=true", json={"source_id": scan_source, "crawl_depth": 1})
    scan_id = resp_scan.json()["id"]

    # Pilih hilang.pdf, besar.pdf, dan a2.pdf
    resp_cands = client.get(f"/api/v1/scans/{scan_id}/candidates")
    cands = resp_cands.json()["items"]
    target_ids = [c["id"] for c in cands if c["filename"] in ("hilang.pdf", "besar.pdf", "a2.pdf")]

    client.patch(f"/api/v1/scans/{scan_id}/selection", json={"action": "select_none"})
    client.patch(f"/api/v1/scans/{scan_id}/selection", json={"action": "set", "candidate_ids": target_ids, "selected": True})

    # 2. Tarik ke knowledge_base
    resp_pull = client.post(f"/api/v1/scans/{scan_id}/pull?wait=true", json={"destination": "knowledge_base"})
    assert resp_pull.status_code == 200

    resp_cands_final = client.get(f"/api/v1/scans/{scan_id}/candidates")
    cand_hilang = next(c for c in resp_cands_final.json()["items"] if c["filename"] == "hilang.pdf")
    cand_besar = next(c for c in resp_cands_final.json()["items"] if c["filename"] == "besar.pdf")
    cand_a2 = next(c for c in resp_cands_final.json()["items"] if c["filename"] == "a2.pdf")

    # K08: hilang.pdf gagal
    assert cand_hilang["pull_outcome"] in ("failed", "gagal")
    assert cand_hilang["failure_id"] is not None

    # K09: besar.pdf gagal ukuran_melebihi_batas
    assert cand_besar["pull_outcome"] in ("failed", "gagal")
    assert cand_besar["failure_id"] is not None
    failure_besar = db_session.query(IngestFailure).filter(IngestFailure.id == cand_besar["failure_id"]).first()
    assert failure_besar.reason_code == "ukuran_melebihi_batas"
    assert failure_besar.is_retryable is False

    # K10: a2.pdf duplikat
    assert cand_a2["pull_outcome"] in ("duplicate", "duplikat")
    assert cand_a2["document_id"] == doc_dup.id

    # Verifikasi Job Ingest counts untuk K08-K10
    pull_job_id = resp_pull.json()["pull_job_id"]
    resp_job = client.get(f"/api/v1/ingest/jobs/{pull_job_id}")
    assert resp_job.status_code == 200
    job_data = resp_job.json()
    assert job_data["success_count"] == 0
    assert job_data["duplicate_count"] == 1
    assert job_data["failed_count"] == 2
    assert job_data["processed_count"] == 3

    # Verifikasi failure_id hilang.pdf di database
    failure = db_session.query(IngestFailure).filter(IngestFailure.id == cand_hilang["failure_id"]).first()
    assert failure.is_retryable is True
    assert failure.ingest_options.get("fetch_url") is not None

    # Uji retry K08 setelah server menyediakan berkas
    server.serve_hilang_pdf = True
    try:
        resp_retry = client.post(f"/api/v1/ingest/failures/{failure.id}/retry")
        assert resp_retry.status_code == 200
        assert resp_retry.json()["outcome"] == "success"
        assert resp_retry.json()["document_id"] is not None
    finally:
        server.serve_hilang_pdf = False


def test_k11_pull_to_unduh_folder_zip_export(client, scan_source: int, mock_http_server, monkeypatch):
    """K11: Tarik ke unduh_folder -> berkas tersimpan di storage ekspor, GET /download menghasilkan file ZIP valid."""
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    # 1. Scan
    resp_scan = client.post(f"/api/v1/scans/?wait=true", json={"source_id": scan_source, "crawl_depth": 1})
    scan_id = resp_scan.json()["id"]

    # Pilih c.pdf
    resp_cands = client.get(f"/api/v1/scans/{scan_id}/candidates")
    cand_c = next(c for c in resp_cands.json()["items"] if c["filename"] == "c.pdf")
    client.patch(f"/api/v1/scans/{scan_id}/selection", json={"action": "select_none"})
    client.patch(f"/api/v1/scans/{scan_id}/selection", json={"action": "set", "candidate_ids": [cand_c["id"]], "selected": True})

    # 2. Tarik ke unduh_folder
    resp_pull = client.post(f"/api/v1/scans/{scan_id}/pull?wait=true", json={"destination": "unduh_folder"})
    assert resp_pull.status_code == 200

    # Pastikan tidak ada Document baru yang dibuat di database
    resp_cands_final = client.get(f"/api/v1/scans/{scan_id}/candidates")
    c_final = next(c for c in resp_cands_final.json()["items"] if c["filename"] == "c.pdf")
    assert c_final["pull_outcome"] in ("downloaded", "diunduh")
    assert c_final["document_id"] is None
    assert c_final["export_path"] is not None

    # Verifikasi Job Ingest count untuk unduh_folder
    resp_job = client.get(f"/api/v1/ingest/jobs/{resp_pull.json()['pull_job_id']}")
    assert resp_job.status_code == 200
    assert resp_job.json()["success_count"] == 1
    assert resp_job.json()["processed_count"] == 1

    # 3. Unduh ZIP
    resp_zip = client.get(f"/api/v1/scans/{scan_id}/download")
    assert resp_zip.status_code == 200
    assert resp_zip.headers["content-type"] == "application/zip"
    assert f'filename="hero-scan-{scan_id}.zip"' in resp_zip.headers["content-disposition"]

    # Verifikasi isi file ZIP
    zip_bytes = resp_zip.content
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        namelist = zf.namelist()
        assert "c.pdf" in namelist
        c_bytes = zf.read("c.pdf")
        assert len(c_bytes) > 0


def test_k12_k13_conflict_and_validation_errors(client, db_session: Session, scan_source: int, tmp_path, monkeypatch):
    """K12 & K13: 409 pemindaian ganda, pull saat belum siap, download sebelum selesai, sumber folder_lokal ditolak."""
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)

    # 1. K13: Sumber folder_lokal ditolak di POST /scans (422)
    folder_dir = tmp_path / "src_k13"
    folder_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(folder_dir))
    resp_folder = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder K13", "url": str(folder_dir), "source_type": "folder_lokal"},
    )
    folder_src_id = resp_folder.json()["id"]

    resp_scan_folder = client.post("/api/v1/scans/", json={"source_id": folder_src_id})
    assert resp_scan_folder.status_code == 422
    assert "bukan merupakan situs_web" in resp_scan_folder.json()["detail"]

    # 2. K12: POST /scans saat sesi masih aktif (409)
    # Buat sesi langsung di database dengan status 'memindai'
    active_sess = ScanSession(
        source_id=scan_source,
        start_url="http://127.0.0.1:8000/regulasi",
        crawl_depth=1,
        mode="simple_http",
        status=StatusPindai.memindai,
        errors=[],
    )
    db_session.add(active_sess)
    db_session.commit()

    resp_s2 = client.post("/api/v1/scans/", json={"source_id": scan_source})
    assert resp_s2.status_code == 409
    assert str(active_sess.id) in resp_s2.json()["detail"]

    # 3. K12: Pull saat status bukan siap_dipilih (422)
    resp_pull_bad = client.post(f"/api/v1/scans/{active_sess.id}/pull", json={"destination": "knowledge_base"})
    assert resp_pull_bad.status_code == 422

    # 4. K12: Download saat status belum selesai (409)
    resp_dl_fail = client.get(f"/api/v1/scans/{active_sess.id}/download")
    assert resp_dl_fail.status_code in (400, 409)


def test_k16_cancel_scan_session(client, scan_source: int, monkeypatch):
    """K16: Pembatalan sesi pemindaian atau penarikan menghasilkan status dibatalkan tanpa unhandled exception."""
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)

    resp_scan = client.post("/api/v1/scans/", json={"source_id": scan_source})
    scan_id = resp_scan.json()["scan_id"]

    resp_cancel = client.post(f"/api/v1/scans/{scan_id}/cancel")
    assert resp_cancel.status_code == 200
    assert resp_cancel.json()["status"] in ("dibatalkan", "antrian")


def test_k20_recover_stuck_scan_sessions(db_session: Session):
    """K20: Pemulihan sesi pemindaian macet saat startup server."""
    # Buat sesi macet > 60 menit
    old_time = datetime.now(timezone.utc) - timedelta(minutes=90)
    stuck_session = ScanSession(
        start_url="http://example.com/stuck",
        crawl_depth=1,
        mode="simple_http",
        status=StatusPindai.memindai,
        started_at=old_time,
        errors=[],
    )
    db_session.add(stuck_session)
    db_session.commit()

    recovered_count = recover_stuck_scan_sessions(db_session, stuck_minutes=60)
    assert recovered_count >= 1

    db_session.refresh(stuck_session)
    assert stuck_session.status == StatusPindai.gagal
    assert "Dihentikan karena server dimulai ulang." in stuck_session.error_message
