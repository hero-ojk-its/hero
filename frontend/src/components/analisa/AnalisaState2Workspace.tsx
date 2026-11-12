import { useState, useEffect, useRef, useCallback } from 'react';
import {
  FileText,
  ArrowLeft,
  AlertCircle,
  Loader2,
  Clock,
  Info,
  Sparkles,
  Lock,
  Check,
  RefreshCw,
} from 'lucide-react';
import {
  getMlAnalisa,
  getMlAnalisaViaJob,
  ANALISA_AI_INFO_LAMA_MS,
  getDocumentStatus,
  checkMlHealth,
  isDocumentReadyForAnalysis,
  saveStoredAnalisaWorkspace,
  parsePasalRef,
} from '../../lib/analisaApi';
import {
  labelStatusKeberlakuan,
  kelasBadgeStatusKeberlakuan,
} from '../../lib/labelStatus';
import { ApiError } from '../../lib/api';
import { PanelErrorBoundary } from '../PanelErrorBoundary';
import AnalisaBreadcrumb from './AnalisaBreadcrumb';
import HarmonisasiPanel from './HarmonisasiPanel';
import KemiripanDraftBanner from './KemiripanDraftBanner';
import type { HarmonisasiPanelState } from './HarmonisasiPanel';
import {
  postHarmonisasi,
  pesanGalatHarmonisasi,
  getStoredHarmonisasiResult,
  saveStoredHarmonisasiResult,
} from '../../lib/harmonisasiApi';
import type {
  MlAnalisaResponse,
  DocumentArticleSummary,
  DocumentStatusResponse,
} from '../../lib/analisaApi';

// 4 Tahap Analisis Mesin HERO
const PIPELINE_STEPS = [
  { id: 1, title: 'Kesiapan Dokumen', desc: 'Memeriksa kesiapan dokumen dan izin akses...' },
  { id: 2, title: 'Struktur Regulasi', desc: 'Memuat naskah dan susunan pasal dari pangkalan data...' },
  { id: 3, title: 'Analisis Regulasi', desc: 'Menjalankan penelaahan norma, kewajiban, dan sanksi...' },
  { id: 4, title: 'Kompilasi Intisari', desc: 'Menyusun ringkasan eksekutif dan indikator kepatuhan regulasi...' },
];

interface AnalisaState2WorkspaceProps {
  documentId: number;
  mode: 'deterministik' | 'ai';
  onBackToState1: () => void;
  onBackToSummary?: () => void;
}

export default function AnalisaState2Workspace({
  documentId,
  mode,
  onBackToState1,
  onBackToSummary,
}: AnalisaState2WorkspaceProps) {
  // State Data Analisis
  const [data, setData] = useState<MlAnalisaResponse | null>(null);
  const [articles, setArticles] = useState<DocumentArticleSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);

  // State Dokumen
  const [docStatus, setDocStatus] = useState<DocumentStatusResponse | null>(null);

  // State Polling & Pipeline
  const [pipelineStep, setPipelineStep] = useState<number>(1);
  const [loadingStatusText, setLoadingStatusText] = useState<string>('Memulai penyiapan analisis...');
  const [aiStartTime, setAiStartTime] = useState<number | null>(null);
  const [aiMelebihiLimaMenit, setAiMelebihiLimaMenit] = useState<boolean>(false);

  // State Harmonisasi
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
  const harmonisasiDimintaRef = useRef<number | null>(cachedHarmonisasi ? documentId : null);

  // Simpan preferensi workspace aktif
  useEffect(() => {
    saveStoredAnalisaWorkspace({
      documentId,
      mode,
      stage: 'analisa',
      activeTab: 'harmonisasi',
    });
  }, [documentId, mode]);

  // Fungsi Muat Harmonisasi
  const muatHarmonisasi = useCallback(async (segar: boolean) => {
    harmonisasiAbortRef.current?.abort();
    const controller = new AbortController();
    harmonisasiAbortRef.current = controller;
    const permintaanId = ++harmonisasiPermintaanRef.current;
    harmonisasiDimintaRef.current = documentId;

    setHarmonisasiState((prev) => ({
      documentId,
      status: 'loading',
      data: segar ? null : (prev?.documentId === documentId ? prev.data : null),
      galat: null,
    }));

    try {
      const hasil = await postHarmonisasi(documentId, { segar, signal: controller.signal });
      if (permintaanId !== harmonisasiPermintaanRef.current) return;
      saveStoredHarmonisasiResult(documentId, hasil);
      setHarmonisasiState({ documentId, status: 'sukses', data: hasil, galat: null });
    } catch (err) {
      if (permintaanId !== harmonisasiPermintaanRef.current || controller.signal.aborted) return;
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

  // Muat Harmonisasi otomatis saat mount
  useEffect(() => {
    if (harmonisasiDimintaRef.current === documentId) return;
    const t = setTimeout(() => {
      if (harmonisasiDimintaRef.current !== documentId) void muatHarmonisasi(false);
    }, 0);
    return () => clearTimeout(t);
  }, [documentId, muatHarmonisasi]);

  // Timer & Polling Refs
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeControllerRef = useRef<AbortController | null>(null);

  const clearRetryTimer = useCallback(() => {
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  const abortAnalysisRequest = useCallback(() => {
    if (activeControllerRef.current) {
      activeControllerRef.current.abort();
      activeControllerRef.current = null;
    }
  }, []);

  // Monitor waktu tunggu AI
  useEffect(() => {
    if (mode !== 'ai' || !loading || !aiStartTime) {
      setAiMelebihiLimaMenit(false);
      return;
    }
    const interval = setInterval(() => {
      const elapsed = Date.now() - aiStartTime;
      if (elapsed > ANALISA_AI_INFO_LAMA_MS) {
        setAiMelebihiLimaMenit(true);
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [mode, loading, aiStartTime]);

  // Fungsi Utama Pemuatan Analisis Regulasi
  const loadAnalysis = useCallback(async (forceFresh: boolean = false) => {
    abortAnalysisRequest();
    clearRetryTimer();

    const controller = new AbortController();
    activeControllerRef.current = controller;

    setLoading(true);
    setErrorMessage(null);
    setErrorStatus(null);
    setPipelineStep(1);
    setLoadingStatusText('Memeriksa kesiapan dokumen di peladen...');
    if (mode === 'ai') setAiStartTime(Date.now());

    try {
      // 1. Periksa kesiapan dokumen
      const statusDoc = await getDocumentStatus(documentId, controller.signal);
      if (controller.signal.aborted) return;
      setDocStatus(statusDoc);

      if (statusDoc.articles && Array.isArray(statusDoc.articles)) {
        setArticles(statusDoc.articles);
      }

      if (!isDocumentReadyForAnalysis(statusDoc)) {
        setErrorStatus(404);
        setErrorMessage('Dokumen masih dalam proses ekstraksi teks. Silakan tunggu beberapa saat.');
        setLoading(false);
        return;
      }

      // 2. Health check ML
      setPipelineStep(2);
      setLoadingStatusText('Memeriksa status mesin analisis...');
      const health = await checkMlHealth(controller.signal);
      if (controller.signal.aborted) return;

      // 3. Tentukan mode yang diminta
      let requestedMode: 'deterministik' | 'ai' = 'deterministik';
      if (mode === 'ai') {
        if (health?.mode_ai === true) {
          requestedMode = 'ai';
        } else {
          requestedMode = 'deterministik';
        }
      }

      setPipelineStep(3);
      setLoadingStatusText(
        requestedMode === 'ai'
          ? 'Menjalankan analisis cerdas AI (Gemini)...'
          : 'Menjalankan analisis deterministik berbasis aturan...'
      );

      const mlPromise = requestedMode === 'ai'
        ? getMlAnalisaViaJob(
            documentId,
            requestedMode,
            forceFresh,
            controller.signal,
            (dtk: number) => {
              setLoadingStatusText(`Menjalankan analisis AI (${dtk} detik)...`);
            }
          )
        : getMlAnalisa(documentId, requestedMode, forceFresh, controller.signal);

      const res = await mlPromise;
      if (controller.signal.aborted) return;

      setPipelineStep(4);
      setLoadingStatusText('Menyusun hasil telaah...');
      setData(res);
      setLoading(false);
      activeControllerRef.current = null;
    } catch (err: unknown) {
      if (controller.signal.aborted) return;
      if (err instanceof ApiError) {
        setErrorStatus(err.status);
        setErrorMessage(err.message);
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage('Terjadi kendala saat memuat analisis regulasi.');
      }
      setLoading(false);
      activeControllerRef.current = null;
    }
  }, [abortAnalysisRequest, clearRetryTimer, documentId, mode]);

  useEffect(() => {
    void loadAnalysis(false);
    return () => {
      abortAnalysisRequest();
      clearRetryTimer();
    };
  }, [abortAnalysisRequest, clearRetryTimer, loadAnalysis]);

  // Handler Jump to Pasal (halus & aman)
  const handleJumpToPasal = useCallback((pasalStr: string) => {
    if (!pasalStr || typeof pasalStr !== 'string') return;
    const trimmed = pasalStr.trim();
    const parsed = parsePasalRef(trimmed);
    const targetQuery = parsed.pasalNum ? `Pasal ${parsed.pasalNum}` : trimmed;

    // Cari kartu temuan yang memuat nomor pasal tersebut di dalam panel harmonisasi
    const cards = Array.from(document.querySelectorAll('div, h4, span, p'));
    const matched = cards.find(el => el.textContent?.includes(targetQuery));
    if (matched) {
      matched.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, []);

  // Format Metadata Dokumen
  const displayJudulRegulasi =
    data?.identitas?.tentang ||
    data?.identitas?.title ||
    docStatus?.title ||
    '-';

  const displayTanggalTerbit = docStatus?.created_at
    ? new Date(docStatus.created_at).toLocaleDateString('id-ID', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    : data?.identitas?.tahun
    ? `Tahun ${data.identitas.tahun}`
    : '-';

  const displayJumlahBab =
    data?.kerangka && Array.isArray(data.kerangka) && data.kerangka.length > 0
      ? data.kerangka.length
      : '-';

  const displayJumlahPasal =
    articles.length > 0
      ? articles.length
      : data?.jumlah_poin || (data?.poin_utama ? data.poin_utama.length : '-');

  const effectiveStatusKeberlakuan = docStatus?.status_keberlakuan;
  const actualMode: 'deterministik' | 'ai' =
    data?.mode_dipakai === 'ai' || data?.mode_dipakai === 'deterministik'
      ? data.mode_dipakai
      : mode;

  // Status Analisis Badge
  const getStatusBadge = () => {
    if (loading) {
      return (
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-50 text-amber-700 border border-amber-200 text-xs font-semibold shrink-0">
          <Loader2 size={13} className="animate-spin text-amber-600" />
          <span>Sedang menganalisis</span>
        </div>
      );
    }
    if (errorStatus && !data) {
      if (errorStatus === 403) {
        return (
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-50 text-amber-800 border border-amber-200 text-xs font-semibold shrink-0">
            <Lock size={13} className="text-amber-700" />
            <span>Akses Ditolak</span>
          </div>
        );
      }
      return (
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-50 text-red-700 border border-red-200 text-xs font-semibold shrink-0">
          <AlertCircle size={13} className="text-red-600" />
          <span>Analisis gagal</span>
        </div>
      );
    }
    return (
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-semibold shrink-0">
        <span className="w-2 h-2 rounded-full bg-emerald-500" />
        <span>Analisis selesai</span>
      </div>
    );
  };

  return (
    <div className="w-full space-y-4 pb-12 font-sans max-w-7xl mx-auto">
      {/* 1. Header Workspace Breadcrumb */}
      <AnalisaBreadcrumb
        stage="analisa"
        onBackToState1={onBackToState1}
        onBackToSummary={onBackToSummary}
      />

      {/* 2. Top Header Title & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Analisa Regulasi</h1>
          <p className="text-sm text-gray-500 mt-0.5 leading-relaxed">
            Telaah hasil harmonisasi dan uji keselarasan norma regulasi sektor jasa keuangan berbasis struktur pasal.
          </p>
        </div>

        {/* Tombol Aksi Header: Sederhana & Konsisten */}
        <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
          {onBackToSummary && (
            <button
              type="button"
              onClick={onBackToSummary}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-xs font-semibold shadow-2xs transition cursor-pointer"
              title="Kembali ke tampilan Ringkasan Eksekutif dan Key Takeaways"
            >
              <ArrowLeft size={14} className="text-gray-500" />
              <span>Kembali ke Summary</span>
            </button>
          )}

          <button
            type="button"
            onClick={onBackToState1}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-xs font-semibold shadow-2xs transition cursor-pointer"
            title="Mulai analisis dokumen regulasi baru"
          >
            <span>Mulai Analisis Baru</span>
          </button>
        </div>
      </div>

      {/* 3. Informasi Dokumen & Kontrol Status Ringkas */}
      <div className="bg-white rounded-xl border border-gray-200 px-4 py-2.5 shadow-2xs flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div className="flex items-center gap-3.5 min-w-0">
          <div className="w-10 h-10 rounded-lg bg-red-50 text-red-700 border border-red-100 flex items-center justify-center shrink-0">
            <FileText size={20} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-semibold text-gray-900 truncate max-w-[500px]">
                {displayJudulRegulasi !== '-' ? displayJudulRegulasi : (loading ? 'Memuat identitas draft...' : `Draft Peraturan #${documentId}`)}
              </h2>
              {/* Badge Status Keberlakuan */}
              {effectiveStatusKeberlakuan && (
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border shrink-0 ${kelasBadgeStatusKeberlakuan(effectiveStatusKeberlakuan)}`}>
                  {labelStatusKeberlakuan(effectiveStatusKeberlakuan)}
                </span>
              )}

              {/* Badge Status KB */}
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
              {displayTanggalTerbit} • {data?.identitas?.jenis || docStatus?.regulation_type || 'Regulasi'} {data?.identitas?.nomor ? `No. ${data.identitas.nomor}` : ''} • {displayJumlahBab} Bab • {displayJumlahPasal} Pasal
            </p>
          </div>
        </div>

        {/* Right Badges & Mode Control */}
        <div className="flex items-center gap-2.5 shrink-0 self-end md:self-auto flex-wrap">
          {/* Badge Cache Basi jika ada */}
          {data?.cache?.basi === true && (
            <div
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-amber-200 bg-amber-50 text-amber-800 text-xs font-semibold"
              title="Hasil analisis lama tersimpan"
            >
              <Clock size={13} className="text-amber-600" />
              <span>Hasil lama</span>
            </div>
          )}

          {/* Kontrol Mode Ringkas */}
          <div 
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 bg-gray-50 text-gray-700 text-xs font-medium"
            title={`Mode aktif: ${actualMode === 'ai' ? 'AI' : 'Deterministik'}. Analisa berbantuan AI akan segera hadir.`}
          >
            <span className="font-semibold text-gray-900">Mode: {actualMode === 'ai' ? 'AI' : 'Deterministik'}</span>
            <span className="text-gray-300">|</span>
            <span className="text-[11px] text-gray-500 flex items-center gap-1">
              <Sparkles size={11} className="text-gray-400" />
              <span>AI</span>
              <span className="px-1 py-0.2 rounded text-[9px] font-bold bg-amber-100 text-amber-800 uppercase">
                Segera
              </span>
            </span>
          </div>

          {/* Status Analisis Badge */}
          {getStatusBadge()}
        </div>
      </div>

      {/* 3b. Kemiripan Draft Banner */}
      <PanelErrorBoundary nama="Kemiripan Draft">
        <KemiripanDraftBanner documentId={documentId} />
      </PanelErrorBoundary>

      {/* 4. Processing Pipeline Banner saat Loading */}
      {loading && (
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
                0% { transform: translateX(-100%); }
                50% { transform: translateX(100%); }
                100% { transform: translateX(320%); }
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
              <span className={aiMelebihiLimaMenit ? 'text-amber-700 font-semibold animate-pulse' : 'text-gray-500'}>
                {loadingStatusText}
              </span>
              <span className="text-gray-500 font-medium">
                Sedang diproses...
              </span>
            </div>
            {aiMelebihiLimaMenit && (
              <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                <span>Proses ini sudah berjalan lebih dari 5 menit. Dokumen panjang/kompleks memang butuh waktu lebih lama untuk dianalisa AI.</span>
              </div>
            )}
          </div>

          {/* Pipeline Step Pills */}
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
      )}

      {/* 5. Error State */}
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
              {errorStatus !== 403 && (
                <button
                  type="button"
                  onClick={() => void loadAnalysis(false)}
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

      {/* 6. PANEL UTAMA: HASIL ANALISA (SATU KOLOM LENGKAP) */}
      {data && !loading && (
        <div className="w-full bg-white rounded-xl border border-gray-200 shadow-2xs overflow-hidden flex flex-col">
          {/* Header Panel Hasil Analisa */}
          <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between bg-white shrink-0">
            <div>
              <h3 className="text-base font-semibold text-gray-900 tracking-tight">
                Hasil Analisa
              </h3>
              <p className="text-xs text-gray-500 mt-0.5">
                Hasil analisa pembandingan pasal dengan Knowledge Base.
              </p>
            </div>
            {Array.isArray(harmonisasi?.data?.temuan) && harmonisasi.data.temuan.length > 0 && (
              <span className="px-2.5 py-0.5 rounded-full text-xs bg-red-50 text-red-700 font-semibold border border-red-200">
                {harmonisasi.data.temuan.length} Temuan
              </span>
            )}
          </div>

          {/* Konten Harmonisasi Utama */}
          <div className="p-4 flex-1 min-h-[500px]">
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
          </div>

          {/* Catatan Disclaimer */}
          <div className="px-4 py-2.5 border-t border-gray-100 bg-gray-50/50 text-xs text-gray-500 leading-normal flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Info size={13} className="text-gray-400 shrink-0" />
              <span>
                Catatan: Hasil analisis ini merupakan bahan telaah otomatis berbasis sistem dan tetap memerlukan verifikasi oleh pejabat/analis berwenang.
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
