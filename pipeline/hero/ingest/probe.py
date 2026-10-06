"""Scan-time file index: URL, document name, file name and size — no download.

MoM Weekly #4 set the acceptance criterion for scraping: a document counts as
*scraped* once the scan knows its official URL, its name, its file name and
its size. Downloading is explicitly excluded (it depends on bandwidth and
disk, not on the algorithm).

The inventory already held the first three for most records; size was known
for 14 of 3,206. This module fills it with one ``HEAD`` per file, falling
back to a one-byte ``Range`` request whose body is never read. The fallback
matters: jdih.ojk.go.id ignores ``Range`` and answers 200 with the whole
file, so the stream is closed as soon as the headers arrive.

Requests go through :class:`~hero.ingest.web.WebScraper`, so robots.txt, the
per-host delay and retries are the same as for discovery. One worker per
host: hosts proceed in parallel, each at its configured politeness.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable
from urllib.parse import unquote, urlparse

import requests

from ..config import Settings
from ..kb.catalog import Catalog
from .web import WebScraper, filename_from_disposition

log = logging.getLogger(__name__)

# Which attachment stands for "the document" when the record has no
# document_url (drafts published only as .docx, matrix-only drafts).
_ROLE_ORDER = ("utama", "lampiran", "matriks")

_CONTENT_RANGE = re.compile(r"/(\d+)\s*$")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class PrimaryFile:
    url: str
    name: str | None
    role: str          # document_url | utama | lampiran | matriks
    ext: str | None


def primary_file(row: dict[str, Any]) -> PrimaryFile | None:
    """Pick the one file that represents this record."""
    attachments = json.loads(row.get("attachments_json") or "[]")
    if row.get("document_url"):
        url = row["document_url"]
        name = row.get("document_name")
        ext = next((a.get("ext") for a in attachments if a.get("url") == url), None)
        return PrimaryFile(url, name, "document_url", ext or _ext_from_url(url))
    for role in _ROLE_ORDER:
        for a in attachments:
            if a.get("kind") == role and a.get("url"):
                return PrimaryFile(a["url"], a.get("name"), role,
                                   a.get("ext") or _ext_from_url(a["url"]))
    return None


def _ext_from_url(url: str) -> str | None:
    path = unquote(urlparse(url).path)
    if "." in path.rsplit("/", 1)[-1]:
        return path.rsplit(".", 1)[-1].lower()[:8] or None
    return None


@dataclass
class SizeResult:
    size: int | None
    content_type: str | None
    file_name: str | None
    method: str        # head | range | none
    error: str | None = None


def measure(scraper: WebScraper, url: str) -> SizeResult:
    """Size of one remote file without downloading it."""
    if not scraper.allowed(url):
        return SizeResult(None, None, None, "none", "dilarang robots.txt")
    head = scraper.head(url)
    ctype = name = None
    if head is not None:
        ctype = head.headers.get("Content-Type")
        name = filename_from_disposition(head.headers.get("Content-Disposition"))
        if head.status_code < 400:
            length = head.headers.get("Content-Length")
            if length and length.isdigit() and int(length) > 0:
                return SizeResult(int(length), ctype, name, "head")
    # Fallback: ask for one byte; read only headers, never the body.
    scraper._throttle(url)  # noqa: SLF001 - same politeness as every request
    try:
        with scraper.session.get(
            url, headers={"Range": "bytes=0-0"}, stream=True, allow_redirects=True,
            timeout=scraper.settings.request_timeout,
            verify=scraper.settings.verify_tls,
        ) as resp:
            ctype = resp.headers.get("Content-Type") or ctype
            name = filename_from_disposition(
                resp.headers.get("Content-Disposition")) or name
            if resp.status_code >= 400:
                return SizeResult(None, ctype, name, "range", f"HTTP {resp.status_code}")
            m = _CONTENT_RANGE.search(resp.headers.get("Content-Range", ""))
            if resp.status_code == 206 and m:
                return SizeResult(int(m.group(1)), ctype, name, "range")
            length = resp.headers.get("Content-Length")
            if length and length.isdigit() and int(length) > 0:
                return SizeResult(int(length), ctype, name, "range")
            return SizeResult(None, ctype, name, "range",
                              "server tidak menyebut ukuran (chunked)")
    except requests.RequestException as exc:
        return SizeResult(None, ctype, name, "none", f"{type(exc).__name__}: {exc}"[:200])


@dataclass
class ProbeReport:
    checked: int = 0
    sized: int = 0
    failed: int = 0
    skipped_no_file: int = 0
    per_host: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    errors: list[str] = field(default_factory=list)


def probe_inventory(
    settings: Settings,
    source: str | None = None,
    limit: int | None = None,
    refresh: bool = False,
    say: Callable[[str], None] | None = None,
    progress_every: int = 50,
) -> ProbeReport:
    """Fill ``file_*`` columns for inventory rows. Safe to stop and re-run."""
    say = say or (lambda _m: None)
    cat = Catalog(settings.catalog_db)
    where = ["1=1"]
    params: list[Any] = []
    if source:
        where.append("source = ?")
        params.append(source)
    if not refresh:
        where.append("file_checked_at IS NULL")
    rows = [dict(r) for r in cat.conn.execute(
        f"SELECT * FROM inventory WHERE {' AND '.join(where)} ORDER BY source, record_key",
        params)]
    cat.close()

    report = ProbeReport()
    by_host: dict[str, list[tuple[dict[str, Any], PrimaryFile]]] = defaultdict(list)
    no_file: list[dict[str, Any]] = []
    for row in rows:
        pf = primary_file(row)
        if pf is None:
            no_file.append(row)
        else:
            by_host[urlparse(pf.url).netloc].append((row, pf))
    if limit is not None:
        # Spread the budget across hosts so a sample covers every source.
        per = max(1, limit // max(1, len(by_host)))
        by_host = {h: items[:per] for h, items in by_host.items()}

    lock = threading.Lock()
    scraper = WebScraper(settings.scraper)

    def write(cat: Catalog, row: dict[str, Any], pf: PrimaryFile | None,
              res: SizeResult | None) -> None:
        cat.conn.execute(
            "UPDATE inventory SET file_url=?, file_name=?, file_role=?, file_ext=?, "
            "file_size=?, file_type=?, file_method=?, file_error=?, file_checked_at=? "
            "WHERE record_key=?",
            (pf.url if pf else None,
             (pf.name if pf else None) or (res.file_name if res else None),
             pf.role if pf else None, pf.ext if pf else None,
             res.size if res else None, res.content_type if res else None,
             res.method if res else "none",
             (res.error if res else "tidak ada berkas di sumber"),
             _now(), row["record_key"]))

    # Each row is written and committed at once, under one lock. Network I/O
    # happens outside the lock, so a slow host never holds the SQLite write
    # lock (an earlier version did, for 25 requests at a time, which
    # serialised the hosts and starved every other writer of the catalog).
    def run_host(host: str, items: list[tuple[dict[str, Any], PrimaryFile]]) -> None:
        cat = Catalog(settings.catalog_db)  # sqlite connections are per thread
        try:
            _run(cat, host, items)
        finally:
            cat.close()

    def _run(cat: Catalog, host: str, items: list[tuple[dict[str, Any], PrimaryFile]]) -> None:
        for i, (row, pf) in enumerate(items, 1):
            res = measure(scraper, pf.url)
            with lock:
                write(cat, row, pf, res)
                cat.conn.commit()
                report.checked += 1
                report.per_host[host] += 1
                if res.size:
                    report.sized += 1
                else:
                    report.failed += 1
                    if len(report.errors) < 50:
                        report.errors.append(f"{pf.url} — {res.error}")
            if i % progress_every == 0:
                say(f"{host}: {i}/{len(items)}")

    cat = Catalog(settings.catalog_db)
    for row in no_file:
        write(cat, row, None, None)
    cat.conn.commit()
    cat.close()
    report.skipped_no_file = len(no_file)

    say(f"{sum(len(v) for v in by_host.values())} berkas di {len(by_host)} host; "
        f"{len(no_file)} rekaman tanpa berkas")
    with ThreadPoolExecutor(max_workers=max(1, len(by_host))) as pool:
        for fut in [pool.submit(run_host, h, items) for h, items in by_host.items()]:
            fut.result()
    scraper.close()
    return report


# ---------------------------------------------------------------------------
# Acceptance: indexed documents vs DPEA ground truth (MoM #4, issues #87/#88)
# ---------------------------------------------------------------------------

#: Four attributes a scan must know for a document to count as indexed.
CRITERIA = ("url", "nama_dokumen", "nama_berkas", "ukuran")


def acceptance(cat: Catalog, ground_truth: dict[str, Any] | None = None,
               ) -> list[dict[str, Any]]:
    """Per-source counts against the acceptance criterion.

    ``ground_truth`` maps a source key to ``{"min": n, "max": n, "catatan": ...}``
    (a single number may be given as both). Sources without ground truth are
    still reported, with the comparison left empty rather than guessed.
    """
    ground_truth = ground_truth or {}
    out = []
    for r in cat.conn.execute(
        """SELECT source,
                  COUNT(*)                                             AS rekaman,
                  SUM(COALESCE(file_url, document_url, '') != '')      AS url,
                  SUM(COALESCE(title, '') != '')                       AS nama_dokumen,
                  SUM(COALESCE(file_name, document_name, '') != '')    AS nama_berkas,
                  SUM(file_size > 0)                                   AS ukuran,
                  SUM(COALESCE(file_url, document_url, '') != ''
                      AND COALESCE(title, '') != ''
                      AND COALESCE(file_name, document_name, '') != ''
                      AND file_size > 0)                               AS terindeks,
                  SUM(file_checked_at IS NOT NULL)                     AS diperiksa,
                  SUM(LOWER(COALESCE(file_ext, '')) = 'pdf')           AS pdf
             FROM inventory GROUP BY source ORDER BY source"""):
        row = dict(r)
        gt = ground_truth.get(row["source"]) or {}
        lo, hi = gt.get("min"), gt.get("max", gt.get("min"))
        row["ground_truth"] = (None if lo is None else
                               (f"{lo:,}" if lo == hi else f"{lo:,}–{hi:,}").replace(",", "."))
        row["ground_truth_catatan"] = gt.get("catatan")
        if lo is not None:
            mid = (lo + hi) / 2
            row["rasio_terhadap_gt"] = round(row["terindeks"] / mid, 3) if mid else None
            row["dalam_rentang"] = lo <= row["terindeks"] <= hi
        out.append(row)
    return out


def iter_unindexed(cat: Catalog, source: str | None = None) -> Iterable[dict[str, Any]]:
    """Records that miss at least one criterion, with the missing ones named."""
    sql = "SELECT * FROM inventory" + (" WHERE source = ?" if source else "")
    for r in cat.conn.execute(sql, (source,) if source else ()):
        row = dict(r)
        missing = []
        if not (row.get("file_url") or row.get("document_url")):
            missing.append("url")
        if not row.get("title"):
            missing.append("nama_dokumen")
        if not (row.get("file_name") or row.get("document_name")):
            missing.append("nama_berkas")
        if not (row.get("file_size") or 0) > 0:
            missing.append("ukuran")
        if missing:
            row["kurang"] = missing
            yield row
