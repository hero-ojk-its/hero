"""Read model for the Knowledge Base screens: labels, derived fields, search."""
from __future__ import annotations

import sqlite3

import pytest

from hero.kb import readmodel as rm
from hero.kb.topics import assign_topics, primary_topic
from hero.pipeline import IngestPipeline


def test_title_case_keeps_acronyms_and_lowercases_particles():
    assert rm.title_case_id("PEDOMAN TRANSAKSI REPO BAGI LJK DAN BPR") == \
        "Pedoman Transaksi Repo bagi LJK dan BPR"


def test_short_number_matches_the_table_format():
    assert rm.short_number("POJK", "11/POJK.03/2024", 2024) == "POJK-11/2024"
    assert rm.short_number("POJK", "11 Tahun 2024", 2024) == "POJK-11/2024"
    assert rm.short_number("POJK", None, 2024) is None


def test_date_label_is_indonesian():
    assert rm.date_label("2024-03-12") == "12 Maret 2024"


@pytest.mark.parametrize("sq,jenis,expected", [
    ({"article_count": 5, "starts_at_pasal_1": True, "numbering_ascending": True,
      "duplicate_numbers": []}, "POJK", "lengkap"),
    ({"article_count": 5, "starts_at_pasal_1": False, "numbering_ascending": True,
      "duplicate_numbers": []}, "POJK", "sebagian"),
    ({"article_count": 0}, "POJK", "belum"),
    ({"article_count": 0, "section_count": 4}, "SEOJK", "seksi"),
])
def test_pasal_alignment(sq, jenis, expected):
    assert rm.pasal_alignment(jenis, sq)[0] == expected


def test_urgency_names_the_most_severe_sanction():
    ta = [{"category": "Sanksi", "text": "dikenai sanksi berupa teguran tertulis"},
          {"category": "Sanksi", "text": "dan pencabutan izin usaha"}]
    assert rm.harmonization_urgency("berlaku", ta) == ("tinggi", "Sanksi Pencabutan Izin")


def test_revoked_regulation_is_never_urgent():
    ta = [{"category": "Sanksi", "text": "denda"}]
    assert rm.harmonization_urgency("dicabut", ta)[0] == "rendah"


def test_topics_prefer_title_evidence_and_explain_themselves():
    hits = assign_topics("POJK tentang Ketahanan dan Keamanan Siber Bank Umum", None,
                         ["laporan bulanan"])
    assert hits[0].label == "Ketahanan Siber" and hits[0].field == "judul"
    assert primary_topic("Pedoman Pengawasan Bank Berdasarkan Risiko", None) == "Manajemen Risiko"


@pytest.mark.parametrize("raw", ['"', "AND OR NOT", 'keamanan" OR "x', "(((", "*"])
def test_fts_query_never_passes_raw_syntax_to_match(raw):
    q = rm.fts_query(raw)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    if q:
        conn.execute("SELECT * FROM t WHERE t MATCH ?", (q,)).fetchall()   # must not raise


@pytest.fixture
def kb(tmp_path, tmp_settings, regulation_pdf):
    docs = [regulation_pdf(tmp_path / "a.pdf"),
            regulation_pdf(tmp_path / "b.pdf", nomor=12, tahun=2025,
                           tentang="PELAPORAN BULANAN PERUSAHAAN PEMBIAYAAN",
                           subjek="Perusahaan Pembiayaan", kewajiban="menyampaikan laporan bulanan")]
    pipe = IngestPipeline(tmp_settings)
    try:
        run = pipe.run_upload(docs)
    finally:
        pipe.close()
    assert run.ingested == 2
    conn = sqlite3.connect(tmp_settings.catalog_db)
    return rm.ReadModel(conn)


def test_list_filters_and_search(kb):
    everything = kb.list(page_size=10)
    assert everything["total"] == 2
    item = everything["items"][0]
    assert item["status"] == {"value": "berlaku", "label": "Aktif", "tone": "success"}
    assert item["sumber"]["label"] == "Unggah Manual"
    assert kb.list(q="pembiayaan")["total"] == 1
    assert kb.list(q="pembiay")["total"] == 1            # prefix while typing
    assert kb.list(tahun=[2026])["total"] == 1
    assert kb.list(topik=["Pelaporan"])["total"] == 1


def test_detail_carries_reasons_for_every_verdict(kb):
    doc_id = kb.list(tahun=[2026])["items"][0]["id"]
    d = kb.get(doc_id)
    assert d["validasi"]["penyelarasan_pasal"]["label"] == "Terpetakan Lengkap"
    assert d["validasi"]["urgensi_harmonisasi"]["label"] == "Tinggi"
    assert d["validasi"]["urgensi_harmonisasi"]["alasan"] == "Sanksi Tertulis"
    assert d["nomor_singkat"] == "POJK-11/2026"
    assert any("Undang-Undang Nomor 21 Tahun 2011" in b for b in d["dasar_hukum"])


def test_facets_come_from_data(kb):
    f = kb.facets()
    assert {x["value"] for x in f["tahun"]} == {2025, 2026}
    assert sum(x["count"] for x in f["sumber"]) == 2


def test_sync_is_incremental_and_notices_other_connections(kb, tmp_settings):
    rm.sync(kb.conn)
    assert rm.sync(kb.conn).rebuilt == 0                  # nothing changed → nothing rebuilt
    other = sqlite3.connect(tmp_settings.catalog_db)
    doc_id = kb.list(page_size=1)["items"][0]["id"]
    other.execute("UPDATE documents SET reg_status = 'dicabut' WHERE doc_id = ?", (doc_id,))
    other.commit()
    assert kb.get(doc_id)["status"]["label"] == "Dicabut"   # picked up via data_version


def test_deleted_documents_leave_the_read_model(kb, tmp_settings):
    from hero.kb.catalog import Catalog
    doc_id = kb.list(page_size=1)["items"][0]["id"]
    with Catalog(tmp_settings.catalog_db) as cat:
        cat.delete_document(doc_id)
    assert kb.get(doc_id) is None
    assert kb.list()["total"] == 1
