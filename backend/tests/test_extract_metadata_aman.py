"""
backend/tests/test_extract_metadata_aman.py
Pengujian pengamanan endpoint /extract-metadata pada router documents dan ingest:
1. Normal PDF -> 200 dan bentuk respons sesuai skema.
2. Pengguna tanpa izin -> 403 (dan 401 jika tanpa login saat AUTH_ENABLED=True).
3. Berkas melebihi batas -> 413.
4. Berkas bukan PDF (ekstensi bukan .pdf -> 400, isi bukan PDF -> 422).
5. Galat internal -> 422 tanpa bocoran detail internal ("rahasia-internal").
6. Penutupan temporary file / handle berkas saat selesai.
"""
import io
import bcrypt
import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import PeranPengguna
from app.models.user import User
from app.services import metadata_extraction_service
from tests.conftest import make_pdf

ENDPOINTS = [
    "/api/v1/documents/extract-metadata",
    "/api/v1/ingest/extract-metadata",
]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_extract_metadata_normal_pdf(client: TestClient, endpoint: str):
    """1. PDF normal -> 200 dan bentuk respons sama seperti sebelumnya."""
    pdf_bytes = make_pdf(
        "PERATURAN OTORITAS JASA KEUANGAN\n"
        "NOMOR 10/POJK.03/2026\n"
        "TENTANG\n"
        "PENYELENGGARAAN USAHA BANK DIGITAL\n"
        "Ditetapkan di Jakarta pada tanggal 15 Januari 2026"
    )
    files = {"file": ("pojk_10_2026.pdf", pdf_bytes, "application/pdf")}
    res = client.post(endpoint, files=files)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["regulation_type"] == "POJK"
    assert data["page_count"] >= 1
    assert "title" in data
    assert "regulation_number" in data
    assert "regulation_year" in data
    assert "bidang" in data
    assert "release_date" in data
    assert "raw_preview" in data


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_extract_metadata_unauthorized_user(
    auth_client: TestClient,
    db_session: Session,
    endpoint: str,
):
    """2. Pengguna tanpa izin -> 403 (dan 401 jika unauthenticated)."""
    pdf_bytes = make_pdf("PERATURAN OTORITAS JASA KEUANGAN NOMOR 1/POJK.01/2026")
    files = {"file": ("test.pdf", pdf_bytes, "application/pdf")}

    # A. Tanpa token saat AUTH_ENABLED=True -> 401
    res_no_token = auth_client.post(endpoint, files=files)
    assert res_no_token.status_code == 401

    # B. Login sebagai pilot_user (peran yang TIDAK memiliki izin DOKUMEN_UNGGAH) -> 403
    plain_pw = "PilotPass123!"
    hashed_pw = bcrypt.hashpw(plain_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = db_session.query(User).filter(User.username == "pilot_user_extract_test").first()
    if not user:
        user = User(
            username="pilot_user_extract_test",
            hashed_password=hashed_pw,
            role=PeranPengguna.pilot_user.value,
            nama_lengkap="Pilot User Test",
            unit_kerja="Uji",
            is_active=True,
        )
        db_session.add(user)
    else:
        user.role = PeranPengguna.pilot_user.value
        user.hashed_password = hashed_pw
        user.is_active = True
    db_session.commit()

    login_res = auth_client.post(
        "/api/v1/auth/login",
        data={"username": user.username, "password": plain_pw},
    )
    assert login_res.status_code == 200, login_res.text
    token = login_res.json()["access_token"]

    files = {"file": ("test.pdf", pdf_bytes, "application/pdf")}
    res_forbidden = auth_client.post(
        endpoint,
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_forbidden.status_code == 403
    assert res_forbidden.json().get("detail", {}).get("code") == "akses_ditolak"

    # C. Login sebagai analis (peran yang MEMILIKI izin DOKUMEN_UNGGAH) -> 200
    analis = db_session.query(User).filter(User.username == "analis_user_extract_test").first()
    if not analis:
        analis = User(
            username="analis_user_extract_test",
            hashed_password=hashed_pw,
            role=PeranPengguna.analis.value,
            nama_lengkap="Analis User Test",
            unit_kerja="Uji",
            is_active=True,
        )
        db_session.add(analis)
    else:
        analis.role = PeranPengguna.analis.value
        analis.hashed_password = hashed_pw
        analis.is_active = True
    db_session.commit()

    login_res_analis = auth_client.post(
        "/api/v1/auth/login",
        data={"username": analis.username, "password": plain_pw},
    )
    assert login_res_analis.status_code == 200, login_res_analis.text
    analis_token = login_res_analis.json()["access_token"]

    files = {"file": ("test.pdf", pdf_bytes, "application/pdf")}
    res_ok = auth_client.post(
        endpoint,
        files=files,
        headers={"Authorization": f"Bearer {analis_token}"},
    )
    assert res_ok.status_code == 200


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_extract_metadata_file_size_exceeded(
    client: TestClient,
    monkeypatch,
    endpoint: str,
):
    """3. Berkas melebihi batas (atur batas kecil lewat monkeypatch settings) -> 413."""
    monkeypatch.setattr(type(settings), "max_upload_bytes", property(lambda self: 100))

    pdf_bytes = make_pdf("PERATURAN OTORITAS JASA KEUANGAN NOMOR 1/POJK.01/2026")
    assert len(pdf_bytes) > 100

    files = {"file": ("oversized.pdf", pdf_bytes, "application/pdf")}
    res = client.post(endpoint, files=files)
    assert res.status_code == 413
    assert "melebihi batas maksimal" in res.json()["detail"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_extract_metadata_invalid_file_content_and_extension(
    client: TestClient,
    endpoint: str,
):
    """4. Berkas bukan PDF (ekstensi non-.pdf -> 400, konten bukan PDF -> 422)."""
    # Ekstensi bukan .pdf -> 400
    files_txt = {"file": ("dokumen.txt", b"Ini teks biasa bukan PDF", "text/plain")}
    res_txt = client.post(endpoint, files=files_txt)
    assert res_txt.status_code == 400
    assert "File harus berupa berkas PDF (.pdf)" in res_txt.json()["detail"]

    # Ekstensi .pdf tetapi isi bukan PDF (tanpa %PDF-) -> 422
    files_fake = {"file": ("palsu.pdf", b"Ini teks biasa berekstensi pdf", "application/pdf")}
    res_fake = client.post(endpoint, files=files_fake)
    assert res_fake.status_code == 422
    assert "bukan PDF yang valid" in res_fake.json()["detail"]

    # Berkas kosong (0 byte) -> 422
    files_empty = {"file": ("kosong.pdf", b"", "application/pdf")}
    res_empty = client.post(endpoint, files=files_empty)
    assert res_empty.status_code == 422
    assert "kosong (0 byte)" in res_empty.json()["detail"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_extract_metadata_internal_error_no_leak(
    client: TestClient,
    monkeypatch,
    endpoint: str,
):
    """5. Galat internal pada layanan ekstraksi -> 422 tanpa bocoran pesan internal."""
    def mock_extract_fail(content: bytes, filename: str):
        raise RuntimeError("rahasia-internal-kunci-db-12345")

    monkeypatch.setattr(
        metadata_extraction_service,
        "extract_metadata_from_pdf_content",
        mock_extract_fail,
    )

    pdf_bytes = make_pdf("PERATURAN OTORITAS JASA KEUANGAN NOMOR 1/POJK.01/2026")
    files = {"file": ("test.pdf", pdf_bytes, "application/pdf")}
    res = client.post(endpoint, files=files)

    assert res.status_code == 422
    assert "rahasia-internal" not in res.text
    assert res.json()["detail"] == "Metadata tidak dapat dibaca dari berkas ini"


def test_extract_metadata_file_cleanup():
    """6. Berkas sementara / handle file ditutup setelah request selesai."""
    pdf_bytes = make_pdf("PERATURAN OTORITAS JASA KEUANGAN NOMOR 1/POJK.01/2026")
    raw_io = io.BytesIO(pdf_bytes)
    upload_file = UploadFile(filename="test.pdf", file=raw_io)
    assert not upload_file.file.closed
    res = metadata_extraction_service.process_extract_metadata_upload(upload_file)
    assert res is not None
    assert upload_file.file.closed
