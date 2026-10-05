from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Alembic Config object — akses nilai dari alembic.ini
# ---------------------------------------------------------------------------
config = context.config

# Setup logging dari alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import settings untuk membaca DATABASE_URL dari environment / .env
# ---------------------------------------------------------------------------
from app.config import settings  # noqa: E402

# Timpa sqlalchemy.url dengan nilai dinamis dari settings jika belum diset atau masih placeholder
current_url = config.get_main_option("sqlalchemy.url")
if not current_url or "driver://user:pass" in current_url:
    config.set_main_option("sqlalchemy.url", settings.database_url)

# ---------------------------------------------------------------------------
# Import Base dan semua model via app.models agar Alembic mendeteksi skema
# tabel secara otomatis saat --autogenerate dijalankan.
# ---------------------------------------------------------------------------
from app.database import Base  # noqa: E402
import app.models  # noqa: F401, E402

# Target metadata untuk autogenerate
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Fungsi migrasi offline (tanpa koneksi DB aktif)
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    URL database dibaca dari settings (sudah di-set via config.set_main_option
    di atas), bukan dari nilai statis di alembic.ini.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Render nama tipe kolom dengan benar untuk PostgreSQL + pgvector
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Fungsi migrasi online (dengan koneksi DB aktif)
# ---------------------------------------------------------------------------
def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Engine dibuat dari konfigurasi yang sudah memuat database_url dari
    settings, sehingga tidak diperlukan hardcode di alembic.ini.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Deteksi perubahan tipe kolom (misal: VARCHAR(50) → VARCHAR(100))
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
