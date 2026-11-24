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
# Bagian selain pasal yang dicabut: butir, angka, huruf, Bab, Bagian, Lampiran — lazim di SEOJK
# ("angka 3 huruf b Lampiran Surat Edaran …", "butir III.2 SEOJK …", "Lampiran I POJK …").
_UNIT_BAGIAN = (r"(?:Pasal\s+\d+[A-Z]?(?:\s+ayat\s+\(\d+\))?(?:\s+huruf\s+[a-z])?"
                r"|angka\s+[\dIVXL]+(?:\.\d+)*|huruf\s+[a-z]|butir\s+[\w.]+|Bab\s+[IVXLC]+A?"
                r"|Bagian\s+\w+|Lampiran(?:\s+[IVXLC]+)?)")
_PARTIAL_BAGIAN = re.compile(
    rf"(?:Ketentuan\s+)?((?:{_UNIT_BAGIAN}(?:\s*,\s*|\s+dan\s+|\s+sampai\s+dengan\s+|\s+)?)+)"
    r"\s*(?:dalam|pada|dari)?\s*$", re.IGNORECASE)
#   "Ketentuan mengenai pelaporan sebagaimana diatur dalam POJK …" — sebagian menurut pokok bahasan.
_PARTIAL_POKOK = re.compile(r"\bKetentuan\s+mengenai\s+([^;:]{5,160}?)\s+(?:sebagaimana\s+"
                            r"(?:diatur|dimaksud)\s+)?(?:dalam|pada)\s*$", re.IGNORECASE)
#   "… dicabut dan dinyatakan tidak berlaku, kecuali Pasal 5 dan Pasal 6" / "…, kecuali ketentuan
#   mengenai …" — yang dikecualikan TETAP berlaku, jadi pencabutannya sebagian.
_KECUALI = re.compile(r"\bkecuali\s+(.{3,220}?)(?=\s*[;:]|\.\s+[A-Z]|\.?\s*$)", re.IGNORECASE)


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
    # Dari mana relasi dibaca (asumsi status mitra): judul ("PERUBAHAN … ATAS …") → mengubah;
    # pasal penutup ("… dicabut dan dinyatakan tidak berlaku") → mencabut / mencabut sebagian;
    # batang tubuh ("Beberapa ketentuan dalam … diubah") → mengubah; selain itu → rujukan.
    dasar: str = "rujukan"
    bagian_dicabut: list[str] = field(default_factory=list)  # butir/angka/Lampiran/pokok bahasan
    pengecualian: list[str] = field(default_factory=list)    # pasal yang TETAP berlaku ("kecuali")
    pengecualian_teks: str | None = None


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


def _nomor_pasal(teks: str) -> list[str]:
    return sorted({p.upper() for p in _PASAL_NO.findall(teks)}, key=lambda x: (len(x), x))


def _bagian_bukan_pasal(teks: str) -> list[str]:
    """Unit non-pasal yang disebut ("angka 3 huruf b", "Lampiran I", "butir III.2")."""
    t = re.sub(r"\bPasal\s+\d+[A-Z]?(?:\s+ayat\s+\(\d+\))?(?:\s+huruf\s+[a-z])?", " ", teks, flags=re.I)
    t = re.sub(r"^\s*Ketentuan\s+", "", t, flags=re.I)
    parts = [x.strip(" ,") for x in re.split(r"\s*,\s*|\s+dan\s+", t) if x.strip(" ,")]
    return [p for p in parts if re.match(r"(?:angka|huruf|butir|Bab|Bagian|Lampiran)\b", p, re.I)]


def relasi_teks(full_text: str, title: str | None, own_key: str | None = None,
                articles: list[dict[str, Any]] | None = None) -> list[Reference]:
    """Relasi dokumen-ke-dokumen yang dinyatakan SENDIRI oleh teks peraturan (tanpa basis data).

    Asumsi status yang disepakati:

    * judul "PERUBAHAN … ATAS …"                            → ``diubah`` (dasar: judul)
    * "… dicabut dan dinyatakan tidak berlaku" di penutup    → ``dicabut`` (dasar: pasal penutup)
    * klausa itu menyebut Pasal X, butir, angka, Lampiran,
      "ketentuan mengenai …", atau memakai "kecuali …"       → ``dicabut_sebagian``
    * penyebutan lain                                        → ``dirujuk`` (hanya rujukan)

    Dipakai harmonisasi (draft vs KB) dan graf KB (status turunan setiap peraturan).
    """
    text = " ".join((full_text or "").split())
    head = " ".join((title or "").split())
    refs: dict[str, Reference] = {}
    for m in _REF.finditer(text):
        raw = m.group(1)
        if _SELF.search(raw.split("Nomor")[0][-25:]):
            continue  # "Peraturan OJK ini" is the draft itself
        # _REF mulai dari "Peraturan" PERTAMA, jadi "Peraturan OJK ini mulai berlaku, Ketentuan
        # Pasal 5 Peraturan … Nomor 14" tertelan utuh; awalan sebelum jenis terakhir = konteks.
        awal = [x.start() for x in _JENIS.finditer(re.split(r"\bNomor\b", raw, maxsplit=1)[0])]
        potong = awal[-1] if awal else 0
        # Identitas dibaca dari jenis TERAKHIR bila di depannya ada kalimat tentang draft sendiri
        # ("Peraturan OJK ini mulai berlaku, Surat Edaran Bank Indonesia Nomor 9/30/DPNP" bukan POJK).
        # Tanpa "ini", awalan itu bagian nama ("Peraturan Pemerintah Pengganti Undang-Undang").
        rujukan = raw[potong:] if potong and _SELF.search(raw[:potong]) else raw
        ref = canonical_ref(rujukan) or _ref_penerbit(rujukan)
        if ref is None or ref.key == own_key:
            continue
        before = text[max(0, m.start() - 200): m.start()] + raw[:potong]
        raw = rujukan
        after = text[m.end(): m.end() + 360]
        # Klausa tempat rujukan berada: "dicabut" di klausa yang sama SEBELUM rujukan
        # ("pengganti POJK X yang telah dicabut …") bukan pernyataan pencabutan oleh draft.
        klausa = re.split(r"[;:]|\.\s", before)[-1]
        r_new = Reference(ref.key, raw.strip(), _where(raw, articles or []), "dirujuk")
        rev = _REVOKES.search(after[:260]) or _REVOKES_LEMAH.search(re.split(r"\.\s+(?=[A-Z])", after)[0])
        if rev and "dicabut" not in klausa.lower():
            r_new.dasar = "pasal penutup"
            frasa = rev.group(0).strip(" .;")
            kalimat_cabut = re.split(r"\.\s+(?=[A-Z])", after[rev.start():])[0]
            antara = after[:rev.start()]
            kec = _KECUALI.search(antara) or _KECUALI.search(kalimat_cabut)
            part = _PARTIAL.search(before)
            bagian = _PARTIAL_BAGIAN.search(before)
            pokok = _PARTIAL_POKOK.search(before)
            if part or bagian or pokok or kec:
                r_new.relasi = "dicabut_sebagian"
                sebutan = (bagian or part)
                if sebutan:
                    r_new.pasal_dicabut = _nomor_pasal(sebutan.group(1))
                    r_new.bagian_dicabut = _bagian_bukan_pasal(sebutan.group(1))
                if pokok:
                    r_new.bagian_dicabut.append(f"ketentuan mengenai {pokok.group(1).strip()}")
                if kec:
                    r_new.pengecualian = _nomor_pasal(kec.group(1))
                    r_new.pengecualian_teks = kec.group(1).strip(" ,")
                awalan = (sebutan or pokok).group(0).strip() + " " if (sebutan or pokok) else ""
                r_new.kata_kunci = (f"{awalan}{raw.strip()} … {frasa}"
                                    + (f", kecuali {r_new.pengecualian_teks}" if kec else ""))
            else:
                r_new.relasi, r_new.kata_kunci = "dicabut", f"{raw.strip()} … {frasa}"
        elif _AMENDS_AFTER.search(after):
            r_new.relasi, r_new.dasar = "diubah", "batang tubuh"
            r_new.kata_kunci = f"{raw.strip()} … {_AMENDS_AFTER.search(after).group(0)[-40:].strip()}"
        r = refs.get(ref.key)
        if r is None:
            refs[ref.key] = r_new
        elif _RANK[r_new.relasi] > _RANK[r.relasi]:
            r_new.pasal_draft = r.pasal_draft or r_new.pasal_draft
            refs[ref.key] = r_new
    # The title names the parent of an amendment.
    if _AMENDS_TITLE.search(head):
        tail = re.split(_AMENDS_TITLE, head, maxsplit=1)[-1]
        ref = canonical_ref(tail)
        if ref and ref.key != own_key:
            r = refs.setdefault(ref.key, Reference(ref.key, tail[:160], [], "diubah"))
            r.relasi, r.dasar = "diubah", "judul"
            r.kata_kunci = f"judul: {_AMENDS_TITLE.search(head).group(0)} {tail[:120].strip()}"
    urut = {"diubah": 0, "dicabut": 1, "dicabut_sebagian": 2, "dirujuk": 3}
    return sorted(refs.values(), key=lambda r: (urut[r.relasi], r.key))


def explicit_references(conn: sqlite3.Connection, full_text: str, title: str | None,
                        articles: list[dict[str, Any]], own_key: str | None = None,
                        ) -> list[Reference]:
    """Every regulation the draft cites, with its status and replacement (FR-HRM-03/04)."""
    from hero.graph.query import get_node, lineage

    refs = relasi_teks(full_text, title, own_key, articles)
    has_graph = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='graph_node'").fetchone()
    for r in refs:
        if not has_graph:
            break  # graph not built yet: references are listed without status
        node = get_node(conn, r.key)
        if node:
            r.status, r.judul, r.doc_id = node.get("status"), node.get("judul"), node.get("doc_id")
            if r.status == "dicabut":
                r.pengganti = [{"key": n["key"], "judul": n.get("judul"), "status": n.get("status")}
                               for n in lineage(conn, r.key).get("berlaku_terkini", [])]
    return refs
