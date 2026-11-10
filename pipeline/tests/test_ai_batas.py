"""Batas biaya & waktu jalur AI: anggaran berpikir, batas token keluaran, batas waktu.

Sebelumnya Gemini dipanggil tanpa ketiganya: token berpikir (ditagih sebagai keluaran, tak
terlihat di hasil) tak terbatas, dan satu permintaan yang menggantung membuat layar Analisa
menunggu tanpa akhir."""
from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

import pytest

from hero.analysis import analyse_document
from hero.analysis.ai import AiNarrator, _batas_waktu, build_facts, gemini_minta, thinking_config
from hero.config import AnalysisSettings
from hero.pipeline import IngestPipeline


class _Gemini:
    """Klien Gemini palsu: merekam config yang dikirim, membalas sesuai `finish`."""

    def __init__(self, payload=None, finish="STOP", galat=None, thoughts=0):
        self.config = None
        self.panggilan = 0
        self._payload, self._finish, self._galat, self._thoughts = payload, finish, galat, thoughts
        self.models = SimpleNamespace(generate_content=self._gen)

    def _gen(self, model, contents, config):
        self.panggilan += 1
        self.config = config
        if self._galat:
            raise self._galat
        return SimpleNamespace(
            text=json.dumps(self._payload) if self._payload is not None else "",
            model_version=model,
            candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=self._finish))],
            usage_metadata=SimpleNamespace(prompt_token_count=100, candidates_token_count=50,
                                           thoughts_token_count=self._thoughts,
                                           cached_content_token_count=0))


class _Timeout(Exception):
    pass


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


def _ok(analisis):
    f = next(x for x in build_facts(analisis, 24) if x["id"].startswith("F"))
    return {"ringkasan": [{"kalimat": "Peraturan ini mengatur teknologi informasi.", "fakta": ["I2"]},
                          {"kalimat": "Bank memikul kewajiban utama.", "fakta": [f["id"]]}],
            "poin_kunci": [{"fakta": f["id"], "parafrase": "Bank harus menjalankannya."}]}


# -- tuas konfigurasi --------------------------------------------------------
def test_anggaran_berpikir_dari_dua_tuas():
    assert thinking_config(0) == {"thinking_budget": 0}            # 0 = dimatikan, bukan "tak diatur"
    assert thinking_config(512) == {"thinking_budget": 512}
    assert thinking_config(None, "low") == {"thinking_level": "LOW"}
    assert thinking_config(128, "high") == {"thinking_budget": 128}  # angka eksplisit menang
    assert thinking_config(None, "") is None and thinking_config(None, "  ") is None


def test_batas_dikirim_ke_sdk_dalam_satuan_yang_benar():
    k = _Gemini(payload={})
    gemini_minta(k, "gemini-3.6-flash", "halo", berpikir={"thinking_budget": 0},
                 batas_keluaran=1500, batas_detik=45)
    assert k.config["max_output_tokens"] == 1500
    assert k.config["thinking_config"] == {"thinking_budget": 0}
    assert k.config["http_options"] == {"timeout": 45_000}          # SDK Google memakai milidetik
    assert k.config["temperature"] == 0.0


def test_tanpa_batas_tidak_mengirim_kunci_apa_pun():
    k = _Gemini(payload={})
    gemini_minta(k, "m", "halo", batas_keluaran=None, batas_detik=0, berpikir=None)
    assert not {"max_output_tokens", "http_options", "thinking_config"} & set(k.config)


# -- jalur produksi ----------------------------------------------------------
def _narator(analisis, klien, **kw):
    s = AnalysisSettings(ai_enabled=True, ai_model="gemini-3.6-flash", ai_provider="gemini", **kw)
    return AiNarrator(s, client=klien).narrate(analisis)


def test_produksi_meneruskan_batas_dari_konfigurasi(analisis):
    k = _Gemini(payload=_ok(analisis))
    res = _narator(analisis, k, ai_max_output_tokens=2000, ai_thinking_budget=0, ai_timeout=30)
    assert res.status == "ai"
    assert k.config["max_output_tokens"] == 2000
    assert k.config["thinking_config"] == {"thinking_budget": 0}
    assert k.config["http_options"] == {"timeout": 30_000}


def test_bawaan_tetap_tanpa_batas_agar_perilaku_lama_tak_berubah(analisis):
    k = _Gemini(payload=_ok(analisis))
    assert _narator(analisis, k).status == "ai"
    assert not {"max_output_tokens", "http_options", "thinking_config"} & set(k.config)


def test_keluaran_terpotong_ditolak_bukan_ditampilkan_separuh(analisis):
    """Dengan batas token, pemotongan jadi mungkin: separuh ringkasan lebih berbahaya daripada
    hasil Deterministik yang utuh."""
    k = _Gemini(payload=_ok(analisis), finish="MAX_TOKENS")
    res = _narator(analisis, k, ai_max_output_tokens=10)
    assert res.status == "deterministik" and "terpotong" in res.alasan
    assert res.ringkasan == []


def test_batas_waktu_jatuh_ke_deterministik_dengan_alasan_jelas(analisis):
    k = _Gemini(galat=_Timeout("read timeout"))
    res = _narator(analisis, k, ai_timeout=5)
    assert res.status == "deterministik" and res.alasan == "Batas waktu 5 detik terlampaui"


def test_galat_lain_tidak_disamarkan_sebagai_batas_waktu(analisis):
    k = _Gemini(galat=ValueError("skema ditolak"))
    with pytest.raises(ValueError):
        _narator(analisis, k, ai_timeout=5)


def test_deteksi_batas_waktu_dari_nama_kelas_maupun_pesan():
    class ReadTimeout(Exception):
        pass

    assert _batas_waktu(ReadTimeout("x")) and _batas_waktu(RuntimeError("Request timeout after 30s"))
    assert not _batas_waktu(ValueError("skema tidak valid"))


def test_token_berpikir_tercatat_agar_biayanya_terlihat(analisis):
    k = _Gemini(payload=_ok(analisis), thoughts=777)
    res = _narator(analisis, k, ai_thinking_budget=1000)
    assert res.usage["thinking_tokens"] == 777 and res.usage["output_tokens"] == 50
