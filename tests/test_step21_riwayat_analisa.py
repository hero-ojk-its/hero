"""
tests/test_step21_riwayat_analisa.py
Pengujian Riwayat Eksekusi Analisa dan Audit Analisa per Mode (Langkah 21, US-10 #56, US-08 #34).
Kasus Uji: H01 - H19.
"""
from datetime import date, datetime, timezone
import hashlib
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app
from app.models.analysis_result import AnalysisResult
from app.models.analysis_run import AnalysisRun
from app.models.audit_log import AuditLog
from app.models.category import Category
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
from app.services.audit_service import RUN_ANALYSIS, RUN_HARMONIZATION
from app.services.storage_service import StorageService
from tests.conftest import make_pdf


@pytest.fixture(autouse=True)
def setup_ml_config(monkeypatch: pytest.MonkeyPatch):
    """Pastikan konfigurasi ML aktif dan terisolasi untuk tiap pengujian."""
    monkeypatch.setattr(settings, "ml_service_url", "http://ml-test:8100")
    monkeypatch.setattr(settings, "ml_cache_enabled", True)
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)
    monkeypatch.setattr(settings, "auth_enabled", False)
    yield
    app.dependency_overrides.pop(get_ml_client, None)


def _seed_test_doc(
    db: Session,
    storage: StorageService,
    title: str = "Dokumen Uji Langkah 21",
    reg_num: str = "21/POJK.03/2026",
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
        extracted_at=datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_h01_analisa_miss_creates_ml_run(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H01: GET /ml/analisa/{id} sekali (miss) -> 1 baris analysis_runs, sumber=ml, result terisi."""
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen H01", reg_num="01/H01/2026")
    raw_output = {
        "versi": "1.0-rules",
        "mode_dipakai": "deterministik",
        "ringkasan": "Ringkasan Dokumen H01",
        "poin_kunci": ["Poin A", "Poin B"],
        "metrik": {"jumlah_poin": 2, "kata_ringkasan": 3, "waktu_ms": 150},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw_output)

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    resp = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "cache" in data
    assert data["cache"]["run_id"] is not None

    runs = db_session.query(AnalysisRun).filter(AnalysisRun.document_id == doc.id).all()
    assert len(runs) == 1
    run = runs[0]
    assert run.id == data["cache"]["run_id"]
    assert run.kind == JenisAnalisa.analisa
    assert run.sumber == "ml"
    assert run.segar is False
    assert run.mode_diminta == ModeAnalisa.deterministik
    assert run.mode_dipakai == ModeAnalisa.deterministik
    assert run.ml_version == "1.0-rules"
    assert run.params == {"mode": "deterministik"}
    assert run.result is not None
    assert run.result["versi"] == "1.0-rules"
    expected_hash = hashlib.sha256(json.dumps(raw_output, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    assert run.result_hash == expected_hash
    assert run.ringkasan_output == {"jumlah_poin": 2, "kata_ringkasan": 3, "waktu_ms": 150}


def test_h02_analisa_cache_hit_creates_cache_run(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H02: Panggil lagi (cache hit) -> baris ke-2 sumber=cache, result=NULL, result_hash sama."""
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen H02", reg_num="02/H02/2026")
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        return httpx.Response(
            200,
            json={
                "versi": "1.0",
                "mode_dipakai": "deterministik",
                "ringkasan": "Ringkasan H02",
                "poin_kunci": ["Poin 1"],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # Panggilan 1 (miss)
    resp1 = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp1.status_code == 200
    assert call_count[0] == 1

    # Panggilan 2 (hit)
    resp2 = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp2.status_code == 200
    assert call_count[0] == 1  # Tidak panggil ML

    runs = db_session.query(AnalysisRun).filter(AnalysisRun.document_id == doc.id).order_by(AnalysisRun.id.asc()).all()
    assert len(runs) == 2
    r1, r2 = runs[0], runs[1]
    assert r1.sumber == "ml"
    assert r1.result is not None

    assert r2.sumber == "cache"
    assert r2.result is None
    assert r2.result_hash == r1.result_hash

    # analysis_results tetap 1 baris
    results_count = db_session.query(AnalysisResult).filter(AnalysisResult.document_id == doc.id).count()
    assert results_count == 1


def test_h03_analisa_segar_creates_third_ml_run(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H03: Panggil lagi dengan segar=true -> baris ke-3 sumber=ml, segar=true."""
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen H03", reg_num="03/H03/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"versi": "1.0", "mode_dipakai": "deterministik", "ringkasan": "H03"},
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    client.get(f"/api/v1/ml/analisa/{doc.id}")
    client.get(f"/api/v1/ml/analisa/{doc.id}")
    resp3 = client.get(f"/api/v1/ml/analisa/{doc.id}?segar=true")
    assert resp3.status_code == 200

    runs = db_session.query(AnalysisRun).filter(AnalysisRun.document_id == doc.id).order_by(AnalysisRun.id.asc()).all()
    assert len(runs) == 3
    assert runs[2].sumber == "ml"
    assert runs[2].segar is True


def test_h04_mode_diminta_ai_actual_deterministik(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H04: mode=ai, ML menjawab mode_dipakai: "deterministik" -> mode_diminta=ai, mode_dipakai=deterministik."""
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen H04", reg_num="04/H04/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "versi": "2.0-ai-fallback",
                "mode_dipakai": "deterministik",
                "ringkasan": "Fallback deterministik",
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    resp = client.get(f"/api/v1/ml/analisa/{doc.id}?mode=ai")
    assert resp.status_code == 200

    run = db_session.query(AnalysisRun).filter(AnalysisRun.document_id == doc.id).first()
    assert run is not None
    assert run.mode_diminta == ModeAnalisa.ai
    assert run.mode_dipakai == ModeAnalisa.deterministik


def test_h05_ml_connect_error_fallback_cache_basi(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H05: Hasil tersimpan ada, ML ConnectError -> sumber=cache_basi, http_status=200."""
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen H05", reg_num="05/H05/2026")

    # 1. Panggilan awal sukses
    def success_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"versi": "1.0", "mode_dipakai": "deterministik", "ringkasan": "Data awal"},
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(success_handler))
    resp1 = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp1.status_code == 200

    # 2. Panggilan kedua dengan segar=true tetapi ML ConnectError
    def error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("ML layer down", request=request)

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(error_handler))
    resp2 = client.get(f"/api/v1/ml/analisa/{doc.id}?segar=true")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["cache"]["basi"] is True

    runs = db_session.query(AnalysisRun).filter(AnalysisRun.document_id == doc.id).order_by(AnalysisRun.id.desc()).all()
    assert len(runs) == 2
    latest_run = runs[0]
    assert latest_run.sumber == "cache_basi"
    assert latest_run.http_status == 200
    assert latest_run.result is None


def test_h06_ml_connect_error_no_cached_result_fails(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H06: Tidak ada hasil tersimpan, ML ConnectError -> klien 503; baris sumber=gagal, http_status=503, error_code."""
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen H06", reg_num="06/H06/2026")

    def error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("ML layer down", request=request)

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(error_handler))

    resp = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp.status_code == 503
    data = resp.json()
    assert data["detail"]["code"] == "layanan_analisa_tidak_tersedia"

    run = db_session.query(AnalysisRun).filter(AnalysisRun.document_id == doc.id).first()
    assert run is not None
    assert run.sumber == "gagal"
    assert run.http_status == 503
    assert run.error_code == "layanan_analisa_tidak_tersedia"
    assert run.mode_dipakai is None


def test_h07_rejected_before_analysis_no_run_or_audit(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H07: Dokumen nonaktif / non-publik (mode lindung) / tidak ada -> tidak ada riwayat dan tidak ada audit."""
    doc_inactive = _seed_test_doc(db_session, test_storage, title="Dokumen Nonaktif", reg_num="07/INACTIVE/2026", is_active=False)
    doc_nonpublik = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen Nonpublik",
        reg_num="07/NONPUB/2026",
        access_classification=KlasifikasiAkses.non_publik,
    )

    # 1. Dokumen tidak ada
    r1 = client.get("/api/v1/ml/analisa/999999")
    assert r1.status_code == 404

    # 2. Dokumen nonaktif
    r2 = client.get(f"/api/v1/ml/analisa/{doc_inactive.id}")
    assert r2.status_code == 404

    # 3. Dokumen nonpublik (mode lindung)
    r3 = client.get(f"/api/v1/ml/analisa/{doc_nonpublik.id}")
    assert r3.status_code == 403

    # Pastikan tidak ada analysis_runs atau audit RUN_ANALYSIS
    runs = db_session.query(AnalysisRun).all()
    assert len(runs) == 0
    audits = db_session.query(AuditLog).filter(AuditLog.action == RUN_ANALYSIS).all()
    assert len(audits) == 0


def test_h08_harmonisasi_records_run_with_filtered_pembanding(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H08: Harmonisasi -> baris kind=harmonisasi, params.pembanding = daftar setelah disaring."""
    draft = _seed_test_doc(db_session, test_storage, title="Draft H08", reg_num="08/DRAFT/2026")
    comp1 = _seed_test_doc(db_session, test_storage, title="Pembanding 1", reg_num="08/C1/2026")
    comp_inactive = _seed_test_doc(db_session, test_storage, title="Pembanding Nonaktif", reg_num="08/C2/2026", is_active=False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "versi": "1.0-harmonisasi",
                "temuan": [{"document_id": comp1.id, "pasal": "1", "skor": 0.9}],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # Kirim daftar pembanding termasuk yang nonaktif
    resp = client.post(f"/api/v1/ml/harmonisasi/{draft.id}", json=[comp1.id, comp_inactive.id])
    assert resp.status_code == 200

    run = db_session.query(AnalysisRun).filter(AnalysisRun.document_id == draft.id).first()
    assert run is not None
    assert run.kind == JenisAnalisa.harmonisasi
    assert run.params["mode"] == "deterministik"
    # Dokumen nonaktif (comp_inactive.id) harus tersaring dari pembanding
    assert comp1.id in run.params["pembanding"]
    assert comp_inactive.id not in run.params["pembanding"]


def test_h09_audit_run_analysis_after_h01(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H09: Audit RUN_ANALYSIS setelah H01 -> 1 entri dengan detail.mode_dipakai, detail.sumber, detail.run_id."""
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen H09", reg_num="09/H09/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"versi": "1.0", "mode_dipakai": "deterministik", "ringkasan": "Audit Test"},
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    resp = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp.status_code == 200

    run = db_session.query(AnalysisRun).filter(AnalysisRun.document_id == doc.id).first()
    assert run is not None

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == RUN_ANALYSIS, AuditLog.target_resource == f"document:{doc.id}")
        .first()
    )
    assert audit is not None
    assert audit.detail.get("mode_dipakai") == "deterministik"
    assert audit.detail.get("sumber") == "ml"
    assert audit.detail.get("run_id") == run.id
    assert audit.detail.get("http_status") == 200


def test_h10_audit_run_harmonization_extended_detail(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H10: Audit RUN_HARMONIZATION -> detail memuat cache_hit (lama) DAN mode_dipakai, sumber, run_id (baru)."""
    draft = _seed_test_doc(db_session, test_storage, title="Draft H10", reg_num="10/DRAFT/2026")
    comp = _seed_test_doc(db_session, test_storage, title="Comp H10", reg_num="10/COMP/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"versi": "1.0", "temuan": []},
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    resp = client.post(f"/api/v1/ml/harmonisasi/{draft.id}", json=[comp.id])
    assert resp.status_code == 200

    run = db_session.query(AnalysisRun).filter(AnalysisRun.document_id == draft.id).first()
    assert run is not None

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == RUN_HARMONIZATION, AuditLog.target_resource == f"document:{draft.id}")
        .first()
    )
    assert audit is not None
    # Field lama
    assert "cache_hit" in audit.detail
    assert "jumlah_korpus" in audit.detail
    # Field baru
    assert audit.detail.get("mode_dipakai") == "deterministik"
    assert audit.detail.get("sumber") == "ml"
    assert audit.detail.get("run_id") == run.id
    assert audit.detail.get("http_status") == 200


def test_h11_audit_filter_by_mode(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H11: GET /audit/?mode=ai -> hanya entri dengan detail.mode_dipakai == 'ai'."""
    doc1 = _seed_test_doc(db_session, test_storage, title="Doc H11 Det", reg_num="11/DET/2026")
    doc2 = _seed_test_doc(db_session, test_storage, title="Doc H11 AI", reg_num="11/AI/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        if "mode=ai" in str(request.url):
            return httpx.Response(200, json={"versi": "1.0", "mode_dipakai": "ai", "ringkasan": "AI output"})
        return httpx.Response(200, json={"versi": "1.0", "mode_dipakai": "deterministik", "ringkasan": "Det output"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    client.get(f"/api/v1/ml/analisa/{doc1.id}")
    client.get(f"/api/v1/ml/analisa/{doc2.id}?mode=ai")

    resp_all = client.get("/api/v1/audit/?action=RUN_ANALYSIS")
    assert resp_all.status_code == 200
    items_all = resp_all.json()
    assert isinstance(items_all, list)
    assert len(items_all) >= 2

    resp_ai = client.get("/api/v1/audit/?action=RUN_ANALYSIS&mode=ai")
    assert resp_ai.status_code == 200
    items_ai = resp_ai.json()
    assert isinstance(items_ai, list)
    assert len(items_ai) >= 1
    for it in items_ai:
        assert it["detail"]["mode_dipakai"] == "ai"


def test_h12_get_document_analysis_runs_list(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H12: GET /documents/{id}/analisa/riwayat setelah H01-H03 -> total=3, urut terbaru, tanpa hasil."""
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen H12", reg_num="12/H12/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"versi": "1.0", "mode_dipakai": "deterministik", "ringkasan": "Test H12"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    client.get(f"/api/v1/ml/analisa/{doc.id}")
    client.get(f"/api/v1/ml/analisa/{doc.id}")
    client.get(f"/api/v1/ml/analisa/{doc.id}?segar=true")

    resp = client.get(f"/api/v1/documents/{doc.id}/analisa/riwayat")
    assert resp.status_code == 200
    data = resp.json()
    assert data["document_id"] == doc.id
    assert data["total"] == 3
    assert len(data["items"]) == 3
    # Urut terbaru dahulu
    assert data["items"][0]["run_id"] > data["items"][1]["run_id"] > data["items"][2]["run_id"]
    # Tidak memuat output lengkap
    for item in data["items"]:
        assert "hasil" not in item
        assert "ringkasan_output" in item


def test_h13_filter_history_by_kind_and_mode(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H13: Filter kind=harmonisasi dan mode=ai -> hanya baris yang cocok."""
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen H13", reg_num="13/H13/2026")
    comp = _seed_test_doc(db_session, test_storage, title="Comp H13", reg_num="13/C/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        if "harmonisasi" in str(request.url):
            return httpx.Response(200, json={"versi": "1.0", "temuan": []})
        if "mode=ai" in str(request.url):
            return httpx.Response(200, json={"versi": "1.0", "mode_dipakai": "ai", "ringkasan": "AI"})
        return httpx.Response(200, json={"versi": "1.0", "mode_dipakai": "deterministik", "ringkasan": "Det"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    client.get(f"/api/v1/ml/analisa/{doc.id}")  # analisa deterministik
    client.get(f"/api/v1/ml/analisa/{doc.id}?mode=ai")  # analisa ai
    client.post(f"/api/v1/ml/harmonisasi/{doc.id}", json=[comp.id])  # harmonisasi deterministik

    # Filter kind=harmonisasi
    resp_harm = client.get(f"/api/v1/documents/{doc.id}/analisa/riwayat?kind=harmonisasi")
    assert resp_harm.status_code == 200
    assert resp_harm.json()["total"] == 1
    assert resp_harm.json()["items"][0]["kind"] == "harmonisasi"

    # Filter mode=ai
    resp_ai = client.get(f"/api/v1/documents/{doc.id}/analisa/riwayat?mode=ai")
    assert resp_ai.status_code == 200
    assert resp_ai.json()["total"] == 1
    assert resp_ai.json()["items"][0]["mode_dipakai"] == "ai"


def test_h14_detail_cache_run_resolves_hasil_from_ml_run(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H14: GET .../riwayat/{run_id} untuk baris cache (H02) -> hasil terisi dari baris ml (lewat result_hash)."""
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen H14", reg_num="14/H14/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "versi": "1.0-h14",
                "mode_dipakai": "deterministik",
                "ringkasan": "Ringkasan Asli H14",
                "poin_kunci": ["Poin 1"],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # Panggilan 1 (miss)
    resp1 = client.get(f"/api/v1/ml/analisa/{doc.id}")
    run_id_1 = resp1.json()["cache"]["run_id"]

    # Panggilan 2 (hit)
    resp2 = client.get(f"/api/v1/ml/analisa/{doc.id}")
    run_id_2 = resp2.json()["cache"]["run_id"]
    assert run_id_1 != run_id_2

    # Verifikasi baris ke-2 di DB memiliki result = NULL
    r2_db = db_session.query(AnalysisRun).filter(AnalysisRun.id == run_id_2).first()
    assert r2_db.result is None
    assert r2_db.result_hash is not None

    # Panggil detail untuk run_id_2
    detail_resp = client.get(f"/api/v1/documents/{doc.id}/analisa/riwayat/{run_id_2}")
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["sumber"] == "cache"
    assert data["hasil"] is not None
    assert data["hasil"]["ringkasan"] == "Ringkasan Asli H14"
    assert data["cara_ulang"] == f"GET /api/v1/ml/analisa/{doc.id}?mode=deterministik&segar=true"


def test_h15_detail_run_filters_subsequently_deactivated_reference(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H15: Detail run: dokumen rujukan kemudian dinonaktifkan -> rujukan tersaring dari hasil, disaring_backend >= 1."""
    doc = _seed_test_doc(db_session, test_storage, title="Draft H15", reg_num="15/DRAFT/2026")
    comp = _seed_test_doc(db_session, test_storage, title="Comp H15", reg_num="15/COMP/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "versi": "1.0",
                "temuan": [{"document_id": comp.id, "pasal": "5", "skor": 0.85}],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    resp = client.post(f"/api/v1/ml/harmonisasi/{doc.id}", json=[comp.id])
    assert resp.status_code == 200
    run_id = resp.json()["cache"]["run_id"]

    # Sekarang nonaktifkan comp
    comp.is_active = False
    db_session.commit()

    # Buka detail riwayat
    detail_resp = client.get(f"/api/v1/documents/{doc.id}/analisa/riwayat/{run_id}")
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["hasil"] is not None
    assert data["hasil"]["disaring_backend"] >= 1
    # Temuan untuk comp harus sudah dibuang
    assert len(data["hasil"]["temuan"]) == 0


def test_h16_run_id_belongs_to_different_document_returns_404(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H16: run_id milik dokumen lain -> 404."""
    doc_a = _seed_test_doc(db_session, test_storage, title="Doc A", reg_num="16/A/2026")
    doc_b = _seed_test_doc(db_session, test_storage, title="Doc B", reg_num="16/B/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"versi": "1.0", "mode_dipakai": "deterministik"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    resp = client.get(f"/api/v1/ml/analisa/{doc_b.id}")
    run_id_b = resp.json()["cache"]["run_id"]

    # Akses run_id_b melalui doc_a
    detail_resp = client.get(f"/api/v1/documents/{doc_a.id}/analisa/riwayat/{run_id_b}")
    assert detail_resp.status_code == 404


def test_h17_history_non_public_protected_mode_returns_403(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H17: /analisa/riwayat dokumen non-publik, mode lindung -> 403."""
    doc_np = _seed_test_doc(
        db_session,
        test_storage,
        title="Doc NP H17",
        reg_num="17/NP/2026",
        access_classification=KlasifikasiAkses.non_publik,
    )

    resp = client.get(f"/api/v1/documents/{doc_np.id}/analisa/riwayat")
    assert resp.status_code == 403


def test_h18_record_run_exception_does_not_break_response(
    client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch: pytest.MonkeyPatch
):
    """H18: record_run dipaksa melempar exception (monkeypatch) -> GET /ml/analisa tetap 200, cache.run_id = null."""
    doc = _seed_test_doc(db_session, test_storage, title="Doc H18", reg_num="18/H18/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"versi": "1.0", "mode_dipakai": "deterministik", "ringkasan": "Data H18"},
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def broken_record_run(*args, **kwargs):
        raise RuntimeError("Database connection suddenly dropped!")

    monkeypatch.setattr("app.routers.ml_gateway.record_run", broken_record_run)

    resp = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ringkasan"] == "Data H18"
    assert data["cache"]["run_id"] is None


def test_h19_response_cache_run_id_matches_database(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """H19: Respons analisa -> cache.run_id = id baris riwayat yang baru dibuat."""
    doc = _seed_test_doc(db_session, test_storage, title="Doc H19", reg_num="19/H19/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"versi": "1.0", "mode_dipakai": "deterministik", "ringkasan": "Data H19"},
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    resp = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp.status_code == 200
    data = resp.json()
    returned_run_id = data["cache"]["run_id"]
    assert returned_run_id is not None

    run = db_session.query(AnalysisRun).filter(AnalysisRun.id == returned_run_id).first()
    assert run is not None
    assert run.document_id == doc.id
