"""Draft Tanggapan berbasis PoV (URD 3.5): pasal berdampak, checklist, narasi, susunan surat."""
from __future__ import annotations

import pytest

from hero.tanggapan.pov import load_profiles, nilai_pasal, pilih_profil, susun_tanggapan

PROFIL = pilih_profil(load_profiles(None))

ARTS = [
    {"number": "1", "page": 1, "text": "Dalam Peraturan OJK ini yang dimaksud dengan Bank adalah bank umum."},
    {"number": "5", "page": 3, "text": "(1) Bank wajib menerapkan manajemen risiko teknologi informasi secara "
     "efektif. (2) Bank wajib menyampaikan laporan insiden siber kepada Otoritas Jasa Keuangan paling "
     "lambat 1 (satu) hari kerja setelah insiden diketahui."},
    {"number": "9", "page": 5, "text": "Bank dilarang menempatkan sistem elektronik pada pusat data di luar "
     "wilayah Indonesia, kecuali memperoleh persetujuan Otoritas Jasa Keuangan."},
    {"number": "12", "page": 7, "text": "Direksi wajib menyelenggarakan rapat umum pemegang saham tahunan "
     "paling lambat 6 (enam) bulan setelah tahun buku berakhir."},
]
HARMONISASI = {"temuan": [{"pasal_draft": "Pasal 5", "jenis": "konflik", "alasan": "kontradiktif …",
                           "perbedaan": ["ayat (2) ↔ ayat (1) — hari: 3 → 1"],
                           "pembanding": {"key": "POJK|11|2022", "pasal": "23",
                                          "judul": "Penyelenggaraan Teknologi Informasi oleh Bank Umum"}}]}


def test_profil_dari_konfigurasi_dan_siap_banyak_profil():
    profiles = load_profiles(None)
    assert "unit_bisnis_it" in profiles and PROFIL.topik
    with pytest.raises(KeyError):
        pilih_profil(profiles, "unit_tidak_ada")


def test_kata_kunci_utuh_dan_skor_per_topik_bukan_per_kemunculan():
    skor, kena = nilai_pasal("Sistem elektronik, sistem elektronik, dan sistem elektronik.", PROFIL)
    assert skor == 3 and len(kena) == 1
    assert nilai_pasal("Bank wajib membuka jaringan kantor cabang.", PROFIL)[0] <= 2
    assert nilai_pasal("Subsiberan adalah kata karangan.", PROFIL)[0] == 0


def test_pasal_berdampak_beralasan_dan_pasal_umum_tidak():
    r = susun_tanggapan("Rancangan POJK tentang Keamanan Siber Bank Umum", ARTS, PROFIL, HARMONISASI)
    by = {p.pasal: p for p in r.pasal_berdampak}
    assert "Pasal 12" not in by and "Pasal 1" not in by          # RUPS & definisi: bukan lingkup IT
    assert by["Pasal 5"].tingkat == "tinggi" and "keamanan siber" in by["Pasal 5"].alasan
    assert by["Pasal 9"].topik and by["Pasal 9"].topik[0].bukti   # kutipan tempat kata kunci ditemukan


def test_checklist_menandai_pasal_wajib_yang_belum_ditanggapi():
    r = susun_tanggapan("Rancangan POJK", ARTS, PROFIL, HARMONISASI, sudah={"Pasal 9": "Kami sependapat."})
    k = r.kelengkapan
    assert k["wajib"] == 2 and k["sudah"] == 1 and k["pasal_belum"] == ["Pasal 5"] and not k["lengkap"]
    assert "1 dari 2 pasal wajib belum ditanggapi" in k["keterangan"]
    # tanggapan kosong/tanda baca saja tidak dihitung
    assert susun_tanggapan("x", ARTS, PROFIL, sudah={"5": " - ", "9": "ok sudah"}).kelengkapan["belum"] == 1


def test_narasi_menunjuk_ayat_temuan_harmonisasi_dan_usulan():
    r = susun_tanggapan("Rancangan POJK", ARTS, PROFIL, HARMONISASI)
    p5 = next(p for p in r.pasal_berdampak if p.pasal == "Pasal 5")
    assert p5.narasi.startswith("Pasal 5 ayat (2) mengatur bahwa Bank wajib menyampaikan laporan insiden siber")
    assert "berbeda dengan Pasal 23 POJK Nomor 11 Tahun 2022" in p5.narasi and "hari: 3 → 1" in p5.narasi
    assert p5.usulan.startswith("Kami mengusulkan agar ketentuan ini diselaraskan")
    assert any(d.startswith("harmonisasi: Kontradiktif") for d in p5.dasar)


def test_susunan_surat_mengikuti_kop_weekly_10():
    s = susun_tanggapan("Rancangan POJK tentang Keamanan Siber Bank Umum", ARTS, PROFIL, HARMONISASI).surat
    assert (s["kepada"], s["dari"], s["tanggal"]) == ("Kepala Departemen", "Analis Eksekutif", "(diisi manual)")
    assert s["hal"] == "Tanggapan atas Rancangan POJK tentang Keamanan Siber Bank Umum"
    pokok = s["butir"][1]
    assert pokok["judul"] == "Pokok Tanggapan" and [x["pasal"] for x in pokok["pasal"]] == ["Pasal 5", "Pasal 9"]


def test_endpoint_profil_tersedia_di_layanan_analisa(tmp_settings):
    from fastapi.testclient import TestClient

    from hero.bridge.config import BridgeSettings
    from hero.bridge.ml_api import create_app

    client = TestClient(create_app(tmp_settings, BridgeSettings(embedder="none")))
    res = client.get("/tanggapan/profil")
    assert res.status_code == 200
    assert res.json()["profil"][0]["id"] == "unit_bisnis_it"
    assert client.post("/tanggapan/1?profil=tidak_ada").status_code == 404


def test_definisi_berdampak_tetapi_tidak_wajib_dan_usulan_tidak_berulang():
    arts = [{"number": "1", "page": 1, "text": "Dalam Peraturan OJK ini yang dimaksud dengan: 1. Sistem "
             "Elektronik adalah serangkaian perangkat dan prosedur elektronik. 2. Bank adalah bank umum."},
            {"number": "4", "page": 2, "text": "Bank wajib menyediakan sistem elektronik yang andal."}]
    h = {"temuan": [{"pasal_draft": "Pasal 4", "jenis": "menggantikan", "perbedaan": [],
                     "pembanding": {"key": "POJK|1|2020", "pasal": "4", "judul": "x"}}]}
    r = susun_tanggapan("Rancangan POJK", arts, PROFIL, h)
    by = {p.pasal: p for p in r.pasal_berdampak}
    assert by["Pasal 1"].definisi and not by["Pasal 1"].wajib and "definisi istilah" in by["Pasal 1"].narasi
    assert "peralihan" not in by["Pasal 4"].usulan     # menggantikan tanpa perbedaan konkret


def test_cli_terdaftar():
    from typer.testing import CliRunner

    from hero.cli import app
    res = CliRunner().invoke(app, ["tanggapan", "susun", "--help"])
    assert res.exit_code == 0 and "PoV" in res.output


def test_judul_berulang_dan_kapital_dirapikan_untuk_hal_surat():
    from hero.tanggapan.pov import rapikan_judul
    j = ("Peraturan Otoritas Jasa Keuangan Nomor 23 Tahun 2025 tentang PERUBAHAN ATAS PERATURAN OTORITAS "
         "JASA KEUANGAN NOMOR 27 TAHUN 2024 TENTANG ASET KRIPTO PERUBAHAN ATAS PERATURAN OTORITAS JASA "
         "KEUANGAN NOMOR 27 TAHUN 2024 TENTANG ASET KRIPTO")
    assert rapikan_judul(j) == ("Peraturan Otoritas Jasa Keuangan Nomor 23 Tahun 2025 tentang Perubahan atas "
                                "Peraturan Otoritas Jasa Keuangan Nomor 27 Tahun 2024 tentang Aset Kripto")
    assert rapikan_judul("Rancangan POJK tentang Keamanan Siber") == "Rancangan POJK tentang Keamanan Siber"
