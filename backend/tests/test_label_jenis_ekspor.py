"""
backend/tests/test_label_jenis_ekspor.py
Pengujian label jenis temuan pada peta dan ekspor:
1. Peta: setiap nilai pasal_baru, baru, duplikasi, sama, memperjelas, melengkapi, menggantikan, konflik menghasilkan label UI yang benar.
2. Ekspor xlsx, Word, dan Catatan Dinas dari hasil tersimpan berisi temuan duplikasi dan memperjelas:
   teks yang tampil "Tumpang Tindih" dan "Selaras / Melengkapi", dan TIDAK memuat "Duplikasi" atau "Memperjelas" sebagai label jenis.
3. Nilai tak dikenal (mis. jenis_aneh) tetap tidak galat dan memakai fallback lama di tiap format.
"""
from datetime import datetime, timezone
import io
import uuid
import docx
import openpyxl
import pytest
from fastapi.testclient import TestClient
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
from app.services.harmonisasi_export_service import JENIS_LABEL_MAP


def _create_doc(db: Session, title: str, role: PeranDokumen = PeranDokumen.corpus_eksisting) -> Document:
    rnd = uuid.uuid4().hex[:8]
    doc = Document(
        title=title,
        regulation_type="POJK",
        regulation_number=f"POJK-{rnd}",
        regulation_year=2026,
        document_role=role,
        access_classification=KlasifikasiAkses.publik,
        file_path_pdf=f"pdf/{rnd}.pdf",
        file_hash=f"hash_{rnd}" * 4,
        file_size_bytes=1024,
        processing_status=StatusPemrosesan.terindeks,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        is_active=True,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _seed_result(db: Session, doc: Document, payload: dict) -> AnalysisResult:
    res = AnalysisResult(
        document_id=doc.id,
        kind=JenisAnalisa.harmonisasi,
        mode=ModeAnalisa.deterministik,
        params_hash="params-" + uuid.uuid4().hex[:16],
        source_fingerprint=f"hash:{doc.file_hash}",
        result=payload,
        ml_version="1.0",
        duration_ms=100,
        created_at=datetime.now(timezone.utc),
    )
    db.add(res)
    db.commit()
    db.refresh(res)
    return res


def test_c01_peta_label_jenis():
    """1. Peta: setiap nilai kunci internal menghasilkan label tampilan UI yang benar."""
    expected_map = {
        "pasal_baru": "Pasal Baru",
        "baru": "Pasal Baru",
        "duplikasi": "Tumpang Tindih",
        "sama": "Tumpang Tindih",
        "memperjelas": "Selaras / Melengkapi",
        "melengkapi": "Selaras / Melengkapi",
        "menggantikan": "Menggantikan",
        "konflik": "Kontradiktif",
    }
    for internal_key, expected_label in expected_map.items():
        assert JENIS_LABEL_MAP.get(internal_key) == expected_label, (
            f"Kunci '{internal_key}' menghasilkan '{JENIS_LABEL_MAP.get(internal_key)}', diharapkan '{expected_label}'"
        )


def test_c02_ekspor_xlsx_word_catatan_dinas_duplikasi_memperjelas(client: TestClient, db_session: Session):
    """2. Ekspor xlsx, Word, dan Catatan Dinas menampilkan 'Tumpang Tindih' dan 'Selaras / Melengkapi', bukan 'Duplikasi' atau 'Memperjelas'."""
    draft = _create_doc(db_session, "Draft Kajian Uji Label C02", PeranDokumen.draft_kajian)
    comp = _create_doc(db_session, "POJK Pembanding C02")

    payload = {
        "versi": "1.0",
        "ringkasan": {
            "total_temuan": 2,
            "per_jenis": {"duplikasi": 1, "memperjelas": 1},
        },
        "temuan": [
            {
                "id": "t-dup",
                "pasal_draft": "Pasal 5",
                "jenis": "duplikasi",
                "pembanding": {"document_id": comp.id, "nomor": comp.regulation_number, "judul": comp.title},
                "pasal_pembanding": "Pasal 12",
                "alasan": "Rumusan ketentuan identik dengan peraturan eksisting.",
            },
            {
                "id": "t-memp",
                "pasal_draft": "Pasal 8",
                "jenis": "memperjelas",
                "pembanding": {"document_id": comp.id, "nomor": comp.regulation_number, "judul": comp.title},
                "pasal_pembanding": "Pasal 15",
                "alasan": "Rumusan ketentuan melengkapi rincian operasional.",
            },
        ],
    }
    _seed_result(db_session, draft, payload)

    # --- A. Ekspor XLSX ---
    res_xlsx = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=xlsx")
    assert res_xlsx.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(res_xlsx.content))

    # Sheet Temuan (Kolom 4 adalah 'Jenis')
    ws_temuan = wb["Temuan"]
    temuan_labels = [row[0] for row in ws_temuan.iter_rows(min_row=2, min_col=4, max_col=4, values_only=True)]
    assert "Tumpang Tindih" in temuan_labels
    assert "Selaras / Melengkapi" in temuan_labels
    assert "Duplikasi" not in temuan_labels
    assert "Memperjelas" not in temuan_labels

    # Sheet Ringkasan: verifikasi hitungan masuk ke "Tumpang Tindih" dan "Selaras / Melengkapi"
    ws_ringkasan = wb["Ringkasan"]
    ringkasan_text = "\n".join([str(cell) for row in ws_ringkasan.iter_rows(values_only=True) for cell in row if cell])
    assert "Tumpang Tindih" in ringkasan_text
    assert "Selaras / Melengkapi" in ringkasan_text

    # --- B. Ekspor Word (DOCX) ---
    res_docx = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=docx")
    assert res_docx.status_code == 200
    doc_word = docx.Document(io.BytesIO(res_docx.content))

    # Periksa tabel temuan
    tbl_cells = [cell.text for row in doc_word.tables[0].rows for cell in row.cells]
    assert "Tumpang Tindih" in tbl_cells
    assert "Selaras / Melengkapi" in tbl_cells
    assert "Duplikasi" not in tbl_cells
    assert "Memperjelas" not in tbl_cells

    # Periksa ringkasan per jenis
    p_texts = [p.text for p in doc_word.paragraphs]
    ringkasan_word = "\n".join(p_texts)
    assert "• Tumpang Tindih: 1" in ringkasan_word
    assert "• Selaras / Melengkapi: 1" in ringkasan_word
    assert "• Duplikasi" not in ringkasan_word
    assert "• Memperjelas" not in ringkasan_word

    # --- C. Ekspor Catatan Dinas (DOCX) ---
    res_cd = client.post(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas", json={})
    assert res_cd.status_code == 200
    doc_cd = docx.Document(io.BytesIO(res_cd.content))
    cd_text = "\n".join([p.text for p in doc_cd.paragraphs])
    assert "Temuan Tumpang Tindih" in cd_text
    assert "Temuan Selaras / Melengkapi" in cd_text
    assert "Temuan Duplikasi" not in cd_text
    assert "Temuan Memperjelas" not in cd_text


def test_c03_nilai_tak_dikenal_fallback_tidak_error(client: TestClient, db_session: Session):
    """3. Nilai jenis tak dikenal (jenis_aneh) tidak error dan memakai fallback lama di tiap format."""
    draft = _create_doc(db_session, "Draft Kajian Uji Fallback C03", PeranDokumen.draft_kajian)
    comp = _create_doc(db_session, "POJK Pembanding C03")

    payload = {
        "versi": "1.0",
        "ringkasan": {
            "total_temuan": 1,
            "per_jenis": {"jenis_aneh": 1},
        },
        "temuan": [
            {
                "id": "t-aneh",
                "pasal_draft": "Pasal 99",
                "jenis": "jenis_aneh",
                "pembanding": {"document_id": comp.id, "nomor": comp.regulation_number, "judul": comp.title},
                "pasal_pembanding": "Pasal 99",
                "alasan": "Uraian temuan dengan kategori yang belum dipetakan.",
            }
        ],
    }
    _seed_result(db_session, draft, payload)

    # 1. XLSX -> 200, sel berisi fallback str(t.get("jenis") or "-")
    res_xlsx = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=xlsx")
    assert res_xlsx.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(res_xlsx.content))
    ws_temuan = wb["Temuan"]
    temuan_labels = [row[0] for row in ws_temuan.iter_rows(min_row=2, min_col=4, max_col=4, values_only=True)]
    assert "jenis_aneh" in temuan_labels

    # 2. Word (DOCX) -> 200, tabel berisi fallback
    res_docx = client.get(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor?format=docx")
    assert res_docx.status_code == 200
    doc_word = docx.Document(io.BytesIO(res_docx.content))
    tbl_cells = [cell.text for row in doc_word.tables[0].rows for cell in row.cells]
    assert "jenis_aneh" in tbl_cells

    # 3. Catatan Dinas -> 200, berisi fallback capitalize ("Temuan Jenis_aneh")
    res_cd = client.post(f"/api/v1/documents/{draft.id}/harmonisasi/ekspor/catatan-dinas", json={})
    assert res_cd.status_code == 200
    doc_cd = docx.Document(io.BytesIO(res_cd.content))
    cd_text = "\n".join([p.text for p in doc_cd.paragraphs])
    assert "Temuan Jenis_aneh" in cd_text
