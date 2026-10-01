#!/usr/bin/env python3
"""
scripts/scan_benchmark.py
Uji performa dan benchmark perolehan kandidat dokumen secara langsung (live)
terhadap 3 sumber data:
1. Regulasi OJK (SharePoint ASP.NET postback)
2. JDIH OJK (DataTables JSON API)
3. OneDrive Public (SharePoint REST recursive folder traversal)

Penggunaan:
    python scripts/scan_benchmark.py --source ojk --limit-pages 5
    python scripts/scan_benchmark.py --source jdih --limit-pages 5
    python scripts/scan_benchmark.py --source onedrive --limit-pages 10
    python scripts/scan_benchmark.py --source all --limit-pages 5
"""
import argparse
import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Tambahkan root repo ke sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.crawlers.sharepoint_postback import SharepointPostbackCrawler
from app.crawlers.jdih_api import JdihApiCrawler
from app.crawlers.onedrive_share import OneDriveShareCrawler
from app.crawlers.base import ScanResult, PdfCandidate

DEFAULT_SOURCES = {
    "ojk": {
        "name": "Regulasi OJK",
        "url": "https://ojk.go.id/id/regulasi/default.aspx",
        "crawler_cls": SharepointPostbackCrawler,
        "default_pages": 5,
        "adapter": "sharepoint_postback",
    },
    "jdih": {
        "name": "JDIH OJK",
        "url": "https://jdih.ojk.go.id/",
        "crawler_cls": JdihApiCrawler,
        "default_pages": 5,
        "adapter": "jdih_api",
    },
    "onedrive": {
        "name": "OneDrive Public DPEA",
        "url": "https://oneojk-my.sharepoint.com/:f:/g/personal/redacted_user_ojk_go_id/redacted_iduRwqT5X1zPBi_d1AAfA8Ec-W6i3BTN66ZgJI1rA?e=redacted_token",
        "crawler_cls": OneDriveShareCrawler,
        "default_pages": 15,
        "adapter": "onedrive_share",
    },
}


def export_csv(candidates: List[PdfCandidate], filepath: Path):
    """Mengekspor kandidat ke format CSV standar."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "url",
        "filename",
        "document_title",
        "doc_kind",
        "regulation_number",
        "regulation_type",
        "bidang",
        "sub_bidang",
        "release_date",
        "size_bytes",
        "size_source",
        "source_path",
        "found_on_page",
    ]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in candidates:
            writer.writerow({
                "url": c.url,
                "filename": c.filename,
                "document_title": c.document_title or "",
                "doc_kind": c.doc_kind or "",
                "regulation_number": c.regulation_number or "",
                "regulation_type": c.regulation_type or "",
                "bidang": c.bidang or "",
                "sub_bidang": c.sub_bidang or "",
                "release_date": c.release_date.isoformat() if c.release_date else "",
                "size_bytes": c.size_bytes if c.size_bytes is not None else "",
                "size_source": c.size_source or "",
                "source_path": c.source_path or "",
                "found_on_page": c.found_on_page or "",
            })


def run_benchmark_for_source(
    src_key: str,
    limit_pages: int,
    max_candidates: int,
    head_for_size: bool,
    reports_dir: Path,
) -> Dict[str, Any]:
    src_info = DEFAULT_SOURCES[src_key]
    print(f"\n=======================================================")
    print(f" Memulai Benchmark: {src_info['name']} ({src_key})")
    print(f" URL    : {src_info['url']}")
    print(f" Adapter: {src_info['adapter']}")
    print(f" Batas  : max_pages={limit_pages}, max_candidates={max_candidates}, head_for_size={head_for_size}")
    print(f"=======================================================")

    crawler_cls = src_info["crawler_cls"]
    crawler = crawler_cls(delay_seconds=0.2, head_for_size=head_for_size, allow_private=False)

    t0 = time.time()

    def _progress(pages: int, cands: int):
        sys.stdout.write(f"\r  -> Progress: {pages} halaman/folder dijelajahi, {cands} berkas PDF ditemukan...")
        sys.stdout.flush()

    res: ScanResult = crawler.scan(
        src_info["url"],
        depth=10,
        max_pages=limit_pages,
        max_candidates=max_candidates,
        progress=_progress,
    )
    print()  # newline after progress

    elapsed = round(time.time() - t0, 2)
    csv_file = reports_dir / f"scan-benchmark-{src_key}.csv"
    export_csv(res.candidates, csv_file)

    with_size_count = sum(1 for c in res.candidates if c.size_bytes is not None)

    summary = {
        "key": src_key,
        "name": src_info["name"],
        "adapter": src_info["adapter"],
        "url": src_info["url"],
        "duration_sec": elapsed,
        "pages_visited": res.pages_visited,
        "candidates_count": len(res.candidates),
        "with_size_count": with_size_count,
        "stats": res.stats,
        "errors": res.errors,
        "blocked": res.blocked,
        "truncated": res.truncated,
        "csv_path": str(csv_file.relative_to(REPO_ROOT)),
    }

    print(f" Hasil {src_info['name']}:")
    print(f" - Durasi: {elapsed} detik")
    print(f" - Halaman/Folder Dikunjungi: {res.pages_visited}")
    print(f" - Berkas PDF Ditemukan    : {len(res.candidates)}")
    print(f" - Berkas Dengan Ukuran     : {with_size_count} / {len(res.candidates)}")
    print(f" - Rincian Peran Dokumen    : {res.stats.get('by_doc_kind', {})}")
    print(f" - Error / Catatan         : {len(res.errors)}")
    print(f" - CSV disimpan di          : {csv_file}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Live Benchmark Crawler HERO Backend (Step 10)")
    parser.add_argument("--source", choices=["ojk", "jdih", "onedrive", "all"], default="all", help="Sumber data target")
    parser.add_argument("--limit-pages", type=int, default=None, help="Batas jumlah halaman/folder")
    parser.add_argument("--max-candidates", type=int, default=3000, help="Batas maksimum kandidat")
    parser.add_argument("--no-head", action="store_true", help="Jangan lakukan HEAD probing ukuran PDF")
    parser.add_argument("--out", type=str, default=None, help="Jalur berkas markdown laporan benchmark")
    args = parser.parse_args()

    reports_dir = REPO_ROOT / "docs" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    today_str = datetime.now().strftime("%Y-%m-%d")
    out_md = Path(args.out) if args.out else reports_dir / f"scan-benchmark-{today_str}.md"

    sources_to_run = list(DEFAULT_SOURCES.keys()) if args.source == "all" else [args.source]
    head_for_size = not args.no_head

    results: List[Dict[str, Any]] = []
    for s_key in sources_to_run:
        default_limit = DEFAULT_SOURCES[s_key]["default_pages"]
        limit_p = args.limit_pages if args.limit_pages is not None else default_limit
        res_summary = run_benchmark_for_source(
            src_key=s_key,
            limit_pages=limit_p,
            max_candidates=args.max_candidates,
            head_for_size=head_for_size,
            reports_dir=reports_dir,
        )
        results.append(res_summary)

    # Susun laporan Markdown
    md_lines = [
        f"# Hasil Live Scan Benchmark — HERO Backend (Langkah 10)",
        f"",
        f"> **Tanggal Pengujian:** {datetime.now().strftime('%d %B %Y %H:%M:%S WIB')}  ",
        f"> **Metode:** Uji live langsung ke endpoint publik internet (tanpa Playwright / browser headless).",
        f"",
        f"## 1. Ringkasan Performa Benchmark",
        f"",
        f"| Sumber Data | Adapter | Durasi (detik) | Halaman / Folder | PDF Ditemukan | Ukuran Terdeteksi | Rincian Doc Kind | Status |",
        f"|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        kinds_str = ", ".join(f"{k}: {v}" for k, v in r["stats"].get("by_doc_kind", {}).items()) or "-"
        status_str = "Sukses" if not r["blocked"] and not r["errors"] else ("Terblokir" if r["blocked"] else f"Selesai ({len(r['errors'])} catatan)")
        md_lines.append(
            f"| **{r['name']}** | `{r['adapter']}` | {r['duration_sec']}s | {r['pages_visited']} | {r['candidates_count']} | {r['with_size_count']}/{r['candidates_count']} | {kinds_str} | {status_str} |"
        )

    md_lines.extend([
        f"",
        f"## 2. Rincian dan Berkas CSV Hasil Pemindaian",
        f"",
    ])

    for r in results:
        md_lines.extend([
            f"### 2.{results.index(r)+1} {r['name']} (`{r['key']}`)",
            f"- **URL Target:** {r['url']}",
            f"- **Adapter:** `{r['adapter']}`",
            f"- **Waktu Eksekusi:** {r['duration_sec']} detik",
            f"- **Halaman/Folder Dikunjungi:** {r['pages_visited']}",
            f"- **Total Berkas PDF:** {r['candidates_count']}",
            f"- **Berkas dengan Ukuran:** {r['with_size_count']} ({'100%' if r['candidates_count'] > 0 and r['with_size_count'] == r['candidates_count'] else f'{round(r['with_size_count']/max(1,r['candidates_count'])*100,1)}%'})",
            f"- **Berkas CSV Ekspor:** [`{r['csv_path']}`]({r['csv_path']})",
            f"- **Statistik Lengkap:**",
            f"  ```json",
            f"  {r['stats']}",
            f"  ```",
        ])
        if r["errors"]:
            md_lines.append(f"- **Catatan / Error:**")
            for err in r["errors"]:
                md_lines.append(f"  - {err}")
        md_lines.append("")

    out_md.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\n[OK] Laporan benchmark lengkap disimpan ke: {out_md}")


if __name__ == "__main__":
    main()
