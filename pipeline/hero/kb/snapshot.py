"""Static snapshot of the frontend API, built from the real catalog.

The frontend is still built on eight hand-written rows (``regulasiData.ts``)
whose categories ("Fintech", "Asuransi") do not exist in the data. This
writes the responses of the real endpoints — same code path, same shapes as
``docs/API_CONTRACT.md`` — to JSON files the frontend can load while the
backend integration is pending, so screens are built against real values
(empty dates, long titles, the fourth KBS status) instead of a mock that has
to be unlearned later.

Only documents whose ``access_class`` is ``publik`` are included. The
snapshot is built on a throw-away copy of the catalog from which every other
document is removed first, so facets, dashboard counts and "terbaru" lists
agree with the document list instead of leaking counts of internal files.

Layout mirrors the API path with ``.json`` appended::

    <out>/api/meta/enums.json
    <out>/api/kb/facets.json
    <out>/api/kb/documents.json                 all items, one envelope
    <out>/api/kb/documents/<id>.json             detail
    <out>/api/kb/documents/<id>/relations.json
    <out>/api/analisa/<id>.json
    <out>/api/dashboard/summary.json
    <out>/api/graph/findings.json
    <out>/index.json                             manifest
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from hero.config import Settings

# Tables keyed by doc_id that delete_document() does not cover.
_EXTRA_DOC_TABLES = ("analysis_v2", "penamaan", "kb_document_topic")


def _public_copy(settings: Settings, workdir: Path) -> tuple[Settings, int, int]:
    """Copy the catalog and drop every non-public document from the copy."""
    from hero.kb.catalog import Catalog
    from hero.kb.readmodel import sync

    db = workdir / "hero_catalog.db"
    with sqlite3.connect(settings.catalog_db, timeout=60) as src, sqlite3.connect(db) as dst:
        src.backup(dst)
    cat = Catalog(db)
    hidden = [r[0] for r in cat.conn.execute(
        "SELECT doc_id FROM documents WHERE COALESCE(access_class, 'publik') != 'publik'")]
    tables = {r[0] for r in cat.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for doc_id in hidden:
        cat.delete_document(doc_id)
        for t in _EXTRA_DOC_TABLES:
            if t in tables:
                cat.conn.execute(f"DELETE FROM {t} WHERE doc_id = ?", (doc_id,))
    cat.conn.commit()
    sync(cat.conn, full=True)
    kept = cat.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    cat.close()
    # Vectors are not copied: semantic search is not part of the snapshot.
    return replace(settings, catalog_db=db), kept, len(hidden)


def _write(out: Path, path: str, data: Any) -> int:
    target = out / (path.lstrip("/") + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, ensure_ascii=False, indent=1)
    target.write_text(body, encoding="utf-8")
    return len(body.encode("utf-8"))


def build_snapshot(settings: Settings, out: Path) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from hero.server.app import create_app

    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    written: dict[str, int] = {}
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="hero-snapshot-") as tmp:
        public, kept, hidden = _public_copy(settings, Path(tmp))
        with TestClient(create_app(public)) as client:

            def grab(path: str, params: dict[str, Any] | None = None) -> Any:
                r = client.get(path, params=params)
                if r.status_code != 200:
                    failures.append(f"{path} → HTTP {r.status_code}")
                    return None
                return r.json()

            for path in ("/api/meta/enums", "/api/kb/facets", "/api/dashboard/summary",
                         "/api/graph/findings", "/api/analisa-status"):
                data = grab(path)
                if data is not None:
                    written[path] = _write(out, path, data)

            items: list[dict[str, Any]] = []
            page, pages = 1, 1
            while page <= pages:
                env = grab("/api/kb/documents", {"page": page, "page_size": 100})
                if env is None:
                    break
                items += env["items"]
                pages = env["pages"]
                page += 1
            envelope = {"items": items, "total": len(items), "page": 1,
                        "page_size": len(items), "pages": 1, "mode": "lexical",
                        "pencarian": None, "waktu_ms": 0}
            written["/api/kb/documents"] = _write(out, "/api/kb/documents", envelope)

            for it in items:
                doc_id = it["id"]
                for path in (f"/api/kb/documents/{doc_id}",
                             f"/api/kb/documents/{doc_id}/relations",
                             f"/api/analisa/{doc_id}"):
                    data = grab(path)
                    if data is not None:
                        written[path] = _write(out, path, data)

    manifest = {
        "dibuat": datetime.now().isoformat(timespec="seconds"),
        "keterangan": "Snapshot respons API HERO dari katalog nyata. Hanya dokumen "
                      "berklasifikasi publik. Bentuk = docs/API_CONTRACT.md.",
        "dokumen": kept,
        "dokumen_disembunyikan": hidden,
        "berkas": len(written),
        "ukuran_byte": sum(written.values()),
        "gagal": failures,
        "endpoint": sorted(written),
    }
    _write(out, "index", manifest)
    return manifest
