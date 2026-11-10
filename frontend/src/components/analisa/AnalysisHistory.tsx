import { useState, useEffect, useCallback, useRef } from 'react';
import {
  FileText,
  Clock,
  RefreshCw,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import {
  listDraftDocuments,
  getDocumentAnalysisRuns,
  type AnalysisRunItem,
} from '../../lib/analisaApi';
import type { DocumentItem } from '../../lib/api';

interface AnalysisHistoryProps {
  onOpenWorkspace: (docId: number, stage: 'summary' | 'analisa') => void;
  refreshTrigger?: number;
}

interface AnalysisRunStatus {
  loading: boolean;
  harmonisasiRun?: AnalysisRunItem | null;
  analisaRun?: AnalysisRunItem | null;
  checked: boolean;
  error?: string | null;
}

export default function AnalysisHistory({
  onOpenWorkspace,
  refreshTrigger = 0,
}: AnalysisHistoryProps) {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [totalDocs, setTotalDocs] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(10);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Status analisa per document_id: cache agar tidak memanggil berulang
  const [analysisStatusMap, setAnalysisStatusMap] = useState<Record<number, AnalysisRunStatus>>({});
  const activeRunsAbortRef = useRef<AbortController | null>(null);

  const fetchDrafts = useCallback(async () => {
    setLoading(true);
    setError(null);
    const controller = new AbortController();

    try {
      const skip = (page - 1) * pageSize;
      const res = await listDraftDocuments(
        { limit: pageSize, skip },
        controller.signal
      );

      const items = res.items || [];
      setDocuments(items);
      setTotalDocs(res.total ?? items.length);

      // Mulai pemeriksaan status riwayat analisa untuk dokumen yang siap di halaman aktif (terindeks & perlu_koreksi)
      const readyDocs = items.filter(
        (d) => d.processing_status === 'terindeks' || d.processing_status === 'perlu_koreksi'
      );
      if (readyDocs.length > 0) {
        if (activeRunsAbortRef.current) {
          activeRunsAbortRef.current.abort();
        }
        const runsController = new AbortController();
        activeRunsAbortRef.current = runsController;

        // Inisialisasi status loading untuk item yang belum ada di map
        setAnalysisStatusMap((prev) => {
          const updated = { ...prev };
          for (const d of readyDocs) {
            if (!updated[d.id]) {
              updated[d.id] = { loading: true, checked: false };
            }
          }
          return updated;
        });

        // Request riwayat analisa & harmonisasi secara paralel per dokumen yang terlihat
        for (const doc of readyDocs) {
          (async () => {
            try {
              const [harmonisasiRes, analisaRes] = await Promise.allSettled([
                getDocumentAnalysisRuns(doc.id, 'harmonisasi', runsController.signal),
                getDocumentAnalysisRuns(doc.id, 'analisa', runsController.signal),
              ]);

              const harmRun =
                harmonisasiRes.status === 'fulfilled' && harmonisasiRes.value.items?.length > 0
                  ? harmonisasiRes.value.items[0]
                  : null;

              const analRun =
                analisaRes.status === 'fulfilled' && analisaRes.value.items?.length > 0
                  ? analisaRes.value.items[0]
                  : null;

              setAnalysisStatusMap((prev) => ({
                ...prev,
                [doc.id]: {
                  loading: false,
                  checked: true,
                  harmonisasiRun: harmRun,
                  analisaRun: analRun,
                },
              }));
            } catch (err: unknown) {
              if (runsController.signal.aborted) return;
              setAnalysisStatusMap((prev) => ({
                ...prev,
                [doc.id]: {
                  loading: false,
                  checked: true,
                  error: err instanceof Error ? err.message : 'Gagal memeriksa status',
                },
              }));
            }
          })();
        }
      }
    } catch (err: unknown) {
      if (!controller.signal.aborted) {
        const msg = err instanceof Error ? err.message : 'Gagal memuat riwayat draft regulasi.';
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => {
    fetchDrafts();
    return () => {
      if (activeRunsAbortRef.current) {
        activeRunsAbortRef.current.abort();
      }
    };
  }, [fetchDrafts, refreshTrigger]);

  const totalPages = Math.max(1, Math.ceil(totalDocs / pageSize));

  // Format tanggal ramah pengguna
  const formatDate = (isoStr?: string | null): string => {
    if (!isoStr) return '-';
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return isoStr;
      return (
        d.toLocaleDateString('id-ID', {
          day: 'numeric',
          month: 'short',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        }) + ' WIB'
      );
    } catch {
      return isoStr;
    }
  };

  // Helper untuk menentukan apakah dokumen selesai diekstrak dan siap dianalisis
  const isDocumentReady = (status?: string | null): boolean => {
    return status === 'terindeks' || status === 'perlu_koreksi';
  };

  const getDisabledActionLabel = (status?: string | null): string => {
    switch (status) {
      case 'diterima':
        return 'Menunggu Ekstraksi';
      case 'diproses':
        return 'Sedang Diproses';
      case 'gagal':
        return 'Ekstraksi Gagal';
      case 'ditolak':
        return 'Dokumen Ditolak';
      default:
        return 'Belum Siap';
    }
  };

  const getDisabledActionTitle = (status?: string | null): string => {
    switch (status) {
      case 'diterima':
        return 'Dokumen masih dalam antrean ekstraksi teks';
      case 'diproses':
        return 'Dokumen sedang diproses oleh engine ekstraksi';
      case 'gagal':
        return 'Ekstraksi teks PDF gagal (teks tidak dapat dibaca)';
      case 'ditolak':
        return 'Dokumen ditolak oleh sistem';
      default:
        return 'Dokumen belum siap untuk dianalisis';
    }
  };

  // Helper badge status ekstraksi yang bersih & minimalis
  const renderExtractionBadge = (status?: string | null) => {
    switch (status) {
      case 'terindeks':
        return (
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200/60"
            title="Teks PDF terindeks dan metadata lengkap"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
            Terindeks
          </span>
        );
      case 'perlu_koreksi':
        return (
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-900 border border-amber-200/80"
            title="Ekstraksi teks selesai • Metadata belum lengkap"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
            Perlu Koreksi
          </span>
        );
      case 'diterima':
        return (
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-50 text-slate-700 border border-slate-200"
            title="Menunggu proses ekstraksi teks"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
            Menunggu
          </span>
        );
      case 'diproses':
        return (
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-800 border border-blue-200"
            title="Sedang memproses naskah dokumen..."
          >
            <Clock size={12} className="animate-spin text-blue-600" />
            Diproses
          </span>
        );
      case 'gagal':
        return (
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-rose-50 text-rose-800 border border-rose-200"
            title="Ekstraksi teks PDF gagal (teks tidak dapat dibaca)"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-rose-600" />
            Gagal
          </span>
        );
      case 'ditolak':
        return (
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700 border border-gray-200"
            title="Dokumen ditolak oleh sistem"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />
            Ditolak
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-50 text-gray-600 border border-gray-200">
            <span className="w-1.5 h-1.5 rounded-full bg-gray-300" />
            {status || 'Belum diketahui'}
          </span>
        );
    }
  };

  // Helper tampilan status analisa regulasi yang bersih
  const renderAnalysisStatus = (doc: DocumentItem) => {
    const status = doc.processing_status;

    if (status === 'diterima' || status === 'diproses') {
      return (
        <span className="text-gray-400 text-xs">
          Menunggu ekstraksi
        </span>
      );
    }

    if (status === 'gagal' || status === 'ditolak') {
      return (
        <span className="text-gray-400 text-xs">
          Tidak dapat dianalisis
        </span>
      );
    }

    const st = analysisStatusMap[doc.id];
    if (!st || st.loading) {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs text-gray-400">
          <Clock size={12} className="animate-spin text-gray-400" />
          Memeriksa...
        </span>
      );
    }

    if (st.error) {
      return <span className="text-xs text-gray-400">Belum diketahui</span>;
    }

    if (st.harmonisasiRun) {
      const run = st.harmonisasiRun;
      const jmlTemuan = run.ringkasan_output?.jumlah_temuan;
      return (
        <div className="flex items-center gap-2 text-xs">
          <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
          <span className="font-medium text-gray-900">Harmonisasi</span>
          <span className="text-gray-500 font-normal">
            ({typeof jmlTemuan === 'number' ? `${jmlTemuan} temuan` : 'selesai'})
          </span>
        </div>
      );
    }

    if (st.analisaRun) {
      const run = st.analisaRun;
      const jmlPoin = run.ringkasan_output?.jumlah_poin;
      return (
        <div className="flex items-center gap-2 text-xs">
          <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />
          <span className="font-medium text-gray-900">Summary</span>
          <span className="text-gray-500 font-normal">
            ({typeof jmlPoin === 'number' ? `${jmlPoin} poin` : 'tersedia'})
          </span>
        </div>
      );
    }

    return (
      <span className="text-xs text-gray-400 font-normal">
        Belum dianalisis
      </span>
    );
  };

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 space-y-5 animate-in fade-in duration-200">
      {/* Header Section */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-gray-100">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-gray-900">Riwayat Draft Regulasi</h2>
            <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-700">
              {totalDocs} Draft
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            Daftar seluruh draf regulasi yang pernah diunggah. Buka kembali Summary atau Workspace Analisa tanpa harus mengunggah ulang berkas.
          </p>
        </div>

        <button
          type="button"
          onClick={fetchDrafts}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-gray-700 bg-gray-50 hover:bg-gray-100 border border-gray-300 transition-colors shadow-xs cursor-pointer self-start sm:self-auto disabled:opacity-50"
          title="Segarkan daftar draft"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin text-red-700' : ''} />
          <span>Segarkan</span>
        </button>
      </div>

      {/* Loading State */}
      {loading && documents.length === 0 && (
        <div className="py-16 text-center text-gray-500">
          <Clock className="animate-spin mx-auto mb-2 text-red-700" size={30} />
          <p className="text-sm font-semibold">Memuat riwayat draft regulasi...</p>
          <p className="text-xs text-gray-400 mt-0.5">Menghubungkan ke layanan basis data dokumen</p>
        </div>
      )}

      {/* Error State */}
      {!loading && error && (
        <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-center space-y-3">
          <AlertTriangle className="mx-auto text-red-600" size={28} />
          <div>
            <p className="text-sm font-bold text-red-900">Gagal Memuat Riwayat Draft</p>
            <p className="text-xs text-red-700 mt-0.5">{error}</p>
          </div>
          <button
            type="button"
            onClick={fetchDrafts}
            className="px-4 py-1.5 bg-red-800 hover:bg-red-900 text-white rounded-lg text-xs font-semibold transition-colors shadow-xs cursor-pointer"
          >
            Coba Lagi
          </button>
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && documents.length === 0 && (
        <div className="py-14 text-center border-2 border-dashed border-gray-200 rounded-xl space-y-2.5">
          <FileText className="mx-auto text-gray-300" size={36} />
          <div>
            <p className="text-sm font-bold text-gray-800">Belum Ada Riwayat Draft Regulasi</p>
            <p className="text-xs text-gray-500 max-w-md mx-auto mt-0.5">
              Seluruh berkas PDF yang Anda unggah melalui formulir di atas akan tersimpan di sini secara otomatis untuk dianalisis kembali sewaktu-waktu.
            </p>
          </div>
        </div>
      )}

      {/* Data Table View (Desktop & Laptop) */}
      {!error && documents.length > 0 && (
        <div className="space-y-4">
          <div className="hidden md:block overflow-x-auto border border-gray-200 rounded-xl">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-gray-50/70 border-b border-gray-200 text-gray-500 font-semibold text-xs">
                  <th className="py-3 px-4">Nama Dokumen &amp; Regulasi</th>
                  <th className="py-3 px-4 w-40">Tanggal Unggah</th>
                  <th className="py-3 px-4 w-36">Status Ekstraksi</th>
                  <th className="py-3 px-4 w-44">Status Analisa</th>
                  <th className="py-3 px-4 text-right w-44">Aksi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {documents.map((doc) => {
                  const isReady = isDocumentReady(doc.processing_status);
                  return (
                    <tr key={doc.id} className="hover:bg-gray-50/60 transition-colors">
                      <td className="py-3.5 px-4 max-w-sm">
                        <div className="space-y-1">
                          <p className="font-semibold text-gray-900 truncate" title={doc.title}>
                            {doc.title}
                          </p>
                          <div className="flex items-center gap-1.5 text-[11px] text-gray-400 font-mono">
                            <span>#{doc.id}</span>
                            <span className="text-gray-300">•</span>
                            <span className="text-gray-500 font-sans">{doc.regulation_number || 'Tanpa nomor'}</span>
                            {doc.regulation_type && (
                              <span className="px-1.5 py-0.2 rounded bg-gray-100 text-gray-600 font-sans font-medium text-[10px] border border-gray-200/60">
                                {doc.regulation_type}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="py-3.5 px-4 text-gray-500 whitespace-nowrap text-xs">
                        {formatDate(doc.created_at)}
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        {renderExtractionBadge(doc.processing_status)}
                      </td>
                      <td className="py-3.5 px-4">
                        {renderAnalysisStatus(doc)}
                      </td>
                      <td className="py-3.5 px-4 text-right whitespace-nowrap">
                        {isReady ? (
                          <div className="flex items-center justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => onOpenWorkspace(doc.id, 'summary')}
                              className="px-3 py-1 rounded-lg text-xs font-medium text-gray-700 bg-white hover:bg-gray-50 border border-gray-300 transition-colors cursor-pointer shadow-2xs"
                              title="Buka Summary Tahap Awal"
                            >
                              Summary
                            </button>
                            <button
                              type="button"
                              onClick={() => onOpenWorkspace(doc.id, 'analisa')}
                              className="px-3 py-1 rounded-lg text-xs font-medium text-white bg-red-800 hover:bg-red-900 transition-colors cursor-pointer shadow-2xs"
                              title="Buka Workspace Analisa Lengkap"
                            >
                              Analisa
                            </button>
                          </div>
                        ) : (
                          <span
                            className="inline-block px-2.5 py-1 rounded-lg text-xs text-gray-400 bg-gray-50 border border-gray-200 cursor-not-allowed"
                            title={getDisabledActionTitle(doc.processing_status)}
                          >
                            {getDisabledActionLabel(doc.processing_status)}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Card View (Mobile & Tablet) */}
          <div className="block md:hidden space-y-3">
            {documents.map((doc) => {
              const isReady = isDocumentReady(doc.processing_status);
              return (
                <div
                  key={doc.id}
                  className="p-4 bg-white rounded-xl border border-gray-200 space-y-3 shadow-2xs"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="overflow-hidden space-y-1">
                      <h4 className="text-xs font-bold text-gray-900 truncate" title={doc.title}>
                        {doc.title}
                      </h4>
                      <div className="flex items-center gap-1.5 text-[11px] text-gray-400 font-mono">
                        <span>#{doc.id}</span>
                        <span className="text-gray-300">•</span>
                        <span className="text-gray-500 font-sans">{doc.regulation_number || 'Tanpa nomor'}</span>
                        {doc.regulation_type && (
                          <span className="px-1.5 py-0.2 rounded bg-gray-100 text-gray-600 font-sans font-medium text-[10px] border border-gray-200/60">
                            {doc.regulation_type}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="shrink-0">
                      {renderExtractionBadge(doc.processing_status)}
                    </div>
                  </div>

                  <div className="pt-2 border-t border-gray-100 flex flex-wrap items-center justify-between gap-2 text-xs">
                    <span className="text-gray-500 text-[11px]">{formatDate(doc.created_at)}</span>
                    <div className="w-full sm:w-auto">{renderAnalysisStatus(doc)}</div>
                  </div>

                  {/* Mobile Action Buttons */}
                  <div className="pt-2 border-t border-gray-100 flex items-center justify-end gap-2">
                    {isReady ? (
                      <>
                        <button
                          type="button"
                          onClick={() => onOpenWorkspace(doc.id, 'summary')}
                          className="flex-1 py-1.5 rounded-lg text-xs font-semibold text-gray-700 bg-white hover:bg-gray-50 border border-gray-300 text-center transition-colors cursor-pointer shadow-2xs"
                        >
                          Summary
                        </button>
                        <button
                          type="button"
                          onClick={() => onOpenWorkspace(doc.id, 'analisa')}
                          className="flex-1 py-1.5 rounded-lg text-xs font-semibold text-white bg-red-800 hover:bg-red-900 text-center transition-colors cursor-pointer shadow-2xs"
                        >
                          Analisa
                        </button>
                      </>
                    ) : (
                      <span className="text-[11px] text-gray-400 italic">
                        {getDisabledActionTitle(doc.processing_status)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Pagination Bar */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-2 border-t border-gray-100 text-xs text-gray-600">
              <span>
                Halaman {page} dari {totalPages} ({totalDocs} draft total)
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1 || loading}
                  className="p-1.5 rounded-lg border border-gray-300 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
                  title="Halaman Sebelumnya"
                >
                  <ChevronLeft size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages || loading}
                  className="p-1.5 rounded-lg border border-gray-300 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
                  title="Halaman Berikutnya"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
