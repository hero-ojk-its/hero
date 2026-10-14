"""step17 duplicate identity

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-14 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tambah kolom identity_key ke documents dengan index
    op.add_column(
        'documents',
        sa.Column(
            'identity_key',
            sa.String(length=120),
            nullable=True,
            comment='Kunci kanonik identitas regulasi (JENIS|NOMOR|TAHUN)',
        ),
    )
    op.create_index(op.f('ix_documents_identity_key'), 'documents', ['identity_key'], unique=False)

    # 2. Tambah kolom page_count
    op.add_column(
        'documents',
        sa.Column(
            'page_count',
            sa.Integer(),
            nullable=True,
            comment='Jumlah halaman PDF',
        ),
    )

    # 3. Tambah kolom duplicate_of_id sebagai FK ke documents.id (ondelete=SET NULL) dengan index
    op.add_column(
        'documents',
        sa.Column(
            'duplicate_of_id',
            sa.Integer(),
            sa.ForeignKey('documents.id', ondelete='SET NULL'),
            nullable=True,
            comment='ID dokumen pemenang yang dipertahankan jika dokumen ini duplikat',
        ),
    )
    op.create_index(op.f('ix_documents_duplicate_of_id'), 'documents', ['duplicate_of_id'], unique=False)


def downgrade() -> None:
    # Hapus index dan kolom dalam urutan terbalik
    op.drop_index(op.f('ix_documents_duplicate_of_id'), table_name='documents')
    op.drop_column('documents', 'duplicate_of_id')
    op.drop_column('documents', 'page_count')
    op.drop_index(op.f('ix_documents_identity_key'), table_name='documents')
    op.drop_column('documents', 'identity_key')
