"""step33 kunci_otomatis kategori

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-11-01 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6e7f8a9b0c1'
down_revision: Union[str, None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tambah kolom kunci_otomatis pada tabel categories
    op.add_column(
        'categories',
        sa.Column(
            'kunci_otomatis',
            sa.String(length=255),
            nullable=True,
            comment='Kunci segmen template otomatis (mis. POJK atau 2026)',
        ),
    )

    # 2. Data step: isi kunci_otomatis dengan name untuk kategori yang auto_created
    op.execute("UPDATE categories SET kunci_otomatis = name WHERE auto_created = true")

    # 3. Partial unique index untuk kategori akar (parent_id IS NULL)
    op.create_index(
        'ix_categories_kunci_otomatis_root',
        'categories',
        ['kunci_otomatis'],
        unique=True,
        postgresql_where=sa.text("parent_id IS NULL AND kunci_otomatis IS NOT NULL"),
        sqlite_where=sa.text("parent_id IS NULL AND kunci_otomatis IS NOT NULL"),
    )

    # 4. Partial unique index untuk subkategori (parent_id IS NOT NULL)
    op.create_index(
        'ix_categories_kunci_otomatis_child',
        'categories',
        ['parent_id', 'kunci_otomatis'],
        unique=True,
        postgresql_where=sa.text("parent_id IS NOT NULL AND kunci_otomatis IS NOT NULL"),
        sqlite_where=sa.text("parent_id IS NOT NULL AND kunci_otomatis IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index('ix_categories_kunci_otomatis_child', table_name='categories')
    op.drop_index('ix_categories_kunci_otomatis_root', table_name='categories')
    op.drop_column('categories', 'kunci_otomatis')

