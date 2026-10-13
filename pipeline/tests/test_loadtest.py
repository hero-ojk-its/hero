"""Uji latensi/kapasitas: matematikanya, penentuan batas, dan satu putaran nyata.

Tiga lapis, dari murah ke mahal:
1. statistik & aturan kapasitas — murni fungsi, tanpa jaringan;
2. klien/pembangkit beban terhadap server palsu yang perilakunya kita atur
   (lambat, gagal, runtuh) — membuktikan alat ukur mengukur dengan benar;
3. satu putaran penuh terhadap server HERO sungguhan (uvicorn + katalog hasil
   ingest), termasuk regresi untuk galat konkurensi yang ditemukan alat ini.
"""
from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from hero import loadtest as lt


# ---------------------------------------------------------------- 1. statistik
def test_percentile_is_nearest_rank_of_observed_values():
    v = sorted(range(1, 101))
    assert lt.percentile(v, 50) == 50
    assert lt.percentile(v, 95) == 95
    assert lt.percentile(v, 99) == 99
    assert lt.percentile(v, 100) == 100
    assert lt.percentile([7.0], 99) == 7.0
    assert lt.percentile([], 95) == 0.0


def test_p95_is_not_hidden_by_a_good_average():
    # 94 cepat + 6 lambat: rata-rata tampak baik, p95 menangkap ekornya.
    ms = [10.0] * 94 + [2000.0] * 6
    r = lt.ringkas(ms)
    assert r["rata"] < 150 and r["p95"] == 2000.0 and r["maks"] == 2000.0 and r["n"] == 100


def test_failed_requests_are_counted_not_averaged_into_latency():
    h = lt.Hasil()
    h.tambah(5.0, None)
    h.tambah(900.0, "HTTP 500")          # galat cepat/lambat tidak boleh memperbaiki/merusak p50
    assert h.ms == [5.0] and h.galat == 1 and h.rasio_galat == 0.5
    assert h.contoh_galat == ["HTTP 500"]


def _lv(n, rps, p95, galat=0.0, rata=None):
    return {"pengguna": n, "rps": rps, "rps_sukses": rps, "permintaan": int(rps * 10),
            "rasio_galat": galat, "contoh_galat": [], "cpu_klien": 0.1,
            "latensi_ms": {"p95": p95, "rata": rata if rata is not None else p95 / 2}}


def test_capacity_is_the_last_healthy_level_before_the_first_violation():
    levels = [_lv(1, 100, 10), _lv(10, 400, 200), _lv(50, 420, 4000), _lv(100, 410, 100)]
    k = lt.kapasitas(levels, slo_ms=3000, galat_maks=0.01, think_time=5)
    # level 100 kebetulan lolos setelah 50 gagal → derau, tidak boleh menaikkan klaim
    assert k["pengguna_serentak_sehat"] == 10
    assert k["pelanggaran_pertama"]["pengguna"] == 50 and "p95" in k["pelanggaran_pertama"]["alasan"]
    assert k["rps_puncak"] == 420 and k["pengguna_pada_rps_puncak"] == 50


def test_error_rate_alone_breaks_the_limit():
    k = lt.kapasitas([_lv(1, 100, 5), _lv(10, 300, 20, galat=0.05)], 3000, 0.01, 5)
    assert k["pengguna_serentak_sehat"] == 1
    assert "galat" in k["pelanggaran_pertama"]["alasan"]


def test_no_violation_means_limit_not_found_not_infinite_capacity():
    k = lt.kapasitas([_lv(1, 100, 5), _lv(10, 300, 20)], 3000, 0.01, 5)
    assert k["pelanggaran_pertama"] is None and k["pengguna_serentak_sehat"] == 10


def test_real_user_estimate_follows_littles_law():
    # 200 req/s, jeda 5 s, waktu layan 0,1 s → 200 × 5,1 = 1020 orang
    k = lt.kapasitas([_lv(10, 200, 100, rata=100)], 3000, 0.01, think_time=5)
    assert k["perkiraan_pengguna_nyata"] == 1020


def test_nothing_healthy_reports_zero_not_a_guess():
    k = lt.kapasitas([_lv(1, 5, 9000)], 3000, 0.01, 5)
    assert k["pengguna_serentak_sehat"] == 0 and k["perkiraan_pengguna_nyata"] == 0


# ---------------------------------------------------- 2. server palsu terkendali
class _Palsu(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    delay = 0.0
    fail_every = 0                      # setiap permintaan ke-N → 500
    hits = 0
    lock = threading.Lock()

    def do_GET(self):  # noqa: N802
        cls = type(self)
        with cls.lock:
            cls.hits += 1
            n = cls.hits
        time.sleep(cls.delay)
        if self.path.startswith("/api/kb/documents?page_size="):
            body, code = json.dumps({"items": [{"id": f"d{i}"} for i in range(5)]}).encode(), 200
        elif cls.fail_every and n % cls.fail_every == 0:
            body, code = b'{"detail":"boom"}', 500
        elif self.path.startswith("/api/missing"):
            body, code = b"{}", 404
        else:
            body, code = b"{}", 200
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def palsu():
    handler = type("H", (_Palsu,), {"delay": 0.0, "fail_every": 0, "hits": 0, "lock": threading.Lock()})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield handler, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


EPS = [lt.Endpoint("a", lambda r, c: "/a", 1), lt.Endpoint("b", lambda r, c: "/b", 1)]


def test_client_measures_the_delay_the_server_imposes(palsu):
    h, url = palsu
    h.delay = 0.05
    k = lt.Klien(url)
    ms, galat, _ = k.get("/a")
    assert galat is None and 45 <= ms < 400
    k.tutup()


def test_client_reports_http_errors_and_dead_servers(palsu):
    h, url = palsu
    k = lt.Klien(url)
    assert lt.Klien(url).get("/api/missing")[1] == "HTTP 404"
    dead = socket.socket()
    dead.bind(("127.0.0.1", 0))
    port = dead.getsockname()[1]
    dead.close()
    ms, galat, _ = lt.Klien(f"http://127.0.0.1:{port}").get("/a")
    assert galat is not None            # koneksi ditolak = galat, bukan latensi 0
    k.tutup()


def test_a_dead_endpoint_is_reported_and_excluded_not_silently_benchmarked(palsu):
    h, url = palsu
    eps = [lt.Endpoint("hidup", lambda r, c: "/ok", 1), lt.Endpoint("mati", lambda r, c: "/api/missing", 1),
           lt.Endpoint("butuh-id", lambda r, c: "/x", 1, butuh="doc_ids"),
           lt.Endpoint("model-berat", lambda r, c: "/ok", 1, berat=True)]
    hidup, dilewati = lt.periksa_endpoint(url, eps, {"doc_ids": []}, termasuk_berat=False)
    assert [e.nama for e in hidup] == ["hidup"]
    assert set(dilewati) == {"mati", "butuh-id", "model-berat"}
    hidup2, _ = lt.periksa_endpoint(url, eps, {"doc_ids": []}, termasuk_berat=True)
    assert "model-berat" in [e.nama for e in hidup2]


def test_level_counts_requests_and_excludes_warmup(palsu):
    h, url = palsu
    lv = lt.jalankan_level(url, EPS, {}, pengguna=4, durasi=1.0, pemanasan=0.5, server=None)
    # permintaan masa pemanasan sampai ke server tetapi tidak dihitung
    assert h.hits > lv["permintaan"] > 0
    assert lv["rasio_galat"] == 0 and lv["rps"] == pytest.approx(lv["permintaan"] / 1.0, rel=0.01)
    assert set(lv["per_endpoint"]) <= {"a", "b"}


def test_injected_failures_show_up_as_the_right_error_rate(palsu):
    h, url = palsu
    h.fail_every = 4
    lv = lt.jalankan_level(url, EPS, {}, pengguna=2, durasi=1.0, pemanasan=0.2, server=None)
    assert 0.2 <= lv["rasio_galat"] <= 0.3
    assert "HTTP 500" in lv["contoh_galat"]
    assert not lt.sehat(lv, slo_ms=3000, galat_maks=0.01)


def test_latency_phase_orders_slow_above_fast(palsu):
    h, url = palsu
    h.delay = 0.02
    out = lt.ukur_latensi(url, EPS, {}, ulang=5, pemanasan=1)
    assert out["a"]["n"] == 5 and out["a"]["galat"] == 0 and out["a"]["p50"] >= 18


def test_queueing_raises_latency_when_the_server_is_saturated(palsu):
    """Server palsu melayani serial (dikunci) → menambah pengguna tak menambah throughput
    tetapi menaikkan latensi. Inilah bentuk 'lutut' yang harus terbaca di laporan."""
    h, url = palsu
    serial = threading.Lock()
    orig = h.do_GET

    def do_GET(self):  # noqa: N802
        with serial:
            time.sleep(0.01)
            orig(self)

    h.do_GET = do_GET
    a = lt.jalankan_level(url, EPS, {}, 1, 1.0, 0.3, None)
    b = lt.jalankan_level(url, EPS, {}, 8, 1.0, 0.3, None)
    assert b["rps"] < a["rps"] * 1.6                          # throughput tidak ikut naik 8×
    assert b["latensi_ms"]["p95"] > a["latensi_ms"]["p95"] * 3


def test_render_never_claims_a_limit_it_did_not_find():
    rep = _laporan_palsu(batas_ditemukan=False)
    md = lt.render(rep)
    assert "batas bawah" in md and "Batas belum ditemukan" in md
    rep2 = _laporan_palsu(batas_ditemukan=True)
    md2 = lt.render(rep2)
    assert "Batas pertama terlampaui di 50 pengguna" in md2 and "Batas belum ditemukan" not in md2


def test_render_warns_when_the_load_generator_is_the_bottleneck():
    rep = _laporan_palsu(batas_ditemukan=False)
    rep["beban"][-1]["cpu_klien"] = 0.95
    assert "Pembangkit beban hampir jenuh" in lt.render(rep)


def _laporan_palsu(batas_ditemukan: bool) -> dict:
    levels = [_lv(1, 100, 10), _lv(10, 300, 50)]
    if batas_ditemukan:
        levels.append(_lv(50, 310, 5000))
    for lv in levels:
        lv.update(per_endpoint={"x": {"n": 5, "p50": 1, "p95": 2, "galat": 0}}, server=None)
        lv["latensi_ms"].update(p50=1, p99=2, maks=3, n=5, min=1)
    kap = lt.kapasitas(levels, 3000, 0.01, 5)
    return {"dibuat": "2026-10-10 00:00:00", "profil": "api", "target": "http://x",
            "server_diluncurkan": False, "workers": None, "cold_start_s": None,
            "host": {"cpu_inti": 4, "platform": "test", "python": "3"}, "mix_endpoint": {"x": 1},
            "dilewati": {}, "dokumen_contoh": 2,
            "parameter": {"durasi_per_level_s": 1, "pemanasan_s": 0, "ulang_latensi": 1, "levels": [1]},
            "latensi_satu_pengguna": {"x": {"n": 5, "p50": 1, "p95": 2, "p99": 2, "maks": 2, "galat": 0}},
            "beban": levels, "kapasitas": kap}


# ------------------------------------------------- 3. server HERO sungguhan
def _serve(app):
    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return server, t, f"http://127.0.0.1:{port}"


@pytest.fixture
def hero_live(tmp_path, tmp_settings, regulation_pdf):
    pytest.importorskip("uvicorn")
    pytest.importorskip("fastapi")
    from hero.pipeline import IngestPipeline
    from hero.server.app import create_app

    pipe = IngestPipeline(tmp_settings)
    try:
        pipe.run_upload([regulation_pdf(tmp_path / "a.pdf"),
                         regulation_pdf(tmp_path / "b.pdf", nomor=12, tahun=2025,
                                        tentang="PERDAGANGAN KARBON MELALUI BURSA KARBON",
                                        subjek="Penyelenggara Bursa Karbon", kewajiban="mencatat unit karbon")])
    finally:
        pipe.close()
    server, t, url = _serve(create_app(tmp_settings))
    yield url
    server.should_exit = True
    t.join(timeout=10)


def test_full_run_against_the_real_api_has_no_errors_under_concurrency(hero_live):
    """Putaran penuh: temukan dokumen → saring endpoint → latensi → beban 1 & 16 pengguna.

    Pada versi awal, beban serentak di /api/search memunculkan HTTP 500
    (sqlite3.InterfaceError) karena satu koneksi SQLite dipakai banyak utas.
    Alat ini menemukannya; tes ini menjaganya tidak kembali."""
    rep = lt.jalankan(profil="api", url=hero_live, levels=(1, 16), durasi=1.5, pemanasan=0.3,
                      ulang_latensi=3, cari_batas=False)
    assert rep["dokumen_contoh"] == 2
    assert {"health", "dashboard", "kb-daftar", "kb-detail", "analisa"} <= set(rep["latensi_satu_pengguna"])
    for lv in rep["beban"]:
        assert lv["permintaan"] > 0
        assert lv["rasio_galat"] == 0, lv["contoh_galat"]
    assert rep["kapasitas"]["pengguna_serentak_sehat"] == 16
    md = lt.render(rep)
    assert "Latensi satu pengguna" in md and "Beban serentak" in md


def test_vector_store_survives_concurrent_readers(tmp_path):
    """Regresi langsung pada akar masalah, tanpa HTTP: banyak utas mencari bersamaan."""
    from hero.vector.chunking import Chunk
    from hero.vector.embedders import LsaEmbedder
    from hero.vector.store import VectorStore

    corpus = [("d1", "Bank wajib menyampaikan laporan bulanan kepada Otoritas Jasa Keuangan"),
              ("d2", "Perdagangan karbon dilakukan melalui bursa karbon yang diselenggarakan"),
              ("d3", "Reksa dana berbentuk kontrak investasi kolektif dengan aset emas")] * 4
    s = VectorStore(tmp_path / "v.db")
    s.replace_chunks([Chunk(f"c{i}", d, "pasal", str(i), 0, 1, t) for i, (d, t) in enumerate(corpus)])
    lsa = LsaEmbedder(dim=4).fit([t for _, t in corpus] * 2)
    s.index(lsa, use_cache=False)
    s2 = VectorStore(tmp_path / "v.db")        # sisi baca baru: matriks belum di-cache
    errors: list[BaseException] = []

    def baca():
        try:
            for q in ("perdagangan karbon", "laporan bulanan bank", "reksa dana") * 30:
                assert s2.has("lsa")
                assert s2.search(q, method="lsa", k=3, embedder=lsa)
                assert s2.search(q, method="lexical", k=3)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    ts = [threading.Thread(target=baca) for _ in range(16)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors, errors[:2]


def test_cli_registers_loadtest():
    from typer.testing import CliRunner

    from hero.cli import app

    r = CliRunner().invoke(app, ["loadtest", "--help"])
    assert r.exit_code == 0 and "--workers" in r.stdout and "--slo-ms" in r.stdout


def test_launched_server_roundtrip(tmp_path, tmp_settings, regulation_pdf):
    """Jalur yang dipakai CLI: meluncurkan uvicorn sendiri dari berkas config, mengukur, mematikan."""
    pytest.importorskip("uvicorn")
    from hero.pipeline import IngestPipeline

    pipe = IngestPipeline(tmp_settings)
    try:
        pipe.run_upload([regulation_pdf(tmp_path / "a.pdf")])
    finally:
        pipe.close()
    cfg = tmp_path / "sources.yaml"
    cfg.write_text(f"storage:\n  knowledge_base: {tmp_settings.knowledge_base}\n"
                   f"  staging_dir: {tmp_settings.staging_dir}\n  catalog_db: {tmp_settings.catalog_db}\n"
                   "ocr:\n  enabled: false\n", encoding="utf-8")
    rep = lt.jalankan(profil="api", config=cfg, cwd=tmp_path, workers=1, levels=(2,), durasi=1.0,
                      pemanasan=0.2, ulang_latensi=2, cari_batas=False)
    assert rep["server_diluncurkan"] and rep["cold_start_s"] > 0
    assert rep["beban"][0]["server"]["rss_mb"] > 0           # sumber daya server terbaca
    assert rep["beban"][0]["rasio_galat"] == 0


def test_endpoint_subset_is_validated_and_labelled(hero_live):
    with pytest.raises(ValueError, match="tidak dikenal"):
        lt.jalankan(profil="api", url=hero_live, hanya=["kb-daftar", "tidak-ada"])
    rep = lt.jalankan(profil="api", url=hero_live, hanya=["kb-daftar"], levels=(2,), durasi=1.0,
                      pemanasan=0.2, ulang_latensi=2, cari_batas=False)
    assert list(rep["mix_endpoint"]) == ["kb-daftar"]
    assert "Subset endpoint" in lt.render(rep)


def test_fd_limit_is_raised_so_client_errors_are_not_blamed_on_the_server():
    assert lt.siapkan_batas_fd(10) == 10
    import resource
    soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
    assert soft >= 220


def test_a_frozen_server_is_an_error_not_a_silent_zero(palsu, monkeypatch):
    """Server yang tidak menjawab tidak boleh tampak 'tanpa galat' hanya karena tak ada
    permintaan yang selesai (temuan awal: layanan beku → '0 req/s, galat 0%')."""
    h, url = palsu
    h.delay = 2.0
    monkeypatch.setattr(lt, "TIMEOUT_S", 0.3)
    lv = lt.jalankan_level(url, EPS, {}, pengguna=3, durasi=0.8, pemanasan=0.1, server=None)
    assert lv["galat"] > 0 and lv["rasio_galat"] == 1.0
    assert not lt.sehat(lv, 3000, 0.01)


def test_bridge_state_survives_concurrent_readers_and_closes_every_connection(tmp_path):
    """Layanan analisa (ml_api) membaca peta dokumen dari banyak utas sekaligus."""
    from hero.bridge.state import BridgeState

    st = BridgeState(tmp_path / "bridge.db")
    for i in range(1, 6):
        st.map_document(i, f"d{i}")
    errors: list[BaseException] = []

    def baca():
        try:
            for i in range(200):
                n = i % 5 + 1
                assert st.doc_id_for(n) == f"d{n}"
                assert st.document_id_for(f"d{n}") == n
                assert len(st.doc_map()) == 5
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    ts = [threading.Thread(target=baca) for _ in range(16)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors, errors[:2]
    st.close()
    assert st._semua == []
