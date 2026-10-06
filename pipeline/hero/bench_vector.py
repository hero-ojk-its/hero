"""Benchmark penyimpanan vektor: SQLite (NumPy · sqlite-vec) vs Postgres pgvector.

``hero bench`` menjawab "relasional vs vektor vs graf". Berkas ini menjawab
pertanyaan berikutnya, yang muncul begitu backend tim memegang korpusnya:

> Vektornya mau disimpan **di mana**, dan apa harganya?

Empat hal diukur pada **potongan yang sama persis** dan **vektor yang sama
persis**, jadi yang dibandingkan betul-betul penyimpanannya, bukan modelnya:

1. **Waktu bangun** — mengisi penyimpanan + membangun indeksnya.
2. **Ukuran** — tabel dan indeks, dalam MB; termasuk harga zero-padding ke
   kolom 1536 dimensi milik backend.
3. **Latensi** — p50/p95 pencarian top-k, pada kueri yang sama.
4. **Mutu temu-kembali** — recall@k terhadap pencarian *exact* (indeks
   aproksimatif IVFFlat/HNSW boleh salah; angka inilah ongkosnya), ditambah
   MRR@10 di tingkat dokumen pada ``config/eval_queries.yaml``.

Semua vektor HERO ber-norma 1, sehingga cosine di kedua sisi menghasilkan
peringkat yang identik untuk pencarian exact — itulah yang membuat recall
pada indeks aproksimatif bisa dibaca sebagai kehilangan mutu, bukan sebagai
perbedaan implementasi.
"""
from __future__ import annotations

import logging
import sqlite3
import statistics
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import yaml

from hero.config import Settings
from hero.vector import VectorService, vector_paths

log = logging.getLogger("hero.bench_vector")

EVAL_FILE = Path("config/eval_queries.yaml")
BENCH_TABLE = "hero_bench_vec"
BENCH_TABLE_PADDED = "hero_bench_vec_padded"


def _timeit(fn: Callable[[], Any], runs: int, warmup: int = 3) -> dict[str, float]:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t) * 1000)
    samples.sort()
    return {"p50": round(statistics.median(samples), 3),
            "p95": round(samples[min(len(samples) - 1, int(0.95 * len(samples)))], 3),
            "n": runs}


def _recall(got: list[int], truth: list[int]) -> float:
    """Berapa bagian dari k teratas *exact* yang juga ditemukan indeks ini."""
    return len(set(got) & set(truth)) / len(truth) if truth else 0.0


def _queries(eval_file: Path, fallback: list[str]) -> list[str]:
    if not eval_file.exists():
        return fallback
    sets = yaml.safe_load(eval_file.read_text(encoding="utf-8")) or {}
    out = [item["q"] for queries in sets.values() for item in queries if item.get("q")]
    return out or fallback


FALLBACK_QUERIES = [
    "kewajiban bank menyampaikan laporan kepada otoritas",
    "sanksi administratif berupa teguran tertulis",
    "penyelenggaraan teknologi informasi oleh bank umum",
]


# --------------------------------------------------------------------------
# 1. Sisi SQLite
# --------------------------------------------------------------------------
def bench_sqlite(vs: VectorService, method: str, qvecs: list[np.ndarray], k: int,
                 runs: int) -> dict[str, Any]:
    from hero.vector.store import HAS_SQLITE_VEC

    store = vs.store
    out: dict[str, Any] = {"mesin": {}}
    truth = [[rid for rid, _ in store.knn(method, q, k, engine="numpy")] for q in qvecs]
    out["mesin"]["numpy (matriks di memori)"] = {
        "latensi": _timeit(lambda: store.knn(method, qvecs[0], k, engine="numpy"), runs),
        "recall": 1.0, "catatan": "exact — jadi ini juga acuan recall"}
    if HAS_SQLITE_VEC and store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = ?", (f"vec_{method}",)).fetchone():
        got = [[rid for rid, _ in store.knn(method, q, k, engine="sqlite-vec")] for q in qvecs]
        out["mesin"]["sqlite-vec (vec0, baca dari disk)"] = {
            "latensi": _timeit(lambda: store.knn(method, qvecs[0], k, engine="sqlite-vec"), runs),
            "recall": round(float(np.mean([_recall(g, t) for g, t in zip(got, truth)])), 4),
            "catatan": "exact (brute force dalam basis data)"}
    else:
        out["mesin"]["sqlite-vec (vec0, baca dari disk)"] = {
            "catatan": "tidak tersedia — paket sqlite-vec belum terpasang atau indeks belum dibangun"}
    path = vector_paths_db(vs)
    out["ukuran_mb"] = round(path.stat().st_size / 1e6, 2) if path.exists() else 0.0
    out["rincian_mb"] = _sqlite_table_sizes(path)
    return out, truth


def vector_paths_db(vs: VectorService) -> Path:
    return Path(vs.store.path) if vs.store is not None else Path("data/hero_vectors.db")


def _sqlite_table_sizes(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT name, SUM(pgsize) FROM dbstat GROUP BY name").fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return {n: round(s / 1e6, 2) for n, s in rows}


# --------------------------------------------------------------------------
# 2. Sisi Postgres / pgvector
# --------------------------------------------------------------------------
def bench_pgvector(dsn: str | None, chunks: list[tuple[int, str, str | None, np.ndarray]],
                   qvecs: list[np.ndarray], truth: list[list[int]], k: int, runs: int,
                   *, padded_dim: int | None = 1536,
                   progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    from hero.bridge import pg

    say = progress or (lambda m: None)
    dim = len(chunks[0][3])
    conn = pg.connect(dsn)
    try:
        out: dict[str, Any] = {"server": pg.server_version(conn), "dimensi": dim,
                               "baris": len(chunks), "indeks": {}}
        store = pg.PgVectorStore(conn, BENCH_TABLE, dim)
        store.create()
        say(f"pgvector: memuat {len(chunks)} vektor {dim} dimensi lewat COPY…")
        out["muat"] = store.copy_insert(chunks)
        store.analyze()
        out["tabel_mb"] = store.table_size_mb()

        def measure(label: str, **search_kw) -> dict[str, Any]:
            got = [[rid for rid, _ in store.search(q, k, **search_kw)] for q in qvecs]
            return {"latensi": _timeit(lambda: store.search(qvecs[0], k, **search_kw), runs),
                    "recall": round(float(np.mean([_recall(g, t) for g, t in zip(got, truth)])), 4),
                    "rencana": store.plan(qvecs[0], k)}

        store.reset_search_params()
        say("pgvector: exact (tanpa indeks)…")
        out["indeks"]["tanpa indeks (exact)"] = {"bangun": {"detik_bangun": 0.0, "ukuran_mb": 0.0},
                                                 **measure("exact")}

        # IVFFlat: lists ≈ √n adalah anjuran pgvector untuk korpus kecil-sedang;
        # probes menentukan pertukaran recall ↔ latensi saat kueri.
        lists = max(1, min(2000, int(np.sqrt(len(chunks)))))
        say(f"pgvector: membangun IVFFlat (lists={lists})…")
        built = store.create_index("ivfflat", lists=lists)
        store.analyze()
        for probes in (1, 10, lists):
            out["indeks"][f"IVFFlat lists={lists}, probes={probes}"] = {
                "bangun": built, **measure("ivfflat", probes=probes)}
        store.reset_search_params()
        store.drop_indexes()

        say("pgvector: membangun HNSW (m=16, ef_construction=64)…")
        built = store.create_index("hnsw", m=16, ef_construction=64)
        store.analyze()
        for ef in (10, 40, 100):
            out["indeks"][f"HNSW m=16, ef_search={ef}"] = {
                "bangun": built, **measure("hnsw", ef_search=ef)}
        store.reset_search_params()
        store.drop_indexes()

        if padded_dim and padded_dim > dim:
            say(f"pgvector: mengukur harga zero-padding ke {padded_dim} dimensi…")
            from hero.bridge.embed import pad_to

            padded = pg.PgVectorStore(conn, BENCH_TABLE_PADDED, padded_dim)
            padded.create()
            padded.copy_insert((rid, d, r, pad_to(v, padded_dim)) for rid, d, r, v in chunks)
            padded.analyze()
            got = [[rid for rid, _ in padded.search(pad_to(q, padded_dim), k)] for q in qvecs]
            out["padding"] = {
                "dimensi": padded_dim, "tabel_mb": padded.table_size_mb(),
                "latensi_exact": _timeit(
                    lambda: padded.search(pad_to(qvecs[0], padded_dim), k), max(5, runs // 3)),
                "recall_vs_native": round(
                    float(np.mean([_recall(g, t) for g, t in zip(got, truth)])), 4)}
            padded.drop()
        store.drop()
        return out
    finally:
        conn.close()


# --------------------------------------------------------------------------
# 3. Mutu di tingkat dokumen
# --------------------------------------------------------------------------
def bench_quality(settings: Settings, vs: VectorService, method: str, k: int,
                  eval_file: Path = EVAL_FILE) -> dict[str, Any]:
    """MRR@10 per set kueri — mutu yang dirasakan pengguna, bukan recall internal."""
    if not eval_file.exists():
        return {"catatan": f"{eval_file} tidak ada — mutu tingkat dokumen dilewati"}
    sets = yaml.safe_load(eval_file.read_text(encoding="utf-8")) or {}
    conn = sqlite3.connect(settings.catalog_db)
    conn.row_factory = sqlite3.Row
    out: dict[str, Any] = {}
    try:
        for set_name, queries in sets.items():
            rr, hits, n = [], [], 0
            for item in queries:
                relevant: set[str] = set()
                for frag in item.get("relevan", []):
                    relevant |= {r[0] for r in conn.execute(
                        "SELECT doc_id FROM kb_document_view WHERE tentang LIKE ? OR judul LIKE ?",
                        (f"%{frag}%", f"%{frag}%"))}
                if not relevant:
                    continue
                ranked = [h.doc_id for h in vs.search(item["q"], method, k=k)]
                rr.append(next((1.0 / i for i, d in enumerate(ranked[:10], 1) if d in relevant), 0.0))
                hits.append(float(bool(ranked[:1]) and ranked[0] in relevant))
                n += 1
            if n:
                out[set_name] = {"n": n, "mrr10": round(sum(rr) / n, 3),
                                 "hit1": round(sum(hits) / n, 3)}
    finally:
        conn.close()
    return out


# --------------------------------------------------------------------------
def run_benchmark(settings: Settings, *, dsn: str | None = None, k: int = 10, runs: int = 30,
                  method: str | None = None, limit_chunks: int | None = None,
                  with_pg: bool = True, padded_dim: int = 1536,
                  progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    say = progress or (lambda m: None)
    vs = VectorService(settings)
    if vs.store is None:
        raise RuntimeError(f"basis data vektor belum ada di {vector_paths(settings)['db']} — "
                           f"jalankan 'hero vector build' lebih dulu")
    method = method or ("semantic" if vs.ready("semantic") else "lsa")
    if not vs.ready(method):
        raise RuntimeError(f"indeks '{method}' belum dibangun — jalankan 'hero vector build'")

    emb = vs.embedder(method)
    queries = _queries(EVAL_FILE, FALLBACK_QUERIES)
    say(f"{len(queries)} kueri · metode {method} · k={k}")
    qvecs = [np.asarray(emb.embed_query(q), dtype=np.float32) for q in queries]

    report: dict[str, Any] = {
        "korpus": vs.store.stats(),
        "model": {"metode": method, "dim": int(getattr(emb, "dim", 0)),
                  "nama": getattr(emb, "model_name", method),
                  "mode": getattr(emb, "mode", "?")},
        "kueri": {"jumlah": len(queries), "k": k, "contoh": queries[:3]},
    }
    say("sqlite: numpy vs sqlite-vec…")
    sqlite_res, truth = bench_sqlite(vs, method, qvecs, k, runs)
    report["sqlite"] = sqlite_res

    say("mutu tingkat dokumen (MRR@10)…")
    report["mutu"] = bench_quality(settings, vs, method, k)

    if with_pg:
        rows = vs.store.conn.execute(
            f"SELECT c.rowid, c.doc_id, c.ref, e.vec FROM chunk c JOIN emb_{method} e "
            f"USING (rowid) ORDER BY c.rowid" + (f" LIMIT {int(limit_chunks)}" if limit_chunks else "")
        ).fetchall()
        chunks = [(int(r[0]), r[1], r[2], np.frombuffer(r[3], dtype=np.float32)) for r in rows]
        if limit_chunks:
            # Acuan recall harus dihitung ulang pada himpunan yang sama.
            keep = {c[0] for c in chunks}
            truth = [[rid for rid in t if rid in keep] for t in truth]
        try:
            report["pgvector"] = bench_pgvector(dsn, chunks, qvecs, truth, k, runs,
                                                padded_dim=padded_dim, progress=say)
        except Exception as exc:                                  # noqa: BLE001
            log.warning("pgvector dilewati: %s", exc)
            report["pgvector"] = {"galat": str(exc)}
    else:
        report["pgvector"] = {"galat": "dilewati (--tanpa-pg)"}

    say("penyimpanan…")
    report["penyimpanan"] = _storage(settings, report)
    report["markdown"] = render(report)
    return report


def _storage(settings: Settings, report: dict[str, Any]) -> dict[str, Any]:
    kb = Path(settings.knowledge_base)
    pdf_mb = sum(p.stat().st_size for p in kb.rglob("*.pdf")) / 1e6 if kb.exists() else 0.0
    cat = Path(settings.catalog_db)
    pgv = report.get("pgvector") or {}
    return {
        "pdf_asli_mb": round(pdf_mb, 1),
        "katalog_sqlite_mb": round(cat.stat().st_size / 1e6, 2) if cat.exists() else 0.0,
        "vektor_sqlite_mb": report["sqlite"]["ukuran_mb"],
        "vektor_postgres_mb": pgv.get("tabel_mb", 0.0),
        "vektor_postgres_padded_mb": (pgv.get("padding") or {}).get("tabel_mb", 0.0),
    }


# --------------------------------------------------------------------------
def _ms(x: dict | None) -> str:
    if not x or "p50" not in x:
        return "—"
    return f"{x['p50']:.2f} ms (p95 {x['p95']:.2f})"


def render(r: dict[str, Any]) -> str:
    c, m, q = r["korpus"], r["model"], r["kueri"]
    sq, pgv, sto = r["sqlite"], r.get("pgvector") or {}, r["penyimpanan"]
    o: list[str] = [
        "# Benchmark penyimpanan vektor — SQLite vs Postgres/pgvector",
        "",
        f"*Dihasilkan `hero bench vektor` pada {time.strftime('%d %B %Y %H:%M')}. Semua angka "
        "diukur di mesin yang menjalankannya; jalankan ulang di server sebelum memakainya "
        "sebagai dasar keputusan.*",
        "",
        f"**Korpus:** {c.get('chunk')} potongan dari {c.get('dokumen')} dokumen · "
        f"model `{m['nama']}` ({m['dim']} dimensi, mode {m['mode']}) · "
        f"{q['jumlah']} kueri, top-{q['k']}.",
        "",
        "Vektor di kedua penyimpanan **identik** (diambil dari indeks yang sama), jadi yang "
        "dibandingkan adalah penyimpanan dan indeksnya — bukan modelnya.",
        "",
        "## 1. Latensi & mutu pencarian",
        "",
        "`recall@k` = berapa bagian dari k teratas pencarian *exact* yang juga ditemukan. "
        "1,00 berarti tidak ada yang terlewat; di bawah itu adalah ongkos indeks aproksimatif.",
        "",
        "| Penyimpanan & indeks | Latensi | recall@k | Catatan |",
        "|---|---:|---:|---|",
    ]
    for name, v in sq["mesin"].items():
        rec = v.get("recall")
        o.append(f"| SQLite — {name} | {_ms(v.get('latensi'))} | "
                 f"{f'{rec:.2f}' if rec is not None else '—'} | {v.get('catatan', '')} |")
    if "galat" in pgv:
        o.append(f"| Postgres pgvector | — | — | tidak diukur: {pgv['galat']} |")
    else:
        for name, v in pgv.get("indeks", {}).items():
            o.append(f"| Postgres — {name} | {_ms(v.get('latensi'))} | {v.get('recall', 0):.2f} | "
                     f"{'indeks dipakai' if 'Index Scan' in (v.get('rencana') or '') else 'seq scan'} |")
    o.append("")

    if "galat" not in pgv:
        o += [f"Server: {pgv.get('server')} · {pgv.get('baris')} baris dimuat dalam "
              f"{pgv.get('muat', {}).get('detik')} s lewat `COPY`.", ""]
        o += ["### Waktu & ukuran indeks", "", "| Indeks | Waktu bangun | Ukuran indeks |",
              "|---|---:|---:|"]
        seen = set()
        for name, v in pgv.get("indeks", {}).items():
            b = v.get("bangun") or {}
            key = (b.get("indeks"), b.get("detik_bangun"))
            if key in seen or not b.get("detik_bangun"):
                continue
            seen.add(key)
            o.append(f"| {b.get('indeks')} {b.get('parameter')} | {b['detik_bangun']} s | "
                     f"{b.get('ukuran_mb')} MB |")
        o.append("")

    mutu = r.get("mutu") or {}
    if mutu and "catatan" not in mutu:
        o += ["### Mutu di tingkat dokumen (pencarian exact, metode " + m["metode"] + ")", "",
              "| Set kueri | n | Hit@1 | MRR@10 |", "|---|---:|---:|---:|"]
        for set_name, v in mutu.items():
            o.append(f"| {set_name} | {v['n']} | {v['hit1']:.2f} | {v['mrr10']:.2f} |")
        o += ["", "Angka ini **sama** untuk SQLite dan pgvector selama keduanya mencari exact — "
              "peringkatnya identik. Indeks aproksimatif menurunkannya sebanding dengan recall "
              "di tabel pertama.", ""]

    o += ["## 2. Penyimpanan", "", "| Komponen | Ukuran |", "|---|---:|",
          f"| PDF asli (knowledge base) | {sto['pdf_asli_mb']} MB |",
          f"| Katalog SQLite (metadata + teks + FTS) | {sto['katalog_sqlite_mb']} MB |",
          f"| Vektor di SQLite (BLOB + vec0 + cache) | {sto['vektor_sqlite_mb']} MB |"]
    if sto.get("vektor_postgres_mb"):
        o.append(f"| Vektor di Postgres ({m['dim']} dimensi) | {sto['vektor_postgres_mb']} MB |")
    if sto.get("vektor_postgres_padded_mb"):
        o.append(f"| Vektor di Postgres (zero-pad ke "
                 f"{(pgv.get('padding') or {}).get('dimensi')} dimensi) | "
                 f"{sto['vektor_postgres_padded_mb']} MB |")
    o.append("")
    for name, size in sorted(sq.get("rincian_mb", {}).items(), key=lambda kv: -kv[1])[:6]:
        o.append(f"- SQLite `{name}`: {size} MB")
    o.append("")

    pad = pgv.get("padding") or {}
    if pad:
        native = sto.get("vektor_postgres_mb") or 0.0
        extra = pad.get("tabel_mb", 0.0) - native
        o += ["### Harga kolom 1536 dimensi", "",
              f"Kolom `articles.embedding` backend berdimensi {pad['dimensi']}, model ini "
              f"{m['dim']}. Vektor di-zero-pad. Recall terhadap pencarian pada dimensi asli: "
              f"**{pad.get('recall_vs_native', 0):.2f}** — padding nol tidak mengubah cosine "
              f"similarity untuk vektor ber-norma 1, jadi 1,00 adalah hasil yang diharapkan "
              f"dan bukan kebetulan.",
              "",
              f"Yang terbuang hanya ruang dan waktu: {pad.get('tabel_mb')} MB vs {native} MB "
              f"(**+{extra:.1f} MB**, {(pad.get('tabel_mb', 0) / native - 1) * 100:.0f}% lebih besar) "
              f"dan latensi exact {_ms(pad.get('latensi_exact'))} vs "
              f"{_ms((pgv.get('indeks', {}).get('tanpa indeks (exact)') or {}).get('latensi'))}.",
              "",
              "Pilihannya ada dua, keduanya sah:",
              "",
              f"1. **Biarkan 1536.** Tidak ada kehilangan mutu, biaya hanya ruang. Pilih ini "
              f"bila dimensi model masih mungkin berubah.",
              f"2. **Samakan kolom dengan model** ({m['dim']} dimensi) lewat migrasi aditif: "
              f"tambah kolom baru `embedding_{m['dim']}`, isi, pindahkan pembacaan, baru "
              f"hapus yang lama. Hemat ruang, tetapi mengunci pilihan model.",
              ""]

    # Rekomendasi diturunkan dari angka, bukan dari selera.
    o += ["## 3. Bacaan hasil", ""]
    npy = (sq["mesin"].get("numpy (matriks di memori)") or {}).get("latensi") or {}
    exact_pg = ((pgv.get("indeks") or {}).get("tanpa indeks (exact)") or {}).get("latensi") or {}
    if npy and exact_pg:
        ratio = exact_pg.get("p50", 0) / max(npy.get("p50", 1e-9), 1e-9)
        o.append(f"- Pada korpus sebesar ini, NumPy di memori {npy['p50']:.2f} ms vs pgvector "
                 f"exact {exact_pg['p50']:.2f} ms (**{ratio:.0f}×**). Keduanya exact. Selisih ini "
                 f"adalah ongkos jaringan + parsing SQL, bukan ongkos algoritma.")
    ann = {n: v for n, v in (pgv.get("indeks") or {}).items()
           if n.startswith(("IVFFlat", "HNSW"))}
    if "galat" in pgv:
        o.append(f"- Sisi Postgres **tidak diukur** pada jalan ini ({pgv['galat']}), jadi "
                 f"perbandingan penyimpanan di laporan ini belum lengkap. Jalankan ulang "
                 f"dengan Postgres+pgvector terjangkau (`HERO_PG_DSN`) sebelum memakainya "
                 f"sebagai dasar keputusan.")
    elif not ann:
        o.append("- Indeks aproksimatif tidak terukur pada jalan ini.")
    else:
        aman = {n: v for n, v in ann.items() if v.get("recall", 0) >= 0.95}
        if aman:
            name, v = min(aman.items(), key=lambda kv: (kv[1].get("latensi") or {}).get("p50", 1e9))
            o.append(f"- Indeks aproksimatif tercepat yang masih menjaga recall ≥ 0,95: "
                     f"**{name}** — {_ms(v.get('latensi'))}, recall {v['recall']:.2f}.")
        else:
            terbaik = max(ann.items(), key=lambda kv: kv[1].get("recall", 0))
            o.append(f"- **Tidak ada** indeks aproksimatif yang menjaga recall ≥ 0,95 di korpus "
                     f"ini (terbaik: {terbaik[0]}, recall {terbaik[1].get('recall', 0):.2f}). "
                     f"Itu wajar — IVFFlat/HNSW baru membayar ongkos recall-nya di ratusan ribu "
                     f"potongan. Di bawah itu pencarian exact lebih cepat **dan** lebih benar.")
    o += [
        "- Keputusannya bukan \"SQLite atau Postgres\", melainkan **siapa yang bertanya**: "
        "pencarian dari frontend lewat backend sebaiknya dijawab pgvector (satu sumber data, "
        "satu izin akses, tidak ada salinan yang bisa basi); pekerjaan lapisan data — "
        "harmonisasi per pasal, kalibrasi ambang, benchmark — jalan di SQLite karena ia ada di "
        "mesin yang sama dengan modelnya dan tidak membebani basis data produksi.",
        "- Angka di atas kecil karena korpusnya kecil. Yang perlu diukur ulang saat korpus "
        f"tumbuh: latensi exact pgvector (linear terhadap jumlah baris) dan titik di mana HNSW "
        "mulai menang.",
        "",
    ]
    return "\n".join(o)
