"""
tests/test_category_service.py
Pengujian unit dan integrasi untuk category_service (Langkah 3: C01-C04).
"""
import pytest
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.category import Category
from app.services.category_service import CategoryService
from app.database import seed_initial_categories


def test_c01_resolve_or_create_path_idempotent(db_session: Session):
    """C01: resolve_or_create_path(['POJK', '2022']) dua kali -> id sama, jumlah baris tidak bertambah."""
    svc = CategoryService(db_session)
    count_before = db_session.query(Category).count()

    cat1 = svc.resolve_or_create_path(["POJK", "2022"])
    db_session.commit()
    count_after_first = db_session.query(Category).count()
    assert cat1 is not None
    assert cat1.name == "2022"

    cat2 = svc.resolve_or_create_path(["POJK", "2022"])
    db_session.commit()
    count_after_second = db_session.query(Category).count()

    assert cat1.id == cat2.id
    assert count_after_first == count_after_second


def test_c02_duplicate_root_constraint_violation(db_session: Session):
    """C02: Insert manual dua root bernama sama -> IntegrityError (bukti NULLS NOT DISTINCT)."""
    # Root 1
    cat1 = Category(name="Kategori Unik Root", parent_id=None)
    db_session.add(cat1)
    db_session.commit()

    # Root 2 dengan nama yang sama persis dan parent_id=None
    cat2 = Category(name="Kategori Unik Root", parent_id=None)
    db_session.add(cat2)
    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_c03_concurrent_resolve_path_simulation(db_session: Session):
    """C03: Dua pemanggilan resolve path yang sama berurutan tanpa commit di antaranya -> tetap satu baris."""
    svc = CategoryService(db_session)
    # Panggilan 1
    cat1 = svc.resolve_or_create_path(["SEOJK", "2024"])
    # Panggilan 2 langsung dalam sesi yang sama sebelum commit
    cat2 = svc.resolve_or_create_path(["SEOJK", "2024"])

    assert cat1.id == cat2.id
    db_session.commit()

    # Pastikan di database hanya ada 1 baris untuk SEOJK/2024
    child_count = (
        db_session.query(Category)
        .filter(Category.name == "2024", Category.parent_id == cat1.parent_id)
        .count()
    )
    assert child_count == 1


def test_c04_seeder_idempotent(db_session: Session):
    """C04: Seeder dijalankan dua kali -> 7 root, tanpa duplikat."""
    # Sesi awal sudah di-seed oleh fixture conftest
    root_count_1 = db_session.query(Category).filter(Category.parent_id.is_(None)).count()
    assert root_count_1 == 7

    # Jalankan ulang seeder
    seed_initial_categories(db_session)
    root_count_2 = db_session.query(Category).filter(Category.parent_id.is_(None)).count()
    assert root_count_2 == 7

    names = [c.name for c in db_session.query(Category).filter(Category.parent_id.is_(None)).all()]
    expected_roots = ["POJK", "SEOJK", "UU", "PP", "Peraturan Internal DPEA", "Lainnya", "Draft Kajian"]
    for er in expected_roots:
        assert er in names
