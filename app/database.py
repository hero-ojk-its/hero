import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

logger = logging.getLogger("hero")

# SQLAlchemy engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # cek koneksi sebelum dipakai
    pool_size=10,
    max_overflow=20,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class untuk semua ORM model"""
    pass


def get_db():
    """Dependency injection: suplai session DB ke tiap request, lalu tutup setelah selesai"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Nama-nama kategori default yang akan di-seed saat tabel kosong
_DEFAULT_CATEGORIES = [
    "POJK",
    "SEOJK",
    "UU",
    "PP",
    "Peraturan Internal DPEA",
]


def seed_initial_categories(db) -> None:
    """
    Seeder kategori Knowledge Base.

    Dipanggil sekali saat startup aplikasi. Mengecek apakah tabel `categories`
    masih kosong; jika ya, insert 5 kategori default. Jika sudah ada isi,
    fungsi ini tidak melakukan apa-apa (idempotent).

    Args:
        db: SQLAlchemy Session — diambil langsung dari SessionLocal() di caller.
    """
    # Import di sini untuk menghindari circular import saat module di-load
    from app.models.category import Category  # noqa: PLC0415

    existing_count = db.query(Category).count()
    if existing_count > 0:
        logger.info("Seeder dilewati: tabel categories sudah berisi %d baris.", existing_count)
        return

    categories = [
        Category(name=name, auto_created=False)
        for name in _DEFAULT_CATEGORIES
    ]
    db.add_all(categories)
    db.commit()
    logger.info("Seeder: %d kategori default berhasil diinsert -> %s", len(categories), _DEFAULT_CATEGORIES)