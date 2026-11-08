"""step39 tanggapan_temuan

Revision ID: a1b2c3d4e5f6
Revises: f8a9b0c1d2e3
Create Date: 2026-11-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tanggapan_temuan',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False, comment='ID draft kajian yang diharmonisasi'),
        sa.Column('kunci_temuan', sa.String(length=64), nullable=False, comment='Hash penanda stabil temuan (SHA-256)'),
        sa.Column('run_id', sa.Integer(), nullable=True, comment='ID eksekusi harmonisasi tempat temuan dinilai'),
        sa.Column('temuan_id_ml', sa.String(length=100), nullable=True, comment='ID temuan dari respons layanan ML'),
        sa.Column('penilaian', sa.String(length=20), nullable=False, comment='Penilaian analis: valid atau tidak_relevan'),
        sa.Column('catatan', sa.Text(), nullable=True, comment='Catatan analis terhadap temuan'),
        sa.Column('ringkasan_temuan', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Salinan ringkas temuan saat dinilai (tanpa teks pasal panjang)'),
        sa.Column('dinilai_oleh', sa.Integer(), nullable=True, comment='ID user yang menilai'),
        sa.Column('dinilai_oleh_nama', sa.String(length=255), nullable=True, comment='Nama/username penilai'),
        sa.Column('dibuat', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Waktu penilaian dibuat'),
        sa.Column('diperbarui', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Waktu penilaian terakhir diperbarui'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['dinilai_oleh'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_id', 'kunci_temuan', name='uq_tanggapan_temuan_doc_kunci'),
    )
    op.create_index('ix_tanggapan_temuan_id', 'tanggapan_temuan', ['id'], unique=False)
    op.create_index('ix_tanggapan_temuan_document_id', 'tanggapan_temuan', ['document_id'], unique=False)
    op.create_index('ix_tanggapan_temuan_kunci_temuan', 'tanggapan_temuan', ['kunci_temuan'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_tanggapan_temuan_kunci_temuan', table_name='tanggapan_temuan')
    op.drop_index('ix_tanggapan_temuan_document_id', table_name='tanggapan_temuan')
    op.drop_index('ix_tanggapan_temuan_id', table_name='tanggapan_temuan')
    op.drop_table('tanggapan_temuan')

