"""step3 category unique constraint

Revision ID: 3b2c1d4e5f6a
Revises: 2a1b3c4d5e6f
Create Date: 2026-09-26 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b2c1d4e5f6a'
down_revision: Union[str, None] = '2a1b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Gabungkan kategori duplikat jika ada sebelum menambahkan constraint
    op.execute("""
        DO $$
        DECLARE
            r RECORD;
            keeper_id INT;
        BEGIN
            FOR r IN (
                SELECT parent_id, name, MIN(id) AS min_id, ARRAY_AGG(id ORDER BY id) AS all_ids
                FROM categories
                GROUP BY parent_id, name
                HAVING COUNT(*) > 1
            ) LOOP
                keeper_id := r.min_id;
                
                -- Arahkan documents ke keeper_id
                UPDATE documents
                SET category_id = keeper_id
                WHERE category_id = ANY(r.all_ids) AND category_id <> keeper_id;

                -- Arahkan subkategori ke keeper_id
                UPDATE categories
                SET parent_id = keeper_id
                WHERE parent_id = ANY(r.all_ids) AND parent_id <> keeper_id;

                -- Hapus kategori duplikat selain keeper_id
                DELETE FROM categories
                WHERE id = ANY(r.all_ids) AND id <> keeper_id;
            END LOOP;
        END $$;
    """)

    # 2. Buat unique constraint dengan NULLS NOT DISTINCT (fitur PostgreSQL 15)
    op.execute("""
        ALTER TABLE categories
        ADD CONSTRAINT uq_categories_parent_name
        UNIQUE NULLS NOT DISTINCT (parent_id, name);
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE categories
        DROP CONSTRAINT IF EXISTS uq_categories_parent_name;
    """)
