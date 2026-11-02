/**
 * Client API untuk administrasi HERO (Audit Log & Kelola Pengguna).
 * Mengimplementasikan pemanggilan endpoint backend dan penanganan aman HTTP 403 (Langkah 34).
 */

import { apiFetch, ApiError, buildQueryString, PESAN_AKSES_DITOLAK } from './api';
import type { components } from './openapi';

export interface AuditLogItem {
  id: number;
  timestamp?: string | null;
  user_id?: number | null;
  username?: string | null;
  action: string;
  target_resource?: string | null;
  ip_address?: string | null;
  detail?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export type UserResponse = components['schemas']['UserResponse'];

export interface AuditLogsQuery {
  action?: string | null;
  user_id?: number | null;
  target_resource?: string | null;
  mode?: 'deterministik' | 'ai' | null;
  ada_detail?: boolean | null;
  dari?: string | null;
  sampai?: string | null;
  skip?: number;
  limit?: number;
}

export interface UsersQuery {
  role?: components['schemas']['PeranPengguna'] | null;
  is_active?: boolean | null;
  skip?: number;
  limit?: number;
}

export interface AuditSummaryItem {
  [key: string]: unknown;
}

/**
 * Mengambil daftar jejak audit aktivitas (GET /api/v1/audit-logs/).
 */
export async function getAuditLogs(
  query: AuditLogsQuery = {},
  signal?: AbortSignal
): Promise<AuditLogItem[]> {
  const qs = buildQueryString(query as Record<string, unknown>);
  return apiFetch<AuditLogItem[]>(`/api/v1/audit-logs/${qs}`, { signal });
}

/**
 * Mengambil ringkasan statistik audit log per aksi (GET /api/v1/audit-logs/ringkasan).
 */
export async function getAuditSummary(signal?: AbortSignal): Promise<AuditSummaryItem[]> {
  return apiFetch<AuditSummaryItem[]>('/api/v1/audit-logs/ringkasan', { signal });
}

/**
 * Mengambil daftar akun pengguna sistem (GET /api/v1/users/).
 */
export async function getUsers(
  query: UsersQuery = {},
  signal?: AbortSignal
): Promise<UserResponse[]> {
  const qs = buildQueryString(query as Record<string, unknown>);
  return apiFetch<UserResponse[]>(`/api/v1/users/${qs}`, { signal });
}

export interface SafeErrorMessage {
  title: string;
  message: string;
  is403: boolean;
  code?: string;
}

/**
 * Mengekstrak pesan galat secara aman dari ApiError / Error,
 * menangani HTTP 403 dengan membaca detail.message dari backend bila tersedia.
 */
export function extractSafeErrorMessage(
  err: unknown,
  fallbackMessage = 'Terjadi kesalahan saat memuat data dari peladen backend.'
): SafeErrorMessage {
  if (err instanceof ApiError) {
    const detailObj =
      err.detail && typeof err.detail === 'object' && !Array.isArray(err.detail)
        ? (err.detail as Record<string, unknown>)
        : null;

    const code = typeof detailObj?.code === 'string' ? detailObj.code : undefined;
    const detailMessage = typeof detailObj?.message === 'string' ? detailObj.message : undefined;

    if (err.status === 403) {
      if (code === 'butuh_login' && detailMessage) {
        return {
          title: 'Akses Terkunci (Login Dinonaktifkan)',
          message: detailMessage,
          is403: true,
          code,
        };
      }
      if (code === 'akses_ditolak') {
        return {
          title: 'Akses Ditolak',
          message: PESAN_AKSES_DITOLAK,
          is403: true,
          code,
        };
      }
      return {
        title: 'Akses Dibatasi (HTTP 403)',
        message: detailMessage || err.message || 'Anda tidak memiliki izin untuk mengakses sumber daya ini.',
        is403: true,
        code,
      };
    }

    return {
      title: `Galat API (HTTP ${err.status})`,
      message: detailMessage || err.message || fallbackMessage,
      is403: false,
      code,
    };
  }

  if (err instanceof Error) {
    return {
      title: 'Kesalahan Sistem',
      message: err.message || fallbackMessage,
      is403: false,
    };
  }

  return {
    title: 'Gagal Memuat Data',
    message: String(err) || fallbackMessage,
    is403: false,
  };
}
