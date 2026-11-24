"""CLI for the data workstream: scan acceptance, frontend snapshot, harmonisasi.

Kept apart from ``cli.py`` so each workstream's commands stay readable.
Registered on the main app in ``cli.py``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.table import Table

from hero.config import load_settings
from hero.kb.catalog import Catalog

console = Console()
CONFIG_OPT = typer.Option("config/sources.yaml", "--config", "-c")

akses_app = typer.Typer(help="Klasifikasi akses dokumen: publik harus terbukti, bukan diasumsikan.")
harmonisasi_app = typer.Typer(help="Harmonisasi draft vs Knowledge Base, per pasal (URD 3.4).")
scan_app = typer.Typer(help="Indeks hasil scan tanpa unduh: ukuran berkas & kriteria penerimaan (MoM #4).")
uat_app = typer.Typer(help="Set uji UAT Fase 2: skenario 1.480 + 20 dokumen (MoM #7).")


@scan_app.command("ukur")
def scan_ukur(
    source: str = typer.Option(None, "--source", "-s", help="jdih-ojk | ojk-regulasi | ojk-rancangan"),
    limit: int = typer.Option(None, "--limit", "-n", help="Sampel N berkas (dibagi rata per host)"),
    refresh: bool = typer.Option(False, "--refresh", help="Ukur ulang yang sudah diperiksa"),
    config: Path = CONFIG_OPT,
) -> None:
    """Isi ukuran berkas tiap rekaman inventaris lewat HEAD (tanpa mengunduh)."""
    from hero.ingest.probe import probe_inventory

    settings = load_settings(config)
    rep = probe_inventory(settings, source=source, limit=limit, refresh=refresh,
                          say=lambda m: console.print(f"[dim]{m}[/]"))
    console.print(f"Diperiksa {rep.checked} · ukuran diketahui {rep.sized} · "
                  f"gagal {rep.failed} · tanpa berkas {rep.skipped_no_file}")
    for e in rep.errors[:10]:
        console.print(f"  [yellow]•[/] {e}")


@scan_app.command("penerimaan")
def scan_penerimaan(
    ground_truth: Path = typer.Option("config/ground_truth.yaml", "--ground-truth", "-g"),
    out: Path = typer.Option(None, "--out", "-o", help="Tulis JSON hasil ke berkas ini"),
    config: Path = CONFIG_OPT,
) -> None:
    """Jumlah dokumen terindeks (URL+nama+nama berkas+ukuran) vs ground truth DPEA."""
    from hero.ingest.probe import acceptance

    settings = load_settings(config)
    gt = yaml.safe_load(ground_truth.read_text(encoding="utf-8")) if ground_truth.exists() else {}
    cat = Catalog(settings.catalog_db)
    rows = acceptance(cat, gt or {})
    cat.close()
    t = Table(title="Kriteria penerimaan scraping — terindeks tanpa unduh", header_style="bold cyan")
    for col in ("Sumber", "Rekaman", "URL", "Nama dok.", "Nama berkas", "Ukuran",
                "Terindeks", "Ground truth", "Rasio"):
        t.add_column(col, justify="left" if col == "Sumber" else "right")
    for r in rows:
        t.add_row(r["source"], *(f"{r[k]:,}".replace(",", ".") for k in
                  ("rekaman", "url", "nama_dokumen", "nama_berkas", "ukuran", "terindeks")),
                  r["ground_truth"] or "—",
                  f"{r['rasio_terhadap_gt']:.2f}×" if r.get("rasio_terhadap_gt") else "—")
    console.print(t)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[green]✓[/] {out}")


def register_penamaan(penamaan_app: typer.Typer) -> None:
    """Attach data-analysis commands to the existing ``hero penamaan`` group."""

    @penamaan_app.command("bentrok")
    def penamaan_bentrok(config: Path = CONFIG_OPT) -> None:
        """Seberapa sering tiap urutan tombol Nama/Tahun/Jenis/Bidang menghasilkan nama kembar."""
        from hero.dq.naming_collision import from_catalog

        settings = load_settings(config)
        cat = Catalog(settings.catalog_db)
        rows = from_catalog(cat.conn)
        cat.close()
        t = Table(title="Nama berkas kembar per format (inventaris)", header_style="bold cyan")
        for col in ("Sumber", "Urutan komponen", "Rekaman", "Kembar", "…peraturan sama",
                    "…beda peraturan", "%"):
            t.add_column(col, justify="left" if col in ("Sumber", "Urutan komponen") else "right")
        for r in rows:
            t.add_row(r.source, r.komponen, str(r.rekaman), str(r.bentrok),
                      str(r.bentrok_sumber), str(r.bentrok_nyata), f"{r.persen_nyata:.1%}")
        console.print(t)
        console.print("[dim]'peraturan sama' = sumber mencantumkan peraturan yang sama dua kali "
                      "(reg_key sama) — bukan kelemahan format.[/]")


@akses_app.command("audit")
def akses_audit(
    apply_: bool = typer.Option(False, "--apply", help="Terapkan usulan (hanya mengetatkan)"),
    semua: bool = typer.Option(False, "--semua", help="Tampilkan juga yang tidak berubah"),
    config: Path = CONFIG_OPT,
) -> None:
    """Periksa label akses tiap dokumen terhadap bukti publik; tanpa --apply = dry-run."""
    import sqlite3

    from hero.kb.access import apply, audit
    from hero.kb.readmodel import sync

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db, timeout=60) as conn:
        findings = audit(conn)
        t = Table(title="Audit klasifikasi akses", header_style="bold cyan")
        for col in ("Sumber", "Judul", "Sekarang", "Usulan", "Alasan"):
            t.add_column(col, overflow="fold")
        for f in findings:
            if f.berubah or semua:
                t.add_row(f.sumber, f.judul[:60], f.sekarang,
                          f"[red]{f.usulan}[/]" if f.berubah else f.usulan, f.alasan)
        console.print(t)
        n = sum(f.berubah for f in findings)
        console.print(f"{len(findings)} dokumen · {n} perlu diketatkan")
        if apply_ and n:
            apply(conn, findings)
            rep = sync(conn)
            console.print(f"[green]✓[/] {n} dokumen diubah · read model dibangun ulang {rep.rebuilt}")


def snapshot_cmd(
    out: Path = typer.Option("data/export/frontend-snapshot", "--out", "-o"),
    config: Path = CONFIG_OPT,
) -> None:
    """Rekam respons API (dokumen publik saja) ke JSON statis untuk pengembangan frontend."""
    from hero.kb.snapshot import build_snapshot

    m = build_snapshot(load_settings(config), out)
    console.print(f"[green]✓[/] {m['dokumen']} dokumen publik ({m['dokumen_disembunyikan']} "
                  f"disembunyikan) · {m['berkas']} berkas · {m['ukuran_byte'] / 1e6:.1f} MB → {out}")
    for f in m["gagal"]:
        console.print(f"  [yellow]•[/] {f}")


@harmonisasi_app.command("jalankan")
def harmonisasi_jalankan(
    draft: str = typer.Argument(..., help="doc_id di katalog, atau path PDF draft"),
    out: Path = typer.Option(None, "--out", "-o", help="Simpan laporan JSON"),
    aturan: Path = typer.Option("config/harmonisasi.yaml", "--aturan"),
    config: Path = CONFIG_OPT,
) -> None:
    """Bandingkan satu draft dengan seluruh KB: kandidat, rujukan, temuan per pasal."""
    import sqlite3

    from hero.harmonisasi.engine import draft_from_catalog, draft_from_pdf, harmonise, load_config

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        d = draft_from_pdf(Path(draft), settings) if Path(draft).is_file() \
            else draft_from_catalog(conn, draft)
        rep = harmonise(conn, d, load_config(aturan))
    console.print(f"[bold]{d.judul[:110]}[/] · {rep.ringkasan['pasal_draft']} pasal · "
                  f"korpus {rep.ringkasan['pasal_korpus']} pasal · {rep.waktu_detik:.2f} s")
    k = Table(title="Kandidat pembanding", header_style="bold cyan")
    for col in ("Skor", "Peraturan", "Alasan"):
        k.add_column(col, overflow="fold")
    for c in rep.kandidat:
        k.add_row(f"{c['skor']:.2f}", (c["judul"] or "")[:70], "; ".join(c["alasan"]))
    console.print(k)
    t = Table(title="Temuan per pasal — DRAFT / REKOMENDASI", header_style="bold cyan")
    for col in ("Pasal", "Jenis", "Keyakinan", "Pembanding", "Alasan"):
        t.add_column(col, overflow="fold")
    for f in rep.temuan:
        p = f.pembanding or {}
        t.add_row(f.pasal_draft, f.jenis, f"{f.tingkat} ({f.keyakinan:.2f})",
                  f"{p.get('pasal', '')} {(p.get('judul') or '')[:40]}".strip() or "—", f.alasan)
    console.print(t)
    for r in rep.rekomendasi:
        console.print(f"[yellow]•[/] {r}")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rep.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        console.print(f"[green]✓[/] {out}")


@harmonisasi_app.command("siapkan-semantik")
def harmonisasi_siapkan_semantik(
    unduh: bool = typer.Option(False, "--unduh", help="Unduh model bila belum ada (±0,22 GB)"),
    aturan: Path = typer.Option("config/harmonisasi.yaml", "--aturan"),
    config: Path = CONFIG_OPT,
) -> None:
    """Siapkan kemiripan makna (#67): model lokal + cache embedding seluruh pasal korpus.

    Dijalankan sekali di server (dan setelah korpus bertambah banyak); tanpa ini harmonisasi tetap
    jalan secara leksikal. Tidak ada teks yang dikirim ke luar server."""
    import sqlite3
    import time

    from hero.harmonisasi import semantik
    from hero.harmonisasi.engine import _lengkapi_semantik, load_config, load_corpus
    from hero.vector.embedders import SEMANTIC_MODELS

    settings = load_settings(config)
    cfg = load_config(aturan)
    with sqlite3.connect(settings.catalog_db, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        _lengkapi_semantik(conn, cfg)
        sc = cfg["semantik"]
        hf = (SEMANTIC_MODELS.get(sc["model"]) or {"hf": sc["model"]})["hf"]
        if not semantik.model_lokal_ada(Path(sc["models_dir"]), hf):
            if not unduh:
                console.print(f"[red]Model {hf} belum ada di {sc['models_dir']}[/] — ulangi dengan --unduh")
                raise typer.Exit(1)
            console.print(f"Mengunduh {hf} ke {sc['models_dir']} …")
            semantik.unduh(sc["model"], Path(sc["models_dir"]))
        teks = [c.teks for c in load_corpus(conn, cfg, None, None)]
    t0 = time.perf_counter()
    for i in range(0, len(teks), 500):
        semantik.vektor(teks[i:i + 500], cfg)
        console.print(f"  {min(i + 500, len(teks))}/{len(teks)} pasal", end="\r")
    console.print(f"\n[green]✓[/] cache makna siap: {len(teks)} pasal · {time.perf_counter() - t0:.0f} s · "
                  f"{sc['cache']}")


@harmonisasi_app.command("siapkan-uji")
def harmonisasi_siapkan(
    pasangan: int = typer.Option(12, "--pasangan", "-n"),
    unduh: bool = typer.Option(False, "--unduh", help="Unduh dokumen yang belum ada ke KB"),
    config: Path = CONFIG_OPT,
) -> None:
    """Pilih pasangan peraturan perubahan ↔ induk dari register publik untuk evaluasi."""
    import sqlite3

    from hero.harmonisasi.evaluate import find_pairs, prepare

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db, timeout=60) as conn:
        pairs = find_pairs(conn, limit=pasangan)
    for p in pairs:
        a, b = p["perubahan"], p["induk"]
        console.print(f"{a['reg_key']:16} {'✓' if a['doc_id'] else '·'}  →  "
                      f"{b['reg_key']:16} {'✓' if b['doc_id'] else '·'}")
    if unduh:
        console.print(prepare(settings, pairs, say=lambda m: console.print(f"[dim]{m}[/]")))


@harmonisasi_app.command("evaluasi")
def harmonisasi_evaluasi(
    pasangan: int = typer.Option(12, "--pasangan", "-n"),
    out: Path = typer.Option("docs/HARMONISASI_EVALUASI.md", "--out", "-o"),
    aturan: Path = typer.Option("config/harmonisasi.yaml", "--aturan"),
    seluruh_kb: bool = typer.Option(False, "--seluruh-kb",
                                    help="Abaikan kata kunci relasi; bandingkan ke seluruh KB "
                                         "(skenario peraturan baru, untuk kalibrasi ambang)"),
    config: Path = CONFIG_OPT,
) -> None:
    """Recall & kalibrasi ambang dari pasangan perubahan ↔ induk (TD-07, FR-HRM-12)."""
    import sqlite3

    from hero.harmonisasi.evaluate import run, write_markdown

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db, timeout=60) as conn:
        res = run(conn, settings, aturan, limit=pasangan, terarah=False if seluruh_kb else None)
    write_markdown(res, out)
    k = res["kalibrasi_objek_sama"]
    pr = res["presisi_rentang"]
    console.print(f"[{res['mode']}] {res['pasangan']} pasangan · recall {res['recall_deteksi']} · "
                  f"tampil≥{pr['ambang_tampil_75']} kutip≥{pr['ambang_kutip_50']} · "
                  f"induk #1 {res['kandidat_induk_peringkat_1']} · ambang disarankan "
                  f"{k.get('ambang')} (AUC {k.get('auc')}) → {out}")


def ekstrak_ulang_cmd(
    doc: list[str] = typer.Option(None, "--doc", help="doc_id (boleh berulang)"),
    terdampak: bool = typer.Option(False, "--terdampak",
                                   help="Semua dokumen yang terdampak perbaikan ekstraksi"),
    apply_: bool = typer.Option(False, "--apply", help="Jalankan; tanpa ini hanya daftar"),
    config: Path = CONFIG_OPT,
) -> None:
    """Ekstraksi ulang dokumen tersimpan (teks, metadata, pasal) + identitas dari register."""
    import sqlite3

    from hero.kb.readmodel import sync
    from hero.kb.reextract import affected, reextract

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db, timeout=60) as conn:
        reasons = affected(conn) if terdampak else {}
    ids = list(dict.fromkeys((doc or []) + list(reasons)))
    for i in ids:
        console.print(f"  {i[:12]}  {'; '.join(reasons.get(i, ['diminta']))}")
    console.print(f"{len(ids)} dokumen")
    if not apply_ or not ids:
        return
    results = reextract(settings, ids, reasons)
    t = Table(title="Hasil ekstraksi ulang", header_style="bold cyan")
    for col in ("Dokumen", "Sebelum", "Sesudah", "Rujukan tanpa nomor", "Catatan"):
        t.add_column(col, overflow="fold")
    for r in results:
        b, a = r.sebelum, r.sesudah
        t.add_row(r.judul[:50], f"{b.get('jenis')} {b.get('nomor')}",
                  f"{a.get('jenis')} {a.get('nomor')}" if a else "—",
                  str(a.get("rujukan_tanpa_nomor", "—")), r.error or "; ".join(r.alasan))
    console.print(t)
    with sqlite3.connect(settings.catalog_db, timeout=60) as conn:
        rep = sync(conn, full=True)
    console.print(f"[green]✓[/] read model dibangun ulang ({rep.rebuilt}). Lanjutkan dengan "
                  "`hero graph build`, `hero analisa --semua`, dan `hero vector build`.")


@uat_app.command("siapkan")
def uat_siapkan(
    sisihkan: int = typer.Option(20, "--sisihkan", "-n",
                                 help="Jumlah dokumen yang disisihkan sebagai test case."),
    seed: str = typer.Option("uat-fase2", "--seed",
                             help="Benih pemilihan; sama benih = sama pilihan."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Tulis manifes JSON."),
    config: Path = CONFIG_OPT,
) -> None:
    """Skenario uji Pak Faris: sisihkan N dokumen, sisanya ke KB (MoM #7)."""
    import sqlite3

    from hero.dq.uat import siapkan

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db, timeout=60) as conn:
        hasil = siapkan(conn, sisihkan=sisihkan, seed=seed)

    if not hasil["cukup"]:
        console.print(f"[yellow]Korpus belum cukup:[/] {hasil['alasan']}")
        raise typer.Exit(1)

    console.print(f"[bold]Skenario UAT[/] · benih '{hasil['seed']}' · "
                  f"{hasil['total_dokumen']} dokumen terindeks")
    console.print(f"  muat ke KB lebih dulu : {hasil['muat_ke_kb']}")
    console.print(f"  disisihkan (fase A)   : {hasil['disisihkan']} "
                  f"({hasil['kasus_sulit_disisihkan']} kasus sulit: hasil pindai/OCR)")
    console.print(f"  uji duplikat (fase B) : {len(hasil['fase_b_duplikat'])}")
    console.print(f"  sebaran jenis         : {hasil['sebaran_jenis_disisihkan']}")
    if hasil["harapan_tidak_lengkap"]:
        console.print(f"  [yellow]harapan tak lengkap  : {hasil['harapan_tidak_lengkap']} "
                      "dokumen identitasnya belum terbaca — pakai sebagai kasus koreksi "
                      "manual (US-20), bukan kriteria lulus[/]")

    t = Table(title="Fase A — 'terbaca atau tidak?'", header_style="bold cyan")
    for col in ("Dokumen", "Harapan jenis/nomor/tahun", "Hal", "Sulit", "Kriteria"):
        t.add_column(col, overflow="fold")
    for k in hasil["fase_a_keterbacaan"]:
        h = k["harapan"]
        t.add_row(k["doc_id"][:12], f"{h['jenis']} {h['nomor']} / {h['tahun']}",
                  str(h["jumlah_halaman"]), "ya" if k["sulit"] else "",
                  "lulus/gagal" if k["harapan_lengkap"] else "koreksi manual")
    console.print(t)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(hasil, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[green]✓[/] manifes ditulis: {out}")
    else:
        console.print("[dim]Tambahkan --out data/export/uat-fase2.json untuk menyimpan manifes.[/]")

