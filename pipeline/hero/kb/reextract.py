"""Re-extract stored documents after an extraction fix, and reconcile identity.

Ingest skips a file it has seen (same SHA-256), so a better extractor never
reaches documents already in the KB. This re-runs the same steps as
``IngestPipeline.ingest_file`` — text, metadata, structure, summary — on the
stored PDF and replaces the derived rows, leaving the file, its place in the
KB, its category and its legal status alone.

Identity: when a document is linked to a register row (JDIH / ojk.go.id) and
the identity parsed from its text disagrees with the register, the register
wins — it is the publisher's own record. The old values are kept in
``metadata_json["identitas_sebelumnya"]`` so the change is auditable.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from hero.config import Settings

_MISSING_DIGITS = re.compile(r"\bNomor\s*\n?\s*Tahun\b")


@dataclass
class ReextractResult:
    doc_id: str
    judul: str
    alasan: list[str]
    sebelum: dict[str, Any] = field(default_factory=dict)
    sesudah: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def _register_identity(conn: sqlite3.Connection, doc_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT reg_key, doc_type, number, year, title FROM inventory WHERE doc_id = ? "
        "AND reg_key IS NOT NULL ORDER BY source = 'jdih-ojk' DESC LIMIT 1", (doc_id,)).fetchone()
    return dict(row) if row else None


def affected(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Documents an extraction fix would change, with the reason for each."""
    from hero.graph.identity import ref_for_record

    conn.row_factory = sqlite3.Row
    out: dict[str, list[str]] = {}
    for d in conn.execute("SELECT d.doc_id, d.doc_type, d.number, d.year, t.full_text "
                          "FROM documents d LEFT JOIN document_text t USING (doc_id) "
                          "WHERE d.status = 'ingested'"):
        why = []
        n = len(_MISSING_DIGITS.findall(d["full_text"] or ""))
        if n:
            why.append(f"{n} rujukan kehilangan nomor")
        reg = _register_identity(conn, d["doc_id"])
        if reg:
            ref = ref_for_record(d["doc_type"], d["number"], d["year"])
            if (ref.key if ref else None) != reg["reg_key"]:
                why.append(f"identitas {ref.key if ref else '—'} ≠ register {reg['reg_key']}")
        if why:
            out[d["doc_id"]] = why
    return out


def reextract(settings: Settings, doc_ids: list[str], reasons: dict[str, list[str]] | None = None,
              ) -> list[ReextractResult]:
    from hero.extract.metadata import extract_metadata
    from hero.extract.pdf import extract_pdf, probe_pdf
    from hero.extract.quality import assess_quality
    from hero.extract.structure import parse_structure
    from hero.extract.summary import build_summary
    from hero.graph.identity import ref_for_record
    from hero.kb.catalog import Catalog

    cat = Catalog(settings.catalog_db)
    results: list[ReextractResult] = []
    try:
        for doc_id in doc_ids:
            d = cat.get(doc_id)
            if d is None:
                continue
            res = ReextractResult(doc_id, (d["subject"] or d["title"] or "")[:100],
                                  (reasons or {}).get(doc_id, []))
            res.sebelum = {"jenis": d["doc_type"], "nomor": d["number"], "tahun": d["year"],
                           "judul": d["title"]}
            path = Path(d["stored_path"] or "")
            if not path.is_file():
                res.error = "berkas tidak ada di disk"
                results.append(res)
                continue
            ex = extract_pdf(path, settings.ocr, settings.pdf)
            if ex.error and ex.char_count == 0:
                res.error = ex.error
                results.append(res)
                continue
            probe = probe_pdf(path, settings.pdf)
            md = extract_metadata(ex.text, probe.get("pdf_metadata"), path.name)
            meta = json.loads(d["metadata_json"] or "{}")
            reg = _register_identity(cat.conn, doc_id)
            parsed = ref_for_record(md.doc_type, md.number, md.year)
            if reg and (parsed.key if parsed else None) != reg["reg_key"]:
                meta["identitas_sebelumnya"] = {
                    "jenis": md.doc_type, "nomor": md.number, "tahun": md.year,
                    "judul": md.title, "dikoreksi": datetime.now().isoformat(timespec="seconds"),
                    "sumber_koreksi": "register",
                }
                md.doc_type, md.number, md.year = reg["doc_type"], reg["number"], reg["year"]
                if reg.get("title"):
                    md.title = reg["title"]
                    m = re.search(r"\btentang\b\s+(.*)", reg["title"], re.IGNORECASE)
                    md.subject = m.group(1) if m else md.subject
                res.alasan.append("identitas dari register")
            struct = parse_structure(ex.pages)
            analysis = build_summary(ex.text, struct, md)
            analysis["extraction"] = {"page_count": ex.page_count, "ocr_pages": ex.ocr_pages,
                                      "is_scanned": ex.is_scanned, "seconds": ex.duration_seconds,
                                      "repaired": ex.repaired, "diekstrak_ulang": True}
            analysis["quality"] = assess_quality(ex)
            with cat.transaction() as conn:
                conn.execute(
                    "UPDATE documents SET doc_type=?, number=?, year=?, title=?, subject=?, "
                    "page_count=?, ocr_pages=?, is_scanned=?, metadata_json=? WHERE doc_id=?",
                    (md.doc_type, md.number, md.year, md.title or d["title"],
                     md.subject or d["subject"], ex.page_count, ex.ocr_pages, int(ex.is_scanned),
                     json.dumps(meta, ensure_ascii=False, default=str), doc_id))
            cat.save_text(doc_id, ex.text, struct.to_dict(), analysis)
            cat.save_articles(doc_id, [a.to_dict() for a in struct.articles])
            res.sesudah = {"jenis": md.doc_type, "nomor": md.number, "tahun": md.year,
                           "judul": md.title, "pasal": len(struct.articles),
                           "rujukan_tanpa_nomor": len(_MISSING_DIGITS.findall(ex.text)),
                           "halaman_ocr": ex.ocr_pages}
            results.append(res)
    finally:
        cat.close()
    return results
