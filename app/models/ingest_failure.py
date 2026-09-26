from sqlalchemy import (
    Column, Integer, String, Text, Boolean, BigInteger, DateTime, ForeignKey,
    Enum as SQLEnum, CheckConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.models.enums import JenisKegagalan, StatusTindakLanjut


class IngestFailure(Base):
    """
    Tabel: ingest_failures
    Mencatat seluruh kegagalan dan duplikat saat proses ingest dokumen.
    """

    __tablename__ = "ingest_failures"
    __table_args__ = (
        CheckConstraint(
            "failure_type <> 'duplikat' OR duplicate_of_document_id IS NOT NULL",
            name="ck_failure_duplicate_ref",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(
        Integer,
        ForeignKey("job_ingest.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Job asal proses ingest",
    )
    original_filename = Column(
        String(255),
        nullable=False,
        comment="Nama berkas asli (sudah disanitasi untuk tampilan)",
    )
    source_url = Column(Text, nullable=True, comment="URL/jalur asal")
    failure_type = Column(
        SQLEnum(JenisKegagalan, native_enum=False),
        nullable=False,
        index=True,
        comment="Kategori kegagalan / duplikat",
    )
    reason_code = Column(
        String(50),
        nullable=False,
        comment="Kode rinci dari validasi/pipeline",
    )
    message = Column(
        Text,
        nullable=False,
        comment="Pesan untuk pengguna (Bahasa Indonesia)",
    )
    is_retryable = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Apakah kegagalan ini dapat diproses ulang",
    )
    quarantine_path = Column(
        Text,
        nullable=True,
        comment="Path relatif isi berkas di karantina (hanya bila retryable)",
    )
    file_hash = Column(String(64), nullable=True, comment="SHA-256 hash berkas")
    file_size_bytes = Column(BigInteger, nullable=True, comment="Ukuran berkas dalam bytes")
    duplicate_of_document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Wajib terisi bila failure_type=duplikat",
    )
    ingest_options = Column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Opsi ingest saat proses berlangsung (untuk kebutuhan retry)",
    )
    follow_up_status = Column(
        SQLEnum(StatusTindakLanjut, native_enum=False),
        nullable=False,
        default=StatusTindakLanjut.belum_ditangani,
        index=True,
        comment="Status tindak lanjut: belum_ditangani | diproses_ulang | diabaikan",
    )
    attempt_count = Column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Jumlah upaya pemrosesan ulang (retry)",
    )
    last_retry_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Waktu terakhir proses retry dilakukan",
    )
    last_retry_job_id = Column(
        Integer,
        ForeignKey("job_ingest.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Job ingest terakhir untuk retry",
    )
    resolved_document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Dokumen hasil retry yang sukses",
    )
    handled_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Pengguna yang menangani kegagalan ini",
    )
    handling_note = Column(Text, nullable=True, comment="Catatan penanganan")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relasi
    job = relationship("JobIngest", foreign_keys=[job_id], back_populates="failures")
    duplicate_of_document = relationship("Document", foreign_keys=[duplicate_of_document_id])
    resolved_document = relationship("Document", foreign_keys=[resolved_document_id])
    last_retry_job = relationship("JobIngest", foreign_keys=[last_retry_job_id])
    handled_by_user = relationship("User", foreign_keys=[handled_by_user_id])

    def __repr__(self):
        return f"<IngestFailure id={self.id} type={self.failure_type} status={self.follow_up_status}>"
