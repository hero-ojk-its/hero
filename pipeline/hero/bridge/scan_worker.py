"""Worker pemindaian mode *push*: sesi pindai backend dilayani adapter HERO.

Backend punya crawler-nya sendiri (``simple_http``). Mode ``push`` ada supaya
sumber yang **tidak bisa dipindai dengan crawler HTML biasa** tetap terlayani
oleh adapter yang sudah terbukti di lapisan data:

| Sumber | Kenapa butuh adapter khusus |
|---|---|
| ``jdih.ojk.go.id`` | halaman daftarnya tidak memuat tautan; isinya grid JSON per pasangan sektor × jenis (120 pasangan, 986 rekaman) |
| ``ojk.go.id/…/regulasi`` | *postback* ASP.NET (`__VIEWSTATE`), 157 halaman × 10 baris, PDF hanya ada di halaman detail |
| ``ojk.go.id/…/rancangan`` | dokumennya ZIP; "Batang Tubuh" harus dipilih dari dalam arsip |

Alur (kontrak ``crawler-adapter-contract.md`` + Langkah 7 Opsi B):

    POST /internal/scans/claim                 ambil sesi berstatus antrian
      ↓ discover_site()      daftar + halaman detail → register HERO (TANPA unduh)
      ↓ probe_inventory()    ukuran berkas lewat HEAD/Range (kriteria MoM #4)
      ↓ mapping              register → PdfCandidate
    POST /internal/scans/{id}/candidates       batch, batch terakhir done=true

Tidak ada PDF yang diunduh di sini. Yang dikirim adalah *kandidat*: URL, nama
berkas, ukuran, metadata register, dan status keberlakuannya — cukup bagi
layar hasil pemindaian untuk membandingkannya dengan basis pengetahuan dan
membiarkan pengguna memilih apa yang ditarik.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from hero.bridge import mapping
from hero.bridge.client import BackendClient, BackendError
from hero.bridge.config import BridgeSettings
from hero.bridge.state import BridgeState, default_path
from hero.config import Settings, SiteSource

log = logging.getLogger("hero.bridge.scan")


@dataclass
class ScanOutcome:
    scan_id: int
    status: str                      # selesai | gagal
    candidates: int = 0
    pages_visited: int = 0
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0
    adapter: str = ""

    def line(self) -> str:
        return (f"pindai {self.scan_id}: {self.status} · {self.candidates} kandidat · "
                f"{self.pages_visited} halaman · adapter {self.adapter} ({self.seconds:.1f}s)")


def site_for(url: str, settings: Settings, *, depth: int, max_pages: int,
             max_candidates: int) -> SiteSource:
    """Sumber mana yang melayani URL ini.

    Bila URL-nya sudah terdaftar di ``sources.yaml`` (host yang sama), salinan
    konfigurasi itulah yang dipakai — ``follow_patterns``, ``exclude_patterns``
    dan ``sektor``/``jenis`` yang sudah disetel ikut terpakai, bukan dibuang
    hanya karena permintaan datang dari backend. Kalau tidak terdaftar, sumber
    sementara dibuat dengan batas yang diminta backend.
    """
    host = (urlparse(url).netloc or "").lower().removeprefix("www.")
    # URL yang sudah menyebut sektor/jenis secara eksplisit lebih spesifik
    # daripada daftar di sources.yaml: pengguna memilih satu kanal di layar,
    # bukan meminta seluruh matriks 120 pasangan. Jadi kedua sumbu itu tidak
    # diwarisi bila URL-nya sudah menentukannya.
    url_sektor, url_jenis = _jdih_axes(url)
    for s in settings.sites:
        if (urlparse(s.url).netloc or "").lower().removeprefix("www.") == host:
            return SiteSource(
                name=s.name, url=url, enabled=True,
                max_pages=max_pages or s.max_pages,
                max_documents=max_candidates or s.max_documents,
                max_depth=depth if depth is not None else s.max_depth,
                follow_patterns=list(s.follow_patterns),
                include_patterns=list(s.include_patterns),
                exclude_patterns=list(s.exclude_patterns),
                category_hint=s.category_hint, sniff_ambiguous_links=s.sniff_ambiguous_links,
                adapter=s.adapter,
                sektor=[] if url_sektor else list(s.sektor),
                jenis_peraturan=[] if url_jenis else list(s.jenis_peraturan),
                status_hint=s.status_hint)
    return SiteSource(name=f"pindai-backend:{host or 'url'}", url=url, enabled=True,
                      max_pages=max_pages or 50, max_documents=max_candidates or 500,
                      max_depth=depth, adapter="auto")


def _jdih_axes(url: str) -> tuple[str | None, str | None]:
    """``sektor`` / ``jenisPeraturan`` yang tertulis di URL register JDIH."""
    try:
        from hero.ingest.jdih import parse_index_url
        return parse_index_url(url)
    except Exception:                                             # noqa: BLE001
        return None, None


class ScanWorker:
    def __init__(self, settings: Settings, bridge: BridgeSettings, *,
                 client: BackendClient | None = None, state: BridgeState | None = None,
                 probe_sizes: bool = True):
        self.settings = settings
        self.bridge = bridge
        self.client = client or BackendClient(bridge)
        self.state = state or BridgeState(default_path(settings))
        self.probe_sizes = probe_sizes

    # -- satu sesi -------------------------------------------------------
    def process_one(self, session: dict[str, Any],
                    progress: Callable[[str], None] | None = None) -> ScanOutcome:
        from hero.inventory import discover_site, source_key_for_site
        from hero.kb.catalog import Catalog

        say = progress or (lambda m: None)
        scan_id = int(session["scan_id"])
        url = str(session["start_url"])
        depth = int(session.get("crawl_depth") or 1)
        max_pages = int(session.get("max_pages") or 0)
        max_candidates = int(session.get("max_candidates") or 0) or 5000
        cap = self.bridge.max_candidates_cap
        if cap and max_candidates > cap:
            say(f"sesi {scan_id}: backend meminta {max_candidates} kandidat, dibatasi {cap} "
                f"(bridge.max_candidates_cap) — hasil ditandai truncated")
            max_candidates = int(cap)
            self._capped = True
        else:
            self._capped = False
        started = time.perf_counter()

        site = site_for(url, self.settings, depth=depth, max_pages=max_pages,
                        max_candidates=max_candidates)
        adapter = site.resolved_adapter()
        source = source_key_for_site(site)
        self.state.begin_scan(scan_id, url)
        say(f"sesi {scan_id}: {url} → adapter {adapter} (kedalaman {depth})")

        errors: list[str] = []
        try:
            rep = discover_site(site, self.settings, max_pages=max_pages or None,
                                max_details=max_candidates,
                                progress=lambda kind, msg: say(f"  {msg}"))
            errors.extend(rep.errors)
            say(f"  register: {rep.listed} rekaman terdaftar · {rep.new} baru · "
                f"{rep.pages} halaman · {rep.enriched} detail dibaca")

            if self.probe_sizes:
                from hero.ingest.probe import probe_inventory
                pr = probe_inventory(self.settings, source=source, limit=max_candidates,
                                     say=lambda m: say(f"  {m}"))
                say(f"  ukuran: {pr.sized}/{pr.checked} terbaca lewat HEAD (tanpa unduh)")

            with Catalog(self.settings.catalog_db) as cat:
                rows = [dict(r) for r in cat.list_inventory(source, limit=max_candidates)]
            candidates: list[dict[str, Any]] = []
            for row in rows:
                candidates.extend(mapping.candidates_from_inventory_row(row, depth=depth))
                if len(candidates) >= max_candidates:
                    break
            truncated = (len(candidates) >= max_candidates or bool(rep.errors)
                         or getattr(self, "_capped", False))
            candidates = candidates[:max_candidates]
            say(f"  {len(candidates)} kandidat siap dikirim")

            sent = self._send(scan_id, candidates, pages_visited=rep.pages,
                              truncated=truncated, errors=errors, say=say)
            self.state.finish_scan(scan_id, status="selesai")
            self.state.log("pindai", str(scan_id),
                           {"kandidat": sent, "halaman": rep.pages, "adapter": adapter})
            return ScanOutcome(scan_id, "selesai", sent, rep.pages, errors,
                               time.perf_counter() - started, adapter)
        except BackendError as exc:
            self.state.finish_scan(scan_id, status="gagal", error=str(exc))
            return ScanOutcome(scan_id, "gagal", 0, 0, [str(exc)],
                               time.perf_counter() - started, adapter)
        except Exception as exc:                                  # noqa: BLE001
            log.exception("pemindaian sesi %s gagal", scan_id)
            msg = f"{type(exc).__name__}: {exc}"
            self.state.finish_scan(scan_id, status="gagal", error=msg)
            # Sesi harus ditutup dengan done=true, kalau tidak ia menggantung
            # di status "memindai" sampai pemulihan startup backend.
            try:
                self.client.push_candidates(scan_id, [], done=True, error=msg)
            except BackendError as exc2:
                log.error("tidak bisa menutup sesi %s: %s", scan_id, exc2)
            return ScanOutcome(scan_id, "gagal", 0, 0, [msg],
                               time.perf_counter() - started, adapter)

    def _send(self, scan_id: int, candidates: list[dict[str, Any]], *, pages_visited: int,
              truncated: bool, errors: list[str], say: Callable[[str], None]) -> int:
        """Kirim per batch; hanya batch terakhir membawa ``done=true``.

        ``done=true`` memicu perbandingan dengan basis pengetahuan di backend,
        jadi ia harus dikirim sekali saja, setelah kandidat terakhir masuk.
        """
        size = max(1, self.bridge.batch_candidates)
        sent = 0
        batches = [candidates[i:i + size] for i in range(0, len(candidates), size)] or [[]]
        for i, batch in enumerate(batches):
            last = i == len(batches) - 1
            res = self.client.push_candidates(
                scan_id, batch, pages_visited=pages_visited, done=last,
                truncated=truncated, errors=errors[:20] if last else [])
            sent += len(batch)
            self.state.bump_scan(scan_id, candidates=len(batch), pages=pages_visited)
            if last:
                say(f"  backend: {res.get('candidates_total')} total · "
                    f"{res.get('candidates_new')} baru · {res.get('candidates_existing')} sudah ada · "
                    f"{res.get('candidates_uncertain')} belum pasti → status {res.get('status')}")
        return sent

    # -- loop ------------------------------------------------------------
    def run_once(self, limit: int | None = None,
                 progress: Callable[[str], None] | None = None) -> list[ScanOutcome]:
        sessions = self.client.claim_scans(limit or self.bridge.claim_scans)
        return [self.process_one(s, progress=progress) for s in sessions]

    def run_forever(self, *, max_batches: int | None = None,
                    stop: Callable[[], bool] | None = None,
                    progress: Callable[[str], None] | None = None) -> list[ScanOutcome]:
        out: list[ScanOutcome] = []
        batches = 0
        while not (stop and stop()):
            got = self.run_once(progress=progress)
            out.extend(got)
            batches += 1
            if max_batches and batches >= max_batches:
                break
            if not got:
                time.sleep(self.bridge.poll_seconds)
        return out

    def close(self) -> None:
        self.client.close()
        self.state.close()


def staging_dir(settings: Settings) -> Path:
    return Path(settings.staging_dir) / "bridge"
