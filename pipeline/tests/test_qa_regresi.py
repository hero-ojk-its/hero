"""Regresi temuan QA 8 Nov 2026 pada dokumen berpasal (#106, #89).

Dokumen di bawah FIKTIF, meniru bentuk Pasal 4 POJK #106: ayat (1) teguran tertulis, ayat (2)
daftar huruf a–e. Temuan aslinya: daftar itu tidak pernah muncul sebagai poin utama, label
sanksinya "teguran/peringatan tertulis" padahal PDF hanya menulis "teguran tertulis", dan
rujukan kalimat sanksi melewatkan ayat (2)."""
from __future__ import annotations

import sqlite3

import pymupdf
import pytest

from hero.analysis import analyse_document
from hero.analysis.ai import periksa_modalitas, verify
from hero.analysis.structured import _clause, compose_summary, sanctions
from hero.extract.pdf import clean_text
from hero.pipeline import IngestPipeline

TEKS = """SALINAN
PERATURAN OTORITAS JASA KEUANGAN
REPUBLIK INDONESIA
NOMOR 4 TAHUN 2026
TENTANG
PENYELENGGARAAN PRODUK INVESTASI PERBANKAN SYARIAH

Mengingat : 1. Undang-Undang Nomor 21 Tahun 2011 tentang Otoritas Jasa Keuangan;

Pasal 1
Dalam Peraturan ini yang dimaksud dengan Bank adalah bank umum syariah.

Pasal 2
(1) Bank wajib mencatat Produk Investasi Perbankan Syariah secara terpisah.
(2) Bank wajib menerapkan tata kelola dan manajemen risiko dalam penyelenggaraan Produk
Investasi Perbankan Syariah.

Pasal 3
(1) Bank yang melanggar ketentuan sebagaimana dimaksud dalam Pasal 2 ayat (1) dikenai sanksi
administratif berupa teguran tertulis.
(2) Dalam hal Bank telah dikenai sanksi administratif sebagaimana dimaksud pada ayat (1), dan
tetap melanggar ketentuan sebagaimana dimaksud dalam Pasal 2 ayat (1), Bank dikenai sanksi
administratif berupa:
a. larangan untuk menerbitkan produk Bank baru;
b. pembekuan kegiatan usaha Bank tertentu;
c. larangan melakukan ekspansi kegiatan usaha;
d. larangan melakukan kegiatan usaha baru; dan/atau
e. penurunan penilaian faktor tata kelola dalam penilaian tingkat kesehatan Bank.
(3) Selain sanksi administratif sebagaimana dimaksud pada ayat (1) dan ayat (2), Bank dikenai
sanksi administratif berupa denda paling sedikit Rp2.000.000.000,00 (dua miliar rupiah).

Pasal 4
Peraturan ini mulai berlaku pada tanggal ditetapkan.

Ditetapkan di Jakarta
pada tanggal 1 April 2026
"""


@pytest.fixture
def analisis(tmp_path, tmp_settings):
    pdf = tmp_path / "pojk.pdf"
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


# -- QA #1: ayat berdaftar tersingkir dari poin utama -------------------------
def test_ayat_sanksi_berdaftar_masuk_poin_utama(analisis):
    utama = {p.pasal for p in analisis.poin_utama(10)}
    assert "Pasal 3 ayat (2)" in utama, "daftar sanksi a–e harus muncul sebagai poin utama"
    assert "Pasal 3 ayat (1)" in utama, "teguran tertulis juga tidak boleh tergeser"


def test_panjang_tidak_lagi_menjadi_penalti(analisis):
    """Ayat (2) adalah poin TERPANJANG sekaligus paling padat isi; dulu justru dihukum."""
    daftar = next(p for p in analisis.poin if p.pasal == "Pasal 3 ayat (2)")
    assert len(daftar.teks) > 400 and daftar in analisis.poin_utama(10)


def test_rujukan_silang_saja_tetap_dianggap_generik(analisis):
    """Penjaga arah sebaliknya: kalimat tanpa isi sendiri tidak boleh ikut naik peringkat."""
    from hero.analysis.structured import _generik

    assert _generik("Bank melaksanakan hal tersebut sesuai dengan ketentuan peraturan perundang-undangan.")
    assert not _generik("Bank dikenai sanksi sebagaimana dimaksud pada ayat (1) berupa teguran tertulis.")


# -- QA #2: label sanksi & rujukan ayat (2) -----------------------------------
def test_label_sanksi_mengikuti_kata_di_dokumen(analisis):
    assert "teguran tertulis" in analisis.sanksi
    assert not any("/" in s for s in analisis.sanksi), "label gabungan menyebut sanksi yang tak ada di PDF"
    assert "peringatan tertulis" not in analisis.sanksi


def test_bentuk_sanksi_di_daftar_huruf_ikut_terangkum(analisis):
    assert {"pembekuan kegiatan usaha", "larangan ekspansi kegiatan usaha",
            "penurunan penilaian faktor tata kelola", "denda"} <= set(analisis.sanksi)


def test_kalimat_sanksi_merujuk_ayat_yang_memuat_daftarnya(analisis):
    kal = next(k for k in analisis.ringkasan if "sanksi" in k["kalimat"].lower())
    assert "Pasal 3 ayat (2)" in kal["rujukan"]


def test_peringatan_tertulis_tetap_dikenali_bila_dokumennya_memakai_kata_itu():
    from hero.analysis.structured import Point

    p = Point(id="F1", kategori="Sanksi", pasal="Pasal 1", halaman=1, prioritas=0,
              teks="Bank dikenai sanksi administratif berupa peringatan tertulis.")
    assert sanctions([p]) == ["peringatan tertulis"]


# -- QA #5: penggalan kata & kutipan terpotong --------------------------------
@pytest.mark.parametrize("mentah, harapan", [
    ("Undang-\nUndang Nomor 21", "Undang-Undang Nomor 21"),      # nama diri: tanda hubung bagian kata
    ("undang-\nundang dasar", "undang-undang dasar"),            # kata ulang
    ("masing-\nmasing bank", "masing-masing bank"),
    ("sehari-\nhari", "sehari-hari"),
    ("menyam-\npaikan laporan", "menyampaikan laporan"),         # pemenggalan sungguhan: disambung
    ("memper-\ntimbangkan", "mempertimbangkan"),
])
def test_penggalan_akhir_baris(mentah, harapan):
    assert clean_text(mentah) == harapan


def test_dasar_hukum_tidak_lagi_kehilangan_tanda_hubung(analisis):
    assert analisis.dasar_hukum == ["Undang-Undang Nomor 21 Tahun 2011"]
    assert not any("UndangUndang" in d for d in analisis.dasar_hukum)


def test_kutipan_tidak_dimulai_atau_diakhiri_kata_sambung():
    from hero.analysis.structured import Point

    p = Point(id="F1", kategori="Batas Waktu", pasal="Pasal 12", halaman=1, prioritas=4,
              teks=("Bank menyesuaikan hal tersebut sesuai dengan ketentuan paling lambat 2 (dua) tahun "
                    "sejak berlakunya Peraturan Otoritas Jasa Keuangan ini dan seterusnya sampai akhir "
                    "jangka waktu yang ditetapkan dalam perjanjian antara para pihak terkait."))
    k = _clause(p, "paling lambat|paling lama")
    assert not k.lower().startswith(("tersebut", "sesuai", "dengan", "ketentuan"))
    assert not k.rstrip("…").rstrip().split()[-1].lower() in ("dan", "dengan", "sesuai", "yang", "dalam")


def test_kutipan_diselesaikan_bila_sisanya_tinggal_sedikit():
    from hero.analysis.structured import Point

    p = Point(id="F1", kategori="Masa Berlaku", pasal="Pasal 4", halaman=1, prioritas=6,
              teks="Peraturan Otoritas Jasa Keuangan ini mulai berlaku pada tanggal diundangkan.")
    assert _clause(p, "mulai berlaku|berlaku sejak", 25).endswith("diundangkan")


# -- QA #6: modalitas AI -------------------------------------------------------
def test_ai_yang_melemahkan_norma_ditolak_verifikator():
    fakta = [{"id": "F1", "teks": "[Sanksi] Bank dikenai sanksi administratif berupa teguran tertulis.",
              "pasal": "Pasal 3 ayat (1)"}]
    keluaran = {"ringkasan": [{"kalimat": "Bank dapat dikenai teguran tertulis.", "fakta": ["F1"]},
                              {"kalimat": "Bank dikenai teguran tertulis.", "fakta": ["F1"]}],
                "poin_kunci": [{"fakta": "F1", "parafrase": "Bank dapat dikenai teguran tertulis."}]}
    masalah = verify(keluaran, fakta)
    assert any("daya ikat" in m and "kalimat 1" in m for m in masalah)
    assert any("daya ikat" in m and "parafrase F1" in m for m in masalah)
    assert not any("kalimat 2" in m for m in masalah)


def test_parafrase_sah_tidak_ditolak():
    """Gerbang produksi hanya menolak PELEMAHAN; ringkasan yang merangkum beberapa fakta tanpa
    mengulang setiap kata wajib tetap diterima."""
    fakta = [{"id": "F1", "teks": "[Kewajiban] Bank wajib menerapkan tata kelola.", "pasal": "Pasal 2 ayat (2)"},
             {"id": "F2", "teks": "[Sanksi] Bank dikenai sanksi berupa denda.", "pasal": "Pasal 3 ayat (3)"}]
    keluaran = {"ringkasan": [{"kalimat": "Bank harus menerapkan tata kelola.", "fakta": ["F1"]},
                              {"kalimat": "Peraturan ini mengatur tata kelola dan sanksinya.", "fakta": ["F1", "F2"]}],
                "poin_kunci": [{"fakta": "F1", "parafrase": "Tata kelola menjadi kewajiban bank."}]}
    assert verify(keluaran, fakta) == []


def test_kata_pelemah_yang_memang_ada_di_fakta_tidak_dipersoalkan():
    sumber = "[Sanksi] Pihak utama Bank dapat dikenai sanksi administratif."
    assert periksa_modalitas("Pihak utama dapat dikenai sanksi.", sumber) == []
    assert periksa_modalitas("Pihak utama dikenai sanksi.", sumber, ketat=True) == []


def test_mode_ketat_melaporkan_kewajiban_yang_hilang_sebagai_skor():
    sumber = "[Kewajiban] Bank wajib menyampaikan laporan."
    assert periksa_modalitas("Bank menyampaikan laporan.", sumber) == []            # bukan gerbang
    assert periksa_modalitas("Bank menyampaikan laporan.", sumber, ketat=True) == ["menghilangkan 'wajib'"]
