"""Harmonisasi (URD 3.4): explicit references, amendment plans, labels, report."""
from __future__ import annotations

import pytest

from hero.harmonisasi.engine import (
    CorpusArticle, DraftDoc, clean_article, classify, harmonise, load_config, provision_diff,
)
from hero.harmonisasi.refs import amendment_plan
from hero.kb.catalog import Catalog

AMENDMENT = """PERATURAN OTORITAS JASA KEUANGAN NOMOR 10 TAHUN 2026 TENTANG PERUBAHAN ATAS
PERATURAN OTORITAS JASA KEUANGAN NOMOR 14 TAHUN 2023 TENTANG PERDAGANGAN KARBON
Pasal I Beberapa ketentuan diubah sebagai berikut:
1. Ketentuan angka 2, angka 3, dan angka 5 Pasal 1 diubah sehingga berbunyi sebagai berikut: Pasal 1 ...
2. Ketentuan Pasal 3 diubah sehingga berbunyi sebagai berikut: Pasal 3 ...
3. Di antara Pasal 12 dan Pasal 13 disisipkan 1 (satu) pasal, yakni pasal 12A sehingga berbunyi sebagai berikut: Pasal 12A ...
4. Setelah ayat (2) Pasal 26 ditambahkan 1 (satu) ayat, yakni ayat (3) sehingga berbunyi sebagai berikut: Pasal 26 ...
5. Ketentuan ayat (2) Pasal 30 dihapus sehingga berbunyi sebagai berikut: Pasal 30 ...
6. Pasal 31 dihapus.
7. Di antara BAB V dan BAB VI disisipkan1 (satu) BAB yakni BAB VA dengan Pasal 29A, Pasal 29B, dan Pasal 29C sehingga berbunyi sebagai berikut: ...
Ditetapkan di Jakarta
PENJELASAN Angka 11 Pasal 35C Cukup jelas. Ketentuan lain sebagaimana dimaksud dalam Pasal 40 diubah ...
"""


def test_amendment_plan_reads_each_instruction_and_ignores_the_penjelasan():
    plan = amendment_plan(AMENDMENT)
    assert plan.diubah == {"1", "3", "26", "30"}          # ayat removal = article changed
    assert plan.disisipkan == {"12A", "29A", "29B", "29C"}  # incl. "disisipkan1" glued typo
    assert plan.dihapus == {"31"}
    assert "35C" not in plan.diubah and "40" not in plan.diubah


def test_single_change_amendment_with_long_citation():
    text = ("Pasal I Ketentuan Pasal 40 dalam Peraturan Otoritas Jasa Keuangan Nomor 49 Tahun 2024 "
            "tentang Pengawasan Lembaga Pembiayaan (Lembaran Negara Republik Indonesia Tahun 2024 "
            "Nomor 62/OJK, Tambahan Lembaran Negara Republik Indonesia Nomor 130/OJK) diubah sebagai "
            "berikut: Pasal 40 Bagi Lembaga Keuangan Mikro sebagaimana dimaksud dalam Pasal 24 ...")
    assert amendment_plan(text).diubah == {"40"}


def test_plain_regulation_has_no_plan():
    assert amendment_plan("Pasal 1 Bank wajib melapor. Ketentuan lebih lanjut diatur OJK.").kosong


def test_trailing_instruction_is_cut_from_an_article():
    raw = "Unit Karbon terdiri atas: a. Kuota; dan b. SPE GRK. 4. Di antara Pasal 12 dan Pasal 13 disisipkan"
    assert clean_article(raw) == "Unit Karbon terdiri atas: a. Kuota; dan b. SPE GRK."


@pytest.mark.parametrize("old,new,expect", [
    ("Bank wajib menyampaikan laporan paling lambat 10 (sepuluh) hari kerja.",
     "Bank wajib menyampaikan laporan paling lambat 15 (lima belas) hari kerja.", "hari: 10 → 15"),
    ("Bank wajib menyampaikan laporan bulanan.", "Bank dapat menyampaikan laporan bulanan.",
     "kewajiban menjadi kebolehan"),
    ("Denda paling banyak Rp1.000.000,00 (satu juta rupiah).",
     "Denda paling banyak Rp5.000.000,00 (lima juta rupiah).", "rupiah: Rp1.000.000 → Rp5.000.000"),
])
def test_provision_differences_are_concrete_and_quotable(old, new, expect):
    assert expect in provision_diff(old, new)


def test_same_numbers_mean_no_difference():
    assert provision_diff("wajib dalam 10 hari kerja", "wajib paling lambat 10 hari kerja") == []


def _art(text, key="POJK|1|2020", status="berlaku"):
    return CorpusArticle("d1", key, "Pelaporan Bank", "1/POJK.03/2020", status, "7", 3, text)


CFG = load_config(None)
OLD = "Bank wajib menyampaikan laporan kepada Otoritas Jasa Keuangan paling lambat 10 (sepuluh) hari kerja setelah akhir bulan."


def test_labels_follow_the_rules():
    same = OLD
    assert classify(same, _art(OLD), 0.99, set(), CFG)[0] == "duplikasi"
    changed = OLD.replace("10 (sepuluh)", "15 (lima belas)")
    assert classify(changed, _art(OLD), 0.8, set(), CFG)[0] == "konflik"
    assert classify(changed, _art(OLD), 0.8, {"POJK|1|2020"}, CFG)[0] == "menggantikan"
    detailed = OLD + " Laporan disampaikan secara daring melalui sistem pelaporan dengan format yang ditetapkan."
    label, _, why, _ = classify(detailed, _art(OLD), 0.7, set(), CFG)
    assert label == "memperjelas" and "termuat" in why
    assert classify("Penyelenggara aset kripto wajib memisahkan dana nasabah.", _art(OLD), 0.05,
                    set(), CFG)[0] == "pasal_baru"


def test_a_revoked_comparison_is_not_called_conflict():
    changed = OLD.replace("10 (sepuluh)", "15 (lima belas)")
    assert classify(changed, _art(OLD, status="dicabut"), 0.8, set(), CFG)[0] != "konflik"


def _seed(cat: Catalog, doc_id: str, number: str, year: int, subject: str, articles: dict[str, str],
          reg_status="berlaku"):
    cat.conn.execute(
        "INSERT INTO documents (doc_id, sha256, source_type, doc_type, number, year, title, subject, "
        "status, reg_status) VALUES (?,?,'web','POJK',?,?,?,?,'ingested',?)",
        (doc_id, doc_id * 4, number, year, f"POJK tentang {subject}", subject, reg_status))
    for n, t in articles.items():
        cat.conn.execute("INSERT INTO articles (doc_id, number, page, text) VALUES (?,?,?,?)",
                         (doc_id, n, 1, t))


def test_end_to_end_report_has_candidates_findings_and_evidence(tmp_path):
    cat = Catalog(tmp_path / "c.db")
    _seed(cat, "base", "14 Tahun 2023", 2023, "Perdagangan Karbon", {
        "3": "Unit Karbon yang diperdagangkan wajib dicatatkan pada Sistem Registri Nasional "
             "paling lambat 5 (lima) hari kerja sebelum perdagangan.",
        "9": "Penyelenggara Bursa Karbon wajib memiliki modal disetor paling sedikit Rp100.000.000.000,00.",
    })
    _seed(cat, "other", "2 Tahun 2024", 2024, "Kredit Usaha Rakyat", {
        "4": "Bank penyalur kredit usaha rakyat wajib menerapkan prinsip kehati-hatian dalam penyaluran.",
    })
    _seed(cat, "old", "8 Tahun 2015", 2015, "Bursa Lama", {
        "2": "Unit Karbon yang diperdagangkan wajib dicatatkan pada Sistem Registri Nasional.",
    }, reg_status="dicabut")
    cat.conn.commit()
    draft = DraftDoc(
        "POJK tentang Perubahan atas Peraturan Otoritas Jasa Keuangan Nomor 14 Tahun 2023 tentang "
        "Perdagangan Karbon", "POJK|10|2026",
        "Ketentuan Pasal 3 diubah sehingga berbunyi sebagai berikut: Pasal 3 ... "
        "Di antara Pasal 12 dan Pasal 13 disisipkan 1 (satu) pasal, yakni Pasal 12A sehingga berbunyi",
        [{"number": "3", "page": 2, "text": "Unit Karbon yang diperdagangkan wajib dicatatkan pada "
          "Sistem Registri Nasional paling lambat 10 (sepuluh) hari kerja sebelum perdagangan."},
         {"number": "12A", "page": 3, "text": "Penyelenggara Bursa Karbon wajib menyediakan layanan "
          "pengaduan konsumen secara daring setiap hari."}])
    rep = harmonise(cat.conn, draft, CFG)
    by = {f.pasal_draft: f for f in rep.temuan}
    assert rep.kandidat[0]["doc_id"] == "base"
    assert any("mengubah" in a for a in rep.kandidat[0]["alasan"])
    assert by["Pasal 3"].jenis == "menggantikan"                 # explicit amendment, 5 → 10 days
    assert by["Pasal 3"].pembanding["pasal"] == "3" and "hari: 5 → 10" in by["Pasal 3"].perbedaan
    assert by["Pasal 3"].pembanding["pdf"].startswith("/api/kb/documents/base/pdf")
    assert by["Pasal 12A"].jenis == "pasal_baru"
    assert all(f.pembanding is None or f.pembanding["doc_id"] != "old" for f in rep.temuan)
    assert rep.ringkasan["rencana_perubahan"]["disisipkan"] == ["12A"]
    d = rep.to_dict()
    assert d["temuan"][0]["badge"]["tone"] in {"danger", "warning", "info", "neutral", "success"}
    assert "Draft / Rekomendasi" in d["catatan"]


def test_a_citation_is_not_a_duration():
    old = "Bank sebagaimana dimaksud dalam Undang-Undang Nomor 10 Tahun 1998 wajib melapor."
    new = "Bank sebagaimana dimaksud dalam Undang-Undang Nomor 7 Tahun 1992 wajib melapor."
    assert provision_diff(old, new) == []


@pytest.mark.parametrize("text,key", [
    ("Surat Edaran Bank Indonesia Nomor 31/14/UPPB", "SEBI|31/14/UPPB|1998"),
    ("Surat Edaran Bank Indonesia Nomor 27/9/UPPB", "SEBI|27/9/UPPB|1994"),
    ("Peraturan Bank Indonesia Nomor 24/7/PBI/2022", "PBI|24/7|2022"),
])
def test_bank_indonesia_years_never_land_in_the_future(text, key):
    from hero.graph.identity import canonical_ref

    assert canonical_ref(text).key == key


def test_register_suggests_related_regulations_missing_from_the_kb(tmp_path):
    from hero.harmonisasi.engine import register_candidates

    cat = Catalog(tmp_path / "c.db")
    for key, title, doc_id in [
        ("POJK|11|2022", "Peraturan OJK Nomor 11/POJK.03/2022 tentang Penyelenggaraan Teknologi "
                         "Informasi oleh Bank Umum", None),
        ("POJK|1|2026", "Peraturan OJK Nomor 1 Tahun 2026 tentang Penyelenggaraan Teknologi "
                        "Informasi oleh Bank Perekonomian Rakyat", None),
        ("POJK|9|2020", "Peraturan OJK Nomor 9 Tahun 2020 tentang Laporan Bulanan Dana Pensiun", None)]:
        cat.conn.execute("INSERT INTO inventory (record_key, source, reg_key, title, status, doc_id) "
                         "VALUES (?, 'jdih-ojk', ?, ?, 'berlaku', ?)", (key, key, title, doc_id))
    _seed(cat, "have", "1 Tahun 2026", 2026, "Penyelenggaraan Teknologi Informasi oleh Bank "
          "Perekonomian Rakyat", {"1": "x" * 50})   # same identity, arrived via a folder
    cat.conn.commit()
    draft = DraftDoc("Rancangan POJK tentang Standar Penyelenggaraan Teknologi Informasi oleh BPR",
                     None, "", [])
    got = [c["key"] for c in register_candidates(cat.conn, draft, CFG)]
    assert got == ["POJK|11|2022"]


def test_status_pasal_memakai_kosakata_pak_faris():
    from hero.harmonisasi.engine import LABELS, STATUS_KB

    assert set(STATUS_KB) == set(LABELS), "setiap label harus punya padanan kosakata mitra"
    assert {STATUS_KB[k] for k in ("pasal_baru", "duplikasi", "menggantikan", "memperjelas")} == \
        {"baru", "sama", "menggantikan", "melengkapi"}


# --- Weekly #10: kata kunci relasi dulu, lalu bandingkan dengan peraturan yang dirujuk saja ---

def test_kata_kunci_relasi_dibaca_dari_badan_dan_penutup(tmp_path):
    from hero.harmonisasi.refs import explicit_references

    cat = Catalog(tmp_path / "c.db")
    teks = ("Mengingat: Peraturan Otoritas Jasa Keuangan Nomor 3 Tahun 2019 sebagaimana telah diubah "
            "dengan Peraturan Otoritas Jasa Keuangan Nomor 5 Tahun 2021. "
            "Pasal I Beberapa ketentuan dalam Peraturan Otoritas Jasa Keuangan Nomor 14 Tahun 2023 "
            "tentang Perdagangan Karbon (Lembaran Negara Republik Indonesia Tahun 2023 Nomor 7/OJK) "
            "diubah sebagai berikut: 1. Ketentuan Pasal 3 diubah. "
            "Pada saat Peraturan OJK ini mulai berlaku: a. Peraturan Otoritas Jasa Keuangan Nomor 8 "
            "Tahun 2015 tentang Bursa dicabut dan dinyatakan tidak berlaku; dan b. Ketentuan Pasal 10 "
            "dan Pasal 11 Peraturan Otoritas Jasa Keuangan Nomor 2 Tahun 2020 tentang Pelaporan "
            "dicabut dan dinyatakan tidak berlaku.")
    by = {r.key: r for r in explicit_references(cat.conn, teks, "Rancangan POJK", [])}
    assert by["POJK|14|2023"].relasi == "diubah" and "diubah sebagai berikut" in by["POJK|14|2023"].kata_kunci
    assert by["POJK|8|2015"].relasi == "dicabut"
    assert by["POJK|2|2020"].relasi == "dicabut_sebagian"
    assert by["POJK|2|2020"].pasal_dicabut == ["10", "11"]
    assert by["POJK|3|2019"].relasi == "dirujuk"          # dasar hukum di Mengingat, bukan relasi


def _korpus_relasi(tmp_path):
    cat = Catalog(tmp_path / "c.db")
    _seed(cat, "induk", "14 Tahun 2023", 2023, "Perdagangan Karbon", {
        "3": "Unit Karbon yang diperdagangkan wajib dicatatkan pada Sistem Registri Nasional "
             "paling lambat 5 (lima) hari kerja sebelum perdagangan.",
        "4": "Penyelenggara Bursa Karbon wajib memiliki modal disetor paling sedikit Rp100.000.000.000,00.",
        "5": "Penyelenggara Bursa Karbon wajib menyampaikan laporan bulanan kepada Otoritas Jasa Keuangan."})
    # Pasal kembar di peraturan lain — lebih mirip dengan draft daripada induknya sendiri.
    _seed(cat, "saudara", "9 Tahun 2024", 2024, "Registri Karbon", {
        "7": "Unit Karbon yang diperdagangkan wajib dicatatkan pada Sistem Registri Nasional "
             "paling lambat 10 (sepuluh) hari kerja sebelum perdagangan dilakukan."})
    _seed(cat, "lama", "8 Tahun 2015", 2015, "Bursa Lama", {
        "2": "Penyelenggara Bursa wajib memiliki modal disetor paling sedikit Rp50.000.000.000,00."},
        reg_status="dicabut")
    cat.conn.commit()
    return cat


PASAL_3_BARU = {"number": "3", "page": 2, "text": "Unit Karbon yang diperdagangkan wajib dicatatkan "
                "pada Sistem Registri Nasional paling lambat 10 (sepuluh) hari kerja sebelum perdagangan."}


def test_perubahan_hanya_dibandingkan_dengan_induk_dan_dampaknya_per_pasal(tmp_path):
    cat = _korpus_relasi(tmp_path)
    draft = DraftDoc("POJK tentang Perubahan atas Peraturan Otoritas Jasa Keuangan Nomor 14 Tahun 2023 "
                     "tentang Perdagangan Karbon", "POJK|10|2026",
                     "Ketentuan Pasal 3 diubah sehingga berbunyi sebagai berikut: Pasal 3 ... "
                     "Pasal 5 dihapus.", [PASAL_3_BARU])
    rep = harmonise(cat.conn, draft, CFG)
    assert rep.relasi["mode"] == "terarah" and rep.relasi["sasaran"] == ["POJK|14|2023"]
    assert "judul" in rep.relasi["kata_kunci"][0]["bukti"]
    assert {k["doc_id"] for k in rep.kandidat} == {"induk"}       # saudara tak ikut dibandingkan
    f = rep.temuan[0]
    assert f.pembanding["doc_id"] == "induk" and f.jenis == "menggantikan"
    assert f.pembanding["status_setelah_draft"] == "tidak_berlaku"
    (d,) = rep.dampak_status
    assert d["status_setelah"] == "diubah"
    assert d["pasal_tidak_berlaku"] == ["3", "5"] and d["pasal_tetap_berlaku"] == ["4"]
    assert any("Pasal 3, 5 versi lama tidak berlaku" in r for r in rep.rekomendasi)


def test_tanpa_kata_kunci_relasi_dianggap_peraturan_baru(tmp_path):
    cat = _korpus_relasi(tmp_path)
    draft = DraftDoc("Rancangan POJK tentang Registri Karbon", None, "Pasal 1 ...", [PASAL_3_BARU])
    rep = harmonise(cat.conn, draft, CFG)
    assert rep.relasi["mode"] == "seluruh_kb" and "peraturan baru" in rep.relasi["alasan"]
    assert rep.dampak_status == []
    assert rep.temuan[0].pembanding["doc_id"] == "saudara"
    assert rep.temuan[0].kecocokan in {"tampil", "pertimbangkan", "tidak_dikutip"}


def test_pencabutan_dibandingkan_dengan_yang_dicabut_walau_statusnya_sudah_dicabut(tmp_path):
    cat = _korpus_relasi(tmp_path)
    draft = DraftDoc("Rancangan POJK tentang Bursa Karbon", None,
                     "Pada saat Peraturan OJK ini mulai berlaku, Peraturan Otoritas Jasa Keuangan "
                     "Nomor 8 Tahun 2015 tentang Bursa Lama dicabut dan dinyatakan tidak berlaku.",
                     [{"number": "2", "page": 1, "text": "Penyelenggara Bursa wajib memiliki modal "
                       "disetor paling sedikit Rp75.000.000.000,00."}])
    rep = harmonise(cat.conn, draft, CFG)
    assert rep.relasi["mode"] == "terarah" and rep.relasi["sasaran"] == ["POJK|8|2015"]
    (d,) = rep.dampak_status
    assert d["status_setelah"] == "dicabut" and d["pasal_tidak_berlaku"] == ["2"]
    assert rep.temuan[0].pembanding["status_setelah_draft"] == "tidak_berlaku"


def test_induk_belum_di_kb_kembali_ke_seluruh_kb_dengan_catatan(tmp_path):
    cat = _korpus_relasi(tmp_path)
    draft = DraftDoc("POJK tentang Perubahan atas Peraturan Otoritas Jasa Keuangan Nomor 77 Tahun 2022 "
                     "tentang Hal Lain", None, "Ketentuan Pasal 3 diubah.", [PASAL_3_BARU])
    rep = harmonise(cat.conn, draft, CFG)
    assert rep.relasi["mode"] == "seluruh_kb" and rep.relasi["belum_di_kb"] == ["POJK|77|2022"]
    assert any("belum ada di Knowledge Base" in r for r in rep.rekomendasi)


def test_tingkat_kecocokan_mengikuti_mode():
    from hero.harmonisasi.engine import tingkat_kecocokan

    assert tingkat_kecocokan(0.6, "terarah", CFG) == "tampil"
    assert tingkat_kecocokan(0.6, "seluruh_kb", CFG) == "pertimbangkan"
    assert tingkat_kecocokan(0.5, "seluruh_kb", CFG) == "tidak_dikutip"


def test_pencabutan_sebagian_hanya_menggugurkan_pasal_yang_disebut(tmp_path):
    cat = _korpus_relasi(tmp_path)
    draft = DraftDoc("Rancangan POJK tentang Laporan Bursa Karbon", None,
                     "Pada saat Peraturan OJK ini mulai berlaku, Ketentuan Pasal 5 Peraturan Otoritas "
                     "Jasa Keuangan Nomor 14 Tahun 2023 tentang Perdagangan Karbon dicabut dan "
                     "dinyatakan tidak berlaku.",
                     [{"number": "2", "page": 1, "text": "Penyelenggara Bursa Karbon wajib menyampaikan "
                       "laporan mingguan kepada Otoritas Jasa Keuangan."}])
    rep = harmonise(cat.conn, draft, CFG)
    assert rep.relasi["mode"] == "terarah"
    assert "sebagian" in rep.kandidat[0]["alasan"][0]
    (d,) = rep.dampak_status
    assert d["status_setelah"] == "dicabut sebagian"
    assert d["pasal_tidak_berlaku"] == ["5"] and d["pasal_tetap_berlaku"] == ["3", "4"]


def test_nomor_berjenis_di_dalamnya_tidak_memotong_konteks_pencabutan_sebagian(tmp_path):
    from hero.harmonisasi.refs import explicit_references

    cat = Catalog(tmp_path / "c.db")
    teks = ("Pada saat POJK ini mulai berlaku: a) POJK Nomor 4/POJK.03/2015 tentang Tata Kelola BPR; "
            "dan b) Pasal 12 POJK Nomor 3/POJK.03/2022 tentang Penilaian Tingkat Kesehatan BPR, "
            "dicabut dan dinyatakan tidak berlaku.")
    by = {r.key: r for r in explicit_references(cat.conn, teks, "", [])}
    assert by["POJK|3|2022"].relasi == "dicabut_sebagian" and by["POJK|3|2022"].pasal_dicabut == ["12"]
    assert by["POJK|4|2015"].relasi == "dicabut"


# --- Asumsi status & definisi label yang disepakati (contoh dari mitra) -----------------------

def _relasi(teks, judul=""):
    from hero.harmonisasi.refs import relasi_teks
    return {r.key: r for r in relasi_teks(teks, judul)}


def test_mengubah_dibaca_dari_judul():
    by = _relasi("Pasal I ...", "POJK Nomor 5 Tahun 2025 tentang Perubahan atas Peraturan Otoritas Jasa "
                 "Keuangan Nomor 12 Tahun 2021 tentang Pelaporan")
    assert by["POJK|12|2021"].relasi == "diubah" and by["POJK|12|2021"].dasar == "judul"


def test_mencabut_dibaca_dari_pasal_penutup():
    by = _relasi("Pada saat Peraturan Otoritas Jasa Keuangan ini mulai berlaku, Peraturan Otoritas Jasa "
                 "Keuangan Nomor 12 Tahun 2021 tentang Pelaporan dicabut dan dinyatakan tidak berlaku.")
    assert by["POJK|12|2021"].relasi == "dicabut" and by["POJK|12|2021"].dasar == "pasal penutup"


def test_mencabut_sebagian_menyebut_pasal():
    by = _relasi("Pada saat Surat Edaran ini mulai berlaku, Pasal 15 dan Pasal 16 Surat Edaran Otoritas "
                 "Jasa Keuangan Nomor 3/SEOJK.03/2020 dicabut dan dinyatakan tidak berlaku.")
    (r,) = by.values()
    assert r.relasi == "dicabut_sebagian" and r.pasal_dicabut == ["15", "16"]


def test_mencabut_sebagian_menyebut_butir_dan_lampiran():
    by = _relasi("Pada saat Surat Edaran ini mulai berlaku, angka 1 sampai dengan angka 5 dan Lampiran V "
                 "Surat Edaran Otoritas Jasa Keuangan Nomor 20/SEOJK.07/2024 tentang Perdagangan Aset "
                 "dicabut dan dinyatakan tidak berlaku.")
    (r,) = by.values()
    assert r.relasi == "dicabut_sebagian" and "Lampiran V" in r.bagian_dicabut and r.pasal_dicabut == []


def test_mencabut_dengan_kecuali_adalah_sebagian_dan_yang_dikecualikan_tetap_berlaku(tmp_path):
    teks = ("Pada saat Peraturan Otoritas Jasa Keuangan ini mulai berlaku, Peraturan Otoritas Jasa "
            "Keuangan Nomor 14 Tahun 2023 tentang Perdagangan Karbon dicabut dan dinyatakan tidak "
            "berlaku, kecuali Pasal 4.")
    (r,) = _relasi(teks).values()
    assert r.relasi == "dicabut_sebagian" and r.pengecualian == ["4"]
    cat = _korpus_relasi(tmp_path)
    rep = harmonise(cat.conn, DraftDoc("Rancangan POJK tentang Bursa Karbon", None, teks, [PASAL_3_BARU]), CFG)
    (d,) = rep.dampak_status
    assert d["pasal_tetap_berlaku"] == ["4"] and d["pasal_tidak_berlaku"] == ["3", "5"]
    assert "dikecualikan" in d["penjelasan"]


def test_rujukan_diri_tidak_mengacaukan_jenis_peraturan_yang_dicabut():
    by = _relasi("Pada saat Peraturan Otoritas Jasa Keuangan ini mulai berlaku, Surat Edaran Bank "
                 "Indonesia Nomor 9/30/DPNP tanggal 12 Desember 2007 dicabut dan dinyatakan tidak berlaku.")
    assert all(not k.startswith("POJK|") for k in by), by.keys()


def test_menggantikan_bila_draft_mencabut_pembandingnya_bukan_konflik():
    lama = "Bank wajib menyampaikan laporan kepada Otoritas Jasa Keuangan paling lambat 30 (tiga puluh) hari."
    baru = "Bank wajib menyampaikan laporan kepada Otoritas Jasa Keuangan paling lambat 15 (lima belas) hari."
    label, _, why, diffs = classify(baru, _art(lama), 0.9, True, CFG)
    assert label == "menggantikan" and "bukan konflik" in why and diffs


def test_kontradiktif_dibandingkan_ayat_lawan_ayat():
    lama = ("(1) Bank wajib menyusun laporan pelaksanaan tata kelola setiap tahun. "
            "(2) Laporan sebagaimana dimaksud pada ayat (1) wajib disampaikan kepada Otoritas Jasa "
            "Keuangan paling lambat 30 (tiga puluh) hari setelah tahun buku berakhir.")
    draft = ("(1) Bank wajib menyusun laporan pelaksanaan tata kelola setiap tahun paling lambat 7 (tujuh) "
             "hari setelah rapat direksi. (2) Laporan sebagaimana dimaksud pada ayat (1) wajib disampaikan "
             "kepada Otoritas Jasa Keuangan paling lambat 15 (lima belas) hari setelah tahun buku berakhir.")
    label, _, why, diffs = classify(draft, _art(lama), 0.8, False, CFG)
    assert label == "konflik" and "kontradiktif" in why
    assert "ayat (2) ↔ ayat (2) — hari: 30 → 15" in diffs
    assert not any("7" in d for d in diffs), "angka ayat lain tidak boleh dibandingkan silang"


def test_tumpang_tindih_beda_redaksi_substansi_sama():
    lama = ("Direksi wajib menyusun kebijakan manajemen risiko teknologi informasi yang memuat identifikasi, "
            "pengukuran, pengendalian, dan pemantauan risiko.")
    draft = ("Kebijakan pengelolaan risiko atas penggunaan teknologi informasi yang mencakup proses "
             "mengenali, mengukur, mengendalikan, serta memantau risiko wajib disusun oleh Direksi.")
    label, _, why, _ = classify(draft, _art(lama), 0.6, False, CFG, semantik=0.93)
    assert label == "duplikasi" and "tumpang tindih" in why and "makna" in why
    # tanpa sinyal makna yang kuat, redaksi berbeda ini dibaca melengkapi, bukan tumpang tindih
    assert classify(draft, _art(lama), 0.6, False, CFG, semantik=0.5)[0] == "memperjelas"


def test_selaras_melengkapi_topik_sama_tidak_bertentangan_tidak_mengulang():
    lama = "Bank wajib melaporkan insiden siber kepada Otoritas Jasa Keuangan."
    draft = ("Laporan insiden siber kepada Otoritas Jasa Keuangan disampaikan melalui aplikasi pelaporan "
             "daring dengan format sebagaimana tercantum dalam Lampiran.")
    label, _, why, _ = classify(draft, _art(lama), 0.55, False, CFG, semantik=0.7)
    assert label == "memperjelas" and "selaras/melengkapi" in why


def test_pencabutan_sebagian_hanya_pasal_yang_dicabut_menjadi_penggantian(tmp_path):
    cat = _korpus_relasi(tmp_path)
    teks = ("Pada saat Peraturan OJK ini mulai berlaku, Ketentuan Pasal 4 Peraturan Otoritas Jasa "
            "Keuangan Nomor 14 Tahun 2023 tentang Perdagangan Karbon dicabut dan dinyatakan tidak berlaku.")
    rep = harmonise(cat.conn, DraftDoc("Rancangan POJK tentang Registri", None, teks, [PASAL_3_BARU]), CFG)
    (f,) = rep.temuan
    # Pasal 3 induk TIDAK ikut dicabut → tetap berlaku → beda batas waktu = kontradiktif
    assert f.pembanding["pasal"] == "3" and f.jenis == "konflik"


def test_label_tampilan_memakai_istilah_mitra():
    from hero.harmonisasi.engine import LABEL_TEXT
    assert LABEL_TEXT["konflik"] == "Kontradiktif" and LABEL_TEXT["duplikasi"] == "Tumpang Tindih"
    assert LABEL_TEXT["memperjelas"] == "Selaras / Melengkapi"


def test_pihak_dibaca_dari_perihal_dengan_akronim_dan_payung():
    from hero.harmonisasi.engine import pihak_diatur, pihak_sama
    assert pihak_diatur("POJK tentang Perubahan atas POJK Nomor 4 Tahun 2014 tentang Perusahaan "
                        "Pembiayaan Sekunder Perumahan") == {"PPSP"}
    assert pihak_sama({"GADAI"}, {"PEMBIAYAAN"}) is False
    assert pihak_sama({"LJK"}, {"GADAI"}) is True                  # payung berlaku bagi semua
    assert pihak_sama({"LJKNB"}, {"ASURANSI"}) is True
    assert pihak_sama(set(), {"BANK"}) is None                     # tak terbaca → tidak menghukum


def test_ketentuan_templat_untuk_pihak_lain_bukan_konflik():
    pergadaian = CorpusArticle("g", "POJK|39|2024", "Pergadaian", "39 Tahun 2024", "berlaku", "17", 5,
                               "Perusahaan Pergadaian yang telah memperoleh izin konversi wajib "
                               "melaksanakan RUPS paling lambat 60 (enam puluh) hari kerja.")
    draft = ("Perusahaan Pembiayaan yang telah memperoleh izin konversi wajib melaksanakan RUPS paling "
             "lambat 30 (tiga puluh) hari kerja.")
    tanpa_gerbang = classify(draft, pergadaian, 0.8, False, CFG)[0]
    label, _, why, _ = classify(draft, pergadaian, 0.8, False, CFG, pihak_draft={"PEMBIAYAAN"})
    assert tanpa_gerbang == "konflik" and label == "pasal_baru" and "pihak lain" in why


def test_persentase_dengan_tanda_persen_terbaca():
    a = "Perusahaan wajib memiliki rasio Ekuitas terhadap Modal Disetor paling rendah 50% (lima puluh persen)."
    assert provision_diff(a, a.replace("50% (lima puluh", "40% (empat puluh")) == ["persen: 50 → 40"]


def test_tidak_wajib_adalah_kebolehan():
    assert provision_diff("Bank wajib memperoleh persetujuan.", "Bank tidak wajib memperoleh persetujuan.") \
        == ["kewajiban menjadi kebolehan"]


def test_satu_angka_berubah_adalah_kontradiksi_bukan_tumpang_tindih():
    a = "Perusahaan wajib memenuhi Ekuitas paling sedikit Rp1.000.000.000,00 untuk lingkup kabupaten/kota."
    label = classify(a.replace("Rp1.000.000.000,00", "Rp2.000.000.000,00"), _art(a), 0.97, False, CFG)[0]
    assert label == "konflik"


def test_uji_makna_sintetis_terbaca_dan_tidak_berubah_diam_diam():
    """Set parafrase (#67) ikut repo; nilai ketepatannya diukur di docs/HARMONISASI_SEMANTIK.md."""
    from pathlib import Path

    import yaml
    data = yaml.safe_load((Path(__file__).parent / "fixtures" / "uji_makna.yaml").read_text())["butir"]
    assert len(data) == 15 and all({"asli", "parafrase", "melengkapi", "kontradiktif"} <= set(b) for b in data)
    # kontradiktif sintetis harus punya perbedaan yang dapat dikutip (angka atau modalitas)
    from hero.harmonisasi.engine import provision_diff_ayat
    tanpa_beda = [b["id"] for b in data if not provision_diff_ayat(b["asli"], b["kontradiktif"])]
    assert len(tanpa_beda) <= 1, tanpa_beda


def test_klausul_templat_tidak_disebut_tumpang_tindih_karena_makna_saja():
    from hero.harmonisasi.engine import klausul_templat
    lama = ("(1) Bank yang dinyatakan terlambat menyampaikan laporan KPMM dikenai sanksi administratif "
            "berupa denda Rp1.000.000,00 per hari.")
    draft = ("(1) Bank yang tidak memenuhi ketentuan pelaporan teknologi informasi dikenai sanksi "
             "administratif berupa teguran tertulis.")
    assert klausul_templat(draft)
    assert classify(draft, _art(lama), 0.7, False, CFG, semantik=0.95)[0] != "duplikasi"
