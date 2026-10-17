"""
app/services/attachment_service.py
Layanan deteksi dan penautan lampiran dokumen regulasi (Langkah 19).
"""
import logging
import re
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from app.models.document import Document

logger = logging.getLogger("hero")

# Pola regex untuk mendeteksi nama berkas lampiran:
# Nama berkas hanya dianggap lampiran bila diawali kata LAMPIRAN
# (mengabaikan awalan non-huruf seperti angka urut, garis bawah, atau tanda hubung).
# Sesudah kata LAMPIRAN harus ada pemisah (spasi, _, -, .) atau akhir nama.
_RE_FILENAME_ATTACHMENT = re.compile(r"(?i)^[^a-zA-Z]*LAMPIRAN(?:[\s_\-.]|$)")

# Pola label lampiran: LAMPIRAN diikuti spasi/delimitator dan nomor romawi/arab
_RE_LABEL_PATTERN = re.compile(r"(?i)(?:^|[^a-zA-Z0-9])LAMPIRAN[\s_\-]+([IVXLCDM]+|\d+)(?:[^a-zA-Z0-9]|$)")


def detect_attachment_heuristic(
    title: Optional[str] = None,
    original_filename: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Heuristik pendeteksian otomatis lampiran:
    - Judul (setelah strip) diawali LAMPIRAN (case-insensitive),
      atau original_filename diawali LAMPIRAN (mengabaikan awalan non-huruf) -> is_attachment = True.
    - attachment_label diambil dari pola LAMPIRAN\\s+([IVXLC]+|\\d+), menjadi mis. Lampiran I.
      Bila tidak terbaca, isi Lampiran.
    """
    clean_title = (title or "").strip()
    clean_filename = (original_filename or "").strip()

    title_is_attachment = False
    if clean_title:
        # Cek apakah judul diawali LAMPIRAN
        if re.match(r"(?i)^LAMPIRAN(?:[^a-zA-Z0-9]|$)", clean_title):
            title_is_attachment = True

    filename_is_attachment = False
    if clean_filename:
        # Cek apakah original_filename diawali LAMPIRAN (mengabaikan awalan non-huruf)
        if _RE_FILENAME_ATTACHMENT.search(clean_filename):
            filename_is_attachment = True

    is_attachment = title_is_attachment or filename_is_attachment
    if not is_attachment:
        return False, None

    # Ekstraksi label lampiran
    label: Optional[str] = None

    # Coba cari nomor di judul terlebih dahulu
    m_title = _RE_LABEL_PATTERN.search(clean_title)
    if m_title:
        num = m_title.group(1)
        label = f"Lampiran {num.upper()}" if not num.isdigit() else f"Lampiran {num}"
    else:
        # Coba cari di nama berkas
        m_file = _RE_LABEL_PATTERN.search(clean_filename)
        if m_file:
            num = m_file.group(1)
            label = f"Lampiran {num.upper()}" if not num.isdigit() else f"Lampiran {num}"
        else:
            # Fallback sesuai spesifikasi: bila tidak terbaca, isi "Lampiran"
            label = "Lampiran"

    return True, label


def link_attachment(db: Session, doc: Document) -> bool:
    """
    Tautkan sebuah dokumen lampiran ke dokumen induknya:
    Bila doc.is_attachment dan parent_document_id kosong tetapi parent_identity_key terisi ->
    cari dokumen aktif, bukan lampiran dengan identity_key itu, lalu set parent_document_id.
    """
    if not getattr(doc, "is_attachment", False):
        return False

    if doc.parent_document_id is not None:
        return False

    if not doc.parent_identity_key:
        return False

    parent = (
        db.query(Document)
        .filter(
            Document.identity_key == doc.parent_identity_key,
            Document.is_active == True,  # noqa: E712
            Document.is_attachment == False,  # noqa: E712
            Document.id != doc.id,
        )
        .order_by(Document.id.asc())
        .first()
    )

    if parent:
        doc.parent_document_id = parent.id
        logger.info(
            "Lampiran ID #%s ('%s') berhasil ditautkan ke induk ID #%s ('%s')",
            doc.id,
            doc.title,
            parent.id,
            parent.title,
        )
        return True

    return False


def link_pending_children(db: Session, parent_doc: Document) -> int:
    """
    Tautkan semua lampiran yang menunggu induk ini:
    Bila sebuah dokumen non-lampiran mendapat identity_key, tautkan semua lampiran
    yang parent_identity_key-nya sama dan parent_document_id-nya masih kosong.
    """
    if getattr(parent_doc, "is_attachment", False):
        return 0

    if not parent_doc.identity_key or not parent_doc.is_active:
        return 0

    pending_children = (
        db.query(Document)
        .filter(
            Document.parent_identity_key == parent_doc.identity_key,
            Document.parent_document_id.is_(None),
            Document.is_attachment == True,  # noqa: E712
            Document.id != parent_doc.id,
        )
        .all()
    )

    count = 0
    for child in pending_children:
        child.parent_document_id = parent_doc.id
        count += 1
        logger.info(
            "Lampiran ID #%s ('%s') ditautkan otomatis ke induk baru ID #%s ('%s')",
            child.id,
            child.title,
            parent_doc.id,
            parent_doc.title,
        )

    return count
