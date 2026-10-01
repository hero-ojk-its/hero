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
    validate_regulation_filename_match,
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
        delay_seconds: float = 0.15,
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
        referer: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str], str]:
        """Menentukan ukuran berkas via HEAD / Range."""
        ref = referer or "https://jdih.ojk.go.id/"
        host = urlsplit(pdf_url).hostname or "jdih.ojk.go.id"
        self._rate_limit(host)
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Referer": ref,
        }

        try:
            head_resp = client.head(
                pdf_url,
                headers=headers,
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            self.requests_count += 1
            if head_resp.status_code == 200:
                ct = head_resp.headers.get("content-type", "").lower()
                if "text/html" not in ct:
                    cd_name = extract_filename_from_cd(head_resp.headers.get("content-disposition"))
                    cl = head_resp.headers.get("content-length")
                    if cl and cl.isdigit() and int(cl) > 0:
                        return int(cl), cd_name, "head"
        except Exception:
            pass

        try:
            self._rate_limit(host)
            range_headers = {**headers, "Range": "bytes=0-0"}
            range_resp = client.get(
                pdf_url,
                headers=range_headers,
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
                ct = range_resp.headers.get("content-type", "").lower()
                if "text/html" not in ct:
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

                resp = None
                for offset_attempt in range(3):
                    self._rate_limit(base_host)
                    try:
                        self.requests_count += 1
                        r_try = client.get(api_url, headers=headers)
                        if r_try.status_code == 200:
                            resp = r_try
                            break
                        time.sleep(1.0)
                    except Exception as ex:
                        if offset_attempt == 2:
                            errors.append(f"Gagal memanggil API JDIH pada offset {display_start}: {ex}")
                        time.sleep(2.0)

                if resp is None:
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

                    # Kolom 5: Jenis regulasi (dukung inferensi dari judul untuk kategori gabungan)
                    raw_jenis = str(row[5]).strip() if len(row) > 5 and row[5] is not None else None
                    reg_type = normalize_crawler_regulation_type(raw_jenis, title=doc_title) if raw_jenis and raw_jenis != "None" else normalize_crawler_regulation_type(None, title=doc_title)

                    # Ekstrak tahun dari judul terlebih dahulu (misal: "Nomor 18 Tahun 2025")
                    title_year = None
                    t_y_m = re.search(r'\bTahun\s+(20\d\d|19\d\d)\b', doc_title, re.IGNORECASE)
                    if t_y_m:
                        title_year = int(t_y_m.group(1))
                    else:
                        gen_y_m = re.search(r'(?:^|[\W_])(20\d\d|19\d\d)(?:[\W_]|$)', doc_title)
                        if gen_y_m:
                            title_year = int(gen_y_m.group(1))

                    # Format awal regulation_number lengkap dari judul jika ada format nomor slash
                    formatted_reg_num = None
                    slash_num_m = re.search(r'\b(\d+/[A-Z0-9\.]+(?:/\d{4})?)\b', doc_title)
                    if slash_num_m:
                        formatted_reg_num = slash_num_m.group(1)

                    # URL detail regulasi: lampiran PDF HANYA diambil dari halaman detail sebenarnya
                    detail_url = f"{api_base}/Web/ViewPeraturan/Detail/{guid}/All/"

                    # Ambil halaman detail untuk mendapatkan seluruh lampiran berkas asli dan tanggal penetapan/berlaku
                    d_html = ""
                    try:
                        self._rate_limit(base_host)
                        self.requests_count += 1
                        d_headers = {
                            "User-Agent": self.user_agent,
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Referer": f"{api_base}/",
                        }
                        d_resp = client.get(detail_url, headers=d_headers)
                        if d_resp.status_code == 200 and ("Request Rejected" in d_resp.text or len(d_resp.text) < 500):
                            time.sleep(0.5)
                            self._rate_limit(base_host)
                            self.requests_count += 1
                            d_resp = client.get(detail_url, headers=d_headers)

                        if d_resp.status_code == 200 and "Request Rejected" not in d_resp.text:
                            d_html = d_resp.text
                    except Exception as det_ex:
                        logger.debug(f"Gagal memuat detail {detail_url}: {det_ex}")

                    # Ekstrak tanggal dari tabel detail (Tanggal Penetapan, Tanggal Pengundangan, Status Peraturan)
                    penetapan_date: Optional[date] = None
                    pengundangan_date: Optional[date] = None
                    effective_date: Optional[date] = None

                    if d_html:
                        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', d_html, re.DOTALL):
                            th_m = re.search(r'<th[^>]*><h4>(.*?)</h4></th>', tr, re.DOTALL)
                            if not th_m:
                                continue
                            hdr = th_m.group(1).strip().lower()
                            tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
                            val = ""
                            if len(tds) >= 2:
                                val = re.sub(r'<[^>]+>', '', tds[1]).replace('&nbsp;', ' ').strip()
                            elif len(tds) == 1:
                                val = re.sub(r'<[^>]+>', '', tds[0]).replace('&nbsp;', ' ').strip()

                            if "penetapan" in hdr:
                                dm = re.search(r'(\d{1,2}-\d{1,2}-\d{4})', val)
                                if dm:
                                    penetapan_date = _parse_jdih_date(dm.group(1))
                            elif "pengundangan" in hdr:
                                dm = re.search(r'(\d{1,2}-\d{1,2}-\d{4})', val)
                                if dm:
                                    pengundangan_date = _parse_jdih_date(dm.group(1))
                            elif "status" in hdr:
                                # Contoh: "Berlaku Sejak Tanggal 09-02-2026"
                                dm = re.search(r'(\d{1,2}-\d{1,2}-\d{4})', val)
                                if dm and "tidak berlaku" not in val.lower():
                                    effective_date = _parse_jdih_date(dm.group(1))

                    # release_date: penetapan -> pengundangan -> title_year (1 Jan)
                    rel_date = penetapan_date or pengundangan_date
                    if not rel_date and title_year:
                        rel_date = date(title_year, 1, 1)

                    # Fallback tanggal berlaku dari kolom 6 DataTables jika row[7] == 'Berlaku'
                    raw_status_date = str(row[6]).strip() if len(row) > 6 and row[6] is not None else None
                    status_label = str(row[7]).strip() if len(row) > 7 and row[7] is not None else ""
                    dt_status_date = _parse_jdih_date(raw_status_date) if raw_status_date and raw_status_date != "None" else None

                    if not effective_date and "berlaku" in status_label.lower() and "tidak" not in status_label.lower():
                        effective_date = dt_status_date

                    if not rel_date:
                        rel_date = dt_status_date

                    # Format regulation_number sintetis dengan tahun dari judul (atau rel_date jika judul tanpa tahun)
                    if not formatted_reg_num and reg_num:
                        year_val = title_year or (rel_date.year if rel_date else None)
                        type_label = reg_type or "Nomor"
                        if year_val:
                            formatted_reg_num = f"{type_label} {reg_num} Tahun {year_val}"
                        else:
                            formatted_reg_num = f"{type_label} Nomor {reg_num}"

                    attachments_found: List[Tuple[str, str, Optional[str]]] = []
                    if d_html:
                        # Cari blok <tr> yang memuat DownloadDokumen
                        for tr in re.findall(r'<tr>(.*?)</tr>', d_html, re.DOTALL):
                            if "DownloadDokumen" not in tr:
                                continue
                            th_m = re.search(r'<th[^>]*><h4>(.*?)</h4></th>', tr, re.DOTALL)
                            lbl = th_m.group(1).strip() if th_m else ""
                            guid_m_att = re.search(r'/DownloadDokumen/([^"\'\s>]+)', tr)
                            if not guid_m_att:
                                continue
                            att_guid = guid_m_att.group(1).rstrip("/'\"")
                            fn_m = re.search(r'downloadDokumen\([\'"]([^\'"]+\.pdf)[\'"]', tr, re.IGNORECASE)
                            if not fn_m:
                                fn_m = re.search(r'>\s*([^<>]+\.pdf)\s*</a>', tr, re.IGNORECASE)
                            fn = fn_m.group(1).strip() if fn_m else None
                            attachments_found.append((att_guid, lbl, fn))

                        # Fallback jika struktur <tr> tidak ditemukan
                        if not attachments_found:
                            for m in re.finditer(r'href=[\'"]/Web/ViewPeraturan/DownloadDokumen/([^"\'\s>]+)[\'"]', d_html):
                                attachments_found.append((m.group(1).rstrip("/'\""), "", None))

                    found_any_for_reg = False
                    for att_guid, lbl, fn in attachments_found:
                        att_url = normalize_url(f"{api_base}/Web/ViewPeraturan/DownloadDokumen/{att_guid}")
                        if att_url in candidates_map:
                            continue

                        asb, acdf, assrc = (None, None, "unknown")
                        if self.head_for_size:
                            asb, acdf, assrc = self._probe_pdf_size(client, att_url, referer=detail_url)

                        final_fn = acdf or fn
                        if not final_fn:
                            safe_stem = re.sub(r'[\\/*?:"<>|]', '_', doc_title).strip()
                            final_fn = f"{safe_stem[:100]}.pdf"

                        adk = determine_doc_kind(final_fn, label=lbl)
                        match_warn = validate_regulation_filename_match(
                            final_fn,
                            regulation_number=formatted_reg_num or reg_num,
                            release_date=rel_date,
                            document_title=doc_title,
                            regulation_type=reg_type,
                        )

                        cand = PdfCandidate(
                            url=att_url,
                            filename=final_fn,
                            size_bytes=asb,
                            found_on_page=detail_url,
                            depth=1,
                            document_title=doc_title,
                            detail_url=detail_url,
                            final_url=att_url,
                            doc_kind=adk,
                            regulation_number=formatted_reg_num or reg_num,
                            raw_regulation_number=reg_num,
                            regulation_type=reg_type,
                            bidang=bidang,
                            sub_bidang=None,
                            release_date=rel_date,
                            effective_date=effective_date,
                            match_warning=match_warn,
                            size_source=assrc,
                        )
                        candidates_map[att_url] = cand
                        found_any_for_reg = True

                    if found_any_for_reg:
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
        match_warnings_count = 0
        for c in cand_list:
            k = c.doc_kind or "utama"
            doc_kinds[k] = doc_kinds.get(k, 0) + 1
            if c.match_warning:
                match_warnings_count += 1

        stats = {
            "records_total": total_records if 'total_records' in locals() else None,
            "regulations_found": regulations_count,
            "pdfs_found": len(cand_list),
            "match_warnings_count": match_warnings_count,
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
