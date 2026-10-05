"""Vector retrieval layer: chunk → embed → store → search.

Entry points: ``build_vectors`` (index the knowledge base) and
``VectorService`` (query-time, holds loaded embedders so the ONNX model is
loaded once per process, not once per request).
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from hero.config import Settings
from hero.kb import readmodel
from hero.vector.chunking import chunk_catalog
from hero.vector.embedders import SEMANTIC_MODELS, LsaEmbedder, SemanticEmbedder, semantic_available
from hero.vector.store import HAS_SQLITE_VEC, VectorStore


def vector_paths(settings: Settings) -> dict[str, Path]:
    base = Path(settings.catalog_db).parent
    return {"db": base / "hero_vectors.db", "lsa": base / "vectors" / "lsa.pkl",
            "models": base / "models"}


def build_vectors(settings: Settings, *, embedders: tuple[str, ...] = ("lsa", "semantic"),
                  progress=None) -> dict[str, Any]:
    say = progress or (lambda msg: None)
    paths = vector_paths(settings)
    started = time.perf_counter()
    with sqlite3.connect(settings.catalog_db) as cat:
        readmodel.sync(cat)
        chunks, chunk_stats = chunk_catalog(cat)
    store = VectorStore(paths["db"])
    store.replace_chunks(chunks)
    say(f"{len(chunks)} potongan dari {chunk_stats.get('dokumen', 0)} dokumen")
    report: dict[str, Any] = {"chunking": chunk_stats, "chunk": len(chunks), "indeks": []}
    if "lsa" in embedders:
        lsa = LsaEmbedder(dim=settings.vector.lsa_dim).fit([c.text for c in chunks])
        lsa.save(paths["lsa"])
        report["indeks"].append(store.index(lsa, use_cache=False))   # vocabulary changes → refit
        say("indeks LSA selesai")
    if "semantic" in embedders:
        if semantic_available():
            spec = SEMANTIC_MODELS.get(settings.vector.semantic_model, {})
            say(f"memuat model semantik {settings.vector.semantic_model} "
                f"(unduh sekali ±{spec.get('ukuran_gb', '?')} GB bila belum ada)…")
            report["indeks"].append(store.index(
                SemanticEmbedder(paths["models"], model=settings.vector.semantic_model)))
            say("indeks semantik selesai")
        else:
            report["semantic"] = "fastembed tidak terpasang — mode AI-Assisted dilewati"
    report["store"] = store.stats()
    report["detik_total"] = round(time.perf_counter() - started, 1)
    return report


class VectorService:
    """Long-lived query side. Embedders are loaded lazily and kept."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.paths = vector_paths(settings)
        self.store = VectorStore(self.paths["db"]) if self.paths["db"].exists() else None
        self._emb: dict[str, Any] = {}

    def ready(self, method: str) -> bool:
        if self.store is None:
            return False
        if method == "lexical":
            return True
        if method == "hybrid":
            return self.store.has("semantic")
        return self.store.has(method)

    def embedder(self, name: str):
        if name not in self._emb:
            if name == "lsa":
                self._emb[name] = LsaEmbedder.load(self.paths["lsa"])
            elif name == "semantic":
                self._emb[name] = SemanticEmbedder(self.paths["models"],
                                                   model=self.settings.vector.semantic_model)
            else:
                raise ValueError(name)
        return self._emb[name]

    def search(self, q: str, method: str, k: int = 10, **kw):
        emb_name = {"lsa": "lsa", "semantic": "semantic", "hybrid": "semantic"}.get(method)
        emb = self.embedder(emb_name) if emb_name else None
        return self.store.search(q, method=method, k=k, embedder=emb, **kw)


__all__ = ["HAS_SQLITE_VEC", "VectorService", "VectorStore", "build_vectors", "vector_paths"]
