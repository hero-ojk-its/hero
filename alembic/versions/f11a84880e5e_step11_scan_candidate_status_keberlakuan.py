"""step11_scan_candidate_status_keberlakuan

Revision ID: f11a84880e5e
Revises: 17e384880e5d
Create Date: 2026-10-02 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f11a84880e5e'
down_revision: Union[str, None] = '17e384880e5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'scan_candidates',
        sa.Column(
            'status_keberlakuan',
            sa.String(length=50),
            nullable=True,
            server_default='tidak_diketahui',
            comment='Status keberlakuan: berlaku | diubah | dicabut | tidak_diketahui',
        ),
    )


def downgrade() -> None:
    op.drop_column('scan_candidates', 'status_keberlakuan')
