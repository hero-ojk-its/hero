"""step28 kategori_manual column

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-10-30 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'documents',
        sa.Column(
            'kategori_manual',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
            comment='Apakah kategori dokumen ditentukan secara manual oleh pengguna',
        ),
    )


def downgrade() -> None:
    op.drop_column('documents', 'kategori_manual')

