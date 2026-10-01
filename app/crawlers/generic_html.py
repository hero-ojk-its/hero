"""
app/crawlers/generic_html.py
Implementasi GenericHtmlCrawler (evolusi SimpleHttpCrawler).
Mendukung:
- Paging link (1 2 3 ... terakhir, 1 2 ... 7 8 terakhir, Next, ?page=, dll.) tanpa memakan kedalaman.
- Deteksi loop paging berbasis hash isi halaman.
- Redirect hingga 10 hop dengan perlindungan SSRF di setiap hop + meta refresh & simple JS.
- Deteksi Captcha / Cloudflare / WAF (403/429/503 atau marker) dengan pelaporan error dan status blocked.
- Penanganan 429 Too Many Requests dengan Retry-After (maksimal 3 percobaan).
- Penentuan ukuran berkas via HEAD -> Range: bytes=0-0 tanpa mengunduh berkas utuh.
- Pelacakan statistik lengkap (requests_made, pages_visited, non_pdf_links, duration_seconds, pdfs_found).
PENTING: Modul ini TIDAK BOLEH mengimpor app.database, app.models, app.routers, app.services.
"""
import hashlib
import logging
import posixpath
import re
import time
from collections import deque
from html.parser import HTMLParser
from typing import Callable, Optional, List, Dict, Set, Tuple, Any
from urllib.parse import urlsplit, urlunsplit, urljoin, unquote
from urllib.robotparser import RobotFileParser

import httpx

from app.crawlers.base import (
    Crawler,
    PdfCandidate,
    ScanResult,
    FetchedFile,
    CrawlerError,
    BlockedUrlError,
    FetchTooLargeError,
)
from app.crawlers.url_utils import (
    normalize_url,
    is_pdf_link,
    guard_url,
    detect_captcha_or_waf,
    extract_meta_or_js_redirect,
    extract_filename_from_cd,
    determine_doc_kind,
)

logger = logging.getLogger("hero.crawler.generic")


class _HtmlLinkParser(HTMLParser):
    """Parser HTML untuk mengekstrak tautan <a> beserta atribut dan teksnya."""

    def __init__(self):
        super().__init__()
        self.links: List[Tuple[str, str, str]] = []  # (href, rel, text)
        self._current_href: Optional[str] = None
        self._current_rel: str = ""
        self._current_text: List[str] = []

    def handle_starttag(self, tag: str, attrs: list):
        if tag.lower() == "a":
            href = None
            rel = ""
            for k, v in attrs:
                if k.lower() == "href" and v:
                    href = v
                elif k.lower() == "rel" and v:
                    rel = v
            if href:
                self._current_href = href
                self._current_rel = rel
                self._current_text = []

    def handle_data(self, data: str):
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str):
        if tag.lower() == "a" and self._current_href is not None:
            text = "".join(self._current_text).strip()
            self.links.append((self._current_href, self._current_rel, text))
            self._current_href = None
            self._current_rel = ""
            self._current_text = []


def _get_directory_prefix(url_path: str) -> str:
    """Menghitung prefix direktori dari path URL, selalu diakhiri dengan /."""
    if not url_path or url_path == "/":
        return "/"
    if url_path.endswith("/"):
        return url_path
    dirname = posixpath.dirname(url_path)
    if not dirname.endswith("/"):
        dirname += "/"
    return dirname


def _is_paging_link(current_url: str, link_url: str, rel: str, link_text: str) -> bool:
    """
    Memeriksa apakah link merupakan tautan paging.
    - rel="next" / rel="prev".
    - Teks: angka, "next", "berikutnya", "terakhir", "last", "»", "›", ">", "halaman ...".
    - Query param: page, p, hal, halaman, pg, start, offset.
    - Path format: /page/2, /hal/2, dll.
    """
    curr_parsed = urlsplit(current_url)
    link_parsed = urlsplit(link_url)

    # 1. Cek rel
    rel_clean = rel.lower().split()
    if "next" in rel_clean or "prev" in rel_clean:
        return True

    # 2. Cek teks navigasi paging
    text_clean = link_text.strip().lower()
    if text_clean.isdigit():
        return True
    paging_keywords = {
        "next", "berikutnya", "selanjutnya", "halaman selanjutnya",
        "prev", "previous", "sebelumnya", "kembali",
        "terakhir", "last", "akhir", "awal", "first", "pertama",
        "»", "›", ">", "«", "‹", "<",
    }
    if text_clean in paging_keywords:
        return True
    if text_clean.startswith("halaman") or text_clean.startswith("page"):
        return True

    # 3. Cek parameter query paging pada path yang sama
    if curr_parsed.path == link_parsed.path:
        paging_keys = {"page", "p", "hal", "halaman", "start", "offset", "pg", "pagenumber", "pageindex"}
        query_keys = set(re.findall(r"([a-zA-Z0-9_-]+)=", link_parsed.query.lower()))
        if query_keys & paging_keys:
            return True

    # 4. Cek path format seperti /page/N
    if re.search(r"/(?:page|hal|halaman|p)/\d+", link_parsed.path, re.IGNORECASE):
        return True

    return False


class GenericHtmlCrawler:
    """Crawler HTML generik dengan pengecekan kasus lengkap (paging, redirect, captcha, size probing)."""

    name: str = "generic_html"

    def __init__(
        self,
        user_agent: str = "HERO-Capstone-Crawler/0.10 (+kontak: tim HERO)",
        delay_seconds: float = 0.5,
        timeout_seconds: int = 20,
        respect_robots: bool = True,
        allow_private: bool = False,
        head_for_size: bool = True,
    ):
        self.user_agent = user_agent
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.respect_robots = respect_robots
        self.allow_private = allow_private
        self.head_for_size = head_for_size
        self._last_request_time: Dict[str, float] = {}
        self.requests_count = 0

    def _rate_limit(self, host: str):
        """Terapkan jeda waktu sopan antar-request ke host yang sama."""
        if not host or self.delay_seconds <= 0:
            return
        last_t = self._last_request_time.get(host, 0.0)
        now = time.time()
        elapsed = now - last_t
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)
        self._last_request_time[host] = time.time()

    def _load_robots(self, client: httpx.Client, start_url: str) -> Optional[RobotFileParser]:
        """Memuat dan mem-parsing robots.txt dari root situs jika diaktifkan."""
        if not self.respect_robots:
            return None

        parsed = urlsplit(start_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            guard_url(robots_url, self.allow_private)
            self._rate_limit(parsed.hostname or "")
            self.requests_count += 1
            resp = client.get(
                robots_url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout_seconds,
            )
            if resp.status_code == 200:
                rfp = RobotFileParser()
                rfp.parse(resp.text.splitlines())
                return rfp
        except Exception as e:
            logger.debug(f"Gagal memuat robots.txt dari {robots_url}: {e}")
        return None

    def _request_with_redirect_guard(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        max_redirects: int = 10,
        stream: bool = False,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """
        Melakukan HTTP request dengan:
        - Perlindungan SSRF di setiap hop redirect.
        - Penanganan status 429 Too Many Requests (Retry-After maks 3x).
        - Ekstraksi meta refresh & simple JS redirect jika bukan HTTP redirect.
        """
        curr_url = url
        req_headers = {"User-Agent": self.user_agent}
        if headers:
            req_headers.update(headers)

        for hop in range(max_redirects + 1):
            guard_url(curr_url, self.allow_private)
            parsed = urlsplit(curr_url)
            self._rate_limit(parsed.hostname or "")

            # Retry loop untuk 429
            for retry_attempt in range(4):
                self.requests_count += 1
                req = client.build_request(
                    method,
                    curr_url,
                    headers=req_headers,
                    data=data if (method.upper() == "POST" and hop == 0) else None,
                    timeout=self.timeout_seconds,
                )
                resp = client.send(req, stream=stream)

                if resp.status_code == 429 and retry_attempt < 3:
                    retry_after_hdr = resp.headers.get("retry-after")
                    wait_sec = 2.0
                    if retry_after_hdr:
                        try:
                            wait_sec = min(float(retry_after_hdr), 60.0)
                        except ValueError:
                            wait_sec = 2.0
                    resp.close()
                    time.sleep(wait_sec)
                    continue
                break

            # 1. HTTP Redirect (301, 302, 303, 307, 308)
            if resp.is_redirect and "location" in resp.headers:
                loc = resp.headers["location"]
                curr_url = urljoin(curr_url, loc)
                resp.close()
                method = "GET"  # Standard redirect behaves as GET
                continue

            # 2. Cek Meta Refresh / Simple JS redirect pada respon HTML
            if not stream and "text/html" in resp.headers.get("content-type", "").lower() and resp.status_code == 200:
                meta_target = extract_meta_or_js_redirect(resp.text, curr_url)
                if meta_target and meta_target != curr_url and hop < max_redirects:
                    curr_url = meta_target
                    resp.close()
                    method = "GET"
                    continue

            return resp

        raise CrawlerError(f"Terlalu banyak redirect (> {max_redirects}) saat mengakses {url}")

    def probe_size_and_meta(
        self,
        client: httpx.Client,
        url: str,
    ) -> Tuple[Optional[int], Optional[str], str, str]:
        """
        Menentukan ukuran berkas dan nama berkas tanpa mengunduh berkas utuh:
        1. HEAD request -> cek Content-Length & Content-Disposition.
        2. Jika Content-Length tidak ada, fallback GET dengan Range: bytes=0-0 -> cek Content-Range.
        Mengembalikan: (size_bytes, filename, size_source, final_url).
        """
        final_url = url
        # 1. Coba HEAD request
        try:
            head_resp = self._request_with_redirect_guard(client, "HEAD", url)
            final_url = str(head_resp.url)
            cd_hdr = head_resp.headers.get("content-disposition", "")
            filename = extract_filename_from_cd(cd_hdr)

            if head_resp.status_code == 200:
                cl = head_resp.headers.get("content-length")
                if cl and cl.isdigit() and int(cl) > 0:
                    return int(cl), filename, "head", final_url
        except Exception as e:
            logger.debug(f"HEAD request gagal untuk {url}: {e}")

        # 2. Fallback GET dengan header Range: bytes=0-0 (streaming, tanpa download isi)
        try:
            range_resp = self._request_with_redirect_guard(
                client,
                "GET",
                url,
                stream=True,
                headers={"Range": "bytes=0-0"},
            )
            final_url = str(range_resp.url)
            cd_hdr = range_resp.headers.get("content-disposition", "")
            filename = filename or extract_filename_from_cd(cd_hdr)

            if range_resp.status_code == 206:
                # Partial content: baca Content-Range: bytes 0-0/123456
                cr = range_resp.headers.get("content-range", "")
                match = re.search(r"bytes\s+\d+-\d+/(\d+)", cr)
                range_resp.close()
                if match:
                    return int(match.group(1)), filename, "range", final_url
                return None, filename, "range", final_url
            elif range_resp.status_code == 200:
                # Server abaikan Range tapi kirim Content-Length
                cl = range_resp.headers.get("content-length")
                range_resp.close()
                if cl and cl.isdigit() and int(cl) > 0:
                    return int(cl), filename, "head", final_url
            else:
                range_resp.close()
        except Exception as e:
            logger.debug(f"Range request gagal untuk {url}: {e}")

        return None, None, "unknown", final_url

    def scan(
        self,
        url: str,
        depth: int,
        *,
        max_pages: int = 200,
        max_candidates: int = 5000,
        progress: Optional[Callable[[int, int], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> ScanResult:
        """Memindai URL awal secara BFS dan menemukan kandidat PDF."""
        start_time = time.time()
        self.requests_count = 0

        # 1. Validasi URL awal dan SSRF
        guard_url(url, self.allow_private)
        norm_start = normalize_url(url)
        start_parsed = urlsplit(norm_start)
        base_host = (start_parsed.hostname or "").lower()
        dir_prefix = _get_directory_prefix(start_parsed.path)

        visited_pages: Set[str] = set()
        visited_page_hashes: Set[str] = set()
        candidates_map: Dict[str, PdfCandidate] = {}
        errors: List[str] = []
        truncated = False
        blocked = False
        non_pdf_links = 0

        # Queue: list of (page_url, current_depth)
        queue: deque[Tuple[str, int]] = deque()
        queue.append((norm_start, 1))

        with httpx.Client(follow_redirects=False) as client:
            robots = self._load_robots(client, norm_start)

            # 2. Loop penjelajahan halaman (BFS)
            while queue and len(visited_pages) < max_pages:
                if should_cancel and should_cancel():
                    break

                page_url, page_depth = queue.popleft()
                if page_url in visited_pages:
                    continue

                # Cek robots.txt
                if robots and not robots.can_fetch(self.user_agent, page_url):
                    errors.append(f"Akses ke halaman '{page_url}' dilarang oleh robots.txt.")
                    continue

                visited_pages.add(page_url)
                if progress:
                    progress(len(visited_pages), len(candidates_map))

                # Ambil halaman HTML
                try:
                    resp = self._request_with_redirect_guard(client, "GET", page_url)
                except BlockedUrlError as bue:
                    errors.append(f"Halaman '{page_url}' diblokir keamanan (SSRF): {bue}")
                    continue
                except Exception as ex:
                    errors.append(f"Gagal membuka halaman '{page_url}': {ex}")
                    continue

                # 3. Deteksi Captcha / Cloudflare / WAF
                captcha_marker = detect_captcha_or_waf(resp.status_code, resp.headers, resp.text)
                if captcha_marker:
                    blocked = True
                    host_name = urlsplit(page_url).hostname or base_host
                    err_msg = (
                        f"terblokir_captcha: Host '{host_name}' mendeteksi proteksi/captcha "
                        f"({captcha_marker}) pada URL {page_url} (HTTP {resp.status_code})."
                    )
                    errors.append(err_msg)
                    logger.warning(f"[GenericCrawler] {err_msg}")
                    resp.close()
                    break  # Berhenti untuk host yang memblokir

                if resp.status_code != 200:
                    errors.append(f"HTTP {resp.status_code} saat membuka halaman '{page_url}'.")
                    resp.close()
                    continue

                content_type = resp.headers.get("content-type", "").lower()
                if "text/html" not in content_type:
                    non_pdf_links += 1
                    resp.close()
                    continue

                # Deteksi loop paging berdasarkan hash konten
                page_body = resp.text
                page_hash = hashlib.sha256(page_body.encode("utf-8")).hexdigest()
                if page_hash in visited_page_hashes:
                    logger.debug(f"Halaman duplikat/loop terdeteksi ({page_url}), mengabaikan tautan.")
                    continue
                visited_page_hashes.add(page_hash)

                # Parse tautan dalam HTML
                parser = _HtmlLinkParser()
                try:
                    parser.feed(page_body)
                except Exception as parse_err:
                    errors.append(f"Gagal mem-parsing HTML dari '{page_url}': {parse_err}")
                    continue

                for href, rel, link_text in parser.links:
                    abs_url = urljoin(page_url, href)
                    norm_link = normalize_url(abs_url)
                    if not norm_link:
                        continue

                    # 2a. Deteksi jika link adalah berkas PDF
                    if is_pdf_link(abs_url, link_text):
                        try:
                            guard_url(norm_link, self.allow_private)
                        except BlockedUrlError as b_err:
                            errors.append(f"Tautan PDF '{norm_link}' diblokir keamanan (SSRF): {b_err}")
                            continue

                        if norm_link not in candidates_map:
                            if len(candidates_map) >= max_candidates:
                                truncated = True
                                break

                            raw_filename = unquote(posixpath.basename(urlsplit(norm_link).path))
                            if not raw_filename or not raw_filename.lower().endswith(".pdf"):
                                raw_filename = f"{link_text.strip() or 'dokumen'}.pdf"

                            title = link_text.strip() if link_text.strip() else raw_filename
                            kind = determine_doc_kind(raw_filename)

                            cand = PdfCandidate(
                                url=norm_link,
                                filename=raw_filename,
                                size_bytes=None,
                                found_on_page=page_url,
                                depth=page_depth,
                                document_title=title,
                                detail_url=page_url,
                                final_url=norm_link,
                                doc_kind=kind,
                                size_source="unknown",
                            )
                            candidates_map[norm_link] = cand

                    # 2b. Deteksi jika link adalah halaman HTML lain untuk ditelusuri
                    else:
                        link_parsed = urlsplit(norm_link)
                        link_host = (link_parsed.hostname or "").lower()

                        # Hanya ikuti halaman di host yang sama
                        if link_host != base_host:
                            continue

                        # Hanya ikuti halaman di bawah prefix direktori URL awal
                        if not link_parsed.path.startswith(dir_prefix):
                            continue

                        # Tentukan kedalaman berikutnya (paging tidak memakan kedalaman)
                        is_paging = _is_paging_link(page_url, norm_link, rel, link_text)
                        next_depth = page_depth if is_paging else (page_depth + 1)

                        if next_depth <= depth and norm_link not in visited_pages:
                            queue.append((norm_link, next_depth))

                if len(candidates_map) >= max_candidates:
                    truncated = True
                    break

            if len(visited_pages) >= max_pages and queue:
                truncated = True

            # 4. Probe ukuran berkas PDF via HEAD / Range: bytes=0-0 jika diaktifkan
            if self.head_for_size and candidates_map and not blocked:
                for cand_url, cand in list(candidates_map.items()):
                    if should_cancel and should_cancel():
                        break
                    try:
                        size, cd_filename, size_src, final_u = self.probe_size_and_meta(client, cand_url)
                        final_name = cd_filename if cd_filename else cand.filename
                        candidates_map[cand_url] = PdfCandidate(
                            url=cand.url,
                            filename=final_name,
                            size_bytes=size,
                            found_on_page=cand.found_on_page,
                            depth=cand.depth,
                            document_title=cand.document_title,
                            detail_url=cand.detail_url,
                            final_url=final_u or cand.final_url,
                            doc_kind=cand.doc_kind,
                            regulation_number=cand.regulation_number,
                            regulation_type=cand.regulation_type,
                            bidang=cand.bidang,
                            sub_bidang=cand.sub_bidang,
                            release_date=cand.release_date,
                            size_source=size_src,
                            source_path=cand.source_path,
                        )
                    except Exception as probe_err:
                        logger.debug(f"Size probe gagal untuk {cand_url}: {probe_err}")
                        continue

        duration_sec = round(time.time() - start_time, 2)
        candidates_list = list(candidates_map.values())

        # Hitung statistik per doc_kind
        doc_kinds_count: Dict[str, int] = {}
        for c in candidates_list:
            k = c.doc_kind or "utama"
            doc_kinds_count[k] = doc_kinds_count.get(k, 0) + 1

        stats = {
            "regulations_found": len(candidates_list),
            "pdfs_found": len(candidates_list),
            "by_doc_kind": doc_kinds_count,
            "pages_visited": len(visited_pages),
            "requests_made": self.requests_count,
            "non_pdf_links": non_pdf_links,
            "duration_seconds": duration_sec,
        }

        return ScanResult(
            candidates=candidates_list,
            pages_visited=len(visited_pages),
            errors=errors,
            truncated=truncated,
            blocked=blocked,
            stats=stats,
        )

    def fetch(self, url: str, *, max_bytes: int = 100 * 1024 * 1024) -> FetchedFile:
        """Mengunduh berkas dari URL secara streaming dengan batasan ukuran dan proteksi SSRF."""
        guard_url(url, self.allow_private)

        with httpx.Client(follow_redirects=False) as client:
            resp = self._request_with_redirect_guard(client, "GET", url, stream=True)

            if resp.status_code >= 400:
                resp.close()
                raise CrawlerError(f"HTTP {resp.status_code} saat mengunduh berkas dari {url}")

            content_chunks = []
            total_bytes = 0

            try:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        resp.close()
                        raise FetchTooLargeError(
                            f"Ukuran berkas ({total_bytes} bytes) melebihi batas maksimal {max_bytes} bytes."
                        )
                    content_chunks.append(chunk)
            finally:
                resp.close()

            content = b"".join(content_chunks)
            content_type = resp.headers.get("content-type")

            # Tentukan nama file dari Content-Disposition atau URL path
            cd_header = resp.headers.get("content-disposition", "")
            filename = extract_filename_from_cd(cd_header)
            if not filename:
                filename = unquote(posixpath.basename(urlsplit(str(resp.url)).path))
            if not filename or not filename.lower().endswith(".pdf"):
                filename = "dokumen.pdf"

            return FetchedFile(
                content=content,
                filename=filename,
                final_url=str(resp.url),
                content_type=content_type,
            )


# Alias untuk backwards compatibility
SimpleHttpCrawler = GenericHtmlCrawler
