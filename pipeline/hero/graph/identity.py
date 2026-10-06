"""Canonical identity for a regulation mentioned anywhere in the corpus.

The same regulation is written many ways:

    "POJK Nomor 11/POJK.03 Tahun 2022 tentang ..."           (JDIH Landasan Hukum)
    "Peraturan Otoritas Jasa Keuangan Nomor 11/POJK.03/2022"  (Mengingat clause)
    "11/POJK.03/2022"                                         (inventory.number)

A graph is only as good as its node identity: if these become three nodes,
every traversal silently stops at the first hop. ``canonical_ref`` collapses
them to one key, ``POJK|11|2022``.

Why not reuse ``hero.inventory.reg_key``? It keeps the *first* integer of the
number, which is right for OJK (``11/POJK.03/2022`` → 11) but wrong for Bank
Indonesia (``7/1/PBI/2005`` → 7 is the year-series, 1 is the number: 42
different PBIs collapse onto ``PBI|7|2005``) and gives nothing for Bapepam
(``KEP-208/BL/2012``). That is Temuan 4 in docs/DATA_ANALYST_FASE1.md.
``reg_key`` is left untouched because status reconciliation depends on it;
the graph uses this stricter identity instead.

OJK regulation numbers are unique per type and year (the sector code
``.03`` is a suffix, not part of the sequence) — verified on the JDIH
register, where no two POJK share number and year.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Type detected from the words around the number. Order: specific first,
# because "Peraturan Otoritas Jasa Keuangan" is a prefix of the PADK phrase.
_PHRASES: tuple[tuple[str, str], ...] = (
    (r"undang[- ]undang dasar", "UUD"),
    (r"peraturan anggota dewan komisioner|\bpadk\b", "PADK"),
    (r"surat edaran dewan komisioner|\bsedk\b", "SEDK"),
    (r"keputusan dewan komisioner|\bkdk\b|\bkepdk\b", "KDK"),
    (r"peraturan dewan komisioner|\bpdk\b", "PDK"),
    (r"surat edaran otoritas jasa keuangan|\bseojk\b", "SEOJK"),
    (r"peraturan otoritas jasa keuangan|\bpojk\b", "POJK"),
    (r"surat edaran bank indonesia|\bsebi\b", "SEBI"),
    (r"peraturan anggota dewan gubernur|\bpadg\b", "PADG"),
    (r"peraturan bank indonesia|\bpbi\b", "PBI"),
    (r"surat keputusan direksi bank indonesia|keputusan direksi", "SKDIR"),
    (r"peraturan menteri keuangan|\bpmk\b", "PMK"),
    (r"keputusan menteri keuangan|\bkmk\b", "KMK"),
    (r"peraturan pemerintah pengganti undang|\bperpu\b", "PERPU"),
    (r"peraturan pemerintah|\bpp\b", "PP"),
    (r"peraturan presiden|\bperpres\b", "PERPRES"),
    (r"keputusan presiden|\bkeppres\b", "KEPPRES"),
    (r"badan pengawas pasar modal|bapepam", "BAPEPAM"),
    (r"undang[- ]undang|\buu\b", "UU"),
)
_PHRASE_RX = tuple((re.compile(p, re.I), t) for p, t in _PHRASES)

# Codes that appear *inside* a number ("11/POJK.03/2022") — more reliable
# than the surrounding words, which are sometimes abbreviated or missing.
_CODE_TYPES = {
    "POJK": "POJK", "SEOJK": "SEOJK", "PADK": "PADK", "PADKINT": "PADK", "PDK": "PDK",
    "SEDK": "SEDK", "KDK": "KDK", "PMK": "PMK", "KMK": "KMK", "PBI": "PBI",
    "PADG": "PADG", "SPEOJK": "SPEOJK",
}

# The lookbehind matters: without it "8/5/PBI/2006" matches here as
# "5/PBI/2006" and the BI series number is lost — the very bug in reg_key.
# "[/.]" and "/?" absorb real source typos: "10.SEOJK.03/2014", "59/POJK/.04/2016".
_OJK_SLASH = re.compile(       # 11/POJK.03/2022 · 3 /SEOJK.03/2023 · 1/PMK.010/2019
    r"(?<![\d/])(\d+)\s*[/.]\s*([A-Z]{2,8})\s*/?\s*(?:\.\s*\d+)?\s*/\s*(\d{4})(?!\d)", re.I)
_OJK_SLASH_TAHUN = re.compile(  # 11/POJK.03 Tahun 2022  (JDIH Landasan style)
    r"(?<![\d/])(\d+)\s*/\s*([A-Z]{2,8})(?:\.\s*\d+)?\s+Tahun\s+(\d{4})", re.I)
_BI = re.compile(              # 8/5/PBI/2006 · 13/15/DPbS · 32/52/KEP/DIR
    r"(\d+)\s*/\s*(\d+)\s*/\s*([A-Z]{2,8}(?:\s*/\s*DIR)?)(?:\s*/\s*(\d{4}))?", re.I)
_KEP = re.compile(r"Kep\s*-?\s*(\d+)\s*/\s*([A-Z]{1,4})\s*/\s*(\d{4})", re.I)
_NOMOR_TAHUN = re.compile(r"Nomor\s*:?\s*(\d+)[A-Z]?\s+Tahun\s+(\d{4})", re.I)
_BARE_TAHUN = re.compile(r"^\s*(?:[A-Z]{2,8}\s+)?(\d+)\s+Tahun\s+(\d{4})\s*$", re.I)
_UUD = re.compile(r"undang[- ]undang dasar|\buud\b", re.I)


@dataclass(frozen=True)
class RegRef:
    key: str            # "POJK|11|2022"
    jenis: str          # "POJK"
    nomor: str          # "11" or "8/5" or "13/15/DPBS"
    tahun: int | None


def _phrase_type(text: str) -> str | None:
    for rx, t in _PHRASE_RX:
        if rx.search(text):
            return t
    return None


# Department codes that only exist in the pre-1999 numbering series.
_BI_OLD_CODES = {"UPPB", "UPBB"}


def _bi_year(seq: str, code: str | None = None) -> int:
    """Year of a Bank Indonesia number from its leading sequence.

    New series (from 1999): PBI 1/… = 1999. Old series used the bank's own
    year count, where 31 = 1998 (SK Direksi 31/147/KEP/DIR, 12 Nov 1998).
    "1998 + 31" gave 2029 — a year that has not happened.
    """
    from datetime import date

    n = int(seq)
    if code and code.upper() in _BI_OLD_CODES:
        return 1967 + n
    return 1998 + n if 1998 + n <= date.today().year + 1 else 1967 + n


def _ref(jenis: str, nomor: str, tahun: int | None) -> RegRef:
    nomor = re.sub(r"\s+", "", nomor).upper()
    return RegRef(f"{jenis}|{nomor}|{tahun if tahun else ''}", jenis, nomor, tahun)


def canonical_ref(text: str | None, *, type_hint: str | None = None) -> RegRef | None:
    """Parse a free-text reference into a canonical identity, or None.

    ``type_hint`` is used when the text is just a number (inventory rows
    store ``doc_type`` and ``number`` separately). None means "could not
    identify" — the caller keeps the raw text rather than guessing.
    """
    if not text:
        return None
    t = " ".join(text.split())
    # Ignore the "tentang ..." tail: titles often contain other numbers.
    head = re.split(r"\btentang\b", t, maxsplit=1, flags=re.I)[0]
    phrase = _phrase_type(head)
    hint = (type_hint or "").upper() or None

    if _UUD.search(head):
        return _ref("UUD", "1945", 1945)

    m = _KEP.search(head)
    if m:
        return _ref("BAPEPAM", f"KEP-{m.group(1)}/{m.group(2)}", int(m.group(3)))

    m = _BI.search(head)
    if m:
        code = re.sub(r"\s+", "", m.group(3)).upper()
        year = int(m.group(4)) if m.group(4) else None
        if code == "PBI":
            return _ref("PBI", f"{m.group(1)}/{m.group(2)}", year or _bi_year(m.group(1)))
        if code == "PADG":
            return _ref("PADG", f"{m.group(1)}/{m.group(2)}", year or _bi_year(m.group(1)))
        if code.endswith("KEP/DIR"):
            return _ref("SKDIR", f"{m.group(1)}/{m.group(2)}/KEP/DIR", year)
        # Surat Edaran BI: the department code is part of the identity.
        jenis = "SEBI" if (phrase in (None, "SEBI") or hint == "SEBI") else (phrase or hint)
        return _ref(jenis, f"{m.group(1)}/{m.group(2)}/{code}", year or _bi_year(m.group(1), code))

    for rx in (_OJK_SLASH, _OJK_SLASH_TAHUN):
        m = rx.search(head)
        if m and m.group(2).upper() in _CODE_TYPES:
            return _ref(_CODE_TYPES[m.group(2).upper()], m.group(1), int(m.group(3)))

    jenis = phrase or hint
    m = _NOMOR_TAHUN.search(head) or _BARE_TAHUN.search(head)
    if m and jenis:
        return _ref(jenis, m.group(1), int(m.group(2)))
    return None


def ref_for_record(doc_type: str | None, number: str | None, year: int | None) -> RegRef | None:
    """Identity for an inventory/document row (type, number, year stored apart)."""
    if not number:
        return None
    ref = canonical_ref(number, type_hint=doc_type)
    if ref:
        return ref
    ref = canonical_ref(f"Nomor {number} Tahun {year}", type_hint=doc_type) if year else None
    return ref
