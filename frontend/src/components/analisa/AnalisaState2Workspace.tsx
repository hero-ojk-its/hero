import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FileText,
  ExternalLink,
  Check,
  ChevronDown,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Scale,
  ArrowRight,
  ArrowLeft,
  Download,
  RefreshCw,
  FileCode,
  AlertCircle,
  Loader2,
  Building2,
  ShieldAlert,
  Paperclip,
  Clock,
  Info,
  X,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Search,
  GitCompare,
  Columns,
  Cpu,
  Lock,
  Sparkles
} from 'lucide-react';
import {
  getMlAnalisa,
  getMlAnalisaViaJob,
  ANALISA_AI_INFO_LAMA_MS,
  getDocumentStatus,
  checkMlHealth,
  isDocumentReadyForAnalysis,
  exportDocumentAnalysis,
  parsePasalRef,
  normalisasiKerangka,
  getStoredAnalisaWorkspace,
  saveStoredAnalisaWorkspace,
  getDocumentAnalysisComparison,
  getKnowledgeBaseDocuments,
  type DocumentAnalysisComparisonResponse
} from '../../lib/analisaApi';
import {
  labelStatusKeberlakuan,
  kelasBadgeStatusKeberlakuan
} from '../../lib/labelStatus';
import { ApiError, API_BASE_URL, apiFetchBlob } from '../../lib/api';
import { PanelErrorBoundary } from '../PanelErrorBoundary';
import { DraftLabel } from '../DraftLabel';
import RingkasanAiPanel from './RingkasanAiPanel';
import HarmonisasiPanel from './HarmonisasiPanel';
import KemiripanDraftBanner from './KemiripanDraftBanner';
import StatusPasalKb from './StatusPasalKb';
import type { HarmonisasiPanelState } from './HarmonisasiPanel';
import {
  postHarmonisasi,
  pesanGalatHarmonisasi,
  getStoredHarmonisasiResult,
  saveStoredHarmonisasiResult
} from '../../lib/harmonisasiApi';
import type {
  MlAnalisaResponse,
  DocumentArticleSummary,
  DocumentStatusResponse,
  AnalysisExportFormat
} from '../../lib/analisaApi';

/** Backend memotong content_text pasal menjadi 300 karakter + "..." (routers/documents.py) */
function isTeksTerpotong(teks: string | null | undefined): boolean {
  return typeof teks === 'string' && teks.trimEnd().endsWith('...');
}

// 4 Tahap Analisis Mesin HERO
const PIPELINE_STEPS = [
  { id: 1, title: 'Kesiapan Dokumen', desc: 'Memeriksa kesiapan dokumen dan izin akses...' },
  { id: 2, title: 'Struktur Regulasi', desc: 'Memuat naskah dan susunan pasal dari pangkalan data...' },
  { id: 3, title: 'Analisis Regulasi', desc: 'Menjalankan penelaahan norma, kewajiban, dan sanksi...' },
  { id: 4, title: 'Kompilasi Intisari', desc: 'Menyusun ringkasan eksekutif dan indikator kepatuhan regulasi...' }
];

export interface AnalisaState2WorkspaceProps {
  documentId: number;
  mode: 'deterministik' | 'ai';
  onBackToState1: () => void;
  onBackToSummary?: () => void;
}

export default function AnalisaState2Workspace({
  documentId,
  mode,
  onBackToState1,
  onBackToSummary
}: AnalisaState2WorkspaceProps) {
  const navigate = useNavigate();

  // State Pemuatan & Data API
  const [data, setData] = useState<MlAnalisaResponse | null>(null);
  const [docStatus, setDocStatus] = useState<DocumentStatusResponse | null>(null);
  const [articles, setArticles] = useState<DocumentArticleSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // State Perbandingan Analisis (US-05 #49 Deterministik vs AI)
  const [isComparisonOpen, setIsComparisonOpen] = useState<boolean>(false);
  const [comparisonData, setComparisonData] = useState<DocumentAnalysisComparisonResponse | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState<boolean>(false);
  const [comparisonError, setComparisonError] = useState<string | null>(null);

  // Mapping Ketersediaan Rujukan Dasar Hukum di KB
  const [kbReferenceMap, setKbReferenceMap] = useState<Record<string, { available: boolean; documentId?: number; title?: string; isMultiple?: boolean }>>({});

  // State Ekspor Analisis (US-40: DOCX, CSV, JSON)
  const [isExportMenuOpen, setIsExportMenuOpen] = useState<boolean>(false);
  const [isExporting, setIsExporting] = useState<boolean>(false);
  const [exportingFormat, setExportingFormat] = useState<AnalysisExportFormat | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  // State Pemuatan Berkas PDF Asli (Blob Object URL)
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState<boolean>(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const pdfBlobUrlRef = useRef<string | null>(null);

  // State Status Loading Analisis
  const [pipelineStep, setPipelineStep] = useState<number>(1);
  const [loadingStatusText, setLoadingStatusText] = useState<string>('Memeriksa kesiapan dokumen...');
  const [retryCount, setRetryCount] = useState<number>(0);
  const [showProcessingBanner, setShowProcessingBanner] = useState<boolean>(true);
  // Analisis AI sudah berjalan lebih dari 5 menit — hanya informasi, pemollan terus berlanjut
  const [aiMelebihiLimaMenit, setAiMelebihiLimaMenit] = useState<boolean>(false);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const retryStartTimeRef = useRef<number | null>(null);
  const retryCountRef = useRef<number>(0);
  const isMountedRef = useRef<boolean>(true);
  const loadAnalysisRef = useRef<(forceFresh?: boolean, isRetryAttempt?: boolean) => Promise<void>>(null);

  // Tutup dropdown menu ekspor saat klik di luar
  useEffect(() => {
    if (!isExportMenuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (!(e.target as Element).closest('.export-dropdown-container')) {
        setIsExportMenuOpen(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [isExportMenuOpen]);

  // Ambil state tersimpan di sessionStorage (Pekerjaan B: Persistensi Workspace)
  const storedWs = getStoredAnalisaWorkspace();
  const initialPasal = (storedWs?.documentId === documentId && storedWs.selectedPasal)
    ? storedWs.selectedPasal
    : 'Pasal 1';
  const initialTab = (storedWs?.documentId === documentId && storedWs.activeTab)
    ? (storedWs.activeTab as 'harmonisasi' | 'ringkasan' | 'poin_utama' | 'dasar_hukum' | 'perbandingan' | 'info_tambahan')
    : 'harmonisasi';

  // State Workspace Panel 1: Struktur Dokumen
  const [expandedBabs, setExpandedBabs] = useState<Record<string, boolean>>({
    'BAB I': true,
    'BAB II': true,
    'BAB III': true,
    'BAB IV': true,
    'BAB V': true
  });
  const [selectedPasal, setSelectedPasal] = useState<string>(initialPasal);
  const [structureSearch, setStructureSearch] = useState<string>('');

  // State Workspace Panel 2: Naskah Regulasi
  const [viewMode, setViewMode] = useState<'salinan' | 'pdf'>('salinan');
  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pdfTargetPage, setPdfTargetPage] = useState<number | null>(null);

  // Evaluasi totalPages dari metadata metrik, artikel backend, dan poin ML yang valid
  const maxPageFromData = useMemo(() => {
    let max = 1;
    for (const a of articles) {
      if (typeof a.page === 'number' && a.page > max) max = a.page;
    }
    if (data?.poin_utama) {
      for (const p of data.poin_utama) {
        if (typeof p.halaman === 'number' && p.halaman > max) max = p.halaman;
      }
    }
    return max;
  }, [articles, data]);

  const totalPages = typeof data?.metrik?.jumlah_halaman === 'number' && data.metrik.jumlah_halaman > 0
    ? data.metrik.jumlah_halaman
    : maxPageFromData;

  // Konteks Keberlakuan Regulasi & Jenis Dokumen Aktual (Temuan QA 1 & 4)
  const effectiveStatusKeberlakuan = docStatus?.status_keberlakuan || data?.identitas?.status || null;
  const docTypeStr = (docStatus?.regulation_type || data?.identitas?.jenis || data?.identitas?.doc_type || '').toUpperCase();
  const isSeojk = docTypeStr.includes('SEOJK') || docTypeStr.includes('SURAT EDARAN');
  const isDraft = docStatus?.document_role === 'draft_kajian';

  const naskahContainerRef = useRef<HTMLDivElement>(null);
  const [highlightedPasalId, setHighlightedPasalId] = useState<string | null>(null);
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Feedback Navigasi Rujukan Pasal (US-37)
  const [navFeedback, setNavFeedback] = useState<{
    type: 'success' | 'warning' | 'info';
    message: string;
  } | null>(null);
  const navFeedbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showNavFeedback = useCallback((type: 'success' | 'warning' | 'info', message: string) => {
    if (navFeedbackTimerRef.current) {
      clearTimeout(navFeedbackTimerRef.current);
    }
    setNavFeedback({ type, message });
    navFeedbackTimerRef.current = setTimeout(() => {
      setNavFeedback(null);
      navFeedbackTimerRef.current = null;
    }, 4500);
  }, []);

  // State Workspace Panel 3: Hasil Analisis Tabs (dipulihkan dari storage jika ada, default: harmonisasi perbandingan MVP 3)
  const [activeTab, setActiveTab] = useState<'harmonisasi' | 'ringkasan' | 'poin_utama' | 'dasar_hukum' | 'perbandingan' | 'info_tambahan'>(initialTab);

  // State Collapse Manual Panel Kiri (Struktur) & Kanan (Hasil Analisis)
  const [isLeftCollapsed, setIsLeftCollapsed] = useState<boolean>(() => {
    try {
      return sessionStorage.getItem('hero_ws_left_collapsed') === 'true';
    } catch {
      return false;
    }
  });
  const [isRightCollapsed, setIsRightCollapsed] = useState<boolean>(() => {
    try {
      return sessionStorage.getItem('hero_ws_right_collapsed') === 'true';
    } catch {
      return false;
    }
  });
  // State Tab Aktif untuk Tampilan Adaptif Layar Kecil / Mobile / Tablet (< 1024px)
  const [mobileActivePanel, setMobileActivePanel] = useState<'struktur' | 'naskah' | 'hasil'>('naskah');

  // Persistensi status collapse di sesi pengguna
  useEffect(() => {
    try {
      sessionStorage.setItem('hero_ws_left_collapsed', String(isLeftCollapsed));
    } catch {}
  }, [isLeftCollapsed]);

  useEffect(() => {
    try {
      sessionStorage.setItem('hero_ws_right_collapsed', String(isRightCollapsed));
    } catch {}
  }, [isRightCollapsed]);
  const [kategoriFilter, setKategoriFilter] = useState<string>('Semua');
  const panelHasilRef = useRef<HTMLDivElement>(null);

  // State Harmonisasi: dipulihkan dari sessionStorage agar tidak hilang atau auto-fetch ulang (Pekerjaan B)
  const cachedHarmonisasi = getStoredHarmonisasiResult(documentId);
  const [harmonisasiState, setHarmonisasiState] = useState<(HarmonisasiPanelState & { documentId: number }) | null>(() => {
    if (cachedHarmonisasi) {
      return {
        documentId,
        status: 'sukses',
        data: cachedHarmonisasi,
        galat: null,
      };
    }
    return null;
  });
  const harmonisasi = harmonisasiState?.documentId === documentId ? harmonisasiState : null;
  const harmonisasiAbortRef = useRef<AbortController | null>(null);
  const harmonisasiPermintaanRef = useRef<number>(0);
  /** documentId yang harmonisasinya sudah diminta otomatis atau dipulihkan dari cache (cegah fetch ganda) */
  const harmonisasiDimintaRef = useRef<number | null>(cachedHarmonisasi ? documentId : null);

  // Simpan perubahan navigasi pasal & tab ke storage secara reaktif (Pekerjaan B)
  useEffect(() => {
    saveStoredAnalisaWorkspace({
      documentId,
      mode,
      selectedPasal,
      activeTab,
    });
  }, [documentId, mode, selectedPasal, activeTab]);

  const muatHarmonisasi = useCallback(async (segar: boolean) => {
    harmonisasiAbortRef.current?.abort();
    const controller = new AbortController();
    harmonisasiAbortRef.current = controller;
    const permintaanId = ++harmonisasiPermintaanRef.current;
    harmonisasiDimintaRef.current = documentId;

    setHarmonisasiState((prev) => ({
      documentId,
      status: 'loading',
      data: prev?.documentId === documentId ? prev.data : null,
      galat: null,
    }));

    try {
      const hasil = await postHarmonisasi(documentId, { segar, signal: controller.signal });
      if (permintaanId !== harmonisasiPermintaanRef.current) return;
      saveStoredHarmonisasiResult(documentId, hasil);
      setHarmonisasiState({ documentId, status: 'sukses', data: hasil, galat: null });
    } catch (err: unknown) {
      if (permintaanId !== harmonisasiPermintaanRef.current || controller.signal.aborted) return;
      if (err instanceof Error && err.name === 'AbortError') return;
      setHarmonisasiState((prev) => ({
        documentId,
        status: 'galat',
        data: prev?.documentId === documentId ? prev.data : null,
        galat: pesanGalatHarmonisasi(err),
      }));
    } finally {
      if (harmonisasiAbortRef.current === controller) harmonisasiAbortRef.current = null;
    }
  }, [documentId]);

  // Batalkan harmonisasi in-flight saat ganti dokumen atau unmount
  useEffect(() => {
    return () => {
      harmonisasiAbortRef.current?.abort();
      harmonisasiAbortRef.current = null;
      harmonisasiDimintaRef.current = null;
    };
  }, [documentId]);

  // Status pasal terhadap KB (definisi analisa Pak Faris) tampil di tab Ringkasan, jadi
  // perbandingannya dijalankan otomatis begitu dokumen dibuka (sekali per dokumen).
  useEffect(() => {
    if (harmonisasiDimintaRef.current === documentId) return;
    const t = setTimeout(() => {
      if (harmonisasiDimintaRef.current !== documentId) void muatHarmonisasi(false);
    }, 0);
    return () => clearTimeout(t);
  }, [documentId, muatHarmonisasi]);

  // Buka tab Harmonisasi; jalankan otomatis sekali per dokumen (dari event, bukan effect, agar tidak ganda di StrictMode)
  const bukaTabHarmonisasi = useCallback(() => {
    setActiveTab('harmonisasi');
    if (harmonisasiDimintaRef.current !== documentId) {
      void muatHarmonisasi(false);
    }
  }, [documentId, muatHarmonisasi]);

  // Bersihkan timer retry otomatis saat unmount atau dibatalkan
  const clearRetryTimer = useCallback(() => {
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  // Batalkan request analisis in-flight jika komponen unmount atau di-reset
  const abortAnalysisRequest = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  // Pastikan ref isMounted dan timer dibersihkan saat unmount
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      clearRetryTimer();
      abortAnalysisRequest();
      if (navFeedbackTimerRef.current) {
        clearTimeout(navFeedbackTimerRef.current);
        navFeedbackTimerRef.current = null;
      }
      if (highlightTimerRef.current) {
        clearTimeout(highlightTimerRef.current);
        highlightTimerRef.current = null;
      }
    };
  }, [clearRetryTimer, abortAnalysisRequest]);

  // Muat analisis (panggilan API nyata dengan retry otomatis untuk 404 sementara)
  const loadAnalysis = useCallback(async (forceFresh: boolean = false, isRetryAttempt: boolean = false) => {
    clearRetryTimer();
    abortAnalysisRequest();

    const controller = new AbortController();
    abortControllerRef.current = controller;

    if (!isRetryAttempt) {
      retryStartTimeRef.current = Date.now();
      retryCountRef.current = 0;
      setRetryCount(0);
      setLoading(true);
      setIsRefreshing(forceFresh);
      setErrorStatus(null);
      setErrorMessage(null);
      setShowProcessingBanner(true);
      setPipelineStep(1);
      setLoadingStatusText('Memeriksa kesiapan dokumen dan layanan analisis...');
    }

    // Pemanggilan API Nyata ke Backend ML & Dokumen Status
    try {
      // 1. Tentukan requestedMode: hanya 'ai' jika mode === 'ai' DAN mlHealth?.mode_ai === true
      let requestedMode: 'deterministik' | 'ai' = 'deterministik';
      if (mode === 'ai') {
        try {
          const health = await checkMlHealth(controller.signal);
          if (health?.mode_ai === true) {
            requestedMode = 'ai';
          } else {
            requestedMode = 'deterministik';
          }
        } catch {
          requestedMode = 'deterministik';
        }
      }

      if (controller.signal.aborted || !isMountedRef.current) return;

      // 2. Transisi status visual ke pemuatan struktur & analisis
      setPipelineStep(2);
      setLoadingStatusText(
        requestedMode === 'ai'
          ? 'Memuat struktur regulasi dan mengambil hasil analisis AI...'
          : 'Memuat struktur regulasi dan mengambil hasil analisis deterministik...'
      );
      setAiMelebihiLimaMenit(false);

      // Mode AI: lewat job + poll, bukan satu permintaan sinkron. Panggilan Gemini
      // bisa lebih lama dari batas proxy Cloudflare (~100 d) di depan domain
      // publik; pemollan tidak pernah menyerah menunggu, hanya menampilkan info
      // setelah 5 menit.
      const mlPromise = requestedMode === 'ai'
        ? getMlAnalisaViaJob(documentId, 'ai', forceFresh, controller.signal, (detikBerjalan) => {
            if (!isMountedRef.current) return;
            const lama = detikBerjalan * 1000 >= ANALISA_AI_INFO_LAMA_MS;
            setAiMelebihiLimaMenit(lama);
            setLoadingStatusText(
              lama
                ? `Analisis AI masih berjalan (${Math.floor(detikBerjalan / 60)} menit) — ini normal untuk dokumen besar, tetap menunggu tanpa batas waktu...`
                : 'Memuat struktur regulasi dan mengambil hasil analisis AI...'
            );
          })
        : getMlAnalisa(documentId, requestedMode, forceFresh, controller.signal);

      const [mlRes, statusRes] = await Promise.allSettled([
        mlPromise,
        getDocumentStatus(documentId, controller.signal),
      ]);

      if (controller.signal.aborted || !isMountedRef.current) return;

      let statusDoc: DocumentStatusResponse | null = null;
      if (statusRes.status === 'fulfilled') {
        statusDoc = statusRes.value;
        setDocStatus(statusRes.value);
        if (Array.isArray(statusRes.value.articles)) {
          setArticles(statusRes.value.articles);
        }
      }

      if (mlRes.status === 'fulfilled') {
        retryStartTimeRef.current = null;
        retryCountRef.current = 0;
        setRetryCount(0);
        // Pecah ulang rentang pasal kerangka memakai daftar pasal backend agar pasal sisipan (mis. 5A) ikut
        const hasil = mlRes.value;
        const statusArticles = statusDoc?.articles;
        setData(
          hasil.kerangka && Array.isArray(statusArticles) && statusArticles.length > 0
            ? { ...hasil, kerangka: normalisasiKerangka(hasil.kerangka, statusArticles) }
            : hasil
        );
        setErrorStatus(null);
        setErrorMessage(null);
        setPipelineStep(4);
        setLoadingStatusText('Analisis berhasil diselesaikan.');
        setLoading(false);
        setIsRefreshing(false);
      } else {
        const err = mlRes.reason;
        if (err instanceof DOMException && err.name === 'AbortError') return;
        if (err instanceof Error && err.name === 'AbortError') return;

        if (err instanceof ApiError) {
          if (err.status === 404) {
            // Cek apakah dokumen sudah selesai diekstraksi di backend tetapi belum tersinkron ke ML
            const isExtracted = Boolean(
              statusDoc && (
                isDocumentReadyForAnalysis(statusDoc) ||
                (Array.isArray(statusDoc.articles) && statusDoc.articles.length > 0) ||
                (typeof statusDoc.full_text_length === 'number' && statusDoc.full_text_length > 0) ||
                statusDoc.processing_status === 'terindeks'
              )
            );

            const elapsed = Date.now() - (retryStartTimeRef.current || Date.now());
            const MAX_RETRY_MS = 300000; // Batas retry maksimal 5 menit

            if (isExtracted && elapsed < MAX_RETRY_MS) {
              // Kondisi 404 sementara: dokumen sudah selesai diekstraksi tetapi ML masih proses/sinkron
              retryCountRef.current += 1;
              const nextAttempt = retryCountRef.current;
              setRetryCount(nextAttempt);
              setPipelineStep(3);
              setLoadingStatusText(
                `Dokumen sedang disinkronkan ke layanan analisis, mencoba kembali secara berkala (percobaan #${nextAttempt})...`
              );
              setErrorMessage('Draft sedang diproses layanan analisa, coba lagi sebentar');
              setLoading(true);
              setErrorStatus(null);

              retryTimerRef.current = setTimeout(() => {
                if (isMountedRef.current && !controller.signal.aborted) {
                  loadAnalysisRef.current?.(false, true);
                }
              }, 2500);
              return;
            } else if (isExtracted && elapsed >= MAX_RETRY_MS) {
              // Batas waktu retry 5 menit tercapai
              retryStartTimeRef.current = null;
              setData(null);
              setErrorStatus(404);
              setErrorMessage('Batas waktu sinkronisasi analisis tercapai (5 menit). Silakan coba lagi.');
              setLoading(false);
              setIsRefreshing(false);
              return;
            } else {
              // Bukan kondisi sinkronisasi sementara (dokumen belum diekstraksi / tidak ditemukan)
              retryStartTimeRef.current = null;
              setData(null);
              setErrorStatus(404);
              if (statusDoc) {
                setErrorMessage('Dokumen sedang dalam antrean atau pemrosesan ekstraksi di peladen. Silakan tunggu beberapa saat.');
              } else {
                setErrorMessage('Dokumen regulasi tidak ditemukan di peladen.');
              }
              setLoading(false);
              setIsRefreshing(false);
              return;
            }
          }

          // Error selain 404: 403, 503, 504, 422, dll.
          retryStartTimeRef.current = null;
          setData(null);
          setErrorStatus(err.status);
          if (err.status === 403) {
            // Pastikan pesan hanya dipakai untuk kondisi 403 yang relevan (dokumen non-publik / login)
            const detailStr = typeof err.detail === 'string'
              ? err.detail.toLowerCase()
              : JSON.stringify(err.detail || '').toLowerCase();
            const isNonPublicRestriction = Boolean(
              statusDoc?.access_classification === 'non_publik' ||
              detailStr.includes('non-publik') ||
              detailStr.includes('non_publik') ||
              detailStr.includes('login') ||
              detailStr.includes('autentikasi')
            );
            if (isNonPublicRestriction) {
              setErrorMessage('Dokumen non-publik baru bisa dianalisis setelah fitur login aktif.');
            } else {
              setErrorMessage(err.message || 'Akses ditolak: Anda tidak memiliki wewenang untuk menelaah dokumen ini.');
            }
          } else if (err.status === 503) {
            setErrorMessage('Layanan analisis ML belum siap. Pastikan perintah "hero bridge serve" aktif di server.');
          } else if (err.status === 504) {
            setErrorMessage('Layanan analisis membutuhkan waktu terlalu lama (melebihi batas waktu respons).');
          } else if (err.status === 422) {
            setErrorMessage('Parameter permintaan analisis tidak valid.');
          } else {
            setErrorMessage(err.message || 'Terjadi galat teknis saat memuat data analisis.');
          }
        } else if (err instanceof Error) {
          retryStartTimeRef.current = null;
          setData(null);
          setErrorStatus(0);
          setErrorMessage(err.message || 'Gagal terhubung ke layanan analisis regulasi.');
        } else {
          retryStartTimeRef.current = null;
          setData(null);
          setErrorStatus(0);
          setErrorMessage('Terjadi galat tak dikenal saat memuat data analisis.');
        }
        setLoading(false);
        setIsRefreshing(false);
      }
    } catch (err: unknown) {
      if (controller.signal.aborted || !isMountedRef.current) return;
      retryStartTimeRef.current = null;
      setData(null);
      setErrorStatus(0);
      setErrorMessage(err instanceof Error ? err.message : 'Terjadi galat teknis saat memuat analisis.');
      setLoading(false);
      setIsRefreshing(false);
    }
  }, [abortAnalysisRequest, clearRetryTimer, documentId, mode]);

  useEffect(() => {
    loadAnalysisRef.current = loadAnalysis;
  }, [loadAnalysis]);

  // Efek inisialisasi load analysis
  useEffect(() => {
    let isCancelled = false;

    const initialize = async () => {
      await Promise.resolve();
      if (!isCancelled && isMountedRef.current) {
        loadAnalysis(false, false);
      }
    };

    initialize();

    return () => {
      isCancelled = true;
      clearRetryTimer();
      abortAnalysisRequest();
    };
  }, [loadAnalysis, clearRetryTimer, abortAnalysisRequest]);

  // Pemuatan Berkas PDF Asli secara aman via apiFetchBlob
  const fetchPdf = useCallback((signal?: AbortSignal) => {
    if (!documentId) return;

    setPdfLoading(true);
    setPdfError(null);

    if (pdfBlobUrlRef.current) {
      URL.revokeObjectURL(pdfBlobUrlRef.current);
      pdfBlobUrlRef.current = null;
    }
    setPdfBlobUrl(null);

    const pdfEndpoint = data?.pdf && (data.pdf.startsWith('http://') || data.pdf.startsWith('https://'))
      ? data.pdf
      : `/api/v1/documents/${documentId}/pdf`;

    apiFetchBlob(pdfEndpoint, { signal })
      .then((blob) => {
        if (signal?.aborted) return;
        const objectUrl = URL.createObjectURL(blob);
        pdfBlobUrlRef.current = objectUrl;
        setPdfBlobUrl(objectUrl);
        setPdfLoading(false);
        setPdfError(null);
      })
      .catch((err: unknown) => {
        if (signal?.aborted) return;
        if (err instanceof DOMException && err.name === 'AbortError') return;
        if (err instanceof Error && err.name === 'AbortError') return;

        if (err instanceof ApiError && err.status === 403) {
          setPdfError(
            typeof err.detail === 'string'
              ? err.detail
              : 'Dokumen non-publik hanya dapat dibuka setelah login diaktifkan.'
          );
        } else if (err instanceof ApiError && err.status === 404) {
          setPdfError('Berkas PDF asli tidak ditemukan di penyimpanan peladen.');
        } else {
          setPdfError(err instanceof Error ? err.message : 'Gagal memuat berkas PDF dari peladen.');
        }
        setPdfLoading(false);
      });
  }, [documentId, data]);

  useEffect(() => {
    let isCancelled = false;
    const controller = new AbortController();

    const runFetch = async () => {
      await Promise.resolve();
      if (!isCancelled) {
        fetchPdf(controller.signal);
      }
    };

    runFetch();

    return () => {
      isCancelled = true;
      controller.abort();
      if (pdfBlobUrlRef.current) {
        URL.revokeObjectURL(pdfBlobUrlRef.current);
        pdfBlobUrlRef.current = null;
      }
    };
  }, [fetchPdf]);

  // Handler Expand/Collapse BAB
  const toggleBab = (babName: string) => {
    setExpandedBabs(prev => ({
      ...prev,
      [babName]: !prev[babName]
    }));
  };

  // Handler Klik Rujukan Pasal (US-37 / FR-ANL-06)
  const handleJumpToPasal = useCallback((pasalStr: string) => {
    if (!pasalStr || typeof pasalStr !== 'string') {
      showNavFeedback('warning', 'Rujukan pasal tidak valid atau kosong.');
      return;
    }

    const trimmed = pasalStr.trim();
    setSelectedPasal(trimmed);

    const parsed = parsePasalRef(trimmed);

    // Jika referensi tidak dapat dikenali nomor pasalnya (e.g. "Teks dokumen (pasal tidak terbaca)")
    // JANGAN PERNAH fallback ke Pasal 1!
    if (!parsed.pasalNum) {
      showNavFeedback('warning', `Rujukan "${trimmed}" tidak dapat ditelusuri ke nomor pasal tertentu.`);
      return;
    }

    // 1. Dapatkan nomor halaman fisik asli dari metadata yang valid (tanpa komputasi spekulatif)
    let targetPage: number | null = null;

    // Cari dari data artikel tersimpan di backend
    const matchingArticle = articles.find(a => {
      const aParsed = parsePasalRef(a.article_number);
      return aParsed.pasalNum === parsed.pasalNum;
    });

    if (matchingArticle && typeof matchingArticle.page === 'number' && matchingArticle.page > 0) {
      targetPage = matchingArticle.page;
    }

    // Jika tidak ada di artikel backend, cari dari poin_utama analisis ML
    if (!targetPage && data?.poin_utama) {
      const matchingPoint = data.poin_utama.find(p => {
        const pRef = p.ref || p.pasal;
        if (!pRef) return false;
        const pParsed = parsePasalRef(pRef);
        return pParsed.pasalNum === parsed.pasalNum;
      });
      if (matchingPoint && typeof matchingPoint.halaman === 'number' && matchingPoint.halaman > 0) {
        targetPage = matchingPoint.halaman;
      }
    }

    // Validasi nilai halaman terhadap totalPages jika totalPages valid
    if (targetPage !== null) {
      if (targetPage < 1) targetPage = 1;
      if (totalPages > 0 && targetPage > totalPages) {
        targetPage = totalPages;
      }
    }

    // 2. Expand Bab terkait pada accordion panel kiri secara presisi (tanpa match parsial)
    if (data?.kerangka && parsed.pasalNum) {
      for (const item of data.kerangka) {
        if (item.pasal?.some(p => parsePasalRef(p).pasalNum === parsed.pasalNum)) {
          if (item.bab) {
            setExpandedBabs(prev => ({ ...prev, [item.bab]: true }));
          }
          break;
        }
      }
    }

    // 3. Eksekusi navigasi sesuai mode tampilan aktif
    if (viewMode === 'pdf') {
      // Dalam mode PDF, JANGAN otomatis memaksa berpindah ke salinan teks!
      if (targetPage !== null) {
        setCurrentPage(targetPage);
        setPdfTargetPage(targetPage);
        showNavFeedback('success', `Menavigasi naskah PDF ke Halaman ${targetPage} (${trimmed})`);
      } else {
        showNavFeedback(
          'info',
          `Nomor halaman fisik PDF untuk ${trimmed} belum tercatat pada metadata dokumen. Anda dapat beralih ke tab "Naskah" untuk membaca pasal ini.`
        );
      }
    } else {
      // Dalam mode salinan resmi, cari elemen DOM dan scroll secara halus
      const targetElementId = parsed.canonicalId;
      if (!targetElementId) {
        showNavFeedback('warning', `Pengenal elemen untuk "${trimmed}" tidak dapat dibuat.`);
        return;
      }

      setHighlightedPasalId(targetElementId);

      setTimeout(() => {
        const el = document.getElementById(targetElementId);
        if (el && naskahContainerRef.current) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          if (targetPage !== null) {
            setCurrentPage(targetPage);
          }
          showNavFeedback(
            'success',
            `Menampilkan ${trimmed}${targetPage ? ` (Halaman ${targetPage})` : ''}`
          );
        } else {
          // Tangani kondisi bila elemen DOM target tidak ditemukan di salinan
          const hasKerangka = Array.isArray(data?.kerangka) && data.kerangka.length > 0;
          const hasArticles = articles.length > 0;
          if (!hasKerangka && !hasArticles) {
            showNavFeedback(
              'warning',
              `Struktur pasal naskah belum tersedia untuk ${isDraft ? 'draf ini' : isSeojk ? 'dokumen SEOJK ini' : 'dokumen ini'}. Silakan buka tab "PDF Asli"${targetPage ? ` (Pasal berada di sekitar Hal. ${targetPage})` : ''}.`
            );
          } else {
            showNavFeedback(
              'warning',
              `Teks ${trimmed} tidak ditemukan dalam naskah hasil ekstraksi dokumen ini.`
            );
          }
        }
      }, 60);

      if (highlightTimerRef.current) {
        clearTimeout(highlightTimerRef.current);
      }
      highlightTimerRef.current = setTimeout(() => {
        setHighlightedPasalId(null);
        highlightTimerRef.current = null;
      }, 3500);
    }
  }, [articles, data, isDraft, isSeojk, showNavFeedback, totalPages, viewMode]);

  // Pulihkan navigasi pasal saat pertama kali data berhasil dimuat (Pekerjaan B)
  const hasRestoredPasalRef = useRef<boolean>(false);
  useEffect(() => {
    if (!loading && data && selectedPasal && !hasRestoredPasalRef.current) {
      hasRestoredPasalRef.current = true;
      if (selectedPasal !== 'Pasal 1') {
        const timer = setTimeout(() => {
          handleJumpToPasal(selectedPasal);
        }, 50);
        return () => clearTimeout(timer);
      }
    }
  }, [loading, data, selectedPasal, handleJumpToPasal]);

  // Handler Memuat Perbandingan Deterministik vs AI (US-05 #49)
  const loadComparison = useCallback(async () => {
    setComparisonLoading(true);
    setComparisonError(null);
    try {
      const res = await getDocumentAnalysisComparison(documentId);
      setComparisonData(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setComparisonError('Akses ditolak: Dokumen non-publik memerlukan autentikasi aktif.');
        } else if (err.status === 404) {
          setComparisonError('Dokumen tidak ditemukan atau data perbandingan analisis belum tersedia.');
        } else {
          setComparisonError(err.message || 'Gagal memuat perbandingan analisis regulasi.');
        }
      } else if (err instanceof Error) {
        setComparisonError(err.message);
      } else {
        setComparisonError('Gagal memuat perbandingan analisis.');
      }
    } finally {
      setComparisonLoading(false);
    }
  }, [documentId]);

  // Efek Pemetaan Rujukan Dasar Hukum ke Dokumen Knowledge Base
  useEffect(() => {
    if (!data?.dasar_hukum || data.dasar_hukum.length === 0) return;

    const initialMap: Record<string, { available: boolean; documentId?: number; title?: string; isMultiple?: boolean }> = {};
    const unmapped: string[] = [];
    const legalRefs = docStatus?.legal_references || [];

    for (const dh of data.dasar_hukum) {
      const trimmedDh = dh.trim();
      const matchedRef = legalRefs.find(lr => {
        if (!lr.cited_text) return false;
        const ct = lr.cited_text.toLowerCase();
        const dt = trimmedDh.toLowerCase();
        return ct.includes(dt) || dt.includes(ct);
      });

      if (matchedRef && matchedRef.referenced_document_id) {
        initialMap[trimmedDh] = {
          available: true,
          documentId: matchedRef.referenced_document_id,
          title: matchedRef.cited_text
        };
      } else {
        unmapped.push(trimmedDh);
      }
    }

    setKbReferenceMap(prev => ({ ...prev, ...initialMap }));

    if (unmapped.length > 0) {
      const controller = new AbortController();
      (async () => {
        const updates: Record<string, { available: boolean; documentId?: number; title?: string; isMultiple?: boolean }> = {};
        for (const dh of unmapped) {
          if (controller.signal.aborted) break;
          try {
            // Ekstrak pola jenis, nomor, tahun (misal: "UU 4/2023", "UU No. 4 Tahun 2023", "Undang-Undang Nomor 4 Tahun 2023")
            const uuMatch = dh.match(/(?:Undang[- ]Undang|UU)\s*(?:Nomor|No\.?)?\s*([0-9]+)\s*(?:Tahun|THN|\/)?\s*([0-9]{4})/i);
            const query = uuMatch ? `UU ${uuMatch[1]}/${uuMatch[2]}` : dh;
            const res = await getKnowledgeBaseDocuments({ q: query, limit: 5 }, controller.signal);
            const items = res?.items || [];

            if (uuMatch) {
              const num = uuMatch[1].replace(/^0+/, '');
              const year = parseInt(uuMatch[2], 10);
              const exactMatches = items.filter(it => {
                const itNum = (it.regulation_number || '').replace(/^0+/, '');
                const itYear = it.regulation_year || (it.release_date ? parseInt(it.release_date.slice(0, 4), 10) : null);
                return itNum === num && (!year || itYear === year);
              });

              if (exactMatches.length === 1) {
                updates[dh] = { available: true, documentId: exactMatches[0].id, title: exactMatches[0].title };
              } else if (exactMatches.length > 1) {
                updates[dh] = { available: true, isMultiple: true };
              } else if (items.length === 1) {
                updates[dh] = { available: true, documentId: items[0].id, title: items[0].title };
              } else if (items.length > 1) {
                updates[dh] = { available: true, isMultiple: true };
              } else {
                updates[dh] = { available: false };
              }
            } else {
              if (items.length === 1) {
                updates[dh] = { available: true, documentId: items[0].id, title: items[0].title };
              } else if (items.length > 1) {
                updates[dh] = { available: true, isMultiple: true };
              } else {
                updates[dh] = { available: false };
              }
            }
          } catch {
            updates[dh] = { available: false };
          }
        }
        if (!controller.signal.aborted) {
          setKbReferenceMap(prev => ({ ...prev, ...updates }));
        }
      })();
      return () => controller.abort();
    }
  }, [data?.dasar_hukum, docStatus?.legal_references]);

  // Tombol "Lanjut ke Harmonisasi": buka tab Harmonisasi di panel kanan
  const handleGoToHarmonisasi = () => {
    setMobileActivePanel('hasil');
    bukaTabHarmonisasi();
    panelHasilRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  // Ekspor Hasil Analisis (DOCX, CSV, JSON) via Backend US-40
  const handleExportFormat = async (format: AnalysisExportFormat) => {
    if (isExporting || !data || loading) return;

    setIsExportMenuOpen(false);
    setIsExporting(true);
    setExportingFormat(format);
    setExportError(null);

    try {
      const actualMode: 'deterministik' | 'ai' =
        data.mode_dipakai === 'ai' || data.mode_dipakai === 'deterministik'
          ? data.mode_dipakai
          : mode;

      // Hanya teruskan run_id jika sah tersedia dari data eksekusi/cache saat ini
      const activeRunId =
        typeof data.cache?.run_id === 'number' && data.cache.run_id > 0
          ? data.cache.run_id
          : undefined;

      const blob = await exportDocumentAnalysis(documentId, {
        format,
        mode: actualMode,
        run_id: activeRunId,
      });

      // Gunakan nama file dari header Content-Disposition (blob.filename), fallback jika kosong
      let resolvedFilename = blob.filename;
      if (!resolvedFilename || resolvedFilename.trim() === '') {
        const jenisClean = data.identitas?.jenis
          ? String(data.identitas.jenis).replace(/[/\\:*?"<>|.]/g, '_').trim()
          : '';
        const nomorClean = data.identitas?.nomor || data.identitas?.number
          ? String(data.identitas?.nomor || data.identitas?.number).replace(/[/\\:*?"<>|.]/g, '_').trim()
          : '';
        const tahunClean = data.identitas?.tahun || data.identitas?.year
          ? String(data.identitas?.tahun || data.identitas?.year).trim()
          : '';

        if (jenisClean && nomorClean && tahunClean) {
          resolvedFilename = `analisa_${jenisClean}_${nomorClean}_${tahunClean}_${actualMode}.${format}`;
        } else {
          resolvedFilename = `analisa_dokumen_${documentId}_${actualMode}.${format}`;
        }
      }

      // Buat object URL dari blob, picu download via anchor, lalu revoke secara aman
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = resolvedFilename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);
    } catch (err: unknown) {
      let userMessage = 'Terjadi kesalahan saat mengunduh berkas ekspor.';
      if (err instanceof ApiError) {
        if (err.status === 403) {
          userMessage = 'Akses ditolak: Dokumen non-publik memerlukan sesi login aktif.';
        } else if (err.status === 404) {
          const detailObj =
            err.detail && typeof err.detail === 'object'
              ? (err.detail as Record<string, unknown>)
              : null;
          if (detailObj?.code === 'belum_dianalisa') {
            userMessage =
              'Dokumen belum pernah dianalisa pada mode ini. Silakan jalankan analisa terlebih dahulu.';
          } else if (detailObj?.code === 'run_id_tidak_valid') {
            userMessage = 'ID riwayat eksekusi analisa tidak valid atau tidak ditemukan.';
          } else if (detailObj?.code === 'dokumen_nonaktif') {
            userMessage = 'Dokumen tidak aktif / telah dinonaktifkan.';
          } else {
            userMessage = err.message || 'Hasil analisa tidak ditemukan di basis data backend.';
          }
        } else if (err.status === 422) {
          userMessage = `Parameter ekspor tidak valid: ${err.message}`;
        } else if (err.status >= 500) {
          userMessage = `Terjadi gangguan server backend (HTTP ${err.status}). Silakan coba beberapa saat lagi.`;
        } else {
          userMessage = err.message || userMessage;
        }
      } else if (err instanceof Error) {
        userMessage = err.message;
      }
      setExportError(userMessage);
    } finally {
      setIsExporting(false);
      setExportingFormat(null);
    }
  };

  // Zoom Handler
  const handleZoomIn = () => setZoomLevel(prev => Math.min(150, prev + 15));
  const handleZoomOut = () => setZoomLevel(prev => Math.max(75, prev - 15));

  // Susunan Kerangka Bab & Pasal (Gunakan data.kerangka ML jika tersedia, fallback ke articles database)
  const kerangkaToDisplay = useMemo(() => {
    if (data?.kerangka && data.kerangka.length > 0) {
      return data.kerangka;
    }
    if (articles.length > 0) {
      // Kelompokkan articles dari backend berdasarkan chapter_title
      const babMap = new Map<string, string[]>();
      for (const art of articles) {
        const chapter = art.chapter_title?.trim() || 'BAB I';
        const pasalList = babMap.get(chapter) || [];
        if (!pasalList.includes(art.article_number)) {
          pasalList.push(art.article_number);
        }
        babMap.set(chapter, pasalList);
      }
      return Array.from(babMap.entries()).map(([chapter, pasalList]) => ({
        bab: chapter,
        judul: '',
        pasal: pasalList
      }));
    }
    return [];
  }, [articles, data?.kerangka]);

  // Filter Struktur Dokumen berdasarkan pencarian
  const filteredKerangka = kerangkaToDisplay.map(bab => ({
    ...bab,
    pasal: (bab.pasal || []).filter(p => 
      !structureSearch.trim() || p.toLowerCase().includes(structureSearch.toLowerCase().trim())
    )
  })).filter(bab => 
    !structureSearch.trim() || (bab.pasal && bab.pasal.length > 0) || (bab.judul && bab.judul.toLowerCase().includes(structureSearch.toLowerCase().trim()))
  );

  // Status Analisis Badge
  const getStatusBadge = () => {
    if (loading) {
      return (
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-50 text-amber-700 border border-amber-200 text-xs font-bold shrink-0">
          <Loader2 size={13} className="animate-spin text-amber-600" />
          <span>Sedang menganalisis</span>
        </div>
      );
    }
    if (errorStatus && !data) {
      if (errorStatus === 403) {
        return (
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-50 text-amber-800 border border-amber-200 text-xs font-bold shrink-0">
            <Lock size={13} className="text-amber-700" />
            <span>Akses Ditolak</span>
          </div>
        );
      }
      return (
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-50 text-red-700 border border-red-200 text-xs font-bold shrink-0">
          <AlertCircle size={13} className="text-red-600" />
          <span>Analisis gagal</span>
        </div>
      );
    }
    return (
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-bold shrink-0">
        <span className="w-2 h-2 rounded-full bg-emerald-500" />
        <span>Analisis selesai</span>
      </div>
    );
  };

  const actualMode = data?.mode_dipakai || mode;
  const isFallback = mode === 'ai' && data?.mode_dipakai === 'deterministik';
  const fallbackAbsolutePdfUrl = data?.pdf && (data.pdf.startsWith('http://') || data.pdf.startsWith('https://'))
    ? data.pdf
    : (API_BASE_URL
        ? `${API_BASE_URL}/api/v1/documents/${documentId}/pdf`
        : `/api/v1/documents/${documentId}/pdf`);
  const resolvedPdfUrl = pdfBlobUrl || fallbackAbsolutePdfUrl;

  // ============================================================================
  // Pemetaan Data Aktual Tanpa Fallback Hardcode (Aturan B)
  // ============================================================================
  // 1. Jumlah Bab: kerangka.length
  const jumlahBab = Array.isArray(data?.kerangka) ? data.kerangka.length : null;
  const displayJumlahBab = jumlahBab !== null && !isNaN(jumlahBab) ? String(jumlahBab) : '-';

  // 2. Jumlah Pasal: identitas.jumlah_pasal
  const rawJumlahPasal = data?.identitas?.jumlah_pasal;
  const jumlahPasal = typeof rawJumlahPasal === 'number' && !isNaN(rawJumlahPasal) ? rawJumlahPasal : null;
  const displayJumlahPasal = jumlahPasal !== null ? String(jumlahPasal) : '-';

  // 3. Jumlah Kewajiban dan Larangan: hitung dari poin_utama berdasarkan kategori aktual kontrak
  const poinUtama = Array.isArray(data?.poin_utama) ? data.poin_utama : null;
  const jumlahKewajiban = poinUtama
    ? poinUtama.filter(p => typeof p.kategori === 'string' && p.kategori.trim().toLowerCase() === 'kewajiban').length
    : null;
  const displayJumlahKewajiban = jumlahKewajiban !== null ? String(jumlahKewajiban) : '-';

  const jumlahLarangan = poinUtama
    ? poinUtama.filter(p => typeof p.kategori === 'string' && p.kategori.trim().toLowerCase() === 'larangan').length
    : null;
  const displayJumlahLarangan = jumlahLarangan !== null ? String(jumlahLarangan) : '-';

  // 4. Judul Regulasi: identitas.tentang
  const judulRegulasi = data?.identitas?.tentang?.trim() || null;
  const displayJudulRegulasi = judulRegulasi || data?.identitas?.nomor?.trim() || '-';

  // 4b. Identitas header naskah: bentuk pipeline (jenis, nomor, tahun, tentang, penerbit),
  //     nama field lama (doc_type, number, year, title, issuer) sebagai cadangan
  const teksIdentitas = (...nilai: unknown[]): string | null => {
    for (const v of nilai) {
      if (typeof v === 'number' && !isNaN(v)) return String(v);
      if (typeof v === 'string' && v.trim() !== '') return v.trim();
    }
    return null;
  };
  const naskahJenis = teksIdentitas(data?.identitas?.jenis, data?.identitas?.doc_type);
  const naskahNomor = teksIdentitas(data?.identitas?.nomor, data?.identitas?.number);
  const naskahTahun = teksIdentitas(data?.identitas?.tahun, data?.identitas?.year);
  const naskahTentang = teksIdentitas(data?.identitas?.tentang, data?.identitas?.title);
  const naskahPenerbit = teksIdentitas(data?.identitas?.penerbit, data?.identitas?.issuer);
  // Nomor kadang sudah memuat tahun (mis. "36 Tahun 2024"), jangan diulang
  const nomorMemuatTahun = Boolean(naskahNomor && /\bTahun\s+\d{4}\b/i.test(naskahNomor));
  const judulNaskah = naskahJenis || naskahNomor || naskahTahun
    ? `${naskahJenis ?? '-'} Nomor ${naskahNomor ?? '-'}${nomorMemuatTahun ? '' : ` Tahun ${naskahTahun ?? '-'}`}`
    : null;

  // 5. Tanggal Terbit: identitas.tanggal_terbit
  const tanggalTerbit = data?.identitas?.tanggal_terbit?.trim() || null;
  const displayTanggalTerbit = tanggalTerbit || '-';

  // 6. Kategori Poin Utama yang benar-benar ada di respon API
  const availableCategories = useMemo(() => {
    if (!data?.poin_utama) return ['Semua'];
    const cats = Array.from(new Set(data.poin_utama.map(p => p.kategori).filter(Boolean)));
    return ['Semua', ...cats];
  }, [data?.poin_utama]);

  // Hitung jumlah aktual poin per kategori untuk filter poin utama (Temuan QA 6B)
  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {
      Semua: data?.poin_utama ? data.poin_utama.length : 0,
    };
    if (data?.poin_utama) {
      for (const p of data.poin_utama) {
        if (p.kategori) {
          const cat = p.kategori.trim();
          counts[cat] = (counts[cat] || 0) + 1;
        }
      }
    }
    return counts;
  }, [data?.poin_utama]);

  // Helper Penyorotan Ayat Tertarget pada Teks Pasal (Temuan QA 3)
  const renderArticleContentWithAyat = (text: string | null | undefined, targetAyat: string | null) => {
    if (!text) return null;
    if (!targetAyat) return text;

    // Pola ayat di perundang-undangan RI: diawali tanda kurung "(3)" pada awal baris/paragraf
    const ayatRegex = new RegExp(`(^|\\n)\\s*\\(?(${targetAyat})\\)?\\s+([^\\n]+)`, 'i');
    const match = ayatRegex.exec(text);

    if (!match) {
      // Fallback: cari tanda kurung ayat sederhana "(3)"
      const simpleRegex = new RegExp(`(\\(${targetAyat}\\))`, 'g');
      if (!simpleRegex.test(text)) return text;
      const parts = text.split(simpleRegex);
      return (
        <>
          {parts.map((part, i) =>
            part === `(${targetAyat})` ? (
              <mark key={i} className="bg-amber-100 text-amber-900 font-bold px-1.5 py-0.5 rounded border border-amber-300">
                {part}
              </mark>
            ) : (
              part
            )
          )}
        </>
      );
    }

    const before = text.slice(0, match.index);
    const matchedLine = match[0];
    const after = text.slice(match.index + matchedLine.length);

    return (
      <>
        {before}
        <div className="bg-amber-50 border-l-4 border-amber-500 pl-3 py-1.5 my-2 rounded-r shadow-2xs">
          <span className="font-bold text-amber-900">({targetAyat}) </span>
          <span className="text-gray-900 font-medium">{match[3]}</span>
        </div>
        {after}
      </>
    );
  };

  return (
    <div className="w-full max-w-[1600px] mx-auto space-y-4 pb-16 font-sans">
      {/* 1. Header Workspace Breadcrumb */}
      <div className="flex items-center text-xs font-semibold tracking-wider text-gray-500 flex-wrap">
        <button 
          type="button"
          onClick={onBackToState1}
          className="hover:text-red-700 transition cursor-pointer"
        >
          DASHBOARD
        </button>
        <span className="mx-2 text-gray-400">&gt;</span>
        <button 
          type="button"
          onClick={onBackToState1}
          className="hover:text-red-700 transition cursor-pointer"
        >
          ANALISA REGULASI
        </button>
        {onBackToSummary && (
          <>
            <span className="mx-2 text-gray-400">&gt;</span>
            <button
              type="button"
              onClick={onBackToSummary}
              className="hover:text-red-700 transition cursor-pointer text-gray-700 font-bold"
              title="Kembali ke Ringkasan Eksekutif & Key Takeaways"
            >
              SUMMARY
            </button>
          </>
        )}
        <span className="mx-2 text-gray-400">&gt;</span>
        <span className="text-red-700 uppercase">WORKSPACE ANALISA</span>
      </div>

      {/* 2. Top Header Title & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Analisa Regulasi</h1>
          <p className="text-xs text-gray-600 mt-1 leading-relaxed">
            Telaah mendalam dan analisis dampak regulasi sektor jasa keuangan berbasis struktur pasal.
          </p>
        </div>

        {/* Tombol Aksi Header: Kembali ke Summary, Mulai Analisis Baru, Perbandingan Analisis, & Analisis Ulang */}
        <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
          {onBackToSummary && (
            <button
              type="button"
              onClick={onBackToSummary}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-red-200 bg-red-50 hover:bg-red-100 text-red-800 text-xs font-bold shadow-2xs transition cursor-pointer"
              title="Kembali ke tampilan Ringkasan Eksekutif dan Key Takeaways"
            >
              <ArrowLeft size={13} />
              <span>Kembali ke Summary</span>
            </button>
          )}

          <button
            type="button"
            onClick={onBackToState1}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-xs font-semibold shadow-2xs transition cursor-pointer"
            title="Keluar dari ruang kerja analisis ini dan mulai analisis dokumen baru"
          >
            <span>Mulai Analisis Baru</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setIsComparisonOpen(true);
              if (!comparisonData && !comparisonLoading) {
                void loadComparison();
              }
            }}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-red-200 bg-red-50 hover:bg-red-100 text-red-700 text-xs font-semibold shadow-2xs transition cursor-pointer"
            title="Buka perbandingan analisis Deterministik vs AI berdampingan (US-05 #49)"
          >
            <GitCompare size={12} />
            <span>Perbandingan Analisis</span>
          </button>
          <button
            type="button"
            onClick={() => loadAnalysis(true)}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-xs font-semibold shadow-2xs transition cursor-pointer"
            title="Kirim permintaan analisis ulang ke backend dengan parameter segar=true untuk memaksa kalkulasi ulang tanpa cache."
          >
            <RefreshCw size={12} className={loading && isRefreshing ? 'animate-spin text-red-700' : ''} />
            <span>Analisis Ulang</span>
          </button>
        </div>
      </div>

      {/* 3. Horizontal Card Identitas Dokumen & Status */}
      <div className="bg-white rounded-xl border border-gray-200 px-5 py-3.5 shadow-2xs flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div className="flex items-center gap-3.5 min-w-0">
          <div className="w-10 h-10 rounded-lg bg-red-50 text-red-700 border border-red-100 flex items-center justify-center shrink-0">
            <FileText size={20} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-sm font-bold text-gray-900 truncate max-w-[450px]">
                {displayJudulRegulasi !== '-' ? displayJudulRegulasi : (loading ? 'Memuat identitas draft...' : `Draft Peraturan #${documentId}`)}
              </h2>
              {/* Badge Status Keberlakuan Regulasi (Temuan QA 1) */}
              {effectiveStatusKeberlakuan && (
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border shrink-0 ${kelasBadgeStatusKeberlakuan(effectiveStatusKeberlakuan)}`}>
                  {labelStatusKeberlakuan(effectiveStatusKeberlakuan)}
                </span>
              )}

              {/* Badge Status Terdaftar di Knowledge Base (Temuan QA 1) */}
              {docStatus?.is_active !== undefined ? (
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border shrink-0 ${
                    docStatus.is_active
                      ? 'bg-slate-100 text-slate-700 border-slate-200'
                      : 'bg-gray-100 text-gray-500 border-gray-200'
                  }`}
                  title={docStatus.is_active ? 'Dokumen terdaftar aktif di Knowledge Base' : 'Dokumen dinonaktifkan di Knowledge Base'}
                >
                  {docStatus.is_active ? 'Aktif di KB' : 'Tidak Aktif di KB'}
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-semibold border border-slate-200 shrink-0">
                  Aktif di KB
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500 mt-0.5 truncate">
              {displayTanggalTerbit} • {data?.identitas?.jenis || '-'} • {displayJumlahBab} Bab • {displayJumlahPasal} Pasal
            </p>
          </div>
        </div>

        {/* Right Badges & Controls */}
        <div className="flex items-center gap-2.5 shrink-0 self-end md:self-auto">
          {/* Badge Cache Basi ("Hasil lama") */}
          {data?.cache?.basi === true && (
            <div
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-amber-200 bg-amber-50 text-amber-800 text-xs font-semibold"
              title={`Hasil analisis lama tersimpan (${data.cache.dibuat ? new Date(data.cache.dibuat).toLocaleString('id-ID') : 'cache terdahulu'})`}
            >
              <Clock size={13} className="text-amber-600" />
              <span>Hasil lama</span>
            </div>
          )}

          {/* Badge Mode Aktual */}
          <div 
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 bg-gray-50 text-gray-700 text-xs font-semibold"
            title={isFallback ? 'Mode AI dialihkan (fallback) ke Deterministik oleh backend' : `Menggunakan mode ${actualMode}`}
          >
            <FileCode size={13} className="text-gray-500" />
            <span>Mode {actualMode === 'ai' ? 'AI' : 'Deterministik'}</span>
            {isFallback && (
              <span className="text-[10px] font-bold text-amber-700 bg-amber-100 px-1.5 py-0.2 rounded">
                Fallback
              </span>
            )}
          </div>

          {/* Toggle AI Analisa (Disabled - Segera Hadir untuk MVP 3, Section H) */}
          <div
            className="relative group flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 bg-gray-50/80 cursor-not-allowed select-none"
            title="Analisa berbantuan AI akan tersedia pada pengembangan berikutnya."
          >
            <div className="flex items-center gap-1.5">
              <Sparkles size={13} className="text-gray-400" />
              <span className="text-xs font-semibold text-gray-500">Analisa AI</span>
              <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-amber-100 text-amber-800 border border-amber-200 uppercase">
                Segera
              </span>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={false}
              disabled={true}
              className="relative inline-flex h-4 w-8 shrink-0 cursor-not-allowed rounded-full border-2 border-transparent bg-gray-200 transition-colors opacity-60"
              aria-label="Toggle Analisa AI (Belum tersedia)"
            >
              <span className="pointer-events-none inline-block h-3 w-3 translate-x-0 rounded-full bg-white shadow transform ring-0 transition" />
            </button>
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 hidden group-hover:flex flex-col items-center z-30 pointer-events-none">
              <div className="bg-gray-900 text-white text-[11px] font-medium py-1 px-2.5 rounded shadow-lg whitespace-nowrap">
                Analisa berbantuan AI akan tersedia pada pengembangan berikutnya.
              </div>
              <div className="w-2 h-2 bg-gray-900 rotate-45 -mt-1" />
            </div>
          </div>

          {/* Badge Status */}
          {getStatusBadge()}

          <button
            type="button"
            onClick={onBackToState1}
            className="px-3 py-1.5 text-xs font-semibold text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition border border-gray-200 cursor-pointer"
            title="Kembali ke formulir upload"
          >
            Tinjau Input
          </button>
        </div>
      </div>

      {/* 3b. Kemiripan dengan draft lain (independen dari analisa, tidak memblokirnya) */}
      <PanelErrorBoundary nama="Kemiripan Draft">
        <KemiripanDraftBanner documentId={documentId} />
      </PanelErrorBoundary>

      {/* 4. PROCESSING PIPELINE BANNER */}
      {loading ? (
        <div className="bg-white rounded-xl border border-red-200/90 p-5 shadow-sm space-y-3.5 relative overflow-hidden bg-gradient-to-r from-red-50/50 via-white to-red-50/30 transition-all duration-300">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-red-100 text-red-700 flex items-center justify-center shrink-0">
                <Loader2 size={18} className="animate-spin text-red-700" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-gray-900">
                    Sistem HERO Sedang Memproses Analisis Regulasi
                  </h3>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-100 text-red-700 border border-red-200">
                    Tahap {pipelineStep} dari 4
                  </span>
                </div>
                <p className="text-xs text-gray-600 mt-0.5">
                  {PIPELINE_STEPS[pipelineStep - 1]?.desc}
                </p>
              </div>
            </div>
          </div>

          {/* Indeterminate Animated Moving Shimmer Track */}
          <div className="space-y-1.5">
            <style>{`
              @keyframes heroIndeterminateSlider {
                0% {
                  transform: translateX(-100%);
                }
                50% {
                  transform: translateX(100%);
                }
                100% {
                  transform: translateX(320%);
                }
              }
              .animate-hero-indeterminate {
                animation: heroIndeterminateSlider 1.8s cubic-bezier(0.4, 0, 0.2, 1) infinite;
              }
            `}</style>
            <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden border border-gray-200/60 relative">
              <div 
                className="h-full bg-gradient-to-r from-red-800 via-red-500 to-red-700 rounded-full w-1/3 animate-hero-indeterminate"
              />
            </div>
            <div className="flex items-center justify-between text-[11px] font-mono">
              <span className={retryCount > 0 || aiMelebihiLimaMenit ? 'text-amber-700 font-semibold animate-pulse' : 'text-gray-500'}>
                {loadingStatusText}
              </span>
              <span className="text-gray-500 font-medium">
                {retryCount > 0 ? `Percobaan Sinkronisasi #${retryCount}` : 'Sedang diproses...'}
              </span>
            </div>
            {aiMelebihiLimaMenit && (
              <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                <span>Proses ini sudah berjalan lebih dari 5 menit. Dokumen panjang/kompleks memang butuh waktu lebih lama untuk dianalisa AI — proses tidak akan dibatalkan otomatis dan hasilnya tetap akan muncul begitu selesai.</span>
              </div>
            )}
          </div>

          {/* 4 Pipeline Step Pills */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-1 border-t border-gray-100">
            {PIPELINE_STEPS.map((s) => {
              const isDone = s.id < pipelineStep;
              const isCurrent = s.id === pipelineStep;
              return (
                <div 
                  key={s.id}
                  className={`p-2 rounded-lg border text-xs flex items-center gap-2 transition ${
                    isDone
                      ? 'bg-emerald-50/70 border-emerald-200 text-emerald-800'
                      : isCurrent
                      ? 'bg-red-50 border-red-300 text-red-800 ring-1 ring-red-200 font-semibold'
                      : 'bg-gray-50/60 border-gray-100 text-gray-400'
                  }`}
                >
                  <div className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] shrink-0 ${
                    isDone
                      ? 'bg-emerald-600 text-white font-bold'
                      : isCurrent
                      ? 'bg-red-700 text-white animate-pulse'
                      : 'bg-gray-200 text-gray-500'
                  }`}>
                    {isDone ? <Check size={10} strokeWidth={3} /> : s.id}
                  </div>
                  <span className="truncate text-[11px]">{s.title}</span>
                </div>
              );
            })}
          </div>
        </div>
      ) : showProcessingBanner && data ? (
        <div className="bg-emerald-50/70 border border-emerald-200 rounded-xl px-4 py-2.5 flex items-center justify-between text-xs text-emerald-800 shadow-2xs">
          <div className="flex items-center gap-2.5">
            <div className="w-5 h-5 rounded-full bg-emerald-600 text-white flex items-center justify-center shrink-0">
              <Check size={12} strokeWidth={3} />
            </div>
            <span>
              <strong>Analisis Berhasil:</strong> Seluruh tahap ekstraksi dan identifikasi norma telah tuntas. {displayJumlahPasal} pasal dan {displayJumlahBab} bab siap ditelaah pada 3 panel workspace.
            </span>
            <DraftLabel />
          </div>
          <button
            type="button"
            onClick={() => setShowProcessingBanner(false)}
            className="text-emerald-700 hover:text-emerald-900 text-[11px] font-semibold cursor-pointer ml-2"
          >
            Tutup
          </button>
        </div>
      ) : null}

      {/* ERROR STATE: 404 / 403 / 503 / 504 / 422 (Temuan QA 6A) */}
      {!data && !loading && (
        <div className="bg-white rounded-xl border border-gray-200 p-8 shadow-xs">
          <div className="max-w-md mx-auto text-center space-y-4">
            <div className={`w-12 h-12 rounded-full flex items-center justify-center mx-auto ${
              errorStatus === 403 ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'
            }`}>
              {errorStatus === 403 ? <Lock size={24} /> : <AlertCircle size={24} />}
            </div>
            <div>
              <h3 className="text-base font-bold text-gray-900">
                {errorStatus === 403
                  ? 'Akses Ditolak'
                  : errorStatus === 404
                  ? (errorMessage?.includes('Batas waktu') ? 'Batas Waktu Sinkronisasi Tercapai' : 'Dokumen Belum Siap Dianalisis')
                  : errorStatus === 503
                  ? 'Layanan Analisis Belum Siap'
                  : errorStatus === 504
                  ? 'Layanan Analisis Membutuhkan Waktu Terlalu Lama'
                  : errorStatus === 422
                  ? 'Validasi Parameter Gagal'
                  : 'Gagal Memuat Analisis Regulasi'}
              </h3>
              <p className="text-xs text-gray-600 mt-1.5 leading-relaxed">
                {errorStatus === 403
                  ? 'Anda tidak memiliki izin untuk mengakses dokumen ini. Dokumen non-publik memerlukan sesi login aktif.'
                  : (errorMessage || 'Terjadi kendala teknis saat menghubungi peladen backend.')}
              </p>
            </div>
            <div className="flex items-center justify-center gap-2.5 pt-1">
              {/* Sembunyikan tombol "Coba Lagi" untuk 403 Akses Ditolak (Temuan QA 6A) */}
              {errorStatus !== 403 && (
                <button
                  type="button"
                  onClick={() => loadAnalysis(false, false)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-700 hover:bg-red-800 text-white rounded-lg text-xs font-semibold shadow-xs transition cursor-pointer"
                >
                  <RefreshCw size={13} />
                  <span>Coba Lagi</span>
                </button>
              )}
              <button
                type="button"
                onClick={onBackToState1}
                className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold shadow-xs transition cursor-pointer ${
                  errorStatus === 403
                    ? 'bg-red-700 hover:bg-red-800 text-white'
                    : 'bg-white border border-gray-300 hover:bg-gray-50 text-gray-700'
                }`}
              >
                <span>Mulai Analisis Baru</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* WORKSPACE 3-PANEL (Struktur Dokumen | Naskah Regulasi | Hasil Analisis) */}
      {data && !loading && (
        <div className="space-y-3">
          {/* Kontrol Navigasi Adaptif Layar Mobile / Tablet */}
          <div className="flex lg:hidden bg-gray-100 p-1 rounded-xl text-xs font-semibold mb-3 shadow-2xs">
          <button
            type="button"
            onClick={() => setMobileActivePanel('struktur')}
            className={`flex-1 py-1.5 text-center rounded-lg transition cursor-pointer ${
              mobileActivePanel === 'struktur'
                ? 'bg-white text-gray-900 shadow-2xs font-bold'
                : 'text-gray-500 hover:text-gray-800'
            }`}
          >
            Struktur ({displayJumlahPasal}P)
          </button>
          <button
            type="button"
            onClick={() => setMobileActivePanel('naskah')}
            className={`flex-1 py-1.5 text-center rounded-lg transition cursor-pointer ${
              mobileActivePanel === 'naskah'
                ? 'bg-white text-gray-900 shadow-2xs font-bold'
                : 'text-gray-500 hover:text-gray-800'
            }`}
          >
            Naskah Regulasi
          </button>
          <button
            type="button"
            onClick={() => setMobileActivePanel('hasil')}
            className={`flex-1 py-1.5 text-center rounded-lg transition cursor-pointer ${
              mobileActivePanel === 'hasil'
                ? 'bg-white text-gray-900 shadow-2xs font-bold'
                : 'text-gray-500 hover:text-gray-800'
            }`}
          >
            Hasil Analisis
          </button>
        </div>

        {/* WORKSPACE 3-PANEL DENGAN MANUAL COLLAPSE */}
        <div className="flex items-stretch gap-3.5 h-[calc(100vh-215px)] min-h-[640px] max-h-[880px] w-full">
          {/* =================================================================== */}
          {/* PANEL KIRI: STRUKTUR DOKUMEN */}
          {/* =================================================================== */}
          {isLeftCollapsed ? (
            <div className="hidden lg:flex w-11 bg-white rounded-xl border border-gray-200 flex-col items-center py-3.5 shadow-2xs shrink-0 transition-all duration-300">
              <button
                type="button"
                onClick={() => setIsLeftCollapsed(false)}
                title="Buka Panel Struktur Dokumen (Bab & Pasal)"
                className="p-1.5 rounded-lg text-gray-500 hover:text-red-700 hover:bg-red-50 transition cursor-pointer"
              >
                <PanelLeftOpen size={18} />
              </button>
              <div className="mt-4 flex-1 flex items-center justify-center">
                <span className="[writing-mode:vertical-lr] rotate-180 text-[10px] font-bold text-gray-400 tracking-wider uppercase select-none">
                  Struktur Dokumen
                </span>
              </div>
              <span className="text-[9px] font-mono font-bold text-gray-400 py-1">
                {displayJumlahPasal}P
              </span>
            </div>
          ) : (
            <PanelErrorBoundary
              nama="Struktur Dokumen"
              className={`${mobileActivePanel === 'struktur' ? 'flex' : 'hidden'} lg:flex w-full lg:w-[260px] xl:w-[280px] shrink-0 bg-white rounded-xl border border-gray-200 h-full p-4`}
              onCobaLagi={() => loadAnalysis(false, false)}
            >
            <div className={`${mobileActivePanel === 'struktur' ? 'flex' : 'hidden'} lg:flex w-full lg:w-[260px] xl:w-[280px] shrink-0 bg-white rounded-xl border border-gray-200 flex-col shadow-2xs overflow-hidden h-full transition-all duration-300`}>
              {/* Header Panel Kiri */}
              <div className="p-3.5 border-b border-gray-100 flex items-center justify-between shrink-0 bg-white">
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                    Struktur Dokumen
                  </h3>
                  <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                    {displayJumlahBab}B • {displayJumlahPasal}P
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setIsLeftCollapsed(true)}
                  title="Ciutkan Panel Struktur Dokumen"
                  className="p-1 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition cursor-pointer"
                >
                  <PanelLeftClose size={15} />
                </button>
              </div>

              {/* Filter Cepat Pasal */}
              <div className="p-2.5 border-b border-gray-100 bg-gray-50/50 shrink-0">
                <div className="relative">
                  <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input
                    type="text"
                    value={structureSearch}
                    onChange={(e) => setStructureSearch(e.target.value)}
                    placeholder="Cari bab atau pasal..."
                    className="w-full pl-8 pr-7 py-1.5 text-xs bg-white border border-gray-200 rounded-lg focus:outline-none focus:border-red-700 focus:ring-1 focus:ring-red-700 transition"
                  />
                  {structureSearch && (
                    <button
                      type="button"
                      onClick={() => setStructureSearch('')}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 p-0.5 cursor-pointer"
                      title="Hapus pencarian"
                    >
                      <X size={12} />
                    </button>
                  )}
                </div>
              </div>

              {/* Tree View Bab & Pasal */}
              <div className="flex-1 overflow-y-auto min-h-0 p-2.5 space-y-1.5 text-xs text-gray-700">
              {filteredKerangka.length === 0 && (
                structureSearch.trim() !== '' ? (
                  <div className="py-8 text-center text-xs text-gray-400">
                    Tidak ada bab atau pasal yang cocok dengan &quot;{structureSearch}&quot;.
                  </div>
                ) : isSeojk ? (
                  <div className="py-8 px-3 text-center text-xs text-gray-500 space-y-1.5">
                    <p className="font-semibold text-gray-700">Dokumen SEOJK ini tidak memiliki struktur BAB/Pasal yang dapat ditampilkan.</p>
                    <p className="text-[11px] text-gray-400">Silakan gunakan tab PDF Asli untuk membaca naskah lengkap.</p>
                  </div>
                ) : (
                  <div className="py-8 px-3 text-center text-xs text-gray-500 space-y-1.5">
                    <p className="font-semibold text-gray-700">Dokumen {isDraft ? 'draf' : 'regulasi'} ini tidak memiliki struktur BAB/Pasal yang dapat ditampilkan.</p>
                    <p className="text-[11px] text-gray-400">Silakan gunakan tab PDF Asli untuk membaca naskah lengkap.</p>
                  </div>
                )
              )}

              {filteredKerangka.map((item, babIdx) => {
                const babKey = item.bab || `BAB ${babIdx + 1}`;
                const isExpanded = Boolean(expandedBabs[babKey]);

                return (
                  <div key={babKey} className="border border-gray-100 rounded-lg overflow-hidden bg-gray-50/30">
                    <button
                      type="button"
                      onClick={() => toggleBab(babKey)}
                      className="w-full px-2.5 py-2 flex items-center justify-between text-left hover:bg-gray-100/70 transition font-bold text-gray-800 text-[11px] cursor-pointer"
                    >
                      <span className="truncate pr-1">
                        {babKey} - {item.judul || 'UMUM'}
                      </span>
                      {isExpanded ? (
                        <ChevronDown size={14} className="text-gray-500 shrink-0" />
                      ) : (
                        <ChevronRight size={14} className="text-gray-400 shrink-0" />
                      )}
                    </button>

                    {isExpanded && item.pasal && item.pasal.length > 0 && (
                      <div className="py-1 px-1.5 space-y-0.5 bg-white border-t border-gray-100">
                        {item.pasal.map((pasalText, pIdx) => {
                          const selParsed = parsePasalRef(selectedPasal);
                          const curParsed = parsePasalRef(pasalText);
                          const isSelected = Boolean(
                            (selParsed.pasalNum && curParsed.pasalNum && selParsed.pasalNum === curParsed.pasalNum) ||
                            selectedPasal.toLowerCase() === pasalText.toLowerCase()
                          );

                          return (
                            <button
                              key={pIdx}
                              type="button"
                              onClick={() => handleJumpToPasal(pasalText)}
                              className={`w-full text-left px-2 py-1.5 rounded-md flex items-center justify-between text-xs transition cursor-pointer ${
                                isSelected
                                  ? 'bg-red-50 text-red-700 font-semibold border-l-2 border-red-700'
                                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                              }`}
                            >
                              <span className="truncate">{pasalText}</span>
                              {isSelected && <Check size={12} className="text-red-700 shrink-0 ml-1" />}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            </div>
            </PanelErrorBoundary>
          )}

          {/* =================================================================== */}
          {/* PANEL TENGAH: NASKAH REGULASI (HASIL EKSTRAKSI) & PDF */}
          {/* =================================================================== */}
          <PanelErrorBoundary
            nama="Naskah Regulasi"
            className={`${mobileActivePanel === 'naskah' ? 'flex' : 'hidden'} lg:flex flex-1 min-w-0 bg-white rounded-xl border border-gray-200 h-full p-4`}
            onCobaLagi={() => loadAnalysis(false, false)}
          >
          <div className={`${mobileActivePanel === 'naskah' ? 'flex' : 'hidden'} lg:flex flex-1 min-w-0 bg-white rounded-xl border border-gray-200 flex-col shadow-2xs overflow-hidden h-full transition-all duration-300`}>
            {/* Header Panel Tengah */}
            <div className="p-3 border-b border-gray-100 flex flex-wrap items-center justify-between gap-2.5 shrink-0 bg-white">
              <div className="flex items-center gap-2 text-xs">
                {isLeftCollapsed && (
                  <button
                    type="button"
                    onClick={() => setIsLeftCollapsed(false)}
                    className="hidden lg:inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold text-gray-600 hover:text-red-700 hover:bg-red-50 rounded-lg border border-gray-200 transition cursor-pointer shadow-2xs"
                    title="Buka kembali panel Struktur Dokumen"
                  >
                    <PanelLeftOpen size={13} />
                    <span>Struktur</span>
                  </button>
                )}
                <span className="font-bold text-gray-900 uppercase tracking-wide">
                  NASKAH REGULASI
                </span>
                <span className="text-gray-300">|</span>
                <div className="flex items-center bg-gray-100 p-0.5 rounded-lg text-[11px] font-semibold">
                  <button
                    type="button"
                    onClick={() => setViewMode('salinan')}
                    className={`px-2.5 py-1 rounded-md transition cursor-pointer ${
                      viewMode === 'salinan'
                        ? 'bg-white text-gray-900 shadow-2xs'
                        : 'text-gray-500 hover:text-gray-900'
                    }`}
                  >
                    Naskah
                  </button>
                  <button
                    type="button"
                    onClick={() => setViewMode('pdf')}
                    className={`px-2.5 py-1 rounded-md transition cursor-pointer ${
                      viewMode === 'pdf'
                        ? 'bg-white text-gray-900 shadow-2xs'
                        : 'text-gray-500 hover:text-gray-900'
                    }`}
                  >
                    PDF Asli
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <a
                  href={resolvedPdfUrl}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => {
                    if (pdfBlobUrl) {
                      e.preventDefault();
                      const targetUrl = pdfTargetPage ? `${pdfBlobUrl}#page=${pdfTargetPage}` : pdfBlobUrl;
                      window.open(targetUrl, '_blank');
                    }
                  }}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-gray-600 hover:text-red-700 transition cursor-pointer"
                >
                  <ExternalLink size={12} />
                  <span>Buka PDF Asli</span>
                </a>

                {viewMode === 'salinan' && (
                  <div className="flex items-center gap-1 bg-gray-50 border border-gray-200 rounded-lg px-2 py-0.5 text-xs text-gray-600">
                    <button type="button" onClick={handleZoomOut} title="Perkecil" className="p-0.5 hover:text-gray-900 cursor-pointer">
                      <ZoomOut size={12} />
                    </button>
                    <span className="text-[10px] font-mono font-medium px-1.5">{zoomLevel}%</span>
                    <button type="button" onClick={handleZoomIn} title="Perbesar" className="p-0.5 hover:text-gray-900 cursor-pointer">
                      <ZoomIn size={12} />
                    </button>
                  </div>
                )}

                <span className="text-[11px] text-gray-400 font-mono">
                  Hal. {currentPage} / {totalPages}
                </span>

                {isRightCollapsed && (
                  <button
                    type="button"
                    onClick={() => setIsRightCollapsed(false)}
                    className="hidden lg:inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold text-gray-600 hover:text-red-700 hover:bg-red-50 rounded-lg border border-gray-200 transition cursor-pointer shadow-2xs ml-1"
                    title="Buka kembali panel Hasil Analisis"
                  >
                    <span>Analisis</span>
                    <PanelRightOpen size={13} />
                  </button>
                )}
              </div>
            </div>

            {/* Banner Notifikasi Navigasi Rujukan Pasal (US-37) */}
            {navFeedback && (
              <div className={`px-3.5 py-2 border-b flex items-center justify-between text-xs transition-all shrink-0 ${
                navFeedback.type === 'success'
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-100'
                  : navFeedback.type === 'warning'
                  ? 'bg-amber-50 text-amber-800 border-amber-200'
                  : 'bg-blue-50 text-blue-800 border-blue-100'
              }`}>
                <div className="flex items-center gap-2">
                  {navFeedback.type === 'success' && <Check size={14} className="text-emerald-600 shrink-0" />}
                  {navFeedback.type === 'warning' && <AlertCircle size={14} className="text-amber-600 shrink-0" />}
                  {navFeedback.type === 'info' && <Info size={14} className="text-blue-600 shrink-0" />}
                  <span className="font-medium">{navFeedback.message}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setNavFeedback(null)}
                  className="text-gray-400 hover:text-gray-600 p-0.5 cursor-pointer ml-2"
                  title="Tutup pemberitahuan"
                >
                  <X size={12} />
                </button>
              </div>
            )}

            {/* Konten Naskah: PDF Asli atau naskah hasil ekstraksi */}
            {viewMode === 'pdf' ? (
              <div className="flex-1 bg-gray-100 flex flex-col items-center justify-center p-2 relative overflow-hidden min-h-0">
                {pdfLoading ? (
                  <div className="flex flex-col items-center justify-center gap-2.5 p-8 text-gray-500">
                    <Loader2 size={24} className="animate-spin text-red-700" />
                    <span className="text-xs font-medium">Memuat berkas PDF asli dari peladen...</span>
                  </div>
                ) : pdfError ? (
                  <div className="p-6 max-w-sm mx-auto text-center space-y-3 bg-white rounded-xl border border-gray-200 shadow-xs">
                    <div className="w-10 h-10 rounded-full bg-red-100 text-red-700 flex items-center justify-center mx-auto">
                      <AlertCircle size={20} />
                    </div>
                    <div>
                      <h4 className="text-xs font-bold text-gray-900">Gagal Memuat PDF Asli</h4>
                      <p className="text-[11px] text-gray-500 mt-1 leading-relaxed">
                        {pdfError}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => fetchPdf()}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-red-700 hover:bg-red-800 text-white rounded-lg text-xs font-semibold shadow-xs transition cursor-pointer"
                    >
                      <RefreshCw size={12} />
                      <span>Coba Lagi</span>
                    </button>
                  </div>
                ) : pdfBlobUrl ? (
                  <iframe
                    key={pdfTargetPage ? `pdf-p-${pdfTargetPage}` : 'pdf-initial'}
                    src={pdfBlobUrl ? (pdfTargetPage ? `${pdfBlobUrl}#page=${pdfTargetPage}` : pdfBlobUrl) : ''}
                    className="w-full h-full border-0 rounded bg-white shadow-2xs"
                    title={`Naskah PDF Asli #${documentId}`}
                  />
                ) : (
                  <div className="text-xs text-gray-400 p-8 text-center">
                    Berkas PDF asli tidak tersedia untuk dokumen ini.
                  </div>
                )}
              </div>
            ) : (
              <div 
                ref={naskahContainerRef}
                className="flex-1 overflow-y-auto min-h-0 px-6 py-6 bg-gray-50/40 select-text scroll-smooth"
              >
                <div 
                  style={{ fontSize: `${(zoomLevel / 100) * 12.5}px` }}
                  className="max-w-[760px] mx-auto space-y-6 text-gray-800 leading-relaxed transition-all"
                >
                  {/* Header Naskah Hasil Ekstraksi (bukan salinan resmi) */}
                  <div className="text-center space-y-2 pb-5 border-b border-gray-200">
                    <p className="text-[0.85em] font-mono tracking-widest uppercase text-gray-500 font-bold">
                      NASKAH HASIL EKSTRAKSI (BUKAN SALINAN RESMI)
                    </p>
                    {naskahPenerbit && (
                      <h2 className="text-[1.05em] font-bold uppercase tracking-wider text-gray-900">
                        {naskahPenerbit}
                      </h2>
                    )}
                    {judulNaskah && (
                      <p className="text-[0.95em] font-semibold text-gray-800">
                        {judulNaskah}
                      </p>
                    )}
                    {naskahTentang && (
                      <>
                        <p className="text-[0.85em] font-bold text-gray-600 tracking-wider">
                          TENTANG
                        </p>
                        <h1 className="text-[1.05em] font-extrabold uppercase tracking-wide text-gray-900 max-w-md mx-auto">
                          {naskahTentang}
                        </h1>
                      </>
                    )}
                  </div>

                  {/* Dasar Hukum Terkait (Konsiderans Mengingat) */}
                  {data.dasar_hukum && data.dasar_hukum.length > 0 && (
                    <div className="space-y-1.5 text-left text-[0.92em]">
                      <span className="font-bold text-gray-900 block mb-1">Dasar Hukum Terkait:</span>
                      <div className="pl-4 space-y-1 text-gray-700">
                        {data.dasar_hukum.map((dh, idx) => (
                          <p key={idx} className="flex gap-2">
                            <span className="font-semibold text-gray-800 shrink-0">{idx + 1}.</span>
                            <span>{dh}</span>
                          </p>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Kerangka Bab & Pasal Dinamis */}
                  {data.kerangka && data.kerangka.length > 0 ? (
                    data.kerangka.map((bab, bIdx) => {
                      const babKey = bab.bab || `BAB ${bIdx + 1}`;
                      return (
                        <div key={babKey} className="space-y-4 pt-2">
                          <div className="text-center pt-2">
                            <h3 className="font-bold text-[0.95em] uppercase tracking-wider text-gray-900">
                              {babKey}<br />{bab.judul || ''}
                            </h3>
                          </div>
                          {(bab.pasal || []).map((pasalStr) => {
                            const parsed = parsePasalRef(pasalStr);
                            const selectedParsed = parsePasalRef(selectedPasal);
                            const isCurrentPasal = Boolean(parsed.pasalNum && selectedParsed.pasalNum === parsed.pasalNum);
                            const targetAyat = isCurrentPasal ? selectedParsed.ayatNum : null;
                            const targetId = parsed.canonicalId || undefined;
                            const points = (data.poin_utama || []).filter(p => {
                              const pRef = p.ref || p.pasal;
                              if (!pRef) return false;
                              const pParsed = parsePasalRef(pRef);
                              return Boolean(parsed.pasalNum && pParsed.pasalNum === parsed.pasalNum);
                            });
                            const isHighlighted = targetId ? highlightedPasalId === targetId : false;

                            // Cari teks lengkap artikel dari hasil ekstraksi backend secara presisi
                            const matchingArticle = articles.find(a => {
                              if (!parsed.pasalNum) return false;
                              const aParsed = parsePasalRef(a.article_number);
                              return aParsed.pasalNum === parsed.pasalNum;
                            });
                            const fullArticleText = matchingArticle?.content_text;

                            return (
                              <div
                                key={pasalStr}
                                id={targetId}
                                className={`rounded-xl border p-4 transition-all duration-200 ${
                                  isHighlighted
                                    ? 'border-red-600 bg-red-50/40 ring-2 ring-red-200 shadow-sm'
                                    : 'border-gray-200 bg-white hover:border-gray-300 shadow-2xs'
                                }`}
                              >
                                <div className="flex items-center justify-between mb-2.5 pb-2 border-b border-gray-100">
                                  <div className="flex items-center gap-2">
                                    <span className="font-bold text-[0.95em] text-gray-900">{pasalStr}</span>
                                    {matchingArticle?.page && (
                                      <span className="text-[0.75em] font-mono px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                                        Hal. {matchingArticle.page}
                                      </span>
                                    )}
                                  </div>
                                  {points[0]?.kategori && (
                                    <span className="text-[0.75em] font-medium px-2 py-0.5 rounded bg-gray-100 text-gray-600">
                                      {points[0].kategori}
                                    </span>
                                  )}
                                </div>
                                {fullArticleText ? (
                                  <div className="space-y-3 text-left">
                                    <div className="text-gray-800 leading-relaxed text-[0.92em] whitespace-pre-line font-serif">
                                      {renderArticleContentWithAyat(fullArticleText, targetAyat)}
                                    </div>
                                    {isTeksTerpotong(fullArticleText) && (
                                      <p className="text-[0.75em] italic text-amber-700">
                                        Teks dipotong, buka tab PDF Asli untuk teks lengkap.
                                      </p>
                                    )}
                                    {points.length > 0 && (
                                      <div className="pt-2.5 border-t border-gray-100 space-y-1.5">
                                        <div className="flex items-center justify-between gap-2">
                                          <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block">
                                            Intisari &amp; Norma Terdeteksi ({points.length} klausul)
                                          </span>
                                          <DraftLabel ukuran="kecil" />
                                        </div>
                                        {points.map((pt, pIdx) => (
                                          <div key={pIdx} className="bg-red-50/50 p-2 rounded-lg border border-red-100/70 text-xs">
                                            <span className="font-semibold text-red-800">[{pt.kategori}]</span>{' '}
                                            <span className="text-gray-700">{pt.parafrase || pt.teks}</span>
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                ) : points.length > 0 ? (
                                  <div className="space-y-2 text-left text-gray-700">
                                    <DraftLabel ukuran="kecil" />
                                    {points.map((pt, pIdx) => (
                                      <div key={pIdx} className="space-y-1">
                                        <p className="text-gray-800 leading-relaxed text-[0.92em]">
                                          {pt.teks}
                                        </p>
                                        {pt.parafrase && pt.parafrase !== pt.teks && (
                                          <p className="text-xs text-gray-500 italic bg-gray-50 p-2 rounded border border-gray-100">
                                            Intisari: {pt.parafrase}
                                          </p>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <p className="text-gray-500 text-left text-[0.9em] italic">
                                    Teks klausul lengkap dapat dilihat pada tab PDF Asli.
                                  </p>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      );
                    })
                  ) : articles.length > 0 ? (
                    <div className="space-y-4 pt-2">
                      <div className="p-3 bg-amber-50/60 border border-amber-200/80 rounded-lg text-xs text-amber-800">
                        Kerangka bab dari ML belum diekstrak; menampilkan daftar naskah pasal dari ekstraksi peladen ({articles.length} pasal).
                      </div>
                      {articles.map((art) => {
                        const parsed = parsePasalRef(art.article_number);
                        const selectedParsed = parsePasalRef(selectedPasal);
                        const isCurrentPasal = Boolean(parsed.pasalNum && selectedParsed.pasalNum === parsed.pasalNum);
                        const targetAyat = isCurrentPasal ? selectedParsed.ayatNum : null;
                        const targetId = parsed.canonicalId || undefined;
                        const isHighlighted = targetId ? highlightedPasalId === targetId : false;
                        const points = (data.poin_utama || []).filter(p => {
                          const pRef = p.ref || p.pasal;
                          if (!pRef) return false;
                          const pParsed = parsePasalRef(pRef);
                          return Boolean(parsed.pasalNum && pParsed.pasalNum === parsed.pasalNum);
                        });
                        return (
                          <div
                            key={art.id}
                            id={targetId}
                            className={`rounded-xl border p-4 transition-all duration-200 ${
                              isHighlighted
                                ? 'border-red-600 bg-red-50/40 ring-2 ring-red-200 shadow-sm'
                                : 'border-gray-200 bg-white hover:border-gray-300 shadow-2xs'
                            }`}
                          >
                            <div className="flex items-center justify-between mb-2.5 pb-2 border-b border-gray-100">
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-[0.95em] text-gray-900">{art.article_number}</span>
                                {art.page && (
                                  <span className="text-[0.75em] font-mono px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                                    Hal. {art.page}
                                  </span>
                                )}
                              </div>
                              {points[0]?.kategori && (
                                <span className="text-[0.75em] font-medium px-2 py-0.5 rounded bg-gray-100 text-gray-600">
                                  {points[0].kategori}
                                </span>
                              )}
                            </div>
                            <div className="space-y-3 text-left">
                              <div className="text-gray-800 leading-relaxed text-[0.92em] whitespace-pre-line font-serif">
                                {renderArticleContentWithAyat(art.content_text, targetAyat)}
                              </div>
                              {isTeksTerpotong(art.content_text) && (
                                <p className="text-[0.75em] italic text-amber-700">
                                  Teks dipotong, buka tab PDF Asli untuk teks lengkap.
                                </p>
                              )}
                              {points.length > 0 && (
                                <div className="pt-2.5 border-t border-gray-100 space-y-1.5">
                                  <div className="flex items-center justify-between gap-2">
                                    <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block">
                                      Intisari &amp; Norma Terdeteksi ({points.length} klausul)
                                    </span>
                                    <DraftLabel ukuran="kecil" />
                                  </div>
                                  {points.map((pt, pIdx) => (
                                    <div key={pIdx} className="bg-red-50/50 p-2 rounded-lg border border-red-100/70 text-xs">
                                      <span className="font-semibold text-red-800">[{pt.kategori}]</span>{' '}
                                      <span className="text-gray-700">{pt.parafrase || pt.teks}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-gray-500 text-xs space-y-1.5">
                      <p className="font-semibold text-gray-700">
                        {isSeojk
                          ? 'Dokumen SEOJK ini tidak memiliki struktur BAB/Pasal yang dapat ditampilkan.'
                          : isDraft
                          ? 'Struktur bab dan pasal untuk draf ini belum tersedia.'
                          : 'Struktur bab dan pasal untuk dokumen ini belum tersedia.'}
                      </p>
                      <p className="text-[11px] text-gray-400">Silakan gunakan tab PDF Asli untuk membaca naskah lengkap.</p>
                    </div>
                  )}

                  {/* Footer Naskah */}
                  <div className="pt-6 border-t border-gray-200 flex justify-between items-center text-[0.75em] text-gray-400 font-mono">
                    <span>Naskah hasil ekstraksi — HERO #{documentId}</span>
                    <span>Halaman {currentPage} dari {totalPages}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
          </PanelErrorBoundary>

          {/* =================================================================== */}
          {/* PANEL KANAN: HASIL ANALISIS */}
          {/* =================================================================== */}
          {isRightCollapsed ? (
            <div className="hidden lg:flex w-11 bg-white rounded-xl border border-gray-200 flex-col items-center py-3.5 shadow-2xs shrink-0 transition-all duration-300">
              <button
                type="button"
                onClick={() => setIsRightCollapsed(false)}
                title="Buka Panel Hasil Analisis"
                className="p-1.5 rounded-lg text-gray-500 hover:text-red-700 hover:bg-red-50 transition cursor-pointer"
              >
                <PanelRightOpen size={18} />
              </button>
              <div className="mt-4 flex-1 flex items-center justify-center">
                <span className="[writing-mode:vertical-lr] text-[10px] font-bold text-gray-400 tracking-wider uppercase select-none">
                  Hasil Analisis
                </span>
              </div>
              <DraftLabel ukuran="kecil" />
            </div>
          ) : (
            <PanelErrorBoundary
              nama="Hasil Analisis"
              className={`${mobileActivePanel === 'hasil' ? 'flex' : 'hidden'} lg:flex w-full lg:w-[380px] xl:w-[420px] 2xl:w-[460px] shrink-0 bg-white rounded-xl border border-gray-200 h-full p-4`}
              onCobaLagi={() => loadAnalysis(false, false)}
            >
            <div ref={panelHasilRef} className={`${mobileActivePanel === 'hasil' ? 'flex' : 'hidden'} lg:flex w-full lg:w-[380px] xl:w-[420px] 2xl:w-[460px] shrink-0 bg-white rounded-xl border border-gray-200 flex-col shadow-2xs overflow-hidden h-full transition-all duration-300`}>
              {/* Header Panel Kanan */}
              <div className="p-3.5 border-b border-gray-100 flex items-center justify-between shrink-0 bg-white">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setIsRightCollapsed(true)}
                    title="Ciutkan Panel Hasil Analisis"
                    className="p-1 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition cursor-pointer"
                  >
                    <PanelRightClose size={15} />
                  </button>
                  <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                    Hasil Analisis
                  </h3>
                </div>
                <div className="flex items-center gap-2">
                  <DraftLabel />
                  <div className="flex items-center gap-1 text-emerald-700 font-bold text-xs shrink-0">
                    <Check size={14} className="text-emerald-600" />
                    <span>Selesai</span>
                  </div>
                </div>
              </div>

              {/* Tab Bar: 6 Tab Rapi (Harmonisasi Utama MVP 3, Ringkasan, Poin Utama, Dasar Hukum, Bandingkan, Info Tambahan) */}
              <div className="grid grid-cols-6 border-b border-gray-200 bg-gray-50/70 text-xs shrink-0 select-none">
                <button
                  type="button"
                  onClick={bukaTabHarmonisasi}
                  className={`py-2.5 px-1 text-center font-semibold transition border-b-2 cursor-pointer truncate text-[11px] ${
                    activeTab === 'harmonisasi'
                      ? 'border-red-700 text-red-700 bg-white font-bold'
                      : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-100/50'
                  }`}
                  title="Harmonisasi Draft vs Knowledge Base (MVP 3)"
                >
                  <span className="flex items-center justify-center gap-1">
                    <span>Harmonisasi</span>
                    {Array.isArray(harmonisasi?.data?.temuan) && harmonisasi.data.temuan.length > 0 && (
                      <span className="px-1.5 py-0.2 rounded-full text-[9px] bg-red-100 text-red-800 font-bold">
                        {harmonisasi.data.temuan.length}
                      </span>
                    )}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('ringkasan')}
                  className={`py-2.5 px-1 text-center font-semibold transition border-b-2 cursor-pointer truncate text-[11px] ${
                    activeTab === 'ringkasan'
                      ? 'border-red-700 text-red-700 bg-white font-bold'
                      : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-100/50'
                  }`}
                  title="Ringkasan Eksekutif & Status Pasal"
                >
                  Ringkasan
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('poin_utama')}
                  className={`py-2.5 px-1 text-center font-semibold transition border-b-2 cursor-pointer truncate text-[11px] ${
                    activeTab === 'poin_utama'
                      ? 'border-red-700 text-red-700 bg-white font-bold'
                      : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-100/50'
                  }`}
                  title="Poin Utama & Klausul Regulasi"
                >
                  Poin Utama
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('dasar_hukum')}
                  className={`py-2.5 px-1 text-center font-semibold transition border-b-2 cursor-pointer truncate text-[11px] ${
                    activeTab === 'dasar_hukum'
                      ? 'border-red-700 text-red-700 bg-white font-bold'
                      : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-100/50'
                  }`}
                  title="Dasar Hukum & Konsiderans Mengingat"
                >
                  Dasar Hukum
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setActiveTab('perbandingan');
                    if (!comparisonData && !comparisonLoading) {
                      void loadComparison();
                    }
                  }}
                  className={`py-2.5 px-1 text-center font-semibold transition border-b-2 cursor-pointer truncate text-[11px] ${
                    activeTab === 'perbandingan'
                      ? 'border-red-700 text-red-700 bg-white font-bold'
                      : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-100/50'
                  }`}
                  title="Perbandingan Analisis Deterministik vs AI"
                >
                  Bandingkan
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('info_tambahan')}
                  className={`py-2.5 px-1 text-center font-semibold transition border-b-2 cursor-pointer truncate text-[11px] ${
                    activeTab === 'info_tambahan'
                      ? 'border-red-700 text-red-700 bg-white font-bold'
                      : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-100/50'
                  }`}
                  title="Informasi Tambahan (Subjek, Sanksi, Lampiran)"
                >
                  Info Tambahan
                </button>
              </div>

              {/* Tab Contents */}
              <div data-testid="panel-hasil-scroll" className="flex-1 overflow-y-auto min-h-0 p-4 space-y-4 text-xs">
              {/* TAB 1: RINGKASAN */}
              {activeTab === 'ringkasan' && (
                <div className="space-y-4">
                  <StatusPasalKb
                    state={harmonisasi}
                    onLihatPerPasal={bukaTabHarmonisasi}
                    onCobaLagi={() => void muatHarmonisasi(true)}
                  />

                  {/* RINGKASAN EKSEKUTIF */}
                  <div className="bg-red-50/40 border border-red-100 rounded-xl p-4 space-y-3">
                    <div className="flex items-center justify-between pb-1 border-b border-red-100/60">
                      <span className="text-[11px] font-bold text-red-800 uppercase tracking-wider block">
                        RINGKASAN EKSEKUTIF
                      </span>
                      {mode === 'ai' && data.mode_dipakai === 'ai' ? (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-red-100 text-red-800 border border-red-200">
                          AI-Assisted
                        </span>
                      ) : (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 border border-gray-200">
                          Deterministik
                        </span>
                      )}
                    </div>

                    {/* Narasi Ringkasan AI per kalimat, atau alasan bila AI diminta tetapi tidak dipakai */}
                    {mode === 'ai' && (
                      <RingkasanAiPanel
                        ai={data.ai}
                        ringkasanAi={data.ringkasan_ai}
                        modeDipakai={data.mode_dipakai}
                        onJumpToPasal={handleJumpToPasal}
                      />
                    )}

                    {/* Butir-butir Ringkasan Kalimat Berdasarkan data.ringkasan */}
                    {Array.isArray(data.ringkasan) && data.ringkasan.length > 0 ? (
                      <div className="space-y-2.5 pt-0.5">
                        {data.ringkasan.map((sentence, sIdx) => {
                          const validRefs = Array.isArray(sentence.rujukan)
                            ? sentence.rujukan.filter((r): r is string => typeof r === 'string' && r.trim() !== '' && r.trim() !== '-')
                            : [];
                          const hasRefs = validRefs.length > 0;
                          return (
                            <div key={sIdx} className="space-y-1.5 text-xs bg-white/70 p-2.5 rounded-lg border border-red-100/70">
                              <p className="text-gray-800 leading-relaxed">{sentence.kalimat}</p>
                              <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                                <span className="text-[10px] font-medium text-gray-500">Rujukan:</span>
                                {hasRefs ? (
                                  validRefs.map((refStr, rIdx) => {
                                    const parsed = parsePasalRef(refStr);
                                    const isRecognized = parsed.pasalNum !== null;
                                    return (
                                      <button
                                        key={rIdx}
                                        type="button"
                                        onClick={() => handleJumpToPasal(refStr)}
                                        className={`inline-flex items-center gap-1 font-mono text-[11px] font-semibold px-2 py-0.5 rounded transition ${
                                          isRecognized
                                            ? 'text-red-700 bg-red-50 hover:bg-red-100 hover:text-red-900 border border-red-200 cursor-pointer'
                                            : 'text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-200 cursor-pointer'
                                        }`}
                                        title={isRecognized ? `Lompat ke ${refStr}` : `Telusuri rujukan "${refStr}"`}
                                      >
                                        <ExternalLink size={10} />
                                        <span>{refStr}</span>
                                      </button>
                                    );
                                  })
                                ) : (
                                  <span className="text-[10px] text-gray-400 italic font-mono">
                                    Rujukan pasal tidak tersedia
                                  </span>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      /* Fallback teks lama ketika array data.ringkasan tidak tersedia */
                      <div className="space-y-2">
                        <p className="text-xs text-gray-700 leading-relaxed">
                          {data.ringkasan_teks || '-'}
                        </p>
                        <span className="text-[10px] text-gray-400 italic block font-mono">
                          Rujukan pasal per kalimat tidak tersedia untuk dokumen ini.
                        </span>
                      </div>
                    )}
                  </div>

                  {/* POIN KUNCI / KEY TAKEAWAYS */}
                  <div>
                    <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider mb-2.5">
                      POIN KUNCI
                    </h4>
                    <div className="space-y-3">
                      {(data.poin_utama || []).slice(0, 4).map((p, idx) => {
                        const rawRef = p.ref || p.pasal;
                        const targetRef = typeof rawRef === 'string' && rawRef.trim() !== '' && rawRef.trim() !== '-' ? rawRef.trim() : null;
                        const parsed = targetRef ? parsePasalRef(targetRef) : null;
                        const isRecognized = parsed && parsed.pasalNum !== null;
                        return (
                          <div key={p.id || idx} className="flex items-start gap-2 text-xs">
                            <span className="w-1.5 h-1.5 rounded-full bg-red-700 mt-1.5 shrink-0" />
                            <div className="space-y-1 flex-1">
                              <p className="text-gray-800 leading-relaxed">{p.teks}</p>
                              {targetRef ? (
                                <button
                                  type="button"
                                  onClick={() => handleJumpToPasal(targetRef)}
                                  className={`inline-flex items-center gap-1 font-mono text-[11px] font-semibold cursor-pointer transition ${
                                    isRecognized
                                      ? 'text-red-700 hover:underline'
                                      : 'text-amber-700 hover:underline'
                                  }`}
                                  title={`Lompat ke ${targetRef}`}
                                >
                                  <ExternalLink size={10} />
                                  <span>{targetRef}</span>
                                  {p.halaman ? <span className="text-gray-400 font-normal">(Hal. {p.halaman})</span> : null}
                                </button>
                              ) : (
                                <span className="text-[10px] text-gray-400 italic font-mono">
                                  Rujukan pasal tidak tersedia
                                </span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: POIN UTAMA & KEWAJIBAN */}
              {activeTab === 'poin_utama' && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                      DAFTAR POIN UTAMA
                    </span>
                    <span className="text-[11px] text-gray-500 font-mono">
                      {data.jumlah_poin || data.poin_utama?.length || 0} poin teridentifikasi
                    </span>
                  </div>

                  {/* Filter Kategori (Temuan QA 6B) */}
                  <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-[11px]">
                    {availableCategories.map(kat => {
                      const count = categoryCounts[kat] ?? 0;
                      return (
                        <button
                          key={kat}
                          type="button"
                          onClick={() => setKategoriFilter(kat)}
                          className={`px-2.5 py-1 rounded-md font-semibold shrink-0 cursor-pointer transition flex items-center gap-1.5 ${
                            kategoriFilter === kat
                              ? 'bg-red-700 text-white shadow-2xs'
                              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                          }`}
                        >
                          <span>{kat}</span>
                          <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                            kategoriFilter === kat ? 'bg-red-800 text-red-100' : 'bg-gray-200 text-gray-700'
                          }`}>
                            ({count})
                          </span>
                        </button>
                      );
                    })}
                  </div>

                  {/* List Poin Utama */}
                  <div className="space-y-2.5">
                    {(data.poin_utama || [])
                      .filter(p => kategoriFilter === 'Semua' || p.kategori.toLowerCase() === kategoriFilter.toLowerCase())
                      .map((p, idx) => {
                        const rawRef = p.ref || p.pasal;
                        const targetRef = typeof rawRef === 'string' && rawRef.trim() !== '' && rawRef.trim() !== '-' ? rawRef.trim() : null;
                        const urgencyLabel = p.urgensi || (p.prioritas !== undefined ? `Prioritas ${p.prioritas}` : undefined);
                        const parsed = targetRef ? parsePasalRef(targetRef) : null;
                        const isRecognized = parsed && parsed.pasalNum !== null;
                        return (
                          <div key={p.id || idx} className="p-3 rounded-lg border border-gray-100 bg-gray-50/60 hover:bg-white hover:border-gray-200 transition space-y-1.5">
                            <div className="flex items-center justify-between text-[11px]">
                              <div className="flex items-center gap-1.5">
                                <span className="font-semibold px-2 py-0.2 rounded bg-white border border-gray-200 text-gray-700">
                                  {p.kategori}
                                </span>
                                {urgencyLabel && (
                                  <span className={`text-[10px] font-semibold px-1.5 py-0.2 rounded ${
                                    urgencyLabel.toLowerCase().includes('kritis') || urgencyLabel.toLowerCase().includes('1')
                                      ? 'bg-red-100 text-red-700' 
                                      : urgencyLabel.toLowerCase().includes('tinggi') || urgencyLabel.toLowerCase().includes('2')
                                      ? 'bg-amber-100 text-amber-700'
                                      : 'bg-blue-100 text-blue-700'
                                  }`}>
                                    {urgencyLabel}
                                  </span>
                                )}
                              </div>
                              {targetRef ? (
                                <button
                                  type="button"
                                  onClick={() => handleJumpToPasal(targetRef)}
                                  className={`inline-flex items-center gap-1 font-mono text-[11px] font-semibold cursor-pointer transition ${
                                    isRecognized
                                      ? 'text-red-700 hover:underline'
                                      : 'text-amber-700 hover:underline'
                                  }`}
                                  title={`Lompat ke ${targetRef}`}
                                >
                                  <ExternalLink size={10} />
                                  <span>{targetRef} {p.halaman ? `(Hal. ${p.halaman})` : ''}</span>
                                </button>
                              ) : (
                                <span className="text-[10px] text-gray-400 italic font-mono">
                                  Rujukan pasal tidak tersedia
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-gray-800 leading-relaxed">{p.teks}</p>
                            {p.parafrase && mode === 'ai' && p.parafrase !== p.teks && (
                              <p className="text-xs text-red-900/80 bg-red-50/50 p-2 rounded border border-red-100/60 font-serif italic">
                                Parafrase AI: {p.parafrase}
                              </p>
                            )}
                          </div>
                        );
                      })}
                  </div>
                </div>
              )}

              {/* TAB 3: DASAR HUKUM (Temuan QA 2) */}
              {activeTab === 'dasar_hukum' && (
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                      DASAR HUKUM TERKAIT
                    </h4>
                    <span className="text-[10px] text-gray-500 font-mono">
                      {(data.dasar_hukum || []).length} rujukan
                    </span>
                  </div>
                  {(!data.dasar_hukum || data.dasar_hukum.length === 0) ? (
                    <div className="p-4 rounded-lg bg-gray-50 text-center text-xs text-gray-500">
                      Tidak ada rujukan dasar hukum yang teridentifikasi untuk dokumen ini.
                    </div>
                  ) : (
                    (data.dasar_hukum || []).map((dh, idx) => {
                      const trimmedDh = dh.trim();
                      const kbInfo = kbReferenceMap[trimmedDh];
                      const isAvailable = kbInfo?.available === true;
                      const targetDocId = kbInfo?.documentId;
                      const isMultiple = kbInfo?.isMultiple === true;

                      if (isAvailable && targetDocId) {
                        return (
                          <div
                            key={idx}
                            role="button"
                            tabIndex={0}
                            onClick={() => navigate(`/knowledge/detail/${targetDocId}`)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                navigate(`/knowledge/detail/${targetDocId}`);
                              }
                            }}
                            className="p-3 rounded-lg border border-emerald-200/80 bg-white hover:border-red-300 hover:bg-red-50/20 hover:shadow-2xs transition cursor-pointer flex items-start justify-between gap-3 group"
                            title={`Buka detail dokumen #${targetDocId} di Knowledge Base`}
                          >
                            <div className="flex items-start gap-2.5 text-xs text-gray-800 min-w-0">
                              <Scale size={14} className="text-red-700 shrink-0 mt-0.5 group-hover:scale-110 transition-transform" />
                              <div className="space-y-1 min-w-0">
                                <span className="font-semibold text-gray-900 group-hover:text-red-700 transition-colors block">
                                  {dh}
                                </span>
                                {kbInfo.title && kbInfo.title !== dh && (
                                  <p className="text-[11px] text-gray-500 line-clamp-1">
                                    {kbInfo.title}
                                  </p>
                                )}
                              </div>
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0 pt-0.5">
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                                <Check size={10} className="stroke-[2.5]" />
                                Tersedia di KB
                              </span>
                              <ExternalLink size={12} className="text-gray-400 group-hover:text-red-700 transition-colors" />
                            </div>
                          </div>
                        );
                      }

                      if (isAvailable && isMultiple) {
                        return (
                          <div
                            key={idx}
                            role="button"
                            tabIndex={0}
                            onClick={() => navigate(`/knowledge?q=${encodeURIComponent(trimmedDh)}`)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                navigate(`/knowledge?q=${encodeURIComponent(trimmedDh)}`);
                              }
                            }}
                            className="p-3 rounded-lg border border-emerald-200/80 bg-white hover:border-red-300 hover:bg-red-50/20 hover:shadow-2xs transition cursor-pointer flex items-start justify-between gap-3 group"
                            title="Buka pencarian di Knowledge Base (terdapat beberapa kemungkinan dokumen)"
                          >
                            <div className="flex items-start gap-2.5 text-xs text-gray-800 min-w-0">
                              <Scale size={14} className="text-red-700 shrink-0 mt-0.5" />
                              <span className="font-semibold text-gray-900 group-hover:text-red-700 transition-colors block">
                                {dh}
                              </span>
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0 pt-0.5">
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                                <Check size={10} className="stroke-[2.5]" />
                                Tersedia di KB
                              </span>
                              <ExternalLink size={12} className="text-gray-400 group-hover:text-red-700 transition-colors" />
                            </div>
                          </div>
                        );
                      }

                      return (
                        <div
                          key={idx}
                          className="p-3 rounded-lg border border-gray-100 bg-gray-50/70 flex items-start justify-between gap-3 text-xs text-gray-600 cursor-default opacity-90"
                        >
                          <div className="flex items-start gap-2.5 min-w-0">
                            <Scale size={14} className="text-gray-400 shrink-0 mt-0.5" />
                            <span className="leading-snug">{dh}</span>
                          </div>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-100 text-gray-500 border border-gray-200 shrink-0">
                            Belum tersedia di KB
                          </span>
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {/* TAB PERBANDINGAN: DETERMINISTIK VS AI (Temuan QA 5) */}
              {activeTab === 'perbandingan' && (
                <div className="space-y-3.5">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider flex items-center gap-1.5">
                      <GitCompare size={13} className="text-red-700" />
                      <span>PERBANDINGAN ANALISIS</span>
                    </h4>
                    <button
                      type="button"
                      onClick={() => setIsComparisonOpen(true)}
                      className="text-[11px] text-red-700 hover:text-red-800 font-semibold inline-flex items-center gap-1 cursor-pointer"
                    >
                      <Columns size={11} />
                      <span>Mode Berdampingan</span>
                    </button>
                  </div>

                  {comparisonLoading ? (
                    <div className="p-8 text-center space-y-2 bg-gray-50 rounded-xl border border-gray-100">
                      <Loader2 size={18} className="animate-spin text-red-700 mx-auto" />
                      <p className="text-xs text-gray-600">Memuat perbandingan analisis...</p>
                    </div>
                  ) : comparisonError ? (
                    <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700 space-y-2">
                      <p className="font-semibold">{comparisonError}</p>
                      <button
                        type="button"
                        onClick={() => void loadComparison()}
                        className="px-3 py-1 bg-white border border-red-300 rounded text-red-700 font-semibold hover:bg-red-50 text-[11px] cursor-pointer"
                      >
                        Coba Lagi
                      </button>
                    </div>
                  ) : comparisonData ? (
                    <div className="space-y-3">
                      <p className="text-[11px] text-amber-800 bg-amber-50/70 p-2.5 rounded-lg border border-amber-200/70">
                        {comparisonData.catatan}
                      </p>

                      {/* Card Ringkas Deterministik */}
                      <div className="p-3 rounded-xl border border-gray-200 bg-white space-y-2">
                        <div className="flex items-center justify-between pb-1.5 border-b border-gray-100">
                          <span className="font-bold text-xs text-gray-900 flex items-center gap-1.5">
                            <Cpu size={13} className="text-blue-600" />
                            Deterministik
                          </span>
                          <div className="flex items-center gap-1.5">
                            {comparisonData.deterministik?.ml_version && (
                              <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-800">
                                {comparisonData.deterministik.ml_version}
                              </span>
                            )}
                            <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                              {comparisonData.deterministik ? 'Tersedia' : 'Belum Dijalankan'}
                            </span>
                          </div>
                        </div>
                        {comparisonData.deterministik?.hasil ? (
                          <div className="space-y-1.5 text-xs text-gray-700">
                            <p className="line-clamp-3 text-gray-600">
                              {comparisonData.deterministik.hasil.ringkasan_teks || 'Ringkasan ekstraksi deterministik siap dibaca.'}
                            </p>
                            <div className="text-[10px] text-gray-500 font-mono pt-1">
                              Waktu: {comparisonData.deterministik.hasil.metrik?.waktu_ms ?? '-'} ms • Poin: {comparisonData.deterministik.hasil.poin_utama?.length ?? 0}
                            </div>
                          </div>
                        ) : (
                          <p className="text-xs text-gray-400 italic">Data analisis deterministik tidak tersedia.</p>
                        )}
                      </div>

                      {/* Card Ringkas AI */}
                      <div className="p-3 rounded-xl border border-purple-200 bg-purple-50/20 space-y-2">
                        <div className="flex items-center justify-between pb-1.5 border-b border-purple-100">
                          <span className="font-bold text-xs text-gray-900 flex items-center gap-1.5">
                            <Sparkles size={13} className="text-purple-600" />
                            AI (Gemini)
                          </span>
                          <div className="flex items-center gap-1.5">
                            {comparisonData.ai?.ml_version && (
                              <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-purple-100 text-purple-800">
                                {comparisonData.ai.ml_version}
                              </span>
                            )}
                            <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200">
                              {comparisonData.ai ? 'Tersedia' : 'Belum Dijalankan'}
                            </span>
                          </div>
                        </div>
                        {comparisonData.ai?.hasil ? (
                          <div className="space-y-1.5 text-xs text-gray-700">
                            <p className="line-clamp-3 text-gray-600">
                              {typeof comparisonData.ai.hasil.ringkasan_ai === 'string'
                                ? comparisonData.ai.hasil.ringkasan_ai
                                : (Array.isArray(comparisonData.ai.hasil.ringkasan_ai)
                                    ? comparisonData.ai.hasil.ringkasan_ai.map(k => k.kalimat).join(' ')
                                    : comparisonData.ai.hasil.ringkasan_teks || 'Narasi analisis AI siap.')}
                            </p>
                            <div className="text-[10px] text-gray-500 font-mono pt-1">
                              Model: {comparisonData.ai.hasil.ai?.model || 'Gemini'} • Waktu: {comparisonData.ai.hasil.metrik?.waktu_ms ?? '-'} ms
                            </div>
                          </div>
                        ) : (
                          <p className="text-xs text-gray-400 italic">Data analisis AI belum pernah dieksekusi.</p>
                        )}
                      </div>

                      <button
                        type="button"
                        onClick={() => setIsComparisonOpen(true)}
                        className="w-full py-2 bg-red-700 hover:bg-red-800 text-white rounded-lg text-xs font-semibold shadow-2xs transition cursor-pointer flex items-center justify-center gap-1.5"
                      >
                        <Columns size={13} />
                        <span>Buka Tampilan Berdampingan Penuh</span>
                      </button>
                    </div>
                  ) : (
                    <div className="p-6 text-center space-y-2.5 bg-gray-50 rounded-xl border border-gray-100">
                      <p className="text-xs text-gray-600">Data perbandingan belum dimuat.</p>
                      <button
                        type="button"
                        onClick={() => void loadComparison()}
                        className="px-3.5 py-1.5 bg-red-700 text-white rounded-lg text-xs font-semibold hover:bg-red-800 transition cursor-pointer"
                      >
                        Muat Perbandingan
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 4: INFORMASI TAMBAHAN (Status, Metrik, Subjek, Sanksi, Lampiran) */}
              {activeTab === 'info_tambahan' && (
                <div className="space-y-4">
                  {/* Metrik Statistik */}
                  <div>
                    <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider mb-2">
                      METRIK REGULASI
                    </h4>
                    <div className="grid grid-cols-2 gap-2 text-center">
                      <div className="p-2.5 bg-gray-50 border border-gray-100 rounded-lg">
                        <span className="text-lg font-bold text-gray-900 block">{displayJumlahBab}</span>
                        <span className="text-[10px] text-gray-500 uppercase">Jumlah Bab</span>
                      </div>
                      <div className="p-2.5 bg-gray-50 border border-gray-100 rounded-lg">
                        <span className="text-lg font-bold text-gray-900 block">{displayJumlahPasal}</span>
                        <span className="text-[10px] text-gray-500 uppercase">Jumlah Pasal</span>
                      </div>
                      <div className="p-2.5 bg-gray-50 border border-gray-100 rounded-lg">
                        <span className="text-lg font-bold text-red-700 block">{displayJumlahKewajiban}</span>
                        <span className="text-[10px] text-gray-500 uppercase leading-tight block">Kewajiban di Poin Utama</span>
                      </div>
                      <div className="p-2.5 bg-gray-50 border border-gray-100 rounded-lg">
                        <span className="text-lg font-bold text-amber-700 block">{displayJumlahLarangan}</span>
                        <span className="text-[10px] text-gray-500 uppercase leading-tight block">Larangan di Poin Utama</span>
                      </div>
                    </div>
                  </div>

                  {/* Subjek yang Diatur */}
                  {data.subjek_diatur && data.subjek_diatur.length > 0 && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                        <Building2 size={13} className="text-red-700" />
                        <span>SUBJEK YANG DIATUR</span>
                      </h4>
                      <ul className="list-disc pl-4 space-y-1 text-xs text-gray-600">
                        {data.subjek_diatur.map((s, idx) => {
                          const label = typeof s === 'string' ? s : `${s.subjek} (${s.jumlah})`;
                          return <li key={idx}>{label}</li>;
                        })}
                      </ul>
                    </div>
                  )}

                  {/* Sanksi */}
                  {data.sanksi && data.sanksi.length > 0 && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                        <ShieldAlert size={13} className="text-amber-700" />
                        <span>SANKSI ADMINISTRATIF</span>
                      </h4>
                      <ul className="list-disc pl-4 space-y-1 text-xs text-gray-600">
                        {data.sanksi.map((s, idx) => (
                          <li key={idx}>{s}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Lampiran */}
                  {data.lampiran && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                        <Paperclip size={13} className="text-blue-700" />
                        <span>LAMPIRAN</span>
                      </h4>
                      <ul className="list-disc pl-4 space-y-1 text-xs text-gray-600">
                        {Array.isArray(data.lampiran) ? (
                          data.lampiran.map((l, idx) => (
                            <li key={idx}>{l}</li>
                          ))
                        ) : (
                          <li>Profil: {data.lampiran.profil || '-'} ({data.lampiran.tabel ?? 0} tabel)</li>
                        )}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 5: HARMONISASI (draft vs korpus, per pasal) */}
              {activeTab === 'harmonisasi' && (
                <PanelErrorBoundary nama="Harmonisasi" onCobaLagi={() => void muatHarmonisasi(true)}>
                  <HarmonisasiPanel
                    state={harmonisasi}
                    onMuat={(segar) => void muatHarmonisasi(segar)}
                    onJumpToPasal={handleJumpToPasal}
                    documentId={documentId}
                    documentRole={docStatus?.document_role}
                    onUpdateHarmonisasiData={(updatedData) => {
                      setHarmonisasiState((prev) => prev ? { ...prev, data: updatedData } : null);
                      saveStoredHarmonisasiResult(documentId, updatedData);
                    }}
                  />
                </PanelErrorBoundary>
              )}
            </div>

            {/* Catatan Disclaimer */}
            <div className="p-3 border-t border-gray-100 bg-gray-50/50 text-[10px] text-gray-500 leading-tight shrink-0">
              {typeof data.catatan === 'string' && data.catatan.trim() !== '' && (
                <p className="mb-1.5 font-semibold text-amber-800">{data.catatan}</p>
              )}
              Catatan: Hasil analisis ini merupakan bahan telaah otomatis berbasis sistem dan tetap memerlukan verifikasi oleh pejabat/analis berwenang.
            </div>
          </div>
          </PanelErrorBoundary>
          )}
        </div>
        </div>
      )}

      {/* 5. STICKY BOTTOM BAR */}
      <div className="sticky bottom-4 z-20 bg-white/95 backdrop-blur-xs border border-gray-200 rounded-xl px-5 py-3 shadow-md flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mt-3">
        <div className="flex items-center gap-2 text-xs text-gray-700">
          {loading ? (
            <>
              <span className="w-2 h-2 rounded-full bg-gray-400 shrink-0" />
              <span>Menganalisis dokumen...</span>
            </>
          ) : errorStatus === 403 ? (
            <>
              <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
              <span className="text-amber-800 font-semibold">Akses Ditolak</span>
            </>
          ) : errorStatus !== null || errorMessage ? (
            <>
              <span className="w-2 h-2 rounded-full bg-red-500 shrink-0" />
              <span>Analisis gagal</span>
            </>
          ) : data ? (
            <>
              <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
              <span>
                Analisis selesai. {displayJumlahPasal} pasal dan {displayJumlahBab} bab terindeks lengkap secara {data.mode_dipakai || mode}.
              </span>
              <DraftLabel />
            </>
          ) : (
            <>
              <span className="w-2 h-2 rounded-full bg-gray-300 shrink-0" />
              <span>Menunggu hasil analisis</span>
            </>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={onBackToState1}
            className="px-4 py-2 border border-gray-200 text-gray-700 hover:bg-gray-50 text-xs font-semibold rounded-lg transition shadow-2xs cursor-pointer"
          >
            Tinjau Kembali
          </button>

          {/* Kontrol Ekspor Analisis (DOCX, CSV, JSON) */}
          <div className="relative export-dropdown-container">
            <button
              type="button"
              disabled={!data || loading || isExporting}
              onClick={() => setIsExportMenuOpen(prev => !prev)}
              className={`inline-flex items-center gap-1.5 px-4 py-2 border text-xs font-semibold rounded-lg transition shadow-2xs cursor-pointer ${
                data && !loading && !isExporting
                  ? 'bg-white border-gray-300 hover:bg-gray-50 text-gray-700'
                  : 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
              }`}
              title="Ekspor hasil analisis regulasi ke format Word (.docx), Excel / CSV (.csv), atau JSON (.json)"
            >
              {isExporting ? (
                <Loader2 size={13} className="animate-spin text-red-700" />
              ) : (
                <Download size={13} />
              )}
              <span>{isExporting ? `Mengekspor ${exportingFormat ? `(${exportingFormat.toUpperCase()})...` : '...'}` : 'Ekspor Analisis'}</span>
              <ChevronDown size={12} className={`transition-transform duration-150 ${isExportMenuOpen ? 'rotate-180' : ''}`} />
            </button>

            {isExportMenuOpen && (
              <div className="absolute right-0 bottom-full mb-2 w-72 bg-white rounded-xl shadow-lg border border-gray-200 py-1.5 z-50 animate-in fade-in slide-in-from-bottom-2 duration-150">
                <div className="px-3 py-1.5 border-b border-gray-100">
                  <p className="text-[11px] font-bold text-gray-900 uppercase tracking-wider">Format Ekspor Analisis</p>
                  <p className="text-[10px] text-gray-500">Pilih format berkas resmi yang dibutuhkan</p>
                </div>
                <div className="p-1 space-y-0.5">
                  <button
                    type="button"
                    disabled={isExporting}
                    onClick={() => handleExportFormat('docx')}
                    className="w-full flex items-start gap-2.5 px-2.5 py-2 rounded-lg text-left hover:bg-blue-50/70 transition group cursor-pointer disabled:opacity-50"
                  >
                    <div className="p-1.5 rounded-lg bg-blue-50 text-blue-700 shrink-0 mt-0.5">
                      <FileText size={15} />
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-gray-800 group-hover:text-blue-900 flex items-center gap-1.5">
                        <span>Word (.docx)</span>
                        <span className="text-[9px] font-bold px-1.5 py-0.2 bg-blue-100 text-blue-800 rounded">Disarankan</span>
                      </div>
                      <p className="text-[10px] text-gray-500 mt-0.5 leading-snug">Naskah resmi, intisari eksekutif, tabel poin utama & pasal rujukan</p>
                    </div>
                  </button>

                  <button
                    type="button"
                    disabled={isExporting}
                    onClick={() => handleExportFormat('csv')}
                    className="w-full flex items-start gap-2.5 px-2.5 py-2 rounded-lg text-left hover:bg-emerald-50/70 transition group cursor-pointer disabled:opacity-50"
                  >
                    <div className="p-1.5 rounded-lg bg-emerald-50 text-emerald-700 shrink-0 mt-0.5">
                      <FileCode size={15} />
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-gray-800 group-hover:text-emerald-900">
                        Excel / CSV (.csv)
                      </div>
                      <p className="text-[10px] text-gray-500 mt-0.5 leading-snug">Tabel poin utama, norma & kepatuhan dengan UTF-8 BOM</p>
                    </div>
                  </button>

                  <button
                    type="button"
                    disabled={isExporting}
                    onClick={() => handleExportFormat('json')}
                    className="w-full flex items-start gap-2.5 px-2.5 py-2 rounded-lg text-left hover:bg-purple-50/70 transition group cursor-pointer disabled:opacity-50"
                  >
                    <div className="p-1.5 rounded-lg bg-purple-50 text-purple-700 shrink-0 mt-0.5">
                      <FileCode size={15} />
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-gray-800 group-hover:text-purple-900">
                        JSON (.json)
                      </div>
                      <p className="text-[10px] text-gray-500 mt-0.5 leading-snug">Struktur data mentah lengkap untuk arsip & integrasi sistem</p>
                    </div>
                  </button>
                </div>
              </div>
            )}
          </div>

          <button
            type="button"
            disabled={!data || loading}
            onClick={handleGoToHarmonisasi}
            className={`inline-flex items-center gap-1.5 px-5 py-2 text-xs font-semibold rounded-lg transition shadow-xs cursor-pointer ${
              data && !loading
                ? 'bg-red-800 hover:bg-red-900 text-white'
                : 'bg-red-950/40 text-white/60 cursor-not-allowed'
            }`}
          >
            <Scale size={14} />
            <span>Lanjut ke Harmonisasi</span>
            <ArrowRight size={13} />
          </button>
        </div>
      </div>

      {/* Toast Notifikasi Error Ekspor */}
      {exportError && (
        <div className="fixed bottom-16 right-6 max-w-md bg-white border border-red-300 rounded-xl p-3.5 shadow-xl z-50 flex items-start gap-2.5 animate-in fade-in slide-in-from-bottom-2">
          <AlertCircle size={18} className="text-red-700 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-bold text-red-900">Gagal Mengekspor Hasil Analisis</p>
            <p className="text-xs text-red-700 mt-0.5 leading-relaxed">{exportError}</p>
          </div>
          <button
            type="button"
            onClick={() => setExportError(null)}
            className="text-gray-400 hover:text-gray-700 text-xs font-bold p-1 cursor-pointer"
            title="Tutup pesan"
          >
            ✕
          </button>
        </div>
      )}

      {/* MODAL PERBANDINGAN DETERMINISTIK VS AI BERDAMPINGAN (Temuan QA 5) */}
      {isComparisonOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 animate-in fade-in duration-200">
          <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 w-full max-w-6xl max-h-[92vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between shrink-0 bg-white">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-red-50 text-red-700 border border-red-100 flex items-center justify-center">
                  <GitCompare size={20} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-gray-900 flex items-center gap-2">
                    <span>Perbandingan Analisis: Deterministik vs AI</span>
                    <span className="text-xs font-mono font-normal px-2 py-0.5 rounded bg-gray-100 text-gray-600">
                      Dokumen #{documentId}
                    </span>
                  </h3>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Telaah perbandingan hasil analisis deterministik berbasis aturan dengan analisis naratif AI berdampingan.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void loadComparison()}
                  disabled={comparisonLoading}
                  className="p-2 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition cursor-pointer"
                  title="Muat ulang perbandingan"
                >
                  <RefreshCw size={15} className={comparisonLoading ? 'animate-spin text-red-700' : ''} />
                </button>
                <button
                  type="button"
                  onClick={() => setIsComparisonOpen(false)}
                  className="p-2 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition cursor-pointer"
                  title="Tutup dialog"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-5">
              {comparisonLoading ? (
                <div className="py-24 text-center space-y-3">
                  <Loader2 size={32} className="animate-spin text-red-700 mx-auto" />
                  <p className="text-sm font-semibold text-gray-700">Mengambil data perbandingan Deterministik vs AI...</p>
                  <p className="text-xs text-gray-400">Endpoint: /api/v1/documents/{documentId}/analisa/banding</p>
                </div>
              ) : comparisonError ? (
                <div className="py-12 max-w-lg mx-auto text-center space-y-4">
                  <div className="w-12 h-12 rounded-full bg-red-100 text-red-700 flex items-center justify-center mx-auto">
                    <AlertCircle size={24} />
                  </div>
                  <div>
                    <h4 className="text-base font-bold text-gray-900">Gagal Memuat Perbandingan</h4>
                    <p className="text-xs text-gray-600 mt-1">{comparisonError}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void loadComparison()}
                    className="px-4 py-2 bg-red-700 hover:bg-red-800 text-white rounded-lg text-xs font-semibold shadow-xs transition cursor-pointer"
                  >
                    Coba Lagi
                  </button>
                </div>
              ) : comparisonData ? (
                <div className="space-y-5">
                  {/* Banner Catatan */}
                  {comparisonData.catatan && (
                    <div className="p-3 bg-amber-50/80 border border-amber-200 rounded-xl text-xs text-amber-800 flex items-start gap-2.5">
                      <Info size={16} className="text-amber-700 shrink-0 mt-0.5" />
                      <span>{comparisonData.catatan}</span>
                    </div>
                  )}

                  {/* Side-by-Side 2 Kolom Grid */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                    {/* KOLOM KIRI: DETERMINISTIK */}
                    <div className="rounded-xl border border-blue-200 bg-white flex flex-col overflow-hidden shadow-2xs">
                      {/* Column Header */}
                      <div className="p-4 bg-gradient-to-r from-blue-50/70 to-blue-50/30 border-b border-blue-100 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Cpu size={16} className="text-blue-700" />
                          <h4 className="text-sm font-bold text-gray-900">Mode Deterministik</h4>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {comparisonData.deterministik?.basi && (
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-800 border border-amber-200">
                              Basi
                            </span>
                          )}
                          <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                            comparisonData.deterministik ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-500'
                          }`}>
                            {comparisonData.deterministik ? 'Tersedia' : 'Belum Dijalankan'}
                          </span>
                        </div>
                      </div>

                      {/* Column Body */}
                      <div className="p-4 flex-1 space-y-4 text-xs text-gray-700 overflow-y-auto max-h-[500px]">
                        {comparisonData.deterministik?.hasil ? (
                          <>
                            {/* Metadata */}
                            <div className="text-[11px] text-gray-500 flex flex-wrap items-center gap-x-4 gap-y-1 pb-2 border-b border-gray-100">
                              {comparisonData.deterministik.ml_version && (
                                <span className="font-mono text-[10px] font-semibold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                                  Versi: {comparisonData.deterministik.ml_version}
                                </span>
                              )}
                              <span>Dibuat: {comparisonData.deterministik.dibuat ? new Date(comparisonData.deterministik.dibuat).toLocaleString('id-ID') : '-'}</span>
                              <span>Waktu: {comparisonData.deterministik.hasil.metrik?.waktu_ms ?? '-'} ms</span>
                              <span>Poin: {comparisonData.deterministik.hasil.poin_utama?.length ?? 0}</span>
                            </div>

                            {/* Ringkasan */}
                            <div>
                              <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block mb-1.5">
                                Ringkasan Eksekutif
                              </span>
                              <div className="bg-gray-50 p-3 rounded-lg border border-gray-100 text-gray-800 leading-relaxed space-y-2">
                                {comparisonData.deterministik.hasil.ringkasan_teks ? (
                                  <p>{comparisonData.deterministik.hasil.ringkasan_teks}</p>
                                ) : Array.isArray(comparisonData.deterministik.hasil.ringkasan) ? (
                                  comparisonData.deterministik.hasil.ringkasan.map((r, i) => (
                                    <p key={i}>{r.kalimat}</p>
                                  ))
                                ) : (
                                  <p className="text-gray-400 italic">Ringkasan deterministik tidak tersedia.</p>
                                )}
                              </div>
                            </div>

                            {/* Poin Utama */}
                            <div>
                              <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block mb-1.5">
                                Poin Utama ({comparisonData.deterministik.hasil.poin_utama?.length ?? 0})
                              </span>
                              <div className="space-y-2">
                                {(comparisonData.deterministik.hasil.poin_utama || []).map((pt, i) => (
                                  <div key={i} className="p-2.5 rounded-lg border border-gray-100 bg-gray-50/60 text-xs space-y-1">
                                    <div className="flex items-center justify-between text-[11px]">
                                      <span className="font-semibold text-blue-800">[{pt.kategori || pt.topik || 'Poin'}]</span>
                                      <span className="font-mono text-gray-500">{pt.ref || pt.pasal || '-'}</span>
                                    </div>
                                    <p className="text-gray-800">{pt.teks || pt.poin || ''}</p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </>
                        ) : (
                          <div className="py-12 text-center text-gray-400 italic">
                            Hasil analisis deterministik belum tersedia untuk dokumen ini.
                          </div>
                        )}
                      </div>
                    </div>

                    {/* KOLOM KANAN: AI (GEMINI) */}
                    <div className="rounded-xl border border-purple-200 bg-white flex flex-col overflow-hidden shadow-2xs">
                      {/* Column Header */}
                      <div className="p-4 bg-gradient-to-r from-purple-50/70 to-purple-50/30 border-b border-purple-100 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Sparkles size={16} className="text-purple-700" />
                          <h4 className="text-sm font-bold text-gray-900">Mode AI (Gemini)</h4>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {comparisonData.ai?.basi && (
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-800 border border-amber-200">
                              Basi
                            </span>
                          )}
                          <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                            comparisonData.ai ? 'bg-purple-100 text-purple-800' : 'bg-gray-100 text-gray-500'
                          }`}>
                            {comparisonData.ai ? 'Tersedia' : 'Belum Dijalankan'}
                          </span>
                        </div>
                      </div>

                      {/* Column Body */}
                      <div className="p-4 flex-1 space-y-4 text-xs text-gray-700 overflow-y-auto max-h-[500px]">
                        {comparisonData.ai?.hasil ? (
                          <>
                            {/* Metadata */}
                            <div className="text-[11px] text-gray-500 flex flex-wrap items-center gap-x-4 gap-y-1 pb-2 border-b border-gray-100">
                              {comparisonData.ai.ml_version && (
                                <span className="font-mono text-[10px] font-semibold px-2 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200">
                                  Versi: {comparisonData.ai.ml_version}
                                </span>
                              )}
                              <span>Model: {comparisonData.ai.hasil.ai?.model || 'Gemini'}</span>
                              <span>Dibuat: {comparisonData.ai.dibuat ? new Date(comparisonData.ai.dibuat).toLocaleString('id-ID') : '-'}</span>
                              <span>Waktu: {comparisonData.ai.hasil.metrik?.waktu_ms ?? '-'} ms</span>
                            </div>

                            {/* Ringkasan AI */}
                            <div>
                              <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block mb-1.5">
                                Narasi Ringkasan AI
                              </span>
                              <div className="bg-purple-50/30 p-3 rounded-lg border border-purple-100 text-gray-800 leading-relaxed space-y-2 font-serif">
                                {typeof comparisonData.ai.hasil.ringkasan_ai === 'string' ? (
                                  <p>{comparisonData.ai.hasil.ringkasan_ai}</p>
                                ) : Array.isArray(comparisonData.ai.hasil.ringkasan_ai) ? (
                                  comparisonData.ai.hasil.ringkasan_ai.map((s, i) => (
                                    <div key={i} className="space-y-1">
                                      <p>{s.kalimat}</p>
                                      {Array.isArray(s.rujukan) && s.rujukan.length > 0 && (
                                        <div className="flex gap-1 font-sans text-[10px] text-purple-700">
                                          <span>Rujukan: {s.rujukan.join(', ')}</span>
                                        </div>
                                      )}
                                    </div>
                                  ))
                                ) : (
                                  <p className="text-gray-400 italic">Ringkasan AI belum dibuat.</p>
                                )}
                              </div>
                            </div>

                            {/* Poin Kunci / Parafrase AI */}
                            <div>
                              <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block mb-1.5">
                                Parafrase AI &amp; Poin Kunci
                              </span>
                              <div className="space-y-2">
                                {(comparisonData.ai.hasil.poin_utama || []).map((pt, i) => (
                                  <div key={i} className="p-2.5 rounded-lg border border-purple-100/70 bg-purple-50/20 text-xs space-y-1">
                                    <div className="flex items-center justify-between text-[11px]">
                                      <span className="font-semibold text-purple-800">[{pt.kategori || pt.topik || 'Poin'}]</span>
                                      <span className="font-mono text-gray-500">{pt.ref || pt.pasal || '-'}</span>
                                    </div>
                                    <p className="text-gray-800">{pt.teks || pt.poin || ''}</p>
                                    {pt.parafrase && pt.parafrase !== pt.teks && (
                                      <p className="text-purple-900 bg-white/80 p-1.5 rounded border border-purple-100 font-serif italic text-[11px]">
                                        Parafrase AI: {pt.parafrase}
                                      </p>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          </>
                        ) : (
                          <div className="py-12 text-center text-gray-400 italic space-y-2">
                            <p>Hasil analisis AI belum pernah dijalankan untuk dokumen ini.</p>
                            <p className="text-[11px]">Gunakan opsi analisis dengan mode AI untuk menghasilkan data komparasi.</p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3.5 border-t border-gray-100 bg-gray-50/80 flex items-center justify-between shrink-0">
              <span className="text-xs text-gray-500">
                Penyelarasan komparasi otomatis HERO US-05
              </span>
              <button
                type="button"
                onClick={() => setIsComparisonOpen(false)}
                className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-800 rounded-lg text-xs font-semibold transition cursor-pointer"
              >
                Tutup
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
