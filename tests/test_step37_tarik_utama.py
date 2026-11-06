"""
tests/test_step37_tarik_utama.py
Pengujian unit dan integrasi untuk Langkah 37:
- T01 s.d. T05: tarik_semua.py hanya menarik dokumen utama & opsi --termasuk-non-utama.
- L01 s.d. L09: Pengenal lampiran tepat (determine_doc_kind).
- N01 s.d. N02: periksa_dokumen_non_utama.py dry-run & apply & filter jenis.
- K01 s.d. K05: periksa_konsistensi_pasal.py dry-run, nonaktifkan, antrekan ulang, & default storage.
"""

from datetime import datetime, timezone
import hashlib
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.crawlers.base import FetchedFile
from app.crawlers.generic_html import SimpleHttpCrawler
from app.crawlers.url_utils import determine_doc_kind
from app.models.article import Article
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.enums import (
    JenisSumber,
    KlasifikasiAkses,
    PeranDokumen,
    StatusKandidat,
    StatusPemrosesan,
    StatusPindai,
)
from app.models.scan_candidate import ScanCandidate
from app.models.scan_session import ScanSession
from app.models.scraping_source import ScrapingSource
from app.services.audit_service import DEACTIVATE_DOCUMENT, EXTRACTION_REQUEUED
from app.services.scan_service import NON_UTAMA_DOC_KINDS as SCAN_NON_UTAMA
from scripts.periksa_dokumen_non_utama import periksa_dokumen_non_utama
from scripts.periksa_konsistensi_pasal import periksa_konsistensi_pasal
from scripts.tarik_semua import (
    NON_UTAMA_DOC_KINDS as SCRIPT_NON_UTAMA,
    OpsiTarik,
    jalankan,
)
from tests.conftest import make_pdf, test_engine


@pytest.fixture(autouse=True)
def patch_scan_engine(monkeypatch, client: TestClient, db_session: Session):
    """Pastikan engine pada scan_service selalu memakai test_engine dan sesi DB selalu segar."""
    monkeypatch.setattr("app.services.scan_service.engine", test_engine)

    orig_request = client.request

    def refreshing_request(*args, **kwargs):
        db_session.expire_all()
        resp = orig_request(*args, **kwargs)
        db_session.expire_all()
        return resp

    monkeypatch.setattr(client, "request", refreshing_request)


def _seed_source(db: Session, name: str = "Sumber Step 37", is_active: bool = True) -> ScrapingSource:
    source = ScrapingSource(
        name=name,
        url=f"https://example.com/{name.lower().replace(' ', '_')}_{int(datetime.now().timestamp() * 1000)}",
        source_type=JenisSumber.situs_web,
        is_active=is_active,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def _seed_scan_session(
    db: Session,
    source_id: int,
    status: StatusPindai = StatusPindai.siap_dipilih,
) -> ScanSession:
    sess = ScanSession(
        source_id=source_id,
        start_url=f"https://example.com/source/{source_id}",
        crawl_depth=1,
        status=status,
        pages_visited=5,
        cancel_requested=False,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def _seed_candidate(
    db: Session,
    scan_id: int,
    filename: str,
    match_status: StatusKandidat = StatusKandidat.baru,
    pull_outcome: str | None = None,
    doc_kind: str | None = None,
    selected: bool = False,
    document_id: int | None = None,
) -> ScanCandidate:
    url = f"https://example.com/files/{filename}_{int(datetime.now().timestamp() * 1000)}"
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    cand = ScanCandidate(
        scan_id=scan_id,
        url=url,
        url_hash=url_hash,
        filename=filename,
        document_title=f"Judul {filename}",
        match_status=match_status,
        pull_outcome=pull_outcome,
        doc_kind=doc_kind,
        selected=selected,
        document_id=document_id,
    )
    db.add(cand)
    db.commit()
    db.refresh(cand)
    return cand


def _mock_successful_fetch(self, url: str, max_bytes: int | None = None) -> FetchedFile:
    filename = url.split("/")[-1] or "dokumen.pdf"
    content = make_pdf(f"Isi Dokumen {filename} untuk penarikan UAT Step 37")
    return FetchedFile(
        content=content,
        filename=filename,
        content_type="application/pdf",
        final_url=url,
    )


def _seed_doc(
    db: Session,
    title: str,
    original_filename: str,
    file_path_pdf: str = "regulasi/dummy.pdf",
    file_size_bytes: int = 1024,
    processing_status: StatusPemrosesan = StatusPemrosesan.terindeks,
    is_active: bool = True,
    metadata_corrected_at: datetime | None = None,
) -> Document:
    doc_hash = hashlib.sha256(f"{title}_{original_filename}_{datetime.now().timestamp()}".encode()).hexdigest()
    doc = Document(
        title=title,
        original_filename=original_filename,
        file_path_pdf=file_path_pdf,
        file_size_bytes=file_size_bytes,
        file_hash=doc_hash,
        processing_status=processing_status,
        is_active=is_active,
        metadata_corrected_at=metadata_corrected_at,
        access_classification=KlasifikasiAkses.publik,
        document_role=PeranDokumen.corpus_eksisting,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# ==============================================================================
# §1. Penarikan Dokumen Utama (T01 - T05)
# ==============================================================================

def test_t01_dry_run_campuran_hanya_tarik_utama(client: TestClient, db_session: Session):
    """
    T01: Dry-run tarik_semua dengan kandidat campuran
    (3 utama, 1 abstrak, 1 faq, 1 lampiran, 1 doc_kind null).
    Ekspektasi: perlu ditarik = 4 (null = utama); rincian dilewati benar; hanya GET.
    """
    source = _seed_source(db_session, "Sumber T01")
    sess = _seed_scan_session(db_session, source.id, StatusPindai.siap_dipilih)

    _seed_candidate(db_session, sess.id, "utama_1.pdf", StatusKandidat.baru, None, doc_kind="utama")
    _seed_candidate(db_session, sess.id, "utama_2.pdf", StatusKandidat.baru, None, doc_kind="utama")
    _seed_candidate(db_session, sess.id, "utama_3.pdf", StatusKandidat.baru, None, doc_kind="utama")
    _seed_candidate(db_session, sess.id, "abstrak_1.pdf", StatusKandidat.baru, None, doc_kind="abstrak")
    _seed_candidate(db_session, sess.id, "faq_1.pdf", StatusKandidat.baru, None, doc_kind="faq")
    _seed_candidate(db_session, sess.id, "lampiran_1.pdf", StatusKandidat.baru, None, doc_kind="lampiran")
    _seed_candidate(db_session, sess.id, "null_kind.pdf", StatusKandidat.baru, None, doc_kind=None)

    observed_methods: list[str] = []
    orig_request = client.request

    def spy_request(method, url, *args, **kwargs):
        observed_methods.append(method.upper())
        return orig_request(method, url, *args, **kwargs)

    with patch.object(client, "request", side_effect=spy_request):
        ringkasan = jalankan(client, OpsiTarik(apply=False))

    assert ringkasan.total_perlu_ditarik == 4  # 3 utama + 1 null
    assert ringkasan.total_dilewati_non_utama == 3
    hs = ringkasan.sumber_list[0]
    assert hs.perlu_ditarik == 4
    assert hs.utama_count == 4
    assert hs.dilewati_non_utama_count == 3
    assert hs.non_utama_breakdown == {"abstrak": 1, "faq": 1, "lampiran": 1, "non_regulasi": 0}
    assert hs.catatan == "dry-run"
    assert all(m == "GET" for m in observed_methods)


def test_t02_apply_hanya_pilih_utama(client: TestClient, db_session: Session):
    """
    T02: --apply dengan kandidat campuran.
    Ekspektasi: patch selection hanya memilih 4 id utama; body pull tanpa category_id.
    """
    source = _seed_source(db_session, "Sumber T02")
    sess = _seed_scan_session(db_session, source.id, StatusPindai.siap_dipilih)

    c1 = _seed_candidate(db_session, sess.id, "u1.pdf", StatusKandidat.baru, None, doc_kind="utama")
    c2 = _seed_candidate(db_session, sess.id, "u2.pdf", StatusKandidat.baru, None, doc_kind="utama")
    c3 = _seed_candidate(db_session, sess.id, "u3.pdf", StatusKandidat.baru, None, doc_kind="utama")
    _seed_candidate(db_session, sess.id, "a1.pdf", StatusKandidat.baru, None, doc_kind="abstrak")
    _seed_candidate(db_session, sess.id, "f1.pdf", StatusKandidat.baru, None, doc_kind="faq")
    _seed_candidate(db_session, sess.id, "l1.pdf", StatusKandidat.baru, None, doc_kind="lampiran")
    c4 = _seed_candidate(db_session, sess.id, "null_kind.pdf", StatusKandidat.baru, None, doc_kind=None)

    expected_ids = sorted([c1.id, c2.id, c3.id, c4.id])

    patch_payloads: list[dict] = []
    pull_payloads: list[dict] = []
    orig_patch = client.patch
    orig_post = client.post

    def spy_patch(url, *args, **kwargs):
        if "/selection" in url and "json" in kwargs:
            patch_payloads.append(kwargs["json"])
        return orig_patch(url, *args, **kwargs)

    def spy_post(url, *args, **kwargs):
        if "/pull" in url and "json" in kwargs:
            pull_payloads.append(kwargs["json"])
        return orig_post(url, *args, **kwargs)

    with patch.object(client, "patch", side_effect=spy_patch), \
         patch.object(client, "post", side_effect=spy_post), \
         patch.object(SimpleHttpCrawler, "fetch", new=_mock_successful_fetch):
        ringkasan = jalankan(client, OpsiTarik(apply=True, interval=0))

    set_calls = [p for p in patch_payloads if p.get("action") == "set"]
    assert len(set_calls) == 1
    assert set_calls[0]["candidate_ids"] == expected_ids

    assert len(pull_payloads) == 1
    assert pull_payloads[0] == {"destination": "knowledge_base"}
    assert "category_id" not in pull_payloads[0]
    assert ringkasan.total_perlu_ditarik == 4
    assert ringkasan.total_dilewati_non_utama == 3


def test_t03_termasuk_non_utama(client: TestClient, db_session: Session):
    """
    T03: --termasuk-non-utama.
    Ekspektasi: semua 7 kandidat dipilih.
    """
    source = _seed_source(db_session, "Sumber T03")
    sess = _seed_scan_session(db_session, source.id, StatusPindai.siap_dipilih)

    cands = [
        _seed_candidate(db_session, sess.id, f"cand_{i}.pdf", StatusKandidat.baru, None, doc_kind=k)
        for i, k in enumerate(["utama", "utama", "utama", "abstrak", "faq", "lampiran", None])
    ]
    all_ids = sorted([c.id for c in cands])

    patch_payloads: list[dict] = []
    orig_patch = client.patch

    def spy_patch(url, *args, **kwargs):
        if "/selection" in url and "json" in kwargs:
            patch_payloads.append(kwargs["json"])
        return orig_patch(url, *args, **kwargs)

    with patch.object(client, "patch", side_effect=spy_patch), \
         patch.object(SimpleHttpCrawler, "fetch", new=_mock_successful_fetch):
        ringkasan = jalankan(client, OpsiTarik(apply=True, interval=0, termasuk_non_utama=True))

    set_calls = [p for p in patch_payloads if p.get("action") == "set"]
    assert len(set_calls) == 1
    assert set_calls[0]["candidate_ids"] == all_ids
    assert ringkasan.total_perlu_ditarik == 7
    assert ringkasan.total_dilewati_non_utama == 0


def test_t04_batas_dihitung_setelah_penyaringan(client: TestClient, db_session: Session):
    """
    T04: --batas 2 dengan kandidat non-utama di urutan awal.
    Ekspektasi: 2 id utama dipilih (batas dihitung setelah non-utama disaring).
    """
    source = _seed_source(db_session, "Sumber T04")
    sess = _seed_scan_session(db_session, source.id, StatusPindai.siap_dipilih)

    # Buat non-utama terlebih dahulu sehingga ID lebih kecil
    _seed_candidate(db_session, sess.id, "a1.pdf", StatusKandidat.baru, None, doc_kind="abstrak")
    _seed_candidate(db_session, sess.id, "f1.pdf", StatusKandidat.baru, None, doc_kind="faq")
    c_u1 = _seed_candidate(db_session, sess.id, "u1.pdf", StatusKandidat.baru, None, doc_kind="utama")
    c_u2 = _seed_candidate(db_session, sess.id, "u2.pdf", StatusKandidat.baru, None, doc_kind="utama")
    _seed_candidate(db_session, sess.id, "u3.pdf", StatusKandidat.baru, None, doc_kind="utama")

    patch_payloads: list[dict] = []
    orig_patch = client.patch

    def spy_patch(url, *args, **kwargs):
        if "/selection" in url and "json" in kwargs:
            patch_payloads.append(kwargs["json"])
        return orig_patch(url, *args, **kwargs)

    with patch.object(client, "patch", side_effect=spy_patch), \
         patch.object(SimpleHttpCrawler, "fetch", new=_mock_successful_fetch):
        ringkasan = jalankan(client, OpsiTarik(apply=True, batas=2, interval=0))

    set_calls = [p for p in patch_payloads if p.get("action") == "set"]
    assert len(set_calls) == 1
    assert set_calls[0]["candidate_ids"] == [c_u1.id, c_u2.id]
    assert ringkasan.total_perlu_ditarik == 2


def test_t05_konstanta_set_sama_dengan_scan_service():
    """
    T05: Konstanta set NON_UTAMA_DOC_KINDS di scripts/tarik_semua.py
    sama persis dengan di app/services/scan_service.py.
    """
    assert SCRIPT_NON_UTAMA == SCAN_NON_UTAMA
    assert SCRIPT_NON_UTAMA == {"abstrak", "faq", "lampiran", "non_regulasi"}


# ==============================================================================
# §2. Pengenal Lampiran Tepat (L01 - L09)
# ==============================================================================

def test_l01_lampiran_awalan_sp_faq():
    assert determine_doc_kind("Lampiran SP - FAQ POJK 5") == "lampiran"


def test_l02_lampiran_kompak_nomor():
    assert determine_doc_kind("lampiran1pojktrust.pdf") == "lampiran"


def test_l03_lamp_kompak_kode():
    assert determine_doc_kind("lamppojk12.pdf") == "lampiran"


def test_l04_label_lampiran_judul_pojk():
    assert determine_doc_kind("POJK 5 Tahun 2024", label="Lampiran") == "lampiran"


def test_l05_judul_perubahan_atas_lampiran_utama():
    assert determine_doc_kind("POJK Nomor 3 Tahun 2023 tentang Perubahan atas Lampiran POJK Nomor 1 Tahun 2020") == "utama"


def test_l06_filename_perubahan_atas_lampiran_utama():
    assert determine_doc_kind("perubahan-atas-lampiran-pojk-5-2024.pdf") == "utama"


def test_l07_seojk_pedoman_pengisian_lampiran_utama():
    assert determine_doc_kind("SEOJK tentang Pedoman Pengisian Lampiran Laporan Bulanan") == "utama"


def test_l08_salinan_pojk_utama():
    assert determine_doc_kind("Salinan POJK 12 2025.pdf") == "utama"


def test_l09_faq_dan_abstrak_tetap():
    assert determine_doc_kind("faq_pbi_101708.pdf") == "faq"
    assert determine_doc_kind("2026abspojk008.pdf") == "abstrak"
    assert determine_doc_kind("2024lampiranseojk3.pdf") == "lampiran"


# ==============================================================================
# §3. Pemeriksa Dokumen Non-Utama (N01 - N02)
# ==============================================================================

def test_n01_periksa_dokumen_non_utama_dry_run_dan_apply(db_session: Session):
    """
    N01: periksa_dokumen_non_utama.py dry-run lalu --apply.
    Seed: 1 abstrak via kandidat, 1 faq via nama berkas, 1 utama, 1 abstrak terkoreksi manual.
    Ekspektasi: dry-run tidak mengubah DB; apply menonaktifkan 2 dokumen + audit;
    dokumen terkoreksi manual dilewati.
    """
    source = _seed_source(db_session, "Sumber N01")
    sess = _seed_scan_session(db_session, source.id)

    # 1. Dokumen abstrak via kandidat
    d_abs = _seed_doc(db_session, "Peraturan Terkait 1", "peraturan_1.pdf")
    _seed_candidate(db_session, sess.id, "cand_abs.pdf", doc_kind="abstrak", document_id=d_abs.id)

    # 2. Dokumen FAQ via nama berkas
    d_faq = _seed_doc(db_session, "Tanya Jawab Aturan", "faq_pojk_2025.pdf")

    # 3. Dokumen utama normal
    d_utama = _seed_doc(db_session, "POJK 10 Tahun 2025", "pojk102025.pdf")

    # 4. Dokumen abstrak tapi dikoreksi manual
    d_manual = _seed_doc(
        db_session,
        "Abstrak Resmi Yang Disetujui",
        "abstrak_manual.pdf",
        metadata_corrected_at=datetime.now(timezone.utc),
    )

    # Jalankan DRY-RUN
    res_dry = periksa_dokumen_non_utama(db=db_session, apply=False)
    assert res_dry["total_target"] == 2
    assert res_dry["total_dilewati_manual"] == 1
    assert set(res_dry["target_ids"]) == {d_abs.id, d_faq.id}
    assert res_dry["manual_ids"] == [d_manual.id]

    # Verifikasi DB belum berubah
    db_session.refresh(d_abs)
    db_session.refresh(d_faq)
    db_session.refresh(d_utama)
    db_session.refresh(d_manual)
    assert d_abs.is_active is True
    assert d_faq.is_active is True
    assert d_utama.is_active is True
    assert d_manual.is_active is True

    # Jalankan APPLY
    res_apply = periksa_dokumen_non_utama(db=db_session, apply=True)
    assert res_apply["total_dinonaktifkan"] == 2

    db_session.refresh(d_abs)
    db_session.refresh(d_faq)
    db_session.refresh(d_utama)
    db_session.refresh(d_manual)

    assert d_abs.is_active is False
    assert d_abs.deactivated_reason == "bukan_dokumen_utama"
    assert d_faq.is_active is False
    assert d_faq.deactivated_reason == "bukan_dokumen_utama"
    assert d_utama.is_active is True
    assert d_manual.is_active is True  # Dilewati!

    # Verifikasi jejak audit
    audits = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == DEACTIVATE_DOCUMENT)
        .filter(AuditLog.target_resource.in_([f"document:{d_abs.id}", f"document:{d_faq.id}"]))
        .all()
    )
    assert len(audits) == 2


def test_n02_periksa_dokumen_non_utama_filter_jenis(db_session: Session):
    """
    N02: periksa_dokumen_non_utama.py dengan filter --jenis faq.
    Ekspektasi: hanya dokumen FAQ yang terdeteksi dan dinonaktifkan.
    """
    source = _seed_source(db_session, "Sumber N02")
    sess = _seed_scan_session(db_session, source.id)

    d_abs = _seed_doc(db_session, "Peraturan Terkait Abstrak", "dok_abs.pdf")
    _seed_candidate(db_session, sess.id, "cand_abs2.pdf", doc_kind="abstrak", document_id=d_abs.id)

    d_faq = _seed_doc(db_session, "Tanya Jawab Perbankan", "faq_bank.pdf")

    res = periksa_dokumen_non_utama(db=db_session, apply=True, jenis_filter={"faq"})
    assert res["total_target"] == 1
    assert res["target_ids"] == [d_faq.id]

    db_session.refresh(d_abs)
    db_session.refresh(d_faq)
    assert d_abs.is_active is True
    assert d_faq.is_active is False


# ==============================================================================
# §4. Pemeriksa Konsistensi PDF - Pasal (K01 - K04)
# ==============================================================================

class MockStorageService:
    def __init__(self, existing_paths: set[str]):
        self.existing_paths = existing_paths

    def exists(self, path: str) -> bool:
        return path in self.existing_paths


def test_k01_konsistensi_pasal_dry_run(db_session: Session):
    """
    K01: periksa_konsistensi_pasal.py dry-run.
    Seed:
    - A1: tanpa path (file_path_pdf=None)
    - A2: berkas hilang (file_path_pdf="regulasi/missing.pdf")
    - B: ber-PDF tanpa pasal (status terindeks)
    - C: pasal yatim (merujuk ke dokumen nonaktif atau hilang)
    - Normal: ber-PDF dengan pasal
    Ekspektasi: tiap kelompok terhitung benar; DB tidak berubah.
    """
    mock_storage = MockStorageService(existing_paths={"regulasi/doc_b.pdf", "regulasi/doc_normal.pdf"})

    # Kelompok A:
    doc_a1 = _seed_doc(db_session, "Doc A1 Tanpa Path", "a1.pdf", file_path_pdf="")
    doc_a2 = _seed_doc(db_session, "Doc A2 File Hilang", "a2.pdf", file_path_pdf="regulasi/missing.pdf")

    # Kelompok B:
    doc_b = _seed_doc(
        db_session,
        "Doc B Ber-PDF Tanpa Pasal",
        "b.pdf",
        file_path_pdf="regulasi/doc_b.pdf",
        processing_status=StatusPemrosesan.terindeks,
    )

    # Dokumen normal:
    doc_normal = _seed_doc(
        db_session,
        "Doc Normal",
        "normal.pdf",
        file_path_pdf="regulasi/doc_normal.pdf",
        processing_status=StatusPemrosesan.terindeks,
    )
    art_norm = Article(
        document_id=doc_normal.id,
        article_number="Pasal 1",
        content_text="Ketentuan umum normal.",
    )
    db_session.add(art_norm)

    # Kelompok C: Dokumen nonaktif yang punya pasal
    doc_inactive = _seed_doc(
        db_session,
        "Doc Inactive",
        "inactive.pdf",
        file_path_pdf="regulasi/inactive.pdf",
        is_active=False,
    )
    art_orphan = Article(
        document_id=doc_inactive.id,
        article_number="Pasal 1",
        content_text="Pasal milik dokumen nonaktif.",
    )
    db_session.add(art_orphan)
    db_session.commit()

    res = periksa_konsistensi_pasal(db=db_session, storage=mock_storage)

    assert res["kelompok_a_count"] >= 2
    assert doc_a1.id in res["kelompok_a_ids"]
    assert doc_a2.id in res["kelompok_a_ids"]
    assert res["kelompok_b_count"] >= 1
    assert doc_b.id in res["kelompok_b_ids"]
    assert res["kelompok_c_article_count"] >= 1

    # Verifikasi DB tidak berubah sama sekali
    db_session.refresh(doc_a1)
    db_session.refresh(doc_a2)
    db_session.refresh(doc_b)
    assert doc_a1.is_active is True
    assert doc_a2.is_active is True
    assert doc_b.processing_status == StatusPemrosesan.terindeks


def test_k02_konsistensi_pasal_nonaktifkan_tanpa_pdf(db_session: Session):
    """
    K02: --nonaktifkan-tanpa-pdf.
    Ekspektasi: hanya kelompok A dinonaktifkan; pasal miliknya tetap ada.
    """
    mock_storage = MockStorageService(existing_paths={"regulasi/doc_b2.pdf"})

    doc_a = _seed_doc(db_session, "Doc A Hilang", "a.pdf", file_path_pdf="regulasi/missing2.pdf")
    # Tambahkan pasal ke doc_a untuk memastikan pasalnya tidak terhapus saat dinonaktifkan
    art_a = Article(document_id=doc_a.id, article_number="Pasal 1", content_text="Pasal tetap ada.")
    db_session.add(art_a)

    doc_b = _seed_doc(
        db_session,
        "Doc B Aman",
        "b.pdf",
        file_path_pdf="regulasi/doc_b2.pdf",
        processing_status=StatusPemrosesan.terindeks,
    )
    db_session.commit()

    res = periksa_konsistensi_pasal(
        db=db_session,
        storage=mock_storage,
        nonaktifkan_tanpa_pdf=True,
    )
    assert res["a_deactivated"] == 1

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)

    assert doc_a.is_active is False
    assert doc_a.deactivated_reason == "berkas_pdf_hilang"
    assert doc_b.is_active is True

    # Verifikasi pasal tidak terhapus
    art_check = db_session.query(Article).filter(Article.document_id == doc_a.id).first()
    assert art_check is not None
    assert art_check.content_text == "Pasal tetap ada."

    # Jejak audit
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == DEACTIVATE_DOCUMENT, AuditLog.target_resource == f"document:{doc_a.id}")
        .first()
    )
    assert audit is not None


def test_k03_konsistensi_pasal_antrekan_ulang_tanpa_pasal(db_session: Session):
    """
    K03: --antrekan-ulang-tanpa-pasal.
    Ekspektasi: kelompok B dikembalikan ke status 'diterima' dan claimed_at di-reset.
    """
    mock_storage = MockStorageService(existing_paths={"regulasi/doc_b3.pdf"})

    doc_b = _seed_doc(
        db_session,
        "Doc B Butuh Ekstraksi",
        "b.pdf",
        file_path_pdf="regulasi/doc_b3.pdf",
        processing_status=StatusPemrosesan.terindeks,
    )
    doc_b.extraction_claimed_at = datetime.now(timezone.utc)
    db_session.commit()

    res = periksa_konsistensi_pasal(
        db=db_session,
        storage=mock_storage,
        antrekan_ulang_tanpa_pasal=True,
    )
    assert res["b_requeued"] == 1

    db_session.refresh(doc_b)
    assert doc_b.processing_status == StatusPemrosesan.diterima
    assert doc_b.extraction_claimed_at is None

    # Verifikasi audit log
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == EXTRACTION_REQUEUED, AuditLog.target_resource == f"document:{doc_b.id}")
        .first()
    )
    assert audit is not None


def test_k04_konsistensi_pasal_tanpa_opsi_tindakan_db_utuh(db_session: Session):
    """
    K04: Tanpa opsi tindakan (dry-run).
    Ekspektasi: tidak ada perubahan status atau baris pada DB.
    """
    mock_storage = MockStorageService(existing_paths=set())

    doc_a = _seed_doc(db_session, "Doc A", "a.pdf", file_path_pdf="missing.pdf")
    doc_b = _seed_doc(db_session, "Doc B", "b.pdf", file_path_pdf="", processing_status=StatusPemrosesan.terindeks)

    status_before_a = (doc_a.is_active, doc_a.processing_status)
    status_before_b = (doc_b.is_active, doc_b.processing_status)

    periksa_konsistensi_pasal(db=db_session, storage=mock_storage)

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)

    assert (doc_a.is_active, doc_a.processing_status) == status_before_a
    assert (doc_b.is_active, doc_b.processing_status) == status_before_b


def test_k05_konsistensi_pasal_default_storage_service(db_session: Session, tmp_path, monkeypatch: pytest.MonkeyPatch):
    """
    K05: Panggil periksa_konsistensi_pasal tanpa parameter storage (memakai default StorageService).
    Memastikan inisialisasi default StorageService(base_path=settings.storage_path) bekerja tanpa error
    dan mendeteksi berkas fisik secara nyata di filesystem.
    """
    from app.config import settings

    fake_storage = tmp_path / "storage_k05"
    fake_storage.mkdir(parents=True, exist_ok=True)
    reg_dir = fake_storage / "regulasi"
    reg_dir.mkdir(parents=True, exist_ok=True)
    pdf_ada = reg_dir / "ada.pdf"
    pdf_ada.write_bytes(b"%PDF-1.4 dummy")

    monkeypatch.setattr(settings, "storage_path", str(fake_storage))

    # Doc A: PDF tidak ada di fake_storage
    doc_a = _seed_doc(db_session, "Doc A Hilang K05", "a.pdf", file_path_pdf="regulasi/hilang.pdf")

    # Doc B: PDF ada di fake_storage, status terindeks, 0 pasal
    doc_b = _seed_doc(
        db_session,
        "Doc B Ber-PDF K05",
        "ada.pdf",
        file_path_pdf="regulasi/ada.pdf",
        processing_status=StatusPemrosesan.terindeks,
    )

    # Panggil fungsi tanpa argumen storage= (default StorageService harus dibuat via settings.storage_path)
    res = periksa_konsistensi_pasal(db=db_session)

    assert res["kelompok_a_count"] >= 1
    assert doc_a.id in res["kelompok_a_ids"]
    assert res["kelompok_b_count"] >= 1
    assert doc_b.id in res["kelompok_b_ids"]

