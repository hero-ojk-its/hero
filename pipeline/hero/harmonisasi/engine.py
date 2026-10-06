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

from hero.harmonisasi.refs import AmendmentPlan, Reference, amendment_plan, explicit_references

VERSION = "harmonisasi-v0.1"
LABELS = ("konflik", "menggantikan", "memperjelas", "duplikasi", "pasal_baru")
LABEL_TEXT = {
    "konflik": "Konflik", "menggantikan": "Menggantikan", "memperjelas": "Memperjelas",
    "duplikasi": "Duplikasi", "pasal_baru": "Pasal Baru",
}
LABEL_TONE = {"konflik": "danger", "menggantikan": "warning", "memperjelas": "info",
              "duplikasi": "neutral", "pasal_baru": "success"}

# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    "ambang": {"objek_sama": 0.40, "duplikasi": 0.95, "cakupan_memperjelas": 0.80},
    "kandidat": {"maks": 5, "min_kemiripan": 0.20, "toleransi_pembanding": 0.05},
    "klausul_baku": {"kemiripan": 0.60, "min_dokumen": 3},
    "register": {"maks": 5, "min_kemiripan": 0.30},
    "korpus": {"kecualikan_status": ["rancangan"], "sertakan_dicabut": False},
    "keyakinan": {"tinggi": 0.75, "sedang": 0.50},
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
_QUANTITY = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:\([^)]{1,40}\)\s*)?"
    r"(hari(?:\s+kerja|\s+kalender)?|bulan|tahun|minggu|jam|persen|%|kali)\b",
    re.IGNORECASE)
# Indonesian notation: "." groups thousands, "," starts the decimals (Rp1.000.000,00).
_RUPIAH = re.compile(r"Rp\s?(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?", re.IGNORECASE)
_MODAL = {
    "wajib": re.compile(r"\b(?:wajib|harus)\b(?!\s+pajak)", re.IGNORECASE),
    "dilarang": re.compile(r"\b(?:dilarang|tidak\s+boleh|tidak\s+dapat)\b", re.IGNORECASE),
    "dapat": re.compile(r"(?<!tidak\s)\bdapat\b", re.IGNORECASE),
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
                exclude_key: str | None) -> list[CorpusArticle]:
    from hero.graph.identity import ref_for_record

    skip = set(cfg["korpus"].get("kecualikan_status") or [])
    if not cfg["korpus"].get("sertakan_dicabut"):
        skip.add("dicabut")
    out: list[CorpusArticle] = []
    docs = conn.execute(
        "SELECT doc_id, doc_type, number, year, title, subject, reg_status FROM documents "
        "WHERE status = 'ingested'").fetchall()
    for d in docs:
        if d["doc_id"] == exclude_doc or (d["reg_status"] or "") in skip:
            continue
        ref = ref_for_record(d["doc_type"], d["number"], d["year"])
        key = ref.key if ref else None
        if exclude_key and key == exclude_key:
            continue  # another copy of the draft itself
        judul = d["subject"] or d["title"] or ""
        for a in conn.execute("SELECT number, page, text FROM articles WHERE doc_id = ? ORDER BY id",
                              (d["doc_id"],)):
            teks = clean_article(a["text"])
            if len(teks) >= 40:
                out.append(CorpusArticle(d["doc_id"], key, judul, d["number"], d["reg_status"],
                                         str(a["number"]), a["page"], teks))
    return out


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


def classify(d_text: str, match: CorpusArticle, sim: float, explicit_keys: set[str],
             cfg: dict[str, Any]) -> tuple[str, float, str, list[str]]:
    """Label one draft article given its best counterpart."""
    amb = cfg["ambang"]
    t_same = amb["objek_sama"]
    if sim < t_same:
        conf = min(1.0, 0.5 + 0.5 * (t_same - sim) / t_same)
        return ("pasal_baru", conf,
                f"tidak ada pasal di korpus yang mengatur objek ini (kemiripan tertinggi "
                f"{sim:.2f} < ambang objek sama {t_same:.2f})", [])
    above = min(1.0, 0.5 + 0.5 * (sim - t_same) / (1 - t_same))
    ratio = wording_ratio(match.teks, d_text)
    explicit = match.key in explicit_keys if match.key else False
    # An article the draft explicitly amends is a change even when only a word
    # moved; "duplikasi" is reserved for wording that adds nothing at all.
    if ratio >= amb["duplikasi"] and not (explicit and ratio < 0.999):
        return ("duplikasi", max(above, ratio),
                f"redaksi hampir identik dengan {match.pasal} (kesamaan redaksi {ratio:.2f})", [])
    diffs = provision_diff(match.teks, d_text)
    if diffs:
        if explicit:
            return ("menggantikan", above,
                    f"objek sama dengan {match.pasal}, ketentuan berbeda ({'; '.join(diffs)}), "
                    f"dan draft secara eksplisit mengubah/mencabut peraturan tersebut", diffs)
        if (match.status or "") in ("berlaku", "diubah", ""):
            return ("konflik", above * 0.9,
                    f"objek sama dengan {match.pasal}, ketentuan berbeda ({'; '.join(diffs)}), "
                    f"sedangkan peraturan pembanding masih berlaku dan tidak diubah/dicabut draft",
                    diffs)
    cov = coverage(match.teks, d_text)
    if cov >= amb["cakupan_memperjelas"] and len(d_text) > len(match.teks) * 1.05:
        return ("memperjelas", above,
                f"isi {match.pasal} masih termuat ({cov:.0%}) dan draft menambah rincian", diffs)
    if explicit:
        return ("menggantikan", above,
                f"objek sama dengan {match.pasal}, redaksi ketentuan diganti "
                f"(isi lama termuat {cov:.0%}); draft mengubah/mencabut peraturan tersebut", diffs)
    return ("menggantikan", above * 0.8,
            f"objek sama dengan {match.pasal}, redaksi ketentuan berbeda (isi lama termuat "
            f"{cov:.0%}) tanpa pertentangan angka/kewajiban yang terdeteksi", diffs)


def harmonise(conn: sqlite3.Connection, draft: DraftDoc, cfg: dict[str, Any] | None = None,
              ) -> Report:
    t0 = time.perf_counter()
    cfg = cfg or load_config()
    conn.row_factory = sqlite3.Row

    refs: list[Reference] = explicit_references(conn, draft.full_text, draft.judul,
                                                draft.articles, own_key=draft.key)
    explicit_keys = {r.key for r in refs if r.relasi in ("diubah", "dicabut")}
    plan: AmendmentPlan = amendment_plan(draft.full_text) if any(
        r.relasi == "diubah" for r in refs) else AmendmentPlan()

    corpus = load_corpus(conn, cfg, draft.doc_id, draft.key)
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
                       "per_jenis": {}, "galat": "draft atau korpus tanpa pasal terbaca"},
                      ["Draft tidak memiliki struktur pasal yang terbaca; harmonisasi per pasal "
                       "tidak dapat dijalankan. Periksa hasil ekstraksi atau OCR."],
                      waktu_detik=time.perf_counter() - t0)

    D, C = _vectorise([a[2] for a in d_arts], [c.teks for c in corpus])
    sims = (D @ C.T).toarray()
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
        high = sims[i] >= baku_sim
        boiler.append(len(set(col_doc[high].tolist())) >= baku_min)
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
        best_per_art = sims[np.ix_(voters, np.where(cols)[0])].max(axis=1)
        mirip = [d_arts[voters[n]][0] for n, v in enumerate(best_per_art) if v >= min_c]
        sample = corpus[int(np.where(cols)[0][0])]
        r = by_key.get(sample.key or "")
        score = 0.5 * float(doc_cos[k]) + 0.5 * len(mirip) / len(voters)
        alasan = []
        if r is not None:
            score += 1.0
            alasan.append({"diubah": "draft menyatakan mengubah peraturan ini",
                           "dicabut": "draft mencabut peraturan ini",
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
        jenis, conf, alasan, diffs = classify(text, best, sim, explicit_keys, cfg)
        if boiler[i] and jenis != "pasal_baru":
            n = len(set(col_doc[sims[i] >= baku_sim].tolist()))
            conf *= 0.6
            alasan += f" · klausul baku: redaksi serupa ada di {n} peraturan"
        # Amendment instructions are the draft's own statement about itself.
        if pasal.upper() in plan.disisipkan and jenis != "pasal_baru":
            alasan += " · catatan: draft menyatakan pasal ini disisipkan (baru)"
        if pasal.upper() in plan.diubah and jenis == "pasal_baru":
            alasan += " · catatan: draft menyatakan pasal ini mengubah pasal induk"
        pemb = None
        if jenis != "pasal_baru":
            pemb = {"doc_id": best.doc_id, "key": best.key, "judul": best.judul,
                    "nomor": best.nomor_dok, "status": best.status, "pasal": best.pasal,
                    "halaman": best.halaman, "kutipan": _excerpt(best.teks),
                    "pdf": f"/api/kb/documents/{best.doc_id}/pdf"
                           + (f"#page={best.halaman}" if best.halaman else "")}
        alt = [{"doc_id": corpus[int(x)].doc_id, "judul": corpus[int(x)].judul,
                "pasal": corpus[int(x)].pasal, "kemiripan": round(float(sims[i, x]), 3)}
               for x in order[:4] if int(x) != j and sims[i, x] >= min_c][:3]
        top = [{"doc_id": corpus[int(x)].doc_id, "pasal": corpus[int(x)].pasal,
                "kemiripan": round(float(sims[i, x]), 4)} for x in order[:10]]
        findings.append(Finding(f"Pasal {pasal}", page, _excerpt(text), jenis, round(conf, 3),
                                _tier(conf, cfg), alasan, pemb, round(sim, 3), diffs, alt,
                                klausul_baku=boiler[i],
                                terdekat={"doc_id": best.doc_id, "pasal": best.pasal,
                                          "kemiripan": round(sim, 4), "top": top}))

    per_jenis = {lab: sum(f.jenis == lab for f in findings) for lab in LABELS}
    rujukan_dicabut = [r for r in refs if r.status == "dicabut"]
    summary = {
        "pasal_draft": len(d_arts), "pasal_korpus": len(corpus),
        "dokumen_korpus": len({c.doc_id for c in corpus}),
        "per_jenis": per_jenis, "rujukan": len(refs), "rujukan_dicabut": len(rujukan_dicabut),
        "rencana_perubahan": {"diubah": sorted(plan.diubah), "disisipkan": sorted(plan.disisipkan),
                              "dihapus": sorted(plan.dihapus)} if not plan.kosong else None,
    }
    register = register_candidates(conn, draft, cfg)
    return Report(VERSION, {"judul": draft.judul, "key": draft.key, "doc_id": draft.doc_id,
                            "sumber": draft.sumber, "pasal": len(d_arts)},
                  kandidat, [asdict(r) for r in refs], findings, summary,
                  recommendations(findings, refs, register), register,
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
                    register: list[dict[str, Any]] | None = None) -> list[str]:
    """Initial recommendations (FR-HRM-10) — templated, each pointing at its evidence."""
    out: list[str] = []
    for c in (register or [])[:3]:
        out.append(f"Register memuat \"{c['judul'][:110]}\" (kemiripan perihal "
                   f"{c['kemiripan_perihal']:.2f}) yang belum ada di Knowledge Base — unduh dulu "
                   f"agar ikut dibandingkan (hero harvest, record {c['record_key'][-60:]}).")
    for r in refs:
        if r.relasi in ("diubah", "dicabut") and not r.doc_id:
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
