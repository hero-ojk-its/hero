"""Export the graph for Neo4j, and derive status findings from it.

``export_neo4j`` writes the header format ``neo4j-admin database import``
expects, plus a ``LOAD CSV`` Cypher script for a running server — the SQLite
graph and a Neo4j graph are the same model, so moving is a load, not a
redesign.

``status_findings`` is where the graph pays for itself as a data-quality
tool: a regulation that another regulation *fully* revokes should not be
"berlaku", and one with unknown status can be inferred as revoked. These are
reported as candidates with evidence, never written back automatically —
legal status is not something to overwrite on inference alone.
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any

CYPHER = """// HERO regulation graph — load into a running Neo4j (5.x).
// Copy nodes.csv and edges.csv into the server's import/ directory first.
CREATE CONSTRAINT regulasi_key IF NOT EXISTS FOR (r:Regulasi) REQUIRE r.key IS UNIQUE;

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
MERGE (r:Regulasi {key: row.`key:ID`})
SET r.jenis = row.jenis, r.nomor = row.nomor, r.tahun = toInteger(row.`tahun:int`),
    r.judul = row.judul, r.status = row.status, r.doc_id = row.doc_id,
    r.di_kb = row.`di_kb:boolean` = 'true', r.asal = row.asal;

LOAD CSV WITH HEADERS FROM 'file:///edges.csv' AS row
MATCH (a:Regulasi {key: row.`:START_ID`}), (b:Regulasi {key: row.`:END_ID`})
CALL apoc.merge.relationship(a, row.`:TYPE`, {}, {sebagian: row.`sebagian:boolean` = 'true',
     asal: row.asal, pasal_terkait: row.pasal_terkait}, b) YIELD rel
RETURN count(rel);

// Contoh: siapa saja yang (berantai) bersandar pada UU 21/2011?
// MATCH p = (x:Regulasi)-[:BERDASAR*1..3]->(:Regulasi {key: 'UU|21|2011'}) RETURN count(DISTINCT x);
"""


def export_neo4j(conn: sqlite3.Connection, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    conn.row_factory = sqlite3.Row
    with (out_dir / "nodes.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key:ID", "jenis", "nomor", "tahun:int", "judul", "status", "doc_id",
                    "di_kb:boolean", "asal", ":LABEL"])
        n = 0
        for r in conn.execute("SELECT * FROM graph_node"):
            w.writerow([r["key"], r["jenis"], r["nomor"], r["tahun"] or "", r["judul"] or "",
                        r["status"] or "", r["doc_id"] or "", "true" if r["doc_id"] else "false",
                        r["asal"], "Regulasi"])
            n += 1
    with (out_dir / "edges.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([":START_ID", ":END_ID", ":TYPE", "sebagian:boolean", "asal", "pasal_terkait"])
        m = 0
        for r in conn.execute("SELECT * FROM graph_edge"):
            w.writerow([r["src"], r["dst"], r["rel"], "true" if r["sebagian"] else "false",
                        r["asal"], r["pasal_terkait"] or ""])
            m += 1
    (out_dir / "load.cypher").write_text(CYPHER, encoding="utf-8")
    return {"nodes": n, "edges": m, "dir": str(out_dir)}


def status_findings(conn: sqlite3.Connection, limit: int = 50) -> dict[str, Any]:
    """Where graph relations and recorded status disagree."""
    conn.row_factory = sqlite3.Row
    q = """
        SELECT n.key, n.judul, n.status, n.record_key, e.src AS pencabut, s.judul AS judul_pencabut,
               s.status AS status_pencabut, e.asal
        FROM graph_node n
        JOIN graph_edge e ON e.dst = n.key AND e.rel = 'MENCABUT' AND e.sebagian = 0
        JOIN graph_node s ON s.key = e.src
        WHERE n.asal = 'register' AND n.status = ?
        GROUP BY n.key ORDER BY n.tahun DESC LIMIT ?"""

    def rows(status: str) -> list[dict[str, Any]]:
        return [dict(r) for r in conn.execute(q, (status, limit))]

    def count(status: str) -> int:
        return conn.execute(
            "SELECT COUNT(DISTINCT n.key) FROM graph_node n JOIN graph_edge e ON e.dst = n.key "
            "AND e.rel = 'MENCABUT' AND e.sebagian = 0 WHERE n.asal = 'register' AND n.status = ?",
            (status,)).fetchone()[0]

    return {
        "kandidat_status_basi": {
            "penjelasan": ("Tercatat 'berlaku', tetapi peraturan lain menyatakan mencabutnya "
                           "secara penuh. Kemungkinan status di register belum diperbarui."),
            "jumlah": count("berlaku"), "contoh": rows("berlaku")},
        "status_dapat_disimpulkan": {
            "penjelasan": ("Status tidak diketahui, tetapi ada peraturan yang mencabutnya "
                           "secara penuh — kandidat status 'dicabut'."),
            "jumlah": count("unknown"), "contoh": rows("unknown")},
        "konsisten": {"penjelasan": "Graf dan register sepakat: dicabut.", "jumlah": count("dicabut")},
    }
