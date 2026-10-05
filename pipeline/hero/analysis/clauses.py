"""Klausul yang relevan dengan kebutuhan pengguna (URD 3.3, poin terakhir).

"Tunjukkan pasal tentang pelaporan insiden di POJK ini" — rank the Pasal of
*one* document against a user's stated need. Two signals, fused by rank:

* semantic similarity from the vector index (e5 when built; LSA otherwise —
  the Deterministic mode still gets an answer), and
* BM25 over the same chunks,

then windows of the same Pasal are merged, so each result is one Pasal with
its best-matching passage. Every result is a citation a human can open.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

import numpy as np

from hero.vector.store import RRF_K, lexical_or_query

# Query intent → the v2 point category that answers it. Needed because legal
# drafting states sanctions and duties by cross-reference ("yang melanggar
# ketentuan sebagaimana dimaksud dalam Pasal 4, Pasal 5 … dikenai sanksi"):
# the sanction Pasal of a POJK on foreign workers never says "tenaga kerja
# asing", so neither BM25 nor embeddings rank it for "sanksi penggunaan TKA".
# The structured extraction already knows which Pasal *are* sanctions.
INTENTS: tuple[tuple[re.Pattern, str], ...] = tuple((re.compile(rx, re.I), cat) for rx, cat in (
    (r"\b(sanksi|denda|hukuman|melanggar|pelanggaran)\b", "Sanksi"),
    (r"\b(dilarang|larangan|tidak boleh)\b", "Larangan"),
    (r"\b(lapor|laporan|melaporkan|pelaporan)\b", "Pelaporan"),
    (r"\b(izin|perizinan|persetujuan)\b", "Perizinan"),
    (r"\b(batas waktu|paling lambat|paling lama|kapan|jangka waktu|tenggat)\b", "Batas Waktu"),
    (r"\b(kewajiban|diwajibkan)\b", "Kewajiban"),
    (r"\b(mulai berlaku|berlaku sejak)\b", "Masa Berlaku"),
    (r"\b(mencabut|dicabut|pencabutan)\b", "Pencabutan"),
))


def detect_intents(text: str) -> list[str]:
    return [cat for rx, cat in INTENTS if rx.search(text)]


def _points_by_label(conn: sqlite3.Connection | None, doc_id: str, cats: list[str]) -> dict[str, list[dict]]:
    """chunk-ref label ("11", "II. KETENTUAN UMUM") → v2 points of ``cats`` in it,
    ordered by how many such points the Pasal holds.

    Density, not position: in a POJK nearly every duty has its own "dikenai
    sanksi" ayat, so "has a sanction" does not single anything out — but a
    Pasal whose every ayat is a sanction is the sanction article.
    """
    if conn is None or not cats:
        return {}
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='analysis_v2'").fetchone():
        return {}
    row = conn.execute("SELECT hasil FROM analysis_v2 WHERE doc_id = ?", (doc_id,)).fetchone()
    if not row:
        return {}
    import json
    out: dict[str, list[dict]] = {}
    for p in json.loads(row[0]).get("poin", []):
        if p["kategori"] in cats:
            m = re.match(r"Pasal\s+(\w+)", p["pasal"]) or re.match(r"Bagian\s+(.+?)(?:\s+angka\s+\d+)?$", p["pasal"])
            if m:
                out.setdefault(m.group(1), []).append(p)
    return dict(sorted(out.items(), key=lambda kv: -len(kv[1])))


def find_clauses(service, doc_id: str, kebutuhan: str, *, k: int = 5,
                 conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """``service`` is a hero.vector.VectorService (already holding loaded models);
    ``conn`` (the catalog) enables the intent signal from the v2 analysis."""
    store = service.store
    if store is None:
        return {"metode": None, "hasil": [], "alasan": "indeks vektor belum dibangun (hero vector build)"}
    rows = store.conn.execute(
        "SELECT rowid, level, ref, page, text FROM chunk WHERE doc_id = ? AND level <> 'dokumen'",
        (doc_id,)).fetchall()
    if not rows:
        return {"metode": None, "hasil": [], "alasan": "dokumen belum terindeks"}
    rowids = [r["rowid"] for r in rows]
    info = {r["rowid"]: r for r in rows}

    rankings: dict[str, list[int]] = {}
    method = "semantic" if service.ready("semantic") else ("lsa" if service.ready("lsa") else None)
    if method:
        ids, mat = store._matrix(method)
        pos = {int(i): n for n, i in enumerate(ids)}
        sel = [r for r in rowids if r in pos]
        if sel:
            qv = service.embedder(method).embed_query(kebutuhan)
            scores = mat[[pos[r] for r in sel]] @ qv
            rankings[method] = [sel[i] for i in np.argsort(-scores)]
    match = lexical_or_query(kebutuhan)
    if match:
        placeholders = ",".join(str(int(r)) for r in rowids)
        lex = store.conn.execute(
            f"SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH ? AND rowid IN ({placeholders}) "
            f"ORDER BY bm25(chunk_fts)", (match,)).fetchall()
        rankings["lexical"] = [r[0] for r in lex]

    intents = detect_intents(kebutuhan)
    by_label = _points_by_label(conn, doc_id, intents)
    order = {lab: n for n, lab in enumerate(by_label)}

    def label_of(ref) -> str | None:
        ref = str(ref or "")
        return next((l for l in order if ref == l or ref.startswith(l + " ") or ref.startswith(l)), None)

    if order:
        hits = [r for r in rows if label_of(r["ref"]) is not None]
        hits.sort(key=lambda r: (order[label_of(r["ref"])], r["rowid"]))
        # One entry per Pasal: the niat signal ranks articles, not windows.
        seen, ranked = set(), []
        for r in hits:
            lab = label_of(r["ref"])
            if lab not in seen:
                seen.add(lab)
                ranked.append(r["rowid"])
        rankings["niat"] = ranked

    fused: dict[int, float] = {}
    for ranking in rankings.values():
        for rank, rid in enumerate(ranking, 1):
            fused[rid] = fused.get(rid, 0.0) + 1.0 / (RRF_K + rank)
    best: dict[str, dict[str, Any]] = {}
    for rid, score in sorted(fused.items(), key=lambda kv: -kv[1]):
        c = info[rid]
        key = c["ref"] or f"potongan-{rid}"
        if key in best:
            best[key]["potongan_cocok"] += 1
            continue
        ref = c["ref"]
        if ref and c["level"] == "pasal" and re.fullmatch(r"\d+[A-Z]?", ref.strip()):
            ref = f"Pasal {ref.strip()}"
        snippet, page = c["text"][:400], c["page"]
        lab = label_of(c["ref"]) if order else None
        if lab and by_label.get(lab):
            # Show the ayat that answers the intent, not whichever window matched words.
            pt = by_label[lab][0]
            ref, snippet, page = pt["pasal"], pt["teks"][:400], pt.get("halaman") or page
        best[key] = {"rujukan": ref, "halaman": page, "cuplikan": snippet,
                     "skor": round(score, 5), "potongan_cocok": 1,
                     "peringkat": {m: r.index(rid) + 1 for m, r in rankings.items() if rid in r}}
        if len(best) >= k:
            break
    return {"metode": "+".join(sorted(rankings)) or None, "niat_terdeteksi": intents,
            "hasil": list(best.values()), "alasan": None}
