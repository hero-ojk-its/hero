"""
tests/test_usangkan_cache_analisa.py
Pengujian skrip backend/scripts/usangkan_cache_analisa.py.

Kasus Uji:
1. Dry-run tidak mengubah data dan menampilkan data segar.
2. --apply menandai usang hanya baris yang segar sesuai --kind dan --document-id.
3. Baris yang sudah usang tidak diubah lagi (usang_sejak dan alasan_usang lama dipertahankan).
4. Setelah --apply:
   - get_cached_result(..., expected_fingerprint=fp) -> None (cache hit segar mati).
   - get_cached_result(..., expected_fingerprint=None) -> masih mengembalikan baris (fallback ML mati tetap jalan).
5. Opsi kind 'semua' menandai baik analisa maupun harmonisasi.
6. Validasi CLI main() untuk dry-run dan --apply.
"""
import sys
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.orm import Session

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
from app.services.analysis_result_service import (
    compute_params_hash,
    get_cached_result,
    get_document_fingerprint,
    save_analysis_result,
)
from app.services.audit_service import ANALYSIS_CACHE_INVALIDATED
from scripts.usangkan_cache_analisa import main, run_usangkan_cache_analisa


def _seed_doc(
    db: Session,
    title: str = "Dokumen Uji Cache",
    role: PeranDokumen = PeranDokumen.corpus_eksisting,
    access: KlasifikasiAkses = KlasifikasiAkses.publik,
    **kwargs,
) -> Document:
    uid = uuid.uuid4().hex[:10]
    doc = Document(
        title=f"{title} {uid}",
        regulation_number=f"POJK/TEST/{uid}",
        file_path_pdf=f"pdf/{uid}_test.pdf",
        file_hash=f"hash_{uid}",
        file_size_bytes=2048,
        standardized_filename=f"{uid}.pdf",
        access_classification=access,
        document_role=role,
        status_keberlakuan=StatusKeberlakuan.berlaku,
        processing_status=StatusPemrosesan.terindeks,
        is_active=True,
        full_text="Konten pengujian invalidasi cache analisa.",
        extracted_at=datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc),
        **kwargs,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_dry_run_tidak_mengubah_data(db_session: Session):
    """Dry-run menghitung baris segar, mengelompokkan per kind dan mode, tanpa mengubah data."""
    doc1 = _seed_doc(db_session, title="Doc 1")
    doc2 = _seed_doc(db_session, title="Doc 2")

    fp1 = get_document_fingerprint(doc1)
    fp2 = get_document_fingerprint(doc2)
    hash_analisa = compute_params_hash(JenisAnalisa.analisa)
    hash_harmonisasi = compute_params_hash(JenisAnalisa.harmonisasi)

    # Simpan 3 hasil analisa segar
    row1 = save_analysis_result(
        db_session,
        doc1.id,
        JenisAnalisa.analisa,
        ModeAnalisa.deterministik,
        hash_analisa,
        fp1,
        {"summary": "det doc1"},
        ml_version="v1.0",
    )
    row2 = save_analysis_result(
        db_session,
        doc1.id,
        JenisAnalisa.analisa,
        ModeAnalisa.ai,
        hash_analisa,
        fp1,
        {"summary": "ai doc1"},
        ml_version="v1.0-ai",
    )
    row3 = save_analysis_result(
        db_session,
        doc2.id,
        JenisAnalisa.harmonisasi,
        ModeAnalisa.deterministik,
        hash_harmonisasi,
        fp2,
        {"findings": []},
        ml_version="v2.0",
    )

    # Eksekusi dry-run kind=semua
    res = run_usangkan_cache_analisa(db_session, apply=False, kind="semua")

    assert res["total_segar"] == 3
    assert res["ditandai"] == 0
    assert len(res["contoh"]) == 3
    assert res["breakdown"].get(("analisa", "deterministik")) == 1
    assert res["breakdown"].get(("analisa", "ai")) == 1
    assert res["breakdown"].get(("harmonisasi", "deterministik")) == 1

    # Verifikasi DB tidak tersentuh
    db_session.refresh(row1)
    db_session.refresh(row2)
    db_session.refresh(row3)
    assert row1.usang_sejak is None
    assert row1.alasan_usang is None
    assert row2.usang_sejak is None
    assert row3.usang_sejak is None

    # Pastikan tidak ada audit log yang tercatat
    audit_count = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == ANALYSIS_CACHE_INVALIDATED)
        .count()
    )
    assert audit_count == 0


def test_apply_menandai_usang_hanya_baris_segar_sesuai_kind_dan_document_id(db_session: Session):
    """--apply hanya menandai baris segar yang sesuai --kind dan --document-id."""
    doc1 = _seed_doc(db_session, title="Doc 1")
    doc2 = _seed_doc(db_session, title="Doc 2")

    fp1 = get_document_fingerprint(doc1)
    fp2 = get_document_fingerprint(doc2)
    hash_analisa = compute_params_hash(JenisAnalisa.analisa)
    hash_harmonisasi = compute_params_hash(JenisAnalisa.harmonisasi)

    # Doc 1: analisa & harmonisasi
    row1_analisa = save_analysis_result(
        db_session, doc1.id, JenisAnalisa.analisa, ModeAnalisa.deterministik, hash_analisa, fp1, {"s": 1}
    )
    row1_harmonisasi = save_analysis_result(
        db_session, doc1.id, JenisAnalisa.harmonisasi, ModeAnalisa.deterministik, hash_harmonisasi, fp1, {"h": 1}
    )

    # Doc 2: analisa & harmonisasi
    row2_analisa = save_analysis_result(
        db_session, doc2.id, JenisAnalisa.analisa, ModeAnalisa.deterministik, hash_analisa, fp2, {"s": 2}
    )
    row2_harmonisasi = save_analysis_result(
        db_session, doc2.id, JenisAnalisa.harmonisasi, ModeAnalisa.deterministik, hash_harmonisasi, fp2, {"h": 2}
    )

    # Terapkan apply HANYA untuk doc1 dan kind=analisa
    res = run_usangkan_cache_analisa(
        db_session,
        apply=True,
        kind="analisa",
        document_ids=[doc1.id],
        alasan="PR #209 perbarui ringkasan",
    )

    assert res["total_segar"] == 1
    assert res["ditandai"] == 1

    db_session.refresh(row1_analisa)
    db_session.refresh(row1_harmonisasi)
    db_session.refresh(row2_analisa)
    db_session.refresh(row2_harmonisasi)

    # row1_analisa harus ditandai usang
    assert row1_analisa.usang_sejak is not None
    assert row1_analisa.alasan_usang == "PR #209 perbarui ringkasan"

    # Baris lain tetap segar
    assert row1_harmonisasi.usang_sejak is None
    assert row2_analisa.usang_sejak is None
    assert row2_harmonisasi.usang_sejak is None

    # Terdapat satu entri audit log
    audit_entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == ANALYSIS_CACHE_INVALIDATED)
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.detail.get("ditandai") == 1
    assert audit_entry.detail.get("kind") == "analisa"
    assert audit_entry.detail.get("alasan") == "PR #209 perbarui ringkasan"
    assert audit_entry.detail.get("document_ids") == [doc1.id]


def test_baris_yang_sudah_usang_tidak_diubah_lagi(db_session: Session):
    """Baris yang sudah usang tidak diubah lagi (usang_sejak dan alasan lama dipertahankan)."""
    doc = _seed_doc(db_session, title="Doc Stale")
    fp = get_document_fingerprint(doc)
    hash_analisa = compute_params_hash(JenisAnalisa.analisa)

    # 1. Row deterministik: sudah usang sejak kemarin
    waktu_usang_lama = datetime.now(timezone.utc) - timedelta(days=2)
    row_stale = save_analysis_result(
        db_session, doc.id, JenisAnalisa.analisa, ModeAnalisa.deterministik, hash_analisa, fp, {"mode": "det"}
    )
    row_stale.usang_sejak = waktu_usang_lama
    row_stale.alasan_usang = "alasan lama usang"
    db_session.commit()
    db_session.refresh(row_stale)

    # 2. Row AI: masih segar
    row_fresh = save_analysis_result(
        db_session, doc.id, JenisAnalisa.analisa, ModeAnalisa.ai, hash_analisa, fp, {"mode": "ai"}
    )
    assert row_fresh.usang_sejak is None

    # Eksekusi --apply
    res = run_usangkan_cache_analisa(
        db_session,
        apply=True,
        kind="analisa",
        document_ids=[doc.id],
        alasan="alasan baru 2026",
    )

    assert res["total_segar"] == 1
    assert res["ditandai"] == 1

    db_session.refresh(row_stale)
    db_session.refresh(row_fresh)

    # Row stale lama TIDAK BERUBAH
    assert row_stale.alasan_usang == "alasan lama usang"
    # Bandingkan hingga detik untuk menghindari masalah microsecond timezone rounding
    assert abs((row_stale.usang_sejak - waktu_usang_lama).total_seconds()) < 1.0

    # Row fresh berubah menjadi usang dengan alasan baru
    assert row_fresh.usang_sejak is not None
    assert row_fresh.alasan_usang == "alasan baru 2026"

    # Jalankan ulang --apply saat semua baris sudah usang
    res2 = run_usangkan_cache_analisa(
        db_session,
        apply=True,
        kind="analisa",
        document_ids=[doc.id],
        alasan="coba lagi",
    )
    assert res2["total_segar"] == 0
    assert res2["ditandai"] == 0


def test_setelah_apply_get_cached_result_expected_fingerprint_mengembalikan_none_dan_fallback_tetap_jalan(
    db_session: Session,
):
    """Setelah --apply, expected_fingerprint mengembalikan None tapi expected_fingerprint=None tetap jalan."""
    doc = _seed_doc(db_session, title="Doc Cache Check")
    fp = get_document_fingerprint(doc)
    hash_analisa = compute_params_hash(JenisAnalisa.analisa)

    row = save_analysis_result(
        db_session,
        doc.id,
        JenisAnalisa.analisa,
        ModeAnalisa.deterministik,
        hash_analisa,
        fp,
        {"summary": "hasil awal"},
        ml_version="v2.0",
    )

    # Sebelum apply: cache hit segar dan fallback keduanya mengembalikan row
    cached_fresh = get_cached_result(
        db_session, doc.id, JenisAnalisa.analisa, ModeAnalisa.deterministik, hash_analisa, expected_fingerprint=fp
    )
    assert cached_fresh is not None
    assert cached_fresh.id == row.id

    cached_fallback = get_cached_result(
        db_session, doc.id, JenisAnalisa.analisa, ModeAnalisa.deterministik, hash_analisa, expected_fingerprint=None
    )
    assert cached_fallback is not None
    assert cached_fallback.id == row.id

    # Jalankan apply
    run_usangkan_cache_analisa(
        db_session,
        apply=True,
        kind="analisa",
        document_ids=[doc.id],
        alasan="pipeline diperbarui",
    )

    # Setelah apply:
    # 1. expected_fingerprint=<fingerprint sama> mengembalikan None (cache segar tidak dipakai)
    cached_after_fresh = get_cached_result(
        db_session, doc.id, JenisAnalisa.analisa, ModeAnalisa.deterministik, hash_analisa, expected_fingerprint=fp
    )
    assert cached_after_fresh is None, "Cache segar seharusnya None setelah diusangkan"

    # 2. expected_fingerprint=None masih mengembalikan baris (cadangan saat ML mati tetap jalan)
    cached_after_fallback = get_cached_result(
        db_session, doc.id, JenisAnalisa.analisa, ModeAnalisa.deterministik, hash_analisa, expected_fingerprint=None
    )
    assert cached_after_fallback is not None, "Fallback saat ML mati harus tetap mengembalikan data tersimpan"
    assert cached_after_fallback.id == row.id
    assert cached_after_fallback.usang_sejak is not None


def test_kind_semua_menandai_semua_jenis_analisa(db_session: Session):
    """Pilihan kind='semua' menandai baik analisa maupun harmonisasi."""
    doc = _seed_doc(db_session, title="Doc Semua Kind")
    fp = get_document_fingerprint(doc)
    hash_analisa = compute_params_hash(JenisAnalisa.analisa)
    hash_harmonisasi = compute_params_hash(JenisAnalisa.harmonisasi)

    row_a = save_analysis_result(
        db_session, doc.id, JenisAnalisa.analisa, ModeAnalisa.deterministik, hash_analisa, fp, {"res": "a"}
    )
    row_h = save_analysis_result(
        db_session, doc.id, JenisAnalisa.harmonisasi, ModeAnalisa.deterministik, hash_harmonisasi, fp, {"res": "h"}
    )

    res = run_usangkan_cache_analisa(db_session, apply=True, kind="semua", document_ids=[doc.id])
    assert res["total_segar"] == 2
    assert res["ditandai"] == 2

    db_session.refresh(row_a)
    db_session.refresh(row_h)
    assert row_a.usang_sejak is not None
    assert row_h.usang_sejak is not None


def test_cli_main_eksekusi(monkeypatch, db_session: Session):
    """Memastikan fungsi main() CLI dapat dipanggil tanpa error untuk dry-run dan --apply."""
    doc = _seed_doc(db_session, title="Doc CLI")
    fp = get_document_fingerprint(doc)
    hash_analisa = compute_params_hash(JenisAnalisa.analisa)

    row = save_analysis_result(
        db_session, doc.id, JenisAnalisa.analisa, ModeAnalisa.deterministik, hash_analisa, fp, {"res": "cli"}
    )

    # 1. Panggilan CLI dry-run
    monkeypatch.setattr(
        sys,
        "argv",
        ["usangkan_cache_analisa.py", "--kind", "analisa", "--document-id", str(doc.id)],
    )
    main()

    db_session.refresh(row)
    assert row.usang_sejak is None

    # 2. Panggilan CLI --apply
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "usangkan_cache_analisa.py",
            "--apply",
            "--kind",
            "analisa",
            "--document-id",
            str(doc.id),
            "--alasan",
            "uji coba main",
        ],
    )
    main()

    db_session.refresh(row)
    assert row.usang_sejak is not None
    assert row.alasan_usang == "uji coba main"

