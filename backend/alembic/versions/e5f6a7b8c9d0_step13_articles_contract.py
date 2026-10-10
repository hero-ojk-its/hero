"""step13 articles contract

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-10 12:00:00.000000

"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    # 1. Tambah kolom page ke tabel articles
    op.add_column(
        'articles',
        sa.Column(
            'page',
            sa.Integer(),
            nullable=True,
            comment='Halaman PDF tempat pasal ini dimulai (1-indexed)',
        ),
    )

    # 2. Bersihkan duplikat yang mungkin sudah ada pada (document_id, order_index)
    bind = op.get_bind()

    # Jika ada child yang parent_id-nya mengarah ke baris duplikat yang akan dihapus,
    # arahkan parent_id ke baris dengan id terkecil (keeper)
    bind.execute(sa.text("""
        WITH duplicates AS (
            SELECT id,
                   FIRST_VALUE(id) OVER (
                       PARTITION BY document_id, order_index
                       ORDER BY id ASC
                   ) as keeper_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY document_id, order_index
                       ORDER BY id ASC
                   ) as rn
            FROM articles
            WHERE order_index IS NOT NULL
        )
        UPDATE articles
        SET parent_id = duplicates.keeper_id
        FROM duplicates
        WHERE articles.parent_id = duplicates.id AND duplicates.rn > 1;
    """))

    # Hapus baris duplikat, hanya pertahankan baris dengan id terkecil per (document_id, order_index)
    result = bind.execute(sa.text("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY document_id, order_index
                       ORDER BY id ASC
                   ) as rn
            FROM articles
            WHERE order_index IS NOT NULL
        )
        DELETE FROM articles
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        RETURNING id;
    """))
    deleted_rows = result.fetchall()
    deleted_count = len(deleted_rows)
    logger.info("Pembersihan duplikat articles: %d baris dihapus.", deleted_count)

    # 3. Tambah unique index parsial uq_articles_document_order
    op.create_index(
        'uq_articles_document_order',
        'articles',
        ['document_id', 'order_index'],
        unique=True,
        postgresql_where=sa.text('order_index IS NOT NULL'),
    )


def downgrade() -> None:
    # 1. Hapus unique index parsial
    op.drop_index(
        'uq_articles_document_order',
        table_name='articles',
    )

    # 2. Hapus kolom page
    op.drop_column('articles', 'page')
