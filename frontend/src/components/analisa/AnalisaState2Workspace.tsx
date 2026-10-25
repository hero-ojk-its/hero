import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
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
  X
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  getMlAnalisa,
  getDocumentStatus,
  checkMlHealth,
  isDocumentReadyForAnalysis,
  exportDocumentAnalysis,
  parsePasalRef,
  normalisasiKerangka
} from '../../lib/analisaApi';
import { ApiError, API_BASE_URL, apiFetchBlob } from '../../lib/api';
import { PanelErrorBoundary } from '../PanelErrorBoundary';
import type {
  MlAnalisaResponse,
  DocumentArticleSummary,
  DocumentStatusResponse,
  AnalysisExportFormat
} from '../../lib/analisaApi';

// Garuda Pancasila SVG Emblem untuk Naskah Resmi OJK
function GarudaEmblem() {
  return (
    <div className="flex justify-center mb-4">
      <svg width="56" height="56" viewBox="0 0 100 100" fill="none" className="text-gray-800">
        <circle cx="50" cy="50" r="46" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 2" />
        <path d="M50 15 L54 28 L68 28 L57 37 L61 50 L50 42 L39 50 L43 37 L32 28 L46 28 Z" fill="currentColor" opacity="0.85" />
        <path d="M30 46 C35 60 65 60 70 46 C66 72 34 72 30 46 Z" fill="currentColor" opacity="0.75" />
        <rect x="42" y="52" width="16" height="18" rx="2" fill="white" stroke="currentColor" strokeWidth="1.5" />
        <path d="M46 61 L54 61 M50 56 L50 66" stroke="currentColor" strokeWidth="1.5" />
        <path d="M25 76 Q50 82 75 76 Q50 86 25 76" fill="currentColor" />
        <text x="50" y="81" fontSize="3.8" textAnchor="middle" fill="white" fontWeight="bold" letterSpacing="0.8">BHINNEKA TUNGGAL IKA</text>
      </svg>
    </div>
  );
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
}

export default function AnalisaState2Workspace({
  documentId,
  mode,
  onBackToState1
}: AnalisaState2WorkspaceProps) {
  const navigate = useNavigate();

  // State Pemuatan & Data API
  const [data, setData] = useState<MlAnalisaResponse | null>(null);
  const [articles, setArticles] = useState<DocumentArticleSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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

  // State Workspace Panel 1: Struktur Dokumen
  const [expandedBabs, setExpandedBabs] = useState<Record<string, boolean>>({
    'BAB I': true,
    'BAB II': true,
    'BAB III': true,
    'BAB IV': true,
    'BAB V': true
  });
  const [selectedPasal, setSelectedPasal] = useState<string>('Pasal 1');
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

  // State Workspace Panel 3: Hasil Analisis Tabs
  const [activeTab, setActiveTab] = useState<'ringkasan' | 'poin_utama' | 'dasar_hukum' | 'info_tambahan'>('ringkasan');
  const [kategoriFilter, setKategoriFilter] = useState<string>('Semua');

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

      const [mlRes, statusRes] = await Promise.allSettled([
        getMlAnalisa(documentId, requestedMode, forceFresh, controller.signal),
        getDocumentStatus(documentId, controller.signal),
      ]);

      if (controller.signal.aborted || !isMountedRef.current) return;

      let statusDoc: DocumentStatusResponse | null = null;
      if (statusRes.status === 'fulfilled') {
        statusDoc = statusRes.value;
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
          `Nomor halaman fisik PDF untuk ${trimmed} belum tercatat pada metadata dokumen. Anda dapat beralih ke tab "Salinan Resmi" untuk membaca pasal ini.`
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
              `Struktur pasal salinan resmi belum tersedia untuk draf ini. Silakan buka tab "PDF Asli"${targetPage ? ` (Pasal berada di sekitar Hal. ${targetPage})` : ''}.`
            );
          } else {
            showNavFeedback(
              'warning',
              `Teks ${trimmed} tidak ditemukan dalam naskah salinan resmi dokumen ini.`
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
  }, [articles, data, showNavFeedback, totalPages, viewMode]);

  // Navigasi ke Harmonisasi
  const handleGoToHarmonisasi = () => {
    navigate('/harmonisasi', {
      state: {
        draftId: documentId,
        draftTitle: displayJudulRegulasi
      }
    });
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

  // 5. Tanggal Terbit: identitas.tanggal_terbit
  const tanggalTerbit = data?.identitas?.tanggal_terbit?.trim() || null;
  const displayTanggalTerbit = tanggalTerbit || '-';

  // 6. Kategori Poin Utama yang benar-benar ada di respon API
  const availableCategories = useMemo(() => {
    if (!data?.poin_utama) return ['Semua'];
    const cats = Array.from(new Set(data.poin_utama.map(p => p.kategori).filter(Boolean)));
    return ['Semua', ...cats];
  }, [data?.poin_utama]);

  return (
    <div className="max-w-[1360px] mx-auto space-y-4 pb-16 font-sans">
      {/* 1. Header Workspace Breadcrumb */}
      <div className="flex items-center text-xs font-semibold tracking-wider text-gray-500">
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
        <span className="mx-2 text-gray-400">&gt;</span>
        <span className="text-red-700 uppercase">HASIL ANALISIS</span>
      </div>

      {/* 2. Top Header Title & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Analisa Regulasi</h1>
          <p className="text-xs text-gray-600 mt-1 leading-relaxed">
            Telaah mendalam dan analisis dampak regulasi sektor jasa keuangan berbasis struktur pasal.
          </p>
        </div>

        {/* Tombol Analisis Ulang (Mendukung parameter segar) */}
        <div className="flex items-center gap-2 self-start sm:self-auto">
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
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-gray-900 truncate">
                {displayJudulRegulasi !== '-' ? displayJudulRegulasi : (loading ? 'Memuat identitas draft...' : `Draft Peraturan #${documentId}`)}
              </h2>
              <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-semibold border border-emerald-200/60 shrink-0">
                Dokumen Aktif
              </span>
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
              <span className={retryCount > 0 ? 'text-amber-700 font-semibold animate-pulse' : 'text-gray-500'}>
                {loadingStatusText}
              </span>
              <span className="text-gray-500 font-medium">
                {retryCount > 0 ? `Percobaan Sinkronisasi #${retryCount}` : 'Sedang diproses...'}
              </span>
            </div>
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

      {/* ERROR STATE: 404 / 403 / 503 / 504 / 422 */}
      {!data && !loading && (
        <div className="bg-white rounded-xl border border-gray-200 p-8 shadow-xs">
          <div className="max-w-md mx-auto text-center space-y-4">
            <div className="w-12 h-12 rounded-full bg-red-100 text-red-700 flex items-center justify-center mx-auto">
              <AlertCircle size={24} />
            </div>
            <div>
              <h3 className="text-base font-bold text-gray-900">
                {errorStatus === 404 
                  ? (errorMessage?.includes('Batas waktu') ? 'Batas Waktu Sinkronisasi Tercapai' : 'Dokumen Belum Siap Dianalisis')
                  : errorStatus === 403
                  ? 'Akses Ditolak'
                  : errorStatus === 503
                  ? 'Layanan Analisis Belum Siap'
                  : errorStatus === 504
                  ? 'Layanan Analisis Membutuhkan Waktu Terlalu Lama'
                  : errorStatus === 422
                  ? 'Validasi Parameter Gagal'
                  : 'Gagal Memuat Analisis Regulasi'}
              </h3>
              <p className="text-xs text-gray-600 mt-1 leading-relaxed">
                {errorMessage || 'Terjadi kendala teknis saat menghubungi peladen backend.'}
              </p>
            </div>
            <div className="flex items-center justify-center">
              <button
                type="button"
                onClick={() => loadAnalysis(false, false)}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-700 hover:bg-red-800 text-white rounded-lg text-xs font-semibold shadow-xs transition cursor-pointer"
              >
                <RefreshCw size={13} />
                <span>Coba Lagi</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* WORKSPACE 3-PANEL (Struktur Dokumen | Naskah Regulasi | Hasil Analisis) */}
      {data && !loading && (
        <div className="grid grid-cols-12 gap-4 items-stretch min-h-[720px]">
          {/* =================================================================== */}
          {/* PANEL KIRI: STRUKTUR DOKUMEN (Col-span 3) */}
          {/* =================================================================== */}
          <PanelErrorBoundary
            nama="Struktur Dokumen"
            className="col-span-12 lg:col-span-3 bg-white rounded-xl border border-gray-200 shadow-2xs h-[720px] p-4"
            onCobaLagi={() => loadAnalysis(false, false)}
          >
          <div className="col-span-12 lg:col-span-3 bg-white rounded-xl border border-gray-200 flex flex-col shadow-2xs overflow-hidden h-[720px]">
            {/* Header Panel Kiri */}
            <div className="p-4 border-b border-gray-100 shrink-0">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                    STRUKTUR DOKUMEN
                  </h3>
                </div>
                <span className="text-[11px] font-semibold text-gray-500">
                  {displayJumlahBab} Bab, {displayJumlahPasal} Pasal
                </span>
              </div>

              {/* Filter Cepat Pasal */}
              <div className="mt-2.5 relative">
                <input
                  type="text"
                  value={structureSearch}
                  onChange={(e) => setStructureSearch(e.target.value)}
                  placeholder="Cari bab atau pasal..."
                  className="w-full px-2.5 py-1.5 text-xs bg-gray-50 border border-gray-200 rounded-md focus:outline-none focus:border-red-700 focus:bg-white transition"
                />
              </div>
            </div>

            {/* Tree View Bab & Pasal */}
            <div className="flex-1 overflow-y-auto p-3 space-y-1.5 text-xs text-gray-700">
              {filteredKerangka.length === 0 && (
                <div className="py-8 text-center text-xs text-gray-400">
                  Tidak ada bab atau pasal yang cocok dengan &quot;{structureSearch}&quot;.
                </div>
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

          {/* =================================================================== */}
          {/* PANEL TENGAH: NASKAH REGULASI / SALINAN RESMI & PDF (Col-span 5) */}
          {/* =================================================================== */}
          <PanelErrorBoundary
            nama="Naskah Regulasi"
            className="col-span-12 lg:col-span-5 bg-white rounded-xl border border-gray-200 shadow-2xs h-[720px] p-4"
            onCobaLagi={() => loadAnalysis(false, false)}
          >
          <div className="col-span-12 lg:col-span-5 bg-white rounded-xl border border-gray-200 flex flex-col shadow-2xs overflow-hidden h-[720px]">
            {/* Header Panel Tengah */}
            <div className="p-3.5 border-b border-gray-100 flex items-center justify-between shrink-0 bg-white">
              <div className="flex items-center gap-2 text-xs">
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
                    Salinan Resmi
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

              <div className="flex items-center gap-2.5">
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
                  Halaman {currentPage} dari {totalPages}
                </span>
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

            {/* Konten Naskah: PDF Asli atau Salinan Formal OJK */}
            {viewMode === 'pdf' ? (
              <div className="flex-1 bg-gray-100 flex flex-col items-center justify-center p-2 relative overflow-hidden">
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
                className="flex-1 overflow-y-auto px-6 py-6 bg-gray-50/50 select-text scroll-smooth"
              >
                <div 
                  style={{ fontSize: `${(zoomLevel / 100) * 12.5}px` }}
                  className="max-w-[560px] mx-auto space-y-6 text-gray-800 leading-relaxed transition-all"
                >
                  {/* Header Salinan Resmi OJK */}
                  <div className="text-center space-y-2 pb-5 border-b border-gray-200">
                    <GarudaEmblem />
                    <p className="text-[0.85em] font-mono tracking-widest uppercase text-gray-500 font-bold">
                      SALINAN RESMI
                    </p>
                    <h2 className="text-[1.05em] font-bold uppercase tracking-wider text-gray-900">
                      {data.identitas?.penerbit || 'OTORITAS JASA KEUANGAN'}
                    </h2>
                    <p className="text-[0.95em] font-semibold text-gray-800">
                      {data.identitas?.nomor || (data.identitas?.number ? `${data.identitas.doc_type || 'Peraturan'} Nomor ${data.identitas.number}` : `DRAF REGULASI #${documentId}`)}
                    </p>
                    <p className="text-[0.85em] font-bold text-gray-600 tracking-wider">
                      TENTANG
                    </p>
                    <h1 className="text-[1.05em] font-extrabold uppercase tracking-wide text-gray-900 max-w-md mx-auto">
                      {data.identitas?.title || 'DRAF REGULASI KAJIAN'}
                    </h1>
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
                                    <p className="text-gray-800 leading-relaxed text-[0.92em] whitespace-pre-line font-serif">
                                      {fullArticleText}
                                    </p>
                                    {points.length > 0 && (
                                      <div className="pt-2.5 border-t border-gray-100 space-y-1.5">
                                        <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block">
                                          Intisari &amp; Norma Terdeteksi ({points.length} klausul)
                                        </span>
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
                              <p className="text-gray-800 leading-relaxed text-[0.92em] whitespace-pre-line font-serif">
                                {art.content_text}
                              </p>
                              {points.length > 0 && (
                                <div className="pt-2.5 border-t border-gray-100 space-y-1.5">
                                  <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block">
                                    Intisari &amp; Norma Terdeteksi ({points.length} klausul)
                                  </span>
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
                    <div className="text-center py-8 text-gray-500 text-xs">
                      Struktur bab dan pasal untuk draf ini belum tersedia. Silakan gunakan tab PDF Asli untuk membaca naskah lengkap.
                    </div>
                  )}

                  {/* Footer Dokumen Salinan */}
                  <div className="pt-6 border-t border-gray-200 flex justify-between items-center text-[0.75em] text-gray-400 font-mono">
                    <span>Salinan Dokumen — Harmonisasi HERO #{documentId}</span>
                    <span>Halaman {currentPage} dari {totalPages}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
          </PanelErrorBoundary>

          {/* =================================================================== */}
          {/* PANEL KANAN: HASIL ANALISIS (Col-span 4) */}
          {/* =================================================================== */}
          <PanelErrorBoundary
            nama="Hasil Analisis"
            className="col-span-12 lg:col-span-4 bg-white rounded-xl border border-gray-200 shadow-2xs h-[720px] p-4"
            onCobaLagi={() => loadAnalysis(false, false)}
          >
          <div className="col-span-12 lg:col-span-4 bg-white rounded-xl border border-gray-200 flex flex-col shadow-2xs overflow-hidden h-[720px]">
            {/* Header Panel Kanan */}
            <div className="p-3.5 border-b border-gray-100 flex flex-wrap items-center justify-between gap-2 shrink-0">
              <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                HASIL ANALISIS
              </h3>
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200 text-[11px] font-semibold">
                  <AlertCircle size={12} className="text-amber-600 shrink-0" />
                  <span>Draft / Rekomendasi</span>
                </span>
                <div className="flex items-center gap-1 text-emerald-700 font-bold text-xs shrink-0">
                  <Check size={14} className="text-emerald-600" />
                  <span>Selesai</span>
                </div>
              </div>
            </div>

            {/* Tab Bar: Ringkasan | Poin Utama | Dasar Hukum | Informasi Tambahan */}
            <div className="flex border-b border-gray-200 px-2 bg-gray-50/50 text-xs shrink-0 overflow-x-auto">
              <button
                type="button"
                onClick={() => setActiveTab('ringkasan')}
                className={`py-2.5 px-3 font-semibold transition border-b-2 shrink-0 cursor-pointer ${
                  activeTab === 'ringkasan'
                    ? 'border-red-700 text-red-700'
                    : 'border-transparent text-gray-500 hover:text-gray-800'
                }`}
              >
                Ringkasan
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('poin_utama')}
                className={`py-2.5 px-3 font-semibold transition border-b-2 shrink-0 cursor-pointer ${
                  activeTab === 'poin_utama'
                    ? 'border-red-700 text-red-700'
                    : 'border-transparent text-gray-500 hover:text-gray-800'
                }`}
              >
                Poin Utama
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('dasar_hukum')}
                className={`py-2.5 px-3 font-semibold transition border-b-2 shrink-0 cursor-pointer ${
                  activeTab === 'dasar_hukum'
                    ? 'border-red-700 text-red-700'
                    : 'border-transparent text-gray-500 hover:text-gray-800'
                }`}
              >
                Dasar Hukum
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('info_tambahan')}
                className={`py-2.5 px-3 font-semibold transition border-b-2 shrink-0 cursor-pointer ${
                  activeTab === 'info_tambahan'
                    ? 'border-red-700 text-red-700'
                    : 'border-transparent text-gray-500 hover:text-gray-800'
                }`}
              >
                Informasi Tambahan
              </button>
            </div>

            {/* Tab Contents */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
              {/* TAB 1: RINGKASAN */}
              {activeTab === 'ringkasan' && (
                <div className="space-y-4">
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

                    {/* Narasi Ringkasan AI (Jika mode AI aktif dan ringkasan_ai tersedia) */}
                    {mode === 'ai' && data.mode_dipakai === 'ai' && data.ringkasan_ai && (
                      <div className="bg-white/90 rounded-lg p-3 border border-red-200/70 space-y-1 shadow-2xs">
                        <span className="text-[10px] font-bold text-red-900 uppercase tracking-wider block">
                          Narasi Ringkasan AI
                        </span>
                        <p className="text-xs text-gray-800 leading-relaxed font-serif">
                          {data.ringkasan_ai}
                        </p>
                      </div>
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

                  {/* Filter Kategori */}
                  <div className="flex items-center gap-1 overflow-x-auto pb-1 text-[11px]">
                    {availableCategories.map(kat => (
                      <button
                        key={kat}
                        type="button"
                        onClick={() => setKategoriFilter(kat)}
                        className={`px-2 py-1 rounded-md font-semibold shrink-0 cursor-pointer transition ${
                          kategoriFilter === kat
                            ? 'bg-red-700 text-white'
                            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                      >
                        {kat}
                      </button>
                    ))}
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

              {/* TAB 3: DASAR HUKUM */}
              {activeTab === 'dasar_hukum' && (
                <div className="space-y-2.5">
                  <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider mb-2">
                    DASAR HUKUM TERKAIT
                  </h4>
                  {(data.dasar_hukum || []).map((dh, idx) => (
                    <div key={idx} className="p-2.5 rounded-lg border border-gray-100 bg-gray-50 flex items-start gap-2 text-xs text-gray-700">
                      <Scale size={14} className="text-red-700 shrink-0 mt-0.5" />
                      <span>{dh}</span>
                    </div>
                  ))}
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
            </div>

            {/* Catatan Disclaimer */}
            <div className="p-3 border-t border-gray-100 bg-gray-50/50 text-[10px] text-gray-500 leading-tight">
              Catatan: Hasil analisis ini merupakan bahan telaah otomatis berbasis sistem dan tetap memerlukan verifikasi oleh pejabat/analis berwenang.
            </div>
          </div>
          </PanelErrorBoundary>
        </div>
      )}

      {/* 5. STICKY BOTTOM BAR */}
      <div className="bg-white border border-gray-200 rounded-xl px-5 py-3 shadow-sm flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-gray-700">
          <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
          <span>
            Analisis selesai. {displayJumlahPasal} pasal dan {displayJumlahBab} bab terindeks lengkap secara {data?.mode_dipakai || mode}.
          </span>
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
                        <span className="text-[9px] font-bold px-1.5 py-0.2 bg-blue-100 text-blue-800 rounded">Rekomendasi</span>
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
    </div>
  );
}
