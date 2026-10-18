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
  X, 
  Activity
} from 'lucide-react';

import { 
  uploadDraftPdf, 
  getDocumentStatus, 
  checkMlHealth, 
  isDocumentReadyForAnalysis, 
  isDocumentProcessingFailed 
} from '../lib/analisaApi';
import type { 
  DocumentStatusResponse, 
  DraftUploadMetadata,
  MlHealthResponse
} from '../lib/analisaApi';
import { usePolling } from '../lib/usePolling';
import { ErrorState } from '../components/ErrorState';
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
  const [bidang, setBidang] = useState<string>('Perbankan');
  const [releaseDate, setReleaseDate] = useState<string>(
    new Date().toISOString().split('T')[0]
  );
  // Klasifikasi akses dokumen: 'publik' | 'non_publik' (Kepatuhan NDA)
  const [accessClassification, setAccessClassification] = useState<'publik' | 'non_publik'>('non_publik');

  // 4. State Layanan ML & Eksekusi Upload
  const [mlHealth, setMlHealth] = useState<MlHealthResponse | null>(null);
  const [mlHealthLoading, setMlHealthLoading] = useState<boolean>(true);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadedDocumentId, setUploadedDocumentId] = useState<number | null>(null);

  // 5. State Polling Kesiapan Dokumen
  const [isPollingActive, setIsPollingActive] = useState<boolean>(false);
  const [pollingTimeoutOccurred, setPollingTimeoutOccurred] = useState<boolean>(false);

  // Hook Polling Status Dokumen Backend (Interval 2s, Batas waktu ~5 menit / 300.000 ms)
  const documentPolling = usePolling<DocumentStatusResponse>({
    fn: (signal) => getDocumentStatus(uploadedDocumentId!, signal),
    isTerminal: (doc) => isDocumentReadyForAnalysis(doc) || isDocumentProcessingFailed(doc),
    interval: 2000,
    maxDuration: 300000,
    enabled: isPollingActive && uploadedDocumentId !== null && uploadedDocumentId > 0,
    onSuccess: (doc) => {
      setIsPollingActive(false);
      if (isDocumentReadyForAnalysis(doc)) {
        // Dokumen siap dianalisis: transisi ke State 2 Workspace via useSearchParams
        const effectiveMode = mlHealth?.mode_ai === true ? selectedMode : 'deterministik';
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

  // Hentikan dan bersihkan polling saat komponen dilepas (unmount)
  useEffect(() => {
    return () => {
      documentPolling.stop();
    };
  }, [documentPolling]);

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

  // Handler Submit Unggah Draf
  const handleSubmitUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setUploadError('Pilih berkas PDF draf regulasi terlebih dahulu.');
      return;
    }
    if (!title.trim()) {
      setUploadError('Judul draf regulasi wajib diisi.');
      return;
    }

    setUploadError(null);
    setIsUploading(true);
    setPollingTimeoutOccurred(false);

    try {
      const metadata: DraftUploadMetadata = {
        title: title.trim(),
        regulation_number: regulationNumber.trim() || undefined,
        regulation_type: regulationType.trim() || undefined,
        bidang: bidang.trim() || undefined,
        release_date: releaseDate.trim() || undefined,
        access_classification: accessClassification,
      };

      // Unggah via API client (access_classification='publik' | 'non_publik', document_role='draft_kajian')
      const result = await uploadDraftPdf(selectedFile, metadata);

      const docId = result.documentId;
      setUploadedDocumentId(docId);
      setIsUploading(false);

      // Mulai polling status pemrosesan dokumen di backend
      setIsPollingActive(true);
    } catch (err: unknown) {
      setIsUploading(false);
      const msg = err instanceof Error ? err.message : 'Terjadi kegagalan saat mengunggah berkas draf.';
      setUploadError(msg);
    }
  };

  // Handler Pembukaan Dokumen ke State 2
  const handleOpenWorkspace = (docId: number, mode: 'deterministik' | 'ai' = selectedMode) => {
    documentPolling.stop();
    setIsPollingActive(false);
    const effectiveMode = (mlHealth && mlHealth.mode_ai === false) ? 'deterministik' : mode;
    setSearchParams({
      documentId: String(docId),
      mode: effectiveMode,
    });
  };

  // Handler Kembali dari State 2 ke State 1
  const handleBackToState1 = () => {
    setSearchParams({});
    documentPolling.stop();
    setIsPollingActive(false);
    setUploadedDocumentId(null);
    setPollingTimeoutOccurred(false);
    checkHealthStatus();
  };

  // ============================================================================
  // TAMPILAN STATE 2: WORKSPACE TIGA PANEL (Jika documentId ada di URL)
  // ============================================================================
  if (activeDocumentId !== null) {
    return (
      <AnalisaState2Workspace
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

      {/* 3. MODUL PROGRES & POLLING UNGGAH DRAF (Aktif saat proses upload & ekstraksi berlangsung) */}
      {(isUploading || isPollingActive || pollingTimeoutOccurred) && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-gray-100">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-red-50 text-red-700 border border-red-100 flex items-center justify-center shrink-0">
                <Clock size={20} className="animate-spin text-red-700" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-gray-900">
                  {isUploading 
                    ? 'Mengunggah Berkas Draf Regulasi...' 
                    : 'Memproses Ekstraksi & Penelaahan Draf...'}
                </h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  Dokumen ID: #{uploadedDocumentId || '-'} • Klasifikasi: Non-Publik (Draf Kajian)
                </p>
              </div>
            </div>

            {uploadedDocumentId && (
              <span className="px-2.5 py-1 rounded-md bg-gray-100 text-gray-700 text-xs font-mono font-bold">
                Status: {documentPolling.data?.processing_status || 'diproses'}
              </span>
            )}
          </div>

          {/* Stepper Status Progress */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className={`p-3 rounded-lg border flex items-center gap-2.5 ${
              uploadedDocumentId 
                ? 'border-emerald-200 bg-emerald-50/50 text-emerald-800' 
                : 'border-red-200 bg-red-50/40 text-red-800 font-semibold'
            }`}>
              <CheckCircle2 size={16} className={uploadedDocumentId ? 'text-emerald-600' : 'text-red-700 animate-pulse'} />
              <span>1. Unggah PDF Non-Publik</span>
            </div>

            <div className={`p-3 rounded-lg border flex items-center gap-2.5 ${
              documentPolling.data?.processing_status === 'terindeks' || documentPolling.data?.processing_status === 'perlu_koreksi'
                ? 'border-emerald-200 bg-emerald-50/50 text-emerald-800'
                : uploadedDocumentId
                ? 'border-red-200 bg-red-50/40 text-red-800 font-semibold'
                : 'border-gray-200 bg-gray-50 text-gray-400'
            }`}>
              <Clock size={16} className={uploadedDocumentId ? 'text-red-700 animate-spin' : 'text-gray-400'} />
              <span>2. Ekstraksi Teks &amp; Pasal Backend</span>
            </div>

            <div className={`p-3 rounded-lg border flex items-center gap-2.5 ${
              documentPolling.data?.processing_status === 'terindeks'
                ? 'border-emerald-200 bg-emerald-50/50 text-emerald-800'
                : 'border-gray-200 bg-gray-50 text-gray-400'
            }`}>
              <Sparkles size={16} className="text-gray-400" />
              <span>3. Kesiapan Analisis ML</span>
            </div>
          </div>

          {/* Detail Ekstraksi Terkini */}
          {documentPolling.data && (
            <div className="p-3 bg-gray-50 border border-gray-100 rounded-lg text-xs text-gray-600 flex flex-wrap items-center justify-between gap-2">
              <span>
                Pasal terdeteksi: <strong>{documentPolling.data.articles?.length || 0} pasal</strong> • 
                Teks lengkap: <strong>{documentPolling.data.full_text_length || 0} karakter</strong>
              </span>
              <span className="font-mono text-[11px] text-gray-500">
                Memperbarui setiap 2 detik...
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
          {!selectedFile ? (
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 text-center transition cursor-pointer flex flex-col items-center justify-center space-y-3 ${
                isDragging 
                  ? 'border-red-600 bg-red-50/60' 
                  : 'border-red-200 bg-red-50/15 hover:border-red-400 hover:bg-red-50/30'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                onChange={handleFileInputChange}
                className="hidden"
              />
              <div className="w-12 h-12 rounded-full bg-red-100 text-red-700 flex items-center justify-center">
                <UploadCloud size={24} />
              </div>
              <div>
                <p className="text-xs font-bold text-gray-800">
                  Tarik dan lepaskan berkas PDF draf regulasi ke sini, atau <span className="text-red-700 underline font-semibold">pilih dari komputer</span>
                </p>
                <p className="text-[11px] text-gray-400 mt-1">
                  Format wajib: Dokumen PDF (.pdf) • Batas maksimum ukuran: 100 MB
                </p>
              </div>
            </div>
          ) : (
            <div className="p-4 rounded-xl border border-red-200 bg-red-50/30 flex items-center justify-between">
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-10 h-10 rounded-lg bg-red-100 text-red-700 flex items-center justify-center shrink-0">
                  <FileText size={20} />
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-bold text-gray-900 truncate">{selectedFile.name}</p>
                  <p className="text-[11px] text-gray-500">
                    {(selectedFile.size / 1024 / 1024).toFixed(2)} MB • Dokumen PDF Terverifikasi
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={handleRemoveFile}
                className="p-1.5 rounded-lg text-gray-400 hover:text-red-700 hover:bg-red-100/60 transition cursor-pointer"
                title="Ganti berkas"
              >
                <X size={16} />
              </button>
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
                Nomor Regulasi (Draf / Rujukan)
              </label>
              <input
                type="text"
                value={regulationNumber}
                onChange={(e) => setRegulationNumber(e.target.value)}
                placeholder="Contoh: POJK No. 11/POJK.03/2024"
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
              <label className="text-xs font-bold text-gray-700">
                Sektor / Bidang Regulasi
              </label>
              <select
                value={bidang}
                onChange={(e) => setBidang(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-white border border-gray-200 rounded-lg focus:outline-none focus:border-red-700 focus:ring-1 focus:ring-red-700 transition"
              >
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
                      Dokumen regulasi terbuka untuk umum. Dapat langsung dianalisis tanpa login.
                    </span>
                  </div>
                </button>
              </div>
            </div>
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

        {/* Error Message Box */}
        {uploadError && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-start gap-2">
            <AlertCircle size={15} className="shrink-0 mt-0.5" />
            <span>{uploadError}</span>
          </div>
        )}

        {/* Tombol Aksi Mulai Analisis */}
        <div className="pt-2 flex items-center justify-end">
          <button
            type="submit"
            disabled={!selectedFile || isUploading || isPollingActive}
            className={`inline-flex items-center gap-2 px-6 py-2.5 rounded-lg text-xs font-semibold shadow-xs transition cursor-pointer ${
              selectedFile && !isUploading && !isPollingActive
                ? 'bg-red-700 hover:bg-red-800 text-white'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed'
            }`}
          >
            <span>Mulai Analisis Regulasi</span>
            <ArrowRight size={14} />
          </button>
        </div>
      </form>
    </div>
  );
}
