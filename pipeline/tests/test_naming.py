"""US-20 / US-20a: identitas halaman 1, penamaan baku, antrian koreksi."""
from datetime import date
from pathlib import Path

import pymupdf
import pytest

from hero.extract.firstpage import read_identity
from hero.kb import correction
from hero.kb.catalog import Catalog
from hero.kb.naming import DEFAULT_TEMPLATE, check_template, render_name, save_template
from hero.pipeline import IngestPipeline

FIELDS = {"jenis": "POJK", "nomor": "11/POJK.03/2024", "tahun": 2024, "tanggal": date(2024, 3, 12),
          "judul": "KETAHANAN DAN KEAMANAN SIBER BAGI BANK UMUM", "kategori": "perbankan",
          "sumber": "jdih-ojk", "status": "berlaku"}


def write_pages(path: Path, pages: list[str]) -> Path:
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 545, 800), text, fontsize=10)
    doc.save(path)
    doc.close()
    return path


PAGE_1 = """SALINAN
PERATURAN OTORITAS JASA KEUANGAN
REPUBLIK INDONESIA
NOMOR 7 TAHUN 2025
TENTANG
LAPORAN BULANAN PERUSAHAAN PEMBIAYAAN

DENGAN RAHMAT TUHAN YANG MAHA ESA
DEWAN KOMISIONER OTORITAS JASA KEUANGAN,
Menimbang : a. bahwa untuk meningkatkan kualitas pengawasan perusahaan pembiayaan perlu laporan.
"""
BODY = "Pasal 1\nPerusahaan Pembiayaan wajib menyampaikan laporan bulanan kepada Otoritas Jasa Keuangan.\n" * 3
CLOSING = "Pasal 9\nPeraturan ini mulai berlaku pada tanggal diundangkan.\n\nDitetapkan di Jakarta\npada tanggal 21 Mei 2025\n"


# -- naming engine -------------------------------------------------------------
def test_default_template_renders_a_readable_safe_name():
    assert render_name(DEFAULT_TEMPLATE, FIELDS) == \
        "POJK 11 Tahun 2024 tentang Ketahanan dan Keamanan Siber bagi Bank Umum.pdf"


@pytest.mark.parametrize("template,expected", [
    ("{tanggal:%Y%m%d}_{jenis}_{nomor}", "20240312_POJK_11-POJK.03-2024.pdf"),
    ("{jenis}-{nomor_urut}-{tahun}-{judul:40|slug}", "POJK-11-2024-ketahanan-dan-keamanan-siber-bagi-bank.pdf"),
    ("{sumber}/{kategori} {judul|lower}", "jdih-ojk-perbankan ketahanan dan keamanan siber bagi bank umum.pdf"),
])
def test_template_tokens_arguments_and_filters(template, expected):
    assert check_template(template).valid
    assert render_name(template, FIELDS) == expected


def test_names_never_contain_path_separators_and_are_capped():
    name = render_name("{judul}", {"judul": 'A/B\\C:D*E?"F<G>H|' + "x" * 400})
    assert not set('/\\:*?"<>|') & set(name)
    assert len(name) <= 150 and name.endswith(".pdf")


@pytest.mark.parametrize("template,fragment", [
    ("", "kosong"), ("{jenis} {tidak_ada}", "tidak dikenal"), ("{judul|kapital}", "filter"),
    ("{judul:abc}", "angka"), ("{judul", "kurung"), ("nama tetap", "satu token"),
])
def test_invalid_templates_are_rejected_with_a_reason(template, fragment):
    chk = check_template(template)
    assert not chk.valid and any(fragment in e for e in chk.errors)


def test_tokens_used_by_the_template_become_required():
    need = correction.required_for("{jenis} {nomor_urut} {tahun}", ["judul"])
    assert need == ["judul", "jenis", "nomor", "tahun"]


# -- first-page reader -----------------------------------------------------------
def test_identity_reads_page_one_and_takes_the_date_from_the_closing_block(tmp_path):
    pdf = write_pages(tmp_path / "x.pdf", [PAGE_1, BODY, CLOSING])
    ident = read_identity(pdf)
    assert ident.jenis.nilai == "POJK" and ident.nomor.nilai == "7 Tahun 2025"
    assert ident.judul.nilai == "LAPORAN BULANAN PERUSAHAAN PEMBIAYAAN"
    assert ident.judul.sumber == "halaman-1" and ident.halaman_1_cara == "teks"
    assert ident.tanggal.nilai == date(2025, 5, 21) and ident.tanggal.sumber == "penutup"
    assert ident.lengkap


def test_unreadable_file_yields_an_incomplete_identity_not_an_exception(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 garbage")
    ident = read_identity(bad)
    assert not ident.lengkap and ident.catatan


def test_scanned_page_one_is_read_with_ocr(scanned_pdf):
    from hero.config import OcrSettings
    from hero.extract.ocr import tesseract_available
    if not tesseract_available():
        pytest.skip("tesseract not installed")
    ident = read_identity(scanned_pdf, ocr_settings=OcrSettings())
    assert ident.halaman_1_cara == "ocr"
    assert ident.nomor.nilai and ident.judul.nilai


# -- pipeline integration ----------------------------------------------------------
def _ingest(settings, pdf):
    pipe = IngestPipeline(settings, analyze=False)
    try:
        return pipe.run_upload([pdf]).records[0]
    finally:
        pipe.close()


def test_complete_document_enters_the_kb_under_the_template_name(tmp_path, tmp_settings):
    rec = _ingest(tmp_settings, write_pages(tmp_path / "unduhan (3).pdf", [PAGE_1, BODY, CLOSING]))
    stored = Path(rec.stored_path)
    assert stored.name == "POJK 7 Tahun 2025 tentang Laporan Bulanan Perusahaan Pembiayaan.pdf"
    assert stored.is_relative_to(tmp_settings.knowledge_base)
    # FR-SCR-09b: no file in the KB keeps its source name.
    assert not list(tmp_settings.knowledge_base.rglob("unduhan*"))
    with Catalog(tmp_settings.catalog_db) as cat:
        assert correction.summary(cat.conn) == {"dinamai": 1}


def test_incomplete_document_is_queued_outside_the_kb_not_discarded(tmp_path, tmp_settings):
    page = "SURAT PEMBERITAHUAN\nKepada seluruh pihak terkait.\n" + "Isi pemberitahuan tanpa nomor. " * 20
    rec = _ingest(tmp_settings, write_pages(tmp_path / "memo.pdf", [page]))
    assert rec.status == "ingested" and "antrian koreksi" in rec.reason
    stored = Path(rec.stored_path)
    assert stored.exists() and stored.name == f"{rec.doc_id}.pdf"
    assert not stored.is_relative_to(tmp_settings.knowledge_base)
    assert not list(tmp_settings.knowledge_base.rglob("*.pdf"))
    with Catalog(tmp_settings.catalog_db) as cat:
        q = correction.queue(cat.conn)
        assert [x["doc_id"] for x in q] == [rec.doc_id]
        assert set(q[0]["kurang"]) >= {"nomor", "tanggal"}
        assert cat.get(rec.doc_id) is not None          # still in the catalog


def test_resolving_a_correction_names_and_files_the_document(tmp_path, tmp_settings):
    page = "SURAT PEMBERITAHUAN\nKepada seluruh pihak terkait.\n" + "Isi pemberitahuan tanpa nomor. " * 20
    rec = _ingest(tmp_settings, write_pages(tmp_path / "memo.pdf", [page]))
    with Catalog(tmp_settings.catalog_db) as cat:
        with pytest.raises(correction.CorrectionError, match="YYYY-MM-DD"):
            correction.resolve(cat, tmp_settings, rec.doc_id, {"tanggal": "21/05/2025"})
        with pytest.raises(correction.CorrectionError, match="masih kurang"):
            correction.resolve(cat, tmp_settings, rec.doc_id, {"tanggal": "2025-05-21"})
        out = correction.resolve(cat, tmp_settings, rec.doc_id, {
            "jenis": "SEOJK", "nomor": "3/SEOJK.05/2025", "tanggal": "2025-05-21",
            "judul": "Pemberitahuan Laporan"}, oleh="petugas-uji")
        assert out["nama"] == "SEOJK 3 Tahun 2025 tentang Pemberitahuan Laporan.pdf"
        row = cat.get(rec.doc_id)
        assert Path(row["stored_path"]).exists()
        assert Path(row["stored_path"]).resolve().is_relative_to(tmp_settings.knowledge_base.resolve())
        assert row["number"] == "3/SEOJK.05/2025" and row["issued_date"] == "2025-05-21"
        assert correction.summary(cat.conn) == {"dikoreksi": 1}
        assert correction.queue(cat.conn) == []


def test_changing_the_template_renames_existing_files(tmp_path, tmp_settings):
    rec = _ingest(tmp_settings, write_pages(tmp_path / "a.pdf", [PAGE_1, BODY, CLOSING]))
    with Catalog(tmp_settings.catalog_db) as cat:
        assert save_template(cat.conn, "{tanggal:%Y-%m-%d} {jenis} {nomor_urut}").valid
        plan = correction.apply_template(cat, tmp_settings, dry_run=True)
        assert plan.dinamai == 1 and Path(cat.get(rec.doc_id)["stored_path"]).name != "2025-05-21 POJK 7.pdf"
        correction.apply_template(cat, tmp_settings, dry_run=False)
        stored = Path(cat.get(rec.doc_id)["stored_path"])
        assert stored.name == "2025-05-21 POJK 7.pdf" and stored.exists()
        again = correction.apply_template(cat, tmp_settings, dry_run=True)
        assert again.dinamai == 0 and again.tetap == 1


def test_naming_can_be_switched_off(tmp_path, tmp_settings):
    tmp_settings.naming.enabled = False
    rec = _ingest(tmp_settings, write_pages(tmp_path / "a.pdf", [PAGE_1, BODY, CLOSING]))
    assert Path(rec.stored_path).name.startswith("pojk-7-tahun-2025")


def test_drafts_use_their_own_template_and_need_only_a_title(tmp_path, tmp_settings):
    draft = ("RANCANGAN\nPERATURAN OTORITAS JASA KEUANGAN\nREPUBLIK INDONESIA\nNOMOR … TAHUN …\n"
             "TENTANG\nPENERAPAN TATA KELOLA BAGI BANK PEREKONOMIAN RAKYAT\n\n" + BODY
             + "\nDitetapkan di Jakarta\npada tanggal …\n")
    pipe = IngestPipeline(tmp_settings, analyze=False)
    try:
        rec = pipe.ingest_file(write_pages(tmp_path / "rpojk.pdf", [draft]), "web", "ojk",
                               source_ref="https://ojk.go.id/rancangan/x.pdf", source_key="ojk-rancangan")
    finally:
        pipe.close()
    assert Path(rec.stored_path).name == \
        "RANCANGAN POJK tentang Penerapan Tata Kelola bagi Bank Perekonomian Rakyat.pdf"


def test_english_translation_closing_block_gives_the_date(tmp_path):
    page1 = ("BANK INDONESIA REGULATION\nNUMBER 14/15/PBI/2012\nCONCERNING\n"
             "ASSESSMENT OF COMMERCIAL BANK ASSET QUALITY\n\nWITH THE BLESSINGS OF GOD ALMIGHTY\n" + "x " * 80)
    pdf = write_pages(tmp_path / "en.pdf", [page1, "Article 1\n" + "text " * 50,
                                             "Enacted in Jakarta\nOn 24 October 2012\nGOVERNOR"])
    ident = read_identity(pdf)
    assert ident.tanggal.nilai == date(2012, 10, 24) and ident.tanggal.sumber == "penutup"
