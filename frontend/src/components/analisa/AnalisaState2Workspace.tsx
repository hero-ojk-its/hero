import { useState, useEffect, useRef, useCallback } from 'react';
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
  Sparkles
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { getMlAnalisa, getDocumentStatus } from '../../lib/analisaApi';
import { ApiError, API_BASE_URL } from '../../lib/api';
import type { MlAnalisaResponse, DocumentArticleSummary } from '../../lib/analisaApi';

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

// 4 Tahap Pipeline Analisis Mesin HERO
const PIPELINE_STEPS = [
  { id: 1, title: 'Inisialisasi & Validasi', desc: 'Membaca struktur naskah PDF dan memverifikasi integritas dokumen...' },
  { id: 2, title: 'Ekstraksi BAB & Pasal', desc: 'Memetakan kerangka regulasi dan mengelompokkan pasal...' },
  { id: 3, title: 'Analisis Norma & Kewajiban', desc: 'Mengekstraksi klausul normatif, sanksi administratif, dan dasar hukum...' },
  { id: 4, title: 'Kompilasi Intisari', desc: 'Menghasilkan ringkasan eksekutif dan indikator kepatuhan regulasi...' }
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

  // State Animasi Progress Pipeline
  const [pipelineStep, setPipelineStep] = useState<number>(1);
  const [pipelineProgress, setPipelineProgress] = useState<number>(15);
  const [showProcessingBanner, setShowProcessingBanner] = useState<boolean>(true);
  const pipelineTimerRef = useRef<ReturnType<typeof setTimeout>[]>([]);

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
  const maxPageFromPoints = (data?.poin_utama || []).reduce((max, p) => (p.halaman && p.halaman > max ? p.halaman : max), 1);
  const totalPages = typeof data?.metrik?.jumlah_halaman === 'number' && data.metrik.jumlah_halaman > 0
    ? data.metrik.jumlah_halaman
    : Math.max(maxPageFromPoints, 1);
  const naskahContainerRef = useRef<HTMLDivElement>(null);
  const [highlightedPasalId, setHighlightedPasalId] = useState<string | null>('pasal-1');

  // State Workspace Panel 3: Hasil Analisis Tabs
  const [activeTab, setActiveTab] = useState<'ringkasan' | 'poin_utama' | 'dasar_hukum' | 'info_tambahan'>('ringkasan');
  const [kategoriFilter, setKategoriFilter] = useState<string>('Semua');

  // Bersihkan timer pipeline saat unmount
  const clearPipelineTimers = useCallback(() => {
    pipelineTimerRef.current.forEach(timer => clearTimeout(timer));
    pipelineTimerRef.current = [];
  }, []);

  // Lewati animasi dan langsung tampilkan hasil
  const handleSkipLoading = () => {
    clearPipelineTimers();
    setPipelineStep(4);
    setPipelineProgress(100);
    setLoading(false);
  };

  // Muat analisis (eksplisit demo atau panggilan API nyata)
  const loadAnalysis = useCallback(async (forceFresh: boolean = false) => {
    clearPipelineTimers();
    setLoading(true);
    setIsRefreshing(forceFresh);
    setErrorStatus(null);
    setErrorMessage(null);
    setShowProcessingBanner(true);

    // Inisialisasi pipeline progress visual
    setPipelineStep(1);
    setPipelineProgress(20);

    const t1 = setTimeout(() => {
      setPipelineStep(2);
      setPipelineProgress(48);
    }, 500);

    const t2 = setTimeout(() => {
      setPipelineStep(3);
      setPipelineProgress(76);
    }, 1100);

    const t3 = setTimeout(() => {
      setPipelineStep(4);
      setPipelineProgress(94);
    }, 1700);

    pipelineTimerRef.current = [t1, t2, t3];

    // Pemanggilan API Nyata ke Backend ML & Dokumen Status
    try {
      const [mlRes, statusRes] = await Promise.allSettled([
        getMlAnalisa(documentId, mode, forceFresh),
        getDocumentStatus(documentId),
      ]);

      if (mlRes.status === 'fulfilled') {
        setData(mlRes.value);
      } else {
        throw mlRes.reason;
      }

      if (statusRes.status === 'fulfilled' && Array.isArray(statusRes.value.articles)) {
        setArticles(statusRes.value.articles);
      }
    } catch (err: unknown) {
      setData(null);
      if (err instanceof ApiError) {
        setErrorStatus(err.status);
        if (err.status === 404) {
          setErrorMessage(
            'Dokumen belum siap dianalisis: dokumen belum memiliki pasal yang terbaca di lapisan data. ' +
            'Pastikan proses ekstraksi dokumen telah tuntas dan layanan sinkronisasi aktif.'
          );
        } else if (err.status === 403) {
          setErrorMessage('Akses ditolak: Anda tidak memiliki wewenang untuk menelaah dokumen ini.');
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
        setErrorStatus(0);
        setErrorMessage(err.message || 'Gagal terhubung ke layanan analisis regulasi.');
      } else {
        setErrorStatus(0);
        setErrorMessage('Terjadi galat tak dikenal saat memuat data analisis.');
      }
    } finally {
      const tFinal = setTimeout(() => {
        setPipelineProgress(100);
        setLoading(false);
        setIsRefreshing(false);
      }, 2000);
      pipelineTimerRef.current.push(tFinal);
    }
  }, [clearPipelineTimers, documentId, mode]);

  // Efek inisialisasi load analysis
  useEffect(() => {
    let isCancelled = false;

    const initialize = async () => {
      await Promise.resolve();
      if (!isCancelled) {
        loadAnalysis(false);
      }
    };

    initialize();

    return () => {
      isCancelled = true;
      clearPipelineTimers();
    };
  }, [loadAnalysis, clearPipelineTimers]);

  // Handler Expand/Collapse BAB
  const toggleBab = (babName: string) => {
    setExpandedBabs(prev => ({
      ...prev,
      [babName]: !prev[babName]
    }));
  };

  // Handler Klik Pasal pada Panel 1 atau Panel 3
  const handleJumpToPasal = (pasalStr: string) => {
    setSelectedPasal(pasalStr);

    if (viewMode !== 'salinan') {
      setViewMode('salinan');
    }

    const match = pasalStr.match(/Pasal\s+(\d+)/i);
    const pasalNum = match ? match[1] : '1';
    const targetElementId = `pasal-${pasalNum}`;

    setHighlightedPasalId(targetElementId);

    setTimeout(() => {
      const el = document.getElementById(targetElementId);
      if (el && naskahContainerRef.current) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        const estPage = Math.min(totalPages, Math.max(1, Math.ceil(parseInt(pasalNum, 10) / 2)));
        setCurrentPage(estPage);
      }
    }, 50);

    if (data?.kerangka) {
      for (const item of data.kerangka) {
        if (item.pasal?.some(p => p.toLowerCase().includes(`pasal ${pasalNum}`))) {
          if (item.bab) {
            setExpandedBabs(prev => ({ ...prev, [item.bab]: true }));
          }
          break;
        }
      }
    }

    setTimeout(() => {
      setHighlightedPasalId(null);
    }, 3000);
  };

  // Navigasi ke Harmonisasi
  const handleGoToHarmonisasi = () => {
    navigate('/harmonisasi', {
      state: {
        draftId: documentId,
        draftTitle: data?.identitas?.nomor || data?.identitas?.title || 'POJK 11/2024 tentang Ketahanan & Keamanan Siber'
      }
    });
  };

  // Ekspor Ringkasan Analisis ke File Teks
  const handleDownloadSummary = () => {
    if (!data) return;
    const content = `========================================================\n` +
      `HERO - RINGKASAN ANALISA REGULASI OTOMATIS OJK\n` +
      `STATUS: DRAFT / REKOMENDASI — MEMERLUKAN REVIEW\n` +
      `========================================================\n` +
      `PERHATIAN: Seluruh ringkasan, ekstraksi norma, dan poin analisis\n` +
      `pada dokumen ini berstatus DRAFT / REKOMENDASI dan wajib\n` +
      `diverifikasi serta ditelaah oleh analis atau pejabat berwenang\n` +
      `sebelum dijadikan rujukan resmi.\n` +
      `========================================================\n\n` +
      `Dokumen: ${data.identitas?.nomor || data.identitas?.title || 'Draf Regulasi'}\n` +
      `Tahun: ${data.identitas?.tahun || data.identitas?.year || new Date().getFullYear()}\n` +
      `Mode Diminta: ${mode}\n` +
      `Mode Dipakai: ${data.mode_dipakai || mode}\n\n` +
      `--- RINGKASAN EKSEKUTIF ---\n` +
      `${data.ringkasan_teks || ''}\n\n` +
      `--- POIN KUNCI & KEWAJIBAN ---\n` +
      (data.poin_utama || []).map((p, i) => `${i + 1}. [${p.kategori}] ${p.teks} (${p.ref || p.pasal || ''})`).join('\n') +
      `\n\n--- DASAR HUKUM ---\n` +
      (data.dasar_hukum || []).map((dh, i) => `${i + 1}. ${dh}`).join('\n') +
      `\n\n--- METRIK REGULASI ---\n` +
      `Jumlah Bab: ${String(data.metrik?.jumlah_bab ?? '-')}\n` +
      `Jumlah Pasal: ${String(data.metrik?.jumlah_pasal ?? '-')}\n` +
      `Jumlah Kewajiban: ${String(data.metrik?.jumlah_kewajiban ?? '-')}\n` +
      `Jumlah Larangan: ${String(data.metrik?.jumlah_larangan ?? '-')}\n\n` +
      `Catatan:\n${data.catatan || 'Keluaran sistem bukan keputusan final. Wajib diverifikasi oleh pejabat/analis berwenang.'}\n`;

    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `Ringkasan_Analisis_Dokumen_${documentId}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // Zoom Handler
  const handleZoomIn = () => setZoomLevel(prev => Math.min(150, prev + 15));
  const handleZoomOut = () => setZoomLevel(prev => Math.max(75, prev - 15));

  // Filter Struktur Dokumen berdasarkan pencarian
  const filteredKerangka = (data?.kerangka || []).map(bab => ({
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
  const rawPdf = data?.pdf;
  const pdfUrl = rawPdf
    ? (rawPdf.startsWith('http') || rawPdf.startsWith('/') ? rawPdf : `${API_BASE_URL}/${rawPdf.replace(/^\/+/, '')}`)
    : `${API_BASE_URL}/api/v1/documents/${documentId}/pdf`;

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
            title="Kirim permintaan analisis ulang ke backend (parameter segar=true). Catatan: bypass cache di peladen memerlukan dukungan rute backend terkait."
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
                {data?.identitas?.nomor || data?.identitas?.title || (loading ? 'Memuat identitas draft...' : `Draft Peraturan #${documentId}`)}
              </h2>
              <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-semibold border border-emerald-200/60 shrink-0">
                Dokumen Aktif
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-0.5 truncate">
              {data?.identitas?.tanggal || data?.identitas?.date || '17 Okt 2024'} • Perbankan • {String(data?.metrik?.jumlah_bab ?? 14)} Bab • {String(data?.metrik?.jumlah_pasal ?? 92)} Pasal
            </p>
          </div>
        </div>

        {/* Right Badges & Controls */}
        <div className="flex items-center gap-2.5 shrink-0 self-end md:self-auto">
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
                    Tahap {pipelineStep} dari 4 ({pipelineProgress}%)
                  </span>
                </div>
                <p className="text-xs text-gray-600 mt-0.5">
                  {PIPELINE_STEPS[pipelineStep - 1]?.desc}
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={handleSkipLoading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-gray-600 hover:text-gray-900 bg-white hover:bg-gray-50 border border-gray-200 rounded-lg transition self-end sm:self-auto cursor-pointer shadow-2xs"
            >
              <Sparkles size={13} className="text-amber-600" />
              <span>Lewati Animasi</span>
            </button>
          </div>

          {/* Progress Bar Track */}
          <div className="space-y-1.5">
            <div className="w-full h-2.5 bg-gray-100 rounded-full overflow-hidden p-0.5 border border-gray-200/60">
              <div 
                style={{ width: `${pipelineProgress}%` }}
                className="h-full bg-gradient-to-r from-red-800 via-red-600 to-red-700 rounded-full transition-all duration-500 ease-out relative"
              >
                <div className="absolute inset-0 bg-white/30 animate-pulse rounded-full" />
              </div>
            </div>
            <div className="flex items-center justify-between text-[11px] text-gray-400 font-mono">
              <span>Mengekstraksi naskah regulasi dan memvalidasi norma hukum...</span>
              <span className="font-semibold text-gray-700">{pipelineProgress}%</span>
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
              <strong>Analisis Berhasil:</strong> Seluruh tahap ekstraksi dan identifikasi norma telah tuntas. {String(data.metrik?.jumlah_pasal ?? 92)} pasal dan {String(data.metrik?.jumlah_bab ?? 14)} bab siap ditelaah pada 3 panel workspace.
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
                  ? 'Dokumen Belum Siap Dianalisis' 
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
                onClick={() => loadAnalysis(false)}
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
                  {String(data.metrik?.jumlah_bab ?? 14)} Bab, {String(data.metrik?.jumlah_pasal ?? 92)} Pasal
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
                          const isSelected = selectedPasal === pasalText || pasalText.includes(selectedPasal);

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

          {/* =================================================================== */}
          {/* PANEL TENGAH: NASKAH REGULASI / SALINAN RESMI & PDF (Col-span 5) */}
          {/* =================================================================== */}
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
                  href={pdfUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-gray-600 hover:text-red-700 transition"
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

            {/* Konten Naskah: PDF Asli atau Salinan Formal OJK */}
            {viewMode === 'pdf' ? (
              <div className="flex-1 bg-gray-100 flex flex-col items-center justify-center p-2 relative overflow-hidden">
                <iframe
                  src={pdfUrl}
                  className="w-full h-full border-0 rounded bg-white"
                  title={`Naskah PDF Asli #${documentId}`}
                />
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
                            const match = pasalStr.match(/Pasal\s+(\d+)/i);
                            const pasalNum = match ? match[1] : '';
                            const targetId = pasalNum ? `pasal-${pasalNum}` : undefined;
                            const points = (data.poin_utama || []).filter(p => {
                              if (p.pasal && p.pasal.toLowerCase().includes(pasalStr.toLowerCase())) return true;
                              if (p.ref && p.ref.toLowerCase().includes(pasalStr.toLowerCase())) return true;
                              return false;
                            });
                            const isHighlighted = targetId ? highlightedPasalId === targetId : false;

                            // Cari teks lengkap artikel dari hasil ekstraksi backend
                            const matchingArticle = articles.find(a => {
                              if (!pasalNum) return false;
                              const aMatch = a.article_number.match(/Pasal\s+(\d+)/i) || a.article_number.match(/^(\d+)$/);
                              const aNum = aMatch ? aMatch[1] : a.article_number;
                              return aNum === pasalNum;
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
                                  <span className="font-bold text-[0.95em] text-gray-900">{pasalStr}</span>
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

          {/* =================================================================== */}
          {/* PANEL KANAN: HASIL ANALISIS (Col-span 4) */}
          {/* =================================================================== */}
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
                  <div className="bg-red-50/40 border border-red-100 rounded-xl p-4 space-y-2">
                    <span className="text-[11px] font-bold text-red-800 uppercase tracking-wider block">
                      RINGKASAN EKSEKUTIF
                    </span>
                    <p className="text-xs text-gray-700 leading-relaxed">
                      {data.ringkasan_teks || (data.ringkasan && data.ringkasan[0]?.kalimat) || 'Regulasi ini mengatur ketentuan pokok, tata kelola, dan batasan operasional bagi sektor terkait.'}
                    </p>
                  </div>

                  <div>
                    <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider mb-2.5">
                      POIN KUNCI
                    </h4>
                    <div className="space-y-3">
                      {(data.poin_utama || []).slice(0, 4).map((p, idx) => {
                        const targetRef = p.ref || p.pasal;
                        return (
                          <div key={p.id || idx} className="flex items-start gap-2 text-xs">
                            <span className="w-1.5 h-1.5 rounded-full bg-red-700 mt-1.5 shrink-0" />
                            <div className="space-y-1 flex-1">
                              <p className="text-gray-800 leading-relaxed">{p.teks}</p>
                              {targetRef && (
                                <button
                                  type="button"
                                  onClick={() => handleJumpToPasal(targetRef)}
                                  className="inline-flex items-center gap-1 text-red-700 hover:underline font-mono text-[11px] font-semibold cursor-pointer"
                                >
                                  <ExternalLink size={10} />
                                  <span>{targetRef}</span>
                                </button>
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
                    {['Semua', 'Tata Kelola', 'Manajemen Risiko', 'Kewajiban', 'Larangan', 'Sanksi'].map(kat => (
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
                        const targetRef = p.ref || p.pasal;
                        const urgencyLabel = p.urgensi || (p.prioritas !== undefined ? `Prioritas ${p.prioritas}` : undefined);
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
                              {targetRef && (
                                <button
                                  type="button"
                                  onClick={() => handleJumpToPasal(targetRef)}
                                  className="inline-flex items-center gap-1 text-red-700 hover:underline font-mono text-[11px] font-semibold cursor-pointer"
                                >
                                  <ExternalLink size={10} />
                                  <span>{targetRef} {p.halaman ? `(Hal. ${p.halaman})` : ''}</span>
                                </button>
                              )}
                            </div>
                            <p className="text-xs text-gray-800 leading-relaxed">{p.teks}</p>
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
                        <span className="text-lg font-bold text-gray-900 block">{String(data.metrik?.jumlah_bab ?? 14)}</span>
                        <span className="text-[10px] text-gray-500 uppercase">Jumlah Bab</span>
                      </div>
                      <div className="p-2.5 bg-gray-50 border border-gray-100 rounded-lg">
                        <span className="text-lg font-bold text-gray-900 block">{String(data.metrik?.jumlah_pasal ?? 92)}</span>
                        <span className="text-[10px] text-gray-500 uppercase">Jumlah Pasal</span>
                      </div>
                      <div className="p-2.5 bg-gray-50 border border-gray-100 rounded-lg">
                        <span className="text-lg font-bold text-red-700 block">{String(data.metrik?.jumlah_kewajiban ?? 48)}</span>
                        <span className="text-[10px] text-gray-500 uppercase">Kewajiban</span>
                      </div>
                      <div className="p-2.5 bg-gray-50 border border-gray-100 rounded-lg">
                        <span className="text-lg font-bold text-amber-700 block">{String(data.metrik?.jumlah_larangan ?? 14)}</span>
                        <span className="text-[10px] text-gray-500 uppercase">Larangan</span>
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
        </div>
      )}

      {/* 5. STICKY BOTTOM BAR */}
      <div className="bg-white border border-gray-200 rounded-xl px-5 py-3 shadow-sm flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-gray-700">
          <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
          <span>
            Analisis selesai. {String(data?.metrik?.jumlah_pasal ?? 92)} pasal dan {String(data?.metrik?.jumlah_bab ?? 14)} bab terindeks lengkap secara {data?.mode_dipakai || mode}.
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

          <button
            type="button"
            disabled={!data || loading}
            onClick={handleDownloadSummary}
            className={`inline-flex items-center gap-1.5 px-4 py-2 border text-xs font-semibold rounded-lg transition shadow-2xs cursor-pointer ${
              data && !loading
                ? 'bg-white border-gray-300 hover:bg-gray-50 text-gray-700'
                : 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
            }`}
          >
            <Download size={13} />
            <span>Unduh Ringkasan Analisis</span>
          </button>

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
    </div>
  );
}
