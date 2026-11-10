/**
 * frontend/src/components/analisa/SummaryView.tsx
 *
 * Tampilan Summary Tahap Awal HERO (Keputusan Client Pak Faris):
 * 1. Menampilkan naskah draf regulasi (PDF Asli atau Teks Terstruktur) di Panel Kiri.
 * 2. Menampilkan Ringkasan Eksekutif dan Key Takeaways di Panel Kanan.
 * 3. Default: Deterministik tanpa membandingkan ke Knowledge Base.
 * 4. Toggle AI opsional di kanan atas untuk menyusun narasi AI setelah deterministik siap.
 * 5. Tombol utama di footer: "Lanjutkan Analisa" untuk beralih ke Workspace Analisa Regulasi lengkap.
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  FileText,
  Sparkles,
  ArrowRight,
  ArrowLeft,
  ExternalLink,
  RefreshCw,
  AlertCircle,
  ChevronRight,
} from 'lucide-react';

import {
  getMlAnalisa,
  getMlAnalisaViaJob,
  getDocumentStatus,
  checkMlHealth,
  parsePasalRef,
  normalisasiRingkasanAi,
  type MlAnalisaResponse,
  type MlAnalisaPoint,
  type DocumentStatusResponse,
  type MlHealthResponse,
} from '../../lib/analisaApi';
import { apiFetch, apiFetchBlob } from '../../lib/api';
import type { DocumentTextResponse } from '../../lib/api';
import RingkasanAiPanel from './RingkasanAiPanel';

/**
 * Rujukan yang tidak menunjuk ke Pasal tertentu, mis. dokumen berbentuk
 * Keputusan (diktum KESATU, KEDUA, ...) yang diberi label
 * "Teks dokumen (pasal tidak terbaca)" oleh mesin analisis.
 */
const isNoPasalRef = (ref: string): boolean => /pasal\s+tidak\s+terbaca/i.test(ref);

interface RujukanChipProps {
  refStr: string;
  onJump: (ref: string) => void;
  iconSize?: number;
  title?: string;
}

/** Chip rujukan. Rujukan tanpa Pasal tampil netral (abu-abu), bukan seperti galat. */
function RujukanChip({ refStr, onJump, iconSize = 9, title }: RujukanChipProps) {
  if (isNoPasalRef(refStr)) {
    return (
      <span
        className="inline-flex items-center gap-1 font-mono text-[10px] font-medium text-gray-600 bg-gray-100 px-2 py-0.5 rounded border border-gray-200"
        title="Bagian ini tidak berasal dari satu Pasal tertentu (mis. dokumen berbentuk Keputusan atau tanpa pasal). Periksa langsung pada Naskah."
      >
        Rujukan umum
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onJump(refStr)}
      className="inline-flex items-center gap-1 font-mono text-[10px] font-bold text-red-700 hover:text-red-900 bg-white hover:bg-red-50 px-2 py-0.5 rounded border border-red-200 transition cursor-pointer"
      title={title ?? `Lompat ke ${refStr}`}
    >
      <span>{refStr}</span>
      <ExternalLink size={iconSize} />
    </button>
  );
}

export interface SummaryViewProps {
  documentId: number;
  onBackToState1: () => void;
  onProceedToAnalisa: () => void;
}

export default function SummaryView({
  documentId,
  onBackToState1,
  onProceedToAnalisa,
}: SummaryViewProps) {
  // State Data Analisis Deterministik
  const [data, setData] = useState<MlAnalisaResponse | null>(null);
  const [docStatus, setDocStatus] = useState<DocumentStatusResponse | null>(null);
  const [docText, setDocText] = useState<DocumentTextResponse | null>(null);
  const [mlHealth, setMlHealth] = useState<MlHealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // State AI Opsional
  const [aiEnabled, setAiEnabled] = useState<boolean>(false);
  const [aiData, setAiData] = useState<MlAnalisaResponse | null>(null);
  const [aiLoading, setAiLoading] = useState<boolean>(false);
  const [aiSecondsElapsed, setAiSecondsElapsed] = useState<number>(0);
  const [aiError, setAiError] = useState<string | null>(null);
  const aiAbortControllerRef = useRef<AbortController | null>(null);

  // State Viewer Panel Kiri
  const [viewMode, setViewMode] = useState<'teks' | 'pdf'>('teks');
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState<boolean>(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const pdfBlobUrlRef = useRef<string | null>(null);

  // State Scroll Target Pasal di Panel Teks
  const [activePasalRef, setActivePasalRef] = useState<string | null>(null);
  const articleRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Layout Resizable (Desktop)
  const [leftWidthPercent, setLeftWidthPercent] = useState<number>(52);
  const [isResizing, setIsResizing] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Layout Responsif (Mobile / Tablet < 1024px)
  const [mobileActiveTab, setMobileActiveTab] = useState<'naskah' | 'summary'>('summary');

  // 1. Memuat Data Deterministik & Berkas Dokumen saat mount / documentId berubah
  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();

    setLoading(true);
    setError(null);

    // Bersihkan Blob URL lama
    if (pdfBlobUrlRef.current) {
      URL.revokeObjectURL(pdfBlobUrlRef.current);
      pdfBlobUrlRef.current = null;
    }
    setPdfBlobUrl(null);
    setAiData(null);
    setAiEnabled(false);
    setAiError(null);

    setPdfLoading(true);
    setPdfError(null);

    // Request paralel: status dokumen, analisa deterministik, teks, blob PDF, dan ML health
    Promise.allSettled([
      getDocumentStatus(documentId, controller.signal),
      getMlAnalisa(documentId, 'deterministik', false, controller.signal),
      apiFetch<DocumentTextResponse>(`/api/v1/documents/${documentId}/text`, { signal: controller.signal }),
      apiFetchBlob(`/api/v1/documents/${documentId}/pdf`, { signal: controller.signal }),
      checkMlHealth(),
    ]).then(([statusResult, analisaResult, textResult, pdfResult, healthResult]) => {
      if (!isMounted) return;

      // Status Dokumen
      if (statusResult.status === 'fulfilled') {
        setDocStatus(statusResult.value);
      }

      // ML Health (ketersediaan model AI)
      if (healthResult.status === 'fulfilled') {
        setMlHealth(healthResult.value);
      }

      // Analisa Deterministik
      if (analisaResult.status === 'fulfilled') {
        setData(analisaResult.value);
      } else {
        const err = analisaResult.reason;
        const msg = err instanceof Error ? err.message : 'Gagal memuat hasil summary dokumen.';
        setError(msg);
      }

      // Teks Dokumen
      if (textResult.status === 'fulfilled') {
        setDocText(textResult.value);
      }

      // PDF Blob
      if (pdfResult.status === 'fulfilled') {
        const objectUrl = URL.createObjectURL(pdfResult.value);
        pdfBlobUrlRef.current = objectUrl;
        setPdfBlobUrl(objectUrl);
        setPdfLoading(false);
      } else {
        setPdfError('Berkas PDF tidak dapat dimuat.');
        setPdfLoading(false);
      }

      setLoading(false);
    });

    return () => {
      isMounted = false;
      controller.abort();
      if (pdfBlobUrlRef.current) {
        URL.revokeObjectURL(pdfBlobUrlRef.current);
        pdfBlobUrlRef.current = null;
      }
      if (aiAbortControllerRef.current) {
        aiAbortControllerRef.current.abort();
      }
    };
  }, [documentId]);

  // 2. Handler Toggle AI
  const handleToggleAi = useCallback(async () => {
    if (loading || !data) return;

    // Jika sedang aktif, nonaktifkan (kembali ke Deterministik seketika)
    if (aiEnabled) {
      setAiEnabled(false);
      return;
    }

    // Jika sudah ada cache hasil AI di memori, aktifkan langsung tanpa request ulang
    if (aiData) {
      setAiEnabled(true);
      return;
    }

    // Pemicu pengerjaan AI via backend job
    setAiLoading(true);
    setAiError(null);
    setAiSecondsElapsed(0);

    const controller = new AbortController();
    aiAbortControllerRef.current = controller;

    try {
      const result = await getMlAnalisaViaJob(
        documentId,
        'ai',
        false,
        controller.signal,
        (detik) => setAiSecondsElapsed(detik)
      );

      setAiData(result);
      setAiEnabled(true);
      setAiLoading(false);
    } catch (err: unknown) {
      if (controller.signal.aborted) {
        setAiLoading(false);
        return;
      }
      setAiLoading(false);
      const msg = err instanceof Error ? err.message : 'Gagal menjalankan pemrosesan narasi AI.';
      setAiError(msg);
      // Tetap pada mode deterministik bila AI gagal
      setAiEnabled(false);
    }
  }, [aiData, aiEnabled, data, documentId, loading]);

  // 3. Handler Resize Divider (Desktop)
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const newWidth = ((e.clientX - rect.left) / rect.width) * 100;
      if (newWidth >= 35 && newWidth <= 65) {
        setLeftWidthPercent(Math.round(newWidth));
      }
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

  // Timer untuk reset highlight pasal target
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Bersihkan timer saat unmount
  useEffect(() => {
    return () => {
      if (highlightTimerRef.current) {
        clearTimeout(highlightTimerRef.current);
      }
    };
  }, []);

  // 4. Lompat ke Pasal Tertentu di Panel Kiri dengan Smooth Scroll & Highlight
  const handleJumpToPasal = useCallback((pasalStr: string) => {
    // Alihkan otomatis tab mobile ke naskah jika sedang di layar kecil
    setMobileActiveTab('naskah');
    // Alihkan otomatis ke mode teks agar pasal dapat disorot
    setViewMode('teks');
    setActivePasalRef(pasalStr);

    if (highlightTimerRef.current) {
      clearTimeout(highlightTimerRef.current);
    }
    // Highlight aktif selama 4.5 detik
    highlightTimerRef.current = setTimeout(() => {
      setActivePasalRef(null);
    }, 4500);

    // Cari elemen pasal berdasarkan parsePasalRef
    const parsedTarget = parsePasalRef(pasalStr);
    const targetNum = parsedTarget.pasalNum?.toLowerCase();

    // Beri sedikit jeda agar DOM ter-mount bila ada peralihan view
    setTimeout(() => {
      let targetElement: HTMLElement | null = null;
      if (targetNum) {
        for (const [key, el] of Object.entries(articleRefs.current)) {
          if (el && parsePasalRef(key).pasalNum?.toLowerCase() === targetNum) {
            targetElement = el;
            break;
          }
        }
      }

      if (!targetElement && targetNum) {
        targetElement = document.querySelector(`[data-pasal-num="${targetNum}"]`) as HTMLElement;
      }

      if (targetElement) {
        targetElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 120);
  }, []);

  // Data aktif yang ditampilkan (AI bila diaktifkan dan tersedia, atau Deterministik)
  const activeData: MlAnalisaResponse | null = aiEnabled && aiData ? aiData : data;
  const isAiActive = aiEnabled && Boolean(aiData?.mode_dipakai === 'ai');

  // Hitung jumlah kata ringkasan yang sedang tampil (sinkron antara Deterministik dan AI)
  const displayedWordCount = useMemo(() => {
    const countWords = (str: string | null | undefined): number => {
      if (!str) return 0;
      return str.trim().split(/\s+/).filter(Boolean).length;
    };

    if (isAiActive) {
      const aiSentences = normalisasiRingkasanAi(activeData?.ringkasan_ai ?? activeData?.ai?.ringkasan);
      const aiText = aiSentences.map((s) => s.kalimat).join(' ');
      if (aiText.trim()) return countWords(aiText);
      if (typeof activeData?.metrik?.kata_ringkasan === 'number' && activeData.metrik.kata_ringkasan > 0) {
        return activeData.metrik.kata_ringkasan;
      }
      return 0;
    }

    // Mode Deterministik
    const detSentences = Array.isArray(activeData?.ringkasan)
      ? activeData.ringkasan.map((s) => s.kalimat).join(' ')
      : '';
    const detText = detSentences || activeData?.ringkasan_teks || '';
    if (detText.trim()) return countWords(detText);
    if (typeof activeData?.metrik?.kata_ringkasan === 'number' && activeData.metrik.kata_ringkasan > 0) {
      return activeData.metrik.kata_ringkasan;
    }
    return 0;
  }, [isAiActive, activeData]);

  // Daftar poin utama
  const poinUtama: MlAnalisaPoint[] = activeData?.poin_utama || [];

  // Dokumen tanpa pasal yang dapat dikenali (mis. Keputusan dengan diktum):
  // semua rujukan bertanda "pasal tidak terbaca". Ringkasan bisa tidak lengkap.
  const semuaRujukan: string[] = [
    ...(activeData?.ringkasan || []).flatMap((k) => k.rujukan || []),
    ...poinUtama.map((p) => p.pasal).filter((x): x is string => Boolean(x)),
  ];
  const dokumenTanpaPasal = semuaRujukan.length > 0 && semuaRujukan.every(isNoPasalRef);

  return (
    <div className="max-w-[1600px] mx-auto space-y-4 font-sans pb-12">
      {/* 1. Header Bar: Breadcrumb, Info Dokumen, & Tombol Tahap */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200/80 p-4 sm:p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-1.5 text-xs font-semibold tracking-wider text-gray-500 uppercase flex-wrap">
            <Link
              to="/"
              className="hover:text-red-700 transition cursor-pointer hover:underline"
              title="Kembali ke Dashboard Utama"
            >
              Dashboard
            </Link>
            <ChevronRight size={12} className="text-gray-400 shrink-0" />
            <button
              type="button"
              onClick={onBackToState1}
              className="hover:text-red-700 transition cursor-pointer hover:underline uppercase"
              title="Kembali ke formulir upload dan daftar draft regulasi"
            >
              Analisa Regulasi
            </button>
            <ChevronRight size={12} className="text-gray-400 shrink-0" />
            <span className="text-red-700 font-bold uppercase">Summary</span>
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-lg sm:text-xl font-bold text-gray-900 truncate" title={docStatus?.title || data?.identitas?.title || 'Draf Regulasi'}>
              {docStatus?.title || data?.identitas?.title || 'Draf Regulasi'}
            </h1>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-red-50 text-red-700 border border-red-200">
              Dokumen #{documentId}
            </span>
            {docStatus?.regulation_number && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-700 border border-gray-200">
                {docStatus.regulation_number}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500">
            Tahap awal penelaahan naskah: Ringkasan Eksekutif dan Key Takeaways dokumen mandiri sebelum komparasi Knowledge Base.
          </p>
        </div>

        {/* Tombol Aksi Cepat Header */}
        <div className="flex items-center gap-2.5 shrink-0">
          <button
            type="button"
            onClick={onBackToState1}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-white hover:bg-gray-50 text-gray-700 border border-gray-300 shadow-2xs hover:border-gray-400 transition-colors cursor-pointer"
            title="Ganti dokumen draft regulasi"
          >
            <ArrowLeft size={13} className="text-gray-600" />
            <span>Ganti Dokumen</span>
          </button>

          <button
            type="button"
            onClick={onProceedToAnalisa}
            disabled={loading || !data}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-lg text-xs font-bold bg-red-800 hover:bg-red-900 disabled:bg-gray-300 disabled:cursor-not-allowed text-white shadow-xs transition-colors cursor-pointer"
          >
            <span>Lanjutkan Analisa</span>
            <ArrowRight size={14} />
          </button>
        </div>
      </div>

      {/* 2. Switcher Tab Mobile / Tablet (< 1024px) */}
      <div className="flex lg:hidden bg-gray-100 p-1 rounded-xl border border-gray-200 text-xs font-semibold">
        <button
          type="button"
          onClick={() => setMobileActiveTab('naskah')}
          className={`flex-1 py-2 rounded-lg flex items-center justify-center gap-2 transition cursor-pointer ${
            mobileActiveTab === 'naskah' ? 'bg-white text-gray-900 shadow-xs' : 'text-gray-600 hover:text-gray-900'
          }`}
        >
          <FileText size={15} />
          <span>Naskah Regulasi</span>
        </button>
        <button
          type="button"
          onClick={() => setMobileActiveTab('summary')}
          className={`flex-1 py-2 rounded-lg flex items-center justify-center gap-2 transition cursor-pointer ${
            mobileActiveTab === 'summary' ? 'bg-white text-gray-900 shadow-xs' : 'text-gray-600 hover:text-gray-900'
          }`}
        >
          <Sparkles size={15} className="text-red-700" />
          <span>Hasil Summary</span>
        </button>
      </div>

      {/* 3. Area Utama Dua Panel (Resizable Desktop) */}
      <div
        ref={containerRef}
        className="relative flex flex-col lg:flex-row gap-0 bg-white rounded-xl shadow-xs border border-gray-200 overflow-hidden min-h-[680px]"
      >
        {/* ============================================================== */}
        {/* PANEL KIRI: NASKAH REGULASI (~52%)                             */}
        {/* ============================================================== */}
        <div
          style={{ width: typeof window !== 'undefined' && window.innerWidth >= 1024 ? `${leftWidthPercent}%` : '100%' }}
          className={`flex flex-col border-b lg:border-b-0 lg:border-r border-gray-200 bg-gray-50/40 min-w-0 ${
            mobileActiveTab !== 'naskah' ? 'hidden lg:flex' : 'flex'
          }`}
        >
          {/* Header Panel Kiri: Switcher Naskah Teks vs PDF Asli */}
          <div className="p-3.5 sm:p-4 bg-white border-b border-gray-200 flex items-center justify-between gap-3 shrink-0">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="p-1.5 bg-red-50 text-red-700 rounded-lg shrink-0">
                <FileText size={16} />
              </div>
              <div className="min-w-0">
                <h2 className="text-xs sm:text-sm font-bold text-gray-900 truncate">Naskah Regulasi</h2>
                <p className="text-[11px] text-gray-500 truncate">
                  {docStatus?.articles?.length ? `${docStatus.articles.length} Pasal Terindeks` : 'Naskah draf regulasi'}
                </p>
              </div>
            </div>

            {/* Switcher Teks vs PDF */}
            <div className="flex items-center gap-1.5 bg-gray-100 p-1 rounded-lg border border-gray-200 text-xs shrink-0">
              <button
                type="button"
                onClick={() => setViewMode('teks')}
                className={`px-3 py-1 rounded-md font-semibold transition cursor-pointer ${
                  viewMode === 'teks' ? 'bg-white text-gray-900 shadow-2xs' : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Naskah Teks
              </button>
              <button
                type="button"
                onClick={() => setViewMode('pdf')}
                className={`px-3 py-1 rounded-md font-semibold transition cursor-pointer ${
                  viewMode === 'pdf' ? 'bg-white text-gray-900 shadow-2xs' : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Berkas PDF
              </button>

              {pdfBlobUrl && viewMode === 'pdf' && (
                <a
                  href={pdfBlobUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-1 text-gray-500 hover:text-red-700 rounded transition"
                  title="Buka PDF di jendela baru"
                >
                  <ExternalLink size={13} />
                </a>
              )}
            </div>
          </div>

          {/* Isi Naskah Panel Kiri */}
          <div className="flex-1 p-4 sm:p-6 overflow-y-auto max-h-[720px] select-text">
            {loading ? (
              <div className="py-20 flex flex-col items-center justify-center text-center">
                <RefreshCw size={24} className="animate-spin text-red-700 mb-3" />
                <p className="text-xs text-gray-600 font-medium">Memuat naskah regulasi...</p>
              </div>
            ) : viewMode === 'pdf' ? (
              // Tampilan PDF Asli
              pdfLoading ? (
                <div className="py-20 flex flex-col items-center justify-center text-center">
                  <RefreshCw size={24} className="animate-spin text-red-700 mb-3" />
                  <p className="text-xs text-gray-600 font-medium">Memuat berkas PDF asli...</p>
                </div>
              ) : pdfBlobUrl ? (
                <div className="w-full h-full min-h-[580px] rounded-lg overflow-hidden border border-gray-200 bg-white">
                  <iframe
                    src={pdfBlobUrl}
                    title="Naskah PDF Asli"
                    className="w-full h-full min-h-[580px] border-0"
                  />
                </div>
              ) : (
                <div className="p-8 text-center bg-white rounded-xl border border-gray-200">
                  <AlertCircle size={28} className="text-amber-600 mx-auto mb-2" />
                  <p className="text-xs font-semibold text-gray-800">{pdfError || 'Berkas PDF tidak dapat dimuat'}</p>
                  <p className="text-[11px] text-gray-500 mt-1">Gunakan tampilan Naskah Teks untuk membaca pasal-pasal.</p>
                </div>
              )
            ) : (
              // Tampilan Naskah Teks Terstruktur (Pasal-pasal)
              <div className="space-y-4">
                {docStatus?.articles && docStatus.articles.length > 0 ? (
                  docStatus.articles.map((art) => {
                    const parsedArt = parsePasalRef(art.article_number);
                    const artPasalNum = parsedArt.pasalNum?.toLowerCase() || null;
                    const parsedTarget = activePasalRef ? parsePasalRef(activePasalRef) : null;
                    const targetPasalNum = parsedTarget?.pasalNum?.toLowerCase() || null;
                    const isTarget = Boolean(targetPasalNum && artPasalNum && targetPasalNum === artPasalNum);

                    return (
                      <div
                        key={art.id || art.article_number}
                        data-pasal-num={artPasalNum || undefined}
                        ref={(el) => {
                          articleRefs.current[art.article_number] = el;
                        }}
                        className={`p-4 rounded-xl border transition-all duration-300 ${
                          isTarget
                            ? 'bg-amber-50/95 border-amber-400 ring-4 ring-amber-300/60 shadow-md scale-[1.01]'
                            : 'bg-white border-gray-200 hover:border-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 mb-2 pb-1.5 border-b border-gray-100">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-bold text-red-700">
                              {art.article_number}
                            </span>
                            {isTarget && (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-200 text-amber-900 animate-pulse">
                                Target Rujukan
                              </span>
                            )}
                          </div>
                          {art.chapter_title && (
                            <span className="text-[10px] font-medium text-gray-500 uppercase tracking-wider truncate max-w-[240px]">
                              {art.chapter_title}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-gray-800 leading-relaxed font-serif whitespace-pre-line">
                          {art.content_text}
                        </p>
                      </div>
                    );
                  })
                ) : docText?.text ? (
                  <div className="p-4 bg-white rounded-xl border border-gray-200 text-xs font-mono text-gray-800 leading-relaxed whitespace-pre-wrap">
                    {docText.text}
                  </div>
                ) : (
                  <div className="p-8 text-center bg-white rounded-xl border border-gray-200 text-xs text-gray-500">
                    Teks naskah belum tersedia atau sedang diekstraksi.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ============================================================== */}
        {/* RESIZE DIVIDER (DESKTOP)                                       */}
        {/* ============================================================== */}
        <div
          onMouseDown={handleMouseDown}
          className="hidden lg:flex items-center justify-center w-1.5 bg-gray-200 hover:bg-red-500 transition-colors cursor-col-resize select-none shrink-0"
          title="Geser untuk mengatur lebar panel"
        >
          <div className="w-0.5 h-8 bg-gray-400 rounded-full" />
        </div>

        {/* ============================================================== */}
        {/* PANEL KANAN: HASIL SUMMARY (~48%)                              */}
        {/* ============================================================== */}
        <div
          style={{ width: typeof window !== 'undefined' && window.innerWidth >= 1024 ? `${100 - leftWidthPercent}%` : '100%' }}
          className={`flex flex-col bg-white min-w-0 ${
            mobileActiveTab !== 'summary' ? 'hidden lg:flex' : 'flex'
          }`}
        >
          {/* Header Panel Kanan: Judul & Toggle AI */}
          <div className="p-3.5 sm:p-4 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-gray-50/50 shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <div className="p-1.5 bg-red-100 text-red-800 rounded-lg shrink-0">
                <Sparkles size={16} />
              </div>
              <div className="min-w-0">
                <h2 className="text-xs sm:text-sm font-bold text-gray-900 truncate">Ringkasan & Key Takeaways</h2>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold ${
                    isAiActive
                      ? 'bg-purple-100 text-purple-800 border border-purple-200'
                      : 'bg-blue-100 text-blue-800 border border-blue-200'
                  }`}>
                    {isAiActive ? 'Mode AI Aktif' : 'Mode Deterministik'}
                  </span>
                  {displayedWordCount > 0 && (
                    <span className="text-[10px] text-gray-500 font-medium">
                      • {displayedWordCount} kata
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* TOGGLE SWITCH AI */}
            {(() => {
              const isAiAvailable = mlHealth?.mode_ai === true;
              return (
                <div className="flex items-center gap-2.5 self-start sm:self-auto bg-white px-3 py-1.5 rounded-xl border border-gray-200 shadow-2xs">
                  <div className="flex flex-col text-right">
                    <span className="text-[11px] font-bold text-gray-800 leading-tight">Analisis AI</span>
                    <span className="text-[9px] text-gray-500">
                      {!isAiAvailable
                        ? 'Tidak Tersedia'
                        : aiLoading
                        ? `Memproses (${aiSecondsElapsed}s)`
                        : aiEnabled
                        ? 'Aktif'
                        : 'Nonaktif'}
                    </span>
                  </div>

                  <button
                    type="button"
                    role="switch"
                    aria-checked={aiEnabled}
                    disabled={loading || aiLoading || !isAiAvailable}
                    onClick={handleToggleAi}
                    className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200 focus:outline-hidden disabled:opacity-50 cursor-pointer ${
                      aiEnabled ? 'bg-red-700' : 'bg-gray-300'
                    }`}
                    title={
                      !isAiAvailable
                        ? 'Layanan model AI tidak tersedia atau sedang dinonaktifkan di peladen.'
                        : aiEnabled
                        ? 'Matikan mode AI (kembali ke Deterministik)'
                        : 'Aktifkan narasi AI (Gemini)'
                    }
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-200 shadow-sm ${
                        aiEnabled ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
              );
            })()}
          </div>

          {/* Banner Peringatan Galat AI (Jika AI gagal, fallback ke Deterministik) */}
          {aiError && (
            <div className="m-4 mb-0 p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900 flex items-start gap-2">
              <AlertCircle size={15} className="text-amber-700 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold">Layanan AI Belum Siap: </span>
                <span>{aiError} Menampilkan hasil analisis Deterministik.</span>
              </div>
            </div>
          )}

          {/* Loading State AI Indicator */}
          {aiLoading && (
            <div className="m-4 mb-0 p-3 bg-red-50/70 border border-red-200 rounded-xl flex items-center gap-3 animate-pulse">
              <RefreshCw size={16} className="text-red-700 animate-spin shrink-0" />
              <div className="text-xs text-red-900">
                <p className="font-semibold">Menyusun Narasi Eksekutif berbasis AI...</p>
                <p className="text-[11px] text-red-700 mt-0.5">Memproses parafrase dan intisari draf ({aiSecondsElapsed} detik berjalan).</p>
              </div>
            </div>
          )}

          {/* Catatan: dokumen tanpa pasal yang dapat dikenali */}
          {!loading && !error && dokumenTanpaPasal && (
            <div className="m-4 mb-0 p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900 flex items-start gap-2">
              <AlertCircle size={15} className="text-amber-700 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold">Dokumen ini tidak memiliki pasal yang dapat dikenali. </span>
                <span>
                  Ringkasan disusun dari kalimat dokumen dan mungkin belum mencakup seluruh isi
                  (mis. dokumen berbentuk Keputusan). Mohon periksa langsung pada tab Naskah.
                </span>
              </div>
            </div>
          )}

          {/* Body Panel Kanan */}
          <div className="flex-1 p-4 sm:p-6 overflow-y-auto max-h-[720px] space-y-6">
            {loading ? (
              <div className="py-24 flex flex-col items-center justify-center text-center">
                <RefreshCw size={26} className="animate-spin text-red-700 mb-3" />
                <p className="text-xs text-gray-700 font-semibold">Menghitung Ringkasan Deterministik Dokumen...</p>
                <p className="text-[11px] text-gray-500 mt-1">Menganalisis norma, kewajiban, dan sanksi dari naskah regulasi.</p>
              </div>
            ) : error ? (
              <div className="p-6 text-center bg-red-50 rounded-xl border border-red-200">
                <AlertCircle size={28} className="text-red-700 mx-auto mb-2" />
                <p className="text-xs font-bold text-red-900">Gagal Memuat Summary</p>
                <p className="text-xs text-red-700 mt-1">{error}</p>
              </div>
            ) : (
              <>
                {/* -------------------------------------------------------- */}
                {/* 1. SECTION: RINGKASAN EKSEKUTIF                          */}
                {/* -------------------------------------------------------- */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between pb-2 border-b border-gray-100">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-red-700" />
                      <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                        Ringkasan Eksekutif
                      </h3>
                    </div>

                    {isAiActive && (
                      <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-purple-700 bg-purple-50 px-2 py-0.5 rounded border border-purple-200">
                        <Sparkles size={11} />
                        Narasi AI Terverifikasi
                      </span>
                    )}
                  </div>

                  {/* Narasi Ringkasan AI (bila AI aktif) atau Ringkasan Deterministik */}
                  {isAiActive && activeData?.ringkasan_ai ? (
                    <RingkasanAiPanel
                      ai={activeData.ai}
                      ringkasanAi={activeData.ringkasan_ai}
                      modeDipakai="ai"
                      onJumpToPasal={handleJumpToPasal}
                    />
                  ) : activeData?.ringkasan && activeData.ringkasan.length > 0 ? (
                    <div className="bg-gray-50/80 rounded-xl p-4 border border-gray-200/80 space-y-2.5">
                      {activeData.ringkasan.map((sentence, sIdx) => (
                        <div key={sIdx} className="space-y-1">
                          <p className="text-xs text-gray-800 leading-relaxed font-serif">
                            {sentence.kalimat}
                          </p>
                          {sentence.rujukan && sentence.rujukan.length > 0 && (
                            <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                              <span className="text-[10px] font-medium text-gray-500">Rujukan:</span>
                              {sentence.rujukan.map((refStr, rIdx) => (
                                <RujukanChip key={rIdx} refStr={refStr} onJump={handleJumpToPasal} />
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : activeData?.ringkasan_teks ? (
                    <div className="bg-gray-50/80 rounded-xl p-4 border border-gray-200 text-xs text-gray-800 leading-relaxed font-serif whitespace-pre-line">
                      {activeData.ringkasan_teks}
                    </div>
                  ) : (
                    <div className="p-4 bg-gray-50 rounded-xl border border-gray-200 text-xs text-gray-500 text-center">
                      Ringkasan eksekutif belum tersedia untuk dokumen ini.
                    </div>
                  )}

                  {/* Subjek yang Diatur */}
                  {activeData?.subjek_diatur && activeData.subjek_diatur.length > 0 && (
                    <div className="pt-2">
                      <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block mb-1.5">
                        Subjek yang Diatur
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {activeData.subjek_diatur.map((subj, idx) => {
                          const label = typeof subj === 'string' ? subj : subj.subjek;
                          const count = typeof subj === 'object' && subj ? subj.jumlah : null;
                          return (
                            <span
                              key={idx}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-gray-100 text-gray-700 border border-gray-200"
                            >
                              <span>{label}</span>
                              {count !== null && (
                                <span className="text-[10px] bg-gray-200 text-gray-600 px-1 rounded-full font-mono">
                                  {count}
                                </span>
                              )}
                            </span>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>

                {/* -------------------------------------------------------- */}
                {/* 2. SECTION: KEY TAKEAWAYS (POIN KUNCI)                   */}
                {/* -------------------------------------------------------- */}
                <div className="space-y-3 pt-2">
                  <div className="flex items-center justify-between pb-2 border-b border-gray-100">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-blue-600" />
                      <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                        Key Takeaways
                      </h3>
                    </div>
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-gray-100 text-gray-700 border border-gray-200">
                      {poinUtama.length} Poin Kunci
                    </span>
                  </div>

                  {poinUtama.length > 0 ? (
                    <div className="space-y-2.5">
                      {poinUtama.map((point, pIdx) => {
                        const kat = (point.kategori || 'umum').toLowerCase();
                        const isKewajiban = kat.includes('kewajiban');
                        const isLarangan = kat.includes('larangan');
                        const isSanksi = kat.includes('sanksi');
                        const isHak = kat.includes('hak');

                        const badgeColor = isKewajiban
                          ? 'bg-blue-50 text-blue-800 border-blue-200'
                          : isLarangan
                          ? 'bg-rose-50 text-rose-800 border-rose-200'
                          : isSanksi
                          ? 'bg-amber-50 text-amber-800 border-amber-200'
                          : isHak
                          ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                          : 'bg-gray-100 text-gray-700 border-gray-200';

                        const displayText = isAiActive && point.parafrase ? point.parafrase : point.teks || point.poin || '-';

                        return (
                          <div
                            key={point.id || pIdx}
                            className="p-3.5 bg-gray-50/60 hover:bg-gray-50 border border-gray-200 rounded-xl transition duration-150 space-y-1.5"
                          >
                            <div className="flex items-center justify-between gap-2 flex-wrap">
                              <div className="flex items-center gap-1.5">
                                <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold border ${badgeColor}`}>
                                  {point.kategori || 'Norma'}
                                </span>
                                {point.urgensi && (
                                  <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                                    • Urgensi: {point.urgensi}
                                  </span>
                                )}
                              </div>

                              {point.pasal && (
                                <RujukanChip
                                  refStr={point.pasal}
                                  onJump={handleJumpToPasal}
                                  iconSize={10}
                                  title={`Lihat teks di ${point.pasal}`}
                                />
                              )}
                            </div>

                            <p className="text-xs text-gray-800 leading-relaxed font-serif">
                              {displayText}
                            </p>

                            {isAiActive && point.parafrase && point.parafrase !== point.teks && (
                              <div className="flex items-center gap-1 text-[10px] text-purple-700 font-medium pt-0.5">
                                <Sparkles size={10} />
                                <span>Diparafrase oleh AI</span>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="p-4 bg-gray-50 rounded-xl border border-gray-200 text-xs text-gray-500 text-center">
                      Belum ada poin kunci yang teridentifikasi.
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
