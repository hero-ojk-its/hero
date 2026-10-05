import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { 
  FolderOpen, 
  Cloud, 
  Database, 
  ArrowRight, 
  Loader2, 
  AlertCircle, 
  RefreshCw, 
  Info, 
  XCircle,
  FolderCheck
} from 'lucide-react';
import { 
  getFolderOptions,
  createScrapingSource,
  createScan,
  getScan,
  cancelScan,
  getScanCandidates,
  updateScanSelection,
  startScanPull,
  getCategories,
  type FolderOptionItem,
  type CategoryDetailResponse,
  type ScanSessionResponse,
  type CandidateResponse,
  type RejectedSelection,
  type KlasifikasiAkses
} from '../../lib/ingestApi';
import { usePolling } from '../../lib/usePolling';
import CandidateTable from './components/CandidateTable';
import NamingFormatPicker from './components/NamingFormatPicker';
import PullResultSummary from './components/PullResultSummary';
import JobHistory from './components/JobHistory';
import { getStatusPindaiLabel } from './labels';

export default function RealSyncTab() {
  // Steps: 1 (Config) -> 2 (Scanning & Candidate Selection) -> 3 (Pulling) -> 4 (Result)
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [sourceType, setSourceType] = useState<'folder' | 'onedrive'>('folder');

  // Folder options state
  const [folderOptions, setFolderOptions] = useState<FolderOptionItem[]>([]);
  const [selectedFolder, setSelectedFolder] = useState<FolderOptionItem | null>(null);
  const [isLoadingFolders, setIsLoadingFolders] = useState<boolean>(true);
  const [foldersError, setFoldersError] = useState<string | null>(null);

  // Configuration state
  const [accessClassification, setAccessClassification] = useState<KlasifikasiAkses>('publik');
  const [categories, setCategories] = useState<CategoryDetailResponse[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | null>(null);
  const [namingFormat, setNamingFormat] = useState<string[]>(['nomor', 'nama', 'tahun']);
  const [namingSeparator, setNamingSeparator] = useState<string>(' ');

  // Scan Session state
  const [activeScanId, setActiveScanId] = useState<number | null>(null);
  const [manualScanSession, setManualScanSession] = useState<ScanSessionResponse | null>(null);
  const [isScanInitiating, setIsScanInitiating] = useState<boolean>(false);
  const [scanInitError, setScanInitError] = useState<string | null>(null);

  // Candidate Table state (Step 2)
  const [candidates, setCandidates] = useState<CandidateResponse[]>([]);
  const [candidateTotal, setCandidateTotal] = useState<number>(0);
  const [candidateSkip, setCandidateSkip] = useState<number>(0);
  const candidateLimit = 20;
  const [matchTab, setMatchTab] = useState<string>('all');
  const [docKindFilter, setDocKindFilter] = useState<string>('utama');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [debouncedSearch, setDebouncedSearch] = useState<string>('');
  const [isLoadingCandidates, setIsLoadingCandidates] = useState<boolean>(false);
  const [isUpdatingSelection, setIsUpdatingSelection] = useState<boolean>(false);
  const [rejectedSelections, setRejectedSelections] = useState<RejectedSelection[]>([]);

  // Pulling execution state (Step 3)
  const [isPullInitiating, setIsPullInitiating] = useState<boolean>(false);
  const [isPullRunning, setIsPullRunning] = useState<boolean>(false);
  const [pullError, setPullError] = useState<string | null>(null);

  // --------------------------------------------------------------------------
  // 1. Load Initial Folder Options & Categories
  // --------------------------------------------------------------------------
  const refetchFolderOptions = useCallback(() => {
    setIsLoadingFolders(true);
    setFoldersError(null);
    getFolderOptions()
      .then((res) => {
        setFolderOptions(res.items);
        if (res.items.length > 0) {
          setSelectedFolder((prev) => {
            if (!prev) return res.items[0];
            const exists = res.items.find((item) => item.path === prev.path);
            return exists || res.items[0];
          });
        }
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        setFoldersError(msg || 'Gagal memuat opsi folder lokal dari server.');
      })
      .finally(() => {
        setIsLoadingFolders(false);
      });
  }, []);

  useEffect(() => {
    let mounted = true;
    getFolderOptions()
      .then((res) => {
        if (!mounted) return;
        setFolderOptions(res.items);
        if (res.items.length > 0) {
          setSelectedFolder(res.items[0]);
        }
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        const msg = err instanceof Error ? err.message : String(err);
        setFoldersError(msg || 'Gagal memuat opsi folder lokal dari server.');
      })
      .finally(() => {
        if (mounted) setIsLoadingFolders(false);
      });

    getCategories()
      .then((cats) => {
        if (!mounted) return;
        setCategories(cats);
        if (cats.length > 0) {
          setSelectedCategoryId((prev) => (prev === null ? cats[0].id : prev));
        }
      })
      .catch((err) => console.warn('Gagal memuat kategori:', err));

    return () => {
      mounted = false;
    };
  }, []);

  // Debounce search query
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearch(searchQuery);
      setCandidateSkip(0);
    }, 300);
    return () => clearTimeout(handler);
  }, [searchQuery]);

  // --------------------------------------------------------------------------
  // 2. Polling Scan Session during Step 2
  // --------------------------------------------------------------------------
  const isScanTerminal = useCallback((data: ScanSessionResponse | null): boolean => {
    if (!data) return false;
    return (
      data.status === 'siap_dipilih' ||
      data.status === 'selesai' ||
      data.status === 'gagal' ||
      data.status === 'dibatalkan'
    );
  }, []);

  const scanPolling = usePolling<ScanSessionResponse>({
    fn: (signal) => {
      if (!activeScanId) throw new Error('No active scan ID');
      return getScan(activeScanId, signal);
    },
    isTerminal: isScanTerminal,
    interval: 2000,
    enabled: Boolean(activeScanId && step === 2),
    onSuccess: (data) => {
      setManualScanSession(data);
    },
    onError: (err) => {
      console.error('Scan polling error:', err);
    },
    maxConsecutiveErrors: 3,
  });

  // --------------------------------------------------------------------------
  // 3. Polling Pull Progress during Step 3
  // --------------------------------------------------------------------------
  const isPullTerminal = useCallback((data: ScanSessionResponse | null): boolean => {
    if (!data) return false;
    return (
      data.status === 'selesai' ||
      data.status === 'gagal' ||
      data.status === 'dibatalkan'
    );
  }, []);

  const pullPolling = usePolling<ScanSessionResponse>({
    fn: (signal) => {
      if (!activeScanId) throw new Error('No active scan ID');
      return getScan(activeScanId, signal);
    },
    isTerminal: isPullTerminal,
    interval: 2000,
    enabled: Boolean(activeScanId && step === 3 && isPullRunning),
    onSuccess: (data) => {
      setManualScanSession(data);
      if (data.status === 'selesai') {
        setIsPullRunning(false);
        // Load all final candidates with pull outcome
        getScanCandidates(data.id, { limit: 100 }).then((res) => {
          setCandidates(res.items || []);
          setStep(4);
        });
      }
    },
    onError: (err) => {
      console.error('Pull polling error:', err);
    },
    maxConsecutiveErrors: 3,
  });

  const scanSession = (step === 3 ? pullPolling.data : scanPolling.data) || manualScanSession;
  const setScanSession = useCallback((session: ScanSessionResponse | null) => {
    setManualScanSession(session);
  }, []);

  // --------------------------------------------------------------------------
  // 4. Load Candidates when scan session is ready
  // --------------------------------------------------------------------------
  const loadCandidates = useCallback(async () => {
    if (!activeScanId) return;
    setIsLoadingCandidates(true);
    try {
      const res = await getScanCandidates(activeScanId, {
        skip: candidateSkip,
        limit: candidateLimit,
        match_status: matchTab === 'all' ? undefined : matchTab,
        doc_kind: docKindFilter === 'all' ? undefined : docKindFilter,
        q: debouncedSearch.trim() || undefined,
      });
      setCandidates(res.items || []);
      setCandidateTotal(res.total || 0);
    } catch (err) {
      console.warn('Gagal memuat kandidat:', err);
    } finally {
      setIsLoadingCandidates(false);
    }
  }, [activeScanId, candidateSkip, candidateLimit, matchTab, docKindFilter, debouncedSearch]);

  useEffect(() => {
    if (!activeScanId || step !== 2) return;
    const status = scanSession?.status;
    if (status !== 'siap_dipilih' && status !== 'selesai' && status !== 'dibatalkan') return;

    let mounted = true;
    getScanCandidates(activeScanId, {
      skip: candidateSkip,
      limit: candidateLimit,
      match_status: matchTab === 'all' ? undefined : matchTab,
      doc_kind: docKindFilter === 'all' ? undefined : docKindFilter,
      q: debouncedSearch.trim() || undefined,
    })
      .then((res) => {
        if (!mounted) return;
        setCandidates(res.items || []);
        setCandidateTotal(res.total || 0);
        setIsLoadingCandidates(false);
      })
      .catch((err) => {
        if (!mounted) return;
        console.warn('Gagal memuat kandidat:', err);
        setIsLoadingCandidates(false);
      });

    return () => {
      mounted = false;
    };
  }, [activeScanId, step, scanSession?.status, candidateSkip, candidateLimit, matchTab, docKindFilter, debouncedSearch]);

  // --------------------------------------------------------------------------
  // Start Scan Flow (Step 1 -> 2)
  // --------------------------------------------------------------------------
  const handleStartScan = async () => {
    if (!selectedFolder) {
      setScanInitError('Pilih salah satu folder lokal terlebih dahulu.');
      return;
    }

    setIsScanInitiating(true);
    setScanInitError(null);
    setRejectedSelections([]);

    try {
      let sourceId = selectedFolder.already_registered_source_id;

      // US-16 / TC-05: Bila folder belum terdaftar, buat sumber scraping bertipe folder_lokal
      if (!sourceId) {
        const newSource = await createScrapingSource({
          name: selectedFolder.name,
          url: selectedFolder.path,
          source_type: 'folder_lokal',
          default_access_classification: accessClassification,
          default_document_role: 'corpus_eksisting',
          recursive: true,
          is_active: true,
          default_naming_format: namingFormat.length > 0 ? namingFormat : undefined,
          default_naming_separator: namingSeparator || ' ',
        });
        sourceId = newSource.id;
        setSelectedFolder({
          ...selectedFolder,
          already_registered_source_id: sourceId,
        });
      }

      // Buat sesi pemindaian baru
      const res = await createScan({
        source_id: sourceId,
      });

      setActiveScanId(res.scan_id);
      setStep(2);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setScanInitError(msg || 'Gagal memulai pemindaian folder lokal.');
    } finally {
      setIsScanInitiating(false);
    }
  };

  const handleCancelScan = async () => {
    if (!activeScanId) return;
    try {
      const res = await cancelScan(activeScanId);
      setScanSession(res);
    } catch (err) {
      console.error('Gagal membatalkan pemindaian:', err);
    }
  };

  // --------------------------------------------------------------------------
  // Candidate Selection Handlers (Step 2)
  // --------------------------------------------------------------------------
  const handleToggleCandidate = async (cand: CandidateResponse) => {
    if (!activeScanId) return;
    setIsUpdatingSelection(true);
    try {
      const res = await updateScanSelection(activeScanId, {
        action: 'set',
        candidate_ids: [cand.id],
        selected: !cand.selected,
      });

      setCandidates((prev) =>
        prev.map((c) => (c.id === cand.id ? { ...c, selected: !cand.selected } : c))
      );

      if (scanSession) {
        setScanSession({
          ...scanSession,
          candidates_summary: res.summary,
        });
      }

      if (res.rejected_ids && res.rejected_ids.length > 0) {
        setRejectedSelections(res.rejected_ids);
      }
    } catch (err) {
      console.error('Gagal memperbarui centang kandidat:', err);
    } finally {
      setIsUpdatingSelection(false);
    }
  };

  const handleSelectAllNew = async () => {
    if (!activeScanId) return;
    setIsUpdatingSelection(true);
    try {
      const res = await updateScanSelection(activeScanId, {
        action: 'select_all_new',
      });

      await loadCandidates();

      if (scanSession) {
        setScanSession({
          ...scanSession,
          candidates_summary: res.summary,
        });
      }

      if (res.rejected_ids && res.rejected_ids.length > 0) {
        setRejectedSelections(res.rejected_ids);
      }
    } catch (err) {
      console.error('Gagal memilih semua baru:', err);
    } finally {
      setIsUpdatingSelection(false);
    }
  };

  const handleSelectNone = async () => {
    if (!activeScanId) return;
    setIsUpdatingSelection(true);
    try {
      const res = await updateScanSelection(activeScanId, {
        action: 'select_none',
      });

      await loadCandidates();

      if (scanSession) {
        setScanSession({
          ...scanSession,
          candidates_summary: res.summary,
        });
      }
      setRejectedSelections([]);
    } catch (err) {
      console.error('Gagal menghapus centang:', err);
    } finally {
      setIsUpdatingSelection(false);
    }
  };

  // --------------------------------------------------------------------------
  // Start Pull Flow (Step 2 -> 3 -> 4)
  // --------------------------------------------------------------------------
  const handleProceedToPull = () => {
    setStep(3);
  };

  const handleExecutePull = async () => {
    if (!activeScanId) return;
    setIsPullInitiating(true);
    setPullError(null);

    try {
      await startScanPull(
        activeScanId,
        {
          destination: 'knowledge_base', // Folder lokal hanya boleh masuk Knowledge Base (G05)
          category_id: selectedCategoryId || null,
          naming_format: namingFormat.length > 0 ? namingFormat : null,
          naming_separator: namingSeparator || ' ',
        },
        false // asynchronous (wait=false)
      );

      setIsPullRunning(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setPullError(msg || 'Gagal memulai penarikan dokumen ke Knowledge Base');
    } finally {
      setIsPullInitiating(false);
    }
  };

  // Reset to Step 1
  const handleResetFlow = () => {
    setStep(1);
    setActiveScanId(null);
    setManualScanSession(null);
    setCandidates([]);
    setCandidateTotal(0);
    setCandidateSkip(0);
    setPullError(null);
    setIsPullRunning(false);
    refetchFolderOptions();
  };

  // --------------------------------------------------------------------------
  // RENDER STEP 1: Konfigurasi Parameter Sinkronisasi
  // --------------------------------------------------------------------------
  if (step === 1) {
    return (
      <div className="space-y-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
          <div className="mb-6">
            <h3 className="text-lg font-bold text-gray-900">Parameter Sinkronisasi Folder Lokal</h3>
            <p className="text-gray-600 text-sm mt-1">
              Pilih folder lokal yang terpasang di direktori server untuk memindai berkas regulasi PDF.
            </p>
          </div>

          {scanInitError && (
            <div className="mb-5 p-3.5 bg-red-50 border border-red-200 rounded-xl flex items-start text-xs text-red-700">
              <AlertCircle size={16} className="text-red-600 mr-2 shrink-0 mt-0.5" />
              <span>{scanInitError}</span>
            </div>
          )}

          <div className="space-y-6">
            {/* SUMBER DOKUMEN (Folder Lokal / OneDrive) */}
            <div>
              <label className="block text-xs font-bold text-gray-900 mb-3 uppercase tracking-wider">
                Sumber Dokumen <span className="text-red-600">*</span>
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Card 1: Folder Lokal */}
                <div 
                  className={`border-2 rounded-xl p-4 cursor-pointer flex items-start transition-all ${
                    sourceType === 'folder' 
                      ? 'bg-[#FDF2F2] border-[#B91C1C] shadow-sm' 
                      : 'bg-white border-gray-200 hover:border-gray-300'
                  }`}
                  onClick={() => setSourceType('folder')}
                >
                  <div className="mr-3.5 mt-0.5">
                    <div className={`w-4 h-4 rounded-full border flex items-center justify-center ${
                      sourceType === 'folder' ? 'border-[#B91C1C] bg-[#B91C1C]' : 'border-gray-300'
                    }`}>
                      {sourceType === 'folder' && <div className="w-1.5 h-1.5 bg-white rounded-full"></div>}
                    </div>
                  </div>
                  <FolderOpen size={24} className={`mr-3 mt-0.5 shrink-0 ${sourceType === 'folder' ? 'text-[#B91C1C]' : 'text-gray-500'}`} />
                  <div className="flex-1">
                    <div className="font-bold text-sm text-gray-900">Folder Lokal</div>
                    <div className="text-xs text-gray-500 mt-0.5">Penyimpanan Direktori Server</div>
                  </div>
                </div>
                
                {/* Card 2: OneDrive */}
                <div 
                  className={`border-2 rounded-xl p-4 cursor-pointer flex items-start transition-all ${
                    sourceType === 'onedrive' 
                      ? 'bg-amber-50/70 border-amber-500 shadow-sm' 
                      : 'bg-white border-gray-200 hover:border-gray-300'
                  }`}
                  onClick={() => setSourceType('onedrive')}
                >
                  <div className="mr-3.5 mt-0.5">
                    <div className={`w-4 h-4 rounded-full border flex items-center justify-center ${
                      sourceType === 'onedrive' ? 'border-amber-600 bg-amber-600' : 'border-gray-300'
                    }`}>
                      {sourceType === 'onedrive' && <div className="w-1.5 h-1.5 bg-white rounded-full"></div>}
                    </div>
                  </div>
                  <Cloud size={24} className={`mr-3 mt-0.5 shrink-0 ${sourceType === 'onedrive' ? 'text-amber-700' : 'text-gray-400'}`} />
                  <div className="flex-1">
                    <span className="font-bold text-sm text-gray-800">OneDrive</span>
                    <div className="text-xs text-gray-500 mt-0.5">Cloud Storage (DPEA)</div>
                  </div>
                </div>
              </div>

              {/* Petunjuk OneDrive sesuai G1.4 */}
              {sourceType === 'onedrive' && (
                <div className="mt-4 p-4 bg-amber-50 border border-amber-200 text-amber-900 rounded-xl text-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 animate-in fade-in duration-200">
                  <div className="flex items-start space-x-2.5">
                    <Info size={18} className="text-amber-700 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-bold text-amber-950 text-sm">Petunjuk Sinkronisasi OneDrive</p>
                      <p className="text-amber-800 mt-0.5">
                        Untuk OneDrive, gunakan tab <strong className="font-semibold underline">Scraping URL</strong> dan pilih sumber OneDrive.
                      </p>
                    </div>
                  </div>
                  <Link 
                    to="/ingest?tab=scraping" 
                    className="shrink-0 px-4 py-2 bg-amber-700 hover:bg-amber-800 text-white font-semibold rounded-lg text-xs flex items-center transition-colors shadow-sm"
                  >
                    Buka Scraping URL
                    <ArrowRight size={14} className="ml-1.5" />
                  </Link>
                </div>
              )}
            </div>

            {/* DAFTAR FOLDER LOKAL (G01 / TC-05) */}
            {sourceType === 'folder' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <label className="block text-xs font-bold text-gray-900 uppercase tracking-wider">
                    Pilih Folder Lokal di Server <span className="text-red-600">*</span>
                  </label>
                  <button
                    type="button"
                    onClick={refetchFolderOptions}
                    disabled={isLoadingFolders}
                    className="text-xs font-semibold text-gray-600 hover:text-red-700 flex items-center gap-1 transition-colors cursor-pointer"
                  >
                    <RefreshCw size={13} className={isLoadingFolders ? 'animate-spin text-red-700' : ''} />
                    Segarkan
                  </button>
                </div>

                {isLoadingFolders ? (
                  <div className="p-8 border border-gray-200 rounded-xl bg-gray-50 flex flex-col items-center justify-center text-sm text-gray-500">
                    <Loader2 size={24} className="animate-spin text-red-700 mb-2" />
                    <span>Memuat daftar opsi folder lokal...</span>
                  </div>
                ) : foldersError ? (
                  <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-start gap-2">
                    <AlertCircle size={16} className="text-red-600 shrink-0 mt-0.5" />
                    <span>{foldersError}</span>
                  </div>
                ) : folderOptions.length === 0 ? (
                  <div className="p-6 border border-dashed border-gray-300 rounded-xl text-center text-sm text-gray-500">
                    Tidak ditemukan subfolder berisi PDF di direktori <code>sources/</code>.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                    {folderOptions.map((folder) => {
                      const isSelected = selectedFolder?.path === folder.path;
                      const isRegistered = Boolean(folder.already_registered_source_id);

                      return (
                        <div
                          key={folder.path}
                          onClick={() => setSelectedFolder(folder)}
                          className={`p-4 rounded-xl border-2 cursor-pointer transition-all flex flex-col justify-between ${
                            isSelected
                              ? 'bg-red-50/50 border-red-700 shadow-sm'
                              : 'bg-white border-gray-200 hover:border-gray-300 hover:bg-gray-50/50'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex items-start gap-2.5">
                              <div className={`p-2 rounded-lg shrink-0 mt-0.5 ${
                                isSelected ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'
                              }`}>
                                <FolderOpen size={20} />
                              </div>
                              <div>
                                <div className="font-bold text-sm text-gray-900 leading-snug">
                                  {folder.name}
                                </div>
                                <div className="text-xs font-mono text-gray-500 mt-1 break-all">
                                  {folder.path}
                                </div>
                              </div>
                            </div>

                            <div className="shrink-0 text-right">
                              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold bg-gray-100 text-gray-700">
                                {folder.pdf_count} PDF
                              </span>
                            </div>
                          </div>

                          <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between text-xs">
                            {isRegistered ? (
                              <span className="inline-flex items-center gap-1 text-emerald-700 font-semibold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200/60">
                                <FolderCheck size={13} />
                                Terdaftar (ID: #{folder.already_registered_source_id})
                              </span>
                            ) : (
                              <span className="text-gray-400 italic">
                                Belum terdaftar (akan otomatis didaftarkan)
                              </span>
                            )}

                            <span className={`text-xs font-bold ${isSelected ? 'text-red-700' : 'text-gray-400'}`}>
                              {isSelected ? 'Terpilih' : 'Pilih'}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* KLASIFIKASI AKSES & KATEGORI TARGET */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-4 border-t border-gray-100">
                  {/* Klasifikasi Akses */}
                  <div>
                    <label className="block text-xs font-bold text-gray-900 mb-1.5 uppercase tracking-wider">
                      Klasifikasi Akses Dokumen <span className="text-red-600">*</span>
                    </label>
                    <select
                      value={accessClassification}
                      onChange={(e) => setAccessClassification(e.target.value as KlasifikasiAkses)}
                      className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
                    >
                      <option value="publik">Publik (Dapat Diakses Terbuka)</option>
                      <option value="non_publik">Non-Publik (Internal Terbatas)</option>
                    </select>
                    <p className="text-xs text-gray-500 mt-1 italic">
                      Dokumen Non-Publik belum dapat dibuka PDF-nya sampai fitur login aktif (Fase 2).
                    </p>
                  </div>

                  {/* Kategori Target di Knowledge Base */}
                  <div>
                    <label className="block text-xs font-bold text-gray-900 mb-1.5 uppercase tracking-wider">
                      Kategori Target Knowledge Base <span className="text-red-600">*</span>
                    </label>
                    <select
                      value={selectedCategoryId ?? ''}
                      onChange={(e) => setSelectedCategoryId(Number(e.target.value))}
                      className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
                    >
                      {categories.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-gray-500 mt-1">
                      Folder/koleksi tujuan penempatan dokumen di repositori Knowledge Base.
                    </p>
                  </div>
                </div>

                {/* Format Penamaan Berkas Standar */}
                <div className="pt-4 border-t border-gray-100">
                  <NamingFormatPicker
                    value={namingFormat}
                    onChange={setNamingFormat}
                    separator={namingSeparator}
                    onSeparatorChange={setNamingSeparator}
                  />
                </div>

                {/* Catatan Tujuan Penarikan (G05: Tujuan Hanya KB, tidak ada ZIP) */}
                <div className="p-4 bg-gray-50 border border-gray-200 rounded-xl flex items-start gap-3 text-xs text-gray-700">
                  <Database size={20} className="text-red-700 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold text-gray-900 text-sm block">Tujuan Penarikan: Knowledge Base</span>
                    <span className="text-gray-600 mt-0.5 block">
                      Berkas PDF dari folder lokal akan langsung dimasukkan ke repositori Knowledge Base sesuai kategori yang dipilih.
                      Opsi arsip ZIP tidak disediakan untuk sumber folder lokal karena berkas sudah berada di filesystem lokal.
                    </span>
                  </div>
                </div>

                {/* Tombol Mulai Pindai */}
                <div className="flex justify-end pt-4 border-t border-gray-100">
                  <button
                    type="button"
                    onClick={handleStartScan}
                    disabled={!selectedFolder || isScanInitiating}
                    className="px-6 py-2.5 bg-red-700 hover:bg-red-800 text-white font-semibold text-sm rounded-lg shadow-sm transition-all flex items-center disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                  >
                    {isScanInitiating ? (
                      <>
                        <Loader2 size={16} className="animate-spin mr-2" />
                        Memulai Pemindaian...
                      </>
                    ) : (
                      <>
                        Mulai Pindai Folder
                        <ArrowRight size={16} className="ml-2" />
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Riwayat Job Ingest Terakhir */}
        <JobHistory />
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // RENDER STEP 2: Pemindaian & Pemilihan Kandidat
  // --------------------------------------------------------------------------
  if (step === 2) {
    const isScanReady = scanSession?.status === 'siap_dipilih';
    const isScanning = scanSession?.status === 'memindai' || scanSession?.status === 'antrian';
    const isScanFailed = scanSession?.status === 'gagal';
    const isScanCancelled = scanSession?.status === 'dibatalkan';

    return (
      <div className="space-y-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-in fade-in duration-300">
          {/* Header Sesi Pemindaian */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-gray-100 gap-4">
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-gray-900 text-base">
                  Pemindaian Folder: {selectedFolder?.name}
                </span>
                <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-gray-100 text-gray-700">
                  {getStatusPindaiLabel(scanSession?.status)}
                </span>
              </div>
              <p className="text-xs text-gray-500 font-mono mt-1">
                {selectedFolder?.path}
              </p>
            </div>

            <div className="flex items-center space-x-3">
              {isScanning && (
                <button
                  type="button"
                  onClick={handleCancelScan}
                  className="px-3.5 py-1.5 border border-red-200 text-red-700 hover:bg-red-50 text-xs font-semibold rounded-lg transition-colors flex items-center"
                >
                  <XCircle size={14} className="mr-1.5" />
                  Batalkan Pemindaian
                </button>
              )}
            </div>
          </div>

          {/* Banner Progres Pemindaian */}
          {isScanning && (
            <div className="my-5 p-5 bg-red-50/50 border border-red-100 rounded-xl">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-red-900 flex items-center">
                  <Loader2 size={16} className="animate-spin text-red-700 mr-2" />
                  Membaca berkas PDF dalam folder lokal...
                </span>
                <span className="text-xs font-mono text-red-700">
                  {scanSession?.candidates_summary?.total ?? 0} berkas terdeteksi
                </span>
              </div>
              <div className="w-full bg-red-100 rounded-full h-2 overflow-hidden">
                <div className="bg-red-700 h-2 rounded-full w-2/3 animate-pulse"></div>
              </div>
            </div>
          )}

          {/* Banner Galat */}
          {isScanFailed && (
            <div className="my-5 p-4 bg-red-50 border border-red-200 rounded-xl flex items-start text-xs text-red-700">
              <AlertCircle size={16} className="text-red-600 mr-2.5 shrink-0 mt-0.5" />
              <div>
                <p className="font-bold text-sm">Pemindaian Gagal</p>
                <p className="mt-0.5">{scanSession?.error_message || 'Terjadi kesalahan saat membaca folder lokal.'}</p>
              </div>
            </div>
          )}

          {/* Tabel Kandidat (Langkah 2b) */}
          {(isScanReady || (isScanCancelled && (scanSession?.candidates_summary?.total ?? 0) > 0)) && (
            <div className="pt-4">
              <CandidateTable
                candidates={candidates}
                summary={scanSession?.candidates_summary}
                total={candidateTotal}
                skip={candidateSkip}
                limit={candidateLimit}
                onPageChange={(newSkip) => setCandidateSkip(newSkip)}
                activeMatchTab={matchTab}
                onMatchTabChange={(t) => {
                  setMatchTab(t);
                  setCandidateSkip(0);
                }}
                docKindFilter={docKindFilter}
                onDocKindFilterChange={(k) => {
                  setDocKindFilter(k);
                  setCandidateSkip(0);
                }}
                searchQuery={searchQuery}
                onSearchChange={setSearchQuery}
                onToggleCandidate={handleToggleCandidate}
                onSelectAllNew={handleSelectAllNew}
                onSelectNone={handleSelectNone}
                isLoading={isLoadingCandidates}
                isUpdatingSelection={isUpdatingSelection}
                rejectedSelections={rejectedSelections}
              />
            </div>
          )}

          {/* Footer Back & Proceed Button */}
          <div className="flex justify-between items-center pt-5 border-t border-gray-100 mt-6">
            <button
              type="button"
              onClick={handleResetFlow}
              className="px-4 py-2 border border-gray-300 rounded-lg text-xs font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Kembali ke Konfigurasi
            </button>

            {isScanReady && (
              <button
                type="button"
                disabled={Boolean(
                  !scanSession?.candidates_summary || scanSession.candidates_summary.terpilih === 0
                )}
                onClick={handleProceedToPull}
                className="px-5 py-2.5 bg-red-700 hover:bg-red-800 text-white font-semibold text-xs rounded-lg shadow-sm transition-all flex items-center disabled:opacity-50 cursor-pointer"
              >
                Lanjut ke Penarikan ({scanSession?.candidates_summary?.terpilih ?? 0})
                <ArrowRight size={14} className="ml-1.5" />
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // RENDER STEP 3: Konfirmasi & Eksekusi Penarikan Dokumen ke KB
  // --------------------------------------------------------------------------
  if (step === 3) {
    const selectedCount = scanSession?.candidates_summary?.terpilih ?? candidates.filter((c) => c.selected).length;
    const targetCat = categories.find((c) => c.id === selectedCategoryId);

    return (
      <div className="space-y-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-in fade-in duration-300">
          <div className="mb-6">
            <h3 className="text-lg font-bold text-gray-900">Konfirmasi Penarikan ke Knowledge Base</h3>
            <p className="text-gray-600 text-sm mt-1">
              Periksa ringkasan berkas yang akan ditarik ke dalam repositori Knowledge Base.
            </p>
          </div>

          {pullError && (
            <div className="mb-5 p-3.5 bg-red-50 border border-red-200 rounded-xl flex items-start text-xs text-red-700">
              <AlertCircle size={16} className="text-red-600 mr-2 shrink-0 mt-0.5" />
              <span>{pullError}</span>
            </div>
          )}

          {/* Kartu Ringkasan Konfigurasi */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="p-4 bg-gray-50 border border-gray-200 rounded-xl">
              <span className="text-xs font-bold text-gray-500 uppercase tracking-wider block">Folder Sumber</span>
              <span className="font-bold text-sm text-gray-900 mt-1 block">{selectedFolder?.name}</span>
              <span className="text-xs font-mono text-gray-500 mt-0.5 block truncate">{selectedFolder?.path}</span>
            </div>

            <div className="p-4 bg-gray-50 border border-gray-200 rounded-xl">
              <span className="text-xs font-bold text-gray-500 uppercase tracking-wider block">Kategori Target</span>
              <span className="font-bold text-sm text-gray-900 mt-1 block">{targetCat?.name || 'Default'}</span>
              <span className="text-xs text-gray-500 mt-0.5 block">Klasifikasi: {accessClassification === 'publik' ? 'Publik' : 'Non-Publik'}</span>
            </div>

            <div className="p-4 bg-gray-50 border border-gray-200 rounded-xl">
              <span className="text-xs font-bold text-gray-500 uppercase tracking-wider block">Dokumen Dipilih</span>
              <span className="font-extrabold text-2xl text-red-700 mt-1 block">{selectedCount}</span>
              <span className="text-xs text-gray-500 block">Siap diproses ke Knowledge Base</span>
            </div>
          </div>

          {/* Status Penarikan Berjalan */}
          {isPullRunning && (
            <div className="p-6 bg-red-50/40 border border-red-100 rounded-xl mb-6 text-center animate-in fade-in">
              <Loader2 size={32} className="animate-spin text-red-700 mx-auto mb-3" />
              <h4 className="font-bold text-gray-900 text-sm">Menarik Dokumen ke Knowledge Base...</h4>
              <p className="text-xs text-gray-500 mt-1">
                Proses ekstraksi metadata, standarisasi nama berkas, dan penyimpanan repositori sedang berlangsung.
              </p>
              {scanSession?.pull_progress && (
                <div className="mt-4 max-w-md mx-auto">
                  <div className="flex justify-between text-xs text-gray-600 mb-1">
                    <span>
                      Progres: {scanSession.pull_progress.processed_count} dari{' '}
                      {scanSession.pull_progress.total_found ?? selectedCount}
                    </span>
                    <span className="font-mono font-bold">
                      {scanSession.pull_progress.progress_percent ??
                        Math.round(
                          (scanSession.pull_progress.processed_count /
                            Math.max(1, scanSession.pull_progress.total_found ?? selectedCount)) *
                            100
                        )}
                      %
                    </span>
                  </div>
                  <div className="w-full bg-red-100 rounded-full h-2 overflow-hidden">
                    <div 
                      className="bg-red-700 h-2 rounded-full transition-all duration-300"
                      style={{
                        width: `${
                          scanSession.pull_progress.progress_percent ??
                          Math.round(
                            (scanSession.pull_progress.processed_count /
                              Math.max(1, scanSession.pull_progress.total_found ?? selectedCount)) *
                              100
                          )
                        }%`,
                      }}
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Footer Actions */}
          <div className="flex justify-between items-center pt-5 border-t border-gray-100">
            <button
              type="button"
              disabled={isPullRunning || isPullInitiating}
              onClick={() => setStep(2)}
              className="px-4 py-2 border border-gray-300 rounded-lg text-xs font-semibold text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50 cursor-pointer"
            >
              Kembali ke Pemilihan
            </button>

            {!isPullRunning && (
              <button
                type="button"
                disabled={selectedCount === 0 || isPullInitiating}
                onClick={handleExecutePull}
                className="px-6 py-2.5 bg-red-700 hover:bg-red-800 text-white font-semibold text-xs rounded-lg shadow-sm transition-all flex items-center disabled:opacity-50 cursor-pointer"
              >
                {isPullInitiating ? (
                  <>
                    <Loader2 size={16} className="animate-spin mr-2" />
                    Memulai Penarikan...
                  </>
                ) : (
                  <>
                    <Database size={16} className="mr-2" />
                    Mulai Tarik Dokumen ke Knowledge Base
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // RENDER STEP 4: Ringkasan Hasil Penarikan (PullResultSummary)
  // --------------------------------------------------------------------------
  return (
    <div className="space-y-6">
      <PullResultSummary
        scanId={activeScanId || 0}
        destination="knowledge_base"
        candidates={candidates}
        onReset={handleResetFlow}
      />
    </div>
  );
}
