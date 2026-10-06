"""Akses pgvector di Postgres backend — untuk benchmark dan pencarian pasal.

Dua pemakaian:

* ``PgVectorStore`` membangun tabel vektor sementara dan mengukurnya
  (``hero bench vektor``): tanpa indeks (exact), IVFFlat, dan HNSW.
* ``search_articles`` mencari pasal termirip langsung di tabel ``articles``
  milik backend — jalan temu-kembali yang dipakai layar Harmonisasi dan
  "cari pasal mirip" ketika korpus tinggal di Postgres, bukan di SQLite.

Vektor dikirim sebagai literal teks ``'[0.1,0.2,…]'::vector`` supaya modul ini
tidak bergantung pada paket ``pgvector`` versi tertentu; hanya ekstensi
``vector`` di servernya yang wajib ada (backend sudah mengaktifkannya di
migrasi ``19ab55fb7e4e_fase1_baseline_schema``).

Semua vektor HERO ber-norma 1, jadi jarak cosine ``<=>`` = 1 − dot product,
dan peringkatnya identik dengan pencarian di sisi SQLite — itulah yang membuat
perbandingan kedua penyimpanan setara.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Iterable, Sequence

log = logging.getLogger("hero.bridge.pg")

ENV_DSN = "HERO_PG_DSN"
# Dipakai backend di .env-nya; diterima sebagai alias agar satu .env cukup.
ENV_DSN_ALIAS = "DATABASE_URL"


class PgUnavailable(RuntimeError):
    """Postgres/pgvector tidak dapat dipakai — pesannya menyebutkan cara memperbaikinya."""


def normalise_dsn(dsn: str) -> str:
    """``postgresql+psycopg://…`` (gaya SQLAlchemy) → DSN libpq biasa."""
    return re.sub(r"^postgresql\+\w+://", "postgresql://", dsn.strip())


def dsn_from_env() -> str | None:
    raw = os.environ.get(ENV_DSN) or os.environ.get(ENV_DSN_ALIAS)
    return normalise_dsn(raw) if raw else None


def redact_dsn(dsn: str) -> str:
    """Buang kata sandi sebelum DSN masuk log atau laporan."""
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", dsn)


def connect(dsn: str | None = None, *, timeout: int = 10):
    """Koneksi psycopg ke Postgres backend, dengan ekstensi ``vector`` dipastikan ada."""
    dsn = normalise_dsn(dsn) if dsn else dsn_from_env()
    if not dsn:
        raise PgUnavailable(
            f"DSN Postgres tidak diketahui. Setel {ENV_DSN} (atau {ENV_DSN_ALIAS}) di .env, "
            f"mis. postgresql://hero_user:…@127.0.0.1:5432/hero_db")
    try:
        import psycopg
    except ImportError as exc:
        raise PgUnavailable("psycopg belum terpasang. Pasang: pip install -e '.[pg]'") from exc
    try:
        conn = psycopg.connect(dsn, connect_timeout=timeout, autocommit=True)
    except Exception as exc:                                       # noqa: BLE001
        raise PgUnavailable(f"tidak bisa terhubung ke {redact_dsn(dsn)}: {exc}") from exc
    with conn.cursor() as cur:
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        if cur.fetchone() is None:
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            except Exception as exc:                               # noqa: BLE001
                conn.close()
                raise PgUnavailable(
                    f"ekstensi pgvector tidak aktif dan tidak bisa diaktifkan: {exc}. "
                    f"Pakai image ankane/pgvector (seperti docker-compose backend) atau "
                    f"pasang paket postgresql-NN-pgvector.") from exc
    return conn


def vec_literal(vec: Sequence[float]) -> str:
    """Format literal pgvector. ``repr`` float Python sudah round-trip-safe."""
    return "[" + ",".join(f"{float(x):.7g}" for x in vec) + "]"


def server_version(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("SHOW server_version")
        ver = cur.fetchone()[0]
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        row = cur.fetchone()
    return f"PostgreSQL {ver} + pgvector {row[0] if row else '?'}"


class PgVectorStore:
    """Tabel vektor terukur: isi, indeks, cari, ukur. Dipakai benchmark."""

    def __init__(self, conn, table: str, dim: int):
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", table):
            raise ValueError(f"nama tabel tidak aman: {table!r}")
        self.conn = conn
        self.table = table
        self.dim = int(dim)

    # -- bangun ----------------------------------------------------------
    def create(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {self.table}")
            cur.execute(f"CREATE TABLE {self.table} ("
                        f"rowid integer PRIMARY KEY, doc_id text, ref text, "
                        f"embedding vector({self.dim}))")

    def insert(self, rows: Iterable[tuple[int, str, str | None, Sequence[float]]],
               *, batch: int = 500) -> dict[str, Any]:
        started = time.perf_counter()
        n = 0
        buf: list[tuple] = []
        with self.conn.cursor() as cur:
            for rowid, doc_id, ref, vec in rows:
                buf.append((int(rowid), doc_id, ref, vec_literal(vec)))
                if len(buf) >= batch:
                    cur.executemany(f"INSERT INTO {self.table} VALUES (%s,%s,%s,%s::vector)", buf)
                    n += len(buf)
                    buf.clear()
            if buf:
                cur.executemany(f"INSERT INTO {self.table} VALUES (%s,%s,%s,%s::vector)", buf)
                n += len(buf)
        return {"baris": n, "detik": round(time.perf_counter() - started, 2)}

    def copy_insert(self, rows: Iterable[tuple[int, str, str | None, Sequence[float]]]
                    ) -> dict[str, Any]:
        """Muat massal lewat ``COPY`` — jauh lebih cepat dari INSERT per baris."""
        started = time.perf_counter()
        n = 0
        with self.conn.cursor() as cur:
            with cur.copy(f"COPY {self.table} (rowid, doc_id, ref, embedding) FROM STDIN") as cp:
                for rowid, doc_id, ref, vec in rows:
                    cp.write_row((int(rowid), doc_id, ref, vec_literal(vec)))
                    n += 1
        return {"baris": n, "detik": round(time.perf_counter() - started, 2)}

    def analyze(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(f"ANALYZE {self.table}")

    def reset_search_params(self) -> None:
        """Kembalikan ivfflat.probes / hnsw.ef_search ke bawaan server."""
        with self.conn.cursor() as cur:
            cur.execute("RESET ivfflat.probes")
            cur.execute("RESET hnsw.ef_search")

    def drop_indexes(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = %s "
                        "AND indexname LIKE %s", (self.table, f"{self.table}_vec_%"))
            for (name,) in cur.fetchall():
                cur.execute(f"DROP INDEX IF EXISTS {name}")

    def create_index(self, kind: str, **opts: Any) -> dict[str, Any]:
        """``ivfflat`` (lists) atau ``hnsw`` (m, ef_construction). Cosine ops."""
        name = f"{self.table}_vec_{kind}"
        if kind == "ivfflat":
            lists = int(opts.get("lists") or 100)
            ddl = (f"CREATE INDEX {name} ON {self.table} USING ivfflat "
                   f"(embedding vector_cosine_ops) WITH (lists = {lists})")
            params = {"lists": lists}
        elif kind == "hnsw":
            m = int(opts.get("m") or 16)
            efc = int(opts.get("ef_construction") or 64)
            ddl = (f"CREATE INDEX {name} ON {self.table} USING hnsw "
                   f"(embedding vector_cosine_ops) WITH (m = {m}, ef_construction = {efc})")
            params = {"m": m, "ef_construction": efc}
        else:
            raise ValueError(f"jenis indeks tidak dikenal: {kind}")
        started = time.perf_counter()
        with self.conn.cursor() as cur:
            cur.execute(f"DROP INDEX IF EXISTS {name}")
            cur.execute(ddl)
        return {"indeks": kind, "parameter": params,
                "detik_bangun": round(time.perf_counter() - started, 2),
                "ukuran_mb": self.index_size_mb(name)}

    # -- cari ------------------------------------------------------------
    def search(self, qvec: Sequence[float], k: int, *, probes: int | None = None,
               ef_search: int | None = None) -> list[tuple[int, float]]:
        # ``SET`` (lingkup sesi), bukan ``SET LOCAL``: koneksi ini autocommit,
        # jadi tidak ada transaksi yang bisa dilingkupi ``LOCAL`` — ia akan
        # diabaikan tanpa galat, dan sapuan probes/ef_search jadi tidak
        # berpengaruh sama sekali (terbaca sebagai recall yang datar).
        with self.conn.cursor() as cur:
            if probes is not None:
                cur.execute(f"SET ivfflat.probes = {int(probes)}")
            if ef_search is not None:
                cur.execute(f"SET hnsw.ef_search = {int(ef_search)}")
            cur.execute(f"SELECT rowid, embedding <=> %s::vector AS d FROM {self.table} "
                        f"ORDER BY d LIMIT %s", (vec_literal(qvec), int(k)))
            return [(int(r[0]), 1.0 - float(r[1])) for r in cur.fetchall()]

    def plan(self, qvec: Sequence[float], k: int) -> str:
        """Rencana eksekusi — bukti indeks benar-benar dipakai, bukan asumsi."""
        with self.conn.cursor() as cur:
            cur.execute(f"EXPLAIN (COSTS OFF) SELECT rowid FROM {self.table} "
                        f"ORDER BY embedding <=> %s::vector LIMIT %s", (vec_literal(qvec), int(k)))
            return " | ".join(r[0].strip() for r in cur.fetchall())

    # -- ukur ------------------------------------------------------------
    def table_size_mb(self) -> float:
        with self.conn.cursor() as cur:
            cur.execute("SELECT pg_table_size(%s)", (self.table,))
            return round(float(cur.fetchone()[0]) / 1e6, 2)

    def index_size_mb(self, name: str) -> float:
        with self.conn.cursor() as cur:
            cur.execute("SELECT pg_relation_size(%s)", (name,))
            row = cur.fetchone()
        return round(float(row[0]) / 1e6, 2) if row else 0.0

    def count(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {self.table}")
            return int(cur.fetchone()[0])

    def drop(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {self.table}")


# --------------------------------------------------------------------------
# Pencarian di tabel articles milik backend
# --------------------------------------------------------------------------
def articles_stats(conn) -> dict[str, Any]:
    """Berapa pasal backend yang sudah punya vektor — pintu masuk diagnosa."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*), COUNT(embedding), COUNT(DISTINCT document_id) FROM articles")
        total, with_vec, docs = cur.fetchone()
        cur.execute("SELECT pg_table_size('articles')")
        size = cur.fetchone()[0]
        cur.execute("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'articles'")
        idx = [{"nama": n, "definisi": d} for n, d in cur.fetchall()]
    return {"pasal": int(total), "berembedding": int(with_vec), "dokumen": int(docs),
            "ukuran_mb": round(float(size) / 1e6, 2), "indeks": idx}


def search_articles(conn, qvec: Sequence[float], k: int = 10, *,
                    document_ids: Sequence[int] | None = None,
                    exclude_document_id: int | None = None,
                    only_access: str | None = None) -> list[dict[str, Any]]:
    """Pasal termirip di korpus backend, beserta dokumen induknya.

    ``only_access='publik'`` menyaring dokumen non-publik — dipakai bila hasil
    akan keluar dari server (snapshot, layanan AI eksternal). Penyaringan
    dilakukan di SQL, bukan setelahnya, supaya tidak ada dokumen ber-NDA yang
    sempat ikut terbaca.
    """
    where = ["a.embedding IS NOT NULL"]
    params: list[Any] = [vec_literal(qvec)]
    if document_ids:
        where.append("a.document_id = ANY(%s)")
        params.append(list(int(i) for i in document_ids))
    if exclude_document_id is not None:
        where.append("a.document_id <> %s")
        params.append(int(exclude_document_id))
    if only_access:
        where.append("d.access_classification = %s")
        params.append(only_access)
    params.append(int(k))
    sql = (f"SELECT a.id, a.document_id, a.article_number, a.chapter_title, a.content_text, "
           f"d.title, d.regulation_number, d.regulation_type, d.status_keberlakuan, "
           f"1 - (a.embedding <=> %s::vector) AS skor "
           f"FROM articles a JOIN documents d ON d.id = a.document_id "
           f"WHERE {' AND '.join(where)} ORDER BY a.embedding <=> %s::vector LIMIT %s")
    # Vektor kueri muncul dua kali (SELECT dan ORDER BY): satu parameter lagi,
    # di posisi kedua dari belakang.
    params.insert(len(params) - 1, vec_literal(qvec))
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [{"article_id": r[0], "document_id": r[1], "pasal": r[2], "bab": r[3],
             "kutipan": (r[4] or "")[:400], "judul": r[5], "nomor": r[6], "jenis": r[7],
             "status": r[8], "skor": round(float(r[9]), 4)} for r in rows]


# --------------------------------------------------------------------------
# Pengisian vektor (satu-satunya jalur TULIS ke Postgres backend)
# --------------------------------------------------------------------------
# Kolom ``articles.embedding`` memang disiapkan backend untuk diisi lapisan
# data ("diisi pipeline ML" — app/models/article.py). Pengisian ulang massal
# tidak bisa lewat ``POST /internal/articles`` karena endpoint itu selalu
# INSERT; mengirim ulang akan menggandakan pasal. Karena itu backfill menulis
# langsung, hanya ke kolom embedding, hanya pada baris yang ditunjuk, dan
# tidak pernah menyentuh kolom lain.
def articles_without_embedding(conn, *, limit: int = 1000,
                               document_ids: Sequence[int] | None = None) -> list[dict[str, Any]]:
    where = ["a.embedding IS NULL", "a.level = 'pasal'",
             "a.content_text IS NOT NULL", "length(a.content_text) > 0"]
    params: list[Any] = []
    if document_ids:
        where.append("a.document_id = ANY(%s)")
        params.append([int(i) for i in document_ids])
    params.append(int(limit))
    with conn.cursor() as cur:
        cur.execute(f"SELECT a.id, a.document_id, a.article_number, a.content_text FROM articles a "
                    f"WHERE {' AND '.join(where)} ORDER BY a.document_id, a.id LIMIT %s", params)
        return [{"id": r[0], "document_id": r[1], "pasal": r[2], "teks": r[3]}
                for r in cur.fetchall()]


def set_embeddings(conn, rows: Iterable[tuple[int, Sequence[float]]], *,
                   batch: int = 200) -> int:
    """``UPDATE articles SET embedding`` untuk baris yang ditunjuk. Mengembalikan jumlah baris."""
    n = 0
    buf: list[tuple[str, int]] = []
    with conn.cursor() as cur:
        for article_id, vec in rows:
            buf.append((vec_literal(vec), int(article_id)))
            if len(buf) >= batch:
                cur.executemany("UPDATE articles SET embedding = %s::vector WHERE id = %s", buf)
                n += len(buf)
                buf.clear()
        if buf:
            cur.executemany("UPDATE articles SET embedding = %s::vector WHERE id = %s", buf)
            n += len(buf)
    return n


def embedding_dim(conn) -> int | None:
    """Dimensi kolom ``articles.embedding`` yang sebenarnya ada di server."""
    with conn.cursor() as cur:
        cur.execute("SELECT atttypmod FROM pg_attribute WHERE attrelid = 'articles'::regclass "
                    "AND attname = 'embedding'")
        row = cur.fetchone()
    return int(row[0]) if row and row[0] and row[0] > 0 else None
