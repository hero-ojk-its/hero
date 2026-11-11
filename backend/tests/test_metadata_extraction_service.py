"""
tests/test_metadata_extraction_service.py
Pengujian ekstraksi metadata otomatis dari teks dokumen regulasi dan draf perubahan:
1. Draf perubahan ("NOMOR ... TAHUN 2026 TENTANG PERUBAHAN ATAS ... NOMOR 69/POJK.05/2016 TENTANG ...")
   -> nomor None, tahun 2026, judul utuh.
2. POJK biasa ("NOMOR 11 TAHUN 2026 TENTANG ...") -> nomor "11 Tahun 2026", tahun 2026.
3. POJK bernomor slash ("NOMOR 12/POJK.03/2024 TENTANG ...") -> nomor "12/POJK.03/2024", tahun 2024.
4. Dokumen tanpa TENTANG -> perilaku fallback lama tetap berjalan.
5. Dokumen uji ("TATA KELOLA ... Nomor: SIM-01/2026 • Versi ...") -> judul berhenti sebelum "Nomor:".
"""
from app.services.metadata_extraction_service import (
    _detect_number,
    _detect_year,
    _detect_title,
    _detect_type,
    extract_metadata_from_text,
)


def test_draf_perubahan_nomor_placeholder_dan_tahun_draf():
    """
    Draf perubahan dengan 'NOMOR ... TAHUN 2026 TENTANG PERUBAHAN ATAS ... NOMOR 69/POJK.05/2016 TENTANG ...'
    -> nomor None (karena belum bernomor), tahun 2026 (tahun draf di kepala, bukan 2016),
       judul utuh memuat perubahan atas peraturan yang diubah.
    """
    text = (
        "RANCANGAN\n"
        "PERATURAN OJK\n"
        "NOMOR ... TAHUN 2026\n"
        "TENTANG\n"
        "PERUBAHAN ATAS PERATURAN OJK\n"
        "NOMOR 69/POJK.05/2016\n"
        "TENTANG\n"
        "PENYELENGGARAAN USAHA PERUSAHAAN ASURANSI, PERUSAHAAN ASURANSI SYARIAH, "
        "PERUSAHAAN REASURANSI, DAN PERUSAHAAN REASURANSI SYARIAH\n\n"
        "DENGAN RAHMAT TUHAN YANG MAHA ESA\n"
        "DEWAN KOMISIONER OTORITAS JASA KEUANGAN,"
    )

    # 1. Nomor harus None (tidak mengambil 69/POJK.05/2016 dari teks isi/peraturan yang diubah)
    assert _detect_number(text) is None

    # 2. Tahun harus 2026 (diambil dari 'TAHUN 2026' di kepala dokumen, bukan 2016)
    assert _detect_year(text) == 2026

    # 3. Judul utuh memuat seluruh frasa judul perubahan
    title = _detect_title(text)
    assert title is not None
    assert "Perubahan Atas Peraturan OJK Nomor 69/POJK.05/2016 Tentang" in title
    assert "Penyelenggaraan Usaha Perusahaan Asuransi" in title

    # 4. Melalui fungsi pembungkus extract_metadata_from_text
    meta = extract_metadata_from_text(text)
    assert meta["regulation_number"] is None
    assert meta["regulation_year"] == 2026
    assert meta["year"] == 2026
    assert meta["regulation_type"] == "POJK"
    assert "Perubahan Atas Peraturan OJK Nomor 69/POJK.05/2016 Tentang" in meta["title"]


def test_pojk_biasa_nomor_dan_tahun():
    """POJK biasa 'NOMOR 11 TAHUN 2026 TENTANG ...' -> nomor '11 Tahun 2026', tahun 2026."""
    text = (
        "PERATURAN OTORITAS JASA KEUANGAN\n"
        "NOMOR 11 TAHUN 2026\n"
        "TENTANG\n"
        "PENGAWASAN PERBANKAN DIGITAL\n\n"
        "DENGAN RAHMAT TUHAN YANG MAHA ESA"
    )

    assert _detect_number(text) == "11 Tahun 2026"
    assert _detect_year(text) == 2026
    assert _detect_title(text) == "Pengawasan Perbankan Digital"

    meta = extract_metadata_from_text(text)
    assert meta["regulation_number"] == "11 Tahun 2026"
    assert meta["regulation_year"] == 2026
    assert meta["year"] == 2026
    assert meta["title"] == "Pengawasan Perbankan Digital"


def test_pojk_nomor_slash():
    """POJK bernomor slash 'NOMOR 12/POJK.03/2024 TENTANG ...' -> nomor 12/POJK.03/2024, tahun 2024."""
    text = (
        "PERATURAN OTORITAS JASA KEUANGAN\n"
        "NOMOR 12/POJK.03/2024\n"
        "TENTANG\n"
        "PENERAPAN TATA KELOLA BAGI BANK UMUM\n\n"
        "DENGAN RAHMAT TUHAN YANG MAHA ESA"
    )

    assert _detect_number(text) == "12/POJK.03/2024"
    assert _detect_year(text) == 2024
    assert _detect_title(text) == "Penerapan Tata Kelola Bagi Bank Umum"

    meta = extract_metadata_from_text(text)
    assert meta["regulation_number"] == "12/POJK.03/2024"
    assert meta["regulation_year"] == 2024
    assert meta["year"] == 2024


def test_dokumen_tanpa_tentang_fallback_lama_tetap_berjalan():
    """Dokumen tanpa TENTANG -> perilaku fallback lama tetap berjalan (mencari nomor & tahun di body / filename)."""
    text = (
        "SURAT EDARAN OTORITAS JASA KEUANGAN\n"
        "NOMOR 05/SEOJK.03/2023\n\n"
        "Yth. Direksi Bank Umum di Tempat.\n"
        "Sehubungan dengan penyampaian laporan berkala..."
    )

    assert _detect_number(text) == "05/SEOJK.03/2023"
    assert _detect_year(text) == 2023
    assert _detect_type(text) == "SEOJK"

    # Fallback judul dari filename bila tidak ada TENTANG
    title = _detect_title(text, filename="SEOJK_05_Penyampaian_Laporan_Berkala.pdf")
    assert title == "Penyampaian Laporan Berkala"


def test_dokumen_uji_judul_berhenti_sebelum_nomor_titik_dua():
    """
    Dokumen uji 'TATA KELOLA ... Nomor: SIM-01/2026 • Versi ...'
    -> judul berhenti sebelum 'Nomor:', tidak menelan nomor dokumen simulasi dan butir keterangan.
    """
    text = (
        "PEDOMAN DOKUMEN\n"
        "TENTANG\n"
        "TATA KELOLA PENGELOLAAN DOKUMEN DIGITAL\n"
        "Nomor: SIM-01/2026\n"
        "• Versi pengujian aplikasi HERO\n"
        "• Bukan regulasi resmi\n"
        "Kata Kunci: tata kelola, arsip, digital"
    )

    title = _detect_title(text)
    assert title == "Tata Kelola Pengelolaan Dokumen Digital"


def test_variasi_placeholder_nomor_draf_menghasilkan_none():
    """Memastikan berbagai variasi penulisan placeholder nomor draf selalu menghasilkan None."""
    variations = [
        "NOMOR ... TAHUN 2026",
        "NOMOR … TAHUN 2026",
        "NOMOR ___ TAHUN 2026",
        "NOMOR - TAHUN 2026",
        "NOMOR xx TAHUN 2026",
        "NOMOR XX TAHUN 2026",
        "NOMOR TAHUN 2026",
    ]
    for var in variations:
        text = f"RANCANGAN PERATURAN OJK\n{var}\nTENTANG\nSTANDAR KEAMANAN INFORMASI\n"
        assert _detect_number(text) is None, f"Gagal pada variasi: {var}"
        assert _detect_year(text) == 2026, f"Gagal tahun pada variasi: {var}"


def test_nomor_terpotong_baris_berhasil_dideteksi():
    """Nomor yang terpotong baris (NOMOR\n...) tidak boleh dianggap placeholder dan harus terdeteksi dengan benar."""
    # 1. Kasus NOMOR\n11 TAHUN 2026
    text_tahun = (
        "PERATURAN OJK\n"
        "NOMOR\n"
        "11 TAHUN 2026\n"
        "TENTANG\n"
        "PENGAWASAN PERBANKAN\n"
    )
    assert _detect_number(text_tahun) == "11 Tahun 2026"
    assert _detect_year(text_tahun) == 2026

    # 2. Kasus NOMOR\n12/POJK.03/2024
    text_slash = (
        "PERATURAN OJK\n"
        "NOMOR\n"
        "12/POJK.03/2024\n"
        "TENTANG\n"
        "PENERAPAN TATA KELOLA\n"
    )
    assert _detect_number(text_slash) == "12/POJK.03/2024"
    assert _detect_year(text_slash) == 2024


def test_extracted_metadata_response_includes_regulation_year():
    """Memastikan skema ExtractedMetadataResponse memuat field regulation_year."""
    from app.schemas.ingest import ExtractedMetadataResponse

    data = {
        "title": "Peraturan Uji",
        "regulation_number": "11 Tahun 2026",
        "regulation_type": "POJK",
        "regulation_year": 2026,
        "bidang": "Perbankan",
        "release_date": None,
        "page_count": 1,
        "raw_preview": "...",
    }
    resp = ExtractedMetadataResponse(**data)
    assert resp.regulation_year == 2026
    assert resp.model_dump()["regulation_year"] == 2026


