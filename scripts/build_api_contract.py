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
    """Normalisasi tanggal dinamis agar idempoten pada setiap eksekusi."""
    if isinstance(val, str):
        # Match ISO timestamp pattern
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", val):
            return "2026-10-01T10:00:00Z"
        return val
    elif isinstance(val, dict):
        return {k: normalize_val(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [normalize_val(item) for item in val]
    return val


def format_json_block(data: Any) -> str:
    norm = normalize_val(data)
    return "```json\n" + json.dumps(norm, indent=2, ensure_ascii=False) + "\n```"


def generate_enum_tables() -> str:
    """Membangkitkan tabel enum dari app/models/enums.py secara otomatis."""
    enum_labels = {
        JenisSumber: {
            "title": "Jenis Sumber Dokumen (`JenisSumber`)",
            "key": "source_type",
            "labels": {
                JenisSumber.situs_web: ("Situs Web", "Situs eksternal (misal: JDIH OJK) untuk perayapan berkas."),
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
    for enum_cls, info in enum_labels.items():
        md_out.append(f"### 11.{len(md_out)+1} {info['title']}\n")
        md_out.append(f"Field respons/parameter: `{info['key']}`\n")
        md_out.append("| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |")
        md_out.append("|---|---|---|")
        for member in enum_cls:
            val = member.value
            label, desc = info["labels"].get(member, (val, "-"))
            md_out.append(f"| `{val}` | **{label}** | {desc} |")
        md_out.append("\n")

    return "\n".join(md_out)


from unittest.mock import patch
from app.services.scan_service import ScanService
from app.services.source_runner import SourceRunner


def run_contract_builder():
    print("Memulai build API Contract HERO Backend...")
    reset_test_db()

    # Setup override SessionLocal & client
    app.dependency_overrides[get_db] = lambda: TestingSessionLocal()
    client = TestClient(app)

    db = TestingSessionLocal()

    # Dictionary penampung blok JSON nyata
    auto_blocks: Dict[str, str] = {}

    with patch.object(ScanService, "execute_scan", return_value=None), \
         patch.object(ScanService, "execute_pull", return_value=None), \
         patch.object(SourceRunner, "execute", return_value=None):

        # ==================== SEKSI 1: KONVENSI UMUM ====================
        # 404 App Error
        r_404 = client.get("/api/v1/documents/999999")
        auto_blocks["error_404_sample"] = format_json_block(r_404.json())

        # 422 Validation Error
        r_422 = client.post("/api/v1/naming/preview", json={"naming_format": ["nama", "warna_invalid"]})
        auto_blocks["error_422_sample"] = format_json_block(r_422.json())

        # ==================== SEKSI 2: TAMBAH SUMBER ====================
        # Tambah Sumber Situs Web
        payload_src_web = {
            "name": "JDIH OJK Pusat",
            "url": "https://jdih.ojk.go.id",
            "source_type": "situs_web",
            "crawl_depth": 2,
            "default_access_classification": "publik",
            "default_document_role": "corpus_eksisting",
            "default_naming_format": ["nomor", "nama", "tahun"],
            "default_naming_separator": " ",
            "is_active": True,
        }
        r_src_web = client.post("/api/v1/scraping-sources/", json=payload_src_web)
        auto_blocks["source_create_web_request"] = format_json_block(payload_src_web)
        auto_blocks["source_create_web_response"] = format_json_block(r_src_web.json())
        src_web_id = r_src_web.json()["id"]

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
        auto_blocks["source_create_local_response"] = format_json_block(r_src_local.json())
        src_local_id = r_src_local.json()["id"]

        # List Sumber
        r_src_list = client.get("/api/v1/scraping-sources/")
        auto_blocks["source_list_response"] = format_json_block(r_src_list.json())

        # ==================== SEKSI 3: SCAN & KANDIDAT ====================
        # Buat Sesi Scan
        payload_scan = {"source_id": src_web_id, "crawl_depth": 1, "max_pages": 10}
        r_scan_init = client.post("/api/v1/scans/", json=payload_scan)
        scan_id = r_scan_init.json()["scan_id"]
        auto_blocks["scan_create_request"] = format_json_block(payload_scan)
        auto_blocks["scan_create_response"] = format_json_block(r_scan_init.json())

        # Seed Scan Candidate & Sesi siap_dipilih untuk keperluan dokumentasi
        scan_sess = db.query(ScanSession).filter(ScanSession.id == scan_id).first()
        scan_sess.status = StatusPindai.siap_dipilih
        scan_sess.pages_visited = 5
        scan_sess.candidates_total = 2

        import hashlib
        c1 = ScanCandidate(
            scan_id=scan_id,
            url="https://jdih.ojk.go.id/docs/POJK_16_2026.pdf",
            url_hash=hashlib.sha256("https://jdih.ojk.go.id/docs/POJK_16_2026.pdf".encode()).hexdigest(),
            filename="POJK_16_2026.pdf",
            size_bytes=1048576,
            depth=1,
            match_status=StatusKandidat.baru,
            selected=True,
        )
        c2 = ScanCandidate(
            scan_id=scan_id,
            url="https://jdih.ojk.go.id/docs/SEOJK_05_2025.pdf",
            url_hash=hashlib.sha256("https://jdih.ojk.go.id/docs/SEOJK_05_2025.pdf".encode()).hexdigest(),
            filename="SEOJK_05_2025.pdf",
            size_bytes=524288,
            depth=1,
            match_status=StatusKandidat.sudah_ada,
            match_reason="url_sama",
            selected=False,
        )
        db.add_all([c1, c2])
        db.commit()

        # Detail Sesi Scan
        r_scan_detail = client.get(f"/api/v1/scans/{scan_id}")
        auto_blocks["scan_detail_response"] = format_json_block(r_scan_detail.json())

        # Daftar Kandidat
        r_cand_list = client.get(f"/api/v1/scans/{scan_id}/candidates")
        auto_blocks["scan_candidates_response"] = format_json_block(r_cand_list.json())

        # Update Selection (Centang)
        payload_select = {"action": "set", "candidate_ids": [c1.id], "selected": True}
        r_select = client.patch(f"/api/v1/scans/{scan_id}/selection", json=payload_select)
        auto_blocks["scan_selection_response"] = format_json_block(r_select.json())

        # ==================== SEKSI 4: PILIH FORMAT NAMA ====================
        # GET /naming/components
        r_comp = client.get("/api/v1/naming/components")
        auto_blocks["naming_components_response"] = format_json_block(r_comp.json())

        # POST /naming/preview (Default sample)
        payload_preview_default = {
            "naming_format": ["nama", "jenis", "tahun"],
            "naming_separator": " ",
        }
        r_prev_def = client.post("/api/v1/naming/preview", json=payload_preview_default)
        auto_blocks["naming_preview_default_response"] = format_json_block(r_prev_def.json())

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
        auto_blocks["naming_preview_custom_response"] = format_json_block(r_prev_cust.json())

        # ==================== SEKSI 5: TARIK HASIL SCAN ====================
        # POST /scans/{id}/pull (knowledge_base async)
        payload_pull_kb = {
            "destination": "knowledge_base",
            "naming_format": ["nama", "tahun", "bidang"],
            "naming_separator": "_",
        }
        r_pull_kb = client.post(f"/api/v1/scans/{scan_id}/pull", json=payload_pull_kb)
        auto_blocks["scan_pull_kb_response"] = format_json_block(r_pull_kb.json())

        # POST /scans/{id}/pull (unduh_folder ZIP)
        # Ubah status sesi ke siap_dipilih kembali untuk contoh kedua
        scan_sess = db.query(ScanSession).filter(ScanSession.id == scan_id).first()
        scan_sess.status = StatusPindai.siap_dipilih
        db.commit()

        payload_pull_zip = {
            "destination": "unduh_folder",
            "naming_format": ["nama", "tahun"],
            "naming_separator": " ",
        }
        r_pull_zip = client.post(f"/api/v1/scans/{scan_id}/pull", json=payload_pull_zip)
        auto_blocks["scan_pull_zip_response"] = format_json_block(r_pull_zip.json())

        # ==================== SEKSI 6: UNGGAH MANUAL & SINKRONISASI ====================
        # POST /ingest/upload-pdf
        pdf_sample = make_pdf("Penyelenggaraan Usaha Bank Umum Konvensional dan Syariah di Indonesia.")
        files = [("files", ("POJK 10 Tahun 2026 Bank Umum.pdf", pdf_sample, "application/pdf"))]
        form_data = {
            "access_classification": "publik",
            "document_role": "corpus_eksisting",
            "naming_format": "nama,jenis,tahun,bidang",
            "naming_separator": "_",
            "bidang": "Perbankan",
        }
        r_upload = client.post("/api/v1/ingest/upload-pdf", files=files, data=form_data)
        auto_blocks["upload_pdf_response"] = format_json_block(r_upload.json())
        uploaded_doc_id = r_upload.json()["items"][0]["document_id"] if r_upload.json().get("items") else 1

        # POST /scraping-sources/{id}/run
        payload_run_source = {
            "naming_format": ["nama", "tahun", "bidang"],
            "naming_separator": "-",
        }
        r_run_src = client.post(f"/api/v1/scraping-sources/{src_local_id}/run", json=payload_run_source)
        auto_blocks["source_run_response"] = format_json_block(r_run_src.json())

        # GET /scraping-sources/{id}/files
        r_src_files = client.get(f"/api/v1/scraping-sources/{src_local_id}/files")
        auto_blocks["source_files_response"] = format_json_block(r_src_files.json())

        # ==================== SEKSI 7: KNOWLEDGE BASE & PENCARIAN ====================
        # Seed artikel dan teks dokumen untuk pencarian yang kaya
        doc_row = db.query(Document).filter(Document.id == uploaded_doc_id).first()
        if doc_row:
            doc_row.title = "Penyelenggaraan Usaha Bank Umum"
            doc_row.regulation_number = "POJK 10/2026"
            doc_row.regulation_type = "Peraturan Otoritas Jasa Keuangan"
            doc_row.release_date = datetime(2026, 3, 15, tzinfo=timezone.utc)
            doc_row.status_keberlakuan = StatusKeberlakuan.berlaku
            doc_row.processing_status = StatusPemrosesan.terindeks
            doc_row.bidang = "Perbankan"
            doc_row.category_id = 1
            art1 = Article(
                document_id=doc_row.id,
                article_number="Pasal 1",
                chapter_title="BAB I KETENTUAN UMUM",
                content_text="Dalam Peraturan Otoritas Jasa Keuangan ini yang dimaksud dengan Bank Umum adalah...",
                order_index=1,
            )
            art2 = Article(
                document_id=doc_row.id,
                article_number="Pasal 2",
                chapter_title="BAB II MODAL INTI",
                content_text="Modal inti minimum bagi Bank Umum ditetapkan sebesar Rp3.000.000.000.000.",
                order_index=2,
            )
            db.add_all([art1, art2])
            db.commit()

        # GET /documents/ (Daftar & Filter)
        r_docs_list = client.get("/api/v1/documents/?bidang=Perbankan&skip=0&limit=10")
        auto_blocks["documents_list_response"] = format_json_block(r_docs_list.json())

        # GET /documents/search (Pencarian frasa / pasal)
        r_docs_search = client.get("/api/v1/documents/search?q=modal+inti&bidang=Perbankan&highlight=true")
        auto_blocks["documents_search_response"] = format_json_block(r_docs_search.json())

        # ==================== SEKSI 8: DETAIL DOKUMEN, TEKS & PDF ====================
        # GET /documents/{id}
        r_doc_detail = client.get(f"/api/v1/documents/{uploaded_doc_id}")
        auto_blocks["document_detail_response"] = format_json_block(r_doc_detail.json())

        # GET /documents/{id}/text
        r_doc_text = client.get(f"/api/v1/documents/{uploaded_doc_id}/text")
        auto_blocks["document_text_response"] = format_json_block(r_doc_text.json())

        # ==================== SEKSI 9: KOREKSI METADATA & ANTRIAN GAGAL ====================
        # PATCH /documents/{id}/metadata
        payload_meta_update = {
            "title": "Penyelenggaraan Usaha Bank Umum Terkoreksi",
            "regulation_number": "POJK 10/POJK.03/2026",
            "bidang": "Perbankan",
            "category_id": 1,
            "status_keberlakuan": "berlaku",
        }
        r_patch_meta = client.patch(f"/api/v1/documents/{uploaded_doc_id}/metadata", json=payload_meta_update)
        auto_blocks["document_patch_metadata_response"] = format_json_block(r_patch_meta.json())

        # Seed failure record
        fail_row = IngestFailure(
            job_id=1,
            failure_type=JenisKegagalan.format_tidak_didukung,
            reason_code="corrupt_pdf_header",
            original_filename="Peraturan_Rusak_2026.pdf",
            source_url="https://jdih.ojk.go.id/docs/Peraturan_Rusak_2026.pdf",
            message="Format header berkas PDF tidak valid.",
            is_retryable=True,
            follow_up_status=StatusTindakLanjut.belum_ditangani,
        )
        db.add(fail_row)
        db.commit()

        # GET /failures/
        r_failures = client.get("/api/v1/failures/")
        auto_blocks["failures_list_response"] = format_json_block(r_failures.json())

        # POST /failures/{id}/retry
        r_retry = client.post(f"/api/v1/failures/{fail_row.id}/retry")
        auto_blocks["failure_retry_response"] = format_json_block(r_retry.json())

        # POST /failures/{id}/ignore
        r_ignore = client.post(f"/api/v1/failures/{fail_row.id}/ignore")
        auto_blocks["failure_ignore_response"] = format_json_block(r_ignore.json())

        # ==================== SEKSI 10: DASHBOARD ====================
        # GET /dashboard/summary
        r_dash = client.get("/api/v1/dashboard/summary")
        auto_blocks["dashboard_summary_response"] = format_json_block(r_dash.json())

        # ==================== SEKSI 11: ENUM TABLES ====================
        auto_blocks["enum_tables"] = generate_enum_tables()

    # Generate Dokumen Kontrak Lengkap
    build_markdown_contract(auto_blocks)
    build_openapi_snapshot()
    build_http_requests()
    print("Pembuatan kontrak API selesai!")


def build_markdown_contract(blocks: Dict[str, str]):
    contract_path = BASE_DIR / "docs" / "api" / "KONTRAK-API-FASE1.md"
    
    doc_content = f"""# KONTRAK API HERO BACKEND — FASE 1 (MVP)

> **Untuk Tim Frontend (Personil_D)**  
> **Status:** Resmi Disepakati (Step 9 / Issue #91 AI-T12 & #90 US-20c)  
> **Basis Implementasi:** FastAPI · PostgreSQL 15.4 · SQLAlchemy 2.x  
> **Artefak Pendamping:**
> - [Koleksi Request Siap Eksekusi (REST Client / VS Code)](file:///docs/api/hero-fase1.http)
> - [Snapshot Skema OpenAPI JSON untuk Type Generator](file:///docs/api/openapi-fase1.json)
> - [Catatan Perubahan Frontend Step 9](file:///docs/api/frontend-changes-step9.md)

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
9. [Alur 8: Kurasi & Koreksi Metadata serta Penanganan Gagal](#9-alur-8-kurasi--koreksi-metadata-serta-penanganan-gagal)
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

1. **Galat Logika Bisnis Aplikasi (400, 403, 404, 409, 503):**
   `detail` berupa **string pesan tunggal**:
<!-- AUTO:error_404_sample -->
{blocks['error_404_sample']}
<!-- /AUTO:error_404_sample -->

2. **Galat Validasi Input Schema / Pydantic (422 Unprocessable Entity):**
   `detail` berupa **array of objects**:
<!-- AUTO:error_422_sample -->
{blocks['error_422_sample']}
<!-- /AUTO:error_422_sample -->

> **Saran UI:**  
> Buat interceptor response pada Axios / Fetch:  
> `const errorMsg = typeof err.response.data.detail === 'string' ? err.response.data.detail : err.response.data.detail.map(e => e.msg).join(', ');`

### 1.4 Status Autentikasi (Fase 1)
- Pada Fase 1, `AUTH_ENABLED=false`. Frontend **tidak perlu mengirimkan header Authorization/Bearer token**.
- Seluruh endpoint publik dapat diakses langsung.

### 1.5 CORS (Cross-Origin Resource Sharing)
- Backend mengizinkan origin frontend: `http://localhost:3000` dan `http://127.0.0.1:3000`.
- Jika pengujian frontend berjalan di port lain, pastikan menambahkan port tersebut di konfigurasi `.env` (`CORS_ORIGINS`).

### 1.6 Pola Operasi Panjang (Asynchronous Polling)
Operasi berat seperti pemindaian situs web (`POST /scans/`), penarikan dokumen (`POST /scans/{{id}}/pull`), dan sinkronisasi folder (`POST /scraping-sources/{{id}}/run`):
1. **Default (`wait=false`):** Backend merespons langsung dengan status **`202 Accepted`** berisi `scan_id` atau `job_id` dan status `"antrian"`.
2. **Polling UI:** Frontend melakukan polling GET (`GET /api/v1/scans/{{id}}` atau `GET /api/v1/jobs/{{id}}`) tiap **2 detik**.
3. **Status Final:** Polling berhenti saat status mencapai salah satu nilai final:
   - `selesai` (sukses)
   - `gagal` (terjadi kesalahan, lihat `error_message`)
   - `dibatalkan` (dibatalkan oleh pengguna)

---

## 2. ALUR 1: TAMBAH & KELOLA SUMBER DOKUMEN

### 2.1 Menambah Sumber Situs Web (JDIH OJK)
- **Method & Path:** `POST /api/v1/scraping-sources/`
- **Request Body:**
<!-- AUTO:source_create_web_request -->
{blocks['source_create_web_request']}
<!-- /AUTO:source_create_web_request -->
- **Respons (201 Created):**
<!-- AUTO:source_create_web_response -->
{blocks['source_create_web_response']}
<!-- /AUTO:source_create_web_response -->

### 2.2 Menambah Sumber Folder Lokal
- **Method & Path:** `POST /api/v1/scraping-sources/`
- **Respons (201 Created):**
<!-- AUTO:source_create_local_response -->
{blocks['source_create_local_response']}
<!-- /AUTO:source_create_local_response -->

### 2.3 Daftar Semua Sumber
- **Method & Path:** `GET /api/v1/scraping-sources/`
- **Query Params:** `is_active` (boolean, opsional), `source_type` (JenisSumber, opsional).
- **Respons (200 OK):**
<!-- AUTO:source_list_response -->
{blocks['source_list_response']}
<!-- /AUTO:source_list_response -->

---

## 3. ALUR 2: PEMINDAIAN SITUS WEB, SELEKSI & CENTANG KANDIDAT

### 3.1 Memulai Pemindaian Situs
- **Method & Path:** `POST /api/v1/scans/`
- **Query Param:** `wait=false` (default) → 202 Accepted, `wait=true` → 200 OK setelah selesai.
- **Request Body:**
<!-- AUTO:scan_create_request -->
{blocks['scan_create_request']}
<!-- /AUTO:scan_create_request -->
- **Respons (202 Accepted):**
<!-- AUTO:scan_create_response -->
{blocks['scan_create_response']}
<!-- /AUTO:scan_create_response -->

### 3.2 Detail Status Sesi Pemindaian
- **Method & Path:** `GET /api/v1/scans/{{scan_id}}`
- **Respons (200 OK):**
<!-- AUTO:scan_detail_response -->
{blocks['scan_detail_response']}
<!-- /AUTO:scan_detail_response -->

### 3.3 Menampilkan Daftar Kandidat PDF
- **Method & Path:** `GET /api/v1/scans/{{scan_id}}/candidates`
- **Query Params:** `match_status` (`baru` | `sudah_ada` | `mungkin_ada`), `selected` (boolean), `pull_outcome`, `q` (filter nama berkas), `skip`, `limit`.
- **Respons (200 OK):**
<!-- AUTO:scan_candidates_response -->
{blocks['scan_candidates_response']}
<!-- /AUTO:scan_candidates_response -->

### 3.4 Memperbarui Centang Pilihan (Selection)
- **Method & Path:** `PATCH /api/v1/scans/{{scan_id}}/selection`
- **Aksi Valid:**
  - `select_all_new`: Centang semua kandidat berstatus `baru`.
  - `select_none`: Kosongkan seluruh centang.
  - `set`: Atur centang kandidat tertentu (`candidate_ids: [1, 2]`, `selected: true/false`).
- **Respons (200 OK):**
<!-- AUTO:scan_selection_response -->
{blocks['scan_selection_response']}
<!-- /AUTO:scan_selection_response -->

---

## 4. ALUR 3: PEMILIHAN FORMAT PENAMAAN BERKAS DINAMIS

Mendukung personalisasi nama berkas sesuai urutan tombol di UI (`nama`, `tahun`, `jenis`, `bidang`, `nomor`).

### 4.1 Mendapatkan Komponen Penamaan Tersedia
- **Method & Path:** `GET /api/v1/naming/components`
- **Respons (200 OK):**
<!-- AUTO:naming_components_response -->
{blocks['naming_components_response']}
<!-- /AUTO:naming_components_response -->

### 4.2 Pratinjau Nama Berkas Dinamis (Live Preview)
- **Method & Path:** `POST /api/v1/naming/preview`
- **Contoh 1 (Sample Bawaan Sistem):**
<!-- AUTO:naming_preview_default_response -->
{blocks['naming_preview_default_response']}
<!-- /AUTO:naming_preview_default_response -->
- **Contoh 2 (Kustom Sample):**
<!-- AUTO:naming_preview_custom_response -->
{blocks['naming_preview_custom_response']}
<!-- /AUTO:naming_preview_custom_response -->

---

## 5. ALUR 4: PENARIKAN BERKAS (KNOWLEDGE BASE & UNDUH ZIP)

### 5.1 Tarik ke Knowledge Base (KB)
- **Method & Path:** `POST /api/v1/scans/{{scan_id}}/pull`
- **Body:** `destination: "knowledge_base"`, `naming_format` (array), `naming_separator` (opsional).
- **Respons (202 Accepted):**
<!-- AUTO:scan_pull_kb_response -->
{blocks['scan_pull_kb_response']}
<!-- /AUTO:scan_pull_kb_response -->

### 5.2 Tarik ke Folder Ekspor & Unduh ZIP
- **Method & Path:** `POST /api/v1/scans/{{scan_id}}/pull`
- **Body:** `destination: "unduh_folder"`, `naming_format` (array), `naming_separator` (opsional).
- **Respons (202 Accepted):**
<!-- AUTO:scan_pull_zip_response -->
{blocks['scan_pull_zip_response']}
<!-- /AUTO:scan_pull_zip_response -->

- **Unduh Berkas ZIP Setelah Selesai:**
  - `GET /api/v1/scans/{{scan_id}}/download` → Menghasilkan stream berkas `scan_{{id}}_export.zip` dengan nama berkas di dalam ZIP mengikuti format penamaan yang dipilih.

---

## 6. ALUR 5: UNGGAH BERKAS MANUAL & SINKRONISASI FOLDER LOKAL

### 6.1 Unggah Manual Banyak Berkas (Multipart/form-data)
- **Method & Path:** `POST /api/v1/ingest/upload-pdf`
- **Header:** `Content-Type: multipart/form-data`
- **Form Fields:**
  - `files`: Berkas-berkas PDF (bisa banyak berkas sekaligus).
  - `access_classification`: `publik` atau `non_publik` (default: `publik`).
  - `document_role`: `corpus_eksisting` atau `referensi_tambahan`.
  - `naming_format`: String dipisah koma (contoh: `"nama,jenis,tahun,bidang"`).
  - `naming_separator`: `" "` | `"_"` | `"-"`.
  - `bidang`: String sektor/bidang regulasi (contoh: `"Perbankan"`).
- **Respons (200 OK):**
<!-- AUTO:upload_pdf_response -->
{blocks['upload_pdf_response']}
<!-- /AUTO:upload_pdf_response -->

### 6.2 Eksekusi Sinkronisasi Folder Lokal
- **Method & Path:** `POST /api/v1/scraping-sources/{{source_id}}/run`
- **Body (Opsional):** `naming_format` (array), `naming_separator` (string).
- **Respons (202 Accepted / 200 OK):**
<!-- AUTO:source_run_response -->
{blocks['source_run_response']}
<!-- /AUTO:source_run_response -->

### 6.3 Daftar Berkas Sumber Lokal
- **Method & Path:** `GET /api/v1/scraping-sources/{{source_id}}/files`
- **Respons (200 OK):**
<!-- AUTO:source_files_response -->
{blocks['source_files_response']}
<!-- /AUTO:source_files_response -->

---

## 7. ALUR 6: EKSPLORASI KNOWLEDGE BASE & PENCARIAN REGULASI

### 7.1 Daftar & Filter Dokumen KB
- **Method & Path:** `GET /api/v1/documents/`
- **Query Params:**
  - `skip`, `limit`
  - `bidang` (filter sektor, contoh: `Perbankan`, `Pasar Modal`, `BMKS`)
  - `category_id` (filter kategori)
  - `regulation_type` (filter jenis regulasi)
  - `year` (filter tahun)
  - `status_keberlakuan` (`berlaku`, `dicabut`, `diubah`, dll.)
  - `processing_status` (`tersimpan`, `diekstraksi`, `terindeks`, `perlu_koreksi`)
  - `access_classification` (`publik`, `non_publik`)
- **Respons (200 OK):**
<!-- AUTO:documents_list_response -->
{blocks['documents_list_response']}
<!-- /AUTO:documents_list_response -->

### 7.2 Pencarian Cerdas Regulasi (Full-Text & Semantik)
- **Method & Path:** `GET /api/v1/documents/search`
- **Query Params:**
  - `q`: Kata kunci / frasa hukum (contoh: `modal inti bank umum`).
  - `mode`: `phrase` (pencarian frasa tepat) | `all` (semua kata) | `web` (pencarian berbasis web/boolean).
  - `bidang`: Filter sektor regulasi.
  - `highlight`: `true` untuk menyertakan cuplikan teks dengan tag `<mark>`.
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
- **Query Params:** `offset` (karakter awal, default 0), `limit` (panjang karakter, default 10000).
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

## 9. ALUR 8: KURASI & KOREKSI METADATA SERTA PENANGANAN GAGAL

### 9.1 Koreksi Metadata Dokumen
- **Method & Path:** `PATCH /api/v1/documents/{{document_id}}/metadata`
- **Body:** Mendukung pembaruan `title`, `regulation_number`, `regulation_type`, `release_date`, `bidang`, `category_id`, `status_keberlakuan`, `access_classification`, `document_role`.
- **Respons (200 OK):**
<!-- AUTO:document_patch_metadata_response -->
{blocks['document_patch_metadata_response']}
<!-- /AUTO:document_patch_metadata_response -->

### 9.2 Daftar Antrian Gagal (Ingest Failures)
- **Method & Path:** `GET /api/v1/failures/`
- **Respons (200 OK):**
<!-- AUTO:failures_list_response -->
{blocks['failures_list_response']}
<!-- /AUTO:failures_list_response -->

### 9.3 Mencoba Ulang (Retry) Berkas Gagal
- **Method & Path:** `POST /api/v1/failures/{{failure_id}}/retry`
- **Respons (200 OK):**
<!-- AUTO:failure_retry_response -->
{blocks['failure_retry_response']}
<!-- /AUTO:failure_retry_response -->

### 9.4 Mengabaikan (Ignore) Berkas Gagal
- **Method & Path:** `POST /api/v1/failures/{{failure_id}}/ignore`
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
| **413 Payload Too Large** | Berkas melebihi batas | Ukuran unggah PDF melebihi batas (default 50 MB) | Peringatkan pengguna untuk mengunggah berkas lebih kecil. |
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
  "name": "JDIH OJK Pusat",
  "url": "https://jdih.ojk.go.id",
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

### 11. Documents: Search
GET {{baseUrl}}/documents/search?q=modal+inti&bidang=Perbankan&highlight=true
Accept: application/json

### 12. Documents: Get Detail (Ganti ID)
GET {{baseUrl}}/documents/1
Accept: application/json

### 13. Documents: Read Text (Ganti ID)
GET {{baseUrl}}/documents/1/text?offset=0&limit=5000
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

### 16. Dashboard: Summary
GET {{baseUrl}}/dashboard/summary
Accept: application/json
"""
    http_path.write_text(http_content, encoding="utf-8")
    print(f"REST Client collection berhasil ditulis ke: {http_path}")


if __name__ == "__main__":
    run_contract_builder()
