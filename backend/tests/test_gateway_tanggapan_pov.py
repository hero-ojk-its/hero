"""
tests/test_gateway_tanggapan_pov.py
Pengujian gerbang draft tanggapan PoV (Fase 4):
- GET  /api/v1/ml/tanggapan/profil
- POST /api/v1/ml/tanggapan/{document_id}

Semua data REKAAN; layanan ML diganti httpx.MockTransport (pola tests/test_step16_ml_gateway.py).
"""
from datetime import date, datetime, timedelta, timezone
import json
import uuid
from typing import Any, Optional

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import PeranPengguna
from app.main import app
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.enums import KlasifikasiAkses, PeranDokumen, StatusKeberlakuan, StatusPemrosesan
from app.models.user import User
from app.routers.auth import ALGORITHM
from app.routers.ml_gateway import CATATAN_AKSES_TANGGAPAN, get_ml_client
from app.services.audit_service import RUN_TANGGAPAN_POV

JUDUL_RAHASIA = "Peraturan Rekaan Zeta Kerahasiaan Sandi Internal"
NOMOR_RAHASIA = "77/SEOJK.99/2026"


@pytest.fixture(autouse=True)
def pengaturan_ml(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ml_service_url", "http://ml-test:8100")
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)
    monkeypatch.setattr(settings, "auth_enabled", False)
    yield
    app.dependency_overrides.pop(get_ml_client, None)


def _dok(
    db: Session,
    judul: str,
    *,
    peran: PeranDokumen = PeranDokumen.corpus_eksisting,
    akses: KlasifikasiAkses = KlasifikasiAkses.publik,
    aktif: bool = True,
    nomor: Optional[str] = None,
) -> Document:
    rnd = uuid.uuid4().hex[:10]
    doc = Document(
        title=judul,
        regulation_number=nomor or f"{rnd}/POJK.01/2026",
        regulation_type="POJK",
        release_date=date(2026, 1, 1),
        regulation_year=2026,
        file_path_pdf=f"kb/POJK/2026/{rnd}.pdf",
        file_hash=f"hash_tanggapan_{rnd}",
        file_size_bytes=100,
        standardized_filename=f"{rnd}.pdf",
        access_classification=akses,
        document_role=peran,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        is_active=aktif,
        full_text=f"Isi teks rekaan {judul}",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _laporan(draft_id: int, pembanding: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Laporan tanggapan rekaan berbentuk keluaran susun_tanggapan (pipeline/hero/tanggapan/pov.py)."""
    harm = None
    narasi = "Pasal 5 mewajibkan penyelenggara menyediakan sistem elektronik yang andal."
    usulan = "Kami mengusulkan batas waktu penyesuaian 12 bulan."
    if pembanding is not None:
        nama_pb = f"Pasal 7 {pembanding.get('nomor', '')} tentang {pembanding.get('judul', '')}"
        harm = {
            "jenis": "konflik",
            "istilah": "Kontradiktif",
            "alasan": f"Rumusan bertentangan dengan {nama_pb}.",
            "perbedaan": [],
            "pembanding": {
                "document_id": pembanding.get("document_id"),
                "judul": pembanding.get("judul"),
                "key": f"SEOJK|{pembanding.get('nomor', '')}|2026",
                "pasal": "7",
                "halaman": 3,
                "pdf": "http://ml-test:8100/pdf/x#page=3",
            },
            "keyakinan": 0.8,
        }
        narasi = f"Pasal 5 bertentangan dengan {nama_pb}."
        usulan = f"Kami mengusulkan Pasal 5 diselaraskan dengan {nama_pb}."
    pasal = {
        "pasal": "Pasal 5", "halaman": 2, "kutipan": "Penyelenggara wajib ...", "skor": 6, "tingkat": "tinggi",
        "topik": [], "alasan": "menyentuh ketahanan sistem informasi", "norma": ["kewajiban"],
        "batas_waktu": [], "peralihan": False, "definisi": False, "harmonisasi": harm, "wajib": True,
        "dasar_wajib": ["tingkat tinggi"], "status": "belum", "narasi": narasi, "usulan": usulan,
        "dasar": [f"harmonisasi: Kontradiktif — {harm['alasan']}"] if harm else [],
    }
    return {
        "versi": "0.1-rekaan",
        "profil": {"id": "it", "nama": "Unit Bisnis IT", "unit": "DPTI", "tugas": "Mengawal TI.", "fungsi": [], "topik": []},
        "draft": {"judul": "Rancangan POJK Rekaan", "perihal": "Rekaan", "pasal": 3, "document_id": draft_id},
        "surat": {
            "kepada": "Kepala Departemen", "dari": "Analis Eksekutif", "hal": "Tanggapan atas Rancangan POJK Rekaan",
            "tanggal": "(diisi manual)", "pembuka": "Sehubungan dengan ...",
            "butir": [
                {"nomor": 1, "judul": "Latar Belakang", "isi": "Draft mengatur rekaan."},
                {"nomor": 2, "judul": "Pokok Tanggapan", "isi": "Terdapat 1 pasal:",
                 "pasal": [{"pasal": "Pasal 5", "halaman": 2, "narasi": narasi, "usulan": usulan,
                            "temuan": harm["istilah"] if harm else None, "dasar": pasal["dasar"]}]},
            ],
            "penutup": "Demikian kami sampaikan.",
        },
        "pasal_berdampak": [pasal],
        "kelengkapan": {"wajib": 1, "sudah": 0, "belum": 1, "keterangan": "1 pasal belum ditanggapi"},
        "ringkasan": {"pasal_draft": 3, "pasal_berdampak": 1, "dengan_temuan_harmonisasi": 1 if harm else 0},
        "catatan": "Draft — wajib ditelaah analis.",
    }


def _pasang_ml(handler) -> None:
    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _ml_tanggapan(draft_id: int, pembanding: Optional[dict[str, Any]], tercatat: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        tercatat.append(request)
        dengan = request.url.params.get("dengan_harmonisasi") == "true"
        return httpx.Response(200, json=_laporan(draft_id, pembanding if dengan else None))
    return handler


def _audit_tanggapan(db: Session, document_id: int) -> list[AuditLog]:
    db.expire_all()
    return (
        db.query(AuditLog)
        .filter(AuditLog.action == RUN_TANGGAPAN_POV, AuditLog.target_resource == f"document:{document_id}")
        .all()
    )


def _token(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": user.username, "exp": now + timedelta(hours=2), "iat": now},
                      settings.secret_key, algorithm=ALGORITHM)


def _pengguna(db: Session, peran: PeranPengguna) -> User:
    u = User(username=f"tpov_{uuid.uuid4().hex[:8]}", hashed_password="$2b$12$dummyhashtanggapanpovtest",
             role=peran, is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ---------------------------------------------------------------------------
# Profil
# ---------------------------------------------------------------------------

def test_t01_profil_diteruskan(client: TestClient):
    tercatat: list[httpx.Request] = []
    isi = {"profil": [{"id": "it", "nama": "Unit Bisnis IT"}, {"id": "hukum", "nama": "Unit Hukum"}]}

    def handler(request: httpx.Request) -> httpx.Response:
        tercatat.append(request)
        return httpx.Response(200, json=isi)

    _pasang_ml(handler)
    resp = client.get("/api/v1/ml/tanggapan/profil")
    assert resp.status_code == 200
    assert resp.json() == isi
    assert len(tercatat) == 1
    assert tercatat[0].method == "GET"
    assert tercatat[0].url.path == "/tanggapan/profil"


def test_t02_profil_dan_tanggapan_tanpa_izin_403(client: TestClient, db_session: Session, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    draft = _dok(db_session, "Draft Rekaan T02", peran=PeranDokumen.draft_kajian)
    pilot = _pengguna(db_session, PeranPengguna.pilot_user)
    tercatat: list[httpx.Request] = []
    _pasang_ml(_ml_tanggapan(draft.id, None, tercatat))
    hdr = {"Authorization": f"Bearer {_token(pilot)}"}

    assert client.get("/api/v1/ml/tanggapan/profil", headers=hdr).status_code == 403
    assert client.post(f"/api/v1/ml/tanggapan/{draft.id}", headers=hdr).status_code == 403
    assert client.get("/api/v1/ml/tanggapan/profil").status_code == 401
    assert tercatat == []


# ---------------------------------------------------------------------------
# Tanggapan: alur sukses & validasi dokumen
# ---------------------------------------------------------------------------

def test_t03_tanggapan_sukses_pembanding_publik(client: TestClient, db_session: Session):
    draft = _dok(db_session, "Draft Rekaan T03", peran=PeranDokumen.draft_kajian)
    pb = _dok(db_session, "POJK Rekaan Pembanding Publik T03")
    tercatat: list[httpx.Request] = []
    _pasang_ml(_ml_tanggapan(draft.id, {"document_id": pb.id, "judul": pb.title, "nomor": pb.regulation_number}, tercatat))

    sudah = {"Pasal 5": "Tanggapan analis rekaan."}
    resp = client.post(f"/api/v1/ml/tanggapan/{draft.id}?profil=it", json=sudah)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["harmonisasi_disaring"] is False
    assert "catatan_akses" not in data
    assert data["disaring_backend"] == 0
    assert data["pasal_berdampak"][0]["harmonisasi"]["pembanding"]["document_id"] == pb.id
    assert data["draft"]["document_id"] == draft.id
    assert pb.title in resp.text

    assert len(tercatat) == 1
    req = tercatat[0]
    assert req.method == "POST"
    assert req.url.path == f"/tanggapan/{draft.id}"
    assert req.url.params.get("profil") == "it"
    assert req.url.params.get("dengan_harmonisasi") == "true"
    assert json.loads(req.content) == sudah


def test_t04_tanpa_harmonisasi_dan_profil_kosong(client: TestClient, db_session: Session):
    draft = _dok(db_session, "Draft Rekaan T04", peran=PeranDokumen.draft_kajian)
    tercatat: list[httpx.Request] = []
    _pasang_ml(_ml_tanggapan(draft.id, None, tercatat))

    resp = client.post(f"/api/v1/ml/tanggapan/{draft.id}?dengan_harmonisasi=false&profil=")
    assert resp.status_code == 200
    assert resp.json()["harmonisasi_disaring"] is False
    assert len(tercatat) == 1
    assert tercatat[0].url.params.get("dengan_harmonisasi") == "false"
    assert "profil" not in tercatat[0].url.params
    assert tercatat[0].content in (b"", b"null")


def test_t05_bukan_draft_422(client: TestClient, db_session: Session):
    korpus = _dok(db_session, "POJK Rekaan Korpus T05")
    tercatat: list[httpx.Request] = []
    _pasang_ml(_ml_tanggapan(korpus.id, None, tercatat))

    resp = client.post(f"/api/v1/ml/tanggapan/{korpus.id}")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "bukan_draft"
    assert "draft kajian" in detail["message"]
    assert tercatat == []


def test_t06_dokumen_tak_ada_nonaktif_atau_tanpa_akses(client: TestClient, db_session: Session):
    tercatat: list[httpx.Request] = []
    _pasang_ml(_ml_tanggapan(0, None, tercatat))

    assert client.post("/api/v1/ml/tanggapan/987654321").status_code == 404

    nonaktif = _dok(db_session, "Draft Rekaan Nonaktif T06", peran=PeranDokumen.draft_kajian, aktif=False)
    resp = client.post(f"/api/v1/ml/tanggapan/{nonaktif.id}")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "dokumen_nonaktif"

    rahasia = _dok(db_session, "POJK Rekaan Non-publik T06", akses=KlasifikasiAkses.non_publik)
    assert client.post(f"/api/v1/ml/tanggapan/{rahasia.id}").status_code == 403
    assert tercatat == []


# ---------------------------------------------------------------------------
# Penyaringan akses pembanding
# ---------------------------------------------------------------------------

def test_t07_pembanding_nonpublik_disaring_untuk_pengguna_tanpa_hak(client: TestClient, db_session: Session):
    draft = _dok(db_session, "Draft Rekaan T07", peran=PeranDokumen.draft_kajian)
    rahasia = _dok(db_session, JUDUL_RAHASIA, akses=KlasifikasiAkses.non_publik, nomor=NOMOR_RAHASIA)
    tercatat: list[httpx.Request] = []
    _pasang_ml(_ml_tanggapan(
        draft.id, {"document_id": rahasia.id, "judul": rahasia.title, "nomor": rahasia.regulation_number}, tercatat
    ))

    sudah = {"Pasal 5": "Sudah ditanggapi."}
    resp = client.post(f"/api/v1/ml/tanggapan/{draft.id}?profil=it", json=sudah)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert len(tercatat) == 2
    assert tercatat[0].url.params.get("dengan_harmonisasi") == "true"
    assert tercatat[1].url.params.get("dengan_harmonisasi") == "false"
    assert tercatat[1].url.params.get("profil") == "it"
    assert json.loads(tercatat[1].content) == sudah

    assert data["harmonisasi_disaring"] is True
    assert data["catatan_akses"] == CATATAN_AKSES_TANGGAPAN
    assert data["pasal_berdampak"][0]["harmonisasi"] is None

    teks = resp.text
    assert JUDUL_RAHASIA not in teks
    assert NOMOR_RAHASIA not in teks
    assert "Zeta" not in teks
    assert f'"document_id": {rahasia.id}' not in teks and f'"document_id":{rahasia.id}' not in teks

    entri = _audit_tanggapan(db_session, draft.id)
    assert len(entri) == 1
    assert entri[0].detail["harmonisasi_disaring"] is True
    assert entri[0].detail["dengan_harmonisasi"] is True


def test_t08_pembanding_tanpa_document_id_fail_closed(client: TestClient, db_session: Session):
    """Pembanding di katalog yang tidak tercermin di backend (document_id null) tidak dapat diperiksa haknya."""
    draft = _dok(db_session, "Draft Rekaan T08", peran=PeranDokumen.draft_kajian)
    tercatat: list[httpx.Request] = []
    _pasang_ml(_ml_tanggapan(draft.id, {"document_id": None, "judul": JUDUL_RAHASIA, "nomor": NOMOR_RAHASIA}, tercatat))

    resp = client.post(f"/api/v1/ml/tanggapan/{draft.id}")
    assert resp.status_code == 200
    assert resp.json()["harmonisasi_disaring"] is True
    assert len(tercatat) == 2
    assert JUDUL_RAHASIA not in resp.text


def test_t09_pengguna_berhak_nonpublik_tidak_disaring(client: TestClient, db_session: Session, monkeypatch):
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", False)
    draft = _dok(db_session, "Draft Rekaan T09", peran=PeranDokumen.draft_kajian)
    rahasia = _dok(db_session, JUDUL_RAHASIA + " T09", akses=KlasifikasiAkses.non_publik)
    tercatat: list[httpx.Request] = []
    _pasang_ml(_ml_tanggapan(
        draft.id, {"document_id": rahasia.id, "judul": rahasia.title, "nomor": rahasia.regulation_number}, tercatat
    ))

    resp = client.post(f"/api/v1/ml/tanggapan/{draft.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(tercatat) == 1
    assert data["harmonisasi_disaring"] is False
    assert "catatan_akses" not in data
    assert data["pasal_berdampak"][0]["harmonisasi"]["pembanding"]["document_id"] == rahasia.id
    assert rahasia.title in resp.text


def test_t10_analis_login_berhak_nonpublik(client: TestClient, db_session: Session, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    draft = _dok(db_session, "Draft Rekaan T10", peran=PeranDokumen.draft_kajian)
    rahasia = _dok(db_session, JUDUL_RAHASIA + " T10", akses=KlasifikasiAkses.non_publik)
    analis = _pengguna(db_session, PeranPengguna.analis)
    tercatat: list[httpx.Request] = []
    _pasang_ml(_ml_tanggapan(
        draft.id, {"document_id": rahasia.id, "judul": rahasia.title, "nomor": rahasia.regulation_number}, tercatat
    ))

    resp = client.post(f"/api/v1/ml/tanggapan/{draft.id}", headers={"Authorization": f"Bearer {_token(analis)}"})
    assert resp.status_code == 200
    assert resp.json()["harmonisasi_disaring"] is False
    assert len(tercatat) == 1
    entri = _audit_tanggapan(db_session, draft.id)
    assert len(entri) == 1
    assert entri[0].user_id == analis.id


# ---------------------------------------------------------------------------
# Validasi masukan & galat ML
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sudah",
    [
        {f"Pasal {i}": "x" for i in range(301)},
        {"P" * 41: "x"},
        {"Pasal 5": "x" * 4001},
    ],
    ids=["kunci_lebih_300", "kunci_lebih_40_karakter", "nilai_lebih_4000_karakter"],
)
def test_t11_sudah_melebihi_batas_422(client: TestClient, db_session: Session, sudah):
    draft = _dok(db_session, "Draft Rekaan T11", peran=PeranDokumen.draft_kajian)
    tercatat: list[httpx.Request] = []
    _pasang_ml(_ml_tanggapan(draft.id, None, tercatat))

    resp = client.post(f"/api/v1/ml/tanggapan/{draft.id}", json=sudah)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "sudah_tidak_valid"
    assert "melebihi" in detail["message"]
    assert tercatat == []


def test_t12_sudah_tepat_batas_diterima_dan_profil_terlalu_panjang(client: TestClient, db_session: Session):
    draft = _dok(db_session, "Draft Rekaan T12", peran=PeranDokumen.draft_kajian)
    tercatat: list[httpx.Request] = []
    _pasang_ml(_ml_tanggapan(draft.id, None, tercatat))

    batas = {f"P{i:03d}".ljust(40, "x"): "y" * 4000 for i in range(300)}
    assert client.post(f"/api/v1/ml/tanggapan/{draft.id}", json=batas).status_code == 200

    resp = client.post(f"/api/v1/ml/tanggapan/{draft.id}?profil={'a' * 65}")
    assert resp.status_code == 422
    assert len(tercatat) == 1


def test_t13_profil_tak_dikenal_404_aman(client: TestClient, db_session: Session):
    draft = _dok(db_session, "Draft Rekaan T13", peran=PeranDokumen.draft_kajian)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "profil PoV 'xyz' tidak dikenal (tersedia: it, hukum_internal)"})

    _pasang_ml(handler)
    resp = client.post(f"/api/v1/ml/tanggapan/{draft.id}?profil=xyz")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["code"] == "profil_tidak_dikenal"
    assert detail["message"] == "Profil PoV tidak dikenal."
    assert "tersedia" not in resp.text
    assert "hukum_internal" not in resp.text

    entri = _audit_tanggapan(db_session, draft.id)
    assert len(entri) == 1
    assert entri[0].detail["http_status"] == 404


def test_t14_dokumen_belum_tercermin_di_ml_404_aman(client: TestClient, db_session: Session):
    draft = _dok(db_session, "Draft Rekaan T14", peran=PeranDokumen.draft_kajian)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": f"dokumen {draft.id} belum tercermin di lapisan data. "
                                                   "Penyebab: rahasia. Jalankan: hero bridge sinkron"})

    _pasang_ml(handler)
    resp = client.post(f"/api/v1/ml/tanggapan/{draft.id}")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "dokumen_belum_siap_analisa"
    assert "hero bridge" not in resp.text


@pytest.mark.parametrize(
    "galat, status_harap, kode",
    [
        (httpx.ReadTimeout("habis"), 504, "layanan_analisa_timeout"),
        (httpx.ConnectError("ditolak"), 503, "layanan_analisa_tidak_tersedia"),
    ],
    ids=["timeout", "tidak_terjangkau"],
)
def test_t15_galat_jaringan_ml(client: TestClient, db_session: Session, galat, status_harap, kode):
    draft = _dok(db_session, "Draft Rekaan T15", peran=PeranDokumen.draft_kajian)

    def handler(request: httpx.Request) -> httpx.Response:
        raise galat

    _pasang_ml(handler)
    resp = client.post(f"/api/v1/ml/tanggapan/{draft.id}")
    assert resp.status_code == status_harap
    assert resp.json()["detail"]["code"] == kode

    entri = _audit_tanggapan(db_session, draft.id)
    assert len(entri) == 1
    assert entri[0].detail["sumber"] == "gagal"
    assert entri[0].detail["http_status"] == status_harap


def test_t16_ml_5xx_diteruskan_seperti_harmonisasi(client: TestClient, db_session: Session):
    draft = _dok(db_session, "Draft Rekaan T16", peran=PeranDokumen.draft_kajian)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "galat internal ML"})

    _pasang_ml(handler)
    resp = client.post(f"/api/v1/ml/tanggapan/{draft.id}")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "galat internal ML"}


def test_t17_ml_bukan_json_502(client: TestClient, db_session: Session):
    draft = _dok(db_session, "Draft Rekaan T17", peran=PeranDokumen.draft_kajian)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>Bad Gateway</html>")

    _pasang_ml(handler)
    resp = client.post(f"/api/v1/ml/tanggapan/{draft.id}")
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "layanan_analisa_jawaban_tidak_valid"


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def test_t18_audit_tercatat_satu_entri(client: TestClient, db_session: Session):
    draft = _dok(db_session, "Draft Rekaan T18", peran=PeranDokumen.draft_kajian)
    pb = _dok(db_session, "POJK Rekaan Pembanding T18")
    tercatat: list[httpx.Request] = []
    _pasang_ml(_ml_tanggapan(draft.id, {"document_id": pb.id, "judul": pb.title, "nomor": pb.regulation_number}, tercatat))

    resp = client.post(f"/api/v1/ml/tanggapan/{draft.id}?profil=it")
    assert resp.status_code == 200

    entri = _audit_tanggapan(db_session, draft.id)
    assert len(entri) == 1
    detail = entri[0].detail
    assert detail["document_id"] == draft.id
    assert detail["profil"] == "it"
    assert detail["dengan_harmonisasi"] is True
    assert detail["harmonisasi_disaring"] is False
    assert detail["jumlah_pasal_berdampak"] == 1
    assert detail["sumber"] == "ml"
    assert detail["http_status"] == 200
