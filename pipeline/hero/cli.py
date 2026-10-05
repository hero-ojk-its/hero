"""HERO command line interface."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.markup import escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from hero import __version__
from hero.config import FolderSource, SiteSource, load_settings
from hero.extract.ocr import available_languages, tesseract_available
from hero.extract.pdf import extract_pdf, extract_tables, probe_pdf
from hero.extract.metadata import extract_metadata
from hero.extract.structure import parse_structure
from hero.extract.summary import build_summary
from hero.extract.quality import assess_quality
from hero.kb.catalog import Catalog
from hero.pipeline import IngestPipeline, RunSummary

app = typer.Typer(
    add_completion=False,
    help="HERO — Harmonisasi & Analisa Regulasi Otomatis (baseline CLI).",
)
console = Console()

STATUS_STYLE = {
    "ingested": "green", "duplicate": "yellow",
    "rejected": "red", "failed": "red", "pending": "dim",
}


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(message)s", datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True,
                              show_path=False)],
    )


def _render_run(run: RunSummary, title: str) -> None:
    # Narrow terminals lose the subject entirely if every column is fixed, so
    # the optional columns only appear when there is room for them.
    wide = console.width >= 118
    table = Table(title=title, header_style="bold cyan", expand=True)
    table.add_column("Status", width=9, no_wrap=True)
    table.add_column("Jenis", width=6, no_wrap=True)
    table.add_column("Nomor", width=17, no_wrap=True)
    table.add_column("Hal", justify="right", width=4)
    if wide:
        table.add_column("OCR", justify="right", width=4)
        table.add_column("Kategori", width=18, no_wrap=True)
    # ratio=1 hands the leftover width to the subject instead of collapsing it.
    table.add_column("Judul / Tentang", ratio=1, min_width=22, overflow="ellipsis")

    for rec in run.records:
        md = rec.metadata
        subject = md.subject or md.title or rec.original_filename
        row = [
            f"[{STATUS_STYLE.get(rec.status, 'white')}]{rec.status}[/]",
            md.doc_type or "-",
            md.number or "-",
            str(rec.page_count or "-"),
        ]
        if wide:
            row += [f"{rec.ocr_pages}" if rec.ocr_pages else "-",
                    rec.category or "-"]
        row.append(subject)
        table.add_row(*row)
    if run.records:
        console.print(table)

    console.print(
        f"\n[bold]Ringkasan[/] run [cyan]{run.run_id}[/]: "
        f"[green]{run.ingested} masuk[/] · "
        f"[yellow]{run.duplicates} duplikat[/] · "
        f"[red]{run.rejected} ditolak[/]"
    )
    if run.errors:
        # Escape: source notes start with "[site name]", which Rich would
        # otherwise swallow as a markup tag and drop from the output.
        console.print(
            Panel("\n".join(f"• {escape(e)}" for e in run.errors[:25]),
                  title=f"Catatan sumber ({len(run.errors)})",
                  border_style="yellow"))


# ---------------------------------------------------------------------------
@app.command()
def version() -> None:
    """Show version and the status of optional dependencies."""
    console.print(f"[bold]HERO[/] v{__version__}")
    if not tesseract_available():
        console.print("OCR  : [red]tesseract tidak ditemukan[/] "
                      "(brew install tesseract tesseract-lang)")
        return

    settings = load_settings("config/sources.yaml")
    installed = set(available_languages())
    wanted = settings.ocr.languages.split("+")
    # Show only the languages HERO is configured to use; the full list runs
    # to well over a hundred entries.
    shown = ", ".join(
        f"[green]{code}[/]" if code in installed else f"[red]{code} (hilang)[/]"
        for code in wanted)
    console.print(f"OCR  : [green]tesseract siap[/] — bahasa dipakai: {shown} "
                  f"[dim](total {len(installed)} terpasang)[/]")


@app.command("sources")
def list_sources(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """List the manually-registered sources (URD 3.2)."""
    s = load_settings(config)
    table = Table(title="Sumber terdaftar", header_style="bold cyan", expand=True)
    table.add_column("Jalur", width=12)
    table.add_column("Nama", width=32)
    table.add_column("Aktif", width=6)
    table.add_column("Lokasi", overflow="fold")
    for site in s.sites:
        table.add_row("web", site.name,
                      "[green]ya[/]" if site.enabled else "[dim]tidak[/]", site.url)
    for f in s.folders:
        table.add_row("folder", f.name,
                      "[green]ya[/]" if f.enabled else "[dim]tidak[/]", f.path)
    for sh in s.onedrive_shares:
        table.add_row("onedrive", sh.name,
                      "[green]ya[/]" if sh.enabled else "[dim]tidak[/]", sh.share_url)
    console.print(table)
    console.print(f"Knowledge base: [cyan]{s.knowledge_base}[/]  ·  "
                  f"Katalog: [cyan]{s.catalog_db}[/]")


@app.command()
def scrape(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    url: Optional[list[str]] = typer.Option(
        None, "--url", "-u",
        help="Scrape ad-hoc URL(s) instead of the config list. "
             "Repeatable: --url A --url B"),
    name: str = typer.Option("ad-hoc", "--name", "-n"),
    sektor: Optional[list[str]] = typer.Option(
        None, "--sektor",
        help="JDIH only: sector code(s), e.g. --sektor 01 --sektor 02. "
             "Omit to use whatever the URL specifies, or the full matrix."),
    jenis: Optional[list[str]] = typer.Option(
        None, "--jenis",
        help="JDIH only: regulation-type code(s), e.g. --jenis 06 (Peraturan OJK)."),
    adapter: str = typer.Option(
        "auto", "--adapter",
        help="auto | generic | jdih_ojk. 'auto' picks by hostname."),
    follow: Optional[list[str]] = typer.Option(
        None, "--follow",
        help="Generic adapter: URL substring(s) worth following one hop, "
             "e.g. --follow /regulasi/Pages/"),
    exclude: Optional[list[str]] = typer.Option(
        None, "--exclude",
        help="Skip links matching these substrings, e.g. --exclude abstrak"),
    category: Optional[str] = typer.Option(
        None, "--category", help="Force a knowledge-base category for the run."),
    limit: Optional[int] = typer.Option(None, "--limit", "-l",
                                        help="Max documents per site."),
    pages: int = typer.Option(2, "--pages", help="Max pages to visit per site."),
    no_analyze: bool = typer.Option(False, "--no-analyze"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Route 1 — harvest PDFs from registered sites, or from ad-hoc URLs.

    Examples:

      hero scrape                                   # every enabled site in the config

      hero scrape --url https://ojk.go.id/id/regulasi/default.aspx \\
                  --follow /regulasi/Pages/ --exclude abstrak

      hero scrape --url "https://jdih.ojk.go.id/Web/ViewPeraturan/Index?sektor=02&jenisPeraturan=06"

      hero scrape --url https://jdih.ojk.go.id/Web/ViewPeraturan/Index \\
                  --sektor 01 --sektor 02 --jenis 06 --limit 20
    """
    _setup_logging(verbose)
    settings = load_settings(config)
    sites = None
    if url:
        sites = [
            SiteSource(
                name=name if len(url) == 1 else f"{name}-{i + 1}",
                url=u,
                max_pages=pages,
                max_documents=limit or 25,
                follow_patterns=list(follow or []),
                exclude_patterns=list(exclude or []),
                category_hint=category,
                adapter=adapter,
                sektor=list(sektor or []),
                jenis_peraturan=list(jenis or []),
            )
            for i, u in enumerate(url)
        ]
    elif sektor or jenis:
        # Parameters given without a URL: address the JDIH register directly.
        sites = [SiteSource(
            name=name if name != "ad-hoc" else "JDIH OJK (ad-hoc)",
            url="https://jdih.ojk.go.id/Web/ViewPeraturan/Index",
            max_documents=limit or 25, category_hint=category,
            adapter="jdih_ojk", sektor=list(sektor or []),
            jenis_peraturan=list(jenis or []),
        )]
    pipeline = IngestPipeline(settings, analyze=not no_analyze)
    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                      console=console, transient=True) as prog:
            task = prog.add_task("Menyiapkan scraping…")
            run = pipeline.run_sites(
                sites, limit,
                progress=lambda kind, msg: prog.update(
                    task, description=f"[{kind}] {msg}"))
    finally:
        pipeline.close()
    _render_run(run, "Hasil Scraping Situs")


@app.command()
def upload(
    paths: list[Path] = typer.Argument(..., help="PDF files or directories."),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    name: str = typer.Option("manual-upload", "--name", "-n"),
    category: Optional[str] = typer.Option(None, "--category"),
    force_ocr: bool = typer.Option(False, "--force-ocr",
                                   help="OCR every page, ignoring the text layer."),
    no_analyze: bool = typer.Option(False, "--no-analyze"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Route 2 — ingest manually supplied PDFs."""
    _setup_logging(verbose)
    settings = load_settings(config)
    pipeline = IngestPipeline(settings, analyze=not no_analyze, force_ocr=force_ocr)
    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                      console=console, transient=True) as prog:
            task = prog.add_task("Memproses unggahan…")
            run = pipeline.run_upload(
                paths, name, category,
                progress=lambda kind, msg: prog.update(
                    task, description=f"[{kind}] {msg}"))
    finally:
        pipeline.close()
    _render_run(run, "Hasil Unggah Manual")


@app.command("folders")
def ingest_folders(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    path: Optional[Path] = typer.Option(None, "--path", "-p",
                                        help="Ad-hoc folder instead of the config list."),
    name: str = typer.Option("ad-hoc-folder", "--name", "-n"),
    no_analyze: bool = typer.Option(False, "--no-analyze"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Route 3 — ingest from local or synced OneDrive folders."""
    _setup_logging(verbose)
    settings = load_settings(config)
    folders = [FolderSource(name=name, path=str(path))] if path else None
    pipeline = IngestPipeline(settings, analyze=not no_analyze)
    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                      console=console, transient=True) as prog:
            task = prog.add_task("Memindai folder…")
            run = pipeline.run_folders(
                folders,
                progress=lambda kind, msg: prog.update(
                    task, description=f"[{kind}] {msg}"))
    finally:
        pipeline.close()
    _render_run(run, "Hasil Ingest Folder")


@app.command("onedrive")
def ingest_onedrive(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    share_url: Optional[str] = typer.Option(None, "--share-url", "-u"),
    name: str = typer.Option("ad-hoc-share", "--name", "-n"),
    subfolder: Optional[str] = typer.Option(
        None, "--subfolder", "-s", help="Subfolder di dalam folder yang dibagikan."),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l",
        help="Maksimum PDF BARU yang diunduh pada putaran ini (menimpa max_files di config)."),
    check: bool = typer.Option(
        False, "--check", help="Hanya periksa apakah tautan dapat dibaca tanpa login."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Route 3b — ingest from a public OneDrive share link."""
    from hero.config import OneDriveShareSource
    from hero.ingest.onedrive import diagnose_link

    _setup_logging(verbose)
    settings = load_settings(config)
    if check:
        targets = [share_url] if share_url else [
            s.share_url for s in settings.onedrive_shares]
        if not targets:
            console.print("[yellow]Tidak ada tautan untuk diperiksa.[/]")
            raise typer.Exit(code=1)
        blocked = False
        for url in targets:
            d = diagnose_link(url)
            mark = "[green]dapat dibaca[/]" if d.accessible else "[red]butuh login[/]"
            console.print(f"{mark}  [dim]{escape(url[:90])}…[/]")
            console.print(f"  jenis: {d.kind} · {escape(d.reason)}")
            if d.server_path:
                console.print(f"  folder: [cyan]{escape(d.server_path)}[/]")
            blocked = blocked or not d.accessible
        raise typer.Exit(code=1 if blocked else 0)
    if share_url:
        shares = [OneDriveShareSource(
            name=name, share_url=share_url, subfolder=subfolder,
            max_files=limit if limit is not None else 100)]
    else:
        # Tautan dari config: opsi CLI yang diberikan eksplisit menimpa config,
        # supaya satu putaran bisa dibatasi tanpa mengedit YAML (dipakai skrip
        # backfill di VPS).
        shares = list(settings.enabled_shares)
        for share in shares:
            if limit is not None:
                share.max_files = limit
            if subfolder:
                share.subfolder = subfolder
    pipeline = IngestPipeline(settings)
    try:
        run = pipeline.run_onedrive_shares(shares)
    finally:
        pipeline.close()
    _render_run(run, "Hasil Ingest OneDrive")


@app.command("ingest-all")
def ingest_all(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run every configured route in one pass."""
    _setup_logging(verbose)
    pipeline = IngestPipeline(load_settings(config))
    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                      console=console, transient=True) as prog:
            task = prog.add_task("Menjalankan semua sumber…")
            run = pipeline.run_all(
                progress=lambda kind, msg: prog.update(
                    task, description=f"[{kind}] {msg}"))
    finally:
        pipeline.close()
    _render_run(run, "Hasil Ingest Seluruh Sumber")


# ---------------------------------------------------------------------------
@app.command()
def analyze(
    pdf: Path = typer.Argument(..., help="A PDF file to inspect."),
    force_ocr: bool = typer.Option(False, "--force-ocr"),
    tables: bool = typer.Option(False, "--tables", help="Also extract tables."),
    json_out: Optional[Path] = typer.Option(None, "--json",
                                            help="Write the full result to JSON."),
    text_out: Optional[Path] = typer.Option(None, "--text",
                                            help="Write the extracted text to a file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Extract, OCR and analyse a single PDF without storing it (URD 3.3)."""
    _setup_logging(verbose)
    settings = load_settings("config/sources.yaml")

    probe = probe_pdf(pdf, settings.pdf)
    if not probe["valid"]:
        console.print(f"[red]Bukan PDF yang valid:[/] {probe['error']}")
        raise typer.Exit(1)
    if probe.get("repaired"):
        console.print("[yellow]Struktur PDF rusak — berkas diperbaiki otomatis "
                      "sebelum diproses.[/]")

    with console.status("Mengekstrak teks (OCR bila perlu)…"):
        result = extract_pdf(pdf, settings.ocr, settings.pdf, force_ocr=force_ocr)
    if result.error and not result.char_count:
        console.print(f"[red]Ekstraksi gagal:[/] {result.error}")
        raise typer.Exit(1)

    md = extract_metadata(result.text, probe.get("pdf_metadata"), pdf.name)
    struct = parse_structure(result.pages)
    analysis = build_summary(result.text, struct, md)

    info = Table.grid(padding=(0, 2))
    info.add_column(style="bold cyan")
    info.add_column()
    info.add_row("Berkas", str(pdf))
    info.add_row("Halaman", f"{result.page_count} "
                            f"({result.ocr_pages} via OCR, "
                            f"{result.ocr_ratio:.0%})")
    info.add_row("Jenis dokumen", md.doc_type_label or md.doc_type or "[dim]tidak dikenali[/]")
    info.add_row("Nomor", md.number or "[dim]-[/]")
    info.add_row("Tentang", md.subject or "[dim]-[/]")
    info.add_row("Penerbit", md.issuing_body or "[dim]-[/]")
    info.add_row("Tanggal", str(md.issued_date) if md.issued_date else "[dim]-[/]")
    info.add_row("Status", md.status)
    info.add_row("Keyakinan metadata", f"{md.confidence:.0%}")
    info.add_row("Struktur", f"{len(struct.babs)} bab · "
                             f"{len(struct.articles)} pasal · "
                             f"{analysis['statistics']['ayat_count']} ayat")
    info.add_row("Relevansi IT", analysis["it_relevance"]["level"])
    info.add_row("Waktu proses", f"{result.duration_seconds}s")
    console.print(Panel(info, title="Metadata", border_style="cyan"))

    quality = assess_quality(result)
    grade_style = {"baik": "green", "cukup": "yellow",
                  "perlu-review": "red", "gagal": "red"}.get(quality["grade"], "white")
    q = Table.grid(padding=(0, 2))
    q.add_column(style="bold cyan")
    q.add_column()
    q.add_row("Grade", f"[{grade_style}]{quality['grade']}[/]")
    q.add_row("Rerata keyakinan OCR",
              f"{quality['mean_ocr_confidence']:.1f}%"
              if quality["mean_ocr_confidence"] is not None else "[dim]-[/]")
    q.add_row("Halaman kosong", str(quality["blank_pages"]))
    q.add_row("Halaman diputar (OSD)", str(quality["rotated_pages"]))
    q.add_row("Halaman OCR ulang (adaptif)", str(len(quality["adaptive_retry_pages"])))
    if quality["issues"]:
        q.add_row("Catatan", "\n".join(f"• {i}" for i in quality["issues"]))
    console.print(Panel(q, title="Kualitas Ekstraksi", border_style=grade_style))

    if md.legal_basis:
        console.print(Panel(
            "\n".join(f"• {b}" for b in md.legal_basis[:12]),
            title="Dasar Hukum (Mengingat)", border_style="blue"))

    if analysis["summary"]:
        console.print(Panel(analysis["summary"], title="Ringkasan (Deterministik)",
                            border_style="green"))

    if analysis["key_takeaways"]:
        kt = Table(title="Key Takeaways", header_style="bold magenta", expand=True)
        kt.add_column("Kategori", width=14)
        kt.add_column("Lokasi", width=22)
        kt.add_column("IT", width=4, justify="center")
        kt.add_column("Poin", overflow="fold")
        for item in analysis["key_takeaways"]:
            kt.add_row(item["category"], item["pasal"] or "-",
                       "✓" if item["it_relevant"] else "",
                       item["text"][:300])
        console.print(kt)

    if analysis["topics"]:
        console.print("[bold cyan]Topik dominan:[/] " + " · ".join(
            f"{t['term']}({t['count']})" for t in analysis["topics"][:12]))

    if md.warnings:
        console.print(Panel("\n".join(f"• {w}" for w in md.warnings),
                            title="Peringatan", border_style="yellow"))

    payload = {
        "file": str(pdf),
        "probe": probe,
        "metadata": md.to_dict(),
        "structure": struct.to_dict(),
        "analysis": analysis,
        "pages": [{"page": p.number, "source": p.source, "chars": p.char_count,
                   "ocr_confidence": p.ocr_confidence} for p in result.pages],
    }
    if tables:
        payload["tables"] = extract_tables(pdf)
        console.print(f"[cyan]Tabel terdeteksi:[/] {len(payload['tables'])}")
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                       default=str), encoding="utf-8")
        console.print(f"[green]JSON ditulis ke[/] {json_out}")
    if text_out:
        text_out.parent.mkdir(parents=True, exist_ok=True)
        text_out.write_text(result.text, encoding="utf-8")
        console.print(f"[green]Teks ditulis ke[/] {text_out}")


@app.command("ocr-check")
def ocr_check(
    pdf: Path = typer.Argument(...),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    force_ocr: bool = typer.Option(False, "--force-ocr"),
) -> None:
    """Report per-page whether text came from the PDF layer or from OCR,
    including what the image-quality pipeline had to correct."""
    settings = load_settings(config)
    result = extract_pdf(pdf, settings.ocr, settings.pdf, force_ocr=force_ocr)
    table = Table(title=f"Sumber teks per halaman — {pdf.name}",
                  header_style="bold cyan")
    table.add_column("Hal", justify="right")
    table.add_column("Sumber")
    table.add_column("Karakter", justify="right")
    table.add_column("Keyakinan OCR", justify="right")
    table.add_column("Rotasi", justify="right")
    table.add_column("Percobaan", justify="right")
    for p in result.pages:
        table.add_row(
            str(p.number),
            "[yellow]OCR[/]" if p.source == "ocr" else "[green]text-layer[/]",
            str(p.char_count),
            f"{p.ocr_confidence:.1f}%" if p.ocr_confidence is not None else "-",
            f"{p.rotation_applied}°" if p.rotation_applied else "-",
            str(p.ocr_attempts) if p.source == "ocr" else "-")
    console.print(table)
    console.print(f"Dokumen hasil scan: "
                  f"{'[yellow]ya[/]' if result.is_scanned else '[green]tidak[/]'} "
                  f"· {result.ocr_pages}/{result.page_count} halaman via OCR "
                  f"· {result.duration_seconds}s")
    if result.repaired:
        console.print("[yellow]Berkas diperbaiki otomatis (pikepdf) sebelum dibaca.[/]")
    quality = assess_quality(result)
    console.print(f"Grade kualitas: [bold]{quality['grade']}[/] "
                  f"· rerata keyakinan OCR: "
                  f"{quality['mean_ocr_confidence'] if quality['mean_ocr_confidence'] is not None else '-'}")


# ---------------------------------------------------------------------------
@app.command("kb")
def kb_list(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    category: Optional[str] = typer.Option(None, "--category"),
    doc_type: Optional[str] = typer.Option(None, "--type"),
    year: Optional[int] = typer.Option(None, "--year"),
    limit: int = typer.Option(50, "--limit", "-l"),
) -> None:
    """List documents stored in the knowledge base."""
    settings = load_settings(config)
    with Catalog(settings.catalog_db) as cat:
        rows = cat.list_documents(category, doc_type, year, limit=limit)
    if not rows:
        console.print("[yellow]Knowledge base kosong untuk filter tersebut.[/]")
        return
    wide = console.width >= 118
    table = Table(title=f"Knowledge Base ({len(rows)} dokumen)",
                  header_style="bold cyan", expand=True)
    table.add_column("ID", width=8, no_wrap=True)
    table.add_column("Jenis", width=6, no_wrap=True)
    table.add_column("Nomor", width=17, no_wrap=True)
    table.add_column("Thn", width=4)
    if wide:
        table.add_column("Kategori", width=16, no_wrap=True)
        table.add_column("Sumber", width=12, no_wrap=True)
    table.add_column("Tentang", ratio=1, min_width=22, overflow="ellipsis")
    for r in rows:
        row = [r["doc_id"][:8], r["doc_type"] or "-", r["number"] or "-",
               str(r["year"] or "-")]
        if wide:
            row += [r["category"] or "-", r["source_type"] or "-"]
        row.append(r["subject"] or r["title"] or r["original_filename"])
        table.add_row(*row)
    console.print(table)


@app.command("search")
def kb_search(
    query: str = typer.Argument(..., help="Full-text query."),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    limit: int = typer.Option(15, "--limit", "-l"),
) -> None:
    """Full-text search across the knowledge base."""
    settings = load_settings(config)
    with Catalog(settings.catalog_db) as cat:
        rows = cat.search(query, limit)
    if not rows:
        console.print(f"[yellow]Tidak ada hasil untuk[/] '{query}'")
        return
    for r in rows:
        # Escape first, then turn the FTS sentinels into markup, so bracket
        # characters inside the regulation text cannot break the rendering.
        snippet = escape(r["snippet"] or "")
        snippet = snippet.replace("\x02", "[bold yellow]").replace("\x03", "[/]")
        title = escape(
            f"{r['doc_type'] or '?'} {r['number'] or ''}".strip())
        subject = escape((r["subject"] or r["title"] or "")[:90])
        console.print(Panel(
            snippet,
            title=f"[cyan]{title}[/] — {subject}",
            subtitle=f"{r['doc_id'][:8]} · {r['category']}",
            border_style="blue"))


@app.command("show")
def kb_show(
    doc_id: str = typer.Argument(..., help="Document id (prefix is enough)."),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    articles: bool = typer.Option(False, "--articles", help="Print every pasal."),
) -> None:
    """Show the stored analysis for one document."""
    settings = load_settings(config)
    with Catalog(settings.catalog_db) as cat:
        row = cat.get(doc_id)
        if row is None:
            console.print(f"[red]Dokumen tidak ditemukan:[/] {doc_id}")
            raise typer.Exit(1)
        text_row = cat.get_text(row["doc_id"])

    info = Table.grid(padding=(0, 2))
    info.add_column(style="bold cyan")
    info.add_column(overflow="fold")
    for label, key in (("ID", "doc_id"), ("Judul", "title"), ("Tentang", "subject"),
                       ("Jenis", "doc_type"), ("Nomor", "number"), ("Tahun", "year"),
                       ("Tanggal", "issued_date"), ("Penerbit", "issuing_body"),
                       ("Status", "reg_status"), ("Kategori", "category"),
                       ("Sumber", "source_type"), ("Referensi", "source_ref"),
                       ("Disimpan di", "stored_path"), ("Halaman", "page_count"),
                       ("Halaman OCR", "ocr_pages")):
        info.add_row(label, str(row[key]) if row[key] is not None else "-")
    console.print(Panel(info, title="Dokumen", border_style="cyan"))

    if text_row and text_row["analysis"]:
        analysis = json.loads(text_row["analysis"])
        quality = analysis.get("quality")
        if quality:
            style = {"baik": "green", "cukup": "yellow",
                    "perlu-review": "red", "gagal": "red"}.get(quality["grade"], "white")
            note = f"Grade: [{style}]{quality['grade']}[/]"
            if quality.get("issues"):
                note += "\n" + "\n".join(f"• {i}" for i in quality["issues"])
            console.print(Panel(note, title="Kualitas Ekstraksi", border_style=style))
        if analysis.get("summary"):
            console.print(Panel(analysis["summary"], title="Ringkasan",
                                border_style="green"))
        if analysis.get("key_takeaways"):
            kt = Table(title="Key Takeaways", header_style="bold magenta", expand=True)
            kt.add_column("Kategori", width=14)
            kt.add_column("Lokasi", width=22)
            kt.add_column("Poin", overflow="fold")
            for item in analysis["key_takeaways"]:
                kt.add_row(item["category"], item["pasal"] or "-", item["text"][:300])
            console.print(kt)

    if articles and text_row and text_row["structure"]:
        struct = json.loads(text_row["structure"])
        for art in struct.get("articles", []):
            console.print(Panel(art["text"][:1500],
                                title=f"Pasal {art['number']}"
                                      f"{' — ' + art['bab'] if art['bab'] else ''}",
                                border_style="dim"))


@app.command("export")
def kb_export(
    out_dir: Path = typer.Option(Path("data/export"), "--out", "-o"),
    fmt: str = typer.Option("csv", "--format", "-f", help="csv atau jsonl."),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Export documents, pasal and Key Takeaways as flat tables."""
    from hero.kb.export import export

    if fmt not in ("csv", "jsonl"):
        console.print("[red]--format harus csv atau jsonl[/]")
        raise typer.Exit(1)
    settings = load_settings(config)
    with Catalog(settings.catalog_db) as cat:
        counts = export(cat, out_dir, fmt)

    table = Table(title=f"Export ke {out_dir}", header_style="bold cyan")
    table.add_column("Dataset")
    table.add_column("Baris", justify="right")
    table.add_column("Berkas")
    for name, n in counts.items():
        table.add_row(name, str(n), f"{name}.{fmt}")
    console.print(table)


@app.command("stats")
def kb_stats(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Knowledge base statistics (phase indicators from URD section 5)."""
    settings = load_settings(config)
    with Catalog(settings.catalog_db) as cat:
        s = cat.stats()

    grid = Table.grid(padding=(0, 3))
    grid.add_column(style="bold cyan")
    grid.add_column(justify="right")
    grid.add_row("Total dokumen", str(s["total_documents"]))
    grid.add_row("Berhasil di-ingest", str(s["ingested"]))
    grid.add_row("Dokumen hasil scan", str(s["scanned_documents"]))
    grid.add_row("Punya teks terekstrak", str(s["with_text"]))
    grid.add_row("Total halaman", str(s["total_pages"]))
    grid.add_row("Halaman via OCR", str(s["ocr_pages"]))
    console.print(Panel(grid, title="Statistik Knowledge Base", border_style="cyan"))

    for title, data in (("Kategori", s["by_category"]), ("Jenis", s["by_type"]),
                        ("Sumber", s["by_source"]), ("Tahun", s["by_year"])):
        if not data:
            continue
        t = Table(title=title, header_style="bold")
        t.add_column(title)
        t.add_column("Jumlah", justify="right")
        for k, v in data.items():
            t.add_row(str(k), str(v))
        console.print(t)

    target = 20  # URD Fase 1 indicator
    done = s["ingested"]
    console.print(
        f"\n[bold]Indikator URD Fase 1[/] (≥ {target} dokumen di knowledge base): "
        + (f"[green]tercapai ({done})[/]" if done >= target
           else f"[yellow]{done}/{target}[/]"))


def _adhoc_sites(url, name, sektor, jenis, adapter) -> list[SiteSource] | None:
    """Turn --url / --sektor / --jenis into SiteSource objects (or None)."""
    if url:
        return [SiteSource(
            name=name if len(url) == 1 else f"{name}-{i + 1}", url=u,
            adapter=adapter, sektor=list(sektor or []),
            jenis_peraturan=list(jenis or []), max_pages=25,
        ) for i, u in enumerate(url)]
    if sektor or jenis:
        return [SiteSource(
            name="JDIH OJK (ad-hoc)",
            url="https://jdih.ojk.go.id/Web/ViewPeraturan/Index",
            adapter="jdih_ojk", sektor=list(sektor or []),
            jenis_peraturan=list(jenis or []),
        )]
    return None


@app.command()
def discover(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    url: Optional[list[str]] = typer.Option(
        None, "--url", "-u", help="Discover ad-hoc URL(s) instead of the config list."),
    name: str = typer.Option("ad-hoc", "--name", "-n"),
    sektor: Optional[list[str]] = typer.Option(None, "--sektor", help="JDIH sector code(s)."),
    jenis: Optional[list[str]] = typer.Option(None, "--jenis", help="JDIH type code(s)."),
    adapter: str = typer.Option("auto", "--adapter"),
    full: bool = typer.Option(
        False, "--full", help="Walk every listing page even if the inventory "
                              "already has records (default: stop once pages "
                              "contain nothing new)."),
    refresh: bool = typer.Option(
        False, "--refresh", help="Re-read every detail page, not only new ones."),
    no_details: bool = typer.Option(
        False, "--no-details", help="Listing pass only; skip detail pages."),
    max_pages: Optional[int] = typer.Option(None, "--max-pages",
                                            help="Cap listing pages per site."),
    max_details: Optional[int] = typer.Option(None, "--max-details",
                                              help="Cap detail pages per site."),
    sequential: bool = typer.Option(False, "--sequential",
                                    help="One site at a time instead of in parallel."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Build the inventory: every record each source publishes, every field.

    Nothing is downloaded — that is `hero harvest`. Safe to interrupt and
    re-run: listing merges, and only detail pages not yet read are fetched.

    Examples:

      hero discover                         # all enabled sites, in parallel

      hero discover --no-details            # quick: listings only

      hero discover --sektor 10             # one JDIH sector, all types
    """
    import threading
    from datetime import datetime

    from hero import inventory as inv

    _setup_logging(verbose)
    settings = load_settings(config)
    sites = _adhoc_sites(url, name, sektor, jenis, adapter)
    lock = threading.Lock()

    def progress(kind: str, msg: str) -> None:
        with lock:
            console.print(f"[dim]{datetime.now():%H:%M:%S}[/] [cyan]{kind:6}[/] {escape(msg)}")

    reports = inv.discover_all(
        settings, sites, parallel=not sequential, progress=progress,
        enrich=not no_details, refresh=refresh, full=True if full else None,
        max_pages=max_pages, max_details=max_details,
    )
    rec = inv.reconcile_status(settings)

    table = Table(title="Hasil Discovery", header_style="bold cyan", expand=True)
    for col, just in (("Situs", "left"), ("Sumber", "left"), ("Halaman", "right"),
                      ("Terdaftar", "right"), ("Baru", "right"),
                      ("Detail dibaca", "right"), ("Gagal", "right"), ("Detik", "right")):
        table.add_column(col, justify=just)
    for r in reports:
        table.add_row(r.site, r.source, str(r.pages), str(r.listed), str(r.new),
                      str(r.enriched), str(r.enrich_failed), f"{r.seconds:.0f}")
    console.print(table)
    console.print(f"Status ojk.go.id dicocokkan ke JDIH: [green]{rec['matched']}[/] · "
                  f"tidak ditemukan padanannya: [yellow]{rec['unmatched']}[/]")
    errors = [f"[{r.site}] {e}" for r in reports for e in r.errors]
    if errors:
        console.print(Panel("\n".join(f"• {escape(e)}" for e in errors[:25]),
                            title=f"Catatan ({len(errors)})", border_style="yellow"))
    with Catalog(settings.catalog_db) as cat:
        s = cat.inventory_stats()
    console.print(f"Inventaris: [bold]{s['total']}[/] rekaman · "
                  f"{s['enriched']} lengkap dengan detail · {s['downloaded']} sudah diunduh")


@app.command()
def harvest(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    source: Optional[list[str]] = typer.Option(
        None, "--source", "-s",
        help="jdih-ojk | ojk-regulasi | ojk-rancangan (repeatable). Default: all."),
    status: Optional[str] = typer.Option(
        None, "--status", help="berlaku | dicabut | diubah | rancangan | unknown"),
    category: Optional[str] = typer.Option(None, "--category"),
    limit: int = typer.Option(20, "--limit", "-l",
                              help="Max documents this run (ignored with --all)."),
    all_: bool = typer.Option(False, "--all",
                              help="Download every inventory row not yet held."),
    no_analyze: bool = typer.Option(False, "--no-analyze"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Download the documents behind inventory rows into the knowledge base.

    Run `hero discover` first. Resumable: rows already downloaded are skipped.

    Examples:

      hero harvest --limit 50

      hero harvest --source jdih-ojk --status berlaku --all

      hero harvest --source ojk-rancangan --limit 10
    """
    _setup_logging(verbose)
    settings = load_settings(config)
    pipeline = IngestPipeline(settings, analyze=not no_analyze)
    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                      console=console, transient=True) as prog:
            task = prog.add_task("Menyiapkan unduhan…")
            run = pipeline.harvest_inventory(
                sources=list(source) if source else None, status=status,
                category=category, limit=None if all_ else limit,
                progress=lambda kind, msg: prog.update(
                    task, description=f"[{kind}] {escape(msg)}"))
    finally:
        pipeline.close()
    _render_run(run, "Hasil Harvest Inventaris")


@app.command("inventory")
def inventory_stats(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Summarise the inventory: records per source and status, progress."""
    settings = load_settings(config)
    with Catalog(settings.catalog_db) as cat:
        s = cat.inventory_stats()
        per = cat.conn.execute(
            """SELECT source, COUNT(*) n,
                      SUM(enriched_at IS NOT NULL) enriched,
                      SUM(doc_id IS NOT NULL) downloaded,
                      SUM(enriched_at IS NOT NULL AND document_url IS NULL) no_pdf,
                      SUM(status='berlaku') berlaku, SUM(status='diubah') diubah,
                      SUM(status='dicabut') dicabut, SUM(status='rancangan') rancangan,
                      SUM(status='unknown' OR status IS NULL) unknown
               FROM inventory GROUP BY source ORDER BY n DESC""").fetchall()
    table = Table(title=f"Inventaris — {s['total']} rekaman",
                  header_style="bold cyan", expand=True)
    for col in ("Sumber", "Rekaman", "Detail", "Diunduh", "Tanpa PDF", "Berlaku",
                "Diubah", "Dicabut", "Rancangan", "?"):
        table.add_column(col, justify="left" if col == "Sumber" else "right")
    for r in per:
        table.add_row(r["source"], str(r["n"]), str(r["enriched"]), str(r["downloaded"]),
                      str(r["no_pdf"]), str(r["berlaku"]), str(r["diubah"]),
                      str(r["dicabut"]), str(r["rancangan"]), str(r["unknown"]))
    console.print(table)
    console.print("[dim]Tanpa PDF: detail sudah dibaca tetapi sumber hanya menyediakan "
                  "format lain (mis. .docx) — di luar cakupan PDF URD 4.2.[/]")


@app.command("inventory-export")
def inventory_export(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    out: Path = typer.Option(Path("data/export"), "--out", "-o"),
    fmt: Optional[list[str]] = typer.Option(
        None, "--format", "-f", help="csv | xlsx | json | html (repeatable). Default: all."),
    columns: Optional[list[str]] = typer.Option(
        None, "--column", help="Keep only these columns (by header). Default: every column."),
    source: Optional[list[str]] = typer.Option(None, "--source", "-s"),
) -> None:
    """Export the whole inventory as one table — every field is a column."""
    from hero.kb.inventory_export import export_inventory

    settings = load_settings(config)
    written = export_inventory(
        settings, out, formats=list(fmt) if fmt else ("csv", "xlsx", "json", "html"),
        columns=list(columns) if columns else None,
        sources=list(source) if source else None)
    for kind, path in written.items():
        size = path.stat().st_size / 1024
        console.print(f"[green]{kind:5}[/] {path}  ({size:,.0f} KB)")


@app.command("kb-restructure")
def kb_restructure(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show moves without doing them."),
) -> None:
    """Re-file the KB as source › category › type › year › status (idempotent)."""
    from hero.kb.restructure import restructure

    settings = load_settings(config)
    rep = restructure(settings, dry_run=dry_run)
    for src, dst in rep.moves[:40]:
        console.print(f"[dim]{escape(src)}[/]\n  → [cyan]{escape(dst)}[/]")
    if len(rep.moves) > 40:
        console.print(f"[dim]… dan {len(rep.moves) - 40} lainnya[/]")
    verb = "akan dipindah" if dry_run else "dipindah"
    console.print(f"\n[bold]{rep.moved}[/] berkas {verb} · {rep.unchanged} sudah di tempatnya · "
                  f"{rep.missing} tidak ditemukan · status diperbarui dari JDIH: "
                  f"{rep.status_from_jdih} · kategori ditentukan ulang: {rep.recategorised}")


@app.command("kb-remove")
def kb_remove(
    doc_id: str = typer.Argument(..., help="ID dokumen yang akan dihapus (bisa disingkat)."),
    reason: str = typer.Option(..., "--reason", help="Alasan penghapusan, wajib diisi untuk jejak audit."),
    keep_file: bool = typer.Option(
        False, "--keep-file", help="Hapus baris database tapi biarkan berkas PDF di disk."),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Hapus satu dokumen (baris database + berkas) — untuk artefak pengujian
    yang mengendap di knowledge base produksi (lihat aturan mutu DOC-G01)."""
    import os

    settings = load_settings(config)
    with Catalog(settings.catalog_db) as cat:
        row = cat.get(doc_id)
        if row is None:
            console.print(f"[red]Dokumen '{doc_id}' tidak ditemukan.[/]")
            raise typer.Exit(code=1)
        console.print(f"Menghapus: [bold]{escape(row['title'] or row['doc_id'])}[/]")
        console.print(f"  sumber: {row['source_name']} · alasan: {reason}")
        stored_path = cat.delete_document(row["doc_id"])

    if stored_path and not keep_file and os.path.exists(stored_path):
        os.remove(stored_path)
        console.print(f"[green]Berkas dihapus:[/] {stored_path}")
    elif stored_path and keep_file:
        console.print(f"[yellow]Baris database dihapus; berkas dipertahankan:[/] {stored_path}")


@app.command("kb-rename-source")
def kb_rename_source(
    doc_id: str = typer.Argument(..., help="ID dokumen."),
    source_name: str = typer.Argument(..., help="Nama sumber yang benar."),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Perbaiki label sumber sebuah dokumen tanpa menyentuh isinya — untuk
    dokumen asli yang kebetulan diunduh lewat sesi bernama ad-hoc/uji."""
    settings = load_settings(config)
    with Catalog(settings.catalog_db) as cat:
        row = cat.get(doc_id)
        if row is None:
            console.print(f"[red]Dokumen '{doc_id}' tidak ditemukan.[/]")
            raise typer.Exit(code=1)
        old_name = row["source_name"]
        cat.rename_source(row["doc_id"], source_name)
    console.print(f"[green]'{old_name}' → '{source_name}'[/] untuk {row['doc_id']}")


@app.command("dq")
def data_quality(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    markdown: Optional[Path] = typer.Option(
        None, "--markdown", "-m", help="Tulis laporan lengkap sebagai Markdown."),
    json_out: Optional[Path] = typer.Option(
        None, "--json", help="Tulis seluruh hasil sebagai JSON."),
    dimension: Optional[str] = typer.Option(
        None, "--dimension", "-d", help="Tampilkan satu dimensi saja."),
    strict: bool = typer.Option(
        False, "--strict",
        help="Keluar dengan kode 1 bila ada aturan yang gagal (untuk CI)."),
) -> None:
    """Ukur mutu data knowledge base: aturan, cakupan, dan indikator Fase 1."""
    import sqlite3

    from hero.dq import build_scorecard
    from hero.dq.report import render_markdown

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db) as conn:
        card = build_scorecard(conn)

    marks = {"lulus": "[green]lulus[/]", "perhatian": "[yellow]perhatian[/]",
             "gagal": "[red]gagal[/]", "error": "[red]error[/]",
             "kosong": "[dim]kosong[/]", "perlu-perbaikan": "[yellow]perlu-perbaikan[/]"}

    dim_table = Table(title="Skor per dimensi", header_style="bold")
    for col, justify in (("Dimensi", "left"), ("Skor", "right"),
                         ("Hasil", "left"), ("Gagal", "right")):
        dim_table.add_column(col, justify=justify)
    for d in card.dimensions:
        dim_table.add_row(d.dimension, f"{d.score * 100:.1f}%",
                          marks.get(d.verdict, d.verdict), str(d.failed))
    console.print(dim_table)

    shown = [r for r in card.results
             if dimension is None or r.rule.dimension == dimension]
    rules_table = Table(title="Aturan mutu data", header_style="bold")
    for col in ("ID", "Dataset", "Dimensi", "Keparahan"):
        rules_table.add_column(col)
    rules_table.add_column("Pelanggar", justify="right")
    rules_table.add_column("Lingkup", justify="right")
    rules_table.add_column("Rasio", justify="right")
    rules_table.add_column("Hasil")
    for r in sorted(shown, key=lambda x: (x.rule.dataset, x.rule.id)):
        style = "red" if r.verdict in ("gagal", "error") else None
        rules_table.add_row(
            r.rule.id, r.rule.dataset, r.rule.dimension, r.rule.severity,
            str(r.violating_rows), str(r.scope_rows), f"{r.rate * 100:.1f}%",
            marks.get(r.verdict, r.verdict), style=style)
    console.print(rules_table)

    cov = card.coverage
    if cov.get("matchable"):
        console.print(Panel(
            f"Rekaman ojk.go.id: [bold]{cov['total']}[/] · dapat dicocokkan ke "
            f"JDIH: [bold]{cov['matchable']}[/] · di luar register JDIH: "
            f"[bold]{cov['out_of_universe']}[/]\n"
            f"Cakupan naif (menyesatkan): [yellow]{cov['naive_coverage'] * 100:.1f}%[/] "
            f"· cakupan sebenarnya: [green]{cov['true_coverage'] * 100:.1f}%[/]\n"
            f"Sisa yang layak diperbaiki: [bold]{cov['unresolved_addressable']}[/] "
            f"rekaman (bukan {cov['unresolved_structural'] + cov['unresolved_addressable']})",
            title="Cakupan rekonsiliasi status", border_style="cyan"))

    ph_table = Table(title="Indikator Fase 1 (URD bagian 5)", header_style="bold")
    ph_table.add_column("Indikator")
    ph_table.add_column("Aktual", justify="right")
    ph_table.add_column("Target", justify="right")
    ph_table.add_column("Status")
    for i in card.phase1.get("indicators", []):
        ph_table.add_row(
            i["indikator"], str(i["aktual"]), str(i["target"]),
            "[green]tercapai[/]" if i["tercapai"] else "[red]belum[/]")
    console.print(ph_table)

    raw = card.phase1.get("documents_raw_ingested", 0)
    genuine = card.phase1.get("documents_genuine", 0)
    if raw != genuine:
        console.print(
            f"[yellow]Catatan:[/] {raw} baris berstatus ingested, namun hanya "
            f"[bold]{genuine}[/] dokumen peraturan sungguhan — sisanya artefak "
            f"pengujian/berkas non-peraturan.")

    if markdown:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_markdown(card), encoding="utf-8")
        console.print(f"[green]Laporan Markdown ditulis:[/] {markdown}")
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps(card.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8")
        console.print(f"[green]JSON ditulis:[/] {json_out}")

    console.print(
        f"\n[bold]Kesimpulan:[/] {marks.get(card.verdict, card.verdict)} · "
        f"skor keseluruhan [bold]{card.overall_score * 100:.1f}%[/]")
    if strict and card.verdict in ("gagal", "perlu-perbaikan", "error"):
        raise typer.Exit(code=1)


@app.command("profile")
def data_profile(
    table: str = typer.Argument(
        "inventory", help="Tabel yang diprofilkan: inventory / documents / articles."),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    top: int = typer.Option(5, "--top", help="Berapa nilai terbanyak ditampilkan."),
    json_out: Optional[Path] = typer.Option(None, "--json"),
) -> None:
    """Profil kolom sebuah tabel: kekosongan, kardinalitas, dan sebaran nilai."""
    import sqlite3

    from hero.dq import profile_table

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db) as conn:
        try:
            profiles = profile_table(conn, table, top_n=top)
        except ValueError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(code=1) from exc

    t = Table(title=f"Profil kolom · {table}", header_style="bold")
    t.add_column("Kolom")
    t.add_column("Tipe")
    t.add_column("Kosong", justify="right")
    t.add_column("% kosong", justify="right")
    t.add_column("Distinct", justify="right")
    t.add_column("Catatan")
    for p in profiles:
        notes = []
        if p.is_constant:
            notes.append("konstan")
        if p.is_unique and p.missing == 0:
            notes.append("kandidat kunci")
        if p.missing_rate > 0.5:
            notes.append("mayoritas kosong")
        style = "yellow" if p.missing_rate > 0.2 else None
        t.add_row(p.name, p.declared_type or "—", str(p.missing),
                  f"{p.missing_rate * 100:.1f}%", str(p.distinct),
                  ", ".join(notes), style=style)
    console.print(t)

    for p in profiles:
        if p.top_values and not p.is_unique:
            values = " · ".join(
                f"{escape(str(v)[:28])} ({c})" for v, c in p.top_values)
            console.print(f"[cyan]{p.name}[/]: {values}")

    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps([p.to_dict() for p in profiles],
                       ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        console.print(f"[green]JSON ditulis:[/] {json_out}")


# ---------------------------------------------------------------------------
# Server, read model, vector & graph indexes
# ---------------------------------------------------------------------------
vector_app = typer.Typer(help="Indeks vektor (LSA deterministik + semantik AI-Assisted).")
graph_app = typer.Typer(help="Graf relasi peraturan (MENCABUT / MENGUBAH / BERDASAR).")
app.add_typer(vector_app, name="vector")
app.add_typer(graph_app, name="graph")


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Jalankan API untuk frontend (dokumentasi interaktif di /docs)."""
    import os

    import uvicorn

    os.environ["HERO_CONFIG"] = str(config)
    uvicorn.run("hero.server.app:create_app", factory=True, host=host, port=port, reload=reload)


@app.command("readmodel")
def readmodel_sync(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    full: bool = typer.Option(False, "--full", help="Bangun ulang semua baris."),
) -> None:
    """Sinkronkan read model Knowledge Base (dipakai tabel & filter UI)."""
    import sqlite3

    from hero.kb.readmodel import sync

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db) as conn:
        rep = sync(conn, full=full)
    console.print(f"dibangun ulang {rep.rebuilt} · dihapus {rep.removed} · tetap {rep.unchanged}")


@vector_app.command("build")
def vector_build(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    lsa_only: bool = typer.Option(False, "--lsa-only", help="Lewati model semantik (mode Deterministik)."),
) -> None:
    """Potong dokumen per pasal, embed, dan simpan ke data/hero_vectors.db."""
    from hero.vector import build_vectors

    settings = load_settings(config)
    rep = build_vectors(settings, embedders=("lsa",) if lsa_only else ("lsa", "semantic"),
                        progress=lambda m: console.print(f"[dim]{m}[/]"))
    for idx in rep["indeks"]:
        console.print(f"[green]{idx['embedder']}[/]: {idx['chunks']} potongan · baru {idx['baru_diembed']} "
                      f"· cache {idx['dari_cache']} · {idx['detik']} s")
    st = rep["store"]
    console.print(f"{st['chunk']} potongan dari {st['dokumen']} dokumen · {st['ukuran_mb']} MB · "
                  f"sqlite-vec: {'ya' if st['sqlite_vec'] else 'tidak (NumPy)'}")


@vector_app.command("search")
def vector_search(
    q: str = typer.Argument(...),
    method: str = typer.Option("hybrid", "--method", "-m", help="lexical | lsa | semantic | hybrid"),
    k: int = typer.Option(5, "--k"),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Cari dokumen dengan satu metode, tampilkan pasal yang paling cocok."""
    import sqlite3

    from hero.vector import VectorService

    settings = load_settings(config)
    vs = VectorService(settings)
    if not vs.ready(method):
        console.print(f"[red]indeks '{method}' belum ada — jalankan `hero vector build`[/]")
        raise typer.Exit(code=1)
    hits = vs.search(q, method, k=k)
    with sqlite3.connect(settings.catalog_db) as conn:
        for i, h in enumerate(hits, 1):
            judul = conn.execute("SELECT judul FROM kb_document_view WHERE doc_id = ?",
                                 (h.doc_id,)).fetchone()
            console.print(f"[bold]{i}. {escape((judul or [h.doc_id])[0])}[/] [dim]skor {h.score:.3f}[/]")
            console.print(f"   [cyan]{h.best_ref or h.best_level}[/] {escape(h.best_text[:160])}…")


@graph_app.command("build")
def graph_build(config: Path = typer.Option("config/sources.yaml", "--config", "-c")) -> None:
    """Bangun graf dari Riwayat Peraturan, Landasan Hukum, dan bagian Mengingat."""
    import sqlite3

    from hero.graph.build import build_graph

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db) as conn:
        rep = build_graph(conn)
    console.print(f"node {rep.nodes} (register {rep.nodes_register}, hanya dirujuk {rep.nodes_rujukan}, "
                  f"di KB {rep.nodes_in_kb}) · edge {rep.edges}")
    console.print(f"rujukan terbaca {rep.refs_seen - rep.refs_unresolved}/{rep.refs_seen} "
                  f"({rep.resolution_rate * 100:.1f}%) · konflik identitas {rep.identity_conflicts}")


@graph_app.command("export")
def graph_export(
    out: Path = typer.Option(Path("data/export/graph"), "--out"),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Tulis nodes.csv, edges.csv, dan load.cypher untuk Neo4j."""
    import sqlite3

    from hero.graph.export import export_neo4j

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db) as conn:
        rep = export_neo4j(conn, out)
    console.print(f"{rep['nodes']} node · {rep['edges']} edge → {rep['dir']}")


@graph_app.command("findings")
def graph_findings_cmd(config: Path = typer.Option("config/sources.yaml", "--config", "-c")) -> None:
    """Status tercatat yang bertentangan dengan relasi pencabutan di graf."""
    import sqlite3

    from hero.graph.export import status_findings

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db) as conn:
        f = status_findings(conn, limit=10)
    for key, block in f.items():
        console.print(f"[bold]{key}[/]: {block['jumlah']} — {block['penjelasan']}")
        for r in block.get("contoh", [])[:5]:
            console.print(f"   {r['key']} ← dicabut penuh oleh {r['pencabut']}")


@app.command("bench")
def bench_cmd(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    markdown: Optional[Path] = typer.Option(Path("docs/DB_COMPARISON.md"), "--markdown"),
    runs: int = typer.Option(30, "--runs", help="Pengulangan per pengukuran latensi."),
) -> None:
    """Bandingkan relasional vs vektor vs graf: latensi dan kualitas temu-kembali."""
    from hero.bench import run_benchmark

    settings = load_settings(config)
    rep = run_benchmark(settings, runs=runs, progress=lambda m: console.print(f"[dim]{m}[/]"))
    if markdown:
        markdown.write_text(rep["markdown"], encoding="utf-8")
        console.print(f"[green]Laporan ditulis:[/] {markdown}")


@app.command("bench-vektor")
def bench_vector_cmd(
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
    markdown: Optional[Path] = typer.Option(Path("docs/VEKTOR_BENCHMARK.md"), "--markdown"),
    json_out: Optional[Path] = typer.Option(None, "--json"),
    k: int = typer.Option(10, "--k", help="Top-k yang diukur."),
    runs: int = typer.Option(30, "--runs"),
    metode: Optional[str] = typer.Option(None, "--metode", help="lsa | semantic."),
    potongan: Optional[int] = typer.Option(None, "--potongan",
                                           help="Batasi jumlah potongan (uji cepat)."),
    tanpa_pg: bool = typer.Option(False, "--tanpa-pg", help="Lewati Postgres/pgvector."),
    dsn: Optional[str] = typer.Option(None, "--dsn", help="DSN Postgres (default: HERO_PG_DSN)."),
    padded_dim: int = typer.Option(1536, "--dim-kolom",
                                   help="Dimensi kolom backend yang diukur harga paddingnya."),
) -> None:
    """Bandingkan penyimpanan vektor: SQLite (NumPy/sqlite-vec) vs Postgres pgvector."""
    import json as _json

    from hero.bench_vector import run_benchmark

    settings = load_settings(config)
    rep = run_benchmark(settings, dsn=dsn, k=k, runs=runs, method=metode,
                        limit_chunks=potongan, with_pg=not tanpa_pg, padded_dim=padded_dim,
                        progress=lambda m: console.print(f"[dim]{m}[/]"))
    if markdown:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(rep["markdown"], encoding="utf-8")
        console.print(f"[green]Laporan ditulis:[/] {markdown}")
    if json_out:
        payload = {k2: v for k2, v in rep.items() if k2 != "markdown"}
        json_out.write_text(_json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                            encoding="utf-8")
        console.print(f"[green]JSON ditulis:[/] {json_out}")
    pgv = rep.get("pgvector") or {}
    if pgv.get("galat"):
        console.print(f"[yellow]pgvector tidak diukur:[/] {pgv['galat']}")


@app.command("analisa")
def analisa_cmd(
    doc_id: Optional[str] = typer.Argument(None, help="ID dokumen (awalan cukup). Kosongkan dengan --semua."),
    semua: bool = typer.Option(False, "--semua", help="Analisa seluruh dokumen dan simpan hasilnya."),
    ai: bool = typer.Option(False, "--ai", help="Coba mode AI-Assisted (butuh kredensial Claude)."),
    json_out: Optional[Path] = typer.Option(None, "--json"),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Fase 2: ringkasan terstruktur & poin kunci berbasis pasal (v2)."""
    import sqlite3

    from hero.analysis import AiNarrator, analyse_all, analysis_payload
    from hero.kb.readmodel import sync

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db) as conn:
        conn.row_factory = sqlite3.Row
        if semua:
            import time as _t
            t0 = _t.perf_counter()
            res = analyse_all(conn, use_cache=False)
            sync(conn)
            console.print(f"[green]{len(res)} dokumen dianalisa[/] dalam {_t.perf_counter() - t0:.1f} s · "
                          f"poin kunci {sum(len(a.poin) for a in res)} · "
                          f"berat-Lampiran {sum(a.lampiran['berat_lampiran'] for a in res)}")
            return
        if not doc_id:
            console.print("[red]Beri ID dokumen atau --semua[/]")
            raise typer.Exit(code=1)
        row = conn.execute("SELECT doc_id FROM documents WHERE doc_id LIKE ? || '%'", (doc_id,)).fetchone()
        if row is None:
            console.print(f"[red]Dokumen '{doc_id}' tidak ditemukan[/]")
            raise typer.Exit(code=1)
        out = analysis_payload(conn, row[0], mode="ai" if ai else "deterministik",
                               narrator=AiNarrator(settings.analysis), force_ai=ai)
    ident = out["identitas"]
    console.print(Panel(f"{ident['jenis']} Nomor {ident['nomor']} tentang {ident['tentang']}\n"
                        f"status: {ident['status']} · pasal: {ident['jumlah_pasal']} · poin kunci: {out['jumlah_poin']}",
                        title=f"Analisa {out['versi']} · mode {out['mode_dipakai']}", border_style="cyan"))
    if out["ai"] and out["mode_dipakai"] != "ai":
        console.print(f"[yellow]AI tidak dipakai:[/] {escape(out['ai']['alasan'] or '')}")
        for v in out["ai"].get("pelanggaran") or []:
            console.print(f"   [dim]- {escape(v)}[/]")
    kal = out.get("ringkasan_ai") or out["ringkasan"]
    console.print("[bold]Ringkasan[/]")
    for s in kal:
        console.print(f" • {escape(s['kalimat'])} [dim]{', '.join(s.get('rujukan') or [])}[/]")
    console.print("[bold]Poin kunci utama[/]")
    for p in out["poin_utama"]:
        console.print(f" [{p['kategori']}] [cyan]{p['pasal']}[/] {escape((p.get('parafrase') or p['teks'])[:220])}")
    if json_out:
        json_out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[green]JSON ditulis:[/] {json_out}")


@app.command("klausul")
def klausul_cmd(
    doc_id: str = typer.Argument(...),
    kebutuhan: str = typer.Argument(..., help='Mis. "batas waktu pelaporan insiden"'),
    k: int = typer.Option(5, "--k"),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Pasal dalam satu dokumen yang paling relevan dengan kebutuhan Anda."""
    import sqlite3

    from hero.analysis.clauses import find_clauses
    from hero.vector import VectorService

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db) as conn:
        row = conn.execute("SELECT doc_id FROM documents WHERE doc_id LIKE ? || '%'", (doc_id,)).fetchone()
    if row is None:
        console.print(f"[red]Dokumen '{doc_id}' tidak ditemukan[/]")
        raise typer.Exit(code=1)
    with sqlite3.connect(settings.catalog_db) as conn:
        res = find_clauses(VectorService(settings), row[0], kebutuhan, k=k, conn=conn)
    if res.get("niat_terdeteksi"):
        console.print(f"[dim]niat terdeteksi: {', '.join(res['niat_terdeteksi'])}[/]")
    if res["alasan"]:
        console.print(f"[yellow]{res['alasan']}[/]")
    for h in res["hasil"]:
        console.print(f"[cyan]{h['rujukan']}[/] (hal. {h['halaman']}) {escape(h['cuplikan'][:240])}")


@app.command("fase2")
def fase2_cmd(
    markdown: Optional[Path] = typer.Option(Path("docs/FASE2_EVALUASI.md"), "--markdown"),
    telaah: Optional[Path] = typer.Option(Path("data/export/fase2_telaah_ahli.csv"), "--telaah",
                                          help="Templat CSV untuk telaah ahli (SME)."),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Ukur Fase 2: v1 vs v2 dan indikator keberhasilan URD."""
    import sqlite3

    from hero.analysis import AiNarrator
    from hero.analysis.evaluate import evaluate, phase2_indicators, render, review_template

    settings = load_settings(config)
    with sqlite3.connect(settings.catalog_db) as conn:
        ev = evaluate(conn)
        ai = AiNarrator(settings.analysis).status()
        ai["terverifikasi"] = bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='analysis_ai'").fetchone() and conn.execute(
            "SELECT 1 FROM analysis_ai WHERE status = 'ai' LIMIT 1").fetchone())
        ind = phase2_indicators(conn, ev, ai)
        if telaah:
            review_template(conn, telaah)
    t = Table(title="v1 vs v2", header_style="bold")
    for col in ("Metrik", "v1", "v2"):
        t.add_column(col, justify="left" if col == "Metrik" else "right")
    for k in ev["versi"]["v1"]:
        t.add_row(k, str(ev["versi"]["v1"][k]), str(ev["versi"]["v2"][k]))
    console.print(t)
    for i in ind:
        mark = "[green]tercapai[/]" if i["tercapai"] else "[yellow]belum[/]"
        console.print(f"{mark}  {i['indikator']}: {escape(str(i['aktual']))}")
    if markdown:
        markdown.write_text(render(ev, ind), encoding="utf-8")
        console.print(f"[green]Laporan ditulis:[/] {markdown}")
    if telaah:
        console.print(f"[green]Templat telaah ahli:[/] {telaah}")


# ---------------------------------------------------------------------------
# US-20 / US-20a — identitas halaman 1, penamaan baku, antrian koreksi
# US-24 — aturan kategori yang dapat dikonfigurasi
# ---------------------------------------------------------------------------
penamaan_app = typer.Typer(help="Templat nama berkas baku (US-20a).")
koreksi_app = typer.Typer(help="Antrian koreksi manual metadata (US-20).")
kategori_app = typer.Typer(help="Aturan kategori dari config/kategori.yaml (US-24).")
app.add_typer(penamaan_app, name="penamaan")
app.add_typer(koreksi_app, name="koreksi")
app.add_typer(kategori_app, name="kategori")


@app.command("identitas")
def identitas_cmd(
    path: Optional[Path] = typer.Argument(None, help="Satu PDF; kosongkan untuk survei seluruh KB."),
    ocr: bool = typer.Option(False, "--ocr", help="Selalu OCR halaman 1 (prosedur harfiah mitra)."),
    json_out: Optional[Path] = typer.Option(None, "--json"),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Baca nomor, tanggal, judul dari halaman pertama (OCR bila perlu)."""
    import sqlite3

    from hero.extract.firstpage import read_identity, survey

    settings = load_settings(config)
    mode = "ocr" if ocr else "auto"
    if path:
        out = read_identity(path, mode=mode, ocr_settings=settings.ocr).to_dict()
    else:
        with sqlite3.connect(settings.catalog_db) as conn:
            paths = [Path(r[0]) for r in conn.execute(
                "SELECT stored_path FROM documents WHERE stored_path IS NOT NULL")]
        out = survey([p for p in paths if p.exists()], mode=mode, ocr_settings=settings.ocr)
    console.print_json(json.dumps(out, default=str, ensure_ascii=False))
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(out, default=str, ensure_ascii=False, indent=2), encoding="utf-8")


@penamaan_app.command("cek")
def penamaan_cek(
    templat: Optional[str] = typer.Argument(None, help="Kosongkan untuk templat aktif."),
    contoh: int = typer.Option(5, "--contoh"),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Validasi templat dan pratinjau hasilnya pada dokumen nyata."""
    from hero.kb import correction
    from hero.kb.naming import TOKENS, active_template, check_template

    settings = load_settings(config)
    with Catalog(settings.catalog_db) as cat:
        templat = templat or active_template(cat.conn, settings.naming.template)
        chk = check_template(templat)
        console.print(f"Templat: [cyan]{escape(templat)}[/]")
        if not chk.valid:
            for e in chk.errors:
                console.print(f"[red]✗ {escape(e)}[/]")
            console.print("Token tersedia: " + ", ".join(f"{{{k}}}" for k in TOKENS))
            raise typer.Exit(code=1)
        console.print("Unsur wajib: " + ", ".join(correction.required_for(templat, settings.naming.required)))
        rep = correction.apply_template(cat, settings, template=templat, dry_run=True)
    for r in rep.rencana[:contoh]:
        console.print(f"  {escape(r['dari'])}\n  [green]→ {escape(r['ke'])}[/]")
    console.print(rep.to_dict() | {"contoh": f"{len(rep.rencana)} berkas akan berganti nama"})


@penamaan_app.command("set")
def penamaan_set(templat: str = typer.Argument(...),
                 config: Path = typer.Option("config/sources.yaml", "--config", "-c")) -> None:
    """Simpan templat aktif di katalog (berlaku untuk ingest berikutnya)."""
    from hero.kb.naming import save_template

    settings = load_settings(config)
    with Catalog(settings.catalog_db) as cat:
        chk = save_template(cat.conn, templat)
    if not chk.valid:
        console.print("[red]" + escape("; ".join(chk.errors)) + "[/]")
        raise typer.Exit(code=1)
    console.print("[green]Templat disimpan.[/] Jalankan `hero penamaan terapkan --apply` untuk berkas lama.")


@penamaan_app.command("terapkan")
def penamaan_terapkan(
    apply: bool = typer.Option(False, "--apply", help="Tanpa ini hanya rencana (dry-run)."),
    reread: bool = typer.Option(False, "--baca-ulang", help="Baca ulang halaman 1 semua PDF."),
    ocr: bool = typer.Option(False, "--ocr"),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Namai ulang semua berkas KB dengan templat aktif (#90)."""
    from hero.kb import correction

    settings = load_settings(config)
    with Catalog(settings.catalog_db) as cat:
        rep = correction.apply_template(cat, settings, dry_run=not apply, reread=reread,
                                        mode="ocr" if ocr else "auto")
    console.print_json(json.dumps(rep.to_dict(), ensure_ascii=False))
    if not apply:
        console.print("[yellow]Dry-run.[/] Tambahkan --apply untuk mengganti nama.")


@koreksi_app.command("daftar")
def koreksi_daftar(config: Path = typer.Option("config/sources.yaml", "--config", "-c")) -> None:
    """Dokumen yang menunggu koreksi manual."""
    from hero.kb import correction

    settings = load_settings(config)
    with Catalog(settings.catalog_db) as cat:
        rows, summ = correction.queue(cat.conn), correction.summary(cat.conn)
    t = Table(title=f"Antrian koreksi ({len(rows)}) — {summ}", header_style="bold")
    for col in ("doc_id", "berkas asli", "kurang", "terbaca"):
        t.add_column(col)
    for r in rows:
        seen = ", ".join(f"{k}={v}" for k, v in r["terbaca"].items() if v)
        t.add_row(r["doc_id"][:12], escape(r["berkas_asli"] or ""), ", ".join(r["kurang"]), escape(seen[:80]))
    console.print(t)


@koreksi_app.command("selesaikan")
def koreksi_selesaikan(
    doc_id: str = typer.Argument(...),
    jenis: Optional[str] = typer.Option(None, "--jenis"),
    nomor: Optional[str] = typer.Option(None, "--nomor"),
    tahun: Optional[int] = typer.Option(None, "--tahun"),
    tanggal: Optional[str] = typer.Option(None, "--tanggal", help="YYYY-MM-DD"),
    judul: Optional[str] = typer.Option(None, "--judul"),
    oleh: Optional[str] = typer.Option(None, "--oleh", help="Nama/NIP petugas (jejak audit)."),
    dry_run: bool = typer.Option(False, "--dry-run"),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Lengkapi unsur yang kurang, lalu beri nama baku dan pindahkan ke KB."""
    from hero.kb import correction

    settings = load_settings(config)
    with Catalog(settings.catalog_db) as cat:
        row = cat.conn.execute("SELECT doc_id FROM documents WHERE doc_id LIKE ? || '%'", (doc_id,)).fetchone()
        if row is None:
            console.print(f"[red]Dokumen '{doc_id}' tidak ditemukan[/]")
            raise typer.Exit(code=1)
        try:
            out = correction.resolve(cat, settings, row[0], {
                "jenis": jenis, "nomor": nomor, "tahun": tahun, "tanggal": tanggal, "judul": judul},
                oleh=oleh, dry_run=dry_run)
        except correction.CorrectionError as exc:
            console.print(f"[red]{escape(str(exc))}[/]")
            raise typer.Exit(code=1)
    console.print(f"[green]{escape(out['dari'] or '-')}[/]\n→ {escape(out['ke'])}")


@kategori_app.command("cek")
def kategori_cek(
    rules_file: Optional[Path] = typer.Option(None, "--aturan", help="Default: classification.rules_file"),
    belahan: Optional[str] = typer.Option(None, "--belahan", help="latih | uji (kosong = semua)"),
    json_out: Optional[Path] = typer.Option(None, "--json"),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Validasi berkas aturan dan ukur akurasinya terhadap label sektor JDIH."""
    import sqlite3

    from hero.kb.classify import RulesError, load_rules
    from hero.kb.classify_eval import evaluate_jdih

    settings = load_settings(config)
    try:
        rules = load_rules(rules_file or settings.classification.rules_file)
    except RulesError as exc:
        console.print(f"[red]Aturan tidak valid:[/] {escape(str(exc))}")
        raise typer.Exit(code=1)
    console.print(f"[green]✓[/] {len(rules.kategori)} kategori dari {rules.sumber} (versi {rules.versi})")
    with sqlite3.connect(settings.catalog_db) as conn:
        conn.row_factory = sqlite3.Row
        rep = evaluate_jdih(conn, rules, split=belahan)
    t = Table(title=f"Akurasi vs JDIH ({rep['belahan']}): {rep['akurasi']} dari {rep['dinilai']}",
              header_style="bold")
    for col in ("kategori", "label", "prediksi", "presisi", "recall"):
        t.add_column(col, justify="left" if col == "kategori" else "right")
    for code, v in rep["per_kategori"].items():
        t.add_row(code, *(str(v[k]) for k in ("label", "prediksi", "presisi", "recall")))
    console.print(t)
    console.print(rep["per_kelompok"])
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")


@kategori_app.command("uji")
def kategori_uji(judul: str = typer.Argument(..., help="Judul/perihal peraturan"),
                 config: Path = typer.Option("config/sources.yaml", "--config", "-c")) -> None:
    """Coba aturan pada satu judul."""
    from hero.kb.classify import classify, load_rules
    from hero.models import RegulationMetadata

    settings = load_settings(config)
    cat, hits = classify(RegulationMetadata(title=judul), "", rules=load_rules(settings.classification.rules_file))
    console.print(f"[cyan]{cat}[/]  ({', '.join(hits) or 'tidak ada kata kunci cocok'})")


# ---------------------------------------------------------------------------
# SPIKE #42 — folder PDF vs vektor (dijalankan di VPS)
# ---------------------------------------------------------------------------
spike_app = typer.Typer(help="SPIKE #42: waktu proses & retrieval folder PDF vs vektor.")
app.add_typer(spike_app, name="spike")


@spike_app.command("unduh")
def spike_unduh(
    ke: Path = typer.Option(Path("data/spike/raw"), "--ke"),
    maks: int = typer.Option(3000, "--maks"),
    per_putaran: int = typer.Option(200, "--per-putaran"),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Unduh PDF mentah dari share OneDrive (tanpa ingest), dapat dilanjutkan."""
    import time as _t

    from hero.ingest.onedrive import download_onedrive_share

    settings = load_settings(config)
    shares = settings.enabled_shares
    if not shares:
        console.print("[red]Tidak ada onedrive_shares aktif di konfigurasi[/]")
        raise typer.Exit(code=1)
    share = shares[0]
    ke.mkdir(parents=True, exist_ok=True)
    started, got, errors = _t.perf_counter(), 0, []
    while got < maks:
        paths, errs = download_onedrive_share(
            share.share_url, ke, max_files=min(per_putaran, maks - got), subfolder=share.subfolder,
            exclude=tuple(share.exclude_patterns or ()), skip=lambda name: (ke / name).exists())
        errors += errs
        got += len(paths)
        console.print(f"+{len(paths)} (total baru {got}) · {len(errs)} galat")
        if not paths:
            break
    secs = _t.perf_counter() - started
    files = list(ke.glob("*.pdf"))
    mb = round(sum(f.stat().st_size for f in files) / 1e6, 1)
    out = {"berkas": len(files), "baru": got, "mb": mb, "detik": round(secs, 1),
           "detik_per_berkas": round(secs / got, 2) if got else None, "galat": errors[:20]}
    (ke.parent / "fetch.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(out)


@spike_app.command("jalankan")
def spike_jalankan(
    raw: Path = typer.Option(Path("data/spike/raw"), "--raw"),
    kerja: Path = typer.Option(Path("data/spike/work"), "--kerja"),
    titik: str = typer.Option("100,500,1000,2000", "--titik"),
    semantik: bool = typer.Option(True, "--semantik/--tanpa-semantik"),
    model_cache: Optional[Path] = typer.Option(None, "--model-cache"),
    json_out: Path = typer.Option(Path("data/spike/hasil.json"), "--json"),
    markdown: Optional[Path] = typer.Option(None, "--markdown"),
    label: str = typer.Option("folder OneDrive mitra (HERO/downloads)", "--label"),
    config: Path = typer.Option("config/sources.yaml", "--config", "-c"),
) -> None:
    """Ukur kedua jalur pada korpus nyata dan tulis tabel hasilnya."""
    import platform

    from hero.spike import render, run_spike

    settings = load_settings(config)
    res = run_spike(raw, kerja, checkpoints=tuple(int(x) for x in titik.split(",")), semantic=semantik,
                    label=label,
                    model_cache=model_cache, settings=settings, progress=lambda m: console.print(escape(m)))
    res["host"] = f"{platform.node()} · {platform.machine()} · Python {platform.python_version()}"
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    fetch = raw.parent / "fetch.json"
    if markdown:
        markdown.write_text(render(res, fetch=json.loads(fetch.read_text()) if fetch.exists() else None,
                                   host=res["host"]), encoding="utf-8")
    console.print(f"[green]Selesai[/] {res['detik_total']} s · JSON {json_out}")


from hero.cli_bridge import bridge_app  # noqa: E402 - jembatan ke backend tim
from hero.cli_data import (  # noqa: E402 - data workstream commands
    akses_app, ekstrak_ulang_cmd, harmonisasi_app, register_penamaan, scan_app, snapshot_cmd,
)

app.command("snapshot")(snapshot_cmd)
app.command("ekstrak-ulang")(ekstrak_ulang_cmd)
app.add_typer(harmonisasi_app, name="harmonisasi")
app.add_typer(scan_app, name="scan")
app.add_typer(akses_app, name="akses")
app.add_typer(bridge_app, name="bridge")
register_penamaan(penamaan_app)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
