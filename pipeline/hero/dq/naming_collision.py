"""How often does a file-name format give two documents the same name?

The Scraping screen lets the user compose the name from Nama / Tahun / Jenis /
Bidang (Weekly #4). Folders on disk sort and deduplicate by name, so a format
that collides silently turns two regulations into "X.pdf" and "X (2).pdf".
This measures that rate on the real inventory, and separates genuine
collisions from the same regulation listed twice by its source.
"""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from hero.kb.naming import render_name, template_from_components

DEFAULT_COMBOS: tuple[tuple[str, ...], ...] = (
    ("nama",),
    ("jenis", "tahun"),
    ("nama", "jenis", "tahun"),
    ("tahun", "jenis", "nama"),
    ("bidang", "tahun", "nama"),
    ("jenis", "nomor", "tahun", "nama"),
    ("tahun", "jenis", "nomor", "nama"),
)

_TENTANG = re.compile(r"\btentang\b\s+(.*)", re.IGNORECASE | re.DOTALL)


def perihal(title: str | None) -> str:
    """The subject after "tentang" — what a person calls the regulation's name."""
    m = _TENTANG.search(title or "")
    return (m.group(1) if m else (title or "")).strip()


@dataclass
class CollisionRow:
    source: str
    komponen: str
    rekaman: int
    nama_unik: int
    bentrok: int            # records sharing a name with another record
    bentrok_sumber: int     # ...of which: same regulation (reg_key) listed twice
    bentrok_nyata: int      # different regulations, same name

    @property
    def persen_nyata(self) -> float:
        return self.bentrok_nyata / self.rekaman if self.rekaman else 0.0


def measure(rows: Iterable[dict[str, Any]], combos=DEFAULT_COMBOS) -> list[CollisionRow]:
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_source[r["source"]].append(r)
    out = []
    for source, recs in sorted(by_source.items()):
        for combo in combos:
            tpl = template_from_components(list(combo))
            groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for r in recs:
                name = render_name(tpl, {
                    "jenis": r.get("doc_type"), "nomor": r.get("number"),
                    "tahun": r.get("year"), "judul": perihal(r.get("title")),
                    "kategori": r.get("category"),
                }).lower()
                groups[name].append(r)
            bentrok = sumber = 0
            for g in groups.values():
                if len(g) < 2:
                    continue
                bentrok += len(g)
                keys = {x.get("reg_key") for x in g}
                if len(keys) == 1 and None not in keys:
                    sumber += len(g)
            out.append(CollisionRow(source, " → ".join(combo), len(recs), len(groups),
                                    bentrok, sumber, bentrok - sumber))
    return out


def from_catalog(conn: sqlite3.Connection, sources=("jdih-ojk", "ojk-regulasi")) -> list[CollisionRow]:
    conn.row_factory = sqlite3.Row
    marks = ",".join("?" * len(sources))
    rows = [dict(r) for r in conn.execute(
        f"SELECT source, title, doc_type, number, year, category, reg_key "
        f"FROM inventory WHERE source IN ({marks})", sources)]
    return measure(rows)
