"""
tests/test_qa_nomor_tahun.py
Pengujian QA lanjutan: Tahun tidak boleh hilang saat nomor peraturan dibersihkan.
Kasus Uji: Q01 - Q06.
"""
from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import Document
from app.models.category import Category
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
)
from app.services.naming_service import (
    NamingInput,
    build_standard_filename,
    split_redundant_year,
)
from app.services.storage_service import StorageService
from tests.conftest import make_pdf

INTERNAL_HEADERS = {"X-Internal-API-Key": settings.internal_api_key}


def _seed_doc(
    db: Session,
    storage: StorageService,
    title: str = "Dokumen Regulasi Uji",
    reg_num: str | None = None,
    reg_type: str = "POJK",
    reg_year: int | None = None,
    identity_key: str | None = None,
) -> Document:
    cat = db.query(Category).filter(Category.name == reg_type).first()
    pdf_bytes = make_pdf(f"Konten PDF untuk {title}")
    rel_path = storage.save_pdf(pdf_bytes, filename_hint=f"{title.replace(' ', '_').lower()}.pdf", subdir="pdf/_inbox")

    doc = Document(
        title=title,
        regulation_number=reg_num,
        regulation_type=reg_type,
        release_date=date(reg_year, 1, 1) if reg_year else None,
        regulation_year=reg_year,
        file_path_pdf=rel_path,
        file_hash=f"hash_{title.replace(' ', '_').lower()}_{id(pdf_bytes)}",
        file_size_bytes=len(pdf_bytes),
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.diproses,
        is_active=True,
        category_id=cat.id if cat else None,
        identity_key=identity_key,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_q01_split_redundant_year_cases():
    """Q01: split_redundant_year untuk berbagai variasi format nomor dan None."""
    assert split_redundant_year("91 Tahun 2026") == ("91", 2026)
    assert split_redundant_year("PADK 15 Tahun 2026") == ("15", 2026)
    assert split_redundant_year("Nomor 92 Tahun 2026") == ("92", 2026)
    assert split_redundant_year("11/POJK.03/2022") == ("11/POJK.03/2022", None)
    assert split_redundant_year(None) == (None, None)
    assert split_redundant_year("") == (None, None)
    assert split_redundant_year("   ") == (None, None)


def test_q02_patch_extraction_populates_year_and_identity_key(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    Q02: PATCH extraction: jenis_peraturan=POJK, nomor_peraturan="91 Tahun 2026",
    tanpa tanggal_terbit, dokumen tanpa tahun.
    Ekspektasi: regulation_number="91", regulation_year=2026, identity_key="POJK|91|2026".
    """
    doc = _seed_doc(db_session, test_storage, title="Peraturan Uji Q02", reg_num=None, reg_type="POJK", reg_year=None)

    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={
            "jenis_peraturan": "POJK",
            "nomor_peraturan": "91 Tahun 2026",
        },
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.regulation_number == "91"
    assert doc.regulation_year == 2026
    assert doc.identity_key == "POJK|91|2026"


def test_q03_patch_extraction_keeps_existing_year(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    Q03: Sama dengan Q02, tetapi dokumen sudah punya regulation_year=2025.
    Ekspektasi: nomor "91", tahun tetap 2025, identity_key="POJK|91|2025".
    """
    doc = _seed_doc(db_session, test_storage, title="Peraturan Uji Q03", reg_num=None, reg_type="POJK", reg_year=2025)

    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_HEADERS,
        json={
            "jenis_peraturan": "POJK",
            "nomor_peraturan": "91 Tahun 2026",
        },
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.regulation_number == "91"
    assert doc.regulation_year == 2025
    assert doc.identity_key == "POJK|91|2025"


def test_q04_patch_metadata_populates_year_and_recomputes_key(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    Q04: Koreksi metadata regulation_number="15 Tahun 2026" pada dokumen tanpa tahun.
    Ekspektasi: nomor "15", tahun 2026, kunci dihitung ulang ("PADK|15|2026").
    """
    doc = _seed_doc(db_session, test_storage, title="Peraturan Uji Q04", reg_num=None, reg_type="PADK", reg_year=None)

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={
            "regulation_number": "15 Tahun 2026",
        },
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.regulation_number == "15"
    assert doc.regulation_year == 2026
    assert doc.identity_key == "PADK|15|2026"


def test_q05_patch_metadata_explicit_year_wins(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    Q05: Koreksi metadata yang mengirim regulation_number="15 Tahun 2026" dan regulation_year=2024 sekaligus.
    Ekspektasi: tahun 2024 (isian pengguna menang), nomor "15", identity_key="PADK|15|2024".
    """
    doc = _seed_doc(db_session, test_storage, title="Peraturan Uji Q05", reg_num=None, reg_type="PADK", reg_year=None)

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={
            "regulation_number": "15 Tahun 2026",
            "regulation_year": 2024,
        },
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.regulation_number == "15"
    assert doc.regulation_year == 2024
    assert doc.identity_key == "PADK|15|2024"


def test_q06_naming_build_standard_filename():
    """
    Q06: Nama berkas untuk "91 Tahun 2026" tetap POJK-91-2026.pdf (N15 tetap lulus).
    """
    inp = NamingInput(
        title="Penyelenggaraan Usaha Bank",
        regulation_type="POJK",
        regulation_number="91 Tahun 2026",
        regulation_year=2026,
    )
    res = build_standard_filename(inp, naming_format=["jenis", "nomor", "tahun"], naming_separator="-")
    assert res == "POJK-91-2026.pdf"

    # Uji juga pola PADK 15 Tahun 2026
    inp2 = NamingInput(
        title="Wali Amanat",
        regulation_type="PADK",
        regulation_number="PADK 15 Tahun 2026",
        regulation_year=2026,
    )
    res2 = build_standard_filename(inp2, naming_format=["jenis", "nomor", "tahun"], naming_separator="-")
    assert res2 == "PADK-15-2026.pdf"


def test_q07_patch_metadata_slash_number_populates_year(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    Q07: Dokumen tanpa tahun; koreksi metadata regulation_number="11/POJK.03/2022".
    Ekspektasi: regulation_year=2022, identity_key="POJK|11|2022".
    """
    doc = _seed_doc(db_session, test_storage, title="Peraturan Uji Q07", reg_num=None, reg_type="POJK", reg_year=None)

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={
            "regulation_number": "11/POJK.03/2022",
        },
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.regulation_number == "11/POJK.03/2022"
    assert doc.regulation_year == 2022
    assert doc.identity_key == "POJK|11|2022"


def test_q08_patch_metadata_release_date_updates_year(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    Q08: Dokumen regulation_year=2021, release_date=2021-03-01; koreksi release_date=2022-05-10.
    Ekspektasi: regulation_year=2022.
    """
    doc = _seed_doc(db_session, test_storage, title="Peraturan Uji Q08", reg_num=None, reg_type="POJK", reg_year=2021)
    doc.release_date = date(2021, 3, 1)
    db_session.commit()
    db_session.refresh(doc)

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={
            "release_date": "2022-05-10",
        },
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.regulation_year == 2022


def test_q09_patch_metadata_title_without_year_keeps_existing_year(client: TestClient, db_session: Session, test_storage: StorageService):
    """
    Q09: Dokumen regulation_year=2021; koreksi title saja, yang tidak memuat tahun.
    Ekspektasi: regulation_year tetap 2021 (tidak dihapus).
    """
    doc = _seed_doc(db_session, test_storage, title="Judul Lama", reg_num=None, reg_type="POJK", reg_year=2021)

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={
            "title": "Judul Baru Tanpa Tahun Sama Sekali",
        },
    )
    assert resp.status_code == 200, resp.text
    db_session.refresh(doc)
    assert doc.title == "Judul Baru Tanpa Tahun Sama Sekali"
    assert doc.regulation_year == 2021

