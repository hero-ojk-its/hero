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
    _vectorise, clean_article, draft_from_catalog, harmonise, load_config, pilih_korpus,
    wording_ratio,
)
from hero.harmonisasi.refs import amendment_plan, explicit_references

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
    mode: str = ""                         # terarah | seluruh_kb (hasil kata kunci relasi)
    induk_dari_kata_kunci: bool = False    # induk ditemukan lewat kata kunci, bukan kemiripan
    waktu_detik: float = 0.0
    # (kemiripan, relevan) per pasal berlabel: relevan = padanan benar, ATAU pasal terdekat
    # berredaksi ≥ 80% sama dengan pasal draft / pasal induk bernomor sama (pasal kembar di
    # peraturan saudara, mis. versi BPR vs BPRS — "pasal serupa" yang memang layak dikutip).
    relevan: list[tuple[float, bool]] = field(default_factory=list)


def evaluate_pair(conn: sqlite3.Connection, amend_id: str, base_id: str, cfg: dict[str, Any],
                  ) -> PairResult:
    draft = draft_from_catalog(conn, amend_id)
    plan = amendment_plan(draft.full_text)
    rep = harmonise(conn, draft, cfg)
    ranks = [k["doc_id"] for k in rep.kandidat]
    res = PairResult(draft.key or amend_id, base_id, len(plan.diubah), len(plan.disisipkan),
                     ranks.index(base_id) + 1 if base_id in ranks else None, 0, 0)
    res.mode, res.waktu_detik = rep.relasi.get("mode", ""), rep.waktu_detik

    # Raw similarities through the engine's own corpus and vectoriser — the SAME corpus the
    # engine compared against (terarah: only the regulation named by the keywords).
    refs = explicit_references(conn, draft.full_text, draft.judul, draft.articles, draft.key)
    corpus, _info = pilih_korpus(conn, cfg, draft, refs)
    res.induk_dari_kata_kunci = any(c.doc_id == base_id for c in corpus) and _info["mode"] == "terarah"
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

    base_txt = {str(a["number"]).upper(): clean_article(a["text"] or "") for a in conn.execute(
        "SELECT number, text FROM articles WHERE doc_id = ?", (base_id,))}
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
            ok = n in plan.diubah and aligned
            if not ok and near.get("doc_id"):
                row = conn.execute("SELECT text FROM articles WHERE doc_id = ? AND number = ? LIMIT 1",
                                   (near["doc_id"], str(near.get("pasal")))).fetchone()
                t = clean_article(row[0] or "") if row else ""
                ok = bool(t) and (wording_ratio(t, arts.get(n, "")) >= 0.8 or (
                    n in plan.diubah and n in base_txt and wording_ratio(t, base_txt[n]) >= 0.8))
            res.relevan.append((float(near.get("kemiripan") or 0), ok))
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


def presisi_rentang(items: list[tuple[str, bool, bool, float]], lebar: float = 0.10,
                    min_n: int = 8, relevan: list[tuple[float, bool]] | None = None,
                    ) -> dict[str, Any]:
    """Simulasi ambang tampil/kutip (Weekly #10 keputusan 5, ISU-06 #28).

    Kemiripan TF-IDF bukan persen. Yang bisa dijelaskan ke DPEA adalah: *di rentang kemiripan
    ini, berapa persen pasal terdekat yang ditemukan memang pasal yang benar?* Kebenaran =
    pasal diubah yang dipasangkan ke pasal induk bernomor sama; pasal sisipan (tak punya
    padanan) dan pasal diubah yang salah pasang dihitung salah. Ini batas BAWAH presisi —
    padanan sisipan di peraturan lain bisa saja relevan tetapi tetap dihitung salah.

    ``tampil`` = kemiripan terendah yang di atasnya presisi lokal selalu ≥ 75%;
    ``kutip``  = kemiripan terendah yang di atasnya presisi lokal selalu ≥ 50%.
    Dengan ``relevan``, presisi dihitung atas "pasal serupa yang layak dikutip" (lihat
    :class:`PairResult`) — ukuran yang diminta mitra; versi ketat tetap ikut sebagai batas bawah.
    """
    if relevan is not None:
        hasil = presisi_rentang(items, lebar, min_n)
        rel = presisi_rentang([("diubah", ok, False, s_) for s_, ok in relevan], lebar, min_n)
        for a, b in zip(hasil["rentang"], rel["rentang"]):
            a["presisi_relevan"] = b["presisi_lokal"]
            a["presisi_relevan_kumulatif"] = b["presisi_kumulatif"]
        hasil["ketat"] = {"tampil_75": hasil["ambang_tampil_75"], "kutip_50": hasil["ambang_kutip_50"]}
        hasil["ambang_tampil_75"], hasil["ambang_kutip_50"] = rel["ambang_tampil_75"], rel["ambang_kutip_50"]
        hasil["relevan"] = rel["benar"]
        return hasil
    pts = [(s, k == "diubah" and ok) for k, ok, _, s in items]
    grid = np.round(np.arange(0.15, 0.951, 0.05), 2)
    rows = []
    for t in grid:
        win = [b for s, b in pts if t - lebar / 2 <= s < t + lebar / 2]
        atas = [b for s, b in pts if s >= t]
        rows.append({"kemiripan": float(t), "n": len(win),
                     "presisi_lokal": round(float(np.mean(win)), 3) if len(win) >= min_n else None,
                     "n_atas": len(atas),
                     "presisi_kumulatif": round(float(np.mean(atas)), 3) if atas else None,
                     "cakupan_benar": round(sum(atas) / max(1, sum(b for _, b in pts)), 3)})

    def batas(p: float) -> float | None:
        best = None
        for r in reversed(rows):          # dari kemiripan tinggi turun
            v = r["presisi_lokal"]
            if v is None:
                continue
            if v < p:
                break
            best = r["kemiripan"]
        return best

    return {"rentang": rows, "ambang_tampil_75": batas(0.75), "ambang_kutip_50": batas(0.50),
            "n": len(pts), "benar": sum(b for _, b in pts)}


def run(conn: sqlite3.Connection, settings, cfg_path="config/harmonisasi.yaml",
        limit: int = 12, terarah: bool | None = None) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    cfg = load_config(cfg_path)
    if terarah is not None:
        cfg.setdefault("relasi", {})["terarah"] = terarah
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
    butir = [b for r in results for b in r.butir]
    waktu = [r.waktu_detik for r in results]
    out = {
        "dibuat": datetime.now().isoformat(timespec="seconds"),
        "mode": "terarah" if cfg.get("relasi", {}).get("terarah", True) else "seluruh_kb",
        "induk_dari_kata_kunci": sum(r.induk_dari_kata_kunci for r in results),
        "waktu_median_detik": round(statistics.median(waktu), 2) if waktu else None,
        "waktu_maks_detik": round(max(waktu), 2) if waktu else None,
        "presisi_rentang": presisi_rentang(butir, relevan=[x for r in results for x in r.relevan]),
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
        "sweep": sweep(butir),
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
        f"| Mode pembanding | `{res.get('mode', 'seluruh_kb')}` |",
        f"| Pasangan dievaluasi | {res['pasangan']} |",
        f"| Induk ditemukan lewat kata kunci relasi | {res.get('induk_dari_kata_kunci', 0)} / {res['pasangan']} |",
        f"| Waktu per draft (median / maks) | {res.get('waktu_median_detik')} / {res.get('waktu_maks_detik')} detik |",
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
        "## Simulasi ambang tampil / kutip (ISU-06, Weekly #10)",
        "",
        "Pada jendela ±0,05 di sekitar tiap kemiripan: *presisi ketat* = porsi pasal terdekat yang "
        "tepat pasal induk bernomor sama (batas bawah); *presisi relevan* = ketat + pasal terdekat "
        "yang redaksinya ≥ 80% sama dengan pasal draft atau pasal induknya (pasal kembar di "
        "peraturan saudara) — \"pasal serupa\" yang memang layak dikutip.",
        "",
        f"Ambang tampil (presisi relevan ≥ 75%): **{res['presisi_rentang']['ambang_tampil_75']}** · "
        f"ambang kutip (≥ 50%): **{res['presisi_rentang']['ambang_kutip_50']}** · versi ketat: "
        f"{res['presisi_rentang'].get('ketat')} · {res['presisi_rentang']['benar']} tepat, "
        f"{res['presisi_rentang'].get('relevan')} relevan dari {res['presisi_rentang']['n']} pasal.",
        "",
        "| Kemiripan | n jendela | Presisi ketat | Presisi relevan | n ≥ kemiripan | Presisi kumulatif | Pasal benar tercakup |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        *[f"| {x['kemiripan']:.2f} | {x['n']} | "
          f"{'—' if x['presisi_lokal'] is None else format(x['presisi_lokal'], '.0%')} | "
          f"{'—' if x.get('presisi_relevan') is None else format(x['presisi_relevan'], '.0%')} | {x['n_atas']} | "
          f"{'—' if x['presisi_kumulatif'] is None else format(x['presisi_kumulatif'], '.0%')} | "
          f"{x['cakupan_benar']:.0%} |" for x in res["presisi_rentang"]["rentang"]],
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
