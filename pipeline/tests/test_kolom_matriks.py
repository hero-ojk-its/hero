"""Matriks tanggapan (Batang Tubuh | Penjelasan | Tanggapan) dibaca kolom demi kolom.

Temuan QA 15 Nov 2026 atas Agustus_02 (KP2KS) dan apr_01_in (RPOJK TI BPR/BPRS):
pasal tak terbaca sama sekali, nomor pasal tercetak ganda ("Pasal 41 Pasal 41")
karena dua kolom sama-sama menyebutnya, dan kalimat kolom Penjelasan menyelip di
tengah kalimat batang tubuh.
"""
from __future__ import annotations

import pymupdf
import pytest

from hero.extract.kolom import rencana_matriks
from hero.extract.pdf import extract_pdf
from hero.extract.structure import parse_structure

# (x kiri, lebar) tiap kolom, sesuai tata letak lanskap yang dipakai OJK.
KOLOM = [(40, 250), (300, 250), (560, 220)]
JUDUL = ["BATANG TUBUH", "PENJELASAN", "TANGGAPAN DAN USULAN PENYESUAIAN"]
# (batang tubuh, penjelasan) per baris tabel.
BARIS = [
    ("Pasal 1", "Pasal 1"),
    ("Dalam Peraturan ini yang dimaksud dengan BPR adalah bank konvensional.", "Cukup jelas."),
    ("Pasal 2", "Pasal 2"),
    ("(1) BPR wajib menyelenggarakan teknologi informasi secara andal.", "Ayat (1) Cukup jelas."),
    ("(2) BPR wajib melaporkan penyelenggaraan teknologi informasi kepada OJK.", "Cukup jelas."),
    ("Pasal 3", "Pasal 3"),
    ("Peraturan Otoritas Jasa Keuangan Nomor 75/POJK.03/2016 tentang Standar "
     "Penyelenggaraan Teknologi Informasi, dicabut dan dinyatakan tidak berlaku.", "Cukup jelas."),
]


def _tulis_matriks(path, baris=BARIS, halaman=3, garis=True):
    """PDF lanskap bergaris tabel: tiap halaman mengulang baris judulnya."""
    doc = pymupdf.open()
    for _ in range(halaman):
        page = doc.new_page(width=842, height=595)
        y = 88
        if garis:
            for x, _lebar in KOLOM:
                page.draw_line((x - 6, 40), (x - 6, 560))
            page.draw_line((KOLOM[-1][0] + KOLOM[-1][1], 40), (KOLOM[-1][0] + KOLOM[-1][1], 560))
            page.draw_line((34, 40), (786, 40))
            page.draw_line((34, 74), (786, 74))
        for (x, lebar), judul in zip(KOLOM, JUDUL):
            page.insert_textbox(pymupdf.Rect(x, 46, x + lebar, 72), judul, fontsize=9)
        for kiri, kanan in baris:
            tinggi = 18 + 11 * (len(kiri) // 40)
            page.insert_textbox(pymupdf.Rect(KOLOM[0][0], y, KOLOM[0][0] + KOLOM[0][1], y + tinggi + 20),
                                kiri, fontsize=9)
            page.insert_textbox(pymupdf.Rect(KOLOM[1][0], y, KOLOM[1][0] + KOLOM[1][1], y + tinggi + 20),
                                kanan, fontsize=9)
            if garis:
                page.draw_line((34, y + tinggi + 2), (786, y + tinggi + 2))
            y += tinggi + 8
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def matriks(tmp_path):
    return _tulis_matriks(tmp_path / "matriks.pdf")


def test_kolom_tanggapan_dikenali_dari_garis_tabel(matriks):
    with pymupdf.open(matriks) as doc:
        rencana = rencana_matriks(doc)
    assert rencana is not None
    assert rencana.peran[0] == "badan"
    assert rencana.peran[1] == "buang" and rencana.peran[2] == "buang"


def test_penjelasan_tidak_lagi_menyelip_di_kalimat_batang_tubuh(matriks):
    teks = extract_pdf(matriks).text
    assert "Cukup jelas." not in teks
    assert "BPR wajib menyelenggarakan teknologi informasi secara andal." in teks


def test_pasal_terbaca_dan_nomornya_tidak_kembar(matriks):
    struct = parse_structure(extract_pdf(matriks).pages)
    assert [a.number for a in struct.articles][:3] == ["1", "2", "3"]
    pasal2 = next(a for a in struct.articles if a.number == "2")
    assert not pasal2.text.startswith("Pasal 2")
    assert [n for n, _ in pasal2.ayat] == ["1", "2"]


def test_nama_peraturan_yang_dicabut_tetap_utuh(matriks):
    struct = parse_structure(extract_pdf(matriks).pages)
    pasal3 = next(a for a in struct.articles if a.number == "3")
    assert "75/POJK.03/2016" in pasal3.text
    assert "dicabut dan dinyatakan tidak berlaku" in pasal3.text


def test_judul_kolom_tidak_ikut_terbaca_sebagai_isi(matriks):
    teks = extract_pdf(matriks).text
    assert "TANGGAPAN DAN USULAN" not in teks
    assert "BATANG TUBUH PENJELASAN" not in teks


def test_tabel_tanpa_kolom_tanggapan_tidak_diubah(tmp_path):
    """Dokumen biasa — dan tabel yang tak menyebut kolom tanggapan — dibiarkan."""
    path = _tulis_matriks(tmp_path / "biasa.pdf", garis=False)
    with pymupdf.open(path) as doc:
        assert rencana_matriks(doc) is None


def test_tabel_satu_halaman_bukan_matriks(tmp_path):
    """Satu tabel formulir di lampiran tidak boleh membuang kolom se-dokumen."""
    doc = pymupdf.open()
    for i in range(6):
        page = doc.new_page(width=842, height=595)
        if i == 0:
            for x in (40, 300, 560, 780):
                page.draw_line((x, 40), (x, 560))
            page.draw_line((40, 40), (780, 40))
            page.draw_line((40, 74), (780, 74))
            for x, judul in zip((40, 300, 560), ("No", "Keterangan", "Permohonan")):
                page.insert_textbox(pymupdf.Rect(x + 4, 46, x + 250, 72), judul, fontsize=9)
        else:
            page.insert_text((60, 100), "Pasal %d" % i, fontsize=10)
    path = tmp_path / "formulir.pdf"
    doc.save(path)
    doc.close()
    with pymupdf.open(path) as d:
        assert rencana_matriks(d) is None
