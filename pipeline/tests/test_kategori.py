"""US-24: aturan kategori dari YAML — diubah tanpa mengubah kode."""
import os
import sqlite3
from pathlib import Path

import pytest

from hero.kb.classify import RulesError, builtin_rules, classify, load_rules, parse_rules
from hero.kb.classify_eval import evaluate_jdih
from hero.models import RegulationMetadata

REPO_RULES = Path(__file__).resolve().parents[1] / "config" / "kategori.yaml"


def md(**kw):
    return RegulationMetadata(**kw)


def test_editing_the_yaml_changes_classification_without_code(tmp_path):
    f = tmp_path / "kategori.yaml"
    f.write_text("kategori:\n  - kode: perbankan\n    kata_kunci: [bank]\n")
    meta = md(subject="Penyelenggaraan Layanan Kopi Digital")
    assert classify(meta, rules=load_rules(f))[0] == "lain-lain"

    f.write_text("kategori:\n  - kode: perbankan\n    kata_kunci: [bank]\n"
                 "  - kode: kopi-digital\n    label: Kopi Digital\n    kata_kunci: [kopi digital]\n")
    st = f.stat()
    os.utime(f, (st.st_atime, st.st_mtime + 5))      # make the change visible to the mtime cache
    assert classify(meta, rules=load_rules(f)) == ("kopi-digital", ["kopi digital"])


def test_missing_rules_file_falls_back_to_builtin(tmp_path):
    rules = load_rules(tmp_path / "tidak-ada.yaml")
    assert rules.sumber == "bawaan" and "perbankan" in rules.codes()


@pytest.mark.parametrize("raw,fragment", [
    ({}, "kategori"),
    ({"kategori": [{"label": "x", "kata_kunci": ["a"]}]}, "kode"),
    ({"kategori": [{"kode": "a", "kata_kunci": []}]}, "kosong"),
    ({"kategori": [{"kode": "a", "kata_kunci": ["x"]}, {"kode": "a", "kata_kunci": ["y"]}]}, "dua kali"),
    ({"cocok": "fuzzy", "kategori": [{"kode": "a", "kata_kunci": ["x"]}]}, "cocok"),
    ({"kategori": [{"kode": "a", "kata_kunci": ["x"], "kode_nomor": [{"sejak": 2024}]}]}, "kode_nomor"),
])
def test_broken_rules_fail_loudly_with_a_reason(raw, fragment):
    with pytest.raises(RulesError, match=fragment):
        parse_rules(raw)


def test_word_matching_does_not_fire_inside_other_words():
    rules = parse_rules({"kategori": [{"kode": "pasar-modal", "kata_kunci": ["efek"]}]})
    assert classify(md(subject="Efektivitas Pengawasan"), rules=rules)[0] == "lain-lain"
    assert classify(md(subject="Perdagangan Efek"), rules=rules)[0] == "pasar-modal"
    legacy = builtin_rules()           # substring mode, the old behaviour
    assert classify(md(subject="Efektivitas Pengawasan"), rules=legacy)[0] == "pasar-modal"


def test_number_code_respects_its_validity_years():
    rules = parse_rules({"kategori": [
        {"kode": "konsumen", "kata_kunci": ["konsumen"], "kode_nomor": [{"kode": "07", "sampai": 2023}]},
        {"kode": "digital", "kata_kunci": ["kripto"], "kode_nomor": [{"kode": "7", "sejak": 2024}]},
    ]})
    assert classify(md(title="SEOJK Nomor 2/SEOJK.07/2014 tentang Pelayanan"), rules=rules)[0] == "konsumen"
    assert classify(md(title="SEOJK Nomor 2/SEOJK.07/2025 tentang Pelayanan"), rules=rules)[0] == "digital"


def test_issuer_preamble_does_not_decide_the_category():
    title = ("Peraturan Anggota Dewan Komisioner Otoritas Jasa Keuangan Nomor 45 Tahun 2025 "
             "tentang Laporan Bulanan Perusahaan Pembiayaan")
    assert classify(md(title=title), rules=load_rules(REPO_RULES))[0] == "iknb"


def test_repo_rules_file_is_valid_and_maps_jdih_sectors():
    rules = load_rules(REPO_RULES)
    assert rules.sumber.endswith("kategori.yaml")
    assert {"perbankan", "pasar-modal", "iknb"} <= set(rules.sektor_map().values())


def test_jdih_evaluation_scores_against_sector_labels():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE inventory (record_key TEXT, source TEXT, title TEXT, sektor TEXT)")
    conn.executemany("INSERT INTO inventory VALUES (?, 'jdih-ojk', ?, ?)", [
        ("a", "POJK Nomor 1 Tahun 2024 tentang Bank Perekonomian Rakyat", "Perbankan"),
        ("b", "POJK Nomor 2 Tahun 2024 tentang Reksa Dana", "Pasar Modal, Keuangan Derivatif, dan Bursa Karbon"),
        ("c", "POJK Nomor 3 Tahun 2024 tentang Perusahaan Asuransi", "Perasuransian, Penjaminan , dan Dana Pensiun"),
        ("d", "POJK Nomor 4 Tahun 2024 tentang Rencana Strategis", "Manajemen Strategis"),
    ])
    rep = evaluate_jdih(conn, load_rules(REPO_RULES))
    assert rep["dinilai"] == 3 and rep["akurasi"] == 1.0
    assert rep["dikeluarkan"] == {"Manajemen Strategis": 1}
