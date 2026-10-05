import csv
from collections import Counter
from pathlib import Path

for name, rel_path in [
    ("OJK (Portal)", "docs/reports/scan-benchmark-ojk.csv"),
    ("JDIH OJK", "docs/reports/scan-benchmark-jdih.csv"),
]:
    counter = Counter()
    with open(rel_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        # Cari index kolom bidang
        bidang_idx = header.index("bidang") if "bidang" in header else 7
        for row in reader:
            if len(row) > bidang_idx:
                val = row[bidang_idx].strip()
                counter[val] += 1
    print(f"=== Frekuensi Bidang {name} ({rel_path}) ===")
    for b, c in counter.most_common():
        print(f"  {b or '(Kosong)'}: {c}")
    print()
