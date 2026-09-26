"""
tests/dummy_crawler.py
Dummy crawler untuk pengujian external_module (K18).
"""
from app.crawlers.base import Crawler, PdfCandidate, ScanResult, FetchedFile


class DummyCustomCrawler:
    name: str = "dummy_custom_crawler"

    def __init__(self, settings=None):
        self.settings = settings

    def scan(
        self,
        url: str,
        depth: int,
        *,
        max_pages: int = 200,
        max_candidates: int = 5000,
        progress=None,
        should_cancel=None,
    ) -> ScanResult:
        candidate = PdfCandidate(
            url=f"{url}/dummy_custom.pdf",
            filename="dummy_custom.pdf",
            size_bytes=1024,
            found_on_page=url,
            depth=1,
        )
        return ScanResult(
            candidates=[candidate],
            pages_visited=1,
            errors=[],
            truncated=False,
        )

    def fetch(self, url: str, *, max_bytes: int = 104857600) -> FetchedFile:
        from tests.conftest import make_pdf
        return FetchedFile(
            content=make_pdf("Dummy PDF Content"),
            filename="dummy_custom.pdf",
            final_url=url,
            content_type="application/pdf",
        )
