"""Keputusan berdiktum (KESATU, KEDUA, …) — temuan QA 8–10 Nov 2026 pada KADK "Agustus_01_in.pdf":
0 pasal, ringkasan 55 kata, 2 poin, "Peraturan ini mencabut" untuk sebuah Keputusan, dasar hukum 2 dari 7.
Dokumen di bawah FIKTIF, hanya meniru bentuknya."""
from __future__ import annotations

import sqlite3

import pymupdf
import pytest

from hero.analysis import analyse_document
from hero.analysis.structured import classify_unit, is_diktum, jenis_kata, unit_ref
from hero.extract.metadata import _extract_legal_basis
from hero.extract.structure import parse_structure
from hero.harmonisasi.refs import _ref_penerbit
from hero.models import PageText
from hero.pipeline import IngestPipeline

TEKS = """KEPUTUSAN DEWAN KOMISIONER OTORITAS JASA KEUANGAN
NOMOR 12/KDK.02/2024
TENTANG
TIM PENANGANAN INSIDEN SIBER

DENGAN RAHMAT TUHAN YANG MAHA ESA
DEWAN KOMISIONER OTORITAS JASA KEUANGAN,

Menimbang : a. bahwa untuk menjaga keamanan sistem informasi perlu dibentuk tim penanganan insiden siber;
b. bahwa berdasarkan pertimbangan tersebut perlu menetapkan Keputusan;
Mengingat : 1. Undang-Undang Nomor 21 Tahun 2011 tentang Otoritas Jasa Keuangan;
2. Peraturan Badan Siber dan Sandi Negara Nomor 1 Tahun 2024 tentang Manajemen Krisis Siber;
3. Peraturan Dewan Komisioner Nomor 22/PDK.01/2014 tentang Tata Kelola;
4. Surat Edaran Dewan Komisioner Nomor 3/SEDK.02/2021 tentang Insiden;

MEMUTUSKAN:
Menetapkan : KEPUTUSAN DEWAN KOMISIONER TENTANG TIM PENANGANAN INSIDEN SIBER.
KESATU : Membentuk Tim Penanganan Insiden Siber di lingkungan Otoritas Jasa Keuangan yang selanjutnya disebut Tim.
KEDUA : Tim sebagaimana dimaksud dalam Diktum KESATU bertugas:
a. melakukan identifikasi dan klasifikasi insiden siber;
b. menyusun laporan hasil penanganan insiden siber.
KETIGA : Tim melaksanakan penanganan insiden siber sesuai dengan alur penanganan sebagaimana tercantum dalam Lampiran yang merupakan bagian tidak terpisahkan dari Keputusan ini.
KEEMPAT : Ruang lingkup penanganan meliputi seluruh sistem informasi yang dikelola oleh Otoritas Jasa Keuangan.
KELIMA : Segala biaya yang timbul akibat Keputusan ini dibebankan pada anggaran Otoritas Jasa Keuangan.
KEENAM : Pada saat Keputusan ini mulai berlaku, Keputusan Dewan Komisioner Nomor 5 Tahun 2020 tentang Tim Keamanan Informasi dicabut dan dinyatakan tidak berlaku.
KETUJUH : Keputusan ini mulai berlaku pada tanggal ditetapkan.
Ditetapkan di Jakarta
pada tanggal 5 Agustus 2024
KETUA DEWAN KOMISIONER,

LAMPIRAN
KEPUTUSAN DEWAN KOMISIONER
ALUR PENANGANAN INSIDEN SIBER
I. DETEKSI INSIDEN
II. ANALISIS INSIDEN
III. PEMULIHAN
"""


@pytest.fixture
def analisis(tmp_path, tmp_settings):
    pdf = tmp_path / "kep.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 555, 800), TEKS, fontsize=8)
    doc.save(pdf)
    doc.close()
    pipe = IngestPipeline(tmp_settings)
    try:
        assert pipe.run_upload([pdf]).ingested == 1
    finally:
        pipe.close()
    conn = sqlite3.connect(tmp_settings.catalog_db)
    conn.row_factory = sqlite3.Row
    return analyse_document(conn, conn.execute("SELECT doc_id FROM documents").fetchone()[0])


def test_diktum_dikenali_sebagai_unit_berurutan():
    st = parse_structure([PageText(number=1, text=TEKS, source="text-layer")])
    assert [a.number for a in st.articles] == ["KESATU", "KEDUA", "KETIGA", "KEEMPAT", "KELIMA", "KEENAM", "KETUJUH"]
    assert "bertugas" in st.articles[1].text and "Lampiran" in st.articles[2].text


def test_kata_kesatu_di_dokumen_berpasal_atau_tak_berurutan_bukan_diktum():
    berpasal = "Pasal 1\nKESATU : sesuatu yang bukan diktum karena dokumen ini berpasal.\nPasal 2\nisi dua."
    assert [a.number for a in parse_structure([PageText(number=1, text=berpasal, source="text-layer")]).articles] == ["1", "2"]
    loncat = "KEDUA : tidak boleh membuka unit karena KESATU belum ada.\nKESATU : ini unit pertama yang sah."
    assert [a.number for a in parse_structure([PageText(number=1, text=loncat, source="text-layer")]).articles] == ["KESATU"]


def test_ringkasan_keputusan_memuat_isi_bukan_hanya_pencabutan(analisis):
    a = analisis
    assert a.identitas["jumlah_diktum"] == 7 and a.identitas["jumlah_pasal"] == 0
    assert len(a.poin) >= 6 and len(a.ringkasan_teks().split()) > 100        # QA: 2 poin, 55 kata
    assert {"Tugas", "Pencabutan", "Masa Berlaku"} <= {p.kategori for p in a.poin}
    assert all(p.pasal.startswith("Diktum KE") for p in a.poin)
    assert {p.pasal for p in a.poin if p.kategori == "Tugas"} >= {"Diktum KESATU", "Diktum KEDUA"}


def test_kata_benda_mengikuti_jenis_dokumen(analisis):
    teks = analisis.ringkasan_teks()
    assert "Keputusan ini mencabut" in teks and "Keputusan ini memuat 7 diktum" in teks
    assert "Peraturan ini" not in teks
    assert [jenis_kata({"jenis": j}) for j in ("KEPDK", "SEOJK", "UU", "POJK", None)] == \
        ["Keputusan", "Surat Edaran", "Undang-Undang", "Peraturan", "Peraturan"]


def test_lampiran_keputusan_dianggap_berat_walau_diktumnya_lebih_dari_enam(analisis):
    assert analisis.lampiran["berat_lampiran"] is True
    assert "DETEKSI INSIDEN" in " ".join(analisis.lampiran["judul_bagian"])


def test_membentuk_tim_bukan_definisi():
    assert classify_unit("Membentuk Tim Penanganan Insiden Siber yang selanjutnya disebut Tim.")[0] == "Tugas"
    assert classify_unit("Tim yang selanjutnya disebut Tim adalah kelompok kerja.") is None


def test_rujukan_unit():
    assert (unit_ref("4", 2), unit_ref("KESATU"), unit_ref("II")) == ("Pasal 4 ayat (2)", "Diktum KESATU", "Bagian II")
    assert is_diktum("KEDUA") and not is_diktum("KEMENTERIAN") and not is_diktum("2")


def test_dasar_hukum_terbaca_untuk_semua_penerbit_dan_tanpa_judul_sendiri():
    dasar = _extract_legal_basis(TEKS, number="12/KDK.02/2024", year=2024)
    assert dasar == ["Undang-Undang Nomor 21 Tahun 2011",
                     "Peraturan Badan Siber dan Sandi Negara Nomor 1 Tahun 2024",
                     "Peraturan Dewan Komisioner Nomor 22/PDK.01/2014",
                     "Surat Edaran Dewan Komisioner Nomor 3/SEDK.02/2021"]
    judul = "PERATURAN OTORITAS JASA KEUANGAN\nNOMOR 91 TAHUN 2026\nTENTANG X"
    assert _extract_legal_basis(judul, number="91", year=2026) == []
    assert _extract_legal_basis(judul, number="92", year=2026) != []         # nomor lain tetap dasar hukum


def test_rujukan_penerbit_tak_dikenal_tidak_dibuang():
    r = _ref_penerbit("Peraturan Badan Siber dan Sandi Negara Nomor 1 Tahun 2024")
    assert (r.key, r.jenis, r.tahun) == ("BSSN|1|2024", "BSSN", 2024)
    assert _ref_penerbit("Peraturan ini Nomor 3") is None


def test_judul_sendiri_dengan_nomor_polos_bukan_dasar_hukum():
    judul = "KEPUTUSAN MENTERI KEUANGAN REPUBLIK INDONESIA NOMOR 512 /KMK.06/2002 TENTANG X"
    assert _extract_legal_basis("KEPUTUSAN MENTERI KEUANGAN REPUBLIK INDONESIA NOMOR 512 TENTANG X",
                                number="512/KMK.06/2002", year=2002) == []
    assert _extract_legal_basis("Keputusan Menteri Keuangan Nomor 40/KMK.017/1997 tentang Y",
                                number="512/KMK.06/2002", year=2002) == ["Keputusan Menteri Keuangan Nomor 40/KMK.017/1997"]
