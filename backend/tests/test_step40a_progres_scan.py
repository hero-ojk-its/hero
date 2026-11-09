"""
tests/test_step40a_progres_scan.py
Pengujian progres pemindaian URL (Langkah 40a):
- Hitungan PDF terdeteksi tampil langsung selama pemindaian (status memindai / antrian).
- Saat status siap_dipilih atau selesai, hitungan dihitung dari baris ScanCandidate yang ada.
- candidates_total_live tersaji di ScanSessionResponse.
- Konsistensi pada GET /api/v1/scans/{id} dan GET /api/v1/scans.
"""
import hashlib
import pytest
from sqlalchemy.orm import Session

from app.models.enums import StatusPindai, StatusKandidat, JenisSumber
from app.models.scraping_source import ScrapingSource
from app.models.scan_session import ScanSession
from app.models.scan_candidate import ScanCandidate


@pytest.fixture
def base_source(db_session: Session) -> ScrapingSource:
    source = ScrapingSource(
        name="Sumber Uji Progres Scan",
        source_type=JenisSumber.situs_web,
        url="https://example.com/regulasi",
    )
    db_session.add(source)
    db_session.commit()
    return source


def test_scan_progres_sedang_memindai(client, db_session: Session, base_source: ScrapingSource):
    """
    Sesi dengan status memindai, pages_visited=5, candidates_total=12, belum ada baris ScanCandidate:
    GET /api/v1/scans/{id} mengembalikan pages_visited=5, candidates_summary.total=12, candidates_total_live=12.
    """
    sess = ScanSession(
        source_id=base_source.id,
        start_url="https://example.com/regulasi/memindai",
        status=StatusPindai.memindai,
        pages_visited=5,
        candidates_total=12,
    )
    db_session.add(sess)
    db_session.commit()

    resp = client.get(f"/api/v1/scans/{sess.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "memindai"
    assert data["pages_visited"] == 5
    assert data["candidates_summary"]["total"] == 12
    assert data["candidates_summary"]["baru"] == 0
    assert data["candidates_summary"]["sudah_ada"] == 0
    assert data["candidates_summary"]["mungkin_ada"] == 0
    assert data["candidates_summary"]["terpilih"] == 0
    assert data["candidates_total_live"] == 12


def test_scan_selesai_memindai_dihitung_dari_baris(client, db_session: Session, base_source: ScrapingSource):
    """
    Sesi dengan status siap_dipilih, ada 3 baris candidate, candidates_total=12:
    candidates_summary.total=3 (dari baris, bukan live).
    """
    sess = ScanSession(
        source_id=base_source.id,
        start_url="https://example.com/regulasi/siap",
        status=StatusPindai.siap_dipilih,
        pages_visited=10,
        candidates_total=12,
    )
    db_session.add(sess)
    db_session.flush()

    for i in range(3):
        url = f"https://example.com/regulasi/doc_{i}.pdf"
        cand = ScanCandidate(
            scan_id=sess.id,
            url=url,
            url_hash=hashlib.sha256(url.encode()).hexdigest(),
            filename=f"doc_{i}.pdf",
            match_status=StatusKandidat.baru,
            selected=True,
        )
        db_session.add(cand)
    db_session.commit()

    resp = client.get(f"/api/v1/scans/{sess.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "siap_dipilih"
    assert data["pages_visited"] == 10
    # Dihitung dari baris, bukan live (total = 3)
    assert data["candidates_summary"]["total"] == 3
    assert data["candidates_summary"]["baru"] == 3
    assert data["candidates_summary"]["terpilih"] == 3
    # candidates_total_live tetap mengembalikan nilai candidates_total dari DB
    assert data["candidates_total_live"] == 12


def test_scan_memindai_nol_kandidat(client, db_session: Session, base_source: ScrapingSource):
    """
    Sesi memindai dengan candidates_total=0:
    candidates_summary.total=0 dan candidates_total_live=0.
    """
    sess = ScanSession(
        source_id=base_source.id,
        start_url="https://example.com/regulasi/nol",
        status=StatusPindai.memindai,
        pages_visited=1,
        candidates_total=0,
    )
    db_session.add(sess)
    db_session.commit()

    resp = client.get(f"/api/v1/scans/{sess.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "memindai"
    assert data["pages_visited"] == 1
    assert data["candidates_summary"]["total"] == 0
    assert data["candidates_total_live"] == 0


def test_scan_antrian_dengan_kandidat_live(client, db_session: Session, base_source: ScrapingSource):
    """
    Sesi dengan status antrian dan candidates_total=4 (misalnya resume/re-queued):
    candidates_summary.total=4 dan candidates_total_live=4.
    """
    sess = ScanSession(
        source_id=base_source.id,
        start_url="https://example.com/regulasi/antrian",
        status=StatusPindai.antrian,
        pages_visited=0,
        candidates_total=4,
    )
    db_session.add(sess)
    db_session.commit()

    resp = client.get(f"/api/v1/scans/{sess.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "antrian"
    assert data["candidates_summary"]["total"] == 4
    assert data["candidates_total_live"] == 4


def test_scan_list_endpoint_konsisten(client, db_session: Session, base_source: ScrapingSource):
    """
    Daftar sesi (GET /api/v1/scans) juga konsisten dengan nilai live & baris.
    """
    sess_live = ScanSession(
        source_id=base_source.id,
        start_url="https://example.com/regulasi/list_live",
        status=StatusPindai.memindai,
        pages_visited=3,
        candidates_total=8,
    )
    sess_done = ScanSession(
        source_id=base_source.id,
        start_url="https://example.com/regulasi/list_done",
        status=StatusPindai.selesai,
        pages_visited=7,
        candidates_total=8,
    )
    db_session.add(sess_live)
    db_session.add(sess_done)
    db_session.flush()

    # sess_done memiliki 2 candidate rows
    for i in range(2):
        url = f"https://example.com/regulasi/list_done_{i}.pdf"
        cand = ScanCandidate(
            scan_id=sess_done.id,
            url=url,
            url_hash=hashlib.sha256(url.encode()).hexdigest(),
            filename=f"list_done_{i}.pdf",
            match_status=StatusKandidat.sudah_ada,
            selected=False,
        )
        db_session.add(cand)
    db_session.commit()

    resp = client.get("/api/v1/scans")
    assert resp.status_code == 200
    items = resp.json()["items"]

    item_live = next(item for item in items if item["id"] == sess_live.id)
    item_done = next(item for item in items if item["id"] == sess_done.id)

    assert item_live["candidates_summary"]["total"] == 8
    assert item_live["candidates_total_live"] == 8

    assert item_done["candidates_summary"]["total"] == 2
    assert item_done["candidates_total_live"] == 8

