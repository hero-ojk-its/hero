"""US-24 — ukur aturan kategori terhadap label sektor JDIH OJK.

JDIH menerbitkan sektor setiap peraturan; itu label buatan manusia yang
independen dari aturan HERO, jadi dipakai sebagai kunci jawaban. Hanya sektor
yang dipetakan di ``sektor_jdih`` pada berkas aturan yang dihitung; sektor
lintas-bidang (Manajemen Strategis, Lainnya, …) dikeluarkan dari penyebut dan
dilaporkan jumlahnya.

Supaya tidak menipu diri sendiri: aturan disetel hanya dengan melihat galat
pada belahan ``latih`` (separuh baris, dipilih dari hash record_key), dan
akurasi yang dilaporkan adalah belahan ``uji``. Akurasi juga dipecah menurut
ada/tidaknya kode satker di nomor (".03"): kode itu dekat dengan cara JDIH
memberi sektor, jadi angka "dengan kode" sebagian melingkar; angka "tanpa
kode" (penomoran baru sejak ±2023) adalah kekuatan kata kunci yang sebenarnya.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from hero.kb.classify import Rules, classify, load_rules, number_code, sektor_key
from hero.models import RegulationMetadata


def split_of(key: str) -> str:
    return "latih" if int(hashlib.sha1(key.encode()).hexdigest(), 16) % 2 == 0 else "uji"


def evaluate_jdih(conn, rules: Rules | None = None, *, split: str | None = None) -> dict[str, Any]:
    rules = rules or load_rules()
    smap = rules.sektor_map()
    rows = conn.execute(
        "SELECT record_key, title, sektor FROM inventory WHERE source = 'jdih-ojk' "
        "AND sektor IS NOT NULL AND title IS NOT NULL").fetchall()
    excluded: Counter = Counter()
    conf: Counter = Counter()
    errors: list[dict[str, str]] = []
    n = ok = 0
    by_code: Counter = Counter()
    for r in rows:
        if split and split_of(r["record_key"]) != split:
            continue
        gold = smap.get(sektor_key(r["sektor"]))
        if gold is None:
            excluded[r["sektor"]] += 1
            continue
        md = RegulationMetadata(title=r["title"])
        pred, hits = classify(md, "", rules=rules)
        n += 1
        ok += pred == gold
        grp = "dengan_kode_nomor" if number_code(md)[0] else "tanpa_kode_nomor"
        by_code[(grp, "n")] += 1
        by_code[(grp, "benar")] += pred == gold
        conf[(gold, pred)] += 1
        if pred != gold and len(errors) < 40:
            errors.append({"judul": r["title"][:140], "label": gold, "prediksi": pred,
                           "kata": ", ".join(hits)})
    per: dict[str, dict[str, Any]] = {}
    for code in sorted({g for g, _ in conf} | {p for _, p in conf}):
        tp = conf[(code, code)]
        fp = sum(v for (g, p), v in conf.items() if p == code and g != code)
        fn = sum(v for (g, p), v in conf.items() if g == code and p != code)
        per[code] = {"label": tp + fn, "prediksi": tp + fp,
                     "presisi": round(tp / (tp + fp), 3) if tp + fp else None,
                     "recall": round(tp / (tp + fn), 3) if tp + fn else None}
    return {
        "aturan": rules.sumber, "versi": rules.versi, "belahan": split or "semua",
        "dinilai": n, "benar": ok, "akurasi": round(ok / n, 3) if n else None,
        "per_kelompok": {g: {"dinilai": by_code[(g, "n")], "akurasi": round(by_code[(g, "benar")] / by_code[(g, "n")], 3)
                             if by_code[(g, "n")] else None} for g in ("dengan_kode_nomor", "tanpa_kode_nomor")},
        "dikeluarkan": dict(excluded), "per_kategori": per,
        "salah_teratas": [{"label": g, "prediksi": p, "jumlah": v}
                          for (g, p), v in conf.most_common() if g != p][:12],
        "contoh_salah": errors,
    }
