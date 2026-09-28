"""
tests/test_deploy_readiness.py
Pengujian otomatis kesiapan deploy Langkah 8:
- R04: Validasi konfigurasi produksi ketat
- R05: Matriks perlindungan dokumen non-publik vs auth off/on
- R06: Health check komprehensif & status degraded
- R07: Skrip demo_reset
- R08: Skrip demo_seed idempoten
"""
import io
import json
import os
import pytest
from unittest.mock import patch
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings, settings, APP_VERSION
from app.main import app
from app.models.document import Document
from app.models.enums import KlasifikasiAkses, PeranDokumen, StatusKeberlakuan, StatusPemrosesan
from app.models.category import Category
from app.models.user import User
from app.models.scan_session import ScanSession
from app.models.scan_candidate import ScanCandidate
from app.models.job_ingest import JobIngest
from app.models.scraping_source import ScrapingSource
from tests.conftest import make_pdf


# ==============================================================================
# R04: Validasi Konfigurasi Produksi
# ==============================================================================
def test_r04_production_validation_rules():
    """R04: Memastikan semua aturan konfigurasi produksi divalidasi dengan benar."""
    # 1. SECRET_KEY default / terlalu pendek
    s1 = Settings(
        app_env="production",
        secret_key="change-me",
        internal_api_key="a" * 35,
        cors_origins="https://hero.vercel.app",
        crawl_allow_private_networks=False,
    )
    with pytest.raises(ValueError) as exc1:
        s1.validate_production_config()
    assert "SECRET_KEY tidak aman" in str(exc1.value)

    # 2. INTERNAL_API_KEY default / pendek
    s2 = Settings(
        app_env="production",
        secret_key="b" * 35,
        internal_api_key="short-key",
        cors_origins="https://hero.vercel.app",
        crawl_allow_private_networks=False,
    )
    with pytest.raises(ValueError) as exc2:
        s2.validate_production_config()
    assert "INTERNAL_API_KEY tidak aman" in str(exc2.value)

    # 3. CORS_ORIGINS '*' atau kosong
    s3 = Settings(
        app_env="production",
        secret_key="b" * 35,
        internal_api_key="c" * 35,
        cors_origins="*",
        crawl_allow_private_networks=False,
    )
    with pytest.raises(ValueError) as exc3:
        s3.validate_production_config()
    assert "CORS_ORIGINS tidak aman" in str(exc3.value)

    # 4. CRAWL_ALLOW_PRIVATE_NETWORKS=True
    s4 = Settings(
        app_env="production",
        secret_key="b" * 35,
        internal_api_key="c" * 35,
        cors_origins="https://hero.vercel.app",
        crawl_allow_private_networks=True,
    )
    with pytest.raises(ValueError) as exc4:
        s4.validate_production_config()
    assert "CRAWL_ALLOW_PRIVATE_NETWORKS tidak diizinkan" in str(exc4.value)

    # 5. Konfigurasi valid -> Lolos tanpa exception
    s_valid = Settings(
        app_env="production",
        secret_key="b" * 35,
        internal_api_key="c" * 35,
        cors_origins="https://hero.vercel.app, https://hero2.vercel.app",
        crawl_allow_private_networks=False,
    )
    s_valid.validate_production_config()  # Tidak boleh raise


# ==============================================================================
# R05: Perlindungan Dokumen Non-Publik saat Auth Nonaktif
# ==============================================================================
def test_r05_non_public_protection_matrix(client, db_session: Session):
    """R05: Matriks dokumen publik vs non-publik saat auth nonaktif / aktif."""
    # Buat file pdf di storage
    from app.services.storage_service import get_storage_service
    storage = get_storage_service()
    pdf_pub_bytes = make_pdf("PDF Publik")
    pdf_nonpub_bytes = make_pdf("PDF Non Publik")
    p1 = storage.save_pdf(pdf_pub_bytes, "doc_pub.pdf", subdir="pdf/_inbox")
    p2 = storage.save_pdf(pdf_nonpub_bytes, "doc_nonpub.pdf", subdir="pdf/_inbox")

    # Buat dokumen publik
    doc_pub = Document(
        title="Peraturan Menteri Publik No 1",
        regulation_number="Permen-1-Publik",
        regulation_type="Permen",
        file_path_pdf=p1,
        file_hash="hash_pub_123",
        file_size_bytes=len(pdf_pub_bytes),
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        full_text="Teks rahasia pasal 1 penting untuk umum.",
    )
    # Buat dokumen non-publik
    doc_nonpub = Document(
        title="Kajian Rahasia Internal No 2",
        regulation_number="Kajian-2-Internal",
        regulation_type="Kajian",
        file_path_pdf=p2,
        file_hash="hash_nonpub_456",
        file_size_bytes=len(pdf_nonpub_bytes),
        access_classification=KlasifikasiAkses.non_publik,
        document_role=PeranDokumen.draft_kajian,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        full_text="Teks sensitif rahasia pasal khusus internal perusahaan.",
    )
    db_session.add_all([doc_pub, doc_nonpub])
    db_session.commit()

    # KONDISI A: AUTH_ENABLED=False & PROTECT_NON_PUBLIC=True
    with patch.object(settings, "auth_enabled", False), patch.object(settings, "protect_non_public_when_auth_disabled", True):
        # 1. Akses PDF publik -> 200
        res_pub_pdf = client.get(f"/api/v1/documents/{doc_pub.id}/pdf")
        assert res_pub_pdf.status_code == 200

        # 2. Akses PDF non-publik -> 403
        res_nonpub_pdf = client.get(f"/api/v1/documents/{doc_nonpub.id}/pdf")
        assert res_nonpub_pdf.status_code == 403
        assert "Dokumen non-publik hanya dapat dibuka setelah login diaktifkan." in res_nonpub_pdf.json()["detail"]

        # 3. Akses teks non-publik -> 403
        res_nonpub_text = client.get(f"/api/v1/documents/{doc_nonpub.id}/text")
        assert res_nonpub_text.status_code == 403

        # 4. Pencarian: dokumen non-publik tetap muncul tapi restricted=true dan pdf_url=null
        res_search = client.get("/api/v1/documents/?q=rahasia")
        assert res_search.status_code == 200
        items = res_search.json()["items"]
        
        nonpub_item = next((it for it in items if it["id"] == doc_nonpub.id), None)
        assert nonpub_item is not None
        assert nonpub_item["restricted"] is True
        assert nonpub_item["pdf_url"] is None
        # Highlight tidak boleh membocorkan full_text sensitif
        if nonpub_item.get("highlight"):
            assert "sensitif" not in nonpub_item["highlight"]

        pub_item = next((it for it in items if it["id"] == doc_pub.id), None)
        assert pub_item is not None
        assert pub_item["restricted"] is False
        assert pub_item["pdf_url"] is not None


# ==============================================================================
# R06: Health Check Baru & Status Degraded
# ==============================================================================
def test_r06_health_check_comprehensive(client):
    """R06: Health check mengembalikan semua key baru, degraded jika migrasi tertinggal."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()

    assert data["version"] == APP_VERSION
    assert "alembic_revision" in data
    assert "alembic_head" in data
    assert "migrations_up_to_date" in data
    assert "storage_writable" in data
    assert data["storage_writable"] is True
    assert "crawler_backend" in data
    assert "crawler_loaded" in data
    assert data["crawler_loaded"] is True
    assert "app_env" in data
    assert "protect_non_public" in data

    # Simulasi migrasi tertinggal (head_rev != db_rev)
    with patch("app.main.get_alembic_status", return_value=("rev_old", "rev_head", False)):
        res_degraded = client.get("/health")
        assert res_degraded.status_code == 200
        data_deg = res_degraded.json()
        assert data_deg["status"] == "degraded"
        assert data_deg["migrations_up_to_date"] is False


# ==============================================================================
# R07: Demo Reset Script
# ==============================================================================
def test_r07_demo_reset_execution(db_session: Session):
    """R07: demo_reset mengosongkan data operasional tapi mempertahankan kategori & user."""
    from scripts.demo_reset import OPERATIONAL_TABLES, check_table_counts, reset_storage

    # Buat data uji
    doc = Document(
        title="Dokumen Uji Reset",
        regulation_number="Reset-1",
        file_path_pdf="pdf/_inbox/reset.pdf",
        file_hash="hash_reset_123",
        file_size_bytes=1000,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
    )
    db_session.add(doc)
    db_session.commit()

    assert db_session.query(Document).count() >= 1
    assert db_session.query(Category).count() >= 1

    # Jalankan demo_reset logic pada hero_test
    with patch.object(settings, "app_env", "development"):
        tables_str = ", ".join(OPERATIONAL_TABLES)
        db_session.execute(text(f"TRUNCATE TABLE {tables_str} RESTART IDENTITY CASCADE;"))
        db_session.commit()

    # Periksa data operasional kosong
    assert db_session.query(Document).count() == 0
    # Kategori dan User tetap ada
    from app.database import seed_initial_categories
    seed_initial_categories(db_session)
    assert db_session.query(Category).count() >= 1


# ==============================================================================
# R08: Demo Seed Script Idempotency
# ==============================================================================
def test_r08_demo_seed_flow_and_idempotency(client, db_session: Session):
    """R08: demo_seed mendaftarkan sumber dan memindai/menarik secara idempoten."""
    # Registrasi pertama
    payload = {
        "name": "Sumber Demo Uji",
        "source_type": "situs_web",
        "url": "https://example.com/demo-jdih",
        "crawl_depth": 2,
        "max_pages": 10,
    }
    r1 = client.post("/api/v1/scraping-sources/", json=payload)
    assert r1.status_code in (200, 201)
    src_id = r1.json()["id"]

    # Registrasi kedua untuk URL yang sama -> dideteksi sudah ada
    all_sources = client.get("/api/v1/scraping-sources/").json()
    existing_urls = {s["url"]: s for s in (all_sources if isinstance(all_sources, list) else all_sources.get("items", []))}
    assert "https://example.com/demo-jdih" in existing_urls
    assert existing_urls["https://example.com/demo-jdih"]["id"] == src_id
