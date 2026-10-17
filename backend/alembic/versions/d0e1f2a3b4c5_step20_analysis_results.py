"""step20 analysis results table and cache

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-17 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Buat tabel analysis_results
    op.create_table(
        'analysis_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False, comment='Dokumen yang dianalisa'),
        sa.Column(
            'kind',
            sa.Enum('analisa', 'harmonisasi', name='jenisanalisa', native_enum=False),
            nullable=False,
            comment='Jenis analisa: analisa | harmonisasi',
        ),
        sa.Column(
            'mode',
            sa.Enum('deterministik', 'ai', name='modeanalisa', native_enum=False),
            nullable=False,
            comment='Mode komputasi yang dipakai: deterministik | ai',
        ),
        sa.Column('params_hash', sa.String(length=64), nullable=False, comment='SHA-256 dari parameter penentu hasil'),
        sa.Column('source_fingerprint', sa.String(length=200), nullable=False, comment='Fingerprint dokumen saat hasil dibuat'),
        sa.Column('result', JSONB().with_variant(sa.JSON(), 'sqlite'), nullable=False, comment='Jawaban mentah layanan ML, belum disaring'),
        sa.Column('ml_version', sa.String(length=100), nullable=True, comment='Versi layanan ML bila ada'),
        sa.Column('duration_ms', sa.Integer(), nullable=True, comment='Durasi panggilan ML (ms)'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True, comment='User yang memicu analisa'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_id', 'kind', 'mode', 'params_hash', name='uq_analysis_results_doc_kind_mode_params'),
    )
    op.create_index(op.f('ix_analysis_results_id'), 'analysis_results', ['id'], unique=False)
    op.create_index(op.f('ix_analysis_results_document_id'), 'analysis_results', ['document_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_analysis_results_document_id'), table_name='analysis_results')
    op.drop_index(op.f('ix_analysis_results_id'), table_name='analysis_results')
    op.drop_table('analysis_results')
