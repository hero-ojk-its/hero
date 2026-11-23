"""
tests/test_catatan_dinas_rapikan.py
Pengujian perapihan Catatan Dinas:
1. Hapus baris KONSEP pada dokumen DOCX dan PDF.
2. Fungsi penulisan judul gaya OJK (rapikan_judul_ojk).
3. Penerapan pada teks bawaan (Hal bawaan, Butir 1, Butir 2).
4. Isian Hal dari form pengguna tidak diubah.
5. Butir 1 dengan narasi AI tidak diubah.
"""
from datetime import datetime, timezone
import io
import uuid

import docx
from fastapi.testclient import TestClient
import pypdf
import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app
from app.models.analysis_result import AnalysisResult
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
from app.services.catatan_dinas_export_service import (
    rapikan_judul_ojk,
    resolve_default_hal,
)


@pytest.fixture(autouse=True)
def setup_ml_env(monkeypatch: pytest.MonkeyPatch):
    """Konfigurasi ML dan otentikasi dinonaktifkan untuk pengujian terisolasi."""
    monkeypatch.setattr(settings, "ml_service_url", "http://ml-test:8100")
    monkeypatch.setattr(settings, "ml_cache_enabled", True)
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)
    monkeypatch.setattr(settings, "auth_enabled", False)
    yield
    app.dependency_overrides.pop(get_ml_client, None)


def create_test_doc(**kwargs) -> Document:
    rnd = uuid.uuid4().hex
    data = {
        "title": "Draf Dokumen Uji",
        "regulation_type": "POJK",
        "regulation_number": "12/POJK.03/2026",
        "regulation_year": 2026,
        "document_role": PeranDokumen.draft_kajian,
        "access_classification": KlasifikasiAkses.publik,
        "file_path_pdf": f"pdf/test_{rnd[:8]}.pdf",
        "file_hash": (rnd * 2)[:64],
        "file_size_bytes": 2048,
        "processing_status": StatusPemrosesan.terindeks,
        "status_keberlakuan": StatusKeberlakuan.berlaku,
        "is_active": True,
    }
    data.update(kwargs)
    return Document(**data)


def seed_harmonisasi_result(
    db: Session,
    doc: Document,
    payload: dict,
    mode: ModeAnalisa = ModeAnalisa.deterministik,
) -> AnalysisResult:
    res = AnalysisResult(
        document_id=doc.id,
        kind=JenisAnalisa.harmonisasi,
        mode=mode,
        params_hash="params-" + uuid.uuid4().hex[:16],
        source_fingerprint=f"hash:{doc.file_hash or 'nohash'}",
        result=payload,
        ml_version="1.0",
        duration_ms=100,
        created_at=datetime.now(timezone.utc),
    )
    db.add(res)
    db.commit()
    db.refresh(res)
    return res


def seed_analisa_result(
    db: Session,
    doc: Document,
    payload: dict,
    mode: ModeAnalisa = ModeAnalisa.deterministik,
) -> AnalysisResult:
    res = AnalysisResult(
        document_id=doc.id,
        kind=JenisAnalisa.analisa,
        mode=mode,
        params_hash="params-analisa-" + uuid.uuid4().hex[:16],
        source_fingerprint=f"hash:{doc.file_hash or 'nohash'}",
        result=payload,
        ml_version="1.0",
        duration_ms=150,
        created_at=datetime.now(timezone.utc),
    )
    db.add(res)
    db.commit()
    db.refresh(res)
    return res


def extract_docx_text(content: bytes) -> str:
    doc = docx.Document(io.BytesIO(content))
    lines = []
    for p in doc.paragraphs:
        lines.append(p.text)
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                lines.append(cell.text)
    return "\n".join(lines)


def extract_pdf_text(content: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


# ===========================================================================
# 1. PENGUJIAN UNIT: rapikan_judul_ojk
# ===========================================================================
def test_unit_rapikan_judul_ojk_contoh_wajib():
    """Memverifikasi seluruh contoh wajib yang tercantum pada instruksi Bagian 3.B.2."""
    # Contoh 1: Judul kapital semua dengan kata sambung dan singkatan
    src1 = "PENYELENGGARAAN TEKNOLOGI INFORMASI OLEH BANK PEREKONOMIAN RAKYAT DAN BANK PEREKONOMIAN RAKYAT SYARIAH"
    exp1 = "Penyelenggaraan Teknologi Informasi oleh Bank Perekonomian Rakyat dan Bank Perekonomian Rakyat Syariah"
    assert rapikan_judul_ojk(src1) == exp1

    # Contoh 2: Judul bab dengan pola setiap kata diawali kapital (singkatan rusak jadi huruf kecil)
    src2 = "Tata Kelola Ti Bpr Dan Bpr Syariah"
    exp2 = "Tata Kelola TI BPR dan BPR Syariah"
    assert rapikan_judul_ojk(src2) == exp2

    # Contoh 3: Judul bab pendek kapital semua
    src3 = "KETENTUAN UMUM"
    exp3 = "Ketentuan Umum"
    assert rapikan_judul_ojk(src3) == exp3

    # Contoh 4: Teks huruf campuran wajar (tidak boleh diubah)
    src4 = "Penerapan Manajemen Risiko dalam Penggunaan Teknologi Informasi"
    assert rapikan_judul_ojk(src4) == src4

    # Contoh 5: Judul kapital dengan nomor regulasi / token khusus
    src5 = "PERUBAHAN ATAS PERATURAN OTORITAS JASA KEUANGAN NOMOR 75/POJK.03/2016"
    exp5 = "Perubahan atas Peraturan Otoritas Jasa Keuangan Nomor 75/POJK.03/2016"
    assert rapikan_judul_ojk(src5) == exp5

    # Contoh 6: None dan string kosong
    assert rapikan_judul_ojk("") == ""
    assert rapikan_judul_ojk(None) is None


def test_unit_rapikan_judul_ojk_kasus_tambahan():
    """Pengujian kasus tambahan: angka romawi, tanda baca menempel, singkatan OJK lain."""
    # Angka romawi
    assert rapikan_judul_ojk("BAB I KETENTUAN UMUM") == "Bab I Ketentuan Umum"
    assert rapikan_judul_ojk("BAB IV TATA KELOLA TI") == "Bab IV Tata Kelola TI"
    assert rapikan_judul_ojk("BAB X SANKSI") == "Bab X Sanksi"

    # Kata sambung di awal kalimat tetap diawali kapital
    assert rapikan_judul_ojk("TENTANG TATA KELOLA BPR") == "Tentang Tata Kelola BPR"
    assert rapikan_judul_ojk("ATAS PERMINTAAN TANGGAPAN") == "Atas Permintaan Tanggapan"

    # Singkatan OJK yang ada dalam daftar
    src = "PENGAWASAN BANK UMUM KONVENSIONAL DAN BANK UMUM SYARIAH OLEH OJK"
    exp = "Pengawasan Bank Umum Konvensional dan Bank Umum Syariah oleh OJK"
    assert rapikan_judul_ojk(src) == exp

    # Token dengan tanda baca menempel
    assert rapikan_judul_ojk("(BPR)") == "(BPR)"
    assert rapikan_judul_ojk("TATA KELOLA (BPR)") == "Tata Kelola (BPR)"
    assert rapikan_judul_ojk("POJK NO. 75/POJK.03/2016") == "POJK No. 75/POJK.03/2016"


def test_unit_rapikan_judul_ojk_tambahan_singkatan_dan_tiap_kata_kapital():
    """
    1. Bila teks TIDAK huruf kapital semua (mode 'Tiap Kata Kapital'),
       token all-caps len >= 2 dibiarkan apa adanya (mis. AI, QRIS, BPJS).
    2. Singkatan baru (ESG, QRIS, dll.) tetap kapital di mode all-caps.
    """
    # Draf AI Fallback Deterministik -> tidak berubah
    assert rapikan_judul_ojk("Draf AI Fallback Deterministik") == "Draf AI Fallback Deterministik"

    # Penggunaan QRIS Oleh Bpr Dan Bprs -> Penggunaan QRIS oleh BPR dan BPRS
    assert rapikan_judul_ojk("Penggunaan QRIS Oleh Bpr Dan Bprs") == "Penggunaan QRIS oleh BPR dan BPRS"

    # PENERAPAN ESG BAGI LJK -> Penerapan ESG bagi LJK
    assert rapikan_judul_ojk("PENERAPAN ESG BAGI LJK") == "Penerapan ESG bagi LJK"


def test_unit_resolve_default_hal_tidak_duplikasi():
    """Pencegahan duplikasi 'Tanggapan atas' pada resolve_default_hal."""
    # Judul kapital semua yang diawali TANGGAPAN ATAS
    judul_upper = "TANGGAPAN ATAS RANCANGAN POJK PASAR MODAL"
    hal = resolve_default_hal(judul_upper)
    assert hal == "Tanggapan atas Rancangan POJK Pasar Modal"
    assert not hal.startswith("Tanggapan atas Tanggapan atas")

    # Judul yang belum diawali Tanggapan atas
    judul_biasa = "RANCANGAN PERATURAN OTORITAS JASA KEUANGAN TENTANG BPR"
    hal_biasa = resolve_default_hal(judul_biasa)
    assert hal_biasa == "Tanggapan atas Rancangan Peraturan Otoritas Jasa Keuangan tentang BPR"


# ===========================================================================
# 2. PENGUJIAN INTEGRASI: DOCX & PDF TANPA BARIS KONSEP
# ===========================================================================
def test_cd_tanpa_baris_konsep_docx_dan_pdf(client: TestClient, db_session: Session):
    """DOCX dan PDF tidak memuat label 'KONSEP —' / 'belum ditandatangani'."""
    draft = create_test_doc(
        title="PENYELENGGARAAN TEKNOLOGI INFORMASI OLEH BANK PEREKONOMIAN RAKYAT DAN BANK PEREKONOMIAN RAKYAT SYARIAH",
        regulation_type="Rancangan POJK",
    )
    db_session.add(draft)
    db_session.commit()

    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    # A. DOCX
    resp_docx = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "docx"},
    )
    assert resp_docx.status_code == 200
    text_docx = extract_docx_text(resp_docx.content)

    assert "CATATAN DINAS" in text_docx
    assert "KONSEP —" not in text_docx
    assert "belum ditandatangani" not in text_docx
    assert "dihasilkan sistem HERO sebagai Draft" not in text_docx

    # B. PDF
    resp_pdf = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "pdf"},
    )
    assert resp_pdf.status_code == 200
    text_pdf = extract_pdf_text(resp_pdf.content)

    assert "CATATAN DINAS" in text_pdf
    assert "KONSEP —" not in text_pdf
    assert "belum ditandatangani" not in text_pdf
    assert "dihasilkan sistem HERO sebagai Draft" not in text_pdf


# ===========================================================================
# 3. PENGUJIAN INTEGRASI: TEKS BAWAAN HAL, BUTIR 1, BUTIR 2 DIRAPIKAN
# ===========================================================================
def test_cd_teks_bawaan_dirapikan_pada_judul_kapital(client: TestClient, db_session: Session):
    """
    Hal bawaan, Butir 1, dan Butir 2 memakai judul yang dirapikan
    bila dokumen draf memiliki judul huruf kapital semua dan bab pola rusak.
    """
    draft = create_test_doc(
        title="PENYELENGGARAAN TEKNOLOGI INFORMASI OLEH BANK PEREKONOMIAN RAKYAT DAN BANK PEREKONOMIAN RAKYAT SYARIAH",
        regulation_type="Rancangan Peraturan Otoritas Jasa Keuangan",
    )
    db_session.add(draft)
    db_session.commit()

    # Seed data analisa untuk Butir 1 (jumlah pasal & bab)
    seed_analisa_result(
        db_session,
        draft,
        {
            "identitas": {"jumlah_pasal": 15},
            "kerangka": [
                {"judul": "KETENTUAN UMUM"},
                {"judul": "Tata Kelola Ti Bpr Dan Bpr Syariah"},
                {"judul": "MANAJEMEN RISIKO TEKNOLOGI INFORMASI"},
            ],
        },
    )

    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    resp = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "docx"},
    )
    assert resp.status_code == 200
    text = extract_docx_text(resp.content)

    judul_rapikan = "Penyelenggaraan Teknologi Informasi oleh Bank Perekonomian Rakyat dan Bank Perekonomian Rakyat Syariah"

    # Hal bawaan harus memuat judul yang dirapikan (bukan huruf kapital semua)
    assert f"Tanggapan atas {judul_rapikan}" in text
    assert "PENYELENGGARAAN TEKNOLOGI INFORMASI OLEH BANK" not in text

    # Butir 1 harus memuat judul dan judul bab yang dirapikan
    assert f"Rancangan Peraturan Otoritas Jasa Keuangan tentang {judul_rapikan}" in text
    assert "Tata Kelola TI BPR dan BPR Syariah" in text
    assert "Manajemen Risiko Teknologi Informasi" in text

    # Butir 2 harus memuat judul yang dirapikan
    assert f"meminta tanggapan atas {judul_rapikan}." in text


# ===========================================================================
# 4. PENGUJIAN INTEGRASI: ISIAN HAL DARI FORM TIDAK DIUBAH
# ===========================================================================
def test_cd_isian_hal_form_tidak_diubah(client: TestClient, db_session: Session):
    """Bila pengguna mengisi 'hal' secara eksplisit di form, nilai tersebut TIDAK boleh diubah sama sekali."""
    draft = create_test_doc(
        title="PENYELENGGARAAN TEKNOLOGI INFORMASI OLEH BANK PEREKONOMIAN RAKYAT",
    )
    db_session.add(draft)
    db_session.commit()

    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    hal_pengguna = "PERIHAL KHUSUS DARI PENGGUNA HURUF BESAR SEMUA DAN TIDAK BOLEH DIRAPIKAN"

    resp = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "docx", "hal": hal_pengguna},
    )
    assert resp.status_code == 200
    text = extract_docx_text(resp.content)

    # Nilai Hal harus persis seperti yang diisi pengguna
    assert hal_pengguna in text


# ===========================================================================
# 5. PENGUJIAN INTEGRASI: BUTIR 1 DENGAN NARASI AI TIDAK DIUBAH
# ===========================================================================
def test_cd_butir_1_narasi_ai_tidak_diubah(client: TestClient, db_session: Session):
    """Bila Butir 1 berasal dari narasi AI (pakai_ai=True), teks narasi TIDAK boleh diubah sama sekali."""
    draft = create_test_doc(
        title="PENYELENGGARAAN TEKNOLOGI INFORMASI OLEH BANK PEREKONOMIAN RAKYAT",
    )
    db_session.add(draft)
    db_session.commit()

    narasi_ai_asli = "INI ADALAH NARASI AI ASLI YANG SENGAJA KAPITAL SEMUA DAN TIDAK BOLEH DIUBAH."

    seed_analisa_result(
        db_session,
        draft,
        {
            "mode_dipakai": "ai",
            "ringkasan_ai": narasi_ai_asli,
            "ai": {"status": "ai", "ringkasan": narasi_ai_asli},
        },
        mode=ModeAnalisa.ai,
    )

    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    resp = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "docx", "pakai_ai": True},
    )
    assert resp.status_code == 200
    text = extract_docx_text(resp.content)

    # Narasi AI harus muncul apa adanya
    assert narasi_ai_asli in text
    assert "Butir 1 disusun dengan bantuan AI dari hasil analisa terverifikasi." in text
