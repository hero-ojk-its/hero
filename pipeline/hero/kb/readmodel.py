"""Read model for the Knowledge Base screens — one row per document, shaped
exactly like the table and detail drawer the frontend shows.

Why a separate table instead of querying ``documents`` directly: the fields
the UI needs (ringkasan, poin kunci, topik, penyelarasan pasal, urgensi) live
inside JSON blobs in ``document_text.analysis`` — often hundreds of KB per
document. Serving a filtered, paginated list straight from there means
parsing every blob on every request. This module does that work once, at
write time, into plain indexed columns (a CQRS-style read model), so a list
request is a single indexed SELECT.

Freshness: ``sync()`` rebuilds only rows whose source changed, detected with
a fingerprint computed in SQL. ``sync_if_stale()`` makes that cheap enough to
call on every request by first checking SQLite's ``PRAGMA data_version``,
which changes only when *another* connection commits — so a document ingested
from the CLI appears in a running API without a restart.

All labels here are the ones the UI displays ("Aktif", "Scraping", …), and
every derived value keeps the reason it was derived, because a regulator
must be able to ask "why is this marked Tinggi?" and get an answer.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hero.kb.topics import ALL_TOPICS, assign_topics

# --------------------------------------------------------------------------
# UI vocabularies. The frontend reads these from /api/meta/enums rather than
# hardcoding them, so a label change happens in exactly one place.
# --------------------------------------------------------------------------
STATUS_LABELS: dict[str, tuple[str, str]] = {
    # value: (label, tone) — tone maps to the badge colour in the design
    "berlaku": ("Aktif", "success"),
    "diubah": ("Diubah", "warning"),
    "dicabut": ("Dicabut", "danger"),
    "rancangan": ("Rancangan", "info"),
    "unknown": ("Tidak Diketahui", "neutral"),
}
SOURCE_LABELS: dict[str, str] = {
    "web": "Scraping",
    "onedrive": "OneDrive",
    "local_folder": "Folder Lokal",
    "upload": "Unggah Manual",
}
CATEGORY_LABELS: dict[str, str] = {
    "perbankan": "Perbankan",
    "pasar-modal": "Pasar Modal",
    "iknb": "IKNB",
    "teknologi-informasi": "Teknologi Informasi",
    "perlindungan-konsumen": "Perlindungan Konsumen",
    "apu-ppt": "APU-PPT",
    "tata-kelola": "Tata Kelola",
    "kelembagaan": "Kelembagaan",
    "bank-indonesia": "Bank Indonesia",
    "lain-lain": "Lain-lain",
}
ALIGNMENT_LABELS: dict[str, tuple[str, str]] = {
    "lengkap": ("Terpetakan Lengkap", "success"),
    "sebagian": ("Terpetakan Sebagian", "warning"),
    "seksi": ("Terpetakan per Seksi", "success"),
    "belum": ("Belum Terpetakan", "danger"),
}
URGENCY_LABELS: dict[str, tuple[str, str]] = {
    "tinggi": ("Tinggi", "danger"),
    "sedang": ("Sedang", "warning"),
    "rendah": ("Rendah", "neutral"),
}
ACCESS_LABELS: dict[str, str] = {"publik": "Publik", "internal": "Internal", "rahasia": "Rahasia"}

# Surat Edaran are organised in Roman-numeral sections, not Pasal (see
# hero.dq.rules.PASAL_BEARING_TYPES for the same distinction).
SECTION_TYPES = ("SEOJK", "SEBI", "SE", "SEDK", "SPEOJK")

# Takeaways worth showing first in "Poin Kunci": the ones that create duties.
_TAKEAWAY_PRIORITY = {"Sanksi": 0, "Kewajiban": 1, "Larangan": 2, "Batas Waktu": 3,
                      "Pelaporan": 4, "Perizinan": 5, "Pencabutan": 6, "Masa Berlaku": 7}

# Sanction severity, most severe first — the reason shown next to "Tinggi".
_SANCTION_KINDS = (
    ("pencabutan izin", "Sanksi Pencabutan Izin"),
    ("denda", "Sanksi Denda"),
    ("pembatasan kegiatan", "Sanksi Pembatasan Kegiatan"),
    ("pembekuan", "Sanksi Pembekuan Kegiatan"),
    ("tertulis", "Sanksi Tertulis"),
)

_SMALL_WORDS = {"dan", "di", "ke", "yang", "atau", "untuk", "bagi", "dalam", "oleh",
                "pada", "dari", "serta", "tentang", "atas", "dengan", "melalui", "sebagai",
                "kepada", "terhadap", "secara", "antara", "sebagaimana", "hingga", "atau"}
_ACRONYMS = {"OJK", "BPR", "BPRS", "IT", "TI", "APU", "PPT", "LJK", "BUS", "UUS", "PT",
             "RI", "BI", "IKNB", "P2P", "LPS", "BUMN", "UMKM", "ESG", "API"}
_MONTHS = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
           "September", "Oktober", "November", "Desember")


def title_case_id(text: str | None) -> str:
    """"PEDOMAN TRANSAKSI REPO BAGI LJK" → "Pedoman Transaksi Repo bagi LJK"."""
    if not text:
        return ""
    words = re.split(r"(\s+)", text.strip())
    out = []
    for i, w in enumerate(words):
        if not w.strip():
            out.append(w)
            continue
        bare = re.sub(r"[^\w/-]", "", w)
        if bare.upper() in _ACRONYMS:
            out.append(w.upper())
        elif i > 0 and bare.lower() in _SMALL_WORDS:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:].lower())
    return "".join(out)


def display_title(jenis: str | None, raw_title: str | None) -> str:
    """Source title → the form every table in the design uses.

    "Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 9/POJK.03/2016
    tentang PRINSIP KEHATI-HATIAN …" → "POJK tentang Prinsip Kehati-hatian …".
    Shared by the Knowledge Base table and the scan/ingest tables so the same
    regulation reads the same on every screen.
    """
    if not raw_title:
        return ""
    parts = re.split(r"\btentang\b", raw_title, maxsplit=1, flags=re.I)
    if len(parts) == 2 and jenis:
        return f"{jenis.upper()} tentang {title_case_id(parts[1].strip(' .'))}"
    return raw_title.strip()


def number_line(jenis: str | None, number: str | None) -> str | None:
    """"POJK No. 11/POJK.03/2024" — the grey line under a title in the design."""
    if not number:
        return None
    return f"{jenis.upper()} No. {number}" if jenis else f"No. {number}"


def short_number(doc_type: str | None, number: str | None, year: int | None) -> str | None:
    """"11/POJK.03/2024" → "POJK-11/2024" (the compact form in the table)."""
    if not number:
        return None
    m = re.match(r"\s*(?:No\.?\s*)?(\d+)", number)
    serial = m.group(1) if m else number.strip()
    jenis = (doc_type or "").upper()
    return f"{jenis}-{serial}/{year}" if jenis and year else (f"{jenis}-{serial}" if jenis else serial)


def date_label(iso: str | None) -> str | None:
    """"2024-03-12" → "12 Maret 2024"."""
    if not iso:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso)
    if not m:
        return iso
    y, mo, d = (int(g) for g in m.groups())
    return f"{d} {_MONTHS[mo - 1]} {y}" if 1 <= mo <= 12 else iso


def pasal_alignment(doc_type: str | None, structure_quality: dict | None,
                    section_count: int = 0) -> tuple[str, str]:
    """Is every Pasal mapped? Returns (value, reason)."""
    sq = structure_quality or {}
    n = int(sq.get("article_count") or 0)
    if (doc_type or "").upper() in SECTION_TYPES and (section_count or sq.get("section_count")):
        return "seksi", "Surat Edaran disusun per seksi angka Romawi, bukan pasal"
    if n == 0:
        return "belum", "Parser struktur tidak menemukan satu pun pasal"
    problems = []
    if not sq.get("starts_at_pasal_1", True):
        problems.append("tidak dimulai dari Pasal 1")
    if not sq.get("numbering_ascending", True):
        problems.append("penomoran tidak berurutan")
    if sq.get("duplicate_numbers"):
        problems.append(f"nomor ganda: {', '.join(map(str, sq['duplicate_numbers'][:5]))}")
    if problems:
        return "sebagian", f"{n} pasal terbaca; " + "; ".join(problems)
    return "lengkap", f"{n} pasal terbaca, berurutan mulai Pasal 1"


def harmonization_urgency(status: str | None, takeaways: list[dict]) -> tuple[str, str]:
    """How urgently must a new draft be checked against this regulation?

    Rule, in order: a revoked regulation cannot conflict with anything
    (rendah); one that attaches sanctions is tinggi, with the most severe
    sanction as the reason; one that imposes duties, prohibitions or
    deadlines without sanctions is sedang; anything else is rendah.
    """
    if status == "dicabut":
        return "rendah", "Peraturan sudah dicabut"
    by_cat: dict[str, list[str]] = {}
    for t in takeaways or []:
        by_cat.setdefault(t.get("category", ""), []).append((t.get("text") or "").lower())
    sanksi = by_cat.get("Sanksi", [])
    if sanksi:
        blob = " ".join(sanksi)
        for needle, label in _SANCTION_KINDS:
            if needle in blob:
                return "tinggi", label
        return "tinggi", "Memuat Sanksi"
    duties = sum(len(by_cat.get(k, [])) for k in ("Kewajiban", "Larangan", "Batas Waktu"))
    if duties:
        return "sedang", f"{duties} kewajiban/larangan tanpa sanksi eksplisit"
    return "rendah", "Tidak ditemukan kewajiban, larangan, atau sanksi"


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS kb_document_view (
    doc_id TEXT PRIMARY KEY,
    judul TEXT NOT NULL,
    judul_asli TEXT,
    tentang TEXT,
    jenis TEXT,
    nomor TEXT,
    nomor_singkat TEXT,
    kategori TEXT,
    kategori_label TEXT,
    topik TEXT,
    topik_semua TEXT,
    topik_alasan TEXT,
    tahun INTEGER,
    tanggal_terbit TEXT,
    tanggal_terbit_label TEXT,
    status TEXT,
    status_label TEXT,
    sumber TEXT,
    sumber_label TEXT,
    sumber_detail TEXT,
    akses TEXT DEFAULT 'publik',
    ringkasan TEXT,
    poin_kunci TEXT,
    penyelarasan_pasal TEXT,
    penyelarasan_alasan TEXT,
    urgensi TEXT,
    urgensi_alasan TEXT,
    jumlah_pasal INTEGER,
    jumlah_halaman INTEGER,
    dasar_hukum TEXT,
    pdf_lokal INTEGER,
    ingested_at TEXT,
    fingerprint TEXT
);
CREATE INDEX IF NOT EXISTS ix_kbv_kategori ON kb_document_view(kategori);
CREATE INDEX IF NOT EXISTS ix_kbv_jenis ON kb_document_view(jenis);
CREATE INDEX IF NOT EXISTS ix_kbv_tahun ON kb_document_view(tahun);
CREATE INDEX IF NOT EXISTS ix_kbv_status ON kb_document_view(status);
CREATE INDEX IF NOT EXISTS ix_kbv_sumber ON kb_document_view(sumber);
CREATE INDEX IF NOT EXISTS ix_kbv_ingested ON kb_document_view(ingested_at);
CREATE INDEX IF NOT EXISTS ix_kbv_sort ON kb_document_view(tahun DESC, judul);

CREATE TABLE IF NOT EXISTS kb_document_topic (
    doc_id TEXT NOT NULL,
    topik TEXT NOT NULL,
    PRIMARY KEY (doc_id, topik)
);
CREATE INDEX IF NOT EXISTS ix_kbt_topik ON kb_document_topic(topik, doc_id);

CREATE VIRTUAL TABLE IF NOT EXISTS kb_document_search USING fts5(
    doc_id UNINDEXED, judul, nomor, tentang, topik, ringkasan,
    tokenize = 'unicode61 remove_diacritics 2',
    prefix = '2 3'
);
"""

# Fingerprint of everything a view row is derived from. Computed in SQL so
# finding stale rows never requires parsing JSON.
_FINGERPRINT_SQL = """
    d.ingested_at || '|' || COALESCE(t.updated_at, '') || '|' ||
    COALESCE(d.source_name, '') || '|' || COALESCE(d.reg_status, '') || '|' ||
    COALESCE(d.category, '') || '|' || COALESCE(d.stored_path, '') || '|' ||
    COALESCE(d.title, '') || '|' || COALESCE(d.access_class, '') || '|' ||
    COALESCE((SELECT a.dibuat || a.versi FROM analysis_v2 a WHERE a.doc_id = d.doc_id), '')
"""


def _ensure_access_column(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
    if "access_class" not in cols:
        conn.execute("ALTER TABLE documents ADD COLUMN access_class TEXT DEFAULT 'publik'")


def ensure_schema(conn: sqlite3.Connection) -> None:
    from hero.analysis.structured import SCHEMA as ANALYSIS_SCHEMA

    _ensure_access_column(conn)
    conn.executescript(SCHEMA)
    conn.executescript(ANALYSIS_SCHEMA)


def _json(value: Any, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def build_row(doc: sqlite3.Row, text_row: sqlite3.Row | None) -> dict[str, Any]:
    """Turn one catalog document into one UI-ready row. Pure function."""
    md = _json(doc["metadata_json"], {})
    analysis = _json(text_row["analysis"], {}) if text_row else {}
    structure = _json(text_row["structure"], {}) if text_row else {}

    jenis = (doc["doc_type"] or md.get("doc_type") or "").upper() or None
    tentang_raw = doc["subject"] or md.get("subject") or ""
    tentang = title_case_id(tentang_raw)
    judul = f"{jenis} tentang {tentang}" if jenis and tentang else (doc["title"] or doc["original_filename"])

    terms = [t.get("term", "") for t in analysis.get("topics", []) if isinstance(t, dict)]
    hits = assign_topics(doc["title"], tentang_raw, terms)
    topik_semua = [h.label for h in hits] or ["Umum"]

    status = doc["reg_status"] or md.get("status") or "unknown"
    status_label = STATUS_LABELS.get(status, STATUS_LABELS["unknown"])[0]
    takeaways = [t for t in analysis.get("key_takeaways", []) if isinstance(t, dict)]
    takeaways.sort(key=lambda t: _TAKEAWAY_PRIORITY.get(t.get("category", ""), 99))
    poin = [{"kategori": t.get("category"), "pasal": t.get("pasal"),
             "halaman": t.get("page"), "teks": (t.get("text") or "")[:600]}
            for t in takeaways[:8]]

    align, align_reason = pasal_alignment(
        jenis, analysis.get("structure_quality"), int(structure.get("section_count") or 0))
    urg, urg_reason = harmonization_urgency(status, takeaways)

    stored = doc["stored_path"]
    return {
        "doc_id": doc["doc_id"],
        "judul": judul,
        "judul_asli": doc["title"],
        "tentang": tentang or None,
        "jenis": jenis,
        "nomor": doc["number"],
        "nomor_singkat": short_number(jenis, doc["number"], doc["year"]),
        "kategori": doc["category"],
        "kategori_label": CATEGORY_LABELS.get(doc["category"] or "", title_case_id(doc["category"] or "")),
        "topik": topik_semua[0],
        "topik_semua": json.dumps(topik_semua, ensure_ascii=False),
        "topik_alasan": json.dumps([{"topik": h.label, "kata_kunci": h.keyword, "dari": h.field}
                                    for h in hits], ensure_ascii=False),
        "tahun": doc["year"],
        "tanggal_terbit": doc["issued_date"],
        "tanggal_terbit_label": date_label(doc["issued_date"]),
        "status": status,
        "status_label": status_label,
        "sumber": doc["source_type"],
        "sumber_label": SOURCE_LABELS.get(doc["source_type"] or "", doc["source_type"]),
        "sumber_detail": doc["source_name"],
        "akses": (doc["access_class"] if "access_class" in doc.keys() else None) or "publik",
        "ringkasan": analysis.get("summary"),
        "poin_kunci": json.dumps(poin, ensure_ascii=False),
        "penyelarasan_pasal": align,
        "penyelarasan_alasan": align_reason,
        "urgensi": urg,
        "urgensi_alasan": urg_reason,
        "jumlah_pasal": int((analysis.get("structure_quality") or {}).get("article_count") or 0),
        "jumlah_halaman": doc["page_count"],
        "dasar_hukum": json.dumps(md.get("legal_basis") or [], ensure_ascii=False),
        "pdf_lokal": int(bool(stored) and Path(stored).exists()),
        "ingested_at": doc["ingested_at"],
    }


_COLUMNS = ("doc_id", "judul", "judul_asli", "tentang", "jenis", "nomor", "nomor_singkat",
            "kategori", "kategori_label", "topik", "topik_semua", "topik_alasan", "tahun",
            "tanggal_terbit", "tanggal_terbit_label", "status", "status_label", "sumber",
            "sumber_label", "sumber_detail", "akses", "ringkasan", "poin_kunci",
            "penyelarasan_pasal", "penyelarasan_alasan", "urgensi", "urgensi_alasan",
            "jumlah_pasal", "jumlah_halaman", "dasar_hukum", "pdf_lokal", "ingested_at",
            "fingerprint")


def _write(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        f"INSERT OR REPLACE INTO kb_document_view ({', '.join(_COLUMNS)}) "
        f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
        tuple(row.get(c) for c in _COLUMNS))
    conn.execute("DELETE FROM kb_document_topic WHERE doc_id = ?", (row["doc_id"],))
    conn.executemany("INSERT OR IGNORE INTO kb_document_topic (doc_id, topik) VALUES (?, ?)",
                     [(row["doc_id"], t) for t in json.loads(row["topik_semua"])])
    conn.execute("DELETE FROM kb_document_search WHERE doc_id = ?", (row["doc_id"],))
    conn.execute(
        "INSERT INTO kb_document_search (doc_id, judul, nomor, tentang, topik, ringkasan) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (row["doc_id"], row["judul"], f"{row['nomor'] or ''} {row['nomor_singkat'] or ''}",
         row["tentang"] or "", " ".join(json.loads(row["topik_semua"])),
         (row["ringkasan"] or "")[:4000]))


def _delete(conn: sqlite3.Connection, doc_ids: list[str]) -> None:
    for d in doc_ids:
        conn.execute("DELETE FROM kb_document_view WHERE doc_id = ?", (d,))
        conn.execute("DELETE FROM kb_document_topic WHERE doc_id = ?", (d,))
        conn.execute("DELETE FROM kb_document_search WHERE doc_id = ?", (d,))


def _apply_v2(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    """Drawer text from Fase 2 v2 analysis when it exists (``hero analisa --semua``).

    v2 points are whole ayat with exact Pasal citations; v1 fields stay as the
    fallback so a document analysed before v2 still shows something.
    """
    got = conn.execute("SELECT hasil FROM analysis_v2 WHERE doc_id = ?", (row["doc_id"],)).fetchone()
    if not got:
        return
    a = json.loads(got[0])
    points = {p["id"]: p for p in a.get("poin", [])}
    top = [points[i] for i in a.get("poin_utama", []) if i in points][:8]
    row["ringkasan"] = a.get("ringkasan_teks") or row["ringkasan"]
    row["poin_kunci"] = json.dumps([{"kategori": p["kategori"], "pasal": p["pasal"], "halaman": p["halaman"],
                                     "teks": p["teks"][:600]} for p in top], ensure_ascii=False)
    urg, reason = harmonization_urgency(row["status"], [{"category": p["kategori"], "text": p["teks"]}
                                                        for p in points.values()])
    row["urgensi"], row["urgensi_alasan"] = urg, reason


@dataclass
class SyncReport:
    rebuilt: int = 0
    removed: int = 0
    unchanged: int = 0


def sync(conn: sqlite3.Connection, *, full: bool = False) -> SyncReport:
    """Bring the read model up to date with ``documents``. Idempotent."""
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    rep = SyncReport()
    gone = [r[0] for r in conn.execute(
        "SELECT doc_id FROM kb_document_view WHERE doc_id NOT IN (SELECT doc_id FROM documents)")]
    stale_sql = f"""
        SELECT d.doc_id, {_FINGERPRINT_SQL} AS fp
        FROM documents d LEFT JOIN document_text t USING (doc_id)
        LEFT JOIN kb_document_view v ON v.doc_id = d.doc_id
        WHERE d.status IN ('ingested', 'failed')
          AND ({'1' if full else '0'} OR v.fingerprint IS NULL OR v.fingerprint <> ({_FINGERPRINT_SQL}))
    """
    stale = conn.execute(stale_sql).fetchall()
    with conn:
        _delete(conn, gone)
        for s in stale:
            doc = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (s["doc_id"],)).fetchone()
            text = conn.execute("SELECT structure, analysis, updated_at FROM document_text "
                                "WHERE doc_id = ?", (s["doc_id"],)).fetchone()
            row = build_row(doc, text)
            _apply_v2(conn, row)
            row["fingerprint"] = s["fp"]
            _write(conn, row)
    rep.removed = len(gone)
    rep.rebuilt = len(stale)
    rep.unchanged = conn.execute("SELECT COUNT(*) FROM kb_document_view").fetchone()[0] - rep.rebuilt
    return rep


class ReadModel:
    """Query side of the Knowledge Base screens.

    Holds one connection and re-syncs lazily: ``PRAGMA data_version`` tells
    us whether any other connection committed since we last looked, which
    costs microseconds — so correctness does not require callers to remember
    to refresh after every ingest.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._seen_version: int | None = None
        ensure_schema(conn)

    def sync_if_stale(self) -> SyncReport | None:
        version = self.conn.execute("PRAGMA data_version").fetchone()[0]
        if version == self._seen_version:
            return None
        rep = sync(self.conn)
        self._seen_version = self.conn.execute("PRAGMA data_version").fetchone()[0]
        return rep

    # -- list ------------------------------------------------------------
    def list(self, *, q: str | None = None, kategori: list[str] | None = None,
             jenis: list[str] | None = None, tahun: list[int] | None = None,
             topik: list[str] | None = None, status: list[str] | None = None,
             sumber: list[str] | None = None, akses: list[str] | None = None,
             sort: str = "terbaru", page: int = 1, page_size: int = 8) -> dict[str, Any]:
        self.sync_if_stale()
        where, params = self._filters(kategori, jenis, tahun, topik, status, sumber, akses)
        join, order = "", _SORTS.get(sort, _SORTS["terbaru"])
        mode = None
        if q and q.strip():
            # Tier 1: every word must match (precise, what users expect while
            # typing a title or number). Tier 2, only if tier 1 finds nothing:
            # any word, ranked by BM25 — measured on the paraphrase set, tier 1
            # alone answers 0 of 12 everyday-language queries.
            for mode, match in (("semua_kata", fts_query(q)), ("sebagian_kata", fts_query(q, any_word=True))):
                if not match:
                    continue
                cand_where = [*where, "kb_document_search MATCH ?"]
                cand_params = [*params, match]
                n = self.conn.execute(
                    f"SELECT COUNT(*) FROM kb_document_view v JOIN kb_document_search s "
                    f"ON s.doc_id = v.doc_id WHERE {' AND '.join(cand_where)}", cand_params).fetchone()[0]
                if n or mode == "sebagian_kata":
                    join = "JOIN kb_document_search s ON s.doc_id = v.doc_id"
                    where, params = cand_where, cand_params
                    if sort == "relevansi" or mode == "sebagian_kata":
                        order = "bm25(kb_document_search, 0, 10.0, 8.0, 5.0, 3.0, 1.0)"
                    break
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        total = self.conn.execute(
            f"SELECT COUNT(*) FROM kb_document_view v {join} {clause}", params).fetchone()[0]
        page = max(page, 1)
        page_size = max(1, min(page_size, 100))
        rows = self.conn.execute(
            f"SELECT v.* FROM kb_document_view v {join} {clause} ORDER BY {order} "
            f"LIMIT ? OFFSET ?", [*params, page_size, (page - 1) * page_size]).fetchall()
        return {
            "items": [list_item(r) for r in rows],
            "total": total, "page": page, "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
            # Lets the UI say "menampilkan hasil yang cocok sebagian" instead
            # of silently mixing precise and loose matches.
            "pencarian": mode,
        }

    def filtered_ids(self, *, kategori=None, jenis=None, tahun=None, topik=None,
                     status=None, sumber=None, akses=None) -> set[str] | None:
        """Doc ids passing the filters, or None when no filter is set (= all)."""
        self.sync_if_stale()
        where, params = self._filters(kategori, jenis, tahun, topik, status, sumber, akses)
        if not where:
            return None
        return {r[0] for r in self.conn.execute(
            f"SELECT v.doc_id FROM kb_document_view v WHERE {' AND '.join(where)}", params)}

    def items_by_id(self, doc_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not doc_ids:
            return {}
        rows = self.conn.execute(
            f"SELECT * FROM kb_document_view WHERE doc_id IN ({', '.join('?' for _ in doc_ids)})",
            doc_ids).fetchall()
        return {r["doc_id"]: list_item(r) for r in rows}

    def _filters(self, kategori, jenis, tahun, topik, status, sumber, akses):
        where: list[str] = []
        params: list[Any] = []
        for column, values in (("v.kategori", kategori), ("v.jenis", jenis), ("v.tahun", tahun),
                               ("v.status", status), ("v.sumber", sumber), ("v.akses", akses)):
            if values:
                where.append(f"{column} IN ({', '.join('?' for _ in values)})")
                params.extend(values)
        if topik:
            where.append(f"v.doc_id IN (SELECT doc_id FROM kb_document_topic "
                         f"WHERE topik IN ({', '.join('?' for _ in topik)}))")
            params.extend(topik)
        return where, params

    # -- facets ----------------------------------------------------------
    def facets(self) -> dict[str, list[dict[str, Any]]]:
        """Filter options with counts, straight from the data.

        The frontend builds every dropdown from this, so a category that has
        no documents never appears, and a new one appears without a deploy.
        """
        self.sync_if_stale()
        out: dict[str, list[dict[str, Any]]] = {}
        for key, col, label_col in (("kategori", "kategori", "kategori_label"),
                                    ("jenis", "jenis", "jenis"),
                                    ("status", "status", "status_label"),
                                    ("sumber", "sumber", "sumber_label"),
                                    ("akses", "akses", "akses")):
            out[key] = [{"value": r[0], "label": r[1] if key != "akses" else ACCESS_LABELS.get(r[0], r[0]),
                         "count": r[2]} for r in self.conn.execute(
                f"SELECT {col}, {label_col}, COUNT(*) FROM kb_document_view "
                f"WHERE {col} IS NOT NULL GROUP BY 1, 2 ORDER BY 3 DESC")]
        out["tahun"] = [{"value": r[0], "label": str(r[0]), "count": r[1]} for r in self.conn.execute(
            "SELECT tahun, COUNT(*) FROM kb_document_view WHERE tahun IS NOT NULL "
            "GROUP BY 1 ORDER BY 1 DESC")]
        counts = dict(self.conn.execute("SELECT topik, COUNT(*) FROM kb_document_topic GROUP BY 1"))
        out["topik"] = [{"value": t, "label": t, "count": counts[t]} for t in ALL_TOPICS if t in counts]
        return out

    # -- detail ----------------------------------------------------------
    def get(self, doc_id: str) -> dict[str, Any] | None:
        self.sync_if_stale()
        row = self.conn.execute("SELECT * FROM kb_document_view WHERE doc_id = ?", (doc_id,)).fetchone()
        return detail_item(row) if row else None


_SORTS = {
    "terbaru": "v.ingested_at DESC",
    "tahun_desc": "v.tahun DESC, v.judul",
    "tahun_asc": "v.tahun ASC, v.judul",
    "judul": "v.judul COLLATE NOCASE",
    "relevansi": "v.tahun DESC",   # replaced by bm25 when a query is present
}


_SEARCH_STOP = {"yang", "dan", "di", "ke", "dari", "untuk", "dengan", "pada", "dalam", "atau",
                "ini", "itu", "oleh", "bagi", "tentang", "sebagai", "adalah", "akan", "lewat"}


def fts_query(q: str, *, any_word: bool = False) -> str | None:
    """User text → a safe FTS5 query with prefix matching on each word.

    Raw input cannot go to MATCH directly: a stray quote or "AND" is FTS5
    syntax and raises an error. Every token is quoted, so the search box is
    literal text, and the last token gets a prefix star so "keaman" finds
    "keamanan" while the user is still typing.
    """
    tokens = re.findall(r"[\w./-]+", q.lower())
    tokens = [t.replace('"', "") for t in tokens if len(t) >= 2][:12]
    if any_word:
        tokens = [t for t in tokens if t not in _SEARCH_STOP and len(t) >= 3]
    if not tokens:
        return None
    return (" OR " if any_word else " ").join(f'"{t}"*' for t in tokens)


def list_item(r: sqlite3.Row) -> dict[str, Any]:
    tone = STATUS_LABELS.get(r["status"], STATUS_LABELS["unknown"])[1]
    return {
        "id": r["doc_id"],
        "judul": r["judul"],
        "jenis": r["jenis"],
        "nomor": r["nomor"],
        "nomor_singkat": r["nomor_singkat"],
        "kategori": {"value": r["kategori"], "label": r["kategori_label"]},
        "topik": r["topik"],
        "tahun": r["tahun"],
        "status": {"value": r["status"], "label": r["status_label"], "tone": tone},
        "sumber": {"value": r["sumber"], "label": r["sumber_label"]},
    }


def detail_item(r: sqlite3.Row) -> dict[str, Any]:
    item = list_item(r)
    align_label, align_tone = ALIGNMENT_LABELS.get(r["penyelarasan_pasal"], ("?", "neutral"))
    urg_label, urg_tone = URGENCY_LABELS.get(r["urgensi"], ("?", "neutral"))
    item.update({
        "judul_asli": r["judul_asli"],
        "tentang": r["tentang"],
        "topik_semua": json.loads(r["topik_semua"] or "[]"),
        "topik_alasan": json.loads(r["topik_alasan"] or "[]"),
        "tanggal_terbit": {"iso": r["tanggal_terbit"], "label": r["tanggal_terbit_label"]},
        "sumber_detail": r["sumber_detail"],
        "akses": {"value": r["akses"], "label": ACCESS_LABELS.get(r["akses"], r["akses"])},
        "ringkasan": r["ringkasan"],
        "poin_kunci": json.loads(r["poin_kunci"] or "[]"),
        "validasi": {
            "penyelarasan_pasal": {"value": r["penyelarasan_pasal"], "label": align_label,
                                   "tone": align_tone, "alasan": r["penyelarasan_alasan"]},
            "urgensi_harmonisasi": {"value": r["urgensi"], "label": urg_label, "tone": urg_tone,
                                    "alasan": r["urgensi_alasan"],
                                    "tampil": f"{urg_label} ({r['urgensi_alasan']})"},
        },
        "jumlah_pasal": r["jumlah_pasal"],
        "jumlah_halaman": r["jumlah_halaman"],
        "dasar_hukum": json.loads(r["dasar_hukum"] or "[]"),
        "pdf": {"tersedia_lokal": bool(r["pdf_lokal"]),
                "url": f"/api/kb/documents/{r['doc_id']}/pdf"},
    })
    return item
