"""
app/crawlers
Paket crawler HERO: protokol, implementasi GenericHtmlCrawler, SharepointPostbackCrawler,
JdihApiCrawler, OneDriveShareCrawler, proteksi SSRF, dan registri.
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
from app.crawlers.generic_html import GenericHtmlCrawler, SimpleHttpCrawler
from app.crawlers.sharepoint_postback import SharepointPostbackCrawler
from app.crawlers.jdih_api import JdihApiCrawler
from app.crawlers.onedrive_share import OneDriveShareCrawler
from app.crawlers.registry import get_crawler, detect_adapter_from_url

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
    "GenericHtmlCrawler",
    "SimpleHttpCrawler",
    "SharepointPostbackCrawler",
    "JdihApiCrawler",
    "OneDriveShareCrawler",
    "get_crawler",
    "detect_adapter_from_url",
]
