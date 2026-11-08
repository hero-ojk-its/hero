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
from app.routers.ml_gateway import get_ml_client
from app.services.audit_service import (
    EXPORT_HARMONIZATION,
    TANGGAPAN_TEMUAN,
)
from app.services.tanggapan_service import kunci_temuan


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
    """H07: Draft non-publik saat login mati -> 403."""
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
    assert res.status_code == 403


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

    row_data = rows[1]
    assert row_data[1] == "baru"
    assert row_data[2] == "Pasal 25"
    assert row_data[6] == "tidak_relevan"
    assert row_data[7] == "Klausul dikecualikan"
    assert row_data[8] == "Analis Budi"


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
