"""
tests/test_scan_push.py
Pengujian mode push untuk crawler Data/ML (K17).
"""
import pytest
from sqlalchemy.orm import Session
from app.config import settings
from app.models.document import Document
from app.models.enums import KlasifikasiAkses, PeranDokumen, StatusPemrosesan, StatusKeberlakuan
from app.services.file_validation import fingerprint
from tests.conftest import make_pdf


def test_k17_push_mode_scan_workflow(client, db_session: Session, monkeypatch):
    """K17: Pengujian alur push crawler: claim -> kirim batch kandidat -> KB comparison -> 401 jika tanpa API key."""
    monkeypatch.setattr(settings, "crawl_allow_private_networks", True)
    monkeypatch.setattr(settings, "crawler_backend", "push")

    # Pra-isi dokumen untuk pengujian perbandingan
    content_dup = make_pdf("Pre-existing Doc for Push Test")
    fp_dup = fingerprint(content_dup)
    doc_exist = Document(
        title="Dokumen Push Eksisting",
        source_url="https://ojk.go.id/regulasi/pojk_lama.pdf",
        original_filename="pojk_lama.pdf",
        file_path_pdf="kb/pojk_lama.pdf",
        file_hash=fp_dup.sha256,
        file_size_bytes=fp_dup.size_bytes,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.diterima,
        status_keberlakuan=StatusKeberlakuan.berlaku,
    )
    db_session.add(doc_exist)
    db_session.commit()

    # 1. Daftarkan sumber web dan mulai scan dalam mode push
    resp_src = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Push Source", "url": "https://ojk.go.id/regulasi", "source_type": "situs_web"},
    )
    src_id = resp_src.json()["id"]

    resp_scan = client.post("/api/v1/scans/", json={"source_id": src_id})
    assert resp_scan.status_code == 202
    scan_id = resp_scan.json()["scan_id"]

    # 2. Coba claim tanpa API key -> 401
    resp_unauth = client.post("/api/v1/internal/scans/claim")
    assert resp_unauth.status_code == 401

    # 3. Claim dengan API key yang benar
    headers = {"X-Internal-API-Key": settings.internal_api_key}
    resp_claim = client.post("/api/v1/internal/scans/claim?limit=1", headers=headers)
    assert resp_claim.status_code == 200
    claimed_items = resp_claim.json()
    assert len(claimed_items) == 1
    assert claimed_items[0]["scan_id"] == scan_id

    # 4. Kirim Batch 1 (done=False)
    batch1 = {
        "candidates": [
            {
                "url": "https://ojk.go.id/regulasi/pojk_lama.pdf",
                "filename": "pojk_lama.pdf",
                "size_bytes": fp_dup.size_bytes,
                "found_on_page": "https://ojk.go.id/regulasi",
                "depth": 1,
            }
        ],
        "pages_visited": 1,
        "done": False,
    }
    resp_b1 = client.post(f"/api/v1/internal/scans/{scan_id}/candidates", headers=headers, json=batch1)
    assert resp_b1.status_code == 200
    assert resp_b1.json()["status"] == "memindai"

    # 5. Kirim Batch 2 (done=True)
    batch2 = {
        "candidates": [
            {
                "url": "https://ojk.go.id/regulasi/pojk_baru_2026.pdf",
                "filename": "pojk_baru_2026.pdf",
                "size_bytes": 20480,
                "found_on_page": "https://ojk.go.id/regulasi",
                "depth": 1,
            }
        ],
        "pages_visited": 2,
        "done": True,
    }
    resp_b2 = client.post(f"/api/v1/internal/scans/{scan_id}/candidates", headers=headers, json=batch2)
    assert resp_b2.status_code == 200
    assert resp_b2.json()["status"] == "siap_dipilih"
    assert resp_b2.json()["candidates_total"] == 2
    assert resp_b2.json()["candidates_existing"] == 1
    assert resp_b2.json()["candidates_new"] == 1

    # 6. Verifikasi kandidat di endpoint publik
    resp_cands = client.get(f"/api/v1/scans/{scan_id}/candidates")
    assert resp_cands.status_code == 200
    cands = resp_cands.json()["items"]
    cand_old = next(c for c in cands if c["filename"] == "pojk_lama.pdf")
    cand_new = next(c for c in cands if c["filename"] == "pojk_baru_2026.pdf")

    assert cand_old["match_status"] == "sudah_ada"
    assert cand_old["match_document_id"] == doc_exist.id
    assert cand_old["selected"] is False

    assert cand_new["match_status"] == "baru"
    assert cand_new["selected"] is True
