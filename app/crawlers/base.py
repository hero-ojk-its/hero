"""
app/crawlers/base.py
Protokol dan dataclass dasar untuk crawler HERO.
PENTING: Modul ini TIDAK BOLEH mengimpor app.database, app.models, app.routers, app.services.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional, List, Protocol


@dataclass(frozen=True)
class PdfCandidate:
    """Kandidat berkas PDF yang ditemukan saat pemindaian situs."""
    url: str                 # sudah dinormalisasi
    filename: str            # dari path URL / Content-Disposition, sudah di-unquote
    size_bytes: Optional[int]
    found_on_page: str
    depth: int               # 1 = ditemukan di halaman awal (atau halaman paging-nya)


@dataclass
class ScanResult:
    """Hasil pemindaian situs oleh crawler."""
    candidates: List[PdfCandidate] = field(default_factory=list)
    pages_visited: int = 0
    errors: List[str] = field(default_factory=list)  # pesan Indonesia
    truncated: bool = False                          # true bila kena batas halaman/kandidat


@dataclass
class FetchedFile:
    """Hasil pengunduhan berkas PDF dari URL."""
    content: bytes
    filename: str
    final_url: str
    content_type: Optional[str] = None


class CrawlerError(Exception):
    """Kesalahan umum saat operasi pemindaian atau pengunduhan crawler."""
    pass


class BlockedUrlError(CrawlerError):
    """Kesalahan keamanan URL (SSRF, skema terlarang, akses IP privat/lokal)."""
    pass


class FetchTooLargeError(CrawlerError):
    """Ukuran berkas melebihi batas maksimal bytes yang diizinkan."""
    pass


class Crawler(Protocol):
    """Protokol antarmuka standar untuk semua backend crawler HERO."""
    name: str

    def scan(
        self,
        url: str,
        depth: int,
        *,
        max_pages: int,
        max_candidates: int,
        progress: Optional[Callable[[int, int], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> ScanResult:
        """Memindai URL dan mengembalikan kandidat PDF yang ditemukan."""
        ...

    def fetch(self, url: str, *, max_bytes: int) -> FetchedFile:
        """Mengunduh berkas dari URL dengan batasan ukuran."""
        ...
