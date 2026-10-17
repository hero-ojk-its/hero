"""step19 effective date and attachments

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tambah kolom effective_date ke documents
    op.add_column(
        'documents',
        sa.Column('effective_date', sa.Date(), nullable=True, comment='Tanggal mulai berlaku regulasi'),
    )

    # 2. Tambah kolom is_attachment ke documents
    op.add_column(
        'documents',
        sa.Column(
            'is_attachment',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
            comment='Dokumen ini lampiran',
        ),
    )
    op.create_index(op.f('ix_documents_is_attachment'), 'documents', ['is_attachment'], unique=False)

    # 3. Tambah kolom parent_document_id ke documents
    op.add_column(
        'documents',
        sa.Column(
            'parent_document_id',
            sa.Integer(),
            sa.ForeignKey('documents.id', ondelete='SET NULL'),
            nullable=True,
            comment='Induk lampiran',
        ),
    )
    op.create_index(op.f('ix_documents_parent_document_id'), 'documents', ['parent_document_id'], unique=False)

    # 4. Tambah kolom parent_identity_key ke documents
    op.add_column(
        'documents',
        sa.Column(
            'parent_identity_key',
            sa.String(length=120),
            nullable=True,
            comment='Kunci induk bila dokumennya belum ada di KB',
        ),
    )
    op.create_index(op.f('ix_documents_parent_identity_key'), 'documents', ['parent_identity_key'], unique=False)

    # 5. Tambah kolom attachment_label ke documents
    op.add_column(
        'documents',
        sa.Column(
            'attachment_label',
            sa.String(length=100),
            nullable=True,
            comment='Label lampiran, misal: Lampiran I',
        ),
    )


def downgrade() -> None:
    op.drop_column('documents', 'attachment_label')

    op.drop_index(op.f('ix_documents_parent_identity_key'), table_name='documents')
    op.drop_column('documents', 'parent_identity_key')

    op.drop_index(op.f('ix_documents_parent_document_id'), table_name='documents')
    op.drop_column('documents', 'parent_document_id')

    op.drop_index(op.f('ix_documents_is_attachment'), table_name='documents')
    op.drop_column('documents', 'is_attachment')

    op.drop_column('documents', 'effective_date')
