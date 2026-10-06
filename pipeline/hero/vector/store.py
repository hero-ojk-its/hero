"""Vector store and retrieval, kept in its own SQLite file.

Layout of ``data/hero_vectors.db``:

* ``chunk``        one row per embedded unit (Pasal window, section, …)
* ``chunk_fts``    FTS5 over the *same* chunks — the lexical baseline, so the
                   lexical-vs-vector comparison is on identical units
* ``emb_<name>``   float32 vectors as BLOBs (portable; NumPy search path)
* ``vec_<name>``   sqlite-vec ``vec0`` virtual table (in-database KNN path)
* ``emb_cache``    vectors keyed by text hash, so a rebuild only embeds
                   text it has never seen (the semantic model is the slow part)

Why a separate file: vectors are derived data. They can be deleted and
rebuilt from the catalog at any time, are an order of magnitude larger than
the catalog's metadata, and a separate file keeps the catalog small to back up.

Search always returns *documents*, each with the best-matching passage, because
the UI lists documents; the passage (``Pasal 12``, page, snippet) is what makes
a semantic match checkable by a human instead of a black box.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from hero.vector.chunking import Chunk

try:
    import sqlite_vec
    HAS_SQLITE_VEC = True
except ImportError:   # the store still works — NumPy path only
    sqlite_vec = None
    HAS_SQLITE_VEC = False

RRF_K = 60
# Above this many chunks the float32 matrix stops being "small" (~770 MB at
# 384 dims), and on-disk sqlite-vec search becomes the sensible default.
NUMPY_MAX_ROWS = 500_000
_STOPWORDS = {"yang", "dan", "di", "ke", "dari", "untuk", "dengan", "pada", "dalam", "atau",
              "ini", "itu", "oleh", "bagi", "tentang", "sebagai", "adalah", "akan", "apa",
              "bagaimana", "aturan", "peraturan", "mengenai", "soal", "terkait"}


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if HAS_SQLITE_VEC:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    return conn


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def lexical_or_query(q: str) -> str | None:
    """Natural-language query → FTS5 OR-query of its content words.

    OR, not AND: this is the *retrieval* baseline (rank by BM25 over any
    matching word), which is how lexical search engines are normally
    compared against vector search. An AND query returns nothing for most
    paraphrased questions and would make the baseline look worse than it is.
    """
    toks = [t for t in re.findall(r"[a-z0-9]{3,}", q.lower()) if t not in _STOPWORDS][:20]
    return " OR ".join(f'"{t}"' for t in toks) if toks else None


@dataclass
class Hit:
    doc_id: str
    score: float
    best_ref: str | None
    best_level: str
    best_page: int | None
    best_text: str
    matches: int = 1
    ranks: dict[str, int] = field(default_factory=dict)


class VectorStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.conn = _connect(self.path)
        self._matrices: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS chunk (
                rowid INTEGER PRIMARY KEY, chunk_id TEXT UNIQUE, doc_id TEXT, level TEXT,
                ref TEXT, part INTEGER, page INTEGER, text TEXT);
            CREATE INDEX IF NOT EXISTS ix_chunk_doc ON chunk(doc_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
                text, content='chunk', content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2');
            CREATE TABLE IF NOT EXISTS emb_cache (name TEXT, sha TEXT, vec BLOB,
                PRIMARY KEY (name, sha));
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        """)

    # -- build -----------------------------------------------------------
    def replace_chunks(self, chunks: list[Chunk]) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM chunk")
            self.conn.executemany(
                "INSERT INTO chunk (chunk_id, doc_id, level, ref, part, page, text) VALUES (?,?,?,?,?,?,?)",
                [(c.chunk_id, c.doc_id, c.level, c.ref, c.part, c.page, c.text) for c in chunks])
            self.conn.execute("INSERT INTO chunk_fts(chunk_fts) VALUES ('rebuild')")
        self._matrices.clear()

    def index(self, embedder, *, use_cache: bool = True, batch: int = 256) -> dict[str, Any]:
        """Embed every chunk with ``embedder``; reuse cached vectors by text hash."""
        name, dim = embedder.name, embedder.dim
        # Cache key includes the model: vectors from MiniLM must never be
        # reused after switching to e5 (same name "semantic", different space).
        cache_name = f"{name}:{getattr(embedder, 'model_key', '')}"
        rows = self.conn.execute("SELECT rowid, text FROM chunk ORDER BY rowid").fetchall()
        started = time.perf_counter()
        vecs = np.zeros((len(rows), dim), dtype=np.float32)
        todo: list[int] = []
        if use_cache:
            cached = {r["sha"]: r["vec"] for r in self.conn.execute(
                "SELECT sha, vec FROM emb_cache WHERE name = ?", (cache_name,))}
        else:
            cached = {}
        for i, r in enumerate(rows):
            blob = cached.get(_sha(r["text"]))
            if blob is not None and len(blob) == dim * 4:
                vecs[i] = np.frombuffer(blob, dtype=np.float32)
            else:
                todo.append(i)
        for s in range(0, len(todo), batch):
            idx = todo[s:s + batch]
            passages = [rows[i]["text"] for i in idx]
            vecs[idx] = (embedder.embed_passages(passages) if hasattr(embedder, "embed_passages")
                         else embedder.embed(passages))
        with self.conn:
            if use_cache and todo:
                self.conn.executemany(
                    "INSERT OR REPLACE INTO emb_cache (name, sha, vec) VALUES (?, ?, ?)",
                    [(cache_name, _sha(rows[i]["text"]), vecs[i].tobytes()) for i in todo])
            self.conn.execute(f"DROP TABLE IF EXISTS emb_{name}")
            self.conn.execute(f"CREATE TABLE emb_{name} (rowid INTEGER PRIMARY KEY, vec BLOB)")
            self.conn.executemany(f"INSERT INTO emb_{name} (rowid, vec) VALUES (?, ?)",
                                  [(r["rowid"], vecs[i].tobytes()) for i, r in enumerate(rows)])
            if HAS_SQLITE_VEC:
                self.conn.execute(f"DROP TABLE IF EXISTS vec_{name}")
                self.conn.execute(f"CREATE VIRTUAL TABLE vec_{name} USING vec0("
                                  f"embedding float[{dim}] distance_metric=cosine)")
                self.conn.executemany(f"INSERT INTO vec_{name} (rowid, embedding) VALUES (?, ?)",
                                      [(r["rowid"], vecs[i].tobytes()) for i, r in enumerate(rows)])
            self.conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (f"dim_{name}", str(dim)))
            self.conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)",
                              (f"model_{name}", getattr(embedder, "model_name", name)))
        self._matrices.pop(name, None)
        return {"embedder": name, "chunks": len(rows), "baru_diembed": len(todo),
                "dari_cache": len(rows) - len(todo),
                "detik": round(time.perf_counter() - started, 2)}

    # -- stats -----------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        levels = dict(self.conn.execute("SELECT level, COUNT(*) FROM chunk GROUP BY 1").fetchall())
        emb = [r[0][4:] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'emb\\_%' ESCAPE '\\' "
            "AND name <> 'emb_cache'")]
        return {"chunk": sum(levels.values()), "per_level": levels,
                "dokumen": self.conn.execute("SELECT COUNT(DISTINCT doc_id) FROM chunk").fetchone()[0],
                "embedder": emb, "sqlite_vec": HAS_SQLITE_VEC,
                "ukuran_mb": round(self.path.stat().st_size / 1e6, 2) if self.path.exists() else 0}

    def has(self, name: str) -> bool:
        return self.conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?",
                                 (f"emb_{name}",)).fetchone() is not None

    # -- chunk-level retrieval ------------------------------------------
    def _row_count(self, name: str) -> int:
        if name in self._matrices:
            return len(self._matrices[name][0])
        return self.conn.execute(f"SELECT COUNT(*) FROM emb_{name}").fetchone()[0]

    def _matrix(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        if name not in self._matrices:
            rows = self.conn.execute(f"SELECT rowid, vec FROM emb_{name} ORDER BY rowid").fetchall()
            ids = np.array([r[0] for r in rows], dtype=np.int64)
            mat = np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rows]) if rows \
                else np.zeros((0, 1), dtype=np.float32)
            self._matrices[name] = (ids, mat)
        return self._matrices[name]

    def knn(self, name: str, qvec: np.ndarray, k: int, *, engine: str = "auto") -> list[tuple[int, float]]:
        """Top-k chunk rowids by cosine similarity. engine: 'sqlite-vec' | 'numpy' | 'auto'."""
        q = np.asarray(qvec, dtype=np.float32).reshape(-1)
        if engine == "auto":
            # Measured (hero bench, 7,970 chunks): NumPy on a cached matrix
            # 0.09 ms vs sqlite-vec 3.1 ms — both exact. The matrix is ~12 MB
            # here, so memory wins; sqlite-vec takes over only when the index
            # is too large to keep resident (it reads from disk per query).
            rows = self._row_count(name)
            engine = "numpy" if rows <= NUMPY_MAX_ROWS or not HAS_SQLITE_VEC else "sqlite-vec"
        if engine == "sqlite-vec":
            rows = self.conn.execute(
                f"SELECT rowid, distance FROM vec_{name} WHERE embedding MATCH ? AND k = ? "
                f"ORDER BY distance", (q.tobytes(), int(k))).fetchall()
            return [(r[0], 1.0 - float(r[1])) for r in rows]
        ids, mat = self._matrix(name)
        if not len(ids):
            return []
        scores = mat @ q
        k = min(k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(int(ids[i]), float(scores[i])) for i in top]

    def lexical(self, q: str, k: int) -> list[tuple[int, float]]:
        match = lexical_or_query(q)
        if not match:
            return []
        rows = self.conn.execute(
            "SELECT rowid, bm25(chunk_fts) AS s FROM chunk_fts WHERE chunk_fts MATCH ? "
            "ORDER BY s LIMIT ?", (match, int(k))).fetchall()
        return [(r[0], -float(r[1])) for r in rows]    # bm25: lower is better

    # -- document-level search ------------------------------------------
    def _aggregate(self, ranked: list[tuple[int, float]], k: int, allowed: set[str] | None,
                   levels: set[str] | None) -> list[Hit]:
        if not ranked:
            return []
        info = {r["rowid"]: r for r in self.conn.execute(
            f"SELECT rowid, doc_id, level, ref, page, text FROM chunk WHERE rowid IN "
            f"({', '.join(str(int(i)) for i, _ in ranked)})")}
        hits: dict[str, Hit] = {}
        for rowid, score in ranked:
            c = info.get(rowid)
            if c is None or (allowed is not None and c["doc_id"] not in allowed):
                continue
            if levels and c["level"] not in levels:
                continue
            h = hits.get(c["doc_id"])
            if h is None:      # ranked best-first, so the first chunk seen is the best
                hits[c["doc_id"]] = Hit(c["doc_id"], score, c["ref"], c["level"], c["page"], c["text"])
            else:
                h.matches += 1
        return sorted(hits.values(), key=lambda h: -h.score)[:k]

    def search(self, q: str, *, method: str, k: int = 10, embedder=None,
               engine: str = "auto", allowed_docs: set[str] | None = None,
               levels: set[str] | None = None, fanout: int = 12) -> list[Hit]:
        """method: 'lexical' | 'lsa' | 'semantic' | 'hybrid'."""
        n = k * fanout
        if method == "lexical":
            return self._aggregate(self.lexical(q, n), k, allowed_docs, levels)
        if method in ("lsa", "semantic"):
            qv = embedder.embed_query(q)
            return self._aggregate(self.knn(method, qv, n, engine=engine), k, allowed_docs, levels)
        if method == "hybrid":
            # Reciprocal Rank Fusion over document rankings: robust to the two
            # systems' scores being on incomparable scales (BM25 vs cosine).
            lex = self._aggregate(self.lexical(q, n), n, allowed_docs, levels)
            sem = self._aggregate(self.knn("semantic", embedder.embed_query(q), n, engine=engine),
                                  n, allowed_docs, levels)
            fused: dict[str, Hit] = {}
            for name, ranking in (("lexical", lex), ("semantic", sem)):
                for rank, h in enumerate(ranking, start=1):
                    cur = fused.get(h.doc_id)
                    if cur is None:
                        cur = fused[h.doc_id] = Hit(h.doc_id, 0.0, h.best_ref, h.best_level,
                                                    h.best_page, h.best_text, h.matches)
                    cur.score += 1.0 / (RRF_K + rank)
                    cur.ranks[name] = rank
                    if name == "semantic":   # prefer the semantic passage as evidence
                        cur.best_ref, cur.best_level, cur.best_page, cur.best_text = (
                            h.best_ref, h.best_level, h.best_page, h.best_text)
            return sorted(fused.values(), key=lambda h: -h.score)[:k]
        raise ValueError(f"unknown method: {method}")
