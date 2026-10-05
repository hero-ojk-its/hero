"""
app/services/storage_service.py
Layanan penyimpanan berkas fisik PDF dengan jaminan tanpa timpa (non-overwrite),
penulisan atomik, dan pencegahan path traversal.
"""
import os
import uuid
from pathlib import Path
from app.config import settings


class StorageError(Exception):
    """Kesalahan pada operasi penyimpanan berkas."""
    pass


class StorageService:
    def __init__(self, base_path: str | Path):
        self.base_path = Path(base_path).resolve()
        # Buat folder base, pdf, dan .tmp jika belum ada
        (self.base_path / "pdf").mkdir(parents=True, exist_ok=True)
        (self.base_path / ".tmp").mkdir(parents=True, exist_ok=True)

    def absolute_path(self, relative_path: str) -> Path:
        """
        Mengonversi path relatif menjadi path absolut dengan validasi keamanan path traversal.
        """
        if not relative_path:
            raise StorageError("Path relatif tidak boleh kosong.")

        # Normalisasi pemisah path
        clean_rel = relative_path.replace("\\", "/").lstrip("/")
        candidate = (self.base_path / clean_rel).resolve()

        # Validasi bahwa candidate berada di dalam base_path
        try:
            candidate.relative_to(self.base_path)
        except ValueError:
            raise StorageError(f"Akses ditolak: Percobaan path traversal terdeteksi pada '{relative_path}'.")

        return candidate

    def _resolve_dir(self, subdir: str) -> tuple[Path, str]:
        """Validasi subdir terhadap traversal dan kembalikan (Path absolut, clean_subdir relatif)."""
        clean_subdir = subdir.replace("\\", "/").strip("/")
        if not clean_subdir:
            target_dir = self.base_path
        else:
            target_dir = (self.base_path / clean_subdir).resolve()
            try:
                target_dir.relative_to(self.base_path)
            except ValueError:
                raise StorageError(f"Akses ditolak: Percobaan path traversal terdeteksi pada subdir '{subdir}'.")
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir, clean_subdir

    def save_pdf(self, content: bytes, filename_hint: str, subdir: str = "pdf") -> str:
        """
        Menyimpan berkas PDF secara atomik tanpa menimpa berkas yang sudah ada.
        Jika berkas dengan nama yang sama sudah ada, ditambahkan sufiks -1, -2, dst.
        Mengembalikan path relatif menggunakan pemisah '/' (contoh: 'pdf/3fa1c2d4e5f6_nama.pdf').
        """
        target_dir, clean_subdir = self._resolve_dir(subdir)
        tmp_dir = self.base_path / ".tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # 1. Tulis ke file temporer terlebih dahulu
        tmp_file = tmp_dir / f"{uuid.uuid4().hex}.part"
        try:
            tmp_file.write_bytes(content)

            # 2. Tentukan nama target dengan pencegahan collision / overwrite
            hint_name = Path(filename_hint).name  # Ambil basename saja untuk mencegah traversal di hint
            hint_path = Path(hint_name)
            stem = hint_path.stem if hint_path.stem else "dokumen"
            suffix = hint_path.suffix if hint_path.suffix else ".pdf"

            idx = 0
            while True:
                candidate_name = f"{stem}{suffix}" if idx == 0 else f"{stem}-{idx}{suffix}"
                candidate_path = target_dir / candidate_name

                try:
                    # Mode 'xb' (exclusive creation) menjamin tidak ada penimpaan file
                    with open(candidate_path, "xb") as dst:
                        dst.write(content)
                    # Berhasil disimpan
                    rel_path = f"{clean_subdir}/{candidate_name}".lstrip("/").replace("\\", "/")
                    return rel_path
                except FileExistsError:
                    idx += 1
        finally:
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except OSError:
                    pass

    def read_pdf(self, relative_path: str) -> bytes:
        """
        Membaca isi berkas PDF dari path relatif.
        """
        abs_path = self.absolute_path(relative_path)
        if not abs_path.is_file():
            raise StorageError(f"Berkas '{relative_path}' tidak ditemukan.")
        return abs_path.read_bytes()

    def move(self, rel_src: str, subdir: str, filename_hint: str) -> str:
        """
        Memindahkan berkas dari rel_src ke subdir/filename_hint tanpa menimpa berkas yang sudah ada.
        Jika nama sudah ada, ditambahkan sufiks -1, -2, dst.
        Mengembalikan path relatif baru.
        """
        src_abs = self.absolute_path(rel_src)
        if not src_abs.is_file():
            raise StorageError(f"Berkas sumber '{rel_src}' tidak ditemukan.")

        target_dir, clean_subdir = self._resolve_dir(subdir)
        hint_name = Path(filename_hint).name
        hint_path = Path(hint_name)
        stem = hint_path.stem if hint_path.stem else "dokumen"
        suffix = hint_path.suffix if hint_path.suffix else ".pdf"

        idx = 0
        while True:
            candidate_name = f"{stem}{suffix}" if idx == 0 else f"{stem}-{idx}{suffix}"
            candidate_path = target_dir / candidate_name

            if candidate_path.resolve() == src_abs.resolve():
                # Lokasi sama, kembalikan path relatif saat ini
                return f"{clean_subdir}/{candidate_name}".lstrip("/").replace("\\", "/")

            try:
                # Klaim slot nama berkas secara eksklusif
                with open(candidate_path, "xb") as _:
                    pass
                # Ganti dengan berkas sumber secara atomik
                os.replace(src_abs, candidate_path)
                rel_path = f"{clean_subdir}/{candidate_name}".lstrip("/").replace("\\", "/")
                return rel_path
            except FileExistsError:
                idx += 1

    def delete(self, relative_path: str) -> None:
        """
        Menghapus berkas secara idempoten (tidak error jika berkas tidak ditemukan).
        """
        try:
            abs_path = self.absolute_path(relative_path)
            if abs_path.is_file():
                abs_path.unlink(missing_ok=True)
        except StorageError:
            pass
        except OSError:
            pass

    def exists(self, relative_path: str) -> bool:
        """
        Mengecek apakah berkas pada path relatif tertentu ada dan berupa file.
        """
        try:
            abs_path = self.absolute_path(relative_path)
            return abs_path.is_file()
        except StorageError:
            return False


def get_storage_service() -> StorageService:
    """Dependency injection FastAPI untuk StorageService."""
    return StorageService(base_path=settings.storage_path)

