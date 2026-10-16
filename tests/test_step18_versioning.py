"""
tests/test_step18_versioning.py
Pengujian Versioning Dokumen: Relasi Mengubah/Mencabut (Langkah 18, US-29 #37).
Kasus Uji: R01 - R14.
"""
from datetime import date
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import Document
from app.models.document_relation import DocumentRelation
from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.enums import (
    JenisRelasi,
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
)
from app.services.audit_service import STATUS_FROM_RELATION
from app.services.storage_service import StorageService
from tests.conftest import make_pdf

INTERNAL_HEADERS = {"X-Internal-API-Key": settings.internal_api_key}


def _seed_test_doc(
    db: Session,
    test_storage: StorageService,
    title: str = "Dokumen Regulasi Uji",
    reg_num: str | None = "11/POJK.03/2022",
    reg_type: str = "POJK",
    reg_year: int = 2022,
    identity_key: str | None = "POJK|11|2022",
    status_keberlakuan: StatusKeberlakuan = StatusKeberlakuan.tidak_diketahui,
    status_source: str | None = None,
    access_classification: KlasifikasiAkses = KlasifikasiAkses.publik,
    is_active: bool = True,
) -> Document:
    cat = db.query(Category).filter(Category.name == reg_type).first()
    pdf_bytes = make_pdf(f"Konten PDF untuk {title}")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint=f"{title.replace(' ', '_').lower()}.pdf", subdir="pdf/_inbox")

    doc = Document(
        title=title,
        regulation_number=reg_num,
        regulation_type=reg_type,
        release_date=date(reg_year, 1, 1),
        regulation_year=reg_year,
        file_path_pdf=rel_path,
        file_hash=f"hash_{title.replace(' ', '_').lower()}_{id(pdf_bytes)}",
        file_size_bytes=len(pdf_bytes),
        access_classification=access_classification,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=status_keberlakuan,
        status_source=status_source,
        processing_status=StatusPemrosesan.diproses,
        is_active=is_active,
        category_id=cat.id if cat else None,
        identity_key=identity_key,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_r01_post_relations_inserted_and_skipped(client: TestClient, db_session: Session):
    """
    R01: POST 3 relasi (2 MENGUBAH, 1 MENCABUT) + 1 BERDASAR.
    Ekspektasi: inserted=3, skipped=1.
    """
    payload = {
        "relations": [
            {"src": "POJK|1|2024", "dst": "POJK|11|2022", "rel": "MENGUBAH", "sebagian": 0},
            {"src": "POJK|2|2025", "dst": "POJK|11|2022", "rel": "MENGUBAH", "sebagian": 1},
            {"src": "POJK|3|2026", "dst": "POJK|5|2020", "rel": "MENCABUT", "sebagian": 0},
            {"src": "POJK|4|2026", "dst": "UU|1|2023", "rel": "BERDASAR"},
        ],
        "replace_all": False,
    }
    resp = client.post("/api/v1/internal/relations", json=payload, headers=INTERNAL_HEADERS)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["inserted"] == 3
    assert data["skipped"] == 1
    assert data["updated"] == 0
    assert data["deleted"] == 0


def test_r02_post_duplicate_relation_updates_without_doubles(client: TestClient, db_session: Session):
    """
    R02: POST ulang relasi yang sama dengan pasal_terkait berbeda.
    Ekspektasi: updated >= 1, tidak ada baris ganda di database.
    """
    payload1 = {
        "relations": [
            {"src": "POJK|5|2024", "dst": "POJK|11|2022", "rel": "MENGUBAH", "pasal_terkait": "Pasal 3"},
        ]
    }
    resp1 = client.post("/api/v1/internal/relations", json=payload1, headers=INTERNAL_HEADERS)
    assert resp1.status_code == 200
    assert resp1.json()["inserted"] == 1

    payload2 = {
        "relations": [
            {"src": "POJK|5|2024", "dst": "POJK|11|2022", "rel": "MENGUBAH", "pasal_terkait": "Pasal 3, Pasal 7"},
        ]
    }
    resp2 = client.post("/api/v1/internal/relations", json=payload2, headers=INTERNAL_HEADERS)
    assert resp2.status_code == 200
    assert resp2.json()["updated"] == 1
    assert resp2.json()["inserted"] == 0

    rows = db_session.query(DocumentRelation).filter(
        DocumentRelation.source_key == "POJK|5|2024",
        DocumentRelation.target_key == "POJK|11|2022",
        DocumentRelation.relation == JenisRelasi.mengubah,
    ).all()
    assert len(rows) == 1
    assert rows[0].articles_text == "Pasal 3, Pasal 7"


def test_r03_replace_all_deletes_unspecified_relations(client: TestClient, db_session: Session):
    """
    R03: replace_all=true dengan payload berisi 1 relasi menghapus relasi lama.
    Ekspektasi: relasi lain terhapus, deleted sesuai.
    """
    db_session.query(DocumentRelation).delete()
    db_session.commit()

    # Masukkan 2 relasi awal
    client.post(
        "/api/v1/internal/relations",
        json={
            "relations": [
                {"src": "POJK|1|2020", "dst": "POJK|99|2019", "rel": "MENGUBAH"},
                {"src": "POJK|2|2021", "dst": "POJK|99|2019", "rel": "MENGUBAH"},
            ]
        },
        headers=INTERNAL_HEADERS,
    )
    assert db_session.query(DocumentRelation).count() == 2

    # Kirim replace_all dengan hanya 1 relasi
    resp = client.post(
        "/api/v1/internal/relations",
        json={
            "relations": [
                {"src": "POJK|3|2022", "dst": "POJK|99|2019", "rel": "MENGUBAH"},
            ],
            "replace_all": True,
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["inserted"] == 1
    assert data["deleted"] == 2
    assert db_session.query(DocumentRelation).count() == 1


def test_r04_full_repeal_updates_status_and_records_audit(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    R04: Dok A (POJK|11|2022) aktif, status tidak_diketahui; relasi POJK|1|2026 MENCABUT A (sebagian=0).
    Ekspektasi: A -> dicabut, status_source=relasi, audit tercatat.
    """
    doc_a = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen A",
        identity_key="POJK|11|2022",
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
    )

    resp = client.post(
        "/api/v1/internal/relations",
        json={
            "relations": [
                {"src": "POJK|1|2026", "dst": "POJK|11|2022", "rel": "MENCABUT", "sebagian": 0},
            ]
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    db_session.refresh(doc_a)
    assert doc_a.status_keberlakuan == StatusKeberlakuan.dicabut
    assert doc_a.status_source == "relasi"

    # Cek audit log
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == STATUS_FROM_RELATION,
        AuditLog.target_resource == f"document:{doc_a.id}",
    ).first()
    assert audit is not None
    assert audit.detail.get("rule") == "mencabut_penuh"
    assert audit.detail.get("after") == "dicabut"


def test_r05_amendment_relation_updates_to_diubah(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    R05: Relasi MENGUBAH A -> A diubah, status_source=relasi.
    """
    doc_a = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen A R05",
        identity_key="POJK|15|2022",
        status_keberlakuan=StatusKeberlakuan.berlaku,
    )

    resp = client.post(
        "/api/v1/internal/relations",
        json={
            "relations": [
                {"src": "POJK|2|2024", "dst": "POJK|15|2022", "rel": "MENGUBAH"},
            ]
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    db_session.refresh(doc_a)
    assert doc_a.status_keberlakuan == StatusKeberlakuan.diubah
    assert doc_a.status_source == "relasi"


def test_r06_partial_repeal_updates_to_diubah_not_dicabut(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    R06: Relasi MENCABUT A dengan sebagian=1 -> A diubah (bukan dicabut).
    """
    doc_a = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen A R06",
        identity_key="POJK|20|2022",
        status_keberlakuan=StatusKeberlakuan.berlaku,
    )

    resp = client.post(
        "/api/v1/internal/relations",
        json={
            "relations": [
                {"src": "POJK|3|2025", "dst": "POJK|20|2022", "rel": "MENCABUT", "sebagian": 1},
            ]
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    db_session.refresh(doc_a)
    assert doc_a.status_keberlakuan == StatusKeberlakuan.diubah
    assert doc_a.status_source == "relasi"


def test_r07_manual_status_not_overwritten_by_relations(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    R07: Status A diubah manual lewat endpoint US-31, lalu relasi MENCABUT dikirim.
    Ekspektasi: status A tidak berubah; status_source=manual.
    """
    doc_a = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen A R07",
        identity_key="POJK|30|2022",
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
    )

    # 1. Ubah via endpoint PUT /documents/{id}/status (US-31)
    resp_put = client.put(
        f"/api/v1/documents/{doc_a.id}/status",
        json={"status_keberlakuan": "berlaku"},
    )
    assert resp_put.status_code == 200
    db_session.refresh(doc_a)
    assert doc_a.status_keberlakuan == StatusKeberlakuan.berlaku
    assert doc_a.status_source == "manual"

    # 2. Kirim relasi MENCABUT
    resp_rel = client.post(
        "/api/v1/internal/relations",
        json={
            "relations": [
                {"src": "POJK|99|2026", "dst": "POJK|30|2022", "rel": "MENCABUT", "sebagian": 0},
            ]
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp_rel.status_code == 200
    db_session.refresh(doc_a)
    # Harus tetap berlaku dan status_source tetap manual
    assert doc_a.status_keberlakuan == StatusKeberlakuan.berlaku
    assert doc_a.status_source == "manual"


def test_r08_node_status_applied_when_no_incoming_relation(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    R08: Tanpa relasi masuk, nodes membawa {key: A, status: "berlaku"}.
    Ekspektasi: A -> berlaku, status_source=lapisan_data.
    """
    doc_a = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen A R08",
        identity_key="POJK|40|2022",
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
    )

    resp = client.post(
        "/api/v1/internal/relations",
        json={
            "relations": [],
            "nodes": [{"key": "POJK|40|2022", "status": "berlaku"}],
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    db_session.refresh(doc_a)
    assert doc_a.status_keberlakuan == StatusKeberlakuan.berlaku
    assert doc_a.status_source == "lapisan_data"


def test_r09_relation_saved_before_document_applied_on_extraction(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    R09: Relasi dikirim sebelum dokumennya ada, lalu PATCH extraction mengisi kunci_identitas = kunci itu.
    Ekspektasi: status langsung dihitung saat kunci terisi.
    """
    target_key = "POJK|88|2020"

    # 1. Kirim relasi dulu
    resp_rel = client.post(
        "/api/v1/internal/relations",
        json={
            "relations": [
                {"src": "POJK|10|2025", "dst": target_key, "rel": "MENCABUT", "sebagian": 0},
            ]
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp_rel.status_code == 200

    # 2. Buat dokumen baru tanpa identity_key dan status tidak_diketahui
    doc_new = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Regulasi Baru",
        reg_num=None,
        identity_key=None,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
    )

    # 3. PATCH extraction mengisi identity_key
    resp_extract = client.patch(
        f"/api/v1/internal/documents/{doc_new.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={
            "identity_key": target_key,
            "nomor_peraturan": "88",
            "jenis_peraturan": "POJK",
        },
    )
    assert resp_extract.status_code == 200

    db_session.refresh(doc_new)
    assert doc_new.identity_key == target_key
    assert doc_new.status_keberlakuan == StatusKeberlakuan.dicabut
    assert doc_new.status_source == "relasi"


def test_r10_get_versioning_sorted_and_resolved(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    R10: GET /documents/{A}/versi dengan 3 pengubah tahun 2020/2022/2024 (satu di antaranya ada di KB).
    Ekspektasi: diubah_oleh terurut, perubahan_ke 1/2/3, document_id hanya terisi untuk yang ada di KB.
    """
    doc_a = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Induk A",
        identity_key="POJK|100|2019",
        status_keberlakuan=StatusKeberlakuan.diubah,
    )

    # Buat satu dokumen pengubah yang ada di KB (POJK|5|2022)
    doc_mod2 = _seed_test_doc(
        db_session,
        test_storage,
        title="Perubahan Kedua POJK 100",
        identity_key="POJK|5|2022",
        status_keberlakuan=StatusKeberlakuan.berlaku,
    )

    # Simpan 3 relasi pengubah dengan urutan acak
    client.post(
        "/api/v1/internal/relations",
        json={
            "relations": [
                {"src": "POJK|8|2024", "dst": "POJK|100|2019", "rel": "MENGUBAH", "pasal_terkait": "Pasal 10"},
                {"src": "POJK|1|2020", "dst": "POJK|100|2019", "rel": "MENGUBAH", "pasal_terkait": "Pasal 2"},
                {"src": "POJK|5|2022", "dst": "POJK|100|2019", "rel": "MENGUBAH", "pasal_terkait": "Pasal 5"},
            ]
        },
        headers=INTERNAL_HEADERS,
    )

    resp = client.get(f"/api/v1/documents/{doc_a.id}/versi")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["document_id"] == doc_a.id
    assert data["identity_key"] == "POJK|100|2019"

    diubah = data["diubah_oleh"]
    assert len(diubah) == 3

    # Harus terurut 2020 -> 2022 -> 2024
    assert diubah[0]["key"] == "POJK|1|2020"
    assert diubah[0]["perubahan_ke"] == 1
    assert diubah[0]["document_id"] is None
    assert diubah[0]["judul"] is None

    assert diubah[1]["key"] == "POJK|5|2022"
    assert diubah[1]["perubahan_ke"] == 2
    assert diubah[1]["document_id"] == doc_mod2.id
    assert diubah[1]["judul"] == doc_mod2.title

    assert diubah[2]["key"] == "POJK|8|2024"
    assert diubah[2]["perubahan_ke"] == 3
    assert diubah[2]["document_id"] is None

    # Uji juga endpoint versi dari dokumen pengubah (doc_mod2) untuk mengecek induk
    resp_mod = client.get(f"/api/v1/documents/{doc_mod2.id}/versi")
    assert resp_mod.status_code == 200
    induk_list = resp_mod.json()["induk"]
    assert len(induk_list) == 1
    assert induk_list[0]["key"] == "POJK|100|2019"
    assert induk_list[0]["perubahan_ke"] == 2
    assert induk_list[0]["document_id"] == doc_a.id


def test_r11_get_versioning_non_public_modifier_restricted_in_protect_mode(
    client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch
):
    """
    R11: GET /versi di mana pengubahnya dokumen non-publik dalam mode lindung.
    Ekspektasi: document_id dan judul null, key tetap ada.
    """
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)
    monkeypatch.setattr(settings, "auth_enabled", False)

    doc_induk = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK Induk Publik",
        identity_key="POJK|200|2020",
        access_classification=KlasifikasiAkses.publik,
    )

    doc_non_publik = _seed_test_doc(
        db_session,
        test_storage,
        title="Draft Kajian Rahasia",
        identity_key="POJK|201|2023",
        access_classification=KlasifikasiAkses.non_publik,
    )

    client.post(
        "/api/v1/internal/relations",
        json={
            "relations": [
                {"src": "POJK|201|2023", "dst": "POJK|200|2020", "rel": "MENGUBAH"},
            ]
        },
        headers=INTERNAL_HEADERS,
    )

    resp = client.get(f"/api/v1/documents/{doc_induk.id}/versi")
    assert resp.status_code == 200
    diubah = resp.json()["diubah_oleh"]
    assert len(diubah) == 1
    assert diubah[0]["key"] == "POJK|201|2023"
    assert diubah[0]["document_id"] is None
    assert diubah[0]["judul"] is None

    # Jika dokumen induk sendiri non-publik, maka 403
    resp_induk_np = client.get(f"/api/v1/documents/{doc_non_publik.id}/versi")
    assert resp_induk_np.status_code == 403


def test_r12_get_versioning_without_identity_key_returns_empty_and_note(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    R12: GET /versi dokumen tanpa identity_key -> 200, daftar kosong, catatan menjelaskan.
    """
    doc_no_key = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Tanpa Key",
        reg_num=None,
        identity_key=None,
    )

    resp = client.get(f"/api/v1/documents/{doc_no_key.id}/versi")
    assert resp.status_code == 200
    data = resp.json()
    assert data["identity_key"] is None
    assert data["induk"] == []
    assert data["diubah_oleh"] == []
    assert data["dicabut_oleh"] == []
    assert data["mencabut"] == []
    assert "belum memiliki kunci identitas" in data["catatan"]


def test_r13_lowercase_relation_and_boolean_partial_accepted(client: TestClient, db_session: Session):
    """
    R13: rel huruf kecil ("mencabut") dan sebagian bool diterima.
    """
    resp = client.post(
        "/api/v1/internal/relations",
        json={
            "relations": [
                {"src": "POJK|50|2025", "dst": "POJK|40|2020", "rel": "mencabut", "sebagian": True},
            ]
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 1


def test_r14_forced_error_in_recompute_status_does_not_fail_patch_extraction(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    R14: Galat dipaksa di recompute_status saat PATCH extraction -> PATCH tetap 200.
    """
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Uji R14",
        identity_key="POJK|999|2024",
    )

    with patch("app.routers.internal.recompute_status", side_effect=RuntimeError("Simulated recompute error")):
        resp = client.patch(
            f"/api/v1/internal/documents/{doc.id}/extraction",
            headers=INTERNAL_HEADERS,
            json={
                "jenis_peraturan": "POJK",
                "nomor_peraturan": "999",
            },
        )
        assert resp.status_code == 200
