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
