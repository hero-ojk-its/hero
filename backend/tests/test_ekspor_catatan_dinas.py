"""
tests/test_ekspor_catatan_dinas.py
Pengujian ekspor harmonisasi format "Catatan Dinas" (DOCX + PDF).
Kasus uji:
1. DOCX memuat CATATAN DINAS, nomor, blok identitas, kelima butir, penandatangan; nilai form muncul.
2. Form kosong -> placeholder muncul; butir 4 dilewati dan penomoran menyesuaikan (total 4 butir).
3. Butir 3 memuat SEMUA temuan (valid, tidak relevan, belum dinilai), urut nomor pasal draf, termasuk pasal_baru.
4. PDF: diawali %PDF-, tidak kosong, dan teks memuat CATATAN DINAS serta tanda baca Indonesia yang benar.
5. Akses: dokumen bukan draf -> 422; belum diharmonisasi -> 404; izin ekspor tidak ada -> 403; pembanding non-publik/restricted -> tersaring (peraturan pembanding (akses dibatasi)).
6. pakai_ai=true tanpa cache AI -> template + header tidak_tersedia; dengan cache AI rekaan -> narasi dipakai + header dipakai + catatan kaki.
7. Batas panjang field -> 422 berbahasa Indonesia; karakter kontrol dibuang.
8. Nilai form tidak tersimpan: tidak ada data pribadi (nama/NIP) di tabel audit_logs maupun analysis_results.
"""
from datetime import datetime, timezone, timedelta
import io
import uuid

import docx
from fastapi.testclient import TestClient
import jwt
import pypdf
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
from app.services.catatan_dinas_export_service import format_tanggal_indonesia


@pytest.fixture(autouse=True)
def setup_ml_env(monkeypatch: pytest.MonkeyPatch):
    """Pastikan konfigurasi ML aktif dan terisolasi untuk pengujian."""
    monkeypatch.setattr(settings, "ml_service_url", "http://ml-test:8100")
    monkeypatch.setattr(settings, "ml_cache_enabled", True)
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)
    monkeypatch.setattr(settings, "auth_enabled", False)
    yield
    app.dependency_overrides.pop(get_ml_client, None)


def _buat_token_auth(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username,
        "exp": now + timedelta(hours=2),
        "iat": now,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_test_doc(**kwargs) -> Document:
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


def test_cd01_docx_ekspor_dengan_isian_form_lengkap(client: TestClient, db_session: Session):
    """1. DOCX: memuat CATATAN DINAS, nomor, blok identitas, kelima butir, penandatangan; nilai form muncul."""
    draft = create_test_doc()
    comp = create_test_doc(
        title="POJK 4 Tahun 2023",
        regulation_type="POJK",
        regulation_number="4",
        regulation_year=2023,
    )
    db_session.add_all([draft, comp])
    db_session.commit()

    # Seed hasil analisa (untuk butir 1)
    seed_analisa_result(
        db_session,
        draft,
        {
            "identitas": {"jumlah_pasal": 25},
            "kerangka": [
                {"bab": "I", "judul": "Ketentuan Umum"},
                {"bab": "II", "judul": "Tata Kelola Investasi"},
                {"bab": "III", "judul": "Batasan Penempatan Dana"},
            ],
        },
    )

    # Seed hasil harmonisasi (untuk butir 3)
    seed_harmonisasi_result(
        db_session,
        draft,
        {
            "versi": "1.0",
            "temuan": [
                {
                    "id": "t-1",
                    "jenis": "menggantikan",
                    "pasal_draft": "Pasal 5",
                    "kutipan_draft": "Manajer investasi wajib mengelola portofolio secara terukur.",
                    "pembanding": {"document_id": comp.id, "nomor": "POJK 4 2023", "pasal": "Pasal 10"},
                    "alasan": "Menggantikan ketentuan diversifikasi portofolio.",
                    "tingkat": "tinggi",
                    "keyakinan": 0.88,
                }
            ],
        },
    )

    req_body = {
        "format": "docx",
        "nomor_cd": "CD-10/DPEA/XI/2026",
        "yth": "Direktur Pengaturan Perbankan",
        "dari": "Kepala Departemen Penelaahan Regulasi",
        "sifat": "Segera",
        "lampiran": "1 (satu) Berkas",
        "hal": "Tanggapan Draf Regulasi Reksa Dana",
        "tanggal": "2026-11-13",
        "unit_peminta": "Departemen Pengawasan Pasar Modal",
        "nomor_nd": "ND-99/DPPM/X/2026",
        "tanggal_nd": "2026-10-25",
        "hal_nd": "Permintaan Masukan Harmonisasi Draf",
        "catatan_tambahan": "Perlu koordinasi lebih lanjut dengan Departemen Hukum terkait sanksi.",
        "penandatangan_jabatan": "Direktur Harmonisasi",
        "penandatangan_nama": "Budi Santoso, S.H.",
        "penandatangan_nip": "198001012005011001",
    }

    resp = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json=req_body,
    )
    assert resp.status_code == 200
    assert "application/vnd.openxmlformats-officedocument" in resp.headers["content-type"]
    assert "catatan_dinas_" in resp.headers["content-disposition"]
    assert ".docx" in resp.headers["content-disposition"]

    full_text = extract_docx_text(resp.content)

    # 1. Judul & Konsep
    assert "CATATAN DINAS" in full_text
    assert "NOMOR CD-10/DPEA/XI/2026" in full_text
    assert "KONSEP — dihasilkan sistem HERO sebagai Draft / Rekomendasi; belum ditandatangani." not in full_text

    # 2. Blok Identitas
    assert "Direktur Pengaturan Perbankan" in full_text
    assert "Kepala Departemen Penelaahan Regulasi" in full_text
    assert "Segera" in full_text
    assert "1 (satu) Berkas" in full_text
    assert "Tanggapan Draf Regulasi Reksa Dana" in full_text
    assert "13 November 2026" in full_text

    # 3. Kalimat Pembuka
    assert "Sehubungan dengan nota dinas Departemen Pengawasan Pasar Modal nomor ND-99/DPPM/X/2026" in full_text
    assert "tanggal 25 Oktober 2026 hal Permintaan Masukan Harmonisasi Draf" in full_text

    # 4. Kelima butir bernomor
    assert "1. " in full_text
    assert "terdiri atas 3 bab dan 25 pasal" in full_text
    assert "Tata Kelola Investasi, Batasan Penempatan Dana" in full_text

    assert "2. " in full_text
    assert "meminta tanggapan atas Draf Kajian Reksa Dana Pasar Uang" in full_text

    assert "3. " in full_text
    assert "Pasal 5 mengatur bahwa Manajer investasi wajib mengelola portofolio secara terukur." in full_text
    assert "Temuan Menggantikan" in full_text
    assert "peraturan Nomor POJK 4 2023, Pasal 10" in full_text
    assert "tinggi (0,88)" in full_text

    assert "4. " in full_text
    assert "Perlu koordinasi lebih lanjut dengan Departemen Hukum terkait sanksi." in full_text

    assert "5. " in full_text
    assert "Apabila Bapak/Ibu sependapat, terlampir konsep nota dinas tanggapan untuk ditindaklanjuti." in full_text

    # 5. Kalimat Penutup & Penandatangan
    assert "Demikian kami sampaikan, atas perhatian Bapak/Ibu kami ucapkan terima kasih." in full_text
    assert "Direktur Harmonisasi" in full_text
    assert "Budi Santoso, S.H." in full_text
    assert "NIP 198001012005011001" in full_text
    assert "Keputusan final tetap kewenangan Pengawas / unit terkait." in full_text


def test_cd02_form_kosong_placeholder_dan_butir4_dilewati(client: TestClient, db_session: Session):
    """2. Form kosong -> kop baku Weekly #10 (Kepala Departemen, Analis Eksekutif), hal default, tanggal '…' (bukan hari ini); butir 4 dilewati dan penomoran menyesuaikan."""
    draft = create_test_doc(title="Draf Perbankan Digital")
    db_session.add(draft)
    db_session.commit()

    seed_harmonisasi_result(
        db_session,
        draft,
        {
            "versi": "1.0",
            "temuan": [],
        },
    )

    now_wib = datetime.now(timezone(timedelta(hours=7))).date()
    tgl_hari_ini = format_tanggal_indonesia(now_wib)

    # A. Ekspor DOCX dengan form kosong
    resp = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={},
    )
    assert resp.status_code == 200

    full_text = extract_docx_text(resp.content)

    # Kop baku Weekly #10 dan default
    assert "NOMOR CD-xx/…/xxxx" in full_text
    assert "Kepala Departemen" in full_text
    assert "Analis Eksekutif" in full_text
    assert "Biasa" in full_text
    assert "-" in full_text
    assert f"Tanggapan atas {draft.title}" in full_text
    assert "…" in full_text
    # Tanggal harus berupa placeholder '…' dan BUKAN tanggal hari ini
    assert tgl_hari_ini not in full_text

    # Penomoran menyesuaikan: ada 1, 2, 3, 4, dan TIDAK ada 5
    assert "1. " in full_text
    assert "2. " in full_text
    assert "3. " in full_text
    assert "4. Apabila Bapak/Ibu sependapat, terlampir konsep nota dinas tanggapan untuk ditindaklanjuti." in full_text
    assert "5. " not in full_text

    # B. Ekspor PDF dengan form kosong
    resp_pdf = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "pdf"},
    )
    assert resp_pdf.status_code == 200
    pdf_text = extract_pdf_text(resp_pdf.content)

    assert "Kepala Departemen" in pdf_text
    assert "Analis Eksekutif" in pdf_text
    assert f"Tanggapan atas {draft.title}" in pdf_text
    assert "…" in pdf_text
    assert tgl_hari_ini not in pdf_text


def test_cd03_butir3_memuat_semua_temuan_urut_pasal_termasuk_pasal_baru(client: TestClient, db_session: Session):
    """3. Butir 3 memuat SEMUA temuan (valid, tidak relevan, belum dinilai), urut nomor pasal draf, termasuk pasal_baru."""
    draft = create_test_doc(title="Draf multi temuan")
    comp = create_test_doc(title="POJK Pembanding", regulation_number="1/POJK.03/2020")
    db_session.add_all([draft, comp])
    db_session.commit()

    # Beri 3 temuan dengan pasal tidak urut dan status berbeda
    raw_temuan = [
        {
            "id": "t-pasal-14",
            "jenis": "menggantikan",
            "pasal_draft": "Pasal 14",
            "pembanding": {"document_id": comp.id, "nomor": "POJK 1/2020", "pasal": "Pasal 2"},
            "alasan": "Ketentuan batas maksimum penyaluran dana.",
            "tingkat": "tinggi",
            "keyakinan": 0.85,
        },
        {
            "id": "t-pasal-2",
            "jenis": "pasal_baru",
            "pasal_draft": "Pasal 2",
            "pembanding": None,  # pasal baru: pembanding null
            "alasan": "Pengaturan pasal baru definisi aset kripto.",
            "tingkat": "sedang",
            "keyakinan": 0.60,
        },
        {
            "id": "t-pasal-5",
            "jenis": "konflik",
            "pasal_draft": "Pasal 5 ayat (1)",
            "pembanding": {"document_id": comp.id, "nomor": "POJK 1/2020", "pasal": "Pasal 15"},
            "alasan": "Potensi konflik kewenangan audit internal.",
            "tingkat": "rendah",
            "keyakinan": 0.40,
        },
    ]

    # Beri tanggapan analis pada temuan pertama & ketiga via endpoint tanggapan
    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": raw_temuan})

    # Tanggapan analis untuk pasal 14: valid
    client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": raw_temuan[0], "penilaian": "valid", "catatan": "Perlu sinkronisasi"},
    )
    # Tanggapan analis untuk pasal 5: tidak_relevan
    client.put(
        f"/api/v1/documents/{draft.id}/harmonisasi/tanggapan",
        json={"temuan": raw_temuan[2], "penilaian": "tidak_relevan", "catatan": "Konteks pasal berbeda"},
    )

    resp = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "docx"},
    )
    assert resp.status_code == 200
    full_text = extract_docx_text(resp.content)

    # Verifikasi urutan: Pasal 2 harus muncul SEBELUM Pasal 5, dan Pasal 5 SEBELUM Pasal 14
    idx_p2 = full_text.find("Pasal 2")
    idx_p5 = full_text.find("Pasal 5")
    idx_p14 = full_text.find("Pasal 14")
    assert idx_p2 != -1 and idx_p5 != -1 and idx_p14 != -1
    assert idx_p2 < idx_p5 < idx_p14, "Temuan harus terurut secara alami berdasarkan nomor pasal"

    # Verifikasi temuan pasal_baru (pembanding null) tidak error dan tampil benar
    assert "Temuan Pasal Baru" in full_text
    assert "Pengaturan pasal baru definisi aset kripto" in full_text
    assert "Penilaian analis: Belum dinilai" in full_text

    # Verifikasi temuan konflik dengan penilaian tidak relevan
    assert "Temuan Kontradiktif" in full_text
    assert "Penilaian analis: Tidak Relevan. Catatan analis: Konteks pasal berbeda" in full_text

    # Verifikasi temuan menggantikan dengan penilaian valid
    assert "Temuan Menggantikan" in full_text
    assert "Penilaian analis: Valid. Catatan analis: Perlu sinkronisasi" in full_text


def test_cd04_pdf_valid_dan_memuat_catatan_dinas(client: TestClient, db_session: Session):
    """4. PDF: diawali %PDF-, tidak kosong, dan teksnya memuat CATATAN DINAS."""
    draft = create_test_doc(title="Draf Uji PDF")
    db_session.add(draft)
    db_session.commit()

    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    resp = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "pdf", "nomor_cd": "CD-PDF/01/2026"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "catatan_dinas_" in resp.headers["content-disposition"]
    assert ".pdf" in resp.headers["content-disposition"]

    content = resp.content
    assert content.startswith(b"%PDF-"), "Berkas PDF harus diawali dengan %PDF-"
    assert len(content) > 1000

    pdf_text = extract_pdf_text(content)
    assert "CATATAN DINAS" in pdf_text
    assert "CD-PDF/01/2026" in pdf_text
    assert "KONSEP — dihasilkan sistem HERO sebagai Draft / Rekomendasi; belum ditandatangani." not in pdf_text
    assert "Apabila Bapak/Ibu sependapat, terlampir konsep nota dinas tanggapan untuk ditindaklanjuti." in pdf_text


def test_cd05_akses_dan_keamanan(client: TestClient, db_session: Session):
    """5. Akses: dokumen bukan draf -> 422; belum diharmonisasi -> 404; izin ekspor tidak ada -> ditolak; pembanding tidak boleh dilihat -> tersaring."""
    # A. Bukan draf (corpus_eksisting) -> 422
    corpus_doc = create_test_doc(document_role=PeranDokumen.corpus_eksisting)
    db_session.add(corpus_doc)
    db_session.commit()

    resp_bukan_draft = client.post(
        f"/api/v1/documents/{corpus_doc.id}/harmonisasi/ekspor/catatan-dinas",
        json={},
    )
    assert resp_bukan_draft.status_code == 422
    assert resp_bukan_draft.json().get("detail", {}).get("code") == "bukan_draft"

    # B. Belum diharmonisasi -> 404
    draft_unanalysed = create_test_doc()
    db_session.add(draft_unanalysed)
    db_session.commit()

    resp_belum = client.post(
        f"/api/v1/documents/{draft_unanalysed.id}/harmonisasi/ekspor/catatan-dinas",
        json={},
    )
    assert resp_belum.status_code == 404
    assert resp_belum.json().get("detail", {}).get("code") == "harmonisasi_belum_ada"

    # C. Auth aktif, user tanpa izin ANALISA_EKSPOR -> 403
    orig_auth = settings.auth_enabled
    settings.auth_enabled = True
    try:
        user_pilot = User(
            username=f"pilot_{uuid.uuid4().hex[:6]}",
            hashed_password="$2b$12$dummyhashforpilotuserwithoutperms",
            role=PeranPengguna.pilot_user,
            is_active=True,
        )
        db_session.add(user_pilot)
        db_session.commit()
        token_pilot = _buat_token_auth(user_pilot)

        draft_auth = create_test_doc(access_classification=KlasifikasiAkses.publik)
        db_session.add(draft_auth)
        db_session.commit()
        seed_harmonisasi_result(db_session, draft_auth, {"versi": "1.0", "temuan": []})

        resp_403 = client.post(
            f"/api/v1/documents/{draft_auth.id}/harmonisasi/ekspor/catatan-dinas",
            headers={"Authorization": f"Bearer {token_pilot}"},
            json={},
        )
        assert resp_403.status_code == 403
    finally:
        settings.auth_enabled = orig_auth

    # D. Pembanding nonaktif / tidak boleh dilihat -> tersaring (peraturan pembanding (akses dibatasi))
    draft_filter = create_test_doc()
    comp_nonaktif = create_test_doc(title="Pembanding Rahasia", is_active=False)
    db_session.add_all([draft_filter, comp_nonaktif])
    db_session.commit()

    seed_harmonisasi_result(
        db_session,
        draft_filter,
        {
            "versi": "1.0",
            "temuan": [
                {
                    "id": "t-secret",
                    "jenis": "konflik",
                    "pasal_draft": "Pasal 9",
                    "pembanding": {"document_id": comp_nonaktif.id, "restricted": True},
                    "alasan": "Ketentuan bertentangan dengan standar internal.",
                }
            ],
        },
    )

    resp_filter = client.post(
        f"/api/v1/documents/{draft_filter.id}/harmonisasi/ekspor/catatan-dinas",
        json={},
    )
    assert resp_filter.status_code == 200
    text_filter = extract_docx_text(resp_filter.content)
    # Judul/rahasia pembanding tidak boleh bocor
    assert "Pembanding Rahasia" not in text_filter


def test_cd06_toggle_pakai_ai(client: TestClient, db_session: Session):
    """6. pakai_ai=true tanpa cache AI -> template + header tidak_tersedia; dengan cache AI rekaan -> narasi dipakai + header dipakai."""
    draft = create_test_doc(title="Draf AI Toggle")
    db_session.add(draft)
    db_session.commit()

    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    # 1. Tanpa cache AI -> template + header X-Catatan-Dinas-AI: tidak_tersedia
    resp1 = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"pakai_ai": True},
    )
    assert resp1.status_code == 200
    assert resp1.headers.get("X-Catatan-Dinas-AI") == "tidak_tersedia"
    text1 = extract_docx_text(resp1.content)
    assert "disusun dengan bantuan AI" not in text1

    # 2. Dengan cache AI segar (mode=ai, kind=analisa)
    ai_narasi = "Draf regulasi ini menetapkan arsitektur pengawasan berbasis teknologi digital secara terpadu."
    seed_analisa_result(
        db_session,
        draft,
        {"mode_dipakai": "ai", "ringkasan_ai": ai_narasi},
        mode=ModeAnalisa.ai,
    )

    resp2 = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"pakai_ai": True},
    )
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Catatan-Dinas-AI") == "dipakai"
    text2 = extract_docx_text(resp2.content)
    assert ai_narasi in text2
    assert "Butir 1 disusun dengan bantuan AI dari hasil analisa terverifikasi." in text2


def test_cd07_validasi_batas_panjang_dan_karakter_kontrol(client: TestClient, db_session: Session):
    """7. Batas panjang field -> 422 berbahasa Indonesia; karakter kontrol dibuang."""
    draft = create_test_doc()
    db_session.add(draft)
    db_session.commit()
    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    # A. Nomor CD melebihi 60 karakter -> 422
    resp_panjang = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"nomor_cd": "A" * 65},
    )
    assert resp_panjang.status_code == 422
    assert "melebihi batas maksimum" in resp_panjang.text

    # B. Format tidak didukung -> 422
    resp_fmt = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "xlsx_invalid"},
    )
    assert resp_fmt.status_code == 422
    assert "tidak didukung" in resp_fmt.text

    # C. Karakter kontrol disanitasi dan tidak menimbulkan error
    resp_ctrl = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={
            "nomor_cd": "CD-01\x00\x08/DPEA/2026",
            "penandatangan_nama": "Budi\x07 Santoso",
        },
    )
    assert resp_ctrl.status_code == 200
    text_ctrl = extract_docx_text(resp_ctrl.content)
    assert "CD-01/DPEA/2026" in text_ctrl
    assert "Budi Santoso" in text_ctrl


def test_cd08_nilai_form_tidak_tersimpan_di_db_maupun_audit(client: TestClient, db_session: Session):
    """8. Nilai form tidak tersimpan: tidak ada data pribadi (nama/NIP) di tabel audit maupun analysis_results."""
    draft = create_test_doc()
    db_session.add(draft)
    db_session.commit()
    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    nama_rahasia = "Prof. Dr. Rahasia Negara, S.H."
    nip_rahasia = "199912312020011001"
    catatan_pribadi = "Catatan rahasia pengawas perbankan non publik"

    resp = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={
            "penandatangan_nama": nama_rahasia,
            "penandatangan_nip": nip_rahasia,
            "catatan_tambahan": catatan_pribadi,
        },
    )
    assert resp.status_code == 200

    # Periksa audit log terbaru
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.target_resource == f"document:{draft.id}", AuditLog.action == EXPORT_HARMONIZATION)
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.detail.get("format") == "catatan_dinas_docx"
    assert audit.detail.get("pakai_ai") is False

    # Pastikan data pribadi TIDAK masuk ke audit detail
    audit_detail_str = str(audit.detail)
    assert nama_rahasia not in audit_detail_str
    assert nip_rahasia not in audit_detail_str
    assert catatan_pribadi not in audit_detail_str

    # Pastikan juga tidak tersimpan ke tabel analysis_results
    results = db_session.query(AnalysisResult).filter(AnalysisResult.document_id == draft.id).all()
    for r in results:
        res_str = str(r.result)
        assert nama_rahasia not in res_str
        assert nip_rahasia not in res_str
        assert catatan_pribadi not in res_str


def test_cd09_ai_format_asli_list_of_dict(client: TestClient, db_session: Session):
    """1. pakai_ai=true dengan cache AI berbentuk asli list of dict -> header 'dipakai', teks memuat kalimat di DOCX & PDF."""
    draft = create_test_doc(title="Draf Format Asli AI")
    db_session.add(draft)
    db_session.commit()

    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    # Cache AI dengan struktur asli pipeline / frontend: list of dict {"kalimat": "...", "rujukan": [...]}
    ai_payload = {
        "mode_dipakai": "ai",
        "ringkasan_ai": [
            {"kalimat": "Regulasi ini mengatur tata kelola instrumen pasar uang terpadu.", "rujukan": [1]},
            {"kalimat": "Manajer investasi wajib menerapkan manajemen risiko secara berkala.", "rujukan": [2, 3]},
        ],
    }
    seed_analisa_result(
        db_session,
        draft,
        ai_payload,
        mode=ModeAnalisa.ai,
    )

    # A. Ekspor DOCX
    resp_docx = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "docx", "pakai_ai": True},
    )
    assert resp_docx.status_code == 200
    assert resp_docx.headers.get("X-Catatan-Dinas-AI") == "dipakai"
    text_docx = extract_docx_text(resp_docx.content)
    assert "Regulasi ini mengatur tata kelola instrumen pasar uang terpadu. Manajer investasi wajib menerapkan manajemen risiko secara berkala." in text_docx
    assert "Butir 1 disusun dengan bantuan AI dari hasil analisa terverifikasi." in text_docx

    # B. Ekspor PDF
    resp_pdf = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "pdf", "pakai_ai": True},
    )
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers.get("X-Catatan-Dinas-AI") == "dipakai"
    assert resp_pdf.content.startswith(b"%PDF-")
    text_pdf = extract_pdf_text(resp_pdf.content)
    assert "Regulasi ini mengatur tata kelola instrumen pasar uang terpadu. Manajer investasi wajib menerapkan manajemen risiko secara berkala." in " ".join(text_pdf.split())
    assert "Butir 1 disusun dengan bantuan AI dari hasil analisa terverifikasi." in text_pdf


def test_cd10_ai_fallback_deterministik_abaikan_narasi(client: TestClient, db_session: Session):
    """2. pakai_ai=true dengan cache AI fallback deterministik -> header 'tidak_tersedia', teks memakai template."""
    draft = create_test_doc(title="Draf AI Fallback Deterministik")
    db_session.add(draft)
    db_session.commit()

    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    # Cache AI tersimpan namun hasilnya menunjukkan fallback deterministik
    fallback_payload = {
        "mode_dipakai": "deterministik",
        "ringkasan_ai": [
            {"kalimat": "Kalimat yang tidak boleh muncul karena fallback.", "rujukan": []}
        ],
    }
    seed_analisa_result(
        db_session,
        draft,
        fallback_payload,
        mode=ModeAnalisa.ai,
    )

    resp = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"pakai_ai": True},
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Catatan-Dinas-AI") == "tidak_tersedia"
    text = extract_docx_text(resp.content)
    assert "Kalimat yang tidak boleh muncul karena fallback." not in text
    assert "disusun dengan bantuan AI" not in text
    assert "POJK tentang Draf AI Fallback Deterministik" in text


def test_cd11_ai_format_tak_dikenal_kembali_200_tidak_galat(client: TestClient, db_session: Session):
    """3. pakai_ai=true dengan cache AI berbentuk tak-dikenal (int atau dict) -> 200, header tidak_tersedia."""
    draft = create_test_doc(title="Draf AI Bentuk Aneh")
    db_session.add(draft)
    db_session.commit()

    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    # A. ringkasan_ai bertipe integer
    seed_analisa_result(
        db_session,
        draft,
        {"mode_dipakai": "ai", "ringkasan_ai": 99999},
        mode=ModeAnalisa.ai,
    )

    resp = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"pakai_ai": True},
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Catatan-Dinas-AI") == "tidak_tersedia"

    # B. ringkasan_ai bertipe dict aneh
    draft2 = create_test_doc(title="Draf AI Dict Aneh")
    db_session.add(draft2)
    db_session.commit()
    seed_harmonisasi_result(db_session, draft2, {"versi": "1.0", "temuan": []})
    seed_analisa_result(
        db_session,
        draft2,
        {"mode_dipakai": "ai", "ringkasan_ai": {"bukan_list": True, "nilai": [1, 2]}},
        mode=ModeAnalisa.ai,
    )

    resp2 = client.post(
        f"/api/v1/documents/{draft2.id}/harmonisasi/ekspor/catatan-dinas",
        json={"pakai_ai": True},
    )
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Catatan-Dinas-AI") == "tidak_tersedia"


def test_cd12_nama_pembanding_format_dan_tanpa_internal_key(client: TestClient, db_session: Session):
    """4. Pembanding dengan nomor: '21', judul: 'LAPORAN BERKALA DANA PENSIUN', pasal: 'Pasal 14', key: 'internal-key' -> format benar, key disembunyikan."""
    draft = create_test_doc()
    comp = create_test_doc(
        title="LAPORAN BERKALA DANA PENSIUN",
        regulation_type="POJK",
        regulation_number="21",
        regulation_year=2024,
    )
    db_session.add_all([draft, comp])
    db_session.commit()

    seed_harmonisasi_result(
        db_session,
        draft,
        {
            "versi": "1.0",
            "temuan": [
                {
                    "id": "t-1",
                    "jenis": "konflik",
                    "pasal_draft": "Pasal 8",
                    "kutipan_draft": "Laporan disampaikan tiap triwulan.",
                    "pembanding": {
                        "document_id": comp.id,
                        "nomor": "21",
                        "judul": "LAPORAN BERKALA DANA PENSIUN",
                        "pasal": "Pasal 14",
                        "key": "internal-pembanding-key-12345",
                    },
                    "alasan": "Terdapat benturan jadwal penyampaian laporan.",
                    "tingkat": "tinggi",
                    "keyakinan": 0.95,
                }
            ],
        },
    )

    resp = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "docx"},
    )
    assert resp.status_code == 200
    text = extract_docx_text(resp.content)
    assert "LAPORAN BERKALA DANA PENSIUN (Nomor 21), Pasal 14" in text
    assert "internal-pembanding-key-12345" not in text


def test_cd13_cors_expose_headers_x_catatan_dinas_ai(client: TestClient, db_session: Session):
    """5. Request dengan Origin: http://localhost:5173 mengembalikan X-Catatan-Dinas-AI di Access-Control-Expose-Headers."""
    draft = create_test_doc()
    db_session.add(draft)
    db_session.commit()
    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    resp = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"pakai_ai": True},
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 200
    expose_hdr = resp.headers.get("access-control-expose-headers") or ""
    # Header harus memuat X-Catatan-Dinas-AI (case-insensitive)
    assert "x-catatan-dinas-ai" in expose_hdr.lower()


def test_cd14_catatan_tambahan_multiline_pdf_berhasil(client: TestClient, db_session: Session):
    """6. catatan_tambahan multi-baris -> PDF berhasil dibuat (awalan %PDF-), tidak galat."""
    draft = create_test_doc()
    db_session.add(draft)
    db_session.commit()
    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    catatan_multiline = (
        "Poin A: Perlu koordinasi dengan OJK Regional.\n"
        "Poin B: Sosialisasi dilakukan sebelum Q3.\r\n"
        "Poin C: Penyesuaian sistem IT membutuhkan masa transisi 6 bulan."
    )

    resp = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "pdf", "catatan_tambahan": catatan_multiline},
    )
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF-")
    text_pdf = extract_pdf_text(resp.content)
    assert "Poin A: Perlu koordinasi dengan OJK Regional." in text_pdf
    assert "Poin B: Sosialisasi dilakukan sebelum Q3." in text_pdf
    assert "Poin C: Penyesuaian sistem IT membutuhkan masa transisi 6 bulan." in text_pdf


def test_cd15_temuan_disaring_akses_menampilkan_kalimat_penutup(client: TestClient, db_session: Session):
    """7. Temuan disaring akses -> Butir 3 ditutup dengan kalimat: '<n> temuan tidak ditampilkan karena pembandingnya tidak dapat diakses.'"""
    draft = create_test_doc()
    comp_terbuka = create_test_doc(title="POJK Terbuka", regulation_number="1")
    db_session.add_all([draft, comp_terbuka])
    db_session.commit()

    # Harmonisasi dengan 1 temuan terbuka dan 2 temuan yang pembandingnya tidak ada di allowed_ids (akses dibatasi)
    seed_harmonisasi_result(
        db_session,
        draft,
        {
            "versi": "1.0",
            "temuan": [
                {
                    "id": "t-1",
                    "jenis": "sama",
                    "pasal_draft": "Pasal 3",
                    "kutipan_draft": "Ketentuan batas modal disetor.",
                    "pembanding": {"document_id": comp_terbuka.id, "nomor": "1", "pasal": "Pasal 2"},
                    "alasan": "Ketentuan identik.",
                    "tingkat": "tinggi",
                    "keyakinan": 0.9,
                },
                {
                    "id": "t-2",
                    "jenis": "konflik",
                    "pasal_draft": "Pasal 4",
                    "pembanding": {"document_id": 999999, "nomor": "99", "pasal": "Pasal 1"},
                    "alasan": "Ketentuan rahasia 1.",
                },
                {
                    "id": "t-3",
                    "jenis": "konflik",
                    "pasal_draft": "Pasal 5",
                    "pembanding": {"document_id": 999998, "nomor": "98", "pasal": "Pasal 2"},
                    "alasan": "Ketentuan rahasia 2.",
                },
            ],
        },
    )

    resp_docx = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "docx"},
    )
    assert resp_docx.status_code == 200
    text_docx = extract_docx_text(resp_docx.content)
    assert "2 temuan tidak ditampilkan karena pembandingnya tidak dapat diakses." in text_docx

    resp_pdf = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "pdf"},
    )
    assert resp_pdf.status_code == 200
    text_pdf = extract_pdf_text(resp_pdf.content)
    assert "2 temuan tidak ditampilkan karena pembandingnya tidak dapat diakses." in " ".join(text_pdf.split())


def test_cd16_isian_form_kop_override_dan_format_tanggal(client: TestClient, db_session: Session):
    """8. yth, dari, tanggal diisi form -> nilai form dipakai, format tanggal '13 November 2026' di DOCX dan PDF."""
    draft = create_test_doc(title="Draf Isian Manual")
    db_session.add(draft)
    db_session.commit()

    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    req_body = {
        "yth": "Direktur Pengaturan Perbankan",
        "dari": "Analis Eksekutif Senior",
        "tanggal": "2026-11-13",
        "sifat": "Segera",
        "lampiran": "1 (satu) Berkas",
        "hal": "Tanggapan Khusus atas Draf",
    }

    # A. DOCX
    resp_docx = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json=dict(req_body, format="docx"),
    )
    assert resp_docx.status_code == 200
    text_docx = extract_docx_text(resp_docx.content)
    assert "Direktur Pengaturan Perbankan" in text_docx
    assert "Analis Eksekutif Senior" in text_docx
    assert "13 November 2026" in text_docx
    assert "Segera" in text_docx
    assert "1 (satu) Berkas" in text_docx
    assert "Tanggapan Khusus atas Draf" in text_docx

    # B. PDF
    resp_pdf = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json=dict(req_body, format="pdf"),
    )
    assert resp_pdf.status_code == 200
    text_pdf = extract_pdf_text(resp_pdf.content)
    assert "Direktur Pengaturan Perbankan" in text_pdf
    assert "Analis Eksekutif Senior" in text_pdf
    assert "13 November 2026" in text_pdf
    assert "Segera" in text_pdf
    assert "1 (satu) Berkas" in text_pdf
    assert "Tanggapan Khusus atas Draf" in text_pdf


def test_cd17_konfigurasi_bawaan_dapat_diubah_tanpa_ubah_kode(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, db_session: Session
):
    """9. Nilai bawaan kop dapat diubah lewat konfigurasi Settings (env/override) tanpa ubah kode."""
    draft = create_test_doc(title="Draf Tata Kelola BPR")
    db_session.add(draft)
    db_session.commit()

    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    # Override konfigurasi Settings
    monkeypatch.setattr(settings, "cd_default_yth", "Direktur Utama Pengawasan")
    monkeypatch.setattr(settings, "cd_default_dari", "Pemeriksa Eksekutif Madya")
    monkeypatch.setattr(settings, "cd_default_sifat", "Rahasia")
    monkeypatch.setattr(settings, "cd_default_lampiran", "2 (dua) Eksemplar")
    monkeypatch.setattr(settings, "cd_default_hal_template", "Telaah Regulasi: {judul}")
    monkeypatch.setattr(settings, "cd_placeholder_tanggal", "[TANGGAL_MANUAL]")
    monkeypatch.setattr(settings, "cd_placeholder_nomor_cd", "CD-KUSTOM/2026")

    # Form kosong -> harus memuat nilai konfigurasi baru
    resp_docx = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "docx"},
    )
    assert resp_docx.status_code == 200
    text_docx = extract_docx_text(resp_docx.content)
    assert "NOMOR CD-KUSTOM/2026" in text_docx
    assert "Direktur Utama Pengawasan" in text_docx
    assert "Pemeriksa Eksekutif Madya" in text_docx
    assert "Rahasia" in text_docx
    assert "2 (dua) Eksemplar" in text_docx
    assert "Telaah Regulasi: Draf Tata Kelola BPR" in text_docx
    assert "[TANGGAL_MANUAL]" in text_docx

    # PDF juga harus memuat nilai konfigurasi baru
    resp_pdf = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "pdf"},
    )
    assert resp_pdf.status_code == 200
    text_pdf = extract_pdf_text(resp_pdf.content)
    assert "CD-KUSTOM/2026" in text_pdf
    assert "Direktur Utama Pengawasan" in text_pdf
    assert "Pemeriksa Eksekutif Madya" in text_pdf
    assert "Rahasia" in text_pdf
    assert "2 (dua) Eksemplar" in text_pdf
    assert "Telaah Regulasi: Draf Tata Kelola BPR" in text_pdf
    assert "[TANGGAL_MANUAL]" in text_pdf


def test_cd18_pola_hal_tidak_dobel_tanggapan_atas(client: TestClient, db_session: Session):
    """10. Judul draf yang sudah diawali 'Tanggapan atas' tidak diduplikasi saat pola hal default diterapkan."""
    draft = create_test_doc(title="Tanggapan atas Rancangan POJK Pasar Modal")
    db_session.add(draft)
    db_session.commit()

    seed_harmonisasi_result(db_session, draft, {"versi": "1.0", "temuan": []})

    resp = client.post(
        f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas",
        json={"format": "docx"},
    )
    assert resp.status_code == 200
    text = extract_docx_text(resp.content)

    # Memuat judul asli dengan benar
    assert "Tanggapan atas Rancangan POJK Pasar Modal" in text
    # TIDAK memuat duplikasi 'Tanggapan atas Tanggapan atas'
    assert "Tanggapan atas Tanggapan atas Rancangan POJK Pasar Modal" not in text



