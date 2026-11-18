"""
tests/test_ekspor_keamanan_sel.py
Pengujian keamanan sel dan ekspor:
1. CSV ekspor harmonisasi: kutipan berawalan =, +, -, @ dinetralkan dengan awalan '; teks biasa tidak berubah; BOM tetap ada.
2. CSV rekap tanggapan & catatan analis: awalan = dinetralkan; catatan biasa tidak berubah.
3. Fungsi pembantu netralkan_sel_csv: None, string kosong, angka, teks biasa tidak berubah; tab dan carriage return dinetralkan.
4. Skrip sampling: temuan dengan pembanding nonaktif dan yang dokumennya tidak ada tidak ikut sampel;
   hitungan 'Temuan dilewati (pembanding nonaktif)' benar; temuan tanpa document_id tetap eligible;
   konsol tidak memuat judul/kutipan; DB tidak berubah.
5. Sel Excel 33.000 karakter dipotong menjadi <= 32.767 dan berakhiran '[dipotong]'; sel 100 karakter tidak berubah;
   berkas hasil dapat dibuka openpyxl.
"""
import csv
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import subprocess
import sys
import uuid

from fastapi.testclient import TestClient
import openpyxl
import pytest
from sqlalchemy.orm import Session

from app.config import settings
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
from app.models.tanggapan_temuan import TanggapanTemuan
from app.services.harmonisasi_export_service import (
    clean_cell_text,
    export_harmonisasi_to_xlsx,
    netralkan_sel_csv,
)
from scripts.buat_lembar_sampling import (
    PESAN_PERINGATAN_NON_PUBLIK,
    jalankan_buat_lembar_sampling,
)

BASE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ml_service_url", "http://ml-test:8100")
    monkeypatch.setattr(settings, "ml_cache_enabled", True)
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)
    monkeypatch.setattr(settings, "auth_enabled", False)
    yield


def create_test_doc(**kwargs) -> Document:
    rnd = uuid.uuid4().hex
    data = {
        "title": "Draf Kajian Instrumen Pasar Modal",
        "regulation_type": "POJK",
        "regulation_number": "15/POJK.04/2026",
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


def seed_harmonisasi_result(db: Session, doc: Document, payload: dict) -> AnalysisResult:
    res = AnalysisResult(
        document_id=doc.id,
        kind=JenisAnalisa.harmonisasi,
        mode=ModeAnalisa.deterministik,
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


# ==============================================================================
# 1. CSV ekspor harmonisasi aman dari formula injection
# ==============================================================================
def test_01_csv_ekspor_harmonisasi_formula_injection(client: TestClient, db_session: Session):
    draft = create_test_doc(title="Draf CSV Formula Test")
    comp = create_test_doc(title="Regulasi Pembanding 1", regulation_number="POJK 1/2024")
    db_session.add_all([draft, comp])
    db_session.commit()

    temuan = [
        {
            "id": "t-1",
            "jenis": "sama",
            "pasal_draft": "Pasal 1",
            "pembanding": {"document_id": comp.id, "nomor": "POJK 1/2024", "pasal": "Pasal 10"},
            "alasan": "=1+1",
        },
        {
            "id": "t-2",
            "jenis": "menggantikan",
            "pasal_draft": "Pasal 2",
            "pembanding": {"document_id": comp.id, "nomor": "POJK 1/2024", "pasal": "Pasal 20"},
            "alasan": "+cmd",
        },
        {
            "id": "t-3",
            "jenis": "melengkapi",
            "pasal_draft": "Pasal 3",
            "pembanding": {"document_id": comp.id, "nomor": "POJK 1/2024", "pasal": "Pasal 30"},
            "alasan": "-2*5",
        },
        {
            "id": "t-4",
            "jenis": "konflik",
            "pasal_draft": "Pasal 4",
            "pembanding": {"document_id": comp.id, "nomor": "POJK 1/2024", "pasal": "Pasal 40"},
            "alasan": "@SUM(A1)",
        },
        {
            "id": "t-5",
            "jenis": "sama",
            "pasal_draft": "Pasal 5",
            "pembanding": {"document_id": comp.id, "nomor": "POJK 1/2024", "pasal": "Pasal 50"},
            "alasan": "Ketentuan batas modal disesuaikan dengan standar OJK.",
        },
    ]

    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": temuan})

    resp = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert resp.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM tetap ada

    csv_text = resp.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    header = rows[0]
    uraian_idx = header.index("Uraian Temuan")

    # Baris data: 5 temuan
    assert len(rows) == 6
    assert rows[1][uraian_idx] == "'=1+1"
    assert rows[2][uraian_idx] == "'+cmd"
    assert rows[3][uraian_idx] == "'-2*5"
    assert rows[4][uraian_idx] == "'@SUM(A1)"
    assert rows[5][uraian_idx] == "Ketentuan batas modal disesuaikan dengan standar OJK."


# ==============================================================================
# 2. CSV rekap tanggapan & catatan analis dinetralkan
# ==============================================================================
def test_02_csv_rekap_tanggapan_dan_catatan_analis(client: TestClient, db_session: Session):
    draft = create_test_doc(title="Draf Rekap Formula Test")
    comp = create_test_doc(title="Pembanding Rekap", regulation_number="POJK 2/2024")
    db_session.add_all([draft, comp])
    db_session.commit()

    # 1. Tes CSV rekap tanggapan (endpoint /api/v1/harmonisasi/tanggapan/rekap?format=csv)
    tg_bahaya = TanggapanTemuan(
        document_id=draft.id,
        kunci_temuan="kunci-bahaya-rekap",
        penilaian="valid",
        catatan="Catatan uji rekap",
        ringkasan_temuan={"jenis": "=bahaya_formula", "alasan": "Uji bahaya"},
        dibuat=datetime.now(timezone.utc),
        diperbarui=datetime.now(timezone.utc),
    )
    tg_biasa = TanggapanTemuan(
        document_id=draft.id,
        kunci_temuan="kunci-biasa-rekap",
        penilaian="tidak_relevan",
        catatan="Catatan biasa",
        ringkasan_temuan={"jenis": "baru", "alasan": "Uji biasa"},
        dibuat=datetime.now(timezone.utc),
        diperbarui=datetime.now(timezone.utc),
    )
    db_session.add_all([tg_bahaya, tg_biasa])
    db_session.commit()

    res_rekap = client.get(f"/api/v1/harmonisasi/tanggapan/rekap?document_id={draft.id}&format=csv")
    assert res_rekap.status_code == 200
    assert res_rekap.content.startswith(b"\xef\xbb\xbf")
    rekap_text = res_rekap.content.decode("utf-8-sig")
    r_reader = list(csv.reader(io.StringIO(rekap_text)))

    # Kolom: jenis, valid, tidak_relevan, total
    # Baris '=bahaya_formula' harus ternetralkan menjadi ''=bahaya_formula'
    jenis_col_vals = [r[0] for r in r_reader[1:]]
    assert "'=bahaya_formula" in jenis_col_vals
    assert "baru" in jenis_col_vals

    # 2. Tes catatan analis di ekspor CSV harmonisasi
    temuan = [
        {
            "id": "t-cat-1",
            "jenis": "sama",
            "pasal_draft": "Pasal 1",
            "pembanding": {"document_id": comp.id, "nomor": "POJK 2/2024", "pasal": "Pasal 1"},
            "alasan": "Alasan 1",
        },
        {
            "id": "t-cat-2",
            "jenis": "baru",
            "pasal_draft": "Pasal 2",
            "pembanding": {"document_id": comp.id, "nomor": "POJK 2/2024", "pasal": "Pasal 2"},
            "alasan": "Alasan 2",
        },
    ]
    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": temuan})

    # Simpan tanggapan via endpoint agar kunci_temuan server-side terasosiasi secara tepat
    client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={
            "temuan": temuan[0],
            "penilaian": "valid",
            "catatan": "=SUM(B2:B10)",
            "dinilai_oleh_nama": "Analis Formula",
        },
    )
    client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={
            "temuan": temuan[1],
            "penilaian": "tidak_relevan",
            "catatan": "Catatan biasa analis untuk evaluasi",
            "dinilai_oleh_nama": "Analis Biasa",
        },
    )

    res_exp = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=csv")
    assert res_exp.status_code == 200
    exp_reader = list(csv.reader(io.StringIO(res_exp.content.decode("utf-8-sig"))))
    header = exp_reader[0]
    cat_idx = header.index("Catatan Analis")

    # Catatan berawalan '=' dinetralkan menjadi "'=SUM(B2:B10)"
    assert exp_reader[1][cat_idx] == "'=SUM(B2:B10)"
    # Catatan biasa tidak berubah
    assert exp_reader[2][cat_idx] == "Catatan biasa analis untuk evaluasi"


# ==============================================================================
# 3. Unit test fungsi pembantu netralkan_sel_csv
# ==============================================================================
def test_03_fungsi_pembantu_netralkan_sel_csv():
    # None dan string kosong tidak berubah
    assert netralkan_sel_csv(None) is None
    assert netralkan_sel_csv("") == ""

    # Angka murni tidak berubah
    assert netralkan_sel_csv(0) == 0
    assert netralkan_sel_csv(42) == 42
    assert netralkan_sel_csv(3.14159) == 3.14159

    # Teks biasa tidak berubah
    assert netralkan_sel_csv("Pasal 10 ayat (1)") == "Pasal 10 ayat (1)"
    assert netralkan_sel_csv("Peraturan Otoritas Jasa Keuangan") == "Peraturan Otoritas Jasa Keuangan"

    # Awalan tab dan carriage return dinetralkan
    assert netralkan_sel_csv("\talert('xss')") == "'\talert('xss')"
    assert netralkan_sel_csv("\ralert('xss')") == "'\ralert('xss')"

    # Awalan karakter rumus (=, +, -, @) dinetralkan
    assert netralkan_sel_csv("=1+1") == "'=1+1"
    assert netralkan_sel_csv("+cmd") == "'+cmd"
    assert netralkan_sel_csv("-2*5") == "'-2*5"
    assert netralkan_sel_csv("@SUM(A1)") == "'@SUM(A1)"


# ==============================================================================
# 4. Skrip sampling: pembanding nonaktif dan hilang dilewati, read-only
# ==============================================================================
def test_04_skrip_sampling_pembanding_nonaktif(
    db_session: Session, tmp_path: Path
):
    draft = create_test_doc(title="Draf Rahasia Internal Super")
    comp_aktif = create_test_doc(title="POJK Aktif 2026", regulation_number="POJK 1/2026", is_active=True)
    comp_inaktif = create_test_doc(title="POJK Inaktif 2020", regulation_number="POJK 2/2020", is_active=False)
    db_session.add_all([draft, comp_aktif, comp_inaktif])
    db_session.commit()

    temuan = [
        # Temuan 1: Pembanding aktif -> eligible
        {
            "id": "t-aktif",
            "jenis": "sama",
            "pasal_draft": "Pasal 1",
            "pembanding": {
                "document_id": comp_aktif.id,
                "nomor": "POJK 1/2026",
                "pasal": "Pasal 11",
                "kutipan": "Kutipan aktif",
            },
        },
        # Temuan 2: Pembanding nonaktif -> HARUS DILEWATI
        {
            "id": "t-inaktif",
            "jenis": "konflik",
            "pasal_draft": "Pasal 2",
            "pembanding": {
                "document_id": comp_inaktif.id,
                "nomor": "POJK 2/2020",
                "pasal": "Pasal 12",
                "kutipan": "Kutipan inaktif rahasia",
            },
        },
        # Temuan 3: Pembanding ID tidak ada di DB -> HARUS DILEWATI
        {
            "id": "t-tidak-ada",
            "jenis": "melengkapi",
            "pasal_draft": "Pasal 3",
            "pembanding": {
                "document_id": 99999999,
                "nomor": "POJK Gaib",
                "pasal": "Pasal 13",
                "kutipan": "Kutipan dokumen hilang",
            },
        },
        # Temuan 4: Tanpa document_id -> TETAP ELIGIBLE
        {
            "id": "t-tanpa-doc-id",
            "jenis": "menggantikan",
            "pasal_draft": "Pasal 4",
            "pembanding": {
                "nomor": "POJK 99/2020",
                "pasal": "Pasal 14",
                "kutipan": "Kutipan rujukan luar",
            },
        },
    ]

    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": temuan})

    out_xlsx = tmp_path / "lembar_sampling_filter_nonaktif.xlsx"
    hasil = jalankan_buat_lembar_sampling(
        db=db_session,
        document_ids=[draft.id],
        per_dokumen=10,
        seed=42,
        keluaran=str(out_xlsx),
    )

    # Verifikasi hitungan
    assert hasil["dokumen_diproses"] == 1
    assert hasil["dokumen_dilewati"] == 0
    assert hasil["temuan_dilewati_pembanding_nonaktif"] == 2
    assert hasil["sampel_ditulis"] == 2  # Hanya temuan 1 dan temuan 4

    # Verifikasi isi sheet sampel
    wb = openpyxl.load_workbook(out_xlsx)
    ws_sampel = wb["Sampel"]
    rows = list(ws_sampel.iter_rows(values_only=True))
    assert len(rows) == 3  # Header + 2 baris sampel

    pasal_draf_sampled = [r[2] for r in rows[1:]]
    assert "Pasal 1" in pasal_draf_sampled
    assert "Pasal 4" in pasal_draf_sampled
    assert "Pasal 2" not in pasal_draf_sampled
    assert "Pasal 3" not in pasal_draf_sampled

    # Verifikasi eksekusi CLI: format ringkasan benar dan tidak mencetak judul atau kutipan rahasia
    cmd = [
        sys.executable,
        str(BASE_DIR / "scripts" / "buat_lembar_sampling.py"),
        "--document-id",
        str(draft.id),
        "--keluaran",
        str(tmp_path / "out_cli.xlsx"),
    ]
    sub_env = dict(os.environ)
    sub_env["DATABASE_URL"] = db_session.bind.url.render_as_string(hide_password=False)
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR), env=sub_env)
    assert proc.returncode == 0
    stdout_txt = proc.stdout

    assert PESAN_PERINGATAN_NON_PUBLIK in stdout_txt
    assert "Temuan dilewati (pembanding nonaktif): 2" in stdout_txt
    assert "Dokumen diproses : 1" in stdout_txt
    assert "Sampel ditulis   : 2" in stdout_txt
    assert "Draf Rahasia Internal Super" not in stdout_txt
    assert "Kutipan inaktif rahasia" not in stdout_txt
    assert "Kutipan dokumen hilang" not in stdout_txt

    # Verifikasi status DB tidak berubah (read-only)
    doc_after = db_session.query(Document).filter(Document.id == draft.id).first()
    assert doc_after.title == "Draf Rahasia Internal Super"
    assert doc_after.is_active is True
    comp_inaktif_after = db_session.query(Document).filter(Document.id == comp_inaktif.id).first()
    assert comp_inaktif_after.is_active is False


# ==============================================================================
# 5. Batas panjang sel Excel: 33.000 karakter dipotong menjadi <= 32.767
# ==============================================================================
def test_05_batas_panjang_sel_excel_32k(db_session: Session):
    # 1. Unit test clean_cell_text
    teks_33k = "X" * 33000
    cleaned_33k = clean_cell_text(teks_33k)
    assert len(cleaned_33k) <= 32767
    assert len(cleaned_33k) == 32000 + len(" … [dipotong]")
    assert cleaned_33k.endswith(" … [dipotong]")

    teks_100 = "Y" * 100
    cleaned_100 = clean_cell_text(teks_100)
    assert len(cleaned_100) == 100
    assert cleaned_100 == teks_100

    # 2. Integrasi ke ekspor xlsx sebenarnya
    draft = create_test_doc(title="Draf Panjang Sel Excel")
    comp = create_test_doc(title="Pembanding Panjang", is_active=True)
    db_session.add_all([draft, comp])
    db_session.commit()

    temuan = [
        {
            "id": "t-panjang",
            "jenis": "sama",
            "pasal_draft": "Pasal 1",
            "pembanding": {
                "document_id": comp.id,
                "nomor": "POJK 1/2026",
                "pasal": "Pasal 1",
                "kutipan": "Z" * 33000,
            },
            "alasan": "W" * 33000,
        }
    ]

    xlsx_bytes = export_harmonisasi_to_xlsx(
        doc_model=draft,
        data={"versi": "1.0", "temuan": temuan},
        mode="deterministik",
        dibuat_at=datetime.now(timezone.utc),
        diekspor_at=datetime.now(timezone.utc),
    )

    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws_temuan = wb["Temuan"]
    rows = list(ws_temuan.iter_rows(values_only=True))
    assert len(rows) == 2  # Header + 1 baris temuan

    # Kolom 6 (index 5): Kutipan pembanding
    val_kutipan = str(rows[1][5])
    assert len(val_kutipan) <= 32767
    assert val_kutipan.endswith(" … [dipotong]")

    # Kolom 8 (index 7): Alasan
    val_alasan = str(rows[1][7])
    assert len(val_alasan) <= 32767
    assert val_alasan.endswith(" … [dipotong]")
