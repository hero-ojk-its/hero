"""
tests/test_step33_kunci_kategori.py
Pengujian Langkah 33: Kunci Kategori Otomatis Permanen (K01 - K12).
"""
import io
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import sqlalchemy as sa

from app.config import settings
from app.models.category import Category
from app.models.audit_log import AuditLog
from app.services.category_service import CategoryService
from app.services.audit_service import UPDATE_CATEGORY
from scripts.backfill_kunci_kategori import run_backfill


# ============================================================================
# K01: Penempatan otomatis membuat POJK/2026 -> kedua kategori kunci_otomatis = POJK / 2026
# ============================================================================
def test_k01_auto_placement_creates_kunci_otomatis(db_session: Session):
    cat_svc = CategoryService(db_session)
    leaf = cat_svc.resolve_or_create_path(["POJK", "2026"])
    db_session.commit()

    assert leaf is not None
    assert leaf.name == "2026"
    assert leaf.kunci_otomatis == "2026"
    assert leaf.parent_id is not None

    root = db_session.query(Category).filter(Category.id == leaf.parent_id).first()
    assert root is not None
    assert root.name == "POJK"
    assert root.kunci_otomatis == "POJK"
    assert root.parent_id is None


# ============================================================================
# K02: Ganti nama POJK -> Peraturan OJK, lalu tempatkan dokumen POJK 2026 baru
# ============================================================================
def test_k02_rename_root_category_matches_by_key_no_duplicate_created(db_session: Session):
    cat_svc = CategoryService(db_session)
    leaf1 = cat_svc.resolve_or_create_path(["POJK", "2026"])
    root = db_session.query(Category).filter(Category.id == leaf1.parent_id).first()
    assert root.name == "POJK"
    assert root.kunci_otomatis == "POJK"

    # Admin mengganti nama POJK menjadi Peraturan OJK
    cat_svc.update(root.id, name="Peraturan OJK", name_provided=True)
    db_session.refresh(root)
    assert root.name == "Peraturan OJK"
    assert root.kunci_otomatis == "POJK"
    assert root.auto_created is False

    # Dokumen baru ditempatkan otomatis dengan segmen template ["POJK", "2026"]
    leaf2 = cat_svc.resolve_or_create_path(["POJK", "2026"])
    assert leaf2.id == leaf1.id
    assert leaf2.parent_id == root.id

    # Pastikan tidak ada kategori baru bernama POJK di akar
    root_pojk_count = (
        db_session.query(Category)
        .filter(Category.parent_id.is_(None), Category.name == "POJK")
        .count()
    )
    assert root_pojk_count == 0


# ============================================================================
# K03: Ganti nama 2026 -> Tahun 2026 lalu dokumen baru 2026
# ============================================================================
def test_k03_rename_child_category_matches_by_key(db_session: Session):
    cat_svc = CategoryService(db_session)
    leaf = cat_svc.resolve_or_create_path(["POJK", "2026"])

    # Ganti nama 2026 menjadi Tahun 2026
    cat_svc.update(leaf.id, name="Tahun 2026", name_provided=True)
    db_session.refresh(leaf)
    assert leaf.name == "Tahun 2026"
    assert leaf.kunci_otomatis == "2026"

    # Dokumen baru dengan tahun 2026
    leaf2 = cat_svc.resolve_or_create_path(["POJK", "2026"])
    assert leaf2.id == leaf.id
    assert leaf2.name == "Tahun 2026"
    assert leaf2.kunci_otomatis == "2026"

    # Tidak ada kategori anak bernama 2026 baru di bawah POJK
    child_count = (
        db_session.query(Category)
        .filter(Category.parent_id == leaf.parent_id)
        .count()
    )
    assert child_count == 1


# ============================================================================
# K04: Ganti nama dua kali (POJK -> A -> B), kunci tetap POJK; dokumen baru masuk ke B
# ============================================================================
def test_k04_rename_twice_preserves_original_key(db_session: Session):
    cat_svc = CategoryService(db_session)
    leaf = cat_svc.resolve_or_create_path(["POJK", "2026"])
    root = db_session.query(Category).filter(Category.id == leaf.parent_id).first()

    # Rename 1: POJK -> A
    cat_svc.update(root.id, name="A", name_provided=True)
    db_session.refresh(root)
    assert root.name == "A"
    assert root.kunci_otomatis == "POJK"

    # Rename 2: A -> B
    cat_svc.update(root.id, name="B", name_provided=True)
    db_session.refresh(root)
    assert root.name == "B"
    assert root.kunci_otomatis == "POJK"

    # Dokumen baru POJK/2026 masuk ke B
    leaf2 = cat_svc.resolve_or_create_path(["POJK", "2026"])
    assert leaf2.parent_id == root.id
    path = cat_svc.path_of(leaf2)
    assert path == ["B", "2026"]


# ============================================================================
# K05: Kategori manual (POST) bernama SEOJK, lalu penempatan otomatis SEOJK
# ============================================================================
def test_k05_manual_category_claimed_by_auto_placement(db_session: Session):
    # Hapus kategori SEOJK bawaan seeder agar dapat dibuat manual lewat create
    db_session.query(Category).filter(Category.name == "SEOJK").delete()
    db_session.commit()

    cat_svc = CategoryService(db_session)

    # Kategori manual dibuat pengguna
    manual_cat = cat_svc.create(name="SEOJK")
    assert manual_cat.auto_created is False
    assert manual_cat.kunci_otomatis is None

    # Penempatan otomatis SEOJK/2026
    leaf = cat_svc.resolve_or_create_path(["SEOJK", "2026"])
    db_session.refresh(manual_cat)

    # Memakai kategori manual itu dan mengisi kunci_otomatis="SEOJK"
    assert leaf.parent_id == manual_cat.id
    assert manual_cat.kunci_otomatis == "SEOJK"


# ============================================================================
# K06: Kategori manual diganti nama -> kunci tetap null; penempatan otomatis berikutnya buat baru
# ============================================================================
def test_k06_manual_category_rename_does_not_set_key(db_session: Session):
    cat_svc = CategoryService(db_session)
    manual_cat = cat_svc.create(name="Manual Lama")
    assert manual_cat.auto_created is False
    assert manual_cat.kunci_otomatis is None

    # Ganti nama
    cat_svc.update(manual_cat.id, name="Manual Baru", name_provided=True)
    db_session.refresh(manual_cat)
    assert manual_cat.name == "Manual Baru"
    assert manual_cat.kunci_otomatis is None

    # Penempatan otomatis dengan "Manual Lama"
    auto_cat = cat_svc.resolve_or_create_path(["Manual Lama"])
    assert auto_cat.id != manual_cat.id
    assert auto_cat.name == "Manual Lama"
    assert auto_cat.kunci_otomatis == "Manual Lama"
    assert auto_cat.auto_created is True


# ============================================================================
# K07: Pindah induk kategori otomatis 2026 dari POJK ke SEOJK
# ============================================================================
def test_k07_move_parent_retains_key_and_old_parent_creates_new_child(db_session: Session):
    cat_svc = CategoryService(db_session)
    leaf_pojk = cat_svc.resolve_or_create_path(["POJK", "2026"])
    leaf_seojk = cat_svc.resolve_or_create_path(["SEOJK", "2025"])

    pojk_root = db_session.query(Category).filter(Category.id == leaf_pojk.parent_id).first()
    seojk_root = db_session.query(Category).filter(Category.id == leaf_seojk.parent_id).first()

    # Pindahkan 2026 dari POJK ke SEOJK
    cat_svc.update(leaf_pojk.id, parent_id=seojk_root.id, parent_id_provided=True)
    db_session.refresh(leaf_pojk)
    assert leaf_pojk.parent_id == seojk_root.id
    assert leaf_pojk.kunci_otomatis == "2026"

    # Dokumen POJK/2026 berikutnya sekarang membuat kategori 2026 baru di bawah POJK
    new_leaf = cat_svc.resolve_or_create_path(["POJK", "2026"])
    assert new_leaf.id != leaf_pojk.id
    assert new_leaf.parent_id == pojk_root.id
    assert new_leaf.kunci_otomatis == "2026"


# ============================================================================
# K08: Pindah induk yang menimbulkan bentrok kunci -> 409
# ============================================================================
def test_k08_move_parent_key_conflict_returns_409(db_session: Session):
    cat_svc = CategoryService(db_session)
    pojk_2026 = cat_svc.resolve_or_create_path(["POJK", "2026"])
    seojk_2026 = cat_svc.resolve_or_create_path(["SEOJK", "2026"])

    seojk_root = db_session.query(Category).filter(Category.id == seojk_2026.parent_id).first()

    with pytest.raises(Exception) as exc_info:
        cat_svc.update(pojk_2026.id, parent_id=seojk_root.id, parent_id_provided=True)

    err = exc_info.value
    assert hasattr(err, "status_code") and err.status_code == 409
    assert "Induk tujuan sudah punya kategori otomatis dengan kunci '2026'" in str(err.detail)


# ============================================================================
# K09: Migrasi data step -> auto_created=true terisi kunci=nama, manual null
# ============================================================================
def test_k09_migration_data_step_logic(db_session: Session):
    # Buat kategori auto_created tanpa kunci_otomatis
    cat_auto = Category(name="AutoMigrasi", auto_created=True, kunci_otomatis=None)
    cat_manual = Category(name="ManualMigrasi", auto_created=False, kunci_otomatis=None)
    db_session.add_all([cat_auto, cat_manual])
    db_session.commit()

    # Eksekusi logika SQL data step yang persis ada di alembic upgrade
    db_session.execute(sa.text("UPDATE categories SET kunci_otomatis = name WHERE auto_created = true"))
    db_session.commit()

    db_session.refresh(cat_auto)
    db_session.refresh(cat_manual)

    assert cat_auto.kunci_otomatis == "AutoMigrasi"
    assert cat_manual.kunci_otomatis is None


# ============================================================================
# K10: Race condition: simulasi IntegrityError pada resolve_or_create_path
# ============================================================================
def test_k10_race_condition_handles_integrity_error(db_session: Session):
    cat_svc = CategoryService(db_session)

    orig_flush = db_session.flush
    first_call = True

    def mock_flush(*args, **kwargs):
        nonlocal first_call
        if first_call:
            first_call = False
            from tests.conftest import TestingSessionLocal
            s2 = TestingSessionLocal()
            try:
                s2.add(Category(name="POJK_RACE", kunci_otomatis="POJK_RACE", auto_created=True))
                s2.commit()
            finally:
                s2.close()
            raise IntegrityError("Simulasi race duplicate key", params=None, orig=Exception("duplicate"))
        return orig_flush(*args, **kwargs)

    with patch.object(db_session, "flush", side_effect=mock_flush):
        resolved = cat_svc.resolve_or_create_path(["POJK_RACE"])

    assert resolved is not None
    assert resolved.name == "POJK_RACE"
    assert resolved.kunci_otomatis == "POJK_RACE"


# ============================================================================
# K11: backfill_kunci_kategori.py dry-run lalu --apply
# ============================================================================
def test_k11_backfill_kunci_kategori_dry_run_and_apply(db_session: Session):
    # Buat kategori yang auto_created=False, kunci_otomatis=None
    cat1 = Category(name="Peraturan Baru", auto_created=False, kunci_otomatis=None)
    cat_conflict = Category(name="Konflik Baru", auto_created=False, kunci_otomatis=None)
    db_session.add_all([cat1, cat_conflict])
    db_session.commit()
    db_session.refresh(cat1)
    db_session.refresh(cat_conflict)

    # Catat audit UPDATE_CATEGORY dengan before.name="POJK" untuk cat1
    audit1 = AuditLog(
        action=UPDATE_CATEGORY,
        target_resource=f"category:{cat1.id}",
        detail={"before": {"name": "POJK"}, "after": {"name": "Peraturan Baru"}},
    )
    # Catat audit UPDATE_CATEGORY dengan before.name="POJK" untuk cat_conflict (di root yang sama)
    audit2 = AuditLog(
        action=UPDATE_CATEGORY,
        target_resource=f"category:{cat_conflict.id}",
        detail={"before": {"name": "POJK"}, "after": {"name": "Konflik Baru"}},
    )
    db_session.add_all([audit1, audit2])
    db_session.commit()

    # 1. Dry run
    output_buffer = io.StringIO()
    with patch("sys.stdout", output_buffer):
        run_backfill(apply=False, db=db_session)

    out = output_buffer.getvalue()
    assert f"{cat1.id} | Peraturan Baru | POJK" in out
    assert "[BENTROK - DILEWATI]" in out

    # DB belum berubah
    db_session.refresh(cat1)
    db_session.refresh(cat_conflict)
    assert cat1.kunci_otomatis is None
    assert cat_conflict.kunci_otomatis is None

    # 2. Apply
    output_apply = io.StringIO()
    with patch("sys.stdout", output_apply):
        run_backfill(apply=True, db=db_session)

    db_session.refresh(cat1)
    db_session.refresh(cat_conflict)
    assert cat1.kunci_otomatis == "POJK"
    assert cat_conflict.kunci_otomatis is None  # Dilewati karena bentrok


# ============================================================================
# K12: Respons tree, detail, POST, dan PATCH memuat kunci_otomatis
# ============================================================================
def test_k12_category_responses_include_kunci_otomatis(client: TestClient, db_session: Session):
    cat_svc = CategoryService(db_session)
    cat = cat_svc.resolve_or_create_path(["POJK", "2026"])
    db_session.commit()

    with patch.object(settings, "auth_enabled", False):
        # 1. Tree
        res_tree = client.get("/api/v1/categories/tree")
        assert res_tree.status_code == 200
        tree = res_tree.json()
        pojk_node = next(n for n in tree if n["id"] == cat.parent_id)
        assert "kunci_otomatis" in pojk_node
        assert pojk_node["kunci_otomatis"] == "POJK"
        child_node = pojk_node["children"][0]
        assert "kunci_otomatis" in child_node
        assert child_node["kunci_otomatis"] == "2026"

        # 2. Detail
        res_detail = client.get(f"/api/v1/categories/{cat.id}")
        assert res_detail.status_code == 200
        data_detail = res_detail.json()
        assert "kunci_otomatis" in data_detail
        assert data_detail["kunci_otomatis"] == "2026"

        # 3. POST create
        res_post = client.post("/api/v1/categories/", json={"name": "Kategori Manual API"})
        assert res_post.status_code == 201
        data_post = res_post.json()
        assert "kunci_otomatis" in data_post
        assert data_post["kunci_otomatis"] is None

        # 4. PATCH update
        res_patch = client.patch(
            f"/api/v1/categories/{cat.id}",
            json={"name": "2026 Revisi"},
        )
        assert res_patch.status_code == 200
        data_patch = res_patch.json()
        assert "kategori" in data_patch
        assert "kunci_otomatis" in data_patch["kategori"]
        assert data_patch["kategori"]["kunci_otomatis"] == "2026"
