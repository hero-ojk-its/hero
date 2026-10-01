#!/usr/bin/env python3
"""
scripts/scan_benchmark.py
Uji performa dan benchmark perolehan kandidat dokumen secara langsung (live)
terhadap 3 sumber data:
1. Regulasi OJK (SharePoint ASP.NET postback)
2. JDIH OJK (DataTables JSON API)
3. OneDrive Public (SharePoint REST recursive folder traversal)

Penggunaan:
    python scripts/scan_benchmark.py --source ojk
    python scripts/scan_benchmark.py --source jdih
    python scripts/scan_benchmark.py --source onedrive
    python scripts/scan_benchmark.py --source all
"""
import argparse
import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

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
        "adapter": "sharepoint_postback",
        "default_pages": 5,
        "ground_truth_num": 1700,
        "ground_truth_label": "± 1.700 regulasi",
    },
    "jdih": {
        "name": "JDIH OJK",
        "url": "https://jdih.ojk.go.id/",
        "crawler_cls": JdihApiCrawler,
        "adapter": "jdih_api",
        "default_pages": 5,
        "ground_truth_num": 450,
        "ground_truth_label": "± 400–500 regulasi",
    },
    "onedrive": {
        "name": "OneDrive Public DPEA",
        "url": "https://oneojk-my.sharepoint.com/:f:/g/personal/redacted_user_ojk_go_id/redacted_iduRwqT5X1zPBi_d1AAfA8Ec-W6i3BTN66ZgJI1rA?e=redacted_token",
        "crawler_cls": OneDriveShareCrawler,
        "adapter": "onedrive_share",
        "default_pages": 500,
        "ground_truth_num": 2612,
        "ground_truth_label": "± 2.612 berkas",
    },
}


def is_complete_4_attrs(c: PdfCandidate) -> bool:
    """Memeriksa kelengkapan 4 atribut wajib: URL, nama dokumen, nama berkas, dan ukuran."""
    has_url = bool(c.url and c.url.strip())
    has_doc_title = bool(c.document_title and c.document_title.strip())
    has_filename = bool(c.filename and c.filename.strip())
    has_size = c.size_bytes is not None and c.size_bytes > 0
    return has_url and has_doc_title and has_filename and has_size


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
    limit_pages: Optional[int],
    max_candidates: int,
    head_for_size: bool,
    reports_dir: Path,
) -> Dict[str, Any]:
    src_info = DEFAULT_SOURCES[src_key]
    effective_pages = limit_pages if limit_pages is not None else src_info["default_pages"]

    print(f"\n=======================================================")
    print(f" Memulai Benchmark: {src_info['name']} ({src_key})")
    print(f" URL          : {src_info['url']}")
    print(f" Adapter      : {src_info['adapter']}")
    print(f" Ground Truth : {src_info['ground_truth_label']}")
    print(f" Batas Scan   : max_pages={effective_pages}, max_candidates={max_candidates}, head_for_size={head_for_size}")
    print(f"=======================================================")

    crawler_cls = src_info["crawler_cls"]
    crawler = crawler_cls(delay_seconds=0.1, head_for_size=head_for_size, allow_private=False)

    t0 = time.time()

    def _progress(pages: int, cands: int):
        sys.stdout.write(f"\r  -> Progress: {pages} halaman/folder dijelajahi, {cands} berkas PDF ditemukan...")
        sys.stdout.flush()

    res: ScanResult = crawler.scan(
        src_info["url"],
        depth=10,
        max_pages=effective_pages,
        max_candidates=max_candidates,
        progress=_progress,
    )
    print()  # newline after progress

    elapsed = round(time.time() - t0, 2)
    csv_file = reports_dir / f"scan-benchmark-{src_key}.csv"
    export_csv(res.candidates, csv_file)

    with_size_count = sum(1 for c in res.candidates if c.size_bytes is not None and c.size_bytes > 0)
    complete_4_count = sum(1 for c in res.candidates if is_complete_4_attrs(c))
    candidates_count = len(res.candidates)

    regulations_count = res.stats.get("regulations_found", candidates_count)
    ground_truth_num = src_info["ground_truth_num"]

    # Selisih: jika OJK atau JDIH gunakan perbandingan regulasi jika ada, untuk onedrive gunakan total berkas
    primary_metric = regulations_count if src_key in ("ojk", "jdih") else candidates_count
    selisih_num = primary_metric - ground_truth_num
    selisih_str = f"{selisih_num:+d}" if selisih_num != 0 else "0 (tepat)"

    pct_size = round((with_size_count / max(1, candidates_count)) * 100, 1)
    pct_4_attr = round((complete_4_count / max(1, candidates_count)) * 100, 1)

    requests_made = res.stats.get("requests_made", getattr(crawler, "requests_count", 0))

    summary = {
        "key": src_key,
        "name": src_info["name"],
        "adapter": src_info["adapter"],
        "url": src_info["url"],
        "duration_sec": elapsed,
        "requests_made": requests_made,
        "pages_visited": res.pages_visited,
        "regulations_found": regulations_count,
        "candidates_count": candidates_count,
        "with_size_count": with_size_count,
        "pct_size": pct_size,
        "complete_4_count": complete_4_count,
        "pct_4_attr": pct_4_attr,
        "ground_truth_label": src_info["ground_truth_label"],
        "ground_truth_num": ground_truth_num,
        "selisih_str": selisih_str,
        "stats": res.stats,
        "errors": res.errors,
        "blocked": res.blocked,
        "truncated": res.truncated,
        "csv_path": str(csv_file.relative_to(REPO_ROOT)),
    }

    print(f" Hasil {src_info['name']}:")
    print(f" - Durasi              : {elapsed} detik")
    print(f" - Jumlah Requests     : {requests_made}")
    print(f" - Halaman/Folder      : {res.pages_visited}")
    if src_key == "ojk":
        print(f" - Jumlah Regulasi     : {regulations_count}")
        print(f" - Jumlah Berkas PDF   : {candidates_count}")
    else:
        print(f" - Jumlah Regulasi/Item: {regulations_count}")
        print(f" - Jumlah Berkas PDF   : {candidates_count}")
    print(f" - Ukuran Terdeteksi   : {with_size_count} / {candidates_count} ({pct_size}%)")
    print(f" - Lengkap 4 Atribut   : {complete_4_count} / {candidates_count} ({pct_4_attr}%)")
    print(f" - Ground Truth        : {src_info['ground_truth_label']}")
    print(f" - Selisih vs GT       : {selisih_str}")
    print(f" - Rincian Doc Kind    : {res.stats.get('by_doc_kind', {})}")
    print(f" - Error / Catatan     : {len(res.errors)}")
    print(f" - CSV disimpan di      : {csv_file}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Live Benchmark Crawler HERO Backend (Step 10)")
    parser.add_argument("--source", choices=["ojk", "jdih", "onedrive", "all"], default="all", help="Sumber data target")
    parser.add_argument("--limit-pages", type=int, default=None, help="Batas jumlah halaman/folder (opsional)")
    parser.add_argument("--max-candidates", type=int, default=10000, help="Batas maksimum kandidat")
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
        res_summary = run_benchmark_for_source(
            src_key=s_key,
            limit_pages=args.limit_pages,
            max_candidates=args.max_candidates,
            head_for_size=head_for_size,
            reports_dir=reports_dir,
        )
        results.append(res_summary)

    # Susun tabel ringkasan Markdown
    md_lines = [
        f"# Hasil Live Scan Benchmark — HERO Backend (Langkah 10)",
        f"",
        f"> **Tanggal Pengujian:** {datetime.now().strftime('%d %B %Y %H:%M:%S WIB')}  ",
        f"> **Metode:** Uji live benchmark penuh ke endpoint publik internet (tanpa Playwright / browser headless).",
        f"",
        f"## 1. Ringkasan Performa Benchmark dan Perbandingan Ground Truth",
        f"",
        f"| Sumber Data | Adapter | Durasi | Requests | Halaman/Folder | Regulasi | PDF Ditemukan | Lengkap 4 Atribut | Ukuran Terdeteksi | Ground Truth | Selisih | Status |",
        f"|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        status_str = "Sukses" if not r["blocked"] and not r["errors"] else ("Terblokir" if r["blocked"] else f"Selesai ({len(r['errors'])} catatan)")
        reg_count_display = str(r["regulations_found"])
        pdf_count_display = str(r["candidates_count"])
        comp_display = f"{r['complete_4_count']}/{r['candidates_count']} ({r['pct_4_attr']}%)"
        size_display = f"{r['with_size_count']}/{r['candidates_count']} ({r['pct_size']}%)"
        dur_display = f"{r['duration_sec']}s"

        md_lines.append(
            f"| **{r['name']}** | `{r['adapter']}` | {dur_display} | {r['requests_made']} | {r['pages_visited']} | {reg_count_display} | {pdf_count_display} | {comp_display} | {size_display} | {r['ground_truth_label']} | {r['selisih_str']} | {status_str} |"
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
            f"- **Waktu Eksekusi:** {r['duration_sec']} detik ({r['requests_made']} requests)",
            f"- **Halaman/Folder Dikunjungi:** {r['pages_visited']}",
            f"- **Jumlah Regulasi Ditemukan:** {r['regulations_found']}",
            f"- **Jumlah Berkas PDF Ditemukan:** {r['candidates_count']}",
            f"- **Lengkap 4 Atribut (URL, Judul, Nama Berkas, Ukuran):** {r['complete_4_count']}/{r['candidates_count']} ({r['pct_4_attr']}%)",
            f"- **Ukuran Terdeteksi:** {r['with_size_count']}/{r['candidates_count']} ({r['pct_size']}%)",
            f"- **Ground Truth:** {r['ground_truth_label']} (Selisih: {r['selisih_str']})",
            f"- **Berkas CSV Ekspor:** [`{r['csv_path']}`]({r['csv_path']})",
            f"- **Rincian doc_kind:** `{r['stats'].get('by_doc_kind', {})}`",
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
