#!/usr/bin/env python3
"""
scripts/match_onedrive_ojk.py
Membandingkan berkas regulasi folder OneDrive downloads (2.612 berkas)
terhadap hasil perayapan portal Regulasi OJK (2.665 berkas).

Penggunaan:
    python scripts/match_onedrive_ojk.py
"""
import csv
import re
from pathlib import Path
from typing import Dict, Any, List

import sys
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.crawlers.url_utils import parse_onedrive_filename_metadata


def main():
    ojk_csv = REPO_ROOT / "docs" / "reports" / "scan-benchmark-ojk.csv"
    onedrive_csv = REPO_ROOT / "docs" / "reports" / "scan-benchmark-onedrive.csv"
    output_csv = REPO_ROOT / "docs" / "reports" / "match-onedrive-ojk.csv"

    if not ojk_csv.exists() or not onedrive_csv.exists():
        print(f"Error: scan-benchmark-ojk.csv atau scan-benchmark-onedrive.csv tidak ditemukan.")
        return

    # 1. Baca data Regulasi OJK
    with open(ojk_csv, mode="r", encoding="utf-8-sig") as f:
        ojk_rows = list(csv.DictReader(f))

    ojk_regs = set()
    for r in ojk_rows:
        t = r.get("regulation_type", "").strip().upper()
        n = r.get("regulation_number", "").strip()
        y = r.get("release_year") or (r.get("release_date", "")[:4] if r.get("release_date") else "")
        if t and n and y:
            num_m = re.search(r"\d+", n)
            num_clean = str(int(num_m.group(0))) if num_m else n
            ojk_regs.add((t, num_clean, str(y).strip()))

    print(f"Total kandidat OJK: {len(ojk_rows)}")
    print(f"Total regulasi unik OJK (jenis, nomor, tahun): {len(ojk_regs)}")

    # 2. Baca data OneDrive (hanya folder downloads regulasi)
    with open(onedrive_csv, mode="r", encoding="utf-8-sig") as f:
        onedrive_rows = list(csv.DictReader(f))

    downloads_rows = [
        r for r in onedrive_rows
        if r.get("doc_kind") != "non_regulasi" and "downloads" in (r.get("source_path") or "")
    ]
    print(f"Total berkas OneDrive folder downloads: {len(downloads_rows)}")

    results: List[Dict[str, Any]] = []
    matched_count = 0
    unmatched_count = 0

    unmatched_by_type = {}
    unmatched_ge_2013 = {}
    unmatched_lt_2013 = {}

    for r in downloads_rows:
        fn = r["filename"]
        meta = parse_onedrive_filename_metadata(fn)
        t = (meta.get("regulation_type") or "").strip().upper()
        n = (meta.get("regulation_number") or "").strip()
        y_val = meta.get("release_year")
        y = str(y_val).strip() if y_val else ""

        num_m = re.search(r"\d+", n) if n else None
        num_clean = str(int(num_m.group(0))) if num_m else n

        is_match = bool(t and num_clean and y and (t, num_clean, y) in ojk_regs)

        if is_match:
            status = "COCOK"
            matched_count += 1
        else:
            status = "TIDAK_COCOK"
            unmatched_count += 1

            t_label = t or "TANPA_JENIS"
            unmatched_by_type[t_label] = unmatched_by_type.get(t_label, 0) + 1
            try:
                y_int = int(y)
                if y_int >= 2013:
                    unmatched_ge_2013[t_label] = unmatched_ge_2013.get(t_label, 0) + 1
                else:
                    unmatched_lt_2013[t_label] = unmatched_lt_2013.get(t_label, 0) + 1
            except ValueError:
                unmatched_lt_2013[t_label] = unmatched_lt_2013.get(t_label, 0) + 1

        results.append({
            "filename": fn,
            "parsed_type": t,
            "parsed_number": num_clean,
            "parsed_year": y,
            "match_status": status,
            "source_path": r.get("source_path", ""),
        })

    # Tulis CSV hasil pencocokan
    fieldnames = ["filename", "parsed_type", "parsed_number", "parsed_year", "match_status", "source_path"]
    with open(output_csv, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n================ HASIL PENCOCOKAN ================")
    print(f"Berkas Cocok Tepat (Exact Match) : {matched_count} ({matched_count/len(downloads_rows)*100:.1f}%)")
    print(f"Berkas Tidak Cocok               : {unmatched_count} ({unmatched_count/len(downloads_rows)*100:.1f}%)")
    print(f"CSV disimpan ke                  : {output_csv}")

    print(f"\n================ RINCIAN TIDAK COCOK PER JENIS & TAHUN ================")
    total_ge = sum(unmatched_ge_2013.values())
    total_lt = sum(unmatched_lt_2013.values())
    print(f"Total Tidak Cocok Tahun >= 2013 (Era OJK)     : {total_ge} berkas")
    print(f"Total Tidak Cocok Tahun < 2013 (Pra-2013/Hist): {total_lt} berkas")
    print("-" * 75)
    for t_name, cnt in sorted(unmatched_by_type.items(), key=lambda x: -x[1]):
        ge = unmatched_ge_2013.get(t_name, 0)
        lt = unmatched_lt_2013.get(t_name, 0)
        print(f"  {t_name:15}: {cnt:4} total (Tahun >= 2013: {ge:4}, Tahun < 2013: {lt:4})")


if __name__ == "__main__":
    main()
