"""Export the knowledge base to analysis-friendly files.

The catalog is the system of record, but downstream work (spreadsheets,
notebooks, the harmonisation and PoV modules) wants flat tables. Three
datasets are produced, joinable on ``doc_id``:

    documents.csv     one row per regulation, with its metadata
    articles.csv      one row per pasal, the unit of comparison for URD 3.4
    takeaways.csv     one row per normative clause found (URD 3.3)
    analisa.csv       one row per regulation analysed with v2 (FR-ANL-09)
    analisa_poin.csv  one row per v2 point, carrying its pasal and halaman

``jsonl`` writes the same datasets with nested fields preserved.

``analisa*`` comes from the ``analysis_v2`` table. Every point keeps its pasal
and halaman so a reader can go back to the source (invarian 2: no claim without
a citation), and ``access_class`` travels with the row so a downstream consumer
can drop non-public documents the way ``hero snapshot`` already does.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterator

from hero.kb.catalog import Catalog

DOCUMENT_FIELDS = [
    "doc_id", "sha256", "doc_type", "number", "year", "issued_date",
    "title", "subject", "issuing_body", "reg_status", "category",
    "source_type", "source_name", "source_ref", "stored_path",
    "page_count", "ocr_pages", "is_scanned", "size_bytes",
    "confidence", "status", "ingested_at", "access_class",
]
ARTICLE_FIELDS = [
    "doc_id", "doc_type", "number", "pasal", "bab", "page", "ayat_count", "text",
]
TAKEAWAY_FIELDS = [
    "doc_id", "doc_type", "number", "category", "pasal", "page",
    "it_relevant", "score", "text",
]
ANALISA_FIELDS = [
    "doc_id", "doc_type", "number", "year", "access_class", "versi",
    "tentang", "status", "jumlah_bab", "jumlah_pasal", "jumlah_halaman",
    "jumlah_poin", "jumlah_kewajiban", "jumlah_larangan",
    "kata_ringkasan", "waktu_ms", "ringkasan_teks",
]
ANALISA_POIN_FIELDS = [
    "doc_id", "doc_type", "number", "access_class", "poin_id", "kategori",
    "pasal", "halaman", "prioritas", "subjek", "terpotong", "teks",
]


def _documents(cat: Catalog) -> Iterator[dict[str, Any]]:
    from hero.kb.access import redact_ref

    for row in cat.list_documents(limit=1_000_000):
        out = {k: row[k] if k in row.keys() else None for k in DOCUMENT_FIELDS}
        out["source_ref"] = redact_ref(out["source_ref"])
        yield out


def _articles(cat: Catalog) -> Iterator[dict[str, Any]]:
    for row in cat.list_documents(limit=1_000_000):
        text_row = cat.get_text(row["doc_id"])
        if not text_row or not text_row["structure"]:
            continue
        for art in json.loads(text_row["structure"]).get("articles", []):
            yield {
                "doc_id": row["doc_id"],
                "doc_type": row["doc_type"],
                "number": row["number"],
                "pasal": art["number"],
                "bab": art.get("bab"),
                "page": art.get("page"),
                "ayat_count": len(art.get("ayat") or []),
                "text": art.get("text", ""),
            }


def _takeaways(cat: Catalog) -> Iterator[dict[str, Any]]:
    for row in cat.list_documents(limit=1_000_000):
        text_row = cat.get_text(row["doc_id"])
        if not text_row or not text_row["analysis"]:
            continue
        for item in json.loads(text_row["analysis"]).get("key_takeaways", []):
            yield {
                "doc_id": row["doc_id"],
                "doc_type": row["doc_type"],
                "number": row["number"],
                "category": item["category"],
                "pasal": item.get("pasal"),
                "page": item.get("page"),
                "it_relevant": item.get("it_relevant"),
                "score": item.get("score"),
                "text": item["text"],
            }


def _analisa_rows(cat: Catalog) -> Iterator[tuple[Any, dict[str, Any], str]]:
    """Yield (document row, parsed v2 result, versi) for documents analysed with v2."""
    if not cat.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='analysis_v2'").fetchone():
        return
    for row in cat.list_documents(limit=1_000_000):
        got = cat.conn.execute(
            "SELECT hasil, versi FROM analysis_v2 WHERE doc_id = ?",
            (row["doc_id"],)).fetchone()
        if not got or not got[0]:
            continue
        try:
            hasil = json.loads(got[0])
        except json.JSONDecodeError:
            # A half-written cache row must not sink the whole export.
            continue
        yield row, hasil, got[1]


def _col(row: Any, name: str) -> Any:
    return row[name] if name in row.keys() else None


def _analisa(cat: Catalog) -> Iterator[dict[str, Any]]:
    for row, hasil, versi in _analisa_rows(cat):
        ident = hasil.get("identitas") or {}
        metrik = hasil.get("metrik") or {}
        yield {
            "doc_id": row["doc_id"],
            "doc_type": _col(row, "doc_type"),
            "number": _col(row, "number"),
            "year": _col(row, "year"),
            "access_class": _col(row, "access_class"),
            "versi": versi,
            "tentang": ident.get("tentang"),
            "status": ident.get("status"),
            "jumlah_bab": metrik.get("jumlah_bab"),
            "jumlah_pasal": metrik.get("jumlah_pasal"),
            "jumlah_halaman": metrik.get("jumlah_halaman"),
            "jumlah_poin": metrik.get("jumlah_poin"),
            "jumlah_kewajiban": metrik.get("jumlah_kewajiban"),
            "jumlah_larangan": metrik.get("jumlah_larangan"),
            "kata_ringkasan": metrik.get("kata_ringkasan"),
            "waktu_ms": metrik.get("waktu_ms"),
            "ringkasan_teks": hasil.get("ringkasan_teks"),
        }


def _analisa_poin(cat: Catalog) -> Iterator[dict[str, Any]]:
    for row, hasil, _versi in _analisa_rows(cat):
        for poin in hasil.get("poin") or []:
            yield {
                "doc_id": row["doc_id"],
                "doc_type": _col(row, "doc_type"),
                "number": _col(row, "number"),
                "access_class": _col(row, "access_class"),
                "poin_id": poin.get("id"),
                "kategori": poin.get("kategori"),
                "pasal": poin.get("pasal"),
                "halaman": poin.get("halaman"),
                "prioritas": poin.get("prioritas"),
                "subjek": poin.get("subjek"),
                "terpotong": poin.get("terpotong"),
                "teks": poin.get("teks"),
            }


DATASETS = {
    "documents": (DOCUMENT_FIELDS, _documents),
    "articles": (ARTICLE_FIELDS, _articles),
    "takeaways": (TAKEAWAY_FIELDS, _takeaways),
    "analisa": (ANALISA_FIELDS, _analisa),
    "analisa_poin": (ANALISA_POIN_FIELDS, _analisa_poin),
}


def export(catalog: Catalog, out_dir: Path, fmt: str = "csv") -> dict[str, int]:
    """Write every dataset into ``out_dir``. Returns rows written per dataset."""
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    for name, (fields, producer) in DATASETS.items():
        rows = list(producer(catalog))
        counts[name] = len(rows)
        if fmt == "jsonl":
            path = out_dir / f"{name}.jsonl"
            with open(path, "w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        else:
            path = out_dir / f"{name}.csv"
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                # utf-8-sig so Excel opens Indonesian text correctly.
                writer = csv.DictWriter(fh, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
    return counts
