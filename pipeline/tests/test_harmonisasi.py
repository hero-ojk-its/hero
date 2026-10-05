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
