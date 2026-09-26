"""step2 ingest failures

Revision ID: 2a1b3c4d5e6f
Revises: 19ab55fb7e4e
Create Date: 2026-09-26 18:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2a1b3c4d5e6f'
down_revision: Union[str, None] = '19ab55fb7e4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tambah source_id dan retry_of_failure_id pada job_ingest
    op.add_column('job_ingest', sa.Column('source_id', sa.Integer(), nullable=True, comment='FK ke sumber scraping (Langkah 6-7)'))
    op.create_foreign_key('fk_job_ingest_source_id', 'job_ingest', 'scraping_sources', ['source_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_job_ingest_source_id'), 'job_ingest', ['source_id'], unique=False)

    op.add_column('job_ingest', sa.Column('retry_of_failure_id', sa.Integer(), nullable=True, comment='FK ke baris ingest_failures jika job ini merupakan retry'))

    # 2. Buat tabel ingest_failures
    op.create_table('ingest_failures',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False, comment='Job asal proses ingest'),
        sa.Column('original_filename', sa.String(length=255), nullable=False, comment='Nama berkas asli (sudah disanitasi untuk tampilan)'),
        sa.Column('source_url', sa.Text(), nullable=True, comment='URL/jalur asal'),
        sa.Column('failure_type', sa.Enum('format_tidak_didukung', 'duplikat', 'ekstraksi_gagal', 'ocr_gagal', 'metadata_tidak_lengkap', 'sumber_tidak_dapat_diakses', 'kesalahan_internal', name='jeniskegagalan', native_enum=False), nullable=False, comment='Kategori kegagalan / duplikat'),
        sa.Column('reason_code', sa.String(length=50), nullable=False, comment='Kode rinci dari validasi/pipeline'),
        sa.Column('message', sa.Text(), nullable=False, comment='Pesan untuk pengguna (Bahasa Indonesia)'),
        sa.Column('is_retryable', sa.Boolean(), nullable=False, comment='Apakah kegagalan ini dapat diproses ulang'),
        sa.Column('quarantine_path', sa.Text(), nullable=True, comment='Path relatif isi berkas di karantina (hanya bila retryable)'),
        sa.Column('file_hash', sa.String(length=64), nullable=True, comment='SHA-256 hash berkas'),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=True, comment='Ukuran berkas dalam bytes'),
        sa.Column('duplicate_of_document_id', sa.Integer(), nullable=True, comment='Wajib terisi bila failure_type=duplikat'),
        sa.Column('ingest_options', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='Opsi ingest saat proses berlangsung (untuk kebutuhan retry)'),
        sa.Column('follow_up_status', sa.Enum('belum_ditangani', 'diproses_ulang', 'diabaikan', name='statustindaklanjut', native_enum=False), nullable=False, comment='Status tindak lanjut: belum_ditangani | diproses_ulang | diabaikan'),
        sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False, comment='Jumlah upaya pemrosesan ulang (retry)'),
        sa.Column('last_retry_at', sa.DateTime(timezone=True), nullable=True, comment='Waktu terakhir proses retry dilakukan'),
        sa.Column('last_retry_job_id', sa.Integer(), nullable=True, comment='Job ingest terakhir untuk retry'),
        sa.Column('resolved_document_id', sa.Integer(), nullable=True, comment='Dokumen hasil retry yang sukses'),
        sa.Column('handled_by_user_id', sa.Integer(), nullable=True, comment='Pengguna yang menangani kegagalan ini'),
        sa.Column('handling_note', sa.Text(), nullable=True, comment='Catatan penanganan'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("failure_type <> 'duplikat' OR duplicate_of_document_id IS NOT NULL", name='ck_failure_duplicate_ref'),
        sa.ForeignKeyConstraint(['duplicate_of_document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['handled_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['job_id'], ['job_ingest.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['last_retry_job_id'], ['job_ingest.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['resolved_document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ingest_failures_duplicate_of_document_id'), 'ingest_failures', ['duplicate_of_document_id'], unique=False)
    op.create_index(op.f('ix_ingest_failures_failure_type'), 'ingest_failures', ['failure_type'], unique=False)
    op.create_index(op.f('ix_ingest_failures_follow_up_status'), 'ingest_failures', ['follow_up_status'], unique=False)
    op.create_index(op.f('ix_ingest_failures_handled_by_user_id'), 'ingest_failures', ['handled_by_user_id'], unique=False)
    op.create_index(op.f('ix_ingest_failures_id'), 'ingest_failures', ['id'], unique=False)
    op.create_index(op.f('ix_ingest_failures_job_id'), 'ingest_failures', ['job_id'], unique=False)
    op.create_index(op.f('ix_ingest_failures_last_retry_job_id'), 'ingest_failures', ['last_retry_job_id'], unique=False)
    op.create_index(op.f('ix_ingest_failures_resolved_document_id'), 'ingest_failures', ['resolved_document_id'], unique=False)

    # 3. Hubungkan FK retry_of_failure_id dari job_ingest ke ingest_failures
    op.create_foreign_key('fk_job_ingest_retry_failure', 'job_ingest', 'ingest_failures', ['retry_of_failure_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    # 1. Hapus FK dari job_ingest ke ingest_failures
    op.drop_constraint('fk_job_ingest_retry_failure', 'job_ingest', type_='foreignkey')

    # 2. Hapus tabel ingest_failures
    op.drop_index(op.f('ix_ingest_failures_resolved_document_id'), table_name='ingest_failures')
    op.drop_index(op.f('ix_ingest_failures_last_retry_job_id'), table_name='ingest_failures')
    op.drop_index(op.f('ix_ingest_failures_job_id'), table_name='ingest_failures')
    op.drop_index(op.f('ix_ingest_failures_id'), table_name='ingest_failures')
    op.drop_index(op.f('ix_ingest_failures_handled_by_user_id'), table_name='ingest_failures')
    op.drop_index(op.f('ix_ingest_failures_follow_up_status'), table_name='ingest_failures')
    op.drop_index(op.f('ix_ingest_failures_failure_type'), table_name='ingest_failures')
    op.drop_index(op.f('ix_ingest_failures_duplicate_of_document_id'), table_name='ingest_failures')
    op.drop_table('ingest_failures')

    # 3. Hapus kolom dari job_ingest
    op.drop_constraint('fk_job_ingest_source_id', 'job_ingest', type_='foreignkey')
    op.drop_index(op.f('ix_job_ingest_source_id'), table_name='job_ingest')
    op.drop_column('job_ingest', 'retry_of_failure_id')
    op.drop_column('job_ingest', 'source_id')
