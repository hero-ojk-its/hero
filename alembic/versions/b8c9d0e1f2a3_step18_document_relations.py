"""step18 document relations and status source

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-16 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Buat tabel document_relations
    op.create_table(
        'document_relations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_key', sa.String(length=120), nullable=False, comment='Kunci peraturan yang mengubah/mencabut (src)'),
        sa.Column('target_key', sa.String(length=120), nullable=False, comment='Kunci peraturan yang diubah/dicabut (dst)'),
        sa.Column(
            'relation',
            sa.Enum('mengubah', 'mencabut', name='jenisrelasi', native_enum=False),
            nullable=False,
            comment='Jenis relasi hukum: mengubah | mencabut',
        ),
        sa.Column('partial', sa.Boolean(), server_default=sa.text('false'), nullable=False, comment='Pencabutan/perubahan sebagian'),
        sa.Column('articles_text', sa.Text(), nullable=True, comment='Pasal-pasal terkait'),
        sa.Column('origin', sa.String(length=50), nullable=True, comment='Asal data relasi, mis. jdih-riwayat'),
        sa.Column('evidence', sa.Text(), nullable=True, comment='Bukti tekstual relasi (maks 2000 karakter)'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_key', 'target_key', 'relation', name='uq_document_relations_src_tgt_rel'),
    )
    op.create_index(op.f('ix_document_relations_id'), 'document_relations', ['id'], unique=False)
    op.create_index(op.f('ix_document_relations_source_key'), 'document_relations', ['source_key'], unique=False)
    op.create_index(op.f('ix_document_relations_target_key'), 'document_relations', ['target_key'], unique=False)

    # 2. Tambah kolom status_source ke documents
    op.add_column(
        'documents',
        sa.Column(
            'status_source',
            sa.String(length=20),
            nullable=True,
            comment='Sumber penentuan status_keberlakuan: manual | relasi | lapisan_data',
        ),
    )


def downgrade() -> None:
    # 1. Hapus kolom status_source dari documents
    op.drop_column('documents', 'status_source')

    # 2. Hapus index dan tabel document_relations
    op.drop_index(op.f('ix_document_relations_target_key'), table_name='document_relations')
    op.drop_index(op.f('ix_document_relations_source_key'), table_name='document_relations')
    op.drop_index(op.f('ix_document_relations_id'), table_name='document_relations')
    op.drop_table('document_relations')
