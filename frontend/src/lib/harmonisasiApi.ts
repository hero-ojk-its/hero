/**
 * Client API Harmonisasi HERO (draft vs korpus, per pasal).
 *
 * Endpoint: POST /api/v1/ml/harmonisasi/{document_id}?segar=
 * - Query & body diambil dari tipe hasil gen:api (operations).
 * - Respons di OpenAPI masih `unknown`, jadi tipenya ditulis di sini mengikuti kode yang membentuknya:
 *   pipeline/hero/harmonisasi/engine.py (Finding, Report), pipeline/hero/bridge/ml_api.py (_rewrite_refs:
 *   doc_id -> document_id, pdf -> /api/v1/documents/{id}/pdf#page=N), dan backend/app/routers/ml_gateway.py
 *   (disaring_backend, cache, penyaringan temuan yang pembandingnya tidak boleh diakses).
 */

import { apiJson, ApiError, buildQueryString } from './api';
import { ANALISA_TIMEOUT_MS, ML_API_BASE_URL } from './analisaApi';
import type { MlAnalisaCache } from './analisaApi';
import type { operations } from './openapi';

type HarmonisasiOperation = operations['post_ml_harmonisasi_api_v1_ml_harmonisasi__document_id__post'];
export type HarmonisasiQuery = NonNullable<HarmonisasiOperation['parameters']['query']>;
/** Daftar document_id pembanding; null = seluruh korpus yang boleh diakses */
export type HarmonisasiBody = NonNullable<HarmonisasiOperation['requestBody']>['content']['application/json'];

// ============================================================================
// Tipe respons
// ============================================================================

export type JenisTemuan = 'pasal_baru' | 'duplikasi' | 'menggantikan' | 'memperjelas' | 'konflik';
export const JENIS_TEMUAN: readonly JenisTemuan[] = ['pasal_baru', 'duplikasi', 'menggantikan', 'memperjelas', 'konflik'];

export interface HarmonisasiBadge {
  value?: string | null;
  label?: string | null;
  /** Pipeline: success|neutral|warning|info|danger; dokumen kontrak: green|slate|amber|blue|red */
  tone?: string | null;
}

export interface HarmonisasiPembanding {
  document_id?: number | null;
  doc_id?: string | null;
  key?: string | null;
  judul?: string | null;
  nomor?: string | null;
  status?: string | null;
  pasal?: string | null;
  halaman?: number | null;
  kutipan?: string | null;
  /** Relatif, mis. "/api/v1/documents/2/pdf#page=10"; null bila dokumen tidak terpeta ke backend */
  pdf?: string | null;
}

export interface HarmonisasiAlternatif {
  document_id?: number | null;
  judul?: string | null;
  pasal?: string | null;
  kemiripan?: number | null;
}

export interface HarmonisasiTemuan {
  pasal_draft: string;
  halaman_draft?: number | null;
  kutipan_draft?: string | null;
  jenis: JenisTemuan | string;
  badge?: HarmonisasiBadge | null;
  keyakinan?: number | null;
  tingkat?: 'tinggi' | 'sedang' | 'rendah' | string | null;
  alasan?: string | null;
  /** null untuk pasal_baru */
  pembanding?: HarmonisasiPembanding | null;
  kemiripan?: number | null;
  perbedaan?: string[] | null;
  alternatif?: HarmonisasiAlternatif[] | null;
  klausul_baku?: boolean | null;
  /** Untuk audit/kalibrasi ambang, tidak ditampilkan */
  terdekat?: unknown;
}

export interface HarmonisasiRencanaPerubahan {
  diubah?: string[];
  disisipkan?: string[];
  dihapus?: string[];
}

export interface HarmonisasiRingkasan {
  pasal_draft?: number;
  pasal_korpus?: number;
  dokumen_korpus?: number;
  /** Dihitung pipeline SEBELUM penyaringan akses; jangan dipakai untuk angka kartu */
  per_jenis?: Record<string, number>;
  rujukan?: number;
  rujukan_dicabut?: number;
  /** null bila draft tidak memuat instruksi perubahan */
  rencana_perubahan?: HarmonisasiRencanaPerubahan | null;
}

export interface HarmonisasiDraft {
  judul?: string | null;
  key?: string | null;
  document_id?: number | null;
  doc_id?: string | null;
  sumber?: string | null;
  pasal?: number | null;
}

export interface HarmonisasiKandidat {
  document_id?: number | null;
  doc_id?: string | null;
  judul?: string | null;
  skor?: number | null;
  pasal_mirip?: string[] | null;
  relasi?: string | null;
}

export interface HarmonisasiRujukan {
  key?: string | null;
  teks?: string | null;
  relasi?: string | null;
  status?: string | null;
  document_id?: number | null;
  diganti_oleh?: unknown;
}

export interface HarmonisasiResponse {
  versi?: string;
  draft?: HarmonisasiDraft | null;
  kandidat?: HarmonisasiKandidat[] | null;
  rujukan?: HarmonisasiRujukan[] | null;
  temuan?: HarmonisasiTemuan[] | null;
  ringkasan?: HarmonisasiRingkasan | null;
  rekomendasi?: string[] | null;
  kandidat_register?: unknown[] | null;
  catatan?: string | null;
  waktu_detik?: number | null;
  /** Jumlah item yang disaring gateway karena hak akses */
  disaring_backend?: number;
  cache?: MlAnalisaCache;
}

// ============================================================================
// Pemanggilan API
// ============================================================================

export interface PostHarmonisasiOptions {
  pembanding?: HarmonisasiBody;
  segar?: boolean;
  signal?: AbortSignal;
}

export async function postHarmonisasi(
  documentId: number,
  { pembanding = null, segar = false, signal }: PostHarmonisasiOptions = {}
): Promise<HarmonisasiResponse> {
  const query: HarmonisasiQuery = {};
  if (segar) query.segar = true;
  const qs = buildQueryString(query as Record<string, unknown>);
  return apiJson<HarmonisasiResponse>('POST', `${ML_API_BASE_URL}/harmonisasi/${documentId}${qs}`, pembanding, {
    signal,
    timeout: ANALISA_TIMEOUT_MS,
  });
}

// ============================================================================
// Label & tone tampilan
// ============================================================================

const LABEL_JENIS: Record<JenisTemuan, string> = {
  pasal_baru: 'Baru',
  duplikasi: 'Sama',
  menggantikan: 'Menggantikan',
  memperjelas: 'Melengkapi',
  konflik: 'Konflik',
};

export function isJenisTemuan(jenis: unknown): jenis is JenisTemuan {
  return typeof jenis === 'string' && (JENIS_TEMUAN as readonly string[]).includes(jenis);
}

/** Label dari jenis; badge.label backend hanya cadangan untuk jenis tak dikenal */
export function labelTemuan(temuan: Pick<HarmonisasiTemuan, 'jenis' | 'badge'>): string {
  if (isJenisTemuan(temuan.jenis)) return LABEL_JENIS[temuan.jenis];
  const cadangan = temuan.badge?.label;
  if (typeof cadangan === 'string' && cadangan.trim() !== '') return cadangan.trim();
  return typeof temuan.jenis === 'string' && temuan.jenis.trim() !== '' ? temuan.jenis : 'Tidak dikenal';
}

export type WarnaTemuan = 'hijau' | 'biru' | 'amber' | 'merah' | 'netral';

/** Kedua kosakata tone: pipeline (success/info/...) dan dokumen kontrak (green/blue/...) */
const WARNA_TONE: Record<string, WarnaTemuan> = {
  success: 'hijau', green: 'hijau',
  info: 'biru', blue: 'biru',
  warning: 'amber', amber: 'amber',
  danger: 'merah', red: 'merah',
  neutral: 'netral', slate: 'netral', gray: 'netral', grey: 'netral',
};

const WARNA_JENIS: Record<JenisTemuan, WarnaTemuan> = {
  pasal_baru: 'hijau',
  memperjelas: 'biru',
  menggantikan: 'amber',
  konflik: 'merah',
  duplikasi: 'netral',
};

/**
 * Konflik selalu merah. Selain itu: tone backend bila dikenal, lalu warna bawaan jenis,
 * dan netral untuk jenis maupun tone yang tidak dikenal.
 */
export function warnaTemuan(temuan: Pick<HarmonisasiTemuan, 'jenis' | 'badge'>): WarnaTemuan {
  if (temuan.jenis === 'konflik') return 'merah';
  const tone = typeof temuan.badge?.tone === 'string' ? temuan.badge.tone.trim().toLowerCase() : '';
  if (WARNA_TONE[tone]) return WARNA_TONE[tone];
  if (isJenisTemuan(temuan.jenis)) return WARNA_JENIS[temuan.jenis];
  return 'netral';
}

// ============================================================================
// Pesan galat
// ============================================================================

export interface PesanGalat {
  judul: string;
  pesan: string;
}

function kodeGalat(err: ApiError): string | null {
  const d = err.detail;
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    const code = (d as Record<string, unknown>).code;
    return typeof code === 'string' ? code : null;
  }
  return null;
}

/**
 * Pesan ramah per kode galat gateway. Teks teknis dari layanan ML (mis. perintah
 * 'hero bridge sinkron') tidak diteruskan ke pengguna.
 */
export function pesanGalatHarmonisasi(err: unknown): PesanGalat {
  if (!(err instanceof ApiError)) {
    return { judul: 'Harmonisasi gagal', pesan: 'Terjadi kesalahan tak terduga. Silakan coba lagi.' };
  }
  const kode = kodeGalat(err);
  const teks = typeof err.detail === 'string' ? err.detail : '';

  switch (err.status) {
    case 401:
      return { judul: 'Sesi berakhir', pesan: 'Sesi berakhir, silakan masuk lagi.' };
    case 403:
      if (kode === 'akses_ditolak') {
        return { judul: 'Akses ditolak', pesan: 'Peran Anda tidak memiliki izin untuk menjalankan harmonisasi.' };
      }
      return { judul: 'Akses ditolak', pesan: 'Dokumen non-publik baru bisa diharmonisasi setelah fitur login aktif.' };
    case 404:
      if (kode === 'dokumen_nonaktif') {
        return { judul: 'Dokumen nonaktif', pesan: 'Dokumen ini sudah dinonaktifkan sehingga tidak dapat diharmonisasi.' };
      }
      if (teks === 'Dokumen tidak ditemukan') {
        return { judul: 'Dokumen tidak ditemukan', pesan: 'Dokumen tidak ditemukan di peladen.' };
      }
      return {
        judul: 'Dokumen belum siap dianalisa',
        pesan: 'Naskah draf belum tersedia di layanan analisa. Coba lagi beberapa saat lagi atau hubungi admin.',
      };
    case 422:
      if (kode === 'pembanding_kosong') {
        return { judul: 'Tidak ada pembanding', pesan: 'Belum ada dokumen pembanding yang dapat Anda akses untuk harmonisasi.' };
      }
      return { judul: 'Permintaan tidak valid', pesan: 'Parameter permintaan harmonisasi tidak valid.' };
    case 502:
      return { judul: 'Jawaban tidak terbaca', pesan: 'Layanan analisa mengirim jawaban yang tidak dapat dibaca. Coba lagi nanti.' };
    case 503:
      return { judul: 'Layanan analisa tidak tersedia', pesan: 'Layanan analisa sedang tidak tersedia. Coba lagi beberapa saat lagi.' };
    case 504:
      return { judul: 'Waktu habis', pesan: 'Harmonisasi membutuhkan waktu terlalu lama. Coba lagi nanti.' };
    case 0:
      if (/batas waktu/i.test(err.message)) {
        return { judul: 'Waktu habis', pesan: 'Harmonisasi membutuhkan waktu terlalu lama. Coba lagi nanti.' };
      }
      return { judul: 'Tidak dapat terhubung', pesan: 'Tidak dapat terhubung ke peladen. Periksa koneksi lalu coba lagi.' };
    default:
      return { judul: 'Harmonisasi gagal', pesan: `Harmonisasi gagal dijalankan (HTTP ${err.status}). Silakan coba lagi.` };
  }
}
