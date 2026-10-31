/**
 * Client API statistik corong ingest (Langkah 27).
 *
 * Endpoint: GET /api/v1/dashboard/corong[?format=csv]  (izin KB_BACA)
 * Respons di OpenAPI masih `unknown`; tipe di bawah mengikuti backend/app/services/corong_service.py.
 * Dihitung dengan banyak query agregat per sumber tanpa cache, jadi diambil SEKALI tanpa source_id
 * (respons sudah memuat semua sumber, unggah manual, dan total) lalu difilter di sisi klien.
 *
 * Drill-down: GET /api/v1/ingest/failures?reason_code=&source_id=  (izin KEGAGALAN_KELOLA).
 */

import { apiFetch, apiFetchBlob, ApiError } from './api';
import { getIngestFailures } from './ingestApi';
import type { FailureResponse } from './ingestApi';

/** Perhitungan corong bisa lebih lama dari batas bawaan 15 detik */
export const CORONG_TIMEOUT_MS = 30000;

// ============================================================================
// Tipe respons
// ============================================================================

/** Invarian: ditemukan = sudah_ada_di_kb + ditarik + duplikat + gagal_unduh + belum_ditarik */
export interface CorongScan {
  ditemukan: number;
  sudah_ada_di_kb: number;
  ditarik: number;
  duplikat: number;
  gagal_unduh: number;
  belum_ditarik: number;
}

/** Invarian: di_kb = menunggu_ekstraksi + terbaca + gagal_baca + lainnya */
export interface CorongDokumen {
  di_kb: number;
  tersimpan_di_kb: number;
  menunggu_ekstraksi: number;
  /** = terbaca_teks_langsung + terbaca_ocr (terindeks + perlu_koreksi) */
  terbaca: number;
  terbaca_teks_langsung: number;
  terbaca_ocr: number;
  /** Bagian dari terbaca */
  perlu_koreksi: number;
  gagal_baca: number;
  lainnya: number;
  /** Dokumen yang punya minimal satu pasal (dihitung terpisah dari terbaca) */
  terpecah_pasal: number;
  /** Dokumen yang punya minimal satu pasal ber-embedding */
  tervektor: number;
}

export interface CorongPdf {
  terproteksi: number;
  terproteksi_terbaca: number;
  hasil_pindai_ocr: number;
  /** = gagal teks_kosong_ocr + ocr_gagal */
  ocr_gagal: number;
  /** pdf_terproteksi belum diperiksa (dokumen sebelum backfill Langkah 27) */
  belum_diperiksa: number;
}

/** reason_code -> jumlah; tanpa status "diabaikan" dan tanpa duplikat */
export type GagalPerAlasan = Record<string, number>;

export interface CorongBlok {
  dokumen: CorongDokumen;
  pdf: CorongPdf;
  gagal_per_alasan: GagalPerAlasan;
  /** 0.0–100.0, 1 desimal */
  persen_terbaca: number;
}

export interface CorongSumber extends CorongBlok {
  source_id: number;
  nama: string;
  /** JenisSumber: situs_web | folder_lokal | onedrive_public (nilai lain mungkin muncul) */
  jenis: string;
  scan: CorongScan;
}

/** Unggah manual tidak punya blok scan */
export type CorongUnggahManual = CorongBlok;

export interface CorongTotal extends CorongBlok {
  /** Jumlah scan semua sumber */
  scan: CorongScan;
}

export interface DashboardCorongResponse {
  /** UTC, mis. "2026-10-30T07:34:50Z" */
  dihitung_pada: string | null;
  sumber: CorongSumber[];
  unggah_manual: CorongUnggahManual;
  /** Dokumen unik seluruh KB; jumlah semua sumber tidak sama dengan total */
  total: CorongTotal;
}

// ============================================================================
// Normalisasi: field hilang / bukan angka dianggap 0
// ============================================================================

const KUNCI_SCAN: (keyof CorongScan)[] = ['ditemukan', 'sudah_ada_di_kb', 'ditarik', 'duplikat', 'gagal_unduh', 'belum_ditarik'];
const KUNCI_DOKUMEN: (keyof CorongDokumen)[] = [
  'di_kb', 'tersimpan_di_kb', 'menunggu_ekstraksi', 'terbaca', 'terbaca_teks_langsung', 'terbaca_ocr',
  'perlu_koreksi', 'gagal_baca', 'lainnya', 'terpecah_pasal', 'tervektor',
];
const KUNCI_PDF: (keyof CorongPdf)[] = ['terproteksi', 'terproteksi_terbaca', 'hasil_pindai_ocr', 'ocr_gagal', 'belum_diperiksa'];

type Objek = Record<string, unknown>;
const objek = (v: unknown): Objek => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Objek) : {});
const angka = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0);

function isiAngka<K extends string>(kunci: K[], v: unknown): Record<K, number> {
  const o = objek(v);
  return Object.fromEntries(kunci.map((k) => [k, angka(o[k])])) as Record<K, number>;
}

function normalisasiGagal(v: unknown): GagalPerAlasan {
  return Object.fromEntries(
    Object.entries(objek(v)).filter(([k, n]) => k.trim() !== '' && angka(n) > 0).map(([k, n]) => [k, angka(n)])
  );
}

function normalisasiBlok(v: unknown): CorongBlok {
  const o = objek(v);
  return {
    dokumen: isiAngka(KUNCI_DOKUMEN, o.dokumen),
    pdf: isiAngka(KUNCI_PDF, o.pdf),
    gagal_per_alasan: normalisasiGagal(o.gagal_per_alasan),
    persen_terbaca: angka(o.persen_terbaca),
  };
}

export function normalisasiCorong(raw: unknown): DashboardCorongResponse {
  const o = objek(raw);
  const sumber = Array.isArray(o.sumber) ? o.sumber : [];
  return {
    dihitung_pada: typeof o.dihitung_pada === 'string' ? o.dihitung_pada : null,
    sumber: sumber
      .map((s) => objek(s))
      .filter((s) => typeof s.source_id === 'number')
      .map((s) => ({
        ...normalisasiBlok(s),
        source_id: s.source_id as number,
        nama: typeof s.nama === 'string' && s.nama.trim() !== '' ? s.nama : `Sumber #${s.source_id as number}`,
        jenis: typeof s.jenis === 'string' ? s.jenis : '',
        scan: isiAngka(KUNCI_SCAN, s.scan),
      })),
    unggah_manual: normalisasiBlok(o.unggah_manual),
    total: { ...normalisasiBlok(o.total), scan: isiAngka(KUNCI_SCAN, objek(o.total).scan) },
  };
}

// ============================================================================
// Pemanggilan API
// ============================================================================

export async function getDashboardCorong({ signal }: { signal?: AbortSignal } = {}): Promise<DashboardCorongResponse> {
  const raw = await apiFetch<unknown>('/api/v1/dashboard/corong', { signal, timeout: CORONG_TIMEOUT_MS });
  return normalisasiCorong(raw);
}

/** Nama cadangan bila server tidak mengirim Content-Disposition: corong-hero-YYYYMMDD.csv (tanggal lokal) */
export function namaCsvCadangan(tanggal: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `corong-hero-${tanggal.getFullYear()}${p(tanggal.getMonth() + 1)}${p(tanggal.getDate())}.csv`;
}

/** CSV lewat apiFetchBlob (token di header Authorization, bukan di URL) */
export async function unduhCorongCsv({ signal }: { signal?: AbortSignal } = {}): Promise<{ blob: Blob; namaBerkas: string }> {
  const blob = await apiFetchBlob('/api/v1/dashboard/corong?format=csv', { signal, timeout: CORONG_TIMEOUT_MS });
  const nama = typeof blob.filename === 'string' && blob.filename.trim() !== '' ? blob.filename.trim() : namaCsvCadangan();
  return { blob, namaBerkas: nama };
}

/** Status tindak lanjut yang dihitung corong: semua kecuali "diabaikan" */
const STATUS_DIHITUNG_CORONG = ['belum_ditangani', 'diproses_ulang'] as const;
export const BATAS_DRILLDOWN = 200;

export interface HasilDrilldown {
  items: FailureResponse[];
  /** Total dari backend (jumlah kedua status) */
  total: number;
}

/**
 * Daftar kegagalan untuk satu reason_code (dan sumber, bila ada). Dua request, karena corong
 * menghitung belum_ditangani + diproses_ulang, sedangkan follow_up_status=all ikut memuat "diabaikan".
 */
export async function getKegagalanDrilldown(
  { reasonCode, sourceId, signal }: { reasonCode: string; sourceId?: number | null; signal?: AbortSignal }
): Promise<HasilDrilldown> {
  const hasil = await Promise.all(
    STATUS_DIHITUNG_CORONG.map((status) =>
      getIngestFailures(
        {
          reason_code: [reasonCode],
          ...(typeof sourceId === 'number' ? { source_id: sourceId } : {}),
          follow_up_status: status,
          limit: BATAS_DRILLDOWN,
        },
        signal
      )
    )
  );
  const perId = new Map<number, FailureResponse>();
  for (const r of hasil) for (const item of r.items ?? []) if (!perId.has(item.id)) perId.set(item.id, item);
  return {
    items: [...perId.values()].sort((a, b) => b.id - a.id),
    total: hasil.reduce((n, r) => n + (typeof r.total === 'number' ? r.total : 0), 0),
  };
}

// ============================================================================
// Pesan galat & format tampilan
// ============================================================================

export interface PesanGalatCorong {
  judul: string;
  pesan: string;
  /** "Coba lagi" hanya untuk galat jaringan, timeout, dan 5xx */
  bisaCobaLagi: boolean;
}

function pesanGalat(err: unknown, pesan403: string): PesanGalatCorong {
  if (!(err instanceof ApiError)) {
    return { judul: 'Terjadi kesalahan', pesan: 'Terjadi kesalahan tak terduga.', bisaCobaLagi: false };
  }
  if (err.status === 401) return { judul: 'Sesi berakhir', pesan: 'Sesi berakhir, silakan masuk lagi.', bisaCobaLagi: false };
  if (err.status === 403) return { judul: 'Akses ditolak', pesan: pesan403, bisaCobaLagi: false };
  if (err.status === 0) {
    return /batas waktu/i.test(err.message)
      ? { judul: 'Waktu habis', pesan: 'Perhitungan membutuhkan waktu terlalu lama.', bisaCobaLagi: true }
      : { judul: 'Tidak dapat terhubung', pesan: 'Tidak dapat terhubung ke peladen.', bisaCobaLagi: true };
  }
  if (err.status >= 500) {
    return { judul: 'Gangguan peladen', pesan: `Terjadi gangguan di peladen (HTTP ${err.status}).`, bisaCobaLagi: true };
  }
  return { judul: 'Permintaan gagal', pesan: `Permintaan tidak dapat diproses (HTTP ${err.status}).`, bisaCobaLagi: false };
}

export function pesanGalatCorong(err: unknown): PesanGalatCorong {
  return pesanGalat(err, 'Peran Anda tidak memiliki izin melihat statistik corong.');
}

export function pesanGalatDrilldown(err: unknown): PesanGalatCorong {
  return pesanGalat(err, 'Peran Anda tidak memiliki izin melihat daftar kegagalan.');
}

/** Persen terhadap tahap sebelumnya (boleh > 100); null bila tahap sebelumnya 0 */
export function persenTerhadap(nilai: number, dasar: number): number | null {
  return dasar > 0 ? (nilai / dasar) * 100 : null;
}

const FORMAT_WIB = new Intl.DateTimeFormat('id-ID', {
  timeZone: 'Asia/Jakarta', day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit',
});

/** "2026-10-30T07:34:50Z" -> "30 Oktober 2026 pukul 14.34 WIB"; null bila kosong/tidak valid */
export function formatDihitungPada(iso: string | null | undefined): string | null {
  if (typeof iso !== 'string' || iso.trim() === '') return null;
  const t = new Date(iso);
  return Number.isNaN(t.getTime()) ? null : `${FORMAT_WIB.format(t)} WIB`;
}
