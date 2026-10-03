"""step12b add regulation_year and backfill

Revision ID: d4e5f6a7b8c9
Revises: c34f2a7b8e19
Create Date: 2026-10-03 12:20:00.000000

"""
import re
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c34f2a7b8e19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _extract_year_helper(reg_num: str = None, title: str = None, fn: str = None, rel_date = None) -> Union[int, None]:
    # 1. Nomor resmi
    if reg_num and str(reg_num).strip():
        m = re.findall(r"\b(19\d\d|20\d\d)\b", str(reg_num))
        if m:
            return int(m[-1])
    # 2. Judul
    if title and str(title).strip():
        ym = re.search(r"\bTahun\s+(19\d\d|20\d\d)\b", str(title), re.IGNORECASE)
        if ym:
            return int(ym.group(1))
        m = re.findall(r"\b(19\d\d|20\d\d)\b", str(title))
        if m:
            return int(m[-1])
    # 3. Nama berkas
    if fn and str(fn).strip():
        stem = Path(str(fn).strip()).stem
        m = re.findall(r"\b(19\d\d|20\d\d)\b", stem)
        if not m:
            m = re.findall(r"(?:^|[-_ ])(19\d\d|20\d\d)(?:[-_ ]|$)", stem)
        if m:
            return int(m[-1])
    # 4. release_date
    if rel_date:
        if hasattr(rel_date, "year"):
            return rel_date.year
        s = str(rel_date)[:4]
        if s.isdigit():
            return int(s)
    return None


def upgrade() -> None:
    # 1. Tambah kolom regulation_year ke documents
    op.add_column(
        'documents',
        sa.Column('regulation_year', sa.Integer(), nullable=True, comment='Tahun regulasi resmi'),
    )
    op.create_index(op.f('ix_documents_regulation_year'), 'documents', ['regulation_year'], unique=False)

    # 2. Tambah kolom regulation_year ke scan_candidates
    op.add_column(
        'scan_candidates',
        sa.Column('regulation_year', sa.Integer(), nullable=True, comment='Tahun regulasi resmi yang diekstrak'),
    )
    op.create_index(op.f('ix_scan_candidates_regulation_year'), 'scan_candidates', ['regulation_year'], unique=False)

    # 3. Data backfill & pembersihan release_date palsu
    bind = op.get_bind()
    session = Session(bind=bind)

    # 3a. Koreksi dokumen ID 3 (23/SEOJK.06/2025): release_date palsu 2025-01-01 dijadikan NULL
    bind.execute(
        sa.text("UPDATE documents SET release_date = NULL WHERE id = 3 AND release_date = '2025-01-01'")
    )
    bind.execute(
        sa.text("UPDATE scan_candidates SET release_date = NULL WHERE scan_id = 1 AND regulation_number LIKE '%23/SEOJK.06/2025%' AND release_date = '2025-01-01'")
    )

    # 3b. Backfill documents.regulation_year
    doc_rows = bind.execute(
        sa.text("SELECT id, regulation_number, title, original_filename, standardized_filename, release_date FROM documents")
    ).fetchall()

    for r in doc_rows:
        doc_id = r[0]
        reg_num = r[1]
        title = r[2]
        fn = r[3] or r[4]
        rel_d = r[5]
        year_val = _extract_year_helper(reg_num, title, fn, rel_d)
        if year_val is not None:
            bind.execute(
                sa.text("UPDATE documents SET regulation_year = :yr WHERE id = :did"),
                {"yr": year_val, "did": doc_id},
            )

    # 3c. Backfill scan_candidates.regulation_year
    cand_rows = bind.execute(
        sa.text("SELECT id, regulation_number, document_title, filename, release_date FROM scan_candidates")
    ).fetchall()

    for r in cand_rows:
        cand_id = r[0]
        reg_num = r[1]
        title = r[2]
        fn = r[3]
        rel_d = r[4]
        year_val = _extract_year_helper(reg_num, title, fn, rel_d)
        if year_val is not None:
            bind.execute(
                sa.text("UPDATE scan_candidates SET regulation_year = :yr WHERE id = :cid"),
                {"yr": year_val, "cid": cand_id},
            )

    session.commit()


def downgrade() -> None:
    op.drop_index(op.f('ix_scan_candidates_regulation_year'), table_name='scan_candidates')
    op.drop_column('scan_candidates', 'regulation_year')
    op.drop_index(op.f('ix_documents_regulation_year'), table_name='documents')
    op.drop_column('documents', 'regulation_year')
