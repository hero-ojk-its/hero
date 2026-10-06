"""Data workstream: scan-time file index, dynamic naming, access audit, snapshot."""
from __future__ import annotations

import json
import sqlite3

import pytest

from hero.ingest import probe
from hero.kb.access import apply, audit, redact_ref
from hero.kb.catalog import Catalog
from hero.kb.naming import (
    check_template, components_from_template, render_name, template_from_components,
)


# --------------------------------------------------------------------------- probe
class _Resp:
    def __init__(self, status=200, headers=None):
        self.status_code = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Scraper:
    """HEAD and ranged GET answers scripted per URL; records what was asked."""

    def __init__(self, head, get):
        from hero.config import ScraperSettings

        self.settings = ScraperSettings(delay_seconds=0)
        self._head, self._get, self.calls = head, get, []
        outer = self

        class _Session:
            def get(self, url, headers=None, stream=False, **kw):
                outer.calls.append(("GET", url, headers, stream))
                return outer._get[url]
        self.session = _Session()

    def allowed(self, url):
        return True

    def _throttle(self, url):
        pass

    def head(self, url):
        self.calls.append(("HEAD", url, None, None))
        return self._head.get(url)


def test_size_comes_from_head_without_touching_the_body():
    s = _Scraper({"u": _Resp(200, {"Content-Length": "293236", "Content-Type": "application/pdf"})}, {})
    res = probe.measure(s, "u")
    assert (res.size, res.method) == (293236, "head")
    assert all(c[0] == "HEAD" for c in s.calls)


def test_range_fallback_reads_total_from_content_range_and_streams():
    s = _Scraper({"u": _Resp(200, {})}, {"u": _Resp(206, {"Content-Range": "bytes 0-0/1242506"})})
    res = probe.measure(s, "u")
    assert (res.size, res.method) == (1242506, "range")
    get = [c for c in s.calls if c[0] == "GET"][0]
    assert get[2] == {"Range": "bytes=0-0"} and get[3] is True  # never downloads the file


def test_server_ignoring_range_still_gives_size_from_its_length_header():
    # jdih.ojk.go.id answers 200 to a Range request; the body must not be read.
    s = _Scraper({"u": None}, {"u": _Resp(200, {"Content-Length": "500"})})
    assert probe.measure(s, "u").size == 500


def test_unknown_size_is_reported_not_guessed():
    s = _Scraper({"u": _Resp(200, {})}, {"u": _Resp(200, {"Transfer-Encoding": "chunked"})})
    res = probe.measure(s, "u")
    assert res.size is None and "ukuran" in res.error


@pytest.mark.parametrize("row,role", [
    ({"document_url": "https://x/a.pdf", "document_name": "a.pdf", "attachments_json": "[]"}, "document_url"),
    ({"attachments_json": json.dumps([{"kind": "matriks", "url": "https://x/m.docx"},
                                      {"kind": "utama", "url": "https://x/u.docx"}])}, "utama"),
    ({"attachments_json": json.dumps([{"kind": "matriks", "url": "https://x/m.docx", "ext": "docx"}])}, "matriks"),
])
def test_primary_file_prefers_the_regulation_itself(row, role):
    assert probe.primary_file(row).role == role


def test_acceptance_counts_only_rows_with_all_four_attributes(tmp_path):
    cat = Catalog(tmp_path / "c.db")
    rows = [("a", "https://x/a.pdf", "A", "a.pdf", 10), ("b", "https://x/b.pdf", "B", "b.pdf", None),
            ("c", None, "C", None, None)]
    for key, url, title, name, size in rows:
        cat.conn.execute("INSERT INTO inventory (record_key, source, title, file_url, file_name, file_size) "
                         "VALUES (?, 'jdih-ojk', ?, ?, ?, ?)", (key, title, url, name, size))
    cat.conn.commit()
    (r,) = probe.acceptance(cat, {"jdih-ojk": {"min": 2, "max": 4}})
    assert (r["rekaman"], r["url"], r["ukuran"], r["terindeks"]) == (3, 2, 1, 1)
    assert r["ground_truth"] == "2–4" and r["dalam_rentang"] is False
    missing = {x["record_key"]: x["kurang"] for x in probe.iter_unindexed(cat)}
    assert missing == {"b": ["ukuran"], "c": ["url", "nama_berkas", "ukuran"]}


# --------------------------------------------------------------------------- naming
def test_buttons_compose_a_template_in_click_order():
    tpl = template_from_components(["jenis", "nomor", "tahun", "nama"])
    assert tpl == "{jenis} - {nomor_urut} - {tahun} - {judul:90}"
    assert check_template(tpl).valid
    assert components_from_template(tpl) == ["jenis", "nomor", "tahun", "nama"]
    name = render_name(tpl, {"jenis": "POJK", "nomor": "11/POJK.03/2024", "tahun": 2024,
                             "judul": "Ketahanan dan Keamanan Siber bagi Bank Umum"})
    assert name == "POJK - 11 - 2024 - Ketahanan dan Keamanan Siber bagi Bank Umum.pdf"


def test_bidang_is_the_readable_category_label():
    tpl = template_from_components(["bidang", "tahun"])
    assert render_name(tpl, {"kategori": "pasar-modal", "tahun": 2024}) == "Pasar Modal - 2024.pdf"


def test_same_button_twice_and_unknown_buttons():
    assert template_from_components(["tahun", "tahun"]) == "{tahun} - {tahun}"
    with pytest.raises(ValueError, match="tidak dikenal"):
        template_from_components(["warna"])
    with pytest.raises(ValueError):
        template_from_components([])
    assert components_from_template("{jenis} tentang {judul}") is None


def test_collisions_separate_source_duplicates_from_real_ones():
    from hero.dq.naming_collision import measure

    rows = [  # the same regulation listed twice, and two different ones sharing a subject
        {"source": "s", "title": "POJK tentang Tata Kelola", "doc_type": "POJK", "number": "1",
         "year": 2024, "reg_key": "POJK|1|2024"},
        {"source": "s", "title": "POJK tentang Tata Kelola", "doc_type": "POJK", "number": "1",
         "year": 2024, "reg_key": "POJK|1|2024"},
        {"source": "s", "title": "POJK tentang Tata Kelola", "doc_type": "POJK", "number": "2",
         "year": 2024, "reg_key": "POJK|2|2024"},
    ]
    by = {r.komponen: r for r in measure(rows, combos=(("nama", "jenis", "tahun"),
                                                       ("jenis", "nomor", "tahun", "nama")))}
    assert (by["nama → jenis → tahun"].bentrok, by["nama → jenis → tahun"].bentrok_nyata) == (3, 3)
    assert (by["jenis → nomor → tahun → nama"].bentrok_sumber,
            by["jenis → nomor → tahun → nama"].bentrok_nyata) == (2, 0)


# --------------------------------------------------------------------------- access
def _doc(cat, doc_id, source_type, doc_type, number, year, akses="publik", title="X"):
    cat.conn.execute(
        "INSERT INTO documents (doc_id, sha256, source_type, doc_type, number, year, title, "
        "status, access_class) VALUES (?,?,?,?,?,?,?,'ingested',?)",
        (doc_id, doc_id * 4, source_type, doc_type, number, year, title, akses))


def test_public_must_be_proven_and_labels_only_tighten(tmp_path):
    cat = Catalog(tmp_path / "c.db")
    cat.conn.execute("INSERT INTO inventory (record_key, source, reg_key) VALUES ('r', 'jdih-ojk', 'POJK|5|2024')")
    _doc(cat, "web", "web", "POJK", "9 Tahun 2026", 2026)
    _doc(cat, "reg", "onedrive", "POJK", "5 Tahun 2024", 2024)
    _doc(cat, "int", "onedrive", "PDK", "1/PDK.02/2024", 2024, title="CUTI PEGAWAI OTORITAS JASA KEUANGAN")
    _doc(cat, "anon", "onedrive", None, None, None)
    _doc(cat, "secret", "web", "POJK", "1 Tahun 2020", 2020, akses="rahasia")
    cat.conn.commit()
    f = {x.doc_id: x for x in audit(cat.conn)}
    assert f["web"].usulan == "publik" and f["reg"].usulan == "publik"
    assert f["int"].usulan == "internal" and "nomor bertanda internal" in f["int"].alasan
    assert f["anon"].usulan == "internal" and "tidak terbaca" in f["anon"].alasan
    assert f["secret"].usulan == "rahasia" and not f["secret"].berubah
    assert apply(cat.conn, list(f.values())) == 2


def test_share_links_never_leave_the_catalog():
    link = "https://oneojk-my.sharepoint.com/:f:/g/personal/x/EContohToken?e=abc123"
    assert redact_ref(f"{link}#downloads/a.pdf") == "[tautan-berbagi-onedrive]"
    assert redact_ref("https://ojk.go.id/a.pdf") == "https://ojk.go.id/a.pdf"


def test_share_link_comes_from_environment(tmp_path, monkeypatch):
    from hero.config import load_settings

    cfg = tmp_path / "s.yaml"
    cfg.write_text('onedrive_shares:\n  - name: m\n    share_url: "${HERO_TEST_SHARE}"\n', encoding="utf-8")
    monkeypatch.delenv("HERO_TEST_SHARE", raising=False)
    monkeypatch.chdir(tmp_path)
    assert load_settings(cfg).onedrive_shares[0].enabled is False  # unresolved → off
    monkeypatch.setenv("HERO_TEST_SHARE", "https://1drv.ms/f/s!abc")
    share = load_settings(cfg).onedrive_shares[0]
    assert share.enabled and share.share_url == "https://1drv.ms/f/s!abc"


# --------------------------------------------------------------------------- snapshot
def test_snapshot_has_contract_shapes_and_no_internal_documents(tmp_path, tmp_settings, regulation_pdf):
    from hero.kb.snapshot import build_snapshot
    from hero.pipeline import IngestPipeline

    pdfs = [regulation_pdf(tmp_path / "a.pdf"),
            regulation_pdf(tmp_path / "b.pdf", nomor=12, tahun=2025,
                           tentang="CUTI PEGAWAI", subjek="Pegawai", kewajiban="mengajukan cuti")]
    pipe = IngestPipeline(tmp_settings)
    try:
        assert pipe.run_upload(pdfs).ingested == 2
    finally:
        pipe.close()
    with sqlite3.connect(tmp_settings.catalog_db) as conn:
        conn.execute("UPDATE documents SET access_class='internal' WHERE subject LIKE '%CUTI%'")
    m = build_snapshot(tmp_settings, tmp_path / "snap")
    assert (m["dokumen"], m["dokumen_disembunyikan"]) == (1, 1)
    listing = json.loads((tmp_path / "snap/api/kb/documents.json").read_text(encoding="utf-8"))
    assert listing["total"] == 1 and "CUTI" not in json.dumps(listing).upper()
    facets = json.loads((tmp_path / "snap/api/kb/facets.json").read_text(encoding="utf-8"))
    assert sum(v["count"] for v in facets["jenis"]) == 1
    detail = tmp_path / f"snap/api/kb/documents/{listing['items'][0]['id']}.json"
    assert "poin_kunci" in json.loads(detail.read_text(encoding="utf-8"))
    # the live catalog is untouched
    with sqlite3.connect(tmp_settings.catalog_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 2


# --------------------------------------------------------------------------- extraction fixes
def test_citation_numbers_on_their_own_line_survive_the_page_number_strip():
    from hero.extract.pdf import strip_repeated_lines
    from hero.models import PageText

    page = PageText(number=1, source="text-layer", text="Mengingat : Undang-Undang Nomor\n21\nTahun\n2011\ntentang "
                                   "Otoritas Jasa Keuangan;\n- 2 -\nPasal 1\n7\nBank wajib lapor.")
    strip_repeated_lines([page])
    assert "Undang-Undang Nomor 21 Tahun 2011 tentang" in page.text
    assert "- 2 -" not in page.text and "\n7\n" not in page.text   # real page numbers still go


def test_duplicated_year_in_the_number_is_collapsed():
    from hero.extract.metadata import extract_metadata

    md = extract_metadata("PERATURAN OTORITAS JASA KEUANGAN\nNOMOR 1 /POJK.05/20172017\nTENTANG\n"
                          "PERIZINAN USAHA DAN KELEMBAGAAN LEMBAGA PENJAMIN\nMenimbang : …")
    assert md.number == "1/POJK.05/2017" and md.year == 2017


def test_a_preamble_citation_is_never_read_as_the_documents_own_number():
    from hero.extract.metadata import extract_metadata

    # Text layer lost "NOMOR 14 TAHUN 2023 TENTANG"; the first number left is a citation.
    md = extract_metadata("SALINAN\nPERATURAN OTORITAS JASA KEUANGAN\nPERDAGANGAN KARBON\n"
                          "Menimbang : bahwa untuk melaksanakan Pasal 26 Undang-Undang Nomor 4 "
                          "Tahun 2023 tentang Pengembangan dan Penguatan Sektor Keuangan;")
    assert md.number != "4 Tahun 2023"


def test_garbled_text_layer_is_detected_but_lists_are_not():
    from hero.extract.pdf import garbled_text_layer

    garbled = "\n".join(["Pasal 1", "2.", "s", "d", "m", "p", "i", "a", "p", "i"] * 3)
    listing = "\n".join([f"{n}." if n % 2 else "Bank wajib menyampaikan laporan bulanan."
                         for n in range(30)])
    assert garbled_text_layer(garbled) and not garbled_text_layer(listing)
