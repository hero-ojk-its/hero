"""
Pengujian Langkah 23 (US-01 #32): Manajemen Pengguna & Otorisasi Berbasis Peran.
Kasus Uji P01 - P17 sesuai spesifikasi instruksi HERO Backend Langkah 23.
"""
import os
import subprocess
import sys
from pathlib import Path
import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.models.document import Document
from app.models.enums import KlasifikasiAkses, PeranDokumen, StatusKeberlakuan, StatusPemrosesan
from app.core.permissions import Izin, PeranPengguna, HAK_AKSES_PERAN
from app.routers.ml_gateway import allowed_document_ids
from app.models.audit_log import AuditLog


@pytest.fixture
def auth_enabled_env(monkeypatch):
    """Mengaktifkan AUTH_ENABLED=True selama pengujian."""
    monkeypatch.setattr(settings, "auth_enabled", True)
    yield
    monkeypatch.setattr(settings, "auth_enabled", False)


@pytest.fixture
def test_users(db_session: Session) -> dict[PeranPengguna, tuple[User, str]]:
    """
    Membuat pengguna uji untuk masing-masing dari 4 peran:
    analis, admin_kb, admin_sistem, pilot_user.
    Password aman yang tidak dicetak: TestSecretPass123!
    Mengembalikan dict peran -> (User, plain_password)
    """
    plain_pw = "TestSecretPass123!"
    hashed_pw = bcrypt.hashpw(plain_pw[:72].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    users_map = {}
    for peran in PeranPengguna:
        username = f"user_{peran.value}_step23"
        user = db_session.query(User).filter(User.username == username).first()
        if not user:
            user = User(
                username=username,
                hashed_password=hashed_pw,
                role=peran.value,
                nama_lengkap=f"Pengguna {peran.value}",
                unit_kerja="Divisi Kepatuhan Hukum",
                is_active=True,
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
        else:
            user.role = peran.value
            user.is_active = True
            user.hashed_password = hashed_pw
            db_session.commit()
            db_session.refresh(user)
        users_map[peran] = (user, plain_pw)

    return users_map


@pytest.fixture
def user_tokens(client: TestClient, auth_enabled_env, test_users) -> dict[PeranPengguna, str]:
    """Mendapatkan token akses JWT untuk setiap peran via POST /auth/login."""
    tokens = {}
    for peran, (user, plain_pw) in test_users.items():
        res = client.post(
            "/api/v1/auth/login",
            data={"username": user.username, "password": plain_pw},
        )
        assert res.status_code == 200, f"Gagal login user {user.username}: {res.text}"
        tokens[peran] = res.json()["access_token"]
    return tokens


@pytest.fixture
def sample_docs(db_session: Session) -> tuple[Document, Document]:
    """Membuat dokumen uji publik dan non-publik."""
    doc_pub = Document(
        title="POJK Pengujian Publik Step 23",
        regulation_number="POJK-TEST-PUB-23",
        regulation_type="POJK",
        regulation_year=2026,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        file_path_pdf="kb/test_pub_23.pdf",
        file_hash="hash_pub_step23_fixture",
        file_size_bytes=1024,
        full_text="Teks lengkap dokumen regulasi publik untuk pengujian Langkah 23.",
        is_active=True,
    )
    doc_nonpub = Document(
        title="POJK Pengujian Non-Publik Step 23",
        regulation_number="POJK-TEST-NONPUB-23",
        regulation_type="POJK",
        regulation_year=2026,
        access_classification=KlasifikasiAkses.non_publik,
        document_role=PeranDokumen.draft_kajian,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        file_path_pdf="kb/test_nonpub_23.pdf",
        file_hash="hash_nonpub_step23_fixture",
        file_size_bytes=2048,
        full_text="Teks rahasia non-publik yang memerlukan izin KB_BACA_NONPUBLIK.",
        is_active=True,
    )
    db_session.add(doc_pub)
    db_session.add(doc_nonpub)
    db_session.commit()
    db_session.refresh(doc_pub)
    db_session.refresh(doc_nonpub)
    return doc_pub, doc_nonpub


# ==============================================================================
# P01 - Migrasi: pengguna lama admin/user menjadi admin_sistem/analis
# ==============================================================================
def test_p01_role_mapping_migration(db_session: Session):
    """P01: Pengguna lama dengan role 'admin' dipetakan ke 'admin_sistem' dan 'user' ke 'analis'."""
    u_admin = User(
        username="legacy_admin_p01",
        hashed_password="hashed_legacy_pw",
        role="admin",
        is_active=True,
    )
    u_user = User(
        username="legacy_user_p01",
        hashed_password="hashed_legacy_pw",
        role="user",
        is_active=True,
    )
    db_session.add(u_admin)
    db_session.add(u_user)
    db_session.commit()
    db_session.refresh(u_admin)
    db_session.refresh(u_user)

    assert u_admin.role == "admin_sistem"
    assert u_user.role == "analis"


# ==============================================================================
# P02 - Matriks terparametrisasi: untuk setiap izin, satu endpoint wakil x 4 peran
# ==============================================================================
# Endpoint wakil untuk masing-masing izin:
REPRESENTATIVE_ENDPOINTS = [
    (Izin.KB_BACA, "GET", "/api/v1/categories/"),
    (Izin.DOKUMEN_UNGGAH, "POST", "/api/v1/ingest/upload-pdf"),
    (Izin.METADATA_KOREKSI, "GET", "/api/v1/documents/needs-review"),
    (Izin.KEGAGALAN_KELOLA, "GET", "/api/v1/ingest/failures"),
    (Izin.ANALISA_JALANKAN, "GET", "/api/v1/documents/{doc_id}/analisa/banding"),
    (Izin.ANALISA_EKSPOR, "GET", "/api/v1/documents/{doc_id}/analisa/ekspor"),
    (Izin.SUMBER_KELOLA, "GET", "/api/v1/scraping-sources/"),
    (Izin.KB_KELOLA, "POST", "/api/v1/documents/place-pending"),
    (Izin.STATUS_UBAH, "PUT", "/api/v1/documents/{doc_id}/status"),
    (Izin.AUDIT_BACA, "GET", "/api/v1/audit-logs/"),
    (Izin.PENGGUNA_KELOLA, "GET", "/api/v1/users/"),
]


@pytest.mark.parametrize("izin, method, path_template", REPRESENTATIVE_ENDPOINTS)
def test_p02_matrix_access_control(
    client: TestClient,
    auth_enabled_env,
    user_tokens,
    sample_docs,
    izin: Izin,
    method: str,
    path_template: str,
):
    """
    P02: Untuk setiap izin, panggil endpoint wakil dengan token dari 4 peran.
    Bila peran memiliki izin di HAK_AKSES_PERAN -> 2xx/4xx bisnis (bukan 403 akses_ditolak).
    Bila peran tidak memiliki izin -> 403 {"code": "akses_ditolak"}.
    """
    doc_pub, _ = sample_docs
    path = path_template.format(doc_id=doc_pub.id)

    for peran in PeranPengguna:
        token = user_tokens[peran]
        headers = {"Authorization": f"Bearer {token}"}

        if method == "GET":
            res = client.get(path, headers=headers)
        elif method == "POST":
            res = client.post(path, headers=headers)
        elif method == "PUT":
            res = client.put(path, headers=headers, json={"status_keberlakuan": "berlaku"})
        else:
            res = client.request(method, path, headers=headers)

        has_permission = izin in HAK_AKSES_PERAN[peran]

        if has_permission:
            # Diizinkan: tidak boleh 403 akses_ditolak dan tidak boleh 401
            assert res.status_code != 401, f"{peran.value} ditolak 401 pada {path}"
            if res.status_code == 403:
                body = res.json()
                code = body.get("code") or (body.get("detail", {}).get("code") if isinstance(body.get("detail"), dict) else None)
                assert code != "akses_ditolak", f"{peran.value} seharusnya punya izin {izin.value} pada {path}, tapi ditolak: {body}"
        else:
            # Ditolak: harus 403 dengan code akses_ditolak
            assert res.status_code == 403, f"{peran.value} tidak punya izin {izin.value} tapi mendapat status {res.status_code} pada {path}"
            body = res.json()
            detail = body.get("detail")
            if isinstance(detail, dict):
                assert detail.get("code") == "akses_ditolak"


# ==============================================================================
# P03 - TC-57: Analis -> GET /audit-logs/ -> 403
# ==============================================================================
def test_p03_tc57_analis_cannot_read_audit_logs(client: TestClient, auth_enabled_env, user_tokens):
    """TC-57: Login sebagai Analis lalu mengakses fitur Admin Sistem (audit logs) -> 403 akses_ditolak."""
    token = user_tokens[PeranPengguna.analis]
    res = client.get("/api/v1/audit-logs/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    detail = res.json().get("detail", {})
    assert detail.get("code") == "akses_ditolak"
    assert detail.get("izin") == "AUDIT_BACA"


# ==============================================================================
# P04 - Tanpa token, auth hidup -> endpoint KB_BACA -> 401
# ==============================================================================
def test_p04_unauthenticated_request_rejected(client: TestClient, auth_enabled_env):
    """P04: Akses endpoint yang dilindungi tanpa token saat auth aktif -> 401."""
    res = client.get("/api/v1/documents/")
    assert res.status_code == 401


# ==============================================================================
# P05 - Token valid tetapi akun lalu dinonaktifkan -> 401
# ==============================================================================
def test_p05_token_valid_but_account_deactivated(
    client: TestClient,
    auth_enabled_env,
    test_users,
    user_tokens,
    db_session: Session,
):
    """P05: Pengguna yang dinonaktifkan tidak dapat memakai token lama -> 401."""
    user, _ = test_users[PeranPengguna.analis]
    token = user_tokens[PeranPengguna.analis]

    # Nonaktifkan akun di database
    user.is_active = False
    db_session.commit()

    res = client.get("/api/v1/documents/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert "Akun pengguna tidak aktif" in res.json().get("detail", "")

    # Kembalikan status aktif untuk uji berikutnya
    user.is_active = True
    db_session.commit()


# ==============================================================================
# P06 - Peran diubah Admin Sistem, token lama langsung mengikuti peran baru
# ==============================================================================
def test_p06_role_change_immediately_effective(
    client: TestClient,
    auth_enabled_env,
    test_users,
    user_tokens,
    db_session: Session,
):
    """P06: Saat peran diubah di DB, hak akses token lama langsung berubah tanpa perlu login ulang."""
    user, _ = test_users[PeranPengguna.analis]
    token = user_tokens[PeranPengguna.analis]

    # Sebelum diubah: Analis bisa mengakses antrean needs-review (METADATA_KOREKSI)
    res_before = client.get("/api/v1/documents/needs-review", headers={"Authorization": f"Bearer {token}"})
    assert res_before.status_code == 200

    # Ubah peran menjadi pilot_user
    user.role = "pilot_user"
    db_session.commit()

    # Sesudah diubah: token lama langsung ditolak 403 saat mengakses needs-review
    res_after = client.get("/api/v1/documents/needs-review", headers={"Authorization": f"Bearer {token}"})
    assert res_after.status_code == 403

    # Kembalikan peran semula
    user.role = "analis"
    db_session.commit()


# ==============================================================================
# P07 - Dokumen non-publik, auth hidup: Analis -> 200; Admin Sistem -> 403 KB_BACA_NONPUBLIK
# ==============================================================================
def test_p07_non_public_document_access_auth_enabled(
    client: TestClient,
    auth_enabled_env,
    user_tokens,
    sample_docs,
):
    """P07: Dokumen non-publik dapat diakses Analis (200), tetapi Admin Sistem ditolak 403 KB_BACA di tingkat endpoint."""
    _, doc_nonpub = sample_docs

    # Analis (punya KB_BACA dan KB_BACA_NONPUBLIK)
    token_analis = user_tokens[PeranPengguna.analis]
    res_analis = client.get(
        f"/api/v1/documents/{doc_nonpub.id}/text",
        headers={"Authorization": f"Bearer {token_analis}"},
    )
    assert res_analis.status_code == 200

    # Admin Sistem (tidak punya KB_BACA, ditolak di tingkat endpoint)
    token_admin = user_tokens[PeranPengguna.admin_sistem]
    res_admin = client.get(
        f"/api/v1/documents/{doc_nonpub.id}/text",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_admin.status_code == 403
    detail = res_admin.json().get("detail", {})
    assert detail.get("code") == "akses_ditolak"
    assert detail.get("izin") == "KB_BACA"
    assert detail.get("peran") == "admin_sistem"


def test_p07b_admin_kb_without_non_public_permission_rejected(
    client: TestClient,
    auth_enabled_env,
    user_tokens,
    sample_docs,
):
    """P07b: Jika peran punya KB_BACA tetapi tidak punya KB_BACA_NONPUBLIK, akses dokumen non-publik ditolak 403 KB_BACA_NONPUBLIK."""
    _, doc_nonpub = sample_docs
    token_kb = user_tokens[PeranPengguna.admin_kb]

    # Monkeypatch HAK_AKSES_PERAN: cabut KB_BACA_NONPUBLIK dari admin_kb
    orig_kb_perms = HAK_AKSES_PERAN[PeranPengguna.admin_kb].copy()
    try:
        HAK_AKSES_PERAN[PeranPengguna.admin_kb] = orig_kb_perms - {Izin.KB_BACA_NONPUBLIK}

        res = client.get(
            f"/api/v1/documents/{doc_nonpub.id}/text",
            headers={"Authorization": f"Bearer {token_kb}"},
        )
        assert res.status_code == 403
        detail = res.json().get("detail", {})
        assert detail.get("code") == "akses_ditolak"
        assert detail.get("izin") == "KB_BACA_NONPUBLIK"
    finally:
        HAK_AKSES_PERAN[PeranPengguna.admin_kb] = orig_kb_perms


def test_p07c_no_classification_leak_for_unauthorized_users(
    client: TestClient,
    auth_enabled_env,
    user_tokens,
    sample_docs,
):
    """P07c: Admin Sistem yang mengakses dokumen non-publik vs publik menerima detail respons 403 yang sama persis tanpa membocorkan klasifikasi."""
    doc_pub, doc_nonpub = sample_docs
    token_admin = user_tokens[PeranPengguna.admin_sistem]
    headers = {"Authorization": f"Bearer {token_admin}"}

    res_pub = client.get(f"/api/v1/documents/{doc_pub.id}/text", headers=headers)
    res_nonpub = client.get(f"/api/v1/documents/{doc_nonpub.id}/text", headers=headers)

    assert res_pub.status_code == 403
    assert res_nonpub.status_code == 403
    assert res_pub.json()["detail"] == res_nonpub.json()["detail"]


# ==============================================================================
# P08 - Dokumen non-publik, auth mati -> 403 dengan pesan lama
# ==============================================================================
def test_p08_non_public_document_access_auth_disabled(
    client: TestClient,
    sample_docs,
):
    """P08: Saat auth mati, dokumen non-publik tetap ditolak dengan pesan teks lama."""
    _, doc_nonpub = sample_docs
    res = client.get(f"/api/v1/documents/{doc_nonpub.id}/text")
    assert res.status_code == 403
    assert "Dokumen non-publik hanya dapat dibuka setelah login diaktifkan." in res.json().get("detail", "")


# ==============================================================================
# P09 - Auth mati: endpoint SUMBER_KELOLA, AUDIT_BACA, PENGGUNA_KELOLA tanpa token -> tidak 401/403
# ==============================================================================
def test_p09_auth_disabled_legacy_behavior(client: TestClient):
    """P09: Saat AUTH_ENABLED=false, endpoint tidak melempar 401 maupun 403 bila dipanggil tanpa token."""
    res_sources = client.get("/api/v1/scraping-sources/")
    assert res_sources.status_code not in (401, 403)

    res_audit = client.get("/api/v1/audit-logs/")
    assert res_audit.status_code not in (401, 403)

    res_users = client.get("/api/v1/users/")
    assert res_users.status_code not in (401, 403)


# ==============================================================================
# P10 - POST /users oleh Admin Sistem: 201, tanpa hashed_password, audit CREATE_USER
# ==============================================================================
def test_p10_create_user_by_admin(
    client: TestClient,
    auth_enabled_env,
    user_tokens,
    db_session: Session,
):
    """P10: Admin Sistem membuat user baru -> 201, tanpa password di respons, tercatat di audit log."""
    token = user_tokens[PeranPengguna.admin_sistem]
    new_username = "test_user_created_p10"

    # Bersihkan jika sudah ada
    existing = db_session.query(User).filter(User.username == new_username).first()
    if existing:
        db_session.delete(existing)
        db_session.commit()

    payload = {
        "username": new_username,
        "password": "ValidPassword1234!",
        "role": "analis",
        "nama_lengkap": "Analis Baru P10",
        "unit_kerja": "Biro Regulasi",
    }
    res = client.post("/api/v1/users/", headers={"Authorization": f"Bearer {token}"}, json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["username"] == new_username
    assert "password" not in data
    assert "hashed_password" not in data

    # Verifikasi audit log
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "CREATE_USER",
        AuditLog.target_resource == f"user:{data['id']}",
    ).first()
    assert audit is not None
    assert "password" not in audit.detail
    assert "hashed_password" not in audit.detail


# ==============================================================================
# P11 - POST /users duplikat / password < 12 -> 409 / 422
# ==============================================================================
def test_p11_create_user_validation_and_duplicate(
    client: TestClient,
    auth_enabled_env,
    user_tokens,
):
    """P11: Validasi pembuatan user baru: password < 12 karakter -> 422; username duplikat -> 409."""
    token = user_tokens[PeranPengguna.admin_sistem]

    # Password pendek (< 12)
    res_short = client.post(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "user_pendek_p11", "password": "short", "role": "analis"},
    )
    assert res_short.status_code == 422

    # Username duplikat (menggunakan analis yang sudah ada)
    res_dup = client.post(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "user_analis_step23",
            "password": "ValidPassword1234!",
            "role": "analis",
        },
    )
    assert res_dup.status_code == 409
    assert res_dup.json().get("detail", {}).get("code") in ("username_terdaftar", "username_sudah_ada")


# ==============================================================================
# P12 - Menonaktifkan Admin Sistem aktif terakhir -> 409 admin_terakhir
# ==============================================================================
def test_p12_cannot_deactivate_last_active_admin(
    client: TestClient,
    test_users,
    db_session: Session,
):
    """P12: Upaya menonaktifkan satu-satunya admin aktif ditolak dengan 409 admin_terakhir."""
    admin_user, _ = test_users[PeranPengguna.admin_sistem]

    # Pastikan hanya ada SATU admin aktif
    other_admins = db_session.query(User).filter(
        User.role == "admin_sistem",
        User.id != admin_user.id,
    ).all()
    for oa in other_admins:
        oa.is_active = False
    admin_user.is_active = True
    db_session.commit()

    # Ketika auth mati atau request eksternal tanpa self-token mencoba menonaktifkan admin terakhir:
    res = client.patch(
        f"/api/v1/users/{admin_user.id}",
        json={"is_active": False},
    )
    assert res.status_code == 409
    assert res.json().get("detail", {}).get("code") == "admin_terakhir"


# ==============================================================================
# P13 - Admin Sistem menurunkan peran dirinya sendiri -> 409 ubah_diri_sendiri
# ==============================================================================
def test_p13_admin_cannot_demote_self(
    client: TestClient,
    auth_enabled_env,
    user_tokens,
    test_users,
    db_session: Session,
):
    """P13: Admin Sistem tidak boleh mengubah peran atau menonaktifkan dirinya sendiri -> 409 ubah_diri_sendiri."""
    admin_user, _ = test_users[PeranPengguna.admin_sistem]
    token = user_tokens[PeranPengguna.admin_sistem]

    # Buat admin kedua agar admin_terakhir tidak terpicu
    admin_cadangan = User(
        username="admin_cadangan_p13",
        hashed_password=admin_user.hashed_password,
        role="admin_sistem",
        is_active=True,
    )
    db_session.add(admin_cadangan)
    db_session.commit()

    res = client.patch(
        f"/api/v1/users/{admin_user.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "analis"},
    )
    assert res.status_code == 409
    assert res.json().get("detail", {}).get("code") == "ubah_diri_sendiri"

    db_session.delete(admin_cadangan)
    db_session.commit()


# ==============================================================================
# P14 - GET /auth/me sebagai Analis -> role=analis, izin sama dengan isi matriks
# ==============================================================================
def test_p14_get_auth_me_analis(client: TestClient, auth_enabled_env, user_tokens):
    """P14: GET /auth/me sebagai Analis mengembalikan data profil dan daftar izin sesuai matriks."""
    token = user_tokens[PeranPengguna.analis]
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["auth_enabled"] is True
    assert data["role"] == "analis"
    expected_perms = sorted(p.value for p in HAK_AKSES_PERAN[PeranPengguna.analis])
    assert data["izin"] == expected_perms


# ==============================================================================
# P15 - allowed_document_ids saat auth hidup, Admin KB memuat dokumen non-publik
# ==============================================================================
def test_p15_allowed_document_ids_includes_non_public(
    auth_enabled_env,
    test_users,
    sample_docs,
    db_session: Session,
):
    """P15: allowed_document_ids menyertakan dokumen non-publik untuk pengguna dengan KB_BACA_NONPUBLIK."""
    doc_pub, doc_nonpub = sample_docs
    admin_kb_user, _ = test_users[PeranPengguna.admin_kb]

    allowed_ids = allowed_document_ids(db_session, user=admin_kb_user)
    assert doc_pub.id in allowed_ids
    assert doc_nonpub.id in allowed_ids


# ==============================================================================
# P16 - /internal/* dengan API key, auth hidup, tanpa token pengguna tetap berfungsi
# ==============================================================================
def test_p16_internal_endpoint_works_with_api_key(
    client: TestClient,
    auth_enabled_env,
):
    """P16: Endpoint internal dengan X-Internal-API-Key tetap berfungsi saat auth hidup tanpa token user."""
    # Tanpa API key -> 401
    res_no_key = client.get("/api/v1/internal/documents/999999/pdf")
    assert res_no_key.status_code == 401

    # Dengan API key -> tidak 401 (otorisasi API key worker berhasil)
    api_key = settings.internal_api_key
    headers = {"X-Internal-API-Key": api_key}
    res = client.get("/api/v1/internal/documents/999999/pdf", headers=headers)
    assert res.status_code == 404  # 404 dokumen tidak ditemukan, bukan 401 unauthorized


# ==============================================================================
# P17 - create_user.py dua kali dengan username sama
# ==============================================================================
def test_p17_create_user_script_idempotent(db_session: Session):
    """P17: Skrip create_user.py idempoten dan tidak mencetak password ke stdout/stderr."""
    test_user_cli = "user_cli_test_p17"

    # Bersihkan jika ada
    existing = db_session.query(User).filter(User.username == test_user_cli).first()
    if existing:
        db_session.delete(existing)
        db_session.commit()

    secret_password = "SecretCliPassword999!"
    env = os.environ.copy()
    env["HERO_NEW_USER_PASSWORD"] = secret_password
    env["DATABASE_URL"] = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://hero_user:hero_password@127.0.0.1:5432/hero_test",
    )

    script_path = str(Path(__file__).resolve().parent.parent / "scripts" / "create_user.py")
    python_exe = sys.executable

    # Run 1: Berhasil membuat akun
    res1 = subprocess.run(
        [
            python_exe,
            script_path,
            "--username",
            test_user_cli,
            "--role",
            "admin_sistem",
            "--nama",
            "Admin CLI Test",
            "--unit",
            "IT Infrastructure",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res1.returncode == 0, f"Run 1 gagal: {res1.stderr}"
    assert "berhasil dibuat" in res1.stdout
    assert secret_password not in res1.stdout
    assert secret_password not in res1.stderr

    # Run 2: Idempoten, keluar dengan pesan tanpa mengubah apa pun
    res2 = subprocess.run(
        [
            python_exe,
            script_path,
            "--username",
            test_user_cli,
            "--role",
            "admin_sistem",
            "--nama",
            "Admin CLI Test",
            "--unit",
            "IT Infrastructure",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res2.returncode == 0, f"Run 2 gagal: {res2.stderr}"
    assert "sudah terdaftar" in res2.stdout
    assert secret_password not in res2.stdout
    assert secret_password not in res2.stderr


# ==============================================================================
# P18 - Skrip legacy create_admin.py tidak mencetak password & set role admin_sistem
# ==============================================================================
def test_p18_legacy_create_admin_script(db_session: Session):
    """P18: Skrip legacy create_admin.py tidak mencetak password dan menetapkan role admin_sistem."""
    # Bersihkan admin jika sudah ada
    existing = db_session.query(User).filter(User.username == "admin").first()
    if existing:
        db_session.delete(existing)
        db_session.commit()

    secret_admin_pw = "CustomAdminPass456!"
    env = os.environ.copy()
    env["ADMIN_PASSWORD"] = secret_admin_pw
    env["PYTHONIOENCODING"] = "utf-8"
    env["DATABASE_URL"] = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://hero_user:hero_password@127.0.0.1:5432/hero_test",
    )

    python_exe = sys.executable
    script_path = str(Path(__file__).resolve().parent.parent / "app" / "create_admin.py")

    res = subprocess.run(
        [python_exe, script_path],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"create_admin.py gagal: {res.stderr}"
    assert secret_admin_pw not in res.stdout
    assert secret_admin_pw not in res.stderr
    assert "Username: admin" in res.stdout

    admin_db = db_session.query(User).filter(User.username == "admin").first()
    assert admin_db is not None
    assert admin_db.role == "admin_sistem"
