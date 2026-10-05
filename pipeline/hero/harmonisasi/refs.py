"""Explicit references in a draft (FR-HRM-03) and their legal status (FR-HRM-04).

Two things are read straight from the draft's text, without similarity:

* **Regulations it cites** — every "Peraturan … Nomor … Tahun …" mention,
  resolved to a canonical identity and looked up in the graph, so a citation
  of a revoked regulation becomes a finding together with what replaced it.
* **What it says it changes** — the title "Perubahan atas …", the closing
  "… dicabut dan dinyatakan tidak berlaku", and the amendment instructions
  ("Ketentuan Pasal 5 diubah", "disisipkan 1 (satu) pasal, yakni Pasal 12A",
  "Pasal 7 dihapus"). These decide *menggantikan* versus *konflik*, and they
  double as ground truth for calibrating the similarity thresholds.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from hero.graph.identity import canonical_ref

# "Peraturan Otoritas Jasa Keuangan Nomor 14 Tahun 2023", "POJK Nomor 1/POJK.05/2016",
# "Undang-Undang Nomor 4 Tahun 2023", "Surat Edaran OJK Nomor 25/SEOJK.05/2019".
_REF = re.compile(
    r"((?:Peraturan|Undang-Undang|Surat\s+Edaran|Keputusan|POJK|SEOJK|PADK|UU)\b"
    r"[^;:()]{0,140}?\bNomor\s+[\w./-]+(?:\s+Tahun\s+\d{4})?)",
    re.IGNORECASE)
_SELF = re.compile(r"\b(?:ini|tersebut)\b", re.IGNORECASE)

# One amendment instruction: "3. Ketentuan Pasal 5 diubah sehingga berbunyi …",
# "4. Di antara Pasal 12 dan Pasal 13 disisipkan 1 (satu) pasal, yakni Pasal 12A …".
_INSTRUCTION = re.compile(
    r"(?:^|\s)(?:\d+\.\s+)?((?:Ketentuan|Di\s*antara|Setelah|Pasal\s+\d+[A-Z]?\s+dihapus)"
    r".{0,700}?)(?=(?:berbunyi\s+)?sebagai\s+berikut|\s\d+\.\s+(?:Ketentuan|Di\s*antara|Setelah)|$)",
    re.IGNORECASE)
_PASAL_NO = re.compile(r"\bPasal\s+(\d+[A-Z]?)\b", re.IGNORECASE)
_INSERTS_ARTICLES = re.compile(r"disisipkan\s*\d*\s*\([^)]*\)\s*(?:pasal|bab)\b", re.IGNORECASE)
_INSERT_LIST = re.compile(r"\b(?:yakni|dengan)\b(?!.*\b(?:yakni|dengan)\b)(.*)$", re.IGNORECASE)
_WHOLE_DELETE = re.compile(r"^(?:Ketentuan\s+)?Pasal\s+(\d+[A-Z]?)\s+dihapus", re.IGNORECASE)
_CLOSING = re.compile(r"\bDitetapkan\s+di\b", re.IGNORECASE)
_VERB = re.compile(r"\b(?:diubah|dihapus|disisipkan|ditambahkan)", re.IGNORECASE)
_AMENDS_TITLE = re.compile(r"\bPERUBAHAN\s+(?:\w+\s+)?ATAS\b", re.IGNORECASE)
_REVOKES = re.compile(r"dicabut\s+dan\s+dinyatakan\s+tidak\s+berlaku", re.IGNORECASE)


@dataclass
class AmendmentPlan:
    """What an amending regulation says it does to its parent."""

    diubah: set[str] = field(default_factory=set)
    disisipkan: set[str] = field(default_factory=set)
    dihapus: set[str] = field(default_factory=set)

    @property
    def kosong(self) -> bool:
        return not (self.diubah or self.disisipkan or self.dihapus)


def amendment_plan(full_text: str) -> AmendmentPlan:
    """Read the numbered change instructions of an amending regulation."""
    t = " ".join((full_text or "").split())
    # Instructions live in the body; the Penjelasan repeats "Pasal N" freely.
    t = _CLOSING.split(t, maxsplit=1)[0]
    plan = AmendmentPlan()
    for m in _INSTRUCTION.finditer(t):
        sent = m.group(1)
        if not _VERB.search(sent):
            continue
        whole = _WHOLE_DELETE.match(sent)
        if whole:
            plan.dihapus.add(whole.group(1).upper())
            continue
        if _INSERTS_ARTICLES.search(sent):
            tail = _INSERT_LIST.search(sent)
            nums = re.findall(r"\b(\d+[A-Z]?)\b(?!\s*\()", tail.group(1) if tail else "")
            plan.disisipkan.update(n.upper() for n in nums)
            continue
        # Changed article(s): every "Pasal N" the sentence names, except the
        # neighbours in "Di antara Pasal 12 dan Pasal 13" when nothing is inserted.
        plan.diubah.update(n.upper() for n in _PASAL_NO.findall(sent))
    plan.diubah -= plan.disisipkan | plan.dihapus
    return plan


@dataclass
class Reference:
    key: str
    teks: str
    pasal_draft: list[str]
    relasi: str                     # dirujuk | diubah | dicabut
    status: str | None = None       # from the graph: berlaku | dicabut | diubah | …
    judul: str | None = None
    doc_id: str | None = None       # set when the cited regulation is in the KB
    pengganti: list[dict[str, Any]] = field(default_factory=list)


def _where(snippet: str, articles: list[dict[str, Any]]) -> list[str]:
    head = snippet[:60]
    return [str(a["number"]) for a in articles if head in " ".join((a.get("text") or "").split())]


def explicit_references(conn: sqlite3.Connection, full_text: str, title: str | None,
                        articles: list[dict[str, Any]], own_key: str | None = None,
                        ) -> list[Reference]:
    """Every regulation the draft cites, with its status and replacement."""
    from hero.graph.query import get_node, lineage

    text = " ".join((full_text or "").split())
    head = " ".join((title or "").split())
    refs: dict[str, Reference] = {}
    for m in _REF.finditer(text):
        raw = m.group(1)
        if _SELF.search(raw.split("Nomor")[0][-25:]):
            continue  # "Peraturan OJK ini" is the draft itself
        ref = canonical_ref(raw)
        if ref is None or ref.key == own_key:
            continue
        ctx = text[max(0, m.start() - 160): m.end() + 80]
        relasi = "dirujuk"
        if _REVOKES.search(text[m.end(): m.end() + 260]) and "dicabut" not in ctx[:150]:
            relasi = "dicabut"
        if ref.key not in refs:
            refs[ref.key] = Reference(ref.key, raw.strip(), _where(raw, articles), relasi)
        elif relasi == "dicabut":
            refs[ref.key].relasi = "dicabut"
    # The title names the parent of an amendment.
    if _AMENDS_TITLE.search(head):
        tail = re.split(_AMENDS_TITLE, head, maxsplit=1)[-1]
        ref = canonical_ref(tail)
        if ref and ref.key != own_key:
            r = refs.setdefault(ref.key, Reference(ref.key, tail[:160], [], "diubah"))
            r.relasi = "diubah"
    has_graph = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='graph_node'").fetchone()
    for r in refs.values():
        if not has_graph:
            break  # graph not built yet: references are listed without status
        node = get_node(conn, r.key)
        if node:
            r.status, r.judul, r.doc_id = node.get("status"), node.get("judul"), node.get("doc_id")
            if r.status == "dicabut":
                r.pengganti = [{"key": n["key"], "judul": n.get("judul"), "status": n.get("status")}
                               for n in lineage(conn, r.key).get("berlaku_terkini", [])]
    return sorted(refs.values(), key=lambda r: (r.relasi != "diubah", r.relasi != "dicabut", r.key))
