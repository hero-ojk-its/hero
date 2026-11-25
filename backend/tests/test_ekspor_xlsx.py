"""
tests/test_ekspor_xlsx.py
Pengujian untuk fitur ekspor Excel (.xlsx) laporan harmonisasi dan skrip lembar sampling validasi DPEA.

Mencakup:
1. format=xlsx -> 200, media type benar, openpyxl load_workbook berhasil, ada sheet 'Ringkasan' dan 'Temuan'.
2. Sheet 'Temuan' memuat SEMUA temuan (valid, tidak relevan, belum dinilai), urut pasal draf, termasuk pasal_baru.
3. Keamanan formula injection: sel berawalan =, +, -, @ tersimpan sebagai tipe data string ('s'), bukan rumus.
4. Pembanding tidak boleh dilihat -> tersaring (nonaktif dibuang / restricted dimask).
5. Validasi: bukan draft -> 422; belum diharmonisasi -> 404; tanpa izin ekspor -> 403; format salah -> 422.
6. Audit log EXPORT_HARMONIZATION dengan format 'xlsx'.
7. Skrip buat_lembar_sampling.py: menghasilkan xlsx, K sampel per dokumen, seed sama -> isi sama,
   pasal_baru tidak ikut, pasal draf unik, dokumen tanpa hasil dilewati, konsol tidak memuat judul/kutipan,
   DB tidak berubah (read-only).
8. Kompatibilitas dengan tes ekspor lama.
"""
from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
import subprocess
import sys
import uuid

from fastapi.testclient import TestClient
import jwt
import openpyxl
import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import PeranPengguna
from app.main import app
from app.models.analysis_result import AnalysisResult
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.enums import (
    JenisAnalisa,
    KlasifikasiAkses,
    ModeAnalisa,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
)
from app.models.user import User
from app.routers.auth import ALGORITHM
from app.routers.ml_gateway import get_ml_client
from app.services.audit_service import EXPORT_HARMONIZATION
from scripts.buat_lembar_sampling import (
    PESAN_PERINGATAN_NON_PUBLIK,
    jalankan_buat_lembar_sampling,
)

BASE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def setup_ml_test_env(monkeypatch: pytest.MonkeyPatch):
    """Pastikan konfigurasi ML aktif dan terisolasi untuk tiap pengujian."""
    monkeypatch.setattr(settings, "ml_service_url", "http://ml-test:8100")
    monkeypatch.setattr(settings, "ml_cache_enabled", True)
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)
    monkeypatch.setattr(settings, "auth_enabled", False)
    yield
    app.dependency_overrides.pop(get_ml_client, None)


def _buat_token_auth(user: User) -> str:
    """Helper membuat JWT token untuk user test."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username,
        "exp": now + timedelta(hours=2),
        "iat": now,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_test_doc(**kwargs) -> Document:
    """Helper membuat instance Document valid dengan nilai default NOT NULL."""
    rnd = uuid.uuid4().hex
    data = {
        "title": "Draf Kajian Reksa Dana Pasar Uang",
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
    """Helper membuat baris cache analysis_results harmonisasi."""
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


# ==============================================================================
# KASUS 1: format=xlsx -> 200, media type benar, load_workbook, Ringkasan & Temuan
# ==============================================================================
def test_x01_ekspor_xlsx_berhasil_200_dua_sheet(client: TestClient, db_session: Session):
    """1. format=xlsx -> 200, media type benar, openpyxl.load_workbook, sheet Ringkasan dan Temuan."""
    draft = create_test_doc()
    comp = create_test_doc(title="POJK Tata Kelola", regulation_number="POJK 4/2024")
    db_session.add_all([draft, comp])
    db_session.commit()

    cached_payload = {
        "versi": "1.0",
        "ringkasan": {"total_temuan": 2},
        "temuan": [
            {
                "id": "t1",
                "jenis": "sama",
                "pasal_draft": "Pasal 2",
                "kutipan_draft": "Kewajiban pelaporan berkala setiap semester.",
                "pembanding": {
                    "document_id": comp.id,
                    "nomor": "POJK 4/2024",
                    "judul": "POJK Tata Kelola",
                    "pasal": "Pasal 10",
                    "kutipan": "Laporan disampaikan tiap semester.",
                },
                "tingkat": "tinggi",
                "keyakinan": 0.92,
                "alasan": "Klausul pelaporan identik.",
            },
            {
                "id": "t2",
                "jenis": "konflik",
                "pasal_draft": "Pasal 8",
                "kutipan_draft": "Modal disetor minimal Rp 50 miliar.",
                "pembanding": {
                    "document_id": comp.id,
                    "nomor": "POJK 4/2024",
                    "judul": "POJK Tata Kelola",
                    "pasal": "Pasal 15",
                    "kutipan": "Modal disetor minimal Rp 100 miliar.",
                },
                "tingkat": "sedang",
                "keyakinan": 0.75,
                "alasan": "Batas minimal modal bertentangan.",
            },
        ],
    }
    seed_harmonisasi_result(db_session, draft, cached_payload)

    resp = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=xlsx")
    assert resp.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in resp.headers["content-type"]
    assert 'attachment; filename="' in resp.headers.get("content-disposition", "")
    assert ".xlsx" in resp.headers.get("content-disposition", "")

    # Validasi openpyxl dapat membuka berkas
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    assert "Ringkasan" in wb.sheetnames
    assert "Temuan" in wb.sheetnames

    # Periksa Sheet Ringkasan
    ws_r = wb["Ringkasan"]
    assert ws_r.freeze_panes == "A2"
    r_text_cells = [str(ws_r.cell(row=r, column=2).value) for r in range(1, 20)]
    assert any(draft.title in txt for txt in r_text_cells)
    assert any("Draft / Rekomendasi - keluaran sistem bukan keputusan" in txt for txt in r_text_cells)

    # Periksa Sheet Temuan
    ws_t = wb["Temuan"]
    assert ws_t.freeze_panes == "A2"
    headers = [ws_t.cell(row=1, column=c).value for c in range(1, 11)]
    assert headers == [
        "No",
        "Pasal draf",
        "Kutipan draf",
        "Jenis",
        "Peraturan pembanding",
        "Kutipan pembanding",
        "Keyakinan",
        "Alasan",
        "Penilaian analis",
        "Catatan analis",
    ]


# ==============================================================================
# KASUS 2: Sheet Temuan memuat SEMUA temuan, urut pasal, termasuk pasal_baru
# ==============================================================================
def test_x02_sheet_temuan_semua_temuan_urut_pasal_termasuk_pasal_baru(client: TestClient, db_session: Session):
    """2. Sheet Temuan memuat SEMUA temuan (valid, tidak relevan, belum dinilai), urut pasal, termasuk pasal_baru."""
    draft = create_test_doc()
    comp = create_test_doc(title="POJK Standar Modal", regulation_number="POJK 8/2023")
    db_session.add_all([draft, comp])
    db_session.commit()

    cached_payload = {
        "versi": "1.0",
        "ringkasan": {"total_temuan": 4},
        "temuan": [
            {
                "id": "t-10",
                "jenis": "sama",
                "pasal_draft": "Pasal 10",
                "kutipan_draft": "Ketentuan penutup berlaku 1 tahun.",
                "pembanding": {"document_id": comp.id, "nomor": "8", "judul": "POJK Standar Modal", "pasal": "Pasal 50"},
                "tingkat": "tinggi",
                "keyakinan": 0.88,
                "alasan": "Ketentuan penutup sama.",
            },
            {
                "id": "t-2",
                "jenis": "pasal_baru",
                "pasal_draft": "Pasal 2",
                "kutipan_draft": "Pengaturan teknologi finansial kecerdasan buatan.",
                "pembanding": None,
                "alasan": "Pengaturan baru belum ada di regulasi sebelumnya.",
            },
            {
                "id": "t-1",
                "jenis": "menggantikan",
                "pasal_draft": "Pasal 1",
                "kutipan_draft": "Definisi instrumen investasi syariah.",
                "pembanding": {"document_id": comp.id, "nomor": "8", "judul": "POJK Standar Modal", "pasal": "Pasal 1"},
                "tingkat": "sedang",
                "keyakinan": 0.70,
                "alasan": "Menggantikan definisi lama.",
            },
            {
                "id": "t-5",
                "jenis": "melengkapi",
                "pasal_draft": "Pasal 5",
                "kutipan_draft": "Kriteria manajemen risiko operasional.",
                "pembanding": {"document_id": comp.id, "nomor": "8", "judul": "POJK Standar Modal", "pasal": "Pasal 12"},
                "tingkat": "tinggi",
                "keyakinan": 0.85,
                "alasan": "Melengkapi pedoman operasional.",
            },
        ],
    }
    seed_harmonisasi_result(db_session, draft, cached_payload)

    # Beri penilaian analis:
    # t-1: Valid
    client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": cached_payload["temuan"][2], "penilaian": "valid", "catatan": "Disetujui"},
    )
    # t-2 (pasal_baru): Tidak Relevan
    client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": cached_payload["temuan"][1], "penilaian": "tidak_relevan", "catatan": "Bukan cakupan"},
    )
    # t-10 dan t-5 dibiarkan Belum Dinilai

    resp = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=xlsx")
    assert resp.status_code == 200

    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws_t = wb["Temuan"]

    # Harus ada 4 baris data (baris 2..5)
    rows_data = []
    for r in range(2, 6):
        rows_data.append({
            "no": ws_t.cell(row=r, column=1).value,
            "pasal": ws_t.cell(row=r, column=2).value,
            "kutipan": ws_t.cell(row=r, column=3).value,
            "jenis": ws_t.cell(row=r, column=4).value,
            "pembanding": ws_t.cell(row=r, column=5).value,
            "penilaian": ws_t.cell(row=r, column=9).value,
            "catatan": ws_t.cell(row=r, column=10).value,
        })

    # Urutan alami pasal: Pasal 1, Pasal 2, Pasal 5, Pasal 10
    assert rows_data[0]["pasal"] == "Pasal 1"
    assert rows_data[0]["jenis"] == "Menggantikan"
    assert rows_data[0]["penilaian"] == "Valid"
    assert rows_data[0]["catatan"] == "Disetujui"

    assert rows_data[1]["pasal"] == "Pasal 2"
    assert rows_data[1]["jenis"] == "Pasal Baru"
    assert rows_data[1]["pembanding"] == "-"  # pasal_baru pembanding null tidak error
    assert rows_data[1]["penilaian"] == "Tidak relevan"

    assert rows_data[2]["pasal"] == "Pasal 5"
    assert rows_data[2]["jenis"] == "Selaras / Melengkapi"
    assert rows_data[2]["penilaian"] == "Belum dinilai"

    assert rows_data[3]["pasal"] == "Pasal 10"
    assert rows_data[3]["jenis"] == "Tumpang Tindih"
    assert rows_data[3]["penilaian"] == "Belum dinilai"

    # Periksa Ringkasan jumlah
    ws_r = wb["Ringkasan"]
    r_map = {ws_r.cell(row=r, column=1).value: ws_r.cell(row=r, column=2).value for r in range(2, 20)}
    assert r_map.get("Total Temuan") == 4
    assert r_map.get("Temuan - Pasal Baru") == 1
    assert r_map.get("Temuan - Tumpang Tindih") == 1
    assert r_map.get("Temuan - Menggantikan") == 1
    assert r_map.get("Temuan - Selaras / Melengkapi") == 1
    assert r_map.get("Penilaian - Valid") == 1
    assert r_map.get("Penilaian - Tidak Relevan") == 1
    assert r_map.get("Penilaian - Belum dinilai") == 2


# ==============================================================================
# KASUS 3: Keamanan Formula Injection: string diawali =, +, -, @ diset string
# ==============================================================================
def test_x03_formula_injection_safety_semua_sel_string(client: TestClient, db_session: Session):
    """3. Kutipan berawalan =1+1, +cmd, -2, @SUM(A1) tersimpan sebagai teks (tipe sel string, bukan rumus)."""
    draft = create_test_doc()
    comp = create_test_doc()
    db_session.add_all([draft, comp])
    db_session.commit()

    cached_payload = {
        "versi": "1.0",
        "ringkasan": {"total_temuan": 4},
        "temuan": [
            {
                "id": "t-f1",
                "jenis": "sama",
                "pasal_draft": "Pasal 1",
                "kutipan_draft": "=1+1",
                "pembanding": {"document_id": comp.id, "nomor": "1", "judul": "POJK 1", "kutipan": "=SUM(A1:B10)"},
                "alasan": "=HYPERLINK(\"http://evil.com\")",
            },
            {
                "id": "t-f2",
                "jenis": "konflik",
                "pasal_draft": "Pasal 2",
                "kutipan_draft": "+cmd|' /C calc'!A0",
                "pembanding": {"document_id": comp.id, "nomor": "2", "judul": "POJK 2", "kutipan": "+5-3"},
                "alasan": "+100/2",
            },
            {
                "id": "t-f3",
                "jenis": "menggantikan",
                "pasal_draft": "Pasal 3",
                "kutipan_draft": "-2*5",
                "pembanding": {"document_id": comp.id, "nomor": "3", "judul": "POJK 3", "kutipan": "-99"},
                "alasan": "-10",
            },
            {
                "id": "t-f4",
                "jenis": "melengkapi",
                "pasal_draft": "Pasal 4\x08",  # Karakter kontrol
                "kutipan_draft": "@SUM(A1:A5)\x0b\x0c",
                "pembanding": {"document_id": comp.id, "nomor": "4", "judul": "POJK 4", "kutipan": "@AVERAGE(B1:B5)"},
                "alasan": "@INDIRECT(\"C1\")",
            },
        ],
    }
    seed_harmonisasi_result(db_session, draft, cached_payload)

    resp = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=xlsx")
    assert resp.status_code == 200

    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws_t = wb["Temuan"]

    # Pastikan TIDAK ADA sel rumus sama sekali di sheet Temuan
    for row in ws_t.iter_rows(min_row=1, max_row=5, min_col=1, max_col=10):
        for cell in row:
            assert cell.data_type != "f", f"Sel {cell.coordinate} memiliki data_type='f' (rumus)! Nilai: {cell.value}"

    # Pastikan sel kutipan dan alasan bernilai teks yang tepat
    c_f1 = ws_t.cell(row=2, column=3)
    assert c_f1.data_type == "s"
    assert c_f1.value == "=1+1"

    c_f2 = ws_t.cell(row=3, column=3)
    assert c_f2.data_type == "s"
    assert c_f2.value == "+cmd|' /C calc'!A0"

    c_f3 = ws_t.cell(row=4, column=3)
    assert c_f3.data_type == "s"
    assert c_f3.value == "-2*5"

    c_f4 = ws_t.cell(row=5, column=3)
    assert c_f4.data_type == "s"
    assert c_f4.value == "@SUM(A1:A5)"

    # Karakter kontrol harus sudah dibuang
    c_pasal4 = ws_t.cell(row=5, column=2)
    assert "\x00" not in str(c_pasal4.value)
    assert "\x08" not in str(c_pasal4.value)


# ==============================================================================
# KASUS 4: Pembanding tidak boleh dilihat -> tersaring seperti format lama
# ==============================================================================
def test_x04_penyaringan_pembanding_tidak_boleh_dilihat(client: TestClient, db_session: Session):
    """4. Pembanding tidak boleh dilihat -> tersaring seperti format lama (nonaktif disaring, restricted dimask)."""
    draft = create_test_doc()
    comp_aktif = create_test_doc(title="Pembanding Publik Aktif", is_active=True)
    comp_nonaktif = create_test_doc(title="Pembanding Nonaktif", is_active=False)
    db_session.add_all([draft, comp_aktif, comp_nonaktif])
    db_session.commit()

    cached_payload = {
        "versi": "1.0",
        "ringkasan": {"total_temuan": 3},
        "temuan": [
            {
                "id": "t-aktif",
                "jenis": "sama",
                "pasal_draft": "Pasal 1",
                "kutipan_draft": "Ketentuan terbuka.",
                "pembanding": {
                    "document_id": comp_aktif.id,
                    "nomor": "POJK 1",
                    "judul": "Pembanding Publik Aktif",
                    "pasal": "Pasal 1",
                },
            },
            {
                "id": "t-nonaktif",
                "jenis": "konflik",
                "pasal_draft": "Pasal 2",
                "kutipan_draft": "Ketentuan dokumen nonaktif.",
                "pembanding": {
                    "document_id": comp_nonaktif.id,
                    "nomor": "POJK Nonaktif",
                    "judul": "Pembanding Nonaktif",
                    "pasal": "Pasal 2",
                },
            },
            {
                "id": "t-restricted",
                "jenis": "melengkapi",
                "pasal_draft": "Pasal 3",
                "kutipan_draft": "Ketentuan dokumen rahasia.",
                "pembanding": {
                    "document_id": comp_aktif.id,
                    "restricted": True,
                    "nomor": "POJK Rahasia",
                    "judul": "POJK Rahasia Negara",
                    "pasal": "Pasal 3",
                },
            },
        ],
    }
    seed_harmonisasi_result(db_session, draft, cached_payload)

    resp = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=xlsx")
    assert resp.status_code == 200

    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws_t = wb["Temuan"]

    # Temuan dengan pembanding nonaktif disaring oleh saring_rujukan (dibuang)
    # Temuan tersisa: t-aktif dan t-restricted
    pembanding_col_values = [ws_t.cell(row=r, column=5).value for r in range(2, 10) if ws_t.cell(row=r, column=5).value]
    assert any("Pembanding Publik Aktif" in str(v) for v in pembanding_col_values)
    assert not any("Pembanding Nonaktif" in str(v) for v in pembanding_col_values)

    # Temuan restricted harus dimask sebagai 'peraturan pembanding (akses dibatasi)'
    assert any("peraturan pembanding (akses dibatasi)" in str(v) for v in pembanding_col_values)


# ==============================================================================
# KASUS 5: Validasi: bukan draf -> 422, belum harmonisasi -> 404, izin -> ditolak
# ==============================================================================
def test_x05_validasi_akses_dan_galat(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch):
    """5. Bukan draf -> 422; belum diharmonisasi -> 404; tanpa izin ekspor -> ditolak; format salah -> 422."""
    # A. Bukan draft kajian -> 422
    bukan_draft = create_test_doc(document_role=PeranDokumen.corpus_eksisting)
    db_session.add(bukan_draft)
    db_session.commit()

    resp_bukan = client.get(f"/api/v1/documents/{bukan_draft.id}/harmonisasi/ekspor?format=xlsx")
    assert resp_bukan.status_code == 422
    assert resp_bukan.json()["detail"]["code"] == "bukan_draft"

    # B. Belum diharmonisasi -> 404
    draft_belum = create_test_doc(document_role=PeranDokumen.draft_kajian)
    db_session.add(draft_belum)
    db_session.commit()

    resp_belum = client.get(f"/api/v1/documents/{draft_belum.id}/harmonisasi/ekspor?format=xlsx")
    assert resp_belum.status_code == 404
    assert resp_belum.json()["detail"]["code"] == "harmonisasi_belum_ada"

    # C. Format tidak didukung -> 422 (memuat 'tidak didukung')
    seed_harmonisasi_result(db_session, draft_belum, {"versi": "1.0", "temuan": []})
    resp_salah = client.get(f"/api/v1/documents/{draft_belum.id}/harmonisasi/ekspor?format=unsupported_format")
    assert resp_salah.status_code == 422
    assert "tidak didukung" in resp_salah.text

    # D. Izin: saat auth aktif dan user tanpa izin -> 403
    monkeypatch.setattr(settings, "auth_enabled", True)
    admin_kb_user = User(
        username="admin_kb_test",
        role=PeranPengguna.admin_kb,
        hashed_password="hashed_pwd",
        is_active=True,
    )
    db_session.add(admin_kb_user)
    db_session.commit()

    token = _buat_token_auth(admin_kb_user)
    resp_auth = client.get(
        f"/api/v1/documents/{draft_belum.id}/harmonisasi/ekspor?format=xlsx",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_auth.status_code == 403


# ==============================================================================
# KASUS 6: Audit EXPORT_HARMONIZATION dengan format xlsx
# ==============================================================================
def test_x06_audit_export_harmonization_xlsx(client: TestClient, db_session: Session):
    """6. Audit EXPORT_HARMONIZATION tercatat dengan detail format 'xlsx'."""
    draft = create_test_doc()
    comp = create_test_doc()
    db_session.add_all([draft, comp])
    db_session.commit()

    cached_payload = {
        "versi": "1.0",
        "ringkasan": {"total_temuan": 1},
        "temuan": [
            {
                "id": "t1",
                "jenis": "sama",
                "pasal_draft": "Pasal 1",
                "pembanding": {"document_id": comp.id, "nomor": "1"},
            }
        ],
    }
    seed_harmonisasi_result(db_session, draft, cached_payload)

    resp = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=xlsx")
    assert resp.status_code == 200

    audit_entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.target_resource == f"document:{draft.id}", AuditLog.action == EXPORT_HARMONIZATION)
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.detail.get("format") == "xlsx"
    assert audit_entry.detail.get("jumlah_temuan") == 1


# ==============================================================================
# KASUS 7: Skrip lembar sampling: sampling K temuan, reprodusibel, non-publik
# ==============================================================================
def test_x07_skrip_buat_lembar_sampling(db_session: Session, tmp_path: Path, capsys: pytest.CaptureFixture):
    """
    7. Skrip: menghasilkan xlsx dengan K sampel per dokumen; seed sama -> isi sama;
       pasal_baru tidak ikut; dokumen tanpa hasil dilewati; konsol tidak memuat judul/kutipan; DB tidak berubah.
    """
    # 1. Dokumen 1 (draft valid dengan 5 temuan berpembanding, 1 pasal_baru, dan 2 temuan pasal sama)
    doc1 = create_test_doc(title="Draf Rahasia Alpha 1234")
    comp1 = create_test_doc(title="Regulasi Acuan 1", regulation_number="POJK 10/2020")
    db_session.add_all([doc1, comp1])
    db_session.commit()

    temuan_doc1 = [
        {
            "id": f"t-doc1-{i}",
            "jenis": "sama" if i % 2 == 0 else "menggantikan",
            "pasal_draft": f"Pasal {i}",
            "kutipan_draft": f"Kutipan rahasia draf doc1 nomor {i}",
            "pembanding": {
                "document_id": comp1.id,
                "nomor": "POJK 10/2020",
                "judul": "Regulasi Acuan 1",
                "pasal": f"Pasal {i + 5}",
                "kutipan": f"Kutipan acuan {i}",
                "pdf": f"/static/pdf/pojk_10_2020_{i}.pdf",
            },
            "tingkat": "tinggi",
            "keyakinan": 0.85,
            "alasan": f"Alasan {i}",
        }
        for i in range(1, 6)
    ]
    # Tambah temuan pasal_baru (tidak boleh ikut di sheet Sampel)
    temuan_doc1.append({
        "id": "t-doc1-baru",
        "jenis": "pasal_baru",
        "pasal_draft": "Pasal 99",
        "kutipan_draft": "Ketentuan inovasi baru tanpa pembanding",
        "pembanding": None,
    })
    # Tambah temuan lain pada pasal 1 (satu pasal draf tidak diambil dua kali)
    temuan_doc1.append({
        "id": "t-doc1-pasal1-duplikat",
        "jenis": "konflik",
        "pasal_draft": "Pasal 1",
        "kutipan_draft": "Kutipan kedua pasal 1",
        "pembanding": {
            "document_id": comp1.id,
            "nomor": "POJK 10/2020",
            "judul": "Regulasi Acuan 1",
            "pasal": "Pasal 1",
        },
    })
    seed_harmonisasi_result(db_session, doc1, {"versi": "1.0", "temuan": temuan_doc1})

    # 2. Dokumen 2 (draft valid dengan 2 temuan)
    doc2 = create_test_doc(title="Draf Rahasia Beta 5678")
    db_session.add(doc2)
    db_session.commit()

    temuan_doc2 = [
        {
            "id": f"t-doc2-{i}",
            "jenis": "melengkapi",
            "pasal_draft": f"Pasal {i * 2}",
            "kutipan_draft": f"Kutipan rahasia draf doc2 nomor {i}",
            "pembanding": {
                "document_id": comp1.id,
                "nomor": "POJK 10/2020",
                "judul": "Regulasi Acuan 1",
                "pasal": f"Pasal {i * 3}",
                "kutipan": f"Kutipan pembanding doc2 {i}",
            },
            "tingkat": "sedang",
            "keyakinan": 0.75,
            "alasan": f"Alasan doc2 {i}",
        }
        for i in range(1, 3)
    ]
    seed_harmonisasi_result(db_session, doc2, {"versi": "1.0", "temuan": temuan_doc2})

    # 3. Dokumen 3 (bukan draft kajian -> harus dilewati)
    doc3 = create_test_doc(document_role=PeranDokumen.corpus_eksisting)
    db_session.add(doc3)
    db_session.commit()

    # 4. Dokumen 4 (draft tanpa hasil harmonisasi -> harus dilewati)
    doc4 = create_test_doc(title="Draft Tanpa Cache")
    db_session.add(doc4)
    db_session.commit()

    # Catat jumlah baris DB sebelum eksekusi skrip untuk verifikasi read-only
    count_doc_before = db_session.query(Document).count()
    count_res_before = db_session.query(AnalysisResult).count()
    count_audit_before = db_session.query(AuditLog).count()

    out_file1 = tmp_path / "lembar_sampling_run1.xlsx"
    out_file2 = tmp_path / "lembar_sampling_run2.xlsx"

    # Jalankan run 1 dengan seed=42, per_dokumen=2
    res1 = jalankan_buat_lembar_sampling(
        db=db_session,
        document_ids=[doc1.id, doc2.id, doc3.id, doc4.id],
        per_dokumen=2,
        seed=42,
        keluaran=out_file1,
        base_url="https://hero.internal.ojk.go.id",
    )

    assert res1["dokumen_diproses"] == 2
    assert res1["dokumen_dilewati"] == 2
    assert res1["sampel_ditulis"] == 4  # 2 dari doc1 + 2 dari doc2

    # Jalankan run 2 dengan seed=42 yang sama -> hasil harus identik
    res2 = jalankan_buat_lembar_sampling(
        db=db_session,
        document_ids=[doc1.id, doc2.id, doc3.id, doc4.id],
        per_dokumen=2,
        seed=42,
        keluaran=out_file2,
        base_url="https://hero.internal.ojk.go.id",
    )

    # Verifikasi berkas 1 dan 2 identik isinya
    wb1 = openpyxl.load_workbook(out_file1)
    wb2 = openpyxl.load_workbook(out_file2)
    assert wb1.sheetnames == ["Sampel", "Petunjuk"]

    ws_s1 = wb1["Sampel"]
    ws_s2 = wb2["Sampel"]

    rows1 = list(ws_s1.iter_rows(values_only=True))
    rows2 = list(ws_s2.iter_rows(values_only=True))
    assert rows1 == rows2, "Hasil sampling dengan seed yang sama harus identik!"

    # Verifikasi isi sheet Sampel
    header_sampel = rows1[0]
    assert "Dokumen draf" in header_sampel
    assert "Tautan PDF pembanding" in header_sampel
    assert "Bunyi pasal sesuai? (Ya/Tidak)" in header_sampel
    assert "Jenis temuan sesuai? (Ya/Tidak)" in header_sampel
    assert "Catatan validator" in header_sampel

    # Periksa data baris sampel
    sample_rows = rows1[1:]
    assert len(sample_rows) == 4

    doc1_samples = [r for r in sample_rows if doc1.title in str(r[1])]
    assert len(doc1_samples) == 2
    # Pastikan pasal_baru tidak ikut
    assert not any("Pasal 99" in str(r[2]) for r in doc1_samples)
    # Pastikan satu pasal draf tidak diambil dua kali
    pasal_doc1_taken = [r[2] for r in doc1_samples]
    assert len(set(pasal_doc1_taken)) == len(pasal_doc1_taken)

    # Pastikan tautan PDF memiliki base-url jika relatif
    for r in sample_rows:
        pdf_link = r[9]
        if pdf_link:
            assert pdf_link.startswith("https://hero.internal.ojk.go.id/")

        # Kolom validator kosong
        assert r[10] in ("", None)
        assert r[11] in ("", None)
        assert r[12] in ("", None)

    # Periksa Sheet Petunjuk
    ws_p = wb1["Petunjuk"]
    p_text = "\n".join([str(c[0]) for c in ws_p.iter_rows(values_only=True) if c[0]])
    assert "Petunjuk Validasi Sampling Harmonisasi Regulasi (DPEA)" in p_text
    assert "Seed pengacakan : 42" in p_text

    # Verifikasi DB sama sekali tidak berubah (read-only)
    assert db_session.query(Document).count() == count_doc_before
    assert db_session.query(AnalysisResult).count() == count_res_before
    assert db_session.query(AuditLog).count() == count_audit_before

    # Uji CLI eksekusi langsung untuk memastikan konsol bersih dari judul / kutipan
    cmd = [
        sys.executable,
        str(BASE_DIR / "scripts" / "buat_lembar_sampling.py"),
        "--document-id",
        str(doc1.id),
        "--document-id",
        str(doc2.id),
        "--per-dokumen",
        "2",
        "--seed",
        "42",
        "--keluaran",
        str(tmp_path / "cli_output.xlsx"),
    ]
    sub_env = dict(os.environ)
    sub_env["DATABASE_URL"] = db_session.bind.url.render_as_string(hide_password=False)
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR), env=sub_env)
    assert proc.returncode == 0
    stdout_text = proc.stdout

    # Verifikasi peringatan dokumen non-publik tercetak
    assert PESAN_PERINGATAN_NON_PUBLIK in stdout_text
    assert "Dokumen diproses : 2" in stdout_text
    assert "Sampel ditulis   : 4" in stdout_text

    # JANGAN mencetak judul atau kutipan dokumen ke konsol!
    assert doc1.title not in stdout_text
    assert doc2.title not in stdout_text
    assert "Kutipan rahasia draf" not in stdout_text
