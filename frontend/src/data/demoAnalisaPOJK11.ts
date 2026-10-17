import type { MlAnalisaResponse } from '../lib/analisaApi';

/**
 * Data terverifikasi POJK-11/2024 tentang Ketahanan & Keamanan Siber
 * Sesuai skema kontrak GET /api/v1/ml/analisa/{document_id} dan desain workspace 3-panel.
 * Digunakan secara eksplisit untuk mode demo / simulasi tanpa koneksi backend.
 */
export const DEMO_ANALISA_POJK_11: MlAnalisaResponse = {
  document_id: 1,
  pdf: '/documents/POJK_11_2024.pdf',
  identitas: {
    jenis: 'POJK',
    nomor: 'POJK 11/2024 tentang Ketahanan & Keamanan Siber',
    tahun: 2024,
    tanggal: '17 Okt 2024',
    penerbit: 'Otoritas Jasa Keuangan'
  },
  ringkasan: [
    {
      kalimat: 'Regulasi ini mengatur ketahanan dan keamanan siber bagi bank umum, termasuk tata kelola, manajemen risiko, pengamanan aset, serta penanganan insiden siber.',
      rujukan: ['Pasal 1', 'Pasal 4', 'Pasal 7'],
      fakta: ['Bank Umum', 'Ketahanan Siber', 'Manajemen Risiko TI']
    }
  ],
  ringkasan_teks: 'Regulasi ini mengatur ketahanan dan keamanan siber bagi bank umum, termasuk tata kelola, manajemen risiko, pengamanan aset, serta penanganan insiden siber.',
  kerangka: [
    {
      bab: 'BAB I',
      judul: 'KETENTUAN UMUM',
      pasal: [
        'Pasal 1 (Definisi & Istilah)',
        'Pasal 2 (Ruang Lingkup)',
        'Pasal 3 (Prinsip Tata Kelola)'
      ]
    },
    {
      bab: 'BAB II',
      judul: 'TATA KELOLA SIBER',
      pasal: [
        'Pasal 4 (Strategi Keamanan)',
        'Pasal 5 (Komite & Struktur)'
      ]
    },
    {
      bab: 'BAB III',
      judul: 'MANAJEMEN RISIKO',
      pasal: [
        'Pasal 6 (Identifikasi Kerentanan)',
        'Pasal 7 (Penilaian Risiko Berkala)'
      ]
    },
    {
      bab: 'BAB IV',
      judul: 'PENGAMANAN ASET',
      pasal: [
        'Pasal 8 (Klasifikasi Aset Informasi)',
        'Pasal 9 (Perlindungan Data Nasabah)',
        'Pasal 10 (Pengamanan Jaringan & Sistem)',
        'Pasal 11 (Kriptografi & Enkripsi)',
        'Pasal 12 (Pengamanan Akses & Otentikasi)'
      ]
    },
    {
      bab: 'BAB V',
      judul: 'TANGGAP INSIDEN SIBER',
      pasal: [
        'Pasal 13 (Tim Tanggap Insiden / CSIRT)',
        'Pasal 14 (Deteksi Dini Serangan)',
        'Pasal 15 (Prosedur Eskalasi Insiden)',
        'Pasal 16 (Mitigasi dan Pembendungan)',
        'Pasal 17 (Pemulihan Layanan Kritis)',
        'Pasal 18 (Pelaporan Insiden kepada OJK)'
      ]
    },
    {
      bab: 'BAB VI',
      judul: 'PENGUJIAN KETAHANAN SIBER',
      pasal: [
        'Pasal 19 (Vulnerability Assessment Berkala)',
        'Pasal 20 (Penetration Testing Tahunan)',
        'Pasal 21 (Cyber Crisis Simulation Exercise)'
      ]
    },
    {
      bab: 'BAB VII',
      judul: 'KERJA SAMA DENGAN PIHAK KETIGA',
      pasal: [
        'Pasal 22 (Uji Kelayakan Vendor TI)',
        'Pasal 23 (Klausul Keamanan Siber dalam Kontrak)',
        'Pasal 24 (Audit Kepatuhan Pihak Ketiga)'
      ]
    },
    {
      bab: 'BAB VIII',
      judul: 'PENINGKATAN KESADARAN & KOMPETENSI',
      pasal: [
        'Pasal 25 (Pelatihan Keamanan Siber Pegawai)',
        'Pasal 26 (Sertifikasi Khusus Petugas Keamanan)',
        'Pasal 27 (Edukasi Keamanan bagi Nasabah)'
      ]
    },
    {
      bab: 'BAB IX',
      judul: 'PELAPORAN DAN DOKUMENTASI',
      pasal: [
        'Pasal 28 (Laporan Profil Risiko Siber Tahunan)',
        'Pasal 29 (Laporan Penanganan Insiden Signifikan)',
        'Pasal 30 (Audit Forensik Pasca-Insiden)'
      ]
    },
    {
      bab: 'BAB X',
      judul: 'SANKSI ADMINISTRATIF',
      pasal: [
        'Pasal 31 (Teguran Tertulis)',
        'Pasal 32 (Denda Administratif)',
        'Pasal 33 (Penurunan Tingkat Kesehatan Bank)'
      ]
    }
  ],
  poin_utama: [
    {
      id: 1,
      kategori: 'Tata Kelola',
      teks: 'Penguatan tata kelola keamanan siber melalui pembentukan komite dan struktur pengawas independen.',
      ref: 'Pasal 4',
      halaman: 2,
      urgensi: 'Tinggi'
    },
    {
      id: 2,
      kategori: 'Manajemen Risiko',
      teks: 'Identifikasi dan pengelolaan risiko teknologi informasi serta pengujian ketahanan secara berkala.',
      ref: 'Pasal 7',
      halaman: 3,
      urgensi: 'Tinggi'
    },
    {
      id: 3,
      kategori: 'Pengamanan Aset',
      teks: 'Pengamanan aset kritis dan perlindungan menyeluruh terhadap infrastruktur informasi perbankan.',
      ref: 'Pasal 12',
      halaman: 5,
      urgensi: 'Sedang'
    },
    {
      id: 4,
      kategori: 'Pelaporan',
      teks: 'Mekanisme penanganan dan kewajiban pelaporan insiden keamanan siber langsung kepada OJK.',
      ref: 'Pasal 18',
      halaman: 7,
      urgensi: 'Tinggi'
    },
    {
      id: 5,
      kategori: 'Kewajiban',
      teks: 'Bank wajib menunjuk pejabat setingkat direksi atau CISO yang beroperasi independen untuk memimpin ketahanan siber.',
      ref: 'Pasal 5',
      halaman: 2,
      urgensi: 'Tinggi'
    },
    {
      id: 6,
      kategori: 'Kewajiban',
      teks: 'Pengujian penetrasi (Penetration Testing) wajib dilakukan oleh pihak ketiga independen minimal 1 kali dalam 1 tahun.',
      ref: 'Pasal 20',
      halaman: 8,
      urgensi: 'Tinggi'
    },
    {
      id: 7,
      kategori: 'Larangan',
      teks: 'Dilarang menyimpan kunci enkripsi bersamaan dengan media penyimpanan data nasabah tanpa perlindungan HSM.',
      ref: 'Pasal 11',
      halaman: 5,
      urgensi: 'Tinggi'
    },
    {
      id: 8,
      kategori: 'Sanksi',
      teks: 'Keterlambatan pelaporan insiden siber kritis lebih dari 1x24 jam dikenakan sanksi administratif dan denda progresif.',
      ref: 'Pasal 32',
      halaman: 12,
      urgensi: 'Tinggi'
    }
  ],
  jumlah_poin: 8,
  subjek_diatur: [
    'Bank Umum Konvensional',
    'Bank Umum Syariah',
    'Unit Usaha Syariah (UUS)',
    'Kantor Cabang Bank Asing (KCBA)'
  ],
  sanksi: [
    'Peringatan tertulis pertama dan kedua',
    'Denda administratif hingga Rp500.000.000',
    'Pembatasan penerbitan produk digital baru',
    'Penurunan penilaian tata kelola dan tingkat kesehatan bank'
  ],
  dasar_hukum: [
    'Undang-Undang Nomor 21 Tahun 2011 tentang Otoritas Jasa Keuangan',
    'Undang-Undang Nomor 4 Tahun 2023 tentang Pengembangan dan Penguatan Sektor Keuangan (UU P2SK)',
    'Undang-Undang Nomor 7 Tahun 1992 tentang Perbankan',
    'Peraturan Pemerintah Nomor 71 Tahun 2019 tentang Penyelenggaraan Sistem dan Transaksi Elektronik'
  ],
  lampiran: [
    'Lampiran I: Format Laporan Profil Risiko dan Kesiapan Siber Tahunan',
    'Lampiran II: Tata Cara Pelaporan Insiden Siber Signifikan kepada Satuan Pengawas OJK',
    'Lampiran III: Standar Kualifikasi dan Sertifikasi Keamanan Informasi untuk CISO'
  ],
  metrik: {
    jumlah_pasal: 92,
    jumlah_ayat: 215,
    jumlah_bab: 14,
    jumlah_kewajiban: 48,
    jumlah_larangan: 14
  },
  mode_diminta: 'deterministik',
  mode_dipakai: 'deterministik',
  ai: null,
  catatan: 'Draft / Rekomendasi — keluaran sistem bukan keputusan final. Keputusan tetap kewenangan Pengawas / unit terkait DPEA.'
};
