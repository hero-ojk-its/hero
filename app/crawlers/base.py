"""
app/crawlers/base.py
Protokol dan dataclass dasar untuk crawler HERO.
PENTING: Modul ini TIDAK BOLEH mengimpor app.database, app.models, app.routers, app.services.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional, List, Dict, Any, Protocol


@dataclass(frozen=True)
class PdfCandidate:
    """Kandidat berkas PDF yang ditemukan saat pemindaian situs."""
    url: str                                         # sudah dinormalisasi
    filename: str                                    # dari path URL / Content-Disposition / metadata
    size_bytes: Optional[int] = None
    found_on_page: str = ""
    depth: int = 1                                   # 1 = ditemukan di halaman awal (atau halaman paging-nya)
    document_title: Optional[str] = None             # Judul regulasi / nama dokumen di situs
    detail_url: Optional[str] = None                 # Halaman detail tempat lampiran ditemukan
    final_url: Optional[str] = None                  # URL akhir setelah redirect
    doc_kind: Optional[str] = "utama"                # utama | abstrak | faq | lampiran | lainnya
    regulation_number: Optional[str] = None          # Nomor regulasi
    regulation_type: Optional[str] = None            # Jenis regulasi (dinormalisasi)
    bidang: Optional[str] = None                     # Sektor / bidang regulasi
    sub_bidang: Optional[str] = None                 # Sub-sektor regulasi
    release_date: Optional[date] = None              # Tanggal penetapan / terbit
    release_year: Optional[int] = None               # Tahun penetapan / terbit (terutama untuk OneDrive)
    effective_date: Optional[date] = None            # Tanggal mulai berlaku regulasi
    raw_regulation_number: Optional[str] = None      # Nomor mentah sebelum diformat
    match_warning: Optional[str] = None              # Peringatan ketidakcocokan nama berkas vs metadata regulasi
    size_source: Optional[str] = "unknown"           # listing | head | range | unknown
    source_path: Optional[str] = None                # Jalur folder relatif (OneDrive)


@dataclass
class ScanResult:
    """Hasil pemindaian situs oleh crawler."""
    candidates: List[PdfCandidate] = field(default_factory=list)
    pages_visited: int = 0
    errors: List[str] = field(default_factory=list)  # pesan Indonesia
    truncated: bool = False                          # true bila kena batas halaman/kandidat
    blocked: bool = False                            # true bila terdeteksi captcha / Cloudflare / WAF
    stats: Dict[str, Any] = field(default_factory=dict)  # statistik ringkasan pemindaian


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
