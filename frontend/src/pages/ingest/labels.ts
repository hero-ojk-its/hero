/**
 * Pemetaan label tunggal bahasa Indonesia untuk seluruh enum backend HERO.
 * Berdasarkan KONTRAK-API-FASE1.md §11.
 */

export const MATCH_STATUS_LABELS: Record<string, string> = {
  baru: 'Baru',
  sudah_ada: 'Sudah Ada',
  mungkin_ada: 'Mungkin Ada',
};

export const STATUS_KEBERLAKUAN_LABELS: Record<string, string> = {
  berlaku: 'Berlaku',
  diubah: 'Diubah',
  dicabut: 'Dicabut',
  tidak_diketahui: 'Tidak diketahui',
};

export const DOC_KIND_LABELS: Record<string, string> = {
  utama: 'Peraturan Utama',
  lampiran: 'Lampiran',
  perubahan: 'Peraturan Perubahan',
  pencabutan: 'Peraturan Pencabutan',
};

export const STATUS_PINDAI_LABELS: Record<string, string> = {
  antrian: 'Dalam Antrian',
  memindai: 'Sedang Memindai',
  siap_dipilih: 'Siap Dipilih',
  menarik: 'Sedang Menarik',
  selesai: 'Selesai',
  gagal: 'Gagal',
  dibatalkan: 'Dibatalkan',
};

export const STATUS_JOB_INGEST_LABELS: Record<string, string> = {
  antrian: 'Antrian',
  berjalan: 'Berjalan',
  selesai: 'Selesai',
  gagal: 'Gagal',
};

export const JENIS_KEGAGALAN_LABELS: Record<string, string> = {
  format_tidak_didukung: 'Format Tidak Didukung',
  duplikat: 'Duplikat',
  ekstraksi_gagal: 'Ekstraksi Gagal',
  ocr_gagal: 'OCR Gagal',
  metadata_tidak_lengkap: 'Metadata Tidak Lengkap',
  sumber_tidak_dapat_diakses: 'Sumber Tidak Dapat Diakses',
  kesalahan_internal: 'Kesalahan Internal',
};

export const JENIS_SUMBER_LABELS: Record<string, string> = {
  situs_web: 'Situs Web',
  folder_lokal: 'Folder Lokal',
  onedrive_public: 'OneDrive Publik',
};

export const KLASIFIKASI_AKSES_LABELS: Record<string, string> = {
  publik: 'Publik',
  non_publik: 'Non-Publik',
};

export const PERAN_DOKUMEN_LABELS: Record<string, string> = {
  corpus_eksisting: 'Corpus Eksisting',
  draft_kajian: 'Draft Kajian',
};

export const TUJUAN_TARIK_LABELS: Record<string, string> = {
  knowledge_base: 'Knowledge Base',
  unduh_folder: 'Unduh Folder (ZIP)',
};

export const HASIL_TARIK_LABELS: Record<string, string> = {
  berhasil: 'Berhasil',
  duplikat: 'Duplikat',
  gagal: 'Gagal',
  diunduh: 'Diunduh',
};

/**
 * Format label match_status dengan fallback aman.
 */
export function getMatchStatusLabel(status: string | null | undefined): string {
  if (!status) return '-';
  return MATCH_STATUS_LABELS[status] || status;
}

/**
 * Format label status_keberlakuan dengan fallback aman.
 */
export function getStatusKeberlakuanLabel(status: string | null | undefined): string {
  if (!status) return 'Tidak diketahui';
  return STATUS_KEBERLAKUAN_LABELS[status] || status;
}

/**
 * Format label doc_kind dengan fallback aman.
 */
export function getDocKindLabel(kind: string | null | undefined): string {
  if (!kind) return 'Peraturan Utama';
  return DOC_KIND_LABELS[kind] || kind;
}

/**
 * Format label status pemindaian.
 */
export function getStatusPindaiLabel(status: string | null | undefined): string {
  if (!status) return '-';
  return STATUS_PINDAI_LABELS[status] || status;
}

/**
 * Helper kelas warna badge status keberlakuan.
 */
export function getStatusKeberlakuanBadgeClass(status: string | null | undefined): string {
  switch (status) {
    case 'berlaku':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    case 'diubah':
      return 'bg-amber-50 text-amber-700 border-amber-200';
    case 'dicabut':
      return 'bg-rose-50 text-rose-700 border-rose-200';
    default:
      return 'bg-gray-100 text-gray-600 border-gray-200';
  }
}

/**
 * Helper kelas warna badge match_status.
 */
export function getMatchStatusBadgeClass(status: string | null | undefined): string {
  switch (status) {
    case 'baru':
      return 'bg-blue-50 text-blue-700 border-blue-200';
    case 'sudah_ada':
      return 'bg-gray-100 text-gray-600 border-gray-200';
    case 'mungkin_ada':
      return 'bg-amber-50 text-amber-700 border-amber-200';
    default:
      return 'bg-gray-50 text-gray-600 border-gray-200';
  }
}
