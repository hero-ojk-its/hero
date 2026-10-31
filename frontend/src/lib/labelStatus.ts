/**
 * Sumber kebenaran tunggal label & warna status keberlakuan di seluruh frontend
 * (Knowledge Base, detail dokumen, modal ubah status, kandidat pindai).
 * Nilai enum mengikuti backend (components['schemas']['StatusKeberlakuan']).
 * Komponen membandingkan NILAI ENUM, bukan teks label.
 */

import type { components } from './openapi';

export type StatusKeberlakuanApi = components['schemas']['StatusKeberlakuan'];
/** Nilai yang sudah punya label & warna di frontend */
export type StatusKeberlakuan = Exclude<StatusKeberlakuanApi, 'belum_berlaku'>;

/** Urutan tampilan pada filter dan pilihan status */
export const STATUS_KEBERLAKUAN_OPSI: readonly StatusKeberlakuan[] = ['berlaku', 'diubah', 'dicabut', 'tidak_diketahui'];

export const STATUS_KEBERLAKUAN_LABELS: Record<StatusKeberlakuan, string> = {
  berlaku: 'Berlaku',
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
