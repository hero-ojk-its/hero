/**
 * Client API Kemiripan Draft HERO (draft berulang & perbandingan per pasal).
 *
 * Endpoint: GET /api/v1/documents/{document_id}/kemiripan-draft?ambang=&limit=
 * Read-only dan tidak tercatat di audit, aman dipanggil ulang.
 * Tipe diambil dari hasil gen:api (DraftKemiripanResponse dan turunannya).
 * Galat backend (routers/documents.py) berupa teks: 404 "Dokumen tidak ditemukan",
 * 409 "Draft belum selesai diekstraksi", 422 "Kemiripan draft hanya untuk dokumen draft kajian";
 * 403 teks atau {code: "akses_ditolak"}; 401 bila auth aktif (izin KB_BACA).
 */

import { apiFetch, ApiError, buildQueryString } from './api';
import type { components, operations } from './openapi';

export type DraftKemiripanResponse = components['schemas']['DraftKemiripanResponse'];
export type DraftMiripItem = components['schemas']['DraftMiripItem'];
export type DraftTerdekatItem = components['schemas']['DraftTerdekatItem'];
export type PerPasalDetail = components['schemas']['PerPasalDetail'];
export type RincianPasal = components['schemas']['RincianPasal'];
export type RingkasPasal = components['schemas']['RingkasPasal'];
export type KemiripanDraftQuery = NonNullable<
  operations['get_draft_similarity_api_v1_documents__document_id__kemiripan_draft_get']['parameters']['query']
>;

/** Nilai status draft_mirip dari kemiripan_service.py ("identik" bila >= 99,5%) */
export type StatusDraftMirip = 'identik' | 'sangat_mirip';
/** Nilai status per pasal dari banding_pasal() */
export type StatusPasal = 'sama' | 'berubah' | 'baru' | 'dihapus';

/** Perbandingan Jaccard terhadap hingga 200 draft bisa lebih lama dari batas bawaan 15 detik */
export const KEMIRIPAN_TIMEOUT_MS = 60000;

export interface GetKemiripanDraftOptions {
  /** Tanpa ambang, backend memakai ambang bawaannya (dikembalikan di respons) */
  ambang?: KemiripanDraftQuery['ambang'];
  limit?: KemiripanDraftQuery['limit'];
  signal?: AbortSignal;
}

export async function getKemiripanDraft(
  documentId: number,
  { ambang, limit, signal }: GetKemiripanDraftOptions = {}
): Promise<DraftKemiripanResponse> {
  const query: KemiripanDraftQuery = {};
  if (typeof ambang === 'number') query.ambang = ambang;
  if (typeof limit === 'number') query.limit = limit;
  const qs = buildQueryString(query as Record<string, unknown>);
  return apiFetch<DraftKemiripanResponse>(`/api/v1/documents/${documentId}/kemiripan-draft${qs}`, {
    signal,
    timeout: KEMIRIPAN_TIMEOUT_MS,
  });
}

/** 409: teks draft masih diekstrak, layak dicoba ulang */
export function isSedangDiproses(err: unknown): boolean {
  return err instanceof ApiError && err.status === 409;
}

// ============================================================================
// Pesan galat
// ============================================================================

export interface PesanKemiripan {
  judul: string;
  pesan: string;
  /** 'netral' untuk keadaan yang bukan gangguan sistem (bukan draft kajian, tanpa akses, tidak ditemukan) */
  jenis: 'netral' | 'galat';
  /** Tombol "Coba lagi" hanya untuk galat jaringan, timeout, dan 5xx */
  bisaCobaLagi: boolean;
}

function kodeGalat(err: ApiError): string | null {
  const d = err.detail;
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    const code = (d as Record<string, unknown>).code;
    return typeof code === 'string' ? code : null;
  }
  return null;
}

/** Pesan ramah per status; teks teknis backend tidak diteruskan ke pengguna */
export function pesanGalatKemiripan(err: unknown): PesanKemiripan {
  if (!(err instanceof ApiError)) {
    return { judul: 'Kemiripan draft tidak dapat dimuat', pesan: 'Terjadi kesalahan tak terduga.', jenis: 'galat', bisaCobaLagi: false };
  }
  switch (err.status) {
    case 401:
      return { judul: 'Sesi berakhir', pesan: 'Sesi berakhir, silakan masuk lagi.', jenis: 'galat', bisaCobaLagi: false };
    case 403:
      return kodeGalat(err) === 'akses_ditolak'
        ? { judul: 'Akses ditolak', pesan: 'Peran Anda tidak memiliki izin melihat kemiripan draft.', jenis: 'netral', bisaCobaLagi: false }
        : { judul: 'Akses ditolak', pesan: 'Kemiripan draft non-publik baru bisa dilihat setelah fitur login aktif.', jenis: 'netral', bisaCobaLagi: false };
    case 404:
      return { judul: 'Dokumen tidak ditemukan', pesan: 'Kemiripan draft tidak tersedia karena dokumen tidak ditemukan.', jenis: 'netral', bisaCobaLagi: false };
    case 409:
      return { judul: 'Draft sedang diproses', pesan: 'Teks draft masih diekstrak, kemiripan akan dihitung setelahnya.', jenis: 'netral', bisaCobaLagi: false };
    case 422:
      // Validasi FastAPI (ambang/limit tidak valid) berbentuk array; selain itu dokumen bukan draft kajian
      return Array.isArray(err.detail)
        ? { judul: 'Permintaan tidak valid', pesan: 'Parameter kemiripan draft tidak valid.', jenis: 'galat', bisaCobaLagi: false }
        : { judul: 'Bukan draft kajian', pesan: 'Kemiripan hanya dihitung untuk dokumen draft kajian.', jenis: 'netral', bisaCobaLagi: false };
    case 0:
      return /batas waktu/i.test(err.message)
        ? { judul: 'Waktu habis', pesan: 'Perhitungan kemiripan membutuhkan waktu terlalu lama.', jenis: 'galat', bisaCobaLagi: true }
        : { judul: 'Tidak dapat terhubung', pesan: 'Tidak dapat terhubung ke peladen.', jenis: 'galat', bisaCobaLagi: true };
    default:
      return {
        judul: 'Kemiripan draft tidak dapat dimuat',
        pesan: `Terjadi gangguan di peladen (HTTP ${err.status}).`,
        jenis: 'galat',
        bisaCobaLagi: err.status >= 500,
      };
  }
}

// ============================================================================
// Format tampilan
// ============================================================================

const FORMAT_PERSEN = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 1 });
const FORMAT_TANGGAL = new Intl.DateTimeFormat('id-ID', { day: 'numeric', month: 'long', year: 'numeric' });

/**
 * Maksimal 1 desimal dengan koma Indonesia, mis. 87,5.
 * `potong: true` memotong (floor) alih-alih membulatkan, dipakai untuk status identik
 * agar 99,95 tampil "99,9" dan "100" hanya muncul bila nilainya memang 100.
 */
export function formatPersen(nilai: number | null | undefined, { potong = false }: { potong?: boolean } = {}): string {
  if (typeof nilai !== 'number' || !Number.isFinite(nilai)) return '-';
  // Epsilon menahan galat floating-point (mis. 99.9 * 10 = 998.9999…) agar tidak ikut turun
  const angka = potong ? Math.floor(nilai * 10 + 1e-9) / 10 : nilai;
  return FORMAT_PERSEN.format(angka);
}

/** Tanggal Indonesia, mis. "12 Oktober 2026"; null bila kosong atau tidak valid */
export function formatTanggalUnggah(iso: string | null | undefined): string | null {
  if (typeof iso !== 'string' || iso.trim() === '') return null;
  const t = new Date(iso);
  return Number.isNaN(t.getTime()) ? null : FORMAT_TANGGAL.format(t);
}

/** Potong judul panjang di batas kata, diakhiri elipsis */
export function potongJudul(judul: string | null | undefined, maks = 90): string {
  const teks = typeof judul === 'string' ? judul.replace(/\s+/g, ' ').trim() : '';
  if (teks.length <= maks) return teks;
  const potong = teks.slice(0, maks);
  const spasi = potong.lastIndexOf(' ');
  return `${(spasi > maks * 0.6 ? potong.slice(0, spasi) : potong).trimEnd()}…`;
}
