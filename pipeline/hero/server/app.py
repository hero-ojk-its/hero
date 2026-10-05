"""HTTP API for the HERO frontend.

One router per screen group in the design:

    /api/kb/…        Knowledge Base list, filters, detail drawer, PDF
    /api/ingest/…    Scraping URL: scan → Hasil Pemindaian → Proses → Berhasil
    /api/sync/…      Sinkronisasi OneDrive / Folder Lokal
    /api/search/…    lexical · lsa · semantic · hybrid (+ side-by-side compare)
    /api/graph/…     relations, lineage, impact, status findings
    /api/dashboard/… headline numbers
    /api/meta/enums  every label/tone the UI displays

Run:  hero serve            (or: uvicorn hero.server.app:create_app --factory)

Concurrency model: reads go through one long-lived connection guarded by a
lock (the read model's staleness check needs a persistent connection), and
all writes — scans, ingests, index rebuilds — run on a single background
worker. SQLite handles this comfortably at HERO's scale and there is no
second database server to operate.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import requests
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from hero import __version__
from hero.config import Settings, load_settings
from hero.graph import query as gq
from hero.graph.build import build_graph
from hero.graph.export import status_findings
from hero.ingest.onedrive import diagnose_link
from hero.kb import readmodel as rm
from hero.kb.topics import ALL_TOPICS
from hero.server import schemas as S
from hero.service.flows import FlowRunner, ITEM_LABELS, KBS_LABELS, RUN_LABELS
from hero.vector import VectorService, build_vectors
from hero.analysis import AiNarrator, analysis_payload
from hero.analysis.clauses import find_clauses

log = logging.getLogger(__name__)

SEMANTIC_MAX_RESULTS = 50


class State:
    """Process-wide handles, created once at startup."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(settings.catalog_db, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.read = rm.ReadModel(self.conn)
        self.vectors = VectorService(settings)
        self.flows = FlowRunner(settings)
        self.narrator = AiNarrator(settings.analysis)
        self.flows.after_job = self.after_ingest
        self._link_cache: dict[str, tuple[float, Any]] = {}
        with self.lock:
            self.read.sync_if_stale()
            if not self.conn.execute("SELECT 1 FROM sqlite_master WHERE name='graph_node'").fetchone():
                build_graph(self.conn)
        # Load embedders now, off the request path: the first semantic query
        # otherwise pays ~1 s of model loading inside a user's request.
        threading.Thread(target=self.prewarm, daemon=True, name="hero-prewarm").start()

    def prewarm(self) -> None:
        for name in ("lsa", "semantic"):
            if self.vectors.ready(name):
                try:
                    self.vectors.embedder(name).embed(["pemanasan"])
                except Exception:  # noqa: BLE001 — search will report the real error
                    log.exception("prewarm %s failed", name)

    def after_ingest(self) -> None:
        """New documents change the graph and the vector index. Rebuilt on
        the background worker; the vector rebuild re-embeds only unseen text."""
        with sqlite3.connect(self.settings.catalog_db, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            build_graph(conn)
        if self.vectors.store is not None:
            build_vectors(self.settings)
            self.vectors = VectorService(self.settings)

    def link_status(self, url: str, ttl: float = 300.0):
        hit = self._link_cache.get(url)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        d = diagnose_link(url)
        self._link_cache[url] = (time.monotonic(), d)
        return d


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings(os.environ.get("HERO_CONFIG", "config/sources.yaml"))
    holder: dict[str, State] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        holder["s"] = State(settings)
        yield
        holder["s"].flows.shutdown()

    app = FastAPI(title="HERO API", version=__version__, lifespan=lifespan,
                  description="Harmonisasi & Analisa Regulasi Otomatis — kontrak untuk frontend.")
    origins = os.environ.get("HERO_CORS", "http://localhost:3000,http://localhost:5173").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins if o.strip()],
                       allow_methods=["*"], allow_headers=["*"])

    def st() -> State:
        return holder["s"]

    # ------------------------------------------------------------------ meta
    @app.get("/api/health", tags=["meta"])
    def health():
        s = st()
        return {"ok": True, "versi": __version__,
                "vektor": {m: s.vectors.ready(m) for m in ("lexical", "lsa", "semantic", "hybrid")}}

    @app.get("/api/meta/enums", tags=["meta"])
    def enums():
        """Every label and badge tone the UI shows, from one place."""
        def table(d):
            return [{"value": k, "label": v[0], "tone": v[1]} for k, v in d.items()]
        return {
            "status_regulasi": table(rm.STATUS_LABELS),
            "status_kbs": table(KBS_LABELS),
            "status_item_ingest": table(ITEM_LABELS),
            "status_pemindaian": table(RUN_LABELS),
            "penyelarasan_pasal": table(rm.ALIGNMENT_LABELS),
            "urgensi_harmonisasi": table(rm.URGENCY_LABELS),
            "sumber": [{"value": k, "label": v} for k, v in rm.SOURCE_LABELS.items()],
            "kategori": [{"value": k, "label": v} for k, v in rm.CATEGORY_LABELS.items()],
            "klasifikasi_akses": [{"value": k, "label": v} for k, v in rm.ACCESS_LABELS.items()],
            "topik": list(ALL_TOPICS),
            "kedalaman_scraping": [
                {"value": 0, "label": "0 Level (halaman sumber saja)"},
                {"value": 1, "label": "1 Level"},
                {"value": 2, "label": "2 Level (Rekomendasi)"},
                {"value": 3, "label": "3 Level"}],
            "metode_pencarian": [
                {"value": "lexical", "label": "Kata kunci (FTS5/BM25)", "mode": "deterministik"},
                {"value": "lsa", "label": "Vektor LSA", "mode": "deterministik"},
                {"value": "semantic", "label": "Semantik (MiniLM)", "mode": "ai-assisted"},
                {"value": "hybrid", "label": "Hibrida (RRF)", "mode": "ai-assisted"}],
        }

    # ------------------------------------------------------------ dashboard
    @app.get("/api/dashboard/summary", tags=["dashboard"])
    def dashboard():
        s = st()
        with s.lock:
            s.read.sync_if_stale()
            c = s.conn
            by = lambda col: [dict(r) for r in c.execute(
                f"SELECT {col} AS value, COUNT(*) AS jumlah FROM kb_document_view GROUP BY 1 ORDER BY 2 DESC")]
            return {
                "total_dokumen": c.execute("SELECT COUNT(*) FROM kb_document_view").fetchone()[0],
                "total_register": c.execute("SELECT COUNT(*) FROM inventory").fetchone()[0],
                "per_status": by("status_label"), "per_kategori": by("kategori_label"),
                "per_sumber": by("sumber_label"),
                "urgensi_tinggi": c.execute(
                    "SELECT COUNT(*) FROM kb_document_view WHERE urgensi = 'tinggi' "
                    "AND status <> 'dicabut'").fetchone()[0],
                "terbaru": [rm.list_item(r) for r in c.execute(
                    "SELECT * FROM kb_document_view ORDER BY ingested_at DESC LIMIT 5")],
                "graf": gq.stats(c),
            }

    # ------------------------------------------------------------------- KB
    @app.get("/api/kb/documents", response_model=S.KbListResponse, tags=["knowledge-base"])
    def kb_list(q: Optional[str] = None,
                kategori: list[str] = Query(default=[]), jenis: list[str] = Query(default=[]),
                tahun: list[int] = Query(default=[]), topik: list[str] = Query(default=[]),
                status: list[str] = Query(default=[]), sumber: list[str] = Query(default=[]),
                akses: list[str] = Query(default=[]),
                sort: str = "terbaru", page: int = Query(1, ge=1),
                page_size: int = Query(8, ge=1, le=100),
                mode: S.SearchMethod = "lexical"):
        """Tabel Knowledge Base. ``mode`` selain lexical memakai indeks vektor:
        hasil diurutkan menurut kemiripan makna dan tiap baris membawa pasal
        yang paling cocok (``cocok``) sebagai bukti."""
        s = st()
        started = time.perf_counter()
        filters = dict(kategori=kategori, jenis=jenis, tahun=tahun, topik=topik,
                       status=status, sumber=sumber, akses=akses)
        if mode == "lexical" or not (q and q.strip()):
            with s.lock:
                out = s.read.list(q=q, sort=sort, page=page, page_size=page_size, **filters)
            out.update(mode="lexical", waktu_ms=round((time.perf_counter() - started) * 1000, 2))
            return out
        if not s.vectors.ready(mode):
            raise HTTPException(503, f"indeks '{mode}' belum dibangun — jalankan `hero vector build`")
        with s.lock:
            allowed = s.read.filtered_ids(**filters)
        # In a similarity ranking every document scores *something*, so "total"
        # is defined as the top-N cut (SEMANTIC_MAX_RESULTS), not a match count.
        hits = s.vectors.search(q, mode, k=SEMANTIC_MAX_RESULTS, allowed_docs=allowed)
        window = hits[(page - 1) * page_size: page * page_size]
        with s.lock:
            items = s.read.items_by_id([h.doc_id for h in window])
        rows = []
        for h in window:
            if h.doc_id in items:
                item = items[h.doc_id]
                item["cocok"] = _match(h)
                rows.append(item)
        total = len(hits)
        return {"items": rows, "total": total, "page": page, "page_size": page_size,
                "pages": (total + page_size - 1) // page_size, "mode": mode,
                "waktu_ms": round((time.perf_counter() - started) * 1000, 2)}

    @app.get("/api/kb/facets", tags=["knowledge-base"])
    def kb_facets() -> dict[str, list[S.FacetValue]]:
        s = st()
        with s.lock:
            return s.read.facets()

    @app.get("/api/kb/documents/{doc_id}", response_model=S.KbDetail, tags=["knowledge-base"])
    def kb_detail(doc_id: str):
        s = st()
        with s.lock:
            d = s.read.get(doc_id)
        if d is None:
            raise HTTPException(404, "dokumen tidak ditemukan")
        return d

    @app.get("/api/kb/documents/{doc_id}/relations", tags=["knowledge-base", "graph"])
    def kb_relations(doc_id: str):
        """Relasi hukum dokumen: dasar hukum, pencabutan, perubahan, penerus."""
        s = st()
        with s.lock:
            key = gq.node_for_document(s.conn, doc_id)
            if key is None:
                raise HTTPException(404, "dokumen belum memiliki node graf")
            return {"node": gq.get_node(s.conn, key), "relasi": gq.neighbors(s.conn, key),
                    "lineage": gq.lineage(s.conn, key)}

    @app.get("/api/kb/documents/{doc_id}/pdf", tags=["knowledge-base"],
             responses={200: {"content": {"application/pdf": {}}}, 409: {}, 404: {}})
    def kb_pdf(doc_id: str):
        """"Lihat Dokumen PDF Asli".

        Served from disk when present. Otherwise fetched again from the
        source and served only if its SHA-256 equals the hash recorded at
        ingest — the hash is the proof that this is the same document HERO
        analysed, so the disk copy can be pruned without losing that proof.
        """
        s = st()
        with s.lock:
            row = s.conn.execute("SELECT stored_path, sha256, source_ref, original_filename "
                                 "FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "dokumen tidak ditemukan")
        kb_root = Path(s.settings.knowledge_base).resolve()
        path = Path(row["stored_path"] or "").resolve() if row["stored_path"] else None
        headers = {"X-HERO-SHA256": row["sha256"] or ""}
        if path and path.is_file() and kb_root in path.parents:
            headers["X-HERO-Asal"] = "salinan-lokal"
            return FileResponse(path, media_type="application/pdf", headers=headers,
                                filename=row["original_filename"] or path.name,
                                content_disposition_type="inline")
        ref = row["source_ref"] or ""
        if not ref.startswith(("http://", "https://")):
            raise HTTPException(404, "salinan lokal tidak ada dan sumber bukan URL publik")
        try:
            resp = requests.get(ref, timeout=60, headers={"User-Agent": s.settings.scraper.user_agent})
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise HTTPException(502, f"gagal mengambil ulang dari sumber: {exc}") from exc
        digest = hashlib.sha256(resp.content).hexdigest()
        if digest != row["sha256"]:
            return JSONResponse(status_code=409, content={
                "galat": "Isi dokumen di sumber berbeda dari yang dianalisis HERO",
                "sha256_tercatat": row["sha256"], "sha256_sumber": digest, "sumber": ref})
        headers["X-HERO-Asal"] = "diambil-ulang-terverifikasi"
        return Response(resp.content, media_type="application/pdf", headers=headers)

    # ------------------------------------------------------------- analisa
    @app.get("/api/analisa/{doc_id}", tags=["analisa"])
    def analisa(doc_id: str, mode: str = Query("deterministik", pattern="^(deterministik|ai)$")):
        """Fase 2: ringkasan terstruktur + poin kunci (Deterministik), dan narasi AI
        bila diminta dan tersedia. ``mode_dipakai`` + ``ai.alasan`` selalu
        menjelaskan mode mana yang akhirnya dipakai dan mengapa."""
        s = st()
        with s.lock:
            out = analysis_payload(s.conn, doc_id, mode=mode, narrator=s.narrator)
        if out is None:
            raise HTTPException(404, "dokumen tidak ditemukan")
        return out

    @app.get("/api/analisa/{doc_id}/klausul", tags=["analisa"])
    def klausul(doc_id: str, kebutuhan: str = Query(..., min_length=3), k: int = Query(5, ge=1, le=20)):
        """Pasal dalam satu dokumen yang paling relevan dengan kebutuhan pengguna."""
        s = st()
        with s.lock:
            return find_clauses(s.vectors, doc_id, kebutuhan, k=k, conn=s.conn)

    @app.get("/api/analisa-status", tags=["analisa"])
    def analisa_status():
        return {"ai": st().narrator.status()}

    # --------------------------------------------------------------- ingest
    @app.post("/api/ingest/scans", response_model=S.StartedResponse, status_code=202, tags=["ingest"])
    def start_url_scan(body: S.UrlScanRequest):
        try:
            sid = st().flows.start_url_scan(str(body.url), depth=body.kedalaman,
                                            kategori=body.kategori, sektor=body.sektor,
                                            jenis=body.jenis, max_items=body.maks_item)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"id": sid, "status_url": f"/api/ingest/scans/{sid}"}

    @app.get("/api/ingest/scans/{scan_id}", tags=["ingest"])
    def get_scan(scan_id: str, status_kbs: Optional[str] = None):
        """Hasil Pemindaian. Poll sampai ``status.value`` bukan 'berjalan'."""
        out = st().flows.scan(scan_id, status_kbs)
        if out is None:
            raise HTTPException(404, "pemindaian tidak ditemukan")
        return out

    @app.post("/api/ingest/jobs", response_model=S.StartedResponse, status_code=202, tags=["ingest"])
    def start_job(body: S.IngestJobRequest):
        try:
            jid = st().flows.start_ingest(body.scan_id, body.item_ids, body.kategori)
        except KeyError:
            raise HTTPException(404, "pemindaian tidak ditemukan") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"id": jid, "status_url": f"/api/ingest/jobs/{jid}"}

    @app.get("/api/ingest/jobs/{job_id}", tags=["ingest"])
    def get_job(job_id: str):
        """Proses Ingest (progress bar) dan Dokumen Berhasil Ditambahkan."""
        out = st().flows.job(job_id)
        if out is None:
            raise HTTPException(404, "job tidak ditemukan")
        return out

    @app.get("/api/ingest/history", tags=["ingest"])
    def history(jenis: str = Query("url", pattern="^(url|sinkronisasi)$"), limit: int = 3):
        return st().flows.history(jenis, limit)

    # ----------------------------------------------------------------- sync
    @app.get("/api/sync/sources", tags=["sync"])
    def sync_sources():
        """Sumber OneDrive terdaftar + status koneksi (di-cache 5 menit)."""
        s = st()
        out = []
        for sh in s.settings.onedrive_shares:
            d = s.link_status(sh.share_url)
            out.append({"sumber": "onedrive", "nama": sh.name, "subfolder": sh.subfolder,
                        "aktif": sh.enabled,
                        "koneksi": {"value": "terhubung" if d.accessible else "gagal",
                                    "label": "Terhubung" if d.accessible else "Gagal Terhubung",
                                    "tone": "success" if d.accessible else "danger",
                                    "alasan": None if d.accessible else d.reason}})
        for f in s.settings.folders:
            ok = Path(f.path).expanduser().is_dir()
            out.append({"sumber": "folder", "nama": f.name, "path": f.path, "aktif": f.enabled,
                        "koneksi": {"value": "terhubung" if ok else "gagal",
                                    "label": "Tersedia" if ok else "Tidak Ditemukan",
                                    "tone": "success" if ok else "danger", "alasan": None}})
        return out

    @app.post("/api/sync/scans", response_model=S.StartedResponse, status_code=202, tags=["sync"])
    def start_sync_scan(body: S.SyncScanRequest):
        s = st()
        share_url, subfolder, nama = body.share_url, body.subfolder, body.sumber_nama
        if body.sumber == "onedrive":
            if not share_url:
                cfg = next((x for x in s.settings.onedrive_shares
                            if not nama or x.name == nama), None)
                if cfg is None:
                    raise HTTPException(422, "tidak ada sumber OneDrive terdaftar")
                share_url, subfolder, nama = cfg.share_url, subfolder or cfg.subfolder, cfg.name
        elif not body.path:
            raise HTTPException(422, "path wajib diisi untuk folder lokal")
        sid = s.flows.start_sync_scan(sumber=body.sumber, share_url=share_url, subfolder=subfolder,
                                      path=body.path, nama=nama, kategori=body.kategori,
                                      akses=body.klasifikasi_akses, max_items=body.maks_item)
        return {"id": sid, "status_url": f"/api/ingest/scans/{sid}"}

    # --------------------------------------------------------------- search
    @app.get("/api/search", tags=["search"])
    def search(q: str, method: S.SearchMethod = "hybrid", k: int = Query(10, ge=1, le=50)):
        s = st()
        if not s.vectors.ready(method):
            raise HTTPException(503, f"indeks '{method}' belum dibangun — jalankan `hero vector build`")
        started = time.perf_counter()
        hits = s.vectors.search(q, method, k=k)
        with s.lock:
            items = s.read.items_by_id([h.doc_id for h in hits])
        return {"q": q, "method": method, "waktu_ms": round((time.perf_counter() - started) * 1000, 2),
                "hasil": [dict(items[h.doc_id], cocok=_match(h)) for h in hits if h.doc_id in items]}

    @app.get("/api/search/compare", tags=["search"])
    def compare(q: str, k: int = Query(5, ge=1, le=20)):
        """Satu kueri, empat metode, berdampingan — untuk membandingkan
        relasional (kata kunci) dengan vektor secara langsung."""
        s = st()
        out = {}
        for method in ("lexical", "lsa", "semantic", "hybrid"):
            if not s.vectors.ready(method):
                out[method] = {"tersedia": False}
                continue
            started = time.perf_counter()
            hits = s.vectors.search(q, method, k=k)
            ms = round((time.perf_counter() - started) * 1000, 2)
            with s.lock:
                items = s.read.items_by_id([h.doc_id for h in hits])
            out[method] = {"tersedia": True, "waktu_ms": ms,
                           "hasil": [{"id": h.doc_id, "judul": items.get(h.doc_id, {}).get("judul"),
                                      "skor": round(h.score, 4), "cocok": _match(h)} for h in hits]}
        return {"q": q, "metode": out}

    # ---------------------------------------------------------------- graph
    @app.get("/api/graph/stats", tags=["graph"])
    def graph_stats():
        s = st()
        with s.lock:
            return gq.stats(s.conn)

    @app.get("/api/graph/findings", tags=["graph"])
    def graph_findings(limit: int = Query(20, ge=1, le=200)):
        """Ketidaksesuaian antara relasi graf dan status tercatat."""
        s = st()
        with s.lock:
            return status_findings(s.conn, limit)

    @app.get("/api/graph/nodes/{key:path}/lineage", tags=["graph"])
    def graph_lineage(key: str):
        return _graph(key, lambda c: gq.lineage(c, key))

    @app.get("/api/graph/nodes/{key:path}/impact", tags=["graph"])
    def graph_impact(key: str, max_depth: int = Query(3, ge=1, le=6)):
        return _graph(key, lambda c: gq.impact(c, key, max_depth))

    @app.get("/api/graph/nodes/{key:path}/basis", tags=["graph"])
    def graph_basis(key: str, max_depth: int = Query(4, ge=1, le=6)):
        return _graph(key, lambda c: gq.basis(c, key, max_depth))

    @app.get("/api/graph/nodes/{key:path}", tags=["graph"])
    def graph_node(key: str):
        return _graph(key, lambda c: {"node": gq.get_node(c, key), "relasi": gq.neighbors(c, key)})

    def _graph(key: str, fn):
        s = st()
        with s.lock:
            if gq.get_node(s.conn, key) is None:
                raise HTTPException(404, f"node '{key}' tidak ada — format kunci: JENIS|nomor|tahun")
            return fn(s.conn)

    return app


def _match(h) -> dict[str, Any]:
    ref = h.best_ref
    if ref and h.best_level == "pasal" and ref.strip().isdigit():
        ref = f"Pasal {ref.strip()}"
    return {"rujukan": ref, "level": h.best_level, "halaman": h.best_page,
            "cuplikan": (h.best_text or "")[:280], "skor": round(h.score, 4),
            "jumlah_potongan_cocok": h.matches, **({"peringkat": h.ranks} if h.ranks else {})}
