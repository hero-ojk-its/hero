"""
tests/test_step28_kategori.py
Pengujian Langkah 28: Relokasi Kategori Otomatis, Kelola Kategori (Ubah Nama / Pindah / Hapus / Aturan), dan Audit Penempatan.
Kasus Uji: K01 - K16.
"""
import io
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import bcrypt

from app.models.category import Category
from app.models.document import Document
from app.models.audit_log import AuditLog
from app.models.enums import KlasifikasiAkses, PeranDokumen, StatusPemrosesan
from app.models.user import User
from app.core.permissions import PeranPengguna
from app.services.category_service import CategoryService
from app.services.placement_service import PlacementService
from app.services.storage_service import StorageService
from app.services.audit_service import PLACE_DOCUMENT, UPDATE_CATEGORY, DELETE_CATEGORY
from scripts.relokasi_kategori import run_relokasi


def make_test_pdf(text: str = "Dokumen Uji Kategori") -> bytes:
    """PDF helper minimal untuk pengujian."""
    raw = text.encode("utf-8")
    length = len(raw)
    return (
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(length).encode("ascii") + b" >>\nstream\n"
        + raw +
        b"\nendstream\nendobj\nxref\n0 5\n"
        b"0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000206 00000 n \n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n300\n%%EOF\n"
    )


def write_storage_file(storage: StorageService, rel_path: str, data: bytes) -> None:
    """Helper untuk menulis langsung berkas uji ke storage."""
    abs_path = storage.absolute_path(rel_path)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(data)


# ============================================================================
# K01: Ekstraksi nomor "77", regulation_year=2026, jenis POJK -> POJK/2026
# ============================================================================
def test_k01_category_segments_uses_regulation_year(db_session: Session):
    cat_svc = CategoryService(db_session)
    doc = Document(
        title="POJK 77",
        regulation_type="POJK",
        regulation_number="77",
        regulation_year=2026,
        original_filename="POJK-77-2026.pdf",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
    )
    segs = cat_svc.category_segments_for(doc)
    assert segs == ["POJK", "2026"], f"Ekspektasi ['POJK', '2026'] tapi dapat {segs}"


# ============================================================================
# K02: Dokumen otomatis di POJK/Tanpa Tahun; koreksi metadata -> POJK/2026
# ============================================================================
def test_k02_metadata_correction_relocates_automatic_document(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    cat_svc = CategoryService(db_session)
    cat_tt = cat_svc.resolve_or_create_path(["POJK", "Tanpa Tahun"])

    old_rel_path = "kb/POJK/Tanpa Tahun/POJK 77.pdf"
    write_storage_file(test_storage, old_rel_path, make_test_pdf("POJK 77 Konten"))

    doc = Document(
        title="POJK No 77",
        regulation_type="POJK",
        regulation_number="77",
        regulation_year=None,
        original_filename="POJK-77.pdf",
        file_path_pdf=old_rel_path,
        file_hash="h77",
        file_size_bytes=200,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.terindeks,
        category_id=cat_tt.id,
        kategori_manual=False,
        is_active=True,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={"regulation_year": 2026},
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)

    assert doc.file_path_pdf.startswith("kb/POJK/2026/")
    assert test_storage.exists(doc.file_path_pdf)
    assert not test_storage.exists(old_rel_path)

    # Cek audit log PLACE_DOCUMENT
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == PLACE_DOCUMENT, AuditLog.target_resource == f"document:{doc.id}")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.detail["alasan"] == "relokasi"
    assert audit.detail["kategori_lama"]["path"] == "POJK/Tanpa Tahun"
    assert audit.detail["kategori_baru"]["path"] == "POJK/2026"
    assert audit.detail["kategori_manual"] is False


# ============================================================================
# K03: Dokumen kategori_manual=true di kategori pilihan -> tetap di kategori pilihan
# ============================================================================
def test_k03_manual_category_preserves_placement_on_metadata_correction(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    cat_svc = CategoryService(db_session)
    manual_cat = cat_svc.create("Kajian Khusus")

    rel_path = "kb/Kajian Khusus/doc_manual.pdf"
    write_storage_file(test_storage, rel_path, make_test_pdf("Doc Manual"))

    doc = Document(
        title="Dokumen Manual",
        regulation_type="POJK",
        regulation_number="12",
        regulation_year=2024,
        file_path_pdf=rel_path,
        file_hash="h_man",
        file_size_bytes=300,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.terindeks,
        category_id=manual_cat.id,
        kategori_manual=True,
        is_active=True,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={"regulation_type": "UU", "regulation_year": 2026},
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)

    # Tetap di kategori pilihan manual
    assert doc.category_id == manual_cat.id
    assert doc.kategori_manual is True
    assert doc.file_path_pdf.startswith("kb/Kajian Khusus/")


# ============================================================================
# K04: PATCH metadata category_id: null -> kategori_manual=false & relokasi otomatis
# ============================================================================
def test_k04_patch_null_category_resets_to_automatic(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    cat_svc = CategoryService(db_session)
    manual_cat = cat_svc.create("Folder Manual")

    rel_path = "kb/Folder Manual/doc_k04.pdf"
    write_storage_file(test_storage, rel_path, make_test_pdf("K04 Content"))

    doc = Document(
        title="POJK No 99",
        regulation_type="POJK",
        regulation_number="99",
        regulation_year=2026,
        file_path_pdf=rel_path,
        file_hash="h99",
        file_size_bytes=350,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.terindeks,
        category_id=manual_cat.id,
        kategori_manual=True,
        is_active=True,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={"category_id": None},
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)

    assert doc.kategori_manual is False
    assert doc.file_path_pdf.startswith("kb/POJK/2026/")
    assert not test_storage.exists(rel_path)
    assert test_storage.exists(doc.file_path_pdf)


# ============================================================================
# K05: Unggah dengan category_id -> kategori_manual=true
# ============================================================================
def test_k05_upload_with_category_id_sets_kategori_manual_true(
    client: TestClient, db_session: Session
):
    cat_svc = CategoryService(db_session)
    dest_cat = cat_svc.create("Kategori Upload Khusus")

    pdf_bytes = make_test_pdf("Upload dengan category_id")
    files = [("files", ("peraturan.pdf", pdf_bytes, "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "category_id": str(dest_cat.id),
    }

    resp = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert resp.status_code == 200, resp.text
    doc_id = resp.json()["details"][0]["document_id"]

    doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert doc is not None
    assert doc.category_id == dest_cat.id
    assert doc.kategori_manual is True


# ============================================================================
# K06: Rename kategori berisi 2 dokumen (1 di subkategori) -> path fisik berubah
# ============================================================================
def test_k06_rename_category_relocates_subtree_documents(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    cat_svc = CategoryService(db_session)
    parent_cat = cat_svc.create("Regulasi Lama")
    child_cat = cat_svc.create("Sub 1", parent_id=parent_cat.id)

    # Jadikan auto_created=True untuk menguji perubahan ke False
    parent_cat.auto_created = True
    db_session.commit()

    p1 = "kb/Regulasi Lama/doc1.pdf"
    p2 = "kb/Regulasi Lama/Sub 1/doc2.pdf"
    write_storage_file(test_storage, p1, make_test_pdf("Doc 1"))
    write_storage_file(test_storage, p2, make_test_pdf("Doc 2"))

    d1 = Document(
        title="Doc 1", regulation_type="POJK", regulation_number="1", regulation_year=2021,
        file_path_pdf=p1, file_hash="hd1", file_size_bytes=100, access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting, processing_status=StatusPemrosesan.terindeks,
        category_id=parent_cat.id, kategori_manual=False, is_active=True,
    )
    d2 = Document(
        title="Doc 2", regulation_type="POJK", regulation_number="2", regulation_year=2022,
        file_path_pdf=p2, file_hash="hd2", file_size_bytes=100, access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting, processing_status=StatusPemrosesan.terindeks,
        category_id=child_cat.id, kategori_manual=False, is_active=True,
    )
    db_session.add_all([d1, d2])
    db_session.commit()

    resp = client.patch(
        f"/api/v1/categories/{parent_cat.id}",
        json={"name": "Regulasi Baru"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["dokumen_dipindah"] == 2
    assert len(data["dokumen_gagal"]) == 0
    assert data["kategori"]["auto_created"] is False

    db_session.refresh(parent_cat)
    assert parent_cat.auto_created is False
    assert parent_cat.name == "Regulasi Baru"

    db_session.refresh(d1)
    db_session.refresh(d2)
    assert d1.file_path_pdf.startswith("kb/Regulasi Baru/")
    assert d2.file_path_pdf.startswith("kb/Regulasi Baru/Sub 1/")
    assert test_storage.exists(d1.file_path_pdf)
    assert test_storage.exists(d2.file_path_pdf)

    # Cek audit UPDATE_CATEGORY
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == UPDATE_CATEGORY, AuditLog.target_resource == f"category:{parent_cat.id}")
        .first()
    )
    assert audit is not None
    assert audit.detail["dokumen_dipindah"] == 2


# ============================================================================
# K07: Rename ke nama yang sudah ada di induk yang sama -> 409
# ============================================================================
def test_k07_rename_conflict_same_parent_returns_409(client: TestClient, db_session: Session):
    cat_svc = CategoryService(db_session)
    c1 = cat_svc.create("Folder A")
    c2 = cat_svc.create("Folder B")

    resp = client.patch(
        f"/api/v1/categories/{c2.id}",
        json={"name": "Folder A"},
    )
    assert resp.status_code == 409
    assert "sudah ada" in resp.json()["detail"]


# ============================================================================
# K08: Pindah induk ke turunannya sendiri -> 422
# ============================================================================
def test_k08_move_to_descendant_cycle_returns_422(client: TestClient, db_session: Session):
    cat_svc = CategoryService(db_session)
    root = cat_svc.create("K08 Root")
    child = cat_svc.create("K08 Child", parent_id=root.id)
    grandchild = cat_svc.create("K08 Grandchild", parent_id=child.id)

    resp = client.patch(
        f"/api/v1/categories/{root.id}",
        json={"parent_id": grandchild.id},
    )
    assert resp.status_code == 422
    assert "turunannya" in resp.json()["detail"]


# ============================================================================
# K09: Pindah induk valid -> path dokumen ikut berubah
# ============================================================================
def test_k09_valid_parent_move_relocates_documents(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    cat_svc = CategoryService(db_session)
    parent_old = cat_svc.create("Induk Lama")
    parent_new = cat_svc.create("Induk Baru")
    sub = cat_svc.create("Sub Movable", parent_id=parent_old.id)

    old_p = "kb/Induk Lama/Sub Movable/peraturan.pdf"
    write_storage_file(test_storage, old_p, make_test_pdf("Movable"))

    doc = Document(
        title="Reg", regulation_type="POJK", regulation_number="50", regulation_year=2025,
        file_path_pdf=old_p, file_hash="h50", file_size_bytes=100, access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting, processing_status=StatusPemrosesan.terindeks,
        category_id=sub.id, kategori_manual=False, is_active=True,
    )
    db_session.add(doc)
    db_session.commit()

    resp = client.patch(
        f"/api/v1/categories/{sub.id}",
        json={"parent_id": parent_new.id},
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.file_path_pdf.startswith("kb/Induk Baru/Sub Movable/")
    assert test_storage.exists(doc.file_path_pdf)
    assert not test_storage.exists(old_p)


# ============================================================================
# K10: classification_rule JSON object valid / invalid / array / >4000 char
# ============================================================================
def test_k10_classification_rule_validation(client: TestClient, db_session: Session):
    cat_svc = CategoryService(db_session)
    cat = cat_svc.create("K10 Test")

    # 1. Valid JSON object -> 200
    valid_rule = json.dumps({"keywords": ["ojk", "perbankan"], "match_all": True})
    r1 = client.patch(f"/api/v1/categories/{cat.id}", json={"classification_rule": valid_rule})
    assert r1.status_code == 200
    assert r1.json()["kategori"]["classification_rule"] == valid_rule

    # 2. JSON tidak valid -> 422
    r2 = client.patch(f"/api/v1/categories/{cat.id}", json={"classification_rule": "{not_valid_json"})
    assert r2.status_code == 422

    # 3. JSON array (bukan dict) -> 422
    r3 = client.patch(f"/api/v1/categories/{cat.id}", json={"classification_rule": '["a", "b"]'})
    assert r3.status_code == 422

    # 4. Lebih dari 4.000 karakter -> 422
    long_rule = json.dumps({"key": "x" * 4010})
    r4 = client.patch(f"/api/v1/categories/{cat.id}", json={"classification_rule": long_rule})
    assert r4.status_code == 422


# ============================================================================
# K11: DELETE kategori berisi dokumen, berisi subkategori, dan kosong
# ============================================================================
def test_k11_delete_category_conflict_and_success(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    cat_svc = CategoryService(db_session)
    cat_with_doc = cat_svc.create("K11 With Doc")
    cat_with_sub = cat_svc.create("K11 With Sub")
    cat_svc.create("Sub Child", parent_id=cat_with_sub.id)
    cat_empty = cat_svc.create("K11 Empty")

    doc = Document(
        title="D K11", regulation_type="POJK", regulation_number="11", regulation_year=2021,
        file_path_pdf="kb/doc11.pdf", file_hash="h11", file_size_bytes=100, access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting, processing_status=StatusPemrosesan.terindeks,
        category_id=cat_with_doc.id, is_active=True,
    )
    db_session.add(doc)
    db_session.commit()

    # Hapus kategori berisi dokumen -> 409
    r_doc = client.delete(f"/api/v1/categories/{cat_with_doc.id}")
    assert r_doc.status_code == 409
    assert r_doc.json()["detail"]["dokumen"] == 1

    # Hapus kategori berisi subkategori -> 409
    r_sub = client.delete(f"/api/v1/categories/{cat_with_sub.id}")
    assert r_sub.status_code == 409
    assert r_sub.json()["detail"]["subkategori"] == 1

    # Hapus kategori kosong -> 204
    r_empty = client.delete(f"/api/v1/categories/{cat_empty.id}")
    assert r_empty.status_code == 204

    # Cek audit DELETE_CATEGORY
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == DELETE_CATEGORY, AuditLog.target_resource == f"category:{cat_empty.id}")
        .first()
    )
    assert audit is not None


# ============================================================================
# K12: POST kategori -> auto_created=false
# ============================================================================
def test_k12_post_category_sets_auto_created_false(client: TestClient, db_session: Session):
    resp = client.post(
        "/api/v1/categories/",
        json={"name": "K12 Baru", "classification_rule": '{"tipe": "manual"}'},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["auto_created"] is False
    assert data["name"] == "K12 Baru"

    cat = db_session.query(Category).filter(Category.id == data["id"]).first()
    assert cat is not None
    assert cat.auto_created is False
    assert cat.classification_rule == '{"tipe": "manual"}'


# ============================================================================
# K13: /tree dan GET /{id} memuat jumlah_dokumen dan classification_rule
# ============================================================================
def test_k13_tree_and_detail_contain_jumlah_dokumen_and_rule(client: TestClient, db_session: Session):
    cat_svc = CategoryService(db_session)
    rule = '{"key": "test"}'
    cat = cat_svc.create("K13 Tree Category", classification_rule=rule)

    doc = Document(
        title="D13", regulation_type="POJK", regulation_number="13", regulation_year=2021,
        file_path_pdf="kb/d13.pdf", file_hash="hd13", file_size_bytes=100, access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting, processing_status=StatusPemrosesan.terindeks,
        category_id=cat.id, is_active=True,
    )
    db_session.add(doc)
    db_session.commit()

    # Detail GET /{id}
    r_detail = client.get(f"/api/v1/categories/{cat.id}")
    assert r_detail.status_code == 200
    d_data = r_detail.json()
    assert d_data["jumlah_dokumen"] == 1
    assert d_data["classification_rule"] == rule

    # Tree GET /tree
    r_tree = client.get("/api/v1/categories/tree")
    assert r_tree.status_code == 200
    tree_data = r_tree.json()
    node = next((n for n in tree_data if n["id"] == cat.id), None)
    assert node is not None
    assert node["jumlah_dokumen"] == 1
    assert node["classification_rule"] == rule


# ============================================================================
# K14: relokasi_kategori.py dry-run lalu --apply
# ============================================================================
def test_k14_relokasi_kategori_script_dry_run_and_apply(
    db_session: Session, test_storage: StorageService
):
    cat_svc = CategoryService(db_session)
    cat_tt = cat_svc.resolve_or_create_path(["POJK", "Tanpa Tahun"])
    cat_manual = cat_svc.create("Folder Manual Aman")

    # Dokumen salah kategori (harus dipindah)
    p_wrong = "kb/POJK/Tanpa Tahun/POJK-77-2026.pdf"
    write_storage_file(test_storage, p_wrong, make_test_pdf("Salah Kategori"))
    d_wrong = Document(
        title="POJK 77", regulation_type="POJK", regulation_number="77", regulation_year=2026,
        file_path_pdf=p_wrong, file_hash="h_wrong", file_size_bytes=100, access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting, processing_status=StatusPemrosesan.terindeks,
        category_id=cat_tt.id, kategori_manual=False, is_active=True,
    )

    # Dokumen manual (tidak boleh disentuh)
    p_man = "kb/Folder Manual Aman/manual.pdf"
    write_storage_file(test_storage, p_man, make_test_pdf("Manual"))
    d_man = Document(
        title="Manual Doc", regulation_type="POJK", regulation_number="99", regulation_year=2026,
        file_path_pdf=p_man, file_hash="h_man_sec", file_size_bytes=100, access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting, processing_status=StatusPemrosesan.terindeks,
        category_id=cat_manual.id, kategori_manual=True, is_active=True,
    )
    db_session.add_all([d_wrong, d_man])
    db_session.commit()

    # 1. Jalankan Dry-Run
    res_dry = run_relokasi(db=db_session, storage=test_storage, apply=False)
    assert res_dry["kandidat"] == 1
    assert res_dry["dipindah"] == 0
    db_session.refresh(d_wrong)
    assert d_wrong.file_path_pdf == p_wrong  # Tidak berubah

    # 2. Jalankan Apply
    res_apply = run_relokasi(db=db_session, storage=test_storage, apply=True)
    assert res_apply["kandidat"] == 1
    assert res_apply["dipindah"] == 1
    db_session.refresh(d_wrong)
    db_session.refresh(d_man)

    assert d_wrong.file_path_pdf.startswith("kb/POJK/2026/")
    assert test_storage.exists(d_wrong.file_path_pdf)
    assert not test_storage.exists(p_wrong)

    # Dokumen manual tidak berubah sama sekali
    assert d_man.file_path_pdf == p_man
    assert d_man.category_id == cat_manual.id


# ============================================================================
# K15: Auth aktif, token tanpa KB_KELOLA -> 403 untuk PATCH/DELETE/POST
# ============================================================================
def test_k15_auth_without_kb_kelola_returns_403(auth_client: TestClient, db_session: Session):
    plain_pw = "analispass123"
    hashed_pw = bcrypt.hashpw(plain_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(
        username="analis_k15",
        hashed_password=hashed_pw,
        role=PeranPengguna.analis,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    login_resp = auth_client.post(
        "/api/v1/auth/login",
        data={"username": user.username, "password": plain_pw},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    cat_svc = CategoryService(db_session)
    cat = cat_svc.create("K15 Category")

    # POST
    r_post = auth_client.post("/api/v1/categories/", json={"name": "Baru"}, headers=headers)
    assert r_post.status_code == 403

    # PATCH
    r_patch = auth_client.patch(f"/api/v1/categories/{cat.id}", json={"name": "Ubah"}, headers=headers)
    assert r_patch.status_code == 403

    # DELETE
    r_del = auth_client.delete(f"/api/v1/categories/{cat.id}", headers=headers)
    assert r_del.status_code == 403


# ============================================================================
# K16: Satu dokumen gagal dipindah saat rename -> rename tetap tersimpan, masuk dokumen_gagal
# ============================================================================
def test_k16_one_document_failure_during_rename_keeps_category_change(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    cat_svc = CategoryService(db_session)
    parent_cat = cat_svc.create("Rename Partial Test")

    p1 = "kb/Rename Partial Test/doc_ok.pdf"
    p2 = "kb/Rename Partial Test/doc_missing.pdf"
    write_storage_file(test_storage, p1, make_test_pdf("Doc OK"))
    write_storage_file(test_storage, p2, make_test_pdf("Doc Missing"))

    d1 = Document(
        title="D OK", regulation_type="POJK", regulation_number="1", regulation_year=2021,
        file_path_pdf=p1, file_hash="hok", file_size_bytes=100, access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting, processing_status=StatusPemrosesan.terindeks,
        category_id=parent_cat.id, is_active=True,
    )
    d2 = Document(
        title="D Missing", regulation_type="POJK", regulation_number="2", regulation_year=2022,
        file_path_pdf=p2, file_hash="hmis", file_size_bytes=100, access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting, processing_status=StatusPemrosesan.terindeks,
        category_id=parent_cat.id, is_active=True,
    )
    db_session.add_all([d1, d2])
    db_session.commit()

    # Hapus berkas d2 dari storage sebelum rename untuk memicu kegagalan pemindahan
    test_storage.delete(p2)

    resp = client.patch(
        f"/api/v1/categories/{parent_cat.id}",
        json={"name": "Rename Sukses Sebagian"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["dokumen_dipindah"] == 1
    assert len(data["dokumen_gagal"]) == 1
    assert data["dokumen_gagal"][0]["document_id"] == d2.id

    db_session.refresh(parent_cat)
    assert parent_cat.name == "Rename Sukses Sebagian"
