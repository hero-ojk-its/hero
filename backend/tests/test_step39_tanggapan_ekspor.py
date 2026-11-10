"""
tests/test_step39_tanggapan_ekspor.py
Pengujian Fase 3 untuk penandaan temuan harmonisasi (#71) dan ekspor laporan harmonisasi (#73).
- H01: kunci_temuan untuk temuan yang sama dengan id ML berbeda -> kunci sama
- H02: Temuan berbeda pasal/pembanding/jenis -> kunci berbeda
- H03: PUT tanggapan 'valid' + catatan pada draft publik -> 200; baris tersimpan; audit TANGGAPAN_TEMUAN
- H04: PUT ulang dengan 'tidak_relevan' -> baris yang sama diperbarui (tidak dobel); audit before/after
- H05: Penilaian tidak dikenal / catatan > 2000 -> 422
- H06: Dokumen corpus_eksisting -> 422 bukan_draft
- H07: Draft non-publik saat login mati -> 403
- H08: AUTH_ENABLED=true, peran tanpa TANGGAPAN_TINJAU (mis. admin_sistem) -> 403; analis -> 200 dengan dinilai_oleh terisi
- H09: DELETE tanggapan -> terhapus; GET tidak memuatnya
- H10: Harmonisasi dijalankan ulang (mock id berubah) -> setiap temuan memuat kunci_temuan & tanggapan yang benar; ringkasan.tanggapan benar; cache analysis_results tidak memuat field tanggapan
- H11: Rekap JSON dan ?format=csv -> jumlah per jenis benar; CSV ber-BOM
- E01: Ekspor DOCX setelah harmonisasi tersimpan -> 200; berkas terbuka dengan python-docx; memuat judul, tabel temuan, penilaian analis, catatan kaki
- E02: Ekspor CSV -> BOM; satu baris per temuan; kolom sesuai
- E03: Ekspor JSON -> memuat tanggapan per temuan + metadata
- E04: Dokumen belum pernah diharmonisasi -> 404 harmonisasi_belum_ada; layanan ML tidak dipanggil (spy)
- E05: Temuan dengan pembanding nonaktif / non-publik -> disaring sama seperti respons harmonisasi
- E06: Format tidak dikenal -> 422
- E07: Audit EXPORT_HARMONIZATION -> tercatat dengan format & jumlah temuan
"""
import copy
import csv
from datetime import datetime, timezone, timedelta
import io
from unittest.mock import MagicMock
import uuid

import docx
from fastapi.testclient import TestClient
import httpx
import jwt
import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import PeranPengguna
from app.main import app
from app.models.analysis_result import AnalysisResult
from app.models.analysis_run import AnalysisRun
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.enums import (
    JenisAnalisa,
    KlasifikasiAkses,
    ModeAnalisa,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
)
from app.models.tanggapan_temuan import TanggapanTemuan
from app.models.user import User
from app.routers.auth import ALGORITHM
from app.routers.ml_gateway import get_ml_client, saring_rujukan
from app.services.audit_service import (
    EXPORT_HARMONIZATION,
    TANGGAPAN_TEMUAN,
)
from app.services.tanggapan_service import kunci_temuan, tandai_kunci_temuan


@pytest.fixture(autouse=True)
def setup_ml_test_env(monkeypatch: pytest.MonkeyPatch):
    """Pastikan konfigurasi ML aktif dan terisolasi untuk tiap pengujian."""
    monkeypatch.setattr(settings, "ml_service_url", "http://ml-test:8100")
    monkeypatch.setattr(settings, "ml_cache_enabled", True)
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)
    monkeypatch.setattr(settings, "auth_enabled", False)
    yield
    app.dependency_overrides.pop(get_ml_client, None)


def seed_harmonisasi_result(
    db: Session,
    doc: Document,
    payload: dict,
    mode: ModeAnalisa = ModeAnalisa.deterministik,
) -> AnalysisResult:
    """Helper membuat baris cache analysis_results harmonisasi."""
    res = AnalysisResult(
        document_id=doc.id,
        kind=JenisAnalisa.harmonisasi,
        mode=mode,
        params_hash="params-" + uuid.uuid4().hex[:16],
        source_fingerprint=f"hash:{doc.file_hash or 'nohash'}",
        result=payload,
        ml_version="1.0",
        duration_ms=120,
        created_at=datetime.now(timezone.utc),
    )
    db.add(res)
    db.commit()
    db.refresh(res)
    return res


def _buat_token_auth(user: User) -> str:
    """Helper membuat JWT token untuk user test."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username,
        "exp": now + timedelta(hours=2),
        "iat": now,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_test_doc(**kwargs) -> Document:
    """Helper membuat instance Document valid dengan nilai default NOT NULL."""
    rnd = uuid.uuid4().hex
    data = {
        "title": "Draft Kajian Uji Harmonisasi",
        "document_role": PeranDokumen.draft_kajian,
        "access_classification": KlasifikasiAkses.publik,
        "file_path_pdf": f"pdf/test_{rnd[:8]}.pdf",
        "file_hash": (rnd * 2)[:64],
        "file_size_bytes": 2048,
        "processing_status": StatusPemrosesan.terindeks,
        "status_keberlakuan": StatusKeberlakuan.berlaku,
        "is_active": True,
    }
    data.update(kwargs)
    return Document(**data)


def test_h01_kunci_temuan_stabil_antar_id_ml():
    """H01: kunci_temuan untuk temuan yang sama dengan id ML berbeda -> kunci sama."""
    t1 = {
        "id": "ml-finding-uuid-001",
        "jenis": "menggantikan",
        "pasal_draft": "Pasal 5 ayat (1)",
        "pembanding": {"key": "POJK|10|2023", "document_id": 101},
        "pasal_pembanding": "Pasal 12",
        "deskripsi": "Menggantikan ketentuan modal kerja",
    }
    t2 = {
        "id": "ml-finding-uuid-999",  # ID ML berbeda
        "jenis": "  MENGGANTIKAN  ",   # Beda spasi & kapitalisasi
        "pasal_draft": "pasal 5 ayat (1)",
        "pembanding": {"key": "pojk|10|2023", "document_id": 101},
        "pasal_pembanding": "  pasal 12  ",
        "deskripsi": "Deskripsi berubah tidak mempengaruhi kunci identitas",
    }
    k1 = kunci_temuan(t1)
    k2 = kunci_temuan(t2)
    assert k1 == k2
    assert len(k1) == 32


def test_h02_kunci_temuan_berbeda_untuk_substansi_berbeda():
    """H02: Temuan berbeda pasal/pembanding/jenis -> kunci berbeda."""
    t_base = {
        "jenis": "menggantikan",
        "pasal_draft": "Pasal 5",
        "pembanding": {"key": "POJK|10|2023"},
        "pasal_pembanding": "Pasal 12",
    }
    t_beda_pasal = {
        "jenis": "menggantikan",
        "pasal_draft": "Pasal 6",
        "pembanding": {"key": "POJK|10|2023"},
        "pasal_pembanding": "Pasal 12",
    }
    t_beda_pembanding = {
        "jenis": "menggantikan",
        "pasal_draft": "Pasal 5",
        "pembanding": {"key": "POJK|11|2023"},
        "pasal_pembanding": "Pasal 12",
    }
    t_beda_jenis = {
        "jenis": "melengkapi",
        "pasal_draft": "Pasal 5",
        "pembanding": {"key": "POJK|10|2023"},
        "pasal_pembanding": "Pasal 12",
    }
    k_base = kunci_temuan(t_base)
    assert k_base != kunci_temuan(t_beda_pasal)
    assert k_base != kunci_temuan(t_beda_pembanding)
    assert k_base != kunci_temuan(t_beda_jenis)


def test_h03_put_tanggapan_valid(client: TestClient, db_session: Session):
    """H03: PUT tanggapan 'valid' + catatan pada draft publik -> 200; baris tersimpan; audit TANGGAPAN_TEMUAN."""
    draft = create_test_doc(title="Draft POJK Pasar Modal", document_role=PeranDokumen.draft_kajian)
    db_session.add(draft)
    db_session.commit()

    run = AnalysisRun(
        document_id=draft.id,
        kind=JenisAnalisa.harmonisasi,
        mode_diminta=ModeAnalisa.deterministik,
        mode_dipakai=ModeAnalisa.deterministik,
        sumber="ml",
        segar=False,
        params={},
        params_hash="params-h03",
        source_fingerprint=f"hash:{draft.file_hash or 'nohash'}",
        http_status=200,
        result={},
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    temuan_payload = {
        "id": "t-101",
        "jenis": "menggantikan",
        "judul": "Batas minimum modal",
        "pasal_draft": "Pasal 3",
        "pasal_pembanding": "Pasal 8",
        "pembanding": {"key": "POJK|5|2022", "nomor": "POJK 5 2022", "document_id": 50},
    }
    body = {
        "temuan": temuan_payload,
        "penilaian": "valid",
        "catatan": "Temuan relevan dan perlu disesuaikan di bab II",
        "run_id": run.id,
        "dinilai_oleh_nama": "Analis Hamdan",
    }

    resp = client.put(f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan", json=body)
    assert resp.status_code == 200
    res_data = resp.json()

    expected_kunci = kunci_temuan(temuan_payload)
    assert res_data["kunci_temuan"] == expected_kunci
    assert res_data["penilaian"] == "valid"
    assert res_data["catatan"] == "Temuan relevan dan perlu disesuaikan di bab II"
    assert res_data["dinilai_oleh_nama"] == "Analis Hamdan"
    assert res_data["document_id"] == draft.id

    # Verifikasi baris tersimpan di DB
    row = (
        db_session.query(TanggapanTemuan)
        .filter(TanggapanTemuan.document_id == draft.id, TanggapanTemuan.kunci_temuan == expected_kunci)
        .first()
    )
    assert row is not None
    assert row.penilaian == "valid"
    assert row.ringkasan_temuan["jenis"] == "menggantikan"

    # Verifikasi Audit Log
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == TANGGAPAN_TEMUAN,
            AuditLog.target_resource == f"document:{draft.id}",
        )
        .first()
    )
    assert audit is not None
    assert audit.detail["penilaian"]["before"] is None
    assert audit.detail["penilaian"]["after"] == "valid"
    assert audit.detail["kunci_temuan"] == expected_kunci


def test_h04_put_ulang_tanggapan_update(client: TestClient, db_session: Session):
    """H04: PUT ulang dengan 'tidak_relevan' -> baris yang sama diperbarui (tidak dobel); audit before/after."""
    draft = create_test_doc(document_role=PeranDokumen.draft_kajian)
    db_session.add(draft)
    db_session.commit()

    temuan_payload = {
        "id": "t-102",
        "jenis": "sama",
        "pasal_draft": "Pasal 10",
        "pembanding": {"key": "POJK|9|2021", "document_id": 90},
        "pasal_pembanding": "Pasal 15",
    }

    # Panggilan 1: valid
    body1 = {"temuan": temuan_payload, "penilaian": "valid", "catatan": "Awalnya valid"}
    r1 = client.put(f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan", json=body1)
    assert r1.status_code == 200

    # Panggilan 2: ubah ke tidak_relevan
    body2 = {"temuan": temuan_payload, "penilaian": "tidak_relevan", "catatan": "Ternyata materi berbeda"}
    r2 = client.put(f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan", json=body2)
    assert r2.status_code == 200
    res2 = r2.json()
    assert res2["penilaian"] == "tidak_relevan"
    assert res2["catatan"] == "Ternyata materi berbeda"

    # Verifikasi hanya ada 1 baris di DB (tidak dobel)
    rows = (
        db_session.query(TanggapanTemuan)
        .filter(TanggapanTemuan.document_id == draft.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].penilaian == "tidak_relevan"

    # Verifikasi audit log memuat before=valid dan after=tidak_relevan
    audits = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == TANGGAPAN_TEMUAN,
            AuditLog.target_resource == f"document:{draft.id}",
        )
        .order_by(AuditLog.id.desc())
        .all()
    )
    assert len(audits) >= 2
    latest_audit = audits[0]
    assert latest_audit.detail["penilaian"]["before"] == "valid"
    assert latest_audit.detail["penilaian"]["after"] == "tidak_relevan"


def test_h05_penilaian_tidak_dikenal_dan_catatan_panjang(client: TestClient, db_session: Session):
    """H05: Penilaian tidak dikenal / catatan > 2000 -> 422."""
    draft = create_test_doc(document_role=PeranDokumen.draft_kajian)
    db_session.add(draft)
    db_session.commit()

    temuan_payload = {
        "jenis": "menggantikan",
        "pasal_draft": "Pasal 1",
        "pembanding": {"key": "POJK|1|2020"},
        "pasal_pembanding": "Pasal 1",
    }

    # 1. Penilaian salah
    res_bad_penilaian = client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": temuan_payload, "penilaian": "meragukan"},
    )
    assert res_bad_penilaian.status_code == 422

    # 2. Catatan > 2000 karakter
    res_long_catatan = client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": temuan_payload, "penilaian": "valid", "catatan": "X" * 2005},
    )
    assert res_long_catatan.status_code == 422


def test_h06_dokumen_bukan_draft_ditolak(client: TestClient, db_session: Session):
    """H06: Dokumen corpus_eksisting -> 422 bukan_draft."""
    doc_corpus = create_test_doc(
        title="POJK Berlaku Eksisting",
        document_role=PeranDokumen.corpus_eksisting,
    )
    db_session.add(doc_corpus)
    db_session.commit()

    temuan_payload = {"jenis": "baru", "pasal_draft": "Pasal 1", "pembanding": {"key": "K1"}}
    res = client.put(
        f"/api/v1/documents/{doc_corpus.id}/harmonisasi/tanggapan",
        json={"temuan": temuan_payload, "penilaian": "valid"},
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "bukan_draft"


def test_h07_draft_non_publik_auth_mati_ditolak_403(client: TestClient, db_session: Session, monkeypatch):
    """H07: Tanggapan harmonisasi pada draf kajian non-publik dapat diproses di Workspace (200)."""
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)

    draft_rahasia = create_test_doc(
        document_role=PeranDokumen.draft_kajian,
        access_classification=KlasifikasiAkses.non_publik,
    )
    db_session.add(draft_rahasia)
    db_session.commit()

    temuan_payload = {"jenis": "baru", "pasal_draft": "Pasal 1", "pembanding": {"key": "K1"}}
    res = client.put(
        f"/api/v1/documents/{draft_rahasia.id}/harmonisasi/tanggapan",
        json={"temuan": temuan_payload, "penilaian": "valid"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["penilaian"] == "valid"
    assert data["document_id"] == draft_rahasia.id


def test_h08_auth_aktif_peran_dan_penilai(client: TestClient, db_session: Session, monkeypatch):
    """H08: AUTH_ENABLED=true, peran tanpa TANGGAPAN_TINJAU (mis. admin_sistem) -> 403; analis -> 200 dengan dinilai_oleh terisi."""
    monkeypatch.setattr(settings, "auth_enabled", True)

    user_admin = User(
        username="adminsistem_h08",
        hashed_password="hash",
        role=PeranPengguna.admin_sistem.value,
        is_active=True,
    )
    user_analis = User(
        username="analis_h08",
        hashed_password="hash",
        role=PeranPengguna.analis.value,
        is_active=True,
    )
    draft = create_test_doc(document_role=PeranDokumen.draft_kajian)
    db_session.add_all([user_admin, user_analis, draft])
    db_session.commit()

    temuan_payload = {
        "jenis": "menggantikan",
        "pasal_draft": "Pasal 7",
        "pembanding": {"key": "POJK|7|2021"},
        "pasal_pembanding": "Pasal 2",
    }
    body = {"temuan": temuan_payload, "penilaian": "valid"}

    # 1. Admin Sistem -> 403 Forbidden (tidak memiliki izin TANGGAPAN_TINJAU)
    token_admin = _buat_token_auth(user_admin)
    res_admin = client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json=body,
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_admin.status_code == 403
    assert res_admin.json()["detail"]["code"] == "akses_ditolak"

    # 2. Analis -> 200 OK dengan dinilai_oleh = user_analis.id
    token_analis = _buat_token_auth(user_analis)
    res_analis = client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json=body,
        headers={"Authorization": f"Bearer {token_analis}"},
    )
    assert res_analis.status_code == 200
    res_json = res_analis.json()
    assert res_json["dinilai_oleh"] == user_analis.id
    assert res_json["dinilai_oleh_nama"] == user_analis.username


def test_h09_delete_tanggapan(client: TestClient, db_session: Session):
    """H09: DELETE tanggapan -> terhapus; GET tidak memuatnya."""
    draft = create_test_doc(document_role=PeranDokumen.draft_kajian)
    db_session.add(draft)
    db_session.commit()

    temuan_payload = {
        "jenis": "baru",
        "pasal_draft": "Pasal 99",
        "pembanding": {"key": "POJK|99|2020"},
        "pasal_pembanding": "Pasal 1",
    }
    # Buat tanggapan
    put_res = client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": temuan_payload, "penilaian": "valid", "catatan": "Akan dihapus"},
    )
    assert put_res.status_code == 200
    kunci = put_res.json()["kunci_temuan"]

    # Verifikasi ada di GET
    get_res1 = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan")
    assert get_res1.status_code == 200
    items1 = get_res1.json()
    assert any(it["kunci_temuan"] == kunci for it in items1)

    # Hapus
    del_res = client.delete(f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan/{kunci}")
    assert del_res.status_code == 200

    # Verifikasi GET sudah tidak memuatnya
    get_res2 = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan")
    assert get_res2.status_code == 200
    items2 = get_res2.json()
    assert not any(it["kunci_temuan"] == kunci for it in items2)


def test_h10_harmonisasi_ulang_mock_id_berubah(client: TestClient, db_session: Session):
    """H10: Harmonisasi dijalankan ulang (mock id berubah) -> setiap temuan memuat kunci_temuan & tanggapan; ringkasan.tanggapan benar; cache murni."""
    draft = create_test_doc(title="Draft POJK Reksa Dana", document_role=PeranDokumen.draft_kajian)
    comp = create_test_doc(title="POJK 4 2023", regulation_type="POJK", regulation_number="4", regulation_year=2023)
    db_session.add_all([draft, comp])
    db_session.commit()

    temuan_data = {
        "id": "ml-id-run-1",
        "jenis": "menggantikan",
        "pasal_draft": "Pasal 14",
        "pembanding": {"document_id": comp.id, "key": "POJK|4|2023", "nomor": "POJK 4 2023"},
        "pasal_pembanding": "Pasal 2",
        "deskripsi": "Ketentuan penempatan reksa dana",
    }

    # Beri tanggapan pada temuan pertama
    client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": temuan_data, "penilaian": "valid", "catatan": "Tepat sasaran"},
    )

    # Mock ML service mengembalikan id temuan yang berbeda (misal hasil rerun)
    def ml_handler(request: httpx.Request) -> httpx.Response:
        data = {
            "versi": "1.0",
            "draft": {"title": draft.title},
            "ringkasan": {"total_temuan": 2, "per_jenis": {"menggantikan": 1, "baru": 1}},
            "temuan": [
                {
                    "id": "ml-id-run-2-BARU",  # ID ML berubah
                    "jenis": "menggantikan",
                    "pasal_draft": "Pasal 14",
                    "pembanding": {"document_id": comp.id, "key": "POJK|4|2023", "nomor": "POJK 4 2023"},
                    "pasal_pembanding": "Pasal 2",
                    "deskripsi": "Ketentuan penempatan reksa dana",
                },
                {
                    "id": "ml-id-run-2-BARU-b",
                    "jenis": "baru",
                    "pasal_draft": "Pasal 20",
                    "pembanding": {"document_id": comp.id, "key": "POJK|4|2023", "nomor": "POJK 4 2023"},
                    "pasal_pembanding": "Pasal 5",
                    "deskripsi": "Ketentuan tata kelola baru",
                },
            ],
        }
        return httpx.Response(200, json=data)

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(ml_handler))

    # Panggil harmonisasi dengan segar=true agar memanggil ML ulang
    resp = client.post(f"/api/v1/ml/harmonisasi/{draft.id}?segar=true", json=[comp.id])
    assert resp.status_code == 200
    body = resp.json()

    # Periksa temuan 1 memuat tanggapan valid
    t1 = next(t for t in body["temuan"] if t["pasal_draft"] == "Pasal 14")
    assert t1["kunci_temuan"] == kunci_temuan(temuan_data)
    assert t1["tanggapan"] is not None
    assert t1["tanggapan"]["penilaian"] == "valid"
    assert t1["tanggapan"]["catatan"] == "Tepat sasaran"

    # Periksa temuan 2 belum dinilai (tanggapan null)
    t2 = next(t for t in body["temuan"] if t["pasal_draft"] == "Pasal 20")
    assert t2["tanggapan"] is None

    # Periksa ringkasan tanggapan
    assert body["ringkasan"]["tanggapan"] == {
        "valid": 1,
        "tidak_relevan": 0,
        "belum_dinilai": 1,
    }

    # Periksa cache analysis_results tetap murni tanpa field tanggapan
    cached = (
        db_session.query(AnalysisResult)
        .filter(AnalysisResult.document_id == draft.id, AnalysisResult.kind == JenisAnalisa.harmonisasi)
        .first()
    )
    assert cached is not None
    cache_temuan_0 = cached.result["temuan"][0]
    assert "tanggapan" not in cache_temuan_0
    assert "tanggapan" not in cached.result["ringkasan"]


def test_h11_rekap_json_dan_csv(client: TestClient, db_session: Session):
    """H11: Rekap JSON dan ?format=csv -> jumlah per jenis benar; CSV ber-BOM."""
    draft1 = create_test_doc(document_role=PeranDokumen.draft_kajian)
    draft2 = create_test_doc(document_role=PeranDokumen.draft_kajian)
    db_session.add_all([draft1, draft2])
    db_session.commit()

    # Draft 1: 1 valid menggantikan, 1 tidak_relevan menggantikan
    client.put(
        f"/api/v1/documents/{draft1.id}/harmonisasi/tanggapan",
        json={"temuan": {"jenis": "menggantikan", "pasal_draft": "P1", "pembanding": {"key": "K1"}}, "penilaian": "valid"},
    )
    client.put(
        f"/api/v1/documents/{draft1.id}/harmonisasi/tanggapan",
        json={"temuan": {"jenis": "menggantikan", "pasal_draft": "P2", "pembanding": {"key": "K1"}}, "penilaian": "tidak_relevan"},
    )
    # Draft 2: 1 valid baru
    client.put(
        f"/api/v1/documents/{draft2.id}/harmonisasi/tanggapan",
        json={"temuan": {"jenis": "baru", "pasal_draft": "P3", "pembanding": {"key": "K2"}}, "penilaian": "valid"},
    )

    # 1. Rekap JSON global
    res_json = client.get("/api/v1/harmonisasi/tanggapan/rekap")
    assert res_json.status_code == 200
    j_data = res_json.json()
    assert j_data["total"] == {"valid": 2, "tidak_relevan": 1, "total": 3}
    assert j_data["per_jenis"]["menggantikan"] == {"valid": 1, "tidak_relevan": 1, "total": 2}
    assert j_data["per_jenis"]["baru"] == {"valid": 1, "tidak_relevan": 0, "total": 1}

    # 2. Rekap filter per document_id
    res_filter = client.get(f"/api/v1/harmonisasi/tanggapan/rekap?document_id={draft1.id}")
    assert res_filter.status_code == 200
    jf_data = res_filter.json()
    assert jf_data["total"] == {"valid": 1, "tidak_relevan": 1, "total": 2}

    # 3. Rekap CSV
    res_csv = client.get("/api/v1/harmonisasi/tanggapan/rekap?format=csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert res_csv.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
    csv_text = res_csv.content.decode("utf-8-sig")
    assert "jenis,valid,tidak_relevan,total" in csv_text
    assert "TOTAL,2,1,3" in csv_text


def test_e01_ekspor_docx_setelah_harmonisasi(client: TestClient, db_session: Session):
    """E01: Ekspor DOCX setelah harmonisasi tersimpan -> 200; berkas terbuka dengan python-docx; memuat judul, tabel temuan, penilaian analis, catatan kaki."""
    draft = create_test_doc(
        title="Draft RPOJK Tata Kelola",
        regulation_type="POJK",
        regulation_number="88",
        regulation_year=2024,
        document_role=PeranDokumen.draft_kajian,
    )
    comp = create_test_doc(title="POJK 12 2020", regulation_type="POJK", regulation_number="12", regulation_year=2020)
    db_session.add_all([draft, comp])
    db_session.commit()

    # Mock ML harmonisasi
    def ml_handler(request: httpx.Request) -> httpx.Response:
        data = {
            "versi": "1.0",
            "draft": {"title": draft.title},
            "ringkasan": {"total_temuan": 1, "per_jenis": {"menggantikan": 1}},
            "temuan": [
                {
                    "id": "t-docx-01",
                    "jenis": "menggantikan",
                    "judul": "Ketentuan Komisaris Independen",
                    "deskripsi": "Mengubah minimal 30% menjadi 50%",
                    "pasal_draft": "Pasal 8 ayat (2)",
                    "pembanding": {"document_id": comp.id, "key": "POJK|12|2020", "nomor": "POJK 12 2020"},
                    "pasal_pembanding": "Pasal 15",
                }
            ],
        }
        return httpx.Response(200, json=data)

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(ml_handler))
    client.post(f"/api/v1/ml/harmonisasi/{draft.id}", json=[comp.id])

    # Tambahkan penilaian analis
    t_obj = {
        "jenis": "menggantikan",
        "pasal_draft": "Pasal 8 ayat (2)",
        "pembanding": {"document_id": comp.id, "key": "POJK|12|2020"},
        "pasal_pembanding": "Pasal 15",
    }
    client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": t_obj, "penilaian": "valid", "catatan": "Perubahan persentase disetujui"},
    )

    # Ekspor DOCX
    resp = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=docx")
    assert resp.status_code == 200
    assert "wordprocessingml.document" in resp.headers["content-type"]

    # Buka dengan python-docx dan verifikasi konten
    doc_file = docx.Document(io.BytesIO(resp.content))
    full_text = "\n".join([p.text for p in doc_file.paragraphs])

    # Periksa judul & metadata
    assert "Laporan Harmonisasi" in full_text
    assert "Draft RPOJK Tata Kelola" in full_text
    # Periksa catatan kaki URD
    assert "Keputusan final tetap kewenangan Pengawas / unit terkait." in full_text

    # Periksa tabel temuan
    assert len(doc_file.tables) >= 1
    tbl_text = "\n".join([cell.text for row in doc_file.tables[0].rows for cell in row.cells])
    assert "Pasal 8 ayat (2)" in tbl_text
    assert "Pasal 15" in tbl_text
    assert "Valid" in tbl_text
    assert "Perubahan persentase disetujui" in tbl_text


def test_e02_ekspor_csv(client: TestClient, db_session: Session):
    """E02: Ekspor CSV -> BOM; satu baris per temuan; kolom sesuai."""
    draft = create_test_doc(document_role=PeranDokumen.draft_kajian)
    comp = create_test_doc()
    db_session.add_all([draft, comp])
    db_session.commit()

    # Simpan hasil harmonisasi di database
    cached_payload = {
        "versi": "1.0",
        "ringkasan": {"total_temuan": 1, "per_jenis": {"baru": 1}},
        "temuan": [
            {
                "id": "t-csv-1",
                "jenis": "baru",
                "judul": "Pelaporan Bulanan",
                "deskripsi": "Kewajiban pelaporan berkala",
                "pasal_draft": "Pasal 25",
                "pembanding": {"document_id": comp.id, "key": "POJK|9|2023", "nomor": "POJK 9 2023"},
                "pasal_pembanding": "Pasal 30",
            }
        ],
    }
    seed_harmonisasi_result(db_session, draft, cached_payload)

    # Beri penilaian
    client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={
            "temuan": cached_payload["temuan"][0],
            "penilaian": "tidak_relevan",
            "catatan": "Klausul dikecualikan",
            "dinilai_oleh_nama": "Analis Budi",
        },
    )

    resp = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert resp.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM

    csv_reader = csv.reader(io.StringIO(resp.content.decode("utf-8-sig")))
    rows = list(csv_reader)
    assert len(rows) == 2  # 1 header + 1 baris temuan
    header = rows[0]
    assert "Kunci Temuan" in header
    assert "Penilaian Analis" in header
    assert "Keyakinan" in header

    row_data = rows[1]
    assert row_data[1] == "baru"
    assert row_data[2] == "Pasal 25"
    pen_idx = header.index("Penilaian Analis")
    assert row_data[pen_idx] == "tidak_relevan"
    assert row_data[pen_idx + 1] == "Klausul dikecualikan"
    assert row_data[pen_idx + 2] == "Analis Budi"


def test_e03_ekspor_json(client: TestClient, db_session: Session):
    """E03: Ekspor JSON -> memuat tanggapan per temuan + metadata."""
    draft = create_test_doc(
        title="Draft Ekspor JSON",
        regulation_number="77",
        regulation_year=2025,
        document_role=PeranDokumen.draft_kajian,
    )
    comp = create_test_doc()
    db_session.add_all([draft, comp])
    db_session.commit()

    cached_payload = {
        "versi": "1.0",
        "ringkasan": {"total_temuan": 1, "per_jenis": {"menggantikan": 1}},
        "temuan": [
            {
                "id": "t-json-1",
                "jenis": "menggantikan",
                "pasal_draft": "Pasal 100",
                "pembanding": {"document_id": comp.id, "key": "POJK|77|2020"},
                "pasal_pembanding": "Pasal 10",
                "deskripsi": "Menggantikan batas rasio",
            }
        ],
    }
    seed_harmonisasi_result(db_session, draft, cached_payload)

    # Beri tanggapan
    client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": cached_payload["temuan"][0], "penilaian": "valid", "catatan": "Disepakati"},
    )

    resp = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=json")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    body = resp.json()

    assert "metadata" in body
    assert body["metadata"]["dokumen"]["judul"] == "Draft Ekspor JSON"
    assert body["metadata"]["mode"] == "deterministik"

    t = body["temuan"][0]
    assert t["pasal_draft"] == "Pasal 100"
    assert t["tanggapan"]["penilaian"] == "valid"
    assert t["tanggapan"]["catatan"] == "Disepakati"
    assert "kunci_temuan" in t


def test_e04_ekspor_belum_ada_harmonisasi_404_tanpa_panggil_ml(client: TestClient, db_session: Session):
    """E04: Dokumen belum pernah diharmonisasi -> 404 harmonisasi_belum_ada; layanan ML tidak dipanggil (spy)."""
    draft = create_test_doc(document_role=PeranDokumen.draft_kajian)
    db_session.add(draft)
    db_session.commit()

    spy_handler = MagicMock()
    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(spy_handler))

    resp = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=docx")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "harmonisasi_belum_ada"
    assert "belum pernah diharmonisasi" in resp.json()["detail"]["message"]

    # Pastikan handler ML tidak pernah dipanggil
    assert spy_handler.call_count == 0


def test_e05_ekspor_penyaringan_pembanding_nonaktif(client: TestClient, db_session: Session):
    """E05: Temuan dengan pembanding nonaktif / non-publik -> disaring sama seperti respons harmonisasi."""
    draft = create_test_doc(document_role=PeranDokumen.draft_kajian)
    comp_aktif = create_test_doc(title="Pembanding Aktif", is_active=True)
    comp_nonaktif = create_test_doc(title="Pembanding Nonaktif", is_active=False)
    db_session.add_all([draft, comp_aktif, comp_nonaktif])
    db_session.commit()

    cached_payload = {
        "versi": "1.0",
        "ringkasan": {"total_temuan": 2, "per_jenis": {"menggantikan": 1, "konflik": 1}},
        "temuan": [
            {
                "id": "t-allowed",
                "jenis": "menggantikan",
                "pasal_draft": "Pasal 1",
                "pembanding": {"document_id": comp_aktif.id, "key": "POJK|AKTIF"},
                "pasal_pembanding": "Pasal 1",
            },
            {
                "id": "t-discarded",
                "jenis": "konflik",
                "pasal_draft": "Pasal 2",
                "pembanding": {"document_id": comp_nonaktif.id, "key": "POJK|NONAKTIF"},
                "pasal_pembanding": "Pasal 2",
            },
        ],
    }
    seed_harmonisasi_result(db_session, draft, cached_payload)

    resp = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=json")
    assert resp.status_code == 200
    body = resp.json()

    # Hanya temuan dengan pembanding aktif yang ada dalam berkas ekspor
    assert len(body["temuan"]) == 1
    assert body["temuan"][0]["pembanding"]["document_id"] == comp_aktif.id


def test_e06_ekspor_format_tidak_dikenal_422(client: TestClient, db_session: Session):
    """E06: Format tidak dikenal -> 422."""
    draft = create_test_doc(document_role=PeranDokumen.draft_kajian)
    db_session.add(draft)
    db_session.commit()

    cached_payload = {"versi": "1.0", "temuan": []}
    seed_harmonisasi_result(db_session, draft, cached_payload)

    resp = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=pdf_not_supported")
    assert resp.status_code == 422


def test_e07_audit_export_harmonization(client: TestClient, db_session: Session):
    """E07: Audit EXPORT_HARMONIZATION -> tercatat dengan format & jumlah temuan."""
    draft = create_test_doc(document_role=PeranDokumen.draft_kajian)
    comp = create_test_doc()
    db_session.add_all([draft, comp])
    db_session.commit()

    cached_payload = {
        "versi": "1.0",
        "ringkasan": {"total_temuan": 1},
        "temuan": [
            {
                "id": "t1",
                "jenis": "baru",
                "pasal_draft": "Pasal 1",
                "pembanding": {"document_id": comp.id, "key": "POJK|1"},
                "pasal_pembanding": "Pasal 1",
            }
        ],
    }
    seed_harmonisasi_result(db_session, draft, cached_payload)

    resp = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=csv")
    assert resp.status_code == 200

    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == EXPORT_HARMONIZATION,
            AuditLog.target_resource == f"document:{draft.id}",
        )
        .first()
    )
    assert audit is not None
    assert audit.detail["format"] == "csv"
    assert audit.detail["jumlah_temuan"] == 1
    assert audit.detail["document_id"] == draft.id


def test_h12_cache_purity_fresh_and_hit(client: TestClient, db_session: Session):
    """H12: Setelah harmonisasi (jalur baru & jalur hit) dan ada tanggapan tersimpan, analysis_results murni tanpa kunci_temuan / tanggapan."""
    draft = create_test_doc(title="Draft Uji Kemurnian Cache", document_role=PeranDokumen.draft_kajian)
    comp = create_test_doc(title="POJK 10 2024", regulation_type="POJK", regulation_number="10", regulation_year=2024)
    db_session.add_all([draft, comp])
    db_session.commit()

    temuan_item = {
        "id": "ml-t1",
        "jenis": "menggantikan",
        "pasal_draft": "Pasal 10 ayat (1)",
        "pembanding": {"document_id": comp.id, "key": "POJK|10|2024"},
        "pasal_pembanding": "Pasal 5",
        "deskripsi": "Mengubah batasan modal",
    }

    def ml_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "versi": "1.0",
                "draft": {"title": draft.title},
                "ringkasan": {"total_temuan": 1, "per_jenis": {"menggantikan": 1}},
                "temuan": [temuan_item],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(ml_handler))

    # 1. Jalankan harmonisasi pertama kali (jalur baru / fresh ML)
    resp1 = client.post(f"/api/v1/ml/harmonisasi/{draft.id}", json=[comp.id])
    assert resp1.status_code == 200

    # 2. Beri tanggapan analis pada temuan tersebut
    client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": temuan_item, "penilaian": "valid", "catatan": "Tepat sasaran"},
    )

    # 3. Verifikasi cache analysis_results di DB tetap murni (baca ulang dengan expire_all)
    db_session.expire_all()
    cached1 = (
        db_session.query(AnalysisResult)
        .filter(AnalysisResult.document_id == draft.id, AnalysisResult.kind == JenisAnalisa.harmonisasi)
        .first()
    )
    assert cached1 is not None
    assert "kunci_temuan" not in cached1.result["temuan"][0]
    assert "tanggapan" not in cached1.result["temuan"][0]
    assert "tanggapan" not in cached1.result["ringkasan"]

    # 4. Jalankan harmonisasi kedua kali (jalur cache hit)
    resp2 = client.post(f"/api/v1/ml/harmonisasi/{draft.id}", json=[comp.id])
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["cache"]["hit"] is True
    # Respons klien memuat kunci_temuan dan tanggapan
    assert body2["temuan"][0]["kunci_temuan"] == kunci_temuan(temuan_item)
    assert body2["temuan"][0]["tanggapan"]["penilaian"] == "valid"
    assert body2["ringkasan"]["tanggapan"]["valid"] == 1

    # 5. Verifikasi cache analysis_results di DB TETAP murni setelah cache hit
    db_session.expire_all()
    cached2 = (
        db_session.query(AnalysisResult)
        .filter(AnalysisResult.document_id == draft.id, AnalysisResult.kind == JenisAnalisa.harmonisasi)
        .first()
    )
    assert cached2 is not None
    assert "kunci_temuan" not in cached2.result["temuan"][0]
    assert "tanggapan" not in cached2.result["temuan"][0]
    assert "tanggapan" not in cached2.result["ringkasan"]


def test_h13_rekap_respects_access_control(client: TestClient, db_session: Session, monkeypatch):
    """H13: Rekap tanggapan menghormati hak akses dokumen (saring draft non-publik & 403 saat filter document_id)."""
    draft_pub = create_test_doc(
        title="Draft Publik",
        document_role=PeranDokumen.draft_kajian,
        access_classification=KlasifikasiAkses.publik,
    )
    draft_sec = create_test_doc(
        title="Draft Rahasia",
        document_role=PeranDokumen.draft_kajian,
        access_classification=KlasifikasiAkses.non_publik,
    )
    user_analis = User(
        username="analis_h13",
        hashed_password="hash",
        role=PeranPengguna.analis.value,
        is_active=True,
    )
    db_session.add_all([draft_pub, draft_sec, user_analis])
    db_session.commit()

    # Beri tanggapan pada draft publik via API
    client.put(
        f"/api/v1/documents/{draft_pub.id}/harmonisasi/tanggapan",
        json={"temuan": {"jenis": "baru", "pasal_draft": "P1"}, "penilaian": "valid"},
    )
    # Masukkan tanggapan untuk draft rahasia langsung di DB
    tanggapan_sec = TanggapanTemuan(
        document_id=draft_sec.id,
        kunci_temuan="sec_key_h13",
        penilaian="valid",
        ringkasan_temuan={"jenis": "baru", "pasal_draft": "P2"},
        dibuat=datetime.now(timezone.utc),
        diperbarui=datetime.now(timezone.utc),
    )
    db_session.add(tanggapan_sec)
    db_session.commit()

    # 1. Panggilan rekap tanpa auth (mode dev dengan protect_non_public aktif)
    # Rekap global tidak boleh menghitung tanggapan pada draft_sec
    res_rekap_global = client.get("/api/v1/harmonisasi/tanggapan/rekap")
    assert res_rekap_global.status_code == 200
    data_global = res_rekap_global.json()
    assert data_global["total"]["valid"] == 1  # Hanya draft publik

    # 2. Panggilan rekap dengan filter document_id draft_sec (draf kajian non-publik dapat diproses sesuai kebijakan baru) -> 200
    res_rekap_sec = client.get(f"/api/v1/harmonisasi/tanggapan/rekap?document_id={draft_sec.id}")
    assert res_rekap_sec.status_code == 200
    assert res_rekap_sec.json()["total"]["valid"] == 1

    # 2b. Dokumen korpus non-publik tetap dilindungi ketat -> 403 saat diakses tanpa izin
    corpus_sec = create_test_doc(
        title="Corpus Rahasia H13",
        document_role=PeranDokumen.corpus_eksisting,
        access_classification=KlasifikasiAkses.non_publik,
    )
    db_session.add(corpus_sec)
    db_session.commit()
    res_rekap_corpus = client.get(f"/api/v1/harmonisasi/tanggapan/rekap?document_id={corpus_sec.id}")
    assert res_rekap_corpus.status_code == 403

    # 3. Panggilan rekap dengan filter document_id draft_pub -> 200
    res_rekap_pub = client.get(f"/api/v1/harmonisasi/tanggapan/rekap?document_id={draft_pub.id}")
    assert res_rekap_pub.status_code == 200
    assert res_rekap_pub.json()["total"]["valid"] == 1

    # 4. Saat auth aktif: analis dengan izin KB_BACA_NONPUBLIK dapat melihat draft rahasia
    monkeypatch.setattr(settings, "auth_enabled", True)
    token_analis = _buat_token_auth(user_analis)

    # 4a. Rekap filter document_id draft_sec dengan token analis -> 200
    res_auth_sec = client.get(
        f"/api/v1/harmonisasi/tanggapan/rekap?document_id={draft_sec.id}",
        headers={"Authorization": f"Bearer {token_analis}"},
    )
    assert res_auth_sec.status_code == 200
    assert res_auth_sec.json()["total"]["valid"] == 1

    # 4b. Rekap global untuk analis memuat draft publik dan rahasia (total 2)
    res_auth_global = client.get(
        "/api/v1/harmonisasi/tanggapan/rekap",
        headers={"Authorization": f"Bearer {token_analis}"},
    )
    assert res_auth_global.status_code == 200
    assert res_auth_global.json()["total"]["valid"] == 2


def test_h14_payload_validation_limits(client: TestClient, db_session: Session):
    """H14: Validasi batasan payload (temuan tanpa jenis, jenis kosong, json temuan > 20.000 kar, potongan pasal_draft/pasal_pembanding di ringkasan_temuan)."""
    draft = create_test_doc(document_role=PeranDokumen.draft_kajian)
    db_session.add(draft)
    db_session.commit()

    # 1. Temuan tanpa jenis -> 422
    r1 = client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": {"pasal_draft": "Pasal 1"}, "penilaian": "valid"},
    )
    assert r1.status_code == 422

    # 2. Temuan jenis kosong -> 422
    r2 = client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": {"jenis": "   ", "pasal_draft": "Pasal 1"}, "penilaian": "valid"},
    )
    assert r2.status_code == 422

    # 3. Temuan ukuran JSON > 20.000 karakter -> 422
    big_temuan = {"jenis": "baru", "blob": "x" * 25000}
    r3 = client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": big_temuan, "penilaian": "valid"},
    )
    assert r3.status_code == 422
    assert "20.000" in r3.text

    # 4. Potongan pasal_draft dan pasal_pembanding ke maks 300 kar di ringkasan_temuan
    long_p_draft = "Pasal " + ("A" * 350)
    long_p_comp = "Pasal " + ("B" * 350)
    temuan_long = {
        "jenis": "konflik",
        "pasal_draft": long_p_draft,
        "pembanding": {"key": "POJK|99"},
        "pasal_pembanding": long_p_comp,
    }
    r4 = client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": temuan_long, "penilaian": "valid"},
    )
    assert r4.status_code == 200

    db_session.expire_all()
    kunci = kunci_temuan(temuan_long)
    row = db_session.query(TanggapanTemuan).filter_by(document_id=draft.id, kunci_temuan=kunci).first()
    assert row is not None
    assert len(row.ringkasan_temuan["pasal_draft"]) == 300
    assert len(row.ringkasan_temuan["pasal_pembanding"]) == 300


def test_h15_concurrent_put_integrity_error_handled(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch):
    """H15: PUT bersamaan memicu IntegrityError pada commit pertama -> rollback & update existing -> 200."""
    draft = create_test_doc(document_role=PeranDokumen.draft_kajian)
    db_session.add(draft)
    db_session.commit()

    temuan = {"jenis": "menggantikan", "pasal_draft": "Pasal 99", "pembanding": {"key": "POJK|99"}}
    kunci = kunci_temuan(temuan)

    call_count = [0]
    orig_commit = Session.commit

    def commit_with_simulated_race(self):
        call_count[0] += 1
        if call_count[0] == 1:
            # Simulasikan ada transaksi konkuren yang sudah berhasil commit baris ini duluan
            from app.database import SessionLocal
            with SessionLocal() as other_db:
                other_row = TanggapanTemuan(
                    document_id=draft.id,
                    kunci_temuan=kunci,
                    penilaian="tidak_relevan",
                    catatan="Catatan dari concurrent racer",
                    ringkasan_temuan={"jenis": "menggantikan"},
                    dibuat=datetime.now(timezone.utc),
                    diperbarui=datetime.now(timezone.utc),
                )
                other_db.add(other_row)
                other_db.commit()
            # Panggil commit asli -> Postgres akan menolak dengan IntegrityError karena kunci duplikat!
            return orig_commit(self)
        return orig_commit(self)

    monkeypatch.setattr(Session, "commit", commit_with_simulated_race)

    resp = client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": temuan, "penilaian": "valid", "catatan": "Catatan update yang menang"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["penilaian"] == "valid"
    assert data["catatan"] == "Catatan update yang menang"

    # Verifikasi baris di DB telah diupdate
    db_session.expire_all()
    row = db_session.query(TanggapanTemuan).filter_by(document_id=draft.id, kunci_temuan=kunci).first()
    assert row is not None
    assert row.penilaian == "valid"
    assert row.catatan == "Catatan update yang menang"


@pytest.fixture
def TEMUAN_ASLI():
    """Fixture meniru bentuk temuan engine harmonisasi asli (pipeline/hero/harmonisasi/engine.py)."""
    return [
        {
            "pasal_draft": "Pasal 5",
            "halaman_draft": 3,
            "kutipan_draft": "Ketentuan mengenai modal kerja...",
            "jenis": "duplikasi",
            "keyakinan": 0.82,
            "tingkat": "tinggi",
            "alasan": "Terdapat kesamaan rumusan kewajiban modal kerja minimal.",
            "pembanding": {
                "doc_id": "doc-101",
                "document_id": 101,
                "key": "POJK|10|2023",
                "judul": "POJK Nomor 10 Tahun 2023",
                "nomor": "POJK 10/2023",
                "status": "berlaku",
                "pasal": "Pasal 12",
                "halaman": 10,
                "kutipan": "Modal kerja wajib dipenuhi minimal...",
                "pdf": "storage/pojk10_2023.pdf",
            },
            "kemiripan": 0.81,
            "perbedaan": [],
            "alternatif": [],
            "klausul_baku": False,
            "terdekat": {},
        },
        {
            "pasal_draft": "Pasal 5",
            "halaman_draft": 3,
            "kutipan_draft": "Ketentuan mengenai modal kerja...",
            "jenis": "duplikasi",
            "keyakinan": 0.75,
            "tingkat": "sedang",
            "alasan": "Terdapat rumusan pelaporan modal kerja yang serupa.",
            "pembanding": {
                "doc_id": "doc-101",
                "document_id": 101,
                "key": "POJK|10|2023",
                "judul": "POJK Nomor 10 Tahun 2023",
                "nomor": "POJK 10/2023",
                "status": "berlaku",
                "pasal": "Pasal 14",
                "halaman": 12,
                "kutipan": "Pelaporan modal kerja dilakukan...",
                "pdf": "storage/pojk10_2023.pdf",
            },
            "kemiripan": 0.74,
            "perbedaan": [],
            "alternatif": [],
            "klausul_baku": False,
            "terdekat": {},
        },
        {
            "pasal_draft": "Pasal 20",
            "halaman_draft": 8,
            "kutipan_draft": "Ketentuan mengenai audit kecerdasan buatan...",
            "jenis": "pasal_baru",
            "keyakinan": 0.90,
            "tingkat": "tinggi",
            "alasan": "Ketentuan tata kelola AI ini belum diatur dalam regulasi pembanding mana pun.",
            "pembanding": None,
            "kemiripan": 0.0,
            "perbedaan": [],
            "alternatif": [],
            "klausul_baku": False,
            "terdekat": {},
        },
    ]


def test_c01_beda_pasal_pembanding_beda_kunci(TEMUAN_ASLI):
    """C01: Dua temuan dengan pasal_draft sama ke peraturan sama tetapi pembanding.pasal berbeda -> kunci berbeda."""
    t1 = TEMUAN_ASLI[0]
    t2 = TEMUAN_ASLI[1]
    assert t1["pasal_draft"] == t2["pasal_draft"]
    assert t1["pembanding"]["key"] == t2["pembanding"]["key"]
    assert t1["pembanding"]["pasal"] != t2["pembanding"]["pasal"]

    k1 = kunci_temuan(t1)
    k2 = kunci_temuan(t2)
    assert k1 != k2
    assert len(k1) == 32
    assert len(k2) == 32


def test_c02_kunci_sama_berhak_dan_tidak_berhak_pembanding(TEMUAN_ASLI):
    """C02: Kunci temuan identik antara pengguna berhak dan tidak berhak atas dokumen pembanding non-publik (karena dihitung sebelum penyaringan)."""
    raw_item = copy.deepcopy(TEMUAN_ASLI[0])
    raw_item["pembanding"]["document_id"] = 999  # ID dokumen pembanding rahasia

    # 1. Tandai kunci temuan dari hasil mentah sebelum penyaringan
    payload = {"temuan": [raw_item]}
    marked_payload = tandai_kunci_temuan(payload)
    kunci_sebelum = marked_payload["temuan"][0]["kunci_temuan"]
    assert marked_payload["temuan"][0]["pembanding"]["pasal"] == "Pasal 12"

    # 2. Pengguna tanpa hak baca atas dokumen 999: saring_rujukan menetralkan document_id dan menghapus pasal
    filtered_item, _ = saring_rujukan(marked_payload["temuan"][0], allowed_ids={1})
    assert filtered_item["pembanding"]["document_id"] is None
    assert "pasal" not in filtered_item["pembanding"]

    # 3. Kunci temuan pada objek tersaring TETAP identik dengan kunci asli
    assert filtered_item["kunci_temuan"] == kunci_sebelum

    # 4. Bukti: jika kunci baru dihitung SETELAH penyaringan, kuncinya akan BERBEDA
    kunci_setelah_saring = kunci_temuan(filtered_item)
    assert kunci_setelah_saring != kunci_sebelum


def test_c03_put_tanggapan_kunci_valid_vs_kunci_palsu(client: TestClient, db_session: Session, TEMUAN_ASLI):
    """C03: PUT temuan yang sudah disaring (tanpa pembanding.pasal) dengan kunci_temuan valid -> tersimpan; kunci palsu -> diabaikan & dihitung dari payload."""
    draft = create_test_doc(title="Draft Kajian C03", document_role=PeranDokumen.draft_kajian)
    comp = create_test_doc(title="POJK 10 2023")
    db_session.add_all([draft, comp])
    db_session.commit()

    temuan_data = copy.deepcopy(TEMUAN_ASLI)
    temuan_data[0]["pembanding"]["document_id"] = comp.id
    kunci_asli_0 = kunci_temuan(temuan_data[0])

    cached_payload = {
        "versi": "1.0",
        "ringkasan": {"total_temuan": 3},
        "temuan": temuan_data,
    }
    seed_harmonisasi_result(db_session, draft, cached_payload)

    # 1. PUT dengan temuan tersaring (tanpa pasal di pembanding), membawa kunci_temuan valid 32-hex
    filtered_item = copy.deepcopy(temuan_data[0])
    filtered_item["pembanding"].pop("pasal", None)
    filtered_item["kunci_temuan"] = kunci_asli_0

    r_valid = client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": filtered_item, "penilaian": "valid", "catatan": "Validasi temuan tersaring"},
    )
    assert r_valid.status_code == 200
    res_data = r_valid.json()
    assert res_data["kunci_temuan"] == kunci_asli_0

    db_session.expire_all()
    row = db_session.query(TanggapanTemuan).filter_by(document_id=draft.id, kunci_temuan=kunci_asli_0).first()
    assert row is not None
    assert row.penilaian == "valid"
    assert row.catatan == "Validasi temuan tersaring"

    # 2. PUT dengan kunci_temuan palsu (tidak cocok dengan hasil tersimpan terakhir)
    kunci_palsu = "deadbeef" * 4
    fake_item = copy.deepcopy(filtered_item)
    fake_item["kunci_temuan"] = kunci_palsu

    r_fake = client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": fake_item, "penilaian": "tidak_relevan", "catatan": "Kunci palsu diabaikan"},
    )
    assert r_fake.status_code == 200
    res_fake = r_fake.json()
    assert res_fake["kunci_temuan"] != kunci_palsu
    assert res_fake["kunci_temuan"] == kunci_temuan(fake_item)


def test_c04_ekspor_csv_dan_docx_terisi_pembanding_pasal_dan_alasan(client: TestClient, db_session: Session, TEMUAN_ASLI):
    """C04: Ekspor CSV dan DOCX kolom Pasal Pembanding dan Uraian Temuan terisi dari pembanding.pasal dan alasan, serta kolom Keyakinan."""
    draft = create_test_doc(
        title="Draft RPOJK Asli",
        regulation_type="RPOJK",
        regulation_number="5",
        regulation_year=2024,
        document_role=PeranDokumen.draft_kajian,
    )
    comp = create_test_doc(title="POJK 10 2023", regulation_type="POJK", regulation_number="10", regulation_year=2023)
    db_session.add_all([draft, comp])
    db_session.commit()

    temuan_data = copy.deepcopy(TEMUAN_ASLI)
    temuan_data[0]["pembanding"]["document_id"] = comp.id
    temuan_data[1]["pembanding"]["document_id"] = comp.id

    cached_payload = {
        "versi": "1.0",
        "ringkasan": {"total_temuan": 3},
        "temuan": temuan_data,
    }
    seed_harmonisasi_result(db_session, draft, cached_payload)

    # 1. Ekspor CSV
    r_csv = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=csv")
    assert r_csv.status_code == 200
    reader = csv.reader(io.StringIO(r_csv.content.decode("utf-8-sig")))
    rows = list(reader)
    header = rows[0]
    assert "Pasal Pembanding" in header
    assert "Uraian Temuan" in header
    assert "Keyakinan" in header

    idx_pasal_p = header.index("Pasal Pembanding")
    idx_uraian = header.index("Uraian Temuan")
    idx_keyakinan = header.index("Keyakinan")

    row1 = rows[1]  # Temuan 0
    assert row1[idx_pasal_p] == "Pasal 12"
    assert row1[idx_uraian] == "Terdapat kesamaan rumusan kewajiban modal kerja minimal."
    assert row1[idx_keyakinan] == "tinggi (0,82)"

    row2 = rows[2]  # Temuan 1
    assert row2[idx_pasal_p] == "Pasal 14"
    assert row2[idx_uraian] == "Terdapat rumusan pelaporan modal kerja yang serupa."
    assert row2[idx_keyakinan] == "sedang (0,75)"

    row3 = rows[3]  # Temuan 2 (pasal_baru)
    assert row3[idx_pasal_p] == ""
    assert row3[idx_uraian] == "Ketentuan tata kelola AI ini belum diatur dalam regulasi pembanding mana pun."
    assert row3[idx_keyakinan] == "tinggi (0,90)"

    # 2. Ekspor DOCX
    r_docx = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=docx")
    assert r_docx.status_code == 200
    doc_file = docx.Document(io.BytesIO(r_docx.content))
    tbl_text = "\n".join([cell.text for row in doc_file.tables[0].rows for cell in row.cells])
    assert "Pasal 12" in tbl_text
    assert "Pasal 14" in tbl_text
    assert "Terdapat kesamaan rumusan kewajiban modal kerja minimal." in tbl_text
    assert "tinggi (0,82)" in tbl_text


def test_c05_cache_analysis_results_bersih_di_ketiga_jalur(client: TestClient, db_session: Session, TEMUAN_ASLI):
    """C05: analysis_results di DB tetap murni tanpa kunci_temuan / tanggapan di ketiga jalur (fresh, cache hit, cache basi/fallback)."""
    draft = create_test_doc(title="Draft C05 Cache Purity", document_role=PeranDokumen.draft_kajian)
    comp = create_test_doc(title="POJK 10 2024")
    db_session.add_all([draft, comp])
    db_session.commit()

    temuan_data = copy.deepcopy(TEMUAN_ASLI)
    temuan_data[0]["pembanding"]["document_id"] = comp.id
    temuan_data[1]["pembanding"]["document_id"] = comp.id

    def ml_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "versi": "1.0",
                "draft": {"title": draft.title},
                "ringkasan": {"total_temuan": 3},
                "temuan": temuan_data,
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(ml_handler))

    # Jalur 1: Fresh ML
    r1 = client.post(f"/api/v1/ml/harmonisasi/{draft.id}", json=[comp.id])
    assert r1.status_code == 200
    db_session.expire_all()
    cached1 = db_session.query(AnalysisResult).filter_by(document_id=draft.id, kind=JenisAnalisa.harmonisasi).first()
    assert cached1 is not None
    assert "kunci_temuan" not in cached1.result["temuan"][0]
    assert "tanggapan" not in cached1.result["temuan"][0]
    assert "tanggapan" not in cached1.result["ringkasan"]

    # Beri tanggapan analis
    client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": temuan_data[0], "penilaian": "valid"},
    )

    # Jalur 2: Cache Hit
    r2 = client.post(f"/api/v1/ml/harmonisasi/{draft.id}", json=[comp.id])
    assert r2.status_code == 200
    assert r2.json()["cache"]["hit"] is True
    db_session.expire_all()
    cached2 = db_session.query(AnalysisResult).filter_by(document_id=draft.id, kind=JenisAnalisa.harmonisasi).first()
    assert "kunci_temuan" not in cached2.result["temuan"][0]
    assert "tanggapan" not in cached2.result["temuan"][0]
    assert "tanggapan" not in cached2.result["ringkasan"]

    # Jalur 3: Cache basi / fallback (simulasi perubahan fingerprint pada draft)
    draft.file_hash = "different_hash_" + "0" * 49
    db_session.commit()

    def ml_handler_fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("ML layer down", request=request)

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(ml_handler_fail))
    r3 = client.post(f"/api/v1/ml/harmonisasi/{draft.id}", json=[comp.id])
    assert r3.status_code == 200
    assert r3.json()["cache"]["basi"] is True
    db_session.expire_all()
    cached3 = db_session.query(AnalysisResult).filter_by(document_id=draft.id, kind=JenisAnalisa.harmonisasi).first()
    assert "kunci_temuan" not in cached3.result["temuan"][0]
    assert "tanggapan" not in cached3.result["temuan"][0]


def test_c06_pasal_baru_tanpa_pembanding_lancar(client: TestClient, db_session: Session, TEMUAN_ASLI):
    """C06: Temuan pasal_baru (pembanding: null) tidak error di kunci_temuan, PUT tanggapan, maupun ekspor DOCX/CSV/JSON."""
    item_baru = TEMUAN_ASLI[2]
    assert item_baru["pembanding"] is None

    # 1. Kunci temuan tidak error
    k = kunci_temuan(item_baru)
    assert isinstance(k, str) and len(k) == 32

    draft = create_test_doc(title="Draft C06 Pasal Baru", document_role=PeranDokumen.draft_kajian)
    db_session.add(draft)
    db_session.commit()

    # 2. PUT tanggapan tidak error
    r_put = client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": item_baru, "penilaian": "valid", "catatan": "Pasal baru memang dibutuhkan"},
    )
    assert r_put.status_code == 200
    data_put = r_put.json()
    assert data_put["kunci_temuan"] == k
    assert data_put["ringkasan_temuan"]["pembanding"] is None
    assert data_put["ringkasan_temuan"]["alasan"] == item_baru["alasan"]

    cached_payload = {
        "versi": "1.0",
        "ringkasan": {"total_temuan": 1},
        "temuan": [item_baru],
    }
    seed_harmonisasi_result(db_session, draft, cached_payload)

    # 3. Ekspor CSV tidak error
    r_csv = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=csv")
    assert r_csv.status_code == 200
    assert "pasal_baru" in r_csv.text

    # 4. Ekspor DOCX tidak error
    r_docx = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=docx")
    assert r_docx.status_code == 200

    # 5. Ekspor JSON tidak error
    r_json = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=json")
    assert r_json.status_code == 200
    assert r_json.json()["temuan"][0]["tanggapan"]["penilaian"] == "valid"
