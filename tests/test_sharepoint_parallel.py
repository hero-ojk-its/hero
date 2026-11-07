"""Crawler SharePoint OJK: pengambilan detail paralel (tanpa jaringan & tanpa DB)."""
import re
import threading
import time

import httpx

from app.crawlers import sharepoint_postback as sp

_REAL_CLIENT = httpx.Client
N_PAGES = 3
PER_PAGE = 6


def _listing(page: int) -> str:
    links = "".join(
        f'<a href="/id/regulasi/Pages/reg-{page}-{i}.aspx">r</a>' for i in range(PER_PAGE))
    nxt = ""
    if page < N_PAGES:
        nxt = ("<a href=\"javascript:__doPostBack('p$DataPagerArticles$ctl02$ctl00','')\">"
               "</a>")
    return f"<html><body>{links}{nxt}</body></html>"


def _detail(path: str) -> str:
    return (f'<html><title>T {path}</title><body>Nomor Regulasi : 1/POJK.03/2024'
            f'<a href="{path}.pdf">pdf</a></body></html>')


def _install(monkeypatch, state):
    page_of = {"n": 1}

    def handler(request: httpx.Request) -> httpx.Response:
        url = request.url
        if request.method == "POST":
            page_of["n"] += 1
            return httpx.Response(200, text=_listing(page_of["n"]))
        if "/Pages/reg-" in url.path:
            with state["lock"]:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            time.sleep(0.05)
            with state["lock"]:
                state["active"] -= 1
            return httpx.Response(200, text=_detail(url.path))
        return httpx.Response(200, text=_listing(page_of["n"]))

    def factory(*a, **kw):
        kw.pop("verify", None)
        return _REAL_CLIENT(*a, transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(sp.httpx, "Client", factory)
    monkeypatch.setattr(sp, "guard_url", lambda *a, **k: None)


def _run(monkeypatch, workers, should_cancel=None):
    state = {"lock": threading.Lock(), "active": 0, "peak": 0}
    _install(monkeypatch, state)
    c = sp.SharepointPostbackCrawler(delay_seconds=0, head_for_size=False,
                                     detail_workers=workers)
    res = c.scan("https://ojk.go.id/id/regulasi/default.aspx", 1, max_pages=10,
                 should_cancel=should_cancel)
    return res, state


def test_paralel_hasil_sama_dengan_berurutan(monkeypatch):
    seq, s1 = _run(monkeypatch, 1)
    par, s2 = _run(monkeypatch, 4)
    assert sorted(c.url for c in seq.candidates) == sorted(c.url for c in par.candidates)
    assert len(par.candidates) == N_PAGES * PER_PAGE
    assert par.pages_visited == N_PAGES
    assert s1["peak"] == 1 and s2["peak"] > 1


def test_pembatal_menghentikan_mode_paralel(monkeypatch):
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 3

    res, _ = _run(monkeypatch, 4, should_cancel=cancel)
    assert len(res.candidates) < N_PAGES * PER_PAGE


def test_pembatas_laju_aman_antar_thread():
    c = sp.SharepointPostbackCrawler(delay_seconds=0.05, detail_workers=4)
    stamps = []
    lock = threading.Lock()

    def hit():
        c._rate_limit("h")
        with lock:
            stamps.append(time.time())

    ts = [threading.Thread(target=hit) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    stamps.sort()
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert min(gaps) >= 0.035  # toleransi jitter; tanpa kunci jarak ~0


# ---------------------------------------------------------------- batas "tanpa kemajuan"
def _stub_candidate(url: str):
    from app.crawlers.base import PdfCandidate
    return PdfCandidate(url=url + ".pdf", filename="x.pdf")


def test_macet_total_dihentikan_dan_hasil_sebagian_disimpan(monkeypatch):
    """Satu regulasi tak pernah selesai: scan berhenti setelah selang tanpa kemajuan."""
    state = {"lock": threading.Lock(), "active": 0, "peak": 0}
    _install(monkeypatch, state)
    release = threading.Event()
    c = sp.SharepointPostbackCrawler(delay_seconds=0, head_for_size=False,
                                     detail_workers=2, stall_seconds=1)

    def stub(client, url, page_depth):
        if url.endswith("reg-1-0.aspx"):
            release.wait(30)          # macet, tidak pernah selesai sendiri
            return []
        return [_stub_candidate(url)]

    c._parse_detail_page = stub
    t0 = time.time()
    try:
        res = c.scan("https://ojk.go.id/id/regulasi/default.aspx", 1, max_pages=10)
    finally:
        release.set()
    assert time.time() - t0 < 10
    assert res.truncated is True
    assert any("tidak ada kemajuan" in e for e in res.errors)
    assert len(res.candidates) == PER_PAGE - 1   # yang selesai tetap tersimpan


def test_lambat_tapi_masih_bergerak_tidak_dibatasi(monkeypatch):
    """Total waktu jauh melebihi batas, tetapi selalu ada yang selesai: harus tuntas."""
    state = {"lock": threading.Lock(), "active": 0, "peak": 0}
    _install(monkeypatch, state)
    c = sp.SharepointPostbackCrawler(delay_seconds=0, head_for_size=False,
                                     detail_workers=2, stall_seconds=1)

    def slow(client, url, page_depth):
        time.sleep(0.25)              # 18 regulasi x 0,25 dtk / 2 pekerja ≈ 2,2 dtk > batas 1 dtk
        return [_stub_candidate(url)]

    c._parse_detail_page = slow
    t0 = time.time()
    res = c.scan("https://ojk.go.id/id/regulasi/default.aspx", 1, max_pages=10)
    assert time.time() - t0 > 1.5
    assert not any("tidak ada kemajuan" in e for e in res.errors)
    assert res.truncated is False
    assert len(res.candidates) == N_PAGES * PER_PAGE
