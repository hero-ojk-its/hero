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
import {
  FileText,
  Sparkles,
  ArrowRight,
  ArrowLeft,
  ExternalLink,
  RefreshCw,
  AlertCircle,
  PanelLeftClose,
  PanelLeftOpen,
  BookOpen,
  X,
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
import AnalisaBreadcrumb from './AnalisaBreadcrumb';

/**
 * Rujukan yang tidak menunjuk ke Pasal tertentu, mis. dokumen berbentuk
 * Keputusan (diktum KESATU, KEDUA, ...) yang diberi label
 * "Teks dokumen (pasal tidak terbaca)" oleh mesin analisis.
 */
const isNoPasalRef = (ref: string): boolean => /pasal\s+tidak\s+terbaca/i.test(ref);

export interface DetailPasalModalState {
  refStr: string;
  articleNumber: string;
  chapterTitle?: string | null;
  contentText: string;
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

  // Layout Resizable (Desktop) & Toggle Tampilan Panel Naskah
  const [showNaskahPanel, setShowNaskahPanel] = useState<boolean>(false);
  const [leftWidthPercent, setLeftWidthPercent] = useState<number>(50);
  const [isResizing, setIsResizing] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Deteksi layar desktop (>= 1024px) untuk animasi collapse/expand naskah secara smooth
  const [isDesktop, setIsDesktop] = useState<boolean>(() =>
    typeof window !== 'undefined' ? window.innerWidth >= 1024 : true
  );

  useEffect(() => {
    const handleResize = () => {
      setIsDesktop(window.innerWidth >= 1024);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Layout Responsif (Mobile / Tablet < 1024px)
  const [mobileActiveTab, setMobileActiveTab] = useState<'naskah' | 'summary'>('summary');

  // State Modal Detail Pasal
  const [pasalModal, setPasalModal] = useState<DetailPasalModalState | null>(null);

  // State Filter Kategori Key Takeaways
  const [selectedCategory, setSelectedCategory] = useState<string>('Semua');

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

  // 5. Handler Membuka Modal Detail Pasal dari Key Takeaways
  const handleOpenPasalModal = useCallback((pasalStr: string) => {
    if (!pasalStr) return;

    if (isNoPasalRef(pasalStr)) {
      setPasalModal({
        refStr: pasalStr,
        articleNumber: 'Rujukan Umum',
        chapterTitle: 'Ketentuan Regulasi',
        contentText:
          'Poin ini merujuk pada ketentuan umum dokumen (tidak secara spesifik terikat pada satu nomor pasal, misalnya pada dokumen berbentuk Keputusan atau Diktum). Silakan periksa naskah regulasi untuk membaca bagian terkait.',
      });
      return;
    }

    const parsedTarget = parsePasalRef(pasalStr);
    const targetNum = parsedTarget.pasalNum?.toLowerCase();

    // Cari pada daftar pasal terstruktur
    const matchedArticle = docStatus?.articles?.find((art) => {
      if (!art.article_number) return false;
      if (art.article_number.trim().toLowerCase() === pasalStr.trim().toLowerCase()) return true;
      const parsedArt = parsePasalRef(art.article_number);
      return Boolean(targetNum && parsedArt.pasalNum?.toLowerCase() === targetNum);
    });

    if (matchedArticle) {
      setPasalModal({
        refStr: pasalStr,
        articleNumber: matchedArticle.article_number,
        chapterTitle: matchedArticle.chapter_title,
        contentText: matchedArticle.content_text,
      });
      return;
    }

    // Jika tidak ditemukan dalam articles terstruktur, cari potongan di docText
    if (docText?.text && targetNum) {
      const regex = new RegExp(`(?:Pasal|PASAL)\\s+${targetNum}\\b([\\s\\S]*?)(?=(?:Pasal|PASAL)\\s+[0-9]+|$)`, 'i');
      const match = docText.text.match(regex);
      if (match && match[0]) {
        setPasalModal({
          refStr: pasalStr,
          articleNumber: `Pasal ${parsedTarget.pasalNum}`,
          chapterTitle: 'Hasil Ekstraksi Teks',
          contentText: match[0].trim(),
        });
        return;
      }
    }

    // Fallback jika teks belum terindeks penuh
    setPasalModal({
      refStr: pasalStr,
      articleNumber: pasalStr,
      chapterTitle: 'Rujukan Naskah Regulasi',
      contentText:
        'Teks lengkap untuk pasal ini belum dapat dimuat secara terpisah. Anda dapat membuka naskah lengkap melalui tombol di bawah untuk menelusuri isi dokumen.',
    });
  }, [docStatus?.articles, docText]);

  // Handler Buka di Naskah Lengkap dari Modal
  const handleViewInNaskahFromModal = useCallback(() => {
    if (!pasalModal) return;
    const targetRef = pasalModal.refStr;
    setPasalModal(null);
    setShowNaskahPanel(true);
    setTimeout(() => {
      handleJumpToPasal(targetRef);
    }, 120);
  }, [handleJumpToPasal, pasalModal]);

  // Keyboard shortcut: Escape untuk menutup modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && pasalModal) {
        setPasalModal(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [pasalModal]);

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

  // Helper membersihkan rujukan pasal teknis dari narasi Ringkasan Eksekutif
  const cleanPasalRefs = (text: string): string => {
    if (!text) return '';
    return text
      .replace(/\s*\((?:lihat\s+)?(?:pasal|ps\.)\s+[0-9a-zA-Z\s,–\-\(\)]+\)/gi, '')
      .replace(/\s*\[(?:lihat\s+)?(?:pasal|ps\.)\s+[0-9a-zA-Z\s,–\-\(\)]+\]/gi, '')
      .replace(/(?:sebagaimana\s+dimaksud\s+(?:dalam|pada)\s+)?(?:pasal|ps\.)\s+[0-9]+(?:\s+ayat\s+\([0-9]+\))?/gi, 'ketentuan yang berlaku')
      .replace(/\s{2,}/g, ' ')
      .trim();
  };

  // Ekstraksi data terstruktur untuk Ringkasan Eksekutif (8 Kelompok Informasi Berurutan)
  const structuredSummary = useMemo(() => {
    if (!activeData && !docStatus) return null;

    // 1. Identitas Dokumen
    const namaJudul = docStatus?.title || activeData?.identitas?.title || activeData?.identitas?.tentang || null;
    const nomorReg = docStatus?.regulation_number || activeData?.identitas?.nomor || activeData?.identitas?.number || null;
    const tahunReg = docStatus?.regulation_year || activeData?.identitas?.tahun || activeData?.identitas?.year || null;
    const jenisReg = docStatus?.regulation_type || activeData?.identitas?.jenis || activeData?.identitas?.doc_type || null;
    let statusKeberlakuan: string | null = null;
    const rawStatus = docStatus?.status_keberlakuan || activeData?.identitas?.status;
    if (rawStatus) {
      if (rawStatus === 'belum_berlaku') statusKeberlakuan = 'Belum Berlaku';
      else if (rawStatus === 'berlaku') statusKeberlakuan = 'Berlaku';
      else if (rawStatus === 'dicabut') statusKeberlakuan = 'Dicabut';
      else statusKeberlakuan = rawStatus.charAt(0).toUpperCase() + rawStatus.slice(1).replace(/_/g, ' ');
    }
    const hasIdentitas = Boolean(namaJudul || nomorReg);

    // 2. Kerangka Regulasi
    const jumlahBab = activeData?.metrik?.jumlah_bab || (activeData?.kerangka && activeData.kerangka.length > 0 ? activeData.kerangka.length : null) || null;
    const jumlahPasal = activeData?.metrik?.jumlah_pasal || docStatus?.articles?.length || activeData?.identitas?.jumlah_pasal || null;
    const babList = activeData?.kerangka?.map((k) => `${k.bab}: ${k.judul}`).filter(Boolean) || [];
    let cakupanUmum: string | null = null;
    if (activeData?.ringkasan && activeData.ringkasan.length > 0) {
      cakupanUmum = cleanPasalRefs(activeData.ringkasan[0].kalimat);
    } else if (activeData?.ringkasan_teks) {
      cakupanUmum = cleanPasalRefs(activeData.ringkasan_teks.split('\n')[0] || '');
    }
    const hasKerangka = Boolean(jumlahBab || jumlahPasal || babList.length > 0 || cakupanUmum);

    // 3. Pihak yang Diatur
    const subjekList: Array<{ nama: string; jumlah?: number }> = [];
    if (activeData?.subjek_diatur && activeData.subjek_diatur.length > 0) {
      for (const s of activeData.subjek_diatur) {
        if (typeof s === 'string' && s.trim()) {
          subjekList.push({ nama: s.trim() });
        } else if (s && typeof s === 'object' && s.subjek) {
          subjekList.push({ nama: s.subjek.trim(), jumlah: s.jumlah });
        }
      }
    }
    const hasSubjek = subjekList.length > 0;

    // 4. Kewajiban Utama
    const kewajibanItems: string[] = [];
    if (activeData?.poin_utama) {
      for (const p of activeData.poin_utama) {
        const kat = (p.kategori || '').toLowerCase();
        if (kat.includes('kewajiban')) {
          const text = cleanPasalRefs(p.teks || p.poin || '');
          if (text && !kewajibanItems.includes(text)) {
            kewajibanItems.push(text);
          }
        }
      }
    }
    if (kewajibanItems.length === 0 && activeData?.ringkasan) {
      for (const r of activeData.ringkasan) {
        if (/(?:wajib|kewajiban|keharusan)/i.test(r.kalimat)) {
          const text = cleanPasalRefs(r.kalimat);
          if (text && !kewajibanItems.includes(text)) {
            kewajibanItems.push(text);
          }
        }
      }
    }
    const hasKewajiban = kewajibanItems.length > 0;

    // 5. Kewajiban Pelaporan
    const pelaporanItems: string[] = [];
    if (activeData?.poin_utama) {
      for (const p of activeData.poin_utama) {
        const kat = (p.kategori || '').toLowerCase();
        const txt = (p.teks || p.poin || '').toLowerCase();
        if (kat.includes('lapor') || /(?:pelaporan|laporan|melapor|pemberitahuan\s+insiden)/i.test(txt)) {
          const text = cleanPasalRefs(p.teks || p.poin || '');
          if (text && !pelaporanItems.includes(text)) {
            pelaporanItems.push(text);
          }
        }
      }
    }
    if (pelaporanItems.length === 0 && activeData?.ringkasan) {
      for (const r of activeData.ringkasan) {
        if (/(?:laporan|pelaporan|melaporkan|pemberitahuan\s+insiden)/i.test(r.kalimat)) {
          const text = cleanPasalRefs(r.kalimat);
          if (text && !pelaporanItems.includes(text)) {
            pelaporanItems.push(text);
          }
        }
      }
    }
    const hasPelaporan = pelaporanItems.length > 0;

    // 6. Sanksi
    const sanksiItems: string[] = [];
    if (Array.isArray(activeData?.sanksi) && activeData.sanksi.length > 0) {
      for (const s of activeData.sanksi) {
        const text = cleanPasalRefs(typeof s === 'string' ? s : JSON.stringify(s));
        if (text && !sanksiItems.includes(text)) {
          sanksiItems.push(text);
        }
      }
    }
    if (activeData?.poin_utama) {
      for (const p of activeData.poin_utama) {
        const kat = (p.kategori || '').toLowerCase();
        const txt = (p.teks || p.poin || '').toLowerCase();
        if (kat.includes('sanksi') || /(?:sanksi|denda|peringatan\s+tertulis|pembatasan\s+kegiatan)/i.test(txt)) {
          const text = cleanPasalRefs(p.teks || p.poin || '');
          if (text && !sanksiItems.includes(text)) {
            sanksiItems.push(text);
          }
        }
      }
    }
    if (sanksiItems.length === 0 && activeData?.ringkasan) {
      for (const r of activeData.ringkasan) {
        if (/(?:sanksi|denda|hukuman|teguran)/i.test(r.kalimat)) {
          const text = cleanPasalRefs(r.kalimat);
          if (text && !sanksiItems.includes(text)) {
            sanksiItems.push(text);
          }
        }
      }
    }
    const hasSanksi = sanksiItems.length > 0;

    // 7. Pencabutan atau Perubahan Regulasi
    const pencabutanItems: string[] = [];
    if (docStatus?.legal_references) {
      for (const ref of docStatus.legal_references) {
        const cited = ref.cited_text?.toLowerCase() || '';
        if (/(?:cabut|mencabut|tidak\s+berlaku|ubah|mengubah|perubahan)/i.test(cited)) {
          const text = ref.cited_text.trim();
          if (text && !pencabutanItems.includes(text)) {
            pencabutanItems.push(text);
          }
        }
      }
    }
    if (activeData?.poin_utama) {
      for (const p of activeData.poin_utama) {
        const kat = (p.kategori || '').toLowerCase();
        const txt = (p.teks || p.poin || '').toLowerCase();
        if (kat.includes('cabut') || kat.includes('ubah') || /(?:mencabut|dinyatakan\s+tidak\s+berlaku|perubahan\s+atas)/i.test(txt)) {
          const text = cleanPasalRefs(p.teks || p.poin || '');
          if (text && !pencabutanItems.includes(text)) {
            pencabutanItems.push(text);
          }
        }
      }
    }
    const hasPencabutan = pencabutanItems.length > 0;

    // 8. Masa Berlaku
    const masaBerlakuItems: string[] = [];
    if (activeData?.poin_utama) {
      for (const p of activeData.poin_utama) {
        const kat = (p.kategori || '').toLowerCase();
        const txt = (p.teks || p.poin || '').toLowerCase();
        if (kat.includes('masa') || kat.includes('berlaku') || /(?:mulai\s+berlaku|masa\s+transisi|tanggal\s+pengundangan|diundangkan\s+pada)/i.test(txt)) {
          const text = cleanPasalRefs(p.teks || p.poin || '');
          if (text && !masaBerlakuItems.includes(text)) {
            masaBerlakuItems.push(text);
          }
        }
      }
    }
    if (masaBerlakuItems.length === 0 && activeData?.identitas?.tanggal_terbit) {
      masaBerlakuItems.push(`Ditetapkan / diterbitkan pada tanggal ${activeData.identitas.tanggal_terbit}.`);
    }
    const hasMasaBerlaku = masaBerlakuItems.length > 0;

    return {
      identitas: hasIdentitas ? { namaJudul, nomorReg, tahunReg, jenisReg, statusKeberlakuan } : null,
      kerangka: hasKerangka ? { jumlahBab, jumlahPasal, babList, cakupanUmum } : null,
      pihakDiatur: hasSubjek ? subjekList : null,
      kewajiban: hasKewajiban ? kewajibanItems : null,
      pelaporan: hasPelaporan ? pelaporanItems : null,
      sanksi: hasSanksi ? sanksiItems : null,
      pencabutan: hasPencabutan ? pencabutanItems : null,
      masaBerlaku: hasMasaBerlaku ? masaBerlakuItems : null,
    };
  }, [activeData, docStatus]);

  // Ekstraksi laporan terstruktur (Hanya tampilkan bagian yang memiliki data)
  const structuredSections = useMemo(() => {
    if (!structuredSummary) return [];
    const list: Array<{ id: string; title: string; extraHeader?: React.ReactNode; content: React.ReactNode }> = [];

    // 1. Identitas Dokumen
    if (structuredSummary.identitas) {
      const iden = structuredSummary.identitas;
      list.push({
        id: 'identitas',
        title: 'Identitas Dokumen',
        extraHeader: iden.statusKeberlakuan ? (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-gray-200/80 text-gray-700 font-sans">
            {iden.statusKeberlakuan}
          </span>
        ) : undefined,
        content: (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-sans">
            <div className="sm:col-span-2">
              <span className="text-gray-500 font-medium block mb-0.5">Judul Regulasi:</span>
              <span className="text-gray-900 font-semibold text-sm leading-snug block">
                {iden.namaJudul}
              </span>
            </div>
            {iden.nomorReg && (
              <div>
                <span className="text-gray-500 font-medium block mb-0.5">Nomor Regulasi:</span>
                <span className="text-gray-800 font-mono font-medium">
                  {iden.nomorReg}
                </span>
              </div>
            )}
            {iden.tahunReg && (
              <div>
                <span className="text-gray-500 font-medium block mb-0.5">Tahun Regulasi:</span>
                <span className="text-gray-800 font-medium">
                  {iden.tahunReg}
                </span>
              </div>
            )}
            {iden.jenisReg && (
              <div>
                <span className="text-gray-500 font-medium block mb-0.5">Bentuk Regulasi:</span>
                <span className="text-gray-800 font-medium">
                  {iden.jenisReg}
                </span>
              </div>
            )}
          </div>
        ),
      });
    }

    // 2. Kerangka Regulasi
    if (structuredSummary.kerangka) {
      const kr = structuredSummary.kerangka;
      list.push({
        id: 'kerangka',
        title: 'Kerangka Regulasi',
        extraHeader: (
          <div className="flex items-center gap-2 text-xs font-semibold text-gray-700">
            {kr.jumlahBab && (
              <span className="bg-gray-200/70 px-2 py-0.5 rounded">
                {kr.jumlahBab} Bab
              </span>
            )}
            {kr.jumlahPasal && (
              <span className="bg-gray-200/70 px-2 py-0.5 rounded">
                {kr.jumlahPasal} Pasal
              </span>
            )}
          </div>
        ),
        content: (
          <div className="space-y-2.5 font-sans">
            {kr.cakupanUmum && (
              <p className="text-sm text-gray-800 leading-relaxed">
                {kr.cakupanUmum}
              </p>
            )}
            {kr.babList.length > 0 && (
              <div className="pt-1">
                <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider block mb-1.5">
                  Struktur Bab Dokumen:
                </span>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-xs text-gray-700">
                  {kr.babList.map((bab, bIdx) => (
                    <div key={bIdx} className="bg-white/80 border border-gray-200/80 px-2.5 py-1.5 rounded-lg truncate" title={bab}>
                      <span className="font-semibold text-gray-900">{bab}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ),
      });
    }

    // 3. Pihak yang Diatur
    if (structuredSummary.pihakDiatur && structuredSummary.pihakDiatur.length > 0) {
      const phk = structuredSummary.pihakDiatur;
      list.push({
        id: 'pihak_diatur',
        title: 'Pihak yang Diatur',
        content: (
          <div className="flex flex-wrap gap-2 font-sans">
            {phk.map((p, idx) => (
              <span
                key={idx}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white border border-gray-200 text-gray-800 shadow-2xs"
              >
                <span className="font-semibold">{p.nama}</span>
                {p.jumlah !== undefined && p.jumlah !== null && (
                  <span className="text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.2 rounded-full font-mono font-medium">
                    {p.jumlah} ketentuan
                  </span>
                )}
              </span>
            ))}
          </div>
        ),
      });
    }

    // 4. Kewajiban Utama
    if (structuredSummary.kewajiban && structuredSummary.kewajiban.length > 0) {
      const kwj = structuredSummary.kewajiban;
      list.push({
        id: 'kewajiban',
        title: 'Kewajiban Utama',
        content: (
          <ul className="space-y-2 text-sm text-gray-800 leading-relaxed font-sans">
            {kwj.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2.5 bg-white/80 p-3 rounded-lg border border-gray-200/80">
                <span className="w-1.5 h-1.5 rounded-full bg-gray-500 mt-2 shrink-0" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ),
      });
    }

    // 5. Kewajiban Pelaporan
    if (structuredSummary.pelaporan && structuredSummary.pelaporan.length > 0) {
      const pel = structuredSummary.pelaporan;
      list.push({
        id: 'pelaporan',
        title: 'Kewajiban Pelaporan',
        content: (
          <ul className="space-y-2 text-sm text-gray-800 leading-relaxed font-sans">
            {pel.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2.5 bg-white/80 p-3 rounded-lg border border-gray-200/80">
                <span className="w-1.5 h-1.5 rounded-full bg-gray-500 mt-2 shrink-0" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ),
      });
    }

    // 6. Sanksi
    if (structuredSummary.sanksi && structuredSummary.sanksi.length > 0) {
      const snk = structuredSummary.sanksi;
      list.push({
        id: 'sanksi',
        title: 'Sanksi',
        content: (
          <ul className="space-y-2 text-sm text-gray-800 leading-relaxed font-sans">
            {snk.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2.5 bg-white/80 p-3 rounded-lg border border-gray-200/80">
                <span className="w-1.5 h-1.5 rounded-full bg-gray-500 mt-2 shrink-0" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ),
      });
    }

    // 7. Pencabutan atau Perubahan Regulasi
    if (structuredSummary.pencabutan && structuredSummary.pencabutan.length > 0) {
      const pcb = structuredSummary.pencabutan;
      list.push({
        id: 'pencabutan',
        title: 'Pencabutan atau Perubahan Regulasi',
        content: (
          <ul className="space-y-2 text-sm text-gray-800 leading-relaxed font-sans">
            {pcb.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2.5 bg-white/80 p-3 rounded-lg border border-gray-200/80">
                <span className="w-1.5 h-1.5 rounded-full bg-gray-500 mt-2 shrink-0" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ),
      });
    }

    // 8. Masa Berlaku
    if (structuredSummary.masaBerlaku && structuredSummary.masaBerlaku.length > 0) {
      const msb = structuredSummary.masaBerlaku;
      list.push({
        id: 'masa_berlaku',
        title: 'Masa Berlaku',
        content: (
          <ul className="space-y-2 text-sm text-gray-800 leading-relaxed font-sans">
            {msb.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2.5 bg-white/80 p-3 rounded-lg border border-gray-200/80">
                <span className="w-1.5 h-1.5 rounded-full bg-gray-500 mt-2 shrink-0" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ),
      });
    }

    return list;
  }, [structuredSummary]);

  // Perhitungan Kategori Key Takeaways
  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = { Semua: poinUtama.length };
    for (const p of poinUtama) {
      const rawCat = p.kategori?.trim() || 'Norma';
      const formattedCat = rawCat.charAt(0).toUpperCase() + rawCat.slice(1);
      counts[formattedCat] = (counts[formattedCat] || 0) + 1;
    }
    return counts;
  }, [poinUtama]);

  const availableCategories = useMemo(() => {
    const priority = [
      'Semua',
      'Kewajiban',
      'Pelaporan',
      'Larangan',
      'Sanksi',
      'Perizinan',
      'Pencabutan',
      'Masa Berlaku',
      'Hak',
      'Norma',
    ];
    const present = Object.keys(categoryCounts).filter((cat) => categoryCounts[cat] > 0);
    return present.sort((a, b) => {
      const idxA = priority.indexOf(a);
      const idxB = priority.indexOf(b);
      if (idxA !== -1 && idxB !== -1) return idxA - idxB;
      if (idxA !== -1) return -1;
      if (idxB !== -1) return 1;
      return a.localeCompare(b);
    });
  }, [categoryCounts]);

  const filteredPoints = useMemo(() => {
    if (selectedCategory === 'Semua') return poinUtama;
    return poinUtama.filter((p) => {
      const rawCat = p.kategori?.trim() || 'Norma';
      const formattedCat = rawCat.charAt(0).toUpperCase() + rawCat.slice(1);
      return formattedCat.toLowerCase() === selectedCategory.toLowerCase();
    });
  }, [poinUtama, selectedCategory]);

  useEffect(() => {
    if (selectedCategory !== 'Semua' && !availableCategories.includes(selectedCategory)) {
      setSelectedCategory('Semua');
    }
  }, [availableCategories, selectedCategory]);

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
          <AnalisaBreadcrumb stage="summary" onBackToState1={onBackToState1} />

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
        <div className="flex items-center gap-2.5 shrink-0 flex-wrap">
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
        {/* PANEL KIRI: NASKAH REGULASI (~50% atau collapse kanan-ke-kiri) */}
        {/* ============================================================== */}
        <div
          style={{
            width: isDesktop ? (showNaskahPanel ? `${leftWidthPercent}%` : '0%') : '100%',
            opacity: isDesktop ? (showNaskahPanel ? 1 : 0) : 1,
            pointerEvents: isDesktop && !showNaskahPanel ? 'none' : 'auto',
            borderRightWidth: isDesktop && showNaskahPanel ? '1px' : '0px',
          }}
          className={`flex flex-col bg-gray-50/40 min-w-0 overflow-hidden border-gray-200 transition-all duration-300 ease-in-out ${
            mobileActiveTab !== 'naskah' ? 'hidden lg:flex' : 'flex'
          }`}
        >
          <div className="w-full h-full flex flex-col min-w-[360px] lg:min-w-[400px] max-w-full">
            {/* Header Panel Kiri: Switcher Naskah Teks vs PDF Asli */}
            <div className="p-3.5 sm:p-4 bg-white border-b border-gray-200 flex items-center justify-between gap-3 shrink-0">
            <div className="min-w-0">
              <h2 className="text-xs sm:text-sm font-bold text-gray-900 truncate">Naskah Regulasi</h2>
              <p className="text-[11px] text-gray-500 truncate">
                {docStatus?.articles?.length ? `${docStatus.articles.length} Pasal Terindeks` : 'Naskah draf regulasi'}
              </p>
            </div>

            <div className="flex items-center gap-2">
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
                        <p className="text-sm text-gray-800 leading-relaxed font-sans whitespace-pre-line">
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
      </div>

        {/* ============================================================== */}
        {/* RESIZE DIVIDER (DESKTOP)                                       */}
        {/* ============================================================== */}
        {isDesktop && showNaskahPanel && (
          <div
            onMouseDown={handleMouseDown}
            className="hidden lg:flex items-center justify-center w-1.5 bg-gray-200 hover:bg-red-500 transition-colors cursor-col-resize select-none shrink-0"
            title="Geser untuk mengatur lebar panel"
          >
            <div className="w-0.5 h-8 bg-gray-400 rounded-full" />
          </div>
        )}

        {/* ============================================================== */}
        {/* PANEL KANAN: HASIL SUMMARY (Flex-1 mengambil seluruh lebar secara smooth) */}
        {/* ============================================================== */}
        <div
          className={`flex-1 flex flex-col bg-white min-w-0 transition-all duration-300 ease-in-out ${
            mobileActiveTab !== 'summary' ? 'hidden lg:flex' : 'flex'
          }`}
        >
          {/* Header Panel Kanan: Judul & Toggle AI */}
          <div className="p-3.5 sm:p-4 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-gray-50/50 shrink-0">
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

            <div className="flex items-center gap-2.5 self-start sm:self-auto flex-wrap">
              {/* Tombol Tunggal Toggle Naskah Regulasi di samping Toggle AI */}
              <button
                type="button"
                onClick={() => setShowNaskahPanel((prev) => !prev)}
                className="hidden lg:inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-gray-700 hover:text-gray-900 bg-white hover:bg-gray-50 rounded-lg border border-gray-300 shadow-2xs transition-colors cursor-pointer"
                title={showNaskahPanel ? 'Sembunyikan panel naskah regulasi' : 'Tampilkan panel naskah regulasi di sisi kiri'}
              >
                {showNaskahPanel ? (
                  <>
                    <PanelLeftClose size={14} className="text-gray-500" />
                    <span>Sembunyikan Naskah</span>
                  </>
                ) : (
                  <>
                    <PanelLeftOpen size={14} className="text-gray-500" />
                    <span>Tampilkan Naskah</span>
                  </>
                )}
              </button>

              {/* TOGGLE SWITCH AI */}
              {(() => {
                const isAiAvailable = mlHealth?.mode_ai === true;
                return (
                  <div className="flex items-center gap-2.5 bg-white px-3 py-1.5 rounded-xl border border-gray-200 shadow-2xs">
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
                {/* 1. SECTION: RINGKASAN EKSEKUTIF (LAPORAN TERSTRUKTUR)     */}
                {/* -------------------------------------------------------- */}
                <div className="space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-gray-100">
                    <div>
                      <h3 className="text-sm font-bold text-gray-900 tracking-tight">
                        Ringkasan Eksekutif
                      </h3>
                      <p className="text-xs text-gray-500">
                        Intisari dan kerangka regulasi terstruktur berdasarkan ekstraksi naskah.
                      </p>
                    </div>

                    {isAiActive && (
                      <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-purple-700 bg-purple-50 px-2 py-0.5 rounded-full border border-purple-200">
                        <Sparkles size={11} />
                        Narasi AI Terverifikasi
                      </span>
                    )}
                  </div>

                  {/* Narasi Ringkasan AI (bila AI aktif) */}
                  {isAiActive && activeData?.ringkasan_ai && (
                    <RingkasanAiPanel
                      ai={activeData.ai}
                      ringkasanAi={activeData.ringkasan_ai}
                      modeDipakai="ai"
                    />
                  )}

                  {/* Laporan Terstruktur (8 Kelompok Informasi Berurutan) */}
                  {structuredSections.length > 0 ? (
                    <div className="space-y-3.5">
                      {structuredSections.map((sec, idx) => (
                        <div
                          key={sec.id}
                          className="bg-gray-50/70 border border-gray-200/90 rounded-xl p-4 sm:p-5 space-y-3"
                        >
                          <div className="flex items-center justify-between pb-2 border-b border-gray-200/70">
                            <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                              {idx + 1}. {sec.title}
                            </h4>
                            {sec.extraHeader}
                          </div>
                          {sec.content}
                        </div>
                      ))}
                    </div>
                  ) : activeData?.ringkasan_teks ? (
                    <div className="bg-slate-50/70 rounded-xl p-4 sm:p-5 border border-gray-200/90 text-sm font-normal text-gray-700 leading-relaxed font-sans whitespace-pre-line">
                      {activeData.ringkasan_teks}
                    </div>
                  ) : (
                    <div className="p-6 bg-gray-50 rounded-xl border border-gray-200 text-xs text-gray-500 text-center font-sans">
                      Ringkasan eksekutif belum tersedia untuk dokumen ini.
                    </div>
                  )}
                </div>

                {/* -------------------------------------------------------- */}
                {/* 2. SECTION: KEY TAKEAWAYS (FOKUS UTAMA)                  */}
                {/* -------------------------------------------------------- */}
                <div className="space-y-3.5 pt-4">
                  <div className="flex items-center justify-between pb-2.5 border-b border-gray-200">
                    <div>
                      <h3 className="text-base font-bold text-gray-900 tracking-tight">
                        Key Takeaways
                      </h3>
                      <p className="text-xs text-gray-500 mt-0.5">
                        Poin-poin penting, norma, kewajiban, dan sanksi utama yang diatur dalam regulasi ini.
                      </p>
                    </div>
                    <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-gray-100 text-gray-800 border border-gray-200 shadow-2xs">
                      {poinUtama.length} Poin Kunci
                    </span>
                  </div>

                  {/* Filter Kategori Key Takeaways */}
                  {availableCategories.length > 1 && (
                    <div className="flex items-center gap-1.5 overflow-x-auto pb-1.5 pt-0.5 -mx-1 px-1 scrollbar-thin">
                      {availableCategories.map((cat) => {
                        const count = categoryCounts[cat] || 0;
                        const isActive = selectedCategory.toLowerCase() === cat.toLowerCase();
                        return (
                          <button
                            key={cat}
                            type="button"
                            onClick={() => setSelectedCategory(cat)}
                            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors cursor-pointer shrink-0 ${
                              isActive
                                ? 'bg-red-800 text-white shadow-xs'
                                : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
                            }`}
                          >
                            <span>{cat}</span>
                            <span
                              className={`px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                                isActive ? 'bg-red-950/40 text-red-100' : 'bg-gray-200 text-gray-600'
                              }`}
                            >
                              {count}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {filteredPoints.length > 0 ? (
                    <div className="space-y-3">
                      {filteredPoints.map((point, pIdx) => {
                        const displayText = isAiActive && point.parafrase ? point.parafrase : point.teks || point.poin || '-';

                        return (
                          <div
                            key={point.id || pIdx}
                            className="p-4 sm:p-5 bg-white hover:bg-gray-50/50 border border-gray-200 rounded-xl shadow-2xs hover:shadow-xs transition-all space-y-2.5"
                          >
                            <div className="flex items-center justify-between gap-3 flex-wrap">
                              <div className="flex items-center gap-2">
                                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-800 border border-gray-200">
                                  {point.kategori || 'Norma'}
                                </span>
                                {point.urgensi && (
                                  <span className="text-[11px] font-medium text-gray-500">
                                    • Urgensi: {point.urgensi}
                                  </span>
                                )}
                              </div>

                              {point.pasal && (
                                <button
                                  type="button"
                                  onClick={() => handleOpenPasalModal(point.pasal!)}
                                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold text-red-700 hover:text-red-900 bg-red-50 hover:bg-red-100 border border-red-200 transition-colors cursor-pointer shadow-2xs group"
                                  title={`Klik untuk membaca isi lengkap ${point.pasal}`}
                                >
                                  <BookOpen size={13} className="text-red-600 group-hover:text-red-800" />
                                  <span>{point.pasal}</span>
                                  <span className="text-[11px] text-red-600 font-medium underline ml-0.5">
                                    Lihat Pasal
                                  </span>
                                </button>
                              )}
                            </div>

                            <p className="text-sm font-normal text-gray-800 leading-relaxed font-sans">
                              {displayText}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="p-6 bg-gray-50 rounded-xl border border-gray-200 text-xs text-gray-500 text-center font-sans">
                      {selectedCategory === 'Semua'
                        ? 'Belum ada poin kunci yang teridentifikasi.'
                        : `Tidak ada poin kunci untuk kategori "${selectedCategory}".`}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* 4. MODAL DETAIL PASAL */}
      {pasalModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-gray-900/50 backdrop-blur-xs animate-in fade-in duration-150"
          onClick={() => setPasalModal(null)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="modal-pasal-title"
        >
          <div
            className="bg-white rounded-2xl shadow-2xl border border-gray-200 w-full max-w-xl max-h-[85vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="p-4 sm:p-5 border-b border-gray-200 flex items-start justify-between gap-3 bg-gray-50/80">
              <div className="min-w-0">
                <h3 id="modal-pasal-title" className="text-base font-bold text-gray-900 truncate">
                  Detail {pasalModal.articleNumber || pasalModal.refStr}
                </h3>
                {pasalModal.chapterTitle && (
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mt-0.5 truncate">
                    {pasalModal.chapterTitle}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => setPasalModal(null)}
                className="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors cursor-pointer"
                title="Tutup (Esc)"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 sm:p-6 overflow-y-auto max-h-[55vh] space-y-4">
              <div className="bg-slate-50/80 rounded-xl p-4 sm:p-5 border border-gray-200/90 text-sm font-normal text-gray-800 leading-relaxed font-sans whitespace-pre-line selection:bg-red-100">
                {pasalModal.contentText}
              </div>
              <p className="text-[11px] text-gray-500 italic font-sans">
                * Isi pasal diekstraksi dari naskah regulasi resmi draf ini sebagai dasar pendukung Key Takeaway.
              </p>
            </div>

            {/* Modal Footer */}
            <div className="p-4 sm:px-6 bg-gray-50 border-t border-gray-200 flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={handleViewInNaskahFromModal}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold text-red-800 hover:text-red-900 bg-red-50 hover:bg-red-100 border border-red-200 transition-colors cursor-pointer"
                title="Buka dan sorot pasal ini di panel naskah regulasi"
              >
                <FileText size={14} />
                <span>Buka di Naskah Lengkap</span>
              </button>

              <button
                type="button"
                onClick={() => setPasalModal(null)}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-white hover:bg-gray-100 text-gray-700 border border-gray-300 shadow-2xs transition-colors cursor-pointer"
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
