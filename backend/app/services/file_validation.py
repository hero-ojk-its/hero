"""
app/services/file_validation.py
Layanan validasi format berkas PDF, sanitasi nama berkas, dan penghitungan fingerprint (SHA-256 + ukuran).
"""
import enum
import hashlib
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


class FileRejectCode(str, enum.Enum):
    format_tidak_didukung = "format_tidak_didukung"  # ekstensi bukan .pdf ATAU header bukan %PDF-
    berkas_kosong = "berkas_kosong"
    ukuran_melebihi_batas = "ukuran_melebihi_batas"


class FileValidationError(Exception):
    def __init__(self, code: FileRejectCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class FileFingerprint:
    sha256: str
    size_bytes: int


def sanitize_filename(name: str, max_len: int = 150) -> str:
    """
    Sanitasi nama berkas:
    - Mengambil basename saja (menghapus komponen folder / path traversal).
    - Normalisasi Unicode NFKD -> ASCII (menghapus aksen/karakter non-ASCII).
    - Hanya mengizinkan karakter [A-Za-z0-9._ -].
    - Mengubah spasi beruntun menjadi spasi tunggal dan melakukan strip.
    - Memotong panjang nama hingga max_len dengan tetap mempertahankan ekstensi .pdf.
    - Mengembalikan 'dokumen.pdf' jika hasil pembersihan kosong.
    """
    if not name or not isinstance(name, str):
        return "dokumen.pdf"

    # 1. Ambil basename (tangani pemisah slash Unix / dan Windows \)
    clean_name = name.replace("\\", "/").rstrip("/").split("/")[-1]
    clean_name = os.path.basename(clean_name)

    # 2. Normalisasi Unicode NFKD ke ASCII
    normalized = unicodedata.normalize("NFKD", clean_name).encode("ascii", "ignore").decode("ascii")

    # 3. Filter hanya karakter yang diizinkan: [A-Za-z0-9._ -()]
    filtered = "".join(c for c in normalized if c.isalnum() or c in "._- ()")

    # 4. Ganti spasi beruntun menjadi spasi tunggal dan strip
    collapsed = re.sub(r"\s+", " ", filtered).strip()

    # Hapus titik dan spasi di awal/akhir
    collapsed = collapsed.strip(". ")

    if not collapsed or collapsed.lower() == "pdf":
        return "dokumen.pdf"

    # Pastikan ekstensi .pdf dipertahankan dengan benar
    if not collapsed.lower().endswith(".pdf"):
        collapsed = f"{collapsed}.pdf"

    # Potong panjang jika melebihi max_len dengan mempertahankan akhiran .pdf
    if len(collapsed) > max_len:
        suffix = ".pdf"
        stem_max_len = max_len - len(suffix)
        stem = collapsed[:-4][:stem_max_len].rstrip(". ")
        if not stem:
            return "dokumen.pdf"
        collapsed = f"{stem}{suffix}"

    return collapsed


def validate_pdf(filename: str, content: bytes, max_bytes: int) -> None:
    """
    Validasi berkas PDF sesuai aturan tetap:
    1. Ekstensi case-insensitive harus .pdf
    2. len(content) == 0 -> berkas_kosong
    3. len(content) > max_bytes -> ukuran_melebihi_batas
    4. b'%PDF-' harus muncul dalam 1024 byte pertama -> format_tidak_didukung
    """
    ext = Path(filename).suffix if filename else ""
    if not ext or ext.lower() != ".pdf":
        raise FileValidationError(
            code=FileRejectCode.format_tidak_didukung,
            message=f"Hanya berkas PDF yang diterima. Berkas '{filename}' berekstensi '{ext}'.",
        )

    size = len(content)
    if size == 0:
        raise FileValidationError(
            code=FileRejectCode.berkas_kosong,
            message=f"Berkas PDF '{filename}' kosong (0 byte).",
        )

    if size > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise FileValidationError(
            code=FileRejectCode.ukuran_melebihi_batas,
            message=f"Ukuran berkas ({size} byte) melebihi batas maksimal {limit_mb} MB.",
        )

    header = content[:1024]
    if b"%PDF-" not in header:
        raise FileValidationError(
            code=FileRejectCode.format_tidak_didukung,
            message="Isi berkas bukan PDF yang valid meskipun berekstensi .pdf.",
        )


def fingerprint(content: bytes) -> FileFingerprint:
    """Hitung hash SHA-256 dan ukuran byte dari isi berkas."""
    sha256 = hashlib.sha256(content).hexdigest()
    return FileFingerprint(sha256=sha256, size_bytes=len(content))
