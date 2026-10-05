"""
tests/test_url_guard.py
Pengujian unit untuk guard_url (SSRF), normalisasi URL, dan larangan impor pada paket app/crawlers (K14, K15, K19, K21).
"""
import ast
from pathlib import Path
import pytest
from app.config import settings
from app.crawlers.base import BlockedUrlError
from app.crawlers.url_utils import guard_url, normalize_url


def test_k15_guard_url_blocked_ips_and_schemes():
    """K15: guard_url unit test menolak IP privat, loopback, link-local, AWS metadata, dan skema non-HTTP."""
    blocked_urls = [
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/secret.pdf",
        "http://192.168.1.1/admin.pdf",
        "http://172.16.0.5/doc.pdf",
        "http://127.0.0.1:8000/api",
        "http://localhost:8000/api",
        "http://[::1]:8000/api",
        "ftp://example.com/test.pdf",
        "file:///etc/passwd",
        "gopher://example.com",
    ]
    for u in blocked_urls:
        with pytest.raises(BlockedUrlError):
            guard_url(u, allow_private=False)


def test_k15_guard_url_allowed_when_private_permitted():
    """K15: guard_url mengizinkan IP lokal/privat jika allow_private=True (untuk test & dev)."""
    guard_url("http://127.0.0.1:8000/test.pdf", allow_private=True)
    guard_url("http://localhost:8000/test.pdf", allow_private=True)


def test_k14_ssrf_post_scans_rejected(client, monkeypatch):
    """K14: SSRF: crawl_allow_private_networks=false menolak sumber dengan IP privat (HTTP 422)."""
    monkeypatch.setattr(settings, "crawl_allow_private_networks", False)

    # 1. Buat sumber situs_web mengarah ke 127.0.0.1
    resp_src = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "SSRF Source", "url": "http://127.0.0.1:8000/regulasi", "source_type": "situs_web"},
    )
    src_id = resp_src.json()["id"]

    # 2. POST /scans harus mengembalikan 422 dengan pesan SSRF
    resp_scan = client.post(
        "/api/v1/scans/",
        json={"source_id": src_id},
    )
    assert resp_scan.status_code == 422
    assert "SSRF" in resp_scan.json()["detail"] or "diblokir" in resp_scan.json()["detail"]


def test_k19_ast_no_forbidden_imports_in_crawlers():
    """K19: Paket app/crawlers TIDAK BOLEH mengimpor app.database, app.models, app.services, app.routers."""
    crawlers_dir = Path(__file__).resolve().parent.parent / "app" / "crawlers"
    forbidden_prefixes = (
        "app.database",
        "app.models",
        "app.services",
        "app.routers",
    )

    python_files = list(crawlers_dir.glob("*.py"))
    assert len(python_files) >= 4, f"File crawler ditemukan: {python_files}"

    for py_file in python_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_prefixes:
                        assert not alias.name.startswith(forbidden), (
                            f"File {py_file.name} mengimpor modul terlarang: '{alias.name}'"
                        )
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                for forbidden in forbidden_prefixes:
                    assert not module_name.startswith(forbidden), (
                        f"File {py_file.name} mengimpor modul terlarang via from: '{module_name}'"
                    )


def test_k21_url_normalization():
    """K21: Normalisasi URL menghasilkan format kanonikal yang identik."""
    url1 = "HTTP://Host.GO.ID:80/a%20b.pdf#x"
    url2 = "http://host.go.id/a b.pdf"
    url3 = "https://example.com:443/regulasi/pojk?page=1&sort=asc#top"

    norm1 = normalize_url(url1)
    norm2 = normalize_url(url2)
    norm3 = normalize_url(url3)

    assert norm1 == "http://host.go.id/a%20b.pdf"
    assert norm2 == "http://host.go.id/a%20b.pdf"
    assert norm1 == norm2
    assert norm3 == "https://example.com/regulasi/pojk?page=1&sort=asc"
