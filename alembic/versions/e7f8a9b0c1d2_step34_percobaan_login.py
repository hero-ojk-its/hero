"""step34 percobaan_login

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-11-01 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = 'd6e7f8a9b0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'percobaan_login',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kunci', sa.String(length=255), nullable=False, comment='Kunci pelacak unik: u:<username lower> atau ip:<ip>'),
        sa.Column('jumlah_gagal', sa.Integer(), server_default='0', nullable=False, comment='Akumulasi percobaan login gagal dalam jendela waktu'),
        sa.Column('jendela_mulai', sa.DateTime(timezone=True), nullable=False, comment='Waktu awal jendela perhitungan kegagalan'),
        sa.Column('terkunci_sampai', sa.DateTime(timezone=True), nullable=True, comment='Waktu hingga lockout berakhir; NULL jika tidak sedang terkunci'),
        sa.Column('diperbarui', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment='Waktu pencatatan atau pembaruan terakhir'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_percobaan_login')),
    )
    op.create_index(op.f('ix_percobaan_login_id'), 'percobaan_login', ['id'], unique=False)
    op.create_index(op.f('ix_percobaan_login_kunci'), 'percobaan_login', ['kunci'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_percobaan_login_kunci'), table_name='percobaan_login')
    op.drop_index(op.f('ix_percobaan_login_id'), table_name='percobaan_login')
    op.drop_table('percobaan_login')

