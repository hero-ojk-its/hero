"""Build the regulation graph — nodes are regulations, edges are the legal
relationships between them — as two plain SQLite tables.

Sources of edges, all already in the catalog:

* JDIH "Riwayat Peraturan"   → MENCABUT / MENGUBAH (with "Sebagian" = partial)
* JDIH "Landasan Hukum"      → BERDASAR
* a document's "Mengingat"   → BERDASAR (``metadata_json.legal_basis``)

Edges are stored in active voice. "A: Dicabut : 1. B" means B revoked A, so
it is stored as B -[MENCABUT]-> A; every edge then reads the same way
regardless of which page it was scraped from.

Why a property graph in SQLite rather than Neo4j: at this scale (thousands of
nodes) recursive CTEs answer every traversal in milliseconds, there is no
second server to run on the VPS, and the deterministic mode stays
dependency-free (URD 3.1). ``hero.graph.export`` writes Neo4j import files
for when the graph outgrows this — the schema is the same.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field

from hero.graph.identity import RegRef, canonical_ref, ref_for_record

SCHEMA = """
DROP TABLE IF EXISTS graph_edge;
DROP TABLE IF EXISTS graph_node;
DROP TABLE IF EXISTS graph_identity_conflict;
CREATE TABLE graph_node (
    key TEXT PRIMARY KEY,
    jenis TEXT,
    nomor TEXT,
    tahun INTEGER,
    judul TEXT,
    status TEXT,
    doc_id TEXT,                -- set when the PDF is in the knowledge base
    record_key TEXT,            -- inventory row that described it, if any
    asal TEXT NOT NULL          -- 'register' (listed by a source) | 'rujukan' (only cited)
);
CREATE INDEX ix_gn_doc ON graph_node(doc_id);
CREATE INDEX ix_gn_record ON graph_node(record_key);
CREATE TABLE graph_edge (
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    rel TEXT NOT NULL,          -- MENCABUT | MENGUBAH | BERDASAR
    sebagian INTEGER DEFAULT 0, -- partial revocation/amendment
    pasal_terkait TEXT,
    asal TEXT NOT NULL,         -- jdih-riwayat | jdih-landasan | dokumen-mengingat
    bukti TEXT,                 -- the source text the edge was read from
    PRIMARY KEY (src, dst, rel)
);
CREATE INDEX ix_ge_dst ON graph_edge(dst, rel);
CREATE INDEX ix_ge_src ON graph_edge(src, rel);
CREATE TABLE graph_identity_conflict (
    key TEXT, kept_title TEXT, other_title TEXT, other_record TEXT, similarity REAL
);
"""

_REL_SPLIT = re.compile(
    r"(Mencabut Sebagian|Mencabut|Dicabut Sebagian|Dicabut|Mengubah|Diubah)\s*:")
# (relation, reverse?, partial?) — reverse means the *other* regulation acts on this one.
_REL_MEANING = {
    "Mencabut": ("MENCABUT", False, False),
    "Mencabut Sebagian": ("MENCABUT", False, True),
    "Dicabut": ("MENCABUT", True, False),
    "Dicabut Sebagian": ("MENCABUT", True, True),
    "Mengubah": ("MENGUBAH", False, False),
    "Diubah": ("MENGUBAH", True, False),
}
_ITEM_SPLIT = re.compile(r"(?:^|\s)\d{1,2}\.\s+(?=[A-Z])")
_STOP = {"peraturan", "otoritas", "jasa", "keuangan", "nomor", "tahun", "tentang", "republik",
         "indonesia", "pojk", "seojk", "surat", "edaran", "atas", "perubahan", "bagi", "dalam",
         "yang", "dan", "atau", "untuk", "oleh", "dengan"}


def parse_items(body: str) -> list[tuple[str, str | None]]:
    """"1. POJK X . Pasal Terkait Pasal 5 2. POJK Y" → [(ref, pasal), ...]."""
    out = []
    for raw in _ITEM_SPLIT.split(" " + body):
        raw = raw.strip(" .;")
        if len(raw) < 6:
            continue
        ref, _, pasal = raw.partition("Pasal Terkait")
        pasal = pasal.strip(" .-") or None
        out.append((ref.strip(" .;"), pasal))
    return out


def parse_riwayat(text: str | None) -> list[tuple[str, str, bool, bool, str | None]]:
    """JDIH "Riwayat Peraturan" → [(rel, ref_text, reverse, partial, pasal)].

    A relation is partial when JDIH says "Sebagian" *or* when "Pasal Terkait"
    names specific provisions. JDIH routinely writes "Dicabut : POJK X .
    Pasal Terkait Pasal 44, Pasal 45 …" for a revocation of those articles
    only — the regulation itself stays in force (its JDIH status is still
    "Berlaku"). Treating that as a full revocation made lineage report four
    "successors" for a regulation that was never replaced.
    """
    if not text or "Belum Ada" in text:
        return []
    parts = _REL_SPLIT.split(text)
    out = []
    for label, body in zip(parts[1::2], parts[2::2]):
        rel, reverse, partial = _REL_MEANING[label]
        for ref, pasal in parse_items(body):
            out.append((rel, ref, reverse, partial or bool(pasal), pasal))
    return out


_ENGLISH = re.compile(r"\b(regulation|concerning|authority|circular letter)\b", re.I)


def _subject_words(title: str | None) -> set[str] | None:
    """Content words of the part after "tentang" — the regulation's subject.

    Everything before it is boilerplate ("Peraturan Otoritas Jasa Keuangan
    Republik Indonesia Nomor ..."), which differs between sources for the
    same regulation and would drown the comparison. None = no subject.
    """
    if not title or _ENGLISH.search(title):
        return None
    parts = re.split(r"\btentang\b", title, maxsplit=1, flags=re.I)
    subject = parts[1] if len(parts) == 2 else (title if "nomor" not in title.lower() else "")
    words = {w for w in re.findall(r"[a-z]{4,}", subject.lower()) if w not in _STOP}
    return words or None


def title_similarity(a: str | None, b: str | None) -> float:
    """Containment of subject words, 0..1; 1.0 when not comparable.

    Containment (|A∩B| / min) rather than Jaccard: one source routinely
    shortens the other's title, and a short title fully inside a long one is
    the same regulation. "Not comparable" (no subject, or an official English
    translation) returns 1.0 — absence of evidence is not a conflict.
    """
    wa, wb = _subject_words(a), _subject_words(b)
    if not wa or not wb:
        return 1.0
    return len(wa & wb) / min(len(wa), len(wb))


@dataclass
class GraphReport:
    nodes: int = 0
    nodes_register: int = 0
    nodes_rujukan: int = 0
    nodes_in_kb: int = 0
    edges: dict[str, int] = field(default_factory=dict)
    refs_seen: int = 0
    refs_unresolved: int = 0
    unresolved_examples: list[str] = field(default_factory=list)
    identity_conflicts: int = 0
    self_loops_dropped: int = 0

    @property
    def resolution_rate(self) -> float:
        return 1 - self.refs_unresolved / self.refs_seen if self.refs_seen else 1.0


class _Builder:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.nodes: dict[str, dict] = {}
        self.edges: dict[tuple[str, str, str], dict] = {}
        self.conflicts: list[tuple] = []
        self.rep = GraphReport()

    # -- nodes ---------------------------------------------------------
    def register(self, ref: RegRef, *, judul, status, record_key=None, doc_id=None,
                 priority: int) -> str:
        """Add a regulation listed by a source. Lower priority wins on fields."""
        key = ref.key
        cur = self.nodes.get(key)
        if cur and cur["asal"] == "register" and title_similarity(cur["judul"], judul) < 0.25:
            # Same identity, unrelated titles: a source typo (e.g. wrong year),
            # not the same regulation. Keep it apart instead of corrupting both.
            self.conflicts.append((key, cur["judul"], judul, record_key,
                                   round(title_similarity(cur["judul"], judul), 3)))
            key = f"{key}~{hashlib.sha1((record_key or doc_id or judul or '').encode()).hexdigest()[:8]}"
            cur = None
        if cur is None:
            self.nodes[key] = {"key": key, "jenis": ref.jenis, "nomor": ref.nomor, "tahun": ref.tahun,
                               "judul": judul, "status": status, "doc_id": doc_id,
                               "record_key": record_key, "asal": "register", "_p": priority}
            return key
        if cur["asal"] == "rujukan":
            cur.update(asal="register", judul=judul or cur["judul"], _p=priority)
        if priority < cur["_p"]:
            cur.update(judul=judul or cur["judul"], _p=priority)
            if status and status != "unknown":
                cur["status"] = status
        elif status and status != "unknown" and (not cur["status"] or cur["status"] == "unknown"):
            cur["status"] = status
        cur["doc_id"] = cur["doc_id"] or doc_id
        cur["record_key"] = cur["record_key"] or record_key
        return key

    def cite(self, text: str) -> str | None:
        """Resolve a cited reference to a node, creating a 'rujukan' node."""
        self.rep.refs_seen += 1
        ref = canonical_ref(text)
        if ref is None:
            self.rep.refs_unresolved += 1
            if len(self.rep.unresolved_examples) < 12:
                self.rep.unresolved_examples.append(text[:120])
            return None
        if ref.key not in self.nodes:
            label = re.split(r"\btentang\b", text, maxsplit=1, flags=re.I)
            judul = text.strip()[:300] if len(label) < 2 else f"{ref.jenis} {ref.nomor}/{ref.tahun} tentang {label[1].strip()}"[:300]
            self.nodes[ref.key] = {"key": ref.key, "jenis": ref.jenis, "nomor": ref.nomor,
                                   "tahun": ref.tahun, "judul": judul, "status": None,
                                   "doc_id": None, "record_key": None, "asal": "rujukan", "_p": 9}
        return ref.key

    def edge(self, src: str | None, dst: str | None, rel: str, *, partial=False,
             pasal=None, asal: str, bukti: str) -> None:
        if not src or not dst:
            return
        if src == dst:
            self.rep.self_loops_dropped += 1
            return
        k = (src, dst, rel)
        if k in self.edges:
            e = self.edges[k]
            e["sebagian"] = e["sebagian"] and int(partial)   # a full relation wins
            e["pasal_terkait"] = e["pasal_terkait"] or pasal
            return
        self.edges[k] = {"src": src, "dst": dst, "rel": rel, "sebagian": int(partial),
                         "pasal_terkait": pasal, "asal": asal, "bukti": bukti[:400]}

    # -- passes --------------------------------------------------------
    def load_register(self) -> dict[str, str]:
        """Nodes from inventory + KB documents. Returns record_key/doc_id → node key."""
        index: dict[str, str] = {}
        # JDIH first: it is the authoritative register, so its titles and
        # statuses win over ojk.go.id listings of the same regulation.
        order = {"jdih-ojk": 0, "ojk-regulasi": 1, "ojk-rancangan": 2}
        rows = self.conn.execute(
            "SELECT record_key, source, doc_type, number, year, title, status, doc_id "
            "FROM inventory WHERE COALESCE(number, '') <> ''").fetchall()
        rows = sorted(rows, key=lambda r: order.get(r["source"], 5))
        for r in rows:
            ref = ref_for_record(r["doc_type"], r["number"], r["year"])
            if ref is None:
                continue
            index[r["record_key"]] = self.register(
                ref, judul=r["title"], status=r["status"], record_key=r["record_key"],
                doc_id=r["doc_id"], priority=order.get(r["source"], 5))
        for d in self.conn.execute(
                "SELECT doc_id, doc_type, number, year, title, reg_status FROM documents "
                "WHERE status IN ('ingested', 'failed')"):
            ref = ref_for_record(d["doc_type"], d["number"], d["year"])
            if ref is None:
                # Still a node, so its Mengingat edges are not lost.
                ref = RegRef(f"DOC|{d['doc_id']}|", (d["doc_type"] or "DOC").upper(), d["doc_id"][:8], d["year"])
            index[d["doc_id"]] = self.register(
                ref, judul=d["title"], status=d["reg_status"], doc_id=d["doc_id"], priority=3)
        return index

    def load_jdih_relations(self, index: dict[str, str]) -> None:
        for r in self.conn.execute(
                "SELECT record_key, fields_json FROM inventory WHERE source = 'jdih-ojk' "
                "AND fields_json IS NOT NULL"):
            me = index.get(r["record_key"])
            if not me:
                continue
            fields = json.loads(r["fields_json"])
            for rel, ref_text, reverse, partial, pasal in parse_riwayat(fields.get("Riwayat Peraturan")):
                other = self.cite(ref_text)
                src, dst = (other, me) if reverse else (me, other)
                self.edge(src, dst, rel, partial=partial, pasal=pasal,
                          asal="jdih-riwayat", bukti=ref_text)
            for ref_text, _ in parse_items(fields.get("Landasan Hukum") or ""):
                self.edge(me, self.cite(ref_text), "BERDASAR", asal="jdih-landasan", bukti=ref_text)

    def load_document_basis(self, index: dict[str, str]) -> None:
        for d in self.conn.execute("SELECT doc_id, metadata_json FROM documents "
                                   "WHERE status IN ('ingested', 'failed')"):
            me = index.get(d["doc_id"])
            basis = (json.loads(d["metadata_json"] or "{}").get("legal_basis") or [])
            for ref_text in basis:
                self.edge(me, self.cite(ref_text), "BERDASAR", asal="dokumen-mengingat",
                          bukti=ref_text)

    def write(self) -> GraphReport:
        self.conn.executescript(SCHEMA)
        with self.conn:
            self.conn.executemany(
                "INSERT INTO graph_node (key, jenis, nomor, tahun, judul, status, doc_id, "
                "record_key, asal) VALUES (:key, :jenis, :nomor, :tahun, :judul, :status, "
                ":doc_id, :record_key, :asal)", list(self.nodes.values()))
            self.conn.executemany(
                "INSERT INTO graph_edge (src, dst, rel, sebagian, pasal_terkait, asal, bukti) "
                "VALUES (:src, :dst, :rel, :sebagian, :pasal_terkait, :asal, :bukti)",
                list(self.edges.values()))
            self.conn.executemany("INSERT INTO graph_identity_conflict VALUES (?, ?, ?, ?, ?)",
                                  self.conflicts)
        rep = self.rep
        rep.nodes = len(self.nodes)
        rep.nodes_register = sum(1 for n in self.nodes.values() if n["asal"] == "register")
        rep.nodes_rujukan = rep.nodes - rep.nodes_register
        rep.nodes_in_kb = sum(1 for n in self.nodes.values() if n["doc_id"])
        for e in self.edges.values():
            rep.edges[e["rel"]] = rep.edges.get(e["rel"], 0) + 1
        rep.identity_conflicts = len(self.conflicts)
        return rep


def build_graph(conn: sqlite3.Connection) -> GraphReport:
    """Rebuild the whole graph from the catalog. Deterministic and idempotent."""
    conn.row_factory = sqlite3.Row
    b = _Builder(conn)
    index = b.load_register()
    b.load_jdih_relations(index)
    b.load_document_basis(index)
    return b.write()
