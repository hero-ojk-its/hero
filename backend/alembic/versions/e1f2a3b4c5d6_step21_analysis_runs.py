"""step21 analysis runs append-only execution history

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-10-18 02:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Buat tabel analysis_runs
    op.create_table(
        'analysis_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False, comment='Dokumen yang dianalisa'),
        sa.Column(
            'kind',
            sa.Enum('analisa', 'harmonisasi', name='jenisanalisa', native_enum=False),
            nullable=False,
            comment='Jenis analisa: analisa | harmonisasi',
        ),
        sa.Column(
            'mode_diminta',
            sa.Enum('deterministik', 'ai', name='modeanalisa', native_enum=False),
            nullable=False,
            comment='Mode komputasi yang diminta klien: deterministik | ai',
        ),
        sa.Column(
            'mode_dipakai',
            sa.Enum('deterministik', 'ai', name='modeanalisa', native_enum=False),
            nullable=True,
            comment='Mode komputasi yang benar-benar dipakai; NULL bila gagal',
        ),
        sa.Column('sumber', sa.String(length=20), nullable=False, comment='Asal hasil: ml | cache | cache_basi | gagal'),
        sa.Column('segar', sa.Boolean(), nullable=False, server_default=sa.text('false'), comment='Nilai parameter segar'),
        sa.Column('params', JSONB().with_variant(sa.JSON(), 'sqlite'), nullable=False, comment='Input yang memengaruhi hasil'),
        sa.Column('params_hash', sa.String(length=64), nullable=False, comment='SHA-256 dari parameter penentu hasil'),
        sa.Column('source_fingerprint', sa.String(length=200), nullable=False, comment='Fingerprint dokumen saat eksekusi'),
        sa.Column('ml_version', sa.String(length=100), nullable=True, comment='Versi layanan ML (versi aturan) bila ada'),
        sa.Column('result_hash', sa.String(length=64), nullable=True, comment='SHA-256 dari jawaban mentah ML'),
        sa.Column('result', JSONB().with_variant(sa.JSON(), 'sqlite'), nullable=True, comment='Output mentah ML (hanya bila sumber=ml)'),
        sa.Column('ringkasan_output', JSONB().with_variant(sa.JSON(), 'sqlite'), nullable=True, comment='Ringkasan kecil untuk daftar riwayat'),
        sa.Column('http_status', sa.Integer(), nullable=False, comment='Status HTTP yang dikembalikan ke klien'),
        sa.Column('error_code', sa.String(length=100), nullable=True, comment='Kode galat bila eksekusi gagal'),
        sa.Column('duration_ms', sa.Integer(), nullable=True, comment='Durasi penanganan permintaan di gerbang (ms)'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True, comment='User yang memicu analisa'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_analysis_runs_id'), 'analysis_runs', ['id'], unique=False)
    op.create_index(op.f('ix_analysis_runs_document_id'), 'analysis_runs', ['document_id'], unique=False)
    op.create_index(op.f('ix_analysis_runs_created_at'), 'analysis_runs', ['created_at'], unique=False)
    op.create_index(op.f('ix_analysis_runs_result_hash'), 'analysis_runs', ['result_hash'], unique=False)
    op.create_index(
        'ix_analysis_runs_doc_kind_created',
        'analysis_runs',
        ['document_id', 'kind', sa.text('created_at DESC')],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_analysis_runs_doc_kind_created', table_name='analysis_runs')
    op.drop_index(op.f('ix_analysis_runs_result_hash'), table_name='analysis_runs')
    op.drop_index(op.f('ix_analysis_runs_created_at'), table_name='analysis_runs')
    op.drop_index(op.f('ix_analysis_runs_document_id'), table_name='analysis_runs')
    op.drop_index(op.f('ix_analysis_runs_id'), table_name='analysis_runs')
    op.drop_table('analysis_runs')
