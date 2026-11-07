"""Fase 2: v2 structured analysis, AI-Assisted guard rails, evaluation."""
from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

import pytest

from hero.analysis import AiNarrator, analysis_payload
from hero.analysis.ai import build_facts, verify
from hero.analysis.structured import (
    NO_PASAL, analyse_document, classify_unit, extract_points, lampiran_profile,
    section_units, split_ayat, text_units, _REVOKED_NAME,
)
from hero.config import AnalysisSettings
from hero.pipeline import IngestPipeline


# ----------------------------------------------------------------- units
def test_cross_reference_does_not_open_an_ayat():
    """Regression: "Pasal 4 ayat (2)" inside ayat (1) was read as ayat (2)."""
    text = ("(1) Bank yang melanggar ketentuan sebagaimana dimaksud dalam Pasal 4 ayat (2) dikenai sanksi. "
            "(2) Dalam hal Bank tetap melanggar, dikenai denda.")
    got = split_ayat(text)
    assert [n for n, _ in got] == [1, 2]
    assert got[0][1].endswith("dikenai sanksi.")


def test_capitalised_term_is_not_an_obligation():
    """Regression: "Cuti Wajib adalah …" was a v1 'Kewajiban'."""
    assert classify_unit("Cuti Wajib adalah Cuti yang dilaksanakan untuk pengawasan internal.") is None
    assert classify_unit("Bank wajib menyampaikan laporan bulanan.")[0] == "Pelaporan"
    assert classify_unit("Bank dilarang menggunakan TKA.")[0] == "Larangan"
    assert classify_unit("The Bank shall submit the report.")[0] == "Pelaporan"


def test_points_keep_their_list_and_cite_the_ayat():
    """Regression: v1 cut "… selain untuk jabatan: a." before the list."""
    arts = [{"number": "7", "page": 5, "text": "", "ayat": [
        {"number": "1", "text": "KCBLN dilarang menggunakan TKA selain untuk jabatan: a. Pimpinan KCBLN; "
                                "dan/atau b. Tenaga Ahli atau Konsultan."}]}]
    p = extract_points(arts)[0]
    assert p.pasal == "Pasal 7 ayat (1)" and "b. Tenaga Ahli" in p.teks


def test_lampiran_heavy_regulation_is_flagged_with_real_headings():
    arts = [{"number": "1", "text": "Ketentuan mengenai X sebagaimana tercantum dalam: a. Lampiran I yang memuat pedoman."},
            {"number": "2", "text": "Peraturan ini mulai berlaku pada tanggal 1 September 2026."}]
    full = ("Ditetapkan di Jakarta\nKEPALA EKSEKUTIF PENGAWAS\nLAMPIRAN\nI. KETENTUAN UMUM\n"
            "isi\nII. PELAPORAN BULANAN\nREPUBLIK INDONESIA,")
    prof = lampiran_profile(full, arts)
    assert prof["berat_lampiran"] is True
    assert prof["judul_bagian"] == ["I. KETENTUAN UMUM", "II. PELAPORAN BULANAN"]


def test_lampiran_judul_dibaca_dan_disambung_saat_terpotong_baris():
    """Judul lampiran dicetak terpotong: "PEDOMAN" lalu perihalnya di baris berikut."""
    arts = [{"number": "1", "text": "Pedoman sebagaimana tercantum dalam: a. Lampiran I."}]
    full = ("Ditetapkan di Jakarta\nLAMPIRAN I\nPERATURAN ANGGOTA DEWAN KOMISIONER\n"
            "NOMOR 1 TAHUN 2026\nTENTANG\nPENYELENGGARAAN TEKNOLOGI INFORMASI\n"
            "PEDOMAN\nPENYELENGGARAAN TEKNOLOGI INFORMASI OLEH BANK UMUM\n"
            "I. KETENTUAN UMUM\nisi\n")
    prof = lampiran_profile(full, arts)
    assert prof["judul_lampiran"] == ("PEDOMAN PENYELENGGARAAN TEKNOLOGI INFORMASI "
                                      "OLEH BANK UMUM")


def test_lampiran_tabel_rata_memakai_judul_kapital_sebagai_cadangan():
    """Lampiran berupa satu tabel tidak punya penomoran — bagiannya huruf kapital."""
    arts = [{"number": "1", "text": "Pedoman sebagaimana tercantum dalam Lampiran."}]
    full = ("Ditetapkan di Jakarta\nLAMPIRAN\nNOMOR 7 TAHUN 2026\nTENTANG\n"
            "PENILAIAN KUALITAS PIUTANG\nPEDOMAN PENILAIAN KUALITAS PIUTANG PEMBIAYAAN\n"
            "PROSPEK USAHA DEBITUR\nisi baris\nKUALITAS MANAJEMEN\n")
    prof = lampiran_profile(full, arts)
    assert prof["judul_lampiran"] == "PEDOMAN PENILAIAN KUALITAS PIUTANG PEMBIAYAAN"
    # Tanpa cadangan ini, judul_bagian kosong dan keluarannya nyaris hampa.
    assert "PROSPEK USAHA DEBITUR" in prof["judul_bagian"]
    assert "KUALITAS MANAJEMEN" in prof["judul_bagian"]


def test_lampiran_bagian_bernomor_tetap_menang_atas_cadangan_kapital():
    """Dokumen yang sudah terbaca rapi tidak boleh berubah karena cadangan."""
    arts = [{"number": "1", "text": "Pedoman sebagaimana tercantum dalam Lampiran."}]
    full = ("Ditetapkan di Jakarta\nLAMPIRAN\nI. KETENTUAN UMUM\nPROSPEK USAHA DEBITUR\n"
            "II. PELAPORAN\n")
    prof = lampiran_profile(full, arts)
    assert prof["judul_bagian"] == ["I. KETENTUAN UMUM", "II. PELAPORAN"]


def test_lampiran_kalimat_prosa_tidak_diakui_sebagai_judul():
    """Invarian 6: lebih baik kosong daripada menyajikan kalimat contoh sebagai judul."""
    arts = [{"number": "1", "text": "Pedoman sebagaimana tercantum dalam Lampiran."}]
    full = ("Ditetapkan di Jakarta\nLAMPIRAN\n"
            "Contoh: utang pajak, liabilitas imbal kerja, dan pendapatan yang ditangguhkan.\n")
    prof = lampiran_profile(full, arts)
    assert prof["judul_lampiran"] is None


def test_lampiran_isi_bagian_mengutip_isi_bukan_cuma_judul():
    """T3 (Fase 2): PADK berat-Lampiran mendapat kutipan isi, bukan cuma judul bagian."""
    arts = [{"number": "1", "text": "Ketentuan mengenai X sebagaimana tercantum dalam: a. Lampiran I."}]
    full = ("Ditetapkan di Jakarta\nKEPALA EKSEKUTIF PENGAWAS\nLAMPIRAN\n"
            "I. KETENTUAN UMUM\nBank wajib menyusun pedoman tata kelola teknologi informasi "
            "secara tertulis dan terkini. Pedoman tersebut wajib disetujui direksi.\n"
            "II. PELAPORAN BULANAN\nLaporan disampaikan paling lambat tanggal 10 setiap bulan.\n")
    prof = lampiran_profile(full, arts)
    assert prof["judul_bagian"] == ["I. KETENTUAN UMUM", "II. PELAPORAN BULANAN"]
    isi = {sec["judul"]: sec["ringkasan"] for sec in prof["isi_bagian"]}
    assert isi["I. KETENTUAN UMUM"].startswith(
        "Bank wajib menyusun pedoman tata kelola teknologi informasi secara tertulis dan terkini.")
    assert isi["II. PELAPORAN BULANAN"].startswith("Laporan disampaikan paling lambat tanggal 10")


def test_lampiran_heading_tanpa_isi_tidak_dipaksa_mengutip():
    """Invarian 6: bagian tanpa isi substantif tidak diberi ringkasan karangan."""
    arts = [{"number": "1", "text": "Ketentuan mengenai X sebagaimana tercantum dalam: a. Lampiran I."}]
    full = "Ditetapkan di Jakarta\nLAMPIRAN\nI. KETENTUAN UMUM\nII. PELAPORAN\n"
    prof = lampiran_profile(full, arts)
    assert prof["isi_bagian"] == []


def test_lampiran_daftar_isi_bukan_judul_lampiran():
    arts = [{"number": "1", "text": "Pedoman sebagaimana tercantum dalam Lampiran."}]
    full = ("Ditetapkan di Jakarta\nLAMPIRAN\nDAFTAR ISI\n"
            "BAB I - PENDAHULUAN ....................................\n")
    prof = lampiran_profile(full, arts)
    assert prof["judul_lampiran"] is None


def test_revoked_name_skips_the_self_reference():
    t = ("Pada saat Peraturan Otoritas Jasa Keuangan ini mulai berlaku, Peraturan Otoritas Jasa Keuangan "
         "Nomor 37/POJK.03/2017 tentang Pemanfaatan Tenaga Kerja Asing (Lembaran Negara …), dicabut")
    assert _REVOKED_NAME.search(t).group(1).startswith("Peraturan Otoritas Jasa Keuangan Nomor 37/POJK.03/2017")


def test_surat_edaran_sections_become_numbered_points():
    full = "I. KETENTUAN UMUM 1. Bank wajib menerapkan manajemen risiko. 2. Bank dilarang menunda laporan."
    units = section_units([{"number": "I", "title": "KETENTUAN UMUM", "page": "1"}], full)
    assert [u["number"] for u in units] == ["I. KETENTUAN UMUM angka 1", "I. KETENTUAN UMUM angka 2"]


def test_unparsed_documents_are_labelled_not_guessed():
    units = text_units("Bank wajib menyampaikan laporan kepada OJK setiap bulan. Ditetapkan di Jakarta")
    pts = extract_points(units)
    assert pts and pts[0].pasal == NO_PASAL


# ----------------------------------------------------------------- end-to-end
@pytest.fixture
def catalog(tmp_path, tmp_settings, regulation_pdf):
    pipe = IngestPipeline(tmp_settings)
    try:
        assert pipe.run_upload([regulation_pdf(tmp_path / "a.pdf")]).ingested == 1
    finally:
        pipe.close()
    conn = sqlite3.connect(tmp_settings.catalog_db)
    conn.row_factory = sqlite3.Row
    return conn


def test_v2_analysis_of_a_real_pdf(catalog):
    doc_id = catalog.execute("SELECT doc_id FROM documents").fetchone()[0]
    a = analyse_document(catalog, doc_id)
    cats = {p.kategori for p in a.poin}
    assert {"Kewajiban", "Larangan", "Sanksi"} <= cats
    assert all(p.pasal.startswith("Pasal ") for p in a.poin)
    assert "teguran/peringatan tertulis" in a.sanksi
    assert any("Pasal 3" in r for s in a.ringkasan for r in s["rujukan"])


def test_metrik_memuat_hitungan_yang_dibaca_layar_analisa(catalog):
    """Layar Analisa membaca ``metrik.jumlah_halaman`` untuk penyebut halaman; tanpa itu ia
    menebak "total halaman = halaman tertinggi yang dikutip". Semua angka harus turunan
    dari data nyata, bukan taksiran."""
    doc_id = catalog.execute("SELECT doc_id FROM documents").fetchone()[0]
    a = analyse_document(catalog, doc_id)
    m = a.metrik
    for kunci in ("jumlah_pasal", "jumlah_bab", "jumlah_halaman", "jumlah_kewajiban", "jumlah_larangan"):
        assert kunci in m, kunci
    assert m["jumlah_pasal"] == a.identitas["jumlah_pasal"] > 0
    assert m["jumlah_kewajiban"] == sum(1 for p in a.poin if p.kategori == "Kewajiban") > 0
    assert m["jumlah_larangan"] == sum(1 for p in a.poin if p.kategori == "Larangan") > 0
    row = catalog.execute("SELECT page_count FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
    assert m["jumlah_halaman"] == (row[0] or None)
    assert m["jumlah_halaman"] is None or m["jumlah_halaman"] >= max(
        (p.halaman or 0) for p in a.poin), "halaman total tak boleh lebih kecil dari halaman yang dikutip"


def test_versi_mesin_naik_saat_bentuk_keluaran_berubah(catalog):
    from hero.analysis.structured import VERSION

    doc_id = catalog.execute("SELECT doc_id FROM documents").fetchone()[0]
    assert analyse_document(catalog, doc_id).versi == VERSION and VERSION != "v2.0"


# ----------------------------------------------------------------- AI guard rails
class FakeClient:
    def __init__(self, payload=None, stop_reason="end_turn"):
        self.calls = 0
        self.payload, self.stop_reason = payload, stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls += 1
        self.kwargs = kw
        text = json.dumps(self.payload) if self.payload is not None else ""
        return SimpleNamespace(stop_reason=self.stop_reason, model="claude-opus-5",
                               stop_details=SimpleNamespace(category="cyber"),
                               content=[SimpleNamespace(type="thinking", thinking=""),
                                        SimpleNamespace(type="text", text=text)],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                                     cache_read_input_tokens=0, cache_creation_input_tokens=0))


def _analysis(catalog):
    doc_id = catalog.execute("SELECT doc_id FROM documents").fetchone()[0]
    return analyse_document(catalog, doc_id)


def _good_output(facts):
    f = next(x for x in facts if x["id"].startswith("F"))
    return {"ringkasan": [{"kalimat": "Peraturan ini mengatur teknologi informasi bank.", "fakta": ["I2"]},
                          {"kalimat": "Bank memikul kewajiban utama.", "fakta": [f["id"]]}],
            "poin_kunci": [{"fakta": f["id"], "parafrase": "Bank harus menjalankan kewajiban ini."}]}


def test_ai_is_off_by_default_and_never_called(catalog):
    fake = FakeClient()
    res = AiNarrator(AnalysisSettings(), client=fake).narrate(_analysis(catalog))
    assert res.status == "deterministik" and "dinonaktifkan" in res.alasan and fake.calls == 0


def test_internal_documents_are_never_sent(catalog):
    fake = FakeClient()
    res = AiNarrator(AnalysisSettings(ai_enabled=True), client=fake).narrate(_analysis(catalog), akses="internal")
    assert res.status == "deterministik" and fake.calls == 0


def test_verified_ai_output_is_used_and_cited(catalog):
    a = _analysis(catalog)
    fake = FakeClient(_good_output(build_facts(a)))
    res = AiNarrator(AnalysisSettings(ai_enabled=True), client=fake).narrate(a)
    assert res.status == "ai" and res.ringkasan[1]["rujukan"]
    kw = fake.kwargs
    assert kw["model"] == "claude-opus-5" and kw["fallbacks"] == "default"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_changed_number_is_rejected(catalog):
    """The worst summary error: a deadline or amount silently altered."""
    a = _analysis(catalog)
    out = _good_output(build_facts(a))
    out["ringkasan"][1]["kalimat"] = "Bank wajib melapor dalam 15 hari."
    res = AiNarrator(AnalysisSettings(ai_enabled=True), client=FakeClient(out)).narrate(a)
    assert res.status == "deterministik" and any("angka" in v for v in res.pelanggaran)


def test_unknown_fact_and_foreign_pasal_are_rejected():
    facts = [{"id": "F1", "teks": "[Kewajiban] Bank wajib melapor.", "pasal": "Pasal 2"}]
    out = {"ringkasan": [{"kalimat": "Diatur di Pasal 9.", "fakta": ["F1"]},
                         {"kalimat": "Sesuatu.", "fakta": ["F7"]}], "poin_kunci": []}
    problems = verify(out, facts)
    assert any("pasal di luar" in p for p in problems) and any("tidak ada" in p for p in problems)


def test_refusal_falls_back(catalog):
    res = AiNarrator(AnalysisSettings(ai_enabled=True), client=FakeClient({}, "refusal")).narrate(_analysis(catalog))
    assert res.status == "deterministik" and "menolak" in res.alasan


def test_verified_result_is_cached(catalog):
    a = _analysis(catalog)
    fake = FakeClient(_good_output(build_facts(a)))
    n = AiNarrator(AnalysisSettings(ai_enabled=True), client=fake)
    n.narrate(a, conn=catalog)
    again = n.narrate(a, conn=catalog)
    assert again.dari_cache and fake.calls == 1


def test_payload_explains_which_mode_was_used(catalog):
    doc_id = catalog.execute("SELECT doc_id FROM documents").fetchone()[0]
    out = analysis_payload(catalog, doc_id, mode="ai", narrator=AiNarrator(AnalysisSettings()))
    assert out["mode_dipakai"] == "deterministik" and out["ai"]["alasan"]
    assert out["poin_utama"] and out["ringkasan"]


def test_phase2_evaluation_runs(catalog):
    from hero.analysis.evaluate import evaluate
    ev = evaluate(catalog)
    assert ev["versi"]["v2"]["poin_berujukan_pasal_pct"] == 100.0
    assert ev["versi"]["v2"]["poin_terlacak_pct"] == 100.0


# ----------------------------------------------------------------- clauses
def test_intent_detection():
    from hero.analysis.clauses import detect_intents
    assert detect_intents("sanksi jika melanggar penggunaan TKA") == ["Sanksi"]
    assert set(detect_intents("batas waktu melaporkan pengangkatan")) == {"Pelaporan", "Batas Waktu"}
    assert detect_intents("berapa lama cuti melahirkan") == []


def test_sanction_article_ranks_by_density(tmp_path):
    """Sanctions are written by cross-reference ("yang melanggar … Pasal 4 …
    dikenai sanksi"), so text similarity cannot find the sanction article;
    the article whose every ayat is a sanction must lead the intent ranking."""
    from hero.analysis.clauses import _points_by_label
    conn = sqlite3.connect(tmp_path / "c.db")
    conn.execute("CREATE TABLE analysis_v2 (doc_id TEXT, hasil TEXT)")
    poin = ([{"kategori": "Sanksi", "pasal": f"Pasal 11 ayat ({i})", "teks": "dikenai sanksi"} for i in range(1, 6)]
            + [{"kategori": "Sanksi", "pasal": "Pasal 14 ayat (3)", "teks": "dikenai sanksi"},
               {"kategori": "Kewajiban", "pasal": "Pasal 2 ayat (1)", "teks": "wajib"}])
    conn.execute("INSERT INTO analysis_v2 VALUES ('d', ?)", (json.dumps({"poin": poin}),))
    got = _points_by_label(conn, "d", ["Sanksi"])
    assert list(got) == ["11", "14"] and len(got["11"]) == 5


# ------------------------------------------------- penyedia Gemini (Google AI)
class FakeGemini:
    """Bentuk respons google-genai: .text, .usage_metadata, .candidates[0]."""

    def __init__(self, payload=None, finish_reason="STOP", candidates=True,
                 block_reason=None, raise_exc=None):
        self.calls = 0
        self.payload, self.finish_reason = payload, finish_reason
        self.candidates, self.block_reason, self.raise_exc = candidates, block_reason, raise_exc
        self.models = SimpleNamespace(generate_content=self.generate_content)

    def generate_content(self, **kw):
        self.calls += 1
        self.kwargs = kw
        if self.raise_exc is not None:
            raise self.raise_exc
        text = json.dumps(self.payload) if self.payload is not None else ""
        kand = [SimpleNamespace(finish_reason=self.finish_reason)] if self.candidates else []
        return SimpleNamespace(
            text=text, model_version="gemini-2.5-pro", candidates=kand,
            prompt_feedback=SimpleNamespace(block_reason=self.block_reason),
            usage_metadata=SimpleNamespace(prompt_token_count=11, candidates_token_count=7,
                                           cached_content_token_count=0))


def _gemini(**kw) -> AnalysisSettings:
    return AnalysisSettings(ai_enabled=True, ai_model="gemini-2.5-pro", **kw)


def test_penyedia_ditebak_dari_nama_model():
    from hero.analysis.ai import ANTHROPIC, GEMINI, provider_of

    assert provider_of(AnalysisSettings(ai_model="gemini-2.5-pro")) == GEMINI
    assert provider_of(AnalysisSettings(ai_model="claude-opus-5")) == ANTHROPIC
    # Eksplisit menang atas tebakan.
    assert provider_of(AnalysisSettings(ai_model="claude-opus-5", ai_provider="google")) == GEMINI


def test_penyedia_tidak_dikenal_ditolak_bukan_didiamkan():
    from hero.analysis.ai import provider_of

    with pytest.raises(ValueError, match="tidak dikenal"):
        provider_of(AnalysisSettings(ai_provider="openai"))


def test_gemini_keluaran_terverifikasi_dipakai_dan_berujukan(catalog):
    a = _analysis(catalog)
    fake = FakeGemini(_good_output(build_facts(a)))
    res = AiNarrator(_gemini(), client=fake).narrate(a)
    assert res.status == "ai" and res.ringkasan[1]["rujukan"]
    assert res.model == "gemini-2.5-pro"
    cfg = fake.kwargs["config"]
    assert cfg["response_mime_type"] == "application/json"
    assert cfg["system_instruction"].startswith("Anda membantu analis regulasi")
    # Parafrase fakta, bukan karangan.
    assert cfg["temperature"] == 0


def test_gemini_skema_dibersihkan_dari_additional_properties(catalog):
    a = _analysis(catalog)
    fake = FakeGemini(_good_output(build_facts(a)))
    AiNarrator(_gemini(), client=fake).narrate(a)
    skema = json.dumps(fake.kwargs["config"]["response_schema"])
    # Gemini menolak permintaan yang memuat kata kunci ini.
    assert "additionalProperties" not in skema
    assert "ringkasan" in skema and "poin_kunci" in skema


def test_gemini_angka_diubah_tetap_ditolak_verifikasi(catalog):
    """Jaminan inti tidak boleh bergantung pada penyedia."""
    a = _analysis(catalog)
    facts = build_facts(a)
    buruk = _good_output(facts)
    buruk["ringkasan"][0]["kalimat"] = "Peraturan ini mengatur 99 hari kerja."
    res = AiNarrator(_gemini(), client=FakeGemini(buruk)).narrate(a)
    assert res.status == "deterministik" and res.pelanggaran


def test_gemini_dokumen_internal_tetap_tidak_pernah_dikirim(catalog):
    fake = FakeGemini()
    res = AiNarrator(_gemini(), client=fake).narrate(_analysis(catalog), akses="internal")
    assert res.status == "deterministik" and fake.calls == 0


def test_gemini_keluaran_terpotong_jatuh_ke_deterministik(catalog):
    a = _analysis(catalog)
    res = AiNarrator(_gemini(), client=FakeGemini(_good_output(build_facts(a)),
                                                  finish_reason="MAX_TOKENS")).narrate(a)
    assert res.status == "deterministik" and "terpotong" in res.alasan


def test_gemini_penolakan_filter_keamanan_dilaporkan_apa_adanya(catalog):
    a = _analysis(catalog)
    res = AiNarrator(_gemini(), client=FakeGemini(finish_reason="SAFETY")).narrate(a)
    assert res.status == "deterministik" and "menolak" in res.alasan


def test_gemini_permintaan_diblokir_tidak_dilaporkan_sebagai_json_rusak(catalog):
    """Kandidat kosong berarti diblokir; 'bukan JSON valid' menyesatkan operator."""
    a = _analysis(catalog)
    res = AiNarrator(_gemini(), client=FakeGemini(candidates=False,
                                                  block_reason="SAFETY")).narrate(a)
    assert res.status == "deterministik" and "diblokir" in res.alasan


@pytest.mark.parametrize("kode, petunjuk", [
    (401, "Kredensial"), (403, "Kredensial"), (429, "Kuota"),
    (404, "tidak ditemukan"), (503, "bermasalah"),
])
def test_gemini_galat_api_dipilah_dari_kode_status(kode, petunjuk):
    from hero.analysis.ai import _pilah_galat_gemini

    assert petunjuk in _pilah_galat_gemini(SimpleNamespace(code=kode))


def test_status_menyebut_penyedia_dan_sdk_yang_tepat():
    """Tanpa SDK Google terpasang, status harus menyebut SDK ITU — bukan anthropic.

    Sebelum ada jalur Gemini, pesannya selalu "SDK anthropic belum terpasang",
    yang mengirim operator memasang paket yang salah.
    """
    st = AiNarrator(_gemini(), client=FakeGemini()).status()
    assert st["penyedia"] == "gemini"
    assert st["model"] == "gemini-2.5-pro"
    assert "google.genai" in st["ringkas"] or "gemini-2.5-pro" in st["ringkas"]
    assert "anthropic" not in st["ringkas"]


def test_klien_ai_tanpa_batas_baca_bawaan_tapi_menyambung_dibatasi():
    import httpx

    t = AiNarrator(AnalysisSettings())._timeout()
    assert isinstance(t, httpx.Timeout)
    assert t.read is None and t.connect == 15.0
    assert AiNarrator(AnalysisSettings(ai_timeout=45))._timeout() == 45.0
