"""Evaluate and calibrate harmonisasi on amendment ↔ parent pairs (TD-07, FR-HRM-12).

An amending regulation ("Perubahan atas POJK X") states, in its own text,
which articles of X it changes ("Ketentuan Pasal 5 diubah …") and which it
adds ("disisipkan … Pasal 12A"). That gives labels nobody has to annotate:

* a changed article must find **the same-numbered article of the parent** as
  its counterpart, and be labelled as regulating an existing object
  (menggantikan, since the draft says it amends that parent);
* an inserted article has **no counterpart in the parent**.

From the similarities of those two groups the "same object" threshold is
chosen (Youden's J), instead of being guessed. The labels cover what an
amendment can show — conflict between two in-force rules cannot appear in
an amendment, so ``konflik`` still needs examples labelled by DPEA.
"""
from __future__ import annotations

import json
import re
import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from hero.harmonisasi.engine import (
    _vectorise, clean_article, draft_from_catalog, harmonise, load_config, load_corpus,
)
from hero.harmonisasi.refs import amendment_plan

_AMENDS = re.compile(
    r"Perubahan\s+(?:\w+\s+)?Atas\s+(?:Peraturan\s+Otoritas\s+Jasa\s+Keuangan|POJK)\s+Nomor\s+"
    r"(\d+)(?:/POJK\.\d+)?/?\s*(?:Tahun\s+)?(\d{4})", re.IGNORECASE)


def find_pairs(conn: sqlite3.Connection, limit: int = 12, min_year: int = 2019,
               ) -> list[dict[str, Any]]:
    """Amendment/parent pairs whose PDFs are both listed in public registers.

    Newest first (born-digital, fewer OCR pages). JDIH rows are preferred
    because their document links are the register's own.
    """
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT record_key, source, title, reg_key, year, document_url, doc_id FROM inventory "
        "WHERE source IN ('jdih-ojk','ojk-regulasi') AND document_url IS NOT NULL "
        "AND doc_type = 'POJK' ORDER BY source = 'jdih-ojk' DESC")]
    by_key: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r["reg_key"]:
            by_key.setdefault(r["reg_key"], r)
    pairs, seen = [], set()
    for r in rows:
        m = _AMENDS.search(r["title"] or "")
        if not m or not r["reg_key"] or r["reg_key"] in seen or (r["year"] or 0) < min_year:
            continue
        base = by_key.get(f"POJK|{m.group(1)}|{m.group(2)}")
        if base is None:
            continue
        seen.add(r["reg_key"])
        pairs.append({"perubahan": by_key[r["reg_key"]], "induk": base})
    pairs.sort(key=lambda p: -(p["perubahan"]["year"] or 0))
    return pairs[:limit]


def prepare(settings, pairs: list[dict[str, Any]], say=print) -> dict[str, int]:
    """Download both documents of each pair into the knowledge base (public sources)."""
    from hero.pipeline import IngestPipeline

    keys = []
    for p in pairs:
        for side in ("perubahan", "induk"):
            if not p[side].get("doc_id"):
                keys.append(p[side]["record_key"])
    if not keys:
        return {"diunduh": 0}
    pipe = IngestPipeline(settings)
    run = pipe.harvest_inventory(record_keys=keys,
                                 progress=lambda kind, msg: say(f"  {msg}"))
    return {"diminta": len(keys), "ingested": sum(r.status == "ingested" for r in run.records),
            "duplikat": sum(r.status == "duplicate" for r in run.records),
            "gagal": sum(r.status in ("failed", "rejected") for r in run.records)}


def _doc_for(conn: sqlite3.Connection, inv: dict[str, Any]) -> str | None:
    row = conn.execute("SELECT doc_id FROM inventory WHERE record_key = ?",
                       (inv["record_key"],)).fetchone()
    if row and row[0]:
        return row[0]
    # Same regulation may have entered through another route (folder, upload).
    from hero.graph.identity import ref_for_record

    for d in conn.execute("SELECT doc_id, doc_type, number, year FROM documents "
                          "WHERE doc_type = 'POJK' AND year = ?", (inv["year"],)):
        ref = ref_for_record(d["doc_type"], d["number"], d["year"])
        if ref and ref.key == inv["reg_key"]:
            return d["doc_id"]
    return None


@dataclass
class PairResult:
    perubahan: str
    induk: str
    diubah: int
    disisipkan: int
    peringkat_induk: int | None
    padanan_benar: int                     # changed articles aligned to parent's same article
    terdeteksi: int                        # ...and labelled as an existing object
    label: dict[str, int] = field(default_factory=dict)
    sisipan_baru: int = 0                  # inserted articles not aligned into the parent
    sim_positif: list[float] = field(default_factory=list)
    sim_negatif: list[float] = field(default_factory=list)
    catatan: list[str] = field(default_factory=list)
    # (jenis_label_kebenaran, padanan_ke_induk_benar, terdekat_di_induk, kemiripan) per pasal
    butir: list[tuple[str, bool, bool, float]] = field(default_factory=list)


def evaluate_pair(conn: sqlite3.Connection, amend_id: str, base_id: str, cfg: dict[str, Any],
                  ) -> PairResult:
    draft = draft_from_catalog(conn, amend_id)
    plan = amendment_plan(draft.full_text)
    rep = harmonise(conn, draft, cfg)
    ranks = [k["doc_id"] for k in rep.kandidat]
    res = PairResult(draft.key or amend_id, base_id, len(plan.diubah), len(plan.disisipkan),
                     ranks.index(base_id) + 1 if base_id in ranks else None, 0, 0)

    # Raw similarities through the engine's own corpus and vectoriser.
    corpus = load_corpus(conn, cfg, draft.doc_id, draft.key)
    base_rows = [i for i, c in enumerate(corpus) if c.doc_id == base_id]
    if not base_rows:
        res.catatan.append("induk tidak masuk korpus (status/akses)")
        return res
    arts = {str(a["number"]).upper(): clean_article(a.get("text") or "") for a in draft.articles}
    want = [n for n in sorted(plan.diubah | plan.disisipkan) if n in arts and len(arts[n]) >= 40]
    if want:
        D, C = _vectorise([arts[n] for n in want], [c.teks for c in corpus])
        S = (D @ C[base_rows].T).toarray()
        for r, n in enumerate(want):
            if n in plan.diubah:
                same = [k for k, i in enumerate(base_rows) if corpus[i].pasal.upper() == n]
                if same:
                    res.sim_positif.append(float(S[r, same[0]]))
                else:
                    res.catatan.append(f"Pasal {n} tidak terbaca di induk")
            else:
                res.sim_negatif.append(float(S[r].max()))

    counted: set[str] = set()
    for f in rep.temuan:
        n = f.pasal_draft.replace("Pasal ", "").upper()
        if n in counted:
            continue
        counted.add(n)
        res.label[f.jenis] = res.label.get(f.jenis, 0) + 1
        near = f.terdekat or {}
        aligned = near.get("doc_id") == base_id and str(near.get("pasal")).upper() == n
        if n in plan.diubah or n in plan.disisipkan:
            res.butir.append(("diubah" if n in plan.diubah else "disisipkan", aligned,
                              near.get("doc_id") == base_id, float(near.get("kemiripan") or 0)))
        if n in plan.diubah and aligned:
            res.padanan_benar += 1
            if f.jenis != "pasal_baru":
                res.terdeteksi += 1
        if n in plan.disisipkan and not (f.pembanding and f.pembanding.get("doc_id") == base_id):
            res.sisipan_baru += 1
    return res


def youden(pos: list[float], neg: list[float]) -> dict[str, Any]:
    """Threshold maximising TPR − FPR, with the curve's AUC."""
    if not pos or not neg:
        return {"ambang": None, "auc": None}
    grid = np.round(np.arange(0.05, 0.96, 0.01), 2)
    best = max(grid, key=lambda t: (np.mean(np.array(pos) >= t) - np.mean(np.array(neg) >= t), -t))
    auc = float(np.mean([[1.0 if p > n else 0.5 if p == n else 0.0 for n in neg] for p in pos]))
    return {"ambang": float(best), "auc": round(auc, 3),
            "tpr": round(float(np.mean(np.array(pos) >= best)), 3),
            "fpr": round(float(np.mean(np.array(neg) >= best)), 3)}


def sweep(items: list[tuple[str, bool, bool, float]],
          grid=(0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55)) -> list[dict[str, Any]]:
    """Per threshold: recall on changed articles vs inserted ones wrongly tied to the parent."""
    changed = [x for x in items if x[0] == "diubah"]
    inserted = [x for x in items if x[0] == "disisipkan"]
    out = []
    for t in grid:
        rec = sum(1 for _, ok, _, s in changed if ok and s >= t)
        tied = sum(1 for _, _, in_base, s in inserted if in_base and s >= t)
        out.append({"ambang": t,
                    "recall": round(rec / len(changed), 3) if changed else None,
                    "sisipan_tertaut_induk": round(tied / len(inserted), 3) if inserted else None})
    return out


def run(conn: sqlite3.Connection, settings, cfg_path="config/harmonisasi.yaml",
        limit: int = 12) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    cfg = load_config(cfg_path)
    results: list[PairResult] = []
    skipped = []
    for p in find_pairs(conn, limit=limit):
        a, b = _doc_for(conn, p["perubahan"]), _doc_for(conn, p["induk"])
        if not (a and b):
            skipped.append(f"{p['perubahan']['reg_key']} → {p['induk']['reg_key']}: belum di KB")
            continue
        results.append(evaluate_pair(conn, a, b, cfg))
    pos = [s for r in results for s in r.sim_positif]
    neg = [s for r in results for s in r.sim_negatif]
    total_changed = sum(len(r.sim_positif) for r in results)
    out = {
        "dibuat": datetime.now().isoformat(timespec="seconds"),
        "ambang_dipakai": cfg["ambang"],
        "pasangan": len(results), "dilewati": skipped,
        "kandidat_induk_peringkat_1": sum(r.peringkat_induk == 1 for r in results),
        "kandidat_induk_5_besar": sum(r.peringkat_induk is not None for r in results),
        "pasal_diubah": total_changed,
        "padanan_benar": sum(r.padanan_benar for r in results),
        "recall_deteksi": round(sum(r.terdeteksi for r in results) / total_changed, 3)
        if total_changed else None,
        "pasal_disisipkan": len(neg),
        "sisipan_tidak_dipasangkan_ke_induk": sum(r.sisipan_baru for r in results),
        "distribusi": {
            "positif_median": round(statistics.median(pos), 3) if pos else None,
            "positif_p10": round(float(np.percentile(pos, 10)), 3) if pos else None,
            "negatif_median": round(statistics.median(neg), 3) if neg else None,
            "negatif_p90": round(float(np.percentile(neg, 90)), 3) if neg else None,
        },
        "kalibrasi_objek_sama": youden(pos, neg),
        "sweep": sweep([b for r in results for b in r.butir]),
        "per_pasangan": [r.__dict__ for r in results],
    }
    return out


def write_markdown(res: dict[str, Any], path: Path) -> None:
    k = res["kalibrasi_objek_sama"]
    d = res["distribusi"]
    lines = [
        "# Evaluasi Harmonisasi — pasangan peraturan perubahan ↔ induk",
        "",
        f"*Dihasilkan `hero harmonisasi evaluasi` pada {res['dibuat']}. "
        "Label diambil dari instruksi perubahan di teks peraturan itu sendiri "
        "(\"Ketentuan Pasal N diubah\", \"disisipkan … Pasal NA\"), bukan anotasi manual.*",
        "",
        "## Hasil",
        "",
        "| Ukuran | Nilai |",
        "|---|---:|",
        f"| Pasangan dievaluasi | {res['pasangan']} |",
        f"| Induk menjadi kandidat #1 | {res['kandidat_induk_peringkat_1']} / {res['pasangan']} |",
        f"| Induk masuk 5 kandidat teratas | {res['kandidat_induk_5_besar']} / {res['pasangan']} |",
        f"| Pasal diubah (berpadanan di induk) | {res['pasal_diubah']} |",
        f"| … dipasangkan ke pasal induk yang benar | {res['padanan_benar']} |",
        f"| **Recall deteksi** (padanan benar + dilabel objek yang sudah diatur) | "
        f"**{(res['recall_deteksi'] or 0):.1%}** (target FR-HRM-12: ≥ 70%) |",
        f"| Pasal disisipkan | {res['pasal_disisipkan']} |",
        f"| … tidak dipasangkan ke induk | {res['sisipan_tidak_dipasangkan_ke_induk']} |",
        "",
        "## Kalibrasi ambang `objek_sama` (TD-07)",
        "",
        "Kemiripan TF-IDF pasal baru ↔ pasal induk bernomor sama (positif) dibandingkan "
        "kemiripan tertinggi pasal sisipan ↔ pasal mana pun di induk (negatif).",
        "",
        "| | Nilai |",
        "|---|---:|",
        f"| Median positif / P10 positif | {d['positif_median']} / {d['positif_p10']} |",
        f"| Median negatif / P90 negatif | {d['negatif_median']} / {d['negatif_p90']} |",
        f"| AUC | {k.get('auc')} |",
        f"| Ambang yang disarankan (Youden J) | **{k.get('ambang')}** (TPR {k.get('tpr')}, FPR {k.get('fpr')}) |",
        f"| Ambang yang dipakai saat ini | {res['ambang_dipakai']['objek_sama']} |",
        "",
        "Pengaruh ambang (pasal unik): *recall* = pasal diubah yang dipasangkan ke pasal induk "
        "yang benar dan tidak dilabel `pasal_baru`; *sisipan tertaut* = pasal sisipan yang "
        "keliru dipasangkan ke induk.",
        "",
        "| Ambang | Recall | Sisipan tertaut ke induk |",
        "|---:|---:|---:|",
        *[f"| {x['ambang']:.2f} | {(x['recall'] or 0):.1%} | {(x['sisipan_tertaut_induk'] or 0):.1%} |"
          for x in res["sweep"]],
        "",
        "## Per pasangan",
        "",
        "| Perubahan | Peringkat induk | Diubah | Padanan benar | Terdeteksi | Disisipkan | Label |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in res["per_pasangan"]:
        lab = ", ".join(f"{k} {v}" for k, v in sorted(r["label"].items()))
        lines.append(f"| {r['perubahan'].replace('|', ' ')} | {r['peringkat_induk'] or '—'} | "
                     f"{len(r['sim_positif'])} | {r['padanan_benar']} | {r['terdeteksi']} | "
                     f"{r['disisipkan']} | {lab} |")
        # (butir kept in JSON only)
    if res["dilewati"]:
        lines += ["", "Dilewati: " + "; ".join(res["dilewati"])]
    lines += [
        "",
        "## Batas evaluasi ini",
        "",
        "- Peraturan perubahan hanya bisa menguji *objek sama vs baru* dan *menggantikan*. "
        "`konflik` (dua aturan berbeda yang sama-sama berlaku) tidak pernah muncul di dalamnya; "
        "contohnya perlu dilabel DPEA lewat validasi sampling (FR-HRM-11/12).",
        "- Pasal diubah yang redaksinya hampir tidak berubah menaikkan angka positif; pasal yang "
        "ditulis ulang total menurunkannya. Keduanya nyata terjadi dan sengaja tidak disaring.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
