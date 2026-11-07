"""Pasal / ayat / section parsing."""
from hero.extract.structure import (
    parse_structure, roman_to_int, structure_quality,
)
from hero.models import PageText


def pages(text: str) -> list[PageText]:
    return [PageText(number=1, text=text, source="text-layer")]


BODY = """BAB I
KETENTUAN UMUM

Pasal 1
Dalam Peraturan ini yang dimaksud dengan Pelapor adalah Pihak.

BAB II
KEWAJIBAN

Pasal 2
(1) Pelapor wajib menyampaikan Laporan Insidental.
(2) Laporan sebagaimana dimaksud pada ayat (1) disampaikan secara daring.
(3) Pelapor sebagaimana dimaksud pada ayat (1) dan ayat (2) meliputi bursa efek.

Pasal 3
Pelapor dilarang menyampaikan laporan yang tidak benar.

Ditetapkan di Jakarta

LAMPIRAN
Pasal 2
Cukup jelas.
"""


def test_body_articles_and_bab():
    struct = parse_structure(pages(BODY))
    assert [a.number for a in struct.articles] == ["1", "2", "3"]
    assert struct.articles[0].bab.startswith("BAB I")
    assert struct.articles[1].bab.startswith("BAB II")
    assert struct.has_structure


def test_attachment_articles_are_separated():
    struct = parse_structure(pages(BODY))
    # The "Pasal 2" under LAMPIRAN must not duplicate the body article.
    assert [a.number for a in struct.attachment_articles] == ["2"]
    assert structure_quality(struct)["duplicate_numbers"] == []


def test_ayat_sequence_ignores_cross_references():
    struct = parse_structure(pages(BODY))
    pasal2 = struct.articles[1]
    # Exactly three ayat: the "(1)"/"(2)" inside ayat (3) are references.
    assert [n for n, _ in pasal2.ayat] == ["1", "2", "3"]
    assert "bursa efek" in pasal2.ayat[2][1]


def test_seojk_roman_sections():
    text = """SURAT EDARAN OTORITAS JASA KEUANGAN

I. KETENTUAN UMUM
Dalam Surat Edaran ini yang dimaksud dengan Pelaku Usaha.

II. PUBLIKASI PENANGANAN PENGADUAN
Pelaku usaha wajib mempublikasikan prosedur.

III. KETENTUAN PENUTUP
Surat Edaran ini mulai berlaku pada tanggal ditetapkan.
"""
    struct = parse_structure(pages(text))
    assert [s["number"] for s in struct.sections] == ["I", "II", "III"]
    assert struct.has_structure


def test_out_of_sequence_section_stops_collection():
    # Lampiran forms restart their own numbering; they must not be collected.
    text = """I. LAPORAN PROFIL
isi.
II. LAPORAN KEUANGAN
isi.
I. PENDAPATAN
isi.
II. BEBAN
isi.
"""
    struct = parse_structure(pages(text))
    assert [s["number"] for s in struct.sections] == ["I", "II"]


def test_paragraf_judul_title_case_tidak_bocor_ke_ayat():
    """T5 (Fase 2): "Paragraf 2 Bidang Tugas ..." dicetak Title Case, bukan
    kapital semua seperti BAB — tanpa pengecekan tambahan, baris ini lolos
    dari deteksi judul dan nyangkut di akhir teks ayat sebelumnya."""
    text = """BAB I
KETENTUAN UMUM

Bagian Kesatu
Umum

Paragraf 1
Tugas Pengawasan

Pasal 1
(1) Otoritas melakukan pengawasan terhadap Bank.

Paragraf 2
Bidang Tugas Pengawasan Perbankan

Pasal 2
(1) Pengawasan dilakukan secara berkala.
"""
    struct = parse_structure(pages(text))
    assert [a.number for a in struct.articles] == ["1", "2"]
    assert "Paragraf" not in struct.articles[0].text
    assert "Bidang Tugas" not in struct.articles[0].ayat[0][1]
    assert struct.articles[1].paragraf == "Paragraf 2 Bidang Tugas Pengawasan Perbankan"


def test_prosa_berawal_bagian_tidak_disalah_baca_sebagai_judul():
    """Baris prosa yang (karena word-wrap PDF) kebetulan dimulai dengan
    "Bagian" tetap masuk teks ayat — bukan dianggap judul baru."""
    text = """BAB I
KETENTUAN UMUM

Pasal 1
(1) Pelapor wajib menyampaikan laporan sebagaimana diatur dalam
Bagian yang menjadi tanggung jawabnya, paling lambat 10 hari kerja.
"""
    struct = parse_structure(pages(text))
    assert "Bagian yang menjadi tanggung jawabnya" in struct.articles[0].text


def test_roman_to_int():
    assert roman_to_int("I") == 1
    assert roman_to_int("IV") == 4
    assert roman_to_int("VIII") == 8
    assert roman_to_int("XIV") == 14
    assert roman_to_int("Q") == 0


def test_empty_input():
    struct = parse_structure([])
    assert struct.articles == []
    assert not struct.has_structure
