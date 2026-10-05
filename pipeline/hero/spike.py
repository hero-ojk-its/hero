"""SPIKE #42 — waktu proses & retrieval: folder PDF vs vektor, ±2000 dokumen.

Pertanyaan mitra (Weekly #2): dulu DPEA menyimpan PDF dan harus OCR dulu;
begitu ribuan dokumen, prosesnya lambat karena setiap kali membuka satu per
satu. Vektor membuat retrieval cepat, tetapi surat resmi tetap harus
melampirkan PDF asli. ADR-01 memutuskan penyimpanan ganda. Spike ini memberi
angkanya pada dokumen nyata.

Satu lintasan atas korpus, titik ukur di 100/500/1000/2000 dokumen:

  Jalur PDF (sisi "bukti" ADR-01)   validasi → sha256 → identitas hal. 1 →
                                    nama baku → salin ke folder KB
  Ekstraksi (dipakai kedua indeks)  lapisan teks per halaman; halaman pindaian
                                    dihitung, biaya OCR-nya diestimasi dari sampel
  Indeks relasional                 FTS5 per dokumen (katalog)
  Indeks vektor                     pasal → potongan → LSA (deterministik) dan
                                    MiniLM (semantik), disimpan di VectorStore

  Retrieval per titik ukur          (a) tanpa indeks: buka setiap PDF & cari teks
                                    (b) FTS5 dokumen  (c) BM25 potongan
                                    (d) KNN LSA  (e) KNN semantik
                                    (f) lampirkan PDF asli: cari path → baca → verifikasi sha256

Yang TIDAK diukur di sini: mutu peringkat (lihat hero bench / retrieval-evaluation).
"""
from __future__ import annotations

import hashlib
import json
import random
import resource
import shutil
import sqlite3
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

QUERIES = [
    "batas waktu pelaporan insiden siber",
    "manajemen risiko teknologi informasi bank umum",
    "sanksi administratif berupa denda",
    "perlindungan data pribadi konsumen",
    "layanan pendanaan bersama berbasis teknologi informasi",
    "modal minimum bank perekonomian rakyat",
    "alih daya sistem elektronik kepada pihak ketiga",
    "laporan bulanan perusahaan pembiayaan",
    "tata kelola perusahaan asuransi",
    "penawaran umum efek bersifat utang",
    "program anti pencucian uang",
    "pusat data dan pusat pemulihan bencana",
]


# Bounded LSA fit (see LsaEmbedder): the unbounded fit does not fit in 2 GB RAM at 80k chunks.
LSA_FIT_SAMPLE = 8000
LSA_MAX_FEATURES = 50_000


def _rss_mb() -> float:
    v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss     # Linux: KiB, macOS: bytes
    return round(v / 1024 if sys.platform.startswith("linux") else v / 1e6, 1)


def _dir_mb(path: Path) -> float:
    return round(sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6, 1) if path.exists() else 0.0


def _ms(samples: list[float]) -> dict[str, float | None]:
    if not samples:
        return {"rata2_ms": None, "p95_ms": None}
    s = sorted(samples)
    return {"rata2_ms": round(1000 * statistics.fmean(s), 2),
            "p95_ms": round(1000 * s[min(len(s) - 1, int(0.95 * len(s)))], 2)}


@dataclass
class Clock:
    detik: dict[str, float] = field(default_factory=dict)

    def add(self, stage: str, seconds: float) -> None:
        self.detik[stage] = self.detik.get(stage, 0.0) + seconds

    def snapshot(self) -> dict[str, float]:
        return {k: round(v, 2) for k, v in self.detik.items()}


def _folder_scan(kb_dir: Path, query: str) -> tuple[float, int]:
    """No index at all: open every PDF and look for the query terms."""
    import pymupdf

    terms = [t for t in query.lower().split() if len(t) > 3]
    started, hits = time.perf_counter(), 0
    for pdf in kb_dir.rglob("*.pdf"):
        try:
            with pymupdf.open(pdf) as doc:
                text = " ".join(p.get_text() for p in doc).lower()
        except Exception:  # noqa: BLE001 — a broken file is a miss, not a crash
            continue
        hits += all(t in text for t in terms)
    return time.perf_counter() - started, hits


def _ocr_estimate(samples: list[tuple[Path, int]], ocr_settings) -> dict[str, Any]:
    from hero.extract.ocr import ocr_image, tesseract_available

    if not samples or not tesseract_available():
        return {"halaman_sampel": 0, "detik_per_halaman": None}
    import io

    import pymupdf
    from PIL import Image

    times = []
    for path, index in samples:
        with pymupdf.open(path) as doc:
            png = doc[index].get_pixmap(dpi=ocr_settings.dpi).tobytes("png")
        t = time.perf_counter()
        ocr_image(Image.open(io.BytesIO(png)), languages=ocr_settings.languages)
        times.append(time.perf_counter() - t)
    return {"halaman_sampel": len(times), "detik_per_halaman": round(statistics.fmean(times), 2)}


def run_spike(raw_dir: Path, work_dir: Path, *, checkpoints=(100, 500, 1000, 2000), label: str = "",
              semantic: bool = True, model_cache: Path | None = None, ocr_sample: int = 15,
              folder_scan_queries: int = 1, seed: int = 42, settings=None,
              progress: Callable[[str], None] = print) -> dict[str, Any]:
    import pymupdf

    from hero.config import Settings
    from hero.extract.firstpage import read_identity
    from hero.extract.pdf import is_pdf
    from hero.extract.structure import parse_structure
    from hero.kb.naming import DEFAULT_TEMPLATE, render_name, unique_path
    from hero.models import PageText
    from hero.vector.chunking import chunk_document
    from hero.vector.embedders import LsaEmbedder, SemanticEmbedder, semantic_available
    from hero.vector.store import VectorStore

    settings = settings or Settings()
    files = sorted(p for p in Path(raw_dir).rglob("*") if p.suffix.lower() == ".pdf")
    random.Random(seed).shuffle(files)          # checkpoints = random subsets, not alphabetical
    checkpoints = sorted({min(c, len(files)) for c in checkpoints})
    if work_dir.exists():
        shutil.rmtree(work_dir)
    kb_dir = work_dir / "kb"
    kb_dir.mkdir(parents=True)
    cat = sqlite3.connect(work_dir / "catalog.db")
    cat.executescript("""
        CREATE TABLE doc (doc_id TEXT PRIMARY KEY, sha256 TEXT UNIQUE, path TEXT, judul TEXT, pages INT);
        CREATE VIRTUAL TABLE doc_fts USING fts5(doc_id UNINDEXED, judul, text,
            tokenize='unicode61 remove_diacritics 2');
    """)
    store = VectorStore(work_dir / "vectors.db")
    use_semantic = semantic and semantic_available()
    sem = SemanticEmbedder(model_cache or work_dir / "models", model="minilm") if use_semantic else None

    clock = Clock()
    chunks_all: list = []
    scanned: list[tuple[Path, int]] = []
    totals = {"dokumen": 0, "duplikat": 0, "rusak": 0, "halaman": 0, "halaman_pindaian": 0,
              "pasal": 0, "potongan": 0}
    results: list[dict[str, Any]] = []
    started = time.perf_counter()
    cp_iter = iter(checkpoints)
    next_cp = next(cp_iter, None)

    for n, src in enumerate(files, 1):
        # -- 1. PDF path (ADR-01 "bukti") ---------------------------------
        t = time.perf_counter()
        ok = is_pdf(src)
        sha = hashlib.sha256(src.read_bytes()).hexdigest() if ok else None
        dup = ok and cat.execute("SELECT 1 FROM doc WHERE sha256 = ?", (sha,)).fetchone()
        ident = read_identity(src) if ok and not dup else None
        if ident is not None:
            name = render_name(DEFAULT_TEMPLATE, ident.values()) if ident.lengkap else f"_koreksi_{sha[:16]}.pdf"
            target = unique_path(kb_dir / name)
            shutil.copy2(src, target)
        clock.add("1_simpan_pdf", time.perf_counter() - t)
        if not ok:
            totals["rusak"] += 1
        elif dup:
            totals["duplikat"] += 1
        else:
            doc_id = sha[:32]
            # -- 2. text extraction ---------------------------------------
            t = time.perf_counter()
            pages: list[PageText] = []
            try:
                with pymupdf.open(target) as doc:
                    for i, page in enumerate(doc):
                        txt = page.get_text() or ""
                        pages.append(PageText(i + 1, txt, "text-layer"))
                        if len(txt.strip()) < 120:
                            totals["halaman_pindaian"] += 1
                            if len(scanned) < ocr_sample:
                                scanned.append((target, i))
            except Exception:  # noqa: BLE001
                totals["rusak"] += 1
            clock.add("2_ekstraksi_teks", time.perf_counter() - t)
            totals["halaman"] += len(pages)
            full = "\n".join(p.text for p in pages)
            # -- 3. structure ---------------------------------------------
            t = time.perf_counter()
            struct = parse_structure(pages)
            clock.add("3_struktur_pasal", time.perf_counter() - t)
            # -- 4. relational index (FTS5) -------------------------------
            t = time.perf_counter()
            judul = ident.judul.nilai or src.stem
            cat.execute("INSERT INTO doc VALUES (?,?,?,?,?)", (doc_id, sha, str(target), judul, len(pages)))
            cat.execute("INSERT INTO doc_fts VALUES (?,?,?)", (doc_id, judul, full))
            clock.add("4_indeks_fts", time.perf_counter() - t)
            # -- 5. chunking (vector path) --------------------------------
            t = time.perf_counter()
            arts = [(a.number, a.page, a.text) for a in struct.articles]
            chunks, _ = chunk_document(doc_id, judul=judul, tentang=ident.judul.nilai, ringkasan=None,
                                       articles=arts, sections=struct.sections, full_text=full)
            chunks_all.extend(chunks)
            clock.add("5_chunking", time.perf_counter() - t)
            totals["dokumen"] += 1
            totals["pasal"] += len(arts)
            totals["potongan"] += len(chunks)
            if n % 100 == 0:
                cat.commit()
                progress(f"{n}/{len(files)} berkas · {totals['potongan']} potongan · "
                         f"{time.perf_counter() - started:.0f}s · RSS {_rss_mb()} MB")

        if next_cp is not None and n == next_cp:
            cat.commit()
            results.append(_checkpoint(n, totals, clock, cat, store, chunks_all, sem, kb_dir, work_dir,
                                       folder_scan_queries, LsaEmbedder, settings, progress))
            next_cp = next(cp_iter, None)

    ocr = _ocr_estimate(scanned, settings.ocr)
    if ocr["detik_per_halaman"]:
        ocr["estimasi_detik_semua_pindaian"] = round(ocr["detik_per_halaman"] * totals["halaman_pindaian"], 1)
    cat.close()
    return {"korpus": {"label": label, "berkas_pdf": len(files), **totals}, "titik_ukur": results, "ocr": ocr,
            "semantik": "minilm" if sem else None, "rss_puncak_mb": _rss_mb(),
            "detik_total": round(time.perf_counter() - started, 1)}


def _checkpoint(n, totals, clock, cat, store, chunks_all, sem, kb_dir, work_dir, folder_scan_queries,
                LsaEmbedder, settings, progress) -> dict[str, Any]:
    progress(f"— titik ukur {n}: membangun indeks vektor ({len(chunks_all)} potongan)")
    build: dict[str, float] = {}
    t = time.perf_counter()
    store.replace_chunks(chunks_all)
    build["simpan_potongan_dan_bm25"] = time.perf_counter() - t
    t = time.perf_counter()
    lsa = LsaEmbedder(dim=settings.vector.lsa_dim, fit_sample=LSA_FIT_SAMPLE,
                      max_features=LSA_MAX_FEATURES).fit([c.text for c in chunks_all])
    store.index(lsa, use_cache=False)
    build["lsa_fit_dan_embed"] = time.perf_counter() - t
    sem_info = None
    if sem is not None:
        t = time.perf_counter()
        sem_info = store.index(sem)          # cache: only chunks new since the last checkpoint
        build["semantik_embed_baru"] = time.perf_counter() - t

    # -- retrieval ----------------------------------------------------------
    timings: dict[str, list[float]] = {k: [] for k in ("fts_dokumen", "bm25_potongan", "knn_lsa",
                                                         "knn_semantik", "lampirkan_pdf_asli")}
    for q in QUERIES:
        t = time.perf_counter()
        terms = " OR ".join(f'"{w}"' for w in q.split() if len(w) > 3)
        top = cat.execute("SELECT doc_id FROM doc_fts WHERE doc_fts MATCH ? ORDER BY bm25(doc_fts) LIMIT 10",
                          (terms,)).fetchall()
        timings["fts_dokumen"].append(time.perf_counter() - t)
        t = time.perf_counter()
        store.search(q, method="lexical", k=10)
        timings["bm25_potongan"].append(time.perf_counter() - t)
        t = time.perf_counter()
        hits = store.search(q, method="lsa", k=10, embedder=lsa)
        timings["knn_lsa"].append(time.perf_counter() - t)
        if sem is not None:
            t = time.perf_counter()
            hits = store.search(q, method="semantic", k=10, embedder=sem)
            timings["knn_semantik"].append(time.perf_counter() - t)
        # Attach the original: id → path → bytes → integrity check.
        doc_id = hits[0].doc_id if hits else (top[0][0] if top else None)
        if doc_id:
            t = time.perf_counter()
            path, sha = cat.execute("SELECT path, sha256 FROM doc d WHERE doc_id = ?", (doc_id,)).fetchone()
            data = Path(path).read_bytes()
            assert hashlib.sha256(data).hexdigest() == sha
            timings["lampirkan_pdf_asli"].append(time.perf_counter() - t)

    scan = [_folder_scan(kb_dir, q) for q in QUERIES[:folder_scan_queries]]
    out = {
        "dokumen": totals["dokumen"], "halaman": totals["halaman"], "potongan": len(chunks_all),
        "proses_kumulatif_detik": clock.snapshot(),
        "bangun_indeks_vektor_detik": {k: round(v, 2) for k, v in build.items()},
        "semantik": sem_info,
        "retrieval": {k: _ms(v) for k, v in timings.items()},
        "tanpa_indeks_detik_per_kueri": round(statistics.fmean(s for s, _ in scan), 2) if scan else None,
        "ukuran_mb": {"folder_pdf": _dir_mb(kb_dir),
                      "katalog_fts": round((work_dir / "catalog.db").stat().st_size / 1e6, 1),
                      "vektor_db": round(store.path.stat().st_size / 1e6, 1)},
        "rss_mb": _rss_mb(),
        "lsa": {"fit_sampel": LSA_FIT_SAMPLE, "maks_fitur": LSA_MAX_FEATURES, "dim": lsa.dim},
    }
    progress(json.dumps(out, ensure_ascii=False))
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def render(res: dict[str, Any], *, fetch: dict[str, Any] | None = None, host: str = "") -> str:
    k = res["korpus"]
    lines = [
        "# SPIKE #42 — Folder PDF vs Vektor pada ±2000 dokumen nyata",
        "",
        f"> Dihasilkan oleh `hero spike jalankan` · {host}",
        f"> Korpus: {k.get('label') or 'PDF'} — {k['berkas_pdf']} berkas → {k['dokumen']} dokumen unik "
        f"({k['duplikat']} duplikat isi, {k['rusak']} rusak), {k['halaman']:,} halaman, "
        f"{k['halaman_pindaian']:,} halaman tanpa lapisan teks, {k['potongan']:,} potongan vektor.",
        "",
        "## Waktu proses kumulatif (detik)",
        "",
    ]
    stages = sorted({s for r in res["titik_ukur"] for s in r["proses_kumulatif_detik"]})
    lines.append("| Dokumen | " + " | ".join(s[2:].replace("_", " ") for s in stages)
                 + " | indeks vektor (LSA) | embed semantik baru |")
    lines.append("|---:|" + "---:|" * (len(stages) + 2))
    for r in res["titik_ukur"]:
        b = r["bangun_indeks_vektor_detik"]
        lines.append(f"| {r['dokumen']} | " + " | ".join(str(r["proses_kumulatif_detik"].get(s, "")) for s in stages)
                     + f" | {round(b.get('simpan_potongan_dan_bm25', 0) + b.get('lsa_fit_dan_embed', 0), 1)}"
                     + f" | {b.get('semantik_embed_baru', '—')} |")
    lines += ["", "## Retrieval per kueri (rata-rata / p95, milidetik)", ""]
    keys = ["fts_dokumen", "bm25_potongan", "knn_lsa", "knn_semantik", "lampirkan_pdf_asli"]
    lines.append("| Dokumen | tanpa indeks (buka semua PDF) | " + " | ".join(x.replace("_", " ") for x in keys) + " |")
    lines.append("|---:|---:|" + "---:|" * len(keys))
    for r in res["titik_ukur"]:
        cells = []
        for x in keys:
            v = r["retrieval"][x]
            cells.append("—" if v["rata2_ms"] is None else f"{v['rata2_ms']} / {v['p95_ms']}")
        scan = r["tanpa_indeks_detik_per_kueri"]
        lines.append(f"| {r['dokumen']} | {scan:,} s | " + " | ".join(cells) + " |")
    lines += ["", "## Ukuran penyimpanan (MB)", "",
              "| Dokumen | folder PDF asli | katalog + FTS | basis vektor | RSS proses |", "|---:|---:|---:|---:|---:|"]
    for r in res["titik_ukur"]:
        u = r["ukuran_mb"]
        lines.append(f"| {r['dokumen']} | {u['folder_pdf']} | {u['katalog_fts']} | {u['vektor_db']} | {r['rss_mb']} |")
    o = res["ocr"]
    if o.get("detik_per_halaman"):
        lines += ["", f"**OCR:** {o['detik_per_halaman']} detik/halaman (sampel {o['halaman_sampel']} halaman, "
                      f"300 dpi). Seluruh {k['halaman_pindaian']:,} halaman tanpa lapisan teks ≈ "
                      f"{o['estimasi_detik_semua_pindaian'] / 3600:.1f} jam — dibayar **sekali** saat ingest."]
    if fetch:
        lines += ["", f"**Unduh dari sumber:** {fetch.get('berkas')} berkas, {fetch.get('mb')} MB dalam "
                      f"{fetch.get('detik')} s ≈ {fetch.get('detik_per_berkas')} s/berkas — biaya bila PDF "
                      "asli harus diambil ulang dari sumber setiap kali dilampirkan."]
    return "\n".join(lines) + "\n"
