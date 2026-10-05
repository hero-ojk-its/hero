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


# Nama-nama kategori default root yang akan di-seed (7 root KB skeleton)
_DEFAULT_CATEGORIES = [
    "POJK",
    "SEOJK",
    "UU",
    "PP",
    "Peraturan Internal DPEA",
    "Lainnya",
    "Draft Kajian",
]


def seed_initial_categories(db) -> None:
    """
    Seeder kategori Knowledge Base.
    Idempoten per nama root: memastikan 7 root folder KB selalu ada.
    """
    from app.models.category import Category  # noqa: PLC0415

    created_names = []
    for name in _DEFAULT_CATEGORIES:
        existing = db.query(Category).filter(
            Category.parent_id.is_(None),
            Category.name == name,
        ).first()
        if not existing:
            cat = Category(name=name, parent_id=None, auto_created=False)
            db.add(cat)
            created_names.append(name)

    if created_names:
        db.commit()
        logger.info("Seeder: %d kategori root baru berhasil di-insert -> %s", len(created_names), created_names)
    else:
        logger.info("Seeder: seluruh %d kategori root sudah lengkap.", len(_DEFAULT_CATEGORIES))