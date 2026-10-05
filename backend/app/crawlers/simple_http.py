"""
app/crawlers/simple_http.py
Re-ekspor SimpleHttpCrawler dari GenericHtmlCrawler untuk kompatibilitas ke belakang.
PENTING: Modul ini TIDAK BOLEH mengimpor app.database, app.models, app.routers, app.services.
"""
from app.crawlers.generic_html import (
    GenericHtmlCrawler,
    SimpleHttpCrawler,
    _HtmlLinkParser,
    _get_directory_prefix,
    _is_paging_link,
)
from app.crawlers.url_utils import extract_filename_from_cd

__all__ = [
    "GenericHtmlCrawler",
    "SimpleHttpCrawler",
    "_HtmlLinkParser",
    "_get_directory_prefix",
    "_is_paging_link",
    "extract_filename_from_cd",
]
