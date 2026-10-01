export interface RegulasiItem {
  id: number;
  judul: string;
  jenis: string;
  nomor: string;
  kategori: string;
  topik: string;
  tahun: number;
  status: 'Aktif' | 'Diubah' | 'Dicabut' | string;
  sumber: 'Scraping' | 'Folder Lokal' | 'OneDrive' | 'Upload Manual' | string;
  ukuran?: string;
  sha256?: string;
}

export const regulasiData: RegulasiItem[] = [
  {
    id: 1,
    judul: "POJK tentang Ketahanan dan Keamanan Siber Bank Umum",
    jenis: "POJK",
    nomor: "POJK-11/2024",
    kategori: "Perbankan",
    topik: "Ketahanan Siber",
    tahun: 2024,
    status: "Aktif",
    sumber: "Scraping",
    ukuran: "2.4 MB"
  },
  {
    id: 2,
    judul: "POJK tentang Tata Kelola Teknologi Informasi",
    jenis: "POJK",
    nomor: "POJK-22/2023",
    kategori: "Tata Kelola IT & AI",
    topik: "Tata Kelola",
    tahun: 2023,
    status: "Aktif",
    sumber: "Folder Lokal",
    ukuran: "3.1 MB"
  },
  {
    id: 3,
    judul: "SEOJK tentang Ketentuan Mitigasi Risiko Teknologi...",
    jenis: "SEOJK",
    nomor: "SEOJK-29/2023",
    kategori: "Fintech",
    topik: "Manajemen Risiko",
    tahun: 2023,
    status: "Diubah",
    sumber: "OneDrive",
    ukuran: "1.8 MB"
  },
  {
    id: 4,
    judul: "PDK tentang Perlindungan Konsumen",
    jenis: "PDK",
    nomor: "PDK-08/2022",
    kategori: "Pasar Modal",
    topik: "Perlindungan Konsumen",
    tahun: 2022,
    status: "Aktif",
    sumber: "Scraping",
    ukuran: "1.5 MB"
  },
  {
    id: 5,
    judul: "POJK tentang Manajemen Risiko Teknologi Informasi",
    jenis: "POJK",
    nomor: "POJK-05/2023",
    kategori: "Asuransi",
    topik: "Manajemen Risiko",
    tahun: 2023,
    status: "Aktif",
    sumber: "OneDrive",
    ukuran: "2.9 MB"
  },
  {
    id: 6,
    judul: "SEOJK tentang Format Informasi Ketahanan Siber",
    jenis: "SEOJK",
    nomor: "SEOJK-14/2024",
    kategori: "Perbankan",
    topik: "Ketahanan Siber",
    tahun: 2024,
    status: "Aktif",
    sumber: "Scraping",
    ukuran: "1.2 MB"
  },
  {
    id: 7,
    judul: "PDK tentang Tata Kelola Struktur",
    jenis: "PDK",
    nomor: "PDK-03/2021",
    kategori: "Pasar Modal",
    topik: "Tata Kelola",
    tahun: 2021,
    status: "Diubah",
    sumber: "Folder Lokal",
    ukuran: "2.0 MB"
  },
  {
    id: 8,
    judul: "SEDK tentang Ketentuan Teknis Keamanan",
    jenis: "SEDK",
    nomor: "SEDK-02/2020",
    kategori: "Tata Kelola IT & AI",
    topik: "Ketahanan Siber",
    tahun: 2020,
    status: "Dicabut",
    sumber: "Scraping",
    ukuran: "950 KB"
  }
];
