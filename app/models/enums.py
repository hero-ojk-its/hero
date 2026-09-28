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


class JenisSumber(str, enum.Enum):
    """Jenis situs atau folder sumber dokumen"""
    situs_web = "situs_web"
    folder_lokal = "folder_lokal"
    onedrive_public = "onedrive_public"


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


class JenisKegagalan(str, enum.Enum):
    """Jenis kegagalan ingest (Data Dictionary §2.18 + 1 tambahan)"""
    format_tidak_didukung = "format_tidak_didukung"
    duplikat = "duplikat"
    ekstraksi_gagal = "ekstraksi_gagal"
    ocr_gagal = "ocr_gagal"
    metadata_tidak_lengkap = "metadata_tidak_lengkap"
    sumber_tidak_dapat_diakses = "sumber_tidak_dapat_diakses"
    kesalahan_internal = "kesalahan_internal"


class StatusTindakLanjut(str, enum.Enum):
    """Status tindak lanjut penanganan kegagalan ingest"""
    belum_ditangani = "belum_ditangani"
    diproses_ulang = "diproses_ulang"
    diabaikan = "diabaikan"


class StatusPindai(str, enum.Enum):
    """Status tahapan sesi pemindaian situs web (Langkah 7)"""
    antrian = "antrian"
    memindai = "memindai"
    siap_dipilih = "siap_dipilih"
    menarik = "menarik"
    selesai = "selesai"
    gagal = "gagal"
    dibatalkan = "dibatalkan"


class TujuanTarik(str, enum.Enum):
    """Tujuan penarikan dokumen dari sesi pemindaian"""
    knowledge_base = "knowledge_base"
    unduh_folder = "unduh_folder"


class StatusKandidat(str, enum.Enum):
    """Status kecocokan kandidat berkas terhadap basis pengetahuan (KB)"""
    baru = "baru"
    sudah_ada = "sudah_ada"
    mungkin_ada = "mungkin_ada"


class HasilTarik(str, enum.Enum):
    """Hasil akhir penarikan berkas kandidat (Langkah 8)"""
    berhasil = "berhasil"
    duplikat = "duplikat"
    gagal = "gagal"
    diunduh = "diunduh"


