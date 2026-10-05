"""Uji benchmark penyimpanan vektor — tanpa Postgres, tanpa model yang diunduh.

Yang dijaga: perhitungan recall, pemilihan kueri, dan bahwa laporan tetap
terbaca (serta jujur) ketika sisi Postgres tidak terukur.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hero import bench_vector as bv


def test_recall_terhadap_acuan_exact():
    assert bv._recall([1, 2, 3], [1, 2, 3]) == 1.0
    assert bv._recall([1, 2, 9], [1, 2, 3]) == pytest.approx(2 / 3)
    assert bv._recall([], [1, 2]) == 0.0
    assert bv._recall([1], []) == 0.0, "tanpa acuan, recall tidak bisa diklaim"


def test_kueri_diambil_dari_berkas_evaluasi(tmp_path: Path):
    f = tmp_path / "eval.yaml"
    f.write_text("kata_kunci:\n  - q: keamanan siber\n    relevan: [siber]\n"
                 "parafrase:\n  - q: apa kewajiban bank soal laporan\n    relevan: [laporan]\n",
                 encoding="utf-8")
    assert bv._queries(f, ["cadangan"]) == ["keamanan siber", "apa kewajiban bank soal laporan"]
    assert bv._queries(tmp_path / "tidak-ada.yaml", ["cadangan"]) == ["cadangan"]


def _laporan_minimal(pgvector: dict) -> dict:
    return {
        "korpus": {"chunk": 100, "dokumen": 10},
        "model": {"metode": "lsa", "dim": 256, "nama": "lsa", "mode": "deterministik"},
        "kueri": {"jumlah": 4, "k": 10, "contoh": ["a"]},
        "sqlite": {"mesin": {"numpy (matriks di memori)": {
            "latensi": {"p50": 0.5, "p95": 0.6, "n": 10}, "recall": 1.0, "catatan": "exact"}},
            "ukuran_mb": 1.0, "rincian_mb": {"chunk": 0.5}},
        "mutu": {"kata_kunci": {"n": 4, "mrr10": 0.8, "hit1": 0.75}},
        "pgvector": pgvector,
        "penyimpanan": {"pdf_asli_mb": 1.0, "katalog_sqlite_mb": 2.0, "vektor_sqlite_mb": 1.0,
                        "vektor_postgres_mb": 0.0, "vektor_postgres_padded_mb": 0.0},
    }


def test_laporan_mengakui_postgres_tidak_terukur():
    md = bv.render(_laporan_minimal({"galat": "dilewati (--tanpa-pg)"}))
    assert "tidak diukur" in md
    assert "belum lengkap" in md, "laporan tanpa Postgres tidak boleh terbaca seolah lengkap"
    # Tidak boleh menyimpulkan apa pun tentang indeks yang tidak pernah diukur.
    assert "recall ≥ 0,95" not in md


def test_laporan_menyebut_indeks_tercepat_yang_recall_nya_aman():
    pgv = {
        "server": "PostgreSQL 15 + pgvector 0.5.0", "dimensi": 256, "baris": 100,
        "muat": {"baris": 100, "detik": 0.1}, "tabel_mb": 0.6,
        "indeks": {
            "tanpa indeks (exact)": {"bangun": {"detik_bangun": 0.0, "ukuran_mb": 0.0},
                                     "latensi": {"p50": 9.0, "p95": 9.5, "n": 10},
                                     "recall": 1.0, "rencana": "Seq Scan"},
            "HNSW m=16, ef_search=10": {"bangun": {"indeks": "hnsw", "parameter": {"m": 16},
                                                   "detik_bangun": 1.0, "ukuran_mb": 0.4},
                                        "latensi": {"p50": 1.0, "p95": 1.2, "n": 10},
                                        "recall": 0.80, "rencana": "Index Scan"},
            "HNSW m=16, ef_search=40": {"bangun": {"indeks": "hnsw", "parameter": {"m": 16},
                                                   "detik_bangun": 1.0, "ukuran_mb": 0.4},
                                        "latensi": {"p50": 1.4, "p95": 1.6, "n": 10},
                                        "recall": 0.97, "rencana": "Index Scan"},
        },
    }
    md = bv.render(_laporan_minimal(pgv))
    assert "ef_search=40" in md and "0.97" in md
    # ef_search=10 lebih cepat tapi recall-nya di bawah ambang → tidak direkomendasikan.
    assert "**HNSW m=16, ef_search=10**" not in md


def test_laporan_menjelaskan_harga_padding():
    pgv = {
        "server": "PostgreSQL 15", "dimensi": 1024, "baris": 100,
        "muat": {"baris": 100, "detik": 0.1}, "tabel_mb": 72.75,
        "indeks": {"tanpa indeks (exact)": {"bangun": {"detik_bangun": 0.0, "ukuran_mb": 0.0},
                                            "latensi": {"p50": 16.0, "p95": 17.0, "n": 10},
                                            "recall": 1.0, "rencana": "Seq Scan"}},
        "padding": {"dimensi": 1536, "tabel_mb": 108.31,
                    "latensi_exact": {"p50": 19.9, "p95": 22.9, "n": 10},
                    "recall_vs_native": 1.0},
    }
    rep = _laporan_minimal(pgv)
    rep["penyimpanan"]["vektor_postgres_mb"] = 72.75
    rep["penyimpanan"]["vektor_postgres_padded_mb"] = 108.31
    md = bv.render(rep)
    assert "Harga kolom 1536 dimensi" in md
    assert "+35.6 MB" in md
    assert "1.00" in md
