"""
tests/test_step16_ml_gateway.py
Pengujian Gerbang ML /api/v1/ml/* (Langkah 16, issue #116).
Kasus Uji: M01 - M12.
Semua pengujian menggunakan mock transport tanpa memanggil layanan ML sungguhan.
"""
from datetime import date
from typing import Any
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app
from app.models.document import Document
from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.enums import KlasifikasiAkses, PeranDokumen, StatusKeberlakuan, StatusPemrosesan
from app.routers.ml_gateway import get_ml_client
from app.services.audit_service import RUN_HARMONIZATION
from app.services.storage_service import StorageService
from tests.conftest import make_pdf


@pytest.fixture(autouse=True)
def cleanup_ml_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ml_service_url", "http://ml-test:8100")
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)
    monkeypatch.setattr(settings, "auth_enabled", False)
    yield
    app.dependency_overrides.pop(get_ml_client, None)


def _seed_test_doc(
    db: Session,
    storage: StorageService,
    title: str = "Dokumen Uji ML",
    reg_num: str = "01/POJK.03/2026",
    is_active: bool = True,
    access_classification: KlasifikasiAkses = KlasifikasiAkses.publik,
    processing_status: StatusPemrosesan = StatusPemrosesan.terindeks,
) -> Document:
    cat = db.query(Category).filter(Category.name == "POJK").first()
    pdf_bytes = make_pdf(f"Konten {title}")
    rel_path = storage.save_pdf(pdf_bytes, filename_hint=f"{title.replace(' ', '_').lower()}.pdf", subdir="kb/POJK/2026")

    doc = Document(
        title=title,
        regulation_number=reg_num,
        regulation_type="POJK",
        release_date=date(2026, 1, 1),
        regulation_year=2026,
        file_path_pdf=rel_path,
        file_hash=f"hash_{title.replace(' ', '_').lower()}_{reg_num.replace('/', '_')}",
        file_size_bytes=len(pdf_bytes),
        standardized_filename=f"{title}.pdf",
        access_classification=access_classification,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=processing_status,
        is_active=is_active,
        category_id=cat.id if cat else None,
        full_text=f"Isi teks lengkap dari {title}",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_m01_ml_service_url_empty_returns_503(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """M01: ml_service_url kosong, GET /api/v1/ml/health -> 503 layanan_analisa_belum_dikonfigurasi."""
    monkeypatch.setattr(settings, "ml_service_url", "")
    resp = client.get("/api/v1/ml/health")
    assert resp.status_code == 503
    data = resp.json()["detail"]
    assert data["code"] == "layanan_analisa_belum_dikonfigurasi"


def test_m02_connect_error_returns_503(client: TestClient):
    """M02: transport melempar httpx.ConnectError -> 503 layanan_analisa_tidak_tersedia."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Sambungan ke layanan analisa ditolak")

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.get("/api/v1/ml/health")
    assert resp.status_code == 503
    data = resp.json()["detail"]
    assert data["code"] == "layanan_analisa_tidak_tersedia"


def test_m03_timeout_returns_504(client: TestClient):
    """M03: transport melempar httpx.ReadTimeout -> 504 layanan_analisa_timeout."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Batas waktu pembacaan habis")

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.get("/api/v1/ml/health")
    assert resp.status_code == 504
    data = resp.json()["detail"]
    assert data["code"] == "layanan_analisa_timeout"


def test_m04_analisa_active_public_doc_returns_200(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """M04: GET /analisa/{id} dokumen publik aktif -> 200, body layanan diteruskan, path ke layanan benar."""
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen M04", reg_num="04/POJK/2026")
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"document_id": doc.id, "identitas": {"judul": doc.title}})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp.status_code == 200
    assert len(captured_requests) == 1
    assert captured_requests[0].url.path == f"/analisa/{doc.id}"
    assert resp.json()["document_id"] == doc.id
    assert resp.json()["identitas"]["judul"] == "Dokumen M04"


def test_m05_analisa_inactive_doc_returns_404_handler_not_called(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """M05: GET /analisa/{id} dokumen nonaktif -> 404 dokumen_nonaktif, handler tidak dipanggil."""
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen M05 Nonaktif", is_active=False)
    handler_called = []

    def handler(request: httpx.Request) -> httpx.Response:
        handler_called.append(request)
        return httpx.Response(200, json={})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp.status_code == 404
    assert len(handler_called) == 0
    assert "dokumen_nonaktif" in resp.text


def test_m06_analisa_non_public_doc_protected_mode_returns_403(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """M06: GET /analisa/{id} dokumen non-publik, mode lindung -> 403, handler tidak dipanggil."""
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen M06 Rahasia",
        access_classification=KlasifikasiAkses.non_publik,
    )
    handler_called = []

    def handler(request: httpx.Request) -> httpx.Response:
        handler_called.append(request)
        return httpx.Response(200, json={})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp.status_code == 403
    assert len(handler_called) == 0
    assert "Dokumen non-publik hanya dapat dibuka setelah login diaktifkan." in resp.text


def test_m07_harmonisasi_body_null_filters_inactive_and_non_public(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """M07: POST /harmonisasi/{id} body null; ada 1 dokumen nonaktif + 1 non-publik -> body layanan = daftar eksplisit."""
    draft_doc = _seed_test_doc(db_session, test_storage, title="Draft M07", reg_num="07/DRAFT/2026")
    allowed_doc = _seed_test_doc(db_session, test_storage, title="Allowed M07", reg_num="07/ALLOWED/2026")
    inactive_doc = _seed_test_doc(db_session, test_storage, title="Inactive M07", reg_num="07/INACTIVE/2026", is_active=False)
    secret_doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Secret M07",
        reg_num="07/SECRET/2026",
        access_classification=KlasifikasiAkses.non_publik,
    )

    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"kandidat": [], "temuan": [], "rujukan": []})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.post(f"/api/v1/ml/harmonisasi/{draft_doc.id}", json=None)
    assert resp.status_code == 200
    assert len(captured_requests) == 1

    received_body = json.loads(captured_requests[0].content.decode("utf-8"))
    assert isinstance(received_body, list)
    assert allowed_doc.id in received_body
    assert inactive_doc.id not in received_body
    assert secret_doc.id not in received_body
    assert draft_doc.id not in received_body


def test_m08_harmonisasi_response_filtering_and_audit(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """M08: jawaban harmonisasi memuat kandidat/temuan dari dokumen nonaktif -> dibuang; disaring_backend > 0; rujukan doc_id = null; audit RUN_HARMONIZATION."""
    draft_doc = _seed_test_doc(db_session, test_storage, title="Draft M08", reg_num="08/DRAFT/2026")
    allowed_doc = _seed_test_doc(db_session, test_storage, title="Allowed M08", reg_num="08/ALLOWED/2026")
    inactive_doc = _seed_test_doc(db_session, test_storage, title="Inactive M08", reg_num="08/INACTIVE/2026", is_active=False)

    def handler(request: httpx.Request) -> httpx.Response:
        mock_response = {
            "versi": "1.0",
            "kandidat": [
                {"document_id": allowed_doc.id, "judul": allowed_doc.title},
                {"document_id": inactive_doc.id, "judul": inactive_doc.title},
            ],
            "temuan": [
                {"pasal_draft": "Pasal 1", "jenis": "menggantikan", "pembanding": {"document_id": allowed_doc.id}},
                {"pasal_draft": "Pasal 2", "jenis": "konflik", "pembanding": {"document_id": inactive_doc.id}},
            ],
            "rujukan": [
                {"key": "POJK|ALLOWED", "document_id": allowed_doc.id, "teks": "Rujukan Allowed"},
                {"key": "POJK|INACTIVE", "document_id": inactive_doc.id, "teks": "Rujukan Inactive"},
            ],
        }
        return httpx.Response(200, json=mock_response)

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.post(f"/api/v1/ml/harmonisasi/{draft_doc.id}", json=None)
    assert resp.status_code == 200
    data = resp.json()

    # Kandidat inactive dibuang
    assert len(data["kandidat"]) == 1
    assert data["kandidat"][0]["document_id"] == allowed_doc.id

    # Temuan inactive dibuang
    assert len(data["temuan"]) == 1
    assert data["temuan"][0]["pembanding"]["document_id"] == allowed_doc.id

    # Rujukan inactive tetap ada dengan document_id = null
    assert len(data["rujukan"]) == 2
    rujukan_inactive = [r for r in data["rujukan"] if r["key"] == "POJK|INACTIVE"][0]
    assert rujukan_inactive["document_id"] is None
    assert rujukan_inactive["teks"] == "Rujukan Inactive"

    # disaring_backend > 0 (3: 1 kandidat + 1 temuan + 1 rujukan dinetralkan)
    assert data["disaring_backend"] > 0
    assert data["disaring_backend"] == 3  # 1 kandidat + 1 temuan + 1 rujukan dinetralkan

    # Audit RUN_HARMONIZATION tercatat
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.target_resource == f"document:{draft_doc.id}", AuditLog.action == RUN_HARMONIZATION)
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.detail["document_id"] == draft_doc.id
    assert audit.detail["jumlah_temuan"] == 1
    assert audit.detail["jumlah_korpus"] == 1
    assert audit.detail["korpus_dibatasi_pengguna"] is False
    assert "korpus_dokumen" not in audit.detail


def test_m09_cari_default_method_and_filtering(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """M09: GET /cari?q=modal tanpa metode -> metode=lsa; item nonaktif dibuang, total disesuaikan."""
    allowed_doc = _seed_test_doc(db_session, test_storage, title="Allowed M09", reg_num="09/ALLOWED/2026")
    inactive_doc = _seed_test_doc(db_session, test_storage, title="Inactive M09", reg_num="09/INACTIVE/2026", is_active=False)
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "kueri": "modal",
                "metode": request.url.params.get("metode"),
                "total": 2,
                "items": [
                    {"document_id": allowed_doc.id, "pasal": "1", "skor": 0.8},
                    {"document_id": inactive_doc.id, "pasal": "2", "skor": 0.7},
                ],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.get("/api/v1/ml/cari?q=modal")
    assert resp.status_code == 200
    assert len(captured_requests) == 1
    assert captured_requests[0].url.params.get("metode") == "lsa"

    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["document_id"] == allowed_doc.id
    assert data["disaring_backend"] == 1


def test_m10_pasal_mirip_protected_mode_forces_hanya_publik(client: TestClient):
    """M10: GET /pasal-mirip?teks=<20+ karakter>&hanya_publik=false, mode lindung -> layanan menerima hanya_publik=true."""
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"total": 0, "items": []})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sample_teks = "Peraturan Otoritas Jasa Keuangan Nomor 10 Tahun 2026 tentang Perbankan"
    resp = client.get(f"/api/v1/ml/pasal-mirip?teks={sample_teks}&hanya_publik=false")
    assert resp.status_code == 200
    assert len(captured_requests) == 1
    assert captured_requests[0].url.params.get("hanya_publik") == "true"


def test_m11_ml_service_returns_404_gateway_forwards(client: TestClient):
    """M11: layanan menjawab 404 {"detail":"belum siap"} -> gerbang menjawab 404 dengan body yang sama."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "belum siap"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.get("/api/v1/ml/health")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "belum siap"}


def test_m12_cari_query_too_short_returns_422_backend(client: TestClient):
    """M12: GET /cari?q=a (1 karakter) -> 422 dari backend, handler tidak dipanggil."""
    handler_called = []

    def handler(request: httpx.Request) -> httpx.Response:
        handler_called.append(request)
        return httpx.Response(200, json={})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.get("/api/v1/ml/cari?q=a")
    assert resp.status_code == 422
    assert len(handler_called) == 0


def test_m13_harmonisasi_alternatif_with_inactive_doc_discarded(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    M13: Harmonisasi: temuan yang pembandingnya diizinkan memuat alternatif: [{document_id: <nonaktif>, kutipan: "KUTIPAN-RAHASIA-XYZ"}]
    -> temuan tetap ada, alternatif itu dibuang, penanda tidak ada di resp.text, disaring_backend >= 1.
    """
    draft_doc = _seed_test_doc(db_session, test_storage, title="Draft M13", reg_num="13/DRAFT/2026")
    allowed_doc = _seed_test_doc(db_session, test_storage, title="Allowed M13", reg_num="13/ALLOWED/2026")
    inactive_doc = _seed_test_doc(db_session, test_storage, title="Inactive M13", reg_num="13/INACTIVE/2026", is_active=False)

    secret_marker = "KUTIPAN-RAHASIA-XYZ"

    def handler(request: httpx.Request) -> httpx.Response:
        mock_response = {
            "versi": "1.0",
            "kandidat": [{"document_id": allowed_doc.id, "judul": allowed_doc.title}],
            "temuan": [
                {
                    "pasal_draft": "Pasal 1",
                    "jenis": "menggantikan",
                    "pembanding": {"document_id": allowed_doc.id},
                    "alternatif": [
                        {"document_id": inactive_doc.id, "kutipan": secret_marker},
                    ],
                }
            ],
            "rujukan": [],
        }
        return httpx.Response(200, json=mock_response)

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.post(f"/api/v1/ml/harmonisasi/{draft_doc.id}", json=None)
    assert resp.status_code == 200
    assert secret_marker not in resp.text
    data = resp.json()
    assert len(data["temuan"]) == 1
    assert data["temuan"][0]["alternatif"] == []
    assert data["disaring_backend"] >= 1


def test_m14_analisa_recursive_filtering_dasar_hukum_and_terdekat(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    M14: /analisa/{id} (dokumen diizinkan) memuat dasar_hukum: [{document_id: <non-publik>, kutipan: "KUTIPAN-RAHASIA-XYZ"}]
         dan terdekat: {document_id: <nonaktif>, kutipan: "KUTIPAN-RAHASIA-XYZ", teks: "POJK 1/2020"}
    -> elemen list dibuang; terdekat.document_id = null, kutipan hilang, teks tetap ada; penanda tidak ada di resp.text.
    """
    doc = _seed_test_doc(db_session, test_storage, title="Doc M14", reg_num="14/DOC/2026")
    secret_doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Secret M14",
        reg_num="14/SECRET/2026",
        access_classification=KlasifikasiAkses.non_publik,
    )
    inactive_doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Inactive M14",
        reg_num="14/INACTIVE/2026",
        is_active=False,
    )

    secret_marker = "KUTIPAN-RAHASIA-XYZ"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "document_id": doc.id,
                "dasar_hukum": [
                    {"document_id": secret_doc.id, "kutipan": secret_marker},
                ],
                "terdekat": {
                    "document_id": inactive_doc.id,
                    "kutipan": secret_marker,
                    "teks": "POJK 1/2020",
                },
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp.status_code == 200
    assert secret_marker not in resp.text
    data = resp.json()
    assert data["dasar_hukum"] == []
    assert data["terdekat"]["document_id"] is None
    assert data["terdekat"]["teks"] == "POJK 1/2020"
    assert "kutipan" not in data["terdekat"]


def test_m15_harmonisasi_body_all_unauthorized_returns_422_pembanding_kosong(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    M15: Harmonisasi dengan body [<id non-publik>] -> 422 pembanding_kosong, handler tidak dipanggil.
    """
    draft_doc = _seed_test_doc(db_session, test_storage, title="Draft M15", reg_num="15/DRAFT/2026")
    secret_doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Secret M15",
        reg_num="15/SECRET/2026",
        access_classification=KlasifikasiAkses.non_publik,
    )
    handler_called = []

    def handler(request: httpx.Request) -> httpx.Response:
        handler_called.append(request)
        return httpx.Response(200, json={})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.post(f"/api/v1/ml/harmonisasi/{draft_doc.id}", json=[secret_doc.id])
    assert resp.status_code == 422
    assert len(handler_called) == 0
    data = resp.json()["detail"]
    assert data["code"] == "pembanding_kosong"
    assert "Tidak ada dokumen pembanding yang dapat diakses" in data["message"]


def test_m16_harmonisasi_success_audit_format(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    M16: Harmonisasi sukses -> audit jumlah_korpus berupa int, korpus_dibatasi_pengguna berupa bool, tidak ada list id.
    """
    draft_doc = _seed_test_doc(db_session, test_storage, title="Draft M16", reg_num="16/DRAFT/2026")
    allowed_doc1 = _seed_test_doc(db_session, test_storage, title="Allowed 1 M16", reg_num="16/ALLOWED1/2026")
    _seed_test_doc(db_session, test_storage, title="Allowed 2 M16", reg_num="16/ALLOWED2/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"kandidat": [], "temuan": [], "rujukan": []})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.post(f"/api/v1/ml/harmonisasi/{draft_doc.id}", json=[allowed_doc1.id])
    assert resp.status_code == 200

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.target_resource == f"document:{draft_doc.id}", AuditLog.action == RUN_HARMONIZATION)
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.detail["document_id"] == draft_doc.id
    assert isinstance(audit.detail["jumlah_temuan"], int)
    assert isinstance(audit.detail["jumlah_korpus"], int)
    assert audit.detail["jumlah_korpus"] == 1
    assert isinstance(audit.detail["korpus_dibatasi_pengguna"], bool)
    assert audit.detail["korpus_dibatasi_pengguna"] is True
    assert "korpus_dokumen" not in audit.detail


def test_m17_analisa_klausul_hasil_inactive_doc_discarded(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    M17: /analisa/{id}/klausul memuat hasil: [{document_id: <nonaktif>, kutipan: "KUTIPAN-RAHASIA-XYZ"}]
    -> dibuang, penanda tidak ada di resp.text.
    """
    doc = _seed_test_doc(db_session, test_storage, title="Doc M17", reg_num="17/DOC/2026")
    inactive_doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Inactive M17",
        reg_num="17/INACTIVE/2026",
        is_active=False,
    )
    secret_marker = "KUTIPAN-RAHASIA-XYZ"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "document_id": doc.id,
                "hasil": [
                    {"document_id": inactive_doc.id, "kutipan": secret_marker},
                ],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resp = client.get(f"/api/v1/ml/analisa/{doc.id}/klausul?kebutuhan=modal+inti")
    assert resp.status_code == 200
    assert secret_marker not in resp.text
    data = resp.json()
    assert data["hasil"] == []
    assert data["disaring_backend"] >= 1
