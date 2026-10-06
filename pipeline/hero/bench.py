"""Relational vs vector vs graph, measured on this project's own data.

Three questions, each answered with numbers rather than opinion:

1. **Speed of the screens** — does the read model make the Knowledge Base
   table faster than deriving the same rows per request? (relational)
2. **Quality of search** — which retrieval finds the right regulation, for
   keyword queries and for paraphrased ones? (relational FTS vs vector)
3. **Relationship questions** — what does a graph answer that the others
   cannot, and at what cost? (graph)

Everything reported is measured at run time; the narrative in the Markdown
is chosen from the results, so re-running on a bigger knowledge base can
change the conclusions — which is the point of keeping it executable.
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Callable

import yaml

from hero.config import Settings
from hero.graph import query as gq
from hero.graph.build import build_graph
from hero.kb import readmodel as rm
from hero.vector import VectorService, vector_paths

EVAL_FILE = Path("config/eval_queries.yaml")


def _timeit(fn: Callable[[], Any], runs: int, warmup: int = 2) -> dict[str, float]:
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


# --------------------------------------------------------------------------
# 1. Relational: naive per-request derivation vs read model
# --------------------------------------------------------------------------
def _naive_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """What an API does without a read model: derive every row per request."""
    out = []
    for d in conn.execute("SELECT * FROM documents WHERE status IN ('ingested','failed')").fetchall():
        t = conn.execute("SELECT structure, analysis, updated_at FROM document_text WHERE doc_id = ?",
                         (d["doc_id"],)).fetchone()
        out.append(rm.build_row(d, t))
    return out


def bench_relational(conn: sqlite3.Connection, runs: int) -> dict[str, Any]:
    read = rm.ReadModel(conn)
    read.sync_if_stale()

    def naive_list():
        rows = sorted(_naive_rows(conn), key=lambda r: r["ingested_at"] or "", reverse=True)
        return rows[:8]

    def naive_filter():
        rows = [r for r in _naive_rows(conn) if r["status"] == "berlaku"
                and "Pelaporan" in json.loads(r["topik_semua"])]
        return rows[:8]

    def naive_search():
        return conn.execute(
            "SELECT d.doc_id FROM documents d LEFT JOIN document_text t USING (doc_id) "
            "WHERE d.title LIKE ? OR d.subject LIKE ? OR t.analysis LIKE ? LIMIT 8",
            ("%karbon%",) * 3).fetchall()

    cases = {
        "Daftar KB (halaman 1)": (naive_list, lambda: read.list(page_size=8)),
        "Filter status + topik": (naive_filter,
                                  lambda: read.list(status=["berlaku"], topik=["Pelaporan"], page_size=8)),
        "Kotak cari 'karbon'": (naive_search, lambda: read.list(q="karbon", page_size=8)),
        "Opsi filter (facets)": (lambda: _naive_rows(conn), read.facets),
        "Laci detail dokumen": (lambda: _naive_rows(conn)[0],
                                lambda: read.get(read.list(page_size=1)["items"][0]["id"])),
    }
    results = {}
    for name, (naive, fast) in cases.items():
        results[name] = {"naif": _timeit(naive, max(5, runs // 3)), "read_model": _timeit(fast, runs)}
    return results


# --------------------------------------------------------------------------
# 2. Retrieval quality and latency
# --------------------------------------------------------------------------
def _resolve_relevant(conn: sqlite3.Connection, fragments: list[str]) -> set[str]:
    ids: set[str] = set()
    for frag in fragments:
        ids |= {r[0] for r in conn.execute(
            "SELECT doc_id FROM kb_document_view WHERE tentang LIKE ? OR judul LIKE ?",
            (f"%{frag}%", f"%{frag}%"))}
    return ids


def _metrics(ranked: list[str], relevant: set[str]) -> dict[str, float]:
    rr = next((1.0 / i for i, d in enumerate(ranked[:10], 1) if d in relevant), 0.0)
    return {"hit1": float(bool(ranked[:1]) and ranked[0] in relevant),
            "recall5": len(relevant & set(ranked[:5])) / len(relevant) if relevant else 0.0,
            "mrr10": rr}


def bench_retrieval(conn: sqlite3.Connection, vs: VectorService, runs: int,
                    eval_file: Path = EVAL_FILE) -> dict[str, Any]:
    sets = yaml.safe_load(eval_file.read_text(encoding="utf-8"))
    read = rm.ReadModel(conn)
    methods: dict[str, Callable[[str], list[str]]] = {
        "kotak_cari_ui": lambda q: [i["id"] for i in read.list(q=q, sort="relevansi", page_size=10)["items"]],
    }
    for m in ("lexical", "lsa", "semantic", "hybrid"):
        if vs.ready(m):
            methods[m] = (lambda mm: lambda q: [h.doc_id for h in vs.search(q, mm, k=10)])(m)

    quality: dict[str, dict[str, Any]] = {}
    skipped = []
    for set_name, queries in sets.items():
        per_method = {m: {"hit1": [], "recall5": [], "mrr10": []} for m in methods}
        details = []
        for item in queries:
            relevant = _resolve_relevant(conn, item["relevan"])
            if not relevant:
                skipped.append(item["q"])
                continue
            row = {"q": item["q"], "relevan": len(relevant)}
            for m, fn in methods.items():
                met = _metrics(fn(item["q"]), relevant)
                for k, v in met.items():
                    per_method[m][k].append(v)
                row[m] = met["mrr10"]
            details.append(row)
        quality[set_name] = {
            "n": len(details),
            "metode": {m: {k: round(sum(v) / len(v), 3) if v else 0.0 for k, v in s.items()}
                       for m, s in per_method.items()},
            "rincian": details,
        }

    probe = "kewajiban bank menyampaikan laporan kepada otoritas"
    latency: dict[str, Any] = {"kotak_cari_ui": _timeit(lambda: methods["kotak_cari_ui"](probe), runs)}
    store = vs.store
    if store is not None:
        latency["lexical (FTS5 per potongan)"] = _timeit(lambda: store.lexical(probe, 120), runs)
        for m in ("lsa", "semantic"):
            if not vs.ready(m):
                continue
            emb = vs.embedder(m)
            latency[f"{m}: embed kueri"] = _timeit(lambda: emb.embed_query(probe), runs)
            qv = emb.embed_query(probe)
            for engine in ("sqlite-vec", "numpy"):
                try:
                    latency[f"{m}: KNN {engine}"] = _timeit(lambda: store.knn(m, qv, 120, engine=engine), runs)
                except Exception as exc:  # noqa: BLE001 — engine unavailable on this machine
                    latency[f"{m}: KNN {engine}"] = {"galat": str(exc)}
        if vs.ready("hybrid"):
            latency["hybrid (ujung-ke-ujung)"] = _timeit(lambda: vs.search(probe, "hybrid", k=10), runs)
    return {"kualitas": quality, "latensi": latency, "dilewati": skipped,
            "kueri_latensi": probe}


# --------------------------------------------------------------------------
# 3. Graph questions
# --------------------------------------------------------------------------
def bench_graph(conn: sqlite3.Connection, runs: int) -> dict[str, Any]:
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='graph_node'").fetchone():
        build_graph(conn)
    target = "UU|21|2011"
    cte = gq.impact(conn, target, max_depth=3)

    edges = conn.execute("SELECT src, dst FROM graph_edge WHERE rel = 'BERDASAR'").fetchall()
    incoming: dict[str, list[str]] = defaultdict(list)
    for s, d in edges:
        incoming[d].append(s)

    def bfs(adj):
        seen, q = {target: 0}, deque([target])
        while q:
            cur = q.popleft()
            if seen[cur] >= 3:
                continue
            for nxt in adj.get(cur, ()):
                if nxt not in seen:
                    seen[nxt] = seen[cur] + 1
                    q.append(nxt)
        return len(seen) - 1

    def bfs_cold():
        adj: dict[str, list[str]] = defaultdict(list)
        for s, d in conn.execute("SELECT src, dst FROM graph_edge WHERE rel = 'BERDASAR'"):
            adj[d].append(s)
        return bfs(adj)

    like_rows = conn.execute(
        "SELECT record_key FROM inventory WHERE fields_json LIKE '%21 Tahun 2011%'").fetchall()
    graph_1hop = {n["key"] for n in cte if n["kedalaman"] == 1}
    like_keys = {r[0] for r in like_rows}
    graph_1hop_records = {r[0] for r in conn.execute(
        f"SELECT record_key FROM graph_node WHERE key IN ({','.join('?' for _ in graph_1hop)}) "
        f"AND record_key IS NOT NULL", list(graph_1hop))} if graph_1hop else set()

    key = conn.execute("SELECT n.key FROM graph_node n JOIN graph_edge e ON e.dst = n.key "
                       "AND e.rel = 'MENCABUT' AND e.sebagian = 0 LIMIT 1").fetchone()[0]
    return {
        "dampak_uu21": {
            "target": target,
            "hasil": {"langsung": len(graph_1hop), "total_3_level": len(cte),
                      "per_level": {d: sum(1 for n in cte if n["kedalaman"] == d) for d in (1, 2, 3)}},
            "latensi": {"recursive CTE (SQLite)": _timeit(lambda: gq.impact(conn, target, 3), runs),
                        "BFS Python, graf dimuat per kueri": _timeit(bfs_cold, runs),
                        "BFS Python, graf sudah di memori": _timeit(lambda: bfs(incoming), runs),
                        "LIKE teks (tanpa graf, 1 level)": _timeit(lambda: conn.execute(
                            "SELECT record_key FROM inventory WHERE fields_json LIKE '%21 Tahun 2011%'"
                        ).fetchall(), runs)},
            "tanpa_graf": {"like_cocok": len(like_keys), "graf_1level_di_register": len(graph_1hop_records),
                           "irisan": len(like_keys & graph_1hop_records),
                           "like_saja": len(like_keys - graph_1hop_records),
                           "graf_saja": len(graph_1hop_records - like_keys)},
        },
        "lineage": {"contoh": key, "latensi": _timeit(lambda: gq.lineage(conn, key), runs)},
        "statistik": gq.stats(conn),
    }


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
def _table_sizes(path: Path) -> dict[str, float]:
    """Bytes per table via SQLite's dbstat (absent in some builds → {})."""
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT name, SUM(pgsize) FROM dbstat GROUP BY name").fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return {n: round(s / 1e6, 2) for n, s in rows}


def bench_storage(settings: Settings) -> dict[str, Any]:
    cat = Path(settings.catalog_db)
    vec = vector_paths(settings)["db"]
    kb = Path(settings.knowledge_base)
    pdf_mb = sum(p.stat().st_size for p in kb.rglob("*.pdf")) / 1e6 if kb.exists() else 0.0
    sizes = _table_sizes(cat)
    group = lambda prefix: round(sum(v for k, v in sizes.items() if k.startswith(prefix)), 2)
    return {
        "pdf_knowledge_base_mb": round(pdf_mb, 1),
        "katalog_mb": round(cat.stat().st_size / 1e6, 2),
        "katalog_rincian_mb": {
            "teks dokumen (document_text + FTS)": round(group("document_text") + group("document_fts"), 2),
            "register (inventory)": group("inventory"),
            "pasal (articles)": group("articles"),
            "read model (kb_*)": group("kb_"),
            "graf (graph_*)": group("graph_"),
        },
        "vektor_mb": round(vec.stat().st_size / 1e6, 2) if vec.exists() else 0.0,
        "vektor_rincian_mb": _table_sizes(vec) if vec.exists() else {},
    }


# --------------------------------------------------------------------------
def run_benchmark(settings: Settings, *, runs: int = 30, progress=None) -> dict[str, Any]:
    say = progress or (lambda m: None)
    conn = sqlite3.connect(settings.catalog_db)
    conn.row_factory = sqlite3.Row
    vs = VectorService(settings)
    say("relasional: read model vs derivasi per-request…")
    rel = bench_relational(conn, runs)
    say("temu-kembali: kualitas dan latensi…")
    ret = bench_retrieval(conn, vs, runs)
    say("graf: dampak, lineage…")
    gr = bench_graph(conn, runs)
    say("penyimpanan…")
    sto = bench_storage(settings)
    corpus = {"dokumen": conn.execute("SELECT COUNT(*) FROM kb_document_view").fetchone()[0],
              "register": conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0],
              "pasal": conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0],
              "potongan_vektor": vs.store.stats()["chunk"] if vs.store else 0}
    from hero.vector.embedders import SEMANTIC_MODELS
    model_key = settings.vector.semantic_model
    report = {"korpus": corpus, "relasional": rel, "temu_kembali": ret, "graf": gr, "penyimpanan": sto,
              "model": {"key": model_key, **SEMANTIC_MODELS.get(model_key, {})}}
    report["markdown"] = render(report)
    return report


# --------------------------------------------------------------------------
def _ms(x: dict) -> str:
    return f"{x['p50']:.2f} ms (p95 {x['p95']:.2f})" if "p50" in x else f"— ({x.get('galat', '?')})"


def render(r: dict[str, Any]) -> str:
    c, rel, ret, gr, sto = r["korpus"], r["relasional"], r["temu_kembali"], r["graf"], r["penyimpanan"]
    o: list[str] = [
        "# Perbandingan Relasional · Vektor · Graf — HERO",
        "",
        f"*Dihasilkan oleh `hero bench` pada {time.strftime('%d %B %Y %H:%M')}. Semua angka diukur, "
        "bukan diperkirakan; jalankan ulang setelah knowledge base bertambah — kesimpulan bisa berubah.*",
        "",
        f"**Korpus:** {c['dokumen']} dokumen di KB · {c['register']} rekaman register · "
        f"{c['pasal']} pasal · {c['potongan_vektor']} potongan terindeks vektor.",
        "",
        "## 1. Relasional: read model untuk layar Knowledge Base",
        "",
        "Pembanding *naif* = menurunkan setiap baris (ringkasan, topik, urgensi, dll.) dari JSON "
        "analisis **pada setiap request**. *Read model* = baris yang sama, dihitung sekali saat "
        "ingest, disimpan di kolom berindeks.",
        "",
        "| Operasi layar | Naif (p50) | Read model (p50) | Lebih cepat |",
        "|---|---:|---:|---:|",
    ]
    for name, v in rel.items():
        n, f = v["naif"]["p50"], v["read_model"]["p50"]
        o.append(f"| {name} | {n:.2f} ms | {f:.2f} ms | **{n / f:.0f}×** |" if f else f"| {name} | {n} | {f} | – |")
    o += ["", "Selisih ini tumbuh linear terhadap jumlah dokumen pada cara naif, sedangkan read model "
          "tetap dibatasi indeks dan `LIMIT` — pada ribuan dokumen, cara naif tidak lagi layak dipakai "
          "untuk tabel interaktif.", ""]

    o += ["## 2. Temu-kembali: kata kunci vs vektor", "",
          "Diukur pada `config/eval_queries.yaml`. **Recall@5** = bagian dokumen relevan yang muncul "
          "di 5 teratas; **MRR@10** = rata-rata 1/peringkat dokumen relevan pertama (1,0 = selalu di "
          "posisi pertama).", ""]
    mdl = r.get("model", {})
    mname = mdl.get("key", "semantik")
    names = {"kotak_cari_ui": "Kotak cari UI (FTS5, semua kata → fallback)",
             "lexical": "Leksikal BM25 (FTS5, kata apa saja)", "lsa": "Vektor LSA (deterministik)",
             "semantic": f"Vektor semantik {mname} (AI-Assisted)", "hybrid": "Hibrida RRF (BM25 + semantik)"}
    winners = {}
    for set_name, q in ret["kualitas"].items():
        o += [f"### Set `{set_name}` ({q['n']} kueri)", "",
              "| Metode | Hit@1 | Recall@5 | MRR@10 |", "|---|---:|---:|---:|"]
        best = max(q["metode"].items(), key=lambda kv: kv[1]["mrr10"])
        winners[set_name] = best[0]
        for m, met in q["metode"].items():
            bold = "**" if m == best[0] else ""
            o.append(f"| {bold}{names.get(m, m)}{bold} | {met['hit1']:.2f} | {met['recall5']:.2f} | "
                     f"{bold}{met['mrr10']:.2f}{bold} |")
        o.append("")
    if ret.get("dilewati"):
        o += [f"> Kueri tanpa dokumen relevan di KB (dilewati): {', '.join(ret['dilewati'])}", ""]

    kk, pf = ret["kualitas"].get("kata_kunci", {}), ret["kualitas"].get("parafrase", {})
    def score(s, m):
        return s.get("metode", {}).get(m, {}).get("mrr10", 0.0)
    o += ["**Bacaan hasil:**", ""]
    o.append(f"- Pada kueri kata kunci, metode terbaik adalah **{names.get(winners.get('kata_kunci'), '?')}** "
             f"(MRR {score(kk, winners.get('kata_kunci', '')):.2f}).")
    o.append(f"- Pada kueri parafrase, metode terbaik adalah **{names.get(winners.get('parafrase'), '?')}** "
             f"(MRR {score(pf, winners.get('parafrase', '')):.2f}); kotak cari UI yang mewajibkan semua "
             f"kata hanya {score(pf, 'kotak_cari_ui'):.2f} — kueri berbahasa sehari-hari hampir tak pernah "
             f"memuat semua kata judul.")
    margin = 0.05   # below this, 24 queries cannot tell two methods apart
    sem_gain = {k: score(v, "semantic") - score(v, "lexical") for k, v in (("kk", kk), ("pf", pf))}
    if "semantic" in (pf.get("metode") or {}):
        if sem_gain["pf"] > margin:
            o.append(f"- Semantik mengungguli BM25 pada parafrase ({sem_gain['pf']:+.2f} MRR) — "
                     "manfaat pencarian makna terbukti di tempat kata kunci gagal.")
        else:
            o.append(f"- **Semantik tidak mengungguli BM25**, bahkan pada parafrase ({sem_gain['pf']:+.2f} "
                     f"MRR; kata kunci {sem_gain['kk']:+.2f}). Pada korpus dan model ini, pencarian makna "
                     "belum membayar biayanya sebagai metode tunggal.")
    if "hybrid" in (pf.get("metode") or {}):
        hyb_gain = score(pf, "hybrid") - score(pf, "lexical")
        o.append(f"- Hibrida RRF: {score(kk, 'hybrid'):.2f} (kata kunci) dan {score(pf, 'hybrid'):.2f} "
                 f"(parafrase), selisih {hyb_gain:+.2f} terhadap BM25 pada parafrase"
                 + (" — perbaikan nyata." if hyb_gain > margin else
                    " — dalam batas yang tidak bisa dibedakan dari BM25 dengan 12 kueri."))
    o.append("")

    o += ["### Latensi pencarian (kueri tunggal, sudah hangat)", "",
          f"Kueri: *\"{ret['kueri_latensi']}\"*", "", "| Tahap | Latensi |", "|---|---:|"]
    for k, v in ret["latensi"].items():
        o.append(f"| {k} | {_ms(v)} |")
    lat = ret["latensi"]
    sv, npy = lat.get("semantic: KNN sqlite-vec", {}), lat.get("semantic: KNN numpy", {})
    if "p50" in sv and "p50" in npy:
        o += ["", f"Pencarian tetangga terdekat: NumPy pada matriks di memori {npy['p50']:.2f} ms vs "
              f"`sqlite-vec` {sv['p50']:.2f} ms (**{sv['p50'] / max(npy['p50'], 1e-6):.0f}×**). Keduanya "
              "pencarian *eksak*. Karena matriksnya kecil, HERO memakai NumPy secara default dan beralih ke "
              "`sqlite-vec` hanya bila indeks terlalu besar untuk disimpan di memori. Indeks aproksimatif "
              "(HNSW) baru relevan di ratusan ribu potongan.", ""]

    g = gr["dampak_uu21"]
    o += ["## 3. Graf: pertanyaan yang tidak bisa dijawab dua cara lain", "",
          f"**\"Jika {g['target']} berubah, peraturan mana yang terdampak?\"** — mengikuti relasi "
          "BERDASAR (dasar hukum) secara berantai.", "",
          f"- Langsung (1 level): **{g['hasil']['langsung']}** · total sampai 3 level: "
          f"**{g['hasil']['total_3_level']}** (per level: {g['hasil']['per_level']})", "",
          "| Cara | Latensi |", "|---|---:|"]
    for k, v in g["latensi"].items():
        o.append(f"| {k} | {_ms(v)} |")
    gl = g["latensi"]
    cte, mem = gl["recursive CTE (SQLite)"]["p50"], gl["BFS Python, graf sudah di memori"]["p50"]
    o += ["", f"Recursive CTE {cte:.2f} ms vs BFS di memori {mem:.2f} ms. Graf di memori lebih cepat, "
          "tetapi harus dimuat dan dijaga tetap sinkron di setiap proses; CTE membaca langsung dari "
          "tabel yang selalu mutakhir. Pada beberapa milidetik, CTE sudah cukup untuk interaksi "
          "pengguna — memori baru layak bila traversal dijalankan ribuan kali per detik."]
    t = g["tanpa_graf"]
    o += ["", f"**Tanpa graf** — mencari teks \"21 Tahun 2011\" di register dengan `LIKE`: "
          f"{t['like_cocok']} rekaman cocok. Dibanding 1 level graf ({t['graf_1level_di_register']} rekaman "
          f"register): {t['irisan']} sama, **{t['like_saja']} hanya ditemukan LIKE** (menyebut angka itu "
          f"tapi bukan sebagai dasar hukum, atau UU lain bernomor sama), dan **{t['graf_saja']} hanya "
          "ditemukan graf** (dirujuk lewat dokumen dan bagian Mengingat). LIKE juga tidak bisa "
          "melanjutkan ke level 2 dan 3 sama sekali.", ""]
    lg = gr["lineage"]
    o += [f"**Lineage** (\"sudah diganti dengan apa?\") untuk `{lg['contoh']}`: {_ms(lg['latensi'])}.", ""]
    st = gr["statistik"]
    o += [f"Graf: {st.get('node')} node, edge {st.get('edge')}, konflik identitas "
          f"{st.get('konflik_identitas')}.", ""]

    s = sto
    o += ["## 4. Penyimpanan", "", "| Komponen | Ukuran |", "|---|---:|",
          f"| PDF asli di knowledge base | {s['pdf_knowledge_base_mb']} MB |",
          f"| Katalog SQLite (seluruhnya) | {s['katalog_mb']} MB |"]
    for k, v in s["katalog_rincian_mb"].items():
        o.append(f"| — {k} | {v} MB |")
    o += [f"| Basis data vektor (terpisah) | {s['vektor_mb']} MB |", "",
          "Indeks vektor lebih besar dari metadata katalog karena setiap pasal disimpan beberapa kali "
          "(BLOB, tabel `vec0`, dan cache embedding). Itu data turunan: boleh dihapus dan dibangun "
          "ulang kapan saja dari katalog, jadi tidak perlu ikut dicadangkan.", ""]

    # Recommend the retrieval method with the best *average* over both sets,
    # so a method cannot win the row by excelling on one kind of query only.
    candidates = [m for m in ("lexical", "lsa", "semantic", "hybrid") if m in (pf.get("metode") or {})]
    avg = {m: (score(kk, m) + score(pf, m)) / 2 for m in candidates}
    best = max(avg, key=avg.get) if avg else "lexical"
    if best != "lexical" and avg[best] - avg.get("lexical", 0) > margin:
        vector_row = (
            f"| Cari berdasarkan makna / parafrase (URD 3.4) | **{names.get(best)}** | "
            f"Rata-rata MRR terbaik {avg[best]:.2f} (kata kunci {score(kk, best):.2f}, parafrase "
            f"{score(pf, best):.2f}) vs BM25 {avg.get('lexical', 0):.2f} |")
    else:
        vector_row = ("| Cari berdasarkan makna / parafrase (URD 3.4) | **BM25 dengan fallback; vektor "
                      "sebagai opsi AI-Assisted** | Vektor belum terbukti lebih baik dari BM25 pada set ini |")
    ranking = " · ".join(f"{names.get(m)} {v:.2f}" for m, v in sorted(avg.items(), key=lambda kv: -kv[1]))
    o += ["## 5. Kesimpulan untuk HERO", "",
          "| Kebutuhan | Pilihan | Dasar dari angka di atas |", "|---|---|---|",
          "| Tabel, filter, detail Knowledge Base | **Relasional + read model** | "
          f"{min(v['naif']['p50'] / v['read_model']['p50'] for v in rel.values()):.0f}–"
          f"{max(v['naif']['p50'] / v['read_model']['p50'] for v in rel.values()):.0f}× lebih cepat dari derivasi per-request |",
          "| Kotak cari saat pengguna mengetik | **FTS5, semua kata → fallback sebagian kata** | "
          f"Semua kata: MRR {score(kk, 'kotak_cari_ui'):.2f} pada kata kunci; fallback menutup parafrase |",
          vector_row,
          "| Dasar hukum, pencabutan, dampak perubahan | **Graf** | Satu-satunya yang menjawab rantai "
          f"multi-level; LIKE menghasilkan {t['like_saja']} kecocokan palsu pada 1 level saja |", "",
          f"Rata-rata MRR kedua set: {ranking}.", "",
          "Ketiganya bukan pesaing; masing-masing menjawab jenis pertanyaan berbeda, dan ketiganya "
          "hidup di SQLite yang sama — tanpa server basis data tambahan di VPS.", "",
          "### Keterbatasan pengukuran ini", "",
          f"- Korpus kecil ({c['dokumen']} dokumen), didominasi pasar modal. Kualitas temu-kembali "
          "perlu diukur ulang saat KB tumbuh.",
          f"- Set evaluasi {sum(q['n'] for q in ret['kualitas'].values())} kueri, disusun satu orang. "
          "Tambahkan kueri dari pengguna sebenarnya (unit DPEA) untuk hasil yang lebih dapat dipercaya.",
          f"- Model semantik: `{mdl.get('hf', mname)}` ({mdl.get('dim', '?')} dimensi, "
          f"±{mdl.get('ukuran_gb', '?')} GB). Potongan dibuat 80 kata agar muat di model terkecil "
          "(MiniLM, 128 token); e5 membaca hingga 512 token, jadi jendela yang lebih panjang mungkin "
          "lebih baik untuknya — belum diuji.",
          ""]
    return "\n".join(o)
