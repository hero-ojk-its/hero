/**
 * Sumber kebenaran tunggal label & warna status keberlakuan di seluruh frontend
 * (Knowledge Base, detail dokumen, modal ubah status, kandidat pindai, Dashboard),
 * serta label jenis & alasan kegagalan ingest.
 * Nilai enum mengikuti backend (components['schemas']['StatusKeberlakuan']).
 * Komponen membandingkan NILAI ENUM, bukan teks label.
 */

import type { components } from './openapi';

export type StatusKeberlakuan = components['schemas']['StatusKeberlakuan'];

/** Urutan tampilan pada filter dan pilihan status */
export const STATUS_KEBERLAKUAN_OPSI: readonly StatusKeberlakuan[] = [
  'berlaku',
  'belum_berlaku',
  'diubah',
  'dicabut',
  'tidak_diketahui',
];

/** Label "Belum berlaku" sesuai backend/docs/reports/step26-report.md §9 */
export const STATUS_KEBERLAKUAN_LABELS: Record<StatusKeberlakuan, string> = {
  berlaku: 'Berlaku',
  belum_berlaku: 'Belum berlaku',
  diubah: 'Diubah',
  dicabut: 'Dicabut',
  tidak_diketahui: 'Tidak diketahui',
};

export interface GayaStatusKeberlakuan {
  /** Badge/pil: latar, teks, garis */
  badge: string;
  /** Titik warna kecil */
  titik: string;
  /** Pilihan radio terpilih pada modal ubah status */
  pilihan: string;
}

const GAYA_NETRAL: GayaStatusKeberlakuan = {
  badge: 'bg-gray-100 text-gray-600 border-gray-200',
  titik: 'bg-gray-400',
  pilihan: 'border-gray-400 bg-gray-50 text-gray-900',
};

const GAYA_STATUS: Record<StatusKeberlakuan, GayaStatusKeberlakuan> = {
  berlaku: {
    badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    titik: 'bg-emerald-500',
    pilihan: 'border-emerald-500 bg-emerald-50/40 text-emerald-900',
  },
  // Biru: berbeda dari berlaku (hijau), diubah (amber), dan dicabut (merah)
  belum_berlaku: {
    badge: 'bg-blue-50 text-blue-700 border-blue-200',
    titik: 'bg-blue-500',
    pilihan: 'border-blue-500 bg-blue-50/40 text-blue-900',
  },
  diubah: {
    badge: 'bg-amber-50 text-amber-700 border-amber-200',
    titik: 'bg-amber-500',
    pilihan: 'border-amber-500 bg-amber-50/40 text-amber-900',
  },
  dicabut: {
    badge: 'bg-rose-50 text-rose-700 border-rose-200',
    titik: 'bg-rose-500',
    pilihan: 'border-rose-500 bg-rose-50/40 text-rose-900',
  },
  tidak_diketahui: GAYA_NETRAL,
};

export function isStatusKeberlakuan(nilai: unknown): nilai is StatusKeberlakuan {
  return typeof nilai === 'string' && (STATUS_KEBERLAKUAN_OPSI as readonly string[]).includes(nilai);
}

/**
 * Ubah nilai enum, label tampilan ("Tidak diketahui"), atau label lama ("Aktif" pada data
 * contoh / URL lama) menjadi nilai enum. null bila tidak dikenali.
 */
export function normalisasiStatusKeberlakuan(nilai: unknown): StatusKeberlakuan | null {
  if (typeof nilai !== 'string') return null;
  const kunci = nilai.trim().toLowerCase().replace(/[\s-]+/g, '_');
  if (kunci === 'aktif') return 'berlaku';
  return isStatusKeberlakuan(kunci) ? kunci : null;
}

/** Kode tak dikenal dibuat terbaca: "status_aneh_baru" -> "Status aneh baru"; kosong -> "Tidak diketahui" */
export function formatKodeTakDikenal(kode: unknown): string {
  if (typeof kode !== 'string' || kode.trim() === '') return 'Tidak diketahui';
  const teks = kode.trim().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').toLowerCase();
  return teks.charAt(0).toUpperCase() + teks.slice(1);
}

export function labelStatusKeberlakuan(nilai: unknown): string {
  const status = normalisasiStatusKeberlakuan(nilai);
  return status ? STATUS_KEBERLAKUAN_LABELS[status] : formatKodeTakDikenal(nilai);
}

/** Gaya berdasarkan nilai enum; nilai tak dikenal memakai gaya netral */
export function gayaStatusKeberlakuan(nilai: unknown): GayaStatusKeberlakuan {
  const status = normalisasiStatusKeberlakuan(nilai);
  return status ? GAYA_STATUS[status] : GAYA_NETRAL;
}

export function kelasBadgeStatusKeberlakuan(nilai: unknown): string {
  return gayaStatusKeberlakuan(nilai).badge;
}

// ============================================================================
// Kegagalan ingest: failure_type (enum JenisKegagalan) & reason_code (teks bebas)
// ============================================================================

/** Label failure_type (enum JenisKegagalan di backend) */
export const JENIS_KEGAGALAN_LABELS: Record<string, string> = {
  format_tidak_didukung: 'Format Tidak Didukung',
  duplikat: 'Duplikat',
  ekstraksi_gagal: 'Ekstraksi Gagal',
  ocr_gagal: 'OCR Gagal',
  metadata_tidak_lengkap: 'Metadata Tidak Lengkap',
  sumber_tidak_dapat_diakses: 'Sumber Tidak Dapat Diakses',
  kesalahan_internal: 'Kesalahan Internal',
};

/**
 * Label reason_code yang tidak bernama sama dengan failure_type. Sumber: file_validation.py
 * (FileRejectCode), failure_service.py (REASON_CODE_MAP), routers/internal.py (ekstraksi),
 * step26-report.md §9. reason_code lain yang sama dengan failure_type memakai label di atas.
 */
const ALASAN_GAGAL_LABELS: Record<string, string> = {
  pdf_rusak: 'PDF rusak / tidak bisa dibuka',
  pdf_terenkripsi: 'PDF terkunci kata sandi',
  teks_kosong: 'Teks tidak terbaca',
  teks_kosong_ocr: 'OCR tidak menghasilkan teks',
  berkas_kosong: 'Berkas kosong',
  ukuran_melebihi_batas: 'Ukuran melebihi batas',
  kategori_tidak_ditemukan: 'Kategori tidak ditemukan',
  simpan_ekstraksi_gagal: 'Gagal menyimpan hasil ekstraksi',
  penempatan_gagal: 'Gagal menempatkan berkas',
};

export function labelJenisKegagalan(jenis: unknown): string {
  if (typeof jenis !== 'string' || jenis.trim() === '') return '-';
  return JENIS_KEGAGALAN_LABELS[jenis.trim()] ?? formatKodeTakDikenal(jenis);
}

/** Label reason_code; kode tak dikenal (mis. kode baru dari worker) dibuat terbaca, tidak tampil mentah */
export function labelAlasanGagal(kode: unknown): string {
  if (typeof kode !== 'string' || kode.trim() === '') return 'Tidak diketahui';
  const k = kode.trim();
  return ALASAN_GAGAL_LABELS[k] ?? JENIS_KEGAGALAN_LABELS[k] ?? formatKodeTakDikenal(k);
}

/**
 * Teks untuk baris "Alasan: …" di samping badge failure_type, atau null bila reason_code kosong
 * atau labelnya sama dengan label failure_type (agar tidak tampil ganda).
 */
export function alasanTambahanGagal(failureType: unknown, reasonCode: unknown): string | null {
  if (typeof reasonCode !== 'string' || reasonCode.trim() === '') return null;
  const alasan = labelAlasanGagal(reasonCode);
  return alasan.toLowerCase() === labelJenisKegagalan(failureType).toLowerCase() ? null : alasan;
}

// ============================================================================
// Penempatan dokumen saat kategori diubah nama / dipindah (PATCH /categories/{id}.dokumen_gagal[].alasan)
// ============================================================================

/**
 * Sumber: placement_service.PlacementResult.reason & category_service.update. "metadata_belum_cukup"
 * bukan galat: dokumen tetap di kategorinya, hanya berkasnya belum dipindah ke folder KB.
 */
export interface AlasanPenempatan {
  /** Kunci pengelompokan */
  kode: 'metadata_belum_cukup' | 'gagal';
  jenis: 'info' | 'gagal';
  label: string;
  keterangan: string;
  /** Pesan dari backend tanpa awalan "gagal:"; null bila tidak ada */
  pesan: string | null;
}

const PESAN_PENEMPATAN_MAKS = 200;

export function alasanPenempatan(alasan: unknown): AlasanPenempatan {
  const teks = typeof alasan === 'string' ? alasan.trim() : '';
  if (teks === 'metadata_belum_cukup') {
    return {
      kode: 'metadata_belum_cukup',
      jenis: 'info',
      label: 'Metadata belum lengkap',
      keterangan: 'Tetap di kategori ini; berkas belum ditempatkan di folder KB karena metadata belum lengkap.',
      pesan: null,
    };
  }
  // "gagal: <exception>", "gagal_penempatan", atau teks exception mentah
  const bersih = teks.replace(/^gagal(_penempatan)?\s*:?\s*/i, '').trim();
  return {
    kode: 'gagal',
    jenis: 'gagal',
    label: 'Gagal memindahkan berkas',
    keterangan: 'Kategori sudah diperbarui, tetapi berkas dokumen ini belum berhasil dipindahkan ke folder baru.',
    pesan: bersih === '' ? null : bersih.length > PESAN_PENEMPATAN_MAKS ? `${bersih.slice(0, PESAN_PENEMPATAN_MAKS)}…` : bersih,
  };
}
