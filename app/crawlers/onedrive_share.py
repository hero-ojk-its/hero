"""
app/crawlers/onedrive_share.py
Crawler adapter untuk folder bersama publik OneDrive / SharePoint (US-17 / #30).
Mendukung:
- Inisialisasi sesi tamu melalui pengalihan tautan berbagi "anyone with the link".
- Penelusuran rekursif subfolder hingga kedalaman yang ditentukan (default 10).
- Ekstraksi kandidat PDF dengan source_path, ukuran persis dari listing (size_source="listing"),
  dan URL unduhan langsung (_layouts/15/download.aspx?SourceUrl=...).
- Perhitungan berkas non-PDF pada statistik non_pdf_links.
PENTING: Modul ini TIDAK BOLEH mengimpor app.database, app.models, app.routers, app.services.
"""
import hashlib
import logging
import posixpath
import re
import ssl
import time
from collections import deque
from typing import Callable, Optional, List, Dict, Set, Tuple, Any
from urllib.parse import urlsplit, urlunsplit, parse_qs, unquote, quote

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
    determine_doc_kind,
    normalize_crawler_regulation_type,
    clean_onedrive_filename,
    parse_onedrive_filename_metadata,
    validate_regulation_filename_match,
)

logger = logging.getLogger("hero.crawler.onedrive_share")

# Folder sistem SharePoint yang harus diabaikan saat crawling
IGNORED_SP_FOLDERS = {"_w", "forms", "item", "_t", "_catalogs", "_layouts", "_vti_bin"}


class OneDriveShareCrawler:
    """Crawler adapter untuk folder OneDrive for Business / SharePoint yang dibagikan publik."""

    name: str = "onedrive_share"

    def __init__(
        self,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        delay_seconds: float = 0.3,
        timeout_seconds: int = 30,
        respect_robots: bool = False,
        allow_private: bool = False,
        head_for_size: bool = False,  # Ukuran sudah didapat langsung dari listing
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

    def _resolve_session_and_root(
        self,
        client: httpx.Client,
        share_url: str,
    ) -> Tuple[str, str, str]:
        """
        Mengikuti redirect tautan berbagi OneDrive/SharePoint untuk mendapatkan cookie sesi tamu
        serta menentukan site_base URL dan root folder server-relative URL.
        Mengembalikan: (site_base, root_server_relative_url, display_root_name)
        """
        guard_url(share_url, self.allow_private)
        self.requests_count += 1
        resp = client.get(
            share_url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            follow_redirects=True,
            timeout=self.timeout_seconds,
        )

        if resp.status_code >= 400:
            raise CrawlerError(f"HTTP {resp.status_code} saat membuka tautan berbagi OneDrive.")

        final_url = str(resp.url)
        parsed = urlsplit(final_url)

        # 1. Ekstrak site base URL
        site_match = re.match(r"(https?://[^/]+/personal/[^/]+)", final_url)
        if site_match:
            site_base = site_match.group(1)
        else:
            site_match2 = re.match(r"(https?://[^/]+/sites/[^/]+)", final_url)
            if site_match2:
                site_base = site_match2.group(1)
            else:
                site_base = f"{parsed.scheme}://{parsed.netloc}"

        # 2. Ekstrak folder server relative URL dari parameter query 'id' atau path
        qs = parse_qs(parsed.query)
        folder_id = qs.get("id", [""])[0]
        if folder_id:
            root_folder = unquote(folder_id)
        else:
            # Fallback path URL
            root_folder = unquote(parsed.path)

        display_name = posixpath.basename(root_folder.rstrip("/")) or "root"
        return site_base, root_folder, display_name

    def scan(
        self,
        url: str,
        depth: int = 10,
        *,
        max_pages: int = 500,
        max_candidates: int = 10000,
        progress: Optional[Callable[[int, int], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> ScanResult:
        start_time = time.time()
        self.requests_count = 0
        guard_url(url, self.allow_private)

        ssl_ctx = self._get_ssl_context()
        visited_folders: Set[str] = set()
        candidates_map: Dict[str, PdfCandidate] = {}
        errors: List[str] = []
        truncated = False
        blocked = False
        non_pdf_links = 0

        max_depth = max(1, min(depth or 10, 15))

        with httpx.Client(verify=ssl_ctx, http2=False, timeout=self.timeout_seconds) as client:
            try:
                site_base, root_folder_path, root_name = self._resolve_session_and_root(client, url)
            except Exception as ex:
                return ScanResult(
                    candidates=[],
                    pages_visited=0,
                    errors=[f"Gagal menginisialisasi sesi OneDrive: {ex}"],
                    truncated=False,
                    blocked=False,
                    stats={"duration_seconds": round(time.time() - start_time, 2)},
                )

            api_headers = {
                "User-Agent": self.user_agent,
                "Accept": "application/json;odata=verbose",
                "X-Requested-With": "XMLHttpRequest",
            }

            # Queue penelusuran folder: (server_rel_path, display_rel_path, current_depth)
            queue: deque[Tuple[str, str, int]] = deque()
            queue.append((root_folder_path, "", 1))

            while queue and len(visited_folders) < max_pages:
                if should_cancel and should_cancel():
                    break
                if len(candidates_map) >= max_candidates:
                    truncated = True
                    break

                folder_path, rel_path_prefix, cur_depth = queue.popleft()
                if folder_path in visited_folders:
                    continue
                visited_folders.add(folder_path)

                host = urlsplit(site_base).hostname or ""
                self._rate_limit(host)

                enc_folder = quote(folder_path, safe="")
                files_api = f"{site_base}/_api/web/GetFolderByServerRelativeUrl('{enc_folder}')/Files"
                try:
                    self.requests_count += 1
                    f_resp = client.get(files_api, headers=api_headers)
                    if f_resp.status_code == 200:
                        files_data = f_resp.json().get("d", {}).get("results", [])
                        for fi in files_data:
                            if len(candidates_map) >= max_candidates:
                                truncated = True
                                break

                            fname = fi.get("Name", "")
                            f_rel_url = fi.get("ServerRelativeUrl", "")
                            f_len = fi.get("Length")

                            if not fname:
                                continue

                            # Tentukan jalur relatif folder
                            file_source_path = posixpath.join(rel_path_prefix, fname) if rel_path_prefix else fname

                            if fname.lower().endswith(".pdf"):
                                try:
                                    size_bytes = int(f_len) if f_len is not None else None
                                except (ValueError, TypeError):
                                    size_bytes = None

                                # URL unduhan langsung melalui layout SharePoint
                                download_url = f"{site_base}/_layouts/15/download.aspx?SourceUrl={quote(f_rel_url)}"
                                norm_url = normalize_url(download_url)

                                stem_title = clean_onedrive_filename(fname) or posixpath.splitext(fname)[0].replace("_", " ")
                                doc_k = determine_doc_kind(fname)
                                if rel_path_prefix and any(p.lower() in ("administration", "user requirement & project charter") for p in rel_path_prefix.split("/")):
                                    doc_k = "non_regulasi"

                                meta = parse_onedrive_filename_metadata(fname)
                                reg_type = meta.get("regulation_type")
                                reg_num = meta.get("regulation_number")
                                rel_date = meta.get("release_date")
                                rel_year = meta.get("release_year")
                                match_warn = validate_regulation_filename_match(
                                    fname,
                                    regulation_number=reg_num,
                                    release_date=rel_date,
                                    document_title=stem_title,
                                    regulation_type=reg_type,
                                    release_year=rel_year,
                                )

                                cand = PdfCandidate(
                                    url=norm_url,
                                    filename=fname,
                                    size_bytes=size_bytes,
                                    found_on_page=folder_path,
                                    depth=cur_depth,
                                    document_title=stem_title,
                                    detail_url=folder_path,
                                    final_url=norm_url,
                                    doc_kind=doc_k,
                                    regulation_number=reg_num,
                                    regulation_type=reg_type,
                                    bidang=None,
                                    sub_bidang=None,
                                    release_date=rel_date,
                                    release_year=rel_year,
                                    effective_date=None,
                                    match_warning=match_warn,
                                    size_source="listing",
                                    source_path=file_source_path,
                                )
                                candidates_map[norm_url] = cand
                            else:
                                non_pdf_links += 1

                    elif f_resp.status_code == 403 or f_resp.status_code == 503:
                        c_marker = detect_captcha_or_waf(f_resp.status_code, f_resp.headers, f_resp.text)
                        if c_marker:
                            blocked = True
                            errors.append(f"terblokir_captcha: Proteksi ({c_marker}) pada folder {folder_path}.")
                            break
                    else:
                        errors.append(f"HTTP {f_resp.status_code} saat membaca berkas di {folder_path}.")
                except Exception as file_err:
                    errors.append(f"Gagal membaca berkas di folder '{folder_path}': {file_err}")

                if progress:
                    progress(len(visited_folders), len(candidates_map))

                # 2. Ambil subfolder jika belum melebihi batas kedalaman
                if cur_depth < max_depth:
                    enc_folder = quote(folder_path, safe="")
                    folders_api = f"{site_base}/_api/web/GetFolderByServerRelativeUrl('{enc_folder}')/Folders"
                    try:
                        self.requests_count += 1
                        sub_resp = client.get(folders_api, headers=api_headers)
                        if sub_resp.status_code == 200:
                            sub_folders_data = sub_resp.json().get("d", {}).get("results", [])
                            for sub in sub_folders_data:
                                s_name = sub.get("Name", "")
                                s_rel_url = sub.get("ServerRelativeUrl", "")
                                if not s_name or not s_rel_url:
                                    continue
                                if s_name.lower() in IGNORED_SP_FOLDERS or s_name.startswith("."):
                                    continue

                                next_rel_path = posixpath.join(rel_path_prefix, s_name) if rel_path_prefix else s_name
                                if s_rel_url not in visited_folders:
                                    queue.append((s_rel_url, next_rel_path, cur_depth + 1))
                    except Exception as sub_err:
                        logger.debug(f"Gagal membaca subfolder di '{folder_path}': {sub_err}")

            if len(visited_folders) >= max_pages and queue:
                truncated = True

        duration_sec = round(time.time() - start_time, 2)
        cand_list = list(candidates_map.values())
        doc_kinds: Dict[str, int] = {}
        subfolders_count: Dict[str, int] = {}
        match_warnings_count = 0
        for c in cand_list:
            k = c.doc_kind or "utama"
            doc_kinds[k] = doc_kinds.get(k, 0) + 1
            if c.match_warning:
                match_warnings_count += 1
            top_folder = c.source_path.split("/")[0] if c.source_path and "/" in c.source_path else (c.source_path or "root")
            subfolders_count[top_folder] = subfolders_count.get(top_folder, 0) + 1

        stats = {
            "regulations_found": len(cand_list),
            "pdfs_found": len(cand_list),
            "subfolders_count": subfolders_count,
            "match_warnings_count": match_warnings_count,
            "by_doc_kind": doc_kinds,
            "pages_visited": len(visited_folders),
            "requests_made": self.requests_count,
            "non_pdf_links": non_pdf_links,
            "duration_seconds": duration_sec,
        }

        return ScanResult(
            candidates=cand_list,
            pages_visited=len(visited_folders),
            errors=errors,
            truncated=truncated,
            blocked=blocked,
            stats=stats,
        )

    def fetch(self, url: str, *, max_bytes: int = 100 * 1024 * 1024) -> FetchedFile:
        guard_url(url, self.allow_private)
        ssl_ctx = self._get_ssl_context()

        # Ekstrak SourceUrl jika ada untuk nama berkas default
        parsed = urlsplit(url)
        qs = parse_qs(parsed.query)
        src_url = qs.get("SourceUrl", [""])[0]

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

            # Tentukan nama berkas
            cd_hdr = resp.headers.get("content-disposition", "")
            cd_name = None
            if cd_hdr:
                match = re.search(r'filename\s*=\s*(?:"([^"]+)"|([^;\s]+))', cd_hdr, re.IGNORECASE)
                if match:
                    cd_name = unquote(match.group(1) or match.group(2))

            if not cd_name and src_url:
                cd_name = unquote(posixpath.basename(src_url))
            if not cd_name:
                cd_name = unquote(posixpath.basename(parsed.path)) or "dokumen.pdf"

            return FetchedFile(
                content=content,
                filename=cd_name,
                final_url=str(resp.url),
                content_type=resp.headers.get("content-type"),
            )
