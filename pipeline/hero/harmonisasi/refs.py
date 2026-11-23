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

from hero.graph.identity import RegRef, canonical_ref

# "Peraturan Otoritas Jasa Keuangan Nomor 14 Tahun 2023", "POJK Nomor 1/POJK.05/2016",
# "Undang-Undang Nomor 4 Tahun 2023", "Surat Edaran OJK Nomor 25/SEOJK.05/2019".
_REF = re.compile(
    r"((?:Peraturan|Undang-Undang|Surat\s+Edaran|Keputusan|POJK|SEOJK|PADK|UU)\b"
    r"[^;:()]{0,140}?\bNomor\s+[\w./-]+(?:\s+Tahun\s+\d{4})?)",
    re.IGNORECASE)
_PENERBIT = re.compile(r"^\s*(?:Peraturan|Surat\s+Edaran|Keputusan)\s+((?:[A-Z][\w.]*\s+(?:dan\s+)?){1,5}?)Nomor\s+"
                       r"([\w./-]+)\s+Tahun\s+(\d{4})", re.IGNORECASE)
_JENIS = re.compile(r"\b(?:Peraturan|Undang-Undang|Surat\s+Edaran|Keputusan|POJK|SEOJK|PADK|UU)\b",
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
# Kata kunci relasi (Weekly #10, keputusan 3): dicari LEBIH DULU, sebelum kemiripan.
#   "… dicabut dan dinyatakan tidak berlaku", "… dinyatakan tidak berlaku", "… dicabut."
# Frasa kuat boleh melintasi butir daftar ("a. POJK X …; dan b. POJK Y …, dicabut dan …");
# frasa lemah harus di klausa yang sama. "dicabut." polos sengaja TIDAK dipakai: kalimat sanksi
# ("… izin usaha dicabut.") setelah rujukan akan terbaca sebagai pencabutan peraturan.
_REVOKES = re.compile(r"dicabut\s+dan\s+dinyatakan\s+tidak\s+berlaku", re.IGNORECASE)
_REVOKES_LEMAH = re.compile(r"^[^;]{0,200}?(?<!\.)\s(?:dinyatakan\s+tidak\s+berlaku)", re.IGNORECASE)
#   "Beberapa ketentuan dalam Peraturan … Nomor … (Lembaran Negara …) diubah sebagai berikut"
_AMENDS_AFTER = re.compile(r"^[^.;]{0,360}?\bdiubah\s+(?:sebagai\s+berikut|sehingga)", re.IGNORECASE)
#   "Ketentuan Pasal 10, Pasal 11, dan Pasal 12 ayat (2) [dalam] Peraturan …" tepat sebelum
#   rujukan yang dicabut → pencabutan SEBAGIAN (hanya pasal itu yang tidak berlaku).
_PARTIAL = re.compile(r"(?:Ketentuan\s+)?((?:Pasal\s+\d+[A-Z]?(?:\s+ayat\s+\(\d+\))?"
                      r"(?:\s*,\s*|\s+dan\s+|\s+sampai\s+dengan\s+)?)+)\s*(?:dalam|pada)?\s*$",
                      re.IGNORECASE)


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
    relasi: str                     # dirujuk | diubah | dicabut | dicabut_sebagian
    status: str | None = None       # from the graph: berlaku | dicabut | diubah | …
    judul: str | None = None
    doc_id: str | None = None       # set when the cited regulation is in the KB
    pengganti: list[dict[str, Any]] = field(default_factory=list)
    # Bukti kata kunci yang menetapkan relasi (dikutip apa adanya dari draft) — supaya
    # "kenapa dibandingkan dengan peraturan ini?" selalu bisa dijawab dengan teks.
    kata_kunci: str | None = None
    pasal_dicabut: list[str] = field(default_factory=list)   # hanya untuk dicabut_sebagian


RELASI_EKSPLISIT = ("diubah", "dicabut", "dicabut_sebagian")
_RANK = {"dirujuk": 0, "dicabut_sebagian": 1, "diubah": 2, "dicabut": 3}


def _where(snippet: str, articles: list[dict[str, Any]]) -> list[str]:
    head = snippet[:60]
    return [str(a["number"]) for a in articles if head in " ".join((a.get("text") or "").split())]


def _ref_penerbit(raw: str) -> RegRef | None:
    """Rujukan bernomor dari penerbit yang tak ada di tabel jenis kita ("Peraturan Badan Siber dan
    Sandi Negara Nomor 1 Tahun 2024" → BSSN|1|2024). Tanpa ini ia dibuang diam-diam dari
    daftar "peraturan yang disebut dalam draf"; kini tampil, dengan status tak diketahui."""
    m = _PENERBIT.match(" ".join(raw.split()))
    if not m:
        return None
    singkatan = "".join(w[0].upper() for w in m.group(1).split() if w.lower() != "dan")
    if len(singkatan) < 2:
        return None
    return RegRef(f"{singkatan}|{m.group(2)}|{m.group(3)}", singkatan, m.group(2), int(m.group(3)))


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
        ref = canonical_ref(raw) or _ref_penerbit(raw)
        if ref is None or ref.key == own_key:
            continue
        # _REF mulai dari "Peraturan" PERTAMA, jadi "Peraturan OJK ini mulai berlaku, Ketentuan
        # Pasal 5 Peraturan … Nomor 14" tertelan utuh; awalan sebelum jenis terakhir = konteks.
        awal = [x.start() for x in _JENIS.finditer(re.split(r"\bNomor\b", raw, maxsplit=1)[0])]
        before = text[max(0, m.start() - 200): m.start()] + raw[:awal[-1] if awal else 0]
        after = text[m.end(): m.end() + 360]
        # Klausa tempat rujukan berada: "dicabut" di klausa yang sama SEBELUM rujukan
        # ("pengganti POJK X yang telah dicabut …") bukan pernyataan pencabutan oleh draft.
        klausa = re.split(r"[;:]|\.\s", before)[-1]
        relasi, bukti, pasal_dicabut = "dirujuk", None, []
        rev = _REVOKES.search(after[:260]) or _REVOKES_LEMAH.search(re.split(r"\.\s+(?=[A-Z])", after)[0])
        if rev and "dicabut" not in klausa.lower():
            part = _PARTIAL.search(before)
            if part:
                relasi = "dicabut_sebagian"
                pasal_dicabut = sorted({p.upper() for p in _PASAL_NO.findall(part.group(1))},
                                       key=lambda x: (len(x), x))
                bukti = f"{part.group(0).strip()} {raw.strip()} … {rev.group(0).strip(' .;')}"
            else:
                relasi, bukti = "dicabut", f"{raw.strip()} … {rev.group(0).strip(' .;')}"
        elif _AMENDS_AFTER.search(after):
            relasi = "diubah"
            bukti = f"{raw.strip()} … {_AMENDS_AFTER.search(after).group(0)[-40:].strip()}"
        r = refs.get(ref.key)
        if r is None:
            refs[ref.key] = Reference(ref.key, raw.strip(), _where(raw, articles), relasi,
                                      kata_kunci=bukti, pasal_dicabut=pasal_dicabut)
        elif _RANK[relasi] > _RANK[r.relasi]:
            r.relasi, r.kata_kunci, r.pasal_dicabut = relasi, bukti, pasal_dicabut
    # The title names the parent of an amendment.
    if _AMENDS_TITLE.search(head):
        tail = re.split(_AMENDS_TITLE, head, maxsplit=1)[-1]
        ref = canonical_ref(tail)
        if ref and ref.key != own_key:
            r = refs.setdefault(ref.key, Reference(ref.key, tail[:160], [], "diubah"))
            r.relasi = "diubah"
            r.kata_kunci = f"judul: {_AMENDS_TITLE.search(head).group(0)} {tail[:120].strip()}"
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
    urut = {"diubah": 0, "dicabut": 1, "dicabut_sebagian": 2, "dirujuk": 3}
    return sorted(refs.values(), key=lambda r: (urut[r.relasi], r.key))
