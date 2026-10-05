/**
 * Client API HERO untuk komunikasi dengan Backend FastAPI.
 */

export interface ValidationErrorItem {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
}

export class ApiError extends Error {
  status: number;
  detail: string | ValidationErrorItem[] | unknown;

  constructor(status: number, detail: string | ValidationErrorItem[] | unknown) {
    let formattedMessage = `API Error ${status}`;
    if (typeof detail === 'string') {
      formattedMessage = detail;
    } else if (Array.isArray(detail)) {
      // Menangani format error validasi FastAPI (HTTP 422)
      formattedMessage = detail
        .map((item) => {
          if (typeof item === 'string') return item;
          if (item && typeof item === 'object' && 'msg' in item) {
            const loc = Array.isArray(item.loc) && item.loc.length > 0 ? `${item.loc.join('.')}: ` : '';
            return `${loc}${item.msg}`;
          }
          return JSON.stringify(item);
        })
        .join('; ');
    } else if (detail && typeof detail === 'object') {
      const obj = detail as Record<string, unknown>;
      if (typeof obj.message === 'string') {
        formattedMessage = obj.message;
      } else if (typeof obj.detail === 'string') {
        formattedMessage = obj.detail;
      } else {
        formattedMessage = JSON.stringify(detail);
      }
    }

    super(formattedMessage);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

const rawBaseUrl = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) || '';
export const API_BASE_URL = rawBaseUrl.replace(/\/+$/, '');
export const isApiConfigured: boolean = Boolean(rawBaseUrl && rawBaseUrl.trim() !== '');

export interface FetchOptions extends RequestInit {
  timeout?: number;
}

/**
 * Mengambil token autentikasi jika tersedia di browser storage.
 */
function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  return (
    localStorage.getItem('hero_token') ||
    localStorage.getItem('token') ||
    localStorage.getItem('auth_token') ||
    sessionStorage.getItem('hero_token') ||
    sessionStorage.getItem('token')
  );
}

/**
 * Helper untuk mengekstrak nama berkas dari header Content-Disposition.
 */
export function parseContentDispositionFilename(header: string | null): string | undefined {
  if (!header) return undefined;
  // RFC 5987 / RFC 6266: filename*=UTF-8''filename.ext
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match && utf8Match[1]) {
    try {
      return decodeURIComponent(utf8Match[1].trim());
    } catch {
      // fallback
    }
  }
  // Format standar: filename="filename.ext"
  const quotedMatch = header.match(/filename="([^"]+)"/i);
  if (quotedMatch && quotedMatch[1]) {
    return quotedMatch[1].trim();
  }
  // Format tanpa kutip: filename=filename.ext
  const simpleMatch = header.match(/filename=([^;]+)/i);
  if (simpleMatch && simpleMatch[1]) {
    return simpleMatch[1].trim();
  }
  return undefined;
}

/**
 * Eksekutor fetch bersama untuk apiFetch dan apiFetchBlob.
 * Menangani URL resolution, timeout, authorization, dan listener cleanup.
 */
async function prepareAndFetchResponse(
  endpoint: string,
  options: FetchOptions = {},
  defaultAccept: string = 'application/json'
): Promise<Response> {
  const { timeout = 15000, signal, headers: customHeaders, ...fetchOpts } = options;

  const url = endpoint.startsWith('http://') || endpoint.startsWith('https://')
    ? endpoint
    : `${API_BASE_URL}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;

  const headers = new Headers(customHeaders);
  if (!headers.has('Accept')) {
    headers.set('Accept', defaultAccept);
  }

  // Header Authorization bila token ada (login ditunda; auth backend nonaktif)
  const token = getAuthToken();
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  // Pengaturan Timeout dengan AbortController
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort(new Error(`Permintaan ke ${url} melebihi batas waktu (${timeout} ms)`));
  }, timeout);

  const onExternalAbort = () => {
    clearTimeout(timeoutId);
    controller.abort(signal?.reason);
  };

  // Jika ada signal eksternal, dengarkan pembatalannya
  if (signal) {
    if (signal.aborted) {
      clearTimeout(timeoutId);
      controller.abort(signal.reason);
    } else {
      signal.addEventListener('abort', onExternalAbort);
    }
  }

  try {
    const response = await fetch(url, {
      ...fetchOpts,
      headers,
      signal: controller.signal,
    });

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
        // Jangan tampilkan isi HTML/teks mentah ke pengguna (mis. 405 dari GitHub Pages).
        // Gunakan pesan ringkas berdasarkan status HTTP saja.
        errorDetail = null;
      }

      if (!errorDetail) {
        errorDetail = response.statusText || `Galat HTTP ${response.status}`;
      }

      throw new ApiError(response.status, errorDetail);
    }

    return response;
  } catch (error: unknown) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error;
    }
    if (error instanceof Error && error.name === 'AbortError') {
      throw error;
    }
    const message = error instanceof Error ? error.message : String(error);
    const friendlyMessage =
      message.toLowerCase().includes('failed to fetch') || message.toLowerCase().includes('fetch failed')
        ? 'Gagal terhubung ke peladen backend. Pastikan server backend sedang aktif di ' + (API_BASE_URL || 'http://localhost:8000') + '.'
        : message || 'Gagal terhubung ke peladen API backend.';
    throw new ApiError(0, friendlyMessage);
  } finally {
    clearTimeout(timeoutId);
    if (signal) {
      signal.removeEventListener('abort', onExternalAbort);
    }
  }
}

/**
 * Klien fetch seragam untuk backend FastAPI (mengembalikan JSON atau text).
 */
export async function apiFetch<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
  const response = await prepareAndFetchResponse(endpoint, options, 'application/json');
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return (await response.json()) as T;
  }
  return (await response.text()) as unknown as T;
}

/**
 * Helper untuk request JSON (POST, PUT, PATCH, DELETE) yang otomatis memasang Content-Type: application/json.
 */
export async function apiJson<T>(
  method: string,
  endpoint: string,
  body?: unknown,
  options: FetchOptions = {}
): Promise<T> {
  const headers = new Headers(options.headers);
  if (body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  return apiFetch<T>(endpoint, {
    ...options,
    method,
    headers,
    body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
  });
}

export interface DocumentBlob extends Blob {
  filename?: string;
  contentType?: string;
}

/**
 * Klien fetch untuk mengunduh atau membaca berkas biner (Blob) seperti PDF.
 * Menyertakan nama berkas dari header Content-Disposition jika tersedia.
 */
export async function apiFetchBlob(endpoint: string, options: FetchOptions = {}): Promise<DocumentBlob> {
  const response = await prepareAndFetchResponse(
    endpoint,
    options,
    'application/pdf, application/octet-stream, */*'
  );
  const blob = (await response.blob()) as DocumentBlob;
  const contentDisposition = response.headers.get('content-disposition');
  blob.filename = parseContentDispositionFilename(contentDisposition);
  blob.contentType = response.headers.get('content-type') || 'application/pdf';
  return blob;
}

export interface DocumentTextResponse {
  document_id: number;
  total_length: number;
  offset: number;
  limit: number;
  text: string;
  extraction_method?: string | null;
  extraction_engine?: string | null;
  extracted_at?: string | null;
}

/**
 * Membantu membuat query string yang valid untuk endpoint FastAPI.
 */
export function buildQueryString(params: Record<string, unknown>): string {
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') {
      continue;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item !== null && item !== undefined && item !== '') {
          searchParams.append(key, String(item));
        }
      }
    } else {
      searchParams.append(key, String(value));
    }
  }

  const qs = searchParams.toString();
  return qs ? `?${qs}` : '';
}

// -------------------------------------------------------------
// Tipe Data Kontrak API HERO
// -------------------------------------------------------------

export interface DocumentItem {
  id: number;
  title: string;
  regulation_number: string | null;
  regulation_type: string | null;
  release_date: string | null;
  regulation_year?: number | null;
  bidang: string | null;
  access_classification?: 'publik' | 'non_publik' | string | null;
  document_role?: 'corpus_eksisting' | 'draft_kajian' | string | null;
  category_id: number | null;
  category_path: string[] | null;
  status_keberlakuan: 'berlaku' | 'diubah' | 'dicabut' | 'tidak_diketahui' | string;
  processing_status: 'diterima' | 'diproses' | 'perlu_koreksi' | 'terindeks' | 'gagal' | 'ditolak' | string;
  file_size_bytes: number | null;
  source_url: string | null;
  pdf_url: string;
  is_placed: boolean;
  restricted: boolean;
  created_at: string;
  updated_at?: string | null;
  standardized_filename?: string | null;
  original_filename?: string | null;
  file_hash?: string | null;
  file_path_pdf?: string | null;
  rank?: number | null;
  highlight?: string | null;
}

export interface DocumentsResponse {
  total: number;
  items: DocumentItem[];
  query?: Record<string, unknown>;
}

export interface CategoryNode {
  id: number;
  name: string;
  parent_id: number | null;
  auto_created?: boolean;
  document_count: number;
  total_document_count: number;
  children: CategoryNode[];
}

export interface DashboardSummaryResponse {
  kb: {
    corpus_documents: number;
    draft_documents: number;
    target_fase1: number;
    target_met: boolean;
    by_status_keberlakuan: {
      berlaku?: number;
      diubah?: number;
      dicabut?: number;
      tidak_diketahui?: number;
      [key: string]: number | undefined;
    };
    by_processing_status: {
      diterima?: number;
      diproses?: number;
      perlu_koreksi?: number;
      terindeks?: number;
      gagal?: number;
      ditolak?: number;
      [key: string]: number | undefined;
    };
    by_regulation_type: Array<{
      regulation_type: string | null;
      label: string;
      count: number;
    }>;
    by_year: Array<{
      year: number | null;
      label: string;
      count: number;
    }>;
    placed_documents: number;
    inbox_documents: number;
  };
  ingest: {
    open_failures: number;
    needs_review: number;
    active_scans: number;
    recent_jobs: Array<{
      id: number;
      job_type: string;
      status: string;
      started_at: string;
      finished_at?: string | null;
      success_count: number;
      duplicate_count: number;
      skipped_count: number;
      failed_count: number;
      processed_count: number;
      total_found: number;
    }>;
  };
  sources?: {
    total: number;
    active: number;
    by_type: Record<string, number>;
  };
  generated_at?: string;
}

export interface AdaptedRegulasiDoc {
  id: number;
  judul: string;
  jenis: string;
  nomor: string;
  kategori: string;
  topik: string;
  tahun: number | string;
  status: string;
  sumber: string;
  ukuran?: string;
  sha256?: string;
  tanggalPublikasi?: string;
}

/**
 * Format ukuran byte menjadi B, KB, atau MB. Mengembalikan '-' jika tidak ada atau tidak valid.
 */
export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || isNaN(bytes) || bytes <= 0) {
    return '-';
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Mengadaptasi DocumentItem dari Backend API menjadi model data untuk DetailDokumen.
 * Menghilangkan nilai karangan (fallback fiktif):
 * - sumber: nilai asli backend atau '-' jika tidak ada.
 * - tahun: tahun dari release_date atau created_at, atau '-' jika keduanya kosong.
 * - ukuran: format nyata dari file_size_bytes atau '-' jika tidak ada.
 */
export function adaptDocumentToDetail(doc: DocumentItem): AdaptedRegulasiDoc {
  let tahun: number | string = '-';
  if (doc.release_date) {
    const d = new Date(doc.release_date);
    if (!isNaN(d.getTime())) {
      tahun = d.getFullYear();
    }
  }
  // Bila release_date kosong, gunakan regulation_year; bila kosong juga, '-' (JANGAN gunakan created_at)
  if (tahun === '-' && doc.regulation_year !== null && doc.regulation_year !== undefined) {
    tahun = doc.regulation_year;
  }

  let tanggalPublikasi: string | undefined = undefined;
  if (doc.release_date) {
    try {
      const d = new Date(doc.release_date);
      if (!isNaN(d.getTime())) {
        tanggalPublikasi = d.toLocaleDateString('id-ID', {
          day: 'numeric',
          month: 'long',
          year: 'numeric',
        });
      }
    } catch {
      tanggalPublikasi = doc.release_date;
    }
  }

  const statusMap: Record<string, string> = {
    berlaku: 'Aktif',
    diubah: 'Diubah',
    dicabut: 'Dicabut',
    tidak_diketahui: 'Tidak diketahui',
  };

  return {
    id: doc.id,
    judul: doc.title || '-',
    jenis: doc.regulation_type || '-',
    nomor: doc.regulation_number || '-',
    kategori:
      doc.category_path && doc.category_path.length > 0
        ? doc.category_path.join(' / ')
        : doc.bidang || '-',
    topik: doc.bidang || '-',
    tahun,
    tanggalPublikasi,
    status: statusMap[doc.status_keberlakuan] || doc.status_keberlakuan || 'Tidak diketahui',
    sumber: doc.source_url || '-',
    ukuran: formatFileSize(doc.file_size_bytes),
    sha256: doc.file_hash || undefined,
  };
}

