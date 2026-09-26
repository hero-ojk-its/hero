# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Konfigurasi aplikasi dari environment variables / .env"""

    # Database (tambahkan +psycopg di sini)
    database_url: str = "postgresql+psycopg://hero_user:hero_password@db:5432/hero_db"
    postgres_user: str = "hero_user"
    postgres_password: str = "hero_password"
    postgres_db: str = "hero_db"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # App
    app_env: str = "development"
    app_port: int = 8000
    secret_key: str = "change-me"
    internal_api_key: str = "change-me-internal-key"

    # Storage
    storage_path: str = "/app/storage"

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()