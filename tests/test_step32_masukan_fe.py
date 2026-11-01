"""
tests/test_step32_masukan_fe.py
Pengujian untuk Langkah 32: Masukan Frontend (F01 - F15)
- Bug corong source_id tidak ada -> 404
- Harmonisasi hitung ulang per_jenis dan disaring_rincian
- Pesan izin 403
- Filter antrean kegagalan tanpa_sumber (unggah manual)
- Kategori dokumen nonaktif pada tree dan 409 delete
- Penanda kategori_manual pada dokumen
- Placement eksplisit pada PATCH metadata
- Model OpenAPI 5 endpoint tidak kosong
- Cache corong 60 detik (segar=true, TTL, multi-thread lock)
- Format CSV corong BOM + TOTAL
"""
from datetime import date
import time
from typing import Optional
from unittest.mock import patch

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.config import settings
from app.models.category import Category
from app.models.document import Document
from app.models.enums import (
    JenisJobIngest,
    JenisKegagalan,
    JenisSumber,
    KlasifikasiAkses,
    PeranDokumen,
    StatusJobIngest,
    StatusKeberlakuan,
    StatusPemrosesan,
    StatusTindakLanjut,
)
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.models.scan_candidate import ScanCandidate
from app.models.scan_session import ScanSession
from app.models.scraping_source import ScrapingSource
from app.models.user import User
from app.routers.ml_gateway import get_ml_client
import app.services.corong_service as corong_svc
from app.services.corong_service import clear_corong_cache
from app.services.storage_service import StorageService
from tests.conftest import make_pdf


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ml_service_url", "http://ml-test:8100")
    clear_corong_cache()
    yield
    clear_corong_cache()
    app.dependency_overrides.pop(get_ml_client, None)


def _seed_test_doc(
    db: Session,
    storage: StorageService,
    *,
    title: str,
    reg_num: Optional[str] = "POJK/01/2026",
    reg_type: str = "POJK",
    is_active: bool = True,
    access_class: KlasifikasiAkses = KlasifikasiAkses.publik,
    category_id: Optional[int] = None,
    kategori_manual: bool = False,
    full_text: str = "Isi pasal regulasi lengkap...",
) -> Document:
    clean_title = title.replace(" ", "_").lower().replace("/", "_")
    pdf_bytes = make_pdf(f"Konten {title}")
    rel_path = storage.save_pdf(pdf_bytes, filename_hint=f"{clean_title}.pdf", subdir="kb/POJK/2026")

    doc = Document(
        title=title,
        regulation_number=reg_num,
        regulation_type=reg_type,
        release_date=date(2026, 3, 15),
        regulation_year=2026,
        bidang="Perbankan",
        access_classification=access_class,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        file_path_pdf=rel_path,
        file_hash=f"hash_{clean_title}_{time.time_ns()}",
        file_size_bytes=len(pdf_bytes),
        standardized_filename=f"{clean_title}.pdf",
        category_id=category_id,
        kategori_manual=kategori_manual,
        is_active=is_active,
        full_text=full_text,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# ============================================================================
# F01: /dashboard/corong?source_id=99999 -> 404, bukan 500
# ============================================================================
def test_f01_corong_source_id_not_found(client: TestClient):
    resp = client.get("/api/v1/dashboard/corong?source_id=99999")
    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data
    assert "Sumber dengan ID 99999 tidak ditemukan" in data["detail"]


# ============================================================================
# F02: /dashboard/corong?source_id=<ada> -> 200, total sesuai sumber itu (regresi C10)
# ============================================================================
def test_f02_corong_source_id_exists(client: TestClient, db_session: Session):
    src = ScrapingSource(
        name="Sumber F02",
        url="https://ojk.go.id/f02",
        source_type=JenisSumber.situs_web,
        is_active=True,
    )
    db_session.add(src)
    db_session.commit()
    db_session.refresh(src)

    resp = client.get(f"/api/v1/dashboard/corong?source_id={src.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["sumber"]) == 1
    assert data["sumber"][0]["source_id"] == src.id
    assert "total" in data
    assert "dihitung_pada" in data


# ============================================================================
# F03: Harmonisasi: 4 temuan (2 menggantikan, 1 pasal_baru, 1 memperjelas),
#      1 temuan pembandingnya non-publik saat auth mati
#      -> per_jenis dihitung ulang (sesuai 3 temuan tersisa);
#         disaring_backend tetap angka; disaring_rincian.temuan = 1;
#         jumlah rincian = disaring_backend
# ============================================================================
def test_f03_harmonisasi_ringkasan_and_disaring_rincian(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    draft_doc = _seed_test_doc(db_session, test_storage, title="Draft F03", reg_num="DRAFT/03/2026")
    allowed_doc = _seed_test_doc(db_session, test_storage, title="Publik F03", reg_num="PUB/03/2026")
    secret_doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Rahasia F03",
        reg_num="SEC/03/2026",
        access_class=KlasifikasiAkses.non_publik,
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "versi": "1.0",
                "ringkasan": {
                    "total_temuan": 4,
                    "per_jenis": {
                        "menggantikan": 2,
                        "pasal_baru": 1,
                        "memperjelas": 1,
                    },
                    "rencana_perubahan": None,
                },
                "temuan": [
                    {"id": 1, "jenis": "menggantikan", "pembanding": {"document_id": allowed_doc.id}},
                    {"id": 2, "jenis": "menggantikan", "pembanding": {"document_id": secret_doc.id}},  # Dibuang!
                    {"id": 3, "jenis": "pasal_baru", "pembanding": {"document_id": allowed_doc.id}},
                    {"id": 4, "jenis": "memperjelas", "pembanding": {"document_id": allowed_doc.id}},
                ],
                "rujukan": [],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(mock_handler)
    )

    with patch.object(settings, "auth_enabled", False), patch.object(
        settings, "protect_non_public_when_auth_disabled", True
    ):
        resp = client.post(f"/api/v1/ml/harmonisasi/{draft_doc.id}?segar=true", json=None)

    assert resp.status_code == 200
    data = resp.json()

    assert len(data["temuan"]) == 3
    # per_jenis dihitung ulang: menggantikan tinggal 1, pasal_baru 1, memperjelas 1
    ringkasan = data["ringkasan"]
    assert ringkasan["per_jenis"]["menggantikan"] == 1
    assert ringkasan["per_jenis"]["pasal_baru"] == 1
    assert ringkasan["per_jenis"]["memperjelas"] == 1

    # disaring_backend tetap angka
    assert data["disaring_backend"] == 1
    # disaring_rincian memuat temuan = 1
    rincian = data["disaring_rincian"]
    assert rincian["temuan"] == 1
    assert sum(rincian.values()) == data["disaring_backend"]


# ============================================================================
# F04: Harmonisasi dari cache (panggilan kedua) -> per_jenis juga dihitung ulang
# ============================================================================
def test_f04_harmonisasi_from_cache_recomputes_per_jenis(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    draft_doc = _seed_test_doc(db_session, test_storage, title="Draft F04", reg_num="DRAFT/04/2026")
    allowed_doc = _seed_test_doc(db_session, test_storage, title="Publik F04", reg_num="PUB/04/2026")
    secret_doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Rahasia F04",
        reg_num="SEC/04/2026",
        access_class=KlasifikasiAkses.non_publik,
    )

    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "versi": "1.0",
                "ringkasan": {
                    "total_temuan": 2,
                    "per_jenis": {"menggantikan": 1, "konflik": 1},
                },
                "temuan": [
                    {"id": 1, "jenis": "menggantikan", "pembanding": {"document_id": allowed_doc.id}},
                    {"id": 2, "jenis": "konflik", "pembanding": {"document_id": secret_doc.id}},
                ],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(mock_handler)
    )

    with patch.object(settings, "auth_enabled", False), patch.object(
        settings, "protect_non_public_when_auth_disabled", True
    ), patch.object(settings, "ml_cache_enabled", True):
        # Panggilan pertama (segar)
        r1 = client.post(f"/api/v1/ml/harmonisasi/{draft_doc.id}", json=None)
        assert r1.status_code == 200
        assert r1.json()["cache"]["hit"] is False
        assert call_count == 1

        # Panggilan kedua (cache hit)
        r2 = client.post(f"/api/v1/ml/harmonisasi/{draft_doc.id}", json=None)
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["cache"]["hit"] is True
        assert call_count == 1  # Tidak memanggil ML lagi

        # per_jenis tetap dihitung ulang setelah disaring
        assert data2["ringkasan"]["per_jenis"]["menggantikan"] == 1
        assert data2["ringkasan"]["per_jenis"]["konflik"] == 0
        assert data2["disaring_rincian"]["temuan"] == 1


# ============================================================================
# F05: Auth aktif, token tanpa izin -> 403 dengan detail.code, detail.izin, dan detail.message
# ============================================================================
def test_f05_auth_active_forbidden_message(client: TestClient, db_session: Session):
    # Buat user dengan peran pilot_user yang tidak memiliki hak KB_KELOLA
    user = User(
        username="pilot_f05",
        hashed_password="pw",
        role="pilot_user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    token = jwt.encode({"sub": user.username}, settings.secret_key, algorithm="HS256")

    with patch.object(settings, "auth_enabled", True):
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post(
            "/api/v1/categories/",
            json={"name": "Kategori Dilarang"},
            headers=headers,
        )
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["code"] == "akses_ditolak"
        assert detail["izin"] == "KB_KELOLA"
        assert "message" in detail
        assert "Akun Anda tidak memiliki izin KB_KELOLA untuk aksi ini." in detail["message"]


# ============================================================================
# F06: /ingest/failures?tanpa_sumber=true -> hanya kegagalan unggah manual;
#      dengan source_id sekaligus -> 422
# ============================================================================
def test_f06_failures_tanpa_sumber_and_422_on_conflict(client: TestClient, db_session: Session):
    # 1. Buat kegagalan tanpa sumber (unggah manual)
    job_manual = JobIngest(
        job_type=JenisJobIngest.unggah_manual,
        source_id=None,
        status=StatusJobIngest.selesai,
    )
    db_session.add(job_manual)
    db_session.commit()
    db_session.refresh(job_manual)

    fail_manual = IngestFailure(
        job_id=job_manual.id,
        original_filename="manual_fail.pdf",
        failure_type=JenisKegagalan.ekstraksi_gagal,
        reason_code="teks_kosong",
        message="Gagal mengekstrak teks",
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    # 2. Buat sumber dan kegagalan yang terkait sumber scan
    src = ScrapingSource(name="Sumber F06", url="https://ojk.go.id/f06", source_type=JenisSumber.situs_web, is_active=True)
    db_session.add_all([fail_manual, src])
    db_session.commit()

    scan = ScanSession(source_id=src.id, start_url="https://ojk.go.id/f06", status="siap_dipilih")
    db_session.add(scan)
    db_session.commit()

    job_scan = JobIngest(
        job_type=JenisJobIngest.scraping,
        source_id=src.id,
        status=StatusJobIngest.selesai,
    )
    db_session.add(job_scan)
    db_session.commit()
    db_session.refresh(job_scan)

    fail_scan = IngestFailure(
        job_id=job_scan.id,
        original_filename="scan_fail.pdf",
        failure_type=JenisKegagalan.ekstraksi_gagal,
        reason_code="ocr_timeout",
        message="OCR timeout saat scan",
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    db_session.add(fail_scan)
    db_session.commit()

    cand = ScanCandidate(
        scan_id=scan.id,
        url="https://ojk.go.id/doc.pdf",
        url_hash="hash_f06",
        filename="scan_fail.pdf",
        failure_id=fail_scan.id,
    )
    db_session.add(cand)
    db_session.commit()

    # Query tanpa_sumber=true
    resp = client.get("/api/v1/ingest/failures?tanpa_sumber=true")
    assert resp.status_code == 200
    data = resp.json()
    item_ids = [item["id"] for item in data["items"]]
    assert fail_manual.id in item_ids
    assert fail_scan.id not in item_ids

    # Gabungan tanpa_sumber=true dan source_id -> 422
    resp_err = client.get(f"/api/v1/ingest/failures?tanpa_sumber=true&source_id={src.id}")
    assert resp_err.status_code == 422


# ============================================================================
# F07: Kategori dengan 1 dokumen aktif + 1 nonaktif
#      -> tree: jumlah_dokumen=1, jumlah_dokumen_nonaktif=1
#      -> DELETE -> 409 dengan dokumen_aktif=1, dokumen_nonaktif=1, dan pesan baru
# ============================================================================
def test_f07_category_with_inactive_documents_tree_and_delete_409(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    cat = Category(name="Kategori F07", parent_id=None, auto_created=False)
    db_session.add(cat)
    db_session.commit()
    db_session.refresh(cat)

    _seed_test_doc(db_session, test_storage, title="Doc Aktif", reg_num="A01/2026", category_id=cat.id, is_active=True)
    _seed_test_doc(db_session, test_storage, title="Doc Nonaktif", reg_num="A02/2026", category_id=cat.id, is_active=False)

    # 1. Cek /categories/tree
    resp_tree = client.get("/api/v1/categories/tree")
    assert resp_tree.status_code == 200
    tree_nodes = resp_tree.json()
    node = next((n for n in tree_nodes if n["id"] == cat.id), None)
    assert node is not None
    assert node["jumlah_dokumen"] == 1
    assert node["jumlah_dokumen_nonaktif"] == 1

    # 2. Cek /categories/{id}
    resp_detail = client.get(f"/api/v1/categories/{cat.id}")
    assert resp_detail.status_code == 200
    det = resp_detail.json()
    assert det["jumlah_dokumen"] == 1
    assert det["jumlah_dokumen_nonaktif"] == 1

    # 3. Cek DELETE /categories/{id} -> 409
    resp_del = client.delete(f"/api/v1/categories/{cat.id}")
    assert resp_del.status_code == 409
    del_detail = resp_del.json()["detail"]
    assert del_detail["dokumen"] == 2
    assert del_detail["dokumen_aktif"] == 1
    assert del_detail["dokumen_nonaktif"] == 1
    assert del_detail["message"] == "Kategori masih memiliki 0 subkategori dan 2 dokumen (1 di antaranya nonaktif)."


# ============================================================================
# F08: Detail dan daftar dokumen memuat kategori_manual
# ============================================================================
def test_f08_documents_contain_kategori_manual(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    doc = _seed_test_doc(
        db_session,
        test_storage,
        title="Doc F08",
        reg_num="DOC/08/2026",
        kategori_manual=True,
    )

    # Detail dokumen
    resp_get = client.get(f"/api/v1/documents/{doc.id}")
    assert resp_get.status_code == 200
    data_get = resp_get.json()
    assert "kategori_manual" in data_get
    assert data_get["kategori_manual"] is True

    # Daftar dokumen (search)
    resp_search = client.get("/api/v1/documents/?limit=10")
    assert resp_search.status_code == 200
    items = resp_search.json()["items"]
    target = next((item for item in items if item["id"] == doc.id), None)
    assert target is not None
    assert "kategori_manual" in target
    assert target["kategori_manual"] is True


# ============================================================================
# F09: PATCH metadata mengubah judul pada dokumen yang metadatanya belum cukup
#      -> placement = {placed:false, reason:"metadata_belum_cukup", ...}
# ============================================================================
def test_f09_patch_metadata_insufficient_returns_explicit_placement(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    # Buat dokumen dengan metadata tidak cukup (misal release_date None dan regulation_year None)
    pdf_bytes = make_pdf("Doc F09")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint="doc_f09.pdf", subdir="kb")
    doc = Document(
        title="Dokumen Judul Awal",
        regulation_number=None,
        regulation_type=None,
        release_date=None,
        regulation_year=None,
        bidang=None,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.diterima,
        file_path_pdf=rel_path,
        file_hash="hash_f09",
        file_size_bytes=len(pdf_bytes),
        standardized_filename="doc_f09.pdf",
        is_active=True,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={"title": "Judul Baru F09"},
    )
    assert resp.status_code == 200
    data = resp.json()
    placement = data["placement"]
    assert placement is not None
    assert placement["placed"] is False
    assert placement["reason"] == "metadata_belum_cukup"
    assert "category_id" in placement
    assert "category_path" in placement


# ============================================================================
# F10: PATCH metadata yang tidak mengubah field penempatan -> placement = null
# ============================================================================
def test_f10_patch_metadata_no_placement_fields_changed(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    doc = _seed_test_doc(db_session, test_storage, title="Doc F10", reg_num="DOC/10/2026")

    # Hanya mengubah access_classification (bukan field penempatan)
    resp = client.patch(
        f"/api/v1/documents/{doc.id}/metadata",
        json={"access_classification": "non_publik"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["placement"] is None


# ============================================================================
# F11: POST /categories/ respons memuat semua field lama + jumlah_dokumen
# ============================================================================
def test_f11_post_categories_model_compatibility(client: TestClient):
    resp = client.post(
        "/api/v1/categories/",
        json={"name": "Kategori F11", "classification_rule": '{"tag": "f11"}'},
    )
    assert resp.status_code == 201
    data = resp.json()

    # Field-field lama ORM
    assert "id" in data
    assert data["name"] == "Kategori F11"
    assert "parent_id" in data
    assert "auto_created" in data
    assert data["auto_created"] is False
    assert data["classification_rule"] == '{"tag": "f11"}'
    assert "created_at" in data
    assert "updated_at" in data

    # Field-field baru
    assert "path" in data
    assert "document_count" in data
    assert "jumlah_dokumen" in data
    assert "jumlah_dokumen_nonaktif" in data
    assert data["jumlah_dokumen"] == 0
    assert data["jumlah_dokumen_nonaktif"] == 0


# ============================================================================
# F12: OpenAPI: skema respons kelima endpoint §8 tidak kosong (cek app.openapi())
# ============================================================================
def test_f12_openapi_response_models_not_empty():
    openapi_schema = app.openapi()
    paths = openapi_schema["paths"]

    # 1. POST /api/v1/ml/harmonisasi/{document_id}
    p_harm = paths["/api/v1/ml/harmonisasi/{document_id}"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert p_harm != {}
    assert "$ref" in p_harm or p_harm.get("type") == "object"

    # 2. GET /api/v1/dashboard/corong
    p_corong = paths["/api/v1/dashboard/corong"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert p_corong != {}
    assert "$ref" in p_corong or p_corong.get("type") == "object"

    # 3. GET /api/v1/categories/tree
    p_tree = paths["/api/v1/categories/tree"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert p_tree != {}
    assert p_tree.get("type") == "array" or "$ref" in p_tree

    # 4. POST /api/v1/categories/
    p_cat = paths["/api/v1/categories/"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]
    assert p_cat != {}
    assert "$ref" in p_cat or p_cat.get("type") == "object"

    # 5. PATCH /api/v1/documents/{document_id}/metadata
    p_meta = paths["/api/v1/documents/{document_id}/metadata"]["patch"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert p_meta != {}
    assert "$ref" in p_meta or p_meta.get("type") == "object"


# ============================================================================
# F13: Respons harmonisasi dengan field tambahan tak dikenal dan pembanding: null
#      -> lolos validasi response_model (extra allow, Optional); field tambahan tetap ada
# ============================================================================
def test_f13_harmonisasi_extra_allow_and_nullable_pembanding(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    draft_doc = _seed_test_doc(db_session, test_storage, title="Draft F13", reg_num="DRAFT/13/2026")
    allowed_doc = _seed_test_doc(db_session, test_storage, title="Publik F13", reg_num="PUB/13/2026")

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "versi": "1.0",
                "custom_layer_field": "nilai_tambahan_f13",
                "ringkasan": {
                    "total_temuan": 2,
                    "rencana_perubahan": None,
                },
                "temuan": [
                    {
                        "id": 1,
                        "jenis": "revisi",
                        "pembanding": None,  # pembanding null
                        "catatan_khusus": "tambahan_temuan",
                    },
                    {
                        "id": 2,
                        "jenis": "baru",
                        "pembanding": {
                            "document_id": allowed_doc.id,
                            "key": "KEY-13",
                            "nomor": "NOMOR-13",
                            "status": "berlaku",
                            "pdf": None,
                        },
                    },
                ],
            },
        )

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(mock_handler)
    )

    with patch.object(settings, "auth_enabled", False), patch.object(
        settings, "protect_non_public_when_auth_disabled", False
    ):
        resp = client.post(f"/api/v1/ml/harmonisasi/{draft_doc.id}?segar=true", json=None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["custom_layer_field"] == "nilai_tambahan_f13"
    assert data["temuan"][0]["pembanding"] is None
    assert data["temuan"][0]["catatan_khusus"] == "tambahan_temuan"
    assert data["temuan"][1]["pembanding"]["document_id"] == allowed_doc.id
    assert data["temuan"][1]["pembanding"]["key"] == "KEY-13"


# ============================================================================
# F14: Cache corong: dua panggilan berturut-turut
#      -> panggilan kedua tidak menjalankan query agregat (spy/hitung query);
#      -> segar=true menghitung ulang;
#      -> setelah TTL (mock waktu) dihitung ulang
# ============================================================================
def test_f14_corong_cache_and_segar_and_ttl(client: TestClient, db_session: Session):
    src = ScrapingSource(name="Sumber F14", url="https://ojk.go.id/f14", source_type=JenisSumber.situs_web, is_active=True)
    db_session.add(src)
    db_session.commit()

    # Panggilan 1: hitung fresh
    t0 = 1000.0
    with patch("time.time", return_value=t0):
        with patch("app.services.corong_service._compute_document_metrics", wraps=corong_svc._compute_document_metrics) as spy_compute:
            r1 = client.get(f"/api/v1/dashboard/corong?source_id={src.id}")
            assert r1.status_code == 200
            assert spy_compute.call_count > 0

    # Panggilan 2: dalam rentang 60s, tanpa segar -> ambil dari cache, _compute_document_metrics tidak dipanggil
    t1 = t0 + 10.0
    with patch("time.time", return_value=t1):
        with patch("app.services.corong_service._compute_document_metrics", wraps=corong_svc._compute_document_metrics) as spy_compute:
            r2 = client.get(f"/api/v1/dashboard/corong?source_id={src.id}")
            assert r2.status_code == 200
            assert spy_compute.call_count == 0  # CACHE HIT!
            assert r2.json()["dihitung_pada"] == r1.json()["dihitung_pada"]

    # Panggilan 3: segar=true -> bypass cache dan hitung ulang
    with patch("time.time", return_value=t1):
        with patch("app.services.corong_service._compute_document_metrics", wraps=corong_svc._compute_document_metrics) as spy_compute:
            r3 = client.get(f"/api/v1/dashboard/corong?source_id={src.id}&segar=true")
            assert r3.status_code == 200
            assert spy_compute.call_count > 0  # DIPANGGIL ULANG!

    # Panggilan 4: setelah TTL (misal 65 detik berlalu) -> dihitung ulang
    t2 = t1 + 65.0
    with patch("time.time", return_value=t2):
        with patch("app.services.corong_service._compute_document_metrics", wraps=corong_svc._compute_document_metrics) as spy_compute:
            r4 = client.get(f"/api/v1/dashboard/corong?source_id={src.id}")
            assert r4.status_code == 200
            assert spy_compute.call_count > 0  # TTL KEDALUWARSA -> HITUNG ULANG!


# ============================================================================
# F15: CSV corong tetap BOM + TOTAL (regresi C11)
# ============================================================================
def test_f15_csv_corong_bom_and_total(client: TestClient, db_session: Session):
    src = ScrapingSource(name="Sumber F15", url="https://ojk.go.id/f15", source_type=JenisSumber.situs_web, is_active=True)
    db_session.add(src)
    db_session.commit()

    resp = client.get("/api/v1/dashboard/corong?format=csv")
    assert resp.status_code == 200

    # Diawali UTF-8 BOM
    assert resp.content.startswith(b"\xef\xbb\xbf")

    text_csv = resp.content.decode("utf-8-sig")
    assert "TOTAL" in text_csv
    assert "Content-Disposition" in resp.headers
    assert "filename*=" in resp.headers["Content-Disposition"]


# ============================================================================
# F16: PATCH metadata exclude_unset
# ============================================================================
def test_f16_patch_metadata_exclude_unset(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    from app.routers.documents import router as documents_router

    # Verifikasi konfigurasi response_model_exclude_unset pada route PATCH metadata
    route = next(
        r
        for r in documents_router.routes
        if getattr(r, "path", None) == "/{document_id}/metadata"
        and "PATCH" in r.methods
    )
    assert route.response_model_exclude_unset is True

    doc = _seed_test_doc(db_session, test_storage, title="Judul Lama", reg_num="PATCH/16/2026")

    with patch.object(settings, "auth_enabled", False):
        resp = client.patch(
            f"/api/v1/documents/{doc.id}/metadata",
            json={"title": "Judul Baru F16"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Judul Baru F16"
    assert "changed_fields" in data


# ============================================================================
# F17: POST /ml/harmonisasi exclude_unset & tipe longgar (pembanding, badge, ringkasan)
# ============================================================================
def test_f17_harmonisasi_exclude_unset_and_relaxed_types(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    draft_doc = _seed_test_doc(db_session, test_storage, title="Draft F17", reg_num="DRAFT/17/2026")
    allowed_doc = _seed_test_doc(db_session, test_storage, title="Publik F17", reg_num="PUB/17/2026")

    mock_payload = {
        "status": "selesai",
        "ringkasan": {
            "per_jenis": {"konflik": "satu", "kustom": 99.5},
            "extra_field_ringkasan": "nilai_ringkasan",
            # total_temuan TIDAK DIKIRIM
        },
        "temuan": [
            {
                "id": "t17",
                "jenis": "konflik",
                # judul TIDAK DIKIRIM
                "deskripsi": "Deskripsi F17",
                "badge": {"tone": 123, "label": True, "ikon": "alert"},
                "pembanding": {
                    "document_id": allowed_doc.id,
                    "key": 999,
                    "nomor": 12345,  # int bukan string
                    "status": 1,
                    "judul": 2026,
                    "pdf": False,
                    "tautan": 404,
                    "extra_pembanding": "extra_val",
                },
                "extra_field_temuan": "temuan_extra",
            }
        ],
        "extra_field_root": "nilai_root",
    }

    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_payload)

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(mock_handler)
    )

    with patch.object(settings, "auth_enabled", False):
        resp = client.post(f"/api/v1/ml/harmonisasi/{draft_doc.id}?segar=true", json=None)

    assert resp.status_code == 200
    data = resp.json()

    # 1. exclude_unset: total_temuan & temuan.judul tidak disuntik bila tidak dikirim
    assert "total_temuan" not in data["ringkasan"]
    assert "judul" not in data["temuan"][0]

    # 2. tipe longgar & extra fields dipertahankan
    assert data["extra_field_root"] == "nilai_root"
    assert data["ringkasan"]["per_jenis"]["konflik"] == "satu"
    assert data["ringkasan"]["per_jenis"]["kustom"] == 99.5
    assert data["ringkasan"]["extra_field_ringkasan"] == "nilai_ringkasan"

    item = data["temuan"][0]
    assert item["extra_field_temuan"] == "temuan_extra"
    assert item["badge"]["tone"] == 123
    assert item["badge"]["label"] is True
    assert item["badge"]["ikon"] == "alert"

    p = item["pembanding"]
    assert p["nomor"] == 12345
    assert p["key"] == 999
    assert p["extra_pembanding"] == "extra_val"


# ============================================================================
# F18: sesuaikan_ringkasan_harmonisasi mempertahankan per_jenis asli bila temuan=0
# ============================================================================
def test_f18_sesuaikan_ringkasan_harmonisasi_preserves_per_jenis_when_no_findings_filtered(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    draft_doc = _seed_test_doc(db_session, test_storage, title="Draft F18", reg_num="DRAFT/18/2026")
    allowed_doc = _seed_test_doc(db_session, test_storage, title="Publik F18", reg_num="PUB/18/2026")

    # Mock mengirim count 100 & 50 padahal list temuan hanya 1 item
    mock_payload = {
        "status": "selesai",
        "ringkasan": {
            "total_temuan": 100,
            "per_jenis": {"tipe_a": 50, "tipe_b": 50},
        },
        "temuan": [
            {
                "id": "t18",
                "jenis": "tipe_a",
                "pembanding": {
                    "document_id": allowed_doc.id,  # Dokumen publik diizinkan -> rincian['temuan'] == 0
                },
            }
        ],
    }

    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_payload)

    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(mock_handler)
    )

    with patch.object(settings, "auth_enabled", False):
        resp = client.post(f"/api/v1/ml/harmonisasi/{draft_doc.id}?segar=true", json=None)

    assert resp.status_code == 200
    data = resp.json()

    assert data["disaring_rincian"]["temuan"] == 0
    # Karena tidak ada temuan tersaring, per_jenis asli tidak ditimpa
    assert data["ringkasan"]["per_jenis"] == {"tipe_a": 50, "tipe_b": 50}


# ============================================================================
# F19: tarik_semua dan smoke memanggil corong dengan ?segar=true
# ============================================================================
def test_f19_tarik_semua_and_smoke_call_corong_with_segar_true():
    # 1. tarik_semua.ambil_corong
    from scripts.tarik_semua import ambil_corong

    mock_client = httpx.Client()
    with patch.object(mock_client, "get") as mock_get:
        mock_get.return_value = httpx.Response(
            200,
            json={"total": {"dokumen": {"di_kb": 12}, "scan": {"belum_ditarik": 8}}},
        )
        res = ambil_corong(mock_client)
        assert res is not None
        assert res.di_kb == 12
        assert res.belum_ditarik == 8
        assert mock_get.call_count == 1
        called_url = mock_get.call_args[0][0]
        assert "segar=true" in called_url

    # 2. smoke_fase2 S17
    from scripts.smoke_fase2 import run_checks

    mock_smoke_client = httpx.Client()
    with patch.object(mock_smoke_client, "get") as mock_get:
        mock_get.return_value = httpx.Response(
            200,
            json={
                "status": "ok",
                "migration_version": "head",
                "total": {},
                "sources": [],
                "documents": [],
            },
        )
        run_checks(mock_smoke_client, expect_revision="head", tanpa_harmonisasi=True)
        called_urls = [call.args[0] for call in mock_get.call_args_list if call.args]
        assert any("/api/v1/dashboard/corong?segar=true" in str(url) for url in called_urls)
        called_urls = [call.args[0] for call in mock_get.call_args_list if call.args]
        assert any("/api/v1/dashboard/corong?segar=true" in url for url in called_urls)


