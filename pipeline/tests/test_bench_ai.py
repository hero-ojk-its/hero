"""Benchmark mode AI: metrik, biaya, dan laporan — semuanya tanpa jaringan."""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

from hero import bench_ai as B
from hero.analysis import analyse_document
from hero.pipeline import IngestPipeline

FAKTA = [
    {"id": "I3", "teks": "Status: berlaku", "pasal": None},
    {"id": "F3", "teks": "[Sanksi] Bank yang melanggar dikenai sanksi administratif berupa teguran tertulis.",
     "pasal": "Pasal 4 ayat (1)"},
    {"id": "F4", "teks": "[Sanksi] Bank dikenai sanksi berupa: a. larangan untuk menerbitkan produk; "
                         "b. pembekuan kegiatan usaha.", "pasal": "Pasal 4 ayat (2)"},
    {"id": "F8", "teks": "[Kewajiban] Bank wajib menerapkan tata kelola.", "pasal": "Pasal 5 ayat (1)"},
]


def _keluaran(kalimat, paraf):
    return {"ringkasan": [{"kalimat": k, "fakta": f} for k, f in kalimat],
            "poin_kunci": [{"fakta": f, "parafrase": p} for f, p in paraf]}


def test_modalitas_dikenai_menjadi_dapat_dikenai_terdeteksi():
    out = _keluaran([("Bank yang melanggar dapat dikenai teguran tertulis.", ["F3"])],
                    [("F3", "Pelanggar dapat dikenai teguran tertulis.")])
    s = B.skor_keluaran(out, FAKTA)
    assert s["modalitas_bergeser"] == 2
    assert any("'dapat' ditambahkan" in x for x in s["modalitas_rincian"])


def test_kata_modal_yang_memang_ada_di_fakta_tidak_dihitung():
    fakta = [{"id": "F1", "teks": "[Sanksi] Bank dapat dikenai denda.", "pasal": "Pasal 1"}]
    s = B.skor_keluaran(_keluaran([("Bank dapat dikenai denda.", ["F1"])], [("F1", "Bank dapat dikenai denda.")]), fakta)
    assert s["modalitas_bergeser"] == 0


def test_kewajiban_yang_hilang_dari_parafrase_terdeteksi():
    out = _keluaran([("Bank menerapkan tata kelola.", ["F8"])], [("F8", "Bank menerapkan tata kelola.")])
    assert B.skor_keluaran(out, FAKTA)["modalitas_bergeser"] == 2          # kalimat + parafrase


def test_cakupan_dan_butir_wajib():
    out = _keluaran([("Pelanggar dikenai sanksi teguran tertulis.", ["F3"])],
                    [("F3", "Dikenai teguran tertulis.")])
    s = B.skor_keluaran(out, FAKTA, butir=["teguran tertulis", "pembekuan kegiatan usaha"])
    assert s["cakupan_poin"] == pytest.approx(1 / 3, abs=1e-3)               # F3 dari F3, F4, F8
    assert s["recall_butir"] == 0.5 and s["butir_terlewat"] == ["pembekuan kegiatan usaha"]
    assert s["kategori_terlewat"] == ["Kewajiban"]


def test_kebaruan_menangkap_kata_di_luar_fakta():
    setia = B.skor_keluaran(_keluaran([("Bank wajib menerapkan tata kelola.", ["F8"])], []), FAKTA)
    liar = B.skor_keluaran(_keluaran([("Bank wajib menerapkan tata kelola demi stabilitas ekonomi nasional.", ["F8"])],
                                     []), FAKTA)
    assert setia["kebaruan"] == 0 and liar["kebaruan"] > 0.3


def test_biaya_menghitung_token_berpikir_sebagai_keluaran():
    # 1.000 masuk × $0.10 + (200 keluar + 800 berpikir) × $0.40, per juta
    assert B.biaya_usd("gemini-2.5-flash-lite", 1000, 200, 800) == pytest.approx((100 + 400) / 1e6)
    assert B.biaya_usd("model-tak-dikenal", 1, 1, 1) is None


def test_harga_naik_mengikuti_tanggal_berlaku():
    sebelum = B.biaya_usd("gemini-4-argon", 1_000_000, 0, 0, hari=date(2026, 11, 30))
    sesudah = B.biaya_usd("gemini-4-argon", 1_000_000, 0, 0, hari=date(2026, 12, 1))
    assert (sebelum, sesudah) == (2.0, 4.0)


def test_konsistensi_antar_ulangan():
    r = lambda ids: {"skor": {"fakta_dirujuk": ids}}                       # noqa: E731
    assert B.konsistensi([r(["F1", "F2"]), r(["F1", "F2"])]) == 1.0
    assert B.konsistensi([r(["F1", "F2"]), r(["F2", "F3"])]) == pytest.approx(1 / 3, abs=1e-3)
    assert B.konsistensi([r(["F1"])]) is None


# -- klien Gemini palsu ------------------------------------------------------
class _Klien:
    def __init__(self, balasan):
        self.balasan = balasan
        self.panggilan = []
        self.models = SimpleNamespace(generate_content=self._gen)

    def _gen(self, model, contents, config):
        self.panggilan.append((model, config))
        b = self.balasan[model]
        if isinstance(b, Exception):
            raise b
        return SimpleNamespace(
            text=json.dumps(b), model_version=model,
            usage_metadata=SimpleNamespace(prompt_token_count=1000, candidates_token_count=300,
                                           thoughts_token_count=700),
            candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"))])


@pytest.fixture
def analisis(tmp_path, tmp_settings, regulation_pdf):
    pipe = IngestPipeline(tmp_settings)
    try:
        assert pipe.run_upload([regulation_pdf(tmp_path / "a.pdf")]).ingested == 1
    finally:
        pipe.close()
    conn = sqlite3.connect(tmp_settings.catalog_db)
    conn.row_factory = sqlite3.Row
    return analyse_document(conn, conn.execute("SELECT doc_id FROM documents").fetchone()[0])


def test_jalankan_menghasilkan_laporan_lengkap(analisis, tmp_path, monkeypatch):
    monkeypatch.setattr(B.time, "sleep", lambda *_: None)
    from hero.analysis.ai import build_facts

    facts = build_facts(analisis, 24)
    fid = next(f["id"] for f in facts if f["id"].startswith("F"))
    bagus = _keluaran([("Peraturan ini mengatur kewajiban.", [fid]), ("Pihak terkait wajib mematuhinya.", [fid])],
                      [(fid, "Kewajiban pokok.")])
    klien = _Klien({"gemini-2.5-flash-lite": bagus, "gemini-3.1-flash-lite": RuntimeError("429 kuota")})
    rep = B.jalankan(klien, analisis, [B.Varian("gemini-2.5-flash-lite"), B.Varian("gemini-3.1-flash-lite")],
                     ulangan=2, dokumen="uji", butir=None)
    a, b = rep.ringkasan
    assert a["galat"] == 0 and a["lulus_verifikasi"] == 1.0
    assert a["token_berpikir"] == 700 and a["usd_per_dokumen"] == pytest.approx((1000 * 0.10 + 1000 * 0.40) / 1e6)
    assert b["galat"] == 2 and "RuntimeError" in b["contoh_galat"]
    # konfigurasi produksi dipertahankan: suhu 0, skema tanpa additionalProperties
    cfg = klien.panggilan[0][1]
    assert cfg["temperature"] == 0.0 and "additionalProperties" not in json.dumps(cfg["response_schema"])
    paths = rep.tulis(tmp_path / "out", "uji")
    md = paths["md"].read_text(encoding="utf-8")
    assert "Perbandingan" in md and "Keluaran untuk telaah manual" in md and "Periksa ulang" in md
    assert paths["csv"].read_text().splitlines()[0].startswith("model,ulangan,kelengkapan")


def test_keluaran_yang_melanggar_verifikator_dihitung_tidak_lulus(analisis, monkeypatch):
    monkeypatch.setattr(B.time, "sleep", lambda *_: None)
    rusak = _keluaran([("Denda Rp999 juta.", ["F1"])], [])
    rep = B.jalankan(_Klien({"gemini-2.5-flash-lite": rusak}), analisis, [B.Varian("gemini-2.5-flash-lite")],
                     ulangan=1, dokumen="uji", butir=None)
    assert rep.ringkasan[0]["lulus_verifikasi"] == 0.0
    assert rep.hasil["gemini-2.5-flash-lite"][0]["pelanggaran"]
