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

import { apiFetch, apiFetchBlob, API_BASE_URL, buildQueryString } from './api';
import type { DocumentsResponse, DocumentItem, DocumentBlob } from './api';
import { uploadManualPdf, type IngestUploadResponse, type UploadProgressEvent } from './ingestApi';
export type { UploadProgressEvent };

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
  run_id?: number | null;
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
  signal?: AbortSignal,
  onProgress?: (progress: UploadProgressEvent) => void
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

  const uploadRes = await uploadManualPdf(formData, signal, onProgress);

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
// 8. Ekspor Hasil Analisa Regulasi (GET /api/v1/documents/{document_id}/analisa/ekspor)
// ============================================================================

export type AnalysisExportFormat = 'docx' | 'csv' | 'json';

export interface ExportDocumentAnalysisParams {
  format?: AnalysisExportFormat;
  mode?: 'deterministik' | 'ai';
  run_id?: number | null;
}

/**
 * Mengekspor hasil analisa regulasi (DOCX, CSV, JSON) langsung dari basis data backend (US-40).
 * Endpoint: GET /api/v1/documents/{document_id}/analisa/ekspor
 *
 * Parameter yang didukung:
 * - documentId: ID dokumen regulasi yang diekspor
 * - paramsOrFormat: Opsi ekspor ({ format, mode, run_id }) atau langsung string format ('docx' | 'csv' | 'json')
 * - mode: Mode analisa ('deterministik' | 'ai') jika parameter kedua berupa string format
 * - runId: ID eksekusi tertentu dari riwayat analisa (opsional)
 * - signal: AbortSignal untuk pembatalan fetch
 *
 * Mengembalikan DocumentBlob dengan properti .filename dan .contentType dari header response.
 */
export async function exportDocumentAnalysis(
  documentId: number,
  paramsOrFormat?: AnalysisExportFormat | ExportDocumentAnalysisParams,
  mode?: 'deterministik' | 'ai',
  runId?: number | null,
  signal?: AbortSignal
): Promise<DocumentBlob> {
  let formatVal: AnalysisExportFormat = 'docx';
  let modeVal: 'deterministik' | 'ai' | undefined = undefined;
  let runIdVal: number | null | undefined = undefined;
  let abortSignal: AbortSignal | undefined = signal;

  if (typeof paramsOrFormat === 'string') {
    formatVal = paramsOrFormat;
    modeVal = mode;
    runIdVal = runId;
    abortSignal = signal;
  } else if (paramsOrFormat && typeof paramsOrFormat === 'object') {
    if (paramsOrFormat.format) formatVal = paramsOrFormat.format;
    modeVal = paramsOrFormat.mode;
    runIdVal = paramsOrFormat.run_id;
    if (mode && typeof (mode as unknown) === 'object' && 'aborted' in (mode as unknown as Record<string, unknown>)) {
      abortSignal = mode as unknown as AbortSignal;
    }
  }

  const queryParams: Record<string, unknown> = {
    format: formatVal,
  };
  if (modeVal) {
    queryParams.mode = modeVal;
  }
  if (typeof runIdVal === 'number' && runIdVal > 0) {
    queryParams.run_id = runIdVal;
  }

  const qs = buildQueryString(queryParams);
  return apiFetchBlob(`/api/v1/documents/${documentId}/analisa/ekspor${qs}`, { signal: abortSignal });
}

// ============================================================================
// 9. Helper Penentu Kesiapan Dokumen untuk Polling
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

// ============================================================================
// 10. Helper Parsing & Normalisasi Referensi Pasal (US-37 / FR-ANL-06)
// ============================================================================

export interface ParsedPasalRef {
  /** Nomor pasal ternormalisasi (huruf kapital), misal "5", "5A", "12B". Null jika tidak dikenali */
  pasalNum: string | null;
  /** Nomor ayat jika tercantum dalam referensi, misal "2" dari "Pasal 3 ayat (2)" */
  ayatNum: string | null;
  /** Pengenal DOM canonical, misal "pasal-5a". Null jika nomor pasal tidak valid */
  canonicalId: string | null;
  /** String mentah rujukan asal */
  raw: string;
}

/**
 * Mem-parsing string rujukan pasal hukum secara presisi.
 * Mendukung format:
 * - "Pasal 5" -> { pasalNum: "5", ayatNum: null, canonicalId: "pasal-5" }
 * - "Pasal 5A" / "Pasal 5a" -> { pasalNum: "5A", ayatNum: null, canonicalId: "pasal-5a" }
 * - "Pasal 12B" -> { pasalNum: "12B", ayatNum: null, canonicalId: "pasal-12b" }
 * - "Pasal 3 ayat (2)" / "Pasal 3 ayat 2" -> { pasalNum: "3", ayatNum: "2", canonicalId: "pasal-3" }
 * - Format non-standar / "Teks dokumen (pasal tidak terbaca)" -> { pasalNum: null, ayatNum: null, canonicalId: null }
 */
export function parsePasalRef(str: string): ParsedPasalRef {
  if (!str || typeof str !== 'string') {
    return { pasalNum: null, ayatNum: null, canonicalId: null, raw: '' };
  }
  const trimmed = str.trim();

  // Pola 1: "Pasal 5", "Pasal 5A", "Pasal 5-A", "Pasal 5 A" (di mana A adalah huruf tunggal, bukan awal kata seperti 'ayat')
  // diikuti opsional "ayat (2)" atau "ayat 2"
  const match = trimmed.match(/Pasal\s+([0-9]+)(?:[\s-]*([A-Za-z])(?![A-Za-z]))?(?:\s+ayat\s*\(?([0-9]+)\)?)?/i);
  if (match) {
    const baseNum = match[1].replace(/^0+(?=\d)/, '');
    const letter = match[2] ? match[2].toUpperCase() : '';
    const num = baseNum + letter;
    const ayat = match[3] || null;
    return {
      pasalNum: num,
      ayatNum: ayat,
      canonicalId: `pasal-${num.toLowerCase()}`,
      raw: trimmed
    };
  }

  // Pola 2: String numerik langsung dengan sufiks huruf opsional, misal "5", "5A", "05", "12B", "5 A", "5-A"
  const numOnlyMatch = trimmed.match(/^([0-9]+)(?:[\s-]*([A-Za-z])(?![A-Za-z]))?$/);
  if (numOnlyMatch) {
    const baseNum = numOnlyMatch[1].replace(/^0+(?=\d)/, '');
    const letter = numOnlyMatch[2] ? numOnlyMatch[2].toUpperCase() : '';
    const num = baseNum + letter;
    return {
      pasalNum: num,
      ayatNum: null,
      canonicalId: `pasal-${num.toLowerCase()}`,
      raw: trimmed
    };
  }

  return { pasalNum: null, ayatNum: null, canonicalId: null, raw: trimmed };
}

export type { DocumentsResponse, DocumentItem, DocumentBlob };
