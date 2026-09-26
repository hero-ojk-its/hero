from pydantic import field_validator
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

    # Naming & Category Placement (Langkah 3)
    naming_template: str = "{nomor} {judul} {tahun}"
    naming_wildcard: str = "NA"
    naming_max_length: int = 150
    category_path_template: str = "{jenis}/{tahun}"
    category_unknown_type: str = "Lainnya"
    category_unknown_year: str = "Tanpa Tahun"
    draft_category_root: str = "Draft Kajian"

    # Ekstraksi Data/ML & Metadata (Langkah 5)
    metadata_confidence_threshold: float = 0.7
    extraction_claim_timeout_minutes: int = 30
    extraction_max_attempts: int = 3

    # Sumber Folder Lokal (Langkah 6)
    local_source_roots: str = "./sources"
    local_source_max_files_per_run: int = 5000
    job_progress_commit_every: int = 10

    @field_validator("category_path_template")
    @classmethod
    def validate_category_path_template(cls, v: str) -> str:
        import re
        placeholders = re.findall(r"\{([^}]+)\}", v)
        allowed = {"jenis", "tahun"}
        for p in placeholders:
            if p not in allowed:
                raise ValueError(
                    f"category_path_template memuat placeholder tidak dikenal: '{{{p}}}'. "
                    f"Placeholder yang diizinkan: {', '.join('{' + a + '}' for a in allowed)}."
                )
        return v

    @field_validator("naming_template")
    @classmethod
    def validate_naming_template(cls, v: str) -> str:
        import re
        placeholders = re.findall(r"\{([^}]+)\}", v)
        allowed = {"nomor", "judul", "tahun", "jenis"}
        for p in placeholders:
            if p not in allowed:
                raise ValueError(
                    f"naming_template memuat placeholder tidak dikenal: '{{{p}}}'. "
                    f"Placeholder yang diizinkan: {', '.join('{' + a + '}' for a in allowed)}."
                )
        return v

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()