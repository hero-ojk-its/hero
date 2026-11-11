"""Analisa v2 (URD 3.3, mode Deterministik): ringkasan terstruktur berbasis pasal.

Why a v2 next to ``extract/summary.py`` (v1), measured on the 91 production
documents before writing this:

* v1 picks sentences by word frequency over the whole text. 70% of its
  summaries contain bare ayat markers "(1) … (2) …" with no Pasal to anchor
  them, and a regulation whose substance sits in its Lampiran (10 PADK)
  gets a summary of the one sentence that points at the Lampiran.
* 18% of v1 Key Takeaways carry no Pasal reference, 14% stop exactly where
  the list they introduce begins ("… untuk jabatan: a."), 4% are
  definitions ("Cuti Wajib adalah …" read as an obligation because of the
  capitalised term), and 7% come from the Penjelasan, not the law itself.

v2 works from the parsed Pasal/ayat of the batang tubuh instead of raw
text, so every point is a whole ayat — its list included — with an exact
citation, and the short summary is assembled from those points by a fixed
template. Nothing here calls a model; it is the fallback that must always
work (URD 3.1) and the fact base the AI-Assisted mode is allowed to use.

Every statement carries the Pasal it came from, because a regulator must
be able to check a summary against the law in seconds.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from hero.extract.structure import DIKTUM_ORDINAL

VERSION = "v2.5"

# Lower-case only, matched case-sensitively: Indonesian legislative drafting
# writes obligations in lower case ("wajib menyampaikan") and defined terms in
# Title Case ("Cuti Wajib", "Wajib Pajak"). Matching case-insensitively is
# what made v1 read definitions as obligations.
# Kata kerja tugas Keputusan. Satu daftar: dipakai penanda, pengecualian filter definisi,
# dan pencari klausa di ringkasan.
_KERJA_TUGAS = ("membentuk|menugaskan|menunjuk|mengangkat|menyusun|melaksanakan|melakukan|"
                "menyelenggarakan|mengoordinasikan|menetapkan")
_TUGAS_AWAL = re.compile(rf"^(?i:{_KERJA_TUGAS})\b")
_TUGAS_CARI = rf"bertugas|bertanggung jawab|{_KERJA_TUGAS}"

MARKERS: tuple[tuple[str, str, int], ...] = (
    # (regex, category, priority — lower = more consequential)
    (r"\bdikenai sanksi\b|\bdikenakan sanksi\b|\bsanksi administratif\b", "Sanksi", 0),
    (r"\bdilarang\b|\btidak diperkenankan\b|\btidak boleh\b", "Larangan", 1),
    (r"\bwajib memperoleh (izin|persetujuan)\b|\bwajib mendapatkan (izin|persetujuan)\b", "Perizinan", 2),
    (r"\bwajib menyampaikan\b|\bwajib melaporkan\b|\bmenyampaikan laporan\b", "Pelaporan", 2),
    (r"\bwajib\b|\bharus\b", "Kewajiban", 3),
    # Keputusan menugaskan, bukan mewajibkan. Kata kerja tugas hanya dihitung di AWAL unit
    # (diktum: "Membentuk Tim …") atau sebagai "bertugas/mempunyai tugas" — "melakukan" di
    # tengah kalimat terlalu umum dan akan menangkap hampir semua kalimat.
    (rf"\bbertugas\b|\bmempunyai tugas\b|\bbertanggung jawab\b|^(?i:{_KERJA_TUGAS})\b", "Tugas", 3),
    (r"\bpaling lambat\b|\bpaling lama\b|\bdalam jangka waktu\b", "Batas Waktu", 4),
    (r"\bdicabut dan dinyatakan tidak berlaku\b", "Pencabutan", 5),
    (r"\bmulai berlaku pada\b|\bberlaku sejak\b", "Masa Berlaku", 6),
    # Official English translations (OJK and BI publish both).
    (r"\bshall be (imposed|subject to) (an? )?(administrative )?sanction", "Sanksi", 0),
    (r"\bshall not\b|\bis prohibited\b|\bare prohibited\b", "Larangan", 1),
    (r"\bshall submit\b|\bshall report\b", "Pelaporan", 2),
    (r"\bshall\b|\bmust\b", "Kewajiban", 3),
)
_MARKERS = tuple((re.compile(rx), cat, pr) for rx, cat, pr in MARKERS)
_DEFINITION = re.compile(r"\byang dimaksud dengan\b|\byang selanjutnya (disebut|disingkat)\b|^\s*[A-Z][^.;]{0,80}\badalah\b|"
                         r"\bhereinafter referred to as\b|\bshall mean\b")
_AYAT = re.compile(r"(?:^|\n|\s)\((\d{1,2})\)\s")
_SUBJECT = re.compile(r"^\s*(?:Setiap |Dalam hal )?([A-Z][A-Za-z/\-]*(?: (?:[A-Z][A-Za-z/\-]*|atau|dan|dan/atau)){0,5})"
                      r"\s+(?:yang [^,]{0,80},?\s*)?(wajib|dilarang|harus|dapat)\b")
# Label = kata yang DIPAKAI dokumen. Dulu "teguran tertulis" dan "peringatan tertulis" dilebur
# menjadi "teguran/peringatan tertulis", sehingga ringkasan menyebut bentuk sanksi yang tidak ada
# di PDF-nya (temuan QA #2). Urutan = urutan tampil.
_SANCTION_KINDS = (("teguran tertulis", "teguran tertulis"),
                   ("peringatan tertulis", "peringatan tertulis"),
                   (r"\bdenda\b", "denda"),
                   ("pembatasan kegiatan", "pembatasan kegiatan usaha"),
                   ("pembekuan", "pembekuan kegiatan usaha"),
                   ("pencabutan izin", "pencabutan izin usaha"),
                   # Bentuk yang lazim di daftar huruf pasal sanksi dan dulu tak pernah terangkum.
                   ("larangan (?:untuk )?menerbitkan produk", "larangan menerbitkan produk baru"),
                   ("larangan melakukan ekspansi|larangan ekspansi", "larangan ekspansi kegiatan usaha"),
                   ("larangan melakukan kegiatan usaha baru", "larangan kegiatan usaha baru"),
                   ("larangan sebagai pihak utama", "larangan sebagai pihak utama"),
                   ("penurunan penilaian faktor tata kelola", "penurunan penilaian faktor tata kelola"),
                   ("penurunan tingkat kesehatan", "penurunan tingkat kesehatan"))
_LAMPIRAN_REF = re.compile(r"tercantum dalam[:\s]+(?:[a-z]\.\s*)?Lampiran", re.I)
# Section headings the structure parser sometimes leaves at the end of an ayat.
_TRAILING_HEADING = re.compile(r"\s+(Paragraf \d+|Bagian (Kesatu|Kedua|Ketiga|Keempat|Kelima|Keenam|"
                               r"Ketujuh|Kedelapan|Kesembilan|Kesepuluh)|BAB [IVXLC]+)\b.*$", re.S)
# Tempered: the span may not contain " ini " — that is the regulation
# referring to itself ("Pada saat Peraturan OJK ini mulai berlaku, …").
_REVOKED_NAME = re.compile(r"((?:Peraturan|Surat Edaran|Keputusan)(?:(?!\bini\b)[^;]){0,120}?Nomor\s+[\w./-]+"
                           r"(?:\s+Tahun\s+\d{4})?\s+tentang\s+[^(;]{5,160}?)(?=\s*\(|;|,? dicabut|$)")
MAX_POINT_CHARS = 900


@dataclass
class Point:
    id: str                 # "F7" — the handle the AI mode must cite
    kategori: str
    pasal: str              # "Pasal 4 ayat (1)"
    halaman: int | None
    teks: str
    prioritas: int
    subjek: str | None = None
    terpotong: bool = False


@dataclass
class AnalysisV2:
    doc_id: str
    versi: str
    identitas: dict[str, Any]
    kerangka: list[dict[str, Any]]
    subjek_diatur: list[dict[str, Any]]
    poin: list[Point]
    sanksi: list[str]
    dasar_hukum: list[str]
    lampiran: dict[str, Any]
    ringkasan: list[dict[str, Any]]          # [{"kalimat": str, "rujukan": [...], "fakta": [...]}]
    metrik: dict[str, Any] = field(default_factory=dict)

    def ringkasan_teks(self) -> str:
        return " ".join(s["kalimat"] for s in self.ringkasan)

    def poin_utama(self, n: int | None = None) -> list[Point]:
        """Points ordered for display: round-robin across categories in order of
        legal weight, most specific point of each category first — so near-identical
        "dikenai sanksi administratif …" points never crowd out other categories.
        ``n=None`` returns every point; a number caps the list (AI facts, evaluation)."""
        top = [s["subjek"] for s in self.subjek_diatur[:3]]
        by_cat: dict[str, list[Point]] = {}
        for p in _rank_for_summary(self.poin, top):
            by_cat.setdefault(p.kategori, []).append(p)
        order = sorted(by_cat, key=lambda c: min(p.prioritas for p in by_cat[c]))
        limit = len(self.poin) if n is None else n
        out: list[Point] = []
        while len(out) < limit and any(by_cat.values()):
            for c in order:
                if by_cat[c] and len(out) < limit:
                    out.append(by_cat[c].pop(0))
        return out

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ringkasan_teks"] = self.ringkasan_teks()
        d["poin_utama"] = [p.id for p in self.poin_utama()]
        return d


def _pasal_order(ref: str) -> tuple[int, int]:
    diktum = re.search(r"Diktum KE(\w+)", ref)
    if diktum:
        return DIKTUM_ORDINAL.get(diktum.group(1), 0), 0
    nums = [int(x) for x in re.findall(r"\d+", ref)[:2]] + [0, 0]
    return nums[0], nums[1]


# ---------------------------------------------------------------------------
# Units: one ayat (or a whole Pasal without ayat) — lists stay attached
# ---------------------------------------------------------------------------
def is_diktum(number: Any) -> bool:
    num = str(number)
    return num.startswith("KE") and num[2:] in DIKTUM_ORDINAL


def unit_ref(number: str, ayat: int | None = None) -> str:
    """Rujukan unit: "Pasal 4 ayat (2)", "Diktum KESATU", atau "Bagian II" (Surat Edaran)."""
    num = str(number)
    if re.fullmatch(r"\d+[A-Z]?", num):
        base = f"Pasal {num}"
    elif is_diktum(num):
        base = f"Diktum {num}"
    else:
        base = f"Bagian {num}"
    return base + (f" ayat ({ayat})" if ayat else "")


def split_ayat(text: str) -> list[tuple[int | None, str]]:
    """Split a Pasal into its ayat, accepting "(n)" only as the next number.

    Same rule as the structure parser: "(2)" opens an ayat only right after
    ayat (1), so cross-references ("sebagaimana dimaksud pada ayat (1)")
    never split a sentence. Enumerations (a., b., 1., 2.) stay inside their
    ayat — that is what makes v2 points complete where v1's were cut off.
    """
    text = text.strip()
    cuts: list[tuple[int, int]] = []
    expected = 1
    for m in _AYAT.finditer(text):
        n = int(m.group(1))
        before = text[max(0, m.start() - 14):m.start() + 1].lower()
        # "Pasal 4 ayat (2)", "dan/atau (2)" are cross-references, not ayat openers.
        if re.search(r"(ayat|angka|huruf|dan|atau|dengan|hingga)\s*$", before.strip()):
            continue
        if n == expected:
            cuts.append((n, m.start()))
            expected += 1
    if not cuts:
        return [(None, text)]
    out = []
    head = text[:cuts[0][1]].strip()
    if len(head) > 40:               # a lead-in sentence before ayat (1)
        out.append((None, head))
    for i, (n, start) in enumerate(cuts):
        end = cuts[i + 1][1] if i + 1 < len(cuts) else len(text)
        body = re.sub(r"^\s*\(\d{1,2}\)\s*", "", text[start:end]).strip()
        out.append((n, body))
    return out


def _clean(s: str) -> str:
    return _TRAILING_HEADING.sub("", re.sub(r"\s+", " ", s).strip()).strip()


def classify_unit(text: str) -> tuple[str, int] | None:
    # "Membentuk Tim … yang selanjutnya disebut Tim" adalah norma, bukan definisi.
    if _DEFINITION.search(text[:300]) and not _TUGAS_AWAL.match(text):
        return None
    for rx, cat, pr in _MARKERS:
        if rx.search(text):
            return cat, pr
    return None


def subject_of(text: str) -> str | None:
    m = _SUBJECT.match(text)
    if not m:
        return None
    subj = m.group(1).strip()
    if subj.split()[0] in {"Dalam", "Selain", "Ketentuan", "Pada", "Untuk", "Apabila", "Jika"}:
        return None
    return subj if len(subj) <= 60 else None


def units_of(art: dict[str, Any]) -> list[tuple[int | None, str]]:
    """Ayat of a Pasal: the structure parser's split when available (it already
    handles cross-references correctly), otherwise our own fallback split."""
    ayat = art.get("ayat") or []
    if ayat:
        return [(int(a["number"]) if str(a.get("number", "")).isdigit() else None, a.get("text") or "")
                for a in ayat]
    return split_ayat(art.get("text") or "")


_NUMBERED = re.compile(r"(?:^|\s)(\d{1,2})\.\s+(?=[A-Z])")


def section_units(sections: list[dict[str, Any]], full_text: str | None) -> list[dict[str, Any]]:
    """Surat Edaran have no Pasal: use each Roman-numeral section, split into
    its numbered points ("1. …", "2. …"), as pseudo-articles.

    Without this, 18 Surat Edaran produced no Key Takeaways at all in v2 —
    a regression against v1, which read the raw text.
    """
    from hero.vector.chunking import section_bodies

    out = []
    for label, page, body in section_bodies(sections or [], full_text or ""):
        cuts = [(int(m.group(1)), m.start()) for m in _NUMBERED.finditer(body)]
        expected, keep = 1, []
        for n, pos in cuts:                  # numbered points must count up from 1
            if n == expected:
                keep.append((n, pos))
                expected += 1
        if not keep:
            out.append({"number": label, "page": page, "text": body, "ayat": []})
            continue
        for i, (n, pos) in enumerate(keep):
            end = keep[i + 1][1] if i + 1 < len(keep) else len(body)
            out.append({"number": f"{label} angka {n}", "page": page,
                        "text": re.sub(r"^\s*\d{1,2}\.\s+", "", body[pos:end]), "ayat": []})
    return out


NO_PASAL = "Teks dokumen (pasal tidak terbaca)"


def text_units(full_text: str | None) -> list[dict[str, Any]]:
    """Last resort when neither Pasal nor sections were parsed: sentences of
    the body (before the closing formula). Points from here are labelled
    ``NO_PASAL`` — an honest "we could not tell which Pasal", never a guess."""
    if not full_text:
        return []
    low = full_text.lower()
    end = low.find("ditetapkan di")
    body = re.sub(r"\s+", " ", full_text[: end if end > 0 else len(full_text)])
    sents = re.split(r"(?<=[.;])\s+(?=[A-Z(])", body)
    return [{"number": NO_PASAL, "page": None, "text": x, "ayat": []} for x in sents if len(x) > 30]


MIN_POIN = 3        # FR-ANL-05: minimal 3 poin kunci per dokumen
MAKS_POIN_CADANGAN = 6


def extract_points(articles: list[dict[str, Any]]) -> list[Point]:
    points: list[Point] = []
    seen: set[str] = set()
    sisa: list[tuple[dict[str, Any], int | None, str]] = []      # unit tanpa penanda norma

    def tambah(art: dict[str, Any], ayat: int | None, teks: str, kategori: str, prioritas: int) -> None:
        key = teks[:160].lower()
        if key in seen:
            return
        seen.add(key)
        cut = len(teks) > MAX_POINT_CHARS
        num = str(art["number"])
        ref = NO_PASAL if num == NO_PASAL else unit_ref(num, ayat)
        points.append(Point(id=f"F{len(points) + 1}", kategori=kategori, pasal=ref,
                            halaman=art.get("page"), prioritas=prioritas, subjek=subject_of(teks),
                            teks=(teks[:MAX_POINT_CHARS].rsplit(" ", 1)[0] + " …") if cut else teks,
                            terpotong=cut))

    for art in articles:
        for ayat, body in units_of(art):
            teks = _clean(body)
            if len(teks) < 25:
                continue
            got = classify_unit(teks)
            if got:
                tambah(art, ayat, teks, *got)
            elif str(art["number"]) != NO_PASAL and not _DEFINITION.search(teks[:300]):
                sisa.append((art, ayat, teks))
    # Setiap diktum Keputusan adalah ketetapan tersendiri. Dokumen lain yang normanya tak
    # memakai kata kunci kita juga tidak boleh berakhir dengan satu-dua poin: isi unitnya
    # tetap ditampilkan apa adanya, berlabel "Ketentuan", daripada dokumennya tampak kosong.
    if len(points) < MIN_POIN or any(is_diktum(a["number"]) for a in articles):
        for art, ayat, teks in sisa[:MAKS_POIN_CADANGAN]:
            tambah(art, ayat, teks, "Ketentuan", 7)
    return points


# ---------------------------------------------------------------------------
# Framework, lampiran, sanctions
# ---------------------------------------------------------------------------
def _awal_kata(teks: str, n: int = 9) -> str:
    kata = teks.rstrip(" .;:").split()
    return " ".join(kata[:n]) + (" …" if len(kata) > n else "")


def framework(structure: dict[str, Any], articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """BAB outline with the Pasal range each BAB covers."""
    diktum = [a for a in articles if is_diktum(a["number"])]
    if diktum and not any(str(a["number"]).isdigit() for a in articles):
        # Keputusan: kerangkanya adalah daftar diktum, dengan kalimat pembukanya sebagai "judul".
        return [{"bab": str(a["number"]), "judul": _awal_kata(_clean(a["text"])),
                 "pasal": unit_ref(a["number"])} for a in diktum]
    ranges: dict[str, list[int]] = {}
    for a in articles:
        if a.get("bab") and str(a["number"]).isdigit():
            ranges.setdefault(a["bab"], []).append(int(a["number"]))
    out = []
    for b in structure.get("babs") or []:
        label = f"BAB {b.get('number')} — {b.get('title')}"
        nums = ranges.get(label) or next((v for k, v in ranges.items() if k.startswith(f"BAB {b.get('number')} ")), [])
        if not nums:
            # A BAB with no batang-tubuh Pasal belongs to the Lampiran (the
            # structure parser sees "BAB" headings there too). Leaving it in
            # made a 3-Pasal PADK read as "4 bab".
            continue
        out.append({"bab": f"BAB {b.get('number')}", "judul": b.get("title"),
                    "pasal": f"Pasal {min(nums)}" + (f"–{max(nums)}" if max(nums) != min(nums) else "")})
    return out


_LAMP_HEADING = re.compile(r"^(BAB\s+[IVXLC]+\b.*|[IVXLC]{1,5}\.\s+[A-Z].*|[A-H]\.\s+[A-Z].*)$")
_SIGNATURE = re.compile(r"KEPALA|KETUA|DEWAN KOMISIONER|REPUBLIK INDONESIA|DITETAPKAN|SALINAN|"
                        r"DIREKTUR|DEPUTI|ttd|NOMOR\s|TENTANG$", re.I)
# The Lampiran's own title. These form-words are how OJK actually names an
# attachment, so matching them states a fact instead of guessing which line
# "looks like" a title (invarian 6).
_LAMP_TITLE = re.compile(r"^(PEDOMAN|TATA\s+CARA|FORMAT|FORMULIR|MATRIKS|DAFTAR|CONTOH|"
                         r"PETUNJUK|KERTAS\s+KERJA|STANDAR|TABEL|RINCIAN|KLASIFIKASI)\b",
                         re.I)
# Fallback only: a Lampiran that is one flattened table has no numbered
# headings at all — its sections are bare capitals ("PROSPEK USAHA DEBITUR").
# Used strictly when _LAMP_HEADING found nothing, so documents that already
# parse cleanly keep the headings they have.
_LAMP_CAPS = re.compile(r"^[A-Z][A-Z0-9\s/().,&'-]{5,}$")
_LAMP_SKIP = re.compile(r"^(LAMPIRAN|PERATURAN|SURAT\s+EDARAN|OTORITAS\s+JASA\s+KEUANGAN)\b",
                        re.I)
# "DAFTAR ISI" names the table of contents, not the attachment, and a dotted
# leader line is that table's rows. Neither is a title.
_LAMP_NOT_TITLE = re.compile(r"^DAFTAR\s+ISI\b|\.{4,}", re.I)
# How much of a Lampiran section's own text to quote (T3, Fase 2): enough
# for one real sentence, not the whole section.
_LAMPIRAN_EXCERPT_MAX = 260


def _judul_lampiran_wajar(line: str) -> bool:
    """A Lampiran title is printed in capitals; running prose is not a title.

    Without this, "Contoh: utang pajak, liabilitas imbal kerja dan ..." — an
    example sentence in the middle of an attachment — was presented as the
    attachment's title. An empty field is the honest answer (invarian 6).
    """
    huruf = [c for c in line if c.isalpha()]
    if len(huruf) < 4:
        return False
    return sum(c.isupper() for c in huruf) / len(huruf) >= 0.7


def _lampiran_body_lines(text: str) -> list[str]:
    """Lines worth quoting: no signature block, no "DAFTAR ISI"/dotted leaders."""
    out = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line and not _SIGNATURE.search(line) and not _LAMP_NOT_TITLE.search(line):
            out.append(line)
    return out


def lampiran_section_excerpts(tail: str, headings: list[str], limit: int = 6) -> list[dict[str, str]]:
    """First real sentence under each Lampiran heading, not just its title.

    ``headings`` are the exact lines ``lampiran_profile`` already located in
    ``tail``; this reads what follows each one, up to the next heading (or
    the end), and keeps roughly one sentence of it. A heading followed by
    nothing substantive (only noise, or nothing before the next heading) is
    left out rather than given a fabricated summary (invarian 6) — that is
    still a true fact about the document, just a narrower one.
    """
    out: list[dict[str, str]] = []
    cursor = 0
    for i, heading in enumerate(headings[:limit]):
        pos = tail.find(heading, cursor)
        if pos < 0:
            continue
        body_start = pos + len(heading)
        end = len(tail)
        for other in headings[i + 1:]:
            p = tail.find(other, body_start)
            if p >= 0:
                end = min(end, p)
        blob = " ".join(_lampiran_body_lines(tail[body_start:end]))
        cursor = body_start
        if not blob:
            continue
        m = re.match(r".{0,%d}?[.;:]\s" % _LAMPIRAN_EXCERPT_MAX, blob)
        if m:
            excerpt = m.group(0).strip()
        else:
            excerpt = blob[:_LAMPIRAN_EXCERPT_MAX].rstrip()
            if len(blob) > _LAMPIRAN_EXCERPT_MAX:
                excerpt += "…"
        out.append({"judul": heading, "ringkasan": excerpt})
    return out


def lampiran_profile(full_text: str | None, articles: list[dict[str, Any]]) -> dict[str, Any]:
    """Is the substance in the Lampiran? If so, what does the Lampiran contain?

    Ten PADK in the corpus have ≤6 Pasal that only say "sebagaimana tercantum
    dalam Lampiran". For those, a summary of the batang tubuh is empty; the
    honest output is to say so and list the Lampiran's section headings.
    Only numbered headings (BAB I, II., A.) count — an all-caps heuristic
    picked up the signature block ("KEPALA EKSEKUTIF PENGAWAS …").
    """
    refs = [a for a in articles if _LAMPIRAN_REF.search(a["text"] or "")]
    heavy = bool(refs) and len(articles) <= (12 if any(is_diktum(a["number"]) for a in articles) else 6)
    headings: list[str] = []
    judul: str | None = None
    if heavy and full_text:
        low = full_text.lower()
        close = low.find("ditetapkan di")
        start = low.find("lampiran", close if close >= 0 else 0)
        tail = full_text[start if start >= 0 else 0:]
        caps: list[str] = []
        sisa = 0                      # continuation lines still allowed for the title
        for line in tail.splitlines():
            line = _clean(line)
            if not (6 <= len(line) <= 110) or _SIGNATURE.search(line):
                continue
            if judul is None and _LAMP_TITLE.match(line) \
                    and not _LAMP_NOT_TITLE.search(line) \
                    and _judul_lampiran_wajar(line):
                # The title wraps: the PDF prints "PEDOMAN" on its own line and
                # the subject on the next. A bare form-word is not an answer, so
                # keep collecting the continuation lines.
                judul = line
                sisa = 0 if len(line) > 25 else 2
            elif sisa > 0 and _LAMP_CAPS.match(line) and not _LAMP_SKIP.match(line) \
                    and not _LAMP_NOT_TITLE.search(line):
                judul = f"{judul} {line}".strip()
                sisa = 0 if len(judul) > 40 else sisa - 1
            if _LAMP_HEADING.match(line):
                if line not in headings:
                    headings.append(line)
                if len(headings) >= 10:
                    break
            elif (len(caps) < 10 and line not in caps
                    and not _LAMP_SKIP.match(line) and _LAMP_CAPS.match(line)
                    and line != judul):
                caps.append(line)
        if not headings:
            headings = caps
    isi_bagian = lampiran_section_excerpts(tail, headings) if heavy and full_text and headings else []
    return {"berat_lampiran": heavy, "pasal_rujukan": [f"Pasal {a['number']}" for a in refs][:3],
            "judul_bagian": headings, "judul_lampiran": judul, "isi_bagian": isi_bagian}


def sanctions(points: list[Point]) -> list[str]:
    blob = " ".join(p.teks.lower() for p in points if p.kategori == "Sanksi")
    return [label for rx, label in _SANCTION_KINDS if re.search(rx, blob)]


# ---------------------------------------------------------------------------
# Short summary: fixed template over the points — every sentence cited
# ---------------------------------------------------------------------------
_STATUS_PHRASE = {"berlaku": "masih berlaku", "diubah": "masih berlaku dengan perubahan",
                  "dicabut": "sudah dicabut", "rancangan": "masih berupa rancangan",
                  "belum_berlaku": "belum berlaku"}


_SISA_DISELESAIKAN = 6
_KATA_GANTUNG = re.compile(
    r"(?:dan|atau|dan/atau|dengan|sesuai|serta|untuk|pada|dalam|dari|oleh|ke|di|yang|"
    r"sebagaimana|dimaksud|terhadap|antara|bagi|ketentuan|tersebut|paling|secara|huruf|ayat|pasal)",
    re.I)


def _clause(p: Point, marker: str, words: int = 22) -> str:
    """A short, quotable clause around the normative marker.

    Up to 10 words before the marker (normally the subject) and the rest of
    the budget after it. Starting at the unit's first word instead produced
    clauses that opened mid-way through a cross-reference.
    """
    toks = p.teks.split()
    rx = re.compile(rf"^({marker})", re.I)
    idx = next((i for i in range(len(toks)) if rx.match(" ".join(toks[i:i + 3]))), 0)
    start = max(0, idx - 10)
    for j in range(idx - 1, start - 1, -1):          # do not reach back past a sentence/list break
        if toks[j].endswith((".", ";", ":")) and j < idx - 1:
            start = j + 1
            break
    # Sisa beberapa kata saja: lebih baik diselesaikan daripada diputus dengan elipsis.
    # Jangan MULAI pada kata sambung ("tersebut sesuai dengan ketentuan …"): maju sampai kata
    # yang membawa makna, tetapi tidak pernah melewati penanda normatifnya.
    while start < idx and _KATA_GANTUNG.fullmatch(toks[start].strip(" ,;:.")):
        start += 1
    end = len(toks) if len(toks) - (start + words) <= _SISA_DISELESAIKAN else start + words
    piece = list(toks[start:end])
    # Jangan berhenti pada kata sambung ("…tersebut sesuai dengan ketentuan…"): potong mundur
    # sampai kata terakhir membawa makna.
    while end < len(toks) and len(piece) > 8 and _KATA_GANTUNG.fullmatch(piece[-1].strip(" ,;:.")):
        piece.pop()
    s = " ".join(piece) + ("…" if end < len(toks) else "")
    return s.rstrip(" ,;:.")


_GENERIC = re.compile(r"ketentuan peraturan perundang-undangan|sesuai dengan (ketentuan|peraturan)|"
                      r"berlaku secara mutatis|sebagaimana dimaksud (pada|dalam) (ayat|pasal)|"
                      r"^pada saat peraturan .{0,80} mulai berlaku", re.I)


# Isi yang membuat sebuah ayat layak dikutip meski kalimatnya dibuka rujukan silang:
# daftar huruf/angka, nominal rupiah, persen, atau jangka waktu.
_ISI_KHUSUS = re.compile(r"(?:^|[;:])\s*[a-j]\.\s|\bRp\s?[\d.]|\b\d+\s*%|"
                         r"\b\d+\s*\((?:satu|dua|tiga|empat|lima|enam|tujuh|delapan|sembilan|sepuluh|"
                         r"sebelas|dua belas|tiga puluh|enam puluh|sembilan puluh)\)", re.I)


def _generik(teks: str) -> bool:
    """Kalimat rujukan-silang tanpa isi sendiri ("… sesuai dengan ketentuan peraturan …").

    Pembukanya saja tidak cukup: hampir setiap ayat sanksi dibuka "sebagaimana dimaksud pada
    ayat (1)", lalu justru memuat daftar sanksinya. Dulu pembuka itu membuat seluruh ayat
    sanksi dianggap generik dan tersingkir dari poin utama (temuan QA #1)."""
    if not _GENERIC.search(teks):
        return False
    # Menyebut bentuk sanksi yang konkret ("berupa teguran tertulis") juga termasuk isi sendiri.
    return not (_ISI_KHUSUS.search(teks) or any(re.search(rx, teks, re.I) for rx, _ in _SANCTION_KINDS))


def _rank_for_summary(points: list[Point], top_subjects: list[str]) -> list[Point]:
    """Most informative first: specific (not "comply with the regulations"),
    about a principal subject, earliest Pasal.

    Panjang tidak lagi menjadi penalti: ayat terpanjang justru yang memuat daftar sanksi
    a–e, dan kutipan di ringkasan toh dipotong ``_clause``."""
    return sorted(points, key=lambda p: (_generik(p.teks),
                                         p.subjek not in top_subjects,
                                         _pasal_order(p.pasal)))


_BULAN = ("Januari Februari Maret April Mei Juni Juli Agustus September Oktober November Desember").split()


def _tanggal_id(iso: str) -> str:
    """"2027-01-01" → "1 Januari 2027"."""
    try:
        t, b, h = (int(x) for x in str(iso)[:10].split("-"))
        return f"{h} {_BULAN[b - 1]} {t}"
    except (ValueError, IndexError):
        return str(iso)


def jenis_kata(ident: dict[str, Any]) -> str:
    """Kata benda dokumennya untuk kalimat ringkasan: "Keputusan ini", bukan selalu "Peraturan ini"."""
    jenis = (ident.get("jenis") or "").upper()
    if jenis.startswith("KEP"):
        return "Keputusan"
    if jenis.startswith("SE"):
        return "Surat Edaran"
    if jenis in ("UU", "PERPPU"):
        return "Undang-Undang"
    return "Peraturan"


def compose_summary(ident: dict[str, Any], kerangka: list[dict[str, Any]], subjects: list[dict[str, Any]],
                    points: list[Point], sanksi: list[str], lampiran: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def add(kalimat: str, pts: list[Point]):
        out.append({"kalimat": kalimat, "rujukan": sorted({p.pasal for p in pts}, key=_pasal_order),
                    "fakta": [p.id for p in pts]})

    status = _STATUS_PHRASE.get(ident.get("status") or "", "status berlakunya belum diketahui")
    if ident.get("status") == "belum_berlaku" and ident.get("tanggal_berlaku"):
        status += f", mulai berlaku {_tanggal_id(ident['tanggal_berlaku'])}"
    nomor = f" Nomor {ident['nomor']}" if ident.get("nomor") else ""
    add(f"{ident.get('jenis') or 'Peraturan'}{nomor} tentang {ident.get('tentang') or '—'} {status}.", [])
    kata = jenis_kata(ident)
    if kerangka and ident.get("jumlah_diktum"):
        add(f"{kata} ini memuat {ident['jumlah_diktum']} diktum, antara lain: "
            + "; ".join(f"{k['bab']} {k['judul']}" for k in kerangka[:4]) + ".", [])
    elif kerangka:
        judul = [k["judul"] for k in kerangka if k.get("judul")][1:5]      # skip "Ketentuan Umum"
        if judul:
            add(f"{kata} ini terdiri atas {len(kerangka)} bab dan {ident.get('jumlah_pasal', 0)} pasal, "
                f"antara lain mengatur {', '.join(j.lower() for j in judul)}.", [])
    by_cat: dict[str, list[Point]] = {}
    for p in _rank_for_summary(points, [s["subjek"] for s in subjects[:3]]):
        by_cat.setdefault(p.kategori, []).append(p)
    if subjects:
        names = [s["subjek"] for s in subjects[:3]]
        add(f"Pihak yang paling banyak dibebani kewajiban: {', '.join(names)}.", [])
    for cat, marker, lead in (("Kewajiban", "wajib|harus", "Kewajiban utama"),
                              ("Tugas", _TUGAS_CARI, "Tugas utama"),
                              ("Pelaporan", "wajib menyampaikan|wajib melaporkan|menyampaikan laporan", "Kewajiban pelaporan"),
                              ("Perizinan", "wajib memperoleh|wajib mendapatkan", "Perizinan"),
                              ("Larangan", "dilarang|tidak diperkenankan|tidak boleh", "Larangan")):
        pts = by_cat.get(cat, [])[:2 if cat in ("Kewajiban", "Tugas") else 1]
        if pts:
            clauses = "; ".join(_clause(p, marker, 20) for p in pts)
            add(f"{lead}: {clauses}.", pts)
    if by_cat.get("Batas Waktu"):
        p = by_cat["Batas Waktu"][0]
        add(f"Batas waktu yang diatur: {_clause(p, 'paling lambat|paling lama|dalam jangka waktu')}.", [p])
    if sanksi:
        pts = by_cat.get("Sanksi", [])[:3]
        add(f"Pelanggaran dikenai sanksi berupa {', '.join(sanksi)}.", pts)
    if by_cat.get("Pencabutan"):
        pts = by_cat["Pencabutan"]
        names = []
        for p in pts:
            names += [_clean(m.group(1)) for m in _REVOKED_NAME.finditer(p.teks)]
        names = list(dict.fromkeys(n for n in names if "ini" not in n.split()[:4]))[:3]
        if names:
            add(f"{kata} ini mencabut: {'; '.join(names)}.", pts[:3])
        else:
            add(f"Pencabutan: {_clause(pts[0], 'dicabut', 30)}.", [pts[0]])
    if by_cat.get("Masa Berlaku"):
        p = max(by_cat["Masa Berlaku"], key=lambda q: _pasal_order(q.pasal))
        add(f"{_clause(p, 'mulai berlaku|berlaku sejak', 25)}.", [p])
    if lampiran.get("berat_lampiran"):
        isi = f" Bagian Lampiran antara lain: {'; '.join(lampiran['judul_bagian'][:6])}." if lampiran["judul_bagian"] else ""
        judul = lampiran.get("judul_lampiran")
        apa = f" Lampiran berjudul \"{judul}\"." if judul else ""
        out.append({"kalimat": f"Substansi utama {kata.lower()} ini berada di Lampiran, bukan di batang tubuh; "
                               "ringkasan di atas karenanya tidak lengkap." + apa + isi,
                    "rujukan": lampiran["pasal_rujukan"], "fakta": []})
        # Bukan cuma judul bagian — kutip isinya, supaya PADK yang
        # substansinya di Lampiran tidak berhenti di daftar judul kosong (T3).
        for sec in lampiran.get("isi_bagian") or []:
            out.append({"kalimat": f"{sec['judul']}: {sec['ringkasan']}",
                        "rujukan": lampiran["pasal_rujukan"], "fakta": []})
    return out


# ---------------------------------------------------------------------------
def analyse(doc: sqlite3.Row, text: sqlite3.Row | None, articles: list[dict[str, Any]],
            view: sqlite3.Row | None) -> AnalysisV2:
    started = time.perf_counter()
    md = json.loads(doc["metadata_json"] or "{}")
    structure = json.loads(text["structure"] or "{}") if text else {}
    if not articles and structure.get("sections"):
        articles = section_units(structure["sections"], text["full_text"] if text else None)
    if not articles:
        articles = text_units(text["full_text"] if text else None)
    points = extract_points(articles)
    subj: Counter = Counter()
    for p in points:
        if p.subjek and p.kategori in ("Kewajiban", "Pelaporan", "Larangan", "Perizinan"):
            for part in re.split(r"\s+(?:dan/atau|atau|dan)\s+", p.subjek):   # "Bank atau KPBLN" → both
                subj[part.strip()] += 1
    ident = {"jenis": (doc["doc_type"] or "").upper() or None, "nomor": doc["number"], "tahun": doc["year"],
             "tentang": (view["tentang"] if view else None) or doc["subject"],
             "status": doc["reg_status"], "tanggal_terbit": doc["issued_date"],
             "tanggal_berlaku": md.get("effective_date"),
             "penerbit": doc["issuing_body"],
             "jumlah_pasal": sum(1 for a in articles if re.fullmatch(r"\d+[A-Z]?", str(a["number"]))),
             "jumlah_diktum": sum(1 for a in articles if is_diktum(a["number"]))}
    kerangka = framework(structure, articles)
    subjects = [{"subjek": s, "jumlah": n} for s, n in subj.most_common(5)]
    sank = sanctions(points)
    lamp = lampiran_profile(text["full_text"] if text else None, articles)
    ringkasan = compose_summary(ident, kerangka, subjects, points, sank, lamp)
    a = AnalysisV2(doc_id=doc["doc_id"], versi=VERSION, identitas=ident, kerangka=kerangka,
                   subjek_diatur=subjects, poin=points, sanksi=sank,
                   dasar_hukum=md.get("legal_basis") or [], lampiran=lamp, ringkasan=ringkasan)
    jumlah_halaman = doc["page_count"] if "page_count" in doc.keys() else None
    a.metrik = {"waktu_ms": round((time.perf_counter() - started) * 1000, 2),
                "jumlah_poin": len(points), "kata_ringkasan": len(a.ringkasan_teks().split()),
                # Dipakai layar Analisa (penyebut halaman, kartu ringkas). Semuanya turunan
                # dari data yang sudah terbaca — tidak ada angka yang ditaksir. Tanpa
                # jumlah_halaman layar menebak "total halaman = halaman tertinggi yang dikutip".
                "jumlah_pasal": ident["jumlah_pasal"],
                "jumlah_bab": sum(1 for k in kerangka if k.get("bab")),
                "jumlah_halaman": int(jumlah_halaman) if jumlah_halaman else None,
                "jumlah_kewajiban": sum(1 for p in points if p.kategori == "Kewajiban"),
                "jumlah_larangan": sum(1 for p in points if p.kategori == "Larangan")}
    return a


SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_v2 (
    doc_id TEXT PRIMARY KEY, versi TEXT NOT NULL, fingerprint TEXT, hasil TEXT NOT NULL,
    waktu_ms REAL, dibuat TEXT NOT NULL);
"""


def _load(conn: sqlite3.Connection, doc_id: str):
    doc = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
    if doc is None:
        return None
    text = conn.execute("SELECT full_text, structure, analysis, updated_at FROM document_text "
                        "WHERE doc_id = ?", (doc_id,)).fetchone()
    arts = [dict(r) for r in conn.execute("SELECT number, bab, page, text FROM articles "
                                          "WHERE doc_id = ? ORDER BY id", (doc_id,))]
    structure = json.loads(text["structure"] or "{}") if text else {}
    parsed = {str(a.get("number")): a for a in structure.get("articles") or []
              if not a.get("in_attachment")}
    for a in arts:
        a["ayat"] = (parsed.get(str(a["number"])) or {}).get("ayat") or []
    view = conn.execute("SELECT tentang FROM kb_document_view WHERE doc_id = ?", (doc_id,)).fetchone() \
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='kb_document_view'").fetchone() else None
    return doc, text, arts, view


def _fingerprint(doc, text) -> str:
    return f"{VERSION}|{doc['ingested_at']}|{text['updated_at'] if text else ''}|{doc['reg_status']}"


def analyse_document(conn: sqlite3.Connection, doc_id: str, *, use_cache: bool = True) -> AnalysisV2 | None:
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    loaded = _load(conn, doc_id)
    if loaded is None:
        return None
    doc, text, arts, view = loaded
    fp = _fingerprint(doc, text)
    if use_cache:
        row = conn.execute("SELECT hasil FROM analysis_v2 WHERE doc_id = ? AND fingerprint = ?",
                           (doc_id, fp)).fetchone()
        if row:
            return from_dict(json.loads(row["hasil"]))
    a = analyse(doc, text, arts, view)
    with conn:
        conn.execute("INSERT OR REPLACE INTO analysis_v2 VALUES (?, ?, ?, ?, ?, datetime('now'))",
                     (doc_id, VERSION, fp, json.dumps(a.to_dict(), ensure_ascii=False), a.metrik["waktu_ms"]))
    return a


def from_dict(d: dict[str, Any]) -> AnalysisV2:
    d = dict(d)
    d.pop("ringkasan_teks", None)
    d.pop("poin_utama", None)
    d["poin"] = [Point(**p) for p in d["poin"]]
    return AnalysisV2(**d)


def analyse_all(conn: sqlite3.Connection, *, use_cache: bool = True) -> list[AnalysisV2]:
    conn.row_factory = sqlite3.Row
    ids = [r[0] for r in conn.execute("SELECT doc_id FROM documents WHERE status = 'ingested' ORDER BY doc_id")]
    return [a for a in (analyse_document(conn, i, use_cache=use_cache) for i in ids) if a]
