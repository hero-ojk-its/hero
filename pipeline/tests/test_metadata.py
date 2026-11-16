"""Metadata extraction against the real opening formulas of OJK regulations."""
from datetime import date

from hero.extract.metadata import extract_metadata
from hero.extract.metadata import _extract_subject

POJK_HEAD = """SALINAN
PERATURAN OTORITAS JASA KEUANGAN
REPUBLIK INDONESIA
NOMOR 9 TAHUN 2026
TENTANG
PELAPORAN INSIDENTAL MELALUI SISTEM PELAPORAN OTORITAS JASA KEUANGAN
DI SEKTOR PASAR MODAL, KEUANGAN DERIVATIF, DAN BURSA KARBON

DENGAN RAHMAT TUHAN YANG MAHA ESA

Menimbang : bahwa untuk melaksanakan ketentuan Pasal 2 ayat (4)
Peraturan Otoritas Jasa Keuangan Nomor 17 Tahun 2020 tentang lain-lain
(Lembaran Negara Republik Indonesia Tahun 2020 Nomor 17/OJK);
Mengingat : Undang-Undang Nomor 21 Tahun 2011 tentang Otoritas Jasa Keuangan;

Ditetapkan di Jakarta
pada tanggal 15 Juni 2026
"""

PADK_HEAD = """SALINAN
PERATURAN ANGGOTA DEWAN KOMISIONER
OTORITAS JASA KEUANGAN
REPUBLIK INDONESIA
NOMOR 45/PADK.06/2025
TENTANG
LAPORAN BULANAN PERUSAHAAN PEMBIAYAAN DAN PERUSAHAAN
PEMBIAYAAN SYARIAH

DENGAN RAHMAT TUHAN YANG MAHA ESA
Menimbang : Surat Edaran Otoritas Jasa Keuangan Nomor 3/SEOJK.05/2016 tentang X
"""

SEOJK_HEAD = """Yth. Direksi, di tempat.
SALINAN
SURAT EDARAN OTORITAS JASA KEUANGAN
REPUBLIK INDONESIA
NOMOR 23/SEOJK.06/2025
TENTANG
PERUBAHAN ATAS SURAT EDARAN OTORITAS JASA KEUANGAN NOMOR 25/SEOJK.05/2019
TENTANG LAPORAN BULANAN PERUSAHAAN MODAL VENTURA
"""


def test_pojk_identity():
    md = extract_metadata(POJK_HEAD)
    assert md.doc_type == "POJK"
    # The Menimbang cites 17 Tahun 2020; the document's own number must win.
    assert md.number == "9 Tahun 2026"
    assert md.year == 2026
    assert md.issued_date == date(2026, 6, 15)
    assert md.issuing_body == "Otoritas Jasa Keuangan"
    assert md.subject.startswith("PELAPORAN INSIDENTAL")
    assert md.status == "unknown"       # tak ada tanggal mulai berlaku tertulis: tidak ditebak "berlaku"
    assert md.confidence >= 0.9


def test_padk_is_not_mistaken_for_pojk():
    md = extract_metadata(PADK_HEAD)
    assert md.doc_type == "PADK"
    assert md.number == "45/PADK.06/2025"
    assert md.year == 2025


def test_seojk_amendment_status():
    md = extract_metadata(SEOJK_HEAD)
    assert md.doc_type == "SEOJK"
    assert md.number == "23/SEOJK.06/2025"
    # "PERUBAHAN ATAS" in its own subject makes this an amendment.
    assert md.status == "diubah"


def test_legal_basis_is_collected():
    md = extract_metadata(POJK_HEAD)
    assert any("21 Tahun 2011" in b for b in md.legal_basis)


def test_empty_text_is_reported_not_raised():
    md = extract_metadata("")
    assert md.doc_type is None
    assert md.confidence == 0.0
    assert md.warnings


# -- subject must stop at an abstract/summary section ----------------------
def test_subject_stops_at_inline_abstrak_marker():
    """OJK publishes regulations with an abstract page; once the PDF columns
    are flattened the marker lands mid-line and used to be swallowed whole."""
    text = ("PERATURAN OJK\nTENTANG\nPENERAPAN TATA KELOLA BAGI BANK "
            "PEREKONOMIAN RAKYAT ABSTRAK : - POJK ini merupakan "
            "penyempurnaan atas 2 POJK sebelumnya dan seterusnya")
    subject = _extract_subject(text)
    assert subject == "PENERAPAN TATA KELOLA BAGI BANK PEREKONOMIAN RAKYAT"
    assert "ABSTRAK" not in subject


def test_subject_stops_at_abstrak_on_its_own_line():
    text = "TENTANG\nLAPORAN BULANAN PERUSAHAAN PEMBIAYAAN\nABSTRAK :\n- isi"
    assert _extract_subject(text) == "LAPORAN BULANAN PERUSAHAAN PEMBIAYAAN"


def test_subject_is_hard_capped():
    """A single very long line must not produce a 700-character 'title'."""
    text = "TENTANG\n" + " ".join(["KETENTUAN"] * 200)
    subject = _extract_subject(text)
    assert len(subject) <= 300


def test_identitas_dibaca_dari_amar_saat_teks_dibuka_preambul():
    """Dokumen matriks tanggapan tidak memuat halaman judul di kolom batang
    tubuhnya: teksnya langsung dibuka "Menimbang". Nomor pertama yang terbaca
    di situ milik peraturan yang dirujuk Mengingat — #2016 dan #2017 terbaca
    sebagai "UU Nomor 21 Tahun 2011" (temuan 16 Nov 2026)."""
    teks = (
        "Menimbang\n"
        "a. bahwa Otoritas Jasa Keuangan berfungsi menyelenggarakan sistem pengaturan;\n"
        "Mengingat\n"
        "1. Undang-Undang Nomor 21 Tahun 2011 tentang Otoritas Jasa Keuangan "
        "(Lembaran Negara Republik Indonesia Tahun 2011 Nomor 111);\n"
        "Menetapkan Memutuskan:\n"
        "PERATURAN DEWAN KOMISIONER OTORITAS\n"
        "JASA KEUANGAN TENTANG KOMITE\n"
        "PENGEMBANGAN DAN PENGUATAN KEUANGAN\n"
        "SYARIAH DI OTORITAS JASA KEUANGAN\n"
        "BAB I\nKETENTUAN UMUM\n"
        "Pasal 1\n"
        "Dalam Peraturan Dewan Komisioner ini yang dimaksud dengan OJK adalah lembaga negara.\n"
    )
    md = extract_metadata(teks)
    assert md.doc_type == "PDK"
    assert md.number is None                      # draf memang belum bernomor
    assert md.subject and "KOMITE PENGEMBANGAN" in md.subject
    assert "Undang-Undang" not in (md.subject or "")


def test_dokumen_berhalaman_judul_tidak_berubah():
    """Peraturan dengan halaman judul utuh tetap dibaca dari situ."""
    teks = (
        "SALINAN\nPERATURAN OTORITAS JASA KEUANGAN\nNOMOR 12/POJK.03/2021\n"
        "TENTANG\nKONSOLIDASI BANK UMUM\n"
        "DENGAN RAHMAT TUHAN YANG MAHA ESA\n"
        "Menimbang\na. bahwa perlu dilakukan konsolidasi;\n"
        "Mengingat\n1. Undang-Undang Nomor 21 Tahun 2011 tentang Otoritas Jasa Keuangan;\n"
        "Menetapkan: PERATURAN OTORITAS JASA KEUANGAN TENTANG KONSOLIDASI BANK UMUM\n"
    )
    md = extract_metadata(teks)
    assert md.doc_type == "POJK"
    assert md.number == "12/POJK.03/2021"
    assert md.subject and "KONSOLIDASI BANK UMUM" in md.subject
