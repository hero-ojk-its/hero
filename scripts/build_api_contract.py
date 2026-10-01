"""
scripts/build_api_contract.py
Pembangkit Kontrak API HERO Backend Fase 1 (docs/api/KONTRAK-API-FASE1.md),
snapshot OpenAPI (docs/api/openapi-fase1.json), dan koleksi REST Client (docs/api/hero-fase1.http).

Semua contoh respons JSON diuji dan ditangkap langsung dari eksekusi nyata TestClient
terhadap database pengujian (hero_test).
"""
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

# Pastikan root proyek masuk ke sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Pastikan UTF-8 di Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.config import settings
from app.database import get_db, seed_initial_categories
from app.main import app
from app.models import enums
from app.models.enums import (
    HasilTarik,
    JenisJobIngest,
    JenisKegagalan,
    JenisRujukan,
    JenisSumber,
    KlasifikasiAkses,
    MetodeEkstraksi,
    PeranDokumen,
    StatusJobIngest,
    StatusKandidat,
    StatusKeberlakuan,
    StatusPemrosesan,
    StatusPindai,
    StatusTindakLanjut,
    TujuanTarik,
)
from app.models.document import Document
from app.models.article import Article
from app.models.scraping_source import ScrapingSource
from app.models.scan_session import ScanSession
from app.models.scan_candidate import ScanCandidate
from app.models.ingest_failure import IngestFailure
from app.services.storage_service import get_storage_service
from app.services.scan_service import ScanService
from app.services.source_runner import SourceRunner

# Setup DB Test
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://hero_user:hero_password@127.0.0.1:5432/hero_test",
)
engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def make_pdf(text_content: str) -> bytes:
    content_bytes = text_content.encode("utf-8")
    length = len(content_bytes)
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(length).encode("ascii") + b" >>\nstream\n"
        + content_bytes +
        b"\nendstream\nendobj\n"
        b"xref\n0 5\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000206 00000 n \n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\n"
        b"startxref\n300\n%%EOF\n"
    )


def reset_test_db():
    """Mengosongkan seluruh tabel dan melakukan seeding kategori awal."""
    db = TestingSessionLocal()
    try:
        db.execute(text("""
            TRUNCATE TABLE 
                article_references,
                legal_references,
                articles,
                documents,
                ingest_failures,
                source_files,
                scan_candidates,
                scan_sessions,
                job_ingest,
                scraping_sources,
                audit_logs,
                users,
                categories
            RESTART IDENTITY CASCADE;
        """))
        db.commit()
        seed_initial_categories(db)
    finally:
        db.close()


def normalize_val(val: Any) -> Any:
    """Normalisasi tanggal dinamis dan suffix berkas agar idempoten pada setiap eksekusi."""
    if isinstance(val, str):
        # Match ISO timestamp pattern
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", val):
            return "2026-10-01T10:00:00Z"
        # Normalisasi suffix duplikasi berkas pada path
        if val.endswith(".pdf") and re.search(r"-\d+\.pdf$", val):
            return re.sub(r"-\d+\.pdf$", ".pdf", val)
        return val
    elif isinstance(val, dict):
        normalized_dict = {}
        for k, v in val.items():
            if k == "changed_fields" and isinstance(v, list):
                normalized_dict[k] = sorted(normalize_val(item) for item in v)
            else:
                normalized_dict[k] = normalize_val(v)
        return normalized_dict
    elif isinstance(val, list):
        return [normalize_val(item) for item in val]
    return val


def format_json_block(data: Any) -> str:
    norm = normalize_val(data)
    return "```json\n" + json.dumps(norm, indent=2, ensure_ascii=False) + "\n```"


def generate_enum_tables() -> str:
    """Membangkitkan tabel enum dari app/models/enums.py secara otomatis dengan penomoran urut."""
    enum_labels = {
        JenisSumber: {
            "title": "Jenis Sumber Dokumen (`JenisSumber`)",
            "key": "source_type",
            "labels": {
                JenisSumber.situs_web: ("Situs Web", "Situs eksternal (misal: JDIH ESDM) untuk perayapan berkas."),
                JenisSumber.folder_lokal: ("Folder Lokal", "Direktori penyimpanan lokal di peladen."),
                JenisSumber.onedrive_public: ("OneDrive Publik", "Tautan folder publik Microsoft OneDrive."),
            }
        },
        KlasifikasiAkses: {
            "title": "Klasifikasi Akses Dokumen (`KlasifikasiAkses`)",
            "key": "access_classification",
            "labels": {
                KlasifikasiAkses.publik: ("Publik", "Dapat diakses oleh publik tanpa batasan login."),
                KlasifikasiAkses.non_publik: ("Non-Publik", "Dokumen internal atau rahasia yang memerlukan autentikasi."),
            }
        },
        PeranDokumen: {
            "title": "Peran Dokumen (`PeranDokumen`)",
            "key": "document_role",
            "labels": {
                PeranDokumen.corpus_eksisting: ("Corpus Eksisting", "Dokumen regulasi induk/utama dalam basis pengetahuan."),
                PeranDokumen.draft_kajian: ("Draft Kajian", "Dokumen pendukung atau draft rancangan kajian regulasi."),
            }
        },
        StatusPindai: {
            "title": "Status Sesi Pemindaian (`StatusPindai`)",
            "key": "status",
            "labels": {
                StatusPindai.antrian: ("Dalam Antrian", "Sesi pemindaian baru dibuat dan menunggu worker."),
                StatusPindai.memindai: ("Sedang Memindai", "Crawler sedang merambati halaman dan mengumpulkan tautan."),
                StatusPindai.siap_dipilih: ("Siap Dipilih", "Pemindaian selesai, pengguna dapat memilih berkas."),
                StatusPindai.menarik: ("Sedang Menarik", "Worker sedang mengunduh berkas terpilih."),
                StatusPindai.selesai: ("Selesai", "Seluruh proses pemindaian dan penarikan telah rampung."),
                StatusPindai.gagal: ("Gagal", "Pemindaian atau penarikan mengalami kesalahan fatal."),
                StatusPindai.dibatalkan: ("Dibatalkan", "Sesi dibatalkan atas permintaan pengguna."),
            }
        },
        StatusKandidat: {
            "title": "Status Kecocokan Kandidat (`StatusKandidat`)",
            "key": "match_status",
            "labels": {
                StatusKandidat.baru: ("Baru", "Berkas belum pernah ada di sistem HERO (default dicentang)."),
                StatusKandidat.sudah_ada: ("Sudah Ada", "Berkas persis sama sudah ada di Knowledge Base (tidak dapat ditarik ulang)."),
                StatusKandidat.mungkin_ada: ("Mungkin Ada", "Nama berkas mirip atau hash belum pasti (memerlukan tinjauan)."),
            }
        },
        TujuanTarik: {
            "title": "Tujuan Penarikan Berkas (`TujuanTarik`)",
            "key": "destination",
            "labels": {
                TujuanTarik.knowledge_base: ("Knowledge Base", "Dimasukkan ke basis pengetahuan HERO dan diekstrak metadata/pasal."),
                TujuanTarik.unduh_folder: ("Unduh Folder (ZIP)", "Hanya diunduh sebagai berkas terkompresi ZIP tanpa diekstrak ke KB."),
            }
        },
        HasilTarik: {
            "title": "Hasil Penarikan Berkas (`HasilTarik`)",
            "key": "pull_outcome",
            "labels": {
                HasilTarik.berhasil: ("Berhasil", "Berkas berhasil diunduh dan disimpan."),
                HasilTarik.duplikat: ("Duplikat", "Berkas terdeteksi duplikat saat ingest."),
                HasilTarik.gagal: ("Gagal", "Gagal mengunduh atau validasi format gagal."),
                HasilTarik.diunduh: ("Diunduh", "Tersimpan di direktori ekspor untuk ZIP."),
            }
        },
        StatusPemrosesan: {
            "title": "Status Pemrosesan Dokumen KB (`StatusPemrosesan`)",
            "key": "processing_status",
            "labels": {
                StatusPemrosesan.diterima: ("Diterima", "Berkas PDF diterima di sistem, belum diproses."),
                StatusPemrosesan.diproses: ("Diproses", "Teks dan layout sedang diekstrak oleh worker."),
                StatusPemrosesan.perlu_koreksi: ("Perlu Koreksi", "Dokumen membutuhkan verifikasi/koreksi metadata manual oleh kurator."),
                StatusPemrosesan.terindeks: ("Terindeks", "Teks dan metadata telah terindeks untuk pencarian."),
                StatusPemrosesan.gagal: ("Gagal", "Gagal memproses dokumen pada salah satu tahapan pipeline."),
                StatusPemrosesan.ditolak: ("Ditolak", "Dokumen ditolak karena tidak memenuhi kriteria regulasi."),
            }
        },
        StatusKeberlakuan: {
            "title": "Status Keberlakuan Regulasi (`StatusKeberlakuan`)",
            "key": "status_keberlakuan",
            "labels": {
                StatusKeberlakuan.berlaku: ("Berlaku", "Peraturan sedang berlaku aktif."),
                StatusKeberlakuan.diubah: ("Diubah", "Sebagian ketentuan peraturan telah diubah."),
                StatusKeberlakuan.dicabut: ("Dicabut", "Peraturan telah dicabut seluruhnya oleh regulasi baru."),
                StatusKeberlakuan.tidak_diketahui: ("Tidak Diketahui", "Status keberlakuan belum dapat dipastikan."),
            }
        },
        JenisKegagalan: {
            "title": "Kategori Kegagalan Ingest (`JenisKegagalan`)",
            "key": "failure_type",
            "labels": {
                JenisKegagalan.format_tidak_didukung: ("Format Tidak Didukung", "Berkas rusak, terenkripsi, atau bukan PDF valid."),
                JenisKegagalan.duplikat: ("Duplikat", "Berkas terdeteksi sebagai duplikat."),
                JenisKegagalan.ekstraksi_gagal: ("Ekstraksi Gagal", "Gagal mengekstrak teks dari berkas."),
                JenisKegagalan.ocr_gagal: ("OCR Gagal", "Gagal menjalankan OCR pada berkas hasil pemindaian."),
                JenisKegagalan.metadata_tidak_lengkap: ("Metadata Tidak Lengkap", "Metadata wajib tidak berhasil diperoleh."),
                JenisKegagalan.sumber_tidak_dapat_diakses: ("Sumber Tidak Dapat Diakses", "Koneksi timeout, 404, atau 403 saat mengunduh sumber."),
                JenisKegagalan.kesalahan_internal: ("Kesalahan Internal", "Kesalahan internal lainnya pada sistem."),
            }
        },
        StatusTindakLanjut: {
            "title": "Status Tindak Lanjut Kegagalan (`StatusTindakLanjut`)",
            "key": "follow_up_status",
            "labels": {
                StatusTindakLanjut.belum_ditangani: ("Belum Ditangani", "Kegagalan baru tercatat dan belum ditangani."),
                StatusTindakLanjut.diproses_ulang: ("Diproses Ulang", "Proses retry sedang berjalan."),
                StatusTindakLanjut.diabaikan: ("Diabaikan", "Kurator memutuskan untuk mengabaikan kegagalan ini."),
            }
        },
        JenisJobIngest: {
            "title": "Jenis Tugas Ingest (`JenisJobIngest`)",
            "key": "job_type",
            "labels": {
                JenisJobIngest.scraping: ("Scraping / Pull", "Penarikan berkas dari pemindaian situs web."),
                JenisJobIngest.unggah_manual: ("Unggah Manual", "Unggah berkas langsung melalui antarmuka web."),
                JenisJobIngest.sinkron_folder: ("Sinkronisasi Folder", "Pemindaian folder lokal atau OneDrive."),
            }
        },
        StatusJobIngest: {
            "title": "Status Tugas Ingest (`StatusJobIngest`)",
            "key": "job_status",
            "labels": {
                StatusJobIngest.antrian: ("Antrian", "Tugas telah dijadwalkan."),
                StatusJobIngest.berjalan: ("Berjalan", "Tugas sedang aktif diproses."),
                StatusJobIngest.selesai: ("Selesai", "Tugas telah selesai dengan sukses."),
                StatusJobIngest.gagal: ("Gagal", "Tugas berhenti karena kesalahan fatal."),
            }
        },
    }

    md_out = []
    for idx, (enum_cls, info) in enumerate(enum_labels.items(), start=1):
        md_out.append(f"### 11.{idx} {info['title']}\n")
        md_out.append(f"Field respons/parameter: `{info['key']}`\n")
        md_out.append("| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |")
        md_out.append("|---|---|---|")
        for member in enum_cls:
            val = member.value
            label, desc = info["labels"].get(member, (val, "-"))
            md_out.append(f"| `{val}` | **{label}** | {desc} |")
        md_out.append("\n")

    return "\n".join(md_out)


def run_contract_builder():
    print("Memulai build API Contract HERO Backend...")
    reset_test_db()

    # Setup override SessionLocal & client
    app.dependency_overrides[get_db] = lambda: TestingSessionLocal()
    client = TestClient(app)

    # Dictionary penampung blok JSON nyata
    auto_blocks: Dict[str, str] = {}

    def capture(block_name: str, response: Any, expect: int = 200) -> None:
        """Helper wajib untuk menangkap JSON respons nyata dan memvalidasi status HTTP."""
        if response.status_code != expect:
            raise RuntimeError(
                f"[BUILD ERROR] Blok '{block_name}' gagal! "
                f"Diharapkan status code {expect}, tetapi menerima {response.status_code}. "
                f"Detail: {response.text}"
            )
        auto_blocks[block_name] = format_json_block(response.json())

    with patch.object(ScanService, "execute_scan", return_value=None), \
         patch.object(ScanService, "execute_pull", return_value=None), \
         patch.object(SourceRunner, "execute", return_value=None):

        # ==================== SEKSI 1: KONVENSI UMUM ====================
        # 404 App Error
        r_404 = client.get("/api/v1/documents/999999")
        capture("error_404_sample", r_404, expect=404)

        # 422 Validation Error
        r_422 = client.post("/api/v1/naming/preview", json={"naming_format": ["nama", "warna_invalid"]})
        capture("error_422_sample", r_422, expect=422)

        # ==================== SEKSI 2: TAMBAH SUMBER ====================
        # Tambah Sumber Situs Web (Contoh JDIH ESDM yang divalidasi)
        payload_src_web = {
            "name": "JDIH ESDM",
            "url": "https://jdih.esdm.go.id",
            "source_type": "situs_web",
            "crawl_depth": 2,
            "default_access_classification": "publik",
            "default_document_role": "corpus_eksisting",
            "default_naming_format": ["nomor", "nama", "tahun"],
            "default_naming_separator": " ",
            "is_active": True,
        }
        r_src_web = client.post("/api/v1/scraping-sources/", json=payload_src_web)
        capture("source_create_web_response", r_src_web, expect=201)
        src_web_id = r_src_web.json()["id"]
        auto_blocks["source_create_web_request"] = format_json_block(payload_src_web)

        # Tambah Sumber Folder Lokal
        allowed_roots = [r.strip() for r in settings.local_source_roots.split(";") if r.strip()]
        folder_path = allowed_roots[0] if allowed_roots else "C:\\Users\\IBUCOMP\\Downloads\\hero-backend\\sources"
        os.makedirs(folder_path, exist_ok=True)
        payload_src_local = {
            "name": "Folder Regulasi Lokal Perbankan",
            "url": folder_path,
            "source_type": "folder_lokal",
            "recursive": True,
            "default_access_classification": "non_publik",
            "default_document_role": "corpus_eksisting",
            "default_naming_format": ["nama", "tahun", "bidang"],
            "default_naming_separator": "_",
            "is_active": True,
        }
        r_src_local = client.post("/api/v1/scraping-sources/", json=payload_src_local)
        capture("source_create_local_response", r_src_local, expect=201)
        src_local_id = r_src_local.json()["id"]

        # List Sumber
        r_src_list = client.get("/api/v1/scraping-sources/")
        capture("source_list_response", r_src_list, expect=200)

        # ==================== SEKSI 3: SCAN & KANDIDAT ====================
        # Buat Sesi Scan
        payload_scan = {"source_id": src_web_id, "crawl_depth": 1, "max_pages": 10}
        r_scan_init = client.post("/api/v1/scans/", json=payload_scan)
        capture("scan_create_response", r_scan_init, expect=202)
        scan_id = r_scan_init.json().get("scan_id") or r_scan_init.json().get("id")
        auto_blocks["scan_create_request"] = format_json_block(payload_scan)

        # Seed Scan Candidate & Sesi siap_dipilih untuk menyimulasikan hasil perayapan crawler async
        db = TestingSessionLocal()
        try:
            scan_sess = db.query(ScanSession).filter(ScanSession.id == scan_id).first()
            scan_sess.status = StatusPindai.siap_dipilih
            scan_sess.pages_visited = 5
            scan_sess.candidates_total = 2

            import hashlib
            c1 = ScanCandidate(
                scan_id=scan_id,
                url="https://jdih.esdm.go.id/docs/Permen_ESDM_16_2026.pdf",
                url_hash=hashlib.sha256("https://jdih.esdm.go.id/docs/Permen_ESDM_16_2026.pdf".encode()).hexdigest(),
                filename="Permen_ESDM_16_2026.pdf",
                size_bytes=1048576,
                depth=1,
                match_status=StatusKandidat.baru,
                selected=True,
            )
            c2 = ScanCandidate(
                scan_id=scan_id,
                url="https://jdih.esdm.go.id/docs/Kepmen_05_2025.pdf",
                url_hash=hashlib.sha256("https://jdih.esdm.go.id/docs/Kepmen_05_2025.pdf".encode()).hexdigest(),
                filename="Kepmen_05_2025.pdf",
                size_bytes=524288,
                depth=1,
                match_status=StatusKandidat.sudah_ada,
                match_reason="url_sama",
                selected=False,
            )
            db.add_all([c1, c2])
            db.commit()
            c1_id = c1.id
        finally:
            db.close()

        # Detail Sesi Scan
        r_scan_detail = client.get(f"/api/v1/scans/{scan_id}")
        capture("scan_detail_response", r_scan_detail, expect=200)

        # Daftar Kandidat
        r_cand_list = client.get(f"/api/v1/scans/{scan_id}/candidates")
        capture("scan_candidates_response", r_cand_list, expect=200)

        # Update Selection (Centang)
        payload_select = {"action": "set", "candidate_ids": [c1_id], "selected": True}
        r_select = client.patch(f"/api/v1/scans/{scan_id}/selection", json=payload_select)
        capture("scan_selection_response", r_select, expect=200)

        # ==================== SEKSI 4: PILIH FORMAT NAMA ====================
        # GET /naming/components
        r_comp = client.get("/api/v1/naming/components")
        capture("naming_components_response", r_comp, expect=200)

        # POST /naming/preview (Default sample)
        payload_preview_default = {
            "naming_format": ["nama", "jenis", "tahun"],
            "naming_separator": " ",
        }
        r_prev_def = client.post("/api/v1/naming/preview", json=payload_preview_default)
        capture("naming_preview_default_response", r_prev_def, expect=200)

        # POST /naming/preview (Custom sample)
        payload_preview_custom = {
            "naming_format": ["nomor", "nama", "tahun", "bidang"],
            "naming_separator": "_",
            "sample": {
                "title": "Kesehatan Bank Perkreditan Rakyat",
                "regulation_number": "POJK 12/POJK.03/2025",
                "release_date": "2025-06-15",
                "bidang": "Perbankan",
            },
        }
        r_prev_cust = client.post("/api/v1/naming/preview", json=payload_preview_custom)
        capture("naming_preview_custom_response", r_prev_cust, expect=200)

        # ==================== SEKSI 5: TARIK HASIL SCAN ====================
        # POST /scans/{id}/pull (knowledge_base async)
        payload_pull_kb = {
            "destination": "knowledge_base",
            "naming_format": ["nama", "tahun", "bidang"],
            "naming_separator": "_",
        }
        r_pull_kb = client.post(f"/api/v1/scans/{scan_id}/pull", json=payload_pull_kb)
        capture("scan_pull_kb_response", r_pull_kb, expect=202)

        # POST /scans/{id}/pull (unduh_folder ZIP)
        # Ubah status sesi ke siap_dipilih kembali untuk contoh kedua
        db = TestingSessionLocal()
        try:
            scan_sess = db.query(ScanSession).filter(ScanSession.id == scan_id).first()
            scan_sess.status = StatusPindai.siap_dipilih
            db.commit()
        finally:
            db.close()

        payload_pull_zip = {
            "destination": "unduh_folder",
            "naming_format": ["nama", "tahun"],
            "naming_separator": " ",
        }
        r_pull_zip = client.post(f"/api/v1/scans/{scan_id}/pull", json=payload_pull_zip)
        capture("scan_pull_zip_response", r_pull_zip, expect=202)

        # ==================== SEKSI 6: UNGGAH MANUAL & SINKRONISASI ====================
        # POST /ingest/upload-pdf (Alur murni API)
        pdf_sample = make_pdf(
            "Peraturan Otoritas Jasa Keuangan tentang Penyelenggaraan Usaha Bank Umum. "
            "BAB I KETENTUAN UMUM Pasal 1: Dalam Peraturan Otoritas Jasa Keuangan ini yang dimaksud dengan Bank Umum adalah bank konvensional dan syariah. "
            "BAB II MODAL INTI Pasal 2: Modal inti minimum bagi Bank Umum ditetapkan sebesar Rp3.000.000.000.000 (tiga triliun rupiah)."
        )
        files = [("files", ("POJK 10 Tahun 2026 Bank Umum.pdf", pdf_sample, "application/pdf"))]
        form_data = {
            "access_classification": "publik",
            "document_role": "corpus_eksisting",
            "naming_format": "nama,jenis,tahun,bidang",
            "naming_separator": "_",
            "bidang": "Perbankan",
        }
        r_upload = client.post("/api/v1/ingest/upload-pdf", files=files, data=form_data)
        capture("upload_pdf_response", r_upload, expect=200)
        uploaded_doc_id = r_upload.json()["details"][0]["document_id"]

        # POST /scraping-sources/{id}/run
        payload_run_source = {
            "naming_format": ["nama", "tahun", "bidang"],
            "naming_separator": "-",
        }
        r_run_src = client.post(f"/api/v1/scraping-sources/{src_local_id}/run", json=payload_run_source)
        capture("source_run_response", r_run_src, expect=202)

        # GET /scraping-sources/{id}/files
        r_src_files = client.get(f"/api/v1/scraping-sources/{src_local_id}/files")
        capture("source_files_response", r_src_files, expect=200)

        # ==================== SEKSI 7 & 8: PIPELINE EKSTRAKSI, KNOWLEDGE BASE, DETAIL & TEKS ====================
        # Jalankan pipeline ekstraksi murni lewat HTTP API internal
        headers_internal = {"X-Internal-API-Key": settings.internal_api_key}
        payload_extraction = {
            "title": "Penyelenggaraan Usaha Bank Umum",
            "regulation_number": "POJK 10/POJK.03/2026",
            "regulation_type": "Peraturan Otoritas Jasa Keuangan",
            "release_date": "2026-03-15",
            "bidang": "Perbankan",
            "extraction_method": "teks_langsung",
            "full_text": (
                "Peraturan Otoritas Jasa Keuangan tentang Penyelenggaraan Usaha Bank Umum. "
                "BAB I KETENTUAN UMUM Pasal 1: Dalam Peraturan Otoritas Jasa Keuangan ini yang dimaksud dengan Bank Umum adalah bank konvensional dan syariah. "
                "BAB II MODAL INTI Pasal 2: Modal inti minimum bagi Bank Umum ditetapkan sebesar Rp3.000.000.000.000 (tiga triliun rupiah)."
            ),
            "confidence": {
                "title": 0.98,
                "regulation_number": 0.96,
                "regulation_type": 0.95,
                "release_date": 0.90,
                "bidang": 0.92,
            },
        }
        r_ext = client.patch(
            f"/api/v1/internal/documents/{uploaded_doc_id}/extraction?force=true",
            headers=headers_internal,
            json=payload_extraction,
        )
        if r_ext.status_code != 200:
            raise RuntimeError(f"Gagal ekstraksi dokumen {uploaded_doc_id}: {r_ext.text}")

        # Insert pasal secara murni lewat HTTP API internal
        payload_articles = {
            "articles": [
                {
                    "document_id": uploaded_doc_id,
                    "level": "pasal",
                    "chapter_title": "BAB I KETENTUAN UMUM",
                    "article_number": "Pasal 1",
                    "content_text": "Dalam Peraturan Otoritas Jasa Keuangan ini yang dimaksud dengan Bank Umum adalah bank yang melaksanakan kegiatan usaha secara konvensional dan atau berdasarkan prinsip syariah yang dalam kegiatannya memberikan jasa dalam lalu lintas pembayaran.",
                    "order_index": 1,
                },
                {
                    "document_id": uploaded_doc_id,
                    "level": "pasal",
                    "chapter_title": "BAB II MODAL INTI",
                    "article_number": "Pasal 2",
                    "content_text": "Modal inti minimum bagi Bank Umum ditetapkan paling sedikit sebesar Rp3.000.000.000.000 (tiga triliun rupiah) yang wajib dipenuhi oleh setiap entitas perbankan.",
                    "order_index": 2,
                },
            ]
        }
        r_bulk_art = client.post(
            "/api/v1/internal/articles",
            headers=headers_internal,
            json=payload_articles,
        )
        if r_bulk_art.status_code != 200:
            raise RuntimeError(f"Gagal bulk insert articles: {r_bulk_art.text}")

        # GET /documents/ (Daftar & Filter tanpa parameter q)
        r_docs_list = client.get("/api/v1/documents/?bidang=Perbankan&skip=0&limit=10")
        capture("documents_list_response", r_docs_list, expect=200)

        # GET /documents/ (Pencarian Full-Text Frasa & Highlight dengan parameter q)
        r_docs_search = client.get("/api/v1/documents/?q=modal+inti&bidang=Perbankan")
        capture("documents_search_response", r_docs_search, expect=200)

        # GET /documents/{id}
        r_doc_detail = client.get(f"/api/v1/documents/{uploaded_doc_id}")
        capture("document_detail_response", r_doc_detail, expect=200)

        # GET /documents/{id}/text
        r_doc_text = client.get(f"/api/v1/documents/{uploaded_doc_id}/text?offset=0&limit=20000")
        capture("document_text_response", r_doc_text, expect=200)

        # ==================== SEKSI 9: KOREKSI METADATA & ANTREAN GAGAL ====================
        # PATCH /documents/{id}/metadata
        payload_meta_update = {
            "title": "Penyelenggaraan Usaha Bank Umum Terkoreksi",
            "regulation_number": "POJK 10/POJK.03/2026",
            "bidang": "Perbankan",
            "status_keberlakuan": "berlaku",
        }
        r_patch_meta = client.patch(f"/api/v1/documents/{uploaded_doc_id}/metadata", json=payload_meta_update)
        capture("document_patch_metadata_response", r_patch_meta, expect=200)

        # Unggah PDF corrupt lewat API untuk membuat baris kegagalan nyata di tabel ingest_failures
        bad_pdf = [("files", ("Peraturan_Rusak_2026.pdf", b"INVALID_CORRUPT_HEADER_XYZ", "application/pdf"))]
        r_bad_upload = client.post(
            "/api/v1/ingest/upload-pdf",
            files=bad_pdf,
            data={"access_classification": "publik", "document_role": "corpus_eksisting"},
        )
        if r_bad_upload.status_code != 200:
            raise RuntimeError(f"Gagal membuat failure row via bad upload: {r_bad_upload.text}")

        # Buat failure retryable lewat pelaporan error ekstraksi via API internal
        pdf_retryable = make_pdf("Konten regulasi ekstraksi retryable.")
        r_retry_upload = client.post(
            "/api/v1/ingest/upload-pdf",
            files=[("files", ("Regulasi_Retry_2026.pdf", pdf_retryable, "application/pdf"))],
            data={"access_classification": "publik", "document_role": "corpus_eksisting"},
        )
        retry_doc_id = r_retry_upload.json()["details"][0]["document_id"]
        client.patch(
            f"/api/v1/internal/documents/{retry_doc_id}/extraction?force=true",
            headers=headers_internal,
            json={"error": {"code": "ocr_timeout", "message": "Proses OCR timeout saat ekstraksi berkas."}},
        )

        # GET /ingest/failures
        r_failures = client.get("/api/v1/ingest/failures")
        capture("failures_list_response", r_failures, expect=200)

        fail_items = r_failures.json().get("items", [])
        fail_id = fail_items[0]["id"] if fail_items else 1

        # Temukan failure yang retryable untuk contoh retry
        retryable_fail = next((f for f in fail_items if f.get("is_retryable")), fail_items[0] if fail_items else None)
        retryable_fail_id = retryable_fail["id"] if retryable_fail else fail_id

        # POST /ingest/failures/{id}/retry
        r_retry = client.post(f"/api/v1/ingest/failures/{retryable_fail_id}/retry")
        capture("failure_retry_response", r_retry, expect=200)

        # PATCH /ingest/failures/{id} (Abaikan)
        payload_ignore = {
            "follow_up_status": "diabaikan",
            "handling_note": "Abaikan berkas corrupt hasil pengujian.",
        }
        r_ignore = client.patch(f"/api/v1/ingest/failures/{fail_id}", json=payload_ignore)
        capture("failure_ignore_response", r_ignore, expect=200)

        # ==================== SEKSI 10: DASHBOARD ====================
        # GET /dashboard/summary
        r_dash = client.get("/api/v1/dashboard/summary")
        capture("dashboard_summary_response", r_dash, expect=200)

        # ==================== SEKSI 11: ENUM TABLES ====================
        auto_blocks["enum_tables"] = generate_enum_tables()

    # Generate Dokumen Kontrak Lengkap
    build_markdown_contract(auto_blocks)
    build_openapi_snapshot()
    build_http_requests()
    print("Pembuatan kontrak API selesai!")


def build_markdown_contract(blocks: Dict[str, str]):
    contract_path = BASE_DIR / "docs" / "api" / "KONTRAK-API-FASE1.md"
    max_upload_mb = settings.max_upload_bytes // (1024 * 1024)
    
    doc_content = f"""# KONTRAK API HERO BACKEND — FASE 1 (MVP)

> **Untuk Tim Frontend (Personil_D)**  
> **Status:** DRAF v0.9 — untuk disepakati Personil_D & Personil_E (rapat internal 1 Okt 2026)  
> **Basis Implementasi:** FastAPI · PostgreSQL 15.4 · SQLAlchemy 2.x  
> **Artefak Pendamping:**
> - [Koleksi Request Siap Eksekusi (REST Client / VS Code)](hero-fase1.http)
> - [Snapshot Skema OpenAPI JSON untuk Type Generator](openapi-fase1.json)
> - [Catatan Perubahan Frontend Step 9](frontend-changes-step9.md)

### Tabel Persetujuan

| Nama | Peran | Tanggal | Catatan |
|---|---|---|---|
| Personil_D | Frontend Lead | - | Belum ditandatangani |
| Personil_E | Backend Lead / PM | - | Belum ditandatangani |

---

## DAFTAR ISI

1. [Konvensi Umum & Pola Komunikasi](#1-konvensi-umum--pola-komunikasi)
2. [Alur 1: Tambah & Kelola Sumber Dokumen](#2-alur-1-tambah--kelola-sumber-dokumen)
3. [Alur 2: Pemindaian Situs Web, Seleksi & Centang Kandidat](#3-alur-2-pemindaian-situs-web-seleksi--centang-kandidat)
4. [Alur 3: Pemilihan Format Penamaan Berkas Dinamis](#4-alur-3-pemilihan-format-penamaan-berkas-dinamis)
5. [Alur 4: Penarikan Berkas (Knowledge Base & Unduh ZIP)](#5-alur-4-penarikan-berkas-knowledge-base--unduh-zip)
6. [Alur 5: Unggah Berkas Manual & Sinkronisasi Folder Lokal](#6-alur-5-unggah-berkas-manual--sinkronisasi-folder-lokal)
7. [Alur 6: Eksplorasi Knowledge Base & Pencarian Regulasi](#7-alur-6-eksplorasi-knowledge-base--pencarian-regulasi)
8. [Alur 7: Detail Dokumen, Pembaca Teks & Penampil PDF](#8-alur-7-detail-dokumen-pembaca-teks--penampil-pdf)
9. [Alur 8: Kurasi & Koreksi Metadata serta Antrean Penanganan Gagal](#9-alur-8-kurasi--koreksi-metadata-serta-antrean-penanganan-gagal)
10. [Alur 9: Dashboard Ringkasan Eksekutif](#10-alur-9-dashboard-ringkasan-eksekutif)
11. [Tabel Referensi Enum & Label Bahasa Indonesia](#11-tabel-referensi-enum--label-bahasa-indonesia)
12. [Daftar Kode Galat HTTP & Penanganan di UI](#12-daftar-kode-galat-http--penanganan-di-ui)
13. [Catatan & Pertanyaan untuk Frontend](#13-catatan--pertanyaan-untuk-frontend)

---

## 1. KONVENSI UMUM & POLA KOMUNIKASI

### 1.1 Base URL & Prefix
- **Lokal (Pengembangan):** `http://localhost:8000` (atau `NEXT_PUBLIC_API_URL`)
- **Prefix Endpoint:** Semua rute API diawali dengan `/api/v1`.

### 1.2 Format Waktu & Paginasi
- **Format Tanggal:** ISO 8601 UTC (contoh: `2026-10-01T10:00:00Z`).
- **Paginasi Standar:** Menggunakan query parameter `skip` (offset, default `0`) dan `limit` (ukuran halaman, default `20` atau `50`).
- **Struktur Respons Daftar:**
  ```json
  {{
    "total": 100,
    "items": [ ... ],
    "skip": 0,
    "limit": 20
  }}
  ```

### 1.3 Dua Bentuk Format Galat (Error Response)
Frontend wajib menangani **2 format error**:

1. **Galat Logika Bisnis / HTTP 4xx (dari Backend Application):**
   ```json
   {{
     "detail": "Pesan galat dalam bahasa Indonesia yang ramah pengguna."
   }}
   ```
   *Contoh Riil 404 (Dokumen tidak ditemukan):*
<!-- AUTO:error_404_sample -->
{blocks['error_404_sample']}
<!-- /AUTO:error_404_sample -->

2. **Galat Validasi Schema (HTTP 422 dari FastAPI/Pydantic):**
   ```json
   {{
     "detail": [
       {{
         "loc": ["body", "naming_format", 1],
         "msg": "Komponen naming_format tidak valid: 'warna_invalid'. Komponen yang didukung: 'nama', 'nomor', 'tahun', 'jenis', 'bidang'.",
         "type": "value_error"
       }}
     ]
   }}
   ```
   *Contoh Riil 422:*
<!-- AUTO:error_422_sample -->
{blocks['error_422_sample']}
<!-- /AUTO:error_422_sample -->

### 1.4 Status Autentikasi & CORS
- **`AUTH_ENABLED=false` (Default Fase 1):** Header `Authorization: Bearer <token>` **tidak wajib** disertakan pada seluruh endpoint publik/operasional.
- **CORS:** Backend mengizinkan origin yang didefinisikan pada `CORS_ORIGINS` di `.env` (misal: `http://localhost:3000,http://127.0.0.1:3000`).

### 1.5 Pola Operasi Panjang (Long-Running Operations)
Operasi penarikan berkas (`/pull`) dan pemindaian situs (`/scans/`) menggunakan pola polling:
1. Frontend mengirim request dengan query `wait=false` (default).
2. Backend merespons langsung dengan status `202 Accepted` (atau `200 OK`) berisi `job_id` atau `scan_id`.
3. Frontend melakukan polling `GET /api/v1/scans/{{id}}` atau `GET /api/v1/ingest/jobs/{{job_id}}` setiap 2 detik hingga mencapai **status final**: `selesai`, `gagal`, atau `dibatalkan`.

---

## 2. ALUR 1: TAMBAH & KELOLA SUMBER DOKUMEN

Mendukung pendaftaran situs web dan folder lokal sebagai sumber regulasi.

> [!NOTE]
> Contoh URL menggunakan `https://jdih.esdm.go.id` yang telah divalidasi dengan crawler standar (`SimpleHttpCrawler`). Dukungan untuk situs berbasis SPA (seperti JDIH OJK) dan integrasi Microsoft OneDrive sedang dikerjakan pada isu terpisah (#88, #30).

### 2.1 Tambah Sumber Situs Web
- **Method & Path:** `POST /api/v1/scraping-sources/`
- **Request Body:**
<!-- AUTO:source_create_web_request -->
{blocks['source_create_web_request']}
<!-- /AUTO:source_create_web_request -->
- **Respons (201 Created):**
<!-- AUTO:source_create_web_response -->
{blocks['source_create_web_response']}
<!-- /AUTO:source_create_web_response -->

### 2.2 Tambah Sumber Folder Lokal
- **Method & Path:** `POST /api/v1/scraping-sources/`
- **Respons (201 Created):**
<!-- AUTO:source_create_local_response -->
{blocks['source_create_local_response']}
<!-- /AUTO:source_create_local_response -->

### 2.3 Daftar Sumber Dokumen
- **Method & Path:** `GET /api/v1/scraping-sources/`
- **Respons (200 OK):**
<!-- AUTO:source_list_response -->
{blocks['source_list_response']}
<!-- /AUTO:source_list_response -->

---

## 3. ALUR 2: PEMINDAIAN SITUS WEB, SELEKSI & CENTANG KANDIDAT

### 3.1 Memulai Sesi Pemindaian
- **Method & Path:** `POST /api/v1/scans/`
- **Request Body:**
<!-- AUTO:scan_create_request -->
{blocks['scan_create_request']}
<!-- /AUTO:scan_create_request -->
- **Respons (202 Accepted):**
<!-- AUTO:scan_create_response -->
{blocks['scan_create_response']}
<!-- /AUTO:scan_create_response -->

### 3.2 Memeriksa Detail & Status Sesi Pemindaian
- **Method & Path:** `GET /api/v1/scans/{{scan_id}}`
- **Respons (200 OK):**
<!-- AUTO:scan_detail_response -->
{blocks['scan_detail_response']}
<!-- /AUTO:scan_detail_response -->

### 3.3 Mengambil Daftar Kandidat Berkas
- **Method & Path:** `GET /api/v1/scans/{{scan_id}}/candidates`
- **Query Params:** `match_status` (`baru`, `sudah_ada`, `mungkin_ada`), `selected` (`true`, `false`).
- **Respons (200 OK):**
<!-- AUTO:scan_candidates_response -->
{blocks['scan_candidates_response']}
<!-- /AUTO:scan_candidates_response -->

### 3.4 Mengubah Pilihan Centang Berkas (Selection)
- **Method & Path:** `PATCH /api/v1/scans/{{scan_id}}/selection`
- **Aksi yang Didukung:**
  - `select_all`: Centang semua berkas berstatus `baru`.
  - `select_none`: Hapus semua centangan.
  - `set`: Atur centang berkas tertentu berdasarkan daftar `candidate_ids`.
- **Respons (200 OK):**
<!-- AUTO:scan_selection_response -->
{blocks['scan_selection_response']}
<!-- /AUTO:scan_selection_response -->

---

## 4. ALUR 3: PEMILIHAN FORMAT PENAMAAN BERKAS DINAMIS

Mendukung personalisasi nama berkas sesuai urutan tombol di UI (`nama`, `tahun`, `jenis`, `bidang`, `nomor`).

### 4.1 Mendapatkan Komponen & Aturan Penamaan
- **Method & Path:** `GET /api/v1/naming/components`
- **Respons (200 OK):**
<!-- AUTO:naming_components_response -->
{blocks['naming_components_response']}
<!-- /AUTO:naming_components_response -->

### 4.2 Pratinjau Live Penamaan Berkas
- **Method & Path:** `POST /api/v1/naming/preview`
- **Respons Contoh Bawaan (Default Sample):**
<!-- AUTO:naming_preview_default_response -->
{blocks['naming_preview_default_response']}
<!-- /AUTO:naming_preview_default_response -->
- **Respons Contoh Kustom (Custom Sample):**
<!-- AUTO:naming_preview_custom_response -->
{blocks['naming_preview_custom_response']}
<!-- /AUTO:naming_preview_custom_response -->

---

## 5. ALUR 4: PENARIKAN BERKAS (KNOWLEDGE BASE & UNDUH ZIP)

### 5.1 Tarik ke Knowledge Base (Asinkron)
- **Method & Path:** `POST /api/v1/scans/{{scan_id}}/pull`
- **Respons (202 Accepted):**
<!-- AUTO:scan_pull_kb_response -->
{blocks['scan_pull_kb_response']}
<!-- /AUTO:scan_pull_kb_response -->

### 5.2 Tarik ke Folder Unduhan (Arsip ZIP)
- **Method & Path:** `POST /api/v1/scans/{{scan_id}}/pull`
- **Respons (202 Accepted):**
<!-- AUTO:scan_pull_zip_response -->
{blocks['scan_pull_zip_response']}
<!-- /AUTO:scan_pull_zip_response -->
- **Unduh ZIP:** `GET /api/v1/scans/{{scan_id}}/download` setelah status sesi `selesai`.

---

## 6. ALUR 5: UNGGAH BERKAS MANUAL & SINKRONISASI FOLDER LOKAL

### 6.1 Unggah Berkas PDF (Multipart Form Data)
- **Method & Path:** `POST /api/v1/ingest/upload-pdf`
- **Form Data:**
  - `files`: File PDF tunggal atau jamak.
  - `access_classification`: `publik` | `non_publik` (Wajib).
  - `document_role`: `corpus_eksisting` | `draft_kajian` (Wajib).
  - `naming_format`: String dipisah koma (contoh: `"nama,jenis,tahun,bidang"`).
  - `naming_separator`: `" "` | `"_"` | `"-"`.
  - `bidang`: Sektor regulasi (contoh: `"Perbankan"`).
- **Respons (200 OK):**
<!-- AUTO:upload_pdf_response -->
{blocks['upload_pdf_response']}
<!-- /AUTO:upload_pdf_response -->

### 6.2 Sinkronisasi Folder Lokal
- **Method & Path:** `POST /api/v1/scraping-sources/{{source_id}}/run`
- **Respons (202 Accepted):**
<!-- AUTO:source_run_response -->
{blocks['source_run_response']}
<!-- /AUTO:source_run_response -->

### 6.3 Daftar Berkas Sumber Folder
- **Method & Path:** `GET /api/v1/scraping-sources/{{source_id}}/files`
- **Respons (200 OK):**
<!-- AUTO:source_files_response -->
{blocks['source_files_response']}
<!-- /AUTO:source_files_response -->

---

## 7. ALUR 6: EKSPLORASI KNOWLEDGE BASE & PENCARIAN REGULASI

Pencarian regulasi pada MVP Fase 1 menggunakan **PostgreSQL Full-Text Search** berbasis `tsvector` dan `tsquery` berbobot (`title` [A], `regulation_number` [A], `articles.content_text` [B], `full_text` [C]) serta pencocokan nomor regulasi via indeks trigram GIN. Belum ada pencarian berbasis model vektor atau embedding pada Fase 1.

### 7.1 Daftar, Filter & Pencarian Dokumen KB
- **Method & Path:** `GET /api/v1/documents/`
- **Query Params:**
  - `q` (string, opsional): Kata kunci / frasa teks hukum (contoh: `modal inti bank umum`). Field `highlight` pada respons otomatis terisi cuplikan teks dengan tag `<mark>…</mark>` apabila parameter `q` diisi.
  - `mode` (string, opsional): Mode full-text PostgreSQL: `phrase` (default, frasa berurutan) | `all` (semua kata) | `web` (boolean websearch).
  - `regulation_number` (string, opsional): Pencocokan nomor regulasi via trigram (contoh: `POJK 10/POJK.03/2026`).
  - `regulation_type` (string, opsional): Filter jenis regulasi (contoh: `POJK`, `SEOJK`, `UU`, `PP`).
  - `category_id` (integer, opsional): Filter ID kategori folder KB.
  - `include_subcategories` (boolean, opsional): Sertakan subkategori jika `category_id` diisi (default `true`).
  - `status_keberlakuan` (string / array, opsional): Filter status keberlakuan: `berlaku`, `dicabut`, `diubah`, `tidak_diketahui`.
  - `document_role` (string, opsional): Filter peran dokumen: `corpus_eksisting`, `draft_kajian`.
  - `access_classification` (string, opsional): Filter klasifikasi akses: `publik`, `non_publik`.
  - `processing_status` (string, opsional): Filter status pemrosesan dokumen: `diterima`, `diproses`, `perlu_koreksi`, `terindeks`, `gagal`, `ditolak`.
  - `date_from` (string/date ISO `YYYY-MM-DD`, opsional): Filter tanggal rilis awal inklusif.
  - `date_to` (string/date ISO `YYYY-MM-DD`, opsional): Filter tanggal rilis akhir inklusif.
  - `year` (integer, opsional): Filter tahun rilis regulasi (contoh: `2026`).
  - `bidang` (string, opsional): Filter sektor regulasi (contoh: `Perbankan`, `Pasar Modal`, `BMKS`, `IKNB`).
  - `sort` (string, opsional): Pengurutan hasil pencarian: `relevance` (default bila `q` terisi), `release_date_desc` (default bila `q` kosong), `release_date_asc`, `created_desc`, `title_asc`.
  - `skip` (integer, opsional): Offset paginasi (default `0`, min `0`).
  - `limit` (integer, opsional): Batas dokumen per halaman (default `20`, min `1`, max `100`).

#### Contoh A: Daftar & Filter Dokumen (Tanpa Parameter `q`)
*Request:* `GET /api/v1/documents/?bidang=Perbankan&skip=0&limit=10`
- **Respons (200 OK):**
<!-- AUTO:documents_list_response -->
{blocks['documents_list_response']}
<!-- /AUTO:documents_list_response -->

#### Contoh B: Pencarian Full-Text & Highlight (Dengan Parameter `q`)
*Request:* `GET /api/v1/documents/?q=modal+inti&bidang=Perbankan`
- **Respons (200 OK):**
<!-- AUTO:documents_search_response -->
{blocks['documents_search_response']}
<!-- /AUTO:documents_search_response -->

---

## 8. ALUR 7: DETAIL DOKUMEN, PEMBACA TEKS & PENAMPIL PDF

### 8.1 Detail Lengkap Dokumen
- **Method & Path:** `GET /api/v1/documents/{{document_id}}`
- **Respons (200 OK):**
<!-- AUTO:document_detail_response -->
{blocks['document_detail_response']}
<!-- /AUTO:document_detail_response -->

### 8.2 Membaca Teks Mentah Dokumen
- **Method & Path:** `GET /api/v1/documents/{{document_id}}/text`
- **Query Params:** `offset` (karakter awal, default `0`), `limit` (panjang karakter, default `20000`, maks `100000`).
- **Respons (200 OK):**
<!-- AUTO:document_text_response -->
{blocks['document_text_response']}
<!-- /AUTO:document_text_response -->

### 8.3 Menampilkan Berkas PDF Asli di Browser
- **Method & Path:** `GET /api/v1/documents/{{document_id}}/pdf`
- **Header Respons:**
  - `Content-Type: application/pdf`
  - `Content-Disposition: inline; filename="Nama_Standar.pdf"`
- **Integrasi Frontend:**
  - Dapat langsung dimuat dalam tag `<iframe>`, `<embed>`, `<object>`, atau library PDF viewer seperti `pdf.js` / `@react-pdf-viewer`.
  - Contoh tag HTML:
    ```html
    <iframe src="http://localhost:8000/api/v1/documents/1/pdf" width="100%" height="800px" />
    ```
  - **Perilaku 403 Forbidden:** Jika dokumen berstatus `non_publik` dan autentikasi belum aktif, endpoint mengembalikan galat 403 dengan pesan `"Dokumen non-publik hanya dapat dibuka setelah login diaktifkan."`.

---

## 9. ALUR 8: KURASI & KOREKSI METADATA SERTA ANTREAN PENANGANAN GAGAL

### 9.1 Koreksi Metadata Dokumen
- **Method & Path:** `PATCH /api/v1/documents/{{document_id}}/metadata`
- **Body:** Mendukung pembaruan `title`, `regulation_number`, `regulation_type`, `release_date`, `bidang`, `category_id`, `status_keberlakuan`, `access_classification`, `document_role`.
- **Respons (200 OK):**
<!-- AUTO:document_patch_metadata_response -->
{blocks['document_patch_metadata_response']}
<!-- /AUTO:document_patch_metadata_response -->

### 9.2 Daftar Antrean Gagal (Ingest Failures)
- **Method & Path:** `GET /api/v1/ingest/failures`
- **Query Params:** `job_id`, `failure_type`, `follow_up_status` (`belum_ditangani`, `diproses_ulang`, `diabaikan`, `all`), `include_duplicates` (`false`), `skip` (`0`), `limit` (`50`).
- **Respons (200 OK):**
<!-- AUTO:failures_list_response -->
{blocks['failures_list_response']}
<!-- /AUTO:failures_list_response -->

### 9.3 Mencoba Ulang (Retry) Berkas Gagal
- **Method & Path:** `POST /api/v1/ingest/failures/{{failure_id}}/retry`
- **Respons (200 OK):**
<!-- AUTO:failure_retry_response -->
{blocks['failure_retry_response']}
<!-- /AUTO:failure_retry_response -->

### 9.4 Mengabaikan (Ignore) Berkas Gagal
- **Method & Path:** `PATCH /api/v1/ingest/failures/{{failure_id}}`
- **Body:** `{{"follow_up_status": "diabaikan", "handling_note": "Catatan alasan pengabaian"}}`
- **Respons (200 OK):**
<!-- AUTO:failure_ignore_response -->
{blocks['failure_ignore_response']}
<!-- /AUTO:failure_ignore_response -->

---

## 10. ALUR 9: DASHBOARD RINGKASAN EKSEKUTIF

### 10.1 Ringkasan Metrik Dashboard
- **Method & Path:** `GET /api/v1/dashboard/summary`
- **Respons (200 OK):**
<!-- AUTO:dashboard_summary_response -->
{blocks['dashboard_summary_response']}
<!-- /AUTO:dashboard_summary_response -->

---

## 11. TABEL REFERENSI ENUM & LABEL BAHASA INDONESIA

<!-- AUTO:enum_tables -->
{blocks['enum_tables']}
<!-- /AUTO:enum_tables -->

---

## 12. DAFTAR KODE GALAT HTTP & PENANGANAN DI UI

| Kode HTTP | Makna Teknis | Penyebab Umum | Aksi UI yang Disarankan |
|---|---|---|---|
| **400 Bad Request** | Permintaan tidak valid | URL sumber tidak valid, folder di luar akar yang diizinkan | Tampilkan banner galat dengan pesan dari respons. |
| **403 Forbidden** | Akses ditolak | Mengakses PDF non-publik saat mode proteksi aktif | Tampilkan dialog izin akses atau peringatan login. |
| **404 Not Found** | Data tidak ditemukan | ID dokumen, scan, atau sumber tidak ditemukan | Arahkan pengguna kembali ke halaman daftar. |
| **409 Conflict** | Konflik status | Sesi sedang berjalan atau mencoba retry job aktif | Berikan notifikasi bahwa proses sedang berjalan di latar belakang. |
| **413 Payload Too Large** | Berkas melebihi batas | Ukuran unggah PDF melebihi batas (default {max_upload_mb} MB) | Peringatkan pengguna untuk mengunggah berkas lebih kecil. |
| **422 Unprocessable** | Validasi skema gagal | Komponen format nama salah, field wajib kosong | Sorot field formulir yang bersangkutan dengan pesan spesifik. |
| **503 Service Unavailable** | Layanan database/AI sibuk | Koneksi database terputus atau komponen ML offline | Tampilkan pesan coba lagi beberapa saat. |

---

## 13. CATATAN & PERTANYAAN UNTUK FRONTEND

1. **Komponen Penamaan Berulang:** Backend mengizinkan tombol komponen penamaan yang sama diklik lebih dari sekali (misal: `["tahun", "nama", "tahun"]`). Apakah UI telah mendukung representasi chip/badge yang dapat diurutkan secara drag-and-drop?
2. **Karakter Pemisah Penamaan:** Pemisah default adalah spasi `" "`. Pilihan lain adalah `"_"` dan `"-"`. Jika pengguna tidak memilih pemisah, backend otomatis menggunakan spasi.
3. **Pemberitahuan Status Asinkron:** Disarankan agar frontend menggunakan library seperti React Query / SWR dengan konfigurasi `refetchInterval: 2000` saat sesi berada dalam status `memindai` atau `menarik`.
"""
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(doc_content, encoding="utf-8")
    print(f"Kontrak API berhasil ditulis ke: {contract_path}")


def build_openapi_snapshot():
    openapi_path = BASE_DIR / "docs" / "api" / "openapi-fase1.json"
    schema = app.openapi()
    openapi_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Snapshot OpenAPI berhasil ditulis ke: {openapi_path}")


def build_http_requests():
    http_path = BASE_DIR / "docs" / "api" / "hero-fase1.http"
    http_content = """### HERO Backend Fase 1 - REST Client Collection
### Jalankan request di bawah secara berurutan menggunakan ekstensi REST Client VS Code.

@baseUrl = http://127.0.0.1:8000/api/v1

### 1. Health Check
GET {{baseUrl}}/health
Accept: application/json

### 2. Naming: Get Available Components
GET {{baseUrl}}/naming/components
Accept: application/json

### 3. Naming: Live Preview
POST {{baseUrl}}/naming/preview
Content-Type: application/json

{
  "naming_format": ["nomor", "nama", "tahun", "bidang"],
  "naming_separator": "_",
  "sample": {
    "title": "Kesehatan Bank Perkreditan Rakyat",
    "regulation_number": "POJK 12/POJK.03/2025",
    "release_date": "2025-06-15",
    "bidang": "Perbankan"
  }
}

### 4. Scraping Source: Create Web Source
POST {{baseUrl}}/scraping-sources/
Content-Type: application/json

{
  "name": "JDIH ESDM",
  "url": "https://jdih.esdm.go.id",
  "source_type": "situs_web",
  "crawl_depth": 2,
  "default_access_classification": "publik",
  "default_document_role": "corpus_eksisting",
  "default_naming_format": ["nomor", "nama", "tahun"],
  "default_naming_separator": " ",
  "is_active": true
}

### 5. Scraping Source: List All Sources
GET {{baseUrl}}/scraping-sources/
Accept: application/json

### 6. Scan: Start Website Scan
POST {{baseUrl}}/scans/
Content-Type: application/json

{
  "source_id": 1,
  "crawl_depth": 1,
  "max_pages": 10
}

### 7. Scan: Get Detail Sesi Scan (Ganti ID sesuai hasil di atas)
GET {{baseUrl}}/scans/1
Accept: application/json

### 8. Scan: List Candidates
GET {{baseUrl}}/scans/1/candidates?match_status=baru
Accept: application/json

### 9. Scan: Pull Candidates to Knowledge Base
POST {{baseUrl}}/scans/1/pull
Content-Type: application/json

{
  "destination": "knowledge_base",
  "naming_format": ["nama", "tahun", "bidang"],
  "naming_separator": "_"
}

### 10. Documents: List & Filter KB
GET {{baseUrl}}/documents/?bidang=Perbankan&skip=0&limit=10
Accept: application/json

### 11. Documents: Search Full-Text & Highlight
GET {{baseUrl}}/documents/?q=modal+inti&bidang=Perbankan
Accept: application/json

### 12. Documents: Get Detail (Ganti ID)
GET {{baseUrl}}/documents/1
Accept: application/json

### 13. Documents: Read Text (Ganti ID)
GET {{baseUrl}}/documents/1/text?offset=0&limit=20000
Accept: application/json

### 14. Documents: Open PDF Inline (Ganti ID)
GET {{baseUrl}}/documents/1/pdf
Accept: application/pdf

### 15. Documents: Patch Metadata Koreksi
PATCH {{baseUrl}}/documents/1/metadata
Content-Type: application/json

{
  "title": "Penyelenggaraan Usaha Bank Umum Terkoreksi",
  "regulation_number": "POJK 10/POJK.03/2026",
  "bidang": "Perbankan",
  "status_keberlakuan": "berlaku"
}

### 16. Ingest: List Failures Queue
GET {{baseUrl}}/ingest/failures
Accept: application/json

### 17. Ingest: Retry Failure (Ganti ID)
POST {{baseUrl}}/ingest/failures/1/retry
Accept: application/json

### 18. Ingest: Ignore Failure (Ganti ID)
PATCH {{baseUrl}}/ingest/failures/1
Content-Type: application/json

{
  "follow_up_status": "diabaikan",
  "handling_note": "Abaikan berkas corrupt hasil pengujian."
}

### 19. Dashboard: Summary
GET {{baseUrl}}/dashboard/summary
Accept: application/json
"""
    http_path.write_text(http_content, encoding="utf-8")
    print(f"REST Client collection berhasil ditulis ke: {http_path}")


if __name__ == "__main__":
    run_contract_builder()
