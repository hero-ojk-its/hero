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

VERSION = "v2.0"

# Lower-case only, matched case-sensitively: Indonesian legislative drafting
# writes obligations in lower case ("wajib menyampaikan") and defined terms in
# Title Case ("Cuti Wajib", "Wajib Pajak"). Matching case-insensitively is
# what made v1 read definitions as obligations.
MARKERS: tuple[tuple[str, str, int], ...] = (
    # (regex, category, priority — lower = more consequential)
    (r"\bdikenai sanksi\b|\bdikenakan sanksi\b|\bsanksi administratif\b", "Sanksi", 0),
    (r"\bdilarang\b|\btidak diperkenankan\b|\btidak boleh\b", "Larangan", 1),
    (r"\bwajib memperoleh (izin|persetujuan)\b|\bwajib mendapatkan (izin|persetujuan)\b", "Perizinan", 2),
    (r"\bwajib menyampaikan\b|\bwajib melaporkan\b|\bmenyampaikan laporan\b", "Pelaporan", 2),
    (r"\bwajib\b|\bharus\b", "Kewajiban", 3),
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
_SANCTION_KINDS = (("teguran tertulis|peringatan tertulis", "teguran/peringatan tertulis"),
                   (r"\bdenda\b", "denda"), ("pembatasan kegiatan", "pembatasan kegiatan usaha"),
                   ("pembekuan", "pembekuan kegiatan usaha"), ("pencabutan izin", "pencabutan izin usaha"),
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

    def poin_utama(self, n: int = 10) -> list[Point]:
        """The points to show first: round-robin across categories in order of
        legal weight, most specific point of each category first — so ten
        near-identical "dikenai sanksi administratif …" never fill the list."""
        top = [s["subjek"] for s in self.subjek_diatur[:3]]
        by_cat: dict[str, list[Point]] = {}
        for p in _rank_for_summary(self.poin, top):
            by_cat.setdefault(p.kategori, []).append(p)
        order = sorted(by_cat, key=lambda c: min(p.prioritas for p in by_cat[c]))
        out: list[Point] = []
        while len(out) < n and any(by_cat.values()):
            for c in order:
                if by_cat[c] and len(out) < n:
                    out.append(by_cat[c].pop(0))
        return out

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ringkasan_teks"] = self.ringkasan_teks()
        d["poin_utama"] = [p.id for p in self.poin_utama()]
        return d


def _pasal_order(ref: str) -> tuple[int, int]:
    nums = [int(x) for x in re.findall(r"\d+", ref)[:2]] + [0, 0]
    return nums[0], nums[1]


# ---------------------------------------------------------------------------
# Units: one ayat (or a whole Pasal without ayat) — lists stay attached
# ---------------------------------------------------------------------------
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
    if _DEFINITION.search(text[:300]):
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


def extract_points(articles: list[dict[str, Any]]) -> list[Point]:
    points: list[Point] = []
    seen: set[str] = set()
    for art in articles:
        for ayat, body in units_of(art):
            teks = _clean(body)
            if len(teks) < 25:
                continue
            got = classify_unit(teks)
            if not got:
                continue
            key = teks[:160].lower()
            if key in seen:
                continue
            seen.add(key)
            cut = len(teks) > MAX_POINT_CHARS
            num = str(art["number"])
            if num == NO_PASAL:
                ref = NO_PASAL
            else:
                ref = (f"Pasal {num}" if re.fullmatch(r"\d+[A-Z]?", num) else f"Bagian {num}") \
                    + (f" ayat ({ayat})" if ayat else "")
            points.append(Point(id=f"F{len(points) + 1}", kategori=got[0], pasal=ref,
                                halaman=art.get("page"), prioritas=got[1], subjek=subject_of(teks),
                                teks=(teks[:MAX_POINT_CHARS].rsplit(" ", 1)[0] + " …") if cut else teks,
                                terpotong=cut))
    return points


# ---------------------------------------------------------------------------
# Framework, lampiran, sanctions
# ---------------------------------------------------------------------------
def framework(structure: dict[str, Any], articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """BAB outline with the Pasal range each BAB covers."""
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


def lampiran_profile(full_text: str | None, articles: list[dict[str, Any]]) -> dict[str, Any]:
    """Is the substance in the Lampiran? If so, what does the Lampiran contain?

    Ten PADK in the corpus have ≤6 Pasal that only say "sebagaimana tercantum
    dalam Lampiran". For those, a summary of the batang tubuh is empty; the
    honest output is to say so and list the Lampiran's section headings.
    Only numbered headings (BAB I, II., A.) count — an all-caps heuristic
    picked up the signature block ("KEPALA EKSEKUTIF PENGAWAS …").
    """
    refs = [a for a in articles if _LAMPIRAN_REF.search(a["text"] or "")]
    heavy = bool(refs) and len(articles) <= 6
    headings: list[str] = []
    if heavy and full_text:
        low = full_text.lower()
        close = low.find("ditetapkan di")
        start = low.find("lampiran", close if close >= 0 else 0)
        for line in full_text[start if start >= 0 else 0:].splitlines():
            line = _clean(line)
            if 6 <= len(line) <= 110 and _LAMP_HEADING.match(line) and not _SIGNATURE.search(line):
                if line not in headings:
                    headings.append(line)
            if len(headings) >= 10:
                break
    return {"berat_lampiran": heavy, "pasal_rujukan": [f"Pasal {a['number']}" for a in refs][:3],
            "judul_bagian": headings}


def sanctions(points: list[Point]) -> list[str]:
    blob = " ".join(p.teks.lower() for p in points if p.kategori == "Sanksi")
    return [label for rx, label in _SANCTION_KINDS if re.search(rx, blob)]


# ---------------------------------------------------------------------------
# Short summary: fixed template over the points — every sentence cited
# ---------------------------------------------------------------------------
_STATUS_PHRASE = {"berlaku": "masih berlaku", "diubah": "masih berlaku dengan perubahan",
                  "dicabut": "sudah dicabut", "rancangan": "masih berupa rancangan"}


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
    piece = toks[start:start + words]
    s = " ".join(piece) + ("…" if start + words < len(toks) else "")
    return s.rstrip(" ,;:.")


_GENERIC = re.compile(r"ketentuan peraturan perundang-undangan|sesuai dengan (ketentuan|peraturan)|"
                      r"berlaku secara mutatis|sebagaimana dimaksud (pada|dalam) (ayat|pasal)|"
                      r"^pada saat peraturan .{0,80} mulai berlaku", re.I)


def _rank_for_summary(points: list[Point], top_subjects: list[str]) -> list[Point]:
    """Most informative first: specific (not "comply with the regulations"),
    about a principal subject, short enough to quote, earliest Pasal."""
    return sorted(points, key=lambda p: (bool(_GENERIC.search(p.teks)),
                                         p.subjek not in top_subjects, len(p.teks) > 400,
                                         _pasal_order(p.pasal)))


def compose_summary(ident: dict[str, Any], kerangka: list[dict[str, Any]], subjects: list[dict[str, Any]],
                    points: list[Point], sanksi: list[str], lampiran: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def add(kalimat: str, pts: list[Point]):
        out.append({"kalimat": kalimat, "rujukan": sorted({p.pasal for p in pts}, key=_pasal_order),
                    "fakta": [p.id for p in pts]})

    status = _STATUS_PHRASE.get(ident.get("status") or "", "status berlakunya belum diketahui")
    nomor = f" Nomor {ident['nomor']}" if ident.get("nomor") else ""
    add(f"{ident.get('jenis') or 'Peraturan'}{nomor} tentang {ident.get('tentang') or '—'} {status}.", [])
    if kerangka:
        judul = [k["judul"] for k in kerangka if k.get("judul")][1:5]      # skip "Ketentuan Umum"
        if judul:
            add(f"Peraturan ini terdiri atas {len(kerangka)} bab dan {ident.get('jumlah_pasal', 0)} pasal, "
                f"antara lain mengatur {', '.join(j.lower() for j in judul)}.", [])
    by_cat: dict[str, list[Point]] = {}
    for p in _rank_for_summary(points, [s["subjek"] for s in subjects[:3]]):
        by_cat.setdefault(p.kategori, []).append(p)
    if subjects:
        names = [s["subjek"] for s in subjects[:3]]
        add(f"Pihak yang paling banyak dibebani kewajiban: {', '.join(names)}.", [])
    for cat, marker, lead in (("Kewajiban", "wajib|harus", "Kewajiban utama"),
                              ("Pelaporan", "wajib menyampaikan|wajib melaporkan|menyampaikan laporan", "Kewajiban pelaporan"),
                              ("Perizinan", "wajib memperoleh|wajib mendapatkan", "Perizinan"),
                              ("Larangan", "dilarang|tidak diperkenankan|tidak boleh", "Larangan")):
        pts = by_cat.get(cat, [])[:2 if cat == "Kewajiban" else 1]
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
            add(f"Peraturan ini mencabut: {'; '.join(names)}.", pts[:3])
        else:
            add(f"Pencabutan: {_clause(pts[0], 'dicabut', 30)}.", [pts[0]])
    if by_cat.get("Masa Berlaku"):
        p = max(by_cat["Masa Berlaku"], key=lambda q: _pasal_order(q.pasal))
        add(f"{_clause(p, 'mulai berlaku|berlaku sejak', 25)}.", [p])
    if lampiran.get("berat_lampiran"):
        isi = f" Bagian Lampiran antara lain: {'; '.join(lampiran['judul_bagian'][:6])}." if lampiran["judul_bagian"] else ""
        out.append({"kalimat": "Substansi utama peraturan ini berada di Lampiran, bukan di batang tubuh; "
                               "ringkasan pasal di atas karenanya tidak lengkap." + isi,
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
             "penerbit": doc["issuing_body"],
             "jumlah_pasal": sum(1 for a in articles if re.fullmatch(r"\d+[A-Z]?", str(a["number"])))}
    kerangka = framework(structure, articles)
    subjects = [{"subjek": s, "jumlah": n} for s, n in subj.most_common(5)]
    sank = sanctions(points)
    lamp = lampiran_profile(text["full_text"] if text else None, articles)
    ringkasan = compose_summary(ident, kerangka, subjects, points, sank, lamp)
    a = AnalysisV2(doc_id=doc["doc_id"], versi=VERSION, identitas=ident, kerangka=kerangka,
                   subjek_diatur=subjects, poin=points, sanksi=sank,
                   dasar_hukum=md.get("legal_basis") or [], lampiran=lamp, ringkasan=ringkasan)
    a.metrik = {"waktu_ms": round((time.perf_counter() - started) * 1000, 2),
                "jumlah_poin": len(points), "kata_ringkasan": len(a.ringkasan_teks().split())}
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
