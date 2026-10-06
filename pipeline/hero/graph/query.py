"""Traversals over the regulation graph, as recursive SQL.

Three questions that neither a relational filter nor a vector search can
answer, and that the harmonisation feature (URD 3.4) needs:

* ``lineage``  — "is this still the regulation in force, and if not, what
  replaced it?" Follows MENCABUT/MENGUBAH edges *into* a node, repeatedly.
* ``impact``   — "if this regulation changes, which others stand on it?"
  Follows BERDASAR edges into a node: everything whose legal basis is it,
  directly or through a chain.
* ``basis``    — "what does this regulation ultimately rest on?" Follows
  BERDASAR edges out of a node, up the legal hierarchy to the UU.

Cycle safety: legal graphs do contain cycles (A amends B, B's later revision
cites A). Each recursive CTE carries the visited path as a delimited string
and refuses to revisit a node, and every traversal has a depth limit.
"""
from __future__ import annotations

import sqlite3
from typing import Any

_NODE_COLS = "n.key, n.jenis, n.nomor, n.tahun, n.judul, n.status, n.doc_id, n.asal"


def _node(r: sqlite3.Row) -> dict[str, Any]:
    return {"key": r["key"], "jenis": r["jenis"], "nomor": r["nomor"], "tahun": r["tahun"],
            "judul": r["judul"], "status": r["status"], "doc_id": r["doc_id"],
            "di_kb": bool(r["doc_id"]), "asal": r["asal"]}


def get_node(conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
    conn.row_factory = sqlite3.Row
    r = conn.execute(f"SELECT {_NODE_COLS} FROM graph_node n WHERE n.key = ?", (key,)).fetchone()
    return _node(r) if r else None


def node_for_document(conn: sqlite3.Connection, doc_id: str) -> str | None:
    r = conn.execute("SELECT key FROM graph_node WHERE doc_id = ? LIMIT 1", (doc_id,)).fetchone()
    return r[0] if r else None


def neighbors(conn: sqlite3.Connection, key: str) -> dict[str, list[dict[str, Any]]]:
    """Every direct relationship of a node, grouped by how the UI reads them."""
    conn.row_factory = sqlite3.Row
    out: dict[str, list[dict[str, Any]]] = {
        "mencabut": [], "dicabut_oleh": [], "mengubah": [], "diubah_oleh": [],
        "berdasar_pada": [], "menjadi_dasar_bagi": []}
    groups = {("MENCABUT", "out"): "mencabut", ("MENCABUT", "in"): "dicabut_oleh",
              ("MENGUBAH", "out"): "mengubah", ("MENGUBAH", "in"): "diubah_oleh",
              ("BERDASAR", "out"): "berdasar_pada", ("BERDASAR", "in"): "menjadi_dasar_bagi"}
    rows = conn.execute(
        f"""SELECT 'out' AS arah, e.rel, e.sebagian, e.pasal_terkait, e.asal AS edge_asal, {_NODE_COLS}
            FROM graph_edge e JOIN graph_node n ON n.key = e.dst WHERE e.src = ?
            UNION ALL
            SELECT 'in', e.rel, e.sebagian, e.pasal_terkait, e.asal, {_NODE_COLS}
            FROM graph_edge e JOIN graph_node n ON n.key = e.src WHERE e.dst = ?
            ORDER BY 2, 1""", (key, key)).fetchall()
    for r in rows:
        item = _node(r)
        item.update(sebagian=bool(r["sebagian"]), pasal_terkait=r["pasal_terkait"],
                    sumber_relasi=r["edge_asal"])
        out[groups[(r["rel"], r["arah"])]].append(item)
    return out


def _walk(conn: sqlite3.Connection, key: str, *, rels: tuple[str, ...], direction: str,
          max_depth: int, full_only: bool = False) -> list[dict[str, Any]]:
    """Generic bounded, cycle-safe traversal. direction 'in' follows edges
    pointing at the current node (e.dst = cur); 'out' follows edges leaving it."""
    conn.row_factory = sqlite3.Row
    rel_list = ", ".join(f"'{r}'" for r in rels)
    step = ("e.dst = w.key", "e.src") if direction == "in" else ("e.src = w.key", "e.dst")
    rows = conn.execute(f"""
        WITH RECURSIVE walk(key, depth, path, via) AS (
            SELECT ?, 0, '|' || ? || '|', NULL
            UNION
            SELECT {step[1]}, w.depth + 1, w.path || {step[1]} || '|', e.rel
            FROM walk w JOIN graph_edge e ON {step[0]} AND e.rel IN ({rel_list})
                 {"AND e.sebagian = 0" if full_only else ""}
            WHERE w.depth < ? AND instr(w.path, '|' || {step[1]} || '|') = 0
        )
        SELECT w.depth, w.via, w.path, {_NODE_COLS}
        FROM walk w JOIN graph_node n ON n.key = w.key
        WHERE w.depth > 0
        ORDER BY w.depth, n.tahun DESC""", (key, key, max_depth)).fetchall()
    seen: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r["key"] in seen:            # keep the shortest route to each node
            continue
        item = _node(r)
        item.update(kedalaman=r["depth"], lewat=r["via"],
                    jalur=[k for k in r["path"].split("|") if k])
        seen[r["key"]] = item
    return list(seen.values())


def lineage(conn: sqlite3.Connection, key: str, max_depth: int = 8) -> dict[str, Any]:
    """Was this regulation replaced, by what, and is that still in force?

    Only *full* revocations form the replacement chain. Amendments and
    partial revocations change a regulation without replacing it, so they
    are reported separately as ``perubahan`` — a regulator reading "diganti
    oleh" must be able to trust that the old text no longer applies.

    ``berlaku_terkini`` is the answer actually wanted: the end of the
    replacement chain, i.e. successors that nothing has fully revoked.
    """
    chain = _walk(conn, key, rels=("MENCABUT",), direction="in", max_depth=max_depth,
                  full_only=True)
    fully_revoked = {r[0] for r in conn.execute(
        "SELECT dst FROM graph_edge WHERE rel = 'MENCABUT' AND sebagian = 0")}
    current = [n for n in chain if n["key"] not in fully_revoked]
    changes = [n for n in neighbors(conn, key)["diubah_oleh"]] + \
              [n for n in neighbors(conn, key)["dicabut_oleh"] if n["sebagian"]]
    return {"rantai_penggantian": chain, "berlaku_terkini": current,
            "sudah_diganti": bool(chain), "perubahan": changes}


def impact(conn: sqlite3.Connection, key: str, max_depth: int = 4) -> list[dict[str, Any]]:
    """Regulations that rest on this one, directly or transitively."""
    return _walk(conn, key, rels=("BERDASAR",), direction="in", max_depth=max_depth)


def basis(conn: sqlite3.Connection, key: str, max_depth: int = 4) -> list[dict[str, Any]]:
    """The chain of legal bases this regulation stands on, up to the UU/UUD."""
    return _walk(conn, key, rels=("BERDASAR",), direction="out", max_depth=max_depth)


def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'graph_node'").fetchone():
        return {"dibangun": False}
    edges = dict(conn.execute("SELECT rel, COUNT(*) FROM graph_edge GROUP BY 1").fetchall())
    hub = conn.execute(f"""
        SELECT {_NODE_COLS}, COUNT(*) AS derajat FROM graph_edge e
        JOIN graph_node n ON n.key = e.dst WHERE e.rel = 'BERDASAR'
        GROUP BY n.key ORDER BY derajat DESC LIMIT 5""").fetchall()
    return {
        "dibangun": True,
        "node": conn.execute("SELECT COUNT(*) FROM graph_node").fetchone()[0],
        "node_di_kb": conn.execute("SELECT COUNT(*) FROM graph_node WHERE doc_id IS NOT NULL").fetchone()[0],
        "edge": edges,
        "konflik_identitas": conn.execute("SELECT COUNT(*) FROM graph_identity_conflict").fetchone()[0],
        "paling_banyak_dijadikan_dasar": [dict(_node(h), jumlah=h["derajat"]) for h in hub],
    }
