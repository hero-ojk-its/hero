"""
app/crawlers/registry.py
Factory untuk memuat instance Crawler berdasarkan konfigurasi dan adapter situs.
PENTING: Modul ini TIDAK BOLEH mengimpor app.database, app.models, app.routers, app.services.
"""
import importlib
import logging
from typing import Optional, Any
from urllib.parse import urlsplit

from app.crawlers.base import Crawler
from app.crawlers.generic_html import GenericHtmlCrawler
from app.crawlers.sharepoint_postback import SharepointPostbackCrawler
from app.crawlers.jdih_api import JdihApiCrawler
from app.crawlers.onedrive_share import OneDriveShareCrawler

logger = logging.getLogger("hero.crawler.registry")


def detect_adapter_from_url(url: Optional[str]) -> Optional[str]:
    """Mendeteksi adapter yang cocok berdasarkan pola host dan path URL."""
    if not url:
        return None

    try:
        parsed = urlsplit(url.strip())
        host = (parsed.hostname or "").lower()
        path = parsed.path.lower()
    except Exception:
        return None

    # 1. OneDrive / SharePoint public shared folder
    if "sharepoint.com" in host and (":f:/" in path or ":u:/" in path or "onedrive.aspx" in path or "/personal/" in path or "/sites/" in path):
        return "onedrive_share"
    if "1drv.ms" in host or "onedrive.live.com" in host:
        return "onedrive_share"

    # 2. JDIH OJK
    if "jdih.ojk.go.id" in host or "jdih." in host:
        return "jdih_api"

    # 3. SharePoint ASP.NET postback (Regulasi OJK)
    if "ojk.go.id" in host and "regulasi" in path:
        return "sharepoint_postback"

    return None


def get_crawler(
    settings: Any,
    source_url: Optional[str] = None,
    crawler_adapter: Optional[str] = None,
) -> Optional[Crawler]:
    """
    Mengembalikan instance crawler yang sesuai:
    1. Jika crawler_adapter dispesifikasikan (atau dipaksa di ScrapingSource), gunakan adapter tersebut.
    2. Jika tidak, deteksi otomatis dari source_url.
    3. Jika tidak cocok ke adapter manapun, fallback ke settings.crawler_backend.
    """
    adapter = (crawler_adapter or "").strip().lower()
    if not adapter:
        adapter = detect_adapter_from_url(source_url) or ""

    user_agent = getattr(settings, "crawl_user_agent", "HERO-Capstone-Crawler/0.10 (+kontak: tim HERO)")
    delay_sec = getattr(settings, "crawl_delay_seconds", 0.5)
    timeout_sec = getattr(settings, "crawl_timeout_seconds", 25)
    respect_robots = getattr(settings, "crawl_respect_robots", True)
    allow_private = getattr(settings, "crawl_allow_private_networks", False)
    head_for_size = getattr(settings, "crawl_head_for_size", True)

    if adapter == "onedrive_share":
        return OneDriveShareCrawler(
            user_agent=user_agent,
            delay_seconds=delay_sec,
            timeout_seconds=timeout_sec,
            respect_robots=False,  # OneDrive sharing links do not use robots.txt
            allow_private=allow_private,
            head_for_size=False,
        )

    if adapter == "jdih_api":
        return JdihApiCrawler(
            user_agent=user_agent,
            delay_seconds=delay_sec,
            timeout_seconds=timeout_sec,
            respect_robots=respect_robots,
            allow_private=allow_private,
            head_for_size=head_for_size,
        )

    if adapter == "sharepoint_postback":
        return SharepointPostbackCrawler(
            user_agent=user_agent,
            delay_seconds=delay_sec,
            timeout_seconds=timeout_sec,
            respect_robots=respect_robots,
            allow_private=allow_private,
            head_for_size=head_for_size,
        )

    if adapter in ("generic_html", "simple_http", "html"):
        return GenericHtmlCrawler(
            user_agent=user_agent,
            delay_seconds=delay_sec,
            timeout_seconds=timeout_sec,
            respect_robots=respect_robots,
            allow_private=allow_private,
            head_for_size=head_for_size,
        )

    # Fallback ke settings.crawler_backend
    backend = getattr(settings, "crawler_backend", "simple_http")

    if backend in ("simple_http", "generic_html"):
        return GenericHtmlCrawler(
            user_agent=user_agent,
            delay_seconds=delay_sec,
            timeout_seconds=timeout_sec,
            respect_robots=respect_robots,
            allow_private=allow_private,
            head_for_size=head_for_size,
        )

    if backend == "external_module":
        module_path = getattr(settings, "crawler_module", "")
        if not module_path or ":" not in module_path:
            logger.error(
                f"Konfigurasi crawler_module tidak valid: '{module_path}'. "
                f"Format yang diharapkan: 'paket.modul:NamaKelas'."
            )
            return None

        mod_name, class_name = module_path.split(":", 1)
        try:
            mod = importlib.import_module(mod_name)
            crawler_cls = getattr(mod, class_name)
            try:
                return crawler_cls(settings=settings)
            except TypeError:
                return crawler_cls()
        except Exception as e:
            logger.error(
                f"Gagal memuat modul crawler eksternal '{module_path}': {e}",
                exc_info=True,
            )
            return None

    if backend == "push":
        return None

    logger.warning(f"Backend crawler tidak dikenal: '{backend}'. Mengembalikan GenericHtmlCrawler default.")
    return GenericHtmlCrawler(
        user_agent=user_agent,
        delay_seconds=delay_sec,
        timeout_seconds=timeout_sec,
        respect_robots=respect_robots,
        allow_private=allow_private,
        head_for_size=head_for_size,
    )
