"""
app/crawlers/jdih_api.py
Crawler adapter untuk situs JDIH OJK (https://jdih.ojk.go.id/) berbasis API JSON DataTables.
Mendukung:
- Pemanggilan langsung ke endpoint /Web/ViewPeraturanHome/ListDataPeraturan via httpx.
- Paginasi iDisplayStart/iDisplayLength sampai seluruh data terindeks.
- Ekstraksi metadata: judul, nomor, jenis, tanggal rilis, bidang (sektor), URL detail, dan URL unduh PDF.
- Penentuan ukuran berkas via HEAD / Range.
PENTING: Modul ini TIDAK BOLEH mengimpor app.database, app.models, app.routers, app.services.
"""
import hashlib
import html
import logging
import posixpath
import re
import ssl
import time
from datetime import date
from typing import Callable, Optional, List, Dict, Set, Tuple, Any
from urllib.parse import urlsplit, urlunsplit, urljoin, unquote

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
    guard_url,
    detect_captcha_or_waf,
    extract_filename_from_cd,
    determine_doc_kind,
    normalize_crawler_regulation_type,
)

logger = logging.getLogger("hero.crawler.jdih_api")


def _parse_jdih_date(raw_text: str) -> Optional[date]:
    """Mengekstrak tanggal dari string JDIH seperti '07-07-2026' atau '2026-07-07'."""
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    # Format DD-MM-YYYY
    dm_m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", cleaned)
    if dm_m:
        try:
            return date(int(dm_m.group(3)), int(dm_m.group(2)), int(dm_m.group(1)))
        except ValueError:
            pass

    # Format YYYY-MM-DD
    iso_m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", cleaned)
    if iso_m:
        try:
            return date(int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3)))
        except ValueError:
            pass

    return None


class JdihApiCrawler:
    """Crawler adapter untuk JDIH OJK via API JSON."""

    name: str = "jdih_api"

    def __init__(
        self,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        delay_seconds: float = 0.5,
        timeout_seconds: int = 25,
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

    def _get_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        try:
            ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        except Exception:
            pass
        return ctx

    def _rate_limit(self, host: str):
        if not host or self.delay_seconds <= 0:
            return
        last_t = self._last_request_time.get(host, 0.0)
        now = time.time()
        elapsed = now - last_t
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)
        self._last_request_time[host] = time.time()

    def _probe_pdf_size(
        self,
        client: httpx.Client,
        pdf_url: str,
    ) -> Tuple[Optional[int], Optional[str], str]:
        """Menentukan ukuran berkas via HEAD / Range."""
        try:
            head_resp = client.head(
                pdf_url,
                headers={"User-Agent": self.user_agent, "Referer": "https://jdih.ojk.go.id/"},
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            self.requests_count += 1
            if head_resp.status_code == 200:
                cd_name = extract_filename_from_cd(head_resp.headers.get("content-disposition"))
                cl = head_resp.headers.get("content-length")
                if cl and cl.isdigit() and int(cl) > 0:
                    return int(cl), cd_name, "head"
        except Exception:
            pass

        try:
            range_resp = client.get(
                pdf_url,
                headers={
                    "User-Agent": self.user_agent,
                    "Range": "bytes=0-0",
                    "Referer": "https://jdih.ojk.go.id/",
                },
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            self.requests_count += 1
            cd_name = extract_filename_from_cd(range_resp.headers.get("content-disposition"))
            if range_resp.status_code == 206:
                cr = range_resp.headers.get("content-range", "")
                m = re.search(r"bytes\s+\d+-\d+/(\d+)", cr)
                size = int(m.group(1)) if m else None
                return size, cd_name, "range" if size else "unknown"
            elif range_resp.status_code == 200:
                cl = range_resp.headers.get("content-length")
                size = int(cl) if cl and cl.isdigit() else None
                return size, cd_name, "head" if size else "unknown"
        except Exception:
            pass

        return None, None, "unknown"

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
        start_time = time.time()
        self.requests_count = 0
        guard_url(url, self.allow_private)

        base_parsed = urlsplit(url)
        base_host = (base_parsed.hostname or "jdih.ojk.go.id").lower()
        netloc = base_parsed.netloc or "jdih.ojk.go.id"
        base_scheme = base_parsed.scheme or "https"
        api_base = f"{base_scheme}://{netloc}"

        ssl_ctx = self._get_ssl_context()
        visited_pages: Set[str] = set()
        candidates_map: Dict[str, PdfCandidate] = {}
        regulations_count = 0
        errors: List[str] = []
        truncated = False
        blocked = False
        non_pdf_links = 0

        page_size = 50
        display_start = 0
        echo_counter = 1

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{api_base}/",
        }

        with httpx.Client(verify=ssl_ctx, http2=False, timeout=self.timeout_seconds) as client:
            while display_start < 5000 and len(visited_pages) < max_pages:
                if should_cancel and should_cancel():
                    break
                if len(candidates_map) >= max_candidates:
                    truncated = True
                    break

                api_url = (
                    f"{api_base}/Web/ViewPeraturanHome/ListDataPeraturan"
                    f"?sektor=All&jenisPeraturan=&sLanguage=ID"
                    f"&iDisplayStart={display_start}&iDisplayLength={page_size}&sEcho={echo_counter}"
                )

                self._rate_limit(base_host)
                try:
                    self.requests_count += 1
                    resp = client.get(api_url, headers=headers)
                except Exception as ex:
                    errors.append(f"Gagal memanggil API JDIH pada offset {display_start}: {ex}")
                    break

                c_marker = detect_captcha_or_waf(resp.status_code, resp.headers, resp.text)
                if c_marker:
                    blocked = True
                    errors.append(f"terblokir_captcha: Proteksi ({c_marker}) terdeteksi saat mengakses JDIH API.")
                    break

                if resp.status_code != 200:
                    errors.append(f"HTTP {resp.status_code} saat mengakses JDIH API pada offset {display_start}.")
                    break

                visited_pages.add(f"offset_{display_start}")

                try:
                    data = resp.json()
                except Exception as json_err:
                    errors.append(f"Gagal mem-parsing JSON JDIH pada offset {display_start}: {json_err}")
                    break

                # Baca total records
                total_rec_raw = data.get("iTotalRecords", 0)
                if isinstance(total_rec_raw, list) and total_rec_raw:
                    total_records = int(total_rec_raw[0])
                else:
                    total_records = int(total_rec_raw or 0)

                rows = data.get("aaData", [])
                if not rows:
                    logger.info(f"[JdihApiCrawler] Tidak ada data lagi pada offset {display_start}.")
                    break

                for row in rows:
                    if should_cancel and should_cancel():
                        break
                    if len(candidates_map) >= max_candidates:
                        truncated = True
                        break

                    # Kolom 0: HTML tautan detail <a href='...Detail/{guid}/All/'>Judul Regulasi</a>
                    col0 = str(row[0]) if len(row) > 0 and row[0] is not None else ""
                    guid_m = re.search(r"Detail/([a-f0-9-]+)/", col0, re.IGNORECASE)
                    title_m = re.search(r">([^<]+)</a>", col0, re.DOTALL)
                    if not guid_m:
                        # Fallback cari GUID di seluruh row
                        row_str = " ".join(str(c) for c in row)
                        guid_m = re.search(r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})", row_str, re.IGNORECASE)

                    if not guid_m:
                        continue

                    guid = guid_m.group(1)
                    raw_title = html.unescape(title_m.group(1)).strip() if title_m else re.sub(r"<[^>]+>", "", col0).strip()
                    doc_title = raw_title or f"Regulasi JDIH {guid}"

                    # Kolom 1: Nomor regulasi
                    reg_num = str(row[1]).strip() if len(row) > 1 and row[1] is not None else None
                    if reg_num in ("None", "", "-"):
                        reg_num = None

                    # Kolom 2: Sektor -> bidang
                    bidang = str(row[2]).strip() if len(row) > 2 and row[2] is not None else None
                    if bidang in ("None", "", "-"):
                        bidang = None

                    # Kolom 5: Jenis regulasi
                    raw_jenis = str(row[5]).strip() if len(row) > 5 and row[5] is not None else None
                    reg_type = normalize_crawler_regulation_type(raw_jenis) if raw_jenis and raw_jenis != "None" else None

                    # Kolom 6: Tanggal rilis
                    raw_date = str(row[6]).strip() if len(row) > 6 and row[6] is not None else None
                    rel_date = _parse_jdih_date(raw_date) if raw_date and raw_date != "None" else None

                    # URL unduh langsung dan URL detail
                    pdf_url = f"{api_base}/Web/ViewPeraturan/DownloadDokumen/{guid}"
                    norm_pdf_url = normalize_url(pdf_url)
                    detail_url = f"{api_base}/Web/ViewPeraturan/Detail/{guid}/All/"

                    if norm_pdf_url in candidates_map:
                        continue

                    # Probe ukuran dan nama berkas asli dari Content-Disposition jika diaktifkan
                    size_b, cd_fn, size_src = (None, None, "unknown")
                    if self.head_for_size:
                        size_b, cd_fn, size_src = self._probe_pdf_size(client, norm_pdf_url)

                    # Default filename dari title/nomor atau CD
                    default_fn = cd_fn
                    if not default_fn:
                        safe_stem = re.sub(r'[\\/*?:"<>|]', '_', doc_title).strip()
                        default_fn = f"{safe_stem[:100]}.pdf"

                    doc_k = determine_doc_kind(default_fn)

                    cand = PdfCandidate(
                        url=norm_pdf_url,
                        filename=default_fn,
                        size_bytes=size_b,
                        found_on_page=detail_url,
                        depth=1,
                        document_title=doc_title,
                        detail_url=detail_url,
                        final_url=norm_pdf_url,
                        doc_kind=doc_k,
                        regulation_number=reg_num,
                        regulation_type=reg_type,
                        bidang=bidang,
                        sub_bidang=None,
                        release_date=rel_date,
                        size_source=size_src,
                    )
                    candidates_map[norm_pdf_url] = cand
                    regulations_count += 1

                    if progress:
                        progress(len(visited_pages), len(candidates_map))

                display_start += len(rows)
                echo_counter += 1

                if display_start >= total_records:
                    break

        duration_sec = round(time.time() - start_time, 2)
        cand_list = list(candidates_map.values())
        doc_kinds: Dict[str, int] = {}
        for c in cand_list:
            k = c.doc_kind or "utama"
            doc_kinds[k] = doc_kinds.get(k, 0) + 1

        stats = {
            "regulations_found": regulations_count,
            "pdfs_found": len(cand_list),
            "by_doc_kind": doc_kinds,
            "pages_visited": len(visited_pages),
            "requests_made": self.requests_count,
            "non_pdf_links": non_pdf_links,
            "duration_seconds": duration_sec,
        }

        return ScanResult(
            candidates=cand_list,
            pages_visited=len(visited_pages),
            errors=errors,
            truncated=truncated,
            blocked=blocked,
            stats=stats,
        )

    def fetch(self, url: str, *, max_bytes: int = 100 * 1024 * 1024) -> FetchedFile:
        guard_url(url, self.allow_private)
        ssl_ctx = self._get_ssl_context()

        with httpx.Client(verify=ssl_ctx, http2=False, timeout=self.timeout_seconds) as client:
            resp = client.get(
                url,
                headers={"User-Agent": self.user_agent, "Referer": "https://jdih.ojk.go.id/"},
                follow_redirects=True,
            )
            if resp.status_code >= 400:
                resp.close()
                raise CrawlerError(f"HTTP {resp.status_code} saat mengunduh berkas dari {url}")

            content = resp.content
            if len(content) > max_bytes:
                raise FetchTooLargeError(
                    f"Ukuran berkas ({len(content)} bytes) melebihi batas maksimal {max_bytes} bytes."
                )

            cd_name = extract_filename_from_cd(resp.headers.get("content-disposition"))
            filename = cd_name or unquote(posixpath.basename(urlsplit(str(resp.url)).path)) or "dokumen.pdf"

            return FetchedFile(
                content=content,
                filename=filename,
                final_url=str(resp.url),
                content_type=resp.headers.get("content-type"),
            )
