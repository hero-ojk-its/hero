"""Buku besar lokal worker jembatan — ``data/hero_bridge.db``.

Kenapa perlu state sendiri padahal backend sudah punya statusnya? Karena dua
operasi di kontrak backend **tidak idempoten**:

* ``POST /internal/articles`` selalu *INSERT*. Dokumen yang diklaim ulang
  (upaya ke-2, atau klaim kedaluwarsa 30 menit) akan menggandakan pasalnya,
  dan pasal ganda langsung merusak unit pembanding harmonisasi.
* satu sesi pindai yang diklaim ulang setelah worker mati akan mengirim
  kandidat yang sama dua kali.

Buku besar ini mencatat apa yang **sudah** dikirim, per ``document_id`` +
``file_hash``, sehingga worker boleh mati kapan saja dan dijalankan ulang
tanpa menduplikasi apa pun. Isinya data turunan: aman dihapus, paling buruk
worker mengirim ulang satu batch.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS extraction (
    document_id   INTEGER PRIMARY KEY,
    file_hash     TEXT,
    status        TEXT,            -- selesai | gagal | berjalan
    backend_status TEXT,           -- terindeks | perlu_koreksi | gagal_dicatat
    attempt       INTEGER DEFAULT 0,
    articles      INTEGER DEFAULT 0,
    vectors       INTEGER DEFAULT 0,
    embedder      TEXT,
    error         TEXT,
    started_at    TEXT,
    finished_at   TEXT
);
CREATE TABLE IF NOT EXISTS scan (
    scan_id       INTEGER PRIMARY KEY,
    start_url     TEXT,
    status        TEXT,            -- berjalan | selesai | gagal
    candidates    INTEGER DEFAULT 0,
    pages_visited INTEGER DEFAULT 0,
    error         TEXT,
    started_at    TEXT,
    finished_at   TEXT
);
-- Halaman tiap pasal, per dokumen backend. Tabel ``articles`` backend tidak
-- punya kolom halaman (lihat docs/INTEGRASI_BACKEND.md §Celah kontrak),
-- sedangkan setiap temuan harmonisasi wajib menyebut pasal + HALAMAN + tautan
-- PDF agar bisa divalidasi manusia. Worker ekstraksi sudah memegang nomor
-- halaman tiap pasal saat memparsing, jadi dicatat di sini — bukan ditebak
-- ulang belakangan, dan bukan dikarang.
CREATE TABLE IF NOT EXISTS article_page (
    document_id    INTEGER NOT NULL,
    article_number TEXT NOT NULL,
    page           INTEGER,
    PRIMARY KEY (document_id, article_number)
);
-- Peta identitas: id dokumen backend ↔ doc_id katalog HERO. Satu PDF yang
-- di-ingest dua kali (lewat backend DAN lewat `hero scrape`) punya sha256
-- yang sama, jadi di katalog ia tetap SATU baris dengan doc_id aslinya —
-- peta ini yang menjaga kedua identitas itu tetap tersambung.
-- Metadata hasil ekstraksi yang TIDAK punya tempat di skema backend:
-- dasar hukum ("Mengingat"), penerbit, tahun peraturan, status keberlakuan
-- yang terbaca dari teks. Tanpa ini, graf relasi peraturan (dasar hukum →
-- pencabutan → dampak perubahan) kosong untuk korpus hasil cermin, dan
-- harmonisasi tidak bisa menjawab "peraturan yang dirujuk masih berlaku?".
CREATE TABLE IF NOT EXISTS doc_meta (
    document_id   INTEGER PRIMARY KEY,
    metadata_json TEXT,
    updated_at    TEXT
);
CREATE TABLE IF NOT EXISTS doc_map (
    document_id INTEGER PRIMARY KEY,
    doc_id      TEXT NOT NULL,
    file_hash   TEXT,
    synced_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_doc_map_docid ON doc_map(doc_id);
CREATE TABLE IF NOT EXISTS event (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    at     TEXT,
    kind   TEXT,
    ref    TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_event_kind ON event(kind, at);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BridgeState:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Aditif & idempoten: kolom baru ditambah, yang ada tidak pernah diubah."""
        for table, cols in (
            ("extraction", {"backend_status": "TEXT", "vectors": "INTEGER DEFAULT 0",
                            "embedder": "TEXT"}),
            ("scan", {"pages_visited": "INTEGER DEFAULT 0"}),
        ):
            have = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for col, ddl in cols.items():
                if col not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
        self.conn.commit()

    # -- ekstraksi -------------------------------------------------------
    def articles_already_sent(self, document_id: int, file_hash: str | None) -> int:
        """Berapa pasal yang sudah pernah dikirim untuk berkas ini (0 = belum)."""
        row = self.conn.execute(
            "SELECT articles, file_hash FROM extraction WHERE document_id = ?",
            (int(document_id),)).fetchone()
        if not row or not row["articles"]:
            return 0
        # Berkas diganti (hash beda) → pasal lama tidak lagi mewakili isinya;
        # pengiriman ulang adalah hal yang benar, dan dicatat di laporan.
        if file_hash and row["file_hash"] and row["file_hash"] != file_hash:
            return 0
        return int(row["articles"])

    def begin_extraction(self, document_id: int, *, file_hash: str | None, attempt: int) -> None:
        self.conn.execute(
            "INSERT INTO extraction (document_id, file_hash, status, attempt, started_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET "
            "file_hash=excluded.file_hash, status='berjalan', attempt=excluded.attempt, "
            "started_at=excluded.started_at, error=NULL",
            (int(document_id), file_hash, "berjalan", int(attempt), now()))
        self.conn.commit()

    def finish_extraction(self, document_id: int, *, status: str, backend_status: str | None = None,
                          articles: int | None = None, vectors: int | None = None,
                          embedder: str | None = None, error: str | None = None) -> None:
        sets = ["status = ?", "finished_at = ?"]
        vals: list[Any] = [status, now()]
        for col, val in (("backend_status", backend_status), ("articles", articles),
                         ("vectors", vectors), ("embedder", embedder), ("error", error)):
            if val is not None:
                sets.append(f"{col} = ?")
                vals.append(val)
        vals.append(int(document_id))
        self.conn.execute(f"UPDATE extraction SET {', '.join(sets)} WHERE document_id = ?", vals)
        self.conn.commit()

    # -- halaman pasal ---------------------------------------------------
    def record_article_pages(self, document_id: int,
                             pages: "Iterable[tuple[str, int | None]]") -> int:
        rows = [(int(document_id), str(num), int(pg) if pg is not None else None)
                for num, pg in pages if num]
        if not rows:
            return 0
        self.conn.executemany(
            "INSERT INTO article_page (document_id, article_number, page) VALUES (?,?,?) "
            "ON CONFLICT(document_id, article_number) DO UPDATE SET page = excluded.page", rows)
        self.conn.commit()
        return len(rows)

    def pages_for(self, document_id: int) -> dict[str, int]:
        return {r["article_number"]: r["page"] for r in self.conn.execute(
            "SELECT article_number, page FROM article_page WHERE document_id = ? "
            "AND page IS NOT NULL", (int(document_id),))}

    def all_pages(self) -> dict[int, dict[str, int]]:
        out: dict[int, dict[str, int]] = {}
        for r in self.conn.execute("SELECT document_id, article_number, page FROM article_page "
                                   "WHERE page IS NOT NULL"):
            out.setdefault(int(r["document_id"]), {})[r["article_number"]] = int(r["page"])
        return out

    # -- pindai ----------------------------------------------------------
    def begin_scan(self, scan_id: int, start_url: str) -> None:
        self.conn.execute(
            "INSERT INTO scan (scan_id, start_url, status, started_at) VALUES (?,?,?,?) "
            "ON CONFLICT(scan_id) DO UPDATE SET status='berjalan', started_at=excluded.started_at, "
            "error=NULL, candidates=0, pages_visited=0",
            (int(scan_id), start_url, "berjalan", now()))
        self.conn.commit()

    def bump_scan(self, scan_id: int, *, candidates: int = 0, pages: int = 0) -> None:
        self.conn.execute("UPDATE scan SET candidates = candidates + ?, pages_visited = ? "
                          "WHERE scan_id = ?", (int(candidates), int(pages), int(scan_id)))
        self.conn.commit()

    def finish_scan(self, scan_id: int, *, status: str, error: str | None = None) -> None:
        self.conn.execute("UPDATE scan SET status = ?, error = ?, finished_at = ? WHERE scan_id = ?",
                          (status, error, now(), int(scan_id)))
        self.conn.commit()

    # -- metadata ekstraksi ----------------------------------------------
    def record_metadata(self, document_id: int, metadata: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO doc_meta (document_id, metadata_json, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(document_id) DO UPDATE SET metadata_json=excluded.metadata_json, "
            "updated_at=excluded.updated_at",
            (int(document_id), json.dumps(metadata, ensure_ascii=False, default=str), now()))
        self.conn.commit()

    def metadata_for(self, document_id: int) -> dict[str, Any]:
        row = self.conn.execute("SELECT metadata_json FROM doc_meta WHERE document_id = ?",
                                (int(document_id),)).fetchone()
        if not row or not row["metadata_json"]:
            return {}
        try:
            return json.loads(row["metadata_json"])
        except json.JSONDecodeError:
            return {}

    def all_metadata(self) -> dict[int, dict[str, Any]]:
        out: dict[int, dict[str, Any]] = {}
        for r in self.conn.execute("SELECT document_id, metadata_json FROM doc_meta"):
            try:
                out[int(r["document_id"])] = json.loads(r["metadata_json"] or "{}")
            except json.JSONDecodeError:
                continue
        return out

    # -- peta identitas --------------------------------------------------
    def map_document(self, document_id: int, doc_id: str, file_hash: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO doc_map (document_id, doc_id, file_hash, synced_at) VALUES (?,?,?,?) "
            "ON CONFLICT(document_id) DO UPDATE SET doc_id=excluded.doc_id, "
            "file_hash=excluded.file_hash, synced_at=excluded.synced_at",
            (int(document_id), str(doc_id), file_hash, now()))
        self.conn.commit()

    def doc_id_for(self, document_id: int) -> str | None:
        row = self.conn.execute("SELECT doc_id FROM doc_map WHERE document_id = ?",
                                (int(document_id),)).fetchone()
        return row["doc_id"] if row else None

    def document_id_for(self, doc_id: str) -> int | None:
        row = self.conn.execute("SELECT document_id FROM doc_map WHERE doc_id = ? "
                                "ORDER BY document_id LIMIT 1", (str(doc_id),)).fetchone()
        return int(row["document_id"]) if row else None

    def doc_map(self) -> dict[int, str]:
        return {int(r["document_id"]): r["doc_id"]
                for r in self.conn.execute("SELECT document_id, doc_id FROM doc_map")}

    # -- jejak & laporan -------------------------------------------------
    def log(self, kind: str, ref: str, detail: dict[str, Any] | None = None) -> None:
        self.conn.execute("INSERT INTO event (at, kind, ref, detail) VALUES (?,?,?,?)",
                          (now(), kind, str(ref), json.dumps(detail or {}, ensure_ascii=False)))
        self.conn.commit()

    def summary(self) -> dict[str, Any]:
        ex = dict(self.conn.execute(
            "SELECT status, COUNT(*) FROM extraction GROUP BY 1").fetchall())
        sc = dict(self.conn.execute("SELECT status, COUNT(*) FROM scan GROUP BY 1").fetchall())
        tot = self.conn.execute(
            "SELECT COALESCE(SUM(articles),0), COALESCE(SUM(vectors),0) FROM extraction").fetchone()
        last = self.conn.execute(
            "SELECT at, kind, ref FROM event ORDER BY id DESC LIMIT 5").fetchall()
        halaman = self.conn.execute("SELECT COUNT(*) FROM article_page WHERE page IS NOT NULL"
                                    ).fetchone()[0]
        return {"ekstraksi": ex, "pindai": sc, "pasal_terkirim": tot[0], "vektor_terkirim": tot[1],
                "halaman_pasal_tercatat": halaman,
                "peristiwa_terakhir": [dict(r) for r in last]}

    def close(self) -> None:
        self.conn.close()


def default_path(settings) -> Path:
    """Sebelah katalog, bukan di dalamnya: state worker bukan data knowledge base."""
    return Path(settings.catalog_db).parent / "hero_bridge.db"
