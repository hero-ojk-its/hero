/**
 * Client API Analisa Regulasi HERO
 * 
 * Modul ini menyediakan fungsi pemanggilan dan kontrak tipe TypeScript aktual untuk:
 * 1. Layanan ML Lapisan Data (prefix /api/v1/ml/* atau VITE_ML_API_BASE_URL):
 *    - GET /health: Kesiapan korpus, vektor, dan mesin analisa
 *    - GET /analisa/{document_id}: Hasil intisari, norma, sanksi, dan struktur pasal
 *    - GET /dokumen: Daftar dokumen draf atau korpus yang siap dianalisis
 * 2. Backend FastAPI Ingest & Dokumen:
 *    - POST /api/v1/ingest/upload-pdf (via uploadManualPdf): Unggah draf regulasi non-publik
 *    - GET /api/v1/documents/{document_id}: Pengecekan status ekstraksi dan ketersediaan pasal
 */

import { apiFetch, API_BASE_URL, buildQueryString } from './api';
import type { DocumentsResponse, DocumentItem } from './api';
import { uploadManualPdf } from './ingestApi';
import type { IngestUploadResponse } from './ingestApi';

// ============================================================================
// 1. Konfigurasi URL Layanan ML
// ============================================================================

/**
 * Base URL layanan ML Lapisan Data.
 * - Bila VITE_ML_API_BASE_URL ditentukan (mis. http://localhost:8100 saat pengujian mandiri tanpa proxy),
 *   URL tersebut yang diprioritaskan.
 * - Bila tidak ditentukan, fallback ke `${API_BASE_URL}/api/v1/ml` (mode standar reverse proxy Caddy/Nginx).
 */
const rawMlUrl = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_ML_API_BASE_URL) || '';
export const ML_API_BASE_URL: string = rawMlUrl
  ? rawMlUrl.replace(/\/+$/, '')
  : `${API_BASE_URL}/api/v1/ml`;

// ============================================================================
// 2. Tipe Data Kontrak ML Health (GET /api/v1/ml/health)
// ============================================================================

export interface MlHealthCorpus {
  dokumen: number;
  pasal: number;
  pasal_berhalaman: number;
  dokumen_terpeta_ke_backend: number;
}

export interface MlHealthVector {
  lexical: boolean;
  lsa: boolean;
  semantic: boolean;
  hybrid: boolean;
}

export interface MlHealthResponse {
  status: 'siap' | 'belum-siap';
  korpus: MlHealthCorpus;
  vektor: MlHealthVector;
  mode_ai: boolean;
  langkah_berikutnya: string[];
  catatan: string;
}

// ============================================================================
// 3. Tipe Data Kontrak Analisa Regulasi (GET /api/v1/ml/analisa/{document_id})
// ============================================================================

export interface MlAnalisaPoint {
  id: string | number;
  kategori: string;
  pasal?: string;
  ref?: string;
  halaman: number | null;
  teks: string;
  prioritas?: number;
  urgensi?: string;
  subjek?: string | null;
  terpotong?: boolean;
  parafrase?: string;
}

export interface MlAnalisaSummarySentence {
  kalimat: string;
  rujukan: string[];
  fakta: string[];
}

export interface MlAnalisaFrameworkChapter {
  bab: string;
  judul: string;
  pasal: string[];
}

export interface MlAnalisaIdentity {
  doc_type?: string;
  number?: string;
  year?: number;
  date?: string;
  issuer?: string;
  title?: string;
  nomor?: string;
  tahun?: number;
  jenis?: string;
  tanggal?: string;
  tanggal_terbit?: string;
  tentang?: string;
  status?: string;
  penerbit?: string;
  jumlah_pasal?: number;
}

export interface MlAnalisaAiDetails {
  status?: string;
  ringkasan?: string;
  alasan?: string;
  poin_kunci?: Record<string, string>;
}

export interface MlAnalisaMetrics {
  waktu_ms?: number;
  jumlah_poin?: number;
  kata_ringkasan?: number;
  jumlah_pasal?: number;
  jumlah_ayat?: number;
  jumlah_bab?: number;
  jumlah_kewajiban?: number;
  jumlah_larangan?: number;
  [key: string]: unknown;
}

export interface MlAnalisaCache {
  hit?: boolean;
  dibuat?: string | null;
  basi?: boolean;
  mode_tersimpan?: string;
}

export interface MlAnalisaResponse {
  document_id: number;
  pdf?: string | null;
  identitas?: MlAnalisaIdentity;
  kerangka?: MlAnalisaFrameworkChapter[];
  subjek_diatur?: Array<{ subjek: string; jumlah: number }> | string[];
  poin_utama?: MlAnalisaPoint[];
  jumlah_poin?: number;
  sanksi?: string[];
  dasar_hukum?: string[];
  lampiran?: {
    profil?: string;
    tabel?: number;
  } | string[];
  ringkasan?: MlAnalisaSummarySentence[];
  ringkasan_teks?: string;
  metrik?: MlAnalisaMetrics;
  mode_diminta?: 'deterministik' | 'ai';
  mode_dipakai?: 'deterministik' | 'ai';
  ai?: MlAnalisaAiDetails | null;
  ringkasan_ai?: string;
  catatan?: string;
  cache?: MlAnalisaCache;
  disaring_backend?: boolean;
}

// ============================================================================
// 4. Tipe Data Kontrak Dokumen ML (GET /api/v1/ml/dokumen)
// ============================================================================

export interface MlDokumenItem {
  document_id: number;
  judul: string;
  jenis?: string;
  nomor?: string;
  tahun?: number;
  status?: string;
  peran?: 'corpus_eksisting' | 'draft_kajian';
}

export interface MlDokumenListResponse {
  total: number;
  items: MlDokumenItem[];
}

// ============================================================================
// 5. Tipe Data Status Dokumen Backend (GET /api/v1/documents/{document_id})
// ============================================================================

export type ProcessingStatus =
  | 'diterima'
  | 'diproses'
  | 'perlu_koreksi'
  | 'terindeks'
  | 'gagal'
  | 'ditolak';

export interface DocumentArticleSummary {
  id: number;
  level: string;
  chapter_title: string;
  article_number: string;
  content_text: string;
  order_index: number;
  page: number | null;
}

export interface DocumentStatusResponse {
  id: number;
  title: string;
  regulation_number: string | null;
  regulation_type?: string | null;
  release_date?: string | null;
  regulation_year?: number | null;
  bidang?: string | null;
  access_classification: 'publik' | 'non_publik';
  document_role: 'corpus_eksisting' | 'draft_kajian';
  status_keberlakuan: 'berlaku' | 'diubah' | 'dicabut' | 'tidak_diketahui';
  processing_status: ProcessingStatus;
  pdf_url: string;
  text_url: string;
  full_text_length: number;
  articles: DocumentArticleSummary[];
  job_id?: number | null;
  created_at?: string;
  updated_at?: string;
}

// ============================================================================
// 6. Tipe Data Hasil Unggah Draf Regulasi
// ============================================================================

export interface DraftUploadMetadata {
  title?: string;
  regulation_number?: string;
  regulation_type?: string;
  bidang?: string;
  release_date?: string;
  access_classification?: 'publik' | 'non_publik';
}

export interface UploadDraftResult {
  documentId: number;
  status: 'success' | 'duplicate';
  filename: string;
  isDuplicate: boolean;
  duplicateOfDocumentId?: number | null;
  failureId?: number | null;
  jobId: number;
  originalResponse: IngestUploadResponse;
}

// ============================================================================
// 7. Fungsi-Fungsi API Client
// ============================================================================

/**
 * Pengecekan status kesiapan layanan ML Lapisan Data.
 * Endpoint: GET /health
 */
export async function checkMlHealth(signal?: AbortSignal): Promise<MlHealthResponse> {
  return apiFetch<MlHealthResponse>(`${ML_API_BASE_URL}/health`, { signal });
}

/**
 * Mengunggah berkas PDF draf regulasi baru untuk ditelaah.
 * 
 * Ketentuan Kepatuhan & Arsitektur:
 * - Menggunakan kembali uploadManualPdf (/api/v1/ingest/upload-pdf) dari ingestApi.ts.
 * - Menyematkan access_classification dari formulir ('publik' atau 'non_publik') sesuai kepatuhan NDA.
 * - WAJIB menyematkan document_role='draft_kajian' agar tidak disimpan sebagai regulasi eksisting KBS.
 * - Memvalidasi details[0] dan mengekstrak document_id / duplicate_of_document_id secara ketat.
 * - TIDAK PERNAH menggunakan job_id sebagai document_id.
 */
export async function uploadDraftPdf(
  file: File,
  metadata?: DraftUploadMetadata,
  signal?: AbortSignal
): Promise<UploadDraftResult> {
  const formData = new FormData();
  formData.append('files', file);
  formData.append('access_classification', metadata?.access_classification || 'non_publik');
  formData.append('document_role', 'draft_kajian');

  if (metadata?.title && metadata.title.trim() !== '') {
    formData.append('title', metadata.title.trim());
  }
  if (metadata?.regulation_number && metadata.regulation_number.trim() !== '') {
    formData.append('regulation_number', metadata.regulation_number.trim());
  }
  if (metadata?.regulation_type && metadata.regulation_type.trim() !== '') {
    formData.append('regulation_type', metadata.regulation_type.trim());
  }
  if (metadata?.bidang && metadata.bidang.trim() !== '') {
    formData.append('bidang', metadata.bidang.trim());
  }
  if (metadata?.release_date && metadata.release_date.trim() !== '') {
    formData.append('release_date', metadata.release_date.trim());
  }

  const uploadRes = await uploadManualPdf(formData, signal);

  if (!uploadRes.details || uploadRes.details.length === 0) {
    throw new Error('Respons backend tidak memuat rincian item unggahan (details kosong).');
  }

  const detail = uploadRes.details[0];

  if (detail.status === 'failed') {
    const errorMsg = detail.error || detail.message || detail.reason_code || 'Gagal memproses berkas draf regulasi.';
    throw new Error(`Unggah draf gagal: ${errorMsg}`);
  }

  const documentId = detail.document_id ?? detail.duplicate_of_document_id ?? null;

  if (typeof documentId !== 'number' || documentId <= 0) {
    throw new Error(
      'Backend tidak mengembalikan ID dokumen yang valid pada rincian hasil unggahan. ' +
      'ID pekerjaan ingest (job_id) tidak dapat digunakan sebagai ID dokumen.'
    );
  }

  return {
    documentId,
    status: detail.status === 'duplicate' ? 'duplicate' : 'success',
    filename: detail.filename,
    isDuplicate: detail.status === 'duplicate',
    duplicateOfDocumentId: detail.duplicate_of_document_id ?? null,
    failureId: detail.failure_id ?? null,
    jobId: uploadRes.job_id,
    originalResponse: uploadRes,
  };
}

/**
 * Mengambil status detail dokumen dari Backend FastAPI untuk memantau kemajuan ekstraksi teks dan pasal.
 * Endpoint: GET /api/v1/documents/{document_id}
 */
export async function getDocumentStatus(
  documentId: number,
  signal?: AbortSignal
): Promise<DocumentStatusResponse> {
  return apiFetch<DocumentStatusResponse>(`/api/v1/documents/${documentId}`, { signal });
}

/**
 * Mengambil ringkasan terstruktur dan poin kunci berbasis pasal dari layanan ML.
 * Endpoint: GET /analisa/{document_id}?mode={mode}&segar={segar}
 * 
 * Dukungan parameter:
 * - mode: 'deterministik' | 'ai'
 * - segar: boolean (Query param 'segar=true' didukung backend ml_gateway untuk memaksa kalkulasi ulang tanpa cache)
 */
export async function getMlAnalisa(
  documentId: number,
  mode: 'deterministik' | 'ai' = 'deterministik',
  segar: boolean = false,
  signal?: AbortSignal
): Promise<MlAnalisaResponse> {
  const query = new URLSearchParams();
  query.append('mode', mode);
  if (segar) {
    query.append('segar', 'true');
  }

  const headers: Record<string, string> = {};
  if (segar) {
    headers['Cache-Control'] = 'no-cache, no-store';
    headers['Pragma'] = 'no-cache';
  }

  return apiFetch<MlAnalisaResponse>(
    `${ML_API_BASE_URL}/analisa/${documentId}?${query.toString()}`,
    {
      headers: Object.keys(headers).length > 0 ? headers : undefined,
      signal,
    }
  );
}

/**
 * Mengambil daftar dokumen yang siap dianalisis dari katalog Lapisan Data.
 * Endpoint: GET /dokumen
 */
export async function getMlDokumen(
  params?: { peran?: 'corpus_eksisting' | 'draft_kajian'; limit?: number },
  signal?: AbortSignal
): Promise<MlDokumenListResponse> {
  const query = new URLSearchParams();
  if (params?.peran) query.append('peran', params.peran);
  if (params?.limit) query.append('limit', String(params.limit));
  const qs = query.toString() ? `?${query.toString()}` : '';

  return apiFetch<MlDokumenListResponse>(`${ML_API_BASE_URL}/dokumen${qs}`, { signal });
}

/**
 * Mengambil daftar dokumen regulasi dari basis data Knowledge Base backend.
 * Endpoint: GET /api/v1/documents/
 */
export async function getKnowledgeBaseDocuments(
  params?: { q?: string; limit?: number; skip?: number; document_role?: string },
  signal?: AbortSignal
): Promise<DocumentsResponse> {
  const qs = params ? buildQueryString(params as Record<string, unknown>) : '';
  return apiFetch<DocumentsResponse>(`/api/v1/documents/${qs}`, { signal });
}

// ============================================================================
// 8. Helper Penentu Kesiapan Dokumen untuk Polling
// ============================================================================

/**
 * Menentukan apakah dokumen telah selesai diekstraksi dan memiliki pasal sehingga siap dianalisis ML.
 */
export function isDocumentReadyForAnalysis(doc: DocumentStatusResponse): boolean {
  const isTerminalSuccess = doc.processing_status === 'terindeks' || doc.processing_status === 'perlu_koreksi';
  const hasContent = (Array.isArray(doc.articles) && doc.articles.length > 0) || (typeof doc.full_text_length === 'number' && doc.full_text_length > 0);
  return Boolean(isTerminalSuccess && hasContent);
}

/**
 * Menentukan apakah pemrosesan dokumen mengalami kegagalan terminal.
 */
export function isDocumentProcessingFailed(doc: DocumentStatusResponse): boolean {
  return doc.processing_status === 'gagal' || doc.processing_status === 'ditolak';
}

export type { DocumentsResponse, DocumentItem };
