"""add category_id to sessions jobs and normalize bidang

Revision ID: c34f2a7b8e19
Revises: f11a84880e5e
Create Date: 2026-10-03 10:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c34f2a7b8e19'
down_revision: Union[str, None] = 'f11a84880e5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tambah category_id ke scan_sessions
    op.add_column(
        'scan_sessions',
        sa.Column(
            'category_id',
            sa.Integer(),
            sa.ForeignKey('categories.id', ondelete='SET NULL'),
            nullable=True,
            comment='FK ke kategori target KB saat penarikan dokumen',
        ),
    )
    op.create_index(op.f('ix_scan_sessions_category_id'), 'scan_sessions', ['category_id'], unique=False)

    # 2. Tambah category_id ke job_ingest
    op.add_column(
        'job_ingest',
        sa.Column(
            'category_id',
            sa.Integer(),
            sa.ForeignKey('categories.id', ondelete='SET NULL'),
            nullable=True,
            comment='FK ke kategori target KB',
        ),
    )
    op.create_index(op.f('ix_job_ingest_category_id'), 'job_ingest', ['category_id'], unique=False)

    # 3. Perbesar kolom bidang di scan_candidates ke String(150) agar seragam dengan documents
    op.alter_column('scan_candidates', 'bidang', type_=sa.String(150), existing_type=sa.String(100))

    # 4. Migrasi data normalisasi spasi pada bidang di documents dan scan_candidates
    # Hapus spasi sebelum koma, rapikan spasi ganda, trim
    op.execute("""
        UPDATE documents
        SET bidang = TRIM(
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(bidang, '\\s+,', ',', 'g'),
                    ',\\s*', ', ', 'g'
                ),
                '\\s+', ' ', 'g'
            )
        )
        WHERE bidang IS NOT NULL AND bidang != '';
    """)

    op.execute("""
        UPDATE scan_candidates
        SET bidang = TRIM(
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(bidang, '\\s+,', ',', 'g'),
                    ',\\s*', ', ', 'g'
                ),
                '\\s+', ' ', 'g'
            )
        )
        WHERE bidang IS NOT NULL AND bidang != '';
    """)


def downgrade() -> None:
    op.drop_index(op.f('ix_job_ingest_category_id'), table_name='job_ingest')
    op.drop_column('job_ingest', 'category_id')
    op.drop_index(op.f('ix_scan_sessions_category_id'), table_name='scan_sessions')
    op.drop_column('scan_sessions', 'category_id')
