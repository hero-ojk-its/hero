"""step14 deactivate document

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-10 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tambah kolom is_active ke documents dengan server_default=true dan index
    op.add_column(
        'documents',
        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('true'),
            comment='Status aktif dokumen secara administratif (Knowledge Base)',
        ),
    )
    op.create_index(op.f('ix_documents_is_active'), 'documents', ['is_active'], unique=False)

    # 2. Tambah kolom deactivated_at
    op.add_column(
        'documents',
        sa.Column(
            'deactivated_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Waktu dokumen dinonaktifkan',
        ),
    )

    # 3. Tambah kolom deactivated_reason
    op.add_column(
        'documents',
        sa.Column(
            'deactivated_reason',
            sa.Text(),
            nullable=True,
            comment='Alasan penonaktifan dokumen',
        ),
    )

    # 4. Tambah kolom deactivated_by sebagai FK ke users.id (ondelete=SET NULL)
    op.add_column(
        'documents',
        sa.Column(
            'deactivated_by',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
            comment='ID user yang menonaktifkan dokumen',
        ),
    )
    op.create_index(op.f('ix_documents_deactivated_by'), 'documents', ['deactivated_by'], unique=False)


def downgrade() -> None:
    # Hapus index dan kolom dalam urutan terbalik
    op.drop_index(op.f('ix_documents_deactivated_by'), table_name='documents')
    op.drop_column('documents', 'deactivated_by')
    op.drop_column('documents', 'deactivated_reason')
    op.drop_column('documents', 'deactivated_at')
    op.drop_index(op.f('ix_documents_is_active'), table_name='documents')
    op.drop_column('documents', 'is_active')
