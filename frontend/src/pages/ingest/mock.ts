export interface AvailableFolder {
  name: string;
  path: string;
  description: string;
  fileCount: number;
}

export const availableFolders: AvailableFolder[] = [
  {
    name: 'peraturan_internal',
    path: '/app/sources/peraturan_internal',
    description: 'Regulasi internal perbankan & panduan OJK',
    fileCount: 12,
  },
  {
    name: 'fintech_2026',
    path: '/app/sources/fintech_2026',
    description: 'Regulasi fintech P2P & inovasi digital',
    fileCount: 8,
  },
  {
    name: 'it_governance',
    path: '/app/sources/it_governance',
    description: 'Tata kelola TI & ketahanan siber',
    fileCount: 6,
  },
];

export interface MockScrapedDoc {
  title: string;
  num: string;
  type: string;
  year: string;
  regStatus: 'Aktif' | 'Diubah' | 'Dicabut';
  kbsStatus: 'Baru' | 'Sudah Ada' | 'Duplikat';
  active: boolean;
}

export const mockScrapedDocs: MockScrapedDoc[] = [
  { title: 'POJK tentang Ketahanan dan Keamanan Siber Bank Umum', num: 'POJK No. 11/POJK.03/2024', type: 'POJK', year: '2024', regStatus: 'Aktif', kbsStatus: 'Baru', active: true },
  { title: 'SEOJK tentang Format Pelaporan Ketahanan Siber', num: 'SEOJK No. 14/SEOJK.03/2024', type: 'SEOJK', year: '2024', regStatus: 'Aktif', kbsStatus: 'Baru', active: true },
  { title: 'SEOJK tentang Mitigasi Risiko Penyelenggaraan Fintech P2P', num: 'SEOJK No. 29/SEOJK.05/2023', type: 'SEOJK', year: '2023', regStatus: 'Diubah', kbsStatus: 'Baru', active: true },
  { title: 'POJK tentang Manajemen Risiko Teknologi Informasi', num: 'POJK No. 05/POJK.03/2023', type: 'POJK', year: '2023', regStatus: 'Aktif', kbsStatus: 'Baru', active: true },
  { title: 'PDK tentang Perlindungan Konsumen Sektor Jasa Keuangan', num: 'PDK No. 08/PDK.07/2022', type: 'PDK', year: '2022', regStatus: 'Aktif', kbsStatus: 'Baru', active: true },
  { title: 'POJK tentang Tata Kelola Teknologi Informasi', num: 'POJK No. 11/POJK.03/2022', type: 'POJK', year: '2023', regStatus: 'Aktif', kbsStatus: 'Sudah Ada', active: false },
  { title: 'POJK tentang Inovasi Keuangan Digital (Fintech Sandbox)', num: 'POJK No. 13/POJK.02/2018', type: 'POJK', year: '2018', regStatus: 'Aktif', kbsStatus: 'Sudah Ada', active: false },
  { title: 'SEOJK tentang Penyelenggaraan Layanan Perbankan Digital', num: 'SEOJK No. 21/SEOJK.03/2021', type: 'SEOJK', year: '2021', regStatus: 'Aktif', kbsStatus: 'Sudah Ada', active: false },
  { title: 'POJK tentang Penerapan Manajemen Risiko Terintegrasi bagi Konglomerasi Keuangan', num: 'POJK No. 45/POJK.03/2020', type: 'POJK', year: '2020', regStatus: 'Aktif', kbsStatus: 'Sudah Ada', active: false },
  { title: 'SEOJK tentang Standar Penerapan Tata Kelola TI Bank Umum', num: 'SEOJK No. 35/SEOJK.03/2017', type: 'SEOJK', year: '2017', regStatus: 'Diubah', kbsStatus: 'Sudah Ada', active: false },
  { title: 'POJK tentang Tata Cara Pemeriksaan Sektor Perbankan', num: 'POJK No. 03/POJK.03/2019', type: 'POJK', year: '2019', regStatus: 'Aktif', kbsStatus: 'Sudah Ada', active: false },
  { title: 'SEDK tentang Ketentuan Teknis Keamanan Informasi', num: 'SEDK No. 04/SEDK.03/2020', type: 'SEDK', year: '2020', regStatus: 'Dicabut', kbsStatus: 'Duplikat', active: false },
];

export interface ManualFileItem {
  id: string;
  name: string;
  size: string;
  title: string;
  num: string;
  type: string;
  year: string;
  regStatus: 'Aktif' | 'Diubah' | 'Dicabut';
  kbsStatus: 'Baru' | 'Sudah Ada' | 'Duplikat';
  active: boolean;
}

export const initialManualFiles: ManualFileItem[] = [
  {
    id: 'doc-m-1',
    name: 'POJK_No_12_POJK03_2024_Ketahanan_Siber.pdf',
    size: '2.8 MB',
    title: 'POJK tentang Ketahanan dan Keamanan Siber Bank Umum',
    num: 'POJK No. 12/POJK.03/2024',
    type: 'POJK',
    year: '2024',
    regStatus: 'Aktif',
    kbsStatus: 'Baru',
    active: true,
  },
  {
    id: 'doc-m-2',
    name: 'SEOJK_No_15_SEOJK03_2024_Format_Pelaporan.pdf',
    size: '1.6 MB',
    title: 'SEOJK tentang Pedoman Tata Kelola dan Audit Siber',
    num: 'SEOJK No. 15/SEOJK.03/2024',
    type: 'SEOJK',
    year: '2024',
    regStatus: 'Aktif',
    kbsStatus: 'Baru',
    active: true,
  },
  {
    id: 'doc-m-3',
    name: 'SEOJK_No_30_SEOJK05_2023_Mitigasi_Fintech.pdf',
    size: '3.1 MB',
    title: 'SEOJK tentang Mitigasi Risiko Penyelenggaraan Fintech P2P',
    num: 'SEOJK No. 30/SEOJK.05/2023',
    type: 'SEOJK',
    year: '2023',
    regStatus: 'Diubah',
    kbsStatus: 'Baru',
    active: true,
  },
  {
    id: 'doc-m-4',
    name: 'POJK_No_11_POJK03_2022_Tata_Kelola_TI.pdf',
    size: '2.4 MB',
    title: 'POJK tentang Tata Kelola Teknologi Informasi',
    num: 'POJK No. 11/POJK.03/2022',
    type: 'POJK',
    year: '2022',
    regStatus: 'Aktif',
    kbsStatus: 'Sudah Ada',
    active: false,
  },
  {
    id: 'doc-m-5',
    name: 'SEDK_No_04_SEDK03_2020_Keamanan_Info.pdf',
    size: '980 KB',
    title: 'SEDK tentang Ketentuan Teknis Keamanan Informasi',
    num: 'SEDK No. 04/SEDK.03/2020',
    type: 'SEDK',
    year: '2020',
    regStatus: 'Dicabut',
    kbsStatus: 'Duplikat',
    active: false,
  },
];

export const mockManualUploadHistory = [
  {
    name: 'POJK_No_12_POJK03_2024_Ketahanan_Siber.pdf',
    time: 'Hari ini, 15:20 WIB',
    size: '2.8 MB',
    filesCount: '1 dokumen',
    newDocs: '1 baru',
    status: 'Berhasil',
  },
  {
    name: 'Paket_Regulasi_Fintech_Q3_2025.zip (3 PDF)',
    time: 'Kemarin, 11:45 WIB',
    size: '7.5 MB',
    filesCount: '3 dokumen',
    newDocs: '2 baru',
    status: 'Berhasil',
  },
  {
    name: 'SE_Direksi_Tata_Kelola_Internal_2023.pdf',
    time: '28 Sep 2026, 09:15 WIB',
    size: '1.4 MB',
    filesCount: '1 dokumen',
    newDocs: '0 baru (sudah ada)',
    status: 'Berhasil',
  },
];

export const mockScrapingHistory = [
  {
    url: 'jdih.ojk.go.id/peraturan/sektor-perbankan',
    time: 'Hari ini, 14:30 WIB',
    totalDocs: '12 dokumen',
    newDocs: '5 baru',
    status: 'Berhasil',
  },
  {
    url: 'jdih.ojk.go.id/peraturan/pasar-modal-2024',
    time: 'Kemarin, 09:15 WIB',
    totalDocs: '8 dokumen',
    newDocs: '3 baru',
    status: 'Berhasil',
  },
  {
    url: 'ojk.go.id/id/kanal/fintech/regulasi-sandbox',
    time: '20 Sep 2026, 11:20 WIB',
    totalDocs: '0 dokumen',
    newDocs: '0',
    status: 'Gagal Terhubung',
  },
];

export const mockFailuresList = [
  {
    id: 9,
    job_id: 24,
    original_filename: 'b04_fake.pdf',
    source_url: null,
    failure_type: 'format_tidak_didukung',
    reason_code: 'format_tidak_didukung',
    message: 'Isi berkas bukan PDF yang valid meskipun berekstensi .pdf.',
    is_retryable: false,
    quarantine_path: null,
    file_hash: '51e6d54ae2751e2624038cf7da96abb6a2229b6d357c64694d0192cefa27b5a7',
    file_size_bytes: 66,
    duplicate_of_document_id: null,
    duplicate_of_document: null,
    follow_up_status: 'belum_ditangani',
    attempt_count: 0,
    created_at: '2026-10-04T18:26:06.707543Z',
    updated_at: '2026-10-04T18:26:06.707543Z',
  },
  {
    id: 10,
    job_id: 25,
    original_filename: 'b02_fresh.pdf',
    source_url: null,
    failure_type: 'duplikat',
    reason_code: 'duplikat',
    message: 'Dokumen duplikat: hash SHA-256 dan ukuran 1272 byte sama dengan dokumen ID 59 (b02 fresh sample).',
    is_retryable: false,
    quarantine_path: null,
    file_hash: 'ba252be6a8a929edb8c92651c52776145e80caf69d473728c41599334df8cc52',
    file_size_bytes: 1272,
    duplicate_of_document_id: 59,
    duplicate_of_document: { id: 59, title: 'b02 fresh sample', regulation_number: 'POJK 2/2026' },
    follow_up_status: 'diabaikan',
    attempt_count: 0,
    created_at: '2026-10-04T18:26:14.228241Z',
    updated_at: '2026-10-04T18:26:14.228241Z',
  },
];

