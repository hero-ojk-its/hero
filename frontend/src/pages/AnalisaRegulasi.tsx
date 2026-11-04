import { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  UploadCloud,
  FileText,
  Sparkles,
  AlertCircle,
  CheckCircle2,
  Clock,
  ArrowRight,
  RefreshCw,
  Activity,
  Copy,
  RotateCcw,
  Trash2,
  Loader2
} from 'lucide-react';

import {
  uploadDraftPdf,
  getDocumentStatus,
  checkMlHealth,
  isDocumentReadyForAnalysis,
  isDocumentProcessingFailed,
  getStoredAnalisaWorkspace,
  saveStoredAnalisaWorkspace,
  clearStoredAnalisaWorkspace
} from '../lib/analisaApi';
import type {
  DocumentStatusResponse,
  DraftUploadMetadata,
  MlHealthResponse,
  UploadProgressEvent
} from '../lib/analisaApi';
import { potongJudul } from '../lib/kemiripanApi';
import { usePolling } from '../lib/usePolling';
import { ErrorState } from '../components/ErrorState';
import { ApiError } from '../lib/api';
import AnalisaState2Workspace from '../components/analisa/AnalisaState2Workspace';

export default function AnalisaRegulasi() {
  const [searchParams, setSearchParams] = useSearchParams();

  // State Deep Linking URL
  const paramDocId = searchParams.get('documentId');
  const paramMode = searchParams.get('mode') as 'deterministik' | 'ai' | null;

  // Active Document ID untuk State 2 Workspace
  const activeDocumentId = paramDocId && !isNaN(Number(paramDocId)) && Number(paramDocId) > 0
    ? Number(paramDocId)
    : null;
  const activeMode: 'deterministik' | 'ai' = paramMode === 'ai' ? 'ai' : 'deterministik';

  // 1. Pemilihan Metode Analisis: 'deterministik' (default) | 'ai'
  const [selectedMode, setSelectedMode] = useState<'deterministik' | 'ai'>('deterministik');

  // 2. State Unggah Draf PDF
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // 3. State Metadata Draf Baru
  const [title, setTitle] = useState<string>('');
  const [regulationNumber, setRegulationNumber] = useState<string>('');
  const [regulationType, setRegulationType] = useState<string>('POJK');
  const [bidang, setBidang] = useState<string>('');
  const [releaseDate, setReleaseDate] = useState<string>(
    new Date().toISOString().split('T')[0]
  );
  // Klasifikasi akses dokumen: 'publik' | 'non_publik' (Kepatuhan NDA)
  const [accessClassification, setAccessClassification] = useState<'publik' | 'non_publik'>('non_publik');

  // Persetujuan Publikasi Draft Kajian (Langkah 35, FR-SCR-04a, Kasus B)
  const [persetujuanPublikOleh, setPersetujuanPublikOleh] = useState<string>('');
  const [persetujuanPublikAlasan, setPersetujuanPublikAlasan] = useState<string>('');
  const [persetujuanTouched, setPersetujuanTouched] = useState<boolean>(false);

  // Status Validasi Draft Kajian Publik (Kasus B)
  const isDraftPublik = accessClassification === 'publik';
  const isPersetujuanOlehValid = !isDraftPublik || persetujuanPublikOleh.trim().length > 0;
  const isPersetujuanAlasanValid = !isDraftPublik || persetujuanPublikAlasan.trim().length >= 10;
  const isPersetujuanValid = isPersetujuanOlehValid && isPersetujuanAlasanValid;

  // 4. State Layanan ML & Eksekusi Upload
  const [mlHealth, setMlHealth] = useState<MlHealthResponse | null>(null);
  const [mlHealthLoading, setMlHealthLoading] = useState<boolean>(true);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<UploadProgressEvent | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadedDocumentId, setUploadedDocumentId] = useState<number | null>(null);
  const uploadAbortControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef<boolean>(true);
  const isExplicitCancelRef = useRef<boolean>(false);
  // Tipe & state hasil unggah berupa duplikat byte-identik
  interface DuplikatInfo {
    documentId: number;
    judul: string | null;
    filename?: string | null;
    regulationNumber?: string | null;
    fileSizeBytes?: number | null;
  }
  const [duplikat, setDuplikat] = useState<DuplikatInfo | null>(null);

  // Ref elemen untuk auto-scroll yang nyaman saat duplikat, progres ekstraksi, atau kegagalan
  const duplicateAlertRef = useRef<HTMLDivElement | null>(null);
  const uploadErrorAlertRef = useRef<HTMLDivElement | null>(null);
  const progressCardRef = useRef<HTMLDivElement | null>(null);
  const lastScrolledDocIdRef = useRef<number | null>(null);

  // 5. State Polling Kesiapan Dokumen
  const [isPollingActive, setIsPollingActive] = useState<boolean>(false);
  const [pollingTimeoutOccurred, setPollingTimeoutOccurred] = useState<boolean>(false);

  // 6. State Pemulihan Workspace (Pekerjaan B)
  const [isRestoringWorkspace, setIsRestoringWorkspace] = useState<boolean>(true);
  const [restoreError, setRestoreError] = useState<string | null>(null);

  // Hook Polling Status Dokumen Backend (Interval 2s, tanpa batas waktu: dokumen tebal tetap dipantau sampai selesai)
  const documentPolling = usePolling<DocumentStatusResponse>({
    fn: (signal) => getDocumentStatus(uploadedDocumentId!, signal),
    isTerminal: (doc) => isDocumentReadyForAnalysis(doc) || isDocumentProcessingFailed(doc),
    interval: 2000,
    enabled: isPollingActive && uploadedDocumentId !== null && uploadedDocumentId > 0,
    onSuccess: (doc) => {
      setIsPollingActive(false);
      // Baca klasifikasi aktual dari response backend (Pekerjaan A)
      if (doc.access_classification) {
        setAccessClassification(doc.access_classification);
      }
      if (isDocumentReadyForAnalysis(doc)) {
        // Dokumen siap dianalisis: transisi ke State 2 Workspace via useSearchParams
        const effectiveMode = mlHealth?.mode_ai === true ? selectedMode : 'deterministik';
        if (uploadedDocumentId) {
          saveStoredAnalisaWorkspace({ documentId: uploadedDocumentId, mode: effectiveMode });
        }
        setSearchParams({
          documentId: String(uploadedDocumentId),
          mode: effectiveMode,
        });
      }
    },
    onError: (err) => {
      setIsPollingActive(false);
      if (err.message && err.message.toLowerCase().includes('melebihi batas waktu')) {
        setPollingTimeoutOccurred(true);
      }
    },
  });

  // Simpan referensi polling terbaru ke dalam ref via effect agar fungsi stop() selalu mutakhir tanpa memicu peringatan render ref
  const documentPollingRef = useRef(documentPolling);
  useEffect(() => {
    documentPollingRef.current = documentPolling;
  }, [documentPolling]);

  // Hentikan dan bersihkan polling serta request in-flight hanya saat komponen dilepas (unmount sejati)
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      documentPollingRef.current.stop();
      if (uploadAbortControllerRef.current) {
        uploadAbortControllerRef.current.abort('Komponen AnalisaRegulasi dilepas (unmount).');
      }
    };
  }, []);

  // Efek auto-scroll ke kartu progres ekstraksi (dijaga agar hanya berjalan SATU KALI per docId)
  useEffect(() => {
    if (uploadedDocumentId && isPollingActive && lastScrolledDocIdRef.current !== uploadedDocumentId) {
      lastScrolledDocIdRef.current = uploadedDocumentId;
      const timer = setTimeout(() => {
        if (progressCardRef.current) {
          progressCardRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
          progressCardRef.current.focus({ preventScroll: true });
        }
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [uploadedDocumentId, isPollingActive]);

  // Pengecekan Kesiapan Layanan ML Lapisan Data saat inisialisasi
  const checkHealthStatus = useCallback(async () => {
    setMlHealthLoading(true);
    try {
      const health = await checkMlHealth();
      setMlHealth(health);
      if (health.mode_ai !== true) {
        setSelectedMode('deterministik');
      }
    } catch {
      setMlHealth(null);
      setSelectedMode('deterministik');
    } finally {
      setMlHealthLoading(false);
    }
  }, []);

  useEffect(() => {
    let isCancelled = false;

    const runInit = async () => {
      await Promise.resolve();
      if (!isCancelled) {
        checkHealthStatus();
      }
    };

    runInit();

    return () => {
      isCancelled = true;
    };
  }, [checkHealthStatus]);

  // Efek Pemulihan Workspace Analisa Regulasi (Pekerjaan B)
  useEffect(() => {
    let isCancelled = false;

    const restoreWorkspace = async () => {
      // 1. Jika URL sudah memiliki documentId aktif, simpan ke storage dan selesai
      if (activeDocumentId !== null) {
        saveStoredAnalisaWorkspace({
          documentId: activeDocumentId,
          mode: activeMode,
        });
        setIsRestoringWorkspace(false);
        return;
      }

      // 2. Jika URL tidak punya documentId, periksa apakah ada session yang tersimpan
      const stored = getStoredAnalisaWorkspace();
      if (!stored || !stored.documentId) {
        setIsRestoringWorkspace(false);
        return;
      }

      // 3. Validasi ke backend via GET /api/v1/documents/{document_id}
      try {
        const doc = await getDocumentStatus(stored.documentId);
        if (isCancelled) return;

        // Baca klasifikasi aktual dari response backend (Pekerjaan A)
        if (doc.access_classification) {
          setAccessClassification(doc.access_classification);
        }

        if (isDocumentReadyForAnalysis(doc)) {
          // Dokumen sudah terindeks: pulihkan ke State 2 Workspace via useSearchParams
          const targetMode = stored.mode || 'deterministik';
          setSearchParams({
            documentId: String(stored.documentId),
            mode: targetMode,
          }, { replace: true });
        } else if (doc.processing_status === 'diproses' || doc.processing_status === 'diterima') {
          // Dokumen masih dalam proses: pulihkan State 1 dan aktifkan polling 2 detik
          setUploadedDocumentId(stored.documentId);
          if (doc.title) setTitle(doc.title);
          setIsPollingActive(true);
        } else if (isDocumentProcessingFailed(doc)) {
          // Dokumen gagal diproses
          setUploadedDocumentId(stored.documentId);
        }
      } catch (err: unknown) {
        if (isCancelled) return;
        // Dokumen tidak ditemukan atau akses ditolak
        clearStoredAnalisaWorkspace();
        if (err instanceof ApiError && err.status === 404) {
          setRestoreError(`Dokumen analisis sebelumnya (#${stored.documentId}) tidak ditemukan di peladen.`);
        } else if (err instanceof ApiError && err.status === 403) {
          setRestoreError(`Akses ke dokumen analisis sebelumnya (#${stored.documentId}) dibatasi (memerlukan sesi login).`);
        }
      } finally {
        if (!isCancelled) {
          setIsRestoringWorkspace(false);
        }
      }
    };

    restoreWorkspace();

    return () => {
      isCancelled = true;
    };
  }, [activeDocumentId, activeMode, setSearchParams]);

  // Handler Drag & Drop File
  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelected(e.target.files[0]);
    }
  };

  const handleFileSelected = (file: File) => {
    // Validasi format PDF
    const isPdf = file.name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf';
    if (!isPdf) {
      setUploadError('Berkas harus berupa dokumen format PDF (.pdf).');
      return;
    }
    // Validasi batas ukuran 100 MB (mengikuti batas backend)
    if (file.size > 100 * 1024 * 1024) {
      setUploadError('Ukuran berkas melebihi batas maksimum 100 MB.');
      return;
    }

    setUploadError(null);
    setSelectedFile(file);

    // Otomatis isi judul dari nama berkas jika masih kosong
    if (!title.trim()) {
      const cleanName = file.name.replace(/\.pdf$/i, '').replace(/[_-]/g, ' ');
      setTitle(cleanName);
    }
  };

  const handleRemoveFile = () => {
    setSelectedFile(null);
    setUploadError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Kartu duplikat -> "Unggah berkas lain": kosongkan berkas & isian khusus berkas, pilihan lain dipertahankan
  const handleUnggahBerkasLain = () => {
    clearStoredAnalisaWorkspace();
    setUploadedDocumentId(null);
    lastScrolledDocIdRef.current = null;
    setIsPollingActive(false);
    documentPolling.stop();
    setRestoreError(null);
    setDuplikat(null);
    setSelectedFile(null);
    setTitle('');
    setRegulationNumber('');
    setUploadError(null);
    setIsUploading(false);
    setUploadProgress(null);
    isExplicitCancelRef.current = false;
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Handler Submit Unggah Draf
  const handleSubmitUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setUploadError('Pilih berkas PDF draf regulasi terlebih dahulu.');
      setTimeout(() => {
        uploadErrorAlertRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 50);
      return;
    }
    if (!title.trim()) {
      setUploadError('Judul draf regulasi wajib diisi.');
      setTimeout(() => {
        uploadErrorAlertRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 50);
      return;
    }

    if (isDraftPublik && !isPersetujuanValid) {
      setPersetujuanTouched(true);
      if (!persetujuanPublikOleh.trim()) {
        setUploadError('Nama pihak yang menyetujui (Disetujui oleh) wajib diisi untuk draft kajian publik.');
      } else if (persetujuanPublikAlasan.trim().length < 10) {
        setUploadError('Alasan persetujuan wajib diisi minimal 10 karakter untuk draft kajian publik.');
      }
      setTimeout(() => {
        uploadErrorAlertRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 50);
      return;
    }

    setUploadError(null);
    setDuplikat(null);
    setIsUploading(true);
    setUploadProgress(null);
    setPollingTimeoutOccurred(false);
    isExplicitCancelRef.current = false;

    if (uploadAbortControllerRef.current) {
      uploadAbortControllerRef.current.abort();
    }
    const uploadCtrl = new AbortController();
    uploadAbortControllerRef.current = uploadCtrl;

    try {
      const metadata: DraftUploadMetadata = {
        title: title.trim(),
        regulation_number: regulationNumber.trim() || undefined,
        regulation_type: regulationType.trim() || undefined,
        bidang: bidang.trim() || undefined,
        release_date: releaseDate.trim() || undefined,
        access_classification: accessClassification,
        persetujuan_publik_oleh: isDraftPublik ? persetujuanPublikOleh.trim() || undefined : undefined,
        persetujuan_publik_alasan: isDraftPublik ? persetujuanPublikAlasan.trim() || undefined : undefined,
      };

      // Unggah via API client dengan pemantauan progress byte riil
      const result = await uploadDraftPdf(
        selectedFile,
        metadata,
        uploadCtrl.signal,
        (progress) => {
          if (isMountedRef.current) {
            setUploadProgress(progress);
          }
        }
      );

      if (!isMountedRef.current) return;

      // Duplikat byte-identik: tampilkan kartu peringatan di State 1 dan lakukan auto-scroll terarah
      if (result.isDuplicate) {
        setIsUploading(false);
        setUploadProgress(null);
        uploadAbortControllerRef.current = null;
        setDuplikat({
          documentId: result.duplicateOfDocumentId ?? result.documentId,
          judul: result.duplicateTitle ?? null,
          filename: result.filename,
          regulationNumber: result.duplicateRegulationNumber ?? null,
          fileSizeBytes: result.fileSizeBytes ?? null,
        });
        setTimeout(() => {
          duplicateAlertRef.current?.scrollIntoView({
            behavior: 'smooth',
            block: 'center',
          });
        }, 100);
        return;
      }

      const docId = result.documentId;
      setUploadedDocumentId(docId);
      saveStoredAnalisaWorkspace({ documentId: docId, mode: selectedMode });
      setIsUploading(false);
      setUploadProgress(null);
      uploadAbortControllerRef.current = null;

      // Catat docId agar auto-scroll hanya dijalankan satu kali (mencegah scroll berulang saat polling)
      lastScrolledDocIdRef.current = docId;

      // Mulai polling status pemrosesan dokumen di backend
      setIsPollingActive(true);

      // Jadwalkan auto-scroll ke kartu progres ekstraksi setelah komponen ter-mount di DOM
      setTimeout(() => {
        if (progressCardRef.current) {
          progressCardRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
          progressCardRef.current.focus({ preventScroll: true });
        }
      }, 100);
    } catch (err: unknown) {
      if (!isMountedRef.current) {
        return;
      }
      const isAborted =
        (err instanceof DOMException && err.name === 'AbortError') ||
        (err instanceof Error && err.name === 'AbortError');
      if (isAborted) {
        setIsUploading(false);
        setUploadProgress(null);
        // Tampilkan pesan jika pembatalan terjadi di luar aksi klik sengaja pengguna
        if (!isExplicitCancelRef.current) {
          setUploadError('Permintaan unggah berkas terputus atau dibatalkan.');
        }
        return;
      }
      setIsUploading(false);
      setUploadProgress(null);
      let msg = 'Terjadi kegagalan saat mengunggah berkas draf.';
      if (err instanceof ApiError) {
        const detailObj =
          err.detail && typeof err.detail === 'object' && !Array.isArray(err.detail)
            ? (err.detail as Record<string, unknown>)
            : null;
        if (err.status === 422 && detailObj?.code === 'draft_publik_butuh_persetujuan' && typeof detailObj.message === 'string') {
          msg = detailObj.message;
        } else if (typeof detailObj?.message === 'string') {
          msg = detailObj.message;
        } else {
          msg = err.message;
        }
      } else if (err instanceof Error) {
        msg = err.message;
      }
      setUploadError(msg);
      setTimeout(() => {
        uploadErrorAlertRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
        });
      }, 100);
    }
  };

  // Handler Pembukaan Dokumen ke State 2
  const handleOpenWorkspace = (docId: number, mode: 'deterministik' | 'ai' = selectedMode) => {
    documentPolling.stop();
    setIsPollingActive(false);
    if (uploadAbortControllerRef.current) {
      isExplicitCancelRef.current = true;
      uploadAbortControllerRef.current.abort();
      uploadAbortControllerRef.current = null;
    }
    const effectiveMode = (mlHealth && mlHealth.mode_ai === false) ? 'deterministik' : mode;
    saveStoredAnalisaWorkspace({ documentId: docId, mode: effectiveMode });
    setSearchParams({
      documentId: String(docId),
      mode: effectiveMode,
    });
  };

  // Handler Kembali dari State 2 ke State 1 (Pekerjaan B: reset workspace)
  const handleBackToState1 = () => {
    clearStoredAnalisaWorkspace();
    setSearchParams({});
    documentPolling.stop();
    setIsPollingActive(false);
    if (uploadAbortControllerRef.current) {
      isExplicitCancelRef.current = true;
      uploadAbortControllerRef.current.abort();
      uploadAbortControllerRef.current = null;
    }
    setIsUploading(false);
    setUploadProgress(null);
    setUploadedDocumentId(null);
    lastScrolledDocIdRef.current = null;
    setPollingTimeoutOccurred(false);
    setDuplikat(null);
    setSelectedFile(null);
    setTitle('');
    setRegulationNumber('');
    setPersetujuanPublikOleh('');
    setPersetujuanPublikAlasan('');
    setPersetujuanTouched(false);
    setRestoreError(null);
    checkHealthStatus();
  };

  // Tampilan Memulihkan Sesi Ruang Kerja Sebelumnya (Pekerjaan B)
  if (isRestoringWorkspace && activeDocumentId === null && getStoredAnalisaWorkspace() !== null) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-3">
        <RefreshCw size={24} className="animate-spin text-red-700" />
        <p className="text-xs font-semibold text-gray-600">Memulihkan ruang kerja analisis regulasi...</p>
      </div>
    );
  }

  // ============================================================================
  // TAMPILAN STATE 2: WORKSPACE TIGA PANEL (Jika documentId ada di URL)
  // ============================================================================
  if (activeDocumentId !== null) {
    return (
      <AnalisaState2Workspace
        // key: pindah ke draft lain (mis. dari banner kemiripan) me-mount ulang workspace,
        // sehingga state lama ter-reset dan request/polling dokumen sebelumnya dibatalkan
        key={activeDocumentId}
        documentId={activeDocumentId}
        mode={activeMode}
        onBackToState1={handleBackToState1}
      />
    );
  }

  // ============================================================================
  // TAMPILAN STATE 1: UNGGAH DRAFT PERATURAN UNTUK DIANALISIS
  // ============================================================================
  return (
    <div className="max-w-[1240px] mx-auto space-y-6 font-sans pb-16">
      {/* 1. Breadcrumb Navigasi */}
      <div className="flex items-center text-xs font-semibold tracking-wider text-gray-500">
        <span className="hover:text-red-700 transition">DASHBOARD</span>
        <span className="mx-2 text-gray-400">&gt;</span>
        <span className="text-red-700 uppercase">ANALISA REGULASI</span>
      </div>

      {/* 2. Top Header Title & Service Status */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Analisa Regulasi</h1>
          <p className="text-xs text-gray-600 mt-1 leading-relaxed max-w-2xl">
            Unggah dan analisis rancangan regulasi baru untuk mengekstraksi kewajiban, larangan, sanksi,
            serta memetakan norma hukum dan struktur pasal secara otomatis.
          </p>
        </div>

        {/* Indikator Status Kesiapan Layanan ML Lapisan Data */}
        <div className="shrink-0 flex items-center gap-2">
          {mlHealthLoading ? (
            <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200">
              <RefreshCw size={12} className="animate-spin text-gray-500" />
              <span>Memeriksa layanan...</span>
            </div>
          ) : mlHealth?.status === 'siap' ? (
            <div
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200 shadow-2xs"
              title={`Korpus: ${mlHealth.korpus.dokumen} dokumen, ${mlHealth.korpus.pasal} pasal. Mode AI: ${mlHealth.mode_ai ? 'Aktif' : 'Non-aktif'}`}
            >
              <Activity size={13} className="text-emerald-600" />
              <span>Layanan ML Siap</span>
            </div>
          ) : (
            <div
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200 shadow-2xs"
              title="Layanan ML Lapisan Data belum aktif. Analisis otomatis memerlukan jembatan 'hero bridge serve'."
            >
              <AlertCircle size={13} className="text-amber-600" />
              <span>Layanan ML Belum Siap (hero bridge serve)</span>
            </div>
          )}
        </div>
      </div>

      {/* Banner Galat Pemulihan Workspace (Pekerjaan B) */}
      {restoreError && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-center justify-between text-xs text-amber-900 animate-in fade-in">
          <div className="flex items-center gap-2.5">
            <AlertCircle size={18} className="text-amber-700 shrink-0" />
            <span>{restoreError}</span>
          </div>
          <button
            type="button"
            onClick={() => {
              setRestoreError(null);
              clearStoredAnalisaWorkspace();
            }}
            className="px-3 py-1 bg-white border border-amber-300 hover:bg-amber-100 text-amber-900 rounded-md font-semibold cursor-pointer shrink-0"
          >
            Mulai Analisis Baru
          </button>
        </div>
      )}

      {/* 2b. Hasil unggah duplikat byte-identik (Inline alert dengan role="alert" dan auto-scroll) */}
      {duplikat && (
        <div
          ref={duplicateAlertRef}
          role="alert"
          className="bg-amber-50/95 border-2 border-amber-300 rounded-xl p-5 shadow-sm space-y-4 animate-in fade-in duration-200"
        >
          <div className="flex items-start gap-3.5">
            <div className="w-10 h-10 rounded-lg bg-amber-100 text-amber-800 border border-amber-200 flex items-center justify-center shrink-0">
              <Copy size={20} />
            </div>
            <div className="min-w-0 space-y-1">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-amber-950">Dokumen Terdeteksi Duplikat</h3>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-200/80 text-amber-900">
                  Sudah Terdaftar
                </span>
              </div>
              <p className="text-xs text-amber-900 leading-relaxed">
                Sistem mendeteksi berkas ini memiliki hash identik secara digital dengan dokumen draf regulasi yang sudah pernah diunggah sebelumnya. Berkas tidak diunggah ulang untuk mencegah redundansi pangkalan data.
              </p>
            </div>
          </div>

          {/* Rincian Dokumen Terdaftar */}
          <div className="bg-white/80 border border-amber-200 rounded-lg p-3.5 space-y-2 text-xs">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-gray-700">
              <div>
                <span className="text-[11px] text-gray-500 block">Berkas Baru yang Diuji:</span>
                <span className="font-semibold text-gray-900 truncate block">
                  {duplikat.filename || selectedFile?.name || 'Berkas PDF'}
                </span>
              </div>
              <div>
                <span className="text-[11px] text-gray-500 block">Dokumen Pembanding di Sistem:</span>
                <span className="font-semibold text-red-700 block font-mono">
                  Draft #{duplikat.documentId}
                </span>
              </div>
            </div>

            {duplikat.judul && (
              <div className="pt-1 border-t border-amber-100">
                <span className="text-[11px] text-gray-500 block">Judul Dokumen Terdaftar:</span>
                <p className="font-medium text-gray-900 italic">
                  "{potongJudul(duplikat.judul)}"
                </p>
              </div>
            )}

            {duplikat.regulationNumber && (
              <div>
                <span className="text-[11px] text-gray-500 block">Nomor Regulasi:</span>
                <span className="font-semibold text-gray-800">{duplikat.regulationNumber}</span>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2.5 pt-1">
            <button
              type="button"
              onClick={() => handleOpenWorkspace(duplikat.documentId)}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-700 hover:bg-red-800 text-white rounded-lg text-xs font-semibold cursor-pointer shadow-xs transition"
            >
              <span>Buka Hasil Draf Sebelumnya</span>
              <ArrowRight size={14} />
            </button>
            <button
              type="button"
              onClick={handleUnggahBerkasLain}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 rounded-lg text-xs font-semibold cursor-pointer transition shadow-2xs"
            >
              <RotateCcw size={13} className="text-gray-500" />
              <span>Unggah Berkas Lain</span>
            </button>
          </div>
        </div>
      )}

      {/* 3. MODUL PROGRES & POLLING UNGGAH DRAF (Aktif saat proses upload & ekstraksi berlangsung) */}
      {(isUploading || isPollingActive || pollingTimeoutOccurred) && (
        <div
          ref={progressCardRef}
          tabIndex={-1}
          role="region"
          aria-label="Progres Ekstraksi Regulasi"
          className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4 focus:outline-none scroll-mt-6"
        >
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-gray-100">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-red-50 text-red-700 border border-red-100 flex items-center justify-center shrink-0">
                {isUploading ? (
                  <UploadCloud size={20} className="text-red-700 animate-pulse" />
                ) : (
                  <Clock size={20} className="animate-spin text-red-700" />
                )}
              </div>
              <div className="min-w-0">
                <h3 className="text-sm font-bold text-gray-900">
                  {isUploading
                    ? 'Mengunggah Berkas Draf Regulasi ke Peladen...'
                    : 'Memproses Ekstraksi Naskah di Peladen...'}
                </h3>
                <p className="text-xs text-gray-500 mt-0.5 truncate">
                  {selectedFile ? `${selectedFile.name} • ${(selectedFile.size / (1024 * 1024)).toFixed(2)} MB` : ''}
                  {uploadedDocumentId ? ` • ID Dokumen: #${uploadedDocumentId}` : ''}
                  {` • Klasifikasi: ${accessClassification === 'non_publik' ? 'Non-Publik (Draf Kajian)' : 'Publik (Terbuka)'}`}
                </p>
              </div>
            </div>

            {uploadedDocumentId && !isUploading && (
              <span className={`px-2.5 py-1 rounded-md text-xs font-semibold shrink-0 self-start sm:self-auto border ${
                documentPolling.data?.processing_status === 'terindeks' || documentPolling.data?.processing_status === 'perlu_koreksi'
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                  : documentPolling.data?.processing_status === 'diproses'
                  ? 'bg-amber-50 text-amber-800 border-amber-200'
                  : documentPolling.data?.processing_status === 'gagal' || documentPolling.data?.processing_status === 'ditolak'
                  ? 'bg-rose-50 text-rose-800 border-rose-200'
                  : 'bg-gray-100 text-gray-700 border-gray-200'
              }`}>
                Status: {
                  documentPolling.data?.processing_status === 'diterima'
                    ? 'Dalam Antrean'
                    : documentPolling.data?.processing_status === 'diproses'
                    ? 'Sedang Diproses'
                    : documentPolling.data?.processing_status === 'terindeks' || documentPolling.data?.processing_status === 'perlu_koreksi'
                    ? 'Ekstraksi Selesai'
                    : documentPolling.data?.processing_status === 'gagal' || documentPolling.data?.processing_status === 'ditolak'
                    ? 'Gagal'
                    : 'Memuat...'
                }
              </span>
            )}
          </div>

          {/* Progress Bar Upload Aktual (Aktif hanya selama fase upload HTTP) */}
          {isUploading && (
            <div className="space-y-1.5 p-3 rounded-lg bg-red-50/40 border border-red-100">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-gray-700">Kemajuan Unggah Berkas</span>
                <span className="font-mono text-red-700 font-bold">
                  {uploadProgress?.percent !== null && uploadProgress?.percent !== undefined
                    ? `${uploadProgress.percent}%`
                    : 'Mengirim aliran berkas...'}
                </span>
              </div>
              <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden relative">
                {uploadProgress?.percent !== null && uploadProgress?.percent !== undefined ? (
                  <div
                    style={{ width: `${uploadProgress.percent}%` }}
                    className="h-full bg-red-700 rounded-full transition-all duration-150"
                  />
                ) : (
                  <div className="h-full bg-red-700 rounded-full animate-pulse w-full" />
                )}
              </div>
              <div className="flex items-center justify-between text-[11px] text-gray-500">
                <span>
                  {uploadProgress
                    ? `${(uploadProgress.loaded / (1024 * 1024)).toFixed(2)} MB terkirim ${
                        uploadProgress.total > 0 ? `dari ${(uploadProgress.total / (1024 * 1024)).toFixed(2)} MB` : ''
                      }`
                    : 'Menghubungkan ke peladen...'}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    isExplicitCancelRef.current = true;
                    if (uploadAbortControllerRef.current) {
                      uploadAbortControllerRef.current.abort();
                      uploadAbortControllerRef.current = null;
                    }
                    setIsUploading(false);
                    setUploadProgress(null);
                  }}
                  className="text-red-700 hover:text-red-900 font-semibold cursor-pointer underline text-[11px]"
                >
                  Batalkan Unggah
                </button>
              </div>
            </div>
          )}

          {/* Stepper Status Progress Tiga Tahap */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            {/* Tahap 1: Unggah PDF */}
            <div className={`p-3 rounded-lg border flex items-center gap-2.5 ${
              uploadedDocumentId
                ? 'border-emerald-200 bg-emerald-50/50 text-emerald-800'
                : isUploading
                ? 'border-red-200 bg-red-50/40 text-red-800 font-semibold'
                : 'border-gray-200 bg-gray-50 text-gray-400'
            }`}>
              <CheckCircle2 size={16} className={uploadedDocumentId ? 'text-emerald-600' : isUploading ? 'text-red-700 animate-pulse' : 'text-gray-400'} />
              <div>
                <span className="block font-semibold">1. Unggah PDF</span>
                <span className="text-[11px] opacity-80 block">
                  {uploadedDocumentId ? 'Berkas berhasil disimpan' : isUploading ? 'Sedang mengirim berkas...' : 'Menunggu berkas'}
                </span>
              </div>
            </div>

            {/* Tahap 2: Ekstraksi Naskah Backend */}
            <div className={`p-3 rounded-lg border flex items-center gap-2.5 ${
              documentPolling.data?.processing_status === 'terindeks' || documentPolling.data?.processing_status === 'perlu_koreksi'
                ? 'border-emerald-200 bg-emerald-50/50 text-emerald-800'
                : documentPolling.data?.processing_status === 'gagal' || documentPolling.data?.processing_status === 'ditolak'
                ? 'border-rose-200 bg-rose-50/50 text-rose-800'
                : documentPolling.data?.processing_status === 'diproses'
                ? 'border-amber-200 bg-amber-50/40 text-amber-900 font-semibold'
                : uploadedDocumentId && isPollingActive
                ? 'border-blue-200 bg-blue-50/30 text-blue-800'
                : 'border-gray-200 bg-gray-50 text-gray-400'
            }`}>
              {documentPolling.data?.processing_status === 'terindeks' || documentPolling.data?.processing_status === 'perlu_koreksi' ? (
                <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
              ) : documentPolling.data?.processing_status === 'gagal' || documentPolling.data?.processing_status === 'ditolak' ? (
                <AlertCircle size={16} className="text-rose-600 shrink-0" />
              ) : documentPolling.data?.processing_status === 'diproses' ? (
                <Clock size={16} className="text-amber-700 animate-spin shrink-0" />
              ) : (
                <Clock size={16} className={uploadedDocumentId ? 'text-blue-600 shrink-0' : 'text-gray-400 shrink-0'} />
              )}
              <div>
                <span className="block font-semibold">2. Ekstraksi Naskah</span>
                <span className="text-[11px] opacity-80 block">
                  {documentPolling.data?.processing_status === 'terindeks' || documentPolling.data?.processing_status === 'perlu_koreksi'
                    ? 'Ekstraksi naskah selesai'
                    : documentPolling.data?.processing_status === 'gagal' || documentPolling.data?.processing_status === 'ditolak'
                    ? 'Ekstraksi gagal di peladen'
                    : documentPolling.data?.processing_status === 'diproses'
                    ? 'Worker sedang mengekstrak...'
                    : uploadedDocumentId
                    ? 'Menunggu antrean ekstraksi...'
                    : 'Menunggu unggahan'}
                </span>
              </div>
            </div>

            {/* Tahap 3: Kesiapan Analisis ML */}
            <div className={`p-3 rounded-lg border flex items-center gap-2.5 ${
              documentPolling.data && isDocumentReadyForAnalysis(documentPolling.data)
                ? 'border-emerald-200 bg-emerald-50/50 text-emerald-800'
                : 'border-gray-200 bg-gray-50 text-gray-400'
            }`}>
              <Sparkles size={16} className={
                documentPolling.data && isDocumentReadyForAnalysis(documentPolling.data)
                  ? 'text-emerald-600 shrink-0'
                  : 'text-gray-400 shrink-0'
              } />
              <div>
                <span className="block font-semibold">3. Kesiapan Analisis</span>
                <span className="text-[11px] opacity-80 block">
                  {documentPolling.data && isDocumentReadyForAnalysis(documentPolling.data)
                    ? 'Siap membuka workspace'
                    : 'Menunggu ekstraksi pasal'}
                </span>
              </div>
            </div>
          </div>

          {/* Opsi Mulai Dokumen Baru saat Polling Berlangsung */}
          <div className="flex justify-end pt-1">
            <button
              type="button"
              onClick={handleBackToState1}
              className="text-xs font-semibold text-gray-500 hover:text-red-700 underline cursor-pointer"
            >
              Batalkan dan Mulai Analisis Dokumen Baru
            </button>
          </div>

          {/* Detail Ekstraksi Terkini Berdasarkan processing_status Backend (Live Region role="status") */}
          {documentPolling.data && isPollingActive && (
            <div
              role="status"
              aria-live="polite"
              className="p-3 bg-gray-50 border border-gray-100 rounded-lg text-xs text-gray-600 flex flex-wrap items-center justify-between gap-2"
            >
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-red-700 animate-pulse" />
                <span>
                  {documentPolling.data.processing_status === 'diterima' && (
                    <span>Naskah tersimpan di peladen (status: diterima). Menunggu giliran worker ekstraksi...</span>
                  )}
                  {documentPolling.data.processing_status === 'diproses' && (
                    <span>Peladen sedang memproses ekstraksi teks, pasal, dan OCR...</span>
                  )}
                  {(documentPolling.data.processing_status === 'terindeks' || documentPolling.data.processing_status === 'perlu_koreksi') && (
                    <span>
                      Ekstraksi tuntas: <strong>{documentPolling.data.articles?.length || 0} pasal</strong> terdeteksi •
                      Teks lengkap: <strong>{documentPolling.data.full_text_length || 0} karakter</strong>
                    </span>
                  )}
                </span>
              </div>
              <span className="font-mono text-[11px] text-gray-500">
                Memperbarui status setiap 2 detik...
              </span>
            </div>
          )}

          {/* Status Kegagalan Terminal */}
          {documentPolling.data && isDocumentProcessingFailed(documentPolling.data) && (
            <ErrorState
              title="Ekstraksi Dokumen Gagal di Backend"
              message={`Dokumen #${uploadedDocumentId} mengalami kegagalan ekstraksi (status: ${documentPolling.data.processing_status}). Pastikan format berkas PDF valid dan tidak terproteksi sandi.`}
              retryText="Unggah Berkas Baru"
              onRetry={() => {
                setIsPollingActive(false);
                setSelectedFile(null);
                setUploadedDocumentId(null);
              }}
            />
          )}

          {/* Timeout Alert & Tombol Lanjut Paksa */}
          {pollingTimeoutOccurred && uploadedDocumentId && (
            <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900 space-y-2">
              <div className="flex items-center gap-2 font-bold">
                <AlertCircle size={16} className="text-amber-700" />
                <span>Pemrosesan ekstraksi naskah membutuhkan waktu lebih lama di peladen.</span>
              </div>
              <p className="leading-relaxed">
                Dokumen telah tersimpan dengan aman dengan ID <strong>#{uploadedDocumentId}</strong>.
                Anda dapat mencoba langsung membuka ruang kerja analisis regulasi atau membatalkan proses.
              </p>
              <div className="flex items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => handleOpenWorkspace(uploadedDocumentId)}
                  className="px-3.5 py-1.5 bg-red-700 hover:bg-red-800 text-white rounded-md text-xs font-semibold cursor-pointer"
                >
                  Buka Ruang Kerja Analisis Sekarang
                </button>
                <button
                  type="button"
                  onClick={() => {
                    documentPolling.stop();
                    setIsPollingActive(false);
                    setPollingTimeoutOccurred(false);
                  }}
                  className="px-3.5 py-1.5 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 rounded-md text-xs font-semibold cursor-pointer"
                >
                  Batal
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 4. FORMULIR UTAMA: UNGGAH DRAFT PERATURAN UNTUK DIANALISIS */}
      <form onSubmit={handleSubmitUpload} className="space-y-6">
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-2xs space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-4 border-b border-gray-100">
            <div>
              <h2 className="text-sm font-bold text-gray-900 uppercase tracking-wider">
                1. Unggah Draft Peraturan untuk Dianalisis
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Unggah naskah rancangan peraturan baru dalam format PDF. Dokumen diklasifikasikan sebagai {accessClassification === 'non_publik' ? 'Non-Publik' : 'Publik'} untuk kajian telaah dan ekstraksi pasal.
              </p>
            </div>
            <span className={`self-start sm:self-auto px-2.5 py-1 rounded-full text-[10px] font-semibold border shrink-0 ${
              accessClassification === 'non_publik'
                ? 'bg-red-50 text-red-700 border-red-200'
                : 'bg-emerald-50 text-emerald-700 border-emerald-200'
            }`}>
              Klasifikasi: {accessClassification === 'non_publik' ? 'Non-Publik (Draf Kajian)' : 'Publik (Terbuka)'}
            </span>
          </div>

          {/* Dropzone File */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf"
            onChange={handleFileInputChange}
            className="hidden"
          />

          {!selectedFile ? (
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 text-center transition cursor-pointer flex flex-col items-center justify-center space-y-3.5 ${
                isDragging
                  ? 'border-red-600 bg-red-50/60 ring-2 ring-red-400/40'
                  : 'border-red-200/90 bg-red-50/15 hover:border-red-400 hover:bg-red-50/30 shadow-2xs'
              }`}
            >
              <div className="w-13 h-13 rounded-full bg-red-100 text-red-700 flex items-center justify-center shadow-2xs">
                <UploadCloud size={26} />
              </div>
              <div className="space-y-1">
                <p className="text-xs font-bold text-gray-800">
                  Tarik dan lepaskan berkas PDF draf regulasi ke sini, atau{' '}
                  <span className="text-red-700 underline font-semibold hover:text-red-800">pilih dari komputer</span>
                </p>
                <p className="text-[11px] text-gray-500">
                  Format wajib: Dokumen PDF (.pdf) • Batas maksimum ukuran: 100 MB
                </p>
              </div>
            </div>
          ) : (
            <div className="p-4 rounded-xl border border-red-200 bg-red-50/25 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-2xs">
              <div className="flex items-center gap-3.5 min-w-0">
                <div className="w-11 h-11 rounded-lg bg-red-100 text-red-700 flex items-center justify-center shrink-0 border border-red-200/80 shadow-2xs">
                  <FileText size={22} />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-xs font-bold text-gray-900 truncate max-w-[280px] sm:max-w-md" title={selectedFile.name}>
                      {selectedFile.name}
                    </p>
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200 shrink-0">
                      PDF Siap
                    </span>
                  </div>
                  <p className="text-[11px] text-gray-500 mt-0.5">
                    {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • Berkas PDF Terverifikasi
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-300 bg-white hover:bg-gray-50 text-xs font-semibold text-gray-700 transition cursor-pointer shadow-2xs"
                  title="Pilih berkas PDF lain"
                >
                  <RotateCcw size={13} className="text-gray-500" />
                  <span>Ganti Berkas</span>
                </button>
                <button
                  type="button"
                  onClick={handleRemoveFile}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-200 bg-red-50/60 hover:bg-red-100/80 text-xs font-semibold text-red-700 transition cursor-pointer shadow-2xs"
                  title="Hapus berkas ini"
                >
                  <Trash2 size={13} className="text-red-700" />
                  <span>Hapus</span>
                </button>
              </div>
            </div>
          )}

          {/* Form Kolom Metadata Draf */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
            {/* Judul Draf */}
            <div className="md:col-span-2 space-y-1">
              <label className="text-xs font-bold text-gray-700">
                Judul Draf Regulasi <span className="text-red-600">*</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Contoh: Ketahanan dan Keamanan Siber bagi Bank Umum"
                className="w-full px-3 py-2 text-xs bg-white border border-gray-200 rounded-lg focus:outline-none focus:border-red-700 focus:ring-1 focus:ring-red-700 transition"
                required
              />
            </div>

            {/* Nomor Regulasi */}
            <div className="space-y-1">
              <label className="text-xs font-bold text-gray-700">
                Nomor / Kode Draf Regulasi (Opsional)
              </label>
              <input
                type="text"
                value={regulationNumber}
                onChange={(e) => setRegulationNumber(e.target.value)}
                placeholder="Contoh: RPOJK-Siber-2024 (kosongkan jika belum ada)"
                className="w-full px-3 py-2 text-xs bg-white border border-gray-200 rounded-lg focus:outline-none focus:border-red-700 focus:ring-1 focus:ring-red-700 transition"
              />
            </div>

            {/* Jenis Regulasi */}
            <div className="space-y-1">
              <label className="text-xs font-bold text-gray-700">
                Jenis Regulasi
              </label>
              <select
                value={regulationType}
                onChange={(e) => setRegulationType(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-white border border-gray-200 rounded-lg focus:outline-none focus:border-red-700 focus:ring-1 focus:ring-red-700 transition"
              >
                <option value="POJK">Peraturan OJK (POJK)</option>
                <option value="SEOJK">Surat Edaran OJK (SEOJK)</option>
                <option value="PDK">Peraturan Dewan Komisioner (PDK)</option>
                <option value="SEDK">Surat Edaran Dewan Komisioner (SEDK)</option>
                <option value="Lainnya">Lainnya</option>
              </select>
            </div>

            {/* Bidang / Sektor */}
            <div className="space-y-1">
              <label className="text-xs font-bold text-gray-700 flex items-center justify-between">
                <span>Sektor / Bidang Regulasi (Opsional)</span>
              </label>
              <select
                value={bidang}
                onChange={(e) => setBidang(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-white border border-gray-200 rounded-lg focus:outline-none focus:border-red-700 focus:ring-1 focus:ring-red-700 transition text-gray-800"
              >
                <option value="">-- Pilih Sektor / Bidang Regulasi (Opsional) --</option>
                <option value="Perbankan">Perbankan</option>
                <option value="Pasar Modal">Pasar Modal</option>
                <option value="Asuransi">Perasuransian &amp; Dana Pensiun</option>
                <option value="Fintech">Fintech &amp; Lembaga Pembiayaan</option>
                <option value="Tata Kelola IT & AI">Tata Kelola IT &amp; AI</option>
                <option value="Lainnya">Lainnya</option>
              </select>
            </div>

            {/* Tanggal Rilis / Draf */}
            <div className="space-y-1">
              <label className="text-xs font-bold text-gray-700">
                Tanggal Kajian / Draf
              </label>
              <input
                type="date"
                value={releaseDate}
                onChange={(e) => setReleaseDate(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-white border border-gray-200 rounded-lg focus:outline-none focus:border-red-700 focus:ring-1 focus:ring-red-700 transition"
              />
            </div>

            {/* Klasifikasi Dokumen (Publik vs Non-publik) */}
            <div className="md:col-span-2 space-y-1.5 pt-1">
              <label className="text-xs font-bold text-gray-700 flex items-center justify-between">
                <span>Klasifikasi Akses Dokumen <span className="text-red-600">*</span></span>
                <span className="text-[11px] font-normal text-gray-400">Pilih klasifikasi sesuai kepatuhan NDA regulasi</span>
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setAccessClassification('non_publik')}
                  className={`p-3 rounded-lg border text-left flex items-start gap-2.5 transition cursor-pointer ${
                    accessClassification === 'non_publik'
                      ? 'border-red-700 bg-red-50/40 text-red-900 ring-1 ring-red-700 shadow-2xs'
                      : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'
                  }`}
                >
                  <div className={`w-4 h-4 rounded-full border mt-0.5 flex items-center justify-center shrink-0 ${
                    accessClassification === 'non_publik' ? 'border-red-700 bg-red-700' : 'border-gray-300'
                  }`}>
                    {accessClassification === 'non_publik' && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                  </div>
                  <div className="space-y-0.5">
                    <span className="text-xs font-bold block">Non-publik (Draf Kajian)</span>
                    <span className="text-[11px] text-gray-500 leading-relaxed block">
                      Tunduk pada NDA / rahasia internal. Hanya dapat dianalisis setelah login diaktifkan.
                    </span>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setAccessClassification('publik')}
                  className={`p-3 rounded-lg border text-left flex items-start gap-2.5 transition cursor-pointer ${
                    accessClassification === 'publik'
                      ? 'border-emerald-700 bg-emerald-50/40 text-emerald-900 ring-1 ring-emerald-700 shadow-2xs'
                      : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'
                  }`}
                >
                  <div className={`w-4 h-4 rounded-full border mt-0.5 flex items-center justify-center shrink-0 ${
                    accessClassification === 'publik' ? 'border-emerald-700 bg-emerald-700' : 'border-gray-300'
                  }`}>
                    {accessClassification === 'publik' && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                  </div>
                  <div className="space-y-0.5">
                    <span className="text-xs font-bold block">Publik (Terbuka)</span>
                    <span className="text-[11px] text-gray-500 leading-relaxed block">
                      Dokumen regulasi terbuka untuk umum. Wajib menyertakan persetujuan publikasi draf kajian.
                    </span>
                  </div>
                </button>
              </div>
            </div>

            {/* Form Persetujuan Publikasi Draft Kajian (Langkah 35, Kasus B) */}
            {isDraftPublik && (
              <div className="md:col-span-2 p-4 bg-emerald-50/40 border border-emerald-200 rounded-xl space-y-4 animate-in fade-in duration-200">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-emerald-600" />
                  <h4 className="text-xs font-bold text-emerald-950 uppercase tracking-wide">
                    Persetujuan Publikasi Draf Kajian Terbuka
                  </h4>
                </div>
                <p className="text-[11px] text-emerald-900 leading-relaxed -mt-2">
                  Sesuai kebijakan tata kelola regulasi, draf kajian yang dipublikasikan secara terbuka wajib mencantumkan pihak yang menyetujui dan alasan justifikasi resmi (minimal 10 karakter).
                </p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Input: Disetujui oleh */}
                  <div>
                    <label
                      htmlFor="input-persetujuan-oleh"
                      className="block text-xs font-bold text-gray-900 mb-1"
                    >
                      Disetujui oleh <span className="text-red-600">* (Wajib)</span>
                    </label>
                    <input
                      id="input-persetujuan-oleh"
                      name="persetujuan_publik_oleh"
                      type="text"
                      value={persetujuanPublikOleh}
                      onChange={(e) => {
                        setPersetujuanPublikOleh(e.target.value);
                        setPersetujuanTouched(true);
                      }}
                      placeholder="Contoh: Direktur Eksekutif Riset"
                      className={`block w-full py-2 px-3 border rounded-lg text-xs text-gray-900 bg-white focus:ring-emerald-600 focus:border-emerald-600 font-medium ${
                        persetujuanTouched && !persetujuanPublikOleh.trim()
                          ? 'border-red-500 bg-red-50/30 ring-1 ring-red-500'
                          : 'border-gray-300'
                      }`}
                    />
                    {persetujuanTouched && !persetujuanPublikOleh.trim() && (
                      <p className="text-[11px] text-red-600 mt-1 font-medium">
                        Nama pihak yang menyetujui wajib diisi.
                      </p>
                    )}
                  </div>

                  {/* Input: Alasan Persetujuan (min 10 karakter) */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label
                        htmlFor="textarea-persetujuan-alasan"
                        className="block text-xs font-bold text-gray-900"
                      >
                        Alasan Persetujuan <span className="text-red-600">* (Minimal 10 karakter)</span>
                      </label>
                      <span
                        className={`text-[11px] font-mono font-medium ${
                          persetujuanPublikAlasan.trim().length >= 10
                            ? 'text-emerald-700'
                            : 'text-amber-700'
                        }`}
                      >
                        {persetujuanPublikAlasan.trim().length} / 10 karakter
                      </span>
                    </div>
                    <textarea
                      id="textarea-persetujuan-alasan"
                      name="persetujuan_publik_alasan"
                      rows={2}
                      value={persetujuanPublikAlasan}
                      onChange={(e) => {
                        setPersetujuanPublikAlasan(e.target.value);
                        setPersetujuanTouched(true);
                      }}
                      placeholder="Tuliskan justifikasi persetujuan publikasi resmi (minimal 10 karakter)..."
                      className={`block w-full py-2 px-3 border rounded-lg text-xs text-gray-900 bg-white focus:ring-emerald-600 focus:border-emerald-600 font-medium ${
                        persetujuanTouched && persetujuanPublikAlasan.trim().length < 10
                          ? 'border-red-500 bg-red-50/30 ring-1 ring-red-500'
                          : 'border-gray-300'
                      }`}
                    />
                    {persetujuanTouched && persetujuanPublikAlasan.trim().length < 10 && (
                      <p className="text-[11px] text-red-600 mt-1 font-medium">
                        Alasan persetujuan wajib diisi minimal 10 karakter (kurang {Math.max(0, 10 - persetujuanPublikAlasan.trim().length)} karakter).
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 5. PEMILIHAN METODE ANALISIS */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-2xs space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                2. METODE ANALISIS REGULASI
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Tentukan pendekatan penelaahan naskah regulasi yang akan digunakan.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
            {/* Opsi Deterministik */}
            <div
              onClick={() => setSelectedMode('deterministik')}
              className={`p-4 rounded-xl border-2 transition cursor-pointer space-y-1.5 ${
                selectedMode === 'deterministik'
                  ? 'border-red-700 bg-red-50/20 shadow-xs'
                  : 'border-gray-200 bg-white hover:border-gray-300'
              }`}
            >
              <h3 className="text-sm font-bold text-gray-900">Mode Deterministik</h3>
              <p className="text-xs text-gray-600 leading-relaxed">
                Ekstraksi struktural pasal per pasal, pemetaan norma kewajiban, larangan, dan sanksi berdasarkan aturan hukum pasti tanpa risiko halusinasi.
              </p>
            </div>

            {/* Opsi AI */}
            <div
              onClick={() => {
                if (mlHealth?.mode_ai === true) {
                  setSelectedMode('ai');
                }
              }}
              className={`p-4 rounded-xl border-2 transition space-y-1.5 ${
                mlHealth?.mode_ai !== true
                  ? 'border-gray-200 bg-gray-50/70 opacity-60 cursor-not-allowed'
                  : selectedMode === 'ai'
                  ? 'border-red-700 bg-red-50/20 shadow-xs cursor-pointer'
                  : 'border-gray-200 bg-white hover:border-gray-300 cursor-pointer'
              }`}
            >
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-gray-900">Mode AI</h3>
                {mlHealth?.mode_ai !== true && (
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-gray-200 text-gray-700">
                    Belum tersedia
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-600 leading-relaxed">
                Penelaahan kontekstual berbasis pemahaman teks untuk intisari tematik dan perangkuman klausul kompleks.{' '}
                {mlHealth?.mode_ai !== true
                  ? 'Layanan model AI belum aktif pada mesin analisis.'
                  : 'Otomatis beralih ke Deterministik bila model AI offline.'}
              </p>
            </div>
          </div>
        </div>

        {/* Error Message Box (role="alert" dan auto-scroll) */}
        {uploadError && (
          <div
            ref={uploadErrorAlertRef}
            role="alert"
            className="p-3.5 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-start gap-2.5 animate-in fade-in"
          >
            <AlertCircle size={16} className="shrink-0 mt-0.5 text-red-700" />
            <div className="space-y-0.5">
              <span className="font-semibold block">Gagal Memproses Permintaan</span>
              <span>{uploadError}</span>
            </div>
          </div>
        )}

        {/* Banner Peringatan Persetujuan Publik */}
        {isDraftPublik && !isPersetujuanValid && (
          <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center text-amber-800 text-xs font-medium animate-in fade-in duration-200">
            <AlertCircle size={16} className="text-amber-600 mr-2 shrink-0" />
            <span>
              <strong>Perhatian:</strong> Draft kajian publik memerlukan nama pihak yang menyetujui dan alasan minimal 10 karakter sebelum analisis dapat dimulai.
            </span>
          </div>
        )}

        {/* Tombol Aksi Mulai Analisis */}
        <div className="pt-2 flex items-center justify-end">
          <button
            type="submit"
            disabled={!selectedFile || isUploading || isPollingActive || (isDraftPublik && !isPersetujuanValid)}
            className={`inline-flex items-center gap-2 px-6 py-2.5 rounded-lg text-xs font-semibold shadow-xs transition ${
              selectedFile && !isUploading && !isPollingActive && (!isDraftPublik || isPersetujuanValid)
                ? 'bg-red-700 hover:bg-red-800 text-white cursor-pointer'
                : 'bg-gray-200 text-gray-500 cursor-not-allowed'
            }`}
          >
            {isUploading ? (
              <>
                <Loader2 size={14} className="animate-spin text-gray-500" />
                <span>Mengunggah Berkas...</span>
              </>
            ) : isPollingActive ? (
              <>
                <Loader2 size={14} className="animate-spin text-gray-500" />
                <span>Memproses Ekstraksi...</span>
              </>
            ) : (
              <>
                <span>Mulai Analisis Regulasi</span>
                <ArrowRight size={14} />
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
