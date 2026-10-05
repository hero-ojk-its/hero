"""
tests/test_scan_locks_12d.py
Pengujian Bug Kunci Pindai/Tarik yang Macet (Langkah 12d - K01-K05):
K01: Tarik dua kali berturut-turut dari sumber yang sama (sesi berbeda) -> keduanya selesai.
K02: Pindai -> tarik -> pindai lagi sumber yang sama -> pemindaian kedua normal.
K03: Kunci sengaja ditahan koneksi lain, lalu tarik -> retry lalu gagal dengan pesan jelas.
K04: Sesi menarik tanpa proses saat startup -> ditandai gagal ("Dihentikan karena server dimulai ulang.").
K05: Setelah operasi selesai -> pg_locks advisory kosong.
"""
from datetime import datetime, timezone
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine
from app.models.enums import (
    StatusPindai,
    StatusJobIngest,
    JenisJobIngest,
    TujuanTarik,
)
from app.models.job_ingest import JobIngest
from app.models.scan_session import ScanSession
from app.models.scan_candidate import ScanCandidate
from app.services.scan_service import recover_stuck_scan_sessions
from tests.test_crawler_simple import mock_http_server


@pytest.fixture
def test_source(client, mock_http_server) -> int:
    """Fixture membuat sumber scraping web uji terhubung ke mock HTTP server."""
    base_url, _ = mock_http_server
    resp = client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "Sumber Uji Lock 12d",
            "url": f"{base_url}/regulasi/index.html",
            "source_type": "situs_web",
            "crawl_depth": 1,
            "default_access_classification": "publik",
            "default_document_role": "corpus_eksisting",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_k01_k02_k05_consecutive_pulls_and_scans(client, test_source: int, mock_http_server, monkeypatch):
    """
    K01: Tarik dua kali berturut-turut dari sumber yang sama (sesi berbeda) -> keduanya selesai.
    K02: Pindai -> tarik -> pindai lagi sumber yang sama -> pemindaian kedua berjalan normal.
    K05: Setelah seluruh operasi pemindaian dan penarikan selesai -> pg_locks advisory kosong.
    """
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    # --- SESI 1: Pindai & Tarik ---
    resp_scan1 = client.post("/api/v1/scans/?wait=true", json={"source_id": test_source, "crawl_depth": 1})
    assert resp_scan1.status_code == 200
    scan1_id = resp_scan1.json()["id"]
    assert resp_scan1.json()["status"] == "siap_dipilih"

    # Tarik berkas sesi 1
    resp_pull1 = client.post(
        f"/api/v1/scans/{scan1_id}/pull?wait=true",
        json={"destination": "unduh_folder"},
    )
    assert resp_pull1.status_code == 200
    assert resp_pull1.json()["status"] == "selesai"
    assert resp_pull1.json().get("error_message") is None

    # --- K02: Pindai lagi sumber yang sama setelah tarik selesai ---
    resp_scan2 = client.post("/api/v1/scans/?wait=true", json={"source_id": test_source, "crawl_depth": 1})
    assert resp_scan2.status_code == 200
    scan2_id = resp_scan2.json()["id"]
    assert resp_scan2.json()["status"] == "siap_dipilih"

    # --- K01: Tarik kedua kalinya berturut-turut dari sumber yang sama (sesi 2) ---
    resp_pull2 = client.post(
        f"/api/v1/scans/{scan2_id}/pull?wait=true",
        json={"destination": "unduh_folder"},
    )
    assert resp_pull2.status_code == 200
    assert resp_pull2.json()["status"] == "selesai"
    assert resp_pull2.json().get("error_message") is None

    # --- K05: Verifikasi pg_locks advisory kosong setelah semua selesai ---
    with engine.connect() as conn:
        locks = conn.execute(text("SELECT locktype, classid, objid, pid FROM pg_locks WHERE locktype='advisory'")).fetchall()
        assert len(locks) == 0, f"Ditemukan advisory lock yang bocor di pg_locks: {locks}"


def test_k03_pull_locked_by_other_connection_retries_and_fails(client, db_session: Session, test_source: int, mock_http_server, monkeypatch):
    """
    K03: Kunci sengaja ditahan koneksi lain, lalu tarik -> Retry, lalu sesi gagal dengan pesan jelas (bukan macet di menarik).
    """
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    # 1. Buat sesi pemindaian siap_dipilih
    resp_scan = client.post("/api/v1/scans/?wait=true", json={"source_id": test_source, "crawl_depth": 1})
    assert resp_scan.status_code == 200
    scan_id = resp_scan.json()["id"]

    # 2. Tahan advisory lock penarikan (1396924751, test_source) menggunakan koneksi dedicated lain
    blocker_conn = engine.connect()
    try:
        acquired = blocker_conn.execute(
            text("SELECT pg_try_advisory_lock(1396924751, :key)"),
            {"key": test_source},
        ).scalar()
        assert acquired is True, "Gagal mengunci advisory lock blocker pada koneksi uji"

        # 3. Jalankan penarikan (harus retry 5x lalu gagal karena terkunci)
        resp_pull = client.post(
            f"/api/v1/scans/{scan_id}/pull?wait=true",
            json={"destination": "unduh_folder"},
        )
        assert resp_pull.status_code == 200
        pull_data = resp_pull.json()

        # Ekspektasi: status gagal dengan pesan jelas, BUKAN macet di menarik
        assert pull_data["status"] == "gagal"
        assert "Proses penarikan sedang diproses oleh eksekusi lain." in (pull_data.get("error_message") or "")

        # Verifikasi job ingest juga berstatus gagal
        if pull_data.get("pull_job_id"):
            job = db_session.query(JobIngest).filter(JobIngest.id == pull_data["pull_job_id"]).first()
            assert job is not None
            assert job.status == StatusJobIngest.gagal

    finally:
        # Lepaskan kunci penahan
        blocker_conn.execute(
            text("SELECT pg_advisory_unlock(1396924751, :key)"),
            {"key": test_source},
        )
        blocker_conn.close()

    # Pastikan pg_locks bersih
    with engine.connect() as conn:
        locks = conn.execute(text("SELECT locktype, classid, objid, pid FROM pg_locks WHERE locktype='advisory'")).fetchall()
        assert len(locks) == 0


def test_k04_stuck_pull_session_recovered_at_startup(db_session: Session):
    """
    K04: Sesi berstatus menarik tanpa proses hidup saat aplikasi start ditandai gagal
    dengan pesan "Dihentikan karena server dimulai ulang."
    """
    # 1. Buat JobIngest berstatus antrian
    job = JobIngest(
        job_type=JenisJobIngest.scraping,
        source_ref="test_k04_ref",
        status=StatusJobIngest.antrian,
    )
    db_session.add(job)
    db_session.flush()

    # 2. Buat ScanSession berstatus menarik (seperti sesi yang tertinggal saat server crash)
    stuck_session = ScanSession(
        start_url="http://example.com/stuck_pull",
        crawl_depth=1,
        mode="simple_http",
        status=StatusPindai.menarik,
        pull_job_id=job.id,
        errors=[],
    )
    db_session.add(stuck_session)
    db_session.commit()

    # 3. Jalankan mekanisme pemulihan startup (is_startup=True)
    recovered_count = recover_stuck_scan_sessions(db_session, stuck_minutes=15, is_startup=True)
    assert recovered_count >= 1

    # 4. Verifikasi sesi dan job ditandai gagal dengan pesan yang tepat
    db_session.refresh(stuck_session)
    db_session.refresh(job)

    assert stuck_session.status == StatusPindai.gagal
    assert stuck_session.error_message == "Dihentikan karena server dimulai ulang."
    assert job.status == StatusJobIngest.gagal
