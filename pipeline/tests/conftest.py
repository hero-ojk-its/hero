import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def scanned_pdf() -> Path:
    """An image-only PDF (rasterised POJK 9/2026), used for the OCR path."""
    path = FIXTURES / "scanned_pojk_sample.pdf"
    if not path.exists():
        pytest.skip("scanned fixture not generated; run tests/make_fixtures.py")
    return path


@pytest.fixture
def tmp_settings(tmp_path):
    from hero.config import OcrSettings, ScraperSettings, Settings

    return Settings(
        knowledge_base=tmp_path / "kb",
        staging_dir=tmp_path / "staging",
        catalog_db=tmp_path / "catalog.db",
        scraper=ScraperSettings(delay_seconds=0.0, respect_robots=False),
        ocr=OcrSettings(enabled=False),
    )


REGULATION_TEMPLATE = """SALINAN
PERATURAN OTORITAS JASA KEUANGAN
REPUBLIK INDONESIA
NOMOR {nomor} TAHUN {tahun}
TENTANG
{tentang}

Mengingat : 1. Undang-Undang Nomor 21 Tahun 2011 tentang Otoritas Jasa Keuangan;

Pasal 1
Dalam Peraturan ini yang dimaksud dengan {istilah} adalah {definisi}.

Pasal 2
(1) {subjek} wajib {kewajiban}.
(2) {subjek} dilarang mengalihkan tanggung jawab sebagaimana dimaksud pada ayat (1).

Pasal 3
{subjek} yang melanggar ketentuan dikenai sanksi administratif berupa teguran tertulis.

Ditetapkan di Jakarta
pada tanggal 3 Maret {tahun}
"""


@pytest.fixture
def regulation_pdf():
    """Factory: write a small born-digital POJK with real Pasal structure."""
    import pymupdf

    def make(path, *, nomor=11, tahun=2026,
             tentang="PENYELENGGARAAN TEKNOLOGI INFORMASI OLEH BANK UMUM",
             istilah="Sistem Elektronik", definisi="rangkaian perangkat teknologi informasi",
             subjek="Bank", kewajiban="menerapkan manajemen risiko teknologi informasi"):
        text = REGULATION_TEMPLATE.format(nomor=nomor, tahun=tahun, tentang=tentang,
                                          istilah=istilah, definisi=definisi, subjek=subjek,
                                          kewajiban=kewajiban)
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 545, 800), text, fontsize=9)
        doc.save(path)
        doc.close()
        return path

    return make
