"""
tests/test_step31_tarik_semua.py
Pengujian unit untuk skrip tarik_semua.py (Langkah 31).
Kasus uji A01 s.d. A12.
"""

import hashlib
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy.orm import Session

from app.crawlers.base import FetchedFile
from app.crawlers.generic_html import SimpleHttpCrawler
from app.models.document import Document
from app.models.enums import JenisSumber, StatusKandidat, StatusPindai
from app.models.scan_candidate import ScanCandidate
from app.models.scan_session import ScanSession
from app.models.scraping_source import ScrapingSource
from scripts.tarik_semua import OpsiTarik, Ringkasan, cetak_laporan, jalankan, main
from tests.conftest import make_pdf, test_engine


@pytest.fixture(autouse=True)
def patch_scan_engine(monkeypatch, client: TestClient, db_session: Session):
    """Pastikan engine pada scan_service selalu memakai test_engine (hero_test) dan sesi DB selalu segar."""
    monkeypatch.setattr("app.services.scan_service.engine", test_engine)

    orig_request = client.request

    def refreshing_request(*args, **kwargs):
        db_session.expire_all()
        resp = orig_request(*args, **kwargs)
        db_session.expire_all()
        return resp

    monkeypatch.setattr(client, "request", refreshing_request)


def _seed_source(db: Session, name: str = "Sumber Uji", is_active: bool = True) -> ScrapingSource:
    source = ScrapingSource(
        name=name,
        url=f"https://example.com/{name.lower().replace(' ', '_')}",
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
    selected: bool = False,
) -> ScanCandidate:
    url = f"https://example.com/files/{filename}"
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    cand = ScanCandidate(
        scan_id=scan_id,
        url=url,
        url_hash=url_hash,
        filename=filename,
        document_title=f"Judul {filename}",
        match_status=match_status,
        pull_outcome=pull_outcome,
        selected=selected,
    )
    db.add(cand)
    db.commit()
    db.refresh(cand)
    return cand


def _mock_successful_fetch(self, url: str, max_bytes: int | None = None) -> FetchedFile:
    filename = url.split("/")[-1] or "dokumen.pdf"
    content = make_pdf(f"Isi Dokumen {filename} untuk penarikan UAT")
    return FetchedFile(
        content=content,
        filename=filename,
        content_type="application/pdf",
        final_url=url,
    )


# ==============================================================================
# A01: Dry-run, 1 sumber, kandidat campuran -> perlu ditarik = 3; hanya GET
# ==============================================================================
def test_a01_dry_run_campuran_hanya_get(client: TestClient, db_session: Session):
    source = _seed_source(db_session, "Sumber A01")
    sess = _seed_scan_session(db_session, source.id, StatusPindai.siap_dipilih)

    # 3 baru belum ditarik
    _seed_candidate(db_session, sess.id, "baru_1.pdf", StatusKandidat.baru, None)
    _seed_candidate(db_session, sess.id, "baru_2.pdf", StatusKandidat.baru, None)
    _seed_candidate(db_session, sess.id, "baru_3.pdf", StatusKandidat.baru, None)
    # 1 sudah_ada
    _seed_candidate(db_session, sess.id, "sudah_ada.pdf", StatusKandidat.sudah_ada, None)
    # 1 success
    _seed_candidate(db_session, sess.id, "sukses.pdf", StatusKandidat.baru, "success")
    # 1 failed
    _seed_candidate(db_session, sess.id, "gagal.pdf", StatusKandidat.baru, "failed")

    observed_methods: list[str] = []
    orig_request = client.request

    def spy_request(method, url, *args, **kwargs):
        observed_methods.append(method.upper())
        return orig_request(method, url, *args, **kwargs)

    with patch.object(client, "request", side_effect=spy_request):
        ringkasan = jalankan(client, OpsiTarik(apply=False))

    assert ringkasan.total_perlu_ditarik == 3
    assert len(ringkasan.sumber_list) == 1
    hs = ringkasan.sumber_list[0]
    assert hs.perlu_ditarik == 3
    assert hs.baru_count == 3
    assert hs.ulang_gagal_count == 0
    assert hs.sudah_ada_di_kb == 1
    assert hs.catatan == "dry-run"

    # Seluruh panggilan HTTP WAJIB berstatus GET saja
    assert len(observed_methods) > 0
    assert all(m == "GET" for m in observed_methods), f"Ada metode non-GET: {observed_methods}"


# ==============================================================================
# A02: Dry-run --ulang-gagal -> perlu ditarik = 4 (3 baru + 1 failed)
# ==============================================================================
def test_a02_dry_run_ulang_gagal(client: TestClient, db_session: Session):
    source = _seed_source(db_session, "Sumber A02")
    sess = _seed_scan_session(db_session, source.id, StatusPindai.siap_dipilih)

    _seed_candidate(db_session, sess.id, "baru_1.pdf", StatusKandidat.baru, None)
    _seed_candidate(db_session, sess.id, "baru_2.pdf", StatusKandidat.baru, None)
    _seed_candidate(db_session, sess.id, "baru_3.pdf", StatusKandidat.baru, None)
    _seed_candidate(db_session, sess.id, "sudah_ada.pdf", StatusKandidat.sudah_ada, None)
    _seed_candidate(db_session, sess.id, "sukses.pdf", StatusKandidat.baru, "success")
    _seed_candidate(db_session, sess.id, "gagal.pdf", StatusKandidat.baru, "failed")

    ringkasan = jalankan(client, OpsiTarik(apply=False, ulang_gagal=True))

    assert ringkasan.total_perlu_ditarik == 4
    hs = ringkasan.sumber_list[0]
    assert hs.perlu_ditarik == 4
    assert hs.baru_count == 3
    assert hs.ulang_gagal_count == 1
    assert hs.sudah_ada_di_kb == 1


# ==============================================================================
# A03: --apply -> select_none lalu set hanya 3 id; POST pull tanpa category_id;
#      dokumen hasil tarikan kategori_manual=False
# ==============================================================================
def test_a03_apply_selection_and_no_category_id(client: TestClient, db_session: Session):
    source = _seed_source(db_session, "Sumber A03")
    sess = _seed_scan_session(db_session, source.id, StatusPindai.siap_dipilih)

    c1 = _seed_candidate(db_session, sess.id, "baru_1.pdf", StatusKandidat.baru, None)
    c2 = _seed_candidate(db_session, sess.id, "baru_2.pdf", StatusKandidat.baru, None)
    c3 = _seed_candidate(db_session, sess.id, "baru_3.pdf", StatusKandidat.baru, None)
    _seed_candidate(db_session, sess.id, "sudah_ada.pdf", StatusKandidat.sudah_ada, None)
    _seed_candidate(db_session, sess.id, "sukses.pdf", StatusKandidat.baru, "success")
    _seed_candidate(db_session, sess.id, "gagal.pdf", StatusKandidat.baru, "failed")

    patch_payloads = []
    post_payloads = []

    orig_patch = client.patch
    orig_post = client.post

    def spy_patch(url, *args, **kwargs):
        if "selection" in str(url):
            patch_payloads.append(kwargs.get("json", {}))
        return orig_patch(url, *args, **kwargs)

    def spy_post(url, *args, **kwargs):
        if "/pull" in str(url):
            post_payloads.append(kwargs.get("json", {}))
        return orig_post(url, *args, **kwargs)

    with patch.object(client, "patch", side_effect=spy_patch), \
         patch.object(client, "post", side_effect=spy_post), \
         patch.object(SimpleHttpCrawler, "fetch", new=_mock_successful_fetch):

        ringkasan = jalankan(client, OpsiTarik(apply=True, interval=0))

    # 1. Verifikasi selection
    assert len(patch_payloads) == 2
    assert patch_payloads[0] == {"action": "select_none"}
    assert patch_payloads[1]["action"] == "set"
    assert sorted(patch_payloads[1]["candidate_ids"]) == sorted([c1.id, c2.id, c3.id])
    assert patch_payloads[1]["selected"] is True

    # 2. Verifikasi body POST pull persis tanpa category_id
    assert len(post_payloads) == 1
    assert post_payloads[0] == {"destination": "knowledge_base"}
    assert "category_id" not in post_payloads[0]

    # 3. Verifikasi dokumen di DB tersimpan dengan kategori_manual=False
    docs = db_session.query(Document).filter(Document.title.like("%baru_%")).all()
    assert len(docs) == 3
    for d in docs:
        assert d.kategori_manual is False

    assert ringkasan.total_ditarik == 3
    assert ringkasan.total_gagal == 0


# ==============================================================================
# A04: --apply --batas 2 -> hanya 2 id dipilih
# ==============================================================================
def test_a04_apply_batas_2(client: TestClient, db_session: Session):
    source = _seed_source(db_session, "Sumber A04")
    sess = _seed_scan_session(db_session, source.id, StatusPindai.siap_dipilih)

    c1 = _seed_candidate(db_session, sess.id, "c1.pdf", StatusKandidat.baru, None)
    c2 = _seed_candidate(db_session, sess.id, "c2.pdf", StatusKandidat.baru, None)
    _seed_candidate(db_session, sess.id, "c3.pdf", StatusKandidat.baru, None)

    patch_payloads = []
    orig_patch = client.patch

    def spy_patch(url, *args, **kwargs):
        if "selection" in str(url):
            patch_payloads.append(kwargs.get("json", {}))
        return orig_patch(url, *args, **kwargs)

    with patch.object(client, "patch", side_effect=spy_patch), \
         patch.object(SimpleHttpCrawler, "fetch", new=_mock_successful_fetch):

        ringkasan = jalankan(client, OpsiTarik(apply=True, batas=2, interval=0))

    set_calls = [p for p in patch_payloads if p.get("action") == "set"]
    assert len(set_calls) == 1
    assert set_calls[0]["candidate_ids"] == [c1.id, c2.id]
    assert ringkasan.total_perlu_ditarik == 2
    assert ringkasan.total_ditarik == 2


# ==============================================================================
# A05: Lebih dari 200 kandidat -> selection per batch 200; paging kandidat sampai habis
# ==============================================================================
def test_a05_batching_200_selection_and_paging(client: TestClient, db_session: Session):
    source = _seed_source(db_session, "Sumber A05")
    sess = _seed_scan_session(db_session, source.id, StatusPindai.siap_dipilih)

    # Buat 250 kandidat baru
    cands = [
        ScanCandidate(
            scan_id=sess.id,
            url=f"https://example.com/files/bulk_{i}.pdf",
            url_hash=hashlib.sha256(f"bulk_{i}".encode()).hexdigest(),
            filename=f"bulk_{i}.pdf",
            document_title=f"Judul {i}",
            match_status=StatusKandidat.baru,
            pull_outcome=None,
            selected=False,
        )
        for i in range(1, 251)
    ]
    db_session.add_all(cands)
    db_session.commit()

    patch_payloads = []
    orig_patch = client.patch

    def spy_patch(url, *args, **kwargs):
        if "selection" in str(url):
            patch_payloads.append(kwargs.get("json", {}))
        return orig_patch(url, *args, **kwargs)

    with patch.object(client, "patch", side_effect=spy_patch), \
         patch.object(SimpleHttpCrawler, "fetch", new=_mock_successful_fetch):

        ringkasan = jalankan(client, OpsiTarik(apply=True, interval=0))

    set_calls = [p for p in patch_payloads if p.get("action") == "set"]
    assert len(set_calls) == 2
    assert len(set_calls[0]["candidate_ids"]) == 200
    assert len(set_calls[1]["candidate_ids"]) == 50
    assert ringkasan.total_perlu_ditarik == 250


# ==============================================================================
# A06: Sesi sedang menarik/memindai -> sumber dilewati, tidak ada POST
# ==============================================================================
def test_a06_sesi_sedang_berjalan_dilewati(client: TestClient, db_session: Session):
    source = _seed_source(db_session, "Sumber A06")
    sess = _seed_scan_session(db_session, source.id, StatusPindai.menarik)
    _seed_candidate(db_session, sess.id, "cand1.pdf", StatusKandidat.baru, None)

    post_called = False
    orig_post = client.post

    def spy_post(url, *args, **kwargs):
        nonlocal post_called
        post_called = True
        return orig_post(url, *args, **kwargs)

    with patch.object(client, "post", side_effect=spy_post):
        ringkasan = jalankan(client, OpsiTarik(apply=True))

    assert post_called is False
    assert len(ringkasan.sumber_list) == 1
    assert ringkasan.sumber_list[0].status == "dilewati"
    assert ringkasan.sumber_list[0].catatan == "sesi sedang berjalan"


# ==============================================================================
# A07: Sumber tanpa sesi siap -> dicatat, tidak ada POST, skrip lanjut
# ==============================================================================
def test_a07_sumber_tanpa_sesi_siap(client: TestClient, db_session: Session):
    source = _seed_source(db_session, "Sumber A07")
    # Hanya sesi yang berstatus gagal (bukan siap_dipilih atau selesai)
    _seed_scan_session(db_session, source.id, StatusPindai.gagal)

    post_called = False
    orig_post = client.post

    def spy_post(url, *args, **kwargs):
        nonlocal post_called
        post_called = True
        return orig_post(url, *args, **kwargs)

    with patch.object(client, "post", side_effect=spy_post):
        ringkasan = jalankan(client, OpsiTarik(apply=True))

    assert post_called is False
    assert len(ringkasan.sumber_list) == 1
    assert ringkasan.sumber_list[0].status == "tidak_siap"
    assert ringkasan.sumber_list[0].catatan == "tidak ada sesi scan siap — jalankan scan dulu"
    assert ringkasan.exit_code == 0


# ==============================================================================
# A08: Polling status menarik dua kali lalu selesai & timeout menghasilkan peringatan
# ==============================================================================
def test_a08_polling_and_timeout(client: TestClient, db_session: Session, capsys: pytest.CaptureFixture):
    source = _seed_source(db_session, "Sumber A08")
    sess = _seed_scan_session(db_session, source.id, StatusPindai.siap_dipilih)
    _seed_candidate(db_session, sess.id, "c1.pdf", StatusKandidat.baru, None)

    # 1. Normal polling: status menarik 2 kali lalu selesai
    call_count = 0
    orig_get = client.get

    def spy_get(url, *args, **kwargs):
        nonlocal call_count
        if f"/scans/{sess.id}" in str(url) and not str(url).endswith("/candidates"):
            call_count += 1
            resp = orig_get(url, *args, **kwargs)
            data = resp.json()
            if call_count <= 2:
                data["status"] = "menarik"
            else:
                data["status"] = "selesai"
            resp.json = lambda: data
            return resp
        return orig_get(url, *args, **kwargs)

    with patch.object(client, "get", side_effect=spy_get), \
         patch.object(SimpleHttpCrawler, "fetch", new=_mock_successful_fetch):
        ringkasan = jalankan(client, OpsiTarik(apply=True, interval=0, timeout_menit=10))

    assert call_count >= 3
    assert ringkasan.sumber_list[0].catatan == "selesai ditarik"

    # 2. Timeout case: status tetap menarik dan timeout_menit = -1
    sess2 = _seed_scan_session(db_session, source.id, StatusPindai.siap_dipilih)
    _seed_candidate(db_session, sess2.id, "c2.pdf", StatusKandidat.baru, None)

    def spy_get_stuck(url, *args, **kwargs):
        if f"/scans/{sess2.id}" in str(url) and not str(url).endswith("/candidates"):
            resp = orig_get(url, *args, **kwargs)
            data = resp.json()
            data["status"] = "menarik"
            resp.json = lambda: data
            return resp
        return orig_get(url, *args, **kwargs)

    with patch.object(client, "get", side_effect=spy_get_stuck), \
         patch.object(SimpleHttpCrawler, "fetch", new=_mock_successful_fetch):
        ringkasan_timeout = jalankan(client, OpsiTarik(apply=True, interval=0, timeout_menit=-1))

    captured = capsys.readouterr().out
    assert "PERINGATAN: Batas waktu -1 menit terlampaui" in captured
    assert "timeout (-1m)" in ringkasan_timeout.sumber_list[0].catatan


# ==============================================================================
# A09: Dua sumber dengan --source-id salah satu -> hanya sumber itu yang diproses
# ==============================================================================
def test_a09_filter_source_id(client: TestClient, db_session: Session):
    s1 = _seed_source(db_session, "Sumber 1")
    s2 = _seed_source(db_session, "Sumber 2")
    sess1 = _seed_scan_session(db_session, s1.id, StatusPindai.siap_dipilih)
    _seed_scan_session(db_session, s2.id, StatusPindai.siap_dipilih)

    _seed_candidate(db_session, sess1.id, "c1.pdf", StatusKandidat.baru, None)

    ringkasan = jalankan(client, OpsiTarik(source_ids=[s1.id], apply=False))

    assert len(ringkasan.sumber_list) == 1
    assert ringkasan.sumber_list[0].source_id == s1.id
    assert ringkasan.sumber_list[0].nama == "Sumber 1"


# ==============================================================================
# A10: Corong sebelum/sesudah -> ditampilkan; belum_ditarik turun
# ==============================================================================
def test_a10_corong_sebelum_sesudah(client: TestClient, db_session: Session, capsys: pytest.CaptureFixture):
    source = _seed_source(db_session, "Sumber A10")
    sess = _seed_scan_session(db_session, source.id, StatusPindai.siap_dipilih)
    _seed_candidate(db_session, sess.id, "c1.pdf", StatusKandidat.baru, None)
    _seed_candidate(db_session, sess.id, "c2.pdf", StatusKandidat.baru, None)

    with patch.object(SimpleHttpCrawler, "fetch", new=_mock_successful_fetch):
        ringkasan = jalankan(client, OpsiTarik(apply=True, interval=0))

    assert ringkasan.corong_sebelum is not None
    assert ringkasan.corong_sesudah is not None
    # Sebelum pull: ada kandidat belum ditarik
    assert ringkasan.corong_sebelum.belum_ditarik >= 2
    # Sesudah pull: kandidat telah ditarik ke KB
    assert ringkasan.corong_sesudah.belum_ditarik < ringkasan.corong_sebelum.belum_ditarik
    assert ringkasan.corong_sesudah.di_kb > ringkasan.corong_sebelum.di_kb

    cetak_laporan(ringkasan)
    out = capsys.readouterr().out
    assert "STATISTIK CORONG" in out or "Metrik Corong" in out
    assert "Total Dokumen di KB" in out
    assert "Total Scan Belum Ditarik" in out


# ==============================================================================
# A11: Ada kandidat gagal -> baris PERINGATAN muncul; exit 0
# ==============================================================================
def test_a11_kandidat_gagal_ada_peringatan_exit_0(client: TestClient, db_session: Session, capsys: pytest.CaptureFixture):
    source = _seed_source(db_session, "Sumber A11")
    sess = _seed_scan_session(db_session, source.id, StatusPindai.siap_dipilih)
    _seed_candidate(db_session, sess.id, "sukses.pdf", StatusKandidat.baru, None)
    _seed_candidate(db_session, sess.id, "gagal_unduh.pdf", StatusKandidat.baru, None)

    def mock_fetch_partial(self, url: str, max_bytes: int | None = None) -> FetchedFile:
        if "gagal_unduh" in url:
            raise Exception("Koneksi ditolak oleh server sumber (404 Not Found)")
        return _mock_successful_fetch(self, url, max_bytes)

    with patch.object(SimpleHttpCrawler, "fetch", new=mock_fetch_partial):
        ringkasan = jalankan(client, OpsiTarik(apply=True, interval=0))

    assert ringkasan.total_gagal == 1
    assert ringkasan.total_ditarik == 1
    assert ringkasan.exit_code == 0
    assert ringkasan.pesan_peringatan is not None
    assert "PERINGATAN: 1 kandidat gagal ditarik" in ringkasan.pesan_peringatan

    cetak_laporan(ringkasan)
    out = capsys.readouterr().out
    assert "PERINGATAN: 1 kandidat gagal ditarik" in out


# ==============================================================================
# A12: HERO_API_TOKEN di-set -> terkirim sebagai Bearer dan tidak muncul di capsys
# ==============================================================================
def test_a12_hero_api_token_header_dan_tidak_bocor(monkeypatch, capsys: pytest.CaptureFixture):
    token_rahasia = "token_sangat_rahasia_12345_xyz"
    monkeypatch.setenv("HERO_API_TOKEN", token_rahasia)

    observed_auth_headers: list[str] = []
    orig_client_init = httpx.Client.__init__

    def mock_client_init(self, *args, **kwargs):
        headers = kwargs.get("headers", {})
        if "Authorization" in headers:
            observed_auth_headers.append(headers["Authorization"])
        return orig_client_init(self, *args, **kwargs)

    with patch.object(httpx.Client, "__init__", side_effect=mock_client_init, autospec=True), \
         patch("scripts.tarik_semua.jalankan") as mock_jalankan, \
         patch("scripts.tarik_semua.cetak_laporan"):

        mock_jalankan.return_value = Ringkasan(opsi=OpsiTarik(), exit_code=0)

        with patch("sys.argv", ["tarik_semua.py", "--base-url", "http://localhost:8000"]):
            ret = main()
            assert ret == 0

    assert len(observed_auth_headers) == 1
    assert observed_auth_headers[0] == f"Bearer {token_rahasia}"

    captured = capsys.readouterr()
    stdout_text = captured.out
    stderr_text = captured.err

    # Pastikan teks token tidak bocor di output mana pun
    assert token_rahasia not in stdout_text
    assert token_rahasia not in stderr_text
    assert "Autentikasi: Menggunakan HERO_API_TOKEN (terpasang)" in stdout_text
