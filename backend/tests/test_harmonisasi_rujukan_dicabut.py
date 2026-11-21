"""
backend/tests/test_harmonisasi_rujukan_dicabut.py
Pengujian pass-through rujukan_dicabut dari respons ML ke klien dan ekspor (TC-33):
1. Pengguna berhak non-publik: ringkasan.rujukan_dicabut sampai apa adanya dan kedua rujukan utuh.
2. Pengguna tidak berhak non-publik: ringkasan.rujukan_dicabut tetap sampai; rujukan non-publik disensor oleh saring_rujukan_lengkap.
3. Ekspor (xlsx dan Word) dari hasil tersimpan yang memuat ringkasan.rujukan_dicabut tidak error.
"""
from datetime import datetime, timezone
import io
import uuid
import docx
import httpx
import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import PeranPengguna
from app.main import app
from app.models.analysis_result import AnalysisResult
from app.models.document import Document
from app.models.enums import (
    JenisAnalisa,
    KlasifikasiAkses,
    ModeAnalisa,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
)
from app.routers.ml_gateway import get_ml_client


@pytest.fixture(autouse=True)
def setup_ml_env(monkeypatch: pytest.MonkeyPatch):
    """Pastikan konfigurasi ML aktif dan terisolasi."""
    monkeypatch.setattr(settings, "ml_service_url", "http://ml-test:8100")
    monkeypatch.setattr(settings, "ml_cache_enabled", False)
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)
    yield
    app.dependency_overrides.pop(get_ml_client, None)


def _create_doc(db: Session, title: str, access: KlasifikasiAkses, role: PeranDokumen = PeranDokumen.corpus_eksisting) -> Document:
    rnd = uuid.uuid4().hex[:8]
    doc = Document(
        title=title,
        regulation_type="POJK",
        regulation_number=f"POJK-{rnd}",
        regulation_year=2026,
        document_role=role,
        access_classification=access,
        file_path_pdf=f"pdf/{rnd}.pdf",
        file_hash=f"hash_{rnd}" * 4,
        file_size_bytes=1024,
        processing_status=StatusPemrosesan.terindeks,
        status_keberlakuan=StatusKeberlakuan.dicabut,
        is_active=True,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_b01_rujukan_dicabut_pengguna_berhak_nonpublik(client: TestClient, db_session: Session, monkeypatch):
    """1. Pengguna berhak non-publik: ringkasan.rujukan_dicabut utuh dan kedua rujukan lengkap."""
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", False)

    draft = _create_doc(db_session, "Draft Uji Dicabut B01", KlasifikasiAkses.publik, PeranDokumen.draft_kajian)
    comp_pub = _create_doc(db_session, "POJK Publik Dicabut", KlasifikasiAkses.publik)
    comp_nonpub = _create_doc(db_session, "POJK Non-Publik Dicabut", KlasifikasiAkses.non_publik)

    def ml_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "versi": "1.0",
                "ringkasan": {
                    "total_temuan": 1,
                    "per_jenis": {"konflik": 1},
                    "rujukan_dicabut": 2,
                },
                "kandidat": [
                    {"document_id": comp_pub.id, "judul": comp_pub.title},
                    {"document_id": comp_nonpub.id, "judul": comp_nonpub.title},
                ],
                "temuan": [
                    {
                        "id": "t-1",
                        "pasal_draft": "Pasal 10",
                        "jenis": "konflik",
                        "pembanding": {"document_id": comp_pub.id, "judul": comp_pub.title},
                        "alasan": "Konflik ketentuan",
                    }
                ],
                "rujukan": [
                    {
                        "document_id": comp_pub.id,
                        "nomor": comp_pub.regulation_number,
                        "judul": comp_pub.title,
                        "status": "dicabut",
                        "pasal": "Pasal 5",
                        "kutipan": "Kutipan regulasi publik yang dicabut",
                        "pdf": "storage/pub.pdf",
                        "halaman": 2,
                    },
                    {
                        "document_id": comp_nonpub.id,
                        "nomor": comp_nonpub.regulation_number,
                        "judul": comp_nonpub.title,
                        "status": "dicabut",
                        "pasal": "Pasal 7",
                        "kutipan": "Kutipan rahasia internal non-publik",
                        "pdf": "storage/nonpub.pdf",
                        "halaman": 5,
                    },
                ],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(ml_handler))

    resp = client.post(f"/api/v1/ml/harmonisasi/{draft.id}", json=None)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data.get("ringkasan", {}).get("rujukan_dicabut") == 2
    rujukan_list = data.get("rujukan", [])
    assert len(rujukan_list) == 2

    r_pub = next((r for r in rujukan_list if r.get("document_id") == comp_pub.id), None)
    assert r_pub is not None
    assert r_pub["status"] == "dicabut"
    assert r_pub["kutipan"] == "Kutipan regulasi publik yang dicabut"

    r_nonpub = next((r for r in rujukan_list if r.get("document_id") == comp_nonpub.id), None)
    assert r_nonpub is not None
    assert r_nonpub["status"] == "dicabut"
    assert r_nonpub["kutipan"] == "Kutipan rahasia internal non-publik"


def test_b02_rujukan_dicabut_pengguna_tanpa_hak_nonpublik(client: TestClient, db_session: Session, monkeypatch):
    """2. Pengguna tanpa hak non-publik: angka rujukan_dicabut tetap sampai, rujukan non-publik disensor."""
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)

    draft = _create_doc(db_session, "Draft Uji Dicabut B02", KlasifikasiAkses.publik, PeranDokumen.draft_kajian)
    comp_pub = _create_doc(db_session, "POJK Publik Dicabut B02", KlasifikasiAkses.publik)
    comp_nonpub = _create_doc(db_session, "POJK Non-Publik Dicabut B02", KlasifikasiAkses.non_publik)

    secret_kutipan = "KUTIPAN-RAHASIA-NONPUBLIK-DICABUT-XYZ"

    def ml_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "versi": "1.0",
                "ringkasan": {
                    "total_temuan": 1,
                    "per_jenis": {"konflik": 1},
                    "rujukan_dicabut": 2,
                },
                "kandidat": [
                    {"document_id": comp_pub.id, "judul": comp_pub.title},
                    {"document_id": comp_nonpub.id, "judul": comp_nonpub.title},
                ],
                "temuan": [
                    {
                        "id": "t-1",
                        "pasal_draft": "Pasal 10",
                        "jenis": "konflik",
                        "pembanding": {"document_id": comp_pub.id, "judul": comp_pub.title},
                        "alasan": "Konflik ketentuan",
                    }
                ],
                "rujukan": [
                    {
                        "document_id": comp_pub.id,
                        "nomor": comp_pub.regulation_number,
                        "judul": comp_pub.title,
                        "status": "dicabut",
                        "pasal": "Pasal 5",
                        "kutipan": "Kutipan regulasi publik yang dicabut",
                        "pdf": "storage/pub.pdf",
                        "halaman": 2,
                    },
                    {
                        "document_id": comp_nonpub.id,
                        "nomor": comp_nonpub.regulation_number,
                        "judul": comp_nonpub.title,
                        "status": "dicabut",
                        "pasal": "Pasal 7",
                        "kutipan": secret_kutipan,
                        "pdf": "storage/nonpub.pdf",
                        "halaman": 5,
                    },
                ],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(ml_handler))

    resp = client.post(f"/api/v1/ml/harmonisasi/{draft.id}", json=None)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Angka ringkasan tetap sampai
    assert data.get("ringkasan", {}).get("rujukan_dicabut") == 2
    # Kutipan sensitif non-publik tidak boleh bocor
    assert secret_kutipan not in resp.text

    rujukan_list = data.get("rujukan", [])
    assert len(rujukan_list) == 2

    # Rujukan publik utuh
    r_pub = next((r for r in rujukan_list if r.get("document_id") == comp_pub.id), None)
    assert r_pub is not None
    assert r_pub["status"] == "dicabut"
    assert r_pub["kutipan"] == "Kutipan regulasi publik yang dicabut"

    # Rujukan non-publik disensor: document_id null, kutipan/pdf/halaman/pasal dihapus, nomor/status tetap
    r_nonpub = next((r for r in rujukan_list if r.get("nomor") == comp_nonpub.regulation_number), None)
    assert r_nonpub is not None
    assert r_nonpub.get("document_id") is None
    assert r_nonpub.get("status") == "dicabut"
    assert "kutipan" not in r_nonpub
    assert "pdf" not in r_nonpub
    assert "halaman" not in r_nonpub
    assert "pasal" not in r_nonpub


def test_b03_ekspor_xlsx_dan_docx_dengan_rujukan_dicabut_tidak_error(client: TestClient, db_session: Session):
    """3. Ekspor xlsx dan Word dari hasil tersimpan yang memuat rujukan_dicabut tidak galat."""
    draft = _create_doc(db_session, "Draft Ekspor Dicabut B03", KlasifikasiAkses.publik, PeranDokumen.draft_kajian)
    comp = _create_doc(db_session, "POJK Pembanding B03", KlasifikasiAkses.publik)

    payload = {
        "versi": "1.0",
        "ringkasan": {
            "total_temuan": 1,
            "per_jenis": {"konflik": 1},
            "rujukan_dicabut": 2,
        },
        "temuan": [
            {
                "id": "t-1",
                "pasal_draft": "Pasal 1",
                "jenis": "konflik",
                "pembanding": {"document_id": comp.id, "nomor": comp.regulation_number, "judul": comp.title},
                "pasal_pembanding": "Pasal 2",
                "alasan": "Uraian konflik",
            }
        ],
        "rujukan": [
            {
                "document_id": comp.id,
                "nomor": comp.regulation_number,
                "judul": comp.title,
                "status": "dicabut",
            }
        ],
    }

    res_row = AnalysisResult(
        document_id=draft.id,
        kind=JenisAnalisa.harmonisasi,
        mode=ModeAnalisa.deterministik,
        params_hash="params-" + uuid.uuid4().hex[:16],
        source_fingerprint=f"hash:{draft.file_hash}",
        result=payload,
        ml_version="1.0",
        duration_ms=100,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(res_row)
    db_session.commit()

    # Ekspor XLSX
    r_xlsx = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=xlsx")
    assert r_xlsx.status_code == 200
    assert "spreadsheetml.sheet" in r_xlsx.headers["content-type"]
    wb = openpyxl.load_workbook(io.BytesIO(r_xlsx.content))
    assert "Ringkasan" in wb.sheetnames
    assert "Temuan" in wb.sheetnames

    # Ekspor Word (DOCX)
    r_docx = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=docx")
    assert r_docx.status_code == 200
    assert "wordprocessingml.document" in r_docx.headers["content-type"]
    doc_f = docx.Document(io.BytesIO(r_docx.content))
    assert len(doc_f.tables) >= 1
