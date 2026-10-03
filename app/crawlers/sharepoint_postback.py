"""
app/crawlers/sharepoint_postback.py
Crawler untuk situs SharePoint / ASP.NET yang menggunakan paging __doPostBack (Regulasi OJK).
Mendukung:
- Paginasi __doPostBack dengan pemeliharaan form hidden fields (__VIEWSTATE, __EVENTVALIDATION, dll.).
- Ekstraksi halaman detail regulasi (metadata nomor, jenis, bidang/sektor, sub_bidang, release_date).
- Ekstraksi 2-3 lampiran PDF per regulasi dengan klasifikasi doc_kind (utama, abstrak, faq, lampiran).
- Penentuan ukuran berkas via HEAD -> Range: bytes=0-0 probe.
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
from html.parser import HTMLParser
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
    normalize_bidang,
)

logger = logging.getLogger("hero.crawler.sharepoint_postback")

MONTH_NAMES_ID = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "agt": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "des": 12, "dec": 12,
}


def _parse_indonesian_date(raw_text: str) -> Optional[date]:
    """Mengekstrak tanggal dari format Indonesia seperti '14 Maret 2024' atau '2024-03-14'."""
    if not raw_text:
        return None
    cleaned = raw_text.strip().lower()
    # Format YYYY-MM-DD
    iso_m = re.search(r"\b(20\d\d|19\d\d)-(\d{1,2})-(\d{1,2})\b", cleaned)
    if iso_m:
        try:
            return date(int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3)))
        except ValueError:
            pass

    # Format DD Month YYYY
    date_m = re.search(r"\b(\d{1,2})\s+([a-z]+)\s+(20\d\d|19\d\d)\b", cleaned)
    if date_m:
        d = int(date_m.group(1))
        m_name = date_m.group(2)
        y = int(date_m.group(3))
        m = MONTH_NAMES_ID.get(m_name)
        if m:
            try:
                return date(y, m, d)
            except ValueError:
                pass

    # Format MM/DD/YYYY atau DD/MM/YYYY (format khas kontrol tanggal SharePoint OJK)
    slash_m = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d\d|19\d\d)\b", cleaned)
    if slash_m:
        p1 = int(slash_m.group(1))
        p2 = int(slash_m.group(2))
        y = int(slash_m.group(3))
        if p1 > 12:
            d, m = p1, p2
        elif p2 > 12:
            m, d = p1, p2
        else:
            # Default SharePoint OJK adalah MM/DD/YYYY (bulan/hari/tahun)
            m, d = p1, p2
        try:
            return date(y, m, d)
        except ValueError:
            pass

    # Format tahun saja
    year_m = re.search(r"\b(20\d\d|19\d\d)\b", cleaned)
    if year_m:
        try:
            return date(int(year_m.group(1)), 1, 1)
        except ValueError:
            pass

    return None


class SharepointPostbackCrawler:
    """Crawler adapter khusus untuk SharePoint / ASP.NET dengan form postback."""

    name: str = "sharepoint_postback"

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

    def _safe_request(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        max_attempts: int = 4,
    ) -> httpx.Response:
        guard_url(url, self.allow_private)
        host = urlsplit(url).hostname or ""
        self._rate_limit(host)

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": url,
        }

        for attempt in range(max_attempts):
            self.requests_count += 1
            try:
                if method.upper() == "GET":
                    resp = client.get(url, headers=headers, timeout=self.timeout_seconds)
                else:
                    resp = client.post(url, data=data, headers=headers, timeout=self.timeout_seconds)

                if resp.status_code == 429 and attempt < max_attempts - 1:
                    wait_sec = min(float(resp.headers.get("retry-after", "2")), 60.0)
                    resp.close()
                    time.sleep(wait_sec)
                    continue

                return resp
            except Exception as e:
                if attempt < max_attempts - 1:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise e

        raise CrawlerError(f"Gagal melakukan request ke {url} setelah {max_attempts} percobaan.")

    def _extract_form_inputs(self, html_text: str) -> Dict[str, str]:
        """Mengekstrak input dan select dari HTML SharePoint, mengecualikan tombol submit."""
        inputs: Dict[str, str] = {}
        for m in re.finditer(r"<input\s+([^>]+)>", html_text, re.IGNORECASE):
            attrs = m.group(1)
            name_m = re.search(r'name=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            val_m = re.search(r'value=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
            type_m = re.search(r'type=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
            t = type_m.group(1).lower() if type_m else "text"
            if name_m:
                name = name_m.group(1)
                if t in ("submit", "button", "image"):
                    continue
                val = html.unescape(val_m.group(1)) if val_m else ""
                inputs[name] = val

        # Select dropdowns
        for s_m in re.finditer(r'<select\s+[^>]*name=["\']([^"\']+)["\'][^>]*>(.*?)</select>', html_text, re.DOTALL | re.IGNORECASE):
            s_name = s_m.group(1)
            s_body = s_m.group(2)
            sel_val_m = re.search(r'<option\s+[^>]*selected=["\']selected["\'][^>]*value=["\']([^"\']*)["\']', s_body, re.IGNORECASE)
            if not sel_val_m:
                sel_val_m = re.search(r'<option\s+[^>]*value=["\']([^"\']*)["\']', s_body, re.IGNORECASE)
            inputs[s_name] = sel_val_m.group(1) if sel_val_m else ""

        return inputs

    def _probe_pdf_size(
        self,
        client: httpx.Client,
        pdf_url: str,
    ) -> Tuple[Optional[int], Optional[str], str]:
        """Menentukan ukuran berkas via HEAD / Range tanpa unduh penuh."""
        try:
            head_resp = client.head(pdf_url, headers={"User-Agent": self.user_agent}, timeout=self.timeout_seconds)
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
                headers={"User-Agent": self.user_agent, "Range": "bytes=0-0"},
                timeout=self.timeout_seconds,
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

    def _parse_detail_page(
        self,
        client: httpx.Client,
        detail_url: str,
        page_depth: int,
    ) -> List[PdfCandidate]:
        """Membuka halaman detail regulasi dan mengekstrak semua lampiran PDF beserta metadata."""
        resp = self._safe_request(client, "GET", detail_url)
        if resp.status_code != 200:
            return []

        html_text = resp.text
        # Judul regulasi dari <title> atau <h1>
        title = ""
        t_match = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.DOTALL | re.IGNORECASE)
        if t_match:
            title = re.sub(r"<[^>]+>", "", t_match.group(1)).strip()
            # Hapus suffix situs
            title = re.sub(r"\s*-\s*Otoritas Jasa Keuangan\s*$", "", title, flags=re.IGNORECASE).strip()

        # Ekstraksi metadata dari tabel / teks
        nomor_reg = None
        jenis_reg = None
        bidang = None
        sub_bidang = None
        rel_date = None

        clean_text = re.sub(r"<script.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
        clean_text = re.sub(r"<style.*?</style>", "", clean_text, flags=re.DOTALL | re.IGNORECASE)
        clean_plain = re.sub(r"<[^>]+>", " ", clean_text)
        clean_plain = re.sub(r"[ \t]+", " ", clean_plain)

        # Cari pola metadata spesifik dari elemen OJK SharePoint
        jenis_m = re.search(r"Jenis\s*Regulasi\s*:\s*<span[^>]*>([^<]+)</span>", html_text, re.IGNORECASE)
        if not jenis_m:
            jenis_m = re.search(r"(?:Jenis\s*(?:Regulasi)?)\s*:\s*([^\r\n<]+)", clean_plain, re.IGNORECASE)
        if jenis_m:
            jenis_reg = normalize_crawler_regulation_type(html.unescape(jenis_m.group(1)).strip(), title=title)

        no_m = re.search(r"Nomor\s*Regulasi\s*:\s*<span[^>]*>([^<]+)</span>", html_text, re.IGNORECASE)
        if not no_m:
            no_m = re.search(r"(?:Nomor\s*(?:Regulasi)?)\s*:\s*([^\r\n<]+)", clean_plain, re.IGNORECASE)
        if no_m:
            nomor_reg = html.unescape(no_m.group(1)).strip()

        sektor_m = re.search(r"Sektor\s*:\s*<span[^>]*>([^<]+)</span>", html_text, re.IGNORECASE)
        if not sektor_m:
            sektor_m = re.search(r"(?:Sektor)\s*:\s*([^\r\n<]+)", clean_plain, re.IGNORECASE)
        if sektor_m:
            bidang = normalize_bidang(html.unescape(sektor_m.group(1)).strip())

        sub_m = re.search(r"Sub\s*Sektor\s*:\s*<span[^>]*>([^<]+)</span>", html_text, re.IGNORECASE)
        if not sub_m:
            sub_m = re.search(r"(?:Sub\s*Sektor)\s*:\s*([^\r\n<]+)", clean_plain, re.IGNORECASE)
        if sub_m:
            sub_bidang = html.unescape(sub_m.group(1)).strip()

        # Tanggal Berlaku (effective_date) & Tanggal Penetapan/Terbit (release_date)
        eff_date = None
        rel_date = None

        tb_m = re.search(r"Tanggal\s*Berlaku\s*:\s*<span[^>]*>([^<]+)</span>", html_text, re.IGNORECASE)
        if not tb_m:
            tb_m = re.search(r"Tanggal\s*Berlaku\s*:\s*([^\r\n<]+)", clean_plain, re.IGNORECASE)
        if tb_m:
            eff_date = _parse_indonesian_date(html.unescape(tb_m.group(1)).strip())

        tp_m = re.search(r"Tanggal\s*(?:Penetapan|Terbit)\s*:\s*<span[^>]*>([^<]+)</span>", html_text, re.IGNORECASE)
        if not tp_m:
            tp_m = re.search(r"Tanggal\s*(?:Penetapan|Terbit)\s*:\s*([^\r\n<]+)", clean_plain, re.IGNORECASE)
        if tp_m:
            rel_date = _parse_indonesian_date(html.unescape(tp_m.group(1)).strip())
        else:
            det_tgl_m = re.search(r"ditetapkan\s+(?:pada\s+)?tanggal\s+([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})", clean_plain, re.IGNORECASE)
            if det_tgl_m:
                rel_date = _parse_indonesian_date(det_tgl_m.group(1))

        # Ekstraksi tahun dari nomor atau judul untuk fallback release_date (seperti JDIH di 10c)
        parsed_year = None
        if nomor_reg:
            ym = re.search(r"\b(19\d\d|20\d\d)\b", nomor_reg)
            if ym:
                parsed_year = int(ym.group(1))
        if not parsed_year and title:
            ym = re.search(r"\b(19\d\d|20\d\d)\b", title)
            if ym:
                parsed_year = int(ym.group(1))

        if not rel_date:
            if eff_date:
                # Bila eff_date melompat tahun ke masa depan dibanding tahun regulasi, gunakan tahun regulasi
                if parsed_year and eff_date.year > parsed_year:
                    rel_date = date(parsed_year, 1, 1)
                else:
                    rel_date = eff_date
            elif parsed_year:
                rel_date = date(parsed_year, 1, 1)
        elif parsed_year and rel_date.year > parsed_year:
            # Bila rel_date terisi dari tanggal berlaku masa depan padahal nomor regulasi bertahun lebih awal
            rel_date = date(parsed_year, 1, 1)

        # Jika jenis/nomor belum dapat, ekstrak dari slug URL atau judul
        if not jenis_reg:
            if "POJK" in detail_url.upper() or "POJK" in title.upper():
                jenis_reg = "POJK"
            elif "SEOJK" in detail_url.upper() or "SEOJK" in title.upper():
                jenis_reg = "SEOJK"
            elif "PADK" in detail_url.upper() or "PADK" in title.upper():
                jenis_reg = "PADK"
            elif "KDK" in detail_url.upper() or "KDK" in title.upper():
                jenis_reg = "KDK"

        # Temukan semua lampiran PDF
        pdf_matches = re.findall(
            r'<a\s+[^>]*href=["\']([^"\']+\.pdf[^"\']*)["\'][^>]*>(.*?)</a>',
            html_text,
            re.DOTALL | re.IGNORECASE,
        )

        candidates: List[PdfCandidate] = []
        seen_urls: Set[str] = set()

        for raw_href, raw_link_text in pdf_matches:
            abs_pdf_url = urljoin(detail_url, raw_href)
            norm_pdf_url = normalize_url(abs_pdf_url)
            if not norm_pdf_url or norm_pdf_url in seen_urls:
                continue
            seen_urls.add(norm_pdf_url)

            # Ekstrak nama berkas default
            fn = unquote(posixpath.basename(urlsplit(norm_pdf_url).path))
            if not fn or not fn.lower().endswith(".pdf"):
                clean_lt = re.sub(r"<[^>]+>", "", raw_link_text).strip()
                fn = f"{clean_lt or 'dokumen'}.pdf"

            doc_k = determine_doc_kind(fn)
            size_b, cd_fn, size_src = (None, None, "unknown")
            if self.head_for_size:
                size_b, cd_fn, size_src = self._probe_pdf_size(client, norm_pdf_url)
                if cd_fn:
                    fn = cd_fn

            match_warn = validate_regulation_filename_match(
                fn,
                regulation_number=nomor_reg,
                release_date=rel_date,
                document_title=title,
                regulation_type=jenis_reg,
            )

            cand = PdfCandidate(
                url=norm_pdf_url,
                filename=fn,
                size_bytes=size_b,
                found_on_page=detail_url,
                depth=page_depth,
                document_title=title or fn,
                detail_url=detail_url,
                final_url=norm_pdf_url,
                doc_kind=doc_k,
                regulation_number=nomor_reg,
                regulation_type=jenis_reg,
                bidang=bidang,
                sub_bidang=sub_bidang,
                release_date=rel_date,
                effective_date=eff_date,
                match_warning=match_warn,
                size_source=size_src,
            )
            candidates.append(cand)

        return candidates

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

        ssl_ctx = self._get_ssl_context()
        visited_pages: Set[str] = set()
        candidates_map: Dict[str, PdfCandidate] = {}
        regulations_count = 0
        errors: List[str] = []
        truncated = False
        blocked = False
        non_pdf_links = 0

        with httpx.Client(verify=ssl_ctx, http2=False, timeout=self.timeout_seconds) as client:
            current_url = url
            page_num = 1
            form_inputs: Dict[str, str] = {}

            while page_num <= max_pages:
                if should_cancel and should_cancel():
                    break

                # 1. Ambil halaman daftar regulasi (GET untuk halaman 1, POST untuk selanjutnya)
                try:
                    if page_num == 1:
                        resp = self._safe_request(client, "GET", current_url)
                    else:
                        resp = self._safe_request(client, "POST", current_url, data=form_inputs)
                except Exception as ex:
                    errors.append(f"Gagal memuat halaman daftar regulasi ke-{page_num}: {ex}")
                    break

                # Cek captcha/WAF
                c_marker = detect_captcha_or_waf(resp.status_code, resp.headers, resp.text)
                if c_marker:
                    blocked = True
                    errors.append(f"terblokir_captcha: Proteksi terdeteksi ({c_marker}) pada halaman ke-{page_num}.")
                    break

                if resp.status_code != 200:
                    errors.append(f"HTTP {resp.status_code} pada halaman ke-{page_num}.")
                    break

                visited_pages.add(f"page_{page_num}")
                html_text = resp.text

                # 2. Ekstrak tautan artikel regulasi
                article_links = re.findall(
                    r'<a\s+[^>]*href=["\'](/id/regulasi/[^"\']*/Pages/[^"\']+)["\']',
                    html_text,
                    re.IGNORECASE,
                )
                if not article_links:
                    article_links = re.findall(
                        r'<a\s+[^>]*href=["\'](/id/regulasi/Pages/[^"\']+)["\']',
                        html_text,
                        re.IGNORECASE,
                    )

                # Dedup links di halaman ini
                unique_article_links = list(dict.fromkeys(article_links))
                if not unique_article_links:
                    logger.info(f"[SharepointCrawler] Tidak ada artikel ditemukan di halaman ke-{page_num}, selesai.")
                    break

                # 3. Proses tiap halaman detail regulasi
                for a_link in unique_article_links:
                    if should_cancel and should_cancel():
                        break
                    if len(candidates_map) >= max_candidates:
                        truncated = True
                        break

                    full_detail_url = urljoin(current_url, a_link)
                    try:
                        cands = self._parse_detail_page(client, full_detail_url, page_depth=1)
                        regulations_count += 1
                        for c in cands:
                            if c.url not in candidates_map:
                                candidates_map[c.url] = c
                    except Exception as det_err:
                        logger.debug(f"Gagal parse detail {full_detail_url}: {det_err}")

                    if progress:
                        progress(len(visited_pages), len(candidates_map))

                if truncated or len(visited_pages) >= max_pages:
                    break

                # 4. Siapkan postback untuk halaman berikutnya
                # Cari nomor halaman berikutnya di DataPagerArticles
                next_page_num = page_num + 1
                # Format penanda link halaman di DataPager:
                # href="javascript:__doPostBack('ctl00$PlaceHolderMain$ctl01$DataPagerArticles$ctl01$ctlXX','')"
                # atau tombol next: ctl00$PlaceHolderMain$ctl01$DataPagerArticles$ctl02$ctl00
                next_target = None
                pager_links = re.findall(
                    r'href=["\']javascript:__doPostBack\((?:&#39;|\')([^\'\)]+)(?:&#39;|\'),(?:&#39;|\')([^\'\)]*)(?:&#39;|\')\)["\'][^>]*>(.*?)</a>',
                    html_text,
                    re.DOTALL | re.IGNORECASE,
                )

                for ev_target, ev_arg, btn_text in pager_links:
                    clean_btn = re.sub(r"<[^>]+>", "", btn_text).strip()
                    if clean_btn == str(next_page_num):
                        next_target = html.unescape(ev_target)
                        break

                if not next_target:
                    # Coba cari tombol 'Next' / '»'
                    for ev_target, ev_arg, btn_text in pager_links:
                        clean_btn = re.sub(r"<[^>]+>", "", btn_text).strip().lower()
                        if "next" in clean_btn or "»" in clean_btn or "ctl02$ctl00" in ev_target:
                            next_target = html.unescape(ev_target)
                            break

                if not next_target:
                    logger.info(f"[SharepointCrawler] Paging postback selesai di halaman {page_num}.")
                    break

                # Update form inputs dari response HTML
                form_inputs = self._extract_form_inputs(html_text)
                form_inputs["__EVENTTARGET"] = next_target
                form_inputs["__EVENTARGUMENT"] = ""
                page_num += 1

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
                headers={"User-Agent": self.user_agent},
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
