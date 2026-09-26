"""
app/crawlers/registry.py
Factory untuk memuat instance Crawler berdasarkan konfigurasi.
PENTING: Modul ini TIDAK BOLEH mengimpor app.database, app.models, app.routers, app.services.
"""
import importlib
import logging
from typing import Optional, Any
from app.crawlers.base import Crawler
from app.crawlers.simple_http import SimpleHttpCrawler

logger = logging.getLogger("hero.crawler.registry")


def get_crawler(settings: Any) -> Optional[Crawler]:
    """
    Mengembalikan instance crawler berdasarkan settings.crawler_backend.
    - 'simple_http'     -> SimpleHttpCrawler
    - 'external_module' -> memuat kelas dari settings.crawler_module (format: 'paket.modul:NamaKelas')
    - 'push'            -> None (crawler dijalankan oleh worker push eksternal)
    """
    backend = getattr(settings, "crawler_backend", "simple_http")

    if backend == "simple_http":
        return SimpleHttpCrawler(
            user_agent=getattr(settings, "crawl_user_agent", "HERO-Capstone-Crawler/0.7"),
            delay_seconds=getattr(settings, "crawl_delay_seconds", 0.5),
            timeout_seconds=getattr(settings, "crawl_timeout_seconds", 20),
            respect_robots=getattr(settings, "crawl_respect_robots", True),
            allow_private=getattr(settings, "crawl_allow_private_networks", False),
            head_for_size=getattr(settings, "crawl_head_for_size", True),
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
            # Instansiasi kelas crawler
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

    logger.warning(f"Backend crawler tidak dikenal: '{backend}'. Mengembalikan None.")
    return None
