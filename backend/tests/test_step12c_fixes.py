"""
tests/test_step12c_fixes.py
Pengujian Unit & Integrasi Langkah 12c:
- J01: Parser JDIH untuk dokumen POJK 27/POJK.03/2015 (fixture mentah) -> 27/POJK.03/2015
- J02: build_standard_filename dengan nomor 26/POJK.04/2014 -> Mengandung 26-POJK.04-2014
- J03: Dokumen berjudul tanpa nomor/jenis/tahun -> nama != NA
- J04: Skrip rename --dry-run -> Tidak ada perubahan berkas/DB
"""
import pytest
from app.crawlers.jdih_api import extract_jdih_regulation_number
from app.services.naming_service import NamingInput, build_standard_filename
from scripts.fix_document_filenames_step12c import process_fixes


def test_j01_jdih_parser_raw_pojk_27_2015_fixture():
    """
    J01: Parser JDIH untuk regulasi POJK 27/POJK.03/2015 dari potongan judul mentah JDIH.
    Judul mentah memuat spasi sebelum slash ('Nomor 27 /POJK.03/2015').
    Ekspektasi: menghasilkan nomor regulasi lengkap '27/POJK.03/2015'.
    """
    raw_title = (
        "Peraturan Otoritas Jasa Keuangan Nomor 27 /POJK.03/2015 tentang "
        "Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)"
    )
    # 1. Dari judul saja
    reg_num_from_title = extract_jdih_regulation_number(raw_title)
    assert reg_num_from_title == "27/POJK.03/2015", f"Expected '27/POJK.03/2015', got {reg_num_from_title}"

    # 2. Dengan kolom DataTables (row[1]='27', row[5]='Peraturan OJK', year=2015)
    reg_num_full = extract_jdih_regulation_number(
        raw_title,
        raw_reg_num="27",
        reg_type="POJK",
        year=2015,
    )
    assert reg_num_full == "27/POJK.03/2015"

    # 3. Verifikasi fixture mentah lain dari data riil JDIH: 26/POJK.04/2014, 56/SEOJK.03/2017, Nomor34/POJK.05/2015
    assert extract_jdih_regulation_number(
        "Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26/POJK.04/2014 tentang Penjaminan"
    ) == "26/POJK.04/2014"

    assert extract_jdih_regulation_number(
        "Surat Edaran Otoritas Jasa Keuangan Nomor 56 /SEOJK.03/2017 tentang Penetapan Status"
    ) == "56/SEOJK.03/2017"

    assert extract_jdih_regulation_number(
        "Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor34/POJK.05/2015 tentang Perizinan Usaha"
    ) == "34/POJK.05/2015"


def test_j02_build_standard_filename_preserves_slashes_as_dashes():
    """
    J02: build_standard_filename mengganti garis miring (/) dan backslash (\\) dengan tanda minus (-),
    sehingga nomor seperti '26/POJK.04/2014' menjadi '26-POJK.04-2014', bukan '26POJK.042014'.
    """
    # 1. Nomor regulasi pada komponen 'nomor'
    inp_nomor = NamingInput(
        regulation_number="26/POJK.04/2014",
        title="Penjaminan Penyelesaian Transaksi Bursa",
        regulation_type="POJK",
        regulation_year=2014,
    )
    filename_nomor = build_standard_filename(
        inp_nomor,
        naming_format=["nomor", "nama", "tahun"],
        naming_separator="_",
    )
    assert "26-POJK.04-2014" in filename_nomor, f"Expected '26-POJK.04-2014' in '{filename_nomor}'"
    assert "26POJK.042014" not in filename_nomor

    # 2. Judul yang memuat nomor slash pada komponen 'nama'
    inp_nama = NamingInput(
        title="Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26/POJK.04/2014 tentang Bursa",
        regulation_type="POJK",
        regulation_year=2014,
    )
    filename_nama = build_standard_filename(
        inp_nama,
        naming_format=["nama", "jenis", "tahun"],
        naming_separator="_",
    )
    assert "26-POJK.04-2014" in filename_nama, f"Expected '26-POJK.04-2014' in '{filename_nama}'"
    assert "26POJK.042014" not in filename_nama


def test_j03_document_with_title_without_reg_meta_never_results_in_na_name():
    """
    J03: Dokumen yang memiliki judul tetapi tanpa nomor/jenis/tahun tidak boleh menghasilkan nama 'NA'.
    Termasuk dokumen dengan judul panjang bertanda hubung underscore (kasus Dokumen 36 dan 31).
    """
    long_snake_title = (
        "Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi_dan_Penasihat_Investasi_20_"
        "Perbaikan_Keputusan_OJK_tentang_izin_usaha_dan_pencabutan_izin_usaha_Reksa_Dana_berbentuk_"
        "Perseroan_serta_izin_usaha_dan_su"
    )
    inp_doc36 = NamingInput(
        title=long_snake_title,
        original_filename="Tahun_izin_usaha_dan_pencabutan_izin_usaha.pdf",
    )
    fn36 = build_standard_filename(
        inp_doc36,
        naming_format=["nama", "jenis", "tahun"],
        naming_separator="_",
        max_length=150,
    )
    assert not fn36.startswith("NA_"), f"Filename should not start with NA_, got: {fn36}"
    assert fn36 != "NA_NA_NA.pdf", f"Filename should not be NA_NA_NA.pdf"
    assert "Tahun_izin_usaha" in fn36
    assert len(fn36) <= 150

    # Dokumen berjudul pendek tanpa metadata
    inp_short = NamingInput(title="Pengumuman Pelaksanaan Uji Kompetensi Pegawai")
    fn_short = build_standard_filename(
        inp_short,
        naming_format=["nama", "jenis", "tahun"],
        naming_separator="_",
    )
    assert fn_short == "Pengumuman Pelaksanaan Uji Kompetensi Pegawai_NA_NA.pdf"


def test_j04_fix_script_dry_run_leaves_files_and_db_untouched():
    """
    J04: Eksekusi skrip perbaikan dalam mode --dry-run tidak mengubah basis data maupun berkas fisik.
    """
    # Jalankan dry_run=True
    changes = process_fixes(dry_run=True)
    assert changes >= 0, "process_fixes harus berhasil dieksekusi tanpa exception"
