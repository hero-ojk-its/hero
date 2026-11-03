"""Classification, knowledge-base placement and the catalog."""
from pathlib import Path

from hero.kb.catalog import Catalog
from hero.kb.classify import builtin_rules, classify, kb_relative_path
from hero.models import IngestRecord, RegulationMetadata

BUILTIN = builtin_rules()     # mechanism tests must not depend on the editable YAML


def md(**kw) -> RegulationMetadata:
    return RegulationMetadata(**kw)


def test_classify_prefers_the_subject_over_the_body():
    meta = md(subject="PENYELENGGARAAN TEKNOLOGI INFORMASI")
    category, hits = classify(meta, text="bank umum " * 50, rules=BUILTIN)
    assert category == "teknologi-informasi"
    assert hits


def test_classify_falls_back_to_body_text():
    category, _ = classify(md(subject="KETENTUAN LAIN"),
                           text="pasar modal emiten bursa efek " * 5, rules=BUILTIN)
    assert category == "pasar-modal"


def test_classify_unmatched_goes_to_lain_lain():
    category, hits = classify(md(subject="ABCDEF"), text="xyz", rules=BUILTIN)
    assert category == "lain-lain"
    assert hits == []


def test_configured_hint_wins():
    category, hits = classify(md(subject="BANK UMUM"), hint="Rancangan Regulasi")
    assert category == "rancangan-regulasi"
    assert hits == ["configured hint"]


def test_kb_path_layout_is_source_category_type_year_status():
    meta = md(doc_type="POJK", number="9 Tahun 2026", year=2026,
              subject="PELAPORAN INSIDENTAL", status="berlaku")
    path = kb_relative_path(meta, "pasar-modal", "raw.pdf", source="jdih-ojk")
    assert path.parts[:5] == ("jdih-ojk", "pasar-modal", "pojk", "2026", "berlaku")
    assert path.suffix == ".pdf"
    assert "pelaporan-insidental" in path.stem


def test_kb_path_status_folders():
    for status, folder in (("dicabut", "dicabut"), ("diubah", "diubah"),
                           ("rancangan", "rancangan"),
                           ("unknown", "status-tidak-diketahui"),
                           (None, "status-tidak-diketahui")):
        meta = md(doc_type="POJK", year=2020, status=status or "unknown")
        assert kb_relative_path(meta, "perbankan", "x.pdf", "ojk-regulasi").parts[4] == folder


def test_kb_path_without_metadata_uses_filename():
    path = kb_relative_path(md(), "lain-lain", "Dokumen Tanpa Judul.pdf")
    assert path.parts[:5] == ("lainnya", "lain-lain", "tanpa-jenis", "tanpa-tahun",
                              "status-tidak-diketahui")
    assert path.stem == "dokumen-tanpa-judul"


def record(sha: str, **kw) -> IngestRecord:
    base = dict(
        doc_id=sha[:12], sha256=sha, source_type="web", source_name="s",
        source_ref="https://x/y.pdf", original_filename="y.pdf",
        status="ingested", metadata=md(doc_type="POJK", number="1 Tahun 2026",
                                       year=2026, subject="TENTANG X"),
    )
    base.update(kw)
    return IngestRecord(**base)


def test_catalog_roundtrip_and_dedupe(tmp_path):
    with Catalog(tmp_path / "c.db") as cat:
        rec = record("a" * 64, category="pasar-modal")
        cat.upsert_document(rec)
        assert cat.exists("a" * 64) is not None
        assert cat.exists("b" * 64) is None

        row = cat.get(rec.doc_id)
        assert row["doc_type"] == "POJK"
        assert row["category"] == "pasar-modal"

        # Re-ingesting identical content must not create a second row.
        cat.upsert_document(record("a" * 64, category="pasar-modal"))
        assert cat.stats()["total_documents"] == 1


def test_catalog_full_text_search(tmp_path):
    with Catalog(tmp_path / "c.db") as cat:
        rec = record("c" * 64)
        cat.upsert_document(rec)
        cat.save_text(rec.doc_id,
                      "Pelapor wajib menyampaikan Laporan Insidental daring.")
        hits = cat.search("Insidental")
        assert len(hits) == 1
        assert hits[0]["doc_id"] == rec.doc_id
        assert "Insidental" in hits[0]["snippet"]


def test_search_survives_invalid_fts_syntax(tmp_path):
    with Catalog(tmp_path / "c.db") as cat:
        rec = record("d" * 64)
        cat.upsert_document(rec)
        cat.save_text(rec.doc_id, "laporan bulanan perusahaan pembiayaan")
        # Unbalanced quote would raise straight from FTS5.
        assert cat.search('laporan "bulanan') is not None


def test_stats_group_by(tmp_path):
    with Catalog(tmp_path / "c.db") as cat:
        cat.upsert_document(record("e" * 64, category="perbankan"))
        cat.upsert_document(record("f" * 64, category="pasar-modal",
                                   source_type="upload"))
        stats = cat.stats()
        assert stats["total_documents"] == 2
        assert stats["by_category"]["perbankan"] == 1
        assert stats["by_source"]["upload"] == 1


def test_delete_document_removes_derived_rows_and_unlinks_inventory(tmp_path):
    """delete_document used to leave articles/document_text orphaned and the
    file on disk untouched — exactly the kind of dangling row hero.dq exists
    to catch. It must also let go of the document, not the KB catalog's memory
    that the source published it (URD: inventory tracks what was published,
    independent of whether HERO currently holds a copy)."""
    with Catalog(tmp_path / "c.db") as cat:
        rec = IngestRecord(doc_id="d1", sha256="h1", source_type="upload",
                           source_name="test-upload-regression",
                           source_ref="x", original_filename="a.pdf")
        rec.status = "ingested"
        rec.stored_path = str(tmp_path / "a.pdf")
        cat.upsert_document(rec)
        cat.save_text("d1", "isi", {}, None)
        cat.save_articles("d1", [{"number": "Pasal 1", "bab": None, "page": 1, "text": "x"}])
        cat.upsert_inventory({
            "record_key": "https://x/detail", "source": "ojk-regulasi",
            "title": "T", "status": "berlaku", "doc_id": "d1"})

        path = cat.delete_document("d1")
        assert path == str(tmp_path / "a.pdf")
        assert cat.get("d1") is None
        assert cat.get_text("d1") is None
        assert cat.conn.execute(
            "SELECT COUNT(*) FROM articles WHERE doc_id = 'd1'").fetchone()[0] == 0
        inv = cat.get_inventory("https://x/detail")
        assert inv["doc_id"] is None   # rekaman tetap ada, tautannya dilepas


def test_delete_document_on_missing_id_returns_none(tmp_path):
    with Catalog(tmp_path / "c.db") as cat:
        assert cat.delete_document("tidak-ada") is None


def test_rename_source_leaves_content_untouched(tmp_path):
    with Catalog(tmp_path / "c.db") as cat:
        rec = IngestRecord(doc_id="d1", sha256="h1", source_type="web",
                           source_name="api-test", source_ref="x",
                           original_filename="a.pdf")
        rec.status = "ingested"
        cat.upsert_document(rec)
        cat.rename_source("d1", "JDIH OJK — Register Peraturan")
        row = cat.get("d1")
        assert row["source_name"] == "JDIH OJK — Register Peraturan"
        assert row["sha256"] == "h1"   # konten tidak ikut berubah


# -- ekspor analisa v2 (FR-ANL-09) -------------------------------------------

def _simpan_analisa_v2(cat: Catalog, doc_id: str, hasil: dict) -> None:
    """Tulis satu baris analysis_v2 seperti yang dilakukan analysis/structured.py."""
    import json as _json

    cat.conn.execute(
        "CREATE TABLE IF NOT EXISTS analysis_v2 ("
        "doc_id TEXT PRIMARY KEY, versi TEXT NOT NULL, fingerprint TEXT, "
        "hasil TEXT NOT NULL, waktu_ms REAL, dibuat TEXT NOT NULL)")
    cat.conn.execute(
        "INSERT OR REPLACE INTO analysis_v2 VALUES (?,?,?,?,?,datetime('now'))",
        (doc_id, "v2.1", "fp", _json.dumps(hasil), 12.5))
    cat.conn.commit()


def test_export_analisa_membawa_pasal_dan_halaman(tmp_path):
    from hero.kb.export import export

    with Catalog(tmp_path / "c.db") as cat:
        rec = record("d" * 64)
        cat.upsert_document(rec)
        _simpan_analisa_v2(cat, rec.doc_id, {
            "identitas": {"tentang": "KETAHANAN SIBER", "status": "berlaku"},
            "metrik": {"jumlah_pasal": 3, "jumlah_poin": 2, "kata_ringkasan": 40},
            "ringkasan_teks": "POJK 1 Tahun 2026 tentang Ketahanan Siber.",
            "poin": [
                {"id": "p1", "kategori": "Kewajiban", "pasal": "Pasal 2 ayat (1)",
                 "halaman": 3, "prioritas": 4, "teks": "Bank wajib ..."},
                {"id": "p2", "kategori": "Sanksi", "pasal": "Pasal 9",
                 "halaman": 7, "prioritas": 5, "teks": "Sanksi administratif ..."},
            ],
        })
        counts = export(cat, tmp_path / "out", "csv")

    assert counts["analisa"] == 1
    assert counts["analisa_poin"] == 2

    import csv

    poin = list(csv.DictReader(
        open(tmp_path / "out" / "analisa_poin.csv", encoding="utf-8-sig")))
    # Invarian 2: tidak ada poin tanpa rujukan pasal + halaman.
    assert all(r["pasal"] and r["halaman"] for r in poin)
    # Label akses ikut, supaya konsumen hilir bisa menyaring non-publik.
    assert all("access_class" in r for r in poin)

    ringkas = list(csv.DictReader(
        open(tmp_path / "out" / "analisa.csv", encoding="utf-8-sig")))
    assert ringkas[0]["tentang"] == "KETAHANAN SIBER"
    assert ringkas[0]["versi"] == "v2.1"


def test_export_analisa_kosong_bila_belum_dianalisa(tmp_path):
    """Katalog tanpa tabel analysis_v2 tidak boleh menggagalkan ekspor."""
    from hero.kb.export import export

    with Catalog(tmp_path / "c.db") as cat:
        cat.upsert_document(record("e" * 64))
        counts = export(cat, tmp_path / "out", "csv")

    assert counts["analisa"] == 0
    assert counts["analisa_poin"] == 0
    assert counts["documents"] == 1


def test_export_analisa_melewati_json_rusak(tmp_path):
    """Satu baris cache separuh tertulis tidak boleh menjatuhkan seluruh ekspor."""
    from hero.kb.export import export

    with Catalog(tmp_path / "c.db") as cat:
        rec = record("f" * 64)
        cat.upsert_document(rec)
        _simpan_analisa_v2(cat, rec.doc_id, {"poin": []})
        cat.conn.execute("UPDATE analysis_v2 SET hasil = '{rusak' WHERE doc_id = ?",
                         (rec.doc_id,))
        cat.conn.commit()
        counts = export(cat, tmp_path / "out", "csv")

    assert counts["analisa"] == 0
    assert counts["documents"] == 1
