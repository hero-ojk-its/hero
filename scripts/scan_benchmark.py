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
import json
import os
import posixpath
import re
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
        "default_pages": 500,  # Tanpa batas artifisial, ikuti halaman sampai selesai
        "ground_truth_num": 1700,
        "ground_truth_label": "± 1.700 regulasi",
    },
    "jdih": {
        "name": "JDIH OJK",
        "url": "https://jdih.ojk.go.id/",
        "crawler_cls": JdihApiCrawler,
        "adapter": "jdih_api",
        "default_pages": 200,  # 20 halaman @ 50 item = 986 records total
        "ground_truth_num": 450,
        "ground_truth_label": "± 400–500 regulasi",
    },
    "onedrive": {
        "name": "OneDrive Public DPEA",
        "url": "https://oneojk-my.sharepoint.com/:f:/g/personal/[link share OneDrive DPEA]/redacted_iduRwqT5X1zPBi_d1AAfA8Ec-W6i3BTN66ZgJI1rA?e=redacted_token",
        "crawler_cls": OneDriveShareCrawler,
        "adapter": "onedrive_share",
        "default_pages": 1000,
        "ground_truth_num": None,
        "ground_truth_label": "Belum ada dari mitra",
    },
}


def is_complete_legal_metadata(c: PdfCandidate) -> bool:
    """Memeriksa kelengkapan 3 metadata hukum utama: jenis regulasi, nomor regulasi, dan tanggal/tahun rilis."""
    has_type = bool(c.regulation_type and c.regulation_type.strip())
    has_num = bool(c.regulation_number and c.regulation_number.strip())
    has_date_or_year = bool(c.release_date or getattr(c, "release_year", None))
    return has_type and has_num and has_date_or_year


def export_csv(candidates: List[PdfCandidate], filepath: Path):
    """Mengekspor kandidat ke format CSV standar."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "url",
        "filename",
        "document_title",
        "doc_kind",
        "regulation_number",
        "raw_regulation_number",
        "regulation_type",
        "bidang",
        "sub_bidang",
        "release_date",
        "release_year",
        "effective_date",
        "match_warning",
        "size_bytes",
        "size_source",
        "source_path",
        "found_on_page",
    ]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in candidates:
            # Mask nama personil pada file NDA
            fname = c.filename
            doc_title = c.document_title or ""
            src_path = c.source_path or ""
            url_val = c.url or ""
            found_page = c.found_on_page or ""

            # Untuk OneDrive atau candidate dengan source_path, gunakan relative source_path pada kolom url
            if c.source_path:
                url_val = c.source_path

            if "/personal/" in found_page:
                found_page = posixpath.basename(found_page.rstrip("/")) or found_page

            if c.doc_kind == "non_regulasi" and "nda" in fname.lower():
                fname = "NDA_Personil_Protected.pdf"
                doc_title = "NDA Personil Protected"
                src_path = "Administration/NDA_Personil_Protected.pdf"
                url_val = src_path
                found_page = "Administration"

            writer.writerow({
                "url": url_val,
                "filename": fname,
                "document_title": doc_title,
                "doc_kind": c.doc_kind or "",
                "regulation_number": c.regulation_number or "",
                "raw_regulation_number": getattr(c, "raw_regulation_number", None) or "",
                "regulation_type": c.regulation_type or "",
                "bidang": c.bidang or "",
                "sub_bidang": c.sub_bidang or "",
                "release_date": c.release_date.isoformat() if c.release_date else "",
                "release_year": getattr(c, "release_year", None) or (c.release_date.year if c.release_date else ""),
                "effective_date": c.effective_date.isoformat() if getattr(c, "effective_date", None) else "",
                "match_warning": getattr(c, "match_warning", None) or "",
                "size_bytes": c.size_bytes if c.size_bytes is not None else "",
                "size_source": c.size_source or "",
                "source_path": src_path,
                "found_on_page": found_page,
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

    page_boundary_label = f"limit_pages={limit_pages}" if limit_pages is not None else f"penuh (tanpa batas, default max={effective_pages})"

    print(f"\n=======================================================")
    print(f" Memulai Benchmark: {src_info['name']} ({src_key})")
    print(f" URL          : {'[link share OneDrive DPEA]' if src_key == 'onedrive' else src_info['url']}")
    print(f" Adapter      : {src_info['adapter']}")
    print(f" Ground Truth : {src_info['ground_truth_label']}")
    print(f" Batas Scan   : {page_boundary_label}, max_candidates={max_candidates}, head_for_size={head_for_size}")
    print(f"=======================================================")

    crawler_cls = src_info["crawler_cls"]
    crawler = crawler_cls(delay_seconds=0.02, head_for_size=head_for_size, allow_private=False)

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
    complete_legal_count = sum(1 for c in res.candidates if is_complete_legal_metadata(c))
    candidates_count = len(res.candidates)

    regulations_count = res.stats.get("regulations_found", candidates_count)
    ground_truth_num = src_info["ground_truth_num"]

    if ground_truth_num is not None:
        primary_metric = regulations_count if src_key in ("ojk", "jdih") else candidates_count
        selisih_num = primary_metric - ground_truth_num
        if src_key == "jdih":
            selisih_str = f"{selisih_num:+d} (Di atas rentang mitra 400–500)"
        else:
            selisih_str = f"{selisih_num:+d}" if selisih_num != 0 else "0 (tepat)"
    else:
        selisih_str = "Belum ada dari mitra"

    pct_size = round((with_size_count / max(1, candidates_count)) * 100, 1)
    pct_legal = round((complete_legal_count / max(1, candidates_count)) * 100, 1)

    requests_made = res.stats.get("requests_made", getattr(crawler, "requests_count", 0))
    match_warnings_count = res.stats.get("match_warnings_count", sum(1 for c in res.candidates if getattr(c, "match_warning", None)))

    summary = {
        "key": src_key,
        "name": src_info["name"],
        "adapter": src_info["adapter"],
        "url": "[link share OneDrive DPEA]" if src_key == "onedrive" else src_info["url"],
        "duration_sec": elapsed,
        "requests_made": requests_made,
        "pages_visited": res.pages_visited,
        "page_boundary": page_boundary_label,
        "records_total": res.stats.get("records_total"),
        "subfolders_count": res.stats.get("subfolders_count"),
        "match_warnings_count": match_warnings_count,
        "regulations_found": regulations_count,
        "candidates_count": candidates_count,
        "with_size_count": with_size_count,
        "pct_size": pct_size,
        "complete_legal_count": complete_legal_count,
        "pct_legal": pct_legal,
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
    if res.stats.get("records_total"):
        print(f" - Total Rekod Situs   : {res.stats.get('records_total')}")
    if res.stats.get("subfolders_count"):
        print(f" - Rincian Subfolder   : {res.stats.get('subfolders_count')}")
    if src_key == "ojk":
        print(f" - Jumlah Regulasi     : {regulations_count}")
        print(f" - Jumlah Berkas PDF   : {candidates_count}")
    else:
        print(f" - Jumlah Regulasi/Item: {regulations_count}")
        print(f" - Jumlah Berkas PDF   : {candidates_count}")
    print(f" - Ukuran Terdeteksi   : {with_size_count} / {candidates_count} ({pct_size}%)")
    print(f" - Lengkap Metadata    : {complete_legal_count} / {candidates_count} ({pct_legal}%)")
    print(f" - Match Warnings      : {match_warnings_count}")
    print(f" - Ground Truth        : {src_info['ground_truth_label']}")
    print(f" - Selisih vs GT       : {selisih_str}")
    print(f" - Rincian Doc Kind    : {res.stats.get('by_doc_kind', {})}")
    print(f" - Error / Catatan     : {len(res.errors)}")
    print(f" - CSV disimpan di      : {csv_file}")
    return summary


def main():
    import json
    parser = argparse.ArgumentParser(description="Live Benchmark Crawler HERO Backend (Step 10d)")
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
    cache_file = reports_dir / "benchmark_cache.json"

    # Muat cache benchmark sebelumnya jika ada
    cached_results: Dict[str, Any] = {}
    if cache_file.exists():
        try:
            cached_results = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            cached_results = {}

    sources_to_run = list(DEFAULT_SOURCES.keys()) if args.source == "all" else [args.source]
    head_for_size = not args.no_head

    for s_key in sources_to_run:
        res_summary = run_benchmark_for_source(
            src_key=s_key,
            limit_pages=args.limit_pages,
            max_candidates=args.max_candidates,
            head_for_size=head_for_size,
            reports_dir=reports_dir,
        )
        cached_results[s_key] = res_summary

    # Simpan kembali cache
    try:
        cache_file.write_text(json.dumps(cached_results, indent=2), encoding="utf-8")
    except Exception as err:
        print(f"Warning: Gagal menyimpan benchmark_cache.json: {err}")

    # Gabungkan semua sumber yang ada di cache (urutkan sesuai DEFAULT_SOURCES)
    all_summaries: List[Dict[str, Any]] = []
    for k in DEFAULT_SOURCES.keys():
        if k in cached_results:
            all_summaries.append(cached_results[k])

    # Susun tabel ringkasan Markdown Gabungan 3 Sumber
    md_lines = [
        f"# Hasil Live Scan Benchmark — HERO Backend (Langkah 10d)",
        f"",
        f"> **Tanggal Pengujian:** {datetime.now().strftime('%d %B %Y %H:%M:%S WIB')}  ",
        f"> **Metode:** Uji live benchmark penuh ke endpoint publik internet (tanpa Playwright / browser headless).",
        f"",
        f"## 1. Ringkasan Performa Benchmark dan Perbandingan Ground Truth",
        f"",
        f"| Sumber Data | Adapter | Batas Paging | Halaman Terakhir | Regulasi | PDF | Lengkap Metadata Hukum | Match Warnings | Ground Truth | Selisih | Durasi | Requests | Status |",
        f"|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for r in all_summaries:
        status_str = "Sukses" if not r["blocked"] and not r["errors"] else ("Terblokir" if r["blocked"] else f"Selesai ({len(r['errors'])} catatan)")
        reg_count_display = str(r["regulations_found"])
        pdf_count_display = str(r["candidates_count"])
        comp_display = f"{r.get('complete_legal_count', r.get('complete_4_count', 0))}/{r['candidates_count']} ({r.get('pct_legal', r.get('pct_4_attr', 0.0))}%)"
        warn_display = str(r["match_warnings_count"])
        dur_display = f"{r['duration_sec']}s"

        md_lines.append(
            f"| **{r['name']}** | `{r['adapter']}` | {r['page_boundary']} | {r['pages_visited']} | {reg_count_display} | {pdf_count_display} | {comp_display} | {warn_display} | {r['ground_truth_label']} | {r['selisih_str']} | {dur_display} | {r['requests_made']} | {status_str} |"
        )

    md_lines.extend([
        f"",
        f"## 2. Rincian dan Berkas CSV Hasil Pemindaian",
        f"",
    ])

    for r in all_summaries:
        md_lines.extend([
            f"### 2.{all_summaries.index(r)+1} {r['name']} (`{r['key']}`)",
            f"- **URL Target:** {r['url']}",
            f"- **Adapter:** `{r['adapter']}`",
            f"- **Batas Paging:** {r['page_boundary']}",
            f"- **Waktu Eksekusi:** {r['duration_sec']} detik ({r['requests_made']} requests)",
            f"- **Halaman/Folder Dikunjungi:** {r['pages_visited']}",
            f"- **Jumlah Regulasi Ditemukan:** {r['regulations_found']}",
            f"- **Jumlah Berkas PDF Ditemukan:** {r['candidates_count']}",
            f"- **Lengkap Metadata Hukum (Jenis + Nomor + Tahun/Tanggal):** {r.get('complete_legal_count', r.get('complete_4_count', 0))}/{r['candidates_count']} ({r.get('pct_legal', r.get('pct_4_attr', 0.0))}%)",
            f"- **Ukuran Terdeteksi:** {r['with_size_count']}/{r['candidates_count']} ({r['pct_size']}%)",
            f"- **Jumlah Match Warnings:** {r['match_warnings_count']}",
            f"- **Ground Truth:** {r['ground_truth_label']} (Selisih: {r['selisih_str']})",
            f"- **Berkas CSV Ekspor:** [`{r['csv_path']}`]({r['csv_path']})",
            f"- **Rincian doc_kind:** `{r['stats'].get('by_doc_kind', {})}`",
        ])
        if r.get("records_total"):
            md_lines.append(f"- **Total Rekod Situs (recordsTotal):** {r['records_total']}")
        if r.get("subfolders_count"):
            md_lines.append(f"- **Rincian Berkas per Subfolder:** `{r['subfolders_count']}`")
        md_lines.extend([
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
