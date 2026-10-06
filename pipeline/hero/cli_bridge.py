"""Perintah ``hero bridge …`` — mengoperasikan jembatan ke backend tim.

Dipisah dari ``cli.py`` seperti ``cli_data.py``: satu alur kerja, satu berkas.
Didaftarkan pada aplikasi utama di ``cli.py``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from hero.config import load_settings

console = Console()
bridge_app = typer.Typer(help="Jembatan ke backend tim: pindai (push), ekstraksi, sinkron, layanan.")
CONFIG_OPT = typer.Option("config/sources.yaml", "--config", "-c")


def _ctx(config: Path, **overrides):
    from hero.bridge.config import load_bridge_settings

    settings = load_settings(config)
    bridge = load_bridge_settings(config, **overrides)
    return settings, bridge


def _say(msg: str) -> None:
    console.print(f"[dim]{msg}[/]")


# ---------------------------------------------------------------------------
@bridge_app.command("status")
def status(
    config: Path = CONFIG_OPT,
    json_out: Optional[Path] = typer.Option(None, "--json"),
) -> None:
    """Apa yang tersambung, apa yang belum, dan apa langkah berikutnya."""
    from hero.bridge.client import BackendClient, BackendError
    from hero.bridge.state import BridgeState, default_path

    settings, bridge = _ctx(config)
    out: dict = {"konfigurasi": bridge.redacted()}

    t = Table(title="Jembatan HERO ↔ backend", header_style="bold cyan", show_lines=False)
    t.add_column("Bagian")
    t.add_column("Keadaan")
    for k, v in bridge.redacted().items():
        t.add_row(k, str(v))

    client = BackendClient(bridge)
    try:
        health = client.health()
        out["backend"] = health
        t.add_row("backend /health", f"{health.get('status')} · db {health.get('database')} · "
                                     f"migrasi {'ok' if health.get('migrations_up_to_date') else 'belum'} · "
                                     f"crawler {health.get('crawler_backend')}")
        crawler = health.get("crawler_backend")
        if crawler == "push":
            t.add_row("pindai", "backend mode push — jalankan 'hero bridge pindai --loop'")
        else:
            t.add_row("pindai", f"backend memakai crawler '{crawler}' untuk semua sumber "
                                f"(JDIH, ojk.go.id, OneDrive, folder); 'hero bridge pindai' tidak perlu")
    except BackendError as exc:
        out["backend"] = {"galat": str(exc)}
        t.add_row("backend /health", f"[red]{escape(str(exc))}[/]")
    try:
        ok = client.ping_internal()
        out["kunci_internal"] = ok
        t.add_row("kunci API internal", "[green]diterima[/]" if ok else "[red]ditolak (401)[/]")
    except BackendError as exc:
        out["kunci_internal"] = f"galat: {exc}"
        t.add_row("kunci API internal", f"[red]{escape(str(exc))}[/]")
    client.close()

    st = BridgeState(default_path(settings))
    summ = st.summary()
    peta = len(st.doc_map())
    st.close()
    out["buku_besar"] = summ | {"dokumen_terpeta": peta}
    t.add_row("buku besar worker", f"{summ['ekstraksi']} · pasal terkirim {summ['pasal_terkirim']} · "
                                   f"vektor {summ['vektor_terkirim']} · halaman pasal "
                                   f"{summ['halaman_pasal_tercatat']}")
    t.add_row("cermin korpus", f"{peta} dokumen backend terpeta ke katalog")

    try:
        from hero.bridge import pg

        conn = pg.connect()
        out["postgres"] = {"server": pg.server_version(conn),
                           "dimensi_kolom": pg.embedding_dim(conn),
                           **pg.articles_stats(conn)}
        conn.close()
        p = out["postgres"]
        t.add_row("pgvector", f"{p['server']} · pasal {p['pasal']} "
                              f"({p['berembedding']} berembedding) · kolom {p['dimensi_kolom']} dim · "
                              f"{p['ukuran_mb']} MB")
    except Exception as exc:                                      # noqa: BLE001
        out["postgres"] = {"galat": str(exc)}
        t.add_row("pgvector", f"[yellow]tidak diperiksa: {escape(str(exc))}[/]")

    console.print(t)
    if json_out:
        json_out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[green]JSON ditulis:[/] {json_out}")


# ---------------------------------------------------------------------------
@bridge_app.command("pindai")
def pindai(
    loop: bool = typer.Option(False, "--loop", help="Terus polling (untuk systemd service)."),
    batch: Optional[int] = typer.Option(None, "--batch", help="Jumlah batch sebelum berhenti."),
    limit: Optional[int] = typer.Option(None, "--limit", help="Sesi diklaim per putaran (1-5)."),
    tanpa_ukuran: bool = typer.Option(False, "--tanpa-ukuran",
                                      help="Lewati probe HEAD ukuran berkas (lebih cepat)."),
    maks_kandidat: Optional[int] = typer.Option(
        None, "--maks-kandidat",
        help="Batas kandidat per sesi (anggaran kesopanan scraping; 0 = ikuti backend)."),
    config: Path = CONFIG_OPT,
) -> None:
    """Layani sesi pemindaian backend dengan adapter HERO (JDIH, postback OJK, dsb.)."""
    from hero.bridge.scan_worker import ScanWorker

    cap = None if maks_kandidat is None else (maks_kandidat or None)
    settings, bridge = _ctx(config, claim_scans=limit)
    if maks_kandidat is not None:
        bridge.max_candidates_cap = cap
    w = ScanWorker(settings, bridge, probe_sizes=not tanpa_ukuran)
    try:
        outs = (w.run_forever(max_batches=batch, progress=_say) if loop
                else w.run_once(progress=_say))
    finally:
        w.close()
    if not outs:
        console.print("[dim]tidak ada sesi pemindaian di antrian.[/]")
        return
    for o in outs:
        console.print(("[green]✓[/] " if o.status == "selesai" else "[red]✗[/] ") + o.line())
        for e in o.errors[:5]:
            console.print(f"    [yellow]•[/] {e}")


# ---------------------------------------------------------------------------
@bridge_app.command("ekstraksi")
def ekstraksi(
    loop: bool = typer.Option(False, "--loop", help="Terus polling (untuk systemd service)."),
    batch: Optional[int] = typer.Option(None, "--batch", help="Jumlah batch sebelum berhenti."),
    limit: Optional[int] = typer.Option(None, "--limit", help="Dokumen diklaim per putaran (1-50)."),
    embedder: Optional[str] = typer.Option(None, "--embedder", help="lsa | semantic | none."),
    config: Path = CONFIG_OPT,
) -> None:
    """Ambil antrian ekstraksi backend: OCR → metadata → pasal → vektor → kirim balik."""
    from hero.bridge.extract_worker import ExtractionWorker

    settings, bridge = _ctx(config, claim_documents=limit, embedder=embedder)
    w = ExtractionWorker(settings, bridge)
    try:
        rep = (w.run_forever(max_batches=batch, progress=_say) if loop
               else w.run_once(progress=_say))
    finally:
        w.close()
    d = rep.as_dict()
    if not rep.claimed:
        console.print("[dim]antrian ekstraksi kosong.[/]")
        return
    console.print(f"[bold]{d['diklaim']} dokumen[/] · {d['per_status']} · "
                  f"{d['pasal']} pasal · {d['vektor']} vektor · {d['detik']} s")


# ---------------------------------------------------------------------------
@bridge_app.command("sinkron")
def sinkron(
    dokumen: Optional[list[int]] = typer.Option(None, "--dokumen", "-d",
                                                help="ID dokumen backend tertentu (boleh berulang)."),
    limit: Optional[int] = typer.Option(None, "--limit", help="Batas jumlah dokumen."),
    tanpa_draft: bool = typer.Option(False, "--tanpa-draft", help="Lewati dokumen draft_kajian."),
    vektor: bool = typer.Option(False, "--vektor", help="Bangun ulang indeks vektor setelah sinkron."),
    analisa: bool = typer.Option(False, "--analisa", help="Jalankan analisa Fase 2 untuk semua dokumen."),
    tanpa_graf: bool = typer.Option(False, "--tanpa-graf",
                                    help="Jangan bangun ulang graf relasi peraturan."),
    config: Path = CONFIG_OPT,
) -> None:
    """Cermin korpus backend (dokumen + pasal) ke katalog, agar mesin analisa bisa bekerja."""
    import sqlite3

    from hero.bridge.sync import mirror

    settings, bridge = _ctx(config)
    rep = mirror(settings, limit=limit, document_ids=dokumen or None,
                 include_drafts=not tanpa_draft, progress=_say)
    d = rep.as_dict()
    console.print(f"[green]Cermin:[/] {d['dokumen']} dokumen ({d['draft']} draft) · "
                  f"{d['pasal']} pasal · halaman pasal terisi {d['halaman_pasal_terisi']}, "
                  f"kosong {d['halaman_pasal_kosong']} · {d['detik']} s")
    if d["dilewati_tanpa_teks"]:
        console.print(f"[yellow]{d['dilewati_tanpa_teks']} dokumen dilewati[/] "
                      f"(belum punya teks maupun pasal — belum diekstraksi)")
    for g in d["galat"]:
        console.print(f"  [yellow]•[/] {escape(str(g))}")
    if d["halaman_pasal_kosong"]:
        console.print("[dim]Halaman pasal kosong = pasal itu tidak diekstraksi oleh worker ini, "
                      "jadi nomor halamannya tidak diketahui (tabel articles backend belum punya "
                      "kolom halaman). Lihat docs/INTEGRASI_BACKEND.md §Celah kontrak.[/]")

    # Graf relasi dibangun ulang secara default: harmonisasi memakainya untuk
    # menjawab "peraturan yang dirujuk draft ini masih berlaku atau sudah
    # dicabut?" (FR-HRM-03/04). Tanpa graf, status rujukan jadi tidak diketahui.
    if not tanpa_graf:
        import sqlite3 as _sq

        from hero.graph.build import build_graph

        with _sq.connect(settings.catalog_db) as conn:
            g = build_graph(conn)
        console.print(f"[green]Graf:[/] {g}")

    if analisa:
        from hero.analysis import analyse_all

        with sqlite3.connect(settings.catalog_db) as conn:
            hasil = analyse_all(conn)
        console.print(f"[green]Analisa:[/] {len(hasil)} dokumen · "
                      f"{sum(len(a.poin) for a in hasil)} poin kunci")
    if vektor:
        from hero.vector import build_vectors

        res = build_vectors(settings, progress=_say)
        console.print(f"[green]Vektor:[/] {res['chunk']} potongan · {res['detik_total']} s")


# ---------------------------------------------------------------------------
@bridge_app.command("vektor-isi")
def vektor_isi(
    apply: bool = typer.Option(False, "--apply", help="Tulis ke Postgres (tanpa ini: uji coba)."),
    limit: int = typer.Option(1000, "--limit", help="Maksimum pasal per jalan."),
    dokumen: Optional[list[int]] = typer.Option(None, "--dokumen", "-d"),
    ulang: bool = typer.Option(False, "--ulang",
                               help="Kosongkan semua vektor dulu (wajib saat GANTI model)."),
    embedder: Optional[str] = typer.Option(None, "--embedder", help="lsa | semantic."),
    config: Path = CONFIG_OPT,
) -> None:
    """Isi kolom articles.embedding backend untuk pasal yang belum punya vektor."""
    from hero.bridge.vectorize import backfill

    settings, bridge = _ctx(config, embedder=embedder)
    rep = backfill(settings, bridge, limit=limit, document_ids=dokumen or None,
                   apply=apply, reset=ulang, progress=_say)
    d = rep.as_dict()
    console.print(f"{'[yellow]UJI COBA[/] ' if rep.uji_coba else ''}"
                  f"kandidat {d['kandidat']} · diembed {d['diembed']} · ditulis {d['ditulis']} · "
                  f"model {d['embedder']} ({d['dimensi_model']} dim → kolom {d['dimensi_kolom']}) · "
                  f"{d['detik']} s")
    for g in rep.galat:
        console.print(f"  [red]•[/] {escape(str(g))}")
    if rep.uji_coba and rep.diembed:
        console.print("[dim]Tambahkan --apply untuk menuliskannya.[/]")


# ---------------------------------------------------------------------------
@bridge_app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8100, "--port"),
    cors: str = typer.Option("*", "--cors", help="Asal yang diizinkan, dipisah koma."),
    reload: bool = typer.Option(False, "--reload"),
    config: Path = CONFIG_OPT,
) -> None:
    """Jalankan layanan analisa & harmonisasi (dipasang sebagai /api/v1/ml/*)."""
    import os

    import uvicorn

    os.environ["HERO_CONFIG"] = str(config)
    os.environ["HERO_ML_CORS"] = cors
    console.print(f"[green]Layanan analisa[/] http://{host}:{port}/docs "
                  f"→ pasang di /api/v1/ml/* lewat reverse proxy")
    uvicorn.run("hero.bridge.ml_api:app_from_env", factory=True, host=host, port=port, reload=reload)


# ---------------------------------------------------------------------------
@bridge_app.command("sekali")
def sekali(
    config: Path = CONFIG_OPT,
    lewati_pindai: bool = typer.Option(False, "--lewati-pindai"),
) -> None:
    """Satu putaran lengkap: pindai → ekstraksi → sinkron. Dipakai systemd timer."""
    from hero.bridge.extract_worker import ExtractionWorker
    from hero.bridge.scan_worker import ScanWorker
    from hero.bridge.sync import mirror

    settings, bridge = _ctx(config)
    if not lewati_pindai:
        w = ScanWorker(settings, bridge)
        try:
            for o in w.run_once(progress=_say):
                console.print(o.line())
        finally:
            w.close()
    e = ExtractionWorker(settings, bridge)
    try:
        total = 0
        while True:
            rep = e.run_once(progress=_say)
            total += rep.claimed
            if not rep.claimed:
                break
        console.print(f"[green]Ekstraksi:[/] {total} dokumen diproses")
    finally:
        e.close()
    try:
        import sqlite3 as _sq

        from hero.graph.build import build_graph

        rep = mirror(settings, progress=_say)
        with _sq.connect(settings.catalog_db) as conn:
            build_graph(conn)
        console.print(f"[green]Cermin:[/] {rep.dokumen} dokumen · {rep.pasal} pasal")
    except Exception as exc:                                      # noqa: BLE001
        console.print(f"[yellow]Sinkron dilewati:[/] {escape(str(exc))}")
