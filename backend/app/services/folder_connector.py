"""
app/services/folder_connector.py
[US-16, FR-SCR-05] Konektor Folder Lokal untuk memindai dan membaca berkas PDF dalam direktori lokal.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
from typing import List

logger = logging.getLogger("hero")


@dataclass
class FolderEntry:
    """Representasi berkas yang ditemukan dalam pemindaian folder lokal."""
    relative_path: str
    absolute_path: Path
    size_bytes: int
    mtime: datetime


class FolderAccessError(Exception):
    """Exception saat folder akar tidak ditemukan atau tidak dapat diakses."""
    pass


def _is_hidden(path: Path) -> bool:
    """Cek apakah berkas/folder tersembunyi (awalan '.' atau atribut hidden di Windows)."""
    if path.name.startswith("."):
        return True
    try:
        if os.name == "nt":
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            if attrs != -1 and (attrs & 2):  # FILE_ATTRIBUTE_HIDDEN = 2
                return True
    except Exception:
        pass
    return False


def _is_temp_file(name: str) -> bool:
    """Cek apakah berkas sementara Office/OneDrive (~$*, *.tmp)."""
    return name.startswith("~$") or name.lower().endswith(".tmp")


def list_pdf_files(
    root: Path,
    recursive: bool = True,
    max_files: int = 5000,
) -> List[FolderEntry]:
    """
    Pindai direktori untuk menemukan semua berkas .pdf (case-insensitive).
    
    Aturan:
    - Hanya berkas .pdf yang diambil; berkas lain diabaikan diam-diam.
    - Lewati berkas/folder tersembunyi (awalan . atau atribut hidden) dan berkas sementara (~$*, *.tmp).
    - Jangan mengikuti symlink/junction yang keluar dari root.
    - Urutkan berdasarkan relative_path secara deterministik.
    - Bila melebihi max_files, potong ke max_files.
    - Error per subfolder dicatat ke log dan dilanjutkan.
    - Jika root tidak ada / tidak dapat dibaca, lemparkan FolderAccessError.
    """
    try:
        resolved_root = root.resolve()
    except Exception as exc:
        raise FolderAccessError(f"Folder '{root}' tidak dapat diakses: {exc}") from exc

    if not resolved_root.exists() or not resolved_root.is_dir():
        raise FolderAccessError(f"Folder '{root}' tidak ditemukan atau bukan sebuah direktori.")

    entries: List[FolderEntry] = []

    def scan_dir(dir_path: Path):
        try:
            with os.scandir(dir_path) as it:
                dir_items = list(it)
        except (PermissionError, OSError) as exc:
            logger.warning("[FolderConnector] Izin baca ditolak pada direktori '%s': %s", dir_path, exc)
            return

        for item in dir_items:
            item_path = Path(item.path)

            # Lewati file/folder tersembunyi atau file sementara
            if _is_hidden(item_path) or _is_temp_file(item.name):
                continue

            try:
                resolved_item = item_path.resolve()
                # Cegah symlink/junction keluar dari root
                if not resolved_item.is_relative_to(resolved_root):
                    logger.warning(
                        "[FolderConnector] Jalur '%s' berada di luar akar '%s', diabaikan.",
                        item_path, resolved_root
                    )
                    continue
            except (ValueError, OSError) as exc:
                logger.warning("[FolderConnector] Gagal resolve jalur '%s': %s", item_path, exc)
                continue

            try:
                if item.is_dir(follow_symlinks=False):
                    if recursive:
                        scan_dir(item_path)
                elif item.is_file(follow_symlinks=True):
                    if item.name.lower().endswith(".pdf"):
                        stat = item_path.stat()
                        rel_path = resolved_item.relative_to(resolved_root).as_posix()
                        mtime_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                        entries.append(
                            FolderEntry(
                                relative_path=rel_path,
                                absolute_path=resolved_item,
                                size_bytes=stat.st_size,
                                mtime=mtime_dt,
                            )
                        )
            except (PermissionError, OSError) as exc:
                logger.warning("[FolderConnector] Gagal memproses berkas '%s': %s", item_path, exc)
                continue

    try:
        scan_dir(resolved_root)
    except Exception as exc:
        raise FolderAccessError(f"Terjadi kesalahan saat memindai direktori '{root}': {exc}") from exc

    # Urutkan secara deterministik
    entries.sort(key=lambda e: e.relative_path)

    if len(entries) > max_files:
        logger.info(
            "[FolderConnector] Jumlah berkas (%d) melebihi batas max_files (%d), dipotong.",
            len(entries), max_files
        )
        entries = entries[:max_files]

    return entries
