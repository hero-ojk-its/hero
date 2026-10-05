"""HTTP API: each screen's contract, offline."""
from __future__ import annotations

import hashlib
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from hero.pipeline import IngestPipeline
from hero.server.app import create_app


def _wait(client, url, key="status", timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(url).json()
        if body[key]["value"] != "berjalan":
            return body
        time.sleep(0.1)
    raise AssertionError(f"{url} still running")


@pytest.fixture
def seeded(tmp_path, tmp_settings, regulation_pdf):
    pdfs = [regulation_pdf(tmp_path / "a.pdf"),
            regulation_pdf(tmp_path / "b.pdf", nomor=12, tahun=2025,
                           tentang="PERDAGANGAN KARBON MELALUI BURSA KARBON",
                           subjek="Penyelenggara Bursa Karbon", kewajiban="mencatat unit karbon")]
    pipe = IngestPipeline(tmp_settings)
    try:
        assert pipe.run_upload(pdfs).ingested == 2
    finally:
        pipe.close()
    return tmp_settings


@pytest.fixture
def client(seeded):
    with TestClient(create_app(seeded)) as c:
        yield c


def test_kb_list_matches_the_table_contract(client):
    body = client.get("/api/kb/documents", params={"page_size": 8}).json()
    assert body["total"] == 2 and body["pages"] == 1 and body["mode"] == "lexical"
    item = body["items"][0]
    for key in ("id", "judul", "jenis", "nomor_singkat", "kategori", "topik", "tahun", "status", "sumber"):
        assert key in item
    assert item["status"]["tone"] in {"success", "warning", "danger", "info", "neutral"}


def test_kb_multi_value_filters_and_search(client):
    r = client.get("/api/kb/documents", params=[("tahun", 2025), ("tahun", 2026), ("q", "karbon")])
    assert r.json()["total"] == 1


def test_detail_drawer(client):
    doc_id = client.get("/api/kb/documents", params={"q": "karbon"}).json()["items"][0]["id"]
    d = client.get(f"/api/kb/documents/{doc_id}").json()
    assert d["validasi"]["urgensi_harmonisasi"]["tampil"] == "Tinggi (Sanksi Tertulis)"
    assert d["pdf"]["tersedia_lokal"] is True
    assert client.get("/api/kb/documents/tidak-ada").status_code == 404


def test_pdf_is_served_and_its_hash_exposed(client, seeded):
    doc_id = client.get("/api/kb/documents").json()["items"][0]["id"]
    r = client.get(f"/api/kb/documents/{doc_id}/pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF-")
    assert r.headers["x-hero-sha256"] == hashlib.sha256(r.content).hexdigest()


def test_pdf_outside_the_knowledge_base_is_never_served(client, seeded):
    doc_id = client.get("/api/kb/documents").json()["items"][0]["id"]
    with sqlite3.connect(seeded.catalog_db) as conn:
        conn.execute("UPDATE documents SET stored_path = '/etc/hosts', source_ref = 'lokal' "
                     "WHERE doc_id = ?", (doc_id,))
    assert client.get(f"/api/kb/documents/{doc_id}/pdf").status_code == 404


def test_refetched_pdf_must_match_the_recorded_hash(client, seeded, monkeypatch):
    doc_id = client.get("/api/kb/documents").json()["items"][0]["id"]
    with sqlite3.connect(seeded.catalog_db) as conn:
        conn.execute("UPDATE documents SET stored_path = NULL, source_ref = 'https://x/y.pdf' "
                     "WHERE doc_id = ?", (doc_id,))

    class Resp:
        content = b"%PDF-1.4 berbeda"
        def raise_for_status(self): pass

    monkeypatch.setattr("hero.server.app.requests.get", lambda *a, **k: Resp())
    r = client.get(f"/api/kb/documents/{doc_id}/pdf")
    assert r.status_code == 409 and "berbeda" in r.json()["galat"]


def test_enums_and_facets_feed_the_dropdowns(client):
    e = client.get("/api/meta/enums").json()
    assert {x["label"] for x in e["status_kbs"]} >= {"Baru", "Sudah Ada", "Duplikat"}
    f = client.get("/api/kb/facets").json()
    assert set(f) >= {"kategori", "jenis", "tahun", "topik", "status", "sumber"}


def test_jdih_scan_without_sector_is_rejected_as_bad_input(client):
    r = client.post("/api/ingest/scans", json={"url": "https://jdih.ojk.go.id/x"})
    assert r.status_code == 422


def test_folder_sync_flow_end_to_end(client, tmp_path, regulation_pdf, seeded):
    folder = tmp_path / "onedrive-sinkron"
    folder.mkdir()
    regulation_pdf(folder / "Peraturan_OJK_13_2024.pdf", nomor=13, tahun=2024,
                   tentang="KETAHANAN DAN KEAMANAN SIBER BANK UMUM")
    regulation_pdf(folder / "Peraturan_OJK_11_2026.pdf")                  # already in KB
    (folder / "FAQ_POJK_13_2024.pdf").write_bytes(b"%PDF-1.4 faq")         # companion: skipped

    r = client.post("/api/sync/scans", json={"sumber": "folder", "path": str(folder),
                                             "klasifikasi_akses": "internal", "kategori": "perbankan"})
    assert r.status_code == 202
    scan = _wait(client, r.json()["status_url"])
    assert scan["status"]["label"] == "Berhasil"
    by_name = {i["judul"]: i for i in scan["items"]}
    assert set(by_name) == {"Peraturan OJK 13 2024", "Peraturan OJK 11 2026"}
    assert by_name["Peraturan OJK 11 2026"]["status_kbs"]["value"] == "sudah_ada"
    new = by_name["Peraturan OJK 13 2024"]
    assert new["dapat_dipilih"] and new["metadata_dari"] == "nama_berkas"

    r = client.post("/api/ingest/jobs", json={"scan_id": scan["scan_id"], "item_ids": [new["item_id"]]})
    assert r.status_code == 202
    job = _wait(client, r.json()["status_url"])
    assert job["progres"] == {"selesai": 1, "total": 1, "persen": 100}
    assert job["items"][0]["status_kbs"]["label"] == "Tersimpan di KBS"

    listed = client.get("/api/kb/documents", params={"akses": "internal"}).json()
    assert listed["total"] == 1 and listed["items"][0]["kategori"]["value"] == "perbankan"
    hist = client.get("/api/ingest/history", params={"jenis": "sinkronisasi"}).json()
    assert hist[0]["ringkasan"]["baru"] == 1


def test_only_new_items_can_be_ingested(client, tmp_path, regulation_pdf):
    folder = tmp_path / "f"
    folder.mkdir()
    regulation_pdf(folder / "Peraturan_OJK_11_2026.pdf")
    scan = _wait(client, client.post("/api/sync/scans", json={"sumber": "folder", "path": str(folder)})
                 .json()["status_url"])
    r = client.post("/api/ingest/jobs", json={"scan_id": scan["scan_id"],
                                              "item_ids": [scan["items"][0]["item_id"]]})
    assert r.status_code == 409


def test_semantic_search_reports_missing_index_clearly(client):
    assert client.get("/api/search", params={"q": "karbon", "method": "semantic"}).status_code == 503


def test_graph_relations_for_a_document(client):
    doc_id = client.get("/api/kb/documents", params={"q": "karbon"}).json()["items"][0]["id"]
    rel = client.get(f"/api/kb/documents/{doc_id}/relations").json()
    assert [n["key"] for n in rel["relasi"]["berdasar_pada"]] == ["UU|21|2011"]


@pytest.mark.parametrize("name,key", [
    ("Peraturan_OJK_11_2026.pdf", "POJK|11|2026"),
    ("POJK_203_20Tahun_202025_20Penatalaksanaan.pdf", "POJK|3|2025"),
    ("Surat_Edaran_OJK_6_2016.pdf", "SEOJK|6|2016"),
    ("Peraturan_ADK_19_Tahun_2015_PERUBAHAN.pdf", "PADK|19|2015"),
])
def test_identity_from_filename(name, key):
    """Regression: blind "_20"→space decoding corrupted every year 20xx."""
    from hero.service.flows import identity_from_filename
    assert identity_from_filename(name)[3] == key
