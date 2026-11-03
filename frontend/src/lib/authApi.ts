/**
 * Client API Autentikasi HERO untuk komunikasi dengan endpoint FastAPI (/api/v1/auth).
 * Mengimplementasikan penanganan aman HTTP 429 (Too Many Requests), 401, 403, 5xx, dan network error.
 */

import { API_BASE_URL, ApiError } from './api';

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface UserProfile {
  auth_enabled: boolean;
  username?: string;
  nama_lengkap?: string;
  unit_kerja?: string;
  role?: string;
  izin?: string[];
}

export interface AuthErrorInfo {
  title: string;
  message: string;
  status: number;
  code?: string;
  retryAfter: number | null;
  is429: boolean;
  is401: boolean;
  is403: boolean;
  is5xx: boolean;
  isNetworkError: boolean;
}

export const PESAN_FALLBACK_429 = 'Terlalu banyak percobaan login. Silakan coba kembali beberapa saat lagi.';
export const PESAN_FALLBACK_401 = 'Username atau kata sandi tidak valid. Silakan periksa kembali.';
export const PESAN_FALLBACK_5XX = 'Terjadi kesalahan pada peladen backend. Silakan coba kembali beberapa saat lagi.';
export const PESAN_FALLBACK_NETWORK = 'Gagal terhubung ke peladen backend. Pastikan server backend sedang aktif.';

/**
 * Mengekstrak informasi galat secara aman dari respons backend autentikasi.
 * Menangani HTTP 429 dengan menampilkan detail.message dari backend bila ada,
 * atau fallback tanpa mengarang durasi tunggu jika informasi tidak tersedia.
 */
export function extractAuthError(err: unknown): AuthErrorInfo {
  if (err instanceof ApiError) {
    const status = err.status;
    const retryAfter = typeof err.retryAfter === 'number' && err.retryAfter >= 0 ? err.retryAfter : null;

    const detailObj =
      err.detail && typeof err.detail === 'object' && !Array.isArray(err.detail)
        ? (err.detail as Record<string, unknown>)
        : null;

    const code = typeof detailObj?.code === 'string' ? detailObj.code : undefined;
    const detailMessage = typeof detailObj?.message === 'string' ? detailObj.message : undefined;
    const detailString =
      typeof err.detail === 'string' && err.detail.trim() && !err.detail.startsWith('API Error ')
        ? err.detail.trim()
        : undefined;

    // HTTP 429: Too Many Requests / Rate limit lockout
    if (status === 429) {
      // 1. Tampilkan pesan backend melalui detail.message atau detail string
      let message = detailMessage || detailString;

      // 2. Jika pesan backend tidak tersedia atau hanya kode/status generik, gunakan fallback ramah pengguna
      if (!message || message.startsWith('API Error 429') || message === 'Too Many Requests') {
        message = PESAN_FALLBACK_429;
      }

      return {
        title: 'Batas Percobaan Terlampaui',
        message,
        status: 429,
        code,
        retryAfter,
        is429: true,
        is401: false,
        is403: false,
        is5xx: false,
        isNetworkError: false,
      };
    }

    // HTTP 401: Unauthorized (Kredensial salah / Akun nonaktif)
    if (status === 401) {
      const message = detailMessage || detailString || PESAN_FALLBACK_401;
      return {
        title: 'Gagal Masuk',
        message,
        status: 401,
        code,
        retryAfter: null,
        is429: false,
        is401: true,
        is403: false,
        is5xx: false,
        isNetworkError: false,
      };
    }

    // HTTP 403: Forbidden (Akses Ditolak / Login Dinonaktifkan)
    if (status === 403) {
      let message = detailMessage || detailString;
      if (!message) {
        message = 'Anda tidak memiliki izin untuk mengakses sumber daya ini.';
      }
      return {
        title: 'Akses Ditolak',
        message,
        status: 403,
        code,
        retryAfter: null,
        is429: false,
        is401: false,
        is403: true,
        is5xx: false,
        isNetworkError: false,
      };
    }

    // HTTP 5xx: Server Error
    if (status >= 500) {
      let message = detailMessage || detailString;
      if (!message || message === 'Internal Server Error' || message.startsWith('API Error ')) {
        message = `${PESAN_FALLBACK_5XX} (HTTP ${status})`;
      }
      return {
        title: 'Kesalahan Peladen',
        message,
        status,
        code,
        retryAfter: null,
        is429: false,
        is401: false,
        is403: false,
        is5xx: true,
        isNetworkError: false,
      };
    }

    // Network / Timeout / status 0
    if (status === 0) {
      return {
        title: 'Koneksi Terputus',
        message: err.message || PESAN_FALLBACK_NETWORK,
        status: 0,
        code,
        retryAfter: null,
        is429: false,
        is401: false,
        is403: false,
        is5xx: false,
        isNetworkError: true,
      };
    }

    // Status lainnya
    return {
      title: `Galat Autentikasi (HTTP ${status})`,
      message: detailMessage || detailString || err.message || 'Terjadi kesalahan yang tidak terduga.',
      status,
      code,
      retryAfter,
      is429: false,
      is401: false,
      is403: false,
      is5xx: false,
      isNetworkError: false,
    };
  }

  // Error biasa / Exception DOM
  if (err instanceof Error) {
    const isNetwork =
      err.message.toLowerCase().includes('failed to fetch') ||
      err.message.toLowerCase().includes('networkerror') ||
      err.message.toLowerCase().includes('koneksi');
    return {
      title: isNetwork ? 'Koneksi Terputus' : 'Kesalahan Sistem',
      message: isNetwork ? PESAN_FALLBACK_NETWORK : err.message || 'Terjadi kesalahan pada aplikasi.',
      status: 0,
      retryAfter: null,
      is429: false,
      is401: false,
      is403: false,
      is5xx: false,
      isNetworkError: isNetwork,
    };
  }

  // Objek tak dikenal
  return {
    title: 'Gagal Masuk',
    message: String(err) || 'Terjadi kesalahan yang tidak terduga.',
    status: 0,
    retryAfter: null,
    is429: false,
    is401: false,
    is403: false,
    is5xx: false,
    isNetworkError: false,
  };
}

/**
 * Mengirim permintaan masuk pengguna ke endpoint POST /api/v1/auth/login.
 * Menggunakan format application/x-www-form-urlencoded sesuai kontrak FastAPI OAuth2PasswordRequestForm.
 */
export async function login(
  credentials: LoginCredentials,
  signal?: AbortSignal
): Promise<LoginResponse> {
  const url = `${API_BASE_URL}/api/v1/auth/login`;

  const params = new URLSearchParams();
  params.append('grant_type', 'password');
  params.append('username', credentials.username.trim());
  params.append('password', credentials.password);

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        Accept: 'application/json',
      },
      body: params.toString(),
      signal,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    const friendly =
      msg.toLowerCase().includes('failed to fetch') || msg.toLowerCase().includes('networkerror')
        ? PESAN_FALLBACK_NETWORK
        : msg;
    throw new ApiError(0, friendly);
  }

  if (!response.ok) {
    let errorDetail: unknown = null;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      try {
        const bodyData = await response.json();
        errorDetail =
          bodyData && typeof bodyData === 'object' && 'detail' in (bodyData as Record<string, unknown>)
            ? (bodyData as Record<string, unknown>).detail
            : bodyData;
      } catch {
        errorDetail = null;
      }
    } else {
      errorDetail = null;
    }

    if (!errorDetail) {
      errorDetail = response.statusText || `Galat HTTP ${response.status}`;
    }

    // Ekstrak Retry-After header secara aman
    let retryAfter: number | null = null;
    const retryHeader = response.headers.get('retry-after');
    if (retryHeader) {
      const parsedSec = Number(retryHeader);
      if (!isNaN(parsedSec) && parsedSec >= 0) {
        retryAfter = Math.round(parsedSec);
      } else {
        const parsedDate = Date.parse(retryHeader);
        if (!isNaN(parsedDate)) {
          retryAfter = Math.max(0, Math.round((parsedDate - Date.now()) / 1000));
        }
      }
    }

    throw new ApiError(response.status, errorDetail, { retryAfter, headers: response.headers });
  }

  const data = (await response.json()) as LoginResponse;

  // Simpan token ke storage lokal jika berhasil
  if (data?.access_token && typeof window !== 'undefined') {
    localStorage.setItem('hero_token', data.access_token);
  }

  return data;
}

/**
 * Mengambil profil pengguna aktif dan hak akses dari endpoint GET /api/v1/auth/me.
 */
export async function getMe(signal?: AbortSignal): Promise<UserProfile> {
  const url = `${API_BASE_URL}/api/v1/auth/me`;
  const token = getStoredToken();

  const headers: Record<string, string> = {
    Accept: 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'GET',
      headers,
      signal,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new ApiError(0, msg || PESAN_FALLBACK_NETWORK);
  }

  if (!response.ok) {
    let errorDetail: unknown = null;
    try {
      const bodyData = await response.json();
      errorDetail =
        bodyData && typeof bodyData === 'object' && 'detail' in (bodyData as Record<string, unknown>)
          ? (bodyData as Record<string, unknown>).detail
          : bodyData;
    } catch {
      errorDetail = response.statusText;
    }
    throw new ApiError(response.status, errorDetail);
  }

  return (await response.json()) as UserProfile;
}

/**
 * Menghapus token dari seluruh ruang penyimpanan browser.
 */
export function logout(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem('hero_token');
    localStorage.removeItem('token');
    localStorage.removeItem('auth_token');
    sessionStorage.removeItem('hero_token');
    sessionStorage.removeItem('token');
  } catch {
    // Abaikan jika storage diblokir
  }
}

/**
 * Mengambil token autentikasi yang tersimpan di browser.
 */
export function getStoredToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return (
      localStorage.getItem('hero_token') ||
      localStorage.getItem('token') ||
      localStorage.getItem('auth_token') ||
      sessionStorage.getItem('hero_token') ||
      sessionStorage.getItem('token')
    );
  } catch {
    return null;
  }
}
