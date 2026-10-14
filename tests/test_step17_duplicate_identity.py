"""
tests/test_step17_duplicate_identity.py
Pengujian Cek Duplikat Identitas (Judul + Nomor Peraturan) — Langkah 17.
Kasus Uji: D01 - D13
"""
from datetime import date
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import Document
from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
)
from app.services.audit_service import DUPLICATE_IDENTITY_DETECTED
from app.services.duplicate_service import (
    DuplicateResult,
    check_identity_duplicate,
    compare_docs,
)
from app.services.identity_service import fallback_identity_key
from app.services.storage_service import StorageService
from scripts.backfill_identity import run_backfill
from tests.conftest import make_pdf

INTERNAL_HEADERS = {"X-Internal-API-Key": settings.internal_api_key}


def _seed_test_doc(
    db: Session,
    storage: StorageService,
    title: str = "Dokumen Uji",
    reg_num: str = "11/POJK.03/2022",
    reg_type: str = "POJK",
    reg_year: int = 2022,
    identity_key: str = None,
    page_count: int = None,
    file_size_bytes: int = None,
    document_role: PeranDokumen = PeranDokumen.corpus_eksisting,
    processing_status: StatusPemrosesan = StatusPemrosesan.diproses,
    is_active: bool = True,
    duplicate_of_id: int = None,
) -> Document:
    cat = db.query(Category).filter(Category.name == "POJK").first()
    pdf_bytes = make_pdf(f"Isi konten PDF untuk {title}")
    rel_path = storage.save_pdf(pdf_bytes, filename_hint=f"{title.replace(' ', '_').lower()}.pdf", subdir="pdf/_inbox")

    actual_size = file_size_bytes if file_size_bytes is not None else len(pdf_bytes)

    doc = Document(
        title=title,
        regulation_number=reg_num,
        regulation_type=reg_type,
        release_date=date(reg_year, 1, 1),
        regulation_year=reg_year,
        file_path_pdf=rel_path,
        file_hash=f"hash_{title.replace(' ', '_').lower()}_{id(pdf_bytes)}",
        file_size_bytes=actual_size,
        access_classification=KlasifikasiAkses.publik,
        document_role=document_role,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=processing_status,
        is_active=is_active,
        category_id=cat.id if cat else None,
        identity_key=identity_key,
        page_count=page_count,
        duplicate_of_id=duplicate_of_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_d01_fallback_identity_key_rules():
    """
    D01: Uji logika fallback_identity_key untuk variasi jenis, nomor, dan tahun.
    """
    assert fallback_identity_key("POJK", "11/POJK.03/2022", None) == "POJK|11|2022"
    assert fallback_identity_key("POJK", "36 Tahun 2024", None) == "POJK|36|2024"
    assert fallback_identity_key("POJK", "5", 2020) == "POJK|5|2020"
    assert fallback_identity_key("PBI", "7/1/PBI/2005", 2005) is None
    assert fallback_identity_key("POJK", None, 2020) is None
    assert fallback_identity_key("UU", "4 Tahun 2023", 2023) is None


def test_d02_patch_extraction_page_count_winner(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    D02: Dok A (10 hlm) terindeks; PATCH extraction dok B dengan kunci sama, 25 hlm.
    Ekspektasi: B tetap aktif; A nonaktif, duplicate_of_id = B, alasan memuat duplikat_identitas;
    respons B memuat duplikat.rule = "page_count"; audit tercatat.
    """
    doc_a = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 11 2022 Versi A",
        reg_num="11/POJK.03/2022",
        identity_key="POJK|11|2022",
        page_count=10,
        processing_status=StatusPemrosesan.terindeks,
    )
    doc_b = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 11 2022 Versi B",
        reg_num="11/POJK.03/2022",
        processing_status=StatusPemrosesan.diproses,
    )

    payload = {
        "judul": "POJK 11 2022 Versi B Lengkap",
        "nomor_peraturan": "11/POJK.03/2022",
        "jenis_peraturan": "POJK",
        "kunci_identitas": "POJK|11|2022",
        "jumlah_halaman": 25,
        "teks_lengkap": "Isi teks lengkap peraturan versi 25 halaman.",
    }
    resp = client.patch(f"/api/v1/internal/documents/{doc_b.id}/extraction", headers=INTERNAL_HEADERS, json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["duplikat"] is not None
    assert data["duplikat"]["rule"] == "page_count"
    assert data["duplikat"]["kept_document_id"] == doc_b.id
    assert data["duplikat"]["deactivated_document_ids"] == [doc_a.id]

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)

    assert doc_b.is_active is True
    assert doc_a.is_active is False
    assert doc_a.duplicate_of_id == doc_b.id
    assert "duplikat_identitas" in (doc_a.deactivated_reason or "")

    # Audit check
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == DUPLICATE_IDENTITY_DETECTED, AuditLog.target_resource == f"document:{doc_b.id}")
        .first()
    )
    assert audit is not None
    assert audit.detail["rule"] == "page_count"
    assert audit.detail["identity_key"] == "POJK|11|2022"


def test_d03_patch_extraction_loser_deactivated(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    D03: Sama seperti D02, tetapi B 5 hlm (A 10 hlm).
    Ekspektasi: B nonaktif, A tetap aktif.
    """
    doc_a = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 11 2022 Versi A 10 Hal",
        reg_num="11/POJK.03/2022",
        identity_key="POJK|11|2022",
        page_count=10,
        processing_status=StatusPemrosesan.terindeks,
    )
    doc_b = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 11 2022 Versi B 5 Hal",
        reg_num="11/POJK.03/2022",
        processing_status=StatusPemrosesan.diproses,
    )

    payload = {
        "judul": "POJK 11 2022 Versi B 5 Hal",
        "nomor_peraturan": "11/POJK.03/2022",
        "jenis_peraturan": "POJK",
        "kunci_identitas": "POJK|11|2022",
        "jumlah_halaman": 5,
        "teks_lengkap": "Isi teks regulasi versi 5 halaman.",
    }
    resp = client.patch(f"/api/v1/internal/documents/{doc_b.id}/extraction", headers=INTERNAL_HEADERS, json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["duplikat"] is not None
    assert data["duplikat"]["rule"] == "page_count"
    assert data["duplikat"]["kept_document_id"] == doc_a.id
    assert data["duplikat"]["deactivated_document_ids"] == [doc_b.id]

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)

    assert doc_a.is_active is True
    assert doc_b.is_active is False
    assert doc_b.duplicate_of_id == doc_a.id
    assert "duplikat_identitas" in (doc_b.deactivated_reason or "")


def test_d04_file_size_winner_when_pages_unknown(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    D04: Jumlah halaman tidak diketahui, ukuran B > A.
    Ekspektasi: A nonaktif, rule = "file_size".
    """
    doc_a = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 15 2023 Versi Kecil",
        reg_num="15/POJK.03/2023",
        identity_key="POJK|15|2023",
        page_count=None,
        file_size_bytes=1000,
        processing_status=StatusPemrosesan.terindeks,
    )
    doc_b = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 15 2023 Versi Besar",
        reg_num="15/POJK.03/2023",
        page_count=None,
        file_size_bytes=5000,
        processing_status=StatusPemrosesan.diproses,
    )

    payload = {
        "judul": "POJK 15 2023 Versi Besar",
        "nomor_peraturan": "15/POJK.03/2023",
        "jenis_peraturan": "POJK",
        "kunci_identitas": "POJK|15|2023",
        "jumlah_halaman": None,
        "teks_lengkap": "Teks lengkap.",
    }
    resp = client.patch(f"/api/v1/internal/documents/{doc_b.id}/extraction", headers=INTERNAL_HEADERS, json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["duplikat"] is not None
    assert data["duplikat"]["rule"] == "file_size"
    assert data["duplikat"]["kept_document_id"] == doc_b.id
    assert data["duplikat"]["deactivated_document_ids"] == [doc_a.id]

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)

    assert doc_a.is_active is False
    assert doc_b.is_active is True
    assert doc_a.duplicate_of_id == doc_b.id


def test_d05_older_id_winner_on_tie(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    D05: Halaman dan ukuran sama.
    Ekspektasi: Yang id-nya lebih besar nonaktif, rule = "older".
    """
    doc_a = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 16 2023 Kembar A",
        reg_num="16/POJK.03/2023",
        identity_key="POJK|16|2023",
        page_count=12,
        file_size_bytes=3000,
        processing_status=StatusPemrosesan.terindeks,
    )
    doc_b = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 16 2023 Kembar B",
        reg_num="16/POJK.03/2023",
        page_count=12,
        file_size_bytes=3000,
        processing_status=StatusPemrosesan.diproses,
    )
    assert doc_a.id < doc_b.id

    payload = {
        "judul": "POJK 16 2023 Kembar B",
        "nomor_peraturan": "16/POJK.03/2023",
        "jenis_peraturan": "POJK",
        "kunci_identitas": "POJK|16|2023",
        "jumlah_halaman": 12,
        "teks_lengkap": "Teks kembar.",
    }
    resp = client.patch(f"/api/v1/internal/documents/{doc_b.id}/extraction", headers=INTERNAL_HEADERS, json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["duplikat"] is not None
    assert data["duplikat"]["rule"] == "older"
    assert data["duplikat"]["kept_document_id"] == doc_a.id
    assert data["duplikat"]["deactivated_document_ids"] == [doc_b.id]

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)

    assert doc_a.is_active is True
    assert doc_b.is_active is False
    assert doc_b.duplicate_of_id == doc_a.id


def test_d06_different_keys_no_deactivation(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    D06: Kunci berbeda.
    Ekspektasi: Tidak ada yang dinonaktifkan, duplikat = null.
    """
    doc_a = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 17 2023",
        reg_num="17/POJK.03/2023",
        identity_key="POJK|17|2023",
        processing_status=StatusPemrosesan.terindeks,
    )
    doc_b = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 18 2023",
        reg_num="18/POJK.03/2023",
        processing_status=StatusPemrosesan.diproses,
    )

    payload = {
        "judul": "POJK 18 2023",
        "nomor_peraturan": "18/POJK.03/2023",
        "jenis_peraturan": "POJK",
        "kunci_identitas": "POJK|18|2023",
        "teks_lengkap": "Teks 18.",
    }
    resp = client.patch(f"/api/v1/internal/documents/{doc_b.id}/extraction", headers=INTERNAL_HEADERS, json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["duplikat"] is None

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)
    assert doc_a.is_active is True
    assert doc_b.is_active is True


def test_d07_ignore_draft_kajian_peer(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    D07: Pasangan berperan draft_kajian -> diabaikan.
    """
    doc_a = _seed_test_doc(
        db_session,
        test_storage,
        title="Draft Kajian POJK 19",
        reg_num="19/POJK.03/2023",
        identity_key="POJK|19|2023",
        document_role=PeranDokumen.draft_kajian,
        processing_status=StatusPemrosesan.terindeks,
    )
    doc_b = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 19 2023",
        reg_num="19/POJK.03/2023",
        document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.diproses,
    )

    payload = {
        "judul": "POJK 19 2023 Resmi",
        "nomor_peraturan": "19/POJK.03/2023",
        "jenis_peraturan": "POJK",
        "kunci_identitas": "POJK|19|2023",
        "teks_lengkap": "Teks resmi.",
    }
    resp = client.patch(f"/api/v1/internal/documents/{doc_b.id}/extraction", headers=INTERNAL_HEADERS, json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["duplikat"] is None
    db_session.refresh(doc_a)
    db_session.refresh(doc_b)
    assert doc_a.is_active is True
    assert doc_b.is_active is True


def test_d08_manually_reactivated_doc_not_deactivated_again(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    D08: A pernah duplikat lalu diaktifkan manual (PUT /active); B masuk dengan kunci sama.
    Ekspektasi: A TIDAK dinonaktifkan ulang.
    """
    # A awalnya punya duplicate_of_id (misal pernah jadi duplikat dokumen X)
    doc_x = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen X Pendahulu",
        reg_num="20/POJK.03/2023",
        identity_key="POJK|20|2023",
        page_count=20,
        processing_status=StatusPemrosesan.terindeks,
    )
    doc_a = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen A Duplikat Diaktifkan Manual",
        reg_num="20/POJK.03/2023",
        identity_key="POJK|20|2023",
        page_count=10,
        processing_status=StatusPemrosesan.terindeks,
        is_active=False,
        duplicate_of_id=doc_x.id,
    )

    # Aktifkan manual Dokumen A melalui PUT /api/v1/documents/{id}/active
    resp_act = client.put(
        f"/api/v1/documents/{doc_a.id}/active",
        json={"is_active": True, "reason": "Keputusan manual admin untuk mengaktifkan kembali"},
    )
    assert resp_act.status_code == 200, resp_act.text
    db_session.refresh(doc_a)
    assert doc_a.is_active is True
    assert doc_a.duplicate_of_id == doc_x.id

    # Dokumen B masuk dengan kunci sama dan halaman 30
    doc_b = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen B Baru 30 Hal",
        reg_num="20/POJK.03/2023",
        processing_status=StatusPemrosesan.diproses,
    )

    payload = {
        "judul": "Dokumen B Baru 30 Hal",
        "nomor_peraturan": "20/POJK.03/2023",
        "jenis_peraturan": "POJK",
        "kunci_identitas": "POJK|20|2023",
        "jumlah_halaman": 30,
        "teks_lengkap": "Teks B.",
    }
    resp = client.patch(f"/api/v1/internal/documents/{doc_b.id}/extraction", headers=INTERNAL_HEADERS, json=payload)
    assert resp.status_code == 200, resp.text

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)
    db_session.refresh(doc_x)

    # A TIDAK boleh dinonaktifkan ulang karena keputusan pengguna (manual activation)
    assert doc_a.is_active is True
    # doc_x yang tidak dilindungi dapat dinonaktifkan oleh B yang lebih lengkap
    assert doc_x.is_active is False


def test_d09_batch_patch_internal_identity(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    D09: PATCH /internal/documents/identity dengan 3 item: 1 tidak ada, 2 berkunci sama.
    Ekspektasi: not_found memuat id yang tidak ada; satu dari dua dinonaktifkan.
    """
    doc_1 = _seed_test_doc(
        db_session,
        test_storage,
        title="Regulasi Batch 1",
        reg_num="21/POJK.03/2024",
        page_count=10,
        processing_status=StatusPemrosesan.terindeks,
    )
    doc_2 = _seed_test_doc(
        db_session,
        test_storage,
        title="Regulasi Batch 2",
        reg_num="21/POJK.03/2024",
        page_count=20,
        processing_status=StatusPemrosesan.terindeks,
    )

    items = [
        {"document_id": 999999, "kunci_identitas": "POJK|21|2024", "jumlah_halaman": 5},
        {"document_id": doc_1.id, "kunci_identitas": "POJK|21|2024", "jumlah_halaman": 10},
        {"document_id": doc_2.id, "kunci_identitas": "POJK|21|2024", "jumlah_halaman": 20},
    ]

    resp = client.patch(
        "/api/v1/internal/documents/identity",
        headers=INTERNAL_HEADERS,
        json=items,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["updated"] == 2
    assert 999999 in data["not_found"]
    assert len(data["duplicates"]) >= 1

    db_session.refresh(doc_1)
    db_session.refresh(doc_2)

    # Salah satu harus nonaktif (doc_1 karena halaman lebih sedikit)
    assert doc_2.is_active is True
    assert doc_1.is_active is False
    assert doc_1.duplicate_of_id == doc_2.id


def test_d10_monkeypatch_duplicate_error_resilient(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    D10: Cek duplikat dipaksa melempar galat (monkeypatch) -> PATCH extraction tetap 200, hasil ekstraksi tersimpan.
    """
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen D10 Resilien",
        reg_num="22/POJK.03/2024",
        processing_status=StatusPemrosesan.diproses,
    )

    payload = {
        "judul": "Dokumen D10 Sukses Tersimpan",
        "nomor_peraturan": "22/POJK.03/2024",
        "jenis_peraturan": "POJK",
        "kunci_identitas": "POJK|22|2024",
        "jumlah_halaman": 15,
        "teks_lengkap": "Konten tersimpan meskipun cek duplikat error.",
    }

    with patch("app.routers.internal.check_identity_duplicate", side_effect=RuntimeError("Simulasi error duplikasi")):
        resp = client.patch(f"/api/v1/internal/documents/{doc.id}/extraction", headers=INTERNAL_HEADERS, json=payload)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["duplikat"] is None

    db_session.refresh(doc)
    assert doc.title == "Dokumen D10 Sukses Tersimpan"
    assert doc.full_text == "Konten tersimpan meskipun cek duplikat error."
    assert doc.identity_key == "POJK|22|2024"


def test_d11_fallback_identity_key_applied_when_not_provided(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    D11: Tanpa kunci_identitas, metadata POJK / 11/POJK.03/2022 -> identity_key terisi POJK|11|2022 dari cadangan.
    """
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen D11 Tanpa Kunci",
        reg_num="11/POJK.03/2022",
        reg_type="POJK",
        processing_status=StatusPemrosesan.diproses,
    )

    payload = {
        "judul": "POJK Nomor 11 Tahun 2022",
        "nomor_peraturan": "11/POJK.03/2022",
        "jenis_peraturan": "POJK",
        "jumlah_halaman": 14,
        "teks_lengkap": "Teks peraturan tanpa kunci.",
    }
    resp = client.patch(f"/api/v1/internal/documents/{doc.id}/extraction", headers=INTERNAL_HEADERS, json=payload)
    assert resp.status_code == 200, resp.text

    db_session.refresh(doc)
    assert doc.identity_key == "POJK|11|2022"
    assert doc.page_count == 14


def test_d12_list_and_dashboard_duplicate_filter(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    D12: GET /documents?include_inactive=true&duplikat=true dan dashboard
    Ekspektasi: dokumen duplikat tercantum; kb.duplicate_documents sesuai.
    """
    winner = _seed_test_doc(
        db_session,
        test_storage,
        title="Regulasi Induk D12",
        reg_num="30/POJK.03/2025",
        identity_key="POJK|30|2025",
        is_active=True,
    )
    dup = _seed_test_doc(
        db_session,
        test_storage,
        title="Regulasi Duplikat D12",
        reg_num="30/POJK.03/2025",
        identity_key="POJK|30|2025",
        is_active=False,
        duplicate_of_id=winner.id,
    )

    # 1. List tanpa include_inactive -> dup tidak muncul
    r_list1 = client.get("/api/v1/documents/?duplikat=true")
    assert r_list1.status_code == 200
    ids_1 = [d["id"] for d in r_list1.json()["items"]]
    assert dup.id not in ids_1

    # 2. List dengan include_inactive=true&duplikat=true -> dup muncul
    r_list2 = client.get("/api/v1/documents/?include_inactive=true&duplikat=true")
    assert r_list2.status_code == 200
    items_2 = r_list2.json()["items"]
    dup_item = next((d for d in items_2 if d["id"] == dup.id), None)
    assert dup_item is not None
    assert dup_item["duplicate_of_id"] == winner.id
    assert dup_item["identity_key"] == "POJK|30|2025"

    # 3. Detail dokumen
    r_detail = client.get(f"/api/v1/documents/{dup.id}")
    assert r_detail.status_code == 200
    d_data = r_detail.json()
    assert d_data["duplicate_of_id"] == winner.id
    assert d_data["identity_key"] == "POJK|30|2025"

    # 4. Dashboard summary
    r_dash = client.get("/api/v1/dashboard/summary")
    assert r_dash.status_code == 200
    kb_data = r_dash.json()["kb"]
    assert "duplicate_documents" in kb_data
    assert kb_data["duplicate_documents"] >= 1


def test_d13_backfill_identity_dry_run(db_session: Session, test_storage: StorageService):
    """
    D13: backfill_identity.py --dry-run
    Ekspektasi: tidak ada perubahan di DB; laporan memuat pasangan.
    """
    # Seed dua dokumen tanpa identity_key tetapi memiliki nomor yang bisa di-fallback
    doc1 = _seed_test_doc(
        db_session,
        test_storage,
        title="Regulasi Tanpa Kunci 1",
        reg_num="33/POJK.03/2024",
        reg_type="POJK",
        reg_year=2024,
        identity_key=None,
        page_count=10,
        processing_status=StatusPemrosesan.terindeks,
    )
    doc2 = _seed_test_doc(
        db_session,
        test_storage,
        title="Regulasi Tanpa Kunci 2",
        reg_num="33/POJK.03/2024",
        reg_type="POJK",
        reg_year=2024,
        identity_key=None,
        page_count=20,
        processing_status=StatusPemrosesan.terindeks,
    )

    summary = run_backfill(db_session, apply=False)

    assert summary["filled_keys"] >= 2
    assert summary["duplicate_groups"] >= 1
    assert summary["total_deactivated"] >= 1

    # Verifikasi di database: TIDAK BERUBAH (tetap None dan tetap is_active True)
    db_session.refresh(doc1)
    db_session.refresh(doc2)

    assert doc1.identity_key is None
    assert doc2.identity_key is None
    assert doc1.is_active is True
    assert doc2.is_active is True
    assert doc1.duplicate_of_id is None
