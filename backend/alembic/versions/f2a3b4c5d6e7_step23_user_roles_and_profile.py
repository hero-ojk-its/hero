"""step23 user roles and profile fields (US-01 #32)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-10-19 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update data peran yang sudah ada
    op.execute("UPDATE users SET role = 'admin_sistem' WHERE role = 'admin'")
    op.execute("UPDATE users SET role = 'analis' WHERE role = 'user' OR role NOT IN ('admin_sistem', 'admin_kb', 'pilot_user')")

    # 2. Tambah kolom profil pengguna
    op.add_column(
        'users',
        sa.Column('nama_lengkap', sa.String(length=150), nullable=True, comment='Nama lengkap pengguna'),
    )
    op.add_column(
        'users',
        sa.Column('unit_kerja', sa.String(length=150), nullable=True, comment='Unit kerja / divisi pengguna'),
    )

    # 3. Ubah default role menjadi 'analis'
    op.alter_column(
        'users',
        'role',
        server_default=sa.text("'analis'"),
        existing_type=sa.String(length=20),
        comment="Peran akses: analis | admin_kb | admin_sistem | pilot_user",
    )

    # 4. Tambah CheckConstraint untuk 4 nilai peran yang valid
    op.create_check_constraint(
        'ck_users_role',
        'users',
        "role IN ('analis', 'admin_kb', 'admin_sistem', 'pilot_user')",
    )


def downgrade() -> None:
    # 1. Hapus CheckConstraint peran
    op.drop_constraint('ck_users_role', 'users', type_='check')

    # 2. Kembalikan pemetaan data peran
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'admin_sistem'")
    op.execute("UPDATE users SET role = 'user' WHERE role != 'admin'")

    # 3. Kembalikan default role menjadi 'user'
    op.alter_column(
        'users',
        'role',
        server_default=sa.text("'user'"),
        existing_type=sa.String(length=20),
        comment="Peran akses: admin | user",
    )

    # 4. Hapus kolom baru
    op.drop_column('users', 'unit_kerja')
    op.drop_column('users', 'nama_lengkap')
