"""Layanan analisa untuk layar Fase 2–3, berbicara dalam ID dokumen backend.

Backend tim memegang Fase 1 (ingest, knowledge base, pemindaian). Layar
**Analisa Regulasi** dan **Harmonisasi** butuh mesin yang tinggal di lapisan
data: ringkasan terstruktur per pasal, klasifikasi temuan harmonisasi,
pencarian makna. Layanan ini mengekspos mesin itu dengan satu aturan keras:

> Setiap ``document_id`` yang masuk dan keluar adalah **id dokumen backend**,
> bukan ``doc_id`` internal katalog. Frontend tidak perlu tahu lapisan data
> punya penomoran sendiri.

Dipasang di depan sebagai ``/api/v1/ml/*`` — satu baris di reverse proxy
(contoh Caddy ada di ``docs/INTEGRASI_BACKEND.md``), sehingga dari sisi
frontend ia satu asal dengan backend dan tidak ada CORS tambahan.

Kontrak lengkap: ``docs/API_CONTRACT_ML.md``. Skema mesin: ``/api/v1/ml/openapi.json``.

Semua keluaran membawa sumbernya (pasal + halaman + tautan PDF asli) dan
berlabel *Draft / Rekomendasi* — sistem tidak mengambil keputusan.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

from hero.bridge.config import BridgeSettings, load_bridge_settings
from hero.bridge.state import BridgeState, default_path
from hero.config import Settings, load_settings

log = logging.getLogger("hero.bridge.ml_api")

NOTE = ("Draft / Rekomendasi — keluaran sistem bukan keputusan. Keputusan final tetap "
        "kewenangan Pengawas / unit terkait DPEA.")


class MlState:
    """Sumber daya yang mahal dibuat: katalog, buku besar, embedder, konfigurasi."""

    def __init__(self, settings: Settings, bridge: BridgeSettings,
                 harmonisasi_config: Path | None = None):
        self.settings = settings
        self.bridge = bridge
        self.harmonisasi_config = harmonisasi_config or Path("config/harmonisasi.yaml")
        self.state = BridgeState(default_path(settings))
        self._vs = None
        self._narrator = None
        self._embedder = None
        self._hcfg: dict[str, Any] | None = None

    def catalog(self) -> sqlite3.Connection:
        """Koneksi baru per permintaan: SQLite + thread server tidak berteman."""
        conn = sqlite3.connect(str(self.settings.catalog_db), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @property
    def vectors(self):
        if self._vs is None:
            from hero.vector import VectorService
            self._vs = VectorService(self.settings)
        return self._vs

    @property
    def narrator(self):
        if self._narrator is None:
            from hero.analysis import AiNarrator
            self._narrator = AiNarrator(self.settings.analysis)
        return self._narrator

    @property
    def embedder(self):
        if self._embedder is None:
            from hero.bridge.embed import ArticleEmbedder
            self._embedder = ArticleEmbedder(self.settings, self.bridge)
        return self._embedder

    def hcfg(self) -> dict[str, Any]:
        if self._hcfg is None:
            from hero.harmonisasi.engine import load_config
            self._hcfg = load_config(self.harmonisasi_config)
        return self._hcfg

    # -- penerjemah identitas -------------------------------------------
    def doc_id(self, document_id: int) -> str | None:
        return self.state.doc_id_for(document_id)

    def document_id(self, doc_id: str) -> int | None:
        return self.state.document_id_for(doc_id)

    def pdf_url(self, doc_id: str, page: int | None = None) -> str | None:
        """Tautan ke PDF asli di backend — tombol "buka PDF asli" (US-49a)."""
        bid = self.document_id(doc_id)
        if bid is None:
            return None
        suffix = f"#page={int(page)}" if page else ""
        return f"/api/v1/documents/{bid}/pdf{suffix}"


def _rewrite_refs(obj: Any, st: MlState) -> Any:
    """Ganti setiap ``doc_id`` katalog dengan ``document_id`` backend + tautan PDF.

    Dilakukan di satu tempat, rekursif, supaya tidak ada bentuk keluaran mesin
    (kandidat, temuan, alternatif, terdekat) yang lupa diterjemahkan ketika
    mesinnya berkembang.
    """
    if isinstance(obj, list):
        return [_rewrite_refs(x, st) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out = {k: _rewrite_refs(v, st) for k, v in obj.items()}
    doc_id = out.get("doc_id")
    if isinstance(doc_id, str):
        bid = st.document_id(doc_id)
        out["document_id"] = bid
        if "pdf" in out or "halaman" in out:
            out["pdf"] = st.pdf_url(doc_id, out.get("halaman"))
    return out


def create_app(settings: Settings | None = None, bridge: BridgeSettings | None = None,
               *, cors_origins: str = "*") -> "Any":
    from fastapi import Body, FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware

    settings = settings or load_settings()
    bridge = bridge or load_bridge_settings()
    st = MlState(settings, bridge)

    app = FastAPI(title="HERO — Layanan Analisa & Harmonisasi (lapisan data)",
                  version="1.0.0", docs_url="/docs", openapi_url="/openapi.json",
                  description=__doc__)
    origins = [o.strip() for o in cors_origins.split(",") if o.strip()] or ["*"]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=origins != ["*"],
                       allow_methods=["*"], allow_headers=["*"])

    # -- kesiapan --------------------------------------------------------
    @app.get("/health", tags=["meta"])
    def health() -> dict[str, Any]:
        """Apa yang siap dan apa yang belum — dengan cara memperbaiki yang belum."""
        conn = st.catalog()
        try:
            docs = conn.execute("SELECT COUNT(*) FROM documents WHERE status='ingested'"
                                ).fetchone()[0]
            pasal = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            halaman = conn.execute("SELECT COUNT(*) FROM articles WHERE page IS NOT NULL"
                                   ).fetchone()[0]
        except sqlite3.Error as exc:
            raise HTTPException(503, f"katalog tidak terbaca: {exc}") from exc
        finally:
            conn.close()
        vs = st.vectors
        peta = len(st.state.doc_map())
        siap = docs > 0 and peta > 0
        return {
            "status": "siap" if siap else "belum-siap",
            "korpus": {"dokumen": docs, "pasal": pasal, "pasal_berhalaman": halaman,
                       "dokumen_terpeta_ke_backend": peta},
            "vektor": {m: vs.ready(m) for m in ("lexical", "lsa", "semantic", "hybrid")},
            "mode_ai": settings.analysis.ai_enabled,
            "langkah_berikutnya": [] if siap else [
                "jalankan 'hero bridge sinkron' untuk mencerminkan korpus backend",
                "lalu 'hero vector build' bila pencarian makna dipakai"],
            "catatan": NOTE,
        }

    # -- daftar dokumen (pemilih draft di UI) ----------------------------
    @app.get("/dokumen", tags=["dokumen"])
    def dokumen(peran: Optional[str] = Query(None, pattern="^(corpus_eksisting|draft_kajian)$"),
                limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
        """Dokumen backend yang sudah tercermin di lapisan data (siap dianalisa)."""
        peta = st.state.doc_map()
        conn = st.catalog()
        try:
            rows = []
            for bid, doc_id in sorted(peta.items(), reverse=True):
                d = conn.execute("SELECT doc_id, title, subject, doc_type, number, year, "
                                 "reg_status FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
                if d is None:
                    continue
                is_draft = (d["reg_status"] or "") == "rancangan"
                if peran == "draft_kajian" and not is_draft:
                    continue
                if peran == "corpus_eksisting" and is_draft:
                    continue
                rows.append({"document_id": bid, "judul": d["subject"] or d["title"],
                             "jenis": d["doc_type"], "nomor": d["number"], "tahun": d["year"],
                             "status": d["reg_status"],
                             "peran": "draft_kajian" if is_draft else "corpus_eksisting"})
                if len(rows) >= limit:
                    break
            return {"total": len(rows), "items": rows}
        finally:
            conn.close()

    # -- analisa (URD 3.3) ----------------------------------------------
    @app.get("/analisa/{document_id}", tags=["analisa"])
    def analisa(document_id: int,
                mode: str = Query("deterministik", pattern="^(deterministik|ai)$")) -> dict[str, Any]:
        """Ringkasan terstruktur & poin kunci berbasis pasal, tiap poin mengutip pasalnya."""
        from hero.analysis import analysis_payload

        doc_id = _require_mapped(st, document_id)
        conn = st.catalog()
        try:
            out = analysis_payload(conn, doc_id, mode=mode, narrator=st.narrator)
        finally:
            conn.close()
        if out is None:
            raise HTTPException(404, f"dokumen {document_id} belum punya pasal terbaca di "
                                     f"lapisan data — jalankan ekstraksi lalu 'hero bridge sinkron'")
        out["document_id"] = document_id
        out["pdf"] = st.pdf_url(doc_id)
        out["catatan"] = NOTE
        return out

    @app.get("/analisa/{document_id}/klausul", tags=["analisa"])
    def klausul(document_id: int, kebutuhan: str = Query(..., min_length=3),
                k: int = Query(5, ge=1, le=20)) -> dict[str, Any]:
        """Pasal yang relevan dengan kebutuhan pengguna (bahan checklist tanggapan)."""
        from hero.analysis.clauses import find_clauses

        doc_id = _require_mapped(st, document_id)
        res = find_clauses(st.vectors, doc_id, kebutuhan, k=k)
        return {"document_id": document_id, "kebutuhan": kebutuhan,
                "hasil": _rewrite_refs(res, st), "catatan": NOTE}

    # -- harmonisasi (URD 3.4) ------------------------------------------
    @app.post("/harmonisasi/{document_id}", tags=["harmonisasi"])
    def harmonisasi(document_id: int,
                    pembanding: Optional[list[int]] = Body(
                        None, description="Batasi korpus ke dokumen backend ini (opsional).")
                    ) -> dict[str, Any]:
        """Draft vs korpus, per pasal: kandidat, rujukan & statusnya, temuan berlabel.

        Label: menggantikan · memperjelas · pasal_baru · duplikasi · konflik.
        Tiap temuan membawa alasan yang menyebut pasal penyebabnya, perbedaan
        konkret, dan tautan ke PDF asli pembandingnya pada halaman yang tepat.
        """
        from hero.harmonisasi.engine import draft_from_catalog, harmonise

        doc_id = _require_mapped(st, document_id)
        conn = st.catalog()
        try:
            try:
                draft = draft_from_catalog(conn, doc_id)
            except KeyError as exc:
                raise HTTPException(404, str(exc)) from exc
            report = harmonise(conn, draft, st.hcfg())
        finally:
            conn.close()
        out = _rewrite_refs(report.to_dict(), st)
        out["draft"]["document_id"] = document_id
        if pembanding:
            allowed = {int(i) for i in pembanding}
            out["temuan"] = [t for t in out["temuan"]
                             if not t.get("pembanding")
                             or t["pembanding"].get("document_id") in allowed]
        return out

    # -- pencarian -------------------------------------------------------
    @app.get("/cari", tags=["pencarian"])
    def cari(q: str = Query(..., min_length=2),
             metode: str = Query("hybrid", pattern="^(lexical|lsa|semantic|hybrid|pgvector)$"),
             k: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
        """Pencarian dokumen. ``pgvector`` mencari langsung di korpus backend."""
        if metode == "pgvector":
            return _cari_pgvector(st, q, k)
        if not st.vectors.ready(metode):
            raise HTTPException(503, f"indeks '{metode}' belum dibangun — jalankan 'hero vector build'")
        hits = st.vectors.search(q, metode, k=k)
        items = [{"document_id": st.document_id(h.doc_id), "doc_id": h.doc_id,
                  "skor": round(h.score, 4), "pasal": h.best_ref, "level": h.best_level,
                  "halaman": h.best_page, "kutipan": h.best_text[:400],
                  "pdf": st.pdf_url(h.doc_id, h.best_page)} for h in hits]
        return {"kueri": q, "metode": metode, "total": len(items), "items": items}

    @app.get("/pasal-mirip", tags=["pencarian"])
    def pasal_mirip(teks: str = Query(..., min_length=20),
                    k: int = Query(10, ge=1, le=50),
                    kecuali_dokumen: Optional[int] = Query(None),
                    hanya_publik: bool = Query(False)) -> dict[str, Any]:
        """Pasal termirip di korpus backend (pgvector) — pembanding cepat per potongan teks."""
        from hero.bridge import pg

        try:
            qvec = st.embedder.query_vector(teks)
            conn = pg.connect()
        except Exception as exc:                                  # noqa: BLE001
            raise HTTPException(503, f"pencarian vektor backend tidak siap: {exc}") from exc
        try:
            hits = pg.search_articles(conn, qvec, k, exclude_document_id=kecuali_dokumen,
                                      only_access="publik" if hanya_publik else None)
        finally:
            conn.close()
        for h in hits:
            h["pdf"] = f"/api/v1/documents/{h['document_id']}/pdf"
        return {"total": len(hits), "items": hits, "embedder": st.embedder.name,
                "mode": st.embedder.mode, "catatan": NOTE}

    return app


def _require_mapped(st: MlState, document_id: int) -> str:
    from fastapi import HTTPException

    doc_id = st.doc_id(document_id)
    if doc_id is None:
        raise HTTPException(404, f"dokumen {document_id} belum tercermin di lapisan data. "
                                 f"Jalankan: hero bridge sinkron --dokumen {document_id}")
    return doc_id


def _cari_pgvector(st: MlState, q: str, k: int) -> dict[str, Any]:
    from fastapi import HTTPException

    from hero.bridge import pg

    try:
        qvec = st.embedder.query_vector(q)
        conn = pg.connect()
    except Exception as exc:                                      # noqa: BLE001
        raise HTTPException(503, f"pgvector tidak siap: {exc}") from exc
    try:
        hits = pg.search_articles(conn, qvec, k)
    finally:
        conn.close()
    return {"kueri": q, "metode": "pgvector", "total": len(hits),
            "items": [{"document_id": h["document_id"], "skor": h["skor"], "pasal": h["pasal"],
                       "halaman": None, "kutipan": h["kutipan"], "judul": h["judul"],
                       "pdf": f"/api/v1/documents/{h['document_id']}/pdf"} for h in hits],
            "embedder": st.embedder.name}


def app_from_env():
    """Factory untuk uvicorn: konfigurasi dari ``HERO_CONFIG`` & ``HERO_ML_CORS``."""
    import os

    return create_app(cors_origins=os.environ.get("HERO_ML_CORS", "*"))
