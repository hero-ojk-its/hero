"""
tests/test_crawler_simple.py
Pengujian untuk SimpleHttpCrawler dan integrasi external_module (K01, K02, K03, K04, K18).
Menggunakan mock HTTP server lokal berbasis thread tanpa koneksi internet luar.
"""
import http.server
import threading
from urllib.parse import urlparse
import pytest
from app.config import settings
from app.crawlers.simple_http import SimpleHttpCrawler
from app.crawlers.registry import get_crawler
from tests.conftest import make_pdf


class MockSiteHandler(http.server.BaseHTTPRequestHandler):
    """Handler HTTP tiruan untuk menguji seluruh skenario crawling situs."""

    def log_message(self, format, *args):
        pass  # Sunyikan log HTTP server saat test berjalan

    def do_HEAD(self):
        self._handle_request(is_head=True)

    def do_GET(self):
        self._handle_request(is_head=False)

    def _handle_request(self, is_head: bool):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parsed.query

        # 1. robots.txt
        if path == "/robots.txt":
            content = b"User-agent: *\nDisallow: /regulasi/rahasia/\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if not is_head:
                self.wfile.write(content)
            return

        # 2. Halaman Index Regulasi
        if path == "/regulasi/index.html" or path == "/regulasi/":
            if query == "page=2":
                html = (
                    "<html><body>"
                    "<a href='/regulasi/c.pdf'>Unduh C</a>"
                    "<a href='/regulasi/index.html?page=3'>Berikutnya</a>"
                    "</body></html>"
                )
            elif query == "page=3":
                html = (
                    "<html><body>"
                    "<a href='/regulasi/e.pdf'>Unduh E</a>"
                    "</body></html>"
                )
            else:
                html = (
                    "<html><body>"
                    "<a href='/regulasi/a.pdf'>Peraturan A</a>"
                    "<a href='/regulasi/b.pdf'>Peraturan B</a>"
                    "<a href='/regulasi/a.pdf'>Peraturan A Duplikat Link</a>"
                    "<a href='/regulasi/index.html?page=2'>Halaman 2</a>"
                    "<a href='/regulasi/detail/x.html'>Detail X</a>"
                    "<a href='/berita/luar.html'>Berita Luar</a>"
                    "<a href='http://host-lain.invalid/z.pdf'>Host Lain Z</a>"
                    "<a href='/regulasi/dok.docx'>Dokumen Word</a>"
                    "<a href='/regulasi/besar.pdf'>PDF Berukuran Besar</a>"
                    "<a href='/regulasi/hilang.pdf'>PDF Tidak Ditemukan</a>"
                    "<a href='/regulasi/alih.pdf'>PDF Dialihkan</a>"
                    "<a href='/regulasi/rahasia/r.html'>Regulasi Rahasia</a>"
                    "</body></html>"
                )
            content = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if not is_head:
                self.wfile.write(content)
            return

        # 3. Halaman Detail X (Depth 2)
        if path == "/regulasi/detail/x.html":
            html = "<html><body><a href='/regulasi/d.pdf'>Peraturan D</a></body></html>"
            content = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if not is_head:
                self.wfile.write(content)
            return

        # 4. Halaman Berita Luar (di luar prefix path /regulasi/)
        if path == "/berita/luar.html":
            html = "<html><body><a href='/berita/f.pdf'>Peraturan F</a></body></html>"
            content = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if not is_head:
                self.wfile.write(content)
            return

        # 5. Halaman Rahasia (dilarang robots.txt)
        if path == "/regulasi/rahasia/r.html":
            html = "<html><body><a href='/regulasi/r.pdf'>Peraturan R</a></body></html>"
            content = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if not is_head:
                self.wfile.write(content)
            return

        # 6. Redirect alih.pdf -> a2.pdf
        if path == "/regulasi/alih.pdf":
            self.send_response(302)
            self.send_header("Location", "/regulasi/a2.pdf")
            self.end_headers()
            return

        # 7. File Hilang (404)
        if path == "/regulasi/hilang.pdf":
            # Periksa flag apakah hilang.pdf sudah 'muncul' kembali
            if getattr(self.server, "serve_hilang_pdf", False):
                pdf_bytes = make_pdf("Hilang PDF Content Now Available")
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(pdf_bytes)))
                self.send_header("Content-Disposition", 'attachment; filename="hilang.pdf"')
                self.end_headers()
                if not is_head:
                    self.wfile.write(pdf_bytes)
                return

            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            if not is_head:
                self.wfile.write(b"Not Found")
            return

        # 8. File Word (bukan PDF)
        if path == "/regulasi/dok.docx":
            content = b"Fake Word Content"
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if not is_head:
                self.wfile.write(content)
            return

        # 9. Berkas PDF Valid
        pdf_names = ["a.pdf", "b.pdf", "c.pdf", "d.pdf", "e.pdf", "f.pdf", "r.pdf", "a2.pdf", "besar.pdf"]
        for p_name in pdf_names:
            if path == f"/regulasi/{p_name}" or path == f"/berita/{p_name}":
                if p_name == "besar.pdf":
                    # Buat PDF besar (misal: 60 KB untuk pengujian max_upload_bytes)
                    pdf_bytes = make_pdf("Large PDF Content " * 3000)
                else:
                    pdf_bytes = make_pdf(f"Unique PDF Content for {p_name}")

                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(pdf_bytes)))
                self.send_header("Content-Disposition", f'attachment; filename="{p_name}"')
                self.end_headers()
                if not is_head:
                    self.wfile.write(pdf_bytes)
                return

        # Fallback 404
        self.send_response(404)
        self.end_headers()


@pytest.fixture(scope="module")
def mock_http_server():
    """Menjalankan HTTP server pengujian di thread latar belakang."""
    server = http.server.HTTPServer(("127.0.0.1", 0), MockSiteHandler)
    server.serve_hilang_pdf = False
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    yield base_url, server

    server.shutdown()
    server.server_close()


def test_k01_crawler_scan_depth_1(mock_http_server):
    """K01: Pindai depth 1 menemukan a, b, c, e (paging tanpa nambah depth), besar, hilang, alih/a2 tanpa d, f, r."""
    base_url, _ = mock_http_server
    crawler = SimpleHttpCrawler(
        delay_seconds=0,
        allow_private=True,
        respect_robots=True,
        head_for_size=True,
    )

    result = crawler.scan(f"{base_url}/regulasi/index.html", depth=1)

    candidate_filenames = {c.filename for c in result.candidates}

    # a, b, c, e, besar, hilang, a2 harus ada
    assert "a.pdf" in candidate_filenames
    assert "b.pdf" in candidate_filenames
    assert "c.pdf" in candidate_filenames
    assert "e.pdf" in candidate_filenames
    assert "besar.pdf" in candidate_filenames
    assert "hilang.pdf" in candidate_filenames
    assert "a2.pdf" in candidate_filenames  # hasil redirect dari alih.pdf

    # d.pdf (depth 2), f.pdf (luar prefix), r.pdf (robots), dok.docx TIDAK boleh ada
    assert "d.pdf" not in candidate_filenames
    assert "f.pdf" not in candidate_filenames
    assert "r.pdf" not in candidate_filenames
    assert "dok.docx" not in candidate_filenames

    # a.pdf hanya muncul 1 kali (dedup URL)
    a_candidates = [c for c in result.candidates if c.filename == "a.pdf"]
    assert len(a_candidates) == 1

    # c.pdf dan e.pdf memiliki depth=1 karena merupakan hasil paging
    c_cand = next(c for c in result.candidates if c.filename == "c.pdf")
    e_cand = next(c for c in result.candidates if c.filename == "e.pdf")
    assert c_cand.depth == 1
    assert e_cand.depth == 1


def test_k02_crawler_scan_depth_2(mock_http_server):
    """K02: Pindai depth 2 menambahkan d.pdf, tetap tanpa f.pdf dan r.pdf (dicatat di errors)."""
    base_url, _ = mock_http_server
    crawler = SimpleHttpCrawler(
        delay_seconds=0,
        allow_private=True,
        respect_robots=True,
        head_for_size=True,
    )

    result = crawler.scan(f"{base_url}/regulasi/index.html", depth=2)
    candidate_filenames = {c.filename for c in result.candidates}

    assert "d.pdf" in candidate_filenames
    assert "f.pdf" not in candidate_filenames  # Di luar prefix path /regulasi/
    assert "r.pdf" not in candidate_filenames  # Dilarang robots.txt

    # r.html harus tercatat di errors karena robots.txt
    assert any("robots.txt" in err for err in result.errors)


def test_k03_crawler_head_for_size(mock_http_server):
    """K03: size_bytes terisi dari HEAD request; jika crawl_head_for_size=False maka bernilai None."""
    base_url, _ = mock_http_server

    # 1. Dengan HEAD
    crawler_with_head = SimpleHttpCrawler(
        delay_seconds=0,
        allow_private=True,
        head_for_size=True,
    )
    res_head = crawler_with_head.scan(f"{base_url}/regulasi/index.html", depth=1)
    a_cand = next(c for c in res_head.candidates if c.filename == "a.pdf")
    assert a_cand.size_bytes is not None
    assert a_cand.size_bytes > 0

    # 2. Tanpa HEAD
    crawler_no_head = SimpleHttpCrawler(
        delay_seconds=0,
        allow_private=True,
        head_for_size=False,
    )
    res_no_head = crawler_no_head.scan(f"{base_url}/regulasi/index.html", depth=1)
    a_cand_no = next(c for c in res_no_head.candidates if c.filename == "a.pdf")
    assert a_cand_no.size_bytes is None


def test_k04_crawler_max_pages_truncated(mock_http_server):
    """K04: max_pages=2 membatasi kunjungan halaman dan menghasilkan truncated=True."""
    base_url, _ = mock_http_server
    crawler = SimpleHttpCrawler(
        delay_seconds=0,
        allow_private=True,
    )

    result = crawler.scan(f"{base_url}/regulasi/index.html", depth=1, max_pages=2)
    assert result.pages_visited <= 2
    assert result.truncated is True


def test_k18_external_module_crawler(monkeypatch):
    """K18: external_module memuat kelas crawler dari tests.dummy_crawler:DummyCustomCrawler."""
    monkeypatch.setattr(settings, "crawler_backend", "external_module")
    monkeypatch.setattr(settings, "crawler_module", "tests.dummy_crawler:DummyCustomCrawler")

    crawler = get_crawler(settings)
    assert crawler is not None
    assert crawler.name == "dummy_custom_crawler"

    res = crawler.scan("http://example.com/test", depth=1)
    assert len(res.candidates) == 1
    assert res.candidates[0].filename == "dummy_custom_pdf" or res.candidates[0].filename == "dummy_custom.pdf"
