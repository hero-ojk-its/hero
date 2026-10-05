"""The Ingest screens as server-side workflows: scan → review → ingest.

The UI splits ingestion into two user decisions, and so does this module:

1. **Scan** (``Scan Dokumen``) lists what a source offers *without
   downloading anything*, and labels every item against the knowledge base:
   ``baru`` · ``sudah_ada`` · ``duplikat`` · ``tidak_tersedia``.
2. **Ingest** (``Download Dokumen Terpilih``) fetches only the items the user
   ticked, reporting per-item progress (``menunggu → diproses → selesai``).

Both run as background jobs: a JDIH scan reads one detail page per record
with a polite delay, so fifty records take over a minute — far too long to
hold an HTTP request open. State lives in SQLite (``scan_run``/``scan_item``,
``ingest_job``/``ingest_job_item``), so a restart does not lose history and
the "Riwayat" tables are ordinary queries.

Status vocabulary, defined once here and mirrored in /api/meta/enums:

* ``sudah_ada``      the regulation is already in the KB (same identity, same
                     document URL, or same file from this source)
* ``duplikat``       listed more than once *within this scan* — e.g. ojk.go.id
                     shows a regulation in both the all-sectors and the sector
                     channel (Temuan 3); only the first occurrence is offered
* ``tidak_tersedia`` the source has no downloadable PDF (e.g. a draft
                     published only as .docx — outside URD 4.2 scope)
* ``baru``           everything else: can be selected for download
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests

from hero import inventory as inv
from hero.config import Settings, SiteSource
from hero.graph.identity import canonical_ref, ref_for_record
from hero.ingest.onedrive import (
    DEFAULT_EXCLUDE, download_sharepoint_folder, list_sharepoint_files, open_guest_session,
)
from hero.ingest.jdih import parse_index_url
from hero.ingest.web import WebScraper
from hero.kb.catalog import Catalog
from hero.kb.readmodel import STATUS_LABELS, display_title, number_line
from hero.pipeline import IngestPipeline

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_run (
    scan_id TEXT PRIMARY KEY, jenis TEXT NOT NULL, sumber TEXT NOT NULL, sumber_label TEXT,
    parameter TEXT, kategori TEXT, akses TEXT, status TEXT NOT NULL,
    dibuat TEXT NOT NULL, selesai TEXT, progres TEXT,
    ditemukan INTEGER DEFAULT 0, baru INTEGER DEFAULT 0, sudah_ada INTEGER DEFAULT 0,
    duplikat INTEGER DEFAULT 0, tidak_tersedia INTEGER DEFAULT 0, galat TEXT);
CREATE TABLE IF NOT EXISTS scan_item (
    scan_id TEXT NOT NULL, item_id TEXT NOT NULL, urutan INTEGER, judul TEXT, jenis TEXT,
    nomor TEXT, tahun INTEGER, status_regulasi TEXT, status_kbs TEXT, alasan TEXT,
    identitas TEXT, record_key TEXT, berkas TEXT, doc_id_ada TEXT, metadata_dari TEXT,
    PRIMARY KEY (scan_id, item_id));
CREATE TABLE IF NOT EXISTS ingest_job (
    job_id TEXT PRIMARY KEY, scan_id TEXT NOT NULL, status TEXT NOT NULL, dibuat TEXT NOT NULL,
    mulai TEXT, selesai TEXT, total INTEGER, kategori TEXT, galat TEXT);
CREATE TABLE IF NOT EXISTS ingest_job_item (
    job_id TEXT NOT NULL, item_id TEXT NOT NULL, urutan INTEGER, status TEXT NOT NULL,
    doc_id TEXT, alasan TEXT, diperbarui TEXT, PRIMARY KEY (job_id, item_id));
CREATE INDEX IF NOT EXISTS ix_scan_run_dibuat ON scan_run(jenis, dibuat DESC);
"""

KBS_LABELS = {"baru": ("Baru", "success"), "sudah_ada": ("Sudah Ada", "neutral"),
              "duplikat": ("Duplikat", "warning"), "tidak_tersedia": ("Tidak Tersedia", "neutral")}
ITEM_LABELS = {"menunggu": ("Menunggu", "neutral"), "diproses": ("Sedang Diproses", "info"),
               "selesai": ("Selesai", "success"), "duplikat": ("Sudah Ada", "neutral"),
               "gagal": ("Gagal", "danger")}
RUN_LABELS = {"berjalan": ("Sedang Berjalan", "info"), "selesai": ("Berhasil", "success"),
              "gagal_koneksi": ("Gagal Terhubung", "danger"), "gagal": ("Gagal", "danger"),
              "terputus": ("Terputus", "warning")}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


class _Recorder:
    """Catalog proxy that remembers which inventory rows a lister touched.

    The listers in hero.inventory write straight into the inventory; wrapping
    the catalog is how a scan learns *which* records it found without the
    listers needing to return them.
    """

    def __init__(self, cat: Catalog):
        self._cat = cat
        self.keys: list[str] = []

    def upsert_inventory(self, rec: dict) -> bool:
        if rec.get("record_key") and rec["record_key"] not in self.keys:
            self.keys.append(rec["record_key"])
        return self._cat.upsert_inventory(rec)

    def __getattr__(self, name):
        return getattr(self._cat, name)


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------
_FILE_PATTERNS = (
    (re.compile(r"(?:^|_)(POJK|SEOJK|PADK|PDK|SEDK)[_ ]+(\d+)[_ ]+(?:Tahun[_ ]+)?(\d{4})", re.I), None),
    (re.compile(r"Peraturan_OJK_(\d+)_(\d{4})", re.I), "POJK"),
    (re.compile(r"Surat_Edaran_OJK_(\d+)_(\d{4})", re.I), "SEOJK"),
    (re.compile(r"Peraturan_ADK_(\d+)_Tahun_(\d{4})", re.I), "PADK"),
)


def identity_from_filename(name: str) -> tuple[str | None, str | None, int | None, str | None]:
    """Best-effort (jenis, nomor, tahun, key) from a file name such as
    ``Peraturan_OJK_27_2021.pdf``. Used only to *preview* a sync scan; the
    real metadata is read from the PDF at ingest time."""
    stem = Path(name).stem.replace("%20", "_")
    # Names downloaded from SharePoint sometimes carry "%20" rewritten as
    # "_20" ("POJK_203_20Tahun_202025" = "POJK 3 Tahun 2025"). Decode only when
    # that encoding is evident ("_20" before a letter) — decoding blindly turns
    # the year in "Peraturan_OJK_11_2026" into "_26" and breaks the identity.
    if re.search(r"_20[A-Za-z]", stem):
        stem = stem.replace("_20", "_")
    for rx, fixed in _FILE_PATTERNS:
        m = rx.search(stem)
        if m:
            if fixed:
                jenis, nomor, tahun = fixed, m.group(1), int(m.group(2))
            else:
                jenis, nomor, tahun = m.group(1).upper(), m.group(2), int(m.group(3))
            ref = canonical_ref(f"{jenis} Nomor {nomor} Tahun {tahun}")
            return jenis, nomor, tahun, ref.key if ref else None
    return None, None, None, None


def _kb_identities(cat: Catalog) -> dict[str, str]:
    out = {}
    for r in cat.conn.execute("SELECT doc_id, doc_type, number, year FROM documents "
                              "WHERE status IN ('ingested', 'failed')"):
        ref = ref_for_record(r["doc_type"], r["number"], r["year"])
        if ref:
            out.setdefault(ref.key, r["doc_id"])
    return out


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
class FlowRunner:
    """Owns the background worker. One worker: jobs are serialised, which
    keeps SQLite writes simple and keeps HERO polite to source sites."""

    def __init__(self, settings: Settings, on_change: Callable[[], None] | None = None):
        self.settings = settings
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hero-flow")
        self.on_change = on_change or (lambda: None)
        # Called on the worker after every finished ingest job — the API uses
        # it to rebuild the graph and the vector index (derived data).
        self.after_job: Callable[[], None] | None = None
        self._lock = threading.Lock()
        with self._db() as conn:
            ensure_schema(conn)
            # A job that was running when the process stopped will never finish.
            conn.execute("UPDATE scan_run SET status = 'terputus', selesai = ? "
                         "WHERE status = 'berjalan'", (_now(),))
            conn.execute("UPDATE ingest_job SET status = 'terputus', selesai = ? "
                         "WHERE status = 'berjalan'", (_now(),))

    def _db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.settings.catalog_db, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)

    # -- scan: URL --------------------------------------------------------
    def start_url_scan(self, url: str, *, depth: int = 2, kategori: str | None = None,
                       sektor: list[str] | None = None, jenis: list[str] | None = None,
                       max_items: int = 50) -> str:
        probe = SiteSource(name="probe", url=url, sektor=list(sektor or []),
                           jenis_peraturan=list(jenis or []))
        if probe.resolved_adapter() == "jdih_ojk" and not (sektor and jenis) \
                and not all(parse_index_url(url)):
            # Without both axes JDIH falls back to its full 120-pair matrix —
            # a multi-hour harvest, not a scan. Rejected up front as bad input.
            raise ValueError("URL JDIH perlu menyertakan sektor dan jenis peraturan "
                             "(mis. ?sektor=01&jenisPeraturan=06) atau isi parameter sektor & jenis")
        scan_id = uuid.uuid4().hex[:12]
        host = (urlparse(url).netloc or url).removeprefix("www.")
        params = {"url": url, "kedalaman": depth, "sektor": sektor, "jenis": jenis,
                  "maks_item": max_items}
        with self._db() as conn:
            conn.execute("INSERT INTO scan_run (scan_id, jenis, sumber, sumber_label, parameter, "
                         "kategori, status, dibuat, progres) VALUES (?, 'url', ?, ?, ?, ?, "
                         "'berjalan', ?, ?)", (scan_id, url, host + urlparse(url).path,
                                               json.dumps(params), kategori, _now(),
                                               "Menyiapkan pemindaian…"))
        self.pool.submit(self._guard, scan_id, "scan", self._run_url_scan, scan_id, params)
        return scan_id

    def _progress(self, table: str, key_col: str, key: str, msg: str) -> None:
        with self._db() as conn:
            conn.execute(f"UPDATE {table} SET progres = ? WHERE {key_col} = ?", (msg, key))

    def _guard(self, run_id: str, kind: str, fn, *args) -> None:
        try:
            fn(*args)
        except Exception as exc:  # noqa: BLE001 — a failed job must be recorded, not lost
            log.exception("%s %s failed", kind, run_id)
            table, col = ("scan_run", "scan_id") if kind == "scan" else ("ingest_job", "job_id")
            # "Gagal Terhubung" only when it really was the network — a parse
            # error shown as a connection problem sends people to the wrong fix.
            network = isinstance(exc, (ConnectionError, requests.RequestException, TimeoutError))
            with self._db() as conn:
                conn.execute(f"UPDATE {table} SET status = ?, selesai = ?, galat = ? WHERE {col} = ?",
                             ("gagal_koneksi" if network else "gagal", _now(),
                              f"{type(exc).__name__}: {exc}", run_id))
            log.debug(traceback.format_exc())
        finally:
            self.on_change()

    def _run_url_scan(self, scan_id: str, params: dict) -> None:
        url = params["url"]
        site = SiteSource(name=f"scan:{urlparse(url).netloc}", url=url,
                          max_depth=int(params["kedalaman"]), max_pages=60,
                          sektor=[str(s) for s in params.get("sektor") or []],
                          jenis_peraturan=[str(j) for j in params.get("jenis") or []],
                          exclude_patterns=["abstrak", "faq", "matriks"])
        adapter = site.resolved_adapter()
        source = inv.source_key_for_site(site)
        say = lambda kind, msg: self._progress("scan_run", "scan_id", scan_id, msg)
        rep = inv.DiscoverReport(site=site.name, source=source)
        with WebScraper(self.settings.scraper) as scraper, Catalog(self.settings.catalog_db) as cat:
            rec = _Recorder(cat)
            if adapter == "jdih_ojk":
                inv._list_jdih(site, scraper, rec, rep, say)
            elif adapter == "ojk_sharepoint":
                # Listing pages are newest-first; depth = how many pager pages.
                inv._list_sharepoint(site, scraper, rec, rep, say, False, max(1, params["kedalaman"]))
            else:
                inv._list_generic(site, scraper, rec, rep, say)
            keys = rec.keys[: int(params["maks_item"])]
            if not keys and rep.errors:
                raise ConnectionError("; ".join(rep.errors[:3]))
            rows = [cat.get_inventory(k) for k in keys]
            if adapter in ("jdih_ojk", "ojk_sharepoint"):
                pending = [r for r in rows if r and not r["enriched_at"]]
                if pending:
                    say("detail", f"Membaca {len(pending)} halaman detail…")
                    inv._enrich(site, scraper, cat, rep, say, False, None, rows=pending)
                rows = [cat.get_inventory(k) for k in keys]
            items = self._classify_records(cat, [r for r in rows if r])
        self._finish_scan(scan_id, items, rep.errors)

    def _classify_records(self, cat: Catalog, rows: list[sqlite3.Row]) -> list[dict]:
        kb_ids = _kb_identities(cat)
        seen: set[str] = set()
        items = []
        for i, r in enumerate(rows):
            ref = ref_for_record(r["doc_type"], r["number"], r["year"])
            ident = ref.key if ref else f"URL|{r['document_url'] or r['record_key']}"
            existing = r["doc_id"] or (kb_ids.get(ref.key) if ref else None)
            if not existing and r["document_url"]:
                known = cat.seen_source_ref(r["document_url"])
                existing = known["doc_id"] if known else None
            if existing:
                status, reason = "sudah_ada", "Peraturan ini sudah ada di Knowledge Base"
            elif ident in seen:
                status, reason = "duplikat", "Muncul lebih dari sekali dalam hasil pemindaian ini"
            elif not r["document_url"]:
                atts = json.loads(r["attachments_json"] or "[]")
                exts = sorted({a.get("ext") for a in atts if a.get("ext")})
                status = "tidak_tersedia"
                reason = (f"Hanya tersedia sebagai {'/'.join(exts)} — di luar cakupan PDF (URD 4.2)"
                          if exts else "Sumber tidak menyediakan berkas dokumen")
            else:
                status, reason = "baru", None
            seen.add(ident)
            items.append({"item_id": hashlib_id(r["record_key"]), "urutan": i,
                          "judul": r["title"], "jenis": r["doc_type"], "nomor": r["number"],
                          "tahun": r["year"], "status_regulasi": r["status"] or "unknown",
                          "status_kbs": status, "alasan": reason, "identitas": ident,
                          "record_key": r["record_key"], "berkas": None,
                          "doc_id_ada": existing, "metadata_dari": "sumber"})
        return items

    def _finish_scan(self, scan_id: str, items: list[dict], errors: list[str]) -> None:
        counts = {k: sum(1 for it in items if it["status_kbs"] == k) for k in KBS_LABELS}
        with self._db() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO scan_item (scan_id, item_id, urutan, judul, jenis, nomor, "
                "tahun, status_regulasi, status_kbs, alasan, identitas, record_key, berkas, "
                "doc_id_ada, metadata_dari) VALUES (:scan_id, :item_id, :urutan, :judul, :jenis, "
                ":nomor, :tahun, :status_regulasi, :status_kbs, :alasan, :identitas, :record_key, "
                ":berkas, :doc_id_ada, :metadata_dari)", [dict(it, scan_id=scan_id) for it in items])
            conn.execute(
                "UPDATE scan_run SET status = 'selesai', selesai = ?, progres = NULL, ditemukan = ?, "
                "baru = ?, sudah_ada = ?, duplikat = ?, tidak_tersedia = ?, galat = ? "
                "WHERE scan_id = ?", (_now(), len(items), counts["baru"], counts["sudah_ada"],
                                      counts["duplikat"], counts["tidak_tersedia"],
                                      "; ".join(errors[:5]) or None, scan_id))

    # -- scan: OneDrive / local folder -----------------------------------
    def start_sync_scan(self, *, sumber: str, share_url: str | None = None,
                        subfolder: str | None = None, path: str | None = None,
                        nama: str | None = None, kategori: str | None = None,
                        akses: str = "internal", max_items: int = 200) -> str:
        scan_id = uuid.uuid4().hex[:12]
        label = nama or (f"OneDrive — {subfolder or 'folder bersama'}" if sumber == "onedrive"
                         else f"Folder Lokal — {Path(path or '').name}")
        params = {"sumber": sumber, "share_url": share_url, "subfolder": subfolder, "path": path,
                  "nama": label, "maks_item": max_items}
        with self._db() as conn:
            conn.execute("INSERT INTO scan_run (scan_id, jenis, sumber, sumber_label, parameter, "
                         "kategori, akses, status, dibuat, progres) VALUES (?, 'sinkronisasi', ?, "
                         "?, ?, ?, ?, 'berjalan', ?, 'Membaca daftar berkas…')",
                         (scan_id, share_url or path or "", label, json.dumps(params), kategori,
                          akses, _now()))
        self.pool.submit(self._guard, scan_id, "scan", self._run_sync_scan, scan_id, params)
        return scan_id

    def _run_sync_scan(self, scan_id: str, params: dict) -> None:
        stype = "onedrive" if params["sumber"] == "onedrive" else "local_folder"
        files: list[tuple[str, str]] = []          # (name, locator)
        if stype == "onedrive":
            sess = requests.Session()
            sess.headers["User-Agent"] = self.settings.scraper.user_agent
            origin, site, root, error = open_guest_session(params["share_url"], sess)
            if error:
                raise ConnectionError(error)
            folder = f"{root.rstrip('/')}/{params['subfolder']}" if params.get("subfolder") else root
            listed, error = list_sharepoint_files(sess, origin, site, folder)
            if error:
                raise ConnectionError(error)
            files = [(f.name, f.server_relative_url) for f in listed]
        else:
            base = Path(params["path"] or "").expanduser()
            if not base.is_dir():
                raise FileNotFoundError(f"folder tidak ditemukan: {base}")
            files = [(p.name, str(p)) for p in sorted(base.rglob("*")) if p.is_file()]

        skip = tuple(DEFAULT_EXCLUDE)
        pdfs = [(n, loc) for n, loc in files if n.lower().endswith(".pdf")
                and not any(x in n.lower() for x in skip)][: int(params["maks_item"])]
        with Catalog(self.settings.catalog_db) as cat:
            kb_ids = _kb_identities(cat)
            seen: set[str] = set()
            items = []
            for i, (name, loc) in enumerate(pdfs):
                jenis, nomor, tahun, key = identity_from_filename(name)
                ident = key or f"FILE|{name.lower()}"
                existing = None
                if cat.has_source_file(stype, params["nama"], name):
                    existing = "berkas-sama"
                elif key and key in kb_ids:
                    existing = kb_ids[key]
                if existing:
                    status, reason = "sudah_ada", "Sudah pernah diambil / sudah ada di Knowledge Base"
                elif ident in seen:
                    status, reason = "duplikat", "Identitas sama dengan berkas lain di folder ini"
                else:
                    status, reason = "baru", None
                seen.add(ident)
                items.append({"item_id": hashlib_id(loc), "urutan": i,
                              "judul": Path(name).stem.replace("_", " "), "jenis": jenis,
                              "nomor": nomor, "tahun": tahun, "status_regulasi": "unknown",
                              "status_kbs": status, "alasan": reason, "identitas": ident,
                              "record_key": None, "berkas": loc,
                              "doc_id_ada": existing if existing != "berkas-sama" else None,
                              "metadata_dari": "nama_berkas"})
        self._finish_scan(scan_id, items, [])

    # -- ingest ------------------------------------------------------------
    def start_ingest(self, scan_id: str, item_ids: list[str], kategori: str | None = None) -> str:
        with self._db() as conn:
            run = conn.execute("SELECT * FROM scan_run WHERE scan_id = ?", (scan_id,)).fetchone()
            if run is None:
                raise KeyError(scan_id)
            if run["status"] != "selesai":
                raise ValueError("pemindaian belum selesai")
            rows = conn.execute(
                f"SELECT item_id, urutan, status_kbs FROM scan_item WHERE scan_id = ? AND item_id IN "
                f"({', '.join('?' for _ in item_ids)}) ORDER BY urutan", (scan_id, *item_ids)).fetchall()
            chosen = [r for r in rows if r["status_kbs"] == "baru"]
            if not chosen:
                raise ValueError("tidak ada item berstatus 'baru' yang dipilih")
            job_id = uuid.uuid4().hex[:12]
            conn.execute("INSERT INTO ingest_job (job_id, scan_id, status, dibuat, total, kategori) "
                         "VALUES (?, ?, 'berjalan', ?, ?, ?)",
                         (job_id, scan_id, _now(), len(chosen), kategori or run["kategori"]))
            conn.executemany(
                "INSERT INTO ingest_job_item (job_id, item_id, urutan, status, diperbarui) "
                "VALUES (?, ?, ?, 'menunggu', ?)",
                [(job_id, r["item_id"], n, _now()) for n, r in enumerate(chosen)])
        self.pool.submit(self._guard, job_id, "ingest", self._run_ingest, job_id)
        return job_id

    def _set_item(self, job_id: str, item_id: str, status: str, doc_id=None, alasan=None) -> None:
        with self._db() as conn:
            conn.execute("UPDATE ingest_job_item SET status = ?, doc_id = COALESCE(?, doc_id), "
                         "alasan = ?, diperbarui = ? WHERE job_id = ? AND item_id = ?",
                         (status, doc_id, alasan, _now(), job_id, item_id))
        self.on_change()

    def _run_ingest(self, job_id: str) -> None:
        with self._db() as conn:
            job = conn.execute("SELECT * FROM ingest_job WHERE job_id = ?", (job_id,)).fetchone()
            run = conn.execute("SELECT * FROM scan_run WHERE scan_id = ?", (job["scan_id"],)).fetchone()
            items = conn.execute(
                "SELECT j.item_id, s.record_key, s.berkas FROM ingest_job_item j JOIN scan_item s "
                "ON s.scan_id = ? AND s.item_id = j.item_id WHERE j.job_id = ? ORDER BY j.urutan",
                (job["scan_id"], job_id)).fetchall()
            conn.execute("UPDATE ingest_job SET mulai = ? WHERE job_id = ?", (_now(), job_id))
        kategori = job["kategori"]
        pipeline = IngestPipeline(self.settings)
        try:
            if run["jenis"] == "url":
                for it in items:
                    self._set_item(job_id, it["item_id"], "diproses")
                    summary = pipeline.harvest_inventory(record_keys=[it["record_key"]],
                                                         category_override=kategori)
                    self._record_outcome(job_id, it["item_id"], summary)
            else:
                self._ingest_sync(job_id, run, items, kategori, pipeline)
        finally:
            pipeline.close()
        with self._db() as conn:
            conn.execute("UPDATE ingest_job SET status = 'selesai', selesai = ? WHERE job_id = ?",
                         (_now(), job_id))
        if self.after_job is not None:
            try:
                self.after_job()
            except Exception:  # noqa: BLE001 — the ingest itself succeeded
                log.exception("rebuilding derived indexes after job %s failed", job_id)

    def _record_outcome(self, job_id, item_id, summary) -> None:
        rec = summary.records[0] if summary.records else None
        if rec is None:
            self._set_item(job_id, item_id, "gagal", alasan="; ".join(summary.errors[:2]) or "tidak ada dokumen")
        elif rec.status == "ingested":
            self._set_item(job_id, item_id, "selesai", doc_id=rec.doc_id)
        elif rec.status == "duplicate":
            self._set_item(job_id, item_id, "duplikat", doc_id=rec.doc_id, alasan=rec.reason)
        else:
            self._set_item(job_id, item_id, "gagal", doc_id=rec.doc_id, alasan=rec.reason)

    def _ingest_sync(self, job_id, run, items, kategori, pipeline) -> None:
        params = json.loads(run["parameter"])
        stype = "onedrive" if params["sumber"] == "onedrive" else "local_folder"
        akses = run["akses"] or "internal"
        staging = Path(self.settings.staging_dir) / f"sync-{job_id}"
        by_name = {Path(it["berkas"]).name: it for it in items}
        paths: dict[str, Path] = {}
        if stype == "onedrive":
            for it in items:
                self._set_item(job_id, it["item_id"], "diproses", alasan="mengunduh")
            wanted = set(by_name)
            got, errors = download_sharepoint_folder(
                params["share_url"], staging, subfolder=params.get("subfolder"),
                max_files=len(wanted), skip=lambda n: n not in wanted, delay=0.3)
            paths = {p.name: p for p in got}
        else:
            paths = {n: Path(it["berkas"]) for n, it in by_name.items()}
        for name, it in by_name.items():
            self._set_item(job_id, it["item_id"], "diproses")
            path = paths.get(name)
            if path is None or not path.exists():
                self._set_item(job_id, it["item_id"], "gagal", alasan="berkas tidak dapat diambil")
                continue
            rec = pipeline.ingest_file(path, stype, params["nama"],
                                       params.get("share_url") or str(path), kategori,
                                       job_id, move=(stype == "onedrive"))
            if rec.doc_id and rec.status in ("ingested", "failed"):
                with self._db() as conn:
                    conn.execute("UPDATE documents SET access_class = ? WHERE doc_id = ?",
                                 (akses, rec.doc_id))
            summary = type("S", (), {"records": [rec], "errors": []})
            self._record_outcome(job_id, it["item_id"], summary)
        if stype == "onedrive" and staging.exists():
            for p in staging.glob("*"):
                p.unlink(missing_ok=True)
            staging.rmdir()

    # -- reads -------------------------------------------------------------
    def scan(self, scan_id: str, status_kbs: str | None = None) -> dict[str, Any] | None:
        with self._db() as conn:
            run = conn.execute("SELECT * FROM scan_run WHERE scan_id = ?", (scan_id,)).fetchone()
            if run is None:
                return None
            where, params = "WHERE scan_id = ?", [scan_id]
            if status_kbs:
                where += " AND status_kbs = ?"
                params.append(status_kbs)
            items = conn.execute(f"SELECT * FROM scan_item {where} ORDER BY urutan", params).fetchall()
        return {**run_summary(run), "items": [scan_item_out(i) for i in items]}

    def job(self, job_id: str) -> dict[str, Any] | None:
        with self._db() as conn:
            job = conn.execute("SELECT * FROM ingest_job WHERE job_id = ?", (job_id,)).fetchone()
            if job is None:
                return None
            run = conn.execute("SELECT * FROM scan_run WHERE scan_id = ?", (job["scan_id"],)).fetchone()
            items = conn.execute(
                "SELECT j.*, s.judul, s.jenis, s.nomor, s.tahun, s.status_regulasi FROM ingest_job_item j "
                "JOIN scan_item s ON s.scan_id = ? AND s.item_id = j.item_id WHERE j.job_id = ? "
                "ORDER BY j.urutan", (job["scan_id"], job_id)).fetchall()
        done = sum(1 for i in items if i["status"] in ("selesai", "duplikat", "gagal"))
        total = job["total"] or len(items)
        stored = sum(1 for i in items if i["status"] == "selesai")
        return {
            "job_id": job["job_id"], "scan_id": job["scan_id"],
            "status": {"value": job["status"], "label": RUN_LABELS.get(job["status"], ("?",))[0],
                       "tone": RUN_LABELS.get(job["status"], ("?", "neutral"))[1]},
            "sumber": {"url": run["sumber"], "label": run["sumber_label"]},
            "kategori_target": job["kategori"],
            "progres": {"selesai": done, "total": total,
                        "persen": round(100 * done / total) if total else 100},
            "tersimpan": stored, "dibuat": job["dibuat"], "mulai": job["mulai"],
            "selesai": job["selesai"], "galat": job["galat"],
            "items": [{
                "item_id": i["item_id"], "judul": display_title(i["jenis"], i["judul"]),
                "nomor_tampil": number_line(i["jenis"], i["nomor"]), "jenis": i["jenis"],
                "nomor": i["nomor"], "tahun": i["tahun"],
                "status": {"value": i["status"], "label": ITEM_LABELS[i["status"]][0],
                           "tone": ITEM_LABELS[i["status"]][1]},
                "doc_id": i["doc_id"], "alasan": i["alasan"],
                "status_kbs": ({"value": "tersimpan", "label": "Tersimpan di KBS", "tone": "success"}
                               if i["status"] == "selesai" else None),
            } for i in items],
        }

    def history(self, jenis: str, limit: int = 3) -> list[dict[str, Any]]:
        with self._db() as conn:
            rows = conn.execute("SELECT * FROM scan_run WHERE jenis = ? ORDER BY dibuat DESC LIMIT ?",
                                (jenis, limit)).fetchall()
        return [run_summary(r) for r in rows]


def hashlib_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def run_summary(r: sqlite3.Row) -> dict[str, Any]:
    label, tone = RUN_LABELS.get(r["status"], (r["status"], "neutral"))
    return {
        "scan_id": r["scan_id"], "jenis": r["jenis"],
        "sumber": {"url": r["sumber"], "label": r["sumber_label"]},
        "kategori_target": r["kategori"], "akses": r["akses"],
        "status": {"value": r["status"], "label": label, "tone": tone},
        "progres": r["progres"], "dibuat": r["dibuat"], "selesai": r["selesai"],
        "ringkasan": {"ditemukan": r["ditemukan"], "baru": r["baru"], "sudah_ada": r["sudah_ada"],
                      "duplikat": r["duplikat"], "tidak_tersedia": r["tidak_tersedia"]},
        "galat": r["galat"],
    }


def scan_item_out(i: sqlite3.Row) -> dict[str, Any]:
    reg_label, reg_tone = STATUS_LABELS.get(i["status_regulasi"] or "unknown", STATUS_LABELS["unknown"])
    kbs_label, kbs_tone = KBS_LABELS[i["status_kbs"]]
    return {
        "item_id": i["item_id"], "judul": display_title(i["jenis"], i["judul"]),
        "judul_asli": i["judul"], "nomor_tampil": number_line(i["jenis"], i["nomor"]),
        "jenis": i["jenis"], "nomor": i["nomor"], "tahun": i["tahun"],
        "status_regulasi": {"value": i["status_regulasi"], "label": reg_label, "tone": reg_tone},
        "status_kbs": {"value": i["status_kbs"], "label": kbs_label, "tone": kbs_tone},
        "dapat_dipilih": i["status_kbs"] == "baru",
        "alasan": i["alasan"], "doc_id_ada": i["doc_id_ada"], "metadata_dari": i["metadata_dari"],
    }
