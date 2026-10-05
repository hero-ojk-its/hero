"""step5_detail_extraction

Revision ID: 5467cc220a1b
Revises: a82f54beae58
Create Date: 2026-09-26 19:51:56.021549

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5467cc220a1b'
down_revision: Union[str, None] = 'a82f54beae58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. audit_logs: + detail (JSONB)
    op.add_column(
        'audit_logs',
        sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Keterangan / diff perubahan JSONB')
    )

    # 2. documents: extraction confidence, metadata correction tracking, extraction claim/attempts/extracted_at
    op.add_column(
        'documents',
        sa.Column('extraction_confidence', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Keyakinan ekstraksi per field')
    )
    op.add_column(
        'documents',
        sa.Column('metadata_corrected_at', sa.DateTime(timezone=True), nullable=True, comment='Waktu koreksi metadata manual')
    )
    op.add_column(
        'documents',
        sa.Column('metadata_corrected_by', sa.Integer(), nullable=True, comment='ID pengguna yang melakukan koreksi metadata manual')
    )
    op.create_foreign_key(
        'fk_documents_metadata_corrected_by_users',
        'documents',
        'users',
        ['metadata_corrected_by'],
        ['id'],
        ondelete='SET NULL'
    )
    op.add_column(
        'documents',
        sa.Column('extraction_claimed_at', sa.DateTime(timezone=True), nullable=True, comment='Waktu pengambilan klaim ekstraksi ML')
    )
    op.add_column(
        'documents',
        sa.Column('extraction_attempts', sa.Integer(), server_default='0', nullable=False, comment='Jumlah upaya pemrosesan ekstraksi ML')
    )
    op.add_column(
        'documents',
        sa.Column('extracted_at', sa.DateTime(timezone=True), nullable=True, comment='Waktu hasil ekstraksi ML diterima')
    )

    # 3. ingest_failures: + document_id (FK documents, SET NULL) & index
    op.add_column(
        'ingest_failures',
        sa.Column('document_id', sa.Integer(), nullable=True, comment='FK ke dokumen untuk kegagalan pasca-ingest (ekstraksi/OCR)')
    )
    op.create_foreign_key(
        'fk_ingest_failures_document_id_documents',
        'ingest_failures',
        'documents',
        ['document_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index(
        'ix_ingest_failures_document_id',
        'ingest_failures',
        ['document_id'],
        unique=False
    )


def downgrade() -> None:
    # 3. ingest_failures: drop index, fk, column
    op.drop_index('ix_ingest_failures_document_id', table_name='ingest_failures')
    op.drop_constraint('fk_ingest_failures_document_id_documents', 'ingest_failures', type_='foreignkey')
    op.drop_column('ingest_failures', 'document_id')

    # 2. documents: drop fk, columns
    op.drop_constraint('fk_documents_metadata_corrected_by_users', 'documents', type_='foreignkey')
    op.drop_column('documents', 'extracted_at')
    op.drop_column('documents', 'extraction_attempts')
    op.drop_column('documents', 'extraction_claimed_at')
    op.drop_column('documents', 'metadata_corrected_by')
    op.drop_column('documents', 'metadata_corrected_at')
    op.drop_column('documents', 'extraction_confidence')

    # 1. audit_logs: drop detail column
    op.drop_column('audit_logs', 'detail')

