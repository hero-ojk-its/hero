"""
tests/test_step19_berlaku_lampiran.py
Pengujian Tanggal Berlaku dan Penautan Lampiran Dokumen (Langkah 19).
Kasus Uji: T01 - T16.
"""
from datetime import date, timedelta
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
from scripts.recompute_status import run_recompute
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
    is_attachment: bool = False,
    attachment_label: str | None = None,
    parent_document_id: int | None = None,
    parent_identity_key: str | None = None,
    effective_date: date | None = None,
    original_filename: str | None = None,
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
        is_attachment=is_attachment,
        attachment_label=attachment_label,
        parent_document_id=parent_document_id,
        parent_identity_key=parent_identity_key,
        effective_date=effective_date,
        original_filename=original_filename or f"{title.replace(' ', '_').lower()}.pdf",
        full_text=f"Teks lengkap peraturan {title}.",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_t01_patch_extraction_past_effective_date_updates_status(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T01: PATCH extraction tanggal_berlaku = kemarin, dokumen tanpa relasi, tidak_diketahui.
    Ekspektasi: effective_date tersimpan; status berlaku, status_source=tanggal_berlaku; audit tercatat.
    """
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 11 T01",
        identity_key="POJK|11|2022",
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
    )
    yesterday = date.today() - timedelta(days=1)

    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={"tanggal_berlaku": yesterday.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.effective_date == yesterday
    assert doc.status_keberlakuan == StatusKeberlakuan.berlaku
    assert doc.status_source == "tanggal_berlaku"

    # Verifikasi jejak audit
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == STATUS_FROM_RELATION,
            AuditLog.target_resource == f"document:{doc.id}",
        )
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.detail.get("rule") == "tanggal_berlaku"
    assert audit.detail.get("after") == "berlaku"


def test_t02_future_effective_date_keeps_status(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T02: tanggal_berlaku = besok.
    Ekspektasi (Langkah 26): status menjadi belum_berlaku, status_source=tanggal_berlaku.
    """
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 12 T02",
        identity_key="POJK|12|2022",
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
    )
    tomorrow = date.today() + timedelta(days=1)

    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={"tanggal_berlaku": tomorrow.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.effective_date == tomorrow
    assert doc.status_keberlakuan == StatusKeberlakuan.belum_berlaku
    assert doc.status_source == "tanggal_berlaku"


def test_t03_manual_status_preserved_with_past_effective_date(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T03: Dokumen manual dicabut, lalu effective_date lampau dikirim.
    Ekspektasi: tetap dicabut / manual.
    """
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 13 T03",
        identity_key="POJK|13|2022",
        status_keberlakuan=StatusKeberlakuan.dicabut,
        status_source="manual",
    )
    past_date = date.today() - timedelta(days=10)

    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={"tanggal_berlaku": past_date.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.effective_date == past_date
    assert doc.status_keberlakuan == StatusKeberlakuan.dicabut
    assert doc.status_source == "manual"


def test_t04_full_repeal_relation_beats_past_effective_date(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T04: Ada relasi masuk MENCABUT penuh + effective_date lampau.
    Ekspektasi: dicabut (relasi menang).
    """
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 14 T04",
        identity_key="POJK|14|2022",
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
    )

    # Tambah relasi pencabutan
    rel = DocumentRelation(
        source_key="POJK|99|2025",
        target_key="POJK|14|2022",
        relation=JenisRelasi.mencabut,
        partial=False,
    )
    db_session.add(rel)
    db_session.commit()

    past_date = date.today() - timedelta(days=5)
    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={"tanggal_berlaku": past_date.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.status_keberlakuan == StatusKeberlakuan.dicabut
    assert doc.status_source == "relasi"


def test_t05_document_without_identity_key_applies_effective_date(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T05: Dokumen tanpa identity_key + effective_date lampau.
    Ekspektasi: berlaku (status_source=tanggal_berlaku).
    """
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Tanpa Kunci T05",
        reg_num=None,
        identity_key=None,
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
    )
    doc.identity_key = None
    db_session.commit()

    past_date = date.today() - timedelta(days=2)
    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={"tanggal_berlaku": past_date.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.status_keberlakuan == StatusKeberlakuan.berlaku
    assert doc.status_source == "tanggal_berlaku"


def test_t06_metadata_correction_effective_date_and_worker_protection(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T06: Koreksi metadata effective_date tersimpan, status dihitung ulang;
    worker berikutnya tidak bisa menimpanya (ignored_fields).
    """
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 16 T06",
        identity_key="POJK|16|2022",
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
    )
    correct_date = date.today() - timedelta(days=20)

    # 1. Koreksi metadata oleh pengguna
    patch_resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={"effective_date": correct_date.isoformat()},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    db_session.refresh(doc)
    assert doc.effective_date == correct_date
    assert doc.status_keberlakuan == StatusKeberlakuan.berlaku
    assert doc.metadata_corrected_at is not None

    # 2. Worker mencoba mengirim effective_date berbeda
    worker_date = date.today() - timedelta(days=1)
    ext_resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={"tanggal_berlaku": worker_date.isoformat()},
    )
    assert ext_resp.status_code == 200, ext_resp.text
    res_data = ext_resp.json()
    assert "effective_date" in res_data.get("ignored_fields", [])
    db_session.refresh(doc)
    assert doc.effective_date == correct_date


def test_t07_recompute_status_script_dry_run(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T07: recompute_status.py --dry-run -> DB tidak berubah, laporan memuat kandidat.
    """
    past_date = date.today() - timedelta(days=3)
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 17 T07",
        identity_key="POJK|17|2022",
        status_keberlakuan=StatusKeberlakuan.tidak_diketahui,
        effective_date=past_date,
    )

    # Jalankan run_recompute dengan dry_run=True (apply=False)
    res = run_recompute(db_session, apply=False)
    assert res["dry_run"] is True
    assert res["changed_count"] >= 1
    found = any(item["id"] == doc.id and item["after_status"] == "berlaku" for item in res["changed_items"])
    assert found is True

    # Cek bahwa DB asli belum berubah (karena di-rollback)
    db_session.refresh(doc)
    assert doc.status_keberlakuan == StatusKeberlakuan.tidak_diketahui


def test_t08_patch_extraction_attachment_heuristics(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T08: PATCH extraction dokumen berjudul LAMPIRAN I PERATURAN OTORITAS JASA KEUANGAN NOMOR 91 …,
    jenis POJK, nomor 91, tahun 2026.
    Ekspektasi: is_attachment=True, attachment_label="Lampiran I", parent_identity_key="POJK|91|2026", identity_key=None.
    """
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Draf Dokumen",
        reg_num=None,
        identity_key=None,
    )

    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={
            "judul": "LAMPIRAN I PERATURAN OTORITAS JASA KEUANGAN NOMOR 91 TAHUN 2026",
            "jenis_peraturan": "POJK",
            "nomor_peraturan": "91",
            "tahun": 2026,
        },
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.is_attachment is True
    assert doc.attachment_label == "Lampiran I"
    assert doc.parent_identity_key == "POJK|91|2026"
    assert doc.identity_key is None


def test_t09_attachment_linking_when_parent_exists(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T09: Induk POJK 91 (POJK|91|2026) sudah ada; lampiran T08 masuk.
    Ekspektasi: parent_document_id = id induk; GET induk memuat lampiran di lampiran[].
    """
    parent = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK Nomor 91 Tahun 2026",
        reg_num="91",
        reg_type="POJK",
        reg_year=2026,
        identity_key="POJK|91|2026",
        is_attachment=False,
    )

    child = _seed_test_doc(
        db_session,
        test_storage,
        title="Draf Lampiran",
        reg_num=None,
        identity_key=None,
    )

    resp = client.patch(
        f"/api/v1/internal/documents/{child.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={
            "judul": "LAMPIRAN I PERATURAN OTORITAS JASA KEUANGAN NOMOR 91 TAHUN 2026",
            "jenis_peraturan": "POJK",
            "nomor_peraturan": "91",
            "tahun": 2026,
        },
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(child)
    assert child.parent_document_id == parent.id

    # GET induk
    get_resp = client.get(f"/api/v1/documents/{parent.id}")
    assert get_resp.status_code == 200
    p_data = get_resp.json()
    assert len(p_data["lampiran"]) == 1
    assert p_data["lampiran"][0]["document_id"] == child.id
    assert p_data["lampiran"][0]["attachment_label"] == "Lampiran I"


def test_t10_attachment_linked_retroactively_when_parent_arrives(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T10: Lampiran masuk lebih dulu, induk menyusul dan mendapat identity_key -> tertaut otomatis.
    """
    # 1. Lampiran masuk dulu
    child = _seed_test_doc(
        db_session,
        test_storage,
        title="LAMPIRAN II POJK 100",
        original_filename="LAMPIRAN_II_POJK_100.pdf",
        identity_key=None,
        is_attachment=True,
        attachment_label="Lampiran II",
        parent_identity_key="POJK|100|2026",
    )

    # 2. Induk menyusul via batch identity
    parent = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 100 Tahun 2026",
        identity_key=None,
        is_attachment=False,
    )

    resp = client.patch(
        "/api/v1/internal/documents/identity",
        headers=INTERNAL_HEADERS,
        json=[
            {"document_id": parent.id, "identity_key": "POJK|100|2026"},
        ],
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(child)
    assert child.parent_document_id == parent.id


def test_t11_parent_and_attachment_same_number_no_deactivation(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T11: Induk dan lampiran dengan nomor sama -> tidak ada yang dinonaktifkan oleh cek duplikat.
    """
    parent = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK Nomor 95 Tahun 2026",
        reg_num="95",
        identity_key="POJK|95|2026",
        is_active=True,
        is_attachment=False,
    )

    child = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Lampiran Uji",
        reg_num=None,
        identity_key=None,
        is_active=True,
    )

    # Worker ekstrak lampiran dengan nomor dan tahun yang sama dengan induk
    resp = client.patch(
        f"/api/v1/internal/documents/{child.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={
            "judul": "LAMPIRAN I POJK NOMOR 95 TAHUN 2026",
            "jenis_peraturan": "POJK",
            "nomor_peraturan": "95",
            "tahun": 2026,
        },
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(parent)
    db_session.refresh(child)

    assert parent.is_active is True
    assert child.is_active is True
    assert child.is_attachment is True
    assert child.parent_document_id == parent.id
    assert child.identity_key is None


def test_t12_metadata_correction_parent_document_id_validations(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T12: Koreksi metadata parent_document_id:
    - dirinya sendiri -> 422
    - dokumen lampiran lain -> 422
    - id tidak ada -> 422
    """
    doc_a = _seed_test_doc(db_session, test_storage, title="Dok A", identity_key="POJK|120|2026")
    doc_att = _seed_test_doc(
        db_session,
        test_storage,
        title="Lampiran Lain",
        identity_key=None,
        is_attachment=True,
    )

    # 1. Dirinya sendiri
    r1 = client.patch(
        f"/api/v1/documents/{doc_a.id}/metadata",
        json={"parent_document_id": doc_a.id},
    )
    assert r1.status_code == 422, r1.text

    # 2. Dokumen lampiran lain
    r2 = client.patch(
        f"/api/v1/documents/{doc_a.id}/metadata",
        json={"parent_document_id": doc_att.id},
    )
    assert r2.status_code == 422, r2.text

    # 3. ID tidak ada
    r3 = client.patch(
        f"/api/v1/documents/{doc_a.id}/metadata",
        json={"parent_document_id": 999999},
    )
    assert r3.status_code == 422, r3.text


def test_t13_metadata_correction_unset_attachment_clears_links(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T13: Koreksi metadata is_attachment=false -> label dan tautan induk dikosongkan.
    """
    parent = _seed_test_doc(db_session, test_storage, title="Induk", identity_key="POJK|130|2026")
    child = _seed_test_doc(
        db_session,
        test_storage,
        title="Lampiran",
        identity_key=None,
        is_attachment=True,
        attachment_label="Lampiran I",
        parent_document_id=parent.id,
        parent_identity_key="POJK|130|2026",
    )

    resp = client.patch(
        f"/api/v1/documents/{child.id}/metadata",
        json={"is_attachment": False},
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(child)
    assert child.is_attachment is False
    assert child.parent_document_id is None
    assert child.parent_identity_key is None
    assert child.attachment_label is None


def test_t14_worker_explicit_lampiran_dari_and_label(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T14: Worker mengirim lampiran_dari="POJK|92|2026", label_lampiran="Lampiran II".
    Ekspektasi: tersimpan; tertaut bila induknya ada.
    """
    parent = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 92",
        identity_key="POJK|92|2026",
        is_attachment=False,
    )
    child = _seed_test_doc(
        db_session,
        test_storage,
        title="File Tanpa Kata Khusus",
        identity_key=None,
    )

    resp = client.patch(
        f"/api/v1/internal/documents/{child.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={
            "lampiran_dari": "POJK|92|2026",
            "label_lampiran": "Lampiran II",
        },
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(child)
    assert child.is_attachment is True
    assert child.attachment_label == "Lampiran II"
    assert child.parent_identity_key == "POJK|92|2026"
    assert child.parent_document_id == parent.id


def test_t15_get_documents_filter_lampiran(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T15: GET /documents?lampiran=false -> lampiran tidak tercantum.
    """
    parent = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK 150 Induk",
        identity_key="POJK|150|2026",
        is_attachment=False,
    )
    child = _seed_test_doc(
        db_session,
        test_storage,
        title="Lampiran POJK 150",
        identity_key=None,
        is_attachment=True,
        parent_document_id=parent.id,
    )

    resp = client.get("/api/v1/documents?lampiran=false")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    ids = [i["id"] for i in items]
    assert parent.id in ids
    assert child.id not in ids

    resp_att = client.get("/api/v1/documents?lampiran=true")
    assert resp_att.status_code == 200, resp_att.text
    att_ids = [i["id"] for i in resp_att.json()["items"]]
    assert child.id in att_ids
    assert parent.id not in att_ids


def test_t16_attachment_from_non_public_parent_in_protect_mode_returns_null_induk(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T16: Lampiran dari induk non-publik, mode lindung -> induk bernilai null.
    """
    parent = _seed_test_doc(
        db_session,
        test_storage,
        title="POJK Rahasia",
        identity_key="POJK|160|2026",
        access_classification=KlasifikasiAkses.non_publik,
        is_attachment=False,
    )
    child = _seed_test_doc(
        db_session,
        test_storage,
        title="Lampiran Publik dari Induk Rahasia",
        identity_key=None,
        access_classification=KlasifikasiAkses.publik,
        is_attachment=True,
        parent_document_id=parent.id,
    )

    orig_protect = settings.protect_non_public_when_auth_disabled
    orig_auth = settings.auth_enabled
    try:
        settings.protect_non_public_when_auth_disabled = True
        settings.auth_enabled = False

        resp = client.get(f"/api/v1/documents/{child.id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["is_attachment"] is True
        assert data["induk"] is None
    finally:
        settings.protect_non_public_when_auth_disabled = orig_protect
        settings.auth_enabled = orig_auth


def test_t17_detect_attachment_heuristic_filename_boundary():
    """
    T17: Uji unit detect_attachment_heuristic(title=None, original_filename=...)
    Nama berkas hanya dianggap lampiran bila diawali kata LAMPIRAN (mengabaikan awalan non-huruf).
    """
    from app.services.attachment_service import detect_attachment_heuristic

    cases = [
        ("LAMPIRAN_I.pdf", True, "Lampiran I"),
        ("Lampiran II POJK 91.pdf", True, "Lampiran II"),
        ("01_LAMPIRAN_III.pdf", True, "Lampiran III"),
        ("lampiran.pdf", True, "Lampiran"),
        ("POJK 91 Tahun 2026 beserta Lampiran.pdf", False, None),
        ("SEOJK_7_2026_dan_lampiran.pdf", False, None),
        ("Lampirannya.pdf", False, None),
    ]
    for filename, expected_is_att, expected_label in cases:
        is_att, label = detect_attachment_heuristic(title=None, original_filename=filename)
        assert is_att == expected_is_att, f"Gagal pada {filename}: is_attachment expected {expected_is_att}, got {is_att}"
        assert label == expected_label, f"Gagal pada {filename}: label expected {expected_label}, got {label}"


def test_t18_patch_extraction_main_doc_with_lampiran_in_filename(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    T18: PATCH extraction dokumen dengan original_filename="POJK 91 Tahun 2026 beserta Lampiran.pdf"
    dan judul biasa (bukan diawali LAMPIRAN).
    Ekspektasi: is_attachment=False dan identity_key tetap terbentuk (POJK|91|2026).
    """
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Draf Peraturan OJK",
        original_filename="POJK 91 Tahun 2026 beserta Lampiran.pdf",
        identity_key=None,
    )
    payload = {
        "title": "Peraturan Otoritas Jasa Keuangan Nomor 91/POJK.03/2026 tentang Tata Kelola",
        "regulation_type": "POJK",
        "regulation_number": "91",
        "regulation_year": 2026,
    }
    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        json=payload,
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.is_attachment is False
    assert doc.identity_key == "POJK|91|2026"

    # Verifikasi juga respons GET dokumen
    res_get = client.get(f"/api/v1/documents/{doc.id}")
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get["is_attachment"] is False
    assert data_get["identity_key"] == "POJK|91|2026"


