"""
tests/test_step27_corong.py
Pengujian Langkah 27: Statistik corong per sumber (scan -> unduh -> simpan -> terbaca)
dan penanda PDF diproteksi.
Kasus C01 s.d. C15.
"""
import io
import bcrypt
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import PeranPengguna
from app.models.article import Article
from app.models.document import Document
from app.models.enums import (
    JenisJobIngest,
    JenisKegagalan,
    JenisSumber,
    KlasifikasiAkses,
    MetodeEkstraksi,
    PeranDokumen,
    StatusJobIngest,
    StatusKandidat,
    StatusPemrosesan,
    StatusTindakLanjut,
    TujuanTarik,
)
from app.models.ingest_failure import IngestFailure
from app.models.job_ingest import JobIngest
from app.models.scan_candidate import ScanCandidate
from app.models.scan_session import ScanSession
from app.models.scraping_source import ScrapingSource
from app.models.user import User
from app.services.storage_service import StorageService
from scripts.backfill_pdf_info import run_backfill


def make_valid_pdf(page_count: int = 1) -> bytes:
    """Helper membuat berkas PDF valid dengan pypdf."""
    w = PdfWriter()
    for _ in range(page_count):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def make_owner_encrypted_pdf(owner_pass: str = "owner_secret") -> bytes:
    """Helper membuat PDF dengan proteksi kata sandi pemilik (user pass kosong)."""
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.encrypt(user_password="", owner_password=owner_pass)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


# ============================================================================
# C01: Scan Invariant
# ============================================================================
def test_c01_scan_invariant(client: TestClient, db_session: Session):
    """
    C01: Sumber A: 6 kandidat unik (1 sudah_ada, 2 ditarik, 1 duplikat, 1 gagal, 1 belum)
    + 1 kandidat dobel url_hash di sesi kedua.
    Ekspektasi: ditemukan=6, dan invarian scan terpenuhi.
    """
    src = ScrapingSource(
        name="Sumber A",
        url="https://ojk.go.id/sumber-a",
        source_type=JenisSumber.situs_web,
        is_active=True,
    )
    db_session.add(src)
    db_session.flush()

    sess1 = ScanSession(
        source_id=src.id,
        start_url=src.url,
        destination=TujuanTarik.knowledge_base,
    )
    db_session.add(sess1)
    db_session.flush()

    # Buat dokumen nyata untuk referensi foreign key document_id
    d_tarik1 = Document(
        title="D Tarik 1", file_path_pdf="kb/tarik1.pdf", file_hash="ht1", file_size_bytes=100,
        access_classification=KlasifikasiAkses.publik, document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.terindeks, is_active=True,
    )
    d_tarik2 = Document(
        title="D Tarik 2", file_path_pdf="kb/tarik2.pdf", file_hash="ht2", file_size_bytes=200,
        access_classification=KlasifikasiAkses.publik, document_role=PeranDokumen.corpus_eksisting,
        processing_status=StatusPemrosesan.terindeks, is_active=True,
    )
    db_session.add_all([d_tarik1, d_tarik2])
    db_session.flush()

    # 6 kandidat sesi 1
    c1 = ScanCandidate(scan_id=sess1.id, url="https://ojk.go.id/1.pdf", url_hash="hash1", filename="1.pdf", match_status=StatusKandidat.sudah_ada)
    c2 = ScanCandidate(scan_id=sess1.id, url="https://ojk.go.id/2.pdf", url_hash="hash2", filename="2.pdf", pull_outcome="berhasil", document_id=d_tarik1.id)
    c3 = ScanCandidate(scan_id=sess1.id, url="https://ojk.go.id/3.pdf", url_hash="hash3", filename="3.pdf", pull_outcome="success", document_id=d_tarik2.id)
    c4 = ScanCandidate(scan_id=sess1.id, url="https://ojk.go.id/4.pdf", url_hash="hash4", filename="4.pdf", pull_outcome="duplikat")
    c5 = ScanCandidate(scan_id=sess1.id, url="https://ojk.go.id/5.pdf", url_hash="hash5", filename="5.pdf", pull_outcome="gagal")
    c6 = ScanCandidate(scan_id=sess1.id, url="https://ojk.go.id/6.pdf", url_hash="hash6", filename="6.pdf", match_status=StatusKandidat.baru)
    db_session.add_all([c1, c2, c3, c4, c5, c6])
    db_session.flush()

    # Sesi 2 dengan kandidat hash6 ganda (misal pemindaian ulang)
    sess2 = ScanSession(
        source_id=src.id,
        start_url=src.url,
        destination=TujuanTarik.knowledge_base,
    )
    db_session.add(sess2)
    db_session.flush()
    c6_dup = ScanCandidate(scan_id=sess2.id, url="https://ojk.go.id/6.pdf", url_hash="hash6", filename="6.pdf", match_status=StatusKandidat.baru)
    db_session.add(c6_dup)
    db_session.commit()

    resp = client.get("/api/v1/dashboard/corong")
    assert resp.status_code == 200
    data = resp.json()

    sumber = next(s for s in data["sumber"] if s["source_id"] == src.id)
    scan = sumber["scan"]
    assert scan["ditemukan"] == 6
    assert scan["sudah_ada_di_kb"] == 1
    assert scan["ditarik"] == 2
    assert scan["duplikat"] == 1
    assert scan["gagal_unduh"] == 1
    assert scan["belum_ditarik"] == 1

    # Invarian: ditemukan = sudah_ada_di_kb + ditarik + duplikat + gagal_unduh + belum_ditarik
    assert scan["ditemukan"] == (
        scan["sudah_ada_di_kb"] + scan["ditarik"] + scan["duplikat"] + scan["gagal_unduh"] + scan["belum_ditarik"]
    )


# ============================================================================
# C02: Dokumen Invariant & Persen Terbaca
# ============================================================================
def test_c02_dokumen_invariant_and_percentage(client: TestClient, db_session: Session):
    """
    C02: Dokumen sumber A: 1 terindeks teks langsung, 1 perlu_koreksi OCR, 1 gagal (teks_kosong_ocr), 1 diproses.
    Ekspektasi: terbaca=2 (langsung 1, OCR 1), gagal_baca=1, menunggu=1, invarian terpenuhi, persen_terbaca=50.0.
    """
    src = ScrapingSource(name="Sumber B", url="https://bi.go.id/sumber-b", source_type=JenisSumber.situs_web, is_active=True)
    db_session.add(src)
    db_session.flush()

    job = JobIngest(job_type=JenisJobIngest.scraping, source_id=src.id, status=StatusJobIngest.selesai)
    db_session.add(job)
    db_session.flush()

    doc1 = Document(
        title="POJK 1",
        file_path_pdf="kb/doc1.pdf",
        file_hash="hash_doc1",
        file_size_bytes=1000,
        job_id=job.id,
        processing_status=StatusPemrosesan.terindeks,
        extraction_method=MetodeEkstraksi.teks_langsung,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        is_active=True,
    )
    doc2 = Document(
        title="POJK 2",
        file_path_pdf="kb/doc2.pdf",
        file_hash="hash_doc2",
        file_size_bytes=2000,
        job_id=job.id,
        processing_status=StatusPemrosesan.perlu_koreksi,
        extraction_method=MetodeEkstraksi.ocr,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        is_active=True,
    )
    doc3 = Document(
        title="POJK 3",
        file_path_pdf="kb/doc3.pdf",
        file_hash="hash_doc3",
        file_size_bytes=3000,
        job_id=job.id,
        processing_status=StatusPemrosesan.gagal,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        is_active=True,
    )
    doc4 = Document(
        title="POJK 4",
        file_path_pdf="pdf/_inbox/doc4.pdf",
        file_hash="hash_doc4",
        file_size_bytes=4000,
        job_id=job.id,
        processing_status=StatusPemrosesan.diproses,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        is_active=True,
    )
    db_session.add_all([doc1, doc2, doc3, doc4])
    db_session.flush()

    fail = IngestFailure(
        job_id=job.id,
        reason_code="teks_kosong_ocr",
        failure_type=JenisKegagalan.ocr_gagal,
        message="Hasil OCR kosong",
        original_filename="doc3.pdf",
        file_hash="hash_doc3",
        file_size_bytes=3000,
        document_id=doc3.id,
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    db_session.add(fail)
    db_session.commit()

    resp = client.get("/api/v1/dashboard/corong")
    assert resp.status_code == 200
    data = resp.json()

    sumber = next(s for s in data["sumber"] if s["source_id"] == src.id)
    dk = sumber["dokumen"]
    assert dk["di_kb"] == 4
    assert dk["terbaca"] == 2
    assert dk["terbaca_teks_langsung"] == 1
    assert dk["terbaca_ocr"] == 1
    assert dk["perlu_koreksi"] == 1
    assert dk["gagal_baca"] == 1
    assert dk["menunggu_ekstraksi"] == 1
    assert dk["lainnya"] == 0

    # Invarian: di_kb = menunggu_ekstraksi + terbaca + gagal_baca + lainnya
    assert dk["di_kb"] == dk["menunggu_ekstraksi"] + dk["terbaca"] + dk["gagal_baca"] + dk["lainnya"]
    assert sumber["persen_terbaca"] == 50.0
    assert sumber["pdf"]["hasil_pindai_ocr"] == 1
    assert sumber["pdf"]["ocr_gagal"] == 1


# ============================================================================
# C03: Articles & Embedding Aggregates
# ============================================================================
def test_c03_articles_and_embedding_aggregates(client: TestClient, db_session: Session):
    """
    C03: articles untuk 2 dokumen, dan hanya 1 yang punya embedding.
    Ekspektasi: terpecah_pasal=2, tervektor=1.
    """
    src = ScrapingSource(name="Sumber C", url="https://ojk.go.id/sumber-c", source_type=JenisSumber.situs_web, is_active=True)
    db_session.add(src)
    db_session.flush()

    job = JobIngest(job_type=JenisJobIngest.scraping, source_id=src.id, status=StatusJobIngest.selesai)
    db_session.add(job)
    db_session.flush()

    doc1 = Document(
        title="Dokumen 1",
        file_path_pdf="kb/doc1.pdf",
        file_hash="h_art1",
        file_size_bytes=100,
        job_id=job.id,
        processing_status=StatusPemrosesan.terindeks,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        is_active=True,
    )
    doc2 = Document(
        title="Dokumen 2",
        file_path_pdf="kb/doc2.pdf",
        file_hash="h_art2",
        file_size_bytes=200,
        job_id=job.id,
        processing_status=StatusPemrosesan.terindeks,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        is_active=True,
    )
    db_session.add_all([doc1, doc2])
    db_session.flush()

    # doc1 punya pasal dengan embedding
    art1 = Article(
        document_id=doc1.id,
        article_number="Pasal 1",
        order_index=1,
        content_text="Isi pasal 1",
        embedding=[0.05] * 1536,
    )
    # doc2 punya pasal tanpa embedding
    art2 = Article(
        document_id=doc2.id,
        article_number="Pasal 1",
        order_index=1,
        content_text="Isi pasal 1 doc 2",
        embedding=None,
    )
    db_session.add_all([art1, art2])
    db_session.commit()

    resp = client.get("/api/v1/dashboard/corong")
    assert resp.status_code == 200
    data = resp.json()

    sumber = next(s for s in data["sumber"] if s["source_id"] == src.id)
    dk = sumber["dokumen"]
    assert dk["terpecah_pasal"] == 2
    assert dk["tervektor"] == 1


# ============================================================================
# C04 & C05: Upload PDF Owner Password vs Biasa
# ============================================================================
def test_c04_upload_pdf_owner_password(client: TestClient, db_session: Session):
    """
    C04: Unggah PDF owner-password lewat upload-pdf -> pdf_terproteksi=true dan page_count terisi.
    """
    content = make_owner_encrypted_pdf("pemilik123")
    files = [("files", ("protected.pdf", content, "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "title": "Regulasi Terproteksi",
        "regulation_number": "POJK-77-2026",
    }
    resp = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert resp.status_code == 200
    res_json = resp.json()
    doc_id = res_json["details"][0]["document_id"]

    doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert doc is not None
    assert doc.pdf_terproteksi is True
    assert doc.page_count == 1


def test_c05_upload_pdf_regular(client: TestClient, db_session: Session):
    """
    C05: Unggah PDF biasa -> pdf_terproteksi=false.
    """
    content = make_valid_pdf(2)
    files = [("files", ("biasa.pdf", content, "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "title": "Regulasi Biasa",
        "regulation_number": "POJK-78-2026",
    }
    resp = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert resp.status_code == 200
    res_json = resp.json()
    doc_id = res_json["details"][0]["document_id"]

    doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert doc is not None
    assert doc.pdf_terproteksi is False
    assert doc.page_count == 2


# ============================================================================
# C06: PDF Terproteksi Terbaca dan Belum Diperiksa
# ============================================================================
def test_c06_pdf_terproteksi_terbaca_and_belum_diperiksa(client: TestClient, db_session: Session):
    """
    C06: pdf.terproteksi_terbaca dan belum_diperiksa sesuai data seed.
    """
    src = ScrapingSource(name="Sumber D", url="https://ojk.go.id/sumber-d", source_type=JenisSumber.situs_web, is_active=True)
    db_session.add(src)
    db_session.flush()

    job = JobIngest(job_type=JenisJobIngest.scraping, source_id=src.id, status=StatusJobIngest.selesai)
    db_session.add(job)
    db_session.flush()

    # Doc 1: terproteksi & terindeks (terbaca)
    d1 = Document(
        title="D1", file_path_pdf="kb/d1.pdf", file_hash="hd1", file_size_bytes=100, job_id=job.id,
        processing_status=StatusPemrosesan.terindeks, pdf_terproteksi=True, is_active=True,
        access_classification=KlasifikasiAkses.publik, document_role=PeranDokumen.corpus_eksisting,
    )
    # Doc 2: terproteksi & gagal (belum terbaca)
    d2 = Document(
        title="D2", file_path_pdf="kb/d2.pdf", file_hash="hd2", file_size_bytes=200, job_id=job.id,
        processing_status=StatusPemrosesan.gagal, pdf_terproteksi=True, is_active=True,
        access_classification=KlasifikasiAkses.publik, document_role=PeranDokumen.corpus_eksisting,
    )
    # Doc 3: belum diperiksa (NULL)
    d3 = Document(
        title="D3", file_path_pdf="kb/d3.pdf", file_hash="hd3", file_size_bytes=300, job_id=job.id,
        processing_status=StatusPemrosesan.diterima, pdf_terproteksi=None, is_active=True,
        access_classification=KlasifikasiAkses.publik, document_role=PeranDokumen.corpus_eksisting,
    )
    db_session.add_all([d1, d2, d3])
    db_session.commit()

    resp = client.get("/api/v1/dashboard/corong")
    assert resp.status_code == 200
    data = resp.json()

    sumber = next(s for s in data["sumber"] if s["source_id"] == src.id)
    pdf = sumber["pdf"]
    assert pdf["terproteksi"] == 2
    assert pdf["terproteksi_terbaca"] == 1
    assert pdf["belum_diperiksa"] == 1


# ============================================================================
# C07: Gagal Per Alasan (Exclude Diabaikan & Duplikat)
# ============================================================================
def test_c07_gagal_per_alasan_filters(client: TestClient, db_session: Session):
    """
    C07: gagal_per_alasan: kegagalan diabaikan tidak dihitung, duplikat tidak dihitung.
    """
    src = ScrapingSource(name="Sumber E", url="https://ojk.go.id/sumber-e", source_type=JenisSumber.situs_web, is_active=True)
    db_session.add(src)
    db_session.flush()

    job = JobIngest(job_type=JenisJobIngest.scraping, source_id=src.id, status=StatusJobIngest.selesai)
    db_session.add(job)
    db_session.flush()

    # Buat dokumen referensi untuk duplikat
    ref_doc = Document(
        title="Ref Doc", file_path_pdf="kb/ref.pdf", file_hash="href", file_size_bytes=100,
        processing_status=StatusPemrosesan.terindeks, is_active=True,
        access_classification=KlasifikasiAkses.publik, document_role=PeranDokumen.corpus_eksisting,
    )
    db_session.add(ref_doc)
    db_session.flush()

    f1 = IngestFailure(
        job_id=job.id, reason_code="pdf_rusak", failure_type=JenisKegagalan.format_tidak_didukung,
        message="PDF stream ended unexpectedly", original_filename="f1.pdf", file_hash="hf1", file_size_bytes=10,
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    f2 = IngestFailure(
        job_id=job.id, reason_code="pdf_terenkripsi", failure_type=JenisKegagalan.format_tidak_didukung,
        message="Terenkripsi", original_filename="f2.pdf", file_hash="hf2", file_size_bytes=20,
        follow_up_status=StatusTindakLanjut.diabaikan,  # Harus dilewati
    )
    f3 = IngestFailure(
        job_id=job.id, reason_code="duplikat", failure_type=JenisKegagalan.duplikat,
        message="Duplikat", original_filename="f3.pdf", file_hash="hf3", file_size_bytes=30,
        duplicate_of_document_id=ref_doc.id,
        follow_up_status=StatusTindakLanjut.belum_ditangani,  # Harus dilewati
    )
    db_session.add_all([f1, f2, f3])
    db_session.commit()

    resp = client.get("/api/v1/dashboard/corong")
    assert resp.status_code == 200
    data = resp.json()

    sumber = next(s for s in data["sumber"] if s["source_id"] == src.id)
    gpa = sumber["gagal_per_alasan"]
    assert gpa.get("pdf_rusak") == 1
    assert "pdf_terenkripsi" not in gpa
    assert "duplikat" not in gpa


# ============================================================================
# C08: Unggah Manual Block
# ============================================================================
def test_c08_unggah_manual_isolation(client: TestClient, db_session: Session):
    """
    C08: Dokumen unggah manual (job tanpa source_id) masuk unggah_manual, bukan sumber mana pun.
    """
    src = ScrapingSource(name="Sumber F", url="https://ojk.go.id/sumber-f", source_type=JenisSumber.situs_web, is_active=True)
    db_session.add(src)
    db_session.flush()

    manual_job = JobIngest(job_type=JenisJobIngest.unggah_manual, source_id=None, status=StatusJobIngest.selesai)
    db_session.add(manual_job)
    db_session.flush()

    doc = Document(
        title="Dokumen Manual", file_path_pdf="kb/manual.pdf", file_hash="hman", file_size_bytes=100,
        job_id=manual_job.id, processing_status=StatusPemrosesan.terindeks, is_active=True,
        access_classification=KlasifikasiAkses.publik, document_role=PeranDokumen.corpus_eksisting,
    )
    db_session.add(doc)
    db_session.commit()

    resp = client.get("/api/v1/dashboard/corong")
    assert resp.status_code == 200
    data = resp.json()

    sumber = next(s for s in data["sumber"] if s["source_id"] == src.id)
    assert sumber["dokumen"]["di_kb"] == 0
    assert data["unggah_manual"]["dokumen"]["di_kb"] >= 1
    assert data["unggah_manual"]["dokumen"]["terbaca"] >= 1


# ============================================================================
# C09: Satu Dokumen Terkait Dua Sumber (Deduplikasi di Total)
# ============================================================================
def test_c09_single_doc_multiple_sources_deduplicated_in_total(client: TestClient, db_session: Session):
    """
    C09: Satu dokumen terkait dua sumber -> total.dokumen.di_kb menghitungnya sekali.
    """
    src1 = ScrapingSource(name="Sumber G1", url="https://g1.id/sumber-g1", source_type=JenisSumber.situs_web, is_active=True)
    src2 = ScrapingSource(name="Sumber G2", url="https://g2.id/sumber-g2", source_type=JenisSumber.situs_web, is_active=True)
    db_session.add_all([src1, src2])
    db_session.flush()

    shared_doc = Document(
        title="Dokumen Bersama", file_path_pdf="kb/shared.pdf", file_hash="h_shared", file_size_bytes=500,
        processing_status=StatusPemrosesan.terindeks, is_active=True,
        access_classification=KlasifikasiAkses.publik, document_role=PeranDokumen.corpus_eksisting,
    )
    db_session.add(shared_doc)
    db_session.flush()

    # Kaitkan ke Sumber G1 lewat scan candidate
    sess1 = ScanSession(source_id=src1.id, start_url=src1.url, destination=TujuanTarik.knowledge_base)
    db_session.add(sess1)
    db_session.flush()
    c1 = ScanCandidate(scan_id=sess1.id, url="https://g1.id/1.pdf", url_hash="hg1", filename="1.pdf", match_document_id=shared_doc.id)

    # Kaitkan ke Sumber G2 lewat scan candidate
    sess2 = ScanSession(source_id=src2.id, start_url=src2.url, destination=TujuanTarik.knowledge_base)
    db_session.add(sess2)
    db_session.flush()
    c2 = ScanCandidate(scan_id=sess2.id, url="https://g2.id/2.pdf", url_hash="hg2", filename="2.pdf", match_document_id=shared_doc.id)

    db_session.add_all([c1, c2])
    db_session.commit()

    resp = client.get("/api/v1/dashboard/corong")
    assert resp.status_code == 200
    data = resp.json()

    s1 = next(s for s in data["sumber"] if s["source_id"] == src1.id)
    s2 = next(s for s in data["sumber"] if s["source_id"] == src2.id)

    assert s1["dokumen"]["di_kb"] == 1
    assert s2["dokumen"]["di_kb"] == 1

    # Total dokumen di KB harus 1 (bukan 1 + 1 = 2)
    assert data["total"]["dokumen"]["di_kb"] == 1


# ============================================================================
# C10: Filter ?source_id=A
# ============================================================================
def test_c10_filter_by_source_id(client: TestClient, db_session: Session):
    """
    C10: ?source_id=A -> hanya sumber A di sumber[].
    """
    src_a = ScrapingSource(name="Sumber H1", url="https://ojk.go.id/sumber-h1", source_type=JenisSumber.situs_web, is_active=True)
    src_b = ScrapingSource(name="Sumber H2", url="https://ojk.go.id/sumber-h2", source_type=JenisSumber.situs_web, is_active=True)
    db_session.add_all([src_a, src_b])
    db_session.commit()

    resp = client.get(f"/api/v1/dashboard/corong?source_id={src_a.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["sumber"]) == 1
    assert data["sumber"][0]["source_id"] == src_a.id


# ============================================================================
# C11: Format CSV dengan BOM dan Header
# ============================================================================
def test_c11_format_csv_bom_and_headers(client: TestClient, db_session: Session):
    """
    C11: format=csv -> diawali BOM; ada baris TOTAL; filename*=.
    """
    src = ScrapingSource(name="Sumber CSV", url="https://ojk.go.id/sumber-csv", source_type=JenisSumber.situs_web, is_active=True)
    db_session.add(src)
    db_session.commit()

    resp = client.get("/api/v1/dashboard/corong?format=csv")
    assert resp.status_code == 200

    # Diawali BOM UTF-8
    assert resp.content.startswith(b"\xef\xbb\xbf")

    # Header Content-Disposition
    cd = resp.headers.get("content-disposition", "")
    assert "attachment;" in cd
    assert "corong-hero-" in cd
    assert "filename*=UTF-8''corong-hero-" in cd

    # Isi teks CSV
    csv_text = resp.content.decode("utf-8-sig")
    assert "sumber_id,sumber_nama,sumber_jenis" in csv_text
    assert "TOTAL" in csv_text
    assert "Unggah manual" in csv_text
    assert "Sumber CSV" in csv_text


# ============================================================================
# C12: Failures Drill-Down Filtering
# ============================================================================
def test_c12_failures_drilldown_filters(client: TestClient, db_session: Session):
    """
    C12: /ingest/failures?reason_code=teks_kosong&reason_code=teks_kosong_ocr dan ?source_id=A.
    """
    src_a = ScrapingSource(name="Sumber I1", url="https://ojk.go.id/sumber-i1", source_type=JenisSumber.situs_web, is_active=True)
    src_b = ScrapingSource(name="Sumber I2", url="https://ojk.go.id/sumber-i2", source_type=JenisSumber.situs_web, is_active=True)
    db_session.add_all([src_a, src_b])
    db_session.flush()

    job_a = JobIngest(job_type=JenisJobIngest.scraping, source_id=src_a.id, status=StatusJobIngest.selesai)
    job_b = JobIngest(job_type=JenisJobIngest.scraping, source_id=src_b.id, status=StatusJobIngest.selesai)
    db_session.add_all([job_a, job_b])
    db_session.flush()

    f1 = IngestFailure(
        job_id=job_a.id, reason_code="teks_kosong", failure_type=JenisKegagalan.ekstraksi_gagal,
        message="kosong", original_filename="f1.pdf", file_hash="h1", file_size_bytes=10,
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    f2 = IngestFailure(
        job_id=job_a.id, reason_code="teks_kosong_ocr", failure_type=JenisKegagalan.ocr_gagal,
        message="ocr kosong", original_filename="f2.pdf", file_hash="h2", file_size_bytes=20,
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    f3 = IngestFailure(
        job_id=job_a.id, reason_code="pdf_rusak", failure_type=JenisKegagalan.format_tidak_didukung,
        message="rusak", original_filename="f3.pdf", file_hash="h3", file_size_bytes=30,
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    f4 = IngestFailure(
        job_id=job_b.id, reason_code="teks_kosong", failure_type=JenisKegagalan.ekstraksi_gagal,
        message="kosong b", original_filename="f4.pdf", file_hash="h4", file_size_bytes=40,
        follow_up_status=StatusTindakLanjut.belum_ditangani,
    )
    db_session.add_all([f1, f2, f3, f4])
    db_session.commit()

    # 1. Tanpa filter: seluruh 4 kegagalan
    resp_all = client.get("/api/v1/ingest/failures")
    assert resp_all.status_code == 200
    assert resp_all.json()["total"] == 4

    # 2. Filter reason_code (teks_kosong & teks_kosong_ocr) -> f1, f2, f4 (3 items)
    resp_reasons = client.get("/api/v1/ingest/failures?reason_code=teks_kosong&reason_code=teks_kosong_ocr")
    assert resp_reasons.status_code == 200
    data_reasons = resp_reasons.json()
    assert data_reasons["total"] == 3
    found_ids = {it["id"] for it in data_reasons["items"]}
    assert found_ids == {f1.id, f2.id, f4.id}

    # 3. Filter source_id=src_a -> f1, f2, f3 (3 items)
    resp_source = client.get(f"/api/v1/ingest/failures?source_id={src_a.id}")
    assert resp_source.status_code == 200
    data_source = resp_source.json()
    assert data_source["total"] == 3
    found_src_ids = {it["id"] for it in data_source["items"]}
    assert found_src_ids == {f1.id, f2.id, f3.id}

    # 4. Kombinasi reason_code & source_id -> hanya f1 dan f2
    resp_comb = client.get(f"/api/v1/ingest/failures?reason_code=teks_kosong&source_id={src_a.id}")
    assert resp_comb.status_code == 200
    data_comb = resp_comb.json()
    assert data_comb["total"] == 1
    assert data_comb["items"][0]["id"] == f1.id


# ============================================================================
# C13: Backfill Script (Dry-run vs Apply)
# ============================================================================
def test_c13_backfill_pdf_info_dry_run_and_apply(db_session: Session, test_storage: StorageService):
    """
    C13: backfill_pdf_info.py dry-run lalu --apply.
    Ekspektasi: dry-run tidak mengubah DB; apply mengisi pdf_terproteksi; PDF rusak dilewati dan dihitung.
    """
    valid_pdf = make_valid_pdf(2)
    owner_pdf = make_owner_encrypted_pdf("pemilik")
    corrupt_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nstream\ncorrupt"

    path_valid = test_storage.save_pdf(valid_pdf, filename_hint="valid.pdf", subdir="pdf/_inbox")
    path_owner = test_storage.save_pdf(owner_pdf, filename_hint="owner.pdf", subdir="pdf/_inbox")
    path_corrupt = test_storage.save_pdf(corrupt_pdf, filename_hint="corrupt.pdf", subdir="pdf/_inbox")

    d1 = Document(
        title="D Valid", file_path_pdf=path_valid, file_hash="hv", file_size_bytes=len(valid_pdf),
        pdf_terproteksi=None, page_count=None, is_active=True,
        access_classification=KlasifikasiAkses.publik, document_role=PeranDokumen.corpus_eksisting,
    )
    d2 = Document(
        title="D Owner", file_path_pdf=path_owner, file_hash="ho", file_size_bytes=len(owner_pdf),
        pdf_terproteksi=None, page_count=None, is_active=True,
        access_classification=KlasifikasiAkses.publik, document_role=PeranDokumen.corpus_eksisting,
    )
    d3 = Document(
        title="D Corrupt", file_path_pdf=path_corrupt, file_hash="hc", file_size_bytes=len(corrupt_pdf),
        pdf_terproteksi=None, page_count=None, is_active=True,
        access_classification=KlasifikasiAkses.publik, document_role=PeranDokumen.corpus_eksisting,
    )
    db_session.add_all([d1, d2, d3])
    db_session.commit()

    # 1. Jalankan dry-run
    stats_dry = run_backfill(db=db_session, storage=test_storage, apply=False)
    assert stats_dry["kandidat"] == 3
    assert stats_dry["terproteksi"] == 1
    assert stats_dry["tidak_terproteksi"] == 1
    assert stats_dry["dilewati_rusak"] == 1

    # Verifikasi database TIDAK berubah setelah dry-run
    db_session.refresh(d1)
    db_session.refresh(d2)
    db_session.refresh(d3)
    assert d1.pdf_terproteksi is None
    assert d2.pdf_terproteksi is None
    assert d3.pdf_terproteksi is None

    # 2. Jalankan apply
    stats_apply = run_backfill(db=db_session, storage=test_storage, apply=True)
    assert stats_apply["kandidat"] == 3
    assert stats_apply["terproteksi"] == 1
    assert stats_apply["tidak_terproteksi"] == 1
    assert stats_apply["dilewati_rusak"] == 1

    # Verifikasi database BERUBAH setelah apply
    db_session.refresh(d1)
    db_session.refresh(d2)
    db_session.refresh(d3)
    assert d1.pdf_terproteksi is False
    assert d1.page_count == 2
    assert d2.pdf_terproteksi is True
    assert d2.page_count == 1
    assert d3.pdf_terproteksi is None  # Rusak dilewati, status tidak diubah


# ============================================================================
# C14: Auth Active Token Without KB_BACA -> 403
# ============================================================================
def test_c14_auth_without_kb_baca_returns_403(client: TestClient, db_session: Session, monkeypatch):
    """
    C14: Auth aktif, token tanpa KB_BACA -> 403 pada /dashboard/corong.
    """
    # Aktifkan auth via monkeypatch settings
    monkeypatch.setattr(settings, "auth_enabled", True)

    plain_pw = "TestSecretPass123!"
    hashed_pw = bcrypt.hashpw(plain_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(
        username="admin_sistem_c14",
        hashed_password=hashed_pw,
        role=PeranPengguna.admin_sistem.value,
        nama_lengkap="Admin Sistem Saja",
        unit_kerja="Divisi TI",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": user.username, "password": plain_pw},
    )
    assert login_resp.status_code == 200, f"Login gagal: {login_resp.text}"
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/dashboard/corong", headers=headers)
    assert resp.status_code == 403
    detail = resp.json().get("detail", {})
    assert detail.get("code") == "akses_ditolak"
    assert detail.get("izin") == "KB_BACA"


# ============================================================================
# C15: Corong Tidak Memuat full_text (Event Listener Check)
# ============================================================================
def test_c15_corong_does_not_load_full_text(client: TestClient, db_session: Session):
    """
    C15: Corong tidak memuat full_text.
    Pasang event listener SQLAlchemy before_cursor_execute, lalu pastikan tidak ada SQL dari endpoint
    ini yang menyebut kolom full_text.
    """
    src = ScrapingSource(name="Sumber FullText Test", url="https://ojk.go.id/sumber-fulltext", source_type=JenisSumber.situs_web, is_active=True)
    db_session.add(src)
    db_session.flush()

    job = JobIngest(job_type=JenisJobIngest.scraping, source_id=src.id, status=StatusJobIngest.selesai)
    db_session.add(job)
    db_session.flush()

    doc = Document(
        title="Dokumen Teks Tebal",
        file_path_pdf="kb/teks.pdf",
        file_hash="hteks",
        file_size_bytes=5000,
        full_text="Ini teks sangat panjang yang tidak boleh dimuat di corong " * 50,
        job_id=job.id,
        processing_status=StatusPemrosesan.terindeks,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        is_active=True,
    )
    db_session.add(doc)
    db_session.commit()

    from sqlalchemy.engine import Engine

    executed_statements = []

    def before_cursor_execute_listener(conn, cursor, statement, parameters, context, executemany):
        executed_statements.append(statement)

    event.listen(Engine, "before_cursor_execute", before_cursor_execute_listener)

    try:
        resp = client.get("/api/v1/dashboard/corong")
        assert resp.status_code == 200
    finally:
        event.remove(Engine, "before_cursor_execute", before_cursor_execute_listener)

    assert len(executed_statements) > 0, "Harus ada query SQL yang dieksekusi"
    for stmt in executed_statements:
        clean_stmt = stmt.lower()
        assert "full_text" not in clean_stmt, f"Kolom full_text ditemukan dalam query corong: {stmt}"
