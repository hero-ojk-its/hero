import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Clock,
  ListOrdered,
  AlertTriangle,
  RefreshCw,
  RotateCw,
  EyeOff,
  CheckCircle2,
  XCircle,
  Copy,
  ExternalLink,
  ChevronRight,
  Filter,
  Layers,
  FileWarning,
  Undo2,
  CheckSquare,
  Square,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  getIngestJobs,
  getIngestFailures,
  updateIngestFailureStatus,
  retryIngestFailure,
  batchRetryIngestFailures,
  type IngestJobItem,
  type FailureResponse,
} from '../../lib/ingestApi';
import { isApiConfigured, ApiError } from '../../lib/api';
import {
  getJenisJobIngestLabel,
  getJobStatusBadgeClass,
  getJenisKegagalanLabel,
  getFollowUpStatusLabel,
  getFollowUpStatusBadgeClass,
  JENIS_JOB_INGEST_LABELS,
  JENIS_KEGAGALAN_LABELS,
} from './labels';
import { mockFailuresList } from './mock';
import JobDetailModal from './components/JobDetailModal';
import RetryResponseModal, { type RetryModalData } from './components/RetryResponseModal';

export default function HistoryTab() {
  const [subView, setSubView] = useState<'jobs' | 'failures'>('jobs');

  // Job List State
  const [jobs, setJobs] = useState<IngestJobItem[]>([]);
  const [jobsTotal, setJobsTotal] = useState(0);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [jobStatusFilter, setJobStatusFilter] = useState<string>('all');
  const [jobTypeFilter, setJobTypeFilter] = useState<string>('all');
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);

  // Failure Queue State
  const [failures, setFailures] = useState<FailureResponse[]>([]);
  const [failuresTotal, setFailuresTotal] = useState(0);
  const [unresolvedCount, setUnresolvedCount] = useState(0);
  const [failuresLoading, setFailuresLoading] = useState(false);
  const [failuresError, setFailuresError] = useState<string | null>(null);
  const [followUpStatusFilter, setFollowUpStatusFilter] = useState<string>('belum_ditangani');
  const [failureTypeFilter, setFailureTypeFilter] = useState<string>('all');
  const [includeDuplicates, setIncludeDuplicates] = useState<boolean>(false);
  const [selectedFailureIds, setSelectedFailureIds] = useState<number[]>([]);
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);
  const [batchActionLoading, setBatchActionLoading] = useState(false);

  // Modal response state for C04
  const [retryModalData, setRetryModalData] = useState<RetryModalData | null>(null);

  // Notification Banner
  const [notification, setNotification] = useState<{
    type: 'success' | 'error' | 'info';
    message: string;
  } | null>(null);

  // --------------------------------------------------------------------------
  // 1. Fetch Ingest Jobs
  // --------------------------------------------------------------------------
  const fetchJobs = useCallback(async () => {
    if (!isApiConfigured) {
      setJobs([
        {
          id: 30,
          job_type: 'unggah_manual',
          source_ref: 'peraturan_sample.pdf',
          status: 'selesai',
          started_at: new Date(Date.now() - 3600000).toISOString(),
          finished_at: new Date(Date.now() - 3590000).toISOString(),
          success_count: 1,
          duplicate_count: 0,
          failed_count: 0,
          total_found: 1,
          processed_count: 1,
        },
      ]);
      setJobsTotal(1);
      return;
    }

    setJobsLoading(true);
    setJobsError(null);
    try {
      const params: Record<string, unknown> = { limit: 50 };
      if (jobStatusFilter !== 'all') params.status = jobStatusFilter;
      if (jobTypeFilter !== 'all') params.job_type = jobTypeFilter;

      const res = await getIngestJobs(params);
      setJobs(res.items);
      setJobsTotal(res.total);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setJobsError(msg);
    } finally {
      setJobsLoading(false);
    }
  }, [jobStatusFilter, jobTypeFilter]);

  // --------------------------------------------------------------------------
  // 2. Fetch Ingest Failures
  // --------------------------------------------------------------------------
  const fetchFailures = useCallback(async () => {
    if (!isApiConfigured) {
      let filtered = [...mockFailuresList] as FailureResponse[];
      if (!includeDuplicates) {
        filtered = filtered.filter((f) => f.failure_type !== 'duplikat');
      }
      if (followUpStatusFilter !== 'all') {
        filtered = filtered.filter((f) => f.follow_up_status === followUpStatusFilter);
      }
      if (failureTypeFilter !== 'all') {
        filtered = filtered.filter((f) => f.failure_type === failureTypeFilter);
      }
      setFailures(filtered);
      setFailuresTotal(filtered.length);
      setUnresolvedCount(mockFailuresList.filter((f) => f.follow_up_status === 'belum_ditangani').length);
      return;
    }

    setFailuresLoading(true);
    setFailuresError(null);
    try {
      const params: Record<string, unknown> = {
        limit: 100,
        include_duplicates: includeDuplicates,
        follow_up_status: followUpStatusFilter,
      };
      if (failureTypeFilter !== 'all') {
        params.failure_type = failureTypeFilter;
      }

      const res = await getIngestFailures(params);
      setFailures(res.items);
      setFailuresTotal(res.total);

      // Ambil juga counter unresolved untuk badge jika sedang tidak di tab filter belum_ditangani
      if (followUpStatusFilter === 'belum_ditangani') {
        setUnresolvedCount(res.total);
      } else {
        getIngestFailures({ follow_up_status: 'belum_ditangani', limit: 1 }).then((r) => {
          setUnresolvedCount(r.total);
        }).catch(() => {});
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setFailuresError(msg);
    } finally {
      setFailuresLoading(false);
    }
  }, [followUpStatusFilter, failureTypeFilter, includeDuplicates]);

  // Initial & Filter change triggers
  useEffect(() => {
    let mounted = true;
    const timer = setTimeout(() => {
      if (!mounted) return;
      if (subView === 'jobs') {
        fetchJobs();
      } else {
        fetchFailures();
      }
    }, 0);
    return () => {
      mounted = false;
      clearTimeout(timer);
    };
  }, [subView, fetchJobs, fetchFailures]);

  // Bersihkan notifikasi otomatis setelah 5 detik
  useEffect(() => {
    if (!notification) return;
    const timer = setTimeout(() => setNotification(null), 5000);
    return () => clearTimeout(timer);
  }, [notification]);

  // --------------------------------------------------------------------------
  // 3. Action Handlers (Abaikan, Proses Ulang, Batch)
  // --------------------------------------------------------------------------

  // Aksi Abaikan (C03) / Pulihkan
  const handleToggleIgnore = async (failure: FailureResponse) => {
    const newStatus = failure.follow_up_status === 'diabaikan' ? 'belum_ditangani' : 'diabaikan';
    setActionLoadingId(failure.id);
    try {
      if (isApiConfigured) {
        await updateIngestFailureStatus(failure.id, { follow_up_status: newStatus });
      }
      setNotification({
        type: 'success',
        message: `Status kegagalan "${failure.original_filename}" berhasil diubah menjadi ${getFollowUpStatusLabel(newStatus)}.`,
      });
      // Refresh kegagalan
      await fetchFailures();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setNotification({
        type: 'error',
        message: `Gagal memperbarui status: ${msg}`,
      });
    } finally {
      setActionLoadingId(null);
    }
  };

  // Aksi Proses Ulang (C04) — Menampilkan respons backend apa adanya
  const handleRetrySingle = async (failure: FailureResponse) => {
    setActionLoadingId(failure.id);
    try {
      if (!isApiConfigured) {
        setRetryModalData({
          isOpen: true,
          status: 'konflik',
          httpStatus: 409,
          title: 'Hasil Proses Ulang Dokumen',
          message: 'Kegagalan ini tidak dapat diproses ulang (tidak retryable atau sudah diproses ulang).',
          detail: { failure_id: failure.id, reason: 'offline_mode' },
        });
        return;
      }

      const res = await retryIngestFailure(failure.id);
      setRetryModalData({
        isOpen: true,
        status: 'sukses',
        httpStatus: 200,
        title: 'Hasil Proses Ulang Dokumen Berhasil',
        message: res.message || 'Dokumen berhasil diproses ulang dan dimasukkan ke antrean ekstraksi.',
        detail: res,
      });
      await fetchFailures();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        const errorDetail = err.detail;
        const messageText =
          typeof errorDetail === 'string'
            ? errorDetail
            : errorDetail && typeof errorDetail === 'object' && 'detail' in errorDetail
            ? String((errorDetail as Record<string, unknown>).detail)
            : err.message;

        setRetryModalData({
          isOpen: true,
          status: err.status === 409 ? 'konflik' : 'gagal',
          httpStatus: err.status,
          title: err.status === 409 ? 'Proses Ulang Ditolak (Conflict)' : 'Proses Ulang Gagal',
          message: messageText,
          detail: errorDetail,
        });
      } else {
        const msg = err instanceof Error ? err.message : String(err);
        setRetryModalData({
          isOpen: true,
          status: 'gagal',
          title: 'Gagal Menghubungi Server',
          message: msg,
        });
      }
    } finally {
      setActionLoadingId(null);
    }
  };

  // Aksi Batch Retry
  const handleBatchRetry = async () => {
    if (selectedFailureIds.length === 0) return;
    setBatchActionLoading(true);
    try {
      if (!isApiConfigured) {
        setRetryModalData({
          isOpen: true,
          status: 'konflik',
          httpStatus: 409,
          title: 'Hasil Proses Ulang Massal',
          message: 'Beberapa kegagalan tidak dapat diproses ulang.',
          detail: { selected_count: selectedFailureIds.length },
        });
        return;
      }

      const res = await batchRetryIngestFailures({ failure_ids: selectedFailureIds });
      const summaryMsg = `Batch retry selesai: ${res.success_count} berhasil, ${res.duplicate_count} duplikat, ${res.failed_count} gagal, ${res.skipped_count} dilewati.`;

      setRetryModalData({
        isOpen: true,
        status: res.failed_count > 0 ? 'konflik' : 'sukses',
        httpStatus: 200,
        title: 'Hasil Proses Ulang Massal',
        message: summaryMsg,
        detail: res,
      });

      setSelectedFailureIds([]);
      await fetchFailures();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        const errorDetail = err.detail;
        const messageText =
          typeof errorDetail === 'string'
            ? errorDetail
            : errorDetail && typeof errorDetail === 'object' && 'detail' in errorDetail
            ? String((errorDetail as Record<string, unknown>).detail)
            : err.message;

        setRetryModalData({
          isOpen: true,
          status: 'gagal',
          httpStatus: err.status,
          title: 'Gagal Menjalankan Batch Retry',
          message: messageText,
          detail: errorDetail,
        });
      } else {
        const msg = err instanceof Error ? err.message : String(err);
        setRetryModalData({
          isOpen: true,
          status: 'gagal',
          title: 'Gagal Memproses',
          message: msg,
        });
      }
    } finally {
      setBatchActionLoading(false);
    }
  };

  // Checkbox selection helpers
  const isAllSelected = useMemo(() => {
    if (failures.length === 0) return false;
    return failures.every((f) => selectedFailureIds.includes(f.id));
  }, [failures, selectedFailureIds]);

  const toggleSelectAll = () => {
    if (isAllSelected) {
      setSelectedFailureIds([]);
    } else {
      setSelectedFailureIds(failures.map((f) => f.id));
    }
  };

  const toggleSelectRow = (id: number) => {
    setSelectedFailureIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  return (
    <div className="space-y-6">
      {/* Sub-view Switcher & Header */}
      <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={() => setSubView('jobs')}
            className={`flex items-center px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
              subView === 'jobs'
                ? 'bg-red-700 text-white shadow-sm'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            <ListOrdered size={16} className="mr-2" />
            Daftar Pekerjaan Ingest
            <span
              className={`ml-2 px-2 py-0.5 rounded-full text-xs font-bold ${
                subView === 'jobs' ? 'bg-red-800 text-red-100' : 'bg-gray-200 text-gray-700'
              }`}
            >
              {jobsTotal}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setSubView('failures')}
            className={`flex items-center px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
              subView === 'failures'
                ? 'bg-red-700 text-white shadow-sm'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            <AlertTriangle size={16} className="mr-2" />
            Antrean Kegagalan
            {unresolvedCount > 0 && (
              <span
                className={`ml-2 px-2 py-0.5 rounded-full text-xs font-bold ${
                  subView === 'failures'
                    ? 'bg-amber-400 text-amber-950'
                    : 'bg-amber-100 text-amber-800 border border-amber-300'
                }`}
              >
                {unresolvedCount}
              </span>
            )}
          </button>
        </div>

        <button
          type="button"
          onClick={() => (subView === 'jobs' ? fetchJobs() : fetchFailures())}
          disabled={jobsLoading || failuresLoading}
          className="flex items-center justify-center px-3 py-2 text-xs font-semibold text-gray-700 bg-gray-50 border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors shadow-sm disabled:opacity-50"
          title="Segarkan data"
        >
          <RefreshCw
            size={14}
            className={`mr-1.5 ${jobsLoading || failuresLoading ? 'animate-spin text-red-700' : ''}`}
          />
          Segarkan
        </button>
      </div>

      {/* Notification Toast/Banner */}
      {notification && (
        <div
          className={`p-4 rounded-xl border text-xs flex items-center justify-between animate-in fade-in duration-200 ${
            notification.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
              : notification.type === 'error'
              ? 'bg-rose-50 border-rose-200 text-rose-900'
              : 'bg-blue-50 border-blue-200 text-blue-900'
          }`}
        >
          <div className="flex items-center space-x-2">
            {notification.type === 'success' ? (
              <CheckCircle2 size={16} className="text-emerald-600 flex-shrink-0" />
            ) : notification.type === 'error' ? (
              <XCircle size={16} className="text-rose-600 flex-shrink-0" />
            ) : (
              <AlertTriangle size={16} className="text-blue-600 flex-shrink-0" />
            )}
            <span>{notification.message}</span>
          </div>
          <button
            type="button"
            onClick={() => setNotification(null)}
            className="text-gray-400 hover:text-gray-600 p-1"
          >
            <XCircle size={14} />
          </button>
        </div>
      )}

      {/* ==================================================================== */}
      {/* VIEW A: DAFTAR PEKERJAAN INGEST (C01)                               */}
      {/* ==================================================================== */}
      {subView === 'jobs' && (
        <div className="space-y-4">
          {/* Filters Bar */}
          <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm flex flex-wrap items-center gap-4 text-xs">
            <div className="flex items-center space-x-2">
              <Filter size={14} className="text-gray-400" />
              <span className="font-semibold text-gray-700">Filter Status:</span>
              <select
                value={jobStatusFilter}
                onChange={(e) => setJobStatusFilter(e.target.value)}
                className="bg-gray-50 border border-gray-300 rounded-lg px-2.5 py-1.5 text-xs text-gray-800 focus:ring-1 focus:ring-red-600 focus:outline-none"
              >
                <option value="all">Semua Status</option>
                <option value="selesai">Selesai</option>
                <option value="gagal">Gagal</option>
                <option value="berjalan">Berjalan</option>
                <option value="antrian">Antrian</option>
              </select>
            </div>

            <div className="flex items-center space-x-2">
              <span className="font-semibold text-gray-700">Jenis Pekerjaan:</span>
              <select
                value={jobTypeFilter}
                onChange={(e) => setJobTypeFilter(e.target.value)}
                className="bg-gray-50 border border-gray-300 rounded-lg px-2.5 py-1.5 text-xs text-gray-800 focus:ring-1 focus:ring-red-600 focus:outline-none"
              >
                <option value="all">Semua Jenis</option>
                {Object.entries(JENIS_JOB_INGEST_LABELS).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Jobs Table */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            {jobsLoading && jobs.length === 0 ? (
              <div className="py-16 text-center text-gray-500">
                <Clock className="animate-spin mx-auto mb-2 text-red-700" size={28} />
                <p className="text-sm">Memuat daftar pekerjaan ingest...</p>
              </div>
            ) : jobsError ? (
              <div className="p-8 text-center text-rose-600">
                <AlertTriangle className="mx-auto mb-2" size={28} />
                <p className="text-sm font-semibold">Gagal memuat daftar pekerjaan</p>
                <p className="text-xs text-gray-500 mt-1">{jobsError}</p>
                <button
                  type="button"
                  onClick={fetchJobs}
                  className="mt-3 px-3 py-1.5 bg-red-700 text-white rounded-lg text-xs font-semibold"
                >
                  Coba Lagi
                </button>
              </div>
            ) : jobs.length === 0 ? (
              <div className="py-16 text-center text-gray-500">
                <Layers className="mx-auto mb-2 text-gray-300" size={32} />
                <p className="text-sm font-medium">Tidak ada pekerjaan ingest ditemukan.</p>
                <p className="text-xs text-gray-400 mt-0.5">Ubah filter atau lakukan pemindaian/unggah baru.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-gray-50/80 border-b border-gray-200 text-gray-600 font-semibold uppercase tracking-wider">
                      <th className="py-3 px-4 w-16">ID</th>
                      <th className="py-3 px-4">Jenis Pekerjaan</th>
                      <th className="py-3 px-4">Sumber / Target</th>
                      <th className="py-3 px-4">Waktu Mulai</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4">Hasil (B / D / G)</th>
                      <th className="py-3 px-4 text-right">Aksi</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {jobs.map((j) => (
                      <tr key={j.id} className="hover:bg-gray-50/80 transition-colors">
                        <td className="py-3 px-4 font-mono font-bold text-gray-900">
                          #{j.id}
                        </td>
                        <td className="py-3 px-4">
                          <span className="font-medium text-gray-900">
                            {getJenisJobIngestLabel(j.job_type)}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-gray-600 max-w-xs truncate" title={j.source_ref || '-'}>
                          {j.source_ref || '-'}
                        </td>
                        <td className="py-3 px-4 text-gray-600 whitespace-nowrap">
                          {new Date(j.started_at).toLocaleString('id-ID', {
                            dateStyle: 'short',
                            timeStyle: 'short',
                          })}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[11px] font-semibold border ${getJobStatusBadgeClass(
                              j.status
                            )}`}
                          >
                            {j.status.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <div className="flex items-center space-x-1.5 font-medium">
                            <span
                              className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800"
                              title="Berhasil Masuk KB"
                            >
                              {j.success_count} Berhasil
                            </span>
                            <span
                              className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800"
                              title="Duplikat"
                            >
                              {j.duplicate_count} Duplikat
                            </span>
                            <span
                              className="px-1.5 py-0.5 rounded bg-rose-100 text-rose-800"
                              title="Gagal"
                            >
                              {j.failed_count} Gagal
                            </span>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-right whitespace-nowrap">
                          <button
                            type="button"
                            onClick={() => setSelectedJobId(j.id)}
                            className="text-xs font-semibold text-red-700 hover:text-red-800 hover:underline inline-flex items-center"
                          >
                            <span>Detail</span>
                            <ChevronRight size={14} className="ml-0.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* VIEW B: ANTREAN KEGAGALAN (C02, C03, C04, C05)                      */}
      {/* ==================================================================== */}
      {subView === 'failures' && (
        <div className="space-y-4">
          {/* Filters & Duplicate Toggle */}
          <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm flex flex-wrap items-center justify-between gap-4 text-xs">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center space-x-2">
                <span className="font-semibold text-gray-700">Status Tindak Lanjut:</span>
                <select
                  value={followUpStatusFilter}
                  onChange={(e) => setFollowUpStatusFilter(e.target.value)}
                  className="bg-gray-50 border border-gray-300 rounded-lg px-2.5 py-1.5 text-xs text-gray-800 focus:ring-1 focus:ring-red-600 focus:outline-none"
                >
                  <option value="belum_ditangani">Belum Ditangani (Default)</option>
                  <option value="diproses_ulang">Diproses Ulang</option>
                  <option value="diabaikan">Diabaikan</option>
                  <option value="all">Semua Status</option>
                </select>
              </div>

              <div className="flex items-center space-x-2">
                <span className="font-semibold text-gray-700">Jenis Kegagalan:</span>
                <select
                  value={failureTypeFilter}
                  onChange={(e) => setFailureTypeFilter(e.target.value)}
                  className="bg-gray-50 border border-gray-300 rounded-lg px-2.5 py-1.5 text-xs text-gray-800 focus:ring-1 focus:ring-red-600 focus:outline-none"
                >
                  <option value="all">Semua Jenis</option>
                  {Object.entries(JENIS_KEGAGALAN_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>

              <span className="text-gray-500 font-medium hidden sm:inline">
                (Total: {failuresTotal} berkas)
              </span>
            </div>

            {/* Syarat C05: Toggle Tampilkan Duplikat (disembunyikan secara default) */}
            <label className="flex items-center space-x-2 cursor-pointer bg-amber-50/70 hover:bg-amber-100/70 border border-amber-200 px-3 py-1.5 rounded-lg transition-colors select-none">
              <input
                type="checkbox"
                checked={includeDuplicates}
                onChange={(e) => setIncludeDuplicates(e.target.checked)}
                className="rounded border-amber-400 text-amber-600 focus:ring-amber-500 w-4 h-4 cursor-pointer"
              />
              <span className="font-semibold text-amber-900">
                Tampilkan Duplikat
              </span>
              <span className="text-[11px] text-amber-700">
                (Secara default disembunyikan)
              </span>
            </label>
          </div>

          {/* Batch Actions Bar (ketika ada baris tercentang) */}
          {selectedFailureIds.length > 0 && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-xl flex items-center justify-between text-xs animate-in fade-in duration-150">
              <div className="flex items-center space-x-2 text-red-900 font-semibold">
                <span>{selectedFailureIds.length} berkas dipilih</span>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  type="button"
                  onClick={handleBatchRetry}
                  disabled={batchActionLoading}
                  className="px-3 py-1.5 bg-red-700 hover:bg-red-800 text-white rounded-lg font-semibold flex items-center shadow-sm disabled:opacity-50"
                >
                  <RotateCw
                    size={14}
                    className={`mr-1.5 ${batchActionLoading ? 'animate-spin' : ''}`}
                  />
                  Proses Ulang Terpilih ({selectedFailureIds.length})
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedFailureIds([])}
                  className="px-3 py-1.5 bg-white border border-gray-300 text-gray-700 hover:bg-gray-100 rounded-lg font-medium"
                >
                  Batal Pilihan
                </button>
              </div>
            </div>
          )}

          {/* Failures Table */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            {failuresLoading && failures.length === 0 ? (
              <div className="py-16 text-center text-gray-500">
                <Clock className="animate-spin mx-auto mb-2 text-red-700" size={28} />
                <p className="text-sm">Memuat antrean kegagalan...</p>
              </div>
            ) : failuresError ? (
              <div className="p-8 text-center text-rose-600">
                <AlertTriangle className="mx-auto mb-2" size={28} />
                <p className="text-sm font-semibold">Gagal memuat antrean kegagalan</p>
                <p className="text-xs text-gray-500 mt-1">{failuresError}</p>
                <button
                  type="button"
                  onClick={fetchFailures}
                  className="mt-3 px-3 py-1.5 bg-red-700 text-white rounded-lg text-xs font-semibold"
                >
                  Coba Lagi
                </button>
              </div>
            ) : failures.length === 0 ? (
              <div className="py-16 text-center text-gray-500">
                <CheckCircle2 className="mx-auto mb-2 text-emerald-500" size={32} />
                <p className="text-sm font-medium text-gray-900">
                  Tidak ada kegagalan yang memerlukan tindak lanjut.
                </p>
                <p className="text-xs text-gray-400 mt-0.5">
                  Semua dokumen pada filter ini telah terselesaikan atau tidak ada data yang cocok.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-gray-50/80 border-b border-gray-200 text-gray-600 font-semibold uppercase tracking-wider">
                      <th className="py-3 px-4 w-10 text-center">
                        <button
                          type="button"
                          onClick={toggleSelectAll}
                          className="text-gray-500 hover:text-gray-700"
                          title="Pilih Semua"
                        >
                          {isAllSelected ? (
                            <CheckSquare size={16} className="text-red-700" />
                          ) : (
                            <Square size={16} />
                          )}
                        </button>
                      </th>
                      <th className="py-3 px-4">Nama Berkas</th>
                      <th className="py-3 px-4">Sumber</th>
                      <th className="py-3 px-4">Jenis Kegagalan</th>
                      <th className="py-3 px-4">Pesan & Keterangan</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4 text-right">Aksi</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {failures.map((f) => {
                      const isDuplicate = f.failure_type === 'duplikat';
                      const isSelected = selectedFailureIds.includes(f.id);

                      return (
                        <tr
                          key={f.id}
                          className={`transition-colors ${
                            isDuplicate
                              ? 'bg-amber-50/70 border-l-4 border-l-amber-500 hover:bg-amber-100/60'
                              : isSelected
                              ? 'bg-red-50/40 hover:bg-red-50/70'
                              : 'hover:bg-gray-50/80'
                          }`}
                        >
                          {/* Checkbox */}
                          <td className="py-3 px-4 text-center">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleSelectRow(f.id)}
                              className="rounded border-gray-300 text-red-600 focus:ring-red-500 w-4 h-4 cursor-pointer"
                            />
                          </td>

                          {/* Nama Berkas */}
                          <td className="py-3 px-4">
                            <div className="flex items-center space-x-2">
                              {isDuplicate ? (
                                <Copy size={16} className="text-amber-600 flex-shrink-0" />
                              ) : (
                                <FileWarning size={16} className="text-rose-600 flex-shrink-0" />
                              )}
                              <div>
                                <span className="font-semibold text-gray-900 block truncate max-w-xs" title={f.original_filename}>
                                  {f.original_filename}
                                </span>
                                <span className="text-[10px] text-gray-500 font-mono">
                                  ID Kegagalan: #{f.id} • Job #{f.job_id}
                                </span>
                              </div>
                            </div>
                          </td>

                          {/* Sumber */}
                          <td className="py-3 px-4 text-gray-600 max-w-[180px] truncate" title={f.source_url || `Pekerjaan #${f.job_id}`}>
                            {f.source_url ? (
                              <a
                                href={f.source_url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-red-700 hover:underline flex items-center truncate"
                              >
                                <span className="truncate">{f.source_url}</span>
                                <ExternalLink size={10} className="ml-1 flex-shrink-0" />
                              </a>
                            ) : (
                              <span>Pekerjaan #{f.job_id}</span>
                            )}
                          </td>

                          {/* Jenis Kegagalan (C02: format_tidak_didukung, C05: duplikat) */}
                          <td className="py-3 px-4 whitespace-nowrap">
                            <span
                              className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${
                                isDuplicate
                                  ? 'bg-amber-100 text-amber-800 border-amber-300'
                                  : 'bg-rose-50 text-rose-700 border-rose-300'
                              }`}
                            >
                              {getJenisKegagalanLabel(f.failure_type)}
                            </span>
                          </td>

                          {/* Pesan & Alasan (C05: Tampilkan hash & ukuran sama dengan dokumen #X) */}
                          <td className="py-3 px-4 max-w-sm">
                            <p className="text-gray-800 leading-snug">{f.message}</p>
                            {isDuplicate && f.duplicate_of_document_id && (
                              <div className="mt-1 p-1.5 bg-amber-100/60 rounded border border-amber-300/80 text-[11px] text-amber-900">
                                <span className="font-semibold">Alasan Duplikasi: </span>
                                <span>Hash dan ukuran sama dengan dokumen </span>
                                <Link
                                  to={`/detail-dokumen?id=${f.duplicate_of_document_id}`}
                                  target="_blank"
                                  className="font-bold underline hover:text-amber-950 inline-flex items-center"
                                >
                                  #{f.duplicate_of_document_id}
                                  {f.duplicate_of_document?.title ? ` (${f.duplicate_of_document.title})` : ''}
                                  <ExternalLink size={10} className="ml-0.5" />
                                </Link>
                              </div>
                            )}
                          </td>

                          {/* Status Tindak Lanjut */}
                          <td className="py-3 px-4 whitespace-nowrap">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[11px] border ${getFollowUpStatusBadgeClass(
                                f.follow_up_status
                              )}`}
                            >
                              {getFollowUpStatusLabel(f.follow_up_status)}
                            </span>
                          </td>

                          {/* Aksi Baris (C03: Abaikan, C04: Proses Ulang) */}
                          <td className="py-3 px-4 text-right whitespace-nowrap">
                            <div className="flex items-center justify-end space-x-1.5">
                              {/* Tombol Proses Ulang (C04) */}
                              <button
                                type="button"
                                onClick={() => handleRetrySingle(f)}
                                disabled={actionLoadingId === f.id}
                                className="px-2.5 py-1 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-100 hover:text-gray-900 transition-colors shadow-sm flex items-center disabled:opacity-50"
                                title="Proses Ulang Dokumen (Retry)"
                              >
                                <RotateCw
                                  size={13}
                                  className={`mr-1 ${actionLoadingId === f.id ? 'animate-spin text-red-700' : ''}`}
                                />
                                Proses Ulang
                              </button>

                              {/* Tombol Abaikan / Pulihkan (C03) */}
                              {f.follow_up_status !== 'diabaikan' ? (
                                <button
                                  type="button"
                                  onClick={() => handleToggleIgnore(f)}
                                  disabled={actionLoadingId === f.id}
                                  className="px-2.5 py-1 text-xs font-semibold text-amber-800 bg-amber-50 border border-amber-300 rounded-lg hover:bg-amber-100 transition-colors shadow-sm flex items-center disabled:opacity-50"
                                  title="Abaikan kegagalan ini"
                                >
                                  <EyeOff size={13} className="mr-1" />
                                  Abaikan
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => handleToggleIgnore(f)}
                                  disabled={actionLoadingId === f.id}
                                  className="px-2.5 py-1 text-xs font-semibold text-gray-700 bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200 transition-colors shadow-sm flex items-center disabled:opacity-50"
                                  title="Pulihkan ke Belum Ditangani"
                                >
                                  <Undo2 size={13} className="mr-1" />
                                  Pulihkan
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modal Detail Job */}
      <JobDetailModal
        jobId={selectedJobId}
        onClose={() => setSelectedJobId(null)}
      />

      {/* Modal Hasil Proses Ulang Backend Apa Adanya (C04) */}
      <RetryResponseModal
        data={retryModalData}
        onClose={() => setRetryModalData(null)}
      />
    </div>
  );
}
