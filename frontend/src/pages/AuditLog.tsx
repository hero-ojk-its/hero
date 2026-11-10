import { useState, useEffect, useCallback } from 'react';
import { 
  History, 
  RefreshCw, 
  Filter, 
  Lock, 
  Calendar, 
  User
} from 'lucide-react';
import { getAuditLogs, extractSafeErrorMessage, type AuditLogItem } from '../lib/adminApi';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { EmptyState } from '../components/EmptyState';
import AppBreadcrumb from '../components/common/AppBreadcrumb';

const COMMON_ACTIONS = [
  { label: 'Semua Aksi', value: '' },
  { label: 'LOGIN', value: 'LOGIN' },
  { label: 'LOGIN_FAILED', value: 'LOGIN_FAILED' },
  { label: 'UPLOAD_DOCUMENT', value: 'UPLOAD_DOCUMENT' },
  { label: 'UPDATE_METADATA', value: 'UPDATE_METADATA' },
  { label: 'UPDATE_DOCUMENT_STATUS', value: 'UPDATE_DOCUMENT_STATUS' },
  { label: 'RUN_ANALYSIS', value: 'RUN_ANALYSIS' },
  { label: 'RUN_HARMONIZATION', value: 'RUN_HARMONIZATION' },
  { label: 'EXPORT_ANALYSIS', value: 'EXPORT_ANALYSIS' },
  { label: 'PLACE_DOCUMENT', value: 'PLACE_DOCUMENT' },
];

export default function AuditLog() {
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<unknown | null>(null);
  const [actionFilter, setActionFilter] = useState<string>('');
  const [limit, setLimit] = useState<number>(50);

  const fetchLogs = useCallback(async (signal?: AbortSignal) => {
    queueMicrotask(() => {
      if (!signal?.aborted) {
        setLoading(true);
        setError(null);
      }
    });
    try {
      const data = await getAuditLogs(
        {
          action: actionFilter || null,
          limit,
        },
        signal
      );
      setLogs(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      if (signal?.aborted) return;
      setError(err);
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, [actionFilter, limit]);

  useEffect(() => {
    const controller = new AbortController();
    fetchLogs(controller.signal);
    return () => controller.abort();
  }, [fetchLogs]);

  const safeError = error ? extractSafeErrorMessage(error) : null;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <AppBreadcrumb items={[{ label: 'Audit Log', isCurrent: true }]} />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-gray-200">
        <div>
          <div className="flex items-center space-x-2.5">
            <div className="p-2 bg-red-100 text-red-700 rounded-lg">
              <History size={20} />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900 tracking-tight">Audit Log Aktivitas</h1>
              <p className="text-xs text-gray-500 mt-0.5">
                Jejak audit seluruh aktivitas sistem, login, analisa, dan perubahan dokumen regulasi.
              </p>
            </div>
          </div>
        </div>

        {/* Action button */}
        <div className="flex items-center space-x-3">
          <button
            type="button"
            onClick={() => fetchLogs()}
            disabled={loading}
            className="inline-flex items-center px-3.5 py-2 text-xs font-semibold rounded-lg bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors shadow-sm disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw size={14} className={`mr-1.5 ${loading ? 'animate-spin' : ''}`} />
            Segarkan
          </button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm flex flex-wrap items-center gap-4">
        <div className="flex items-center space-x-2 text-xs font-semibold text-gray-700">
          <Filter size={15} className="text-gray-400" />
          <span>Filter:</span>
        </div>

        <div className="flex items-center space-x-2">
          <label htmlFor="action-filter" className="text-xs text-gray-500">
            Jenis Aksi:
          </label>
          <select
            id="action-filter"
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="py-1.5 px-2.5 border border-gray-300 rounded-lg text-xs text-gray-800 bg-white focus:ring-red-600 focus:border-red-600"
          >
            {COMMON_ACTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center space-x-2">
          <label htmlFor="limit-select" className="text-xs text-gray-500">
            Tampilkan:
          </label>
          <select
            id="limit-select"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="py-1.5 px-2.5 border border-gray-300 rounded-lg text-xs text-gray-800 bg-white focus:ring-red-600 focus:border-red-600"
          >
            <option value={20}>20 entri</option>
            <option value={50}>50 entri</option>
            <option value={100}>100 entri</option>
          </select>
        </div>
      </div>

      {/* Content Area */}
      {loading ? (
        <LoadingState message="Memuat jejak audit log dari peladen backend..." />
      ) : safeError ? (
        <div className="space-y-4">
          {safeError.is403 && (
            <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start space-x-3 text-amber-900">
              <Lock className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div className="text-xs space-y-1">
                <p className="font-semibold">{safeError.title}</p>
                <p className="text-amber-800">{safeError.message}</p>
              </div>
            </div>
          )}
          <ErrorState
            title={safeError.title}
            message={safeError.message}
            onRetry={() => fetchLogs()}
            retryText="Coba Ambil Ulang"
          />
        </div>
      ) : logs.length === 0 ? (
        <EmptyState
          title="Tidak ada catatan audit log"
          message="Belum ada catatan aktivitas yang sesuai dengan filter yang dipilih."
          onAction={() => setActionFilter('')}
          actionLabel="Hapus Filter"
        />
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-gray-700 divide-y divide-gray-200">
              <thead className="bg-gray-50 text-[11px] font-bold text-gray-500 uppercase tracking-wider">
                <tr>
                  <th scope="col" className="px-4 py-3">Waktu</th>
                  <th scope="col" className="px-4 py-3">Aksi</th>
                  <th scope="col" className="px-4 py-3">Pengguna</th>
                  <th scope="col" className="px-4 py-3">Target Sumber Daya</th>
                  <th scope="col" className="px-4 py-3">Alamat IP</th>
                  <th scope="col" className="px-4 py-3">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {logs.map((item) => {
                  const waktuStr = item.timestamp
                    ? new Date(item.timestamp).toLocaleString('id-ID', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })
                    : '-';

                  return (
                    <tr key={item.id} className="hover:bg-gray-50/80 transition-colors">
                      <td className="px-4 py-3 whitespace-nowrap text-gray-600 font-medium flex items-center gap-1.5">
                        <Calendar size={13} className="text-gray-400 shrink-0" />
                        <span>{waktuStr}</span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-gray-100 text-gray-800 border border-gray-200">
                          {item.action}
                        </span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="flex items-center gap-1.5 font-medium text-gray-800">
                          <User size={13} className="text-gray-400 shrink-0" />
                          <span>{item.username || (item.user_id ? `ID #${item.user_id}` : 'Sistem')}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-gray-600">
                        {item.target_resource ? (
                          <span className="font-mono text-[11px] bg-gray-50 px-1.5 py-0.5 rounded border border-gray-200">
                            {item.target_resource}
                          </span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-gray-500 font-mono text-[11px]">
                        {item.ip_address || '-'}
                      </td>
                      <td className="px-4 py-3 text-gray-600 max-w-xs truncate">
                        {item.detail ? (
                          <pre className="text-[10px] font-mono bg-gray-50 p-1 rounded border border-gray-200 max-h-16 overflow-y-auto whitespace-pre-wrap">
                            {JSON.stringify(item.detail, null, 2)}
                          </pre>
                        ) : (
                          <span className="text-gray-400 italic">Kosong</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
