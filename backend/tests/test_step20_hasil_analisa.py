"""
tests/test_step20_hasil_analisa.py
Pengujian Penyimpanan Hasil Analisa per Mode dan Cache Gerbang ML (Langkah 20, US-05 #49).
Kasus Uji: A01 - A14.
"""
from datetime import date, datetime, timezone
import json
from typing import Any
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app
from app.models.analysis_result import AnalysisResult
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
from app.services.audit_service import RUN_HARMONIZATION
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
    title: str = "Dokumen Uji Analisa",
    reg_num: str = "20/POJK.03/2026",
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
        file_hash=f"hash_{title.replace(' ', '_').lower()}",
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


def test_a01_analisa_two_calls_hits_cache(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    A01: GET /ml/analisa/{id} dua kali -> panggilan ML 1 kali; panggilan kedua cache.hit=true.
    """
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen A01", reg_num="01/A01/2026")
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        return httpx.Response(
            200,
            json={
                "versi": "1.0",
                "mode_dipakai": "deterministik",
                "ringkasan": "Ringkasan Dokumen A01",
                "poin_kunci": ["Poin A", "Poin B"],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # Panggilan pertama (cache miss)
    resp1 = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()
    assert call_count[0] == 1
    assert data1["cache"]["hit"] is False
    assert data1["cache"]["basi"] is False
    assert data1["cache"]["mode_tersimpan"] == "deterministik"

    # Panggilan kedua (cache hit)
    resp2 = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert call_count[0] == 1  # ML TIDAK dipanggil lagi
    assert data2["cache"]["hit"] is True
    assert data2["cache"]["basi"] is False
    assert data2["cache"]["mode_tersimpan"] == "deterministik"
    assert data2["ringkasan"] == "Ringkasan Dokumen A01"


def test_a02_analisa_segar_true_forces_recomputation(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    A02: Kali kedua dengan segar=true -> ML dipanggil lagi, cache.hit=false, baris diperbarui (tidak ganda).
    """
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen A02", reg_num="02/A02/2026")
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        return httpx.Response(
            200,
            json={
                "versi": f"1.{call_count[0]}",
                "mode_dipakai": "deterministik",
                "ringkasan": f"Ringkasan Call {call_count[0]}",
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    resp1 = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp1.status_code == 200
    assert call_count[0] == 1

    # Panggilan kedua dengan segar=true
    resp2 = client.get(f"/api/v1/ml/analisa/{doc.id}?segar=true")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert call_count[0] == 2
    assert data2["cache"]["hit"] is False
    assert data2["ringkasan"] == "Ringkasan Call 2"

    # Pastikan baris di tabel analysis_results tidak berlipat ganda
    rows = (
        db_session.query(AnalysisResult)
        .filter(
            AnalysisResult.document_id == doc.id,
            AnalysisResult.kind == JenisAnalisa.analisa,
            AnalysisResult.mode == ModeAnalisa.deterministik,
        )
        .all()
    )
    assert len(rows) == 1
    assert rows[0].result["ringkasan"] == "Ringkasan Call 2"


def test_a03_document_extracted_at_change_invalidates_cache(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    A03: Setelah panggilan pertama, extracted_at dokumen berubah -> panggilan berikut memanggil ML lagi (fingerprint berbeda).
    """
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen A03", reg_num="03/A03/2026")
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        return httpx.Response(200, json={"mode_dipakai": "deterministik", "call": call_count[0]})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    resp1 = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp1.status_code == 200
    assert call_count[0] == 1

    # Ubah extracted_at dokumen (mensimulasikan ekstraksi ulang berkas)
    doc.extracted_at = datetime(2026, 10, 15, 8, 30, 0, tzinfo=timezone.utc)
    db_session.commit()

    # Panggilan berikutnya dengan segar=false bawaan
    resp2 = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp2.status_code == 200
    assert call_count[0] == 2  # ML dipanggil ulang karena fingerprint berubah
    assert resp2.json()["cache"]["hit"] is False


def test_a04_mode_ai_fallback_to_deterministik_saved_as_deterministik(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    A04: mode=ai diminta, ML menjawab mode_dipakai: "deterministik" -> tersimpan sebagai deterministik, tidak ada baris ai.
    """
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen A04", reg_num="04/A04/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "mode_dipakai": "deterministik",
                "ringkasan": "AI tidak tersedia, jatuh ke deterministik",
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    resp = client.get(f"/api/v1/ml/analisa/{doc.id}?mode=ai")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cache"]["mode_tersimpan"] == "deterministik"

    # Verifikasi di database: hanya ada deterministik, tidak ada baris ai
    row_ai = (
        db_session.query(AnalysisResult)
        .filter(
            AnalysisResult.document_id == doc.id,
            AnalysisResult.kind == JenisAnalisa.analisa,
            AnalysisResult.mode == ModeAnalisa.ai,
        )
        .first()
    )
    assert row_ai is None

    row_det = (
        db_session.query(AnalysisResult)
        .filter(
            AnalysisResult.document_id == doc.id,
            AnalysisResult.kind == JenisAnalisa.analisa,
            AnalysisResult.mode == ModeAnalisa.deterministik,
        )
        .first()
    )
    assert row_det is not None


def test_a05_mode_ai_saved_as_ai_and_preserves_deterministik(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    A05: mode=ai, ML menjawab mode_dipakai: "ai" -> tersimpan sebagai ai; baris deterministik sebelumnya tetap utuh.
    """
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen A05", reg_num="05/A05/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        mode_req = request.url.params.get("mode")
        if mode_req == "ai":
            return httpx.Response(200, json={"mode_dipakai": "ai", "ringkasan": "Analisa AI"})
        return httpx.Response(200, json={"mode_dipakai": "deterministik", "ringkasan": "Analisa Deterministik"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # Panggil deterministik lebih dulu
    resp_det = client.get(f"/api/v1/ml/analisa/{doc.id}?mode=deterministik")
    assert resp_det.status_code == 200
    assert resp_det.json()["cache"]["mode_tersimpan"] == "deterministik"

    # Panggil AI
    resp_ai = client.get(f"/api/v1/ml/analisa/{doc.id}?mode=ai")
    assert resp_ai.status_code == 200
    assert resp_ai.json()["cache"]["mode_tersimpan"] == "ai"

    # Verifikasi di DB: kedua baris tersimpan berdampingan
    rows = (
        db_session.query(AnalysisResult)
        .filter(
            AnalysisResult.document_id == doc.id,
            AnalysisResult.kind == JenisAnalisa.analisa,
        )
        .all()
    )
    modes = {r.mode for r in rows}
    assert modes == {ModeAnalisa.deterministik, ModeAnalisa.ai}


def test_a06_cached_result_exists_ml_connect_error_returns_stale_cache(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    A06: Hasil tersimpan ada; ML melempar ConnectError -> 200, isi tersimpan, cache.basi=true.
    """
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen A06", reg_num="06/A06/2026")

    def good_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"mode_dipakai": "deterministik", "ringkasan": "Hasil Awal"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(good_handler))
    resp1 = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp1.status_code == 200

    # Sekarang ML mati (ConnectError) dan dokumen diekstraksi ulang sehingga fingerprint berubah
    def broken_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("ML service down")

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(broken_handler))

    # Paksa hitung ulang atau dengan fingerprint berubah
    doc.extracted_at = datetime(2026, 10, 16, 0, 0, 0, tzinfo=timezone.utc)
    db_session.commit()

    resp2 = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["cache"]["hit"] is True
    assert data2["cache"]["basi"] is True
    assert data2["ringkasan"] == "Hasil Awal"


def test_a07_no_cached_result_ml_connect_error_returns_503(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    A07: Tidak ada hasil tersimpan; ML melempar ConnectError -> 503 layanan_analisa_tidak_tersedia.
    """
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen A07", reg_num="07/A07/2026")

    def broken_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("ML service down")

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(broken_handler))

    resp = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "layanan_analisa_tidak_tersedia"


def test_a08_cached_result_with_later_deactivated_reference_is_filtered(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    A08: Hasil tersimpan memuat rujukan ke dokumen yang kemudian dinonaktifkan ->
    saat dibaca dari cache, rujukan itu tersaring dan disaring_backend >= 1.
    """
    main_doc = _seed_test_doc(db_session, test_storage, title="Main A08", reg_num="08/MAIN/2026")
    ref_doc = _seed_test_doc(db_session, test_storage, title="Ref A08", reg_num="08/REF/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "mode_dipakai": "deterministik",
                "ringkasan": "Analisa dengan rujukan",
                "rujukan": [
                    {
                        "document_id": ref_doc.id,
                        "key": "POJK|08|REF",
                        "teks": "Rujukan ke dokumen ref",
                        "kutipan": "Pasal 1 ayat 1",
                    }
                ],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # Panggilan 1 saat ref_doc masih aktif
    resp1 = client.get(f"/api/v1/ml/analisa/{main_doc.id}")
    assert resp1.status_code == 200
    assert resp1.json()["rujukan"][0]["document_id"] == ref_doc.id
    assert resp1.json()["disaring_backend"] == 0

    # Nonaktifkan ref_doc
    ref_doc.is_active = False
    db_session.commit()

    # Panggilan 2 membaca dari cache
    resp2 = client.get(f"/api/v1/ml/analisa/{main_doc.id}")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["cache"]["hit"] is True
    # Rujukan disaring secara dinamis: document_id dinetralkan, kutipan dibuang
    assert data2["rujukan"][0]["document_id"] is None
    assert "kutipan" not in data2["rujukan"][0]
    assert data2["disaring_backend"] >= 1


def test_a09_harmonisasi_two_calls_same_corpus_hits_cache(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    A09: Harmonisasi dua kali dengan korpus sama -> ML 1 kali; audit kedua cache_hit=true.
    """
    draft = _seed_test_doc(db_session, test_storage, title="Draft A09", reg_num="09/DRAFT/2026")
    corpus = _seed_test_doc(db_session, test_storage, title="Corpus A09", reg_num="09/CORPUS/2026")

    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        return httpx.Response(
            200,
            json={
                "versi": "1.0",
                "kandidat": [{"document_id": corpus.id, "judul": corpus.title}],
                "temuan": [],
                "rujukan": [],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # Panggilan 1
    resp1 = client.post(f"/api/v1/ml/harmonisasi/{draft.id}", json=[corpus.id])
    assert resp1.status_code == 200
    assert call_count[0] == 1
    assert resp1.json()["cache"]["hit"] is False

    # Panggilan 2
    resp2 = client.post(f"/api/v1/ml/harmonisasi/{draft.id}", json=[corpus.id])
    assert resp2.status_code == 200
    assert call_count[0] == 1
    assert resp2.json()["cache"]["hit"] is True

    # Cek audit RUN_HARMONIZATION terbaru
    audits = (
        db_session.query(AuditLog)
        .filter(AuditLog.target_resource == f"document:{draft.id}", AuditLog.action == RUN_HARMONIZATION)
        .order_by(AuditLog.id.desc())
        .all()
    )
    assert len(audits) >= 2
    assert audits[0].detail["cache_hit"] is True
    assert audits[1].detail["cache_hit"] is False


def test_a10_harmonisasi_corpus_change_triggers_recomputation(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    A10: Harmonisasi, lalu satu dokumen korpus dinonaktifkan, lalu harmonisasi lagi ->
    ML dipanggil lagi (params_hash berbeda).
    """
    draft = _seed_test_doc(db_session, test_storage, title="Draft A10", reg_num="10/DRAFT/2026")
    c1 = _seed_test_doc(db_session, test_storage, title="Corpus 1 A10", reg_num="10/C1/2026")
    c2 = _seed_test_doc(db_session, test_storage, title="Corpus 2 A10", reg_num="10/C2/2026")

    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        return httpx.Response(200, json={"kandidat": [], "temuan": [], "rujukan": []})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # Panggilan 1: harmonisasi terhadap seluruh korpus (body null)
    resp1 = client.post(f"/api/v1/ml/harmonisasi/{draft.id}", json=None)
    assert resp1.status_code == 200
    assert call_count[0] == 1

    # Nonaktifkan c2
    c2.is_active = False
    db_session.commit()

    # Panggilan 2: harmonisasi body null lagi
    resp2 = client.post(f"/api/v1/ml/harmonisasi/{draft.id}", json=None)
    assert resp2.status_code == 200
    assert call_count[0] == 2  # ML dipanggil lagi karena forward_body berkurang
    assert resp2.json()["cache"]["hit"] is False


def test_a11_comparison_endpoint_returns_both_modes_without_calling_ml(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    A11: GET /documents/{id}/analisa/banding setelah A05 ->
    deterministik dan ai keduanya terisi; ML TIDAK dipanggil.
    """
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen A11", reg_num="11/A11/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        mode_req = request.url.params.get("mode")
        if mode_req == "ai":
            return httpx.Response(200, json={"versi": "ai-1", "mode_dipakai": "ai", "ringkasan": "AI Ringkasan"})
        return httpx.Response(200, json={"versi": "det-1", "mode_dipakai": "deterministik", "ringkasan": "Det Ringkasan"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # Eksekusi kedua mode via gateway
    client.get(f"/api/v1/ml/analisa/{doc.id}?mode=deterministik")
    client.get(f"/api/v1/ml/analisa/{doc.id}?mode=ai")

    # Sekarang pasang handler yang melempar AssertionError jika ML dipanggil
    def forbidden_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Layanan ML tidak boleh dipanggil oleh endpoint perbandingan!")

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(forbidden_handler))

    resp = client.get(f"/api/v1/documents/{doc.id}/analisa/banding")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["document_id"] == doc.id
    assert data["deterministik"] is not None
    assert data["ai"] is not None
    assert data["deterministik"]["basi"] is False
    assert data["ai"]["basi"] is False
    assert data["deterministik"]["hasil"]["ringkasan"] == "Det Ringkasan"
    assert data["ai"]["hasil"]["ringkasan"] == "AI Ringkasan"
    assert "Draft / Rekomendasi" in data["catatan"]


def test_a12_comparison_endpoint_unanalysed_document_returns_null_modes(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    A12: /analisa/banding untuk dokumen yang belum pernah dianalisa -> 200, keduanya null.
    """
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen A12 Kosong", reg_num="12/A12/2026")

    resp = client.get(f"/api/v1/documents/{doc.id}/analisa/banding")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["document_id"] == doc.id
    assert data["deterministik"] is None
    assert data["ai"] is None
    assert "catatan" in data


def test_a13_ml_cache_disabled_bypasses_cache_and_persistence(
    client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch: pytest.MonkeyPatch
):
    """
    A13: ml_cache_enabled=False, analisa dua kali -> ML dipanggil 2 kali, tidak ada baris tersimpan.
    """
    monkeypatch.setattr(settings, "ml_cache_enabled", False)
    doc = _seed_test_doc(db_session, test_storage, title="Dokumen A13", reg_num="13/A13/2026")
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        return httpx.Response(200, json={"mode_dipakai": "deterministik", "ringkasan": "No Cache"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    resp1 = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp1.status_code == 200
    assert call_count[0] == 1

    resp2 = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert resp2.status_code == 200
    assert call_count[0] == 2  # Dipanggil lagi karena cache nonaktif

    # Cek DB: tidak ada baris di analysis_results
    rows = db_session.query(AnalysisResult).filter(AnalysisResult.document_id == doc.id).all()
    assert len(rows) == 0


def test_a14_comparison_endpoint_non_public_protected_returns_403(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    A14: /analisa/banding dokumen non-publik, mode lindung -> 403.
    """
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Dokumen A14 Rahasia",
        reg_num="14/A14/2026",
        access_classification=KlasifikasiAkses.non_publik,
    )

    resp = client.get(f"/api/v1/documents/{doc.id}/analisa/banding")
    assert resp.status_code == 403
    assert "Dokumen non-publik hanya dapat dibuka setelah login diaktifkan." in resp.text
