"""
tests/test_naming_service.py
Pengujian unit untuk naming_service (Langkah 3).
"""
from datetime import date
from app.services.naming_service import (
    NamingInput,
    normalize_regulation_type,
    extract_year,
    build_standard_filename,
    is_metadata_sufficient,
)


def test_n01_mandatory_example():
    """N01: Contoh wajib §3.2 -> String persis sama."""
    inp = NamingInput(
        regulation_number="11/POJK.03/2022",
        title="Penyelenggaraan Teknologi Informasi oleh Bank Umum",
        regulation_type="POJK",
        release_date=date(2022, 7, 7),
    )
    result = build_standard_filename(
        inp,
        template="{nomor} {judul} {tahun}",
        wildcard="NA",
        max_length=150,
    )
    assert result == "11-POJK.03-2022 Penyelenggaraan Teknologi Informasi oleh Bank Umum 2022.pdf"


def test_n02_empty_metadata():
    """N02: Semua metadata kosong -> 'NA NA NA.pdf'."""
    inp = NamingInput(
        regulation_number=None,
        title=None,
        regulation_type=None,
        release_date=None,
    )
    result = build_standard_filename(
        inp,
        template="{nomor} {judul} {tahun}",
        wildcard="NA",
        max_length=150,
    )
    assert result == "NA NA NA.pdf"


def test_n03_year_from_regulation_number():
    """N03: Tahun dari nomor ('PADK 5/2019', tanpa tanggal) -> Mengandung 2019."""
    inp = NamingInput(
        regulation_number="PADK 5/2019",
        title="Tata Kelola Internal",
        regulation_type="PADK",
        release_date=None,
    )
    year = extract_year(inp)
    assert year == 2019

    result = build_standard_filename(
        inp,
        template="{nomor} {judul} {tahun}",
        wildcard="NA",
        max_length=150,
    )
    assert "2019" in result
    assert result == "PADK 5-2019 Tata Kelola Internal 2019.pdf"


def test_n04_title_exceeds_max_length():
    """N04: Judul 400 karakter -> Panjang <= 150, berakhiran .pdf, nomor & tahun utuh."""
    long_title = "Ketentuan dan Pedoman Operasional Mengenai Pelaksanaan Manajemen Risiko dan Tata Kelola Serta Transformasi Digital Perbankan Dalam Menghadapi Era Inovasi Keuangan dan Perlindungan Data Nasabah " * 5
    inp = NamingInput(
        regulation_number="12/POJK.03/2023",
        title=long_title,
        regulation_type="POJK",
        release_date=date(2023, 1, 1),
    )
    result = build_standard_filename(
        inp,
        template="{nomor} {judul} {tahun}",
        wildcard="NA",
        max_length=150,
    )
    assert len(result) <= 150
    assert result.endswith(".pdf")
    assert "12-POJK.03-2023" in result
    assert "2023.pdf" in result


def test_n05_illegal_characters_sanitized():
    """N05: Karakter ilegal di judul (: * ? \" < > |) terbuang."""
    inp = NamingInput(
        regulation_number="1/UU/2021",
        title='Peraturan: Tentang "Pasar Modal" <Edisi Baru> & Hal-Hal Terkait?',
        regulation_type="UU",
        release_date=date(2021, 5, 5),
    )
    result = build_standard_filename(
        inp,
        template="{nomor} {judul} {tahun}",
        wildcard="NA",
        max_length=150,
    )
    assert ":" not in result
    assert "*" not in result
    assert "?" not in result
    assert '"' not in result
    assert "<" not in result
    assert ">" not in result
    assert "|" not in result
    assert result.endswith(".pdf")


def test_n06_normalize_regulation_type():
    """N06: normalize_regulation_type('se ojk'), ('Undang-Undang') -> SEOJK, UU."""
    assert normalize_regulation_type("se ojk") == "SEOJK"
    assert normalize_regulation_type("SE OJK") == "SEOJK"
    assert normalize_regulation_type("Undang-Undang") == "UU"
    assert normalize_regulation_type("undang undang") == "UU"
    assert normalize_regulation_type("Peraturan Pemerintah") == "PP"
    assert normalize_regulation_type("PERMENKEU") == "PERMENKEU"
    assert normalize_regulation_type("peraturan dewan lain") == "PERATURAN DEWAN LAIN"
    assert normalize_regulation_type("") is None
    assert normalize_regulation_type(None) is None


def test_n07_is_metadata_sufficient():
    """N07: is_metadata_sufficient hanya judul -> False; ada nomor atau jenis+tanggal -> True."""
    # Hanya judul -> False
    assert not is_metadata_sufficient(
        NamingInput(
            regulation_number=None,
            title="Judul Dari Nama Asli File Sumber",
            regulation_type=None,
            release_date=None,
        )
    )

    # Ada nomor regulasi -> True
    assert is_metadata_sufficient(
        NamingInput(
            regulation_number="11/POJK.03/2022",
            title=None,
            regulation_type=None,
            release_date=None,
        )
    )

    # Ada jenis dan release_date -> True
    assert is_metadata_sufficient(
        NamingInput(
            regulation_number=None,
            title=None,
            regulation_type="POJK",
            release_date=date(2022, 7, 7),
        )
    )

    # Hanya jenis tanpa tanggal -> False
    assert not is_metadata_sufficient(
        NamingInput(
            regulation_number=None,
            title=None,
            regulation_type="POJK",
            release_date=None,
        )
    )
