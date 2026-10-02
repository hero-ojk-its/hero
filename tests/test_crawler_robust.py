"""
tests/test_crawler_robust.py
Pengujian otomatis offline komprehensif untuk kasus-kasus pemindaian tangguh (S01-S16).
Menguji paging link/postback, deteksi captcha/WAF, redirect SSRF guard, 429 retry,
size probing, adapter JDIH/OneDrive, dan penarikan bermetadata ke KB.
"""
import hashlib
import json
import os
import posixpath
import re
import socket
import threading
from datetime import date
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, parse_qs, unquote, quote

import httpx
import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.config import settings
from app.crawlers.base import (
    PdfCandidate,
    ScanResult,
    BlockedUrlError,
    CrawlerError,
)
from app.crawlers.generic_html import GenericHtmlCrawler
from app.crawlers.sharepoint_postback import SharepointPostbackCrawler
from app.crawlers.jdih_api import JdihApiCrawler
from app.crawlers.onedrive_share import OneDriveShareCrawler
from app.crawlers.registry import get_crawler, detect_adapter_from_url
from app.crawlers.url_utils import normalize_url, guard_url, detect_captcha_or_waf, determine_doc_kind
from app.models.document import Document
from app.models.enums import (
    JenisSumber,
    StatusPindai,
    StatusKandidat,
    TujuanTarik,
    KlasifikasiAkses,
    PeranDokumen,
    StatusPemrosesan,
    StatusKeberlakuan,
)
from app.models.scan_candidate import ScanCandidate
from app.models.scan_session import ScanSession
from app.models.scraping_source import ScrapingSource
from app.services.scan_service import ScanService
from tests.conftest import make_pdf


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "scan"


class MockRobustServer(BaseHTTPRequestHandler):
    """Server HTTP serbaguna untuk menyajikan berbagai skenario pengujian crawling."""

    # Handlers dapat diatur per pengujian
    routes: Dict[str, Any] = {}
    request_logs: List[Dict[str, Any]] = []

    def log_message(self, format, *args):
        pass  # Sunyikan logging standar

    def do_HEAD(self):
        parsed = urlparse(self.path)
        path = parsed.path
        MockRobustServer.request_logs.append({"method": "HEAD", "path": path, "headers": dict(self.headers)})

        route = MockRobustServer.routes.get(path)
        if route:
            status_code = route.get("status", 200)
            headers = route.get("headers", {})
            self.send_response(status_code)
            for k, v in headers.items():
                self.send_header(k, str(v))
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        MockRobustServer.request_logs.append({"method": "GET", "path": path, "headers": dict(self.headers)})

        route = MockRobustServer.routes.get(path)
        if route:
            # Dukung dynamic callable handler
            if callable(route):
                route(self)
                return

            status_code = route.get("status", 200)
            headers = route.get("headers", {})
            body = route.get("body", b"")
            if isinstance(body, str):
                body = body.encode("utf-8")

            # Dukung Range header
            range_hdr = self.headers.get("Range")
            if range_hdr and "bytes=" in range_hdr:
                total_len = len(body)
                self.send_response(206)
                self.send_header("Content-Type", headers.get("Content-Type", "application/pdf"))
                self.send_header("Content-Range", f"bytes 0-0/{total_len}")
                self.send_header("Content-Length", "1")
                self.end_headers()
                self.wfile.write(body[:1])
                return

            self.send_response(status_code)
            for k, v in headers.items():
                self.send_header(k, str(v))
            if "Content-Length" not in headers:
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8", errors="ignore")
        MockRobustServer.request_logs.append({
            "method": "POST",
            "path": path,
            "body": post_body,
            "headers": dict(self.headers),
        })

        route = MockRobustServer.routes.get(path)
        if route:
            if callable(route):
                route(self, post_body)
                return
            status_code = route.get("status", 200)
            headers = route.get("headers", {})
            body = route.get("body", b"")
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status_code)
            for k, v in headers.items():
                self.send_header(k, str(v))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def robust_server():
    """Menjalankan server HTTP tiruan lokal di thread terpisah."""
    server = HTTPServer(("127.0.0.1", 0), MockRobustServer)
    port = server.server_port
    base_url = f"http://127.0.0.1:{port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield base_url, MockRobustServer

    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def reset_mock_routes():
    MockRobustServer.routes.clear()
    MockRobustServer.request_logs.clear()


# ==============================================================================
# S01: Paging Link 1 2 3 ... terakhir (5 halaman)
# ==============================================================================
def test_s01_paging_link_five_pages(robust_server, monkeypatch):
    """S01: Paging link 1 2 3 ... terakhir -> Semua 5 halaman terbaca, kandidat lengkap."""
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    # Siapkan 5 halaman dari fixture
    for i in range(1, 6):
        fn = f"s01_page{i}.html"
        p_path = f"/s01/page{i}.html"
        html_content = (FIXTURE_DIR / fn).read_text(encoding="utf-8")
        srv.routes[p_path] = {
            "status": 200,
            "headers": {"Content-Type": "text/html; charset=utf-8"},
            "body": html_content,
        }
    srv.routes["/s01/index.html"] = srv.routes["/s01/page1.html"]

    crawler = GenericHtmlCrawler(allow_private=True, delay_seconds=0, head_for_size=False)
    res = crawler.scan(f"{base_url}/s01/page1.html", depth=1, max_pages=10)

    assert res.pages_visited == 5
    assert len(res.candidates) == 7
    urls_found = [c.url for c in res.candidates]
    assert f"{base_url}/s01/doc1.pdf" in urls_found
    assert f"{base_url}/s01/doc7.pdf" in urls_found


# ==============================================================================
# S02: Paging Link dengan link tengah tersembunyi (1 2 ... 7 8 terakhir)
# ==============================================================================
def test_s02_paging_link_hidden_middle_pages(robust_server, monkeypatch):
    """S02: Paging link 1 2 ... 7 8 terakhir -> Semua 8 halaman terbaca via Berikutnya/Next."""
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    for i in range(1, 9):
        next_link = f'<a href="/s02/page{i+1}.html">Berikutnya</a>' if i < 8 else ''
        p_html = f"""
        <html><body>
            <h2>Halaman {i}</h2>
            <a href="/s02/doc{i}.pdf">PDF {i}</a>
            <div class="paging">
                <span>{i}</span>
                {next_link}
                <a href="/s02/page8.html">Terakhir</a>
            </div>
        </body></html>
        """
        p_path = f"/s02/page{i}.html" if i > 1 else "/s02/index.html"
        srv.routes[p_path] = {
            "status": 200,
            "headers": {"Content-Type": "text/html; charset=utf-8"},
            "body": p_html,
        }

    crawler = GenericHtmlCrawler(allow_private=True, delay_seconds=0, head_for_size=False)
    res = crawler.scan(f"{base_url}/s02/index.html", depth=1, max_pages=20)

    assert res.pages_visited == 8
    assert len(res.candidates) == 8


# ==============================================================================
# S03: Paging Loop (halaman 3 menaut kembali ke 2)
# ==============================================================================
def test_s03_paging_loop_detection(robust_server, monkeypatch):
    """S03: Paging loop -> Berhenti tanpa perulangan tak terbatas dan tanpa duplikasi."""
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    # Halaman 1 -> 2 -> 3 -> 2 (loop)
    srv.routes["/s03/page1.html"] = {
        "status": 200,
        "headers": {"Content-Type": "text/html"},
        "body": '<html><body><a href="/s03/a.pdf">A.pdf</a><a href="/s03/page2.html">2</a></body></html>',
    }
    srv.routes["/s03/page2.html"] = {
        "status": 200,
        "headers": {"Content-Type": "text/html"},
        "body": '<html><body><a href="/s03/b.pdf">B.pdf</a><a href="/s03/page3.html">3</a></body></html>',
    }
    srv.routes["/s03/page3.html"] = {
        "status": 200,
        "headers": {"Content-Type": "text/html"},
        "body": '<html><body><a href="/s03/c.pdf">C.pdf</a><a href="/s03/page2.html">2</a></body></html>',
    }

    crawler = GenericHtmlCrawler(allow_private=True, delay_seconds=0, head_for_size=False)
    res = crawler.scan(f"{base_url}/s03/page1.html", depth=1, max_pages=20)

    assert res.pages_visited == 3
    assert len(res.candidates) == 3


# ==============================================================================
# S04: Postback SharePoint (__EVENTTARGET + form hidden fields)
# ==============================================================================
def test_s04_sharepoint_postback_pagination(robust_server, monkeypatch):
    """S04: Postback SharePoint -> __EVENTTARGET dan hidden field dikirim benar, 3 halaman terbaca."""
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    def postback_handler(handler, post_body=None):
        method = handler.command
        if method == "GET":
            # Halaman 1
            body = """
            <html><body>
                <form method="post" action="/s04/regulasi.aspx" id="aspnetForm">
                    <input type="hidden" name="__VIEWSTATE" value="VS_PAGE1" />
                    <input type="hidden" name="__EVENTVALIDATION" value="EV_PAGE1" />
                    <a href="/id/regulasi/Pages/Regulasi-1.aspx">Regulasi 1</a>
                    <div id="DataPagerArticles">
                        <span class="current">1</span>
                        <a href="javascript:__doPostBack('ctl00$PlaceHolderMain$ctl01$DataPagerArticles$ctl01$ctl01','')">2</a>
                    </div>
                </form>
            </body></html>
            """
        else:
            # POST
            body_params = parse_qs(post_body or "")
            target = body_params.get("__EVENTTARGET", [""])[0]
            vs = body_params.get("__VIEWSTATE", [""])[0]

            if target.endswith("ctl02") or "3" in target:
                # Halaman 3
                body = """
                <html><body>
                    <form method="post" action="/s04/regulasi.aspx" id="aspnetForm">
                        <input type="hidden" name="__VIEWSTATE" value="VS_PAGE3" />
                        <a href="/id/regulasi/Pages/Regulasi-3.aspx">Regulasi 3</a>
                        <div id="DataPagerArticles">
                            <span class="current">3</span>
                        </div>
                    </form>
                </body></html>
                """
            elif target.endswith("ctl01") or "2" in target:
                # Halaman 2
                body = """
                <html><body>
                    <form method="post" action="/s04/regulasi.aspx" id="aspnetForm">
                        <input type="hidden" name="__VIEWSTATE" value="VS_PAGE2" />
                        <input type="hidden" name="__EVENTVALIDATION" value="EV_PAGE2" />
                        <a href="/id/regulasi/Pages/Regulasi-2.aspx">Regulasi 2</a>
                        <div id="DataPagerArticles">
                            <a href="javascript:__doPostBack('ctl00$PlaceHolderMain$ctl01$DataPagerArticles$ctl01$ctl00','')">1</a>
                            <span class="current">2</span>
                            <a href="javascript:__doPostBack('ctl00$PlaceHolderMain$ctl01$DataPagerArticles$ctl01$ctl02','')">3</a>
                        </div>
                    </form>
                </body></html>
                """
            else:
                body = "<html><body>Unknown Postback</body></html>"

        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.end_headers()
        handler.wfile.write(body.encode("utf-8"))

    srv.routes["/s04/regulasi.aspx"] = postback_handler

    # Route untuk detail pages
    for i in range(1, 4):
        srv.routes[f"/id/regulasi/Pages/Regulasi-{i}.aspx"] = {
            "status": 200,
            "headers": {"Content-Type": "text/html"},
            "body": f'<html><head><title>Regulasi {i}</title></head><body><a href="/docs/reg{i}.pdf">PDF {i}</a></body></html>',
        }

    crawler = SharepointPostbackCrawler(allow_private=True, delay_seconds=0, head_for_size=False)
    res = crawler.scan(f"{base_url}/s04/regulasi.aspx", depth=1, max_pages=10)

    assert res.pages_visited == 3
    assert len(res.candidates) == 3


# ==============================================================================
# S05: Halaman Detail OJK (Metadata + 3 Lampiran PDF dengan doc_kind)
# ==============================================================================
def test_s05_ojk_detail_page_metadata_and_attachments(robust_server, monkeypatch):
    """S05: Halaman detail OJK (snapshot asli dipangkas) -> Nomor, jenis, sektor, tanggal, dan 3 lampiran doc_kind benar."""
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    html_detail = (FIXTURE_DIR / "s05_ojk_detail.html").read_text(encoding="utf-8")
    srv.routes["/id/regulasi/Pages/POJK-13-Tahun-2026.aspx"] = {
        "status": 200,
        "headers": {"Content-Type": "text/html"},
        "body": html_detail,
    }

    crawler = SharepointPostbackCrawler(allow_private=True, delay_seconds=0, head_for_size=False)
    with httpx.Client(follow_redirects=True) as client:
        candidates = crawler._parse_detail_page(client, f"{base_url}/id/regulasi/Pages/POJK-13-Tahun-2026.aspx", page_depth=1)

    assert len(candidates) == 3
    kinds = {c.filename: c.doc_kind for c in candidates}
    assert kinds["POJK 13 Tahun 2026 Pemegang Saham Bursa Efek.pdf"] == "utama"
    assert kinds["Abstrak POJK 13 Tahun 2026 Pemegang Saham Bursa Efek.pdf"] == "abstrak"
    assert kinds["FAQ POJK 13 Tahun 2026 Pemegang Saham Bursa Efek.pdf"] == "faq"

    cand0 = candidates[0]
    assert cand0.regulation_number == "13 Tahun 2026"
    assert cand0.regulation_type == "POJK"
    assert cand0.bidang == "Pasar Modal"
    assert cand0.sub_bidang == "Bursa Efek"
    assert cand0.release_date == date(2026, 9, 15)
    assert cand0.effective_date == date(2026, 9, 15)


# ==============================================================================
# S06: Redirect Chain 3-Hop + Meta Refresh + SSRF Guard
# ==============================================================================
def test_s06_redirect_chain_and_ssrf_guard(robust_server, monkeypatch):
    """S06: Redirect chain 3 hop + meta refresh -> final_url benar; hop ke IP privat ditolak jika allow_private=False."""
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    srv.routes["/s06/hop1"] = {
        "status": 302,
        "headers": {"Location": f"{base_url}/s06/hop2"},
    }
    srv.routes["/s06/hop2"] = {
        "status": 301,
        "headers": {"Location": f"{base_url}/s06/hop3"},
    }
    srv.routes["/s06/hop3"] = {
        "status": 200,
        "headers": {"Content-Type": "text/html"},
        "body": f'<html><head><meta http-equiv="refresh" content="0; url={base_url}/s06/final.html"></head></html>',
    }
    srv.routes["/s06/final.html"] = {
        "status": 200,
        "headers": {"Content-Type": "text/html"},
        "body": '<html><body><a href="/s06/doc.pdf">Doc</a></body></html>',
    }

    crawler = GenericHtmlCrawler(allow_private=True, delay_seconds=0, head_for_size=False)
    res = crawler.scan(f"{base_url}/s06/hop1", depth=1, max_pages=10)
    assert len(res.candidates) == 1

    # Uji SSRF guard menolak private IP saat allow_private=False
    with pytest.raises(BlockedUrlError):
        guard_url("http://127.0.0.1:8000/private", allow_private=False)
    with pytest.raises(BlockedUrlError):
        guard_url("http://169.254.169.254/latest/meta-data", allow_private=False)


# ==============================================================================
# S07: Halaman Cloudflare "Just a moment" (503 + cf-chl)
# ==============================================================================
def test_s07_cloudflare_503_detection(robust_server, monkeypatch):
    """S07: Cloudflare 503 + cf-chl -> blocked=true, error terblokir_captcha, scan tidak crash."""
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    cf_html = (FIXTURE_DIR / "s07_cloudflare_503.html").read_text(encoding="utf-8")
    srv.routes["/s07/blocked.html"] = {
        "status": 503,
        "headers": {
            "Content-Type": "text/html",
            "cf-ray": "8c456789abcdef-CGK",
            "cf-chl-bypass": "1",
        },
        "body": cf_html,
    }

    crawler = GenericHtmlCrawler(allow_private=True, delay_seconds=0)
    res = crawler.scan(f"{base_url}/s07/blocked.html", depth=1)

    assert res.blocked is True
    assert any("terblokir_captcha" in err for err in res.errors)


# ==============================================================================
# S08: reCAPTCHA di Halaman 200
# ==============================================================================
def test_s08_recaptcha_200_detection(robust_server, monkeypatch):
    """S08: reCAPTCHA di halaman status 200 -> Terdeteksi dan dilaporkan."""
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    rc_html = (FIXTURE_DIR / "s08_recaptcha_200.html").read_text(encoding="utf-8")
    srv.routes["/s08/captcha.html"] = {
        "status": 200,
        "headers": {"Content-Type": "text/html"},
        "body": rc_html,
    }

    crawler = GenericHtmlCrawler(allow_private=True, delay_seconds=0)
    res = crawler.scan(f"{base_url}/s08/captcha.html", depth=1)

    assert res.blocked is True
    assert any("terblokir_captcha" in err for err in res.errors)


# ==============================================================================
# S09: 429 Too Many Requests dengan Retry-After
# ==============================================================================
def test_s09_rate_limit_retry_after(robust_server, monkeypatch):
    """S09: 429 dengan Retry-After: 1 -> Menunggu lalu berhasil."""
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    attempts = {"count": 0}

    def rate_limit_handler(handler):
        attempts["count"] += 1
        if attempts["count"] < 2:
            handler.send_response(429)
            handler.send_header("Retry-After", "1")
            handler.end_headers()
            handler.wfile.write(b"Rate limited")
        else:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html")
            handler.end_headers()
            handler.wfile.write(b'<html><body><a href="/s09/ok.pdf">OK PDF</a></body></html>')

    srv.routes["/s09/page.html"] = rate_limit_handler

    crawler = GenericHtmlCrawler(allow_private=True, delay_seconds=0, head_for_size=False)
    res = crawler.scan(f"{base_url}/s09/page.html", depth=1)

    assert attempts["count"] == 2
    assert len(res.candidates) == 1


# ==============================================================================
# S10: Ukuran: HEAD tanpa Content-Length -> Fallback Range 0-0
# ==============================================================================
def test_s10_size_probing_head_fallback_range(robust_server, monkeypatch):
    """S10: Ukuran via Range 0-0 -> size_bytes terisi dari Content-Range, size_source=range."""
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    pdf_bytes = make_pdf("PDF bytes test size probing range")
    srv.routes["/s10/test.pdf"] = {
        "status": 200,
        "headers": {
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="test_s10.pdf"',
        },
        "body": pdf_bytes,
    }

    crawler = GenericHtmlCrawler(allow_private=True, delay_seconds=0, head_for_size=True)
    with httpx.Client(follow_redirects=True) as client:
        size, fn, size_src, _ = crawler.probe_size_and_meta(client, f"{base_url}/s10/test.pdf")

    assert size == len(pdf_bytes)
    assert fn == "test_s10.pdf"
    assert size_src in ("head", "range")


# ==============================================================================
# S11: Fixture JSON JDIH (2 Halaman API)
# ==============================================================================
def test_s11_jdih_api_crawler_two_pages(robust_server, monkeypatch):
    """S11: Fixture JSON JDIH -> Paging API, metadata dan bidang terisi lengkap."""
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    p1_json = (FIXTURE_DIR / "s11_jdih_page1.json").read_text(encoding="utf-8")
    p2_json = (FIXTURE_DIR / "s11_jdih_page2.json").read_text(encoding="utf-8")

    def jdih_handler(handler):
        qs = parse_qs(urlparse(handler.path).query)
        start = int(qs.get("iDisplayStart", ["0"])[0])
        body = p1_json if start == 0 else p2_json
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(body.encode("utf-8"))

    srv.routes["/Web/ViewPeraturanHome/ListDataPeraturan"] = jdih_handler

    # Mock halaman detail untuk masing-masing regulasi (GUID asli dari fixture DataTables)
    for guid, name in [
        ("95716c28-8ed1-5964-7ed5-592615a5b53c", "2026padk004.pdf"),
        ("ffba8600-32dd-1c98-e8c3-68d0c8922808", "2026pojk010.pdf"),
        ("d123dff4-9d95-6f53-9568-5224e371a676", "2026pojk009.pdf"),
        ("009e5e55-ce9b-5f02-6b0b-2fdb55e5675a", "2026pojk008.pdf"),
    ]:
        att_guid = f"att-{guid[:8]}"
        detail_html = f"""
        <html><body><table><tr>
            <th style="width:200px"><h4>Peraturan</h4></th>
            <td><a download href="/Web/ViewPeraturan/DownloadDokumen/{att_guid}" onclick="downloadDokumen('{name}','~/Dokumen/{name}')">Unduh</a></td>
        </tr></table></body></html>
        """
        srv.routes[f"/Web/ViewPeraturan/Detail/{guid}/All/"] = {
            "status": 200,
            "headers": {"Content-Type": "text/html"},
            "body": detail_html,
        }

    crawler = JdihApiCrawler(allow_private=True, delay_seconds=0, head_for_size=False)
    res = crawler.scan(base_url, depth=1, max_pages=10)

    assert len(res.candidates) == 4
    types = [c.regulation_type for c in res.candidates]
    assert "POJK" in types
    assert "PADK" in types

    bidangs = [c.bidang for c in res.candidates]
    assert any("Pasar Modal" in b for b in bidangs if b)
    assert any("Lembaga Pembiayaan" in b for b in bidangs if b)


# ==============================================================================
# S12: Fixture Listing OneDrive (Folder Bersarang 3 Level + Campur Non-PDF)
# ==============================================================================
def test_s12_onedrive_share_crawler_recursive(robust_server, monkeypatch):
    """S12: OneDrive share -> Rekursif 3 level, source_path benar, size_source=listing, non-PDF dihitung."""
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    # 1. Initial share redirect
    srv.routes["/share/test"] = {
        "status": 302,
        "headers": {
            "Location": f"{base_url}/personal/user_test/_layouts/15/onedrive.aspx?id=%2Fpersonal%2Fuser_test%2FDocuments%2Froot",
        },
    }
    srv.routes["/personal/user_test/_layouts/15/onedrive.aspx"] = {
        "status": 200,
        "headers": {"Content-Type": "text/html"},
        "body": "<html><body>OneDrive Layout</body></html>",
    }

    # 2. Mock SharePoint REST API
    def sp_api_handler(handler):
        path = handler.path
        if "/Folders" in path:
            if "root" in path and "sub1" not in path:
                # Root folders: sub1
                data = {"d": {"results": [{"Name": "sub1", "ServerRelativeUrl": "/personal/user_test/Documents/root/sub1"}]}}
            elif "sub1" in path:
                # Sub1 folders: sub2
                data = {"d": {"results": [{"Name": "sub2", "ServerRelativeUrl": "/personal/user_test/Documents/root/sub1/sub2"}]}}
            else:
                data = {"d": {"results": []}}
        elif "/Files" in path:
            if "sub2" in path:
                data = {"d": {"results": [
                    {"Name": "leaf.pdf", "ServerRelativeUrl": "/personal/user_test/Documents/root/sub1/sub2/leaf.pdf", "Length": "12345"},
                    {"Name": "notes.docx", "ServerRelativeUrl": "/personal/user_test/Documents/root/sub1/sub2/notes.docx", "Length": "999"},
                ]}}
            elif "sub1" in path:
                data = {"d": {"results": [
                    {"Name": "mid.pdf", "ServerRelativeUrl": "/personal/user_test/Documents/root/sub1/mid.pdf", "Length": "54321"},
                ]}}
            else:
                data = {"d": {"results": [
                    {"Name": "top.pdf", "ServerRelativeUrl": "/personal/user_test/Documents/root/top.pdf", "Length": "8888"},
                ]}}
        else:
            data = {"d": {"results": []}}

        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps(data).encode("utf-8"))

    srv.routes["/personal/user_test/_api/web/GetFolderByServerRelativeUrl('%2Fpersonal%2Fuser_test%2FDocuments%2Froot')/Folders"] = sp_api_handler
    srv.routes["/personal/user_test/_api/web/GetFolderByServerRelativeUrl('%2Fpersonal%2Fuser_test%2FDocuments%2Froot')/Files"] = sp_api_handler
    srv.routes["/personal/user_test/_api/web/GetFolderByServerRelativeUrl('%2Fpersonal%2Fuser_test%2FDocuments%2Froot%2Fsub1')/Folders"] = sp_api_handler
    srv.routes["/personal/user_test/_api/web/GetFolderByServerRelativeUrl('%2Fpersonal%2Fuser_test%2FDocuments%2Froot%2Fsub1')/Files"] = sp_api_handler
    srv.routes["/personal/user_test/_api/web/GetFolderByServerRelativeUrl('%2Fpersonal%2Fuser_test%2FDocuments%2Froot%2Fsub1%2Fsub2')/Folders"] = sp_api_handler
    srv.routes["/personal/user_test/_api/web/GetFolderByServerRelativeUrl('%2Fpersonal%2Fuser_test%2FDocuments%2Froot%2Fsub1%2Fsub2')/Files"] = sp_api_handler

    crawler = OneDriveShareCrawler(allow_private=True, delay_seconds=0)
    res = crawler.scan(f"{base_url}/share/test", depth=5)

    assert len(res.candidates) == 3
    paths = {c.filename: c.source_path for c in res.candidates}
    assert paths["top.pdf"] == "top.pdf"
    assert paths["mid.pdf"] == "sub1/mid.pdf"
    assert paths["leaf.pdf"] == "sub1/sub2/leaf.pdf"
    assert res.stats.get("non_pdf_links") == 1
    assert all(c.size_source == "listing" for c in res.candidates)


# ==============================================================================
# S13: Pull Kandidat Bermetadata ke KB dengan Dynamic Naming Format
# ==============================================================================
def test_s13_pull_candidate_with_metadata_to_kb(client: TestClient, db_session: Session, monkeypatch):
    """S13: Pull kandidat bermetadata ke KB -> nama berkas tanpa NA, ditempatkan sesuai naming_format."""
    src = ScrapingSource(
        name="Source S13",
        url="https://ojk.go.id/s13",
        source_type=JenisSumber.situs_web,
        default_access_classification=KlasifikasiAkses.publik,
        default_document_role=PeranDokumen.corpus_eksisting,
    )
    db_session.add(src)
    db_session.flush()

    sess = ScanSession(
        source_id=src.id,
        start_url=src.url,
        crawl_depth=1,
        mode="test",
        status=StatusPindai.siap_dipilih,
    )
    db_session.add(sess)
    db_session.flush()

    cand_url = "https://ojk.go.id/s13/pojk13.pdf"
    cand = ScanCandidate(
        scan_id=sess.id,
        url=cand_url,
        url_hash=hashlib.sha256(cand_url.encode()).hexdigest(),
        filename="pojk13.pdf",
        document_title="Pemegang Saham Bursa Efek",
        regulation_number="13 Tahun 2026",
        regulation_type="POJK",
        bidang="Pasar Modal",
        release_date=date(2026, 3, 15),
        size_bytes=5000,
        match_status=StatusKandidat.baru,
        selected=True,
    )
    db_session.add(cand)
    db_session.commit()

    class MockFetched:
        filename = "pojk13.pdf"
        content = make_pdf("PDF S13 POJK 13 2026")

    monkeypatch.setattr(
        "app.services.scan_service.get_crawler",
        lambda *a, **kw: type("MockC", (), {"fetch": lambda self, u, **k: MockFetched()})(),
    )

    pull_payload = {
        "destination": "knowledge_base",
        "naming_format": ["jenis", "tahun", "nama"],
        "naming_separator": "_",
    }
    resp = client.post(f"/api/v1/scans/{sess.id}/pull?wait=true", json=pull_payload)
    assert resp.status_code == 200

    # Verifikasi dokumen di KB
    doc = db_session.query(Document).filter(Document.source_url == cand_url).first()
    assert doc is not None
    assert doc.regulation_type == "POJK"
    assert doc.regulation_number == "13 Tahun 2026"
    assert doc.bidang == "Pasar Modal"
    # Nama baku tidak boleh ada 'NA'
    assert "NA" not in doc.standardized_filename
    assert doc.standardized_filename.startswith("POJK_2026_")


# ==============================================================================
# S14: Run pada Sumber OneDrive Mengembalikan 409
# ==============================================================================
def test_s14_run_onedrive_source_returns_409(client: TestClient):
    """S14: POST /scraping-sources/{id}/run untuk OneDrive mengembalikan 409 mengarahkan ke /scans."""
    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "OneDrive S14",
            "url": "https://oneojk-my.sharepoint.com/:f:/g/personal/test/Ig123?e=abc",
            "source_type": "onedrive_public",
        },
    )
    assert resp_create.status_code == 201
    source_id = resp_create.json()["id"]

    resp_run = client.post(f"/api/v1/scraping-sources/{source_id}/run")
    assert resp_run.status_code == 409
    assert "POST /api/v1/scans" in resp_run.json()["detail"]


# ==============================================================================
# S15: Robots.txt Melarang Path
# ==============================================================================
def test_s15_robots_txt_disallow(robust_server, monkeypatch):
    """S15: Path dilarang oleh robots.txt -> Tidak diakses, dicatat di errors."""
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    srv.routes["/robots.txt"] = {
        "status": 200,
        "headers": {"Content-Type": "text/plain"},
        "body": "User-agent: *\nDisallow: /s15/rahasia/\n",
    }
    srv.routes["/s15/index.html"] = {
        "status": 200,
        "headers": {"Content-Type": "text/html"},
        "body": '<html><body><a href="/s15/rahasia/page.html">Halaman Rahasia</a></body></html>',
    }

    crawler = GenericHtmlCrawler(allow_private=True, delay_seconds=0, respect_robots=True)
    res = crawler.scan(f"{base_url}/s15/index.html", depth=2)

    assert any("robots.txt" in err for err in res.errors)


# ==============================================================================
# S16: Filter Kandidat (doc_kind, bidang, q)
# ==============================================================================
def test_s16_filter_candidates_query_params(client: TestClient, db_session: Session):
    """S16: Filter GET /scans/{id}/candidates dengan doc_kind, bidang, dan q pada document_title."""
    src = ScrapingSource(
        name="Source S16",
        url="https://ojk.go.id/s16",
        source_type=JenisSumber.situs_web,
    )
    db_session.add(src)
    db_session.flush()

    sess = ScanSession(
        source_id=src.id,
        start_url=src.url,
        crawl_depth=1,
        mode="test",
        status=StatusPindai.siap_dipilih,
    )
    db_session.add(sess)
    db_session.flush()

    # Buat 3 kandidat berbeda
    c1 = ScanCandidate(
        scan_id=sess.id,
        url="https://ojk.go.id/s16/utama.pdf",
        url_hash="h1",
        filename="utama.pdf",
        document_title="Peraturan Tata Kelola Bank",
        doc_kind="utama",
        bidang="Perbankan",
        selected=True,
    )
    c2 = ScanCandidate(
        scan_id=sess.id,
        url="https://ojk.go.id/s16/abstrak.pdf",
        url_hash="h2",
        filename="abstrak.pdf",
        document_title="Abstrak Tata Kelola Bank",
        doc_kind="abstrak",
        bidang="Perbankan",
        selected=True,
    )
    c3 = ScanCandidate(
        scan_id=sess.id,
        url="https://ojk.go.id/s16/pasar_modal.pdf",
        url_hash="h3",
        filename="pasar_modal.pdf",
        document_title="Bursa Karbon Efek",
        doc_kind="utama",
        bidang="Pasar Modal",
        selected=True,
    )
    db_session.add_all([c1, c2, c3])
    db_session.commit()

    # 1. Filter doc_kind=abstrak
    r_kind = client.get(f"/api/v1/scans/{sess.id}/candidates?doc_kind=abstrak")
    assert r_kind.status_code == 200
    assert r_kind.json()["total"] == 1
    assert r_kind.json()["items"][0]["filename"] == "abstrak.pdf"

    # 2. Filter bidang=Perbankan
    r_bidang = client.get(f"/api/v1/scans/{sess.id}/candidates?bidang=Perbankan")
    assert r_bidang.status_code == 200
    assert r_bidang.json()["total"] == 2

    # 3. Filter q="Bursa Karbon"
    r_q = client.get(f"/api/v1/scans/{sess.id}/candidates?q=Bursa%20Karbon")
    assert r_q.status_code == 200
    assert r_q.json()["total"] == 1
    assert r_q.json()["items"][0]["document_title"] == "Bursa Karbon Efek"


# ==============================================================================
# LANGKAH 10B: PERBAIKAN KEBENARAN DATA SCAN & BENCHMARK PENUH (T01 - T06)
# ==============================================================================

def test_t01_jdih_detail_attachment_guids(robust_server, monkeypatch):
    """
    T01: Fixture detail JDIH asli dengan 3 lampiran -> URL berkas diambil dari
    GUID lampiran di halaman detail, BUKAN dari GUID regulasi.
    """
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    reg_guid = "95716c28-8ed1-5964-7ed5-592615a5b53c"
    att_utama_guid = "ad5fef9e-4dc9-f433-636c-082bc8a95d90"
    att_abs_guid = "525798ef-b7a2-733d-a056-b4896734e37c"
    att_faq_guid = "f61670b2-df9d-037e-a684-485fd72e772b"

    # 1. API ListDataPeraturan
    api_data = {
        "sEcho": 1,
        "iTotalRecords": 1,
        "iTotalDisplayRecords": 1,
        "aaData": [
            [
                f"<a href='http://jdih.ojk.go.id/Web/ViewPeraturan/Detail/{reg_guid}/All/'>PADK Nomor 4 Tahun 2026 Wali Amanat</a>",
                "4",
                "Pasar Modal",
                "-",
                "-",
                "Surat Edaran OJK / Peraturan Anggota Dewan Komisioner OJK",
                "07-07-2026",
            ]
        ],
    }
    srv.routes["/Web/ViewPeraturanHome/ListDataPeraturan"] = {
        "status": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(api_data),
    }

    # 2. Halaman detail dengan 3 lampiran
    detail_html = f"""
    <html><body>
    <table>
      <tr>
        <th style="width:200px"><h4>Peraturan</h4></th>
        <td>
          <a download href="/Web/ViewPeraturan/DownloadDokumen/{att_utama_guid}" onclick="downloadDokumen('2026padk004.pdf','~/Dokumen/Peraturan/2026padk004.pdf')">Unduh</a>
        </td>
      </tr>
      <tr>
        <th style="width:200px"><h4>Abstrak</h4></th>
        <td>
          <a download href="/Web/ViewPeraturan/DownloadDokumen/{att_abs_guid}" onclick="downloadDokumen('2026abspadk004.pdf','~/Dokumen/Peraturan/2026abspadk004.pdf')">Unduh</a>
        </td>
      </tr>
      <tr>
        <th style="width:200px"><h4>FAQ</h4></th>
        <td>
          <a download href="/Web/ViewPeraturan/DownloadDokumen/{att_faq_guid}" onclick="downloadDokumen('2026faqpadk004.pdf','~/Dokumen/Peraturan/2026faqpadk004.pdf')">Unduh</a>
        </td>
      </tr>
    </table>
    </body></html>
    """
    srv.routes[f"/Web/ViewPeraturan/Detail/{reg_guid}/All/"] = {
        "status": 200,
        "headers": {"Content-Type": "text/html"},
        "body": detail_html,
    }

    # 3. Route lampiran HEAD
    pdf_bytes = make_pdf("Dokumen Lampiran")
    srv.routes[f"/Web/ViewPeraturan/DownloadDokumen/{att_utama_guid}"] = {
        "status": 200,
        "headers": {"Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="2026padk004.pdf"', "Content-Length": str(len(pdf_bytes))},
        "body": pdf_bytes,
    }
    srv.routes[f"/Web/ViewPeraturan/DownloadDokumen/{att_abs_guid}"] = {
        "status": 200,
        "headers": {"Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="2026abspadk004.pdf"', "Content-Length": str(len(pdf_bytes))},
        "body": pdf_bytes,
    }
    srv.routes[f"/Web/ViewPeraturan/DownloadDokumen/{att_faq_guid}"] = {
        "status": 200,
        "headers": {"Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="2026faqpadk004.pdf"', "Content-Length": str(len(pdf_bytes))},
        "body": pdf_bytes,
    }

    crawler = JdihApiCrawler(allow_private=True, delay_seconds=0, head_for_size=True)
    res = crawler.scan(f"{base_url}/", depth=1)

    assert len(res.candidates) == 3
    # Verifikasi URL TIDAK memakai GUID regulasi
    assert all(reg_guid not in c.url for c in res.candidates)
    # Verifikasi URL memakai GUID lampiran yang benar
    candidate_urls = [c.url for c in res.candidates]
    assert any(att_utama_guid in u for u in candidate_urls)
    assert any(att_abs_guid in u for u in candidate_urls)
    assert any(att_faq_guid in u for u in candidate_urls)

    # Verifikasi doc_kind dan metadata
    kinds = {c.filename: c.doc_kind for c in res.candidates}
    assert kinds["2026padk004.pdf"] == "utama"
    assert kinds["2026abspadk004.pdf"] == "abstrak"
    assert kinds["2026faqpadk004.pdf"] == "faq"


def test_t02_regulation_filename_mismatch_warning():
    """
    T02: Respons berkas yang nama berkasnya tidak cocok dengan nomor/tahun
    regulasi -> match_warning terisi dan dihitung di ringkasan.
    """
    from app.crawlers.url_utils import validate_regulation_filename_match

    # Kasus 1: Tahun dan nomor berkas dari regulasi lain (FAQ POJK 19/2023 pada PADK 4/2026)
    warn1 = validate_regulation_filename_match(
        filename="FAQ POJK Nomor 19 Tahun 2023.pdf",
        regulation_number="4",
        release_date=date(2026, 7, 7),
        document_title="PADK Nomor 4 Tahun 2026 tentang Wali Amanat",
        regulation_type="PADK",
    )
    assert warn1 is not None
    assert "2023" in warn1 and "2026" in warn1
    assert "19" in warn1 and "4" in warn1

    # Kasus 2: Berkas yang cocok (2026padk004.pdf pada PADK 4/2026)
    warn2 = validate_regulation_filename_match(
        filename="2026padk004.pdf",
        regulation_number="PADK Nomor 4 Tahun 2026",
        release_date=date(2026, 7, 7),
        document_title="PADK Nomor 4 Tahun 2026 tentang Wali Amanat",
        regulation_type="PADK",
    )
    assert warn2 is None

    # Kasus 3: Toleransi format SAL POJK 72 - Ketentuan.pdf
    warn3 = validate_regulation_filename_match(
        filename="SAL POJK 72 - Ketentuan.pdf",
        regulation_number="72",
        release_date=date(2020, 1, 1),
        document_title="POJK Nomor 72 Tahun 2020",
        regulation_type="POJK",
    )
    assert warn3 is None

    # Kasus pola ADK dengan perubahan regulasi lain di judulnya (jangan memicu false positive)
    warn_adk = validate_regulation_filename_match(
        "Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_DEWAN_KOMISIONER_OTORITAS_JASA_KEUANGAN_NOMOR_33_SEDK.02_2013_TENTANG_PEDOMAN_TATA_NASKAH_DINAS_OTORITAS_JASA_KEUANGAN.pdf",
        regulation_number="19",
        release_year=2015,
        regulation_type="PADK",
    )
    assert warn_adk is None


def test_t03_doc_kind_detection():
    """
    T03: Deteksi doc_kind untuk variasi nama file abstrak, faq, salinan, non_regulasi, dsb.
    """
    from app.crawlers.url_utils import determine_doc_kind

    assert determine_doc_kind("2026abspojk008.pdf") == "abstrak"
    assert determine_doc_kind("2024faqseojk020.pdf") == "faq"
    assert determine_doc_kind("SAL POJK 72 - Dokumen Regulasi.pdf") == "utama"
    assert determine_doc_kind("Abstrak POJK 10 Tahun 2026.pdf") == "abstrak"
    assert determine_doc_kind("FAQ POJK 10 Tahun 2026.pdf") == "faq"
    # Kasus tambahan dan variasi underscore
    assert determine_doc_kind("faq_pbi_101708.pdf") == "faq"
    assert determine_doc_kind("faq_se_150613.pdf") == "faq"
    assert determine_doc_kind("abs_pbi_101708.pdf") == "abstrak"
    assert determine_doc_kind("abstrak_pojk_12.pdf") == "abstrak"
    assert determine_doc_kind("lamp_ketentuan.pdf") == "lampiran"
    # Prioritas lampiran bila diawali Lampiran
    assert determine_doc_kind("Lampiran SP - FAQ Ketentuan POJK.pdf") == "lampiran"
    # Berkas non-regulasi
    assert determine_doc_kind("NDA Personil Synthetic Name_Backend.pdf") == "non_regulasi"
    assert determine_doc_kind("HERO_User_Requirement_Document.pdf") == "non_regulasi"
    assert determine_doc_kind("Project Charter Mitra_OJK.pdf") == "non_regulasi"
    assert determine_doc_kind("2026padk004.pdf") == "utama"
    assert determine_doc_kind("Salinan POJK Nomor 19 Tahun 2023.pdf") == "utama"
    assert determine_doc_kind("dokumen.pdf", label="Abstrak") == "abstrak"
    assert determine_doc_kind("dokumen.pdf", label="FAQ") == "faq"
    # Berkas Ringkasan & Summary dipetakan ke abstrak
    assert determine_doc_kind("Ringkasan POJK 14.pdf") == "abstrak"
    assert determine_doc_kind("Ringkasan SEOJK 12 - 2017.pdf") == "abstrak"
    assert determine_doc_kind("12 - Ringkasan SEOJK 14 - 2017.pdf") == "abstrak"
    assert determine_doc_kind("2020ringkasanseojk022.pdf") == "abstrak"
    assert determine_doc_kind("Ringkasan Eksekutif dan FAQ SEOJK 53.pdf") == "faq"
    # Pola tanpa spasi dan underscore tambahan
    assert determine_doc_kind("faqpbi101708.pdf") == "faq"
    assert determine_doc_kind("abspbi101708.pdf") == "abstrak"
    assert determine_doc_kind("abstrakpojk12.pdf") == "abstrak"
    assert determine_doc_kind("ringkasan_pojk_14.pdf") == "abstrak"
    assert determine_doc_kind("ringkasanpojk14.pdf") == "abstrak"
    assert determine_doc_kind("summary_pojk_22.pdf") == "abstrak"
    assert determine_doc_kind("summarypojk22.pdf") == "abstrak"


def test_t04_regulation_type_normalization():
    """
    T04: Normalisasi jenis regulasi:
    PERATURAN ADK -> PADK
    Judul 'Peraturan Anggota Dewan Komisioner…' -> PADK
    Judul 'Surat Edaran…' -> SEOJK
    """
    from app.crawlers.url_utils import normalize_crawler_regulation_type

    assert normalize_crawler_regulation_type("PERATURAN ADK") == "PADK"
    assert normalize_crawler_regulation_type(None, title="Peraturan Anggota Dewan Komisioner Nomor 4...") == "PADK"
    assert normalize_crawler_regulation_type(None, title="Surat Edaran OJK Nomor 12...") == "SEOJK"
    assert normalize_crawler_regulation_type(
        "SURAT EDARAN OJK / PERATURAN ANGGOTA DEWAN KOMISIONER OJK",
        title="Peraturan Anggota Dewan Komisioner Nomor 4 Tahun 2026"
    ) == "PADK"
    assert normalize_crawler_regulation_type(
        "SURAT EDARAN OJK / PERATURAN ANGGOTA DEWAN KOMISIONER OJK",
        title="Surat Edaran OJK Nomor 19/SEOJK.06/2024"
    ) == "SEOJK"


def test_t05_parse_onedrive_filename_metadata():
    """
    T05: Parse metadata dari berbagai pola penamaan berkas OneDrive
    """
    from app.crawlers.url_utils import parse_onedrive_filename_metadata

    res1 = parse_onedrive_filename_metadata("Peraturan_OJK_3_2015.pdf")
    assert res1.get("regulation_type") == "POJK"
    assert res1.get("regulation_number") == "3"
    assert res1.get("release_year") == 2015
    assert res1.get("release_date") is None

    res2 = parse_onedrive_filename_metadata("SEOJKNo02Tahun2013_1395202423.pdf")
    assert res2.get("regulation_type") == "SEOJK"
    assert res2.get("regulation_number") == "2"
    assert res2.get("release_year") == 2013

    res3 = parse_onedrive_filename_metadata("SK_Dir_28-83-KEP-DIR-1995_Perubahan_SK_Dir_No._27121KEPDIR.pdf")
    assert res3.get("regulation_type") == "KEPDIR"
    assert res3.get("regulation_number") == "28-83-KEP-DIR-1995"
    assert res3.get("release_year") == 1995

    res4 = parse_onedrive_filename_metadata("Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_DEWAN_KOMISIONER_OTORITAS_JASA_KEUANGAN_NOMOR_33_SEDK.02_2013_TENTANG_PEDOMAN_TATA_NASKAH_DINAS_OTORITAS_JASA_KEUANGAN.pdf")
    assert res4.get("regulation_type") == "PADK"
    assert res4.get("regulation_number") == "19"
    assert res4.get("release_year") == 2015

    res5 = parse_onedrive_filename_metadata("POJK_203_20Tahun_202025_20Penatalaksanaan_20Lembaga_20Sertifikasi_20Profesi_20di_20Sektor_20Jasa_20Keuangan.pdf")
    assert res5.get("regulation_type") == "POJK"
    assert res5.get("regulation_number") == "3"
    assert res5.get("release_year") == 2025

    # Kasus regresi _20, _29, PBI, dan awalan indeks
    res6 = parse_onedrive_filename_metadata("Surat_Edaran_OJK_20_2017.pdf")
    assert res6.get("regulation_type") == "SEOJK"
    assert res6.get("regulation_number") == "20"
    assert res6.get("release_year") == 2017

    res7 = parse_onedrive_filename_metadata("Surat_Edaran_OJK_20_2014.pdf")
    assert res7.get("regulation_type") == "SEOJK"
    assert res7.get("regulation_number") == "20"
    assert res7.get("release_year") == 2014

    res8 = parse_onedrive_filename_metadata("Peraturan_Bank_Indonesia_20_2008.pdf")
    assert res8.get("regulation_type") == "PBI"
    assert res8.get("regulation_number") == "20"
    assert res8.get("release_year") == 2008

    res9 = parse_onedrive_filename_metadata("Surat_Edaran_OJK_29_2016.pdf")
    assert res9.get("regulation_type") == "SEOJK"
    assert res9.get("regulation_number") == "29"
    assert res9.get("release_year") == 2016

    res10 = parse_onedrive_filename_metadata("Surat_Edaran_OJK_29_2025.pdf")
    assert res10.get("regulation_type") == "SEOJK"
    assert res10.get("regulation_number") == "29"
    assert res10.get("release_year") == 2025

    res11 = parse_onedrive_filename_metadata("43_-_Rijksblaad_dari_Daerah_Paku_Alaman_Tahun_1937_Nomor_9.pdf")
    assert res11.get("regulation_number") == "9"
    assert res11.get("release_year") == 1937

    res12 = parse_onedrive_filename_metadata("42_-_Staatsblad_Tahun_1929_Nomor_357.pdf")
    assert res12.get("regulation_number") == "357"
    assert res12.get("release_year") == 1929

    from app.crawlers.url_utils import validate_regulation_filename_match
    assert validate_regulation_filename_match("43_-_Rijksblaad_dari_Daerah_Paku_Alaman_Tahun_1937_Nomor_9.pdf", regulation_number="9", release_year=1937) is None
    assert validate_regulation_filename_match("42_-_Staatsblad_Tahun_1929_Nomor_357.pdf", regulation_number="357", release_year=1929) is None


# ==============================================================================
# U01–U04: Pengujian Tanggal, Nomor Sintetis, dan Validasi Berkas JDIH (Langkah 10c)
# ==============================================================================
def test_u01_jdih_penetapan_vs_effective_date(robust_server, monkeypatch):
    """
    U01: Item JDIH (fixture asli) dengan tanggal penetapan != tanggal berlaku.
    Ekspektasi: release_date = penetapan, effective_date = berlaku.
    """
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    guid = "406ece2b-a508-fc8c-31a4-c7a312908c2e"
    api_payload = {
        "sEcho": 1,
        "iTotalRecords": [1],
        "iTotalDisplayRecords": [1],
        "aaData": [
            [
                f"<a href='http://jdih.ojk.go.id/Web/ViewPeraturan/Detail/{guid}/All/'>Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 18 Tahun 2025 tentang Transparansi dan Publikasi Laporan Bank</a>",
                "18",
                "Perbankan",
                None,
                None,
                "Peraturan OJK",
                "09-02-2026",
                "Berlaku"
            ]
        ]
    }
    import json
    srv.routes["/Web/ViewPeraturanHome/ListDataPeraturan"] = {
        "status": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(api_payload),
    }

    # Halaman detail asli dengan penetapan: 04-08-2025, status berlaku: 09-02-2026
    detail_html = f"""
    <html><body><table>
        <tr><th><h4>Tanggal Penetapan</h4></th><td>:</td><td>04-08-2025</td></tr>
        <tr><th><h4>Tanggal Pengundangan</h4></th><td>:</td><td>08-08-2025</td></tr>
        <tr><th><h4>Status Peraturan</h4></th><td>:</td><td>Berlaku Sejak Tanggal 09-02-2026</td></tr>
        <tr>
            <th><h4>Peraturan</h4></th>
            <td><a download href="/Web/ViewPeraturan/DownloadDokumen/att-pojk18" onclick="downloadDokumen('2025pojk018.pdf','~/Dokumen/2025pojk018.pdf')">Unduh</a></td>
        </tr>
    </table></body></html>
    """
    srv.routes[f"/Web/ViewPeraturan/Detail/{guid}/All/"] = {
        "status": 200,
        "headers": {"Content-Type": "text/html"},
        "body": detail_html,
    }

    crawler = JdihApiCrawler(allow_private=True, delay_seconds=0, head_for_size=False)
    res = crawler.scan(base_url, depth=1, max_pages=1)
    assert len(res.candidates) == 1
    cand = res.candidates[0]
    assert cand.release_date == date(2025, 8, 4)
    assert cand.effective_date == date(2026, 2, 9)


def test_u02_jdih_synthetic_number_year_from_title(robust_server, monkeypatch):
    """
    U02: Item JDIH tanpa nomor resmi lengkap, judul 'Nomor 18 Tahun 2025', tanggal berlaku 2026.
    Ekspektasi: regulation_number = 'POJK 18 Tahun 2025' (tahun diambil dari judul, bukan 2026).
    """
    base_url, srv = robust_server
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    guid = "406ece2b-a508-fc8c-31a4-c7a312908c2e"
    api_payload = {
        "sEcho": 1,
        "iTotalRecords": [1],
        "iTotalDisplayRecords": [1],
        "aaData": [
            [
                f"<a href='http://jdih.ojk.go.id/Web/ViewPeraturan/Detail/{guid}/All/'>Peraturan Otoritas Jasa Keuangan Nomor 18 Tahun 2025 tentang Transparansi</a>",
                "18",
                "Perbankan",
                None,
                None,
                "Peraturan OJK",
                "09-02-2026",
                "Berlaku"
            ]
        ]
    }
    import json
    srv.routes["/Web/ViewPeraturanHome/ListDataPeraturan"] = {
        "status": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(api_payload),
    }

    detail_html = f"""
    <html><body><table>
        <tr><th><h4>Tanggal Penetapan</h4></th><td>:</td><td>04-08-2025</td></tr>
        <tr><th><h4>Status Peraturan</h4></th><td>:</td><td>Berlaku Sejak Tanggal 09-02-2026</td></tr>
        <tr>
            <th><h4>Peraturan</h4></th>
            <td><a download href="/Web/ViewPeraturan/DownloadDokumen/att-pojk18" onclick="downloadDokumen('2025pojk018.pdf','~/Dokumen/2025pojk018.pdf')">Unduh</a></td>
        </tr>
    </table></body></html>
    """
    srv.routes[f"/Web/ViewPeraturan/Detail/{guid}/All/"] = {
        "status": 200,
        "headers": {"Content-Type": "text/html"},
        "body": detail_html,
    }

    crawler = JdihApiCrawler(allow_private=True, delay_seconds=0, head_for_size=False)
    res = crawler.scan(base_url, depth=1, max_pages=1)
    assert len(res.candidates) == 1
    cand = res.candidates[0]
    assert cand.regulation_number == "POJK 18 Tahun 2025"
    assert "2026" not in cand.regulation_number


def test_u03_match_warning_2025pojk018_no_warning():
    """
    U03: 2025pojk018.pdf vs regulasi 18/2025 -> Tanpa warning.
    """
    from app.crawlers.url_utils import validate_regulation_filename_match

    warn = validate_regulation_filename_match(
        filename="2025pojk018.pdf",
        regulation_number="POJK 18 Tahun 2025",
        release_date=date(2025, 8, 4),
        document_title="Peraturan Otoritas Jasa Keuangan Nomor 18 Tahun 2025",
        regulation_type="POJK",
    )
    assert warn is None


def test_u04_match_warning_real_mismatch_warning():
    """
    U04: Ringkasan POJK 4 Tahun 2023.pdf vs 23/POJK.04/2016 -> Warning.
    """
    from app.crawlers.url_utils import validate_regulation_filename_match

    warn = validate_regulation_filename_match(
        filename="Ringkasan POJK 4 Tahun 2023.pdf",
        regulation_number="23/POJK.04/2016",
        release_date=date(2016, 7, 14),
        document_title="Peraturan Otoritas Jasa Keuangan Nomor 23/POJK.04/2016",
        regulation_type="POJK",
    )
    assert warn is not None
    assert "2023" in warn and "2016" in warn
