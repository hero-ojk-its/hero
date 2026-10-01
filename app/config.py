from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.10.0"


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
    app_version: str = APP_VERSION
    secret_key: str = "change-me"
    internal_api_key: str = "change-me-internal-key"
    auth_enabled: bool = False
    cors_origins: str = "*"
    access_token_expire_hours: int = 8
    expose_api_docs: bool = True
    protect_non_public_when_auth_disabled: bool = True
    uvicorn_workers: int = 1
    forwarded_allow_ips: str = "127.0.0.1"

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

    # Alur Pindai Situs / Web Crawler (Langkah 7)
    crawler_backend: str = "simple_http"  # simple_http | external_module | push
    crawler_module: str = ""  # paket.modul:NamaKelas jika external_module
    crawl_max_pages: int = 200
    crawl_max_candidates: int = 5000
    crawl_delay_seconds: float = 0.5
    crawl_timeout_seconds: int = 20
    crawl_user_agent: str = "HERO-Capstone-Crawler/0.7 (+kontak: tim HERO)"
    crawl_respect_robots: bool = True
    crawl_allow_private_networks: bool = False
    crawl_head_for_size: bool = True
    scan_stuck_minutes: int = 60

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
        allowed = {"nomor", "judul", "nama", "tahun", "jenis", "bidang"}
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

    def validate_production_config(self) -> None:
        """Validasi konfigurasi produksi yang ketat saat APP_ENV=production."""
        if self.app_env.lower() == "production":
            errors = []
            default_secret_prefixes = ("change-me", "ganti-dengan", "secret", "default", "password", "hero")
            if any(self.secret_key.lower().startswith(p) for p in default_secret_prefixes) or len(self.secret_key) < 32:
                errors.append(
                    "SECRET_KEY tidak aman untuk production: tidak boleh nilai default dan minimal 32 karakter."
                )

            default_internal_prefixes = ("change-me", "ganti-dengan", "secret", "default", "password", "hero")
            if any(self.internal_api_key.lower().startswith(p) for p in default_internal_prefixes) or len(self.internal_api_key) < 32:
                errors.append(
                    "INTERNAL_API_KEY tidak aman untuk production: tidak boleh nilai default dan minimal 32 karakter."
                )

            raw_cors = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
            if not raw_cors or "*" in raw_cors:
                errors.append(
                    "CORS_ORIGINS tidak aman untuk production: tidak boleh bernilai '*' atau kosong."
                )

            if self.crawl_allow_private_networks:
                errors.append(
                    "CRAWL_ALLOW_PRIVATE_NETWORKS tidak diizinkan pada production (risiko SSRF/keamanan jaringan internal)."
                )

            if errors:
                error_msg = (
                    "Gagal memulai aplikasi dalam mode produksi karena konfigurasi tidak valid:\n"
                    + "\n".join(f"  - {e}" for e in errors)
                )
                raise ValueError(error_msg)

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()