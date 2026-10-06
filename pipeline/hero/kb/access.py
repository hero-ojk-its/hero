"""Access classification audit: "publik" must be proven, not assumed.

``documents.access_class`` decides what may leave the system — the
AI-Assisted layer refuses ``internal`` documents unless
``analysis.ai_allow_internal`` is set, and exports/snapshots filter on it.
The column defaults to ``publik``, so every document synced from the
partner's OneDrive arrived as public, including internal instruments such as
staff leave rules (PDK), travel tariffs (KDK) and ``…/PADKINT…`` guidelines.

Rule, deterministic and explainable per document:

* fetched from a public regulation site → publik (proof: the source);
* its identity (jenis|nomor|tahun) is listed by JDIH OJK or ojk.go.id → publik
  (proof: the public register);
* otherwise → internal, with the reason recorded, until a person says otherwise.

The audit only ever *tightens*: it never turns ``internal``/``rahasia`` into
``publik``, because a stricter label set by a person outranks inference.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from hero.inventory import reg_key

PUBLIC_SOURCE_TYPES = {"web"}
PUBLIC_REGISTERS = ("jdih-ojk", "ojk-regulasi")
RANK = {"publik": 0, "internal": 1, "rahasia": 2}

# Signals that make "internal" more than a default; reported, not required.
_INTERNAL_NUMBER = re.compile(r"INT\b|INT\.|/PADKINT|/SEDK|/KDK|/PDK\.", re.IGNORECASE)
_INTERNAL_WORDS = re.compile(
    r"\bpegawai otoritas jasa keuangan\b|\bperjalanan dinas\b|\bcuti pegawai\b",
    re.IGNORECASE)


_SHARE_LINK = re.compile(
    r"https?://[^\s]*(?:sharepoint\.com/:[a-z]:/|1drv\.ms/|onedrive\.live\.com/)[^\s]*",
    re.IGNORECASE)


def redact_ref(ref: str | None) -> str | None:
    """Hide share links (bearer secrets) in anything that leaves the catalog."""
    if not ref:
        return ref
    return _SHARE_LINK.sub("[tautan-berbagi-onedrive]", ref)


@dataclass
class AccessFinding:
    doc_id: str
    judul: str
    sumber: str
    reg_key: str | None
    sekarang: str
    usulan: str
    alasan: str

    @property
    def berubah(self) -> bool:
        return RANK.get(self.usulan, 1) > RANK.get(self.sekarang, 0)


def audit(conn: sqlite3.Connection) -> list[AccessFinding]:
    conn.row_factory = sqlite3.Row
    public_keys = {r[0] for r in conn.execute(
        f"SELECT reg_key FROM inventory WHERE reg_key IS NOT NULL "
        f"AND source IN ({','.join('?' * len(PUBLIC_REGISTERS))})", PUBLIC_REGISTERS)}
    out = []
    for d in conn.execute(
            "SELECT doc_id, source_type, doc_type, number, year, title, subject, "
            "original_filename, COALESCE(access_class, 'publik') AS akses FROM documents"):
        key = reg_key(d["doc_type"], d["number"], d["year"])
        judul = (d["subject"] or d["title"] or d["original_filename"] or "")[:120]
        if d["source_type"] in PUBLIC_SOURCE_TYPES:
            usulan, alasan = "publik", "diambil dari situs regulasi publik"
        elif key and key in public_keys:
            usulan, alasan = "publik", f"{key} terdaftar di register publik (JDIH/ojk.go.id)"
        else:
            usulan = "internal"
            signals = []
            if _INTERNAL_NUMBER.search(d["number"] or ""):
                signals.append(f"nomor bertanda internal ({d['number']})")
            if _INTERNAL_WORDS.search(judul):
                signals.append("perihal tentang internal OJK")
            if not key:
                signals.append("identitas tidak terbaca, tidak bisa dicocokkan")
            elif not signals:
                signals.append(f"{key} tidak ditemukan di register publik")
            alasan = "belum terbukti publik: " + "; ".join(signals)
        # Never loosen a stricter label.
        if RANK.get(d["akses"], 1) > RANK[usulan]:
            usulan, alasan = d["akses"], "label lebih ketat dari pengguna dipertahankan"
        out.append(AccessFinding(d["doc_id"], judul, d["source_type"], key,
                                 d["akses"], usulan, alasan))
    return out


def apply(conn: sqlite3.Connection, findings: list[AccessFinding]) -> int:
    changed = [f for f in findings if f.berubah]
    with conn:
        for f in changed:
            conn.execute("UPDATE documents SET access_class = ? WHERE doc_id = ?",
                         (f.usulan, f.doc_id))
    return len(changed)
