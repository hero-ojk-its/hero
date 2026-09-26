"""
tests/test_search.py
Pengujian otomatis pencarian Knowledge Base (Langkah 4).
Menguji skenario S01 - S16 secara lengkap.
"""
from datetime import date
import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.models.document import Document
from app.models.category import Category
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
    MetodeEkstraksi,
)


@pytest.fixture
def seed_search_data(db_session):
    """Seed data pengujian pencarian."""
    # Ambil root categories yang sudah di-seed
    cat_root = db_session.query(Category).filter(Category.name == "POJK", Category.parent_id.is_(None)).first()
    if not cat_root:
        cat_root = Category(name="POJK", auto_created=True)
        db_session.add(cat_root)
        db_session.flush()

    cat_other = db_session.query(Category).filter(Category.name == "SEOJK", Category.parent_id.is_(None)).first()
    if not cat_other:
        cat_other = Category(name="SEOJK", auto_created=True)
        db_session.add(cat_other)
        db_session.flush()

    cat_sub = db_session.query(Category).filter(Category.name == "2022", Category.parent_id == cat_root.id).first()
    if not cat_sub:
        cat_sub = Category(name="2022", parent_id=cat_root.id, auto_created=True)
        db_session.add(cat_sub)
        db_session.flush()

    # Dokumen A: memuat frasa persis "sepatu roda"
    doc_a = Document(
        title="Regulasi Operasional Sepatu Roda",
        regulation_number="01/POJK.03/2022",
        regulation_type="POJK",
        release_date=date(2022, 5, 10),
        file_path_pdf="kb/POJK/2022/doc_a.pdf",
        file_hash="hash_search_01",
        file_size_bytes=1000,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        extraction_method=MetodeEkstraksi.teks_langsung,
        full_text="Ketentuan keselamatan penggunaan sepatu roda di lingkungan perkantoran perbankan.",
        category_id=cat_sub.id,
    )

    # Dokumen B: memuat kata "sepatu" dan "roda" terpisah jauh
    doc_b = Document(
        title="Pengadaan Alat Perlindungan Diri",
        regulation_number="02/POJK.03/2022",
        regulation_type="POJK",
        release_date=date(2022, 6, 15),
        file_path_pdf="kb/POJK/2022/doc_b.pdf",
        file_hash="hash_search_02",
        file_size_bytes=2000,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        extraction_method=MetodeEkstraksi.teks_langsung,
        full_text="Penyediaan sepatu keselamatan kerja wajib bagi staf. Bagian lain mengurus putaran roda keuangan industri.",
        category_id=cat_sub.id,
    )

    # Dokumen C: memuat kata "sepeda"
    doc_c = Document(
        title="Kendaraan Ramah Lingkungan Kantor",
        regulation_number="03/SEOJK.03/2021",
        regulation_type="SEOJK",
        release_date=date(2021, 3, 20),
        file_path_pdf="kb/SEOJK/2021/doc_c.pdf",
        file_hash="hash_search_03",
        file_size_bytes=3000,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.dicabut,
        processing_status=StatusPemrosesan.terindeks,
        extraction_method=MetodeEkstraksi.teks_langsung,
        full_text="Fasilitas parkir sepeda disediakan di setiap kantor cabang.",
        category_id=cat_other.id,
    )

    # Dokumen D: Nomor regulasi 11/POJK.03/2022
    doc_d = Document(
        title="Penyelenggaraan Produk Bank Umum",
        regulation_number="11/POJK.03/2022",
        regulation_type="POJK",
        release_date=date(2022, 11, 1),
        file_path_pdf="kb/POJK/2022/doc_d.pdf",
        file_hash="hash_search_04",
        file_size_bytes=4000,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.diubah,
        processing_status=StatusPemrosesan.terindeks,
        extraction_method=MetodeEkstraksi.teks_langsung,
        full_text="Peraturan OJK nomor sebelas tentang produk digital bank umum.",
        category_id=cat_sub.id,
    )

    db_session.add_all([doc_a, doc_b, doc_c, doc_d])
    db_session.commit()

    return {
        "cat_root_id": cat_root.id,
        "cat_sub_id": cat_sub.id,
        "cat_other_id": cat_other.id,
        "doc_a_id": doc_a.id,
        "doc_b_id": doc_b.id,
        "doc_c_id": doc_c.id,
        "doc_d_id": doc_d.id,
    }


def test_s01_phrase_search_default(client, seed_search_data):
    """S01: q=sepatu roda (mode default phrase) -> Hanya dokumen A yang cocok."""
    resp = client.get("/api/v1/documents/?q=sepatu roda")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == seed_search_data["doc_a_id"]


def test_s02_all_mode_search(client, seed_search_data):
    """S02: q=sepatu roda&mode=all -> Dokumen A dan B keduanya cocok."""
    resp = client.get("/api/v1/documents/?q=sepatu roda&mode=all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    matched_ids = {item["id"] for item in data["items"]}
    assert matched_ids == {seed_search_data["doc_a_id"], seed_search_data["doc_b_id"]}


def test_s03_web_mode_search(client, seed_search_data):
    """S03: q="sepatu roda" OR sepeda&mode=web -> Sesuai semantik websearch."""
    resp = client.get('/api/v1/documents/?q="sepatu roda" OR sepeda&mode=web')
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    matched_ids = {item["id"] for item in data["items"]}
    assert matched_ids == {seed_search_data["doc_a_id"], seed_search_data["doc_c_id"]}


def test_s04_regulation_number_in_q(client, seed_search_data):
    """S04: q=11/POJK.03/2022 -> Ditemukan dokumen D, peringkat teratas."""
    resp = client.get("/api/v1/documents/?q=11/POJK.03/2022")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["items"][0]["id"] == seed_search_data["doc_d_id"]


def test_s05_regulation_number_filter_normalized(client, seed_search_data):
    """S05: regulation_number=11-POJK.03-2022 -> Ditemukan (normalisasi tanda hubung / garis miring)."""
    resp = client.get("/api/v1/documents/?regulation_number=11-POJK.03-2022")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == seed_search_data["doc_d_id"]


def test_s06_status_keberlakuan_multi_filter(client, seed_search_data):
    """S06: Filter status_keberlakuan=dicabut&status_keberlakuan=diubah -> Hanya status tersebut."""
    resp = client.get("/api/v1/documents/?status_keberlakuan=dicabut&status_keberlakuan=diubah")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    statuses = {item["status_keberlakuan"] for item in data["items"]}
    assert statuses == {"dicabut", "diubah"}


def test_s07_revoked_document_appears_by_default(client, seed_search_data):
    """S07: Tanpa filter status, dokumen dicabut tetap ikut muncul."""
    resp = client.get("/api/v1/documents/?q=sepeda")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == seed_search_data["doc_c_id"]
    assert data["items"][0]["status_keberlakuan"] == "dicabut"


def test_s08_category_hierarchy_filter(client, seed_search_data):
    """S08: category_id=<root POJK> mencakup subkategori 2022 jika include_subcategories=true."""
    root_id = seed_search_data["cat_root_id"]
    resp_with_sub = client.get(f"/api/v1/documents/?category_id={root_id}&include_subcategories=true")
    assert resp_with_sub.status_code == 200
    data_with = resp_with_sub.json()
    # Dokumen A, B, D ada di subkategori 2022
    assert data_with["total"] == 3

    resp_no_sub = client.get(f"/api/v1/documents/?category_id={root_id}&include_subcategories=false")
    assert resp_no_sub.status_code == 200
    data_without = resp_no_sub.json()
    assert data_without["total"] == 0


def test_s09_date_range_validation(client, seed_search_data):
    """S09: date_from/date_to inklusif; date_from > date_to menghasilkan 422."""
    resp_ok = client.get("/api/v1/documents/?date_from=2022-01-01&date_to=2022-12-31")
    assert resp_ok.status_code == 200
    assert resp_ok.json()["total"] == 3

    resp_err = client.get("/api/v1/documents/?date_from=2023-01-01&date_to=2022-01-01")
    assert resp_err.status_code == 422


def test_s10_year_and_regulation_type_normalization(client, seed_search_data):
    """S10: year=2021 & regulation_type='se ojk' dinormalisasi menjadi SEOJK."""
    resp = client.get("/api/v1/documents/?year=2021&regulation_type=se ojk")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == seed_search_data["doc_c_id"]


def test_s11_q_whitespace_and_punctuation(client, seed_search_data):
    """S11: q=!!! menghasilkan total 0 (tsquery kosong), q='   ' mengembalikan semua dokumen."""
    resp_punct = client.get("/api/v1/documents/?q=!!!")
    assert resp_punct.status_code == 200
    assert resp_punct.json()["total"] == 0

    resp_spaces = client.get("/api/v1/documents/?q=   ")
    assert resp_spaces.status_code == 200
    assert resp_spaces.json()["total"] == 4


def test_s12_highlight_snippet(client, seed_search_data):
    """S12: highlight mengandung <mark>...</mark> untuk kata kunci yang cocok."""
    resp = client.get("/api/v1/documents/?q=sepatu roda")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["highlight"] is not None
    assert "<mark>" in item["highlight"]
    assert "</mark>" in item["highlight"]


def test_s13_sort_relevance_vs_release_date(client, seed_search_data):
    """S13: Pengurutan relevance vs release_date_desc."""
    resp_date = client.get("/api/v1/documents/?sort=release_date_desc")
    assert resp_date.status_code == 200
    items_date = resp_date.json()["items"]
    dates = [item["release_date"] for item in items_date]
    assert dates == sorted(dates, reverse=True)


def test_s14_legacy_compatibility(client, seed_search_data):
    """S14: Kompatibilitas query lama GET /documents/?access_classification=publik."""
    resp = client.get("/api/v1/documents/?access_classification=publik")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data
    assert "query" in data
    for item in data["items"]:
        assert item["access_classification"] == "publik"
        assert "pdf_url" in item
        assert "category_path" in item


def test_s15_limit_clamping(client, seed_search_data):
    """S15: limit=500 dibatasi otomatis ke 100."""
    resp = client.get("/api/v1/documents/?limit=500")
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"]["limit"] == 100


def test_s16_no_n_plus_one_sql_queries(client, seed_search_data, db_session):
    """S16: Jumlah query SQL per request pencarian <= 4 (tidak N+1)."""
    query_count = 0

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        resp = client.get("/api/v1/documents/?q=sepatu&include_subcategories=true")
        assert resp.status_code == 200
        assert query_count <= 4, f"Terlalu banyak query SQL: {query_count} (harus <= 4)"
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


def test_s17_regulation_number_normalization_search(client, db_session):
    """
    S17 (§1.1): Normalisasi nomor peraturan di pencarian (toleransi /, -, spasi).
    - Dokumen A: 11/POJK.03/2022
    - Dokumen B: 22-POJK.03-2022
    - Pencarian dengan '-' atau '/' atau spasi harus menemukan dokumen yang sesuai.
    """
    doc_slash = Document(
        title="Penyelenggaraan TI Bank Slash",
        regulation_number="11/POJK.03/2022",
        regulation_type="POJK",
        release_date=date(2022, 7, 7),
        file_path_pdf="kb/POJK/2022/doc_slash.pdf",
        file_hash="hash_s17_slash",
        file_size_bytes=1000,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        extraction_method=MetodeEkstraksi.teks_langsung,
        full_text="Ketentuan tata kelola teknologi informasi bank umum.",
    )
    doc_dash = Document(
        title="Penyelenggaraan TI Bank Dash",
        regulation_number="22-POJK.03-2022",
        regulation_type="POJK",
        release_date=date(2022, 8, 8),
        file_path_pdf="kb/POJK/2022/doc_dash.pdf",
        file_hash="hash_s17_dash",
        file_size_bytes=1000,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        extraction_method=MetodeEkstraksi.teks_langsung,
        full_text="Ketentuan pelaporan berkala teknologi informasi bank umum.",
    )
    db_session.add_all([doc_slash, doc_dash])
    db_session.commit()

    # 1. Cari nomor tersimpan ber-slash dengan input ber-dash: 11-POJK.03-2022
    resp_filter_dash = client.get("/api/v1/documents/?regulation_number=11-POJK.03-2022")
    assert resp_filter_dash.status_code == 200
    assert any(it["id"] == doc_slash.id for it in resp_filter_dash.json()["items"])

    # 2. Cari via q dengan input ber-dash: q=11-POJK.03-2022 -> harus peringkat 1
    resp_q_dash = client.get("/api/v1/documents/?q=11-POJK.03-2022")
    assert resp_q_dash.status_code == 200
    assert resp_q_dash.json()["items"][0]["id"] == doc_slash.id

    # 3. Kebalikannya: cari nomor tersimpan ber-dash (22-POJK.03-2022) dengan input ber-slash (22/POJK.03/2022)
    resp_filter_slash = client.get("/api/v1/documents/?regulation_number=22/POJK.03/2022")
    assert resp_filter_slash.status_code == 200
    assert any(it["id"] == doc_dash.id for it in resp_filter_slash.json()["items"])

    resp_q_slash = client.get("/api/v1/documents/?q=22/POJK.03/2022")
    assert resp_q_slash.status_code == 200
    assert resp_q_slash.json()["items"][0]["id"] == doc_dash.id

    # 4. Pencarian dengan spasi di sekitar pemisah: "11 / POJK.03 / 2022"
    resp_space_filter = client.get("/api/v1/documents/?regulation_number=11%20/%20POJK.03%20/%202022")
    assert resp_space_filter.status_code == 200
    assert any(it["id"] == doc_slash.id for it in resp_space_filter.json()["items"])

    resp_space_q = client.get("/api/v1/documents/?q=11%20/%20POJK.03%20/%202022")
    assert resp_space_q.status_code == 200
    assert resp_space_q.json()["items"][0]["id"] == doc_slash.id

