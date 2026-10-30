"""step27 pdf_terproteksi column

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-10-30 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'documents',
        sa.Column(
            'pdf_terproteksi',
            sa.Boolean(),
            nullable=True,
            comment='PDF memiliki proteksi kata sandi pemilik / diproteksi',
        ),
    )
    op.create_index(
        op.f('ix_documents_pdf_terproteksi'),
        'documents',
        ['pdf_terproteksi'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_documents_pdf_terproteksi'), table_name='documents')
    op.drop_column('documents', 'pdf_terproteksi')

