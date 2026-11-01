"""
tests/test_step35_draft_publik_judul.py
Pengujian HERO Backend Langkah 35: Draft Kajian Publik Wajib Persetujuan & Pengaman Judul Hasil Ekstraksi.
Kasus Uji:
- D01: Unggah draft_kajian + publik tanpa persetujuan -> 422 draft_publik_butuh_persetujuan
- D02: Sama, alasan < 10 karakter -> 422
- D03: Sama, persetujuan lengkap (auth mati) -> 200/201; tiga kolom terisi; audit UPLOAD_DOCUMENT & PUBLIKASI_DRAFT
- D04: Unggah draft_kajian + non_publik dan corpus_eksisting + publik tanpa persetujuan -> diterima
- D05: PATCH draft non_publik -> publik tanpa persetujuan -> 422
- D06: PATCH dengan persetujuan -> 200; kolom terisi; persetujuan_publik ada di respons & detail
- D07: PATCH corpus_eksisting + publik -> draft_kajian tanpa persetujuan -> 422
- D08: PATCH draft yang sudah disetujui -> non_publik -> 200; tiga kolom dikosongkan
- D09: PATCH judul saja pada draft yang sudah disetujui publik -> 200 tanpa persetujuan ulang
- D10: AUTH_ENABLED=true, pengguna analis dengan persetujuan -> 403 akses_ditolak
- D11: AUTH_ENABLED=true, pengguna admin_kb -> diterima; disetujui_oleh = username login
- D12: Buat/ubah sumber dengan default draft_kajian + publik -> 422 sumber_draft_publik_tidak_diizinkan
- D13: periksa_draft_publik.py dry-run lalu --apply (seed: 2 draft publik tanpa persetujuan, 1 dengan persetujuan)
- J01: periksa_judul judul OJK wajar (No. dan POJK.03) -> ok
- J02: Judul + Menimbang : a. bahwa … -> dipotong, judul tanpa paragraf
- J03: Judul hanya berisi paragraf tanpa penanda, 60 kata -> ditolak
- J04: Judul 400 karakter -> ditolak (dan extraction-result tidak 422)
- J05: Judul dengan 3 kalimat -> ditolak
- J06: extraction-result dengan judul ditolak -> judul lama dipertahankan, perlu_koreksi, detail.judul di audit & respons, teks lengkap tersimpan
- J07: extraction-result dengan judul dipotong -> judul potongan dipakai, status perlu_koreksi
- J08: extraction-result untuk dokumen yang sudah dikoreksi manual -> perilaku lama (judul diabaikan)
- J09: PATCH manual judul panjang (<= panjang kolom) -> diterima
- J10: periksa_judul.py dry-run lalu --apply -> judul tidak berubah, status jadi perlu_koreksi, audit tercatat
"""
import io
import uuid
from typing import Any
from datetime import datetime, timezone, timedelta
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.models.document import Document
from app.models.scraping_source import ScrapingSource
from app.models.job_ingest import JobIngest
from app.models.audit_log import AuditLog
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
    JenisSumber,
)
from app.core.permissions import PeranPengguna
from app.routers.auth import ALGORITHM
from app.services.judul_service import periksa_judul
from scripts.periksa_draft_publik import run_periksa_draft_publik
from scripts.periksa_judul import run_periksa_judul
from tests.conftest import make_pdf


INTERNAL_KEY_HEADER = {"X-Internal-API-Key": settings.internal_api_key}


@pytest.fixture
def db(db_session: Session) -> Session:
    """Alias fixture db_session ke db untuk kemudahan penulisan tes."""
    return db_session


def _buat_token_auth(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username,
        "exp": now + timedelta(hours=2),
        "iat": now,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def _seed_doc(
    db: Session,
    title: str = "Dokumen Uji",
    role: PeranDokumen = PeranDokumen.corpus_eksisting,
    access: KlasifikasiAkses = KlasifikasiAkses.publik,
    test_storage: Any = None,
    **kwargs,
) -> Document:
    uid = uuid.uuid4().hex[:12]
    file_path = f"pdf/{uid}_dokumen.pdf"
    if test_storage is not None:
        file_path = test_storage.save_pdf(b"%PDF-1.4 dummy", filename_hint=f"{uid}_dokumen.pdf", subdir="pdf/_inbox")
    doc_fields = {
        "title": title,
        "file_path_pdf": file_path,
        "file_hash": f"{uid}" * 5 + "0" * 4,
        "file_size_bytes": 1024,
        "document_role": role,
        "access_classification": access,
        "status_keberlakuan": StatusKeberlakuan.tidak_diketahui,
        "processing_status": StatusPemrosesan.terindeks,
    }
    doc_fields.update(kwargs)
    doc = Document(**doc_fields)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_d01_unggah_draft_publik_tanpa_persetujuan(client: TestClient, db: Session):
    """D01: Unggah draft_kajian + publik tanpa persetujuan -> 422 draft_publik_butuh_persetujuan."""
    doc_count_before = db.query(Document).count()
    job_count_before = db.query(JobIngest).count()

    pdf_bytes = make_pdf("Draft Kajian Publik Tanpa Persetujuan")
    files = [("files", ("draft1.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "draft_kajian",
        "title": "Draft Kajian Tanpa Persetujuan",
    }

    resp = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert resp.status_code == 422
    body = resp.json()
    assert body.get("detail", {}).get("code") == "draft_publik_butuh_persetujuan"

    # Tidak ada dokumen atau job baru yang tersimpan
    assert db.query(Document).count() == doc_count_before
    assert db.query(JobIngest).count() == job_count_before


def test_d02_unggah_draft_publik_alasan_kurang_panjang(client: TestClient, db: Session):
    """D02: Sama, alasan < 10 karakter -> 422 draft_publik_butuh_persetujuan."""
    pdf_bytes = make_pdf("Draft Kajian Alasan Pendek")
    files = [("files", ("draft2.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "draft_kajian",
        "title": "Draft Kajian Alasan Pendek",
        "persetujuan_publik_oleh": "Admin KB",
        "persetujuan_publik_alasan": "pendek",  # < 10 karakter
    }

    resp = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert resp.status_code == 422
    body = resp.json()
    assert body.get("detail", {}).get("code") == "draft_publik_butuh_persetujuan"


def test_d03_unggah_draft_publik_persetujuan_lengkap_auth_mati(client: TestClient, db: Session):
    """D03: Persetujuan lengkap (auth mati) -> 200; 3 kolom terisi; audit UPLOAD_DOCUMENT & PUBLIKASI_DRAFT."""
    orig_auth = settings.auth_enabled
    settings.auth_enabled = False
    try:
        pdf_bytes = make_pdf("Draft Kajian Persetujuan Sah")
        files = [("files", ("draft_sah.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
        data = {
            "access_classification": "publik",
            "document_role": "draft_kajian",
            "title": "Draft Kajian Sah Dipublikasikan",
            "persetujuan_publik_oleh": "Kepala Departemen DPEA",
            "persetujuan_publik_alasan": "Telah disetujui untuk uji publik sesuai disposisi",
        }

        resp = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()["details"][0]["document_id"]

        doc = db.query(Document).filter(Document.id == doc_id).first()
        assert doc is not None
        assert doc.publik_disetujui_oleh == "Kepala Departemen DPEA"
        assert doc.publik_disetujui_alasan == "Telah disetujui untuk uji publik sesuai disposisi"
        assert doc.publik_disetujui_pada is not None

        # Periksa audit log UPLOAD_DOCUMENT memuat persetujuan_publik
        audit_upload = (
            db.query(AuditLog)
            .filter(AuditLog.target_resource == f"document:{doc.id}", AuditLog.action == "UPLOAD_DOCUMENT")
            .first()
        )
        assert audit_upload is not None
        assert "persetujuan_publik" in audit_upload.detail
        assert audit_upload.detail["persetujuan_publik"]["disetujui_oleh"] == "Kepala Departemen DPEA"

        # Periksa audit log PUBLIKASI_DRAFT
        audit_draft = (
            db.query(AuditLog)
            .filter(AuditLog.target_resource == f"document:{doc.id}", AuditLog.action == "PUBLIKASI_DRAFT")
            .first()
        )
        assert audit_draft is not None
        assert audit_draft.detail["jalur"] == "unggah"
        assert audit_draft.detail["disetujui_oleh"] == "Kepala Departemen DPEA"
    finally:
        settings.auth_enabled = orig_auth


def test_d04_unggah_kombinasi_valid_tanpa_persetujuan(client: TestClient, db: Session):
    """D04: Unggah draft_kajian + non_publik dan corpus_eksisting + publik tanpa persetujuan -> diterima."""
    # 1. draft_kajian + non_publik
    pdf1 = make_pdf("Draft Internal Non Publik")
    resp1 = client.post(
        "/api/v1/ingest/upload-pdf",
        files=[("files", ("draft_np.pdf", io.BytesIO(pdf1), "application/pdf"))],
        data={"access_classification": "non_publik", "document_role": "draft_kajian", "title": "Draft Internal"},
    )
    assert resp1.status_code == 200

    # 2. corpus_eksisting + publik
    pdf2 = make_pdf("Corpus Regulasi Publik")
    resp2 = client.post(
        "/api/v1/ingest/upload-pdf",
        files=[("files", ("corpus_pub.pdf", io.BytesIO(pdf2), "application/pdf"))],
        data={"access_classification": "publik", "document_role": "corpus_eksisting", "title": "POJK Publik"},
    )
    assert resp2.status_code == 200


def test_d05_patch_draft_nonpublik_ke_publik_tanpa_persetujuan(client: TestClient, db: Session):
    """D05: PATCH draft non_publik -> publik tanpa persetujuan -> 422; dokumen tidak berubah."""
    doc = _seed_doc(
        db,
        title="Draft Awal Non Publik",
        role=PeranDokumen.draft_kajian,
        access=KlasifikasiAkses.non_publik,
    )

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={"access_classification": "publik"},
    )
    assert resp.status_code == 422
    assert resp.json().get("detail", {}).get("code") == "draft_publik_butuh_persetujuan"

    db.refresh(doc)
    assert doc.access_classification == KlasifikasiAkses.non_publik
    assert doc.publik_disetujui_pada is None


def test_d06_patch_draft_ke_publik_dengan_persetujuan(client: TestClient, db: Session):
    """D06: PATCH dengan persetujuan -> 200; kolom terisi; persetujuan_publik ada di respons & detail."""
    doc = _seed_doc(
        db,
        title="Draft Awal Non Publik",
        role=PeranDokumen.draft_kajian,
        access=KlasifikasiAkses.non_publik,
    )

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={
            "access_classification": "publik",
            "persetujuan_publik": {
                "disetujui_oleh": "Direktur Pengaturan",
                "alasan": "Telah melalui harmonisasi antardirektorat dan siap dipublikasikan",
            },
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "persetujuan_publik" in data
    assert data["persetujuan_publik"]["disetujui_oleh"] == "Direktur Pengaturan"

    # Periksa endpoint GET detail
    resp_get = client.get(f"/api/v1/documents/{doc.id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["persetujuan_publik"]["disetujui_oleh"] == "Direktur Pengaturan"

    # Periksa audit log PUBLIKASI_DRAFT dengan jalur koreksi_metadata
    audit_patch = (
        db.query(AuditLog)
        .filter(AuditLog.target_resource == f"document:{doc.id}", AuditLog.action == "PUBLIKASI_DRAFT")
        .first()
    )
    assert audit_patch is not None
    assert audit_patch.detail["jalur"] == "koreksi_metadata"


def test_d07_patch_corpus_ke_draft_tanpa_persetujuan(client: TestClient, db: Session):
    """D07: PATCH dokumen corpus_eksisting + publik -> document_role=draft_kajian tanpa persetujuan -> 422."""
    doc = _seed_doc(
        db,
        title="Dokumen Corpus Publik",
        role=PeranDokumen.corpus_eksisting,
        access=KlasifikasiAkses.publik,
        status_keberlakuan=StatusKeberlakuan.berlaku,
    )

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={"document_role": "draft_kajian"},
    )
    assert resp.status_code == 422
    assert resp.json().get("detail", {}).get("code") == "draft_publik_butuh_persetujuan"


def test_d08_patch_draft_disetujui_ke_nonpublik_kosongkan_kolom(client: TestClient, db: Session):
    """D08: PATCH draft yang sudah disetujui -> non_publik -> 200; tiga kolom dikosongkan."""
    now_utc = datetime.now(timezone.utc)
    doc = _seed_doc(
        db,
        title="Draft Publik Resmi",
        role=PeranDokumen.draft_kajian,
        access=KlasifikasiAkses.publik,
        publik_disetujui_oleh="Direktur Pengaturan",
        publik_disetujui_alasan="Sudah disetujui rapat pimpinan",
        publik_disetujui_pada=now_utc,
    )

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={"access_classification": "non_publik"},
    )
    assert resp.status_code == 200
    db.refresh(doc)
    assert doc.publik_disetujui_oleh is None
    assert doc.publik_disetujui_alasan is None
    assert doc.publik_disetujui_pada is None

    # Respons persetujuan_publik menjadi null
    assert resp.json()["persetujuan_publik"] is None


def test_d09_patch_judul_pada_draft_disetujui_tanpa_persetujuan_ulang(client: TestClient, db: Session):
    """D09: PATCH judul saja pada draft yang sudah disetujui publik -> 200 tanpa persetujuan ulang."""
    now_utc = datetime.now(timezone.utc)
    doc = _seed_doc(
        db,
        title="Draft Judul Lama",
        role=PeranDokumen.draft_kajian,
        access=KlasifikasiAkses.publik,
        publik_disetujui_oleh="Direktur Pengaturan",
        publik_disetujui_alasan="Disetujui untuk publikasi",
        publik_disetujui_pada=now_utc,
    )

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={"title": "Draft Judul Baru yang Dibenahi"},
    )
    assert resp.status_code == 200
    db.refresh(doc)
    assert doc.title == "Draft Judul Baru yang Dibenahi"
    assert doc.publik_disetujui_oleh == "Direktur Pengaturan"
    assert doc.publik_disetujui_pada == now_utc


def test_d10_auth_aktif_pengguna_analis_ditolak_403(client: TestClient, db: Session):
    """D10: AUTH_ENABLED=true, pengguna analis dengan persetujuan -> 403 akses_ditolak."""
    orig_auth = settings.auth_enabled
    settings.auth_enabled = True
    try:
        user_analis = User(
            username="analis_test_d10",
            hashed_password="$2b$12$dummyhashforanalisandadmin",
            role=PeranPengguna.analis,
            is_active=True,
        )
        db.add(user_analis)
        db.commit()
        token = _buat_token_auth(user_analis)

        doc = _seed_doc(
            db,
            title="Draft Analis Non Publik",
            role=PeranDokumen.draft_kajian,
            access=KlasifikasiAkses.non_publik,
        )

        resp = client.patch(
            f"/api/v1/documents/{doc.id}/metadata",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "access_classification": "publik",
                "persetujuan_publik": {
                    "disetujui_oleh": "Siapa Saja",
                    "alasan": "Alasan yang cukup panjang untuk disetujui",
                },
            },
        )
        assert resp.status_code == 403
        assert resp.json().get("detail", {}).get("code") == "akses_ditolak"
    finally:
        settings.auth_enabled = orig_auth


def test_d11_auth_aktif_pengguna_admin_kb_diterima(client: TestClient, db: Session):
    """D11: AUTH_ENABLED=true, pengguna admin_kb -> diterima; disetujui_oleh = username login."""
    orig_auth = settings.auth_enabled
    settings.auth_enabled = True
    try:
        user_admin = User(
            username="admin_kb_d11",
            hashed_password="$2b$12$dummyhashforanalisandadmin",
            role=PeranPengguna.admin_kb,
            is_active=True,
        )
        db.add(user_admin)
        db.commit()
        token = _buat_token_auth(user_admin)

        doc = _seed_doc(
            db,
            title="Draft Admin Non Publik",
            role=PeranDokumen.draft_kajian,
            access=KlasifikasiAkses.non_publik,
        )

        resp = client.patch(
            f"/api/v1/documents/{doc.id}/metadata",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "access_classification": "publik",
                "persetujuan_publik": {
                    "disetujui_oleh": "Nama Lain Dari Klien",
                    "alasan": "Disetujui oleh admin KB resmi untuk publikasi",
                },
            },
        )
        assert resp.status_code == 200, resp.text
        db.refresh(doc)
        # Nama dari klien diabaikan, otomatis diisi dari username pengguna login
        assert doc.publik_disetujui_oleh == "admin_kb_d11"
        assert doc.access_classification == KlasifikasiAkses.publik
    finally:
        settings.auth_enabled = orig_auth


def test_d12_sumber_draft_publik_ditolak_422(client: TestClient, db: Session):
    """D12: Buat/ubah sumber dengan default draft_kajian + publik -> 422 sumber_draft_publik_tidak_diizinkan."""
    # 1. POST sumber baru
    resp_create = client.post(
        "/api/v1/scraping-sources",
        json={
            "name": "Sumber Draft Publik Ilegal",
            "url": "https://ojk.go.id/draft-publik-test",
            "source_type": "situs_web",
            "default_document_role": "draft_kajian",
            "default_access_classification": "publik",
        },
    )
    assert resp_create.status_code == 422
    assert resp_create.json().get("detail", {}).get("code") == "sumber_draft_publik_tidak_diizinkan"

    # 2. PATCH sumber yang ada
    src = ScrapingSource(
        name="Sumber Legal Awal",
        url="https://ojk.go.id/sumber-legal-test",
        source_type=JenisSumber.situs_web,
        default_document_role=PeranDokumen.corpus_eksisting,
        default_access_classification=KlasifikasiAkses.publik,
        is_active=True,
    )
    db.add(src)
    db.commit()
    db.refresh(src)

    resp_patch = client.patch(
        f"/api/v1/scraping-sources/{src.id}",
        json={"default_document_role": "draft_kajian"},
    )
    assert resp_patch.status_code == 422
    assert resp_patch.json().get("detail", {}).get("code") == "sumber_draft_publik_tidak_diizinkan"


def test_d13_skrip_periksa_draft_publik(db: Session):
    """D13: periksa_draft_publik.py dry-run lalu --apply (2 draft publik tanpa persetujuan, 1 dengan persetujuan)."""
    now = datetime.now(timezone.utc)
    # Seed doc 1: draft publik tanpa persetujuan
    d1 = _seed_doc(
        db,
        title="Draft Tanpa Persetujuan 1",
        role=PeranDokumen.draft_kajian,
        access=KlasifikasiAkses.publik,
        publik_disetujui_pada=None,
    )
    # Seed doc 2: draft publik tanpa persetujuan
    d2 = _seed_doc(
        db,
        title="Draft Tanpa Persetujuan 2",
        role=PeranDokumen.draft_kajian,
        access=KlasifikasiAkses.publik,
        publik_disetujui_pada=None,
    )
    # Seed doc 3: draft publik DENGAN persetujuan
    d3 = _seed_doc(
        db,
        title="Draft DENGAN Persetujuan Sah",
        role=PeranDokumen.draft_kajian,
        access=KlasifikasiAkses.publik,
        publik_disetujui_oleh="admin",
        publik_disetujui_alasan="Disetujui sah pimpinan",
        publik_disetujui_pada=now,
    )

    # Dry-run
    res_dry = run_periksa_draft_publik(db, apply=False)
    assert res_dry["total_ditemukan"] >= 2
    assert res_dry["diubah"] == 0

    db.refresh(d1)
    db.refresh(d2)
    db.refresh(d3)
    assert d1.access_classification == KlasifikasiAkses.publik
    assert d2.access_classification == KlasifikasiAkses.publik
    assert d3.access_classification == KlasifikasiAkses.publik

    # Apply
    res_apply = run_periksa_draft_publik(db, apply=True)
    assert res_apply["diubah"] >= 2

    db.refresh(d1)
    db.refresh(d2)
    db.refresh(d3)
    assert d1.access_classification == KlasifikasiAkses.non_publik
    assert d2.access_classification == KlasifikasiAkses.non_publik
    assert d3.access_classification == KlasifikasiAkses.publik  # tetap publik


def test_j01_periksa_judul_ojk_wajar():
    """J01: periksa_judul judul OJK wajar (termasuk No. dan POJK.03) -> ok."""
    j = "Peraturan Otoritas Jasa Keuangan Nomor 11/POJK.03/2016 tentang Kewajiban Penyediaan Modal Minimum Bank Umum"
    res = periksa_judul(j)
    assert res.status == "ok"
    assert res.judul == j

    j2 = "Peraturan Otoritas Jasa Keuangan No. 5/POJK.03/2015 tentang Penerapan Tata Kelola"
    res2 = periksa_judul(j2)
    assert res2.status == "ok"


def test_j02_periksa_judul_dengan_penanda_isi():
    """J02: Judul + Menimbang : a. bahwa … -> dipotong, judul tanpa paragraf."""
    raw = "Peraturan Otoritas Jasa Keuangan Nomor 10/POJK.03/2020 tentang Penilaian Kualitas Aset Bank Menimbang : a. bahwa untuk menjaga stabilitas..."
    res = periksa_judul(raw)
    assert res.status == "dipotong"
    assert res.alasan == "mengandung_isi_peraturan"
    assert res.judul == "Peraturan Otoritas Jasa Keuangan Nomor 10/POJK.03/2020 tentang Penilaian Kualitas Aset Bank"


def test_j03_periksa_judul_paragraf_tanpa_penanda_60_kata():
    """J03: Judul hanya berisi paragraf tanpa penanda, 60 kata -> ditolak."""
    raw = " ".join(["kata"] * 60)
    res = periksa_judul(raw)
    assert res.status == "ditolak"
    assert res.alasan in ("terlalu_banyak_kata", "terlalu_panjang")


def test_j04_periksa_judul_400_karakter(client: TestClient, db: Session, test_storage: Any):
    """J04: Judul 400 karakter -> ditolak (dan extraction-result tidak 422)."""
    raw = "Peraturan tentang " + ("panjang " * 50)
    assert len(raw) > 300
    res = periksa_judul(raw)
    assert res.status == "ditolak"

    # Verifikasi extraction-result TIDAK ditolak 422
    doc = _seed_doc(
        db,
        title="Judul Asli Awal",
        regulation_number="POJK-TEST-J04",
        processing_status=StatusPemrosesan.diproses,
        test_storage=test_storage,
    )

    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_KEY_HEADER,
        json={
            "judul": raw,
            "teks_lengkap": "Ini teks lengkap regulasi dari hasil ekstraksi yang berhasil disimpan.",
        },
    )
    assert resp.status_code == 200, resp.text


def test_j05_periksa_judul_tiga_kalimat():
    """J05: Judul dengan 3 kalimat -> ditolak."""
    raw = "Ini kalimat pertama tentang aturan. Ini kalimat kedua mengenai pedoman operasional perbankan; Dan ini kalimat ketiga penutup regulasi."
    res = periksa_judul(raw)
    assert res.status == "ditolak"
    assert res.alasan == "berbentuk_paragraf"


def test_j06_extraction_result_judul_ditolak(client: TestClient, db: Session, test_storage: Any):
    """J06: extraction-result dengan judul ditolak -> judul lama dipertahankan, perlu_koreksi, detail.judul."""
    doc = _seed_doc(
        db,
        title="Judul Asli Yang Bagus",
        regulation_number="POJK-TEST-J06",
        processing_status=StatusPemrosesan.diproses,
        test_storage=test_storage,
    )

    raw_buruk = " ".join(["paragraf_tanpa_batas"] * 55)
    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_KEY_HEADER,
        json={
            "judul": raw_buruk,
            "teks_lengkap": "Teks lengkap dokumen J06 tetap utuh.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "perlu_koreksi"
    assert "title" in data["low_confidence_fields"]
    assert "judul" in data
    assert data["judul"]["status"] == "ditolak"

    db.refresh(doc)
    # Judul lama dipertahankan
    assert doc.title == "Judul Asli Yang Bagus"
    assert doc.processing_status == StatusPemrosesan.perlu_koreksi
    assert doc.full_text == "Teks lengkap dokumen J06 tetap utuh."

    # Periksa audit log
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.target_resource == f"document:{doc.id}", AuditLog.action == "EXTRACTION_RESULT")
        .first()
    )
    assert audit is not None
    assert "judul" in audit.detail
    assert audit.detail["judul"]["status"] == "ditolak"


def test_j07_extraction_result_judul_dipotong(client: TestClient, db: Session, test_storage: Any):
    """J07: extraction-result dengan judul dipotong -> judul potongan dipakai, status perlu_koreksi."""
    doc = _seed_doc(
        db,
        title="Placeholder",
        regulation_number="POJK-TEST-J07",
        processing_status=StatusPemrosesan.diproses,
        test_storage=test_storage,
    )

    raw = "Peraturan Otoritas Jasa Keuangan Nomor 99/POJK.03/2021 tentang Tata Kelola Terintegrasi Menimbang : a. bahwa untuk ..."
    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_KEY_HEADER,
        json={
            "judul": raw,
            "teks_lengkap": "Teks lengkap dokumen J07.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "perlu_koreksi"
    assert "judul" in data
    assert data["judul"]["status"] == "dipotong"

    db.refresh(doc)
    assert doc.title == "Peraturan Otoritas Jasa Keuangan Nomor 99/POJK.03/2021 tentang Tata Kelola Terintegrasi"
    assert doc.processing_status == StatusPemrosesan.perlu_koreksi


def test_j08_extraction_result_dokumen_koreksi_manual_diabaikan(client: TestClient, db: Session, test_storage: Any):
    """J08: extraction-result untuk dokumen yang sudah dikoreksi manual -> perilaku lama (judul diabaikan)."""
    now = datetime.now(timezone.utc)
    doc = _seed_doc(
        db,
        title="Judul Tetap Manual",
        regulation_number="POJK-TEST-J08",
        processing_status=StatusPemrosesan.diproses,
        metadata_corrected_at=now,
        test_storage=test_storage,
    )

    resp = client.patch(
        f"/api/v1/internal/documents/{doc.id}/extraction",
        headers=INTERNAL_KEY_HEADER,
        json={
            "judul": "Judul Baru Dari Ekstraksi Menimbang: a. bahwa...",
            "teks_lengkap": "Teks lengkap baru.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "title" in data["ignored_fields"]

    db.refresh(doc)
    assert doc.title == "Judul Tetap Manual"


def test_j09_patch_manual_judul_panjang_diterima(client: TestClient, db: Session, test_storage: Any):
    """J09: PATCH manual judul panjang (<= panjang kolom) -> diterima (aturan §2 tidak berlaku)."""
    doc = _seed_doc(
        db,
        title="Judul Pendek",
        regulation_number="POJK-TEST-J09",
        test_storage=test_storage,
    )

    # Buat judul 200 karakter yang memuat kalimat / kata Menimbang
    judul_manual = "Peraturan Otoritas Jasa Keuangan tentang Petunjuk Teknis Menimbang Aspek Risiko Perbankan Secara Menyeluruh dan Berkelanjutan dalam Rangka Mendukung Pemulihan Ekonomi Nasional dan Stabilitas Sistem Keuangan."
    assert len(judul_manual) <= 255

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={"title": judul_manual},
    )
    assert resp.status_code == 200, resp.text
    db.refresh(doc)
    assert doc.title == judul_manual


def test_j10_skrip_periksa_judul(db: Session):
    """J10: periksa_judul.py dry-run lalu --apply -> judul tidak berubah; status jadi perlu_koreksi; audit tercatat."""
    judul_buruk = "Peraturan Otoritas Jasa Keuangan Nomor 88/POJK.03/2022 tentang Bank Menimbang : a. bahwa ..."
    doc = _seed_doc(
        db,
        title=judul_buruk,
        regulation_number="POJK-TEST-J10",
        processing_status=StatusPemrosesan.terindeks,
        is_active=True,
        metadata_corrected_at=None,
    )

    # Dry-run
    res_dry = run_periksa_judul(db, apply=False)
    assert res_dry["dipotong"] >= 1
    assert res_dry["diubah"] == 0

    db.refresh(doc)
    assert doc.title == judul_buruk
    assert doc.processing_status == StatusPemrosesan.terindeks

    # Apply
    res_apply = run_periksa_judul(db, apply=True)
    assert res_apply["diubah"] >= 1

    db.refresh(doc)
    # Judul tidak berubah
    assert doc.title == judul_buruk
    # Status berubah jadi perlu_koreksi
    assert doc.processing_status == StatusPemrosesan.perlu_koreksi

    # Audit UPDATE_METADATA tercatat
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.target_resource == f"document:{doc.id}", AuditLog.action == "UPDATE_METADATA")
        .first()
    )
    assert audit is not None
    assert audit.detail.get("alasan") == "langkah35_judul_mencurigakan"
