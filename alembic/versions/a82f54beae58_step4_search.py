"""step4_search

Revision ID: a82f54beae58
Revises: 3b2c1d4e5f6a
Create Date: 2026-09-26 19:44:03.656580

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR


# revision identifiers, used by Alembic.
revision: str = 'a82f54beae58'
down_revision: Union[str, None] = '3b2c1d4e5f6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Aktifkan pg_trgm untuk pencarian ILIKE / regex / trigram
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # 2. Tambahkan kolom generated search_vector (TSVector)
    op.add_column(
        'documents',
        sa.Column(
            'search_vector',
            TSVECTOR,
            sa.Computed(
                "setweight(to_tsvector('simple'::regconfig, coalesce(regulation_number, '')), 'A') || "
                "setweight(to_tsvector('simple'::regconfig, coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('simple'::regconfig, coalesce(regulation_type, '')), 'B') || "
                "setweight(to_tsvector('simple'::regconfig, left(coalesce(full_text, ''), 300000)), 'C')",
                persisted=True,
            ),
            nullable=True,
            comment='TSVector computed untuk full-text search',
        )
    )

    # 3. Buat indeks GIN dan B-tree
    op.create_index(
        'ix_documents_search_vector',
        'documents',
        ['search_vector'],
        unique=False,
        postgresql_using='gin',
    )
    op.create_index(
        'ix_documents_reg_num_trgm',
        'documents',
        ['regulation_number'],
        unique=False,
        postgresql_using='gin',
        postgresql_ops={'regulation_number': 'gin_trgm_ops'},
    )
    op.create_index(
        'ix_documents_title_trgm',
        'documents',
        ['title'],
        unique=False,
        postgresql_using='gin',
        postgresql_ops={'title': 'gin_trgm_ops'},
    )
    op.create_index(
        'ix_documents_release_date',
        'documents',
        ['release_date'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_documents_release_date', table_name='documents')
    op.drop_index(
        'ix_documents_title_trgm',
        table_name='documents',
        postgresql_using='gin',
        postgresql_ops={'title': 'gin_trgm_ops'},
    )
    op.drop_index(
        'ix_documents_reg_num_trgm',
        table_name='documents',
        postgresql_using='gin',
        postgresql_ops={'regulation_number': 'gin_trgm_ops'},
    )
    op.drop_index(
        'ix_documents_search_vector',
        table_name='documents',
        postgresql_using='gin',
    )
    op.drop_column('documents', 'search_vector')

