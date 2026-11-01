"""
tests/test_step34_audit_keamanan.py
Pengujian HERO Backend Langkah 34: Detail Audit Log Lengkap, Lockout Login, dan Pengamanan Admin (P01 - P18).
"""
import io
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.models.document import Document
from app.models.scraping_source import ScrapingSource
from app.models.scan_session import ScanSession
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.models.audit_log import AuditLog
from app.models.percobaan_login import PercobaanLogin
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
    JenisKegagalan,
    StatusTindakLanjut,
    JenisSumber,
    JenisJobIngest,
    StatusJobIngest,
)
from app.routers.auth import ALGORITHM
from app.core.permissions import PeranPengguna
from app.services.failure_service import FailureService
from tests.conftest import make_pdf
from scripts.buka_kunci_login import buka_kunci


INTERNAL_KEY_HEADER = {"X-Internal-API-Key": settings.internal_api_key}


def make_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=1)
    return jwt.encode({"sub": username, "role": role, "exp": expire}, settings.secret_key, algorithm=ALGORITHM)


@pytest.fixture
def test_user_analis(db_session: Session) -> User:
    plain = "TestPass123!"
    hashed = bcrypt.hashpw(plain[:72].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(
        username="analis_step34",
        hashed_password=hashed,
        role=PeranPengguna.analis.value,
        nama_lengkap="Analis Step 34",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_user_admin(db_session: Session) -> User:
    plain = "AdminPass123!"
    hashed = bcrypt.hashpw(plain[:72].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(
        username="admin_step34",
        hashed_password=hashed,
        role=PeranPengguna.admin_sistem.value,
        nama_lengkap="Admin Sistem Step 34",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


# ============================================================================
# P01: Upload PDF baru mencatat detail audit lengkap tanpa menyimpan teks isi
# ============================================================================
def test_p01_upload_pdf_audit_detail_lengkap(client: TestClient, db_session: Session):
    pdf_bytes = make_pdf("Naskah Regulasi Perbankan Syariah Nomor 99 Tahun 2026")
    files = [("files", ("pojk_99_2026.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "title": "POJK Nomor 99 Tahun 2026 tentang Perbankan Syariah",
    }

    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200, res.text
    assert res.json()["success_count"] == 1

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "UPLOAD_DOCUMENT")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.detail is not None

    d = audit.detail
    assert d.get("nama_berkas_asli") == "pojk_99_2026.pdf"
    assert d.get("ukuran_byte") == len(pdf_bytes)
    assert "sha256" in d
    assert d.get("hasil") == "baru"
    assert "document_id" in d

    # Pastikan teks lengkap / body mentah TIDAK disimpan dalam detail audit
    assert "raw_content" not in d
    assert "full_text" not in d
    assert "isi_lengkap" not in d


# ============================================================================
# P02: Upload duplikat mencatat detail duplikat_dari dan tidak menambah doc ganda
# ============================================================================
def test_p02_upload_duplikat_audit_detail(client: TestClient, db_session: Session):
    pdf_bytes = make_pdf("Konten Identik Regulasi Pencegahan Fraud")
    files1 = [("files", ("fraud_01.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    data1 = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "title": "Aturan Anti Fraud 2026",
    }
    res1 = client.post("/api/v1/ingest/upload-pdf", files=files1, data=data1)
    assert res1.status_code == 200
    doc_id_1 = res1.json()["details"][0]["document_id"]

    # Unggah berkas identik kedua
    files2 = [("files", ("fraud_02.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    data2 = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "title": "Aturan Anti Fraud 2026 Duplikat",
    }
    res2 = client.post("/api/v1/ingest/upload-pdf", files=files2, data=data2)
    assert res2.status_code == 200
    assert res2.json()["duplicate_count"] == 1

    # Ambil audit UPLOAD_DOCUMENT terbaru
    audits = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "UPLOAD_DOCUMENT")
        .order_by(AuditLog.id.desc())
        .all()
    )
    assert len(audits) >= 2
    latest_audit = audits[0]
    assert latest_audit.detail is not None
    assert latest_audit.detail.get("hasil") == "duplikat"
    duplikat_dari = latest_audit.detail.get("duplikat_dari")
    assert duplikat_dari is not None
    assert duplikat_dari == doc_id_1 or (isinstance(duplikat_dari, dict) and duplikat_dari.get("id") == doc_id_1)


# ============================================================================
# P03: OPEN_PDF dan DOWNLOAD_PDF mencatat detail audit
# ============================================================================
def test_p03_open_dan_download_pdf_audit_detail(client: TestClient, db_session: Session):
    pdf_bytes = make_pdf("Dokumen Uji Open dan Download PDF")
    files = [("files", ("dok_uji_view.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "title": "POJK Uji Tampilan PDF",
    }
    res_up = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res_up.status_code == 200
    doc_id = res_up.json()["details"][0]["document_id"]

    # Buka PDF (inline)
    res_open = client.get(f"/api/v1/documents/{doc_id}/pdf")
    assert res_open.status_code == 200

    audit_open = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "OPEN_PDF")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit_open is not None
    assert audit_open.detail is not None
    assert audit_open.detail.get("document_id") == doc_id
    assert "judul" in audit_open.detail
    assert "nama_berkas" in audit_open.detail

    # Unduh PDF (attachment)
    res_dl = client.get(f"/api/v1/documents/{doc_id}/pdf?download=true")
    assert res_dl.status_code == 200

    audit_dl = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "DOWNLOAD_PDF")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit_dl is not None
    assert audit_dl.detail is not None
    assert audit_dl.detail.get("document_id") == doc_id
    assert "judul" in audit_dl.detail
    assert "nama_berkas" in audit_dl.detail


# ============================================================================
# P04: DELETE_SOURCE mencatat detail sumber sebelum dihapus
# ============================================================================
def test_p04_delete_source_audit_detail(client: TestClient, db_session: Session):
    source = ScrapingSource(
        name="Sumber OJK Step 34",
        url="https://ojk.go.id/step34",
        source_type=JenisSumber.situs_web,
        is_active=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    source_id = source.id

    # Tambahkan 1 scan session terkait
    sess = ScanSession(source_id=source_id, start_url="https://ojk.go.id/step34", status="siap_dipilih")
    db_session.add(sess)
    db_session.commit()

    res = client.delete(f"/api/v1/scraping-sources/{source_id}")
    assert res.status_code == 200

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "DELETE_SOURCE")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.detail is not None
    assert audit.detail.get("source_id") == source_id
    assert audit.detail.get("nama") == "Sumber OJK Step 34"
    assert audit.detail.get("url") == "https://ojk.go.id/step34"


# ============================================================================
# P05: UPDATE_DOCUMENT_STATUS mencatat detail sebelum & sesudah serta alasan
# ============================================================================
def test_p05_update_document_status_audit_detail(client: TestClient, db_session: Session):
    doc = Document(
        regulation_number="POJK-34/2026",
        regulation_year=2026,
        title="POJK Step 34 Status",
        file_path_pdf="pdf/dummy_step34.pdf",
        file_hash="dummyhashstep34",
        file_size_bytes=1000,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    res = client.put(
        f"/api/v1/documents/{doc.id}/status",
        json={"status_keberlakuan": "dicabut", "alasan": "Digantikan aturan baru tahun 2027"},
    )
    assert res.status_code == 200

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "UPDATE_DOCUMENT_STATUS")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.target_resource == f"document:{doc.id}"
    assert audit.detail is not None
    assert audit.detail.get("before", {}).get("status_keberlakuan") == "berlaku"
    assert audit.detail.get("after", {}).get("status_keberlakuan") == "dicabut"
    assert audit.detail.get("alasan") == "Digantikan aturan baru tahun 2027"


# ============================================================================
# P06: UPDATE_FAILURE dan RETRY_FAILURE mencatat detail audit
# ============================================================================
def test_p06_update_failure_dan_retry_failure_audit_detail(
    test_storage,
    db_session: Session,
):
    job = JobIngest(job_type=JenisJobIngest.unggah_manual, status=StatusJobIngest.selesai)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    failure = IngestFailure(
        job_id=job.id,
        original_filename="fail.pdf",
        reason_code="ekstraksi_gagal",
        message="Gagal ekstraksi teks",
        failure_type=JenisKegagalan.ekstraksi_gagal,
        is_retryable=True,
        follow_up_status=StatusTindakLanjut.belum_ditangani,
        attempt_count=0,
    )
    db_session.add(failure)
    db_session.commit()
    db_session.refresh(failure)

    svc = FailureService(db=db_session, storage=test_storage)

    # 1. Update status failure
    svc.update_status(
        failure_id=failure.id,
        status=StatusTindakLanjut.diabaikan,
        note="Dokumen corrupt tidak terpakai",
    )
    audit_update = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "UPDATE_FAILURE")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit_update is not None
    assert audit_update.detail is not None
    assert audit_update.detail.get("failure_id") == failure.id
    assert audit_update.detail.get("before", {}).get("status") == "belum_ditangani"
    assert audit_update.detail.get("after", {}).get("status") == "diabaikan"
    assert audit_update.detail.get("after", {}).get("catatan") == "Dokumen corrupt tidak terpakai"


# ============================================================================
# P07: Filter audit log (ada_detail, dari, sampai) dan endpoint GET /ringkasan
# ============================================================================
def test_p07_filter_audit_logs_dan_ringkasan(client: TestClient, db_session: Session):
    now = datetime.now(timezone.utc)
    log_detail = AuditLog(
        action="LOGIN",
        detail={"metode": "password", "hasil": "sukses"},
        timestamp=now - timedelta(hours=2),
    )
    log_no_detail = AuditLog(
        action="OPEN_PDF",
        detail=None,
        timestamp=now - timedelta(hours=1),
    )
    db_session.add_all([log_detail, log_no_detail])
    db_session.commit()

    # Query ada_detail=true
    res_true = client.get(
        "/api/v1/audit-logs/?ada_detail=true",
        headers=INTERNAL_KEY_HEADER,
    )
    assert res_true.status_code == 200
    items_true = res_true.json()
    assert any(item["action"] == "LOGIN" for item in items_true)

    # Query ada_detail=false
    res_false = client.get(
        "/api/v1/audit-logs/?ada_detail=false",
        headers=INTERNAL_KEY_HEADER,
    )
    assert res_false.status_code == 200
    items_false = res_false.json()
    assert any(item["action"] == "OPEN_PDF" for item in items_false)

    # Query ringkasan
    res_sum = client.get(
        "/api/v1/audit-logs/ringkasan",
        headers=INTERNAL_KEY_HEADER,
    )
    assert res_sum.status_code == 200
    data_sum = res_sum.json()
    assert isinstance(data_sum, list)
    assert len(data_sum) >= 2
    actions = [item["action"] for item in data_sum]
    assert "LOGIN" in actions
    assert "OPEN_PDF" in actions
    for item in data_sum:
        assert "jumlah" in item
        assert "jumlah_detail_kosong" in item
        assert "terakhir" in item


# ============================================================================
# P08: Lockout login setelah 5x gagal -> percobaan ke-6 dapat 429 + Retry-After
# ============================================================================
def test_p08_lockout_login_setelah_maksimal_gagal(
    client: TestClient,
    test_user_analis: User,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "login_maks_gagal_per_akun", 5)

    # 5 kali gagal berturut-turut
    for i in range(5):
        res = client.post(
            "/api/v1/auth/login",
            data={"username": test_user_analis.username, "password": f"WrongPass{i}!"},
        )
        assert res.status_code == 401, f"Percobaan {i+1} harus 401"

    # Percobaan ke-6 harus 429 Too Many Requests
    res_locked = client.post(
        "/api/v1/auth/login",
        data={"username": test_user_analis.username, "password": "AnyPassword!"},
    )
    assert res_locked.status_code == 429
    assert "Retry-After" in res_locked.headers
    body = res_locked.json()
    assert "terlalu banyak percobaan login" in body.get("detail", "").lower()


# ============================================================================
# P09: Username tidak ada vs password salah memberikan respons 401 identik
# ============================================================================
def test_p09_username_tidak_ada_vs_password_salah_identik(
    client: TestClient,
    test_user_analis: User,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_enabled", True)

    # User ada, password salah
    res_wrong_pw = client.post(
        "/api/v1/auth/login",
        data={"username": test_user_analis.username, "password": "SalahTotalPassword123!"},
    )
    assert res_wrong_pw.status_code == 401

    # User tidak ada
    res_non_user = client.post(
        "/api/v1/auth/login",
        data={"username": "user_pasti_tidak_ada_xyz_999", "password": "SalahTotalPassword123!"},
    )
    assert res_non_user.status_code == 401

    # Respons harus identik tanpa bocoran eksistensi username
    assert res_wrong_pw.json() == res_non_user.json()


# ============================================================================
# P10: Login sukses me-reset hitungan gagal akun
# ============================================================================
def test_p10_login_sukses_reset_hitungan_gagal(
    client: TestClient,
    test_user_analis: User,
    db_session: Session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "login_maks_gagal_per_akun", 5)

    # Gagal 3 kali
    for i in range(3):
        res = client.post(
            "/api/v1/auth/login",
            data={"username": test_user_analis.username, "password": f"WrongPass{i}!"},
        )
        assert res.status_code == 401

    # Login sukses ke-4
    res_ok = client.post(
        "/api/v1/auth/login",
        data={"username": test_user_analis.username, "password": "TestPass123!"},
    )
    assert res_ok.status_code == 200

    # Catatan kegagalan akun harus terhapus/direset
    rec = (
        db_session.query(PercobaanLogin)
        .filter(PercobaanLogin.kunci == f"u:{test_user_analis.username}")
        .first()
    )
    assert rec is None or rec.jumlah_gagal == 0

    # Dapat gagal 4 kali lagi tanpa langsung terkunci
    for i in range(4):
        res = client.post(
            "/api/v1/auth/login",
            data={"username": test_user_analis.username, "password": f"WrongPassAgain{i}!"},
        )
        assert res.status_code == 401


# ============================================================================
# P11: Manipulasi terkunci_sampai yang sudah lewat memungkinkan login kembali
# ============================================================================
def test_p11_manipulasi_terkunci_sampai_lewat_bisa_login(
    client: TestClient,
    test_user_analis: User,
    db_session: Session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_enabled", True)

    # Buat catatan terkunci di masa lalu (1 menit lalu)
    past_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    rec = PercobaanLogin(
        kunci=f"u:{test_user_analis.username}",
        jumlah_gagal=5,
        jendela_mulai=past_time - timedelta(minutes=15),
        terkunci_sampai=past_time,
        diperbarui=past_time,
    )
    db_session.add(rec)
    db_session.commit()

    # Login dengan password benar langsung berhasil
    res = client.post(
        "/api/v1/auth/login",
        data={"username": test_user_analis.username, "password": "TestPass123!"},
    )
    assert res.status_code == 200


# ============================================================================
# P12: Lockout berbasis IP ketika banyak akun gagal dari IP yang sama
# ============================================================================
def test_p12_lockout_berbasis_ip(
    client: TestClient,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "login_maks_gagal_per_ip", 3)

    # 3 kegagalan dari IP yang sama menggunakan username acak berbeda
    for i in range(3):
        res = client.post(
            "/api/v1/auth/login",
            data={"username": f"random_user_{i}", "password": "WrongPassword!"},
        )
        assert res.status_code == 401

    # Percobaan ke-4 dari IP yang sama harus 429
    res_locked = client.post(
        "/api/v1/auth/login",
        data={"username": "another_random_user", "password": "AnyPassword!"},
    )
    assert res_locked.status_code == 429
    assert "terlalu banyak percobaan login" in res_locked.json().get("detail", "").lower()


# ============================================================================
# P13: Audit LOGIN_FAILED dan LOGIN_LOCKED tidak memuat password atau hash
# ============================================================================
def test_p13_audit_login_failed_dan_login_locked_tanpa_password(
    client: TestClient,
    test_user_analis: User,
    db_session: Session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "login_maks_gagal_per_akun", 2)

    secret_guess = "MyUltraSecretPassword999!"
    # Gagal 1 & 2
    client.post("/api/v1/auth/login", data={"username": test_user_analis.username, "password": secret_guess})
    client.post("/api/v1/auth/login", data={"username": test_user_analis.username, "password": secret_guess})
    # Ke-3 memicu locked
    client.post("/api/v1/auth/login", data={"username": test_user_analis.username, "password": secret_guess})

    audits = (
        db_session.query(AuditLog)
        .filter(AuditLog.action.in_(["LOGIN_FAILED", "LOGIN_LOCKED"]))
        .all()
    )
    assert len(audits) >= 2
    for a in audits:
        detail_str = str(a.detail)
        assert secret_guess not in detail_str
        assert "password" not in detail_str.lower() or "password salah" in detail_str.lower()
        assert "hashed_password" not in detail_str


# ============================================================================
# P14: AUTH_ENABLED=false menolak /users dan /audit-logs dengan 403 butuh_login
# ============================================================================
def test_p14_auth_mati_admin_endpoints_403(
    client: TestClient,
    db_session: Session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "admin_butuh_kunci_saat_auth_mati", True)

    # GET /users/
    res_users = client.get("/api/v1/users/")
    assert res_users.status_code == 403
    assert res_users.json().get("detail", {}).get("code") == "butuh_login"

    # POST /users/ tidak boleh membuat akun
    res_create = client.post(
        "/api/v1/users/",
        json={
            "username": "hacker_user",
            "password": "HackerPassword123!",
            "nama_lengkap": "Hacker",
            "role": "admin_sistem",
        },
    )
    assert res_create.status_code == 403
    user_created = db_session.query(User).filter(User.username == "hacker_user").first()
    assert user_created is None

    # GET /audit-logs/
    res_audit = client.get("/api/v1/audit-logs/")
    assert res_audit.status_code == 403
    assert res_audit.json().get("detail", {}).get("code") == "butuh_login"


# ============================================================================
# P15: Header X-Internal-API-Key membuka akses endpoint admin saat AUTH_ENABLED=false
# ============================================================================
def test_p15_internal_api_key_membuka_akses_saat_auth_mati(
    client: TestClient,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "admin_butuh_kunci_saat_auth_mati", True)
    monkeypatch.setattr(settings, "internal_api_key", "secret-key-internal-123")

    # Header salah -> 403
    res_bad = client.get("/api/v1/users/", headers={"X-Internal-API-Key": "wrong-key"})
    assert res_bad.status_code == 403

    # Header benar -> 200
    res_ok = client.get("/api/v1/users/", headers={"X-Internal-API-Key": "secret-key-internal-123"})
    assert res_ok.status_code == 200


# ============================================================================
# P16: AUTH_ENABLED=true mematuhi sistem otorisasi peran lama (JWT)
# ============================================================================
def test_p16_auth_hidup_perilaku_peran_tetap(
    client: TestClient,
    test_user_admin: User,
    test_user_analis: User,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_enabled", True)

    # Tanpa token -> 401
    res_no_auth = client.get("/api/v1/users/")
    assert res_no_auth.status_code == 401

    # Login analis (tidak punya hak PENGGUNA_KELOLA)
    analis_token = make_token(test_user_analis.username, test_user_analis.role)
    res_analis = client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {analis_token}"},
    )
    assert res_analis.status_code == 403

    # Login admin_sistem (punya hak PENGGUNA_KELOLA)
    admin_token = make_token(test_user_admin.username, test_user_admin.role)
    res_admin = client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin.status_code == 200


# ============================================================================
# P17: ADMIN_BUTUH_KUNCI_SAAT_AUTH_MATI=false tetap membuka akses (legacy mode)
# ============================================================================
def test_p17_admin_butuh_kunci_saat_auth_mati_false_legacy(
    client: TestClient,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "admin_butuh_kunci_saat_auth_mati", False)

    res = client.get("/api/v1/users/")
    assert res.status_code == 200


# ============================================================================
# P18: Skrip scripts/buka_kunci_login.py dry-run vs apply
# ============================================================================
def test_p18_skrip_buka_kunci_login(db_session: Session):
    lock_time = datetime.now(timezone.utc) + timedelta(minutes=15)
    rec_user = PercobaanLogin(
        kunci="u:user_terkunci_p18",
        jumlah_gagal=5,
        jendela_mulai=datetime.now(timezone.utc),
        terkunci_sampai=lock_time,
        diperbarui=datetime.now(timezone.utc),
    )
    rec_ip = PercobaanLogin(
        kunci="ip:192.168.1.99",
        jumlah_gagal=30,
        jendela_mulai=datetime.now(timezone.utc),
        terkunci_sampai=lock_time,
        diperbarui=datetime.now(timezone.utc),
    )
    db_session.add_all([rec_user, rec_ip])
    db_session.commit()

    # Dry-run: tidak boleh merubah database
    buka_kunci(username="user_terkunci_p18", apply=False, db=db_session)
    db_session.refresh(rec_user)
    assert rec_user.jumlah_gagal == 5
    assert rec_user.terkunci_sampai is not None

    # Apply: buka kunci username
    buka_kunci(username="user_terkunci_p18", apply=True, db=db_session)
    db_session.refresh(rec_user)
    assert rec_user.jumlah_gagal == 0
    assert rec_user.terkunci_sampai is None

    # Apply: buka kunci IP
    buka_kunci(ip="192.168.1.99", apply=True, db=db_session)
    db_session.refresh(rec_ip)
    assert rec_ip.jumlah_gagal == 0
    assert rec_ip.terkunci_sampai is None


# ============================================================================
# P19: Dua pemanggilan _catat_kegagalan_login di session terpisah aman dari IntegrityError
# ============================================================================
def test_p19_catat_kegagalan_login_konkurensi_insert_aman(db_session: Session):
    from sqlalchemy.orm import sessionmaker
    from app.routers.auth import _catat_kegagalan_login

    kunci = "u:konkurensi_test_p19"
    now = datetime.now(timezone.utc)

    db_session.query(PercobaanLogin).filter(PercobaanLogin.kunci == kunci).delete()
    db_session.commit()

    # Session 1 memanggil _catat_kegagalan_login pertama kali
    gagal1, terkunci1 = _catat_kegagalan_login(
        db_session, kunci, now, maks_gagal=5, jendela_menit=15, kunci_menit=15
    )
    db_session.commit()
    assert gagal1 == 1
    assert terkunci1 is False

    # Session 2 terpisah memanggil _catat_kegagalan_login untuk kunci yang sama
    SessionMaker = sessionmaker(bind=db_session.get_bind())
    session2 = SessionMaker()
    try:
        gagal2, terkunci2 = _catat_kegagalan_login(
            session2, kunci, now, maks_gagal=5, jendela_menit=15, kunci_menit=15
        )
        session2.commit()
        assert gagal2 == 2
        assert terkunci2 is False
    finally:
        session2.close()

    # Verifikasi akhir di basis data: tidak ada IntegrityError dan jumlah_gagal = 2
    rec = db_session.query(PercobaanLogin).filter(PercobaanLogin.kunci == kunci).first()
    assert rec is not None
    assert rec.jumlah_gagal == 2


# ============================================================================
# P20: Login username tidak ada memanggil bcrypt.checkpw (spy) tepat sekali
# ============================================================================
def test_p20_login_username_tidak_ada_memanggil_bcrypt_checkpw_sekali(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    call_count = 0
    orig_checkpw = bcrypt.checkpw

    def spy_checkpw(password, hashed_password):
        nonlocal call_count
        call_count += 1
        return orig_checkpw(password, hashed_password)

    monkeypatch.setattr(bcrypt, "checkpw", spy_checkpw)

    res = client.post(
        "/api/v1/auth/login",
        data={"username": "user_pasti_tidak_eksis_xyz_p20", "password": "RandomPassword123!"},
    )
    assert res.status_code == 401
    assert call_count == 1


# ============================================================================
# P21: Smoke S14 tanpa HERO_INTERNAL_API_KEY tidak mengirim header X-Internal-API-Key
# ============================================================================
def test_p21_smoke_s14_tanpa_hero_internal_api_key_tidak_mengirim_header(monkeypatch):
    from scripts.smoke_fase2 import run_checks

    # INTERNAL_API_KEY di-set di environment, tetapi HERO_INTERNAL_API_KEY dikosongkan
    monkeypatch.setenv("INTERNAL_API_KEY", "kunci_internal_bukan_hero")
    monkeypatch.delenv("HERO_INTERNAL_API_KEY", raising=False)

    captured_headers = []

    class MockResponse:
        status_code = 403

        def json(self):
            return {}

    class MockClient:
        def get(self, url, **kwargs):
            if "/audit-logs" in url:
                captured_headers.append(kwargs.get("headers", {}))
            return MockResponse()

    client = MockClient()
    run_checks(client, doc_id=None)

    assert len(captured_headers) >= 1
    assert "X-Internal-API-Key" not in captured_headers[0]


# ============================================================================
# P22: Buka kunci --apply mencetak gagal=<nilai lama>
# ============================================================================
def test_p22_buka_kunci_apply_mencetak_nilai_gagal_lama(capsys, db_session: Session):
    now = datetime.now(timezone.utc)
    kunci = "u:test_user_p22"
    rec = PercobaanLogin(
        kunci=kunci,
        jumlah_gagal=4,
        jendela_mulai=now,
        terkunci_sampai=now + timedelta(minutes=15),
        diperbarui=now,
    )
    db_session.merge(rec)
    db_session.commit()

    buka_kunci(username="test_user_p22", apply=True, db=db_session)
    captured = capsys.readouterr().out
    assert "[APPLY]" in captured
    assert "gagal=4" in captured
    assert "gagal=0" not in captured
