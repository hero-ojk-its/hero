"""Regulation graph: identity, relation parsing, traversal semantics."""
from __future__ import annotations

import json
import sqlite3

import pytest

from hero.graph import query as gq
from hero.graph.build import build_graph, parse_riwayat, title_similarity
from hero.graph.identity import canonical_ref, ref_for_record


@pytest.mark.parametrize("text,key", [
    ("POJK Nomor 11/POJK.03 Tahun 2022 tentang Penyelenggaraan TI", "POJK|11|2022"),
    ("Peraturan Otoritas Jasa Keuangan Nomor 11/POJK.03/2022", "POJK|11|2022"),
    ("Peraturan Otoritas Jasa Keuangan Nomor 46 Tahun 2024", "POJK|46|2024"),
    ("UU Nomor 21 Tahun 2011 tentang Otoritas Jasa Keuangan", "UU|21|2011"),
    ("Pasal 33 Undang-Undang Dasar 1945", "UUD|1945|1945"),
    ("Surat Edaran Bank Indonesia Nomor 13/15/DPbS", "SEBI|13/15/DPBS|2011"),
    ("Keputusan Ketua Bapepam Nomor Kep-46/PM/1996", "BAPEPAM|KEP-46/PM|1996"),
    ("Peraturan Menteri Keuangan Nomor 1/PMK.010/2019", "PMK|1|2019"),
])
def test_canonical_identity(text, key):
    assert canonical_ref(text).key == key


def test_bank_indonesia_numbers_keep_their_series():
    """Regression for Temuan 4: reg_key collapses 42 different 2005 PBIs onto
    PBI|7|2005. The graph identity must keep 7/1 and 7/10 apart."""
    a = canonical_ref("Peraturan Bank Indonesia Nomor 7/1/PBI/2005")
    b = canonical_ref("Peraturan Bank Indonesia Nomor 7/10/PBI/2005")
    assert a.key == "PBI|7/1|2005" and b.key == "PBI|7/10|2005"


def test_source_typos_still_resolve():
    assert ref_for_record("POJK", "59/POJK/.04/2016", 2016).key == "POJK|59|2016"
    assert ref_for_record("SEOJK", "10.SEOJK.03/2014", 2014).key == "SEOJK|10|2014"
    assert ref_for_record("PADK", "PADK 9 Tahun 2026", 2026).key == "PADK|9|2026"
    assert ref_for_record("SEOJK", "5/SEOJK.05/014", 2014) is None   # unrecoverable: say so


def test_riwayat_directions_and_partial_revocations():
    rows = parse_riwayat(
        "Mencabut : 1. POJK Nomor 1 Tahun 2020 . Pasal Terkait - "
        "Dicabut : 1. POJK Nomor 9 Tahun 2025 . Pasal Terkait Pasal 44, Pasal 45 "
        "Diubah : 1. POJK Nomor 3 Tahun 2024")
    by = {(r[0], r[2]): r for r in rows}
    assert by[("MENCABUT", False)][3] is False            # full: "Pasal Terkait -"
    assert by[("MENCABUT", True)][3] is True               # names articles → partial
    assert ("MENGUBAH", True) in by


def test_title_similarity_ignores_boilerplate_and_translations():
    long = "Peraturan OJK Nomor 21/POJK.03/2014 tentang Kewajiban Penyediaan Modal Minimum Bank Umum Syariah"
    assert title_similarity(long, "Kewajiban Penyediaan Modal Minimum Bank Umum Syariah") == 1.0
    assert title_similarity(long, "Penerapan Pedoman Tata Kelola Perusahaan Terbuka") < 0.25
    assert title_similarity(long, "Financial Services Authority Regulation Number 21") == 1.0


def _catalog(tmp_path) -> sqlite3.Connection:
    from hero.kb.catalog import Catalog
    Catalog(tmp_path / "c.db").close()                 # create the real schema
    conn = sqlite3.connect(tmp_path / "c.db")
    conn.row_factory = sqlite3.Row

    def jdih(key, number, year, status, riwayat="", landasan=""):
        conn.execute(
            "INSERT INTO inventory (record_key, source, title, number, doc_type, year, status, "
            "fields_json, detail_url, listed_at) VALUES (?, 'jdih-ojk', ?, ?, 'POJK', ?, ?, ?, ?, 'x')",
            (key, f"POJK {number} tentang Contoh {key}", number, year, status,
             json.dumps({"Riwayat Peraturan": riwayat, "Landasan Hukum": landasan}), key))

    base = "1. UU Nomor 21 Tahun 2011 tentang Otoritas Jasa Keuangan"
    jdih("a", "1 Tahun 2015", 2015, "dicabut", landasan=base)
    jdih("b", "2 Tahun 2019", 2019, "berlaku", "Mencabut : 1. POJK Nomor 1 Tahun 2015 . Pasal Terkait -", base)
    jdih("c", "3 Tahun 2023", 2023, "berlaku", "Mencabut : 1. POJK Nomor 2 Tahun 2019 . Pasal Terkait Pasal 4",
         "1. POJK Nomor 2 Tahun 2019 tentang Contoh b")
    # A cycle: d and e cite each other as legal basis.
    jdih("d", "4 Tahun 2024", 2024, "berlaku", landasan="1. POJK Nomor 5 Tahun 2024 tentang x")
    jdih("e", "5 Tahun 2024", 2024, "berlaku", landasan="1. POJK Nomor 4 Tahun 2024 tentang x")
    conn.commit()
    return conn


def test_lineage_follows_only_full_revocations(tmp_path):
    conn = _catalog(tmp_path)
    build_graph(conn)
    old = gq.lineage(conn, "POJK|1|2015")
    assert [n["key"] for n in old["rantai_penggantian"]] == ["POJK|2|2019"]
    assert [n["key"] for n in old["berlaku_terkini"]] == ["POJK|2|2019"]
    mid = gq.lineage(conn, "POJK|2|2019")
    assert mid["sudah_diganti"] is False                 # only Pasal 4 was revoked
    assert [n["key"] for n in mid["perubahan"]] == ["POJK|3|2023"]


def test_impact_is_transitive_and_cycle_safe(tmp_path):
    conn = _catalog(tmp_path)
    build_graph(conn)
    hit = {n["key"]: n["kedalaman"] for n in gq.impact(conn, "UU|21|2011")}
    assert hit["POJK|2|2019"] == 1 and hit["POJK|3|2023"] == 2
    around = {n["key"] for n in gq.impact(conn, "POJK|4|2024", max_depth=6)}
    assert around == {"POJK|5|2024"}                     # terminates despite the cycle


def test_cited_but_unlisted_regulations_become_rujukan_nodes(tmp_path):
    conn = _catalog(tmp_path)
    rep = build_graph(conn)
    assert gq.get_node(conn, "UU|21|2011")["asal"] == "rujukan"
    assert rep.refs_unresolved == 0 and rep.nodes_register == 5


@pytest.mark.parametrize("text,key", [
    ("PADK Nomor 1 Tahun 2026 tentang Tata Cara", "PADK|1|2026"),
    ("PDK Nomor 3 Tahun 2021", "PDK|3|2021"),
    ("SEDK Nomor 19 Tahun 2015", "SEDK|19|2015"),
])
def test_dewan_komisioner_abbreviations(text, key):
    """Regression: only the long phrases were recognised, so JDIH Landasan
    entries written as "PADK Nomor 1 Tahun 2026" were dropped as unresolved."""
    assert canonical_ref(text).key == key
