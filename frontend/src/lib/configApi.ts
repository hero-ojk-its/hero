/**
 * frontend/src/lib/configApi.ts
 *
 * Client API untuk mengambil konfigurasi aplikasi dari backend HERO.
 * Endpoint: GET /api/v1/konfigurasi
 */

import { apiFetch, isApiConfigured } from './api';

export interface KonfigurasiUnggah {
  max_upload_mb?: number;
  max_fetch_mb?: number;
  format_diterima?: string[];
  maks_berkas_per_unggah?: number;
}

export interface KonfigurasiResponse {
  unggah?: KonfigurasiUnggah;
  auth_enabled?: boolean;
  versi_api?: string;
  [key: string]: unknown;
}

/** Batas default ukuran upload (MB) jika endpoint konfigurasi belum siap atau data tidak valid */
export const DEFAULT_MAX_UPLOAD_MB = 25;

/** Konfigurasi fallback default */
export const DEFAULT_APP_CONFIG: KonfigurasiResponse = {
  unggah: {
    max_upload_mb: DEFAULT_MAX_UPLOAD_MB,
    max_fetch_mb: DEFAULT_MAX_UPLOAD_MB,
    format_diterima: ['pdf'],
    maks_berkas_per_unggah: 50,
  },
  auth_enabled: false,
  versi_api: '',
};

// In-memory cache singleton promise untuk menghindari request konfigurasi berulang
let configPromise: Promise<KonfigurasiResponse> | null = null;
let cachedConfig: KonfigurasiResponse | null = null;

/**
 * Mengambil konfigurasi aplikasi HERO.
 * Menggunakan in-memory caching agar hanya dipanggil satu kali per sesi,
 * dan menggunakan fallback defensif jika endpoint backend belum tersedia.
 */
export async function getAppKonfigurasi(): Promise<KonfigurasiResponse> {
  if (cachedConfig) {
    return cachedConfig;
  }

  if (configPromise) {
    return configPromise;
  }

  if (!isApiConfigured) {
    cachedConfig = DEFAULT_APP_CONFIG;
    return cachedConfig;
  }

  configPromise = (async () => {
    try {
      const res = await apiFetch<KonfigurasiResponse>('/api/v1/konfigurasi');
      if (res && typeof res === 'object') {
        const uploadMb = res.unggah?.max_upload_mb;
        const validUploadMb =
          typeof uploadMb === 'number' && Number.isFinite(uploadMb) && uploadMb > 0
            ? uploadMb
            : DEFAULT_MAX_UPLOAD_MB;

        cachedConfig = {
          ...res,
          unggah: {
            ...res.unggah,
            max_upload_mb: validUploadMb,
            format_diterima:
              Array.isArray(res.unggah?.format_diterima) && res.unggah!.format_diterima.length > 0
                ? res.unggah!.format_diterima
                : ['pdf'],
          },
        };
        return cachedConfig;
      }
      cachedConfig = DEFAULT_APP_CONFIG;
      return cachedConfig;
    } catch {
      // Backend belum mendeploy endpoint /api/v1/konfigurasi atau respons tidak dapat diurai.
      // Gunakan nilai fallback 25 MB secara defensif.
      cachedConfig = DEFAULT_APP_CONFIG;
      return cachedConfig;
    } finally {
      configPromise = null;
    }
  })();

  return configPromise;
}

/**
 * Reset cache konfigurasi (berguna untuk testing atau pembaruan konfigurasi manual).
 */
export function resetConfigCache(): void {
  configPromise = null;
  cachedConfig = null;
}

/**
 * Helper untuk mendapatkan nilai batas upload dalam MB.
 */
export function resolveMaxUploadMb(config?: KonfigurasiResponse | null): number {
  const mb = config?.unggah?.max_upload_mb;
  if (typeof mb === 'number' && Number.isFinite(mb) && mb > 0) {
    return mb;
  }
  return DEFAULT_MAX_UPLOAD_MB;
}

/**
 * Helper untuk memformat pesan galat batas berkas ramah pengguna.
 */
export function formatUploadLimitErrorMessage(limitMb: number = DEFAULT_MAX_UPLOAD_MB): string {
  return `Ukuran file melebihi batas maksimum ${limitMb} MB. Silakan pilih file yang lebih kecil.`;
}
