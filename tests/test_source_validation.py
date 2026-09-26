"""
tests/test_source_validation.py
Pengujian validasi sumber dokumen (situs web, folder lokal, OneDrive) — V01 s/d V08.
"""
from pathlib import Path
import pytest
from app.config import settings
from app.models.enums import JenisSumber, KlasifikasiAkses


def test_v01_register_folder_lokal_inside_root(client, tmp_path: Path, monkeypatch):
    """V01: Daftar folder_lokal di dalam akar -> 201, path normal, crawl_depth=null, default_access=non_publik."""
    root_dir = tmp_path / "allowed_sources"
    root_dir.mkdir(parents=True, exist_ok=True)
    sub_folder = root_dir / "pojk_2023"
    sub_folder.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    resp = client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "Folder POJK 2023",
            "url": str(sub_folder),
            "source_type": "folder_lokal",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Folder POJK 2023"
    assert data["source_type"] == "folder_lokal"
    assert data["crawl_depth"] is None
    assert data["default_access_classification"] == "non_publik"
    assert data["address"] == str(sub_folder.resolve())


def test_v02_folder_outside_root(client, tmp_path: Path, monkeypatch):
    """V02: Folder di luar akar (mis. direktori lain atau .. keluar akar) -> 400."""
    root_dir = tmp_path / "allowed_sources"
    root_dir.mkdir(parents=True, exist_ok=True)
    outside_dir = tmp_path / "outside_sources"
    outside_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    resp = client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "Folder Ilegal",
            "url": str(outside_dir),
            "source_type": "folder_lokal",
        },
    )
    assert resp.status_code == 400
    assert "akar yang diizinkan" in resp.json()["detail"]


def test_v03_folder_does_not_exist(client, tmp_path: Path, monkeypatch):
    """V03: Folder tidak ada -> 400."""
    root_dir = tmp_path / "allowed_sources"
    root_dir.mkdir(parents=True, exist_ok=True)
    non_existent = root_dir / "non_existent_subfolder"

    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    resp = client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "Folder Gaib",
            "url": str(non_existent),
            "source_type": "folder_lokal",
        },
    )
    assert resp.status_code == 400
    assert "tidak ditemukan atau bukan sebuah direktori" in resp.json()["detail"]


def test_v04_folder_lokal_with_crawl_depth(client, tmp_path: Path, monkeypatch):
    """V04: folder_lokal + crawl_depth=2 -> 422."""
    root_dir = tmp_path / "allowed_sources"
    root_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    resp = client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "Folder Salah Depth",
            "url": str(root_dir),
            "source_type": "folder_lokal",
            "crawl_depth": 2,
        },
    )
    assert resp.status_code == 422


def test_v05_situs_web_crawl_depth(client):
    """V05: situs_web tanpa crawl_depth -> Default 1; crawl_depth=9 -> 422."""
    # Tanpa crawl_depth -> default 1
    resp1 = client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "JDIH OJK",
            "url": "https://jdih.ojk.go.id",
            "source_type": "situs_web",
        },
    )
    assert resp1.status_code == 201, resp1.text
    assert resp1.json()["crawl_depth"] == 1
    assert resp1.json()["default_access_classification"] == "publik"

    # crawl_depth = 9 -> 422
    resp2 = client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "JDIH BI",
            "url": "https://jdih.bi.go.id",
            "source_type": "situs_web",
            "crawl_depth": 9,
        },
    )
    assert resp2.status_code == 422


def test_v06_onedrive_public_host_validation(client):
    """V06: onedrive_public host example.com -> 400; host 1drv.ms -> 201."""
    # Host example.com -> 400
    resp1 = client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "OneDrive Palsu",
            "url": "https://example.com/share/folder1",
            "source_type": "onedrive_public",
        },
    )
    assert resp1.status_code == 400
    assert "Host URL OneDrive tidak valid" in resp1.json()["detail"]

    # Host 1drv.ms -> 201
    resp2 = client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "OneDrive Sah",
            "url": "https://1drv.ms/f/s!Anv928374",
            "source_type": "onedrive_public",
        },
    )
    assert resp2.status_code == 201, resp2.text
    data = resp2.json()
    assert data["source_type"] == "onedrive_public"
    assert data["crawl_depth"] is None
    assert data["default_access_classification"] == "non_publik"


def test_v07_legacy_client_post(client):
    """V07: Klien lama POST {name, url} saja -> 201 sebagai situs_web depth 1 (kompatibel)."""
    resp = client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "Klien Lama Source",
            "url": "https://peraturan.go.id",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["source_type"] == "situs_web"
    assert data["crawl_depth"] == 1
    assert data["default_access_classification"] == "publik"
    assert data["address"] == "https://peraturan.go.id"


def test_v08_filter_by_source_type(client, tmp_path: Path, monkeypatch):
    """V08: GET /scraping-sources/?source_type=folder_lokal -> Hanya folder."""
    root_dir = tmp_path / "sources_v08"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    # Buat 1 situs_web dan 1 folder_lokal
    client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "Web Source",
            "url": "https://www.ojk.go.id",
            "source_type": "situs_web",
        },
    )
    client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "Folder Source",
            "url": str(root_dir),
            "source_type": "folder_lokal",
        },
    )

    # Filter folder_lokal
    resp = client.get("/api/v1/scraping-sources/?source_type=folder_lokal")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["source_type"] == "folder_lokal"
    assert items[0]["name"] == "Folder Source"
