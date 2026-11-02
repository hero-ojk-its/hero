"""step35 persetujuan_draft_publik

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-11-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8a9b0c1d2e3'
down_revision: Union[str, None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'documents',
        sa.Column(
            'publik_disetujui_oleh',
            sa.String(length=255),
            nullable=True,
            comment='Username/nama pihak yang menyetujui publikasi draft kajian',
        ),
    )
    op.add_column(
        'documents',
        sa.Column(
            'publik_disetujui_alasan',
            sa.Text(),
            nullable=True,
            comment='Alasan persetujuan publikasi draft kajian',
        ),
    )
    op.add_column(
        'documents',
        sa.Column(
            'publik_disetujui_pada',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Waktu persetujuan publikasi draft kajian',
        ),
    )


def downgrade() -> None:
    op.drop_column('documents', 'publik_disetujui_pada')
    op.drop_column('documents', 'publik_disetujui_alasan')
    op.drop_column('documents', 'publik_disetujui_oleh')

