"""
tests/test_local_folder.py
Pengujian lengkap integrasi Sumber Folder Lokal — L01 s/d L16 (US-16, FR-SCR-05).
"""
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
import pytest

from app.config import settings
from app.models.document import Document
from app.models.enums import JenisJobIngest, StatusJobIngest
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.models.scraping_source import ScrapingSource
from app.models.source_file import SourceFile
from app.services.source_runner import recover_stuck_folder_jobs
from tests.conftest import make_pdf


def test_l01_sync_folder_basic_and_filtering(client, db_session, tmp_path: Path, monkeypatch):
    """L01: Folder berisi 3 PDF valid + 1 .docx + 1 ~$temp.pdf + subfolder berisi 1 PDF -> 4 success, docx/~$ diabaikan."""
    root_dir = tmp_path / "sources_l01"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    # Buat file-file di folder
    (root_dir / "pojk_01.pdf").write_bytes(make_pdf("Konten POJK 01/POJK.03/2023"))
    (root_dir / "pojk_02.pdf").write_bytes(make_pdf("Konten POJK 02/POJK.03/2023"))
    (root_dir / "pojk_03.pdf").write_bytes(make_pdf("Konten POJK 03/POJK.03/2023"))
    (root_dir / "catatan.docx").write_text("Ini berkas docx yang harus diabaikan", encoding="utf-8")
    (root_dir / "~$temp.pdf").write_bytes(b"temp file office")

    sub_dir = root_dir / "subfolder"
    sub_dir.mkdir(parents=True, exist_ok=True)
    (sub_dir / "seojk_sub.pdf").write_bytes(make_pdf("Konten SEOJK Subfolder 2023"))

    # Daftarkan sumber
    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "Folder Uji L01",
            "url": str(root_dir),
            "source_type": "folder_lokal",
            "recursive": True,
        },
    )
    assert resp_create.status_code == 201
    source_id = resp_create.json()["id"]

    # Jalankan dengan wait=true
    resp_run = client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")
    assert resp_run.status_code == 200, resp_run.text
    run_data = resp_run.json()
    assert run_data["job_status"] == "selesai"
    assert run_data["total_found"] == 4
    assert run_data["success_count"] == 4
    assert run_data["duplicate_count"] == 0
    assert run_data["skipped_count"] == 0
    assert run_data["failed_count"] == 0

    # Verifikasi dokumen di database
    docs = db_session.query(Document).all()
    assert len(docs) == 4
    for doc in docs:
        assert doc.source_url.startswith(f"folder://{source_id}/")
        assert doc.access_classification.value == "non_publik"
        assert doc.document_role.value == "corpus_eksisting"

    # Verifikasi status sumber
    source = db_session.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
    assert source.last_run_status == "selesai"
    assert "Ditemukan: 4" in source.last_run_message
    assert "Berhasil: 4" in source.last_run_message


def test_l02_rerun_unchanged_skips_content_read(client, tmp_path: Path, monkeypatch):
    """L02: Jalankan ulang tanpa perubahan -> skipped_count=4, success=0, duplicate=0, tidak ada pembacaan isi berkas."""
    root_dir = tmp_path / "sources_l02"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    for i in range(4):
        (root_dir / f"doc_{i}.pdf").write_bytes(make_pdf(f"Konten Unik L02 Dokumen {i}"))

    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder L02", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    source_id = resp_create.json()["id"]

    # Run 1
    resp1 = client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")
    assert resp1.status_code == 200
    assert resp1.json()["success_count"] == 4

    # Monkeypatch Path.read_bytes untuk memverifikasi tidak ada pemanggilan
    read_count = {"count": 0}
    orig_read_bytes = Path.read_bytes

    def mock_read_bytes(self, *args, **kwargs):
        read_count["count"] += 1
        return orig_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", mock_read_bytes)

    # Run 2
    resp2 = client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["skipped_count"] == 4
    assert data2["success_count"] == 0
    assert data2["duplicate_count"] == 0
    assert data2["failed_count"] == 0
    assert read_count["count"] == 0, "read_bytes tidak boleh dipanggil untuk file yang skipped_unchanged"


def test_l03_add_new_pdf_rerun(client, tmp_path: Path, monkeypatch):
    """L03: Tambah 1 PDF baru, jalankan ulang -> Hanya 1 success, 4 skipped."""
    root_dir = tmp_path / "sources_l03"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    for i in range(4):
        (root_dir / f"doc_{i}.pdf").write_bytes(make_pdf(f"Konten L03 Dokumen {i}"))

    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder L03", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    source_id = resp_create.json()["id"]

    # Run 1
    client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")

    # Tambah 1 file baru
    (root_dir / "doc_new.pdf").write_bytes(make_pdf("Konten L03 Dokumen Baru ke-5"))

    # Run 2
    resp2 = client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["total_found"] == 5
    assert data2["success_count"] == 1
    assert data2["skipped_count"] == 4


def test_l04_modify_pdf_content(client, tmp_path: Path, monkeypatch):
    """L04: Ubah isi salah satu PDF (mtime/size berubah) -> Diproses ulang -> success (hash baru)."""
    root_dir = tmp_path / "sources_l04"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    f1 = root_dir / "doc_1.pdf"
    f1.write_bytes(make_pdf("Konten Versi Awal L04"))

    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder L04", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    source_id = resp_create.json()["id"]

    # Run 1
    client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")

    # Modifikasi file (pastikan mtime/size berubah)
    import time
    time.sleep(0.05)
    f1.write_bytes(make_pdf("Konten Versi Baru Yang Diubah Total L04-Revised"))

    # Run 2
    resp2 = client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["success_count"] == 1
    assert data2["skipped_count"] == 0


def test_l05_duplicate_pdf_in_folder(client, db_session, tmp_path: Path, monkeypatch):
    """L05: Salin PDF yang sama ke nama lain di folder -> duplicate dengan duplicate_of_document_id benar."""
    root_dir = tmp_path / "sources_l05"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    pdf_bytes = make_pdf("Konten Kembar Identik L05")
    (root_dir / "asli.pdf").write_bytes(pdf_bytes)
    (root_dir / "salinan.pdf").write_bytes(pdf_bytes)

    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder L05", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    source_id = resp_create.json()["id"]

    resp_run = client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")
    assert resp_run.status_code == 200
    data = resp_run.json()
    assert data["total_found"] == 2
    assert data["success_count"] == 1
    assert data["duplicate_count"] == 1

    # Verifikasi source_files
    sf_list = db_session.query(SourceFile).filter(SourceFile.source_id == source_id).all()
    assert len(sf_list) == 2
    outcomes = {sf.relative_path: sf.last_outcome for sf in sf_list}
    assert outcomes["asli.pdf"] == "success"
    assert outcomes["salinan.pdf"] == "duplicate"


def test_l06_fake_pdf_failed(client, db_session, tmp_path: Path, monkeypatch):
    """L06: PDF palsu (isi teks biasa, ekstensi .pdf) -> failed format_tidak_didukung di ingest_failures."""
    root_dir = tmp_path / "sources_l06"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    (root_dir / "palsu.pdf").write_text("Ini bukan PDF valid, hanya teks biasa", encoding="utf-8")

    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder L06", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    source_id = resp_create.json()["id"]

    resp_run = client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")
    assert resp_run.status_code == 200
    data = resp_run.json()
    assert data["failed_count"] == 1
    assert data["success_count"] == 0

    fail = db_session.query(IngestFailure).filter(IngestFailure.job_id == data["job_id"]).first()
    assert fail is not None
    assert fail.failure_type.value == "format_tidak_didukung"


def test_l07_recursive_false(client, tmp_path: Path, monkeypatch):
    """L07: recursive=false -> Subfolder diabaikan."""
    root_dir = tmp_path / "sources_l07"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    (root_dir / "root_doc.pdf").write_bytes(make_pdf("Doc di Root L07"))
    sub_dir = root_dir / "sub"
    sub_dir.mkdir(parents=True, exist_ok=True)
    (sub_dir / "sub_doc.pdf").write_bytes(make_pdf("Doc di Sub L07"))

    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={
            "name": "Folder Non-Recursive L07",
            "url": str(root_dir),
            "source_type": "folder_lokal",
            "recursive": False,
        },
    )
    source_id = resp_create.json()["id"]

    resp_run = client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")
    assert resp_run.status_code == 200
    data = resp_run.json()
    assert data["total_found"] == 1
    assert data["success_count"] == 1


def test_l08_folder_deleted_after_registration(client, db_session, tmp_path: Path, monkeypatch):
    """L08: Folder dihapus setelah didaftarkan -> run -> Job gagal, sumber_tidak_dapat_diakses, no unhandled exception."""
    root_dir = tmp_path / "sources_l08"
    root_dir.mkdir(parents=True, exist_ok=True)
    target_folder = root_dir / "to_be_deleted"
    target_folder.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder Dihapus", "url": str(target_folder), "source_type": "folder_lokal"},
    )
    source_id = resp_create.json()["id"]

    # Hapus folder
    target_folder.rmdir()

    resp_run = client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")
    assert resp_run.status_code == 200
    data = resp_run.json()
    assert data["job_status"] == "gagal"

    source = db_session.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
    assert source.last_run_status == "gagal"
    assert "tidak ditemukan" in source.last_run_message or "tidak dapat diakses" in source.last_run_message

    fail = db_session.query(IngestFailure).filter(IngestFailure.job_id == data["job_id"]).first()
    assert fail is not None
    assert fail.failure_type.value == "sumber_tidak_dapat_diakses"


def test_l09_symlink_outside_root(client, tmp_path: Path, monkeypatch):
    """L09: Symlink ke luar akar di dalam folder -> Tidak diikuti."""
    root_dir = tmp_path / "sources_l09"
    root_dir.mkdir(parents=True, exist_ok=True)
    outside_dir = tmp_path / "outside_l09"
    outside_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    (root_dir / "doc_valid.pdf").write_bytes(make_pdf("Doc Valid L09"))
    (outside_dir / "secret.pdf").write_bytes(make_pdf("Secret Doc Outside L09"))

    symlink_path = root_dir / "symlink_outside"
    try:
        symlink_path.symlink_to(outside_dir, target_is_directory=True)
    except (OSError, NotImplementedError) as err:
        pytest.skip(f"OS/Hak akses tidak mengizinkan pembuatan symlink ({err})")

    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder Symlink L09", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    source_id = resp_create.json()["id"]

    resp_run = client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")
    assert resp_run.status_code == 200
    data = resp_run.json()
    # Hanya doc_valid.pdf yang diproses, secret.pdf di luar symlink tidak diikuti
    assert data["total_found"] == 1
    assert data["success_count"] == 1


def test_l10_run_while_job_already_running(client, db_session, tmp_path: Path, monkeypatch):
    """L10: Run ketika job sumber yang sama masih berjalan -> 409 berisi job_id."""
    root_dir = tmp_path / "sources_l10"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder L10", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    source_id = resp_create.json()["id"]

    # Buat dummy running job di database
    running_job = JobIngest(
        job_type=JenisJobIngest.sinkron_folder,
        source_id=source_id,
        status=StatusJobIngest.berjalan,
    )
    db_session.add(running_job)
    db_session.commit()

    resp_run = client.post(f"/api/v1/scraping-sources/{source_id}/run")
    assert resp_run.status_code == 409
    detail = resp_run.json()["detail"]
    assert str(running_job.id) in str(detail)


def test_l11_reject_invalid_source_types_and_inactive(client, tmp_path: Path, monkeypatch):
    """L11: Run sumber situs_web (409) / onedrive_public (422) / nonaktif (409)."""
    root_dir = tmp_path / "sources_l11"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    # 1. situs_web -> 409
    resp_web = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Web Source L11", "url": "https://jdih.ojk.go.id", "source_type": "situs_web"},
    )
    web_id = resp_web.json()["id"]
    r1 = client.post(f"/api/v1/scraping-sources/{web_id}/run")
    assert r1.status_code == 409
    assert "alur pindai (scan)" in r1.json()["detail"]

    # 2. onedrive_public -> 422
    resp_one = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "OneDrive L11", "url": "https://1drv.ms/f/s!test1", "source_type": "onedrive_public"},
    )
    one_id = resp_one.json()["id"]
    r2 = client.post(f"/api/v1/scraping-sources/{one_id}/run")
    assert r2.status_code == 422
    assert "Konektor OneDrive langsung belum tersedia" in r2.json()["detail"]

    # 3. nonaktif -> 409
    resp_inact = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Inactive Folder", "url": str(root_dir), "source_type": "folder_lokal", "is_active": False},
    )
    inact_id = resp_inact.json()["id"]
    r3 = client.post(f"/api/v1/scraping-sources/{inact_id}/run")
    assert r3.status_code == 409
    assert "nonaktif" in r3.json()["detail"]


def test_l12_run_async_background(client, db_session, tmp_path: Path, monkeypatch):
    """L12: run tanpa wait -> 202; setelah BackgroundTasks selesai, job selesai."""
    root_dir = tmp_path / "sources_l12"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    (root_dir / "async_doc.pdf").write_bytes(make_pdf("Doc Async L12"))

    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder Async L12", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    source_id = resp_create.json()["id"]

    # run async (wait=false) -> TestClient mengeksekusi BackgroundTasks sebelum mereturn
    resp_run = client.post(f"/api/v1/scraping-sources/{source_id}/run")
    assert resp_run.status_code == 202
    job_id = resp_run.json()["job_id"]

    # Cek status job di database
    job = db_session.query(JobIngest).filter(JobIngest.id == job_id).first()
    assert job is not None
    assert job.status == StatusJobIngest.selesai
    assert job.success_count == 1


def test_l13_recover_stuck_folder_jobs(client, db_session, tmp_path: Path, monkeypatch):
    """L13: Job berjalan > 60 menit lalu fungsi pemulihan startup dipanggil -> Job gagal dengan pesan pemulihan."""
    root_dir = tmp_path / "sources_l13"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder L13", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    source_id = resp_create.json()["id"]

    # Buat job yang seolah-olah macet 90 menit lalu
    old_time = datetime.now(timezone.utc) - timedelta(minutes=90)
    stuck_job = JobIngest(
        job_type=JenisJobIngest.sinkron_folder,
        source_id=source_id,
        status=StatusJobIngest.berjalan,
        started_at=old_time,
    )
    db_session.add(stuck_job)
    db_session.flush()

    source = db_session.query(ScrapingSource).filter(ScrapingSource.id == source_id).first()
    source.last_job_id = stuck_job.id
    source.last_run_status = "berjalan"
    db_session.commit()

    # Jalankan pemulihan startup
    recovered_count = recover_stuck_folder_jobs(db_session)
    assert recovered_count == 1

    db_session.refresh(stuck_job)
    db_session.refresh(source)
    assert stuck_job.status == StatusJobIngest.gagal
    assert source.last_run_status == "gagal"
    assert "Dihentikan karena server dimulai ulang." in source.last_run_message


def test_l14_progress_keys_and_files_endpoint(client, tmp_path: Path, monkeypatch):
    """L14: GET /ingest/jobs/{id} & GET /scraping-sources/{id}/files -> Key progres benar; daftar berkas benar."""
    root_dir = tmp_path / "sources_l14"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    (root_dir / "pojk_14.pdf").write_bytes(make_pdf("Konten POJK L14"))

    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder L14", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    source_id = resp_create.json()["id"]

    resp_run = client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")
    job_id = resp_run.json()["job_id"]

    # Cek detail job
    resp_job = client.get(f"/api/v1/ingest/jobs/{job_id}")
    assert resp_job.status_code == 200
    job_data = resp_job.json()
    assert job_data["total_found"] == 1
    assert job_data["processed_count"] == 1
    assert job_data["skipped_count"] == 0
    assert job_data["progress_percent"] == 100.0
    assert job_data["source"]["id"] == source_id
    assert job_data["source"]["source_type"] == "folder_lokal"

    # Cek endpoint files
    resp_files = client.get(f"/api/v1/scraping-sources/{source_id}/files")
    assert resp_files.status_code == 200
    files_data = resp_files.json()
    assert files_data["total"] == 1
    item = files_data["items"][0]
    assert item["relative_path"] == "pojk_14.pdf"
    assert item["last_outcome"] == "success"
    assert item["document_id"] is not None


def test_l15_delete_source_cascades_source_files(client, db_session, tmp_path: Path, monkeypatch):
    """L15: Hapus sumber -> source_files ikut terhapus (cascade); dokumen & job tetap ada."""
    root_dir = tmp_path / "sources_l15"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))

    (root_dir / "doc_15.pdf").write_bytes(make_pdf("Konten Doc L15"))

    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder L15", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    source_id = resp_create.json()["id"]

    resp_run = client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")
    job_id = resp_run.json()["job_id"]

    # Pastikan source_files ada sebelum dihapus
    sf_count = db_session.query(SourceFile).filter(SourceFile.source_id == source_id).count()
    assert sf_count == 1

    # Hapus sumber
    resp_del = client.delete(f"/api/v1/scraping-sources/{source_id}")
    assert resp_del.status_code == 200

    # Verifikasi source_files terhapus (cascade)
    sf_count_after = db_session.query(SourceFile).filter(SourceFile.source_id == source_id).count()
    assert sf_count_after == 0

    # Dokumen dan Job tetap ada
    job = db_session.query(JobIngest).filter(JobIngest.id == job_id).first()
    assert job is not None
    docs_count = db_session.query(Document).count()
    assert docs_count == 1


def test_l16_max_files_per_run_truncation(client, tmp_path: Path, monkeypatch):
    """L16: max_files_per_run=2 dengan 3 PDF -> Hanya 2 diproses; pesan pemotongan di last_run_message."""
    root_dir = tmp_path / "sources_l16"
    root_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "local_source_roots", str(root_dir))
    monkeypatch.setattr(settings, "local_source_max_files_per_run", 2)

    for i in range(3):
        (root_dir / f"doc_{i}.pdf").write_bytes(make_pdf(f"Konten Doc {i} L16"))

    resp_create = client.post(
        "/api/v1/scraping-sources/",
        json={"name": "Folder L16", "url": str(root_dir), "source_type": "folder_lokal"},
    )
    source_id = resp_create.json()["id"]

    resp_run = client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")
    assert resp_run.status_code == 200
    data = resp_run.json()
    assert data["total_found"] == 2
    assert data["success_count"] == 2
    assert "dipotong ke 2 berkas" in data["last_run_message"]
