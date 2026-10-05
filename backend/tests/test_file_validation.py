import pytest
from app.services.file_validation import (
    FileFingerprint,
    FileRejectCode,
    FileValidationError,
    fingerprint,
    sanitize_filename,
    validate_pdf,
)
from tests.conftest import make_pdf


def test_sanitize_filename_t24():
    """T24: sanitize_filename('..\\..\\a b/Peraturan  OJK*?.PDF') menghasilkan basename aman berakhiran .pdf."""
    raw_name = "..\\..\\a b/Peraturan  OJK*?.PDF"
    clean = sanitize_filename(raw_name)

    assert ".." not in clean
    assert "/" not in clean
    assert "\\" not in clean
    assert "*" not in clean
    assert "?" not in clean
    assert clean.lower().endswith(".pdf")
    assert "Peraturan OJK.PDF" in clean or "Peraturan OJK.pdf" in clean


def test_sanitize_filename_edge_cases():
    """Uji kasus batas untuk sanitize_filename."""
    assert sanitize_filename("") == "dokumen.pdf"
    assert sanitize_filename(None) == "dokumen.pdf"
    assert sanitize_filename("   ") == "dokumen.pdf"
    assert sanitize_filename("....pdf") == "dokumen.pdf"
    assert sanitize_filename("test document.pdf") == "test document.pdf"
    assert sanitize_filename("spasi   banyak   banget.pdf") == "spasi banyak banget.pdf"


def test_validate_pdf_success():
    """Validasi PDF valid berhasil tanpa exception."""
    pdf_bytes = make_pdf("UU No 1 Tahun 2026")
    validate_pdf("uu_1_2026.pdf", pdf_bytes, max_bytes=10 * 1024 * 1024)


def test_validate_pdf_non_pdf_extension():
    """Validasi ekstensi selain .pdf gagal dengan format_tidak_didukung."""
    with pytest.raises(FileValidationError) as exc_info:
        validate_pdf("document.txt", b"plain text", max_bytes=1024)
    assert exc_info.value.code == FileRejectCode.format_tidak_didukung
    assert "Hanya berkas PDF yang diterima" in exc_info.value.message


def test_validate_pdf_empty_content():
    """Validasi berkas 0 byte gagal dengan berkas_kosong."""
    with pytest.raises(FileValidationError) as exc_info:
        validate_pdf("empty.pdf", b"", max_bytes=1024)
    assert exc_info.value.code == FileRejectCode.berkas_kosong
    assert "kosong" in exc_info.value.message


def test_validate_pdf_exceed_max_bytes():
    """Validasi ukuran melebihi batas gagal dengan ukuran_melebihi_batas."""
    pdf_bytes = make_pdf("a" * 2000)
    with pytest.raises(FileValidationError) as exc_info:
        validate_pdf("large.pdf", pdf_bytes, max_bytes=500)
    assert exc_info.value.code == FileRejectCode.ukuran_melebihi_batas
    assert "melebihi batas maksimal" in exc_info.value.message


def test_validate_pdf_invalid_header():
    """Berkas berekstensi .pdf tetapi tanpa header %PDF- gagal dengan format_tidak_didukung."""
    fake_pdf = b"INI BUKAN PDF SAMA SEKALI"
    with pytest.raises(FileValidationError) as exc_info:
        validate_pdf("fake.pdf", fake_pdf, max_bytes=1024 * 1024)
    assert exc_info.value.code == FileRejectCode.format_tidak_didukung
    assert "bukan PDF yang valid" in exc_info.value.message


def test_fingerprint():
    """Penghitungan fingerprint SHA-256 dan ukuran berkas akurat."""
    data = b"isi berkas dokumen regulasi"
    fp = fingerprint(data)
    assert isinstance(fp, FileFingerprint)
    assert fp.size_bytes == len(data)
    assert len(fp.sha256) == 64
