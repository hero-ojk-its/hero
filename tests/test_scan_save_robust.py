"""
tests/test_scan_save_robust.py
Regresi: sesi pemindaian tidak boleh menggantung di 'memindai' saat penyimpanan
kandidat gagal (mis. nilai situs sumber lebih panjang dari kolom database).
"""
from app.crawlers.base import PdfCandidate, ScanResult
from app.models.enums import JenisSumber, StatusPindai
from app.models.scan_candidate import ScanCandidate
from app.models.scan_session import ScanSession
from app.models.scraping_source import ScrapingSource
from app.services.scan_service import ScanService

# Panjangnya melebihi kolom scan_candidates.sub_bidang (String(100)); kasus nyata
# dari ojk.go.id yang dulu membuat seluruh pemindaian 10 halaman macet.
SUB_BIDANG_PANJANG = ("Lembaga Pembiayaan; Lembaga Keuangan Mikro; Lembaga Jasa Keuangan "
                      "Lainnya; Perusahaan Modal Ventura; Peraturan Lain-lain Yang Panjang")


class _StubCrawler:
    name = "stub"

    def __init__(self, candidates):
        self._candidates = candidates

    def scan(self, url, depth, *, max_pages=200, max_candidates=5000,
             progress=None, should_cancel=None):
        return ScanResult(candidates=self._candidates, pages_visited=1, stats={})


def _mulai(db_session, monkeypatch, candidates):
    src = ScrapingSource(name="Sumber Regresi", url="https://ojk.go.id/id/regulasi/default.aspx",
                         source_type=JenisSumber.situs_web)
    db_session.add(src)
    db_session.flush()
    sess = ScanSession(source_id=src.id, start_url=src.url, crawl_depth=1,
                       mode="simple_http", status=StatusPindai.antrian)
    db_session.add(sess)
    db_session.commit()
    monkeypatch.setattr("app.services.scan_service.get_crawler",
                        lambda *a, **k: _StubCrawler(candidates))
    ScanService(db_session).execute_scan(sess.id)
    db_session.expire_all()
    return db_session.query(ScanSession).filter(ScanSession.id == sess.id).one()


def test_sub_bidang_terlalu_panjang_dipangkas_dan_sesi_selesai(db_session, monkeypatch):
    assert len(SUB_BIDANG_PANJANG) > 100
    cand = PdfCandidate(url="https://ojk.go.id/a.pdf", filename="a.pdf",
                        sub_bidang=SUB_BIDANG_PANJANG)
    sess = _mulai(db_session, monkeypatch, [cand])

    assert sess.status == StatusPindai.siap_dipilih
    row = db_session.query(ScanCandidate).filter(ScanCandidate.scan_id == sess.id).one()
    assert len(row.sub_bidang) <= 100 and row.sub_bidang.startswith("Lembaga Pembiayaan")


def test_penyimpanan_gagal_dicatat_gagal_bukan_menggantung(db_session, monkeypatch):
    """URL kembar melanggar uq_scan_candidates_scan_url_hash: sesi harus 'gagal', bukan 'memindai'."""
    a = PdfCandidate(url="https://ojk.go.id/kembar.pdf", filename="k1.pdf")
    b = PdfCandidate(url="https://ojk.go.id/kembar.pdf", filename="k2.pdf")
    sess = _mulai(db_session, monkeypatch, [a, b])

    assert sess.status == StatusPindai.gagal
    assert sess.error_message
