import enum


class StatusKeberlakuan(str, enum.Enum):
    """Status keberlakuan suatu dokumen regulasi"""
    berlaku = "berlaku"
    diubah = "diubah"
    dicabut = "dicabut"
    tidak_diketahui = "tidak_diketahui"


class KlasifikasiAkses(str, enum.Enum):
    """
    Klasifikasi akses dokumen:
    - publik: dokumen regulasi terbuka / umum
    - non_publik: dokumen internal / draft yang tunduk pada NDA
    """
    publik = "publik"
    non_publik = "non_publik"


class PeranDokumen(str, enum.Enum):
    """Peran dokumen dalam basis pengetahuan / kajian"""
    corpus_eksisting = "corpus_eksisting"
    draft_kajian = "draft_kajian"


class MetodeEkstraksi(str, enum.Enum):
    """Metode ekstraksi teks dari file sumber"""
    teks_langsung = "teks_langsung"
    ocr = "ocr"


class StatusPemrosesan(str, enum.Enum):
    """Status tahapan pemrosesan dokumen dalam pipeline ingest"""
    diterima = "diterima"
    diproses = "diproses"
    perlu_koreksi = "perlu_koreksi"
    terindeks = "terindeks"
    gagal = "gagal"
    ditolak = "ditolak"


class JenisJobIngest(str, enum.Enum):
    """Tipe sumber pekerjaan ingest"""
    scraping = "scraping"
    unggah_manual = "unggah_manual"
    sinkron_folder = "sinkron_folder"


class StatusJobIngest(str, enum.Enum):
    """Status eksekusi batch/job ingest"""
    antrian = "antrian"
    berjalan = "berjalan"
    selesai = "selesai"
    gagal = "gagal"


class JenisRujukan(str, enum.Enum):
    """Tipe hubungan rujukan hukum antar dokumen regulasi"""
    dasar_hukum = "dasar_hukum"
    rujukan_pasal = "rujukan_pasal"
    pencabutan = "pencabutan"
    perubahan = "perubahan"
