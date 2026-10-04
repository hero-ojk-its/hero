import { useState, useEffect, useCallback } from 'react';
import { 
  ArrowRight, 
  Loader2, 
  AlertCircle, 
  AlertTriangle,
  RotateCcw, 
  Database,
  Archive,
  Layers,
  XCircle
} from 'lucide-react';
import { 
  getScrapingSources,
  createScrapingSource,
  updateScrapingSource,
  deleteScrapingSource,
  createScan,
  getScan,
  cancelScan,
  getScanCandidates,
  updateScanSelection,
  startScanPull,
  getCategories,
  type ScrapingSourceResponse,
  type ScrapingSourceCreate,
  type ScrapingSourceUpdate,
  type ScanSessionResponse,
  type CandidateResponse,
  type CategoryDetailResponse,
  type RejectedSelection,
  type NamingSampleInput
} from '../../lib/ingestApi';
import { isApiConfigured } from '../../lib/api';
import { usePolling } from '../../lib/usePolling';
import SourcePicker from './components/SourcePicker';
import SourceFormModal from './components/SourceFormModal';
import NamingFormatPicker from './components/NamingFormatPicker';
import CandidateTable from './components/CandidateTable';
import PullResultSummary from './components/PullResultSummary';
import JobHistory from './components/JobHistory';
import { ErrorState } from '../../components/ErrorState';
import { getStatusPindaiLabel } from './labels';
import { mockScrapedDocs, type MockScrapedDoc } from './mock';

export default function ScrapingTab() {
  // Step: 1 (Config) -> 2 (Scanning & Candidate Selection) -> 3 (Pulling) -> 4 (Result)
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);

  // Sources state
  const [sources, setSources] = useState<ScrapingSourceResponse[]>([]);
  const [selectedSource, setSelectedSource] = useState<ScrapingSourceResponse | null>(null);
  const [isLoadingSources, setIsLoadingSources] = useState(isApiConfigured);

  // Source Modal state
  const [isSourceModalOpen, setIsSourceModalOpen] = useState(false);
  const [sourceModalMode, setSourceModalMode] = useState<'create' | 'edit'>('create');
  const [editingSource, setEditingSource] = useState<ScrapingSourceResponse | null>(null);
  const [sourceToDelete, setSourceToDelete] = useState<ScrapingSourceResponse | null>(null);

  // Form parameter states
  const [crawlDepth, setCrawlDepth] = useState<number>(1);
  const [maxPages, setMaxPages] = useState<number>(3);
  const [allPagesWarning, setAllPagesWarning] = useState<boolean>(false);
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | null>(null);
  const [categories, setCategories] = useState<CategoryDetailResponse[]>([]);
  const [namingFormat, setNamingFormat] = useState<string[]>([]);
  const [namingSeparator, setNamingSeparator] = useState<string>(' ');

  // Scan Session State
  const [activeScanId, setActiveScanId] = useState<number | null>(null);
  const [manualScanSession, setManualScanSession] = useState<ScanSessionResponse | null>(null);
  const [isScanInitiating, setIsScanInitiating] = useState<boolean>(false);
  const [scanInitError, setScanInitError] = useState<string | null>(null);

  // Candidates Table State
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
  const [pullDestination, setPullDestination] = useState<'knowledge_base' | 'unduh_folder'>('knowledge_base');
  const [isPullInitiating, setIsPullInitiating] = useState<boolean>(false);
  const [isPullRunning, setIsPullRunning] = useState<boolean>(false);
  const [pullError, setPullError] = useState<string | null>(null);

  // Mock Mode States (when !isApiConfigured)
  const [mockDocs] = useState<MockScrapedDoc[]>(mockScrapedDocs);
  const [mockSelectedNums, setMockSelectedNums] = useState<string[]>(
    mockScrapedDocs.filter((d) => d.active).map((d) => d.num)
  );
  const [mockProgress, setMockProgress] = useState<number>(0);
  const [mockPullProgress, setMockPullProgress] = useState<number>(0);

  // --------------------------------------------------------------------------
  // 1. Load Initial Sources & Categories
  // --------------------------------------------------------------------------
  useEffect(() => {
    if (!isApiConfigured) return;
    let mounted = true;
    getScrapingSources()
      .then((data) => {
        if (!mounted) return;
        setSources(data);
        if (data.length > 0 && !selectedSource) {
          const firstActive = data.find((s) => s.is_active) || data[0];
          setSelectedSource(firstActive);
          setCrawlDepth(firstActive.crawl_depth || 1);
          if (firstActive.default_naming_format) {
            setNamingFormat(firstActive.default_naming_format);
          }
          if (firstActive.default_naming_separator) {
            setNamingSeparator(firstActive.default_naming_separator);
          }
        }
      })
      .catch((err) => {
        console.warn('Gagal memuat sumber scraping:', err);
      })
      .finally(() => {
        if (mounted) setIsLoadingSources(false);
      });

    return () => {
      mounted = false;
    };
  }, [selectedSource]);

  useEffect(() => {
    if (!isApiConfigured) return;
    getCategories()
      .then(setCategories)
      .catch((err) => console.warn('Gagal memuat kategori:', err));
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
    enabled: Boolean(isApiConfigured && activeScanId && step === 2),
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
    enabled: Boolean(isApiConfigured && activeScanId && step === 3 && isPullRunning),
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

  // Derived scanSession from polling or manual action
  const scanSession = (step === 3 ? pullPolling.data : scanPolling.data) || manualScanSession;
  const setScanSession = useCallback((session: ScanSessionResponse | null) => {
    setManualScanSession(session);
  }, []);

  // --------------------------------------------------------------------------
  // 4. Load Candidates when scan session is ready
  // --------------------------------------------------------------------------
  const loadCandidates = useCallback(async () => {
    if (!activeScanId) return;
    void Promise.resolve().then(() => {
      setIsLoadingCandidates(true);
    });
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
    if (status !== 'siap_dipilih' && status !== 'selesai') return;

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
  // Event Handlers for Source Modal
  // --------------------------------------------------------------------------
  const handleOpenAddSource = () => {
    setEditingSource(null);
    setSourceModalMode('create');
    setIsSourceModalOpen(true);
  };

  const handleOpenEditSource = (source: ScrapingSourceResponse) => {
    setEditingSource(source);
    setSourceModalMode('edit');
    setIsSourceModalOpen(true);
  };

  const handleSaveSource = async (payload: ScrapingSourceCreate | ScrapingSourceUpdate) => {
    if (sourceModalMode === 'edit' && editingSource) {
      const updated = await updateScrapingSource(editingSource.id, payload as ScrapingSourceUpdate);
      setSources((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      if (selectedSource?.id === updated.id) {
        setSelectedSource(updated);
      }
    } else {
      const created = await createScrapingSource(payload as ScrapingSourceCreate);
      setSources((prev) => [created, ...prev]);
      setSelectedSource(created);
      setCrawlDepth(created.crawl_depth || 1);
    }
  };

  const handleToggleActiveSource = async (source: ScrapingSourceResponse) => {
    try {
      const updated = await updateScrapingSource(source.id, { is_active: !source.is_active });
      setSources((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      if (selectedSource?.id === updated.id) {
        setSelectedSource(updated);
      }
    } catch (err) {
      console.error('Gagal mengubah status aktif sumber:', err);
    }
  };

  const handleDeleteSource = async () => {
    if (!sourceToDelete) return;
    try {
      await deleteScrapingSource(sourceToDelete.id);
      setSources((prev) => prev.filter((s) => s.id !== sourceToDelete.id));
      if (selectedSource?.id === sourceToDelete.id) {
        const remaining = sources.filter((s) => s.id !== sourceToDelete.id);
        setSelectedSource(remaining.length > 0 ? remaining[0] : null);
      }
      setSourceToDelete(null);
    } catch (err) {
      console.error('Gagal menghapus sumber:', err);
    }
  };

  // --------------------------------------------------------------------------
  // Start Scan Flow (Step 1 -> 2)
  // --------------------------------------------------------------------------
  const handleStartScan = async () => {
    if (!isApiConfigured) {
      // Mock Mode Flow
      setStep(2);
      setMockProgress(10);
      const timer = setInterval(() => {
        setMockProgress((prev) => {
          if (prev >= 100) {
            clearInterval(timer);
            return 100;
          }
          return prev + 25;
        });
      }, 500);
      return;
    }

    if (!selectedSource) {
      setScanInitError('Pilih salah satu sumber regulasi terdaftar terlebih dahulu.');
      return;
    }

    setIsScanInitiating(true);
    setScanInitError(null);
    setRejectedSelections([]);

    try {
      const res = await createScan({
        source_id: selectedSource.id,
        crawl_depth: crawlDepth,
        max_pages: maxPages,
      });

      setActiveScanId(res.scan_id);
      setStep(2);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setScanInitError(msg || 'Gagal memulai pemindaian sumber');
    } finally {
      setIsScanInitiating(false);
    }
  };

  // Cancel Scan Handler
  const handleCancelScan = async () => {
    if (!isApiConfigured) {
      setStep(1);
      return;
    }
    if (!activeScanId) return;

    try {
      const res = await cancelScan(activeScanId);
      setScanSession(res);
    } catch (err) {
      console.error('Gagal membatalkan pemindaian:', err);
    }
  };

  // --------------------------------------------------------------------------
  // Selection Handlers (Candidate Selection)
  // --------------------------------------------------------------------------
  const handleToggleCandidate = async (cand: CandidateResponse) => {
    if (!isApiConfigured || !activeScanId) return;
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
    if (!isApiConfigured || !activeScanId) return;
    setIsUpdatingSelection(true);
    try {
      const res = await updateScanSelection(activeScanId, {
        action: 'select_all_new',
      });

      // Refetch candidate page
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
    if (!isApiConfigured || !activeScanId) return;
    setIsUpdatingSelection(true);
    try {
      const res = await updateScanSelection(activeScanId, {
        action: 'select_none',
      });

      // Refetch candidate page
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
    if (!isApiConfigured) {
      // Mock pull execution
      setIsPullRunning(true);
      setMockPullProgress(10);
      const timer = setInterval(() => {
        setMockPullProgress((prev) => {
          if (prev >= 100) {
            clearInterval(timer);
            setIsPullRunning(false);
            setStep(4);
            return 100;
          }
          return prev + 30;
        });
      }, 600);
      return;
    }

    if (!activeScanId) return;
    setIsPullInitiating(true);
    setPullError(null);

    try {
      await startScanPull(
        activeScanId,
        {
          destination: pullDestination,
          category_id: selectedCategoryId || null,
          naming_format: namingFormat.length > 0 ? namingFormat : null,
          naming_separator: namingSeparator || ' ',
        },
        false // asynchronous (wait=false)
      );

      setIsPullRunning(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setPullError(msg || 'Gagal memulai penarikan dokumen');
    } finally {
      setIsPullInitiating(false);
    }
  };

  // Reset to Step 1
  const handleResetFlow = () => {
    setStep(1);
    setActiveScanId(null);
    setScanSession(null);
    setCandidates([]);
    setCandidateSkip(0);
    setRejectedSelections([]);
    setMockProgress(0);
    setMockPullProgress(0);
    setIsPullRunning(false);
  };

  // Sample metadata for naming preview
  const firstSelectedCandidate = candidates.find((c) => c.selected);
  const sampleForNaming: NamingSampleInput = firstSelectedCandidate
    ? {
        regulation_number: firstSelectedCandidate.regulation_number,
        title: firstSelectedCandidate.document_title || firstSelectedCandidate.filename,
        regulation_type: firstSelectedCandidate.regulation_type,
        bidang: firstSelectedCandidate.bidang,
        regulation_year: firstSelectedCandidate.regulation_year,
      }
    : {
        regulation_number: 'POJK 11/POJK.03/2024',
        title: 'Ketahanan dan Keamanan Siber Bank Umum',
        regulation_type: 'POJK',
        regulation_year: 2024,
        bidang: 'Perbankan',
      };

  // Status checks for UI
  const isScanningActive =
    scanSession?.status === 'antrian' || scanSession?.status === 'memindai';
  const isScanReady =
    scanSession?.status === 'siap_dipilih' || scanSession?.status === 'selesai';
  const isScanCancelled = scanSession?.status === 'dibatalkan';
  const isScanFailed = scanSession?.status === 'gagal';

  // --------------------------------------------------------------------------
  // RENDER STEP 1: Konfigurasi Parameter Scraping
  // --------------------------------------------------------------------------
  if (step === 1) {
    return (
      <div className="space-y-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-in fade-in duration-300">
          <div className="flex justify-between items-center mb-2">
            <h3 className="text-lg font-bold text-gray-900">Parameter Scraping URL</h3>
            <span className="inline-flex items-center bg-gray-100 text-gray-700 text-xs font-semibold px-2.5 py-1 rounded-full">
              <span className="w-1.5 h-1.5 bg-red-700 rounded-full mr-1.5"></span>
              Tahap 1: Konfigurasi Sumber & Parameter
            </span>
          </div>
          <p className="text-gray-600 text-sm mb-6">
            Pilih sumber regulasi terdaftar atau tambahkan URL portal baru untuk memindai berkas PDF.
          </p>

          {scanInitError && (
            <div className="mb-5 p-3.5 bg-red-50 border border-red-200 rounded-xl flex items-start text-xs text-red-700">
              <AlertCircle size={16} className="text-red-600 mr-2 shrink-0 mt-0.5" />
              <span>{scanInitError}</span>
            </div>
          )}

          <div className="space-y-6">
            {/* Pemilih Sumber Terdaftar */}
            {isApiConfigured ? (
              <SourcePicker
                sources={sources}
                selectedSourceId={selectedSource?.id || null}
                onSelectSource={(s) => {
                  setSelectedSource(s);
                  setCrawlDepth(s.crawl_depth || 1);
                  if (s.default_naming_format) {
                    setNamingFormat(s.default_naming_format);
                  }
                  if (s.default_naming_separator) {
                    setNamingSeparator(s.default_naming_separator);
                  }
                }}
                onAddSourceClick={handleOpenAddSource}
                onEditSourceClick={handleOpenEditSource}
                onDeleteSourceClick={(s) => setSourceToDelete(s)}
                onToggleActiveClick={handleToggleActiveSource}
                isLoading={isLoadingSources}
              />
            ) : (
              // Mode contoh static input
              <div>
                <label className="block text-sm font-medium text-gray-900 mb-1">
                  URL Sumber Regulasi (Mode Contoh)
                </label>
                <input
                  type="text"
                  readOnly
                  value="https://jdih.ojk.go.id/peraturan/sektor-perbankan"
                  className="block w-full px-3.5 py-2.5 border border-gray-300 rounded-lg text-sm bg-gray-50 text-gray-700 font-mono"
                />
              </div>
            )}

            {/* Parameter Batas Halaman, Kedalaman, Kategori */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5 pt-2 border-t border-gray-100">
              {/* Kedalaman Scraping */}
              <div>
                <label className="block text-sm font-semibold text-gray-900 mb-1">
                  Kedalaman Scraping
                </label>
                <select
                  value={crawlDepth}
                  onChange={(e) => setCrawlDepth(Number(e.target.value))}
                  className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
                >
                  <option value={1}>1 Level (Halaman Ini Saja)</option>
                  <option value={2}>2 Level (Rekomendasi)</option>
                  <option value={3}>3 Level (Mendalam)</option>
                  <option value={4}>4 Level (Sangat Dalam)</option>
                </select>
                <p className="text-[11px] text-gray-500 mt-1">
                  Menentukan seberapa dalam tautan sub-halaman dijelajahi.
                </p>
              </div>

              {/* Batas Halaman */}
              <div>
                <label className="block text-sm font-semibold text-gray-900 mb-1">
                  Batas Halaman
                </label>
                <select
                  value={maxPages}
                  onChange={(e) => {
                    const val = Number(e.target.value);
                    setMaxPages(val);
                    setAllPagesWarning(val >= 100);
                  }}
                  className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
                >
                  <option value={1}>1 Halaman (Uji Cepat)</option>
                  <option value={3}>3 Halaman (Standar - 3 halaman)</option>
                  <option value={5}>5 Halaman (Luas)</option>
                  <option value={10}>10 Halaman (Banyak)</option>
                  <option value={100}>Semua Halaman (Penuh)</option>
                </select>
                <p className="text-[11px] text-gray-500 mt-1">
                  Membatasi jumlah halaman perambatan crawler.
                </p>
              </div>

              {/* Kategori Target */}
              <div>
                <label className="block text-sm font-semibold text-gray-900 mb-1">
                  Kategori Target KB
                </label>
                <select
                  value={selectedCategoryId ?? ''}
                  onChange={(e) =>
                    setSelectedCategoryId(e.target.value ? Number(e.target.value) : null)
                  }
                  className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
                >
                  <option value="">Semua Kategori (Otomatis)</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-gray-500 mt-1">
                  Penempatan otomatis ke struktur folder Knowledge Base.
                </p>
              </div>
            </div>

            {/* Peringatan jika memilih semua halaman */}
            {allPagesWarning && (
              <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-xl flex items-start text-xs text-amber-800 animate-in fade-in">
                <AlertTriangle size={16} className="text-amber-600 mr-2 shrink-0 mt-0.5" />
                <div>
                  <span className="font-bold">Perhatian: Pemindaian Penuh Seluruh Halaman</span>
                  <p className="mt-0.5">
                    Memindai seluruh portal (misal: JDIH OJK) membutuhkan waktu sekitar ±50 menit
                    dan akan mengunduh ribuan dokumen. Disarankan menggunakan batas 3 atau 5 halaman
                    untuk pengujian reguler.
                  </p>
                </div>
              </div>
            )}

            {/* Format Penamaan Berkas Dinamis */}
            <div className="pt-2 border-t border-gray-100">
              <NamingFormatPicker
                value={namingFormat}
                onChange={setNamingFormat}
                separator={namingSeparator}
                onSeparatorChange={setNamingSeparator}
                sampleInput={sampleForNaming}
              />
            </div>

            {/* Info Box */}
            <div className="bg-[#F8F9FA] border border-gray-100 rounded-xl p-4 flex items-start text-xs text-gray-600">
              <Layers size={18} className="text-red-700 mr-3 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold text-gray-900 block mb-0.5">
                  Pipeline Ingest Regulasi HERO
                </span>
                Sistem akan merambati situs web sumber, mendeteksi berkas PDF baru dan membandingkan
                hash dengan koleksi Knowledge Base agar terhindar dari duplikasi berkas.
              </div>
            </div>

            {/* Tombol Eksekusi Mulai Scraping */}
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={handleStartScan}
                disabled={isScanInitiating || (isApiConfigured && !selectedSource?.is_active)}
                className="inline-flex items-center px-6 py-2.5 bg-red-700 hover:bg-red-800 text-white font-semibold text-sm rounded-lg shadow-sm transition-all disabled:opacity-50"
              >
                {isScanInitiating ? (
                  <>
                    <Loader2 size={16} className="animate-spin mr-2" />
                    Menjadwalkan Pemindaian...
                  </>
                ) : (
                  <>
                    Mulai Scraping URL
                    <ArrowRight size={16} className="ml-2" />
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Riwayat Scraping Terakhir */}
        <JobHistory
          onSelectScan={(scan) => {
            setActiveScanId(scan.id);
            setScanSession(scan);
            setStep(2);
          }}
        />

        {/* Modal Tambah/Ubah Sumber */}
        <SourceFormModal
          key={editingSource ? `edit-${editingSource.id}` : 'new-source'}
          isOpen={isSourceModalOpen}
          mode={sourceModalMode}
          initialData={editingSource}
          onClose={() => setIsSourceModalOpen(false)}
          onSubmit={handleSaveSource}
        />

        {/* Modal Konfirmasi Hapus Sumber */}
        {sourceToDelete && (
          <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6 space-y-4 border border-gray-100">
              <div className="w-12 h-12 rounded-full bg-red-100 text-red-700 flex items-center justify-center mx-auto">
                <AlertCircle size={24} />
              </div>
              <div className="text-center">
                <h4 className="text-base font-bold text-gray-900">Hapus Sumber Regulasi?</h4>
                <p className="text-xs text-gray-500 mt-1">
                  Sumber <span className="font-semibold text-gray-800">{sourceToDelete.name}</span>{' '}
                  akan dihapus dari daftar perambatan.
                </p>
              </div>
              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setSourceToDelete(null)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-xs font-semibold text-gray-700 hover:bg-gray-50"
                >
                  Batal
                </button>
                <button
                  type="button"
                  onClick={handleDeleteSource}
                  className="px-4 py-2 bg-red-700 hover:bg-red-800 text-white rounded-lg text-xs font-semibold shadow-sm"
                >
                  Ya, Hapus
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // RENDER STEP 2: Status Pemindaian & Pilihan Kandidat
  // --------------------------------------------------------------------------
  if (step === 2) {
    // Mode Contoh (Mock)
    if (!isApiConfigured) {
      const isMockDone = mockProgress >= 100;
      return (
        <div className="space-y-6">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <div className="flex justify-between items-center mb-4">
              <div>
                <h3 className="text-lg font-bold text-gray-900">
                  {isMockDone ? 'Kandidat Berkas Terdeteksi (Mode Contoh)' : 'Memindai URL...'}
                </h3>
                <p className="text-xs text-gray-500">
                  https://jdih.ojk.go.id/peraturan/sektor-perbankan
                </p>
              </div>
              <span className="text-xs font-semibold bg-gray-100 px-3 py-1 rounded-full text-gray-700">
                Tahap 2: Seleksi Berkas
              </span>
            </div>

            {!isMockDone ? (
              <div className="py-12 text-center space-y-4">
                <Loader2 size={36} className="animate-spin text-red-600 mx-auto" />
                <p className="text-sm font-semibold text-gray-800">
                  Merambati halaman regulasi... ({mockProgress}%)
                </p>
                <div className="max-w-md mx-auto bg-gray-200 rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-red-700 h-2 transition-all duration-300"
                    style={{ width: `${mockProgress}%` }}
                  ></div>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-800 flex items-center justify-between">
                  <span>
                    Ditemukan <strong>{mockDocs.length}</strong> dokumen regulasi. Pilih berkas yang
                    ingin ditarik ke sistem.
                  </span>
                  <span className="font-semibold text-blue-900">
                    {mockSelectedNums.length} dipilih
                  </span>
                </div>

                <div className="border border-gray-200 rounded-xl overflow-hidden">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-gray-50 text-gray-600 font-bold uppercase tracking-wider text-[11px] border-b">
                      <tr>
                        <th className="p-3 w-10 text-center">Centang</th>
                        <th className="p-3">Judul Regulasi</th>
                        <th className="p-3">Nomor</th>
                        <th className="p-3">Jenis</th>
                        <th className="p-3">Tahun</th>
                        <th className="p-3">Keberlakuan</th>
                        <th className="p-3">Status KB</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {mockDocs.map((doc) => {
                        const isChecked = mockSelectedNums.includes(doc.num);
                        return (
                          <tr key={doc.num} className="hover:bg-gray-50">
                            <td className="p-3 text-center">
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={() => {
                                  setMockSelectedNums((prev) =>
                                    prev.includes(doc.num)
                                      ? prev.filter((n) => n !== doc.num)
                                      : [...prev, doc.num]
                                  );
                                }}
                                className="rounded text-red-600"
                              />
                            </td>
                            <td className="p-3 font-semibold text-gray-900">{doc.title}</td>
                            <td className="p-3 text-gray-700">{doc.num}</td>
                            <td className="p-3">{doc.type}</td>
                            <td className="p-3">{doc.year}</td>
                            <td className="p-3">
                              <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-semibold text-[10px]">
                                {doc.regStatus}
                              </span>
                            </td>
                            <td className="p-3">
                              <span
                                className={`px-2 py-0.5 rounded-full font-semibold text-[10px] ${
                                  doc.kbsStatus === 'Baru'
                                    ? 'bg-blue-50 text-blue-700'
                                    : 'bg-gray-100 text-gray-700'
                                }`}
                              >
                                {doc.kbsStatus}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="flex justify-between items-center pt-3 border-t">
                  <button
                    type="button"
                    onClick={handleResetFlow}
                    className="px-4 py-2 border rounded-lg text-xs font-semibold text-gray-700"
                  >
                    Batal & Kembali
                  </button>
                  <button
                    type="button"
                    onClick={handleProceedToPull}
                    className="px-5 py-2 bg-red-700 hover:bg-red-800 text-white rounded-lg text-xs font-semibold"
                  >
                    Lanjut ke Penarikan ({mockSelectedNums.length})
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      );
    }

    // Mode API Nyata
    return (
      <div className="space-y-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-in fade-in duration-300">
          {/* Header Status Sesi */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-gray-100 gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-bold text-gray-900">
                  {isScanReady ? 'Daftar Kandidat Berkas' : 'Memindai Sumber Regulasi'}
                </h3>
                <span
                  className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border ${
                    isScanningActive
                      ? 'bg-amber-50 text-amber-700 border-amber-200'
                      : isScanReady
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : 'bg-red-50 text-red-700 border-red-200'
                  }`}
                >
                  {getStatusPindaiLabel(scanSession?.status)}
                </span>
              </div>
              <p className="text-xs text-gray-500 font-mono mt-1 truncate max-w-xl">
                {scanSession?.start_url || selectedSource?.url}
              </p>
            </div>

            <div className="flex items-center space-x-3">
              {isScanningActive && (
                <button
                  type="button"
                  onClick={handleCancelScan}
                  className="px-3 py-1.5 border border-red-200 bg-red-50 hover:bg-red-100 text-red-700 text-xs font-semibold rounded-lg transition-colors flex items-center shadow-2xs"
                >
                  <XCircle size={14} className="mr-1.5" />
                  Batalkan Pemindaian
                </button>
              )}

              {(isScanCancelled || isScanFailed) && (
                <button
                  type="button"
                  onClick={handleResetFlow}
                  className="px-3.5 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs font-semibold rounded-lg transition-colors flex items-center"
                >
                  <RotateCcw size={14} className="mr-1.5" />
                  Pindai Ulang
                </button>
              )}

              {isScanReady && (
                <button
                  type="button"
                  disabled={Boolean(
                    !scanSession?.candidates_summary || scanSession.candidates_summary.terpilih === 0
                  )}
                  onClick={handleProceedToPull}
                  className="px-5 py-2 bg-red-700 hover:bg-red-800 text-white font-semibold text-xs rounded-lg shadow-sm transition-all flex items-center disabled:opacity-50"
                >
                  Lanjut ke Penarikan ({scanSession?.candidates_summary?.terpilih ?? 0})
                  <ArrowRight size={14} className="ml-1.5" />
                </button>
              )}
            </div>
          </div>

          {/* Jaringan / ErrorState dari Polling jika koneksi backend bermasalah */}
          {scanPolling.error && (
            <div className="my-4">
              <ErrorState
                title="Gagal Terhubung ke Peladen"
                message={scanPolling.error.message}
                onRetry={scanPolling.retry}
              />
            </div>
          )}

          {/* Error Message dari Backend jika ada */}
          {scanSession?.error_message && (
            <div className="my-4 p-3 bg-red-50 border border-red-200 rounded-xl flex items-start text-xs text-red-700">
              <AlertCircle size={16} className="text-red-600 mr-2 shrink-0 mt-0.5" />
              <span>{scanSession.error_message}</span>
            </div>
          )}

          {/* Animasi Saat Masih Memindai */}
          {isScanningActive && (
            <div className="py-12 text-center space-y-4">
              <div className="relative w-16 h-16 mx-auto">
                <Loader2 size={64} className="animate-spin text-red-600" />
                <div className="absolute inset-0 flex items-center justify-center font-bold text-xs text-gray-700">
                  {scanSession?.pages_visited ?? 0}
                </div>
              </div>
              <div>
                <h4 className="text-base font-bold text-gray-900">
                  {scanSession?.status === 'antrian'
                    ? 'Menunggu antrean pemindaian...'
                    : 'Sedang merambati halaman situs...'}
                </h4>
                <p className="text-xs text-gray-500 mt-1">
                  Halaman dikunjungi: <strong>{scanSession?.pages_visited ?? 0}</strong> • Dokumen
                  PDF terdeteksi: <strong>{scanSession?.candidates_summary?.total ?? 0}</strong>
                </p>
              </div>
            </div>
          )}

          {/* Tampilan Selesai & Dibatalkan */}
          {isScanCancelled && (
            <div className="py-8 text-center space-y-2 bg-gray-50 rounded-xl my-4 border border-dashed border-gray-200">
              <XCircle size={32} className="text-gray-400 mx-auto" />
              <h4 className="text-sm font-bold text-gray-800">Sesi Pemindaian Dibatalkan</h4>
              <p className="text-xs text-gray-500">
                Pemindaian dihentikan oleh pengguna. Anda dapat memilih dokumen yang sempat ditemukan
                atau memulai pemindaian baru.
              </p>
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

          {/* Footer Back Button */}
          <div className="flex justify-between items-center pt-4 border-t border-gray-100">
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
                className="px-5 py-2 bg-red-700 hover:bg-red-800 text-white font-semibold text-xs rounded-lg shadow-sm transition-all flex items-center disabled:opacity-50"
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
  // RENDER STEP 3: Konfigurasi & Progres Penarikan
  // --------------------------------------------------------------------------
  if (step === 3) {
    const selectedCount = isApiConfigured
      ? scanSession?.candidates_summary?.terpilih ?? candidates.filter((c) => c.selected).length
      : mockSelectedNums.length;

    const pullProcessed = isApiConfigured
      ? scanSession?.pull_progress?.processed_count ?? 0
      : Math.floor((mockPullProgress / 100) * selectedCount);

    const pullTotal = isApiConfigured
      ? scanSession?.pull_progress?.total_found ?? selectedCount
      : selectedCount;

    const percent =
      pullTotal > 0 ? Math.min(100, Math.round((pullProcessed / pullTotal) * 100)) : 0;

    return (
      <div className="space-y-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-in fade-in duration-300">
          <div className="flex justify-between items-center mb-2">
            <h3 className="text-lg font-bold text-gray-900">
              {isPullRunning ? 'Menarik Berkas Terpilih...' : 'Konfigurasi Penarikan Berkas'}
            </h3>
            <span className="inline-flex items-center bg-gray-100 text-gray-700 text-xs font-semibold px-2.5 py-1 rounded-full">
              Tahap 3: Penarikan Berkas
            </span>
          </div>
          <p className="text-gray-600 text-sm mb-6">
            Pilih tujuan penyimpanan dan konfirmasi format penamaan standar sebelum berkas diunduh.
          </p>

          {pullError && (
            <div className="mb-5 p-3.5 bg-red-50 border border-red-200 rounded-xl flex items-start text-xs text-red-700">
              <AlertCircle size={16} className="text-red-600 mr-2 shrink-0 mt-0.5" />
              <span>{pullError}</span>
            </div>
          )}

          {/* Polling ErrorState */}
          {pullPolling.error && (
            <div className="my-4">
              <ErrorState
                title="Gagal Terhubung ke Peladen saat Penarikan"
                message={pullPolling.error.message}
                onRetry={pullPolling.retry}
              />
            </div>
          )}

          {!isPullRunning ? (
            <div className="space-y-6">
              {/* Pilihan Tujuan Penarikan */}
              <div>
                <label className="block text-sm font-semibold text-gray-900 mb-2">
                  Tujuan Penarikan Berkas <span className="text-red-600">*</span>
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div
                    onClick={() => setPullDestination('knowledge_base')}
                    className={`p-4 rounded-xl border cursor-pointer transition-all ${
                      pullDestination === 'knowledge_base'
                        ? 'border-red-600 bg-red-50/30 ring-1 ring-red-600'
                        : 'border-gray-200 hover:border-gray-300 bg-white'
                    }`}
                  >
                    <div className="flex items-start space-x-3">
                      <div
                        className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                          pullDestination === 'knowledge_base'
                            ? 'bg-red-100 text-red-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        <Database size={18} />
                      </div>
                      <div>
                        <span className="text-sm font-bold text-gray-900 block">
                          Masukkan ke Knowledge Base
                        </span>
                        <p className="text-xs text-gray-500 mt-0.5">
                          Dokumen akan diindeks, diekstrak pasalnya, dan dapat dicari di menu
                          Knowledge Base.
                        </p>
                      </div>
                    </div>
                  </div>

                  <div
                    onClick={() => setPullDestination('unduh_folder')}
                    className={`p-4 rounded-xl border cursor-pointer transition-all ${
                      pullDestination === 'unduh_folder'
                        ? 'border-red-600 bg-red-50/30 ring-1 ring-red-600'
                        : 'border-gray-200 hover:border-gray-300 bg-white'
                    }`}
                  >
                    <div className="flex items-start space-x-3">
                      <div
                        className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                          pullDestination === 'unduh_folder'
                            ? 'bg-red-100 text-red-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        <Archive size={18} />
                      </div>
                      <div>
                        <span className="text-sm font-bold text-gray-900 block">
                          Unduh Folder (Arsip ZIP)
                        </span>
                        <p className="text-xs text-gray-500 mt-0.5">
                          Hanya unduh berkas PDF terkompresi ZIP tanpa memproses ekstraksi teks ke
                          basis data.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Ringkasan Konfigurasi */}
              <div className="p-4 bg-gray-50 rounded-xl border border-gray-200 space-y-2 text-xs">
                <div className="flex justify-between py-1 border-b border-gray-200">
                  <span className="text-gray-500">Jumlah Berkas Terpilih:</span>
                  <span className="font-bold text-gray-900">{selectedCount} dokumen</span>
                </div>
                <div className="flex justify-between py-1 border-b border-gray-200">
                  <span className="text-gray-500">Format Nama Berkas:</span>
                  <span className="font-mono text-gray-800">
                    {namingFormat.length > 0
                      ? namingFormat.join(namingSeparator || ' ')
                      : 'Default Backend'}
                  </span>
                </div>
                {pullDestination === 'knowledge_base' && (
                  <div className="flex justify-between py-1">
                    <span className="text-gray-500">Kategori Target:</span>
                    <span className="font-semibold text-gray-900">
                      {categories.find((c) => c.id === selectedCategoryId)?.name ||
                        'Otomatis / Root'}
                    </span>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex justify-between items-center pt-3 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-xs font-semibold text-gray-700 hover:bg-gray-50"
                >
                  Kembali ke Seleksi
                </button>

                <button
                  type="button"
                  disabled={isPullInitiating || selectedCount === 0}
                  onClick={handleExecutePull}
                  className="px-6 py-2.5 bg-red-700 hover:bg-red-800 text-white font-semibold text-xs rounded-lg shadow-sm transition-all flex items-center disabled:opacity-50"
                >
                  {isPullInitiating ? (
                    <>
                      <Loader2 size={16} className="animate-spin mr-2" />
                      Memulai Penarikan...
                    </>
                  ) : (
                    <>
                      Eksekusi Penarikan Berkas
                      <ArrowRight size={14} className="ml-1.5" />
                    </>
                  )}
                </button>
              </div>
            </div>
          ) : (
            /* Tampilan Progres Penarikan Berkas Nyata */
            <div className="py-12 text-center space-y-5 max-w-md mx-auto">
              <Loader2 size={40} className="animate-spin text-red-600 mx-auto" />
              <div>
                <h4 className="text-base font-bold text-gray-900">Mengunduh & Menyimpan Berkas...</h4>
                <p className="text-xs text-gray-500 mt-1">
                  Memproses {pullProcessed} dari {pullTotal} dokumen ({percent}%)
                </p>
              </div>

              <div className="bg-gray-200 rounded-full h-2.5 overflow-hidden w-full">
                <div
                  className="bg-red-700 h-2.5 transition-all duration-300 rounded-full"
                  style={{ width: `${percent}%` }}
                ></div>
              </div>

              <p className="text-[11px] text-gray-400">
                {pullDestination === 'knowledge_base'
                  ? 'Menyimpan berkas PDF dan mendaftarkan metadata ke database HERO.'
                  : 'Mengompresi berkas PDF ke dalam paket ZIP...'}
              </p>
            </div>
          )}
        </div>
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // RENDER STEP 4: Ringkasan Hasil Penarikan
  // --------------------------------------------------------------------------
  if (step === 4) {
    return (
      <PullResultSummary
        scanId={activeScanId || 1}
        destination={pullDestination}
        candidates={candidates}
        onReset={handleResetFlow}
      />
    );
  }

  return null;
}
