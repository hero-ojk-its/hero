"""
scripts/show_scan2_duplicates.py
Menampilkan seluruh kandidat scan 2 yang berstatus pull_outcome 'duplikat'
beserta dokumen pembanding dan pesan deteksi duplikatnya.
"""
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.database import SessionLocal
from app.models.scan_candidate import ScanCandidate
from app.models.document import Document

db = SessionLocal()
try:
    dups = (
        db.query(ScanCandidate)
        .filter(ScanCandidate.scan_id == 2, ScanCandidate.pull_outcome == "duplikat")
        .order_by(ScanCandidate.id)
        .all()
    )
    print(f"Total kandidat duplikat pada Scan 2: {len(dups)}\n")
    for c in dups:
        matched_doc = db.query(Document).filter(Document.id == c.document_id).first()
        matched_title = matched_doc.title if matched_doc else "N/A"
        matched_fn = matched_doc.original_filename if matched_doc else "N/A"
        print(f"ID Kandidat     : {c.id}")
        print(f"Nama Berkas     : {c.filename}")
        print(f"Nomor Regulasi  : {c.regulation_number}")
        print(f"Pull Outcome    : {c.pull_outcome}")
        print(f"Pesan Deteksi   : {c.message}")
        print(f"Dokumen di KB   : ID {c.document_id} ({matched_fn}) - {matched_title[:80]}...")
        print("-" * 80)
finally:
    db.close()
