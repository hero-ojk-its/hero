"""
app/crawlers/simple_http.py
Implementasi SimpleHttpCrawler menggunakan httpx dan parser standar Python.
PENTING: Modul ini TIDAK BOLEH mengimpor app.database, app.models, app.routers, app.services.
"""
import logging
import posixpath
import re
import time
from collections import deque
from html.parser import HTMLParser
from typing import Callable, Optional, List, Dict, Set, Tuple
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
from app.crawlers.url_utils import normalize_url, is_pdf_link, guard_url

logger = logging.getLogger("hero.crawler")


class _HtmlLinkParser(HTMLParser):
    """Parser HTML sederhana untuk mengekstrak tautan <a> beserta atribut dan teksnya."""

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


def _extract_filename_from_cd(cd_header: str) -> Optional[str]:
    """Mengekstrak nama file dari header Content-Disposition."""
    if not cd_header:
        return None
    # Cari format filename*=UTF-8''...
    match_star = re.search(r"filename\*\s*=\s*UTF-8''([^;\s]+)", cd_header, re.IGNORECASE)
    if match_star:
        return unquote(match_star.group(1))
    # Cari format filename="..." atau filename=...
    match = re.search(r'filename\s*=\s*(?:"([^"]+)"|([^;\s]+))', cd_header, re.IGNORECASE)
    if match:
        raw_name = match.group(1) or match.group(2)
        return unquote(raw_name)
    return None


def _is_paging_link(current_url: str, link_url: str, rel: str, link_text: str) -> bool:
    """
    Memeriksa apakah link merupakan tautan paging pada level yang sama.
    - Path sama, berbeda pada query param (page, p, hal, halaman, start, offset, pg).
    - ATAU rel="next" / rel="prev".
    - ATAU link_text adalah angka atau kata kunci navigasi paging.
    """
    curr_parsed = urlsplit(current_url)
    link_parsed = urlsplit(link_url)

    # Cek rel="next"
    if "next" in rel.lower().split():
        return True

    # Cek teks navigasi paging
    text_clean = link_text.strip().lower()
    if text_clean.isdigit():
        return True
    if text_clean in ("next", "berikutnya", "»", "›", ">", "halaman selanjutnya", "selanjutnya"):
        return True

    # Cek parameter query paging pada path yang sama
    if curr_parsed.path == link_parsed.path:
        paging_keys = {"page", "p", "hal", "halaman", "start", "offset", "pg"}
        query_keys = set(re.findall(r"([a-zA-Z0-9_-]+)=", link_parsed.query.lower()))
        if query_keys & paging_keys:
            return True

    return False


class SimpleHttpCrawler:
    """Crawler HTTP bawaan berbasis httpx, html.parser, dan urllib.robotparser."""

    name: str = "simple_http"

    def __init__(
        self,
        user_agent: str = "HERO-Capstone-Crawler/0.7 (+kontak: tim HERO)",
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
        max_redirects: int = 5,
        stream: bool = False,
    ) -> httpx.Response:
        """Melakukan HTTP request dengan perlindungan SSRF pada setiap redirect hop."""
        curr_url = url
        for _ in range(max_redirects + 1):
            guard_url(curr_url, self.allow_private)
            parsed = urlsplit(curr_url)
            self._rate_limit(parsed.hostname or "")

            req = client.build_request(
                method,
                curr_url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout_seconds,
            )
            resp = client.send(req, stream=stream)

            if resp.is_redirect and "location" in resp.headers:
                loc = resp.headers["location"]
                curr_url = urljoin(curr_url, loc)
                resp.close()
                continue
            return resp

        raise CrawlerError(f"Terlalu banyak redirect (> {max_redirects}) saat mengakses {url}")

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
        # 1. Validasi URL awal dan SSRF
        guard_url(url, self.allow_private)
        norm_start = normalize_url(url)
        start_parsed = urlsplit(norm_start)
        base_host = (start_parsed.hostname or "").lower()
        dir_prefix = _get_directory_prefix(start_parsed.path)

        visited_pages: Set[str] = set()
        candidates_map: Dict[str, PdfCandidate] = {}
        errors: List[str] = []
        truncated = False

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

                if resp.status_code != 200:
                    errors.append(f"HTTP {resp.status_code} saat membuka halaman '{page_url}'.")
                    continue

                content_type = resp.headers.get("content-type", "").lower()
                if "text/html" not in content_type:
                    continue

                # Parse tautan dalam HTML
                parser = _HtmlLinkParser()
                try:
                    parser.feed(resp.text)
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

                            # Ekstrak nama file default dari URL path
                            raw_filename = unquote(posixpath.basename(urlsplit(norm_link).path))
                            if not raw_filename or not raw_filename.lower().endswith(".pdf"):
                                raw_filename = f"{link_text.strip() or 'dokumen'}.pdf"

                            cand = PdfCandidate(
                                url=norm_link,
                                filename=raw_filename,
                                size_bytes=None,
                                found_on_page=page_url,
                                depth=page_depth,
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

                        # Tentukan kedalaman berikutnya
                        is_paging = _is_paging_link(page_url, norm_link, rel, link_text)
                        next_depth = page_depth if is_paging else (page_depth + 1)

                        if next_depth <= depth and norm_link not in visited_pages:
                            queue.append((norm_link, next_depth))

                if len(candidates_map) >= max_candidates:
                    truncated = True
                    break

            if len(visited_pages) >= max_pages and queue:
                truncated = True

            # 3. HEAD request untuk mengambil Content-Length & Content-Disposition jika diaktifkan
            if self.head_for_size and candidates_map:
                for cand_url, cand in list(candidates_map.items()):
                    if should_cancel and should_cancel():
                        break
                    try:
                        head_resp = self._request_with_redirect_guard(client, "HEAD", cand_url)
                        if head_resp.status_code == 200:
                            content_len = head_resp.headers.get("content-length")
                            size = int(content_len) if content_len and content_len.isdigit() else None
                            cd_header = head_resp.headers.get("content-disposition", "")
                            cd_filename = _extract_filename_from_cd(cd_header)
                            final_name = cd_filename if cd_filename else cand.filename

                            candidates_map[cand_url] = PdfCandidate(
                                url=cand.url,
                                filename=final_name,
                                size_bytes=size,
                                found_on_page=cand.found_on_page,
                                depth=cand.depth,
                            )
                    except Exception as head_err:
                        logger.debug(f"HEAD request gagal untuk {cand_url}: {head_err}")
                        continue

        return ScanResult(
            candidates=list(candidates_map.values()),
            pages_visited=len(visited_pages),
            errors=errors,
            truncated=truncated,
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
            filename = _extract_filename_from_cd(cd_header)
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
