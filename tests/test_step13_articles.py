"""
tests/test_step13_articles.py
Pengujian Kontrak Pasal untuk Lapisan Data (Langkah 13).
Kasus uji P01 s.d. P10 sesuai spesifikasi.
"""
import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient
import alembic.config
import alembic.command

from app.config import settings
from app.main import app
from app.models.document import Document
from app.models.article import Article
from app.models.enums import KlasifikasiAkses, PeranDokumen, StatusKeberlakuan, StatusPemrosesan
from tests.conftest import TEST_DATABASE_URL

INTERNAL_HEADERS = {"X-Internal-API-Key": settings.internal_api_key}


@pytest.fixture
def sample_doc(db_session):
    """Fixture membuat dokumen contoh untuk pengujian artikel."""
    doc = Document(
        title="POJK Pengujian Kontrak Pasal",
        regulation_number="POJK 13/POJK.03/2026",
        file_path_pdf="pdf/_inbox/test_step13.pdf",
        file_hash="hash_step13_test",
        file_size_bytes=2048,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.diterima,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def test_p01_duplicate_order_upsert(client: TestClient, sample_doc: Document, db_session):
    """
    P01: Kirim 3 pasal (order 0–2) dua kali.
    Ekspektasi: Total tetap 3; respons kedua updated_count = 3 (dan inserted_count = 0).
    """
    articles_payload = [
        {
            "document_id": sample_doc.id,
            "level": "pasal",
            "chapter_title": "BAB I KETENTUAN UMUM",
            "article_number": f"Pasal {i + 1}",
            "content_text": f"Teks awal pasal {i + 1}",
            "order_index": i,
        }
        for i in range(3)
    ]

    # Kiriman pertama
    resp1 = client.post(
        "/api/v1/internal/articles",
        headers=INTERNAL_HEADERS,
        json={"articles": articles_payload},
    )
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()
    assert data1["inserted_count"] == 3
    assert data1["updated_count"] == 0

    count_after_1 = db_session.query(Article).filter(Article.document_id == sample_doc.id).count()
    assert count_after_1 == 3

    # Kiriman kedua dengan teks diperbarui
    articles_payload_update = [
        {
            "document_id": sample_doc.id,
            "level": "pasal",
            "chapter_title": "BAB I KETENTUAN UMUM",
            "article_number": f"Pasal {i + 1}",
            "content_text": f"Teks revisi pasal {i + 1}",
            "order_index": i,
        }
        for i in range(3)
    ]
    resp2 = client.post(
        "/api/v1/internal/articles",
        headers=INTERNAL_HEADERS,
        json={"articles": articles_payload_update},
    )
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["inserted_count"] == 0
    assert data2["updated_count"] == 3

    # Total di database tetap 3, teks terbukti diperbarui
    db_session.expire_all()
    articles_db = (
        db_session.query(Article)
        .filter(Article.document_id == sample_doc.id)
        .order_by(Article.order_index)
        .all()
    )
    assert len(articles_db) == 3
    for i, a in enumerate(articles_db):
        assert a.content_text == f"Teks revisi pasal {i + 1}"


def test_p02_multi_batch_sequential(client: TestClient, sample_doc: Document, db_session):
    """
    P02: Satu dokumen 320 pasal dikirim 3 request (150/150/20).
    Ekspektasi: Total 320; tidak ada yang terhapus antar-request.
    """
    # Batch 1: order 0..149 (150 items)
    b1 = [
        {
            "document_id": sample_doc.id,
            "level": "pasal",
            "article_number": f"Pasal {i}",
            "content_text": f"Isi pasal {i}",
            "order_index": i,
        }
        for i in range(150)
    ]
    resp1 = client.post(
        "/api/v1/internal/articles",
        headers=INTERNAL_HEADERS,
        json={"articles": b1},
    )
    assert resp1.status_code == 200
    assert resp1.json()["inserted_count"] == 150

    # Batch 2: order 150..299 (150 items)
    b2 = [
        {
            "document_id": sample_doc.id,
            "level": "pasal",
            "article_number": f"Pasal {i}",
            "content_text": f"Isi pasal {i}",
            "order_index": i,
        }
        for i in range(150, 300)
    ]
    resp2 = client.post(
        "/api/v1/internal/articles",
        headers=INTERNAL_HEADERS,
        json={"articles": b2},
    )
    assert resp2.status_code == 200
    assert resp2.json()["inserted_count"] == 150

    # Batch 3: order 300..319 (20 items)
    b3 = [
        {
            "document_id": sample_doc.id,
            "level": "pasal",
            "article_number": f"Pasal {i}",
            "content_text": f"Isi pasal {i}",
            "order_index": i,
        }
        for i in range(300, 320)
    ]
    resp3 = client.post(
        "/api/v1/internal/articles",
        headers=INTERNAL_HEADERS,
        json={"articles": b3},
    )
    assert resp3.status_code == 200
    assert resp3.json()["inserted_count"] == 20

    total = db_session.query(Article).filter(Article.document_id == sample_doc.id).count()
    assert total == 320


def test_p03_replace_document_ids(client: TestClient, sample_doc: Document, db_session):
    """
    P03: Kirim ulang 320 lalu 300 dengan replace_document_ids=[id] di request pertama.
    Ekspektasi: Total 300; deleted_count = 320.
    """
    # Masukkan 320 pasal awal
    initial_articles = [
        {
            "document_id": sample_doc.id,
            "level": "pasal",
            "article_number": f"Pasal {i}",
            "content_text": f"Isi lama {i}",
            "order_index": i,
        }
        for i in range(320)
    ]
    r_init1 = client.post(
        "/api/v1/internal/articles",
        headers=INTERNAL_HEADERS,
        json={"articles": initial_articles[:150]},
    )
    r_init2 = client.post(
        "/api/v1/internal/articles",
        headers=INTERNAL_HEADERS,
        json={"articles": initial_articles[150:300]},
    )
    r_init3 = client.post(
        "/api/v1/internal/articles",
        headers=INTERNAL_HEADERS,
        json={"articles": initial_articles[300:]},
    )
    assert r_init1.status_code == 200 and r_init2.status_code == 200 and r_init3.status_code == 200
    assert db_session.query(Article).filter(Article.document_id == sample_doc.id).count() == 320

    # Kirim ulang: request 1 (150 pasal) dengan replace_document_ids=[sample_doc.id]
    new_articles_p1 = [
        {
            "document_id": sample_doc.id,
            "level": "pasal",
            "article_number": f"Pasal Baru {i}",
            "content_text": f"Isi baru {i}",
            "order_index": i,
        }
        for i in range(150)
    ]
    resp_rep1 = client.post(
        "/api/v1/internal/articles",
        headers=INTERNAL_HEADERS,
        json={
            "articles": new_articles_p1,
            "replace_document_ids": [sample_doc.id],
        },
    )
    assert resp_rep1.status_code == 200
    data_rep1 = resp_rep1.json()
    assert data_rep1["deleted_count"] == 320
    assert data_rep1["inserted_count"] == 150

    # Request 2 (150 pasal lagi sehingga total 300) tanpa replace_document_ids
    new_articles_p2 = [
        {
            "document_id": sample_doc.id,
            "level": "pasal",
            "article_number": f"Pasal Baru {i}",
            "content_text": f"Isi baru {i}",
            "order_index": i,
        }
        for i in range(150, 300)
    ]
    resp_rep2 = client.post(
        "/api/v1/internal/articles",
        headers=INTERNAL_HEADERS,
        json={"articles": new_articles_p2},
    )
    assert resp_rep2.status_code == 200
    assert resp_rep2.json()["inserted_count"] == 150

    # Total akhir tepat 300 (sisa 20 pasal lama 300..319 bersih terbuang)
    total_after = db_session.query(Article).filter(Article.document_id == sample_doc.id).count()
    assert total_after == 300


def test_p04_page_stored_and_displayed(client: TestClient, sample_doc: Document, db_session):
    """
    P04: page terisi.
    Ekspektasi: Tersimpan dan tampil di GET /documents/{id}.
    """
    payload = {
        "articles": [
            {
                "document_id": sample_doc.id,
                "level": "pasal",
                "chapter_title": "BAB I",
                "article_number": "Pasal 1",
                "content_text": "Ketentuan umum dengan nomor halaman",
                "order_index": 0,
                "page": 7,
            }
        ]
    }
    resp = client.post(
        "/api/v1/internal/articles",
        headers=INTERNAL_HEADERS,
        json=payload,
    )
    assert resp.status_code == 200

    # Periksa di database
    art = db_session.query(Article).filter(Article.document_id == sample_doc.id, Article.order_index == 0).first()
    assert art is not None
    assert art.page == 7

    # Periksa GET /api/v1/documents/{id}
    resp_doc = client.get(f"/api/v1/documents/{sample_doc.id}")
    assert resp_doc.status_code == 200
    doc_data = resp_doc.json()
    assert "articles" in doc_data
    assert len(doc_data["articles"]) > 0
    assert doc_data["articles"][0]["page"] == 7


def test_p05_parent_order_index_previous_request(client: TestClient, sample_doc: Document, db_session):
    """
    P05: Ayat dengan parent_order_index pasal di request sebelumnya.
    Ekspektasi: parent_id menunjuk pasal yang benar.
    """
    # Request 1: Pasal induk (order_index = 0)
    p_req1 = {
        "articles": [
            {
                "document_id": sample_doc.id,
                "level": "pasal",
                "article_number": "Pasal 5",
                "content_text": "Pasal lima mengatur tentang hal penting.",
                "order_index": 0,
            }
        ]
    }
    r1 = client.post("/api/v1/internal/articles", headers=INTERNAL_HEADERS, json=p_req1)
    assert r1.status_code == 200

    parent_art = db_session.query(Article).filter(Article.document_id == sample_doc.id, Article.order_index == 0).first()
    assert parent_art is not None

    # Request 2: Ayat anak (order_index = 1, parent_order_index = 0)
    p_req2 = {
        "articles": [
            {
                "document_id": sample_doc.id,
                "level": "ayat",
                "article_number": "Ayat (1)",
                "content_text": "Ayat satu rincian ketentuan pasal lima.",
                "order_index": 1,
                "parent_order_index": 0,
            }
        ]
    }
    r2 = client.post("/api/v1/internal/articles", headers=INTERNAL_HEADERS, json=p_req2)
    assert r2.status_code == 200

    db_session.expire_all()
    child_art = db_session.query(Article).filter(Article.document_id == sample_doc.id, Article.order_index == 1).first()
    assert child_art is not None
    assert child_art.parent_id == parent_art.id


def test_p06_nonexistent_parent_order_index(client: TestClient, sample_doc: Document, db_session):
    """
    P06: parent_order_index yang tidak ada.
    Ekspektasi: 422, tidak ada baris tersimpan.
    """
    payload = {
        "articles": [
            {
                "document_id": sample_doc.id,
                "level": "ayat",
                "article_number": "Ayat (1)",
                "content_text": "Ayat menggantung tanpa induk",
                "order_index": 5,
                "parent_order_index": 9999,
            }
        ]
    }
    resp = client.post("/api/v1/internal/articles", headers=INTERNAL_HEADERS, json=payload)
    assert resp.status_code == 422
    err_detail = resp.json()["detail"]
    assert str(sample_doc.id) in err_detail or "document_id" in err_detail
    assert "9999" in err_detail

    # Tidak ada baris yang tersimpan
    count = db_session.query(Article).filter(Article.document_id == sample_doc.id).count()
    assert count == 0


def test_p07_unknown_document_id(client: TestClient):
    """
    P07: document_id tidak dikenal.
    Ekspektasi: 422 berisi daftar id.
    """
    payload = {
        "articles": [
            {
                "document_id": 888888,
                "level": "pasal",
                "article_number": "Pasal 1",
                "content_text": "Isi",
                "order_index": 0,
            },
            {
                "document_id": 999999,
                "level": "pasal",
                "article_number": "Pasal 2",
                "content_text": "Isi",
                "order_index": 1,
            },
        ]
    }
    resp = client.post("/api/v1/internal/articles", headers=INTERNAL_HEADERS, json=payload)
    assert resp.status_code == 422
    err_detail = str(resp.json()["detail"])
    assert "888888" in err_detail and "999999" in err_detail


def test_p08_null_embedding_on_resend(client: TestClient, sample_doc: Document, db_session):
    """
    P08: Embedding null pada kiriman ulang.
    Ekspektasi: Embedding lama tidak tertimpa null.
    """
    dummy_vec = [0.05] * 1536
    payload_1 = {
        "articles": [
            {
                "document_id": sample_doc.id,
                "level": "pasal",
                "article_number": "Pasal 1",
                "content_text": "Teks bervektor",
                "order_index": 0,
                "embedding": dummy_vec,
            }
        ]
    }
    r1 = client.post("/api/v1/internal/articles", headers=INTERNAL_HEADERS, json=payload_1)
    assert r1.status_code == 200

    art_db1 = db_session.query(Article).filter(Article.document_id == sample_doc.id, Article.order_index == 0).first()
    assert art_db1 is not None
    assert art_db1.embedding is not None

    # Kiriman kedua: embedding None
    payload_2 = {
        "articles": [
            {
                "document_id": sample_doc.id,
                "level": "pasal",
                "article_number": "Pasal 1",
                "content_text": "Teks teks revisi tanpa embedding",
                "order_index": 0,
                "embedding": None,
            }
        ]
    }
    r2 = client.post("/api/v1/internal/articles", headers=INTERNAL_HEADERS, json=payload_2)
    assert r2.status_code == 200

    db_session.expire_all()
    art_db2 = db_session.query(Article).filter(Article.document_id == sample_doc.id, Article.order_index == 0).first()
    assert art_db2 is not None
    assert art_db2.content_text == "Teks teks revisi tanpa embedding"
    # Embedding tetap ada dan tidak tertimpa NULL
    assert art_db2.embedding is not None


def test_p09_migration_cleans_duplicates_and_creates_index(sample_doc: Document):
    """
    P09: Migrasi pada DB yang sudah berisi duplikat.
    Ekspektasi: Duplikat dibersihkan, index terpasang.
    """
    alembic_cfg = alembic.config.Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    # 1. Downgrade ke revisi sebelum Step 13
    alembic.command.downgrade(alembic_cfg, "d4e5f6a7b8c9")

    # 2. Sisipkan data duplikat (document_id, order_index)
    from tests.conftest import TestingSessionLocal
    s = TestingSessionLocal()
    try:
        # Masukkan 2 baris dengan order_index = 0 yang sama untuk sample_doc
        s.execute(text("""
            INSERT INTO articles (document_id, article_number, content_text, level, order_index)
            VALUES 
                (:doc_id, 'Pasal 1 Asli', 'Konten id kecil', 'pasal', 0),
                (:doc_id, 'Pasal 1 Duplikat', 'Konten id besar', 'pasal', 0);
        """), {"doc_id": sample_doc.id})
        s.commit()

        # Pastikan ada 2 baris sebelum migrasi upgrade
        count_pre = s.execute(text(
            "SELECT count(*) FROM articles WHERE document_id = :doc_id AND order_index = 0"
        ), {"doc_id": sample_doc.id}).scalar()
        assert count_pre == 2
    finally:
        s.close()

    # 3. Jalankan upgrade ke head (e5f6a7b8c9d0)
    alembic.command.upgrade(alembic_cfg, "head")

    # 4. Verifikasi hasil pembersihan
    s = TestingSessionLocal()
    try:
        rows = s.execute(text("""
            SELECT id, article_number, content_text 
            FROM articles 
            WHERE document_id = :doc_id AND order_index = 0
            ORDER BY id ASC
        """), {"doc_id": sample_doc.id}).fetchall()

        # Hanya tersisa tepat 1 baris
        assert len(rows) == 1
        # Baris yang tersimpan adalah baris dengan id terkecil ('Pasal 1 Asli')
        assert rows[0][1] == "Pasal 1 Asli"

        # Verifikasi bahwa index uq_articles_document_order terpasang di postgres
        idx_check = s.execute(text("""
            SELECT indexname FROM pg_indexes 
            WHERE tablename = 'articles' AND indexname = 'uq_articles_document_order';
        """)).scalar()
        assert idx_check == "uq_articles_document_order"

        # Verifikasi bahwa mencoba insert duplikat sekarang ditolak oleh database constraint
        dup_failed = False
        try:
            s.execute(text("""
                INSERT INTO articles (document_id, article_number, content_text, level, order_index)
                VALUES (:doc_id, 'Pasal 1 Lagi', 'Gagal', 'pasal', 0);
            """), {"doc_id": sample_doc.id})
            s.commit()
        except Exception:
            s.rollback()
            dup_failed = True
        assert dup_failed is True
    finally:
        s.close()


def test_p10_legacy_payload_compatibility(client: TestClient, sample_doc: Document, db_session):
    """
    P10: Payload lama persis seperti worker sekarang (tanpa field baru).
    Ekspektasi: Tetap diterima.
    """
    legacy_payload = {
        "articles": [
            {
                "document_id": sample_doc.id,
                "level": "pasal",
                "chapter_title": "BAB I",
                "article_number": "Pasal 1",
                "content_text": "Teks payload lama tanpa field page atau parent_order_index",
                "order_index": 0,
                "embedding": None,
            }
        ]
    }
    resp = client.post(
        "/api/v1/internal/articles",
        headers=INTERNAL_HEADERS,
        json=legacy_payload,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "ok"
    assert data["inserted_count"] == 1
    assert data["updated_count"] == 0
    assert data["deleted_count"] == 0

    art = db_session.query(Article).filter(Article.document_id == sample_doc.id, Article.order_index == 0).first()
    assert art is not None
    assert art.page is None
    assert art.parent_id is None
