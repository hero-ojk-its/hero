"""
tests/test_step29_smoke_lanjutan.py
Pengujian smoke test Fase 2 lanjutan (T01–T12) sesuai spesifikasi Langkah 29.
"""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock
import bcrypt
import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app
from app.models.category import Category
from app.models.document import Document
from app.models.enums import (
    JenisSumber,
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
    StatusPindai,
    StatusKandidat,
)
from app.models.scan_candidate import ScanCandidate
from app.models.scan_session import ScanSession
from app.models.scraping_source import ScrapingSource
from app.models.user import User
from app.routers.ml_gateway import get_ml_client
from app.services.storage_service import StorageService
from scripts.smoke_fase2 import (
    print_report,
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
    reg_num: str = "29/POJK/2026",
    access_classification: KlasifikasiAkses = KlasifikasiAkses.publik,
    processing_status: StatusPemrosesan = StatusPemrosesan.terindeks,
    document_role: PeranDokumen = PeranDokumen.corpus_eksisting,
    is_active: bool = True,
    pdf_terproteksi: bool = False,
    category_id: int = None,
) -> Document:
    cat = db.query(Category).filter(Category.name == "POJK").first()
    effective_cat_id = category_id if category_id is not None else (cat.id if cat else None)

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
        document_role=document_role,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=processing_status,
        is_active=is_active,
        category_id=effective_cat_id,
        pdf_terproteksi=pdf_terproteksi,
        full_text=f"Isi teks lengkap dari {title}",
        extracted_at=datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _seed_source_and_candidate(
    db: Session,
    storage: StorageService,
    doc: Document = None,
    pull_outcome: str = "success",
    match_status: str = "baru",
) -> tuple[ScrapingSource, ScanSession, ScanCandidate]:
    source = ScrapingSource(
        name="JDIH OJK Test",
        source_type=JenisSumber.situs_web,
        url="https://jdih.ojk.go.id",
        is_active=True,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    session = ScanSession(
        source_id=source.id,
        start_url=source.url,
        status=StatusPindai.selesai,
        candidates_total=1,
        candidates_new=1,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    cand = ScanCandidate(
        scan_id=session.id,
        url_hash="hash_candidate_001",
        url="https://jdih.ojk.go.id/pojk_001.pdf",
        filename="pojk_001.pdf",
        match_status=match_status,
        pull_outcome=pull_outcome,
        document_id=doc.id if doc else None,
    )
    db.add(cand)
    db.commit()
    db.refresh(cand)

    return source, session, cand


# ==============================================================================
# T01: Server normal (seed 1 sumber dengan kandidat dan dokumen) -> S16–S20 OK
# ==============================================================================
def test_t01_normal_server_s16_to_s20_ok(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """T01: Server normal dengan 1 sumber, 1 kandidat ditarik, dan 1 dokumen -> S16–S20 OK."""
    doc = _seed_smoke_doc(db_session, test_storage, title="Doc T01 Normal", reg_num="01/T01/2026")
    _seed_source_and_candidate(db_session, test_storage, doc=doc, pull_outcome="success")

    hasil = run_checks(client, doc_id=doc.id)
    by_name = {h.nama: h for h in hasil}

    assert by_name["S16"].status == "OK"
    assert "belum_berlaku" in by_name["S16"].keterangan

    assert by_name["S17"].status == "OK"
    assert "sumber=1" in by_name["S17"].keterangan

    assert by_name["S18"].status == "OK"
    assert "BOM=ada" in by_name["S18"].keterangan

    assert by_name["S19"].status == "OK"
    assert by_name["S20"].status == "OK"


# ==============================================================================
# T02: Respons summary tanpa belum_berlaku -> S16 GAGAL dengan pesan Langkah 26
# ==============================================================================
def test_t02_summary_without_belum_berlaku_fails_step26(client: TestClient):
    """T02: Respons summary tanpa kunci 'belum_berlaku' -> S16 GAGAL dengan pesan Langkah 26."""
    orig_get = client.get

    def mock_get(url, *args, **kwargs):
        if "/dashboard/summary" in url:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "kb": {
                    "by_status_keberlakuan": {
                        "berlaku": 5,
                        "tidak_berlaku": 1,
                        "diubah": 0,
                        "dicabut": 0,
                        # belum_berlaku absen
                    }
                }
            }
            return mock_resp
        return orig_get(url, *args, **kwargs)

    client.get = mock_get
    try:
        hasil = run_checks(client)
    finally:
        client.get = orig_get

    by_name = {h.nama: h for h in hasil}
    assert by_name["S16"].status == "GAGAL"
    assert "Langkah 26" in by_name["S16"].keterangan


# ==============================================================================
# T03: Corong dengan invarian dilanggar -> S17 GAGAL dan menyebut nama sumber
# ==============================================================================
def test_t03_corong_invariant_violation_fails_with_source_name(client: TestClient):
    """T03: Invarian corong dilanggar (ditemukan != sum kategori) -> S17 GAGAL dan menyebut nama sumber."""
    orig_get = client.get

    def mock_get(url, *args, **kwargs):
        if "/dashboard/corong" in url and "csv" not in url:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "sumber": [
                    {
                        "source_id": 99,
                        "nama": "Sumber Uji Rusak",
                        "jenis": "web_jdih",
                        "scan": {
                            "ditemukan": 100,  # 100 ≠ sum(10 + 20 + 5 + 5 + 10) = 50
                            "sudah_ada_di_kb": 10,
                            "ditarik": 20,
                            "duplikat": 5,
                            "gagal_unduh": 5,
                            "belum_ditarik": 10,
                        },
                        "dokumen": {
                            "di_kb": 20,
                            "menunggu_ekstraksi": 5,
                            "terbaca": 10,
                            "gagal_baca": 2,
                            "lainnya": 3,
                        },
                        "pdf": {},
                        "gagal_per_alasan": {},
                        "persen_terbaca": 50.0,
                    }
                ],
                "total": {"dokumen": {"di_kb": 20, "terbaca": 10}, "scan": {}, "pdf": {}},
            }
            return mock_resp
        return orig_get(url, *args, **kwargs)

    client.get = mock_get
    try:
        hasil = run_checks(client)
    finally:
        client.get = orig_get

    by_name = {h.nama: h for h in hasil}
    assert by_name["S17"].status == "GAGAL"
    assert "Sumber Uji Rusak" in by_name["S17"].keterangan


# ==============================================================================
# T04: Ada dokumen di kategori "Tanpa Tahun" -> S21 OK + baris PERINGATAN relokasi
# ==============================================================================
def test_t04_document_in_tanpa_tahun_shows_warning(
    client: TestClient,
    db_session: Session,
    test_storage: StorageService,
    capsys: pytest.CaptureFixture,
):
    """T04: Ada dokumen di kategori 'Tanpa Tahun' -> S21 OK dan memunculkan peringatan relokasi."""
    parent_cat = db_session.query(Category).filter(Category.name == "POJK").first()
    if not parent_cat:
        parent_cat = Category(name="POJK", auto_created=False)
        db_session.add(parent_cat)
        db_session.commit()
        db_session.refresh(parent_cat)

    cat_tt = Category(name="Tanpa Tahun", parent_id=parent_cat.id, auto_created=True)
    db_session.add(cat_tt)
    db_session.commit()
    db_session.refresh(cat_tt)

    _seed_smoke_doc(
        db_session,
        test_storage,
        title="Dokumen Tanpa Tahun T04",
        reg_num="04/TT/2026",
        category_id=cat_tt.id,
    )

    hasil = run_checks(client)
    by_name = {h.nama: h for h in hasil}

    assert by_name["S21"].status == "OK"
    assert "dokumen di 'Tanpa Tahun' — jalankan scripts/relokasi_kategori.py (dry-run dulu)" in by_name["S21"].keterangan

    print_report(hasil)
    captured = capsys.readouterr()
    assert "PERINGATAN:" in captured.out
    assert "dokumen di 'Tanpa Tahun' — jalankan scripts/relokasi_kategori.py (dry-run dulu)" in captured.out


# ==============================================================================
# T05: Seed belum_ditarik > 0 dan pdf_terproteksi NULL -> 2 baris PERINGATAN, exit code 0
# ==============================================================================
def test_t05_scan_belum_ditarik_and_uninspected_pdf_warnings(
    client: TestClient,
    db_session: Session,
    test_storage: StorageService,
    capsys: pytest.CaptureFixture,
):
    """T05: Seed belum_ditarik > 0 dan pdf_terproteksi NULL -> 2 peringatan muncul, exit 0."""
    # 1. Dokumen dengan pdf_terproteksi = None
    doc = _seed_smoke_doc(db_session, test_storage, title="Doc T05 Proteksi Null", reg_num="05/PROT/2026")
    doc.pdf_terproteksi = None
    db_session.commit()

    # 2. ScanCandidate yang belum ditarik (pull_outcome None, match_status belum_ada/baru)
    _seed_source_and_candidate(
        db_session,
        test_storage,
        doc=None,
        pull_outcome=None,
        match_status=StatusKandidat.baru,
    )

    hasil = run_checks(client, doc_id=doc.id)
    assert not any(h.status == "GAGAL" for h in hasil)

    print_report(hasil)
    captured = capsys.readouterr()

    assert "PERINGATAN: 1 hasil scan belum ditarik ke KB — Pak Faris meminta semua hasil scan masuk KB (Weekly #7)." in captured.out
    assert "PERINGATAN: 1 dokumen belum diperiksa proteksi PDF — jalankan scripts/backfill_pdf_info.py --apply." in captured.out


# ==============================================================================
# T06: Draft draft_kajian terindeks + mock ML harmonisasi 200 (2 temuan valid)
# ==============================================================================
def test_t06_harmonisasi_success_valid_findings(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """T06: Draft terindeks + mock harmonisasi 200 dengan 2 temuan valid -> S22 OK, temuan=2."""
    corpus_doc = _seed_smoke_doc(
        db_session, test_storage, title="Corpus T06", reg_num="06/CORPUS/2026"
    )
    draft_doc = _seed_smoke_doc(
        db_session,
        test_storage,
        title="Draft T06",
        reg_num="06/DRAFT/2026",
        document_role=PeranDokumen.draft_kajian,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/health"):
            return httpx.Response(200, json={"status": "siap"})
        elif "/harmonisasi/" in path:
            return httpx.Response(
                200,
                json={
                    "versi": "1.0",
                    "ringkasan": {"per_jenis": {"menggantikan": 1, "konflik": 1}},
                    "temuan": [
                        {
                            "pasal_draft": "Pasal 1",
                            "jenis": "menggantikan",
                            "pembanding": {
                                "document_id": corpus_doc.id,
                                "pdf": f"/api/v1/documents/{corpus_doc.id}/pdf",
                            },
                        },
                        {
                            "pasal_draft": "Pasal 2",
                            "jenis": "konflik",
                            "pembanding": {
                                "document_id": corpus_doc.id,
                                "pdf": f"/api/v1/documents/{corpus_doc.id}/pdf",
                            },
                        },
                    ],
                    "rujukan": [],
                },
            )
        elif "/analisa/" in path:
            return httpx.Response(200, json={"cache": {"hit": True, "run_id": 1}})
        return httpx.Response(200, json={"status": "ok"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )

    hasil = run_checks(client, doc_id=corpus_doc.id, draft_id=draft_doc.id)
    by_name = {h.nama: h for h in hasil}

    assert by_name["S22"].status == "OK"
    assert "temuan=2" in by_name["S22"].keterangan


# ==============================================================================
# T07: Mock harmonisasi dengan pembanding.pdf = "http://evil/x.pdf" -> GAGAL
# ==============================================================================
def test_t07_harmonisasi_invalid_hyperlink_fails(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """T07: Temuan memiliki hyperlink tidak valid (bukan /api/v1/documents/) -> S22 GAGAL."""
    corpus_doc = _seed_smoke_doc(
        db_session, test_storage, title="Corpus T07", reg_num="07/CORPUS/2026"
    )
    draft_doc = _seed_smoke_doc(
        db_session,
        test_storage,
        title="Draft T07",
        reg_num="07/DRAFT/2026",
        document_role=PeranDokumen.draft_kajian,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/health"):
            return httpx.Response(200, json={"status": "siap"})
        elif "/harmonisasi/" in path:
            return httpx.Response(
                200,
                json={
                    "versi": "1.0",
                    "ringkasan": {"per_jenis": {"menggantikan": 1}},
                    "temuan": [
                        {
                            "pasal_draft": "Pasal 1",
                            "jenis": "menggantikan",
                            "pembanding": {
                                "document_id": corpus_doc.id,
                                "pdf": "http://evil/x.pdf",  # Hyperlink tidak valid
                            },
                        }
                    ],
                    "rujukan": [],
                },
            )
        return httpx.Response(200, json={"status": "ok"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )

    hasil = run_checks(client, doc_id=corpus_doc.id, draft_id=draft_doc.id)
    by_name = {h.nama: h for h in hasil}

    assert by_name["S22"].status == "GAGAL"
    assert "hyperlink pembanding tidak valid" in by_name["S22"].keterangan


# ==============================================================================
# T08: Mock harmonisasi 422 / ConnectError -> S22 LEWATI
# ==============================================================================
def test_t08_harmonisasi_422_and_connect_error_skips(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """T08: Mock harmonisasi 422 (KB kosong) / ConnectError -> S22 LEWATI."""
    corpus_doc = _seed_smoke_doc(
        db_session, test_storage, title="Corpus T08", reg_num="08/CORPUS/2026"
    )
    draft_doc = _seed_smoke_doc(
        db_session,
        test_storage,
        title="Draft T08",
        reg_num="08/DRAFT/2026",
        document_role=PeranDokumen.draft_kajian,
    )

    # Sub-kasus 1: ML error 422 (pembanding kosong)
    def handler_422(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"status": "siap"})
        elif "/harmonisasi/" in request.url.path:
            return httpx.Response(422, json={"detail": {"code": "pembanding_kosong"}})
        return httpx.Response(200, json={"status": "ok"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler_422)
    )

    hasil_422 = run_checks(client, doc_id=corpus_doc.id, draft_id=draft_doc.id)
    by_name_422 = {h.nama: h for h in hasil_422}
    assert by_name_422["S22"].status == "LEWATI"
    assert "KB pembanding kosong" in by_name_422["S22"].keterangan

    # Sub-kasus 2: ConnectError / 503
    def handler_503(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"status": "siap"})
        elif "/harmonisasi/" in request.url.path:
            return httpx.Response(503, json={"detail": "Service Unavailable"})
        return httpx.Response(200, json={"status": "ok"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler_503)
    )

    hasil_503 = run_checks(client, doc_id=corpus_doc.id, draft_id=draft_doc.id)
    by_name_503 = {h.nama: h for h in hasil_503}
    assert by_name_503["S22"].status == "LEWATI"
    assert "jalur ML mati" in by_name_503["S22"].keterangan


# ==============================================================================
# T09: Tidak ada draft kajian -> S22 LEWATI
# ==============================================================================
def test_t09_no_draft_kajian_skips_s22(client: TestClient):
    """T09: Tidak ada dokumen peran draft_kajian di KB -> S22 LEWATI."""
    # Pastikan ML siap
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"status": "siap"})
        return httpx.Response(200, json={"status": "ok"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )

    # Mock GET /documents/?document_role=draft_kajian mengembalikan items kosong
    orig_get = client.get

    def mock_get(url, *args, **kwargs):
        if "document_role=draft_kajian" in url:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"items": [], "total": 0}
            return mock_resp
        return orig_get(url, *args, **kwargs)

    client.get = mock_get
    try:
        hasil = run_checks(client, draft_id=None)
    finally:
        client.get = orig_get

    by_name = {h.nama: h for h in hasil}
    assert by_name["S22"].status == "LEWATI"
    assert "Tidak ada draft kajian terindeks" in by_name["S22"].keterangan


# ==============================================================================
# T10: --tanpa-harmonisasi -> S22 LEWATI dinonaktifkan, dan tidak ada POST
# ==============================================================================
def test_t10_tanpa_harmonisasi_skips_without_post(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """T10: Opsi tanpa_harmonisasi -> S22 LEWATI 'dinonaktifkan' dan tidak melakukan request POST."""
    corpus_doc = _seed_smoke_doc(
        db_session, test_storage, title="Corpus T10", reg_num="10/CORPUS/2026"
    )
    draft_doc = _seed_smoke_doc(
        db_session,
        test_storage,
        title="Draft T10",
        reg_num="10/DRAFT/2026",
        document_role=PeranDokumen.draft_kajian,
    )

    post_called = []
    orig_post = client.post

    def tracking_post(url, *args, **kwargs):
        post_called.append(url)
        return orig_post(url, *args, **kwargs)

    client.post = tracking_post
    try:
        hasil = run_checks(
            client,
            doc_id=corpus_doc.id,
            draft_id=draft_doc.id,
            tanpa_harmonisasi=True,
        )
    finally:
        client.post = orig_post

    by_name = {h.nama: h for h in hasil}
    assert by_name["S22"].status == "LEWATI"
    assert "dinonaktifkan" in by_name["S22"].keterangan
    assert len(post_called) == 0


# ==============================================================================
# T11: Hanya-baca: semua GET kecuali tepat satu POST /api/v1/ml/harmonisasi/{id}
# ==============================================================================
def test_t11_strictly_read_only_except_one_harmonisasi_post(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """T11: Catat semua request HTTP saat run_checks: semua GET kecuali tepat satu POST ke /ml/harmonisasi/."""
    corpus_doc = _seed_smoke_doc(
        db_session, test_storage, title="Corpus T11", reg_num="11/CORPUS/2026"
    )
    draft_doc = _seed_smoke_doc(
        db_session,
        test_storage,
        title="Draft T11",
        reg_num="11/DRAFT/2026",
        document_role=PeranDokumen.draft_kajian,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/health"):
            return httpx.Response(200, json={"status": "siap"})
        elif "/harmonisasi/" in path:
            return httpx.Response(
                200,
                json={
                    "versi": "1.0",
                    "ringkasan": {"per_jenis": {"menggantikan": 1}},
                    "temuan": [
                        {
                            "pasal_draft": "Pasal 1",
                            "jenis": "menggantikan",
                            "pembanding": {
                                "document_id": corpus_doc.id,
                                "pdf": f"/api/v1/documents/{corpus_doc.id}/pdf",
                            },
                        }
                    ],
                    "rujukan": [],
                },
            )
        elif "/analisa/" in path:
            return httpx.Response(200, json={"cache": {"hit": True, "run_id": 1}})
        return httpx.Response(200, json={"status": "ok"})

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )

    observed_requests: list[tuple[str, str]] = []

    orig_get = client.get
    orig_post = client.post
    orig_put = client.put
    orig_patch = client.patch
    orig_delete = client.delete

    client.get = lambda url, *args, **kwargs: (observed_requests.append(("GET", str(url))) or orig_get(url, *args, **kwargs))
    client.post = lambda url, *args, **kwargs: (observed_requests.append(("POST", str(url))) or orig_post(url, *args, **kwargs))
    client.put = lambda url, *args, **kwargs: (observed_requests.append(("PUT", str(url))) or orig_put(url, *args, **kwargs))
    client.patch = lambda url, *args, **kwargs: (observed_requests.append(("PATCH", str(url))) or orig_patch(url, *args, **kwargs))
    client.delete = lambda url, *args, **kwargs: (observed_requests.append(("DELETE", str(url))) or orig_delete(url, *args, **kwargs))

    try:
        run_checks(client, doc_id=corpus_doc.id, draft_id=draft_doc.id)
    finally:
        client.get = orig_get
        client.post = orig_post
        client.put = orig_put
        client.patch = orig_patch
        client.delete = orig_delete

    # Verifikasi metode dan URL
    post_requests = [req for req in observed_requests if req[0] == "POST"]
    get_requests = [req for req in observed_requests if req[0] == "GET"]
    other_requests = [req for req in observed_requests if req[0] not in ("GET", "POST")]

    assert len(other_requests) == 0, f"Request HTTP selain GET dan POST ditemukan: {other_requests}"
    assert len(get_requests) > 0, "Harus ada request GET"
    assert len(post_requests) == 1, f"Harus ada tepat satu POST, ditemukan {len(post_requests)}"
    assert f"/api/v1/ml/harmonisasi/{draft_doc.id}" in post_requests[0][1]


# ==============================================================================
# T12: Auth aktif, token tanpa izin kegagalan -> S19 LEWATI
# ==============================================================================
def test_t12_auth_enabled_without_kegagalan_kelola_skips_s19(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """T12: Auth aktif, user dengan peran tanpa KEGAGALAN_KELOLA (pilot_user) -> S19 LEWATI."""
    monkeypatch.setattr(settings, "auth_enabled", True)

    pw_hash = bcrypt.hashpw(b"PilotPassword123!", bcrypt.gensalt()).decode("utf-8")
    user = User(
        username="pilot_smoke_tester",
        nama_lengkap="Pilot User Tester",
        hashed_password=pw_hash,
        role="pilot_user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    expire = datetime.now(timezone.utc) + timedelta(hours=1)
    token = jwt.encode(
        {"sub": user.username, "role": user.role, "exp": expire},
        settings.secret_key,
        algorithm="HS256",
    )
    client.headers["Authorization"] = f"Bearer {token}"

    try:
        hasil = run_checks(client)
    finally:
        client.headers.pop("Authorization", None)

    by_name = {h.nama: h for h in hasil}
    assert by_name["S19"].status == "LEWATI"
    assert "token tanpa izin kegagalan" in by_name["S19"].keterangan
