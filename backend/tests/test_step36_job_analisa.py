"""
tests/test_step36_job_analisa.py
Pengujian Langkah 36:
- Pengamanan job analisa latar belakang (_AnalisaJobStore, task reference, cek akses pra-job, ownership, timeout)
- Batas waktu tunggu ML & fallback cache basi
- Peringatan startup multi-worker
- Konsistensi audit target_resource scraping_source:{id}
- Kelengkapan access_classification & document_role pada respons dokumen
"""
import asyncio
import time
from datetime import date
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app, lifespan
from app.models.document import Document
from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.scraping_source import ScrapingSource
from app.models.enums import (
    JenisAnalisa,
    KlasifikasiAkses,
    ModeAnalisa,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
)
from app.routers.ml_gateway import _analisa_jobs
from app.schemas.scan import CandidateMatchDocument
from app.services.analysis_result_service import save_analysis_result, compute_params_hash
from app.services.storage_service import StorageService
from scripts.periksa_draft_publik import run_periksa_draft_publik
from tests.conftest import make_pdf


@pytest.fixture(autouse=True)
def cleanup_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ml_service_url", "http://ml-test:8100")
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "ml_timeout_seconds", 300.0)
    monkeypatch.setattr(settings, "ml_job_timeout_seconds", 900.0)
    yield
    # Bersihkan store job setelah setiap tes
    _analisa_jobs._jobs.clear()
    _analisa_jobs._tasks.clear()


def _seed_doc(
    db: Session,
    storage: StorageService,
    title: str = "Dokumen Step36",
    reg_num: str = "36/POJK.03/2026",
    is_active: bool = True,
    access_classification: KlasifikasiAkses = KlasifikasiAkses.publik,
    document_role: PeranDokumen = PeranDokumen.corpus_eksisting,
    processing_status: StatusPemrosesan = StatusPemrosesan.terindeks,
    parent_id: int | None = None,
    is_attachment: bool = False,
    attachment_label: str | None = None,
    full_text: str | None = None,
    identity_key: str | None = None,
) -> Document:
    cat = db.query(Category).filter(Category.name == "POJK").first()
    pdf_bytes = make_pdf(f"Konten {title}")
    rel_path = storage.save_pdf(pdf_bytes, filename_hint=f"{title.replace(' ', '_').lower()}.pdf", subdir="kb/POJK/2026")

    import hashlib
    h = hashlib.sha256(f"{title}_{reg_num}_{time.time()}".encode()).hexdigest()

    doc = Document(
        title=title,
        regulation_number=reg_num,
        regulation_type="POJK",
        release_date=date(2026, 1, 1),
        regulation_year=2026,
        file_path_pdf=rel_path,
        file_hash=h,
        file_size_bytes=len(pdf_bytes),
        standardized_filename=f"{title}.pdf",
        access_classification=access_classification,
        document_role=document_role,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=processing_status,
        is_active=is_active,
        category_id=cat.id if cat else None,
        parent_document_id=parent_id,
        is_attachment=is_attachment,
        attachment_label=attachment_label,
        full_text=full_text or f"Isi teks lengkap dari {title} Pasal 1 mengatur ketentuan umum regulasi.",
        identity_key=identity_key,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_j01_post_mulai_sukses_lalu_poll(
    client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch: pytest.MonkeyPatch
):
    """J01: POST .../mulai dokumen publik, ML mock sukses, lalu poll -> berjalan -> selesai; document_id & mode ada."""
    doc = _seed_doc(db_session, test_storage, title="Dokumen J01", reg_num="01/POJK/2026")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"document_id": doc.id, "identitas": {"judul": doc.title}, "struktur": {"bab": 1}})

    monkeypatch.setattr(
        "app.routers.ml_gateway.make_job_ml_client",
        lambda timeout: httpx.AsyncClient(timeout=timeout, transport=httpx.MockTransport(handler)),
    )

    resp = client.post(f"/api/v1/ml/analisa/{doc.id}/mulai?mode=ai")
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "berjalan"
    job_id = data["job_id"]

    # Poll hingga selesai (maks 5 detik)
    hasil_job = None
    for _ in range(50):
        time.sleep(0.05)
        poll_resp = client.get(f"/api/v1/ml/analisa-job/{job_id}")
        assert poll_resp.status_code == 200
        poll_data = poll_resp.json()
        assert poll_data["document_id"] == doc.id
        assert poll_data["mode"] == "ai"
        assert "berjalan_detik" in poll_data
        if poll_data["status"] == "selesai":
            hasil_job = poll_data
            break

    assert hasil_job is not None, "Job tidak selesai dalam batas waktu polling"
    assert hasil_job["status"] == "selesai"
    assert hasil_job["hasil"]["document_id"] == doc.id
    assert hasil_job["hasil"]["identitas"]["judul"] == "Dokumen J01"


def test_j02_post_mulai_doc_tidak_ada_404_langsung(client: TestClient):
    """J02: POST .../mulai dokumen tidak ada -> 404 langsung, tidak ada job dibuat."""
    init_jobs_count = len(_analisa_jobs._jobs)
    resp = client.post("/api/v1/ml/analisa/999999/mulai")
    assert resp.status_code == 404
    assert len(_analisa_jobs._jobs) == init_jobs_count


def test_j03_post_mulai_doc_non_publik_auth_mati_403(
    client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch: pytest.MonkeyPatch
):
    """J03: POST .../mulai dokumen non-publik saat login mati -> 403 langsung, tidak ada job dibuat."""
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)
    doc = _seed_doc(
        db_session,
        test_storage,
        title="Dokumen Non-Publik J03",
        access_classification=KlasifikasiAkses.non_publik,
    )

    init_jobs_count = len(_analisa_jobs._jobs)
    resp = client.post(f"/api/v1/ml/analisa/{doc.id}/mulai")
    assert resp.status_code == 403
    assert len(_analisa_jobs._jobs) == init_jobs_count


def test_j04_post_mulai_ml_service_url_kosong_503(
    client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch: pytest.MonkeyPatch
):
    """J04: POST .../mulai saat ML_SERVICE_URL kosong -> 503 langsung, tidak ada job dibuat."""
    monkeypatch.setattr(settings, "ml_service_url", "")
    doc = _seed_doc(db_session, test_storage, title="Dokumen J04")

    init_jobs_count = len(_analisa_jobs._jobs)
    resp = client.post(f"/api/v1/ml/analisa/{doc.id}/mulai")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "layanan_analisa_belum_dikonfigurasi"
    assert len(_analisa_jobs._jobs) == init_jobs_count


def test_j05_poll_job_tidak_ada_404(client: TestClient):
    """J05: Poll job yang tidak ada -> 404 job_tidak_ditemukan."""
    resp = client.get("/api/v1/ml/analisa-job/non_existent_job_123")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "job_tidak_ditemukan"


def test_j06_poll_job_milik_pengguna_lain_auth_aktif_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """J06: Poll job milik pengguna lain saat AUTH_ENABLED=true -> 404 job_tidak_ditemukan."""
    monkeypatch.setattr(settings, "auth_enabled", True)

    # Simulasikan job milik user ID 999
    job_id = "job_user_999"
    _analisa_jobs._jobs[job_id] = {
        "status": "berjalan",
        "mulai": time.time(),
        "hasil": None,
        "error": None,
        "document_id": 10,
        "mode": "ai",
        "pemilik_id": 999,
    }

    # Request tanpa user atau user berbeda -> 404 (bukan 403, agar tidak bocor)
    from app.routers.auth import get_current_user
    from app.core.permissions import Izin, perlu_izin

    class MockUser:
        id = 1
        username = "analis1"
        role = "analis"
        is_active = True

    app.dependency_overrides[get_current_user] = lambda: MockUser()
    app.dependency_overrides[perlu_izin(Izin.ANALISA_JALANKAN)] = lambda: MockUser()
    try:
        resp = client.get(f"/api/v1/ml/analisa-job/{job_id}")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "job_tidak_ditemukan"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(perlu_izin(Izin.ANALISA_JALANKAN), None)


def test_j07_ml_timeout_fallback_cache_atau_504(
    client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch: pytest.MonkeyPatch
):
    """J07: ML timeout -> fallback cache basi tetap berjalan di dalam job jika cache tersedia; jika tidak -> gagal 504."""
    doc = _seed_doc(db_session, test_storage, title="Dokumen J07 Timeout")

    # 1. Simpan cache lama (stale cache) di database
    params_hash = compute_params_hash(JenisAnalisa.analisa)
    save_analysis_result(
        db_session,
        document_id=doc.id,
        kind=JenisAnalisa.analisa,
        mode=ModeAnalisa.ai,
        raw_result={"skor": 90, "fallback_flag": "dari_cache_lama"},
        params_hash=params_hash,
        source_fingerprint="fingerprint_lama_123",
    )

    # Mock ML transport melempar TimeoutException
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("ML service hung", request=request)

    monkeypatch.setattr(
        "app.routers.ml_gateway.make_job_ml_client",
        lambda timeout: httpx.AsyncClient(timeout=timeout, transport=httpx.MockTransport(timeout_handler)),
    )

    resp = client.post(f"/api/v1/ml/analisa/{doc.id}/mulai?mode=ai")
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    # Poll hingga selesai
    selesai_data = None
    for _ in range(50):
        time.sleep(0.05)
        poll_resp = client.get(f"/api/v1/ml/analisa-job/{job_id}")
        if poll_resp.json()["status"] != "berjalan":
            selesai_data = poll_resp.json()
            break

    assert selesai_data is not None
    # Sukses via fallback cache basi!
    assert selesai_data["status"] == "selesai"
    assert selesai_data["hasil"]["fallback_flag"] == "dari_cache_lama"
    assert selesai_data["hasil"]["cache"]["basi"] is True

    # 2. Kasus tanpa cache: untuk dokumen baru, timeout harus menghasilkan status gagal (504)
    doc_fresh = _seed_doc(db_session, test_storage, title="Dokumen J07 Fresh No Cache")
    resp_fresh = client.post(f"/api/v1/ml/analisa/{doc_fresh.id}/mulai?mode=ai")
    job_id_fresh = resp_fresh.json()["job_id"]

    gagal_data = None
    for _ in range(50):
        time.sleep(0.05)
        poll_resp = client.get(f"/api/v1/ml/analisa-job/{job_id_fresh}")
        if poll_resp.json()["status"] != "berjalan":
            gagal_data = poll_resp.json()
            break

    assert gagal_data is not None
    assert gagal_data["status"] == "gagal"
    assert gagal_data["error"]["status_code"] == 504
    assert gagal_data["error"]["detail"]["code"] == "layanan_analisa_timeout"


def test_j08_ml_gagal_500_status_job_gagal(
    client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch: pytest.MonkeyPatch
):
    """J08: ML gagal 500 -> status job gagal, error dicatat."""
    doc = _seed_doc(db_session, test_storage, title="Dokumen J08 ML Error")

    def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Internal AI server error"})

    monkeypatch.setattr(
        "app.routers.ml_gateway.make_job_ml_client",
        lambda timeout: httpx.AsyncClient(timeout=timeout, transport=httpx.MockTransport(error_handler)),
    )

    resp = client.post(f"/api/v1/ml/analisa/{doc.id}/mulai?mode=ai")
    job_id = resp.json()["job_id"]

    res_data = None
    for _ in range(50):
        time.sleep(0.05)
        poll_resp = client.get(f"/api/v1/ml/analisa-job/{job_id}")
        if poll_resp.json()["status"] != "berjalan":
            res_data = poll_resp.json()
            break

    assert res_data is not None
    assert res_data["status"] == "gagal"
    assert res_data["error"]["status_code"] in (500, 502)


def test_j09_task_reference_disimpan_dan_dibersihkan(monkeypatch: pytest.MonkeyPatch):
    """J09: Task reference disimpan di set store dan dibersihkan saat selesai."""
    store = _analisa_jobs

    async def sample_run():
        await asyncio.sleep(0.05)
        return {"ok": True}

    async def runner():
        initial_tasks = len(store._tasks)
        job_id = await store.mulai(sample_run, document_id=1, mode="ai")
        # Saat baru mulai, task harus ada di _tasks
        assert len(store._tasks) == initial_tasks + 1

        # Tunggu task selesai
        await asyncio.sleep(0.1)
        # Setelah selesai, callback add_done_callback harus membersihkannya dari _tasks
        assert len(store._tasks) == initial_tasks

        job = await store.get(job_id)
        assert job["status"] == "selesai"

    asyncio.run(runner())


def test_j10_bersih_bersih_ttl_1_jam():
    """J10: Bersih-bersih TTL 1 jam untuk job selesai/gagal."""
    store = _analisa_jobs
    now = time.time()
    store._jobs["job_old"] = {"status": "selesai", "mulai": now - 3700, "hasil": {}}
    store._jobs["job_recent"] = {"status": "selesai", "mulai": now - 100, "hasil": {}}

    asyncio.run(store._bersihkan())

    assert "job_old" not in store._jobs
    assert "job_recent" in store._jobs


def test_j11_bersih_bersih_job_berjalan_lewat_timeout():
    """J11: Bersih-bersih job berjalan yang melewati batas timeout -> ditandai gagal (analisa_terlalu_lama)."""
    store = _analisa_jobs
    now = time.time()
    # ml_job_timeout_seconds = 900, cutoff_berjalan = 900 + 120 = 1020
    store._jobs["job_stuck"] = {
        "status": "berjalan",
        "mulai": now - 1100,
        "hasil": None,
        "error": None,
    }

    asyncio.run(store._bersihkan())

    stuck = store._jobs["job_stuck"]
    assert stuck["status"] == "gagal"
    assert stuck["error"]["status_code"] == 504
    assert stuck["error"]["detail"]["code"] == "analisa_terlalu_lama"


def test_j12_startup_warning_multi_worker(monkeypatch: pytest.MonkeyPatch):
    """J12: Startup warning jika UVICORN_WORKERS > 1."""
    from app.main import logger as main_logger

    warnings = []
    orig_warning = main_logger.warning

    def capture_warning(msg, *args, **kwargs):
        rendered = (msg % args) if args else msg
        warnings.append(rendered)
        orig_warning(msg, *args, **kwargs)

    monkeypatch.setattr(main_logger, "warning", capture_warning)
    monkeypatch.setattr(settings, "uvicorn_workers", 2)

    async def run_ls():
        async with lifespan(app):
            pass

    asyncio.run(run_ls())

    assert any("UVICORN_WORKERS diatur ke 2" in w for w in warnings)


def test_j13_audit_sumber_scraping_source_di_periksa_draft_publik(db_session: Session):
    """J13: Audit sumber pada scripts/periksa_draft_publik.py menggunakan scraping_source:{id}."""
    from app.models.enums import JenisSumber

    src = ScrapingSource(
        name="Sumber Uji J13",
        url=f"https://ojk.go.id/j13_{time.time()}",
        source_type=JenisSumber.situs_web,
        default_document_role=PeranDokumen.draft_kajian,
        default_access_classification=KlasifikasiAkses.publik,
        is_active=True,
    )
    db_session.add(src)
    db_session.commit()
    db_session.refresh(src)

    run_periksa_draft_publik(db_session, apply=True)

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.target_resource == f"scraping_source:{src.id}", AuditLog.action == "UPDATE_SOURCE")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.target_resource == f"scraping_source:{src.id}"


def test_r01_kelengkapan_access_classification_dan_document_role_needs_review_dan_detail(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """R01: access_classification & document_role ada pada GET /needs-review dan lampiran/induk di detail."""
    # 1. Dokumen induk & lampiran
    induk = _seed_doc(
        db_session,
        test_storage,
        title="Induk R01",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
    )
    lampiran = _seed_doc(
        db_session,
        test_storage,
        title="Lampiran R01",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        parent_id=induk.id,
        is_attachment=True,
        attachment_label="Lampiran I",
    )

    # Cek detail dokumen induk: lampiran memuat peran & klasifikasi
    resp_induk = client.get(f"/api/v1/documents/{induk.id}")
    assert resp_induk.status_code == 200
    data_induk = resp_induk.json()
    assert len(data_induk["lampiran"]) >= 1
    lamp_item = next(item for item in data_induk["lampiran"] if item["document_id"] == lampiran.id)
    assert lamp_item["access_classification"] == "publik"
    assert lamp_item["document_role"] == "corpus_eksisting"

    # Cek detail dokumen lampiran: induk memuat peran & klasifikasi
    resp_lamp = client.get(f"/api/v1/documents/{lampiran.id}")
    assert resp_lamp.status_code == 200
    data_lamp = resp_lamp.json()
    assert data_lamp["induk"] is not None
    assert data_lamp["induk"]["access_classification"] == "publik"
    assert data_lamp["induk"]["document_role"] == "corpus_eksisting"

    # 2. Dokumen needs-review
    doc_review = _seed_doc(
        db_session,
        test_storage,
        title="Review R01",
        processing_status=StatusPemrosesan.perlu_koreksi,
        access_classification=KlasifikasiAkses.non_publik,
        document_role=PeranDokumen.draft_kajian,
    )
    resp_nr = client.get("/api/v1/documents/needs-review")
    assert resp_nr.status_code == 200
    items_nr = resp_nr.json()["items"]
    target_nr = next((it for it in items_nr if it["id"] == doc_review.id), None)
    assert target_nr is not None
    assert target_nr["access_classification"] == "non_publik"
    assert target_nr["document_role"] == "draft_kajian"


def test_r02_kelengkapan_access_classification_dan_document_role_versi_dan_kemiripan(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """R02: access_classification & document_role ada pada /versi, /kemiripan-draft, dan CandidateMatchDocument."""
    # 1. Dokumen versi
    doc_versi = _seed_doc(
        db_session,
        test_storage,
        title="Versi R02",
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        identity_key="POJK/1/2026",
    )
    resp_v = client.get(f"/api/v1/documents/{doc_versi.id}/versi")
    assert resp_v.status_code == 200
    data_v = resp_v.json()
    assert data_v["access_classification"] == "publik"
    assert data_v["document_role"] == "corpus_eksisting"

    # 2. Kemiripan draft
    draft_1 = _seed_doc(
        db_session,
        test_storage,
        title="Draft R02 Utama",
        document_role=PeranDokumen.draft_kajian,
        access_classification=KlasifikasiAkses.publik,
        full_text="Peraturan Otoritas Jasa Keuangan mengenai permodalan bank umum dan rasio kecukupan modal minimum.",
    )
    draft_2 = _seed_doc(
        db_session,
        test_storage,
        title="Draft R02 Pembanding",
        document_role=PeranDokumen.draft_kajian,
        access_classification=KlasifikasiAkses.publik,
        full_text="Peraturan Otoritas Jasa Keuangan mengenai permodalan bank umum dan rasio kecukupan modal minimum pasal 1.",
    )
    resp_km = client.get(f"/api/v1/documents/{draft_1.id}/kemiripan-draft?ambang=50.0")
    assert resp_km.status_code == 200
    data_km = resp_km.json()
    assert len(data_km["draft_mirip"]) >= 1
    mirip_item = next(it for it in data_km["draft_mirip"] if it["document_id"] == draft_2.id)
    assert mirip_item["access_classification"] == "publik"
    assert mirip_item["document_role"] == "draft_kajian"

    # 3. CandidateMatchDocument
    match_model = CandidateMatchDocument.model_validate(doc_versi)
    assert match_model.access_classification == "publik"
    assert match_model.document_role == "corpus_eksisting"
