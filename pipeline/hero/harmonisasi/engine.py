"""Harmonisasi: compare a draft regulation with the knowledge base, per article.

Deterministic end to end (ADR-02): TF-IDF over article text, rules over the
normative content, the graph for legal status. Nothing here needs a network
or a model, and every finding carries the reason it was given its label —
the reviewer must be able to ask "why konflik?" and get an answer that points
at text (FR-HRM-09, validasi sampling DPEA).

Labels (SRS FR-HRM-06..08b):

``duplikasi``    same object, near-identical wording — adds nothing.
``menggantikan`` same object, different provision, and the draft explicitly
                 amends or revokes the regulation it differs from.
``konflik``      same object, contradicting provision (a number, a deadline,
                 an obligation turned permission…), and the draft does *not*
                 amend or revoke that regulation — both would be in force.
``memperjelas``  same object, the old content is still there, the draft adds detail.
``pasal_baru``   nothing in the corpus regulates this object.

Same object vs not is a similarity threshold; the others are rules over the
text. Thresholds live in ``config/harmonisasi.yaml`` and are calibrated by
:mod:`hero.harmonisasi.evaluate`.
"""
from __future__ import annotations

import difflib
import json
import re
import sqlite3
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from hero.harmonisasi.refs import (
    RELASI_EKSPLISIT, AmendmentPlan, Reference, amendment_plan, explicit_references,
)

VERSION = "harmonisasi-v0.3"
LABELS = ("konflik", "menggantikan", "memperjelas", "duplikasi", "pasal_baru")
# Istilah tampilan mengikuti definisi mitra (kunci internal tetap — backend/frontend memakainya).
LABEL_TEXT = {
    "konflik": "Kontradiktif", "menggantikan": "Menggantikan", "memperjelas": "Selaras / Melengkapi",
    "duplikasi": "Tumpang Tindih", "pasal_baru": "Pasal Baru",
}
# Kosakata Pak Faris (Weekly #7) untuk "analisa": status tiap pasal terhadap KB.
# Kunci internal tetap sama; ini hanya nama tampilan yang disepakati dengan mitra.
STATUS_KB = {"pasal_baru": "baru", "duplikasi": "sama", "menggantikan": "menggantikan",
             "memperjelas": "melengkapi", "konflik": "konflik"}
# Status pembanding yang (setidaknya sebagian) masih berlaku. "unknown" ikut: tanpa bukti
# pencabutan, pembanding diperlakukan berlaku (perilaku dan recall M3 dipertahankan).
MASIH_BERLAKU = ("berlaku", "diubah", "dicabut_sebagian", "unknown", "")
LABEL_TONE = {"konflik": "danger", "menggantikan": "warning", "memperjelas": "info",
              "duplikasi": "neutral", "pasal_baru": "success"}

# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    "ambang": {"objek_sama": 0.45, "duplikasi": 0.95, "cakupan_memperjelas": 0.80,
               # dipakai bila kemiripan makna aktif (gabungan leksikal + makna) — lihat harmonisasi.yaml
               "objek_sama_hibrida": 0.60, "topik_sama": 0.75, "makna_tumpang_tindih": 0.88,
               "redaksi_tumpang_tindih": 0.80, "panjang_sebanding": 0.67},
    # Kemiripan makna (#67): auto = aktif bila model lokal ada; mati = leksikal murni.
    "semantik": {"metode": "auto", "model": "minilm", "bobot": 0.5, "maks_tanpa_cache": 2000,
                 "cache": None, "models_dir": None},
    "kandidat": {"maks": 5, "min_kemiripan": 0.20, "toleransi_pembanding": 0.05},
    "klausul_baku": {"kemiripan": 0.60, "min_dokumen": 3},
    "register": {"maks": 5, "min_kemiripan": 0.30},
    "korpus": {"kecualikan_status": ["rancangan"], "sertakan_dicabut": False},
    "keyakinan": {"tinggi": 0.75, "sedang": 0.50},
    # Weekly #10 (keputusan 3): draft yang menyatakan mengubah/mencabut peraturan di KB
    # dibandingkan HANYA dengan peraturan itu; tanpa kata kunci relasi → seluruh KB.
    "relasi": {"terarah": True},
    # Ambang tampil/kutip "pasal serupa" (Weekly #10 keputusan 5, ISU-06) per mode pembanding,
    # dari simulasi presisi `hero harmonisasi evaluasi` — lihat docs/HARMONISASI_AMBANG.md.
    "tampil": {"terarah": {"tampil": 0.50, "kutip": 0.45},
               "seluruh_kb": {"tampil": 0.80, "kutip": 0.55}},
    "tampil_hibrida": {"terarah": {"tampil": 0.65, "kutip": 0.60},
                       "seluruh_kb": {"tampil": 0.85, "kutip": 0.70}},
}


def load_config(path: str | Path | None = "config/harmonisasi.yaml") -> dict[str, Any]:
    cfg = json.loads(json.dumps(DEFAULTS))
    if path and Path(path).is_file():
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        for section, values in raw.items():
            if isinstance(values, dict):
                cfg.setdefault(section, {}).update(values)
    return cfg


# ---------------------------------------------------------------------------
# text helpers
# ---------------------------------------------------------------------------

# Amendment instructions and section headings that the structure parser
# leaves glued to the end of an article ("… 4. Di antara Pasal 12 dan …").
_TRAILING = re.compile(
    r"\s+(?:\d+\.\s+(?:Ketentuan|Di\s*antara|Setelah|Pasal\s+\d+[A-Z]?\s+dihapus)\b"
    r"|Pasal\s+(?:I|II|III|IV|V)\b"
    r"|Paragraf\s+\d+\b|Bagian\s+(?:Kesatu|Kedua|Ketiga|Keempat|Kelima|Keenam|Ketujuh|"
    r"Kedelapan|Kesembilan|Kesepuluh)\b|BAB\s+[IVXLC]+A?\b).*$",
    re.DOTALL)
_WS = re.compile(r"\s+")

# Normative signature: what changes when a provision changes.
# "%" berdiri di luar \b: antara "%" dan spasi tidak ada batas kata, sehingga "50%" dulu tak pernah
# terbaca dan selisih rasio/persentase luput dari deteksi kontradiksi.
_QUANTITY = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:\([^)]{1,40}\)\s*)?"
    r"((?:hari(?:\s+kerja|\s+kalender)?|bulan|tahun|minggu|jam|persen|kali)\b|%)",
    re.IGNORECASE)
# Indonesian notation: "." groups thousands, "," starts the decimals (Rp1.000.000,00).
_RUPIAH = re.compile(r"Rp\s?(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?", re.IGNORECASE)
_MODAL = {
    # "tidak wajib"/"tidak harus" adalah KEBOLEHAN, bukan kewajiban (pergeseran wajib → tidak wajib
    # dulu luput karena kata "wajib" tetap ada di kalimat).
    "wajib": re.compile(r"(?<!tidak\s)\b(?:wajib|harus)\b(?!\s+pajak)", re.IGNORECASE),
    "dilarang": re.compile(r"\b(?:dilarang|tidak\s+boleh|tidak\s+dapat)\b", re.IGNORECASE),
    "dapat": re.compile(r"(?<!tidak\s)\bdapat\b|\btidak\s+(?:wajib|harus)\b", re.IGNORECASE),
}
_STOP = set("""yang dan atau dengan untuk dalam pada dari ke oleh sebagaimana dimaksud ayat pasal
huruf angka ini itu tersebut adalah merupakan serta bagi atas sebagai secara terhadap akan telah
oleh paling sedikit lambat lama""".split())


def clean_article(text: str) -> str:
    return _WS.sub(" ", _TRAILING.sub("", text or "")).strip()


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 1]


def coverage(old: str, new: str) -> float:
    """Share of the old article's content words still present in the new one."""
    a, b = set(_tokens(old)), set(_tokens(new))
    return len(a & b) / len(a) if a else 0.0


def wording_ratio(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return difflib.SequenceMatcher(None, ta, tb, autojunk=False).ratio()


# "Nomor 10 Tahun 1998" is a citation, not a ten-year period.
_CITATION = re.compile(r"\b(?:Nomor|No\.)\s+[\w./-]+\s+Tahun\s+\d{4}", re.IGNORECASE)


def _quantities(text: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    text = _CITATION.sub(" ", text)
    for num, unit in _QUANTITY.findall(text):
        u = unit.lower().replace("%", "persen").split()[0]
        out[u].add(num.replace(",", "."))
    for num in _RUPIAH.findall(text):
        out["rupiah"].add("Rp" + f"{int(num.replace('.', '')):,}".replace(",", "."))
    return out


def _modalities(text: str) -> set[str]:
    return {m for m, rx in _MODAL.items() if rx.search(text)}


def provision_diff(old: str, new: str) -> list[str]:
    """Concrete, quotable differences in what the two provisions require."""
    diffs: list[str] = []
    qa, qb = _quantities(old), _quantities(new)
    for unit in sorted(set(qa) & set(qb)):
        if qa[unit] != qb[unit]:
            diffs.append(f"{unit}: {', '.join(sorted(qa[unit]))} → {', '.join(sorted(qb[unit]))}")
    ma, mb = _modalities(old), _modalities(new)
    if "wajib" in ma and "wajib" not in mb and ("dapat" in mb or "dilarang" in mb):
        diffs.append("kewajiban menjadi " + ("larangan" if "dilarang" in mb else "kebolehan"))
    elif "dilarang" in ma and "dilarang" not in mb and ("dapat" in mb or "wajib" in mb):
        diffs.append("larangan menjadi " + ("kewajiban" if "wajib" in mb else "kebolehan"))
    elif "dapat" in ma and "wajib" not in ma and "wajib" in mb:
        diffs.append("kebolehan menjadi kewajiban")
    return diffs


# "(2) Laporan …" membuka ayat; "pada ayat (1) wajib" adalah rujukan silang, bukan penanda.
_AYAT = re.compile(r"(?:^|(?<!ayat)\s)\((\d{1,2})\)\s+", re.IGNORECASE)


def ayat_units(text: str) -> list[tuple[str | None, str]]:
    """Pasal → [(nomor ayat, teks)]; pasal tanpa ayat = satu unit tanpa nomor."""
    marks, berikut = [], 1
    for m in _AYAT.finditer(text or ""):
        if int(m.group(1)) == berikut:          # ayat berurutan 1, 2, 3 …
            marks.append(m)
            berikut += 1
    if len(marks) < 2:
        return [(None, text or "")]
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(1), text[m.end():end].strip()))
    return out


def _jaccard(a: str, b: str) -> float:
    x, y = set(_tokens(a)), set(_tokens(b))
    return len(x & y) / len(x | y) if x | y else 0.0


def provision_diff_ayat(old: str, new: str, min_selaras: float = 0.25) -> list[str]:
    """Kontradiksi dicari AYAT LAWAN AYAT: tiap ayat draft dipasangkan dengan ayat lama yang
    paling mirip, lalu angka/batas waktu/modalitasnya dibandingkan di pasangan itu saja.

    Tanpa ini, "15 hari" di ayat (2) draft dibandingkan dengan "7 hari" milik ayat lain yang
    mengatur hal berbeda — perbedaan palsu. Pasal tanpa ayat dibandingkan utuh (perilaku lama).
    """
    ua, ub = ayat_units(old), ayat_units(new)
    if len(ua) == 1 and len(ub) == 1:
        return provision_diff(old, new)
    diffs: list[str] = []
    for nb, tb in ub:
        skor = [(_jaccard(ta, tb), na, ta) for na, ta in ua]
        s_best, na, ta = max(skor, key=lambda x: x[0])
        if s_best < min_selaras:
            continue
        for d in provision_diff(ta, tb):
            label = (f"ayat ({nb})" if nb else "pasal") + " ↔ " + (f"ayat ({na})" if na else "pasal")
            diffs.append(f"{label} — {d}")
    return diffs


# --- Pihak yang diatur --------------------------------------------------------------------
# Di KB nyata, pasal lintas peraturan yang "mirip makna" kebanyakan adalah KETENTUAN TEMPLAT untuk
# pihak lain (RUPS 60 hari bagi Lembaga Penjamin vs bagi Perusahaan Pergadaian). Itu bukan
# tumpang tindih dan bukan kontradiksi: pihak yang diaturnya berbeda. Pada anotasi 40 pasangan
# lintas dokumen, semua pasangan yang benar-benar satu objek berbagi pihak yang sama.
#
# Pihak dibaca dari PERIHAL peraturan (subjek kalimat seperti "Perusahaan" atau "Bank" maknanya
# ditentukan definisi di peraturan itu). Leksikon: frasa → kode pihak. Urutan penting: frasa
# panjang lebih dulu ("bank pembiayaan rakyat syariah" sebelum "bank").
PIHAK_LEKSIKON: tuple[tuple[str, str], ...] = (
    (r"bank pembiayaan rakyat syariah|\bbprs\b", "BPRS"),
    (r"bank (?:perkreditan|perekonomian) rakyat|\bbpr\b", "BPR"),
    (r"bank umum syariah|unit usaha syariah|\bbus\b|\buus\b", "BUS"),
    (r"pembiayaan sekunder perumahan|\bppsp\b", "PPSP"),
    (r"pembiayaan infrastruktur", "PPI"),
    (r"lembaga pendanaan efek|\blpe\b", "LPE"),
    (r"pendanaan bersama|pinjam meminjam|\blpbbti\b|\bp2p\b", "LPBBTI"),
    (r"inovasi teknologi sektor keuangan|\bitsk\b|agregasi jasa keuangan", "ITSK"),
    (r"aset kripto|aset keuangan digital", "KRIPTO"),
    (r"bursa karbon|unit karbon|perdagangan karbon", "KARBON"),
    (r"lembaga keuangan mikro|\blkm\b", "LKM"),
    (r"modal ventura", "MV"),
    (r"dana pensiun", "DAPEN"),
    (r"pergadaian|\bgadai\b", "GADAI"),
    (r"penjaminan|lembaga penjamin", "PENJAMIN"),
    (r"reasuransi|asuransi|pialang|penilai kerugian|agen asuransi", "ASURANSI"),
    (r"perusahaan pembiayaan|\bpembiayaan\b", "PEMBIAYAAN"),
    (r"manajer investasi|reksa dana|kontrak investasi kolektif", "MI"),
    (r"perusahaan efek|perantara pedagang efek|penjamin emisi|biro administrasi efek|derivatif", "PE"),
    (r"bursa efek|lembaga kliring|penyimpanan dan penyelesaian|penyelenggara pasar", "SRO"),
    (r"emiten|perusahaan terbuka|perusahaan publik|penawaran umum|\bhmetd\b", "EMITEN"),
    (r"lembaga jasa keuangan nonbank|\bljknb\b|industri keuangan non-?bank|\biknb\b", "LJKNB"),
    (r"lembaga jasa keuangan|pelaku usaha jasa keuangan|\bpujk\b|\bljk\b|sektor jasa keuangan", "LJK"),
    (r"\bbank\b|perbankan", "BANK"),
)
_PIHAK_RX = [(re.compile(rx, re.IGNORECASE), kode) for rx, kode in PIHAK_LEKSIKON]
_NONBANK = {"BPRS", "PPSP", "PPI", "LPE", "LPBBTI", "LKM", "MV", "DAPEN", "GADAI", "PENJAMIN",
            "ASURANSI", "PEMBIAYAAN"}
# Payung: berlaku bagi banyak pihak sekaligus, jadi tidak pernah "berbeda" dengan anggotanya.
_PAYUNG = {"LJK": None, "LJKNB": _NONBANK, "BANK": {"BUS", "BPR", "BPRS"}}


def pihak_diatur(perihal: str | None) -> set[str]:
    """Kode pihak yang diatur sebuah peraturan, dibaca dari perihalnya (setelah "tentang" terakhir)."""
    teks = re.split(r"\btentang\b", perihal or "", flags=re.IGNORECASE)[-1]
    kode: set[str] = set()
    for rx, k in _PIHAK_RX:
        if rx.search(teks):
            kode.add(k)
            teks = rx.sub(" ", teks)          # frasa panjang "memakan" kata di dalamnya
    return kode


def pihak_sama(a: set[str], b: set[str]) -> bool | None:
    """True/False bila kedua pihak terbaca; None bila salah satu tak terbaca (tidak menghukum)."""
    if not a or not b:
        return None
    if a & b:
        return True
    for x, y in ((a, b), (b, a)):
        for k in x & set(_PAYUNG):
            anggota = _PAYUNG[k]
            if anggota is None or y & anggota:
                return True
    return False


# Ketentuan templat yang berulang di hampir setiap peraturan: kemiripannya dengan pasal serupa di
# peraturan lain adalah kemiripan bentuk, bukan objek. Diperlakukan sebagai klausul baku (keyakinan
# ×0,6) dan TIDAK boleh disebut tumpang tindih hanya karena maknanya mirip.
_TEMPLAT = re.compile(
    r"^\s*(?:\(1\)\s*)?(?:Setiap\s+(?:Pihak|pihak|orang)\s+yang\s+melanggar|Selain\s+sanksi|"
    r"Otoritas\s+Jasa\s+Keuangan\s+dapat\s+mengumumkan|Dalam\s+(?:Peraturan|Surat\s+Edaran)\b.{0,90}?"
    r"yang\s+dimaksud\s+dengan|(?:Peraturan|Surat\s+Edaran)\b.{0,60}?\bini\s+mulai\s+berlaku|"
    r"Ketentuan\s+lebih\s+lanjut\b|Pada\s+saat\s+(?:Peraturan|Surat\s+Edaran)\b)"
    r"|\bdikenai\s+sanksi\s+administratif\b|\bdikenakan\s+sanksi\s+administratif\b",
    re.IGNORECASE)


def klausul_templat(teks: str) -> bool:
    return bool(_TEMPLAT.search((teks or "")[:400]))


def _excerpt(text: str, n: int = 320) -> str:
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------

@dataclass
class DraftDoc:
    judul: str
    key: str | None
    full_text: str
    articles: list[dict[str, Any]]          # {number, text, page}
    doc_id: str | None = None
    sumber: str = "katalog"


def draft_from_catalog(conn: sqlite3.Connection, doc_id: str) -> DraftDoc:
    from hero.graph.identity import ref_for_record

    d = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
    if d is None:
        raise KeyError(f"dokumen {doc_id} tidak ada di katalog")
    t = conn.execute("SELECT full_text FROM document_text WHERE doc_id = ?", (doc_id,)).fetchone()
    arts = [dict(r) for r in conn.execute(
        "SELECT number, text, page FROM articles WHERE doc_id = ? ORDER BY id", (doc_id,))]
    ref = ref_for_record(d["doc_type"], d["number"], d["year"])
    judul = " ".join(x for x in (d["title"], d["subject"]) if x)
    return DraftDoc(judul, ref.key if ref else None, t["full_text"] if t else "", arts, doc_id)


def draft_from_pdf(path: Path, settings) -> DraftDoc:
    """Analyse a PDF that is not (yet) in the knowledge base."""
    from hero.extract.metadata import extract_metadata
    from hero.extract.pdf import extract_pdf
    from hero.extract.structure import parse_structure
    from hero.graph.identity import ref_for_record

    res = extract_pdf(Path(path), settings.ocr, settings.pdf)
    if res.error:
        raise ValueError(f"PDF tidak terbaca: {res.error}")
    md = extract_metadata(res.text, None, Path(path).name)
    struct = parse_structure(res.pages)
    arts = [{"number": a.number, "text": a.text, "page": a.page} for a in struct.articles]
    ref = ref_for_record(md.doc_type, md.number, md.year)
    judul = " ".join(x for x in (md.title, md.subject) if x) or Path(path).stem
    return DraftDoc(judul, ref.key if ref else None, res.text, arts, None, "berkas")


@dataclass
class CorpusArticle:
    doc_id: str
    key: str | None
    judul: str
    nomor_dok: str | None
    status: str | None
    pasal: str
    halaman: int | None
    teks: str


def load_corpus(conn: sqlite3.Connection, cfg: dict[str, Any], exclude_doc: str | None,
                exclude_key: str | None, only_keys: set[str] | None = None) -> list[CorpusArticle]:
    """Pasal pembanding. ``only_keys`` = mode terarah: hanya peraturan yang dinyatakan
    diubah/dicabut draft, apa pun statusnya di KB (yang dicabut tetap dibandingkan — draft
    yang mencabut justru harus disandingkan dengan yang dicabutnya)."""
    from hero.graph.identity import ref_for_record

    skip = set(cfg["korpus"].get("kecualikan_status") or [])
    if not cfg["korpus"].get("sertakan_dicabut"):
        skip.add("dicabut")
    if only_keys is not None:
        skip = {"rancangan"}
    out: list[CorpusArticle] = []
    docs = conn.execute(
        "SELECT doc_id, doc_type, number, year, title, subject, reg_status FROM documents "
        "WHERE status = 'ingested'").fetchall()
    turunan = status_turunan(conn)
    for d in docs:
        ref = ref_for_record(d["doc_type"], d["number"], d["year"])
        key = ref.key if ref else None
        # Status diturunkan dari relasi antar-peraturan di graf (mis. dicabut oleh peraturan lain
        # di KB) mengalahkan status katalog yang kosong/usang — draft tetap rancangan.
        status = d["reg_status"] if (d["reg_status"] or "") == "rancangan" else (
            turunan.get(key or "") or d["reg_status"])
        if d["doc_id"] == exclude_doc or (status or "") in skip:
            continue
        if exclude_key and key == exclude_key:
            continue  # another copy of the draft itself
        if only_keys is not None and key not in only_keys:
            continue
        judul = d["subject"] or d["title"] or ""
        for a in conn.execute("SELECT number, page, text FROM articles WHERE doc_id = ? ORDER BY id",
                              (d["doc_id"],)):
            teks = clean_article(a["text"])
            if len(teks) >= 40:
                out.append(CorpusArticle(d["doc_id"], key, judul, d["number"], status,
                                         str(a["number"]), a["page"], teks))
    return out


def _lengkapi_semantik(conn: sqlite3.Connection, cfg: dict[str, Any]) -> None:
    """Lokasi model & cache mengikuti folder katalog (sama seperti indeks vektor) bila tak diatur."""
    sc = cfg.setdefault("semantik", dict(DEFAULTS["semantik"]))
    if sc.get("cache") and sc.get("models_dir"):
        return
    try:
        path = next((r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main"), "")
    except sqlite3.Error:
        path = ""
    if not path:
        return                                    # katalog di memori: tanpa cache, tanpa model
    base = Path(path).parent
    sc.setdefault("cache", None)
    sc["cache"] = sc["cache"] or str(base / "harmonisasi_semantik.db")
    sc["models_dir"] = sc.get("models_dir") or str(base / "models")


def status_turunan(conn: sqlite3.Connection) -> dict[str, str]:
    """key → status yang DITURUNKAN graf dari relasi mencabut/mengubah (kosong bila graf belum ada)."""
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(graph_node)")}
        if "status_asal" not in cols:
            return {}
        return {k: st for k, st in conn.execute(
            "SELECT key, status FROM graph_node WHERE status_asal = 'turunan'")}
    except sqlite3.Error:
        return {}


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    pasal_draft: str
    halaman_draft: int | None
    kutipan_draft: str
    jenis: str
    keyakinan: float
    tingkat: str
    alasan: str
    pembanding: dict[str, Any] | None = None   # doc_id, judul, nomor, pasal, halaman, kutipan, pdf
    kemiripan: float | None = None
    perbedaan: list[str] = field(default_factory=list)
    alternatif: list[dict[str, Any]] = field(default_factory=list)
    klausul_baku: bool = False
    # tampil (presisi ≥ 75%) | pertimbangkan (50–75%) | tidak_dikutip (< 50%) — lihat cfg "tampil"
    kecocokan: str | None = None
    # Closest corpus article even when the label is pasal_baru — kept for
    # audit and threshold calibration, never shown as a "pembanding".
    terdekat: dict[str, Any] | None = None

    def badge(self) -> dict[str, str]:
        return {"value": self.jenis, "label": LABEL_TEXT[self.jenis], "tone": LABEL_TONE[self.jenis]}


@dataclass
class Report:
    versi: str
    draft: dict[str, Any]
    kandidat: list[dict[str, Any]]
    rujukan: list[dict[str, Any]]
    temuan: list[Finding]
    ringkasan: dict[str, Any]
    rekomendasi: list[str]
    kandidat_register: list[dict[str, Any]] = field(default_factory=list)
    relasi: dict[str, Any] = field(default_factory=dict)          # mode pembanding + bukti kata kunci
    dampak_status: list[dict[str, Any]] = field(default_factory=list)
    catatan: str = ("Draft / Rekomendasi — keluaran sistem bukan keputusan. Keputusan final "
                    "tetap kewenangan Pengawas / unit terkait DPEA.")
    waktu_detik: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for f, src in zip(d["temuan"], self.temuan):
            f["badge"] = src.badge()
        return d


# ---------------------------------------------------------------------------
# engine
# ---------------------------------------------------------------------------

def _tier(conf: float, cfg: dict[str, Any]) -> str:
    k = cfg["keyakinan"]
    return "tinggi" if conf >= k["tinggi"] else "sedang" if conf >= k["sedang"] else "rendah"


def _vectorise(draft_texts: list[str], corpus_texts: list[str]):
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1,
                          token_pattern=r"(?u)\b[a-zA-Z0-9]{2,}\b", lowercase=True,
                          stop_words=sorted(_STOP))
    vec.fit(corpus_texts + draft_texts)
    return vec.transform(draft_texts), vec.transform(corpus_texts)


def classify(d_text: str, match: CorpusArticle, sim: float, explicit: bool | set[str],
             cfg: dict[str, Any], semantik: float | None = None, pihak_draft: set[str] | None = None,
             hibrida: bool = False) -> tuple[str, float, str, list[str]]:
    """Label satu pasal draft terhadap padanan terbaiknya.

    Definisi yang disepakati mitra (kunci internal → istilah tampilan):

    * ``pasal_baru``   objek belum diatur di KB (untuk pihak yang diatur draft).
    * ``menggantikan`` draft MENCABUT/MENGUBAH peraturan pembanding (relasi eksplisit, dibaca dari
                       judul/pasal penutup); perbedaan isinya = penggantian, BUKAN konflik.
    * ``konflik``      *Kontradiktif* — ayat lawan ayat: angka, batas waktu, nilai Rupiah, atau
                       modalitas (wajib/dilarang/dapat) berbeda, dan keduanya tetap berlaku.
    * ``duplikasi``    *Tumpang tindih* — substansi hampir sama, hanya beda redaksi.
    * ``memperjelas``  *Selaras / melengkapi* — topik sama, tidak bertentangan, tidak mengulang.

    ``sim``       kemiripan "objek sama": leksikal, atau gabungan leksikal + makna bila ``hibrida``.
    ``semantik``  kemiripan makna saja (opsional) — mengenali tumpang tindih beda redaksi, dan
                  pasal pelengkap yang kata-katanya berbeda tetapi topiknya sama.
    ``explicit``  draft mengubah/mencabut PASAL ini (bool), atau kumpulan key peraturan.
    """
    if isinstance(explicit, (set, frozenset, list, tuple)):
        explicit = bool(match.key and match.key in explicit)
    amb = cfg["ambang"]
    t_same = amb["objek_sama_hibrida"] if hibrida else amb["objek_sama"]
    pihak_pemb = pihak_diatur(match.judul) if pihak_draft is not None else set()
    sama_pihak = pihak_sama(pihak_draft, pihak_pemb) if pihak_draft is not None else None
    if sim < t_same:
        if (semantik is not None and not explicit and sama_pihak is True
                and semantik >= amb["topik_sama"]):
            return ("memperjelas", 0.5 + 0.15 * min(1.0, (semantik - amb["topik_sama"]) / 0.15),
                    f"selaras/melengkapi: topik sama dengan {match.pasal} (kemiripan makna "
                    f"{semantik:.2f}, pihak yang diatur sama) tetapi mengatur aspek lain — redaksinya "
                    f"berbeda (kemiripan {sim:.2f} < {t_same:.2f})", [])
        conf = min(1.0, 0.5 + 0.5 * (t_same - sim) / t_same)
        return ("pasal_baru", conf,
                f"tidak ada pasal di korpus yang mengatur objek ini (kemiripan tertinggi "
                f"{sim:.2f} < ambang objek sama {t_same:.2f})", [])
    above = min(1.0, 0.5 + 0.5 * (sim - t_same) / (1 - t_same))
    if not explicit and sama_pihak is False:
        return ("pasal_baru", min(1.0, 0.55 + 0.25 * above),
                f"objek ini belum diatur untuk pihak yang diatur draft ({', '.join(sorted(pihak_draft))}); "
                f"ketentuan serupa ada di {match.pasal} \"{match.judul[:70]}\" untuk pihak lain "
                f"({', '.join(sorted(pihak_pemb))}) — rujukan penyelarasan, bukan konflik/tumpang tindih",
                [])
    ratio = wording_ratio(match.teks, d_text)
    diffs = provision_diff_ayat(match.teks, d_text)
    cov = coverage(match.teks, d_text)
    if explicit:
        if ratio >= 0.999 and not diffs:
            return ("duplikasi", max(above, ratio),
                    f"tumpang tindih: redaksi {match.pasal} dimuat ulang tanpa perubahan, padahal draft "
                    f"menyatakan mengubah/mencabut peraturan tersebut", [])
        rinci = f"ketentuan berbeda ({'; '.join(diffs)})" if diffs else \
            f"redaksi ketentuan diganti (isi lama termuat {cov:.0%})"
        return ("menggantikan", above,
                f"objek sama dengan {match.pasal}, {rinci}; draft mencabut/mengubah peraturan "
                f"tersebut, sehingga perbedaannya dibaca sebagai penggantian, bukan konflik", diffs)
    # Perbedaan ketentuan diperiksa SEBELUM kemiripan redaksi: satu angka yang berubah di pasal
    # yang selebihnya identik (kesamaan redaksi ≥ 0,95) adalah kontradiksi, bukan tumpang tindih.
    if diffs:
        if (match.status or "") in MASIH_BERLAKU:
            return ("konflik", above * 0.9,
                    f"kontradiktif: objek sama dengan {match.pasal}, ketentuan berbeda "
                    f"({'; '.join(diffs)}), sedangkan peraturan pembanding masih berlaku dan tidak "
                    f"diubah/dicabut draft", diffs)
        return ("menggantikan", above * 0.8,
                f"objek sama dengan {match.pasal}, ketentuan berbeda ({'; '.join(diffs)}); "
                f"peraturan pembanding sudah tidak berlaku", diffs)
    if ratio >= amb["duplikasi"]:
        return ("duplikasi", max(above, ratio),
                f"tumpang tindih: redaksi hampir identik dengan {match.pasal} "
                f"(kesamaan redaksi {ratio:.2f})", [])
    sem = semantik if semantik is not None else (sim if not hibrida else 0.0)
    pj = len(_tokens(d_text)) / max(1, len(_tokens(match.teks)))
    sebanding = amb.get("panjang_sebanding", 0.67) <= pj <= 1 / amb.get("panjang_sebanding", 0.67)
    # Klausul templat (sanksi, definisi, penutup, delegasi) mirip MAKNA di mana-mana; hanya redaksi
    # yang hampir sama yang boleh disebut tumpang tindih.
    makna_boleh = not (klausul_templat(d_text) or klausul_templat(match.teks))
    if sebanding and (ratio >= amb.get("redaksi_tumpang_tindih", 0.80)
                      or (makna_boleh and sem >= amb.get("makna_tumpang_tindih", 0.88))):
        dasar = (f"kesamaan redaksi {ratio:.2f}" if ratio >= amb.get("redaksi_tumpang_tindih", 0.80)
                 else f"kemiripan makna {sem:.2f} walau redaksinya berbeda (kesamaan redaksi {ratio:.2f})")
        return ("duplikasi", above * 0.9,
                f"tumpang tindih: substansi {match.pasal} hampir sama ({dasar}), tanpa "
                f"pertentangan angka/kewajiban — pertimbangkan merujuk alih-alih mengulang", [])
    if cov >= amb["cakupan_memperjelas"] and len(d_text) > len(match.teks) * 1.05:
        return ("memperjelas", above,
                f"selaras/melengkapi: isi {match.pasal} masih termuat ({cov:.0%}) dan draft "
                f"menambah rincian", [])
    return ("memperjelas", above * 0.85,
            f"selaras/melengkapi: topik sama dengan {match.pasal} (kemiripan {sim:.2f}), tidak "
            f"bertentangan dan tidak mengulang (isi lama termuat {cov:.0%}) — draft mengatur aspek "
            f"lain dari objek yang sama", [])


def _urut_pasal(nomor: set[str] | list[str]) -> list[str]:
    def k(x: str):
        m = re.match(r"(\d+)(.*)", x)
        return (int(m.group(1)), m.group(2)) if m else (10**6, x)
    return sorted(nomor, key=k)


def pilih_korpus(conn: sqlite3.Connection, cfg: dict[str, Any], draft: DraftDoc,
                 refs: list[Reference]) -> tuple[list[CorpusArticle], dict[str, Any]]:
    """Kata kunci dulu, kemiripan kemudian (Weekly #10, keputusan 3).

    * Draft menyatakan mengubah / mencabut (sebagian) peraturan yang ADA di KB →
      ``terarah``: pasal draft hanya dibandingkan dengan pasal peraturan itu.
    * Tidak ada kata kunci relasi, atau peraturan sasarannya belum di KB →
      ``seluruh_kb``: diperlakukan sebagai peraturan baru, pasal per pasal ke seluruh KB.
    """
    sasaran = [r for r in refs if r.relasi in RELASI_EKSPLISIT]
    info: dict[str, Any] = {
        "mode": "seluruh_kb",
        "kata_kunci": [{"key": r.key, "relasi": r.relasi, "dasar": r.dasar, "bukti": r.kata_kunci}
                       for r in sasaran],
        "sasaran": [], "belum_di_kb": [],
    }
    if sasaran and cfg.get("relasi", {}).get("terarah", True):
        keys = {r.key for r in sasaran}
        corpus = load_corpus(conn, cfg, draft.doc_id, draft.key, only_keys=keys)
        ada = {c.key for c in corpus}
        info["sasaran"] = sorted(ada)
        info["belum_di_kb"] = sorted(keys - ada)
        if corpus:
            info["mode"] = "terarah"
            info["alasan"] = ("draft menyatakan " + "; ".join(
                f"{_RELASI_TEKS[r.relasi]} {r.key.replace('|', ' ')}" for r in sasaran
                if r.key in ada) + " — pasal draft dibandingkan langsung dengan peraturan itu, "
                "bukan dengan seluruh Knowledge Base")
            return corpus, info
        info["alasan"] = ("draft menyatakan mengubah/mencabut peraturan yang belum ada di Knowledge "
                          "Base — sementara dibandingkan dengan seluruh KB; unduh peraturan itu dulu")
    else:
        info["alasan"] = ("tidak ditemukan kata kunci relasi (Perubahan atas, mengubah, dicabut, "
                          "dinyatakan tidak berlaku) — diperlakukan sebagai peraturan baru dan "
                          "dibandingkan pasal per pasal dengan seluruh Knowledge Base")
    return load_corpus(conn, cfg, draft.doc_id, draft.key), info


_RELASI_TEKS = {"diubah": "mengubah", "dicabut": "mencabut",
                "dicabut_sebagian": "mencabut sebagian", "dirujuk": "merujuk"}


def dampak_status(conn: sqlite3.Connection, refs: list[Reference], plan: AmendmentPlan,
                  corpus: list[CorpusArticle]) -> list[dict[str, Any]]:
    """Akibat draft terhadap status peraturan yang dirujuknya (Weekly #10, keputusan 4).

    * perubahan → hanya pasal yang disebut diubah/dihapus yang tidak berlaku lagi;
      pasal lain tetap berlaku, pasal sisipan menambah.
    * pencabutan → seluruh pasal peraturan itu tidak berlaku.
    * pencabutan sebagian → hanya pasal yang disebut.
    """
    doc_of = {c.key: c.doc_id for c in corpus if c.key}
    induk_ubah = next((r.key for r in refs if r.relasi == "diubah"), None)
    out = []
    for r in refs:
        if r.relasi not in RELASI_EKSPLISIT:
            continue
        did = doc_of.get(r.key) or r.doc_id
        pasal_kb: list[str] = []
        if did:
            pasal_kb = _urut_pasal({str(x[0]).upper() for x in conn.execute(
                "SELECT DISTINCT number FROM articles WHERE doc_id = ?", (did,))})
        d: dict[str, Any] = {"key": r.key, "doc_id": did, "judul": r.judul, "relasi": r.relasi,
                             "dasar": r.dasar, "bukti": r.kata_kunci, "pasal_di_kb": len(pasal_kb)}
        if r.relasi == "dicabut":
            d.update(status_setelah="dicabut", pasal_tidak_berlaku=pasal_kb or ["seluruh pasal"],
                     pasal_tetap_berlaku=[],
                     penjelasan="pencabutan: seluruh peraturan tidak berlaku sejak draft berlaku")
        else:
            if r.relasi == "diubah" and r.key == induk_ubah:
                gugur, sisip = plan.diubah | plan.dihapus, plan.disisipkan
                d.update(pasal_diubah=_urut_pasal(plan.diubah), pasal_dihapus=_urut_pasal(plan.dihapus),
                         pasal_disisipkan=_urut_pasal(sisip))
            elif r.relasi == "dicabut_sebagian" and r.pengecualian:
                # "… dicabut, kecuali Pasal 5": semua gugur KECUALI yang dikecualikan.
                tetap = set(r.pengecualian)
                gugur = ({x for x in pasal_kb if x not in tetap} if pasal_kb else set()) | set(r.pasal_dicabut)
                sisip = set()
            elif r.relasi == "dicabut_sebagian":
                gugur, sisip = set(r.pasal_dicabut), set()
            else:
                gugur, sisip = set(), set()      # draft kedua yang ikut diubah: rinciannya tak terbaca
            bagian = list(r.bagian_dicabut) if r.relasi == "dicabut_sebagian" else []
            if r.relasi == "dicabut_sebagian" and r.pengecualian:
                tetap_berlaku = [x for x in pasal_kb if x in set(r.pengecualian)] or _urut_pasal(r.pengecualian)
            else:
                tetap_berlaku = [x for x in pasal_kb if x not in gugur]
            if gugur or sisip:
                penjelasan = (f"{_RELASI_TEKS[r.relasi]}: {len(gugur)} pasal lama tidak berlaku"
                              + (f" dari {len(pasal_kb)} pasal di KB" if pasal_kb else "")
                              + (f", {len(sisip)} pasal disisipkan" if sisip else "")
                              + (f"; tetap berlaku karena dikecualikan: {r.pengecualian_teks}"
                                 if r.pengecualian_teks else "; pasal lain tetap berlaku"))
            elif bagian or r.pengecualian_teks:
                penjelasan = (f"{_RELASI_TEKS[r.relasi]}: yang tidak berlaku "
                              + (", ".join(bagian) if bagian else "seluruhnya")
                              + (f", kecuali {r.pengecualian_teks}" if r.pengecualian_teks else "")
                              + " — tidak dapat dipetakan ke nomor pasal; periksa manual")
            else:
                penjelasan = (f"{_RELASI_TEKS[r.relasi]}: pasal yang diubah tidak terbaca dari "
                              "instruksi perubahan — periksa manual")
            d.update(status_setelah="dicabut sebagian" if r.relasi == "dicabut_sebagian" else "diubah",
                     pasal_tidak_berlaku=_urut_pasal(gugur),
                     pasal_tetap_berlaku=tetap_berlaku,
                     bagian_tidak_berlaku=bagian,
                     pengecualian=r.pengecualian_teks,
                     tidak_ditemukan_di_kb=_urut_pasal(gugur - set(pasal_kb)) if pasal_kb else [],
                     penjelasan=penjelasan)
        out.append(d)
    return out


def tingkat_kecocokan(sim: float, mode: str, cfg: dict[str, Any], hibrida: bool = False) -> str:
    """Seberapa layak padanan dikutip, dari presisi empiris di rentang kemiripannya."""
    kunci = "tampil_hibrida" if hibrida else "tampil"
    t = (cfg.get(kunci) or DEFAULTS[kunci]).get(mode) or DEFAULTS[kunci]["seluruh_kb"]
    return "tampil" if sim >= t["tampil"] else "pertimbangkan" if sim >= t["kutip"] else "tidak_dikutip"


def harmonise(conn: sqlite3.Connection, draft: DraftDoc, cfg: dict[str, Any] | None = None,
              ) -> Report:
    t0 = time.perf_counter()
    cfg = cfg or load_config()
    conn.row_factory = sqlite3.Row

    refs: list[Reference] = explicit_references(conn, draft.full_text, draft.judul,
                                                draft.articles, own_key=draft.key)
    plan: AmendmentPlan = amendment_plan(draft.full_text) if any(
        r.relasi == "diubah" for r in refs) else AmendmentPlan()

    corpus, relasi = pilih_korpus(conn, cfg, draft, refs)
    dampak = dampak_status(conn, refs, plan, corpus)
    gugur = {(d["key"], p) for d in dampak for p in d["pasal_tidak_berlaku"]}
    penuh = {r.key for r in refs if r.relasi in ("diubah", "dicabut")}
    pihak_d = pihak_diatur(draft.judul)
    dicabut_penuh = {d["key"] for d in dampak if d["status_setelah"] == "dicabut"}
    d_arts = [(str(a["number"]), a.get("page"), clean_article(a.get("text") or ""))
              for a in draft.articles]
    # A repeated number is the Penjelasan or a quoted article; the body comes first.
    seen: set[str] = set()
    d_arts = [a for a in d_arts if len(a[2]) >= 40
              and not (a[0].upper() in seen or seen.add(a[0].upper()))]
    if not corpus or not d_arts:
        return Report(VERSION, {"judul": draft.judul, "key": draft.key, "pasal": len(d_arts)},
                      [], [asdict(r) for r in refs], [],
                      {"pasal_draft": len(d_arts), "pasal_korpus": len(corpus),
                       "per_jenis": {}, "galat": "draft atau korpus tanpa pasal terbaca",
                       "mode_pembanding": relasi["mode"]},
                      ["Draft tidak memiliki struktur pasal yang terbaca; harmonisasi per pasal "
                       "tidak dapat dijalankan. Periksa hasil ekstraksi atau OCR."],
                      relasi=relasi, dampak_status=dampak,
                      waktu_detik=time.perf_counter() - t0)

    D, C = _vectorise([a[2] for a in d_arts], [c.teks for c in corpus])
    lex = (D @ C.T).toarray()
    from hero.harmonisasi import semantik as _sem

    _lengkapi_semantik(conn, cfg)
    sem_m = _sem.matriks([a[2] for a in d_arts], [c.teks for c in corpus], cfg)
    hibrida = sem_m is not None
    w = float(cfg["semantik"].get("bobot", 0.5))
    sims = (1 - w) * lex + w * sem_m if hibrida else lex
    doc_ids = sorted({c.doc_id for c in corpus})
    col_doc = np.array([doc_ids.index(c.doc_id) for c in corpus])
    by_key = {r.key: r for r in refs}

    # --- candidates (FR-HRM-02): whole-document similarity + share of draft
    # articles with a counterpart + explicit relation. Boilerplate articles
    # (same wording in many regulations) do not vote.
    baku_sim, baku_min = cfg["klausul_baku"]["kemiripan"], cfg["klausul_baku"]["min_dokumen"]
    min_c = cfg["kandidat"]["min_kemiripan"]
    boiler = []
    for i in range(len(d_arts)):
        high = lex[i] >= baku_sim          # ambang klausul baku dikalibrasi pada kemiripan leksikal
        boiler.append(len(set(col_doc[high].tolist())) >= baku_min or klausul_templat(d_arts[i][2]))
    from scipy.sparse import csr_matrix
    from sklearn.preprocessing import normalize

    member = csr_matrix((np.ones(len(corpus)), (col_doc, np.arange(len(corpus)))),
                        shape=(len(doc_ids), len(corpus)))
    doc_vec = normalize(member @ C)                      # one row per corpus document
    dv = normalize(csr_matrix(D.sum(axis=0)))
    doc_cos = np.asarray((doc_vec @ dv.T).todense()).ravel()

    doc_score: dict[str, dict[str, Any]] = {}
    voters = [i for i in range(len(d_arts)) if not boiler[i]] or list(range(len(d_arts)))
    for k, did in enumerate(doc_ids):
        cols = col_doc == k
        # Suara kandidat memakai skor LEKSIKAL: min_kemiripan (0,20) dikalibrasi di sana, sedangkan
        # skor makna hampir selalu > 0,20 sehingga setiap dokumen tampak "punya padanan".
        best_per_art = lex[np.ix_(voters, np.where(cols)[0])].max(axis=1)
        mirip = [d_arts[voters[n]][0] for n, v in enumerate(best_per_art) if v >= min_c]
        sample = corpus[int(np.where(cols)[0][0])]
        r = by_key.get(sample.key or "")
        score = 0.5 * float(doc_cos[k]) + 0.5 * len(mirip) / len(voters)
        alasan = []
        if r is not None:
            score += 1.0
            alasan.append({"diubah": "draft menyatakan mengubah peraturan ini",
                           "dicabut": "draft mencabut peraturan ini",
                           "dicabut_sebagian": "draft mencabut sebagian pasal peraturan ini",
                           "dirujuk": "dirujuk eksplisit oleh draft"}[r.relasi])
        alasan.append(f"kemiripan dokumen {float(doc_cos[k]):.2f}; "
                      f"{len(mirip)} dari {len(voters)} pasal draft punya padanan")
        doc_score[did] = {"doc_id": did, "key": sample.key, "judul": sample.judul,
                          "nomor": sample.nomor_dok, "status": sample.status,
                          "skor": round(score, 3), "kemiripan_dokumen": round(float(doc_cos[k]), 3),
                          "pasal_mirip": sorted(mirip, key=lambda x: (len(x), x)), "alasan": alasan}
    kandidat = sorted(doc_score.values(), key=lambda s: -s["skor"])[: cfg["kandidat"]["maks"]]
    top_docs = {k["doc_id"] for k in kandidat[:3]}
    tol = cfg["kandidat"]["toleransi_pembanding"]

    # --- per-article alignment + label (FR-HRM-05..09)
    findings: list[Finding] = []
    for i, (pasal, page, text) in enumerate(d_arts):
        order = np.argsort(-sims[i])[:25]
        j = int(order[0])
        # Prefer a counterpart from the leading candidates when it is nearly as close.
        for jj in order[:25]:
            if corpus[int(jj)].doc_id in top_docs and sims[i, jj] >= sims[i, j] - tol:
                j = int(jj)
                break
        best, sim = corpus[j], float(sims[i, j])
        # Eksplisit per PASAL: dicabut/diubah penuh → seluruh pasal peraturan itu; dicabut
        # sebagian → hanya pasal yang gugur (pasal lain tetap berlaku, jadi bisa kontradiktif).
        eksplisit = bool(best.key) and (best.key in penuh or (best.key, best.pasal.upper()) in gugur)
        jenis, conf, alasan, diffs = classify(text, best, sim, eksplisit, cfg,
                                              semantik=float(sem_m[i, j]) if hibrida else None,
                                              pihak_draft=pihak_d, hibrida=hibrida)
        # Draft sendiri menyatakan pasal ini DISISIPKAN: itu pasal baru, apa pun kemiripannya.
        if pasal.upper() in plan.disisipkan and jenis != "pasal_baru":
            jenis, conf = "pasal_baru", max(conf, 0.9)
            alasan = (f"draft menyatakan pasal ini disisipkan (pasal baru); pasal terdekat {best.pasal} "
                      f"\"{best.judul[:60]}\" (kemiripan {sim:.2f}) dicatat sebagai pembanding")
        if boiler[i] and jenis != "pasal_baru":
            n = len(set(col_doc[lex[i] >= baku_sim].tolist()))
            conf *= 0.6
            alasan += (f" · klausul baku: redaksi serupa ada di {n} peraturan" if n >= baku_min
                       else " · klausul baku: ketentuan templat (sanksi/definisi/penutup/delegasi)")
        if pasal.upper() in plan.diubah and jenis == "pasal_baru":
            alasan += " · catatan: draft menyatakan pasal ini mengubah pasal induk"
        pemb = None
        if jenis != "pasal_baru":
            pemb = {"doc_id": best.doc_id, "key": best.key, "judul": best.judul,
                    "nomor": best.nomor_dok, "status": best.status, "pasal": best.pasal,
                    "halaman": best.halaman, "kutipan": _excerpt(best.teks),
                    "pdf": f"/api/kb/documents/{best.doc_id}/pdf"
                           + (f"#page={best.halaman}" if best.halaman else ""),
                    # Status pasal pembanding SETELAH draft berlaku (keputusan 4 Weekly #10).
                    "status_setelah_draft": (
                        "tidak_berlaku" if best.key in dicabut_penuh
                        or (best.key, best.pasal.upper()) in gugur else "tetap_berlaku")}
        # "Pasal serupa" lain hanya bila layak dikutip — di bawah ambang kutip presisinya < 50%.
        kutip = ((cfg.get("tampil_hibrida" if hibrida else "tampil") or {}).get(relasi["mode"]) or {}
                 ).get("kutip", min_c)
        alt = [{"doc_id": corpus[int(x)].doc_id, "judul": corpus[int(x)].judul,
                "pasal": corpus[int(x)].pasal, "kemiripan": round(float(sims[i, x]), 3),
                "kecocokan": tingkat_kecocokan(float(sims[i, x]), relasi["mode"], cfg, hibrida)}
               for x in order[:4] if int(x) != j and sims[i, x] >= max(min_c, kutip)][:3]
        if jenis == "pasal_baru" and sim >= cfg["ambang"]["objek_sama"]:
            alt.insert(0, {"doc_id": best.doc_id, "judul": best.judul, "pasal": best.pasal,
                           "kemiripan": round(sim, 3), "kecocokan": "pihak_lain",
                           "pihak": sorted(pihak_diatur(best.judul))})
        top = [{"doc_id": corpus[int(x)].doc_id, "pasal": corpus[int(x)].pasal,
                "kemiripan": round(float(sims[i, x]), 4)} for x in order[:10]]
        findings.append(Finding(f"Pasal {pasal}", page, _excerpt(text), jenis, round(conf, 3),
                                _tier(conf, cfg), alasan, pemb, round(sim, 3), diffs, alt,
                                klausul_baku=boiler[i],
                                kecocokan=tingkat_kecocokan(sim, relasi["mode"], cfg, hibrida),
                                terdekat={"doc_id": best.doc_id, "pasal": best.pasal,
                                          "kemiripan": round(sim, 4), "top": top}))

    per_jenis = {lab: sum(f.jenis == lab for f in findings) for lab in LABELS}
    rujukan_dicabut = [r for r in refs if r.status == "dicabut"]
    summary = {
        "pasal_draft": len(d_arts), "pasal_korpus": len(corpus),
        "dokumen_korpus": len({c.doc_id for c in corpus}),
        "per_jenis": per_jenis,
        "status_pasal": {STATUS_KB[k]: v for k, v in per_jenis.items()},
        "rujukan": len(refs), "rujukan_dicabut": len(rujukan_dicabut),
        "rencana_perubahan": {"diubah": sorted(plan.diubah), "disisipkan": sorted(plan.disisipkan),
                              "dihapus": sorted(plan.dihapus)} if not plan.kosong else None,
        "mode_pembanding": relasi["mode"],
        "metode_kemiripan": (f"leksikal + makna ({cfg['semantik'].get('model')}, lokal)" if hibrida
                             else "leksikal (TF-IDF)"),
    }
    register = register_candidates(conn, draft, cfg)
    return Report(VERSION, {"judul": draft.judul, "key": draft.key, "doc_id": draft.doc_id,
                            "sumber": draft.sumber, "pasal": len(d_arts)},
                  kandidat, [asdict(r) for r in refs], findings, summary,
                  recommendations(findings, refs, register, dampak), register,
                  relasi=relasi, dampak_status=dampak,
                  waktu_detik=round(time.perf_counter() - t0, 3))


def _perihal(title: str | None) -> str:
    m = re.search(r"\btentang\b\s+(.*)", title or "", re.IGNORECASE | re.DOTALL)
    return _WS.sub(" ", m.group(1) if m else (title or "")).strip()


def register_candidates(conn: sqlite3.Connection, draft: DraftDoc,
                        cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Related regulations listed by a register but not in the KB (FR-HRM-02).

    The KB holds a fraction of what is published. When the regulation a
    draft most resembles was never downloaded, every article would look new;
    saying "download X first" is the honest answer.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    rows = [dict(r) for r in conn.execute(
        "SELECT record_key, source, reg_key, title, status, doc_id, file_url, file_size "
        "FROM inventory WHERE source IN ('jdih-ojk','ojk-regulasi') AND title IS NOT NULL "
        "AND COALESCE(status, '') != 'dicabut'")]
    have = {r[0] for r in conn.execute("SELECT doc_id FROM documents")}
    from hero.graph.identity import ref_for_record

    have_keys = set()
    for d in conn.execute("SELECT doc_type, number, year FROM documents WHERE status='ingested'"):
        ref = ref_for_record(d[0], d[1], d[2])
        if ref:
            have_keys.add(ref.key)
    # Already in the KB — linked by record, or arrived another way with the same identity.
    rows = [r for r in rows if r["reg_key"] != draft.key and r["doc_id"] not in have
            and r["reg_key"] not in have_keys]
    query = _perihal(draft.judul)
    if not rows or not query:
        return []
    texts = [_perihal(r["title"]) for r in rows]
    vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True,
                          token_pattern=r"(?u)\b[a-zA-Z0-9]{2,}\b", stop_words=sorted(_STOP))
    M = vec.fit_transform(texts + [query])
    sims = (M[:-1] @ M[-1].T).toarray().ravel()
    out, seen = [], set()
    for i in np.argsort(-sims):
        if sims[i] < cfg["register"]["min_kemiripan"] or len(out) >= cfg["register"]["maks"]:
            break
        r = rows[int(i)]
        if r["reg_key"] and r["reg_key"] in seen:
            continue
        seen.add(r["reg_key"])
        out.append({"record_key": r["record_key"], "sumber": r["source"], "key": r["reg_key"],
                    "judul": r["title"], "status": r["status"],
                    "kemiripan_perihal": round(float(sims[i]), 3),
                    "berkas": r["file_url"], "ukuran": r["file_size"]})
    return out


def recommendations(findings: list[Finding], refs: list[Reference],
                    register: list[dict[str, Any]] | None = None,
                    dampak: list[dict[str, Any]] | None = None) -> list[str]:
    """Initial recommendations (FR-HRM-10) — templated, each pointing at its evidence."""
    out: list[str] = []
    for d in dampak or []:
        nama = d["key"].replace("|", " ")
        if d["status_setelah"] == "dicabut":
            out.append(f"Draft mencabut {nama}: seluruh pasalnya tidak berlaku setelah draft "
                       f"berlaku — perbarui status di Knowledge Base dan rujukan yang masih menunjuknya.")
        elif d["pasal_tidak_berlaku"]:
            daftar = ", ".join(d["pasal_tidak_berlaku"][:12])
            out.append(f"Draft {_RELASI_TEKS[d['relasi']]} {nama}: Pasal {daftar} versi lama tidak "
                       f"berlaku; {len(d['pasal_tetap_berlaku'])} pasal lain tetap berlaku.")
    for c in (register or [])[:3]:
        out.append(f"Register memuat \"{c['judul'][:110]}\" (kemiripan perihal "
                   f"{c['kemiripan_perihal']:.2f}) yang belum ada di Knowledge Base — unduh dulu "
                   f"agar ikut dibandingkan (hero harvest, record {c['record_key'][-60:]}).")
    for r in refs:
        di_kb = r.doc_id or any(d["key"] == r.key and d["doc_id"] for d in dampak or [])
        if r.relasi in RELASI_EKSPLISIT and not di_kb:
            out.append(f"Draft {'mengubah' if r.relasi == 'diubah' else 'mencabut'} "
                       f"{r.key.replace('|', ' ')}, tetapi peraturan itu belum ada di Knowledge Base — "
                       f"unduh dulu agar pasal yang diubah dapat dibandingkan dengan aslinya.")
        if r.status == "dicabut":
            ganti = ", ".join(p["key"].replace("|", " ") for p in r.pengganti) or "penggantinya"
            out.append(f"Draft merujuk {r.key.replace('|', ' ')} yang sudah dicabut — pertimbangkan "
                       f"merujuk {ganti}.")
    konflik = [f for f in findings if f.jenis == "konflik"]
    by_doc: dict[str, list[Finding]] = defaultdict(list)
    for f in konflik:
        by_doc[(f.pembanding or {}).get("judul") or "?"].append(f)
    for judul, fs in by_doc.items():
        pasal = ", ".join(f.pasal_draft for f in fs[:6])
        out.append(f"{pasal} draft berbeda ketentuan dengan \"{judul[:90]}\" yang masih berlaku dan "
                   f"tidak diubah/dicabut draft — tegaskan hubungan keduanya (ubah/cabut secara "
                   f"eksplisit) atau selaraskan ketentuannya.")
    dup = [f for f in findings if f.jenis == "duplikasi"]
    if dup:
        out.append(f"{len(dup)} pasal menduplikasi ketentuan yang sudah ada "
                   f"({', '.join(f.pasal_draft for f in dup[:6])}) — pertimbangkan merujuk "
                   f"alih-alih mengulang.")
    baru = [f for f in findings if f.jenis == "pasal_baru"]
    if baru:
        out.append(f"{len(baru)} pasal mengatur objek yang belum ada di korpus — fokuskan telaah "
                   f"substansi pada pasal-pasal ini.")
    return out
