"""Build the regulation graph — nodes are regulations, edges are the legal
relationships between them — as two plain SQLite tables.

Sources of edges, all already in the catalog:

* JDIH "Riwayat Peraturan"   → MENCABUT / MENGUBAH (with "Sebagian" = partial)
* JDIH "Landasan Hukum"      → BERDASAR
* a document's "Mengingat"   → BERDASAR (``metadata_json.legal_basis``)
* a document's own text      → MENCABUT / MENGUBAH, read with the same rules as harmonisasi
  (:func:`hero.harmonisasi.refs.relasi_teks`): title "PERUBAHAN … ATAS …" → MENGUBAH; closing
  "… dicabut dan dinyatakan tidak berlaku" → MENCABUT, partial when it names Pasal X, butir,
  Lampiran, "ketentuan mengenai …", or says "kecuali …".

Status is then DERIVED from those edges (a regulation revoked by an enacted one is
``dicabut``), not only copied from a register — most ojk.go.id listings carry no status.

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
    asal TEXT NOT NULL,         -- 'register' (listed by a source) | 'rujukan' (only cited)
    status_register TEXT,       -- status as listed by the register, before derivation
    status_asal TEXT,           -- 'register' | 'turunan' (derived from MENCABUT/MENGUBAH edges)
    status_bukti TEXT           -- for 'turunan': which regulation, and the text that says so
);
CREATE INDEX ix_gn_doc ON graph_node(doc_id);
CREATE INDEX ix_gn_record ON graph_node(record_key);
CREATE TABLE graph_edge (
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    rel TEXT NOT NULL,          -- MENCABUT | MENGUBAH | BERDASAR
    sebagian INTEGER DEFAULT 0, -- partial revocation/amendment
    pasal_terkait TEXT,
    asal TEXT NOT NULL,         -- jdih-riwayat | jdih-landasan | dokumen-mengingat | dokumen-teks
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
    edges_from_text: int = 0
    status_derived: dict[str, int] = field(default_factory=dict)

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

    def load_document_relations(self, index: dict[str, str]) -> None:
        """MENCABUT / MENGUBAH yang dinyatakan teks peraturan itu sendiri (judul & pasal penutup).

        Draft (``rancangan``) dilewati: rancangan belum berlaku, jadi belum mencabut apa pun (ADR-03).
        """
        from hero.harmonisasi.refs import relasi_teks

        rows = self.conn.execute(
            "SELECT d.doc_id, d.doc_type, d.number, d.year, d.title, d.subject, d.reg_status, "
            "t.full_text FROM documents d JOIN document_text t ON t.doc_id = d.doc_id "
            "WHERE d.status = 'ingested' AND COALESCE(d.reg_status, '') <> 'rancangan'").fetchall()
        for d in rows:
            me = index.get(d["doc_id"])
            if not me or me.startswith("DOC|"):
                continue
            judul = " ".join(x for x in (d["title"], d["subject"]) if x)
            for r in relasi_teks(d["full_text"] or "", judul, own_key=me):
                if r.relasi == "dirujuk":
                    continue
                other = self.cite(r.teks)
                if other != r.key:          # rujukan yang tak terpetakan ke identitas kanonik
                    continue
                rel = "MENGUBAH" if r.relasi == "diubah" else "MENCABUT"
                terkait = ", ".join([f"Pasal {p}" for p in r.pasal_dicabut] + r.bagian_dicabut
                                    + ([f"kecuali {r.pengecualian_teks}"] if r.pengecualian_teks else []))
                before = len(self.edges)
                self.edge(me, other, rel, partial=r.relasi == "dicabut_sebagian", pasal=terkait or None,
                          asal="dokumen-teks", bukti=f"[{r.dasar}] {r.kata_kunci or r.teks}")
                self.rep.edges_from_text += len(self.edges) - before

    # Urutan kekuatan status: status turunan hanya MENAIKKAN, tidak pernah menurunkan.
    _RANK = {None: 0, "": 0, "unknown": 0, "tidak_diketahui": 0, "berlaku": 1, "belum_berlaku": 1,
             "diubah": 2, "dicabut_sebagian": 3, "dicabut": 4}

    def derive_status(self) -> None:
        """Status peraturan lama diturunkan dari relasi dokumen-ke-dokumen.

        MENCABUT penuh → ``dicabut``; MENCABUT sebagian → ``dicabut_sebagian``; MENGUBAH →
        ``diubah``. Sumbernya harus peraturan yang berlaku (bukan rancangan). Status register
        yang lebih kuat (mis. JDIH "Dicabut") tidak pernah diturunkan.
        """
        for n in self.nodes.values():
            n["status_register"] = n["status"]
            n["status_asal"] = "register" if n["status"] not in (None, "", "unknown") else None
            n["status_bukti"] = None
        # Peraturan yang masih DIUBAH oleh peraturan lebih baru belum dicabut penuh pada saat itu:
        # riwayat JDIH kadang menulis "Dicabut" tanpa "Sebagian" untuk pencabutan beberapa pasal.
        diubah_tahun: dict[str, int] = {}
        for e in self.edges.values():
            src = self.nodes.get(e["src"])
            if e["rel"] == "MENGUBAH" and src and src.get("tahun"):
                diubah_tahun[e["dst"]] = max(diubah_tahun.get(e["dst"], 0), int(src["tahun"]))
        for e in sorted(self.edges.values(), key=lambda e: (e["rel"] != "MENCABUT", e["sebagian"])):
            if e["rel"] not in ("MENCABUT", "MENGUBAH"):
                continue
            src, dst = self.nodes.get(e["src"]), self.nodes.get(e["dst"])
            if not src or not dst or (src.get("status") or "") == "rancangan":
                continue
            turunan = ("diubah" if e["rel"] == "MENGUBAH"
                       else "dicabut_sebagian" if e["sebagian"] else "dicabut")
            catatan = ""
            if turunan == "dicabut" and src.get("tahun") and diubah_tahun.get(e["dst"], 0) > int(src["tahun"]):
                turunan = "dicabut_sebagian"
                catatan = (f" [dibaca sebagian: masih diubah peraturan tahun {diubah_tahun[e['dst']]}, "
                           f"setelah pencabutan tahun {src['tahun']}]")
            if self._RANK.get(turunan, 0) > self._RANK.get(dst["status"], 0):
                dst["status"], dst["status_asal"] = turunan, "turunan"
                dst["status_bukti"] = f"{e['src']} {e['rel']} ({e['asal']}): {e['bukti']}{catatan}"[-400:] \
                    if catatan else f"{e['src']} {e['rel']} ({e['asal']}): {e['bukti']}"[:400]
                self.rep.status_derived[turunan] = self.rep.status_derived.get(turunan, 0) + 1

    def write(self) -> GraphReport:
        self.conn.executescript(SCHEMA)
        with self.conn:
            self.conn.executemany(
                "INSERT INTO graph_node (key, jenis, nomor, tahun, judul, status, doc_id, "
                "record_key, asal, status_register, status_asal, status_bukti) VALUES (:key, :jenis, "
                ":nomor, :tahun, :judul, :status, :doc_id, :record_key, :asal, :status_register, "
                ":status_asal, :status_bukti)",
                [{"status_register": n.get("status"), "status_asal": None, "status_bukti": None, **n}
                 for n in self.nodes.values()])
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
    b.load_document_relations(index)
    b.derive_status()
    return b.write()
