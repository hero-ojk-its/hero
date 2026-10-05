"""Evaluasi Fase 2: v1 (ekstraktif) vs v2 (terstruktur), dan indikator URD.

No human reference summaries exist yet, so quality is measured through
properties that can be checked mechanically and that a reviewer would
otherwise check by hand:

* **keterlacakan** — does each point's text actually occur in the Pasal it
  cites? (The property that makes a summary auditable.)
* **cakupan**      — what share of normative Pasal (containing lower-case
  "wajib", "dilarang", "dikenai sanksi") is represented by at least one point?
* noise: points without a Pasal, cut off at the start of a list, definitions
  read as obligations, points taken from the Penjelasan/Lampiran.
* summary: length, bare ayat markers "(n)" with no anchor, share of
  sentences carrying a citation.

These are necessary, not sufficient: a summary can pass all of them and
still miss what matters. The SME review template (``review_template``)
is the next step, and is how the URD indicator "divalidasi" is met.
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import statistics
import time
from pathlib import Path
from typing import Any

from hero.analysis.structured import AnalysisV2, analyse_all

NORMATIVE = re.compile(r"\bwajib\b|\bdilarang\b|\bdikenai sanksi\b|\bdikenakan sanksi\b|\btidak diperkenankan\b")
DEFINITION = re.compile(r"\badalah\b|yang dimaksud dengan|yang selanjutnya (disebut|disingkat)", re.I)
TRUNCATED = re.compile(r"(:\s*[a-z1]\.?|\b[a-z]\.)\s*$")
# An ayat marker with nothing anchoring it — not "pada ayat (1)", which is a
# legitimate cross-reference in both versions.
BARE_AYAT = re.compile(r"(?<!ayat)(?<!dan/atau)(?<!atau)(?<!dan)(?:^|\s)\(\d+\)\s")
PHASE2_MIN_DOCS = 10
PHASE2_MAX_SECONDS = 300


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _pasal_no(ref: str | None) -> str | None:
    """"Pasal 4 ayat (1)" → "4"; "Bagian II. Ketentuan Umum angka 3" → that label."""
    m = re.match(r"\s*Pasal\s+(\w+)", ref or "")
    if m:
        return m.group(1)
    m = re.match(r"\s*Bagian\s+(.+?)(?:\s+ayat\s+\(\d+\))?$", ref or "")
    return m.group(1) if m else None


def _traceable(text: str, pasal_text: str | None) -> bool:
    if not pasal_text:
        return False
    probe = _norm(text.replace("…", ""))[:120]
    return bool(probe) and probe[:80] in _norm(pasal_text)


def evaluate(conn: sqlite3.Connection) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    started = time.perf_counter()
    v2_list = analyse_all(conn, use_cache=False)
    v2_seconds = time.perf_counter() - started
    v2 = {a.doc_id: a for a in v2_list}

    arts: dict[str, dict[str, str]] = {}
    for r in conn.execute("SELECT doc_id, number, text FROM articles"):
        arts.setdefault(r["doc_id"], {})[str(r["number"])] = r["text"] or ""
    from hero.analysis.structured import section_units
    for r in conn.execute("SELECT t.doc_id, t.structure, t.full_text FROM document_text t "
                          "WHERE t.doc_id NOT IN (SELECT DISTINCT doc_id FROM articles)"):
        st = json.loads(r["structure"] or "{}")
        for u in section_units(st.get("sections") or [], r["full_text"]):
            arts.setdefault(r["doc_id"], {})[str(u["number"])] = u["text"]
    closing: dict[str, int] = {}
    v1: dict[str, dict] = {}
    for r in conn.execute("SELECT t.doc_id, t.analysis, t.full_text FROM document_text t "
                          "JOIN documents d USING (doc_id) WHERE d.status = 'ingested'"):
        v1[r["doc_id"]] = json.loads(r["analysis"] or "{}")
        ft = (r["full_text"] or "").lower()
        closing[r["doc_id"]] = ft.find("ditetapkan di")

    def points_of(version: str, doc_id: str) -> list[dict[str, Any]]:
        if version == "v1":
            return [{"teks": t.get("text") or "", "pasal": t.get("pasal"), "kategori": t.get("category")}
                    for t in v1.get(doc_id, {}).get("key_takeaways", [])]
        a = v2.get(doc_id)
        return [{"teks": p.teks, "pasal": p.pasal, "kategori": p.kategori} for p in (a.poin if a else [])]

    def summary_of(version: str, doc_id: str) -> tuple[str, int, int]:
        if version == "v1":
            s = v1.get(doc_id, {}).get("summary") or ""
            return s, len(re.split(r"(?<=[.;])\s+", s)) if s else 0, 0
        a = v2.get(doc_id)
        if not a:
            return "", 0, 0
        return a.ringkasan_teks(), len(a.ringkasan), sum(1 for x in a.ringkasan if x["rujukan"])

    docs = sorted(set(v1) & set(v2))
    result: dict[str, Any] = {"dokumen": len(docs), "versi": {}}
    for version in ("v1", "v2"):
        tot = ref = trunc = defs = trace = 0
        empty = 0
        normative = covered = 0
        words, bare, sent, cited = [], 0, 0, 0
        for d in docs:
            pts = points_of(version, d)
            empty += not pts
            cited_pasal = set()
            for p in pts:
                tot += 1
                no = _pasal_no(p["pasal"])
                ref += bool(no)
                trunc += bool(TRUNCATED.search(p["teks"].strip()))
                defs += bool(DEFINITION.search(p["teks"][:200])) and p["kategori"] in ("Kewajiban", "Larangan")
                trace += _traceable(p["teks"], arts.get(d, {}).get(no) if no else None)
                if no:
                    cited_pasal.add(no)
            for no, txt in arts.get(d, {}).items():
                if NORMATIVE.search(txt):
                    normative += 1
                    covered += no in cited_pasal
            s, n_sent, n_cited = summary_of(version, d)
            words.append(len(s.split()))
            bare += bool(BARE_AYAT.search(s))
            sent += n_sent
            cited += n_cited
        pct = lambda a, b: round(100 * a / b, 1) if b else 0.0
        result["versi"][version] = {
            "poin_total": tot,
            "poin_median_per_dok": statistics.median([len(points_of(version, d)) for d in docs]) if docs else 0,
            "dok_tanpa_poin": empty,
            "poin_berujukan_pasal_pct": pct(ref, tot),
            "poin_terlacak_pct": pct(trace, tot),
            "poin_terpotong_pct": pct(trunc, tot),
            "poin_definisi_pct": pct(defs, tot),
            "cakupan_pasal_normatif_pct": pct(covered, normative),
            "ringkasan_median_kata": statistics.median(words) if words else 0,
            "ringkasan_ayat_lepas_pct": pct(bare, len(docs)),
            "kalimat_ringkasan_bercitasi_pct": pct(cited, sent),
        }
    result["v2_waktu"] = {
        "total_detik": round(v2_seconds, 2),
        "per_dok_ms_median": statistics.median([a.metrik["waktu_ms"] for a in v2_list]) if v2_list else 0,
        "per_dok_ms_maks": max((a.metrik["waktu_ms"] for a in v2_list), default=0),
    }
    result["berat_lampiran"] = sum(1 for a in v2_list if a.lampiran["berat_lampiran"])
    return result


def phase2_indicators(conn: sqlite3.Connection, ev: dict[str, Any], ai_status: dict[str, Any]) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    v2 = ev["versi"]["v2"]
    ready = ev["dokumen"] - v2["dok_tanpa_poin"]
    ext_max = 0.0
    for r in conn.execute("SELECT analysis FROM document_text"):
        ext_max = max(ext_max, float((json.loads(r["analysis"] or "{}").get("extraction") or {}).get("seconds") or 0))
    worst = ext_max + ev["v2_waktu"]["per_dok_ms_maks"] / 1000
    return [
        {"indikator": "Summary & Key Takeaways untuk ≥10 dokumen uji", "aktual": ready,
         "target": PHASE2_MIN_DOCS, "tercapai": ready >= PHASE2_MIN_DOCS,
         "cara_hitung": "dokumen ingested dengan ≥1 poin kunci v2 dan ringkasan terstruktur"},
        {"indikator": "Waktu proses per dokumen < 5 menit (Deterministik)",
         "aktual": f"{worst:.1f} s (terburuk: ekstraksi {ext_max:.1f} s + analisa v2)",
         "target": "300 s", "tercapai": worst < PHASE2_MAX_SECONDS,
         "cara_hitung": "maks detik ekstraksi PDF tersimpan + maks waktu analisa v2"},
        {"indikator": "Mode AI-Assisted dapat diaktifkan/nonaktifkan",
         "aktual": ai_status["ringkas"], "target": "toggle berfungsi, narasi lebih natural",
         "tercapai": ai_status["terverifikasi"],
         "cara_hitung": "konfigurasi analysis.ai_enabled + panggilan nyata ke model berhasil dan lolos verifikasi"},
    ]


def review_template(conn: sqlite3.Connection, out: Path, n: int = 10) -> Path:
    """CSV for subject-matter experts: one row per key point of n documents.

    The URD asks for results "divalidasi manual"; this is the instrument. The
    reviewer marks each point benar/salah/kurang-penting and adds what is
    missing — that becomes the first human-labelled evaluation set.
    """
    conn.row_factory = sqlite3.Row
    from hero.analysis.structured import analyse_document

    ids = [r[0] for r in conn.execute(
        "SELECT doc_id FROM kb_document_view WHERE akses = 'publik' AND jumlah_pasal >= 5 "
        "ORDER BY tahun DESC LIMIT ?", (n,))]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["doc_id", "judul", "jenis_baris", "id", "kategori", "pasal", "teks",
                    "penilaian (benar/salah/kurang-penting)", "catatan / poin yang terlewat"])
        for d in ids:
            a = analyse_document(conn, d)
            judul = f"{a.identitas['jenis']} {a.identitas['nomor']} — {a.identitas['tentang']}"
            w.writerow([d, judul, "ringkasan", "-", "-", "-", a.ringkasan_teks(), "", ""])
            for p in a.poin_utama(10):
                w.writerow([d, judul, "poin", p.id, p.kategori, p.pasal, p.teks, "", ""])
    return out


def render(ev: dict[str, Any], indicators: list[dict[str, Any]]) -> str:
    v1, v2 = ev["versi"]["v1"], ev["versi"]["v2"]
    rows = [
        ("Poin kunci berujukan pasal", "poin_berujukan_pasal_pct", "%", "naik"),
        ("Poin kunci terlacak ke teks pasalnya", "poin_terlacak_pct", "%", "naik"),
        ("Poin kunci terpotong di awal daftar", "poin_terpotong_pct", "%", "turun"),
        ("Definisi terbaca sebagai kewajiban/larangan", "poin_definisi_pct", "%", "turun"),
        ("Cakupan pasal normatif", "cakupan_pasal_normatif_pct", "%", "naik"),
        ("Dokumen tanpa poin kunci", "dok_tanpa_poin", "", "turun"),
        ("Median kata ringkasan", "ringkasan_median_kata", "", "turun"),
        ("Ringkasan dengan penanda ayat lepas", "ringkasan_ayat_lepas_pct", "%", "turun"),
        ("Kalimat ringkasan bercitasi pasal", "kalimat_ringkasan_bercitasi_pct", "%", "naik"),
    ]
    o = ["# Evaluasi Fase 2 — Analisa, Summary, Key Takeaways", "",
         f"*Dihasilkan oleh `hero fase2` pada {time.strftime('%d %B %Y %H:%M')} atas {ev['dokumen']} "
         "dokumen. Semua angka diukur ulang setiap kali perintah dijalankan.*", "",
         "## v1 (ekstraktif) vs v2 (terstruktur berbasis pasal)", "",
         "| Metrik | v1 | v2 | Arah yang baik |", "|---|---:|---:|---|"]
    for label, key, unit, better in rows:
        o.append(f"| {label} | {v1[key]}{unit} | **{v2[key]}{unit}** | {better} |")
    w = ev["v2_waktu"]
    o += ["", f"Waktu analisa v2: total {w['total_detik']} s untuk {ev['dokumen']} dokumen · median "
          f"{w['per_dok_ms_median']} ms · maks {w['per_dok_ms_maks']} ms per dokumen.",
          f"Dokumen yang substansinya di Lampiran (ditandai eksplisit): {ev['berat_lampiran']}.", "",
          "## Indikator Fase 2 (URD bagian 5)", "", "| Indikator | Aktual | Target | Status |",
          "|---|---|---|:---:|"]
    for i in indicators:
        o.append(f"| {i['indikator']} | {i['aktual']} | {i['target']} | {'✅' if i['tercapai'] else '⏳'} |")
    o += ["", "**Cara hitung:**", ""] + [f"- *{i['indikator']}* — {i['cara_hitung']}" for i in indicators]
    o += ["", "## Batas evaluasi ini", "",
          "- Metrik di atas memeriksa sifat yang bisa diuji mesin (rujukan, keterlacakan, cakupan, kebisingan). "
          "Ringkasan yang lolos semuanya tetap bisa melewatkan hal penting.",
          "- Belum ada ringkasan acuan buatan manusia. Templat telaah ahli ada di "
          "`data/export/fase2_telaah_ahli.csv`; hasil telaah itu menjadi set evaluasi berlabel pertama.", ""]
    return "\n".join(o)
