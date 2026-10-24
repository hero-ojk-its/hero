"""step25 analysis cache invalidation (usang_sejak, alasan_usang)

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-10-24 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'analysis_results',
        sa.Column(
            'usang_sejak',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Waktu ditandai usang; NULL = masih valid',
        ),
    )
    op.add_column(
        'analysis_results',
        sa.Column(
            'alasan_usang',
            sa.String(length=200),
            nullable=True,
            comment='Alasan cache ditandai usang, misal versi mesin',
        ),
    )
    op.create_index(
        op.f('ix_analysis_results_usang_sejak'),
        'analysis_results',
        ['usang_sejak'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_analysis_results_usang_sejak'), table_name='analysis_results')
    op.drop_column('analysis_results', 'alasan_usang')
    op.drop_column('analysis_results', 'usang_sejak')
