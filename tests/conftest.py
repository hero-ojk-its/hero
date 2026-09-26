import os
import pytest
from pathlib import Path
from typing import Generator
import bcrypt
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient
import alembic.config
import alembic.command

from app.config import settings
from app.database import get_db, seed_initial_categories
from app.main import app
from app.models.user import User
from app.services.storage_service import StorageService, get_storage_service

# Test Database URL (menggunakan 127.0.0.1 untuk koneksi instan di Windows tanpa timeout IPv6)
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://hero_user:hero_password@127.0.0.1:5432/hero_test"
)

test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def make_pdf(text_content: str) -> bytes:
    """Helper untuk membuat konten berkas PDF minimal yang valid dengan isi unik."""
    content_bytes = text_content.encode("utf-8")
    length = len(content_bytes)
    pdf_template = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(length).encode("ascii") + b" >>\nstream\n"
        + content_bytes +
        b"\nendstream\nendobj\n"
        b"xref\n0 5\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000206 00000 n \n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\n"
        b"startxref\n300\n%%EOF\n"
    )
    return pdf_template


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Jalankan migrasi alembic pada database hero_test sebelum suite test dimulai."""
    # Pastikan database test bersih dan migrasi berjalan
    with test_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()

    alembic_cfg = alembic.config.Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    alembic.command.upgrade(alembic_cfg, "head")
    yield


@pytest.fixture(autouse=True)
def bind_test_session_local(monkeypatch):
    """Pastikan SessionLocal yang dibuat oleh background task/service selalu memakai test database."""
    monkeypatch.setattr("app.database.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("app.services.source_runner.SessionLocal", TestingSessionLocal)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Truncate seluruh tabel data, seed kategori, dan sediakan session DB baru untuk tiap test."""
    db = TestingSessionLocal()
    try:
        # Truncate semua tabel yang relevan dengan RESTART IDENTITY CASCADE
        db.execute(text("""
            TRUNCATE TABLE 
                article_references,
                legal_references,
                articles,
                documents,
                ingest_failures,
                source_files,
                job_ingest,
                scraping_sources,
                audit_logs,
                users,
                categories
            RESTART IDENTITY CASCADE;
        """))
        db.commit()

        # Seed 5 kategori awal
        seed_initial_categories(db)
        yield db
    finally:
        db.close()


@pytest.fixture
def test_storage(tmp_path: Path) -> StorageService:
    """Sediakan StorageService yang terisolasi di direktori temporer."""
    storage_dir = tmp_path / "test_storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return StorageService(base_path=storage_dir)


@pytest.fixture
def client(db_session: Session, test_storage: StorageService, monkeypatch) -> Generator[TestClient, None, None]:
    """TestClient dengan override dependency DB dan Storage."""
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "storage_path", str(test_storage.base_path))

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_storage_service():
        return test_storage

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_service] = override_get_storage_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def auth_client(db_session: Session, test_storage: StorageService, monkeypatch) -> Generator[TestClient, None, None]:
    """TestClient dengan AUTH_ENABLED=True."""
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "storage_path", str(test_storage.base_path))

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_storage_service():
        return test_storage

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_service] = override_get_storage_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def seed_admin_user(db_session: Session) -> User:
    """Membuat user admin di database test."""
    safe_password = "adminpassword123"[:72].encode("utf-8")
    hashed_pw = bcrypt.hashpw(safe_password, bcrypt.gensalt()).decode("utf-8")

    admin = User(
        username="admin_test",
        hashed_password=hashed_pw,
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin
