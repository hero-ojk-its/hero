import pytest
from pathlib import Path
from app.services.storage_service import StorageError, StorageService


def test_storage_save_pdf_no_overwrite_t22(tmp_path: Path):
    """
    T22: StorageService.save_pdf dua kali dengan filename_hint sama.
    Nama kedua bersufiks '-1'; isi berkas pertama tidak berubah.
    """
    storage = StorageService(base_path=tmp_path / "storage")

    content1 = b"%PDF-1.4 konten pertama regulasi"
    content2 = b"%PDF-1.4 konten kedua peraturan"

    hint = "test_document.pdf"
    path1 = storage.save_pdf(content1, filename_hint=hint)
    path2 = storage.save_pdf(content2, filename_hint=hint)

    assert path1 == "pdf/test_document.pdf"
    assert path2 == "pdf/test_document-1.pdf"

    abs_path1 = storage.absolute_path(path1)
    abs_path2 = storage.absolute_path(path2)

    assert abs_path1.is_file()
    assert abs_path2.is_file()
    assert abs_path1.read_bytes() == content1
    assert abs_path2.read_bytes() == content2


def test_storage_path_traversal_t23(tmp_path: Path):
    """
    T23: StorageService.absolute_path('../../etc/passwd') melempar StorageError.
    """
    storage = StorageService(base_path=tmp_path / "storage")

    with pytest.raises(StorageError) as exc_info:
        storage.absolute_path("../../etc/passwd")
    assert "path traversal" in exc_info.value.args[0].lower()

    with pytest.raises(StorageError):
        storage.absolute_path("..\\..\\windows\\system32\\calc.exe")


def test_storage_delete_and_exists(tmp_path: Path):
    """Uji metode exists dan delete idempoten."""
    storage = StorageService(base_path=tmp_path / "storage")
    content = b"%PDF-1.4 dokumen demo"
    rel_path = storage.save_pdf(content, filename_hint="demo.pdf")

    assert storage.exists(rel_path) is True
    assert storage.exists("pdf/tidak_ada.pdf") is False

    storage.delete(rel_path)
    assert storage.exists(rel_path) is False

    # Hapus lagi tidak menimbulkan error (idempoten)
    storage.delete(rel_path)
    storage.delete("pdf/file_fiktif.pdf")
