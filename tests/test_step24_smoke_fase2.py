"""
tests/test_step24_smoke_fase2.py
Pengujian smoke test Fase 2 (Q01–Q09) sesuai spesifikasi Langkah 24.
"""
from datetime import date, datetime, timezone
import sys
from typing import List
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app
from app.models.category import Category
from app.models.document import Document
from app.models.enums import KlasifikasiAkses, PeranDokumen, StatusKeberlakuan, StatusPemrosesan
from app.routers.ml_gateway import get_ml_client
from app.services.storage_service import StorageService
from scripts.smoke_fase2 import (
    get_local_alembic_head,
    main as smoke_main,
    run_checks,
)
from tests.conftest import make_pdf


@pytest.fixture(autouse=True)
def _setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ml_service_url", "http://mock-ml-service:8080")
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)
    monkeypatch.setattr(settings, "auth_enabled", False)
    yield
    app.dependency_overrides.pop(get_ml_client, None)


def _seed_smoke_doc(
    db: Session,
    storage: StorageService,
    title: str = "Dokumen Smoke Fase 2",
    reg_num: str = "24/POJK.03/2026",
    access_classification: KlasifikasiAkses = KlasifikasiAkses.publik,
    processing_status: StatusPemrosesan = StatusPemrosesan.terindeks,
    is_active: bool = True,
) -> Document:
    cat = db.query(Category).filter(Category.name == "POJK").first()
    pdf_bytes = make_pdf(f"Konten {title}")
    rel_path = storage.save_pdf(
        pdf_bytes,
        filename_hint=f"{title.replace(' ', '_').lower()}.pdf",
        subdir="kb/POJK/2026",
    )

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


def _create_ml_success_handler():
    raw_output = {
        "versi": "1.0-rules",
        "mode_dipakai": "deterministik",
        "ringkasan": "Ringkasan Dokumen Uji Smoke",
        "poin_kunci": ["Poin A", "Poin B"],
        "poin_utama": [
            {"pasal": "Pasal 1", "isi": "Ketentuan umum", "kategori": "umum"}
        ],
        "metrik": {"jumlah_poin": 2, "kata_ringkasan": 4, "waktu_ms": 120},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/health"):
            return httpx.Response(200, json={"status": "siap"})
        elif "/analisa/" in path:
            return httpx.Response(200, json=raw_output)
        return httpx.Response(200, json={"status": "ok"})

    return handler


# ==============================================================================
# Q01: ML hidup, semua normal
# ==============================================================================
def test_q01_ml_alive_all_normal(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """Q01: ML hidup, semua normal -> Semua cek OK kecuali yang memang LEWATI (S15); exit code 0."""
    doc = _seed_smoke_doc(db_session, test_storage, title="Doc Q01 Normal", reg_num="01/Q01/2026")
    handler = _create_ml_success_handler()
    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )

    hasil = run_checks(client, doc_id=doc.id)
    by_name = {h.nama: h for h in hasil}

    assert by_name["S01"].status == "OK"
    assert by_name["S02"].status == "OK"
    assert by_name["S03"].status == "OK"
    assert by_name["S04"].status == "OK"
    assert by_name["S05"].status == "OK"
    assert by_name["S06"].status == "OK"
    assert by_name["S07"].status == "OK"
    assert by_name["S08"].status == "OK"
    assert by_name["S09"].status == "OK"
    assert by_name["S10"].status == "OK"
    assert by_name["S11"].status == "OK"
    assert by_name["S12"].status == "OK"
    assert by_name["S13"].status == "OK"
    assert by_name["S14"].status == "OK"
    assert by_name["S15"].status == "LEWATI"  # Belum ada dokumen non-publik

    assert not any(h.status == "GAGAL" for h in hasil)


# ==============================================================================
# Q02: --expect-revision salah
# ==============================================================================
def test_q02_expect_revision_wrong(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """Q02: --expect-revision salah -> S01 GAGAL dengan pesan 'VPS belum di-deploy versi terbaru'; exit code 1."""
    doc = _seed_smoke_doc(db_session, test_storage, title="Doc Q02 Rev Wrong", reg_num="02/Q02/2026")
    handler = _create_ml_success_handler()
    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )

    wrong_rev = "revisi_palsu_999999"
    hasil = run_checks(client, expect_revision=wrong_rev, doc_id=doc.id)
    by_name = {h.nama: h for h in hasil}

    s01 = by_name["S01"]
    assert s01.status == "GAGAL"
    assert "VPS belum di-deploy versi terbaru" in s01.keterangan
    assert wrong_rev in s01.keterangan
    assert any(h.status == "GAGAL" for h in hasil)


# ==============================================================================
# Q03: ML mati (ConnectError) setelah satu analisa tersimpan
# ==============================================================================
def test_q03_ml_dead_after_one_analysis_saved(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """Q03: ML mati (ConnectError) setelah satu analisa tersimpan -> S03 LEWATI, S06 OK jalur ML mati, S07 LEWATI."""
    doc = _seed_smoke_doc(db_session, test_storage, title="Doc Q03 ML Dead After", reg_num="03/Q03/2026")

    # 1. Jalankan sekali analisa saat ML hidup
    handler_good = _create_ml_success_handler()
    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler_good)
    )
    init_res = client.get(f"/api/v1/ml/analisa/{doc.id}")
    assert init_res.status_code == 200

    # 2. Matikan ML (simulasikan ConnectError)
    def handler_dead(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Koneksi ditolak ke ML service")

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler_dead)
    )

    hasil = run_checks(client, doc_id=doc.id)
    by_name = {h.nama: h for h in hasil}

    assert by_name["S03"].status == "LEWATI"
    assert "ML tidak siap" in by_name["S03"].keterangan

    assert by_name["S06"].status == "OK"
    assert "jalur ML mati" in by_name["S06"].keterangan

    assert by_name["S07"].status == "LEWATI"
    assert not any(h.status == "GAGAL" for h in hasil)


# ==============================================================================
# Q04: ML mati, belum pernah ada analisa
# ==============================================================================
def test_q04_ml_dead_never_analyzed(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """Q04: ML mati, belum pernah ada analisa -> S06 OK (503 jalur ML mati); S08–S13 tidak GAGAL."""
    doc = _seed_smoke_doc(db_session, test_storage, title="Doc Q04 ML Dead Brand New", reg_num="04/Q04/2026")

    def handler_dead(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Layanan ML tidak aktif")

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler_dead)
    )

    hasil = run_checks(client, doc_id=doc.id)
    by_name = {h.nama: h for h in hasil}

    assert by_name["S03"].status == "LEWATI"
    assert by_name["S06"].status == "OK"
    assert "jalur ML mati" in by_name["S06"].keterangan
    assert by_name["S07"].status == "LEWATI"

    # S08–S13 tidak boleh GAGAL
    for code in ("S08", "S09", "S10", "S11", "S12", "S13"):
        assert by_name[code].status in ("OK", "LEWATI"), f"{code} berstatus {by_name[code].status}"

    assert not any(h.status == "GAGAL" for h in hasil)


# ==============================================================================
# Q05: Tidak ada dokumen yang memenuhi syarat
# ==============================================================================
def test_q05_no_eligible_document(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    """Q05: Tidak ada dokumen memenuhi syarat -> S04 LEWATI; cek dokumen LEWATI; exit code 0."""
    # Mock GET /documents/?limit=20 mengembalikan daftar kosong
    from unittest.mock import MagicMock

    def mock_get(url, *args, **kwargs):
        if "/api/v1/documents/?limit=20" in url or "/api/v1/documents/?limit=50" in url:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"total": 0, "items": []}
            return mock_resp
        return client.get(url, *args, **kwargs)

    client_mock = MagicMock()
    client_mock.get = mock_get
    client_mock.headers = client.headers

    hasil = run_checks(client_mock, doc_id=None)
    by_name = {h.nama: h for h in hasil}

    assert by_name["S04"].status == "LEWATI"
    for code in ("S05", "S06", "S07", "S08", "S09", "S10", "S11", "S12", "S13"):
        assert by_name[code].status == "LEWATI", f"{code} tidak berstatus LEWATI"

    assert not any(h.status == "GAGAL" for h in hasil)


# ==============================================================================
# Q06: Ada dokumen non-publik, auth mati
# ==============================================================================
def test_q06_non_public_document_auth_disabled(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """Q06: Ada dokumen non-publik, auth mati -> S15 OK (403)."""
    doc_pub = _seed_smoke_doc(db_session, test_storage, title="Doc Publik Q06", reg_num="06/PUB/2026")
    _seed_smoke_doc(
        db_session,
        test_storage,
        title="Doc NonPublik Q06",
        reg_num="06/NONPUB/2026",
        access_classification=KlasifikasiAkses.non_publik,
    )
    handler = _create_ml_success_handler()
    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )

    hasil = run_checks(client, doc_id=doc_pub.id)
    by_name = {h.nama: h for h in hasil}

    assert by_name["S15"].status == "OK"
    assert "403" in by_name["S15"].keterangan


# ==============================================================================
# Q07: Skrip hanya membaca (hanya HTTP GET)
# ==============================================================================
def test_q07_script_is_strictly_read_only(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """Q07: Skrip hanya membaca -> Semua panggilan HTTP dari run_checks adalah metode GET."""
    doc = _seed_smoke_doc(db_session, test_storage, title="Doc Q07 ReadOnly", reg_num="07/RO/2026")
    handler = _create_ml_success_handler()
    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )

    observed_methods: List[str] = []

    original_get = client.get
    original_post = client.post
    original_put = client.put
    original_patch = client.patch
    original_delete = client.delete

    def tracking_get(url, *args, **kwargs):
        observed_methods.append("GET")
        return original_get(url, *args, **kwargs)

    def tracking_post(url, *args, **kwargs):
        observed_methods.append("POST")
        return original_post(url, *args, **kwargs)

    def tracking_put(url, *args, **kwargs):
        observed_methods.append("PUT")
        return original_put(url, *args, **kwargs)

    def tracking_patch(url, *args, **kwargs):
        observed_methods.append("PATCH")
        return original_patch(url, *args, **kwargs)

    def tracking_delete(url, *args, **kwargs):
        observed_methods.append("DELETE")
        return original_delete(url, *args, **kwargs)

    client.get = tracking_get
    client.post = tracking_post
    client.put = tracking_put
    client.patch = tracking_patch
    client.delete = tracking_delete

    try:
        run_checks(client, doc_id=doc.id)
    finally:
        client.get = original_get
        client.post = original_post
        client.put = original_put
        client.patch = tracking_patch
        client.delete = original_delete

    assert len(observed_methods) > 0
    assert all(m == "GET" for m in observed_methods)
    assert "POST" not in observed_methods
    assert "PUT" not in observed_methods
    assert "PATCH" not in observed_methods
    assert "DELETE" not in observed_methods


# ==============================================================================
# Q08: HERO_SMOKE_TOKEN di-set
# ==============================================================================
def test_q08_hero_smoke_token_attached_and_redacted(
    client: TestClient,
    db_session: Session,
    test_storage: StorageService,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
):
    """Q08: HERO_SMOKE_TOKEN di-set -> Token terkirim sebagai Authorization: Bearer, tidak muncul di output."""
    secret_token = "rahasia_smoke_jwt_token_xyz123"
    monkeypatch.setenv("HERO_SMOKE_TOKEN", secret_token)

    captured_headers: List[dict] = []
    orig_get = client.get

    def header_inspecting_get(url, *args, **kwargs):
        # Ambil header yang efektif
        merged_headers = dict(client.headers)
        if "headers" in kwargs and kwargs["headers"]:
            merged_headers.update(kwargs["headers"])
        captured_headers.append(merged_headers)
        return orig_get(url, *args, **kwargs)

    client.get = header_inspecting_get
    try:
        run_checks(client)
    finally:
        client.get = orig_get

    # Pastikan header Authorization terpasang dengan Bearer <token>
    assert len(captured_headers) > 0
    assert any(
        h.get("authorization") == f"Bearer {secret_token}" or h.get("Authorization") == f"Bearer {secret_token}"
        for h in captured_headers
    )

    # Simulasikan pemanggilan main() dengan argumen --help / eksekusi
    monkeypatch.setattr(sys, "argv", ["smoke_fase2.py", "--expect-revision", "test_rev"])
    # Jalankan smoke_main yang akan menangkap exception koneksi ke default URL
    smoke_main()
    captured = capsys.readouterr()

    # Pastikan token tidak pernah bocor ke stdout maupun stderr
    assert secret_token not in captured.out
    assert secret_token not in captured.err


# ==============================================================================
# Q09: Head Alembic default
# ==============================================================================
def test_q09_alembic_head_default():
    """Q09: Head Alembic default -> get_local_alembic_head sama dengan revisi head Alembic saat ini."""
    head_rev = get_local_alembic_head()
    assert head_rev == "f2a3b4c5d6e7"
