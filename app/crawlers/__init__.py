"""
app/crawlers
Paket crawler HERO: protokol, implementasi SimpleHttpCrawler, proteksi SSRF, dan registri.
PENTING: Seluruh modul dalam paket ini TIDAK BOLEH mengimpor app.database, app.models, app.routers, app.services.
"""
from app.crawlers.base import (
    PdfCandidate,
    ScanResult,
    FetchedFile,
    Crawler,
    CrawlerError,
    BlockedUrlError,
    FetchTooLargeError,
)
from app.crawlers.url_utils import normalize_url, is_pdf_link, guard_url
from app.crawlers.simple_http import SimpleHttpCrawler
from app.crawlers.registry import get_crawler

__all__ = [
    "PdfCandidate",
    "ScanResult",
    "FetchedFile",
    "Crawler",
    "CrawlerError",
    "BlockedUrlError",
    "FetchTooLargeError",
    "normalize_url",
    "is_pdf_link",
    "guard_url",
    "SimpleHttpCrawler",
    "get_crawler",
]
