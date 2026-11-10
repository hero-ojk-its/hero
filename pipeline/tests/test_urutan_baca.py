"""Urutan baca halaman: tabel/bagan Lampiran yang digambar acak (temuan QA, KADK 8–10 Nov 2026)
tidak lagi bercampur, sementara prosa dan halaman dua kolom tetap persis seperti sebelumnya."""
from __future__ import annotations

import random

import pymupdf
import pytest

from hero.extract.pdf import extract_pdf, page_text, reflow_paragraphs, urutan_acak

BARIS = [("No", "Tahapan", "Penanggung Jawab"), ("1", "Deteksi insiden", "Tim Operasional"),
         ("2", "Analisis dan klasifikasi", "Tim Analisis"), ("3", "Penanganan dan pemulihan", "Tim Pemulihan"),
         ("4", "Pelaporan kepada pimpinan", "Ketua Tim"), ("5", "Evaluasi pascainsiden", "Seluruh Tim")]
HARAPAN = ["No | Tahapan | Penanggung Jawab", "1 | Deteksi insiden | Tim Operasional",
           "2 | Analisis dan klasifikasi | Tim Analisis", "3 | Penanganan dan pemulihan | Tim Pemulihan",
           "4 | Pelaporan kepada pimpinan | Ketua Tim", "5 | Evaluasi pascainsiden | Seluruh Tim"]


def _pdf(path, sel, judul="LAMPIRAN ALUR PENANGANAN INSIDEN SIBER"):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), judul, fontsize=11)
    for x, y, t in sel:
        page.insert_text((x, y), t, fontsize=10)
    doc.save(path)
    doc.close()
    return path


def _sel_tabel(acak):
    sel = [((50, 90, 330)[c], 100 + r * 30, t) for r, row in enumerate(BARIS) for c, t in enumerate(row)]
    if acak:
        random.Random(7).shuffle(sel)
    return sel


def _halaman(path):
    with pymupdf.open(path) as doc:
        return doc[0].get_text("text"), page_text(doc[0])


def test_tabel_yang_digambar_acak_dibaca_baris_demi_baris(tmp_path):
    pdf = _pdf(tmp_path / "acak.pdf", _sel_tabel(acak=True))
    lama, baru = _halaman(pdf)
    assert baru.splitlines()[1:] == HARAPAN
    assert baru.splitlines()[1:] != lama.splitlines()[1:]          # tanpa perbaikan urutannya memang bercampur


def test_tabel_yang_sudah_berurutan_tidak_disentuh(tmp_path):
    lama, baru = _halaman(_pdf(tmp_path / "rapi.pdf", _sel_tabel(acak=False)))
    assert baru == lama


def test_prosa_biasa_tidak_berubah(tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 545, 800), "Pasal 1\nBank wajib menerapkan manajemen risiko. " * 12, fontsize=10)
    doc.save(tmp_path / "p.pdf")
    doc.close()
    lama, baru = _halaman(tmp_path / "p.pdf")
    assert baru == lama


def test_dua_kolom_tidak_diinterleave(tmp_path):
    """Terjemahan Inggris OJK/BI: kolom kiri selesai dulu, baru kolom kanan (satu loncatan ke atas)."""
    sel = [(50, 100 + i * 14, f"kiri {i}") for i in range(12)] + [(320, 100 + i * 14, f"kanan {i}") for i in range(12)]
    lama, baru = _halaman(_pdf(tmp_path / "k.pdf", sel))
    assert baru == lama
    assert baru.index("kiri 11") < baru.index("kanan 0")


def test_deteksi_acak_butuh_banyak_loncatan():
    kotak = lambda ys: [(0, y, 10, y + 10, "x") for y in ys]            # noqa: E731
    assert not urutan_acak(kotak([10, 20, 30, 40, 50, 60, 70]))        # menurun terus
    assert not urutan_acak(kotak([10, 20, 30, 10, 20, 30, 40]))        # dua kolom: satu loncatan
    assert urutan_acak(kotak([90, 10, 70, 20, 60, 30, 80]))           # acak
    assert not urutan_acak(kotak([90, 10]))                            # terlalu sedikit untuk menilai


def test_reflow_tidak_menggabungkan_baris_tabel():
    teks = reflow_paragraphs("No | Tahapan\n1 | Deteksi insiden\n2 | Analisis")
    assert teks.splitlines() == ["No | Tahapan", "1 | Deteksi insiden", "2 | Analisis"]


def test_extract_pdf_ujung_ke_ujung(tmp_path):
    hasil = extract_pdf(_pdf(tmp_path / "acak.pdf", _sel_tabel(acak=True)))
    assert hasil.pages[0].text.splitlines()[1:] == HARAPAN
