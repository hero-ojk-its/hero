"""
tests/test_ekspor_analisa_csv_aman.py
Pengujian netralisasi formula injection (CSV injection) pada ekspor analisa regulasi:
GET /api/v1/documents/{document_id}/analisa/ekspor?format=csv

Mencakup:
1. Formula injection pada poin utama (kategori, pasal_rujukan, teks, parafrase), ringkasan (teks, pasal_rujukan),
   dasar hukum dan sanksi (teks berawalan =/+).
2. Teks biasa dan angka murni (urutan, halaman) tidak terpengaruh kutip satu; BOM tetap ada.
3. Sel kosong tetap kosong "" (tidak menjadi "'" atau "'None").
4. Endpoint ekspor CSV integrasi bekerja tanpa error dan menetralkan sel berbahaya.
5. Regresi keluaran identik: payload ringkasan dict dengan kunci bagian/kategori/parafrase tetap literal "ringkasan"
   dan kolom kategori/parafrase kosong; poin utama tetap literal "poin_utama"; dasar hukum/sanksi dict menghasilkan str(dict).
6. Pengujian kolom halaman: int 5 -> "5", string "=1+1" -> "'=1+1", None -> "".
"""
import csv
from datetime import date, datetime, timezone
import io
from typing import Optional

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app
from app.models.analysis_result import AnalysisResult
from app.models.category import Category
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
from app.services.analysis_export_service import export_to_csv
from app.services.analysis_result_service import compute_params_hash, get_document_fingerprint
from app.services.storage_service import StorageService
from tests.conftest import make_pdf


def failing_ml_handler(request: httpx.Request) -> httpx.Response:
    pytest.fail(f"Layanan ML dipanggil secara tidak terduga pada pengujian ekspor analisa: {request.url}")


@pytest.fixture(autouse=True)
def setup_ml_config(monkeypatch: pytest.MonkeyPatch):
    """Pastikan ML transport tidak dipanggil dan auth dinonaktifkan untuk pengujian ekspor."""
    monkeypatch.setattr(settings, "ml_service_url", "http://ml-test:8100")
    monkeypatch.setattr(settings, "ml_cache_enabled", True)
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)
    monkeypatch.setattr(settings, "auth_enabled", False)
    app.dependency_overrides[get_ml_client] = lambda: httpx.AsyncClient(transport=httpx.MockTransport(failing_ml_handler))
    yield
    app.dependency_overrides.pop(get_ml_client, None)


# ==============================================================================
# Kasus Uji 1: Formula injection pada kolom teks, parafrase, kategori, pasal_rujukan
# ==============================================================================

def test_01_formula_injection_dinetralkan():
    """
    Sel berawalan '=', '+', '-', '@' pada poin utama (kategori, pasal_rujukan, teks, parafrase),
    ringkasan (teks, pasal_rujukan), dasar hukum, dan sanksi harus dinetralkan dengan awalan '.
    Kolom bagian pada semua baris tetap literal.
    """
    payload = {
        "versi": "v1.0",
        "mode_dipakai": "deterministik",
        "identitas": {
            "jenis": "=POJK",
            "nomor": "+12",
            "tahun": "-2024",
            "tentang": "@Tentang",
        },
        "poin_utama": [
            {
                "id": 1,
                "kategori": "-2*5",
                "pasal": "=Pasal 1",
                "halaman": 5,
                "teks": "=1+1",
                "parafrase": "+cmd",
            }
        ],
        "ringkasan": [
            {
                "kalimat": "=KalimatBahaya",
                "rujukan": ["+Pasal 2"],
            }
        ],
        "dasar_hukum": ["=UU 1/2023"],
        "sanksi": ["+Sanksi denda"],
    }

    raw = export_to_csv(payload)
    assert raw.startswith(b"\xef\xbb\xbf"), "BOM UTF-8 harus ada di awal berkas"

    text = raw.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))

    # Periksa poin_utama lewat teks
    pu_rows = [r for r in rows if r["teks"] == "'=1+1"]
    assert len(pu_rows) == 1, "Baris poin_utama dengan teks '=1+1 harus ditemukan"
    pu = pu_rows[0]
    assert pu["bagian"] == "poin_utama", "bagian harus literal 'poin_utama'"
    assert pu["teks"] == "'=1+1", "teks berawalan = harus diawali kutip satu"
    assert pu["parafrase"] == "'+cmd", "parafrase berawalan + harus diawali kutip satu"
    assert pu["kategori"] == "'-2*5", "kategori berawalan - harus diawali kutip satu"
    assert pu["pasal_rujukan"] == "'=Pasal 1", "pasal_rujukan berawalan = harus diawali kutip satu"

    # Periksa ringkasan lewat bagian
    rg_rows = [r for r in rows if r["bagian"] == "ringkasan"]
    assert len(rg_rows) == 1
    rg = rg_rows[0]
    assert rg["teks"] == "'=KalimatBahaya"
    assert rg["pasal_rujukan"] == "'+Pasal 2"
    assert rg["kategori"] == ""
    assert rg["parafrase"] == ""

    # Periksa dasar hukum dan sanksi
    dh_rows = [r for r in rows if r["bagian"] == "dasar_hukum"]
    assert len(dh_rows) == 1
    assert dh_rows[0]["teks"] == "'=UU 1/2023"

    sk_rows = [r for r in rows if r["bagian"] == "sanksi"]
    assert len(sk_rows) == 1
    assert sk_rows[0]["teks"] == "'+Sanksi denda"


# ==============================================================================
# Kasus Uji 2: Teks biasa dan angka murni tidak berubah, BOM tetap ada
# ==============================================================================

def test_02_teks_biasa_dan_angka_tidak_berubah_dan_bom_ada():
    """
    Teks biasa dan angka murni (urutan, halaman) tidak boleh terpengaruh kutip satu.
    Header kolom dan urutan harus tetap sesuai spesifikasi US-40.
    """
    payload = {
        "versi": "v1.0",
        "mode_dipakai": "deterministik",
        "identitas": {
            "jenis": "POJK",
            "nomor": "11",
            "tahun": 2024,
            "tentang": "Penerapan Manajemen Risiko Bank",
            "status": "Berlaku",
            "tanggal_terbit": "2024-06-15",
            "penerbit": "Otoritas Jasa Keuangan",
            "jumlah_pasal": 45,
        },
        "poin_utama": [
            {
                "id": 1,
                "kategori": "Kewajiban",
                "pasal": "Pasal 2",
                "halaman": 5,
                "teks": "Penyusunan kerangka manajemen risiko wajib disetujui.",
                "parafrase": "Direksi wajib menyetujui kerangka manajemen risiko.",
            }
        ],
    }

    raw = export_to_csv(payload)
    assert raw.startswith(b"\xef\xbb\xbf"), "BOM UTF-8 harus ada di awal berkas"

    text = raw.decode("utf-8-sig")

    # Periksa header
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    assert header == ["bagian", "urutan", "kategori", "pasal_rujukan", "halaman", "teks", "parafrase"]

    rows = list(csv.DictReader(io.StringIO(text)))
    pu_rows = [r for r in rows if r["bagian"] == "poin_utama"]
    assert len(pu_rows) == 1
    pu = pu_rows[0]

    assert pu["urutan"] == "1"
    assert pu["kategori"] == "Kewajiban"
    assert pu["pasal_rujukan"] == "Pasal 2"
    assert pu["halaman"] == "5"
    assert pu["teks"] == "Penyusunan kerangka manajemen risiko wajib disetujui."
    assert pu["parafrase"] == "Direksi wajib menyetujui kerangka manajemen risiko."

    # Pastikan tidak ada kolom pada baris poin_utama yang diawali kutip satu
    for col in ["bagian", "urutan", "kategori", "pasal_rujukan", "halaman", "teks", "parafrase"]:
        val = pu[col]
        assert not val.startswith("'"), f"Kolom {col} dengan nilai '{val}' tidak boleh diawali kutip satu"


# ==============================================================================
# Kasus Uji 3: Sel kosong tetap kosong ""
# ==============================================================================

def test_03_sel_kosong_tetap_kosong():
    """
    Sel kosong atau bernilai None harus tetap menjadi string kosong "" di CSV,
    tidak boleh berubah menjadi "'" atau "'None" atau "None".
    """
    payload = {
        "versi": "v1.0",
        "mode_dipakai": "deterministik",
        "identitas": {
            "jenis": None,
            "nomor": "",
            "tahun": None,
        },
        "poin_utama": [
            {
                "id": 1,
                "kategori": "",
                "pasal": None,
                "halaman": None,
                "teks": "",
                "parafrase": None,
            }
        ],
    }

    raw = export_to_csv(payload)
    text = raw.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))

    pu_rows = [r for r in rows if r["bagian"] == "poin_utama"]
    assert len(pu_rows) == 1
    pu = pu_rows[0]

    assert pu["kategori"] == ""
    assert pu["pasal_rujukan"] == ""
    assert pu["halaman"] == ""
    assert pu["teks"] == ""
    assert pu["parafrase"] == ""

    for col in ["kategori", "pasal_rujukan", "halaman", "teks", "parafrase"]:
        assert pu[col] != "'", f"Kolom {col} tidak boleh bernilai petik satu tunggal"
        assert pu[col] != "'None", f"Kolom {col} tidak boleh bernilai 'None"
        assert pu[col] != "None", f"Kolom {col} tidak boleh bernilai None"


# ==============================================================================
# Kasus Uji 4: Integrasi utuh endpoint GET /api/v1/documents/{doc_id}/analisa/ekspor?format=csv
# ==============================================================================

def test_04_endpoint_ekspor_csv_integrasi(
    client: TestClient, db_session: Session, test_storage: StorageService
):
    """
    Pengujian integrasi endpoint ekspor CSV analisa regulasi:
    1. Mengembalikan status 200 dan tipe konten text/csv.
    2. Berkas diawali UTF-8 BOM.
    3. Formula injection pada data terenkapsulasi dan dinetralkan dengan tepat.
    """
    cat = db_session.query(Category).filter(Category.name == "POJK").first()
    pdf_bytes = make_pdf("Konten Uji Integrasi Ekspor CSV Aman")
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint="uji_formula_analisa.pdf", subdir="kb/POJK/2026")

    doc = Document(
        title="Dokumen Uji Formula Injection Analisa",
        regulation_number="88/POJK.03/2026",
        regulation_type="POJK",
        release_date=date(2026, 1, 1),
        regulation_year=2026,
        file_path_pdf=rel_path,
        file_hash="hash_uji_formula_injection_analisa_csv",
        file_size_bytes=len(pdf_bytes),
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        is_active=True,
        category_id=cat.id if cat else None,
        extracted_at=datetime.now(timezone.utc),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    res_payload = {
        "versi": "v1.0",
        "mode_dipakai": "deterministik",
        "identitas": {
            "jenis": "POJK",
            "nomor": "88",
            "tahun": 2026,
            "tentang": "=2+2",
        },
        "poin_utama": [
            {
                "id": 1,
                "kategori": "-KategoriBahaya",
                "pasal": "=Pasal 88",
                "halaman": 12,
                "teks": "=1+1",
                "parafrase": "+cmd",
            }
        ],
    }

    ar = AnalysisResult(
        document_id=doc.id,
        kind=JenisAnalisa.analisa,
        mode=ModeAnalisa.deterministik,
        params_hash=compute_params_hash(JenisAnalisa.analisa),
        source_fingerprint=get_document_fingerprint(doc),
        result=res_payload,
        ml_version="1.0",
        duration_ms=500,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(ar)
    db_session.commit()

    resp = client.get(f"/api/v1/documents/{doc.id}/analisa/ekspor?format=csv")
    assert resp.status_code == 200
    assert resp.content.startswith(b"\xef\xbb\xbf"), "Ekspor harus berawalan BOM UTF-8"
    assert "text/csv" in resp.headers["content-type"]

    csv_text = resp.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    # Cari baris poin_utama lewat teks yang dinetralkan
    pu_rows = [r for r in rows if r["teks"] == "'=1+1"]
    assert len(pu_rows) == 1
    r = pu_rows[0]
    assert r["bagian"] == "poin_utama", "bagian harus literal 'poin_utama'"
    assert r["teks"] == "'=1+1", "teks berawalan = harus dinetralkan"
    assert r["parafrase"] == "'+cmd", "parafrase berawalan + harus dinetralkan"
    assert r["kategori"] == "'-KategoriBahaya", "kategori berawalan - harus dinetralkan"
    assert r["pasal_rujukan"] == "'=Pasal 88", "pasal_rujukan berawalan = harus dinetralkan"
    assert r["halaman"] == "12", "halaman tidak boleh diawali kutip satu"


# ==============================================================================
# Kasus Uji 5: Regresi keluaran identik dengan data tambahan
# ==============================================================================

def test_05_regresi_keluaran_identik_dengan_data_tambahan():
    """
    1. Ringkasan dict dengan kunci bagian/kategori/parafrase: kolom bagian tetap 'ringkasan',
       kolom kategori dan parafrase tetap kosong "".
    2. Poin utama dict dengan kunci bagian aneh: kolom bagian tetap literal 'poin_utama'.
    3. Dasar hukum & sanksi berisi dict {"teks": "x"}: sel teks berisi str(dict) yang dinetralkan, tidak kosong.
    """
    payload = {
        "versi": "v1.0",
        "mode_dipakai": "deterministik",
        "identitas": {"jenis": "POJK", "nomor": "10", "tahun": 2025},
        "ringkasan": [
            {
                "bagian": "custom_bagian",
                "kategori": "custom_kategori",
                "parafrase": "custom_parafrase",
                "kalimat": "Bank wajib mematuhi ketentuan.",
                "rujukan": ["Pasal 1"],
            }
        ],
        "poin_utama": [
            {
                "bagian": "bagian_aneh",
                "id": 1,
                "kategori": "Kewajiban",
                "pasal": "Pasal 2",
                "halaman": 5,
                "teks": "Penyusunan kerangka manajemen risiko.",
                "parafrase": "Direksi wajib menyetujui.",
            }
        ],
        "dasar_hukum": [{"teks": "x"}],
        "sanksi": [{"teks": "s"}],
    }

    raw = export_to_csv(payload)
    text = raw.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))

    # 1. Ringkasan
    rg_rows = [r for r in rows if r["bagian"] == "ringkasan"]
    assert len(rg_rows) == 1, "Kolom bagian harus tetap literal 'ringkasan'"
    rg = rg_rows[0]
    assert rg["kategori"] == "", "Kolom kategori harus kosong"
    assert rg["parafrase"] == "", "Kolom parafrase harus kosong"
    assert rg["teks"] == "Bank wajib mematuhi ketentuan."
    assert rg["pasal_rujukan"] == "Pasal 1"

    # 2. Poin utama
    pu_rows = [r for r in rows if r["bagian"] == "poin_utama"]
    assert len(pu_rows) == 1, "Kolom bagian harus tetap literal 'poin_utama'"
    pu = pu_rows[0]
    assert pu["kategori"] == "Kewajiban"
    assert pu["teks"] == "Penyusunan kerangka manajemen risiko."

    # 3. Dasar hukum & sanksi
    dh_rows = [r for r in rows if r["bagian"] == "dasar_hukum"]
    assert len(dh_rows) == 1
    assert dh_rows[0]["teks"] == str({"teks": "x"}), "Dasar hukum harus memuat str(dict)"

    sk_rows = [r for r in rows if r["bagian"] == "sanksi"]
    assert len(sk_rows) == 1
    assert sk_rows[0]["teks"] == str({"teks": "s"}), "Sanksi harus memuat str(dict)"


# ==============================================================================
# Kasus Uji 6: Pengujian kolom halaman
# ==============================================================================

def test_06_kolom_halaman():
    """
    Kolom halaman pada poin utama:
    - int 5 -> "5" (tanpa kutip)
    - float 5.5 -> "5.5" (tanpa kutip)
    - string "=1+1" -> "'=1+1" (dinetralkan)
    - string "+10" -> "'+10" (dinetralkan)
    - string "12" -> "12" (tanpa kutip)
    - None -> "" (kosong)
    """
    payload = {
        "versi": "v1.0",
        "mode_dipakai": "deterministik",
        "poin_utama": [
            {"id": 1, "teks": "Poin Int", "halaman": 5},
            {"id": 2, "teks": "Poin Float", "halaman": 5.5},
            {"id": 3, "teks": "Poin Formula Eq", "halaman": "=1+1"},
            {"id": 4, "teks": "Poin Formula Plus", "halaman": "+10"},
            {"id": 5, "teks": "Poin String Num", "halaman": "12"},
            {"id": 6, "teks": "Poin None", "halaman": None},
        ],
    }

    raw = export_to_csv(payload)
    text = raw.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))

    h_map = {r["teks"]: r["halaman"] for r in rows if r["bagian"] == "poin_utama"}
    assert h_map["Poin Int"] == "5"
    assert h_map["Poin Float"] == "5.5"
    assert h_map["Poin Formula Eq"] == "'=1+1"
    assert h_map["Poin Formula Plus"] == "'+10"
    assert h_map["Poin String Num"] == "12"
    assert h_map["Poin None"] == ""
