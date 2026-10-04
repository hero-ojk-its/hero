import { apiFetch, apiJson, apiFetchBlob, buildQueryString, type DocumentBlob } from './api';
import type { components } from './openapi';

// Re-export core schema types directly from openapi
export type ScrapingSourceCreate = components['schemas']['ScrapingSourceCreate'];
export type ScrapingSourceResponse = components['schemas']['ScrapingSourceResponse'];
export type ScrapingSourceUpdate = components['schemas']['ScrapingSourceUpdate'];
export type ScrapingSourceRunRequest = components['schemas']['ScrapingSourceRunRequest'];

export type ScanCreate = components['schemas']['ScanCreate'];
export type ScanSessionResponse = components['schemas']['ScanSessionResponse'];
export type ScanListResponse = components['schemas']['ScanListResponse'];
export type ScanSummaryCount = components['schemas']['ScanSummaryCount'];
export type ScanSelectionUpdate = components['schemas']['ScanSelectionUpdate'];
export type ScanSelectionResponse = components['schemas']['ScanSelectionResponse'];
export type ScanPullRequest = components['schemas']['ScanPullRequest'];
export type PullProgress = components['schemas']['PullProgress'];
export type RejectedSelection = components['schemas']['RejectedSelection'];

export type CandidateListResponse = components['schemas']['CandidateListResponse'];
export type CandidateResponse = components['schemas']['CandidateResponse'];
export type CandidateMatchDocument = components['schemas']['CandidateMatchDocument'];

export type NamingComponentsResponse = components['schemas']['NamingComponentsResponse'];
export type NamingComponentItem = components['schemas']['NamingComponentItem'];
export type NamingPreviewRequest = components['schemas']['NamingPreviewRequest'];
export type NamingPreviewResponse = components['schemas']['NamingPreviewResponse'];
export type NamingSampleInput = components['schemas']['NamingSampleInput'];

export type CategoryDetailResponse = components['schemas']['CategoryDetailResponse'];

export type JenisSumber = components['schemas']['JenisSumber'];
export type StatusPindai = components['schemas']['StatusPindai'];
export type StatusKandidat = components['schemas']['StatusKandidat'];
export type TujuanTarik = components['schemas']['TujuanTarik'];
export type KlasifikasiAkses = components['schemas']['KlasifikasiAkses'];
export type PeranDokumen = components['schemas']['PeranDokumen'];

export interface ScanPullAcceptedResponse {
  job_id?: number;
  status: string;
  message: string;
}

export interface CandidateQueryParams {
  skip?: number;
  limit?: number;
  match_status?: string;
  doc_kind?: string;
  selected?: boolean;
  q?: string;
}

// ============================================================================
// 1. Scraping Sources API (/api/v1/scraping-sources/)
// ============================================================================

export async function getScrapingSources(signal?: AbortSignal): Promise<ScrapingSourceResponse[]> {
  return apiFetch<ScrapingSourceResponse[]>('/api/v1/scraping-sources/', { signal });
}

export async function createScrapingSource(
  body: ScrapingSourceCreate,
  signal?: AbortSignal
): Promise<ScrapingSourceResponse> {
  return apiJson<ScrapingSourceResponse>('POST', '/api/v1/scraping-sources/', body, { signal });
}

export async function getScrapingSource(
  sourceId: number,
  signal?: AbortSignal
): Promise<ScrapingSourceResponse> {
  return apiFetch<ScrapingSourceResponse>(`/api/v1/scraping-sources/${sourceId}`, { signal });
}

export async function updateScrapingSource(
  sourceId: number,
  body: ScrapingSourceUpdate,
  signal?: AbortSignal
): Promise<ScrapingSourceResponse> {
  return apiJson<ScrapingSourceResponse>('PATCH', `/api/v1/scraping-sources/${sourceId}`, body, { signal });
}

export async function deleteScrapingSource(
  sourceId: number,
  signal?: AbortSignal
): Promise<{ message?: string }> {
  return apiJson<{ message?: string }>('DELETE', `/api/v1/scraping-sources/${sourceId}`, undefined, { signal });
}

export async function runScrapingSource(
  sourceId: number,
  body?: ScrapingSourceRunRequest,
  signal?: AbortSignal
): Promise<ScanSessionResponse> {
  return apiJson<ScanSessionResponse>('POST', `/api/v1/scraping-sources/${sourceId}/run`, body || {}, { signal });
}

// ============================================================================
// 2. Scans API (/api/v1/scans/)
// ============================================================================

export async function createScan(
  body: ScanCreate,
  signal?: AbortSignal
): Promise<{ scan_id: number; status: string; message: string }> {
  return apiJson<{ scan_id: number; status: string; message: string }>('POST', '/api/v1/scans/', body, { signal });
}

export async function getScan(
  scanId: number,
  signal?: AbortSignal
): Promise<ScanSessionResponse> {
  return apiFetch<ScanSessionResponse>(`/api/v1/scans/${scanId}`, { signal });
}

export async function listScans(
  params?: { limit?: number; skip?: number },
  signal?: AbortSignal
): Promise<ScanListResponse> {
  const qs = params ? buildQueryString(params) : '';
  return apiFetch<ScanListResponse>(`/api/v1/scans/${qs}`, { signal });
}

export async function cancelScan(
  scanId: number,
  signal?: AbortSignal
): Promise<ScanSessionResponse> {
  return apiJson<ScanSessionResponse>('POST', `/api/v1/scans/${scanId}/cancel`, undefined, { signal });
}

export async function getScanCandidates(
  scanId: number,
  params?: CandidateQueryParams,
  signal?: AbortSignal
): Promise<CandidateListResponse> {
  const qs = params ? buildQueryString(params as Record<string, unknown>) : '';
  return apiFetch<CandidateListResponse>(`/api/v1/scans/${scanId}/candidates${qs}`, { signal });
}

export async function updateScanSelection(
  scanId: number,
  body: ScanSelectionUpdate,
  signal?: AbortSignal
): Promise<ScanSelectionResponse> {
  return apiJson<ScanSelectionResponse>('PATCH', `/api/v1/scans/${scanId}/selection`, body, { signal });
}

export async function startScanPull(
  scanId: number,
  body: ScanPullRequest,
  wait: boolean = false,
  signal?: AbortSignal
): Promise<ScanPullAcceptedResponse | ScanSessionResponse> {
  const qs = wait ? '?wait=true' : '';
  return apiJson<ScanPullAcceptedResponse | ScanSessionResponse>(
    'POST',
    `/api/v1/scans/${scanId}/pull${qs}`,
    body,
    { signal }
  );
}

export async function downloadScanZip(
  scanId: number,
  signal?: AbortSignal
): Promise<DocumentBlob> {
  return apiFetchBlob(`/api/v1/scans/${scanId}/download`, { signal });
}

// ============================================================================
// 3. Naming Format API (/api/v1/naming/)
// ============================================================================

export async function getNamingComponents(signal?: AbortSignal): Promise<NamingComponentsResponse> {
  return apiFetch<NamingComponentsResponse>('/api/v1/naming/components', { signal });
}

export async function previewNaming(
  body: NamingPreviewRequest,
  signal?: AbortSignal
): Promise<NamingPreviewResponse> {
  return apiJson<NamingPreviewResponse>('POST', '/api/v1/naming/preview', body, { signal });
}

// ============================================================================
// 4. Categories API (/api/v1/categories/)
// ============================================================================

export async function getCategories(signal?: AbortSignal): Promise<CategoryDetailResponse[]> {
  return apiFetch<CategoryDetailResponse[]>('/api/v1/categories/', { signal });
}

// ============================================================================
// 5. Ingest Upload & Duplicate Check API (/api/v1/ingest/)
// ============================================================================

export type IngestUploadResponse = components['schemas']['IngestUploadResponse'];
export type IngestItemDetailResponse = components['schemas']['IngestItemDetailResponse'];
export type DuplicateCheckResponse = components['schemas']['DuplicateCheckResponse'];

export interface IngestJobItem {
  id: number;
  job_type: string;
  source_ref?: string | null;
  source_id?: number | null;
  status: string;
  started_at: string;
  finished_at?: string | null;
  success_count: number;
  duplicate_count: number;
  failed_count: number;
  total_found?: number | null;
  processed_count?: number;
  skipped_count?: number;
  open_failures_count?: number;
}

export interface IngestJobListResponse {
  total: number;
  items: IngestJobItem[];
}

export interface IngestJobQueryParams {
  skip?: number;
  limit?: number;
  status?: string;
  job_type?: string;
  source_id?: number;
}

/**
 * Menghitung hash SHA-256 dari berkas menggunakan Web Crypto API.
 * Mengembalikan string heksadesimal jika berhasil, atau null jika crypto.subtle tidak tersedia / gagal.
 */
export async function calculateFileHash(file: File): Promise<string | null> {
  if (typeof window === 'undefined' || !window.crypto || !window.crypto.subtle) {
    return null;
  }
  try {
    const arrayBuffer = await file.arrayBuffer();
    const hashBuffer = await window.crypto.subtle.digest('SHA-256', arrayBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  } catch (err) {
    console.warn('Gagal menghitung SHA-256 berkas:', err);
    return null;
  }
}

/**
 * Pengecekan pra-unggah duplikasi berkas via GET /api/v1/ingest/check-duplicate
 */
export async function checkDuplicate(
  params: { file_hash?: string | null; file_size?: number | null },
  signal?: AbortSignal
): Promise<DuplicateCheckResponse> {
  const qs = buildQueryString(params as Record<string, unknown>);
  return apiFetch<DuplicateCheckResponse>(`/api/v1/ingest/check-duplicate${qs}`, { signal });
}

/**
 * Mengunggah berkas PDF secara manual via POST /api/v1/ingest/upload-pdf (multipart/form-data)
 * Timeout diatur 120 detik (120.000 ms) sesuai spesifikasi.
 */
export async function uploadManualPdf(
  formData: FormData,
  signal?: AbortSignal
): Promise<IngestUploadResponse> {
  return apiFetch<IngestUploadResponse>('/api/v1/ingest/upload-pdf', {
    method: 'POST',
    body: formData,
    timeout: 120000,
    signal,
  });
}

/**
 * Mengambil riwayat pekerjaan ingest via GET /api/v1/ingest/jobs
 */
export async function getIngestJobs(
  params?: IngestJobQueryParams,
  signal?: AbortSignal
): Promise<IngestJobListResponse> {
  const qs = params ? buildQueryString(params as Record<string, unknown>) : '';
  return apiFetch<IngestJobListResponse>(`/api/v1/ingest/jobs${qs}`, { signal });
}

