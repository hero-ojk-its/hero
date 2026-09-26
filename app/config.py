from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Konfigurasi aplikasi dari environment variables / .env"""

    # Database
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
    auth_enabled: bool = False
    cors_origins: str = "*"
    access_token_expire_hours: int = 8

    # Storage & Upload
    storage_path: str = "./storage"
    max_upload_mb: int = 100

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()