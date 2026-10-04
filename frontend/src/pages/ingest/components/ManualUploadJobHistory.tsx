import { useState, useEffect } from 'react';
import { FileText, Loader2, RefreshCw } from 'lucide-react';
import { getIngestJobs, type IngestJobItem } from '../../../lib/ingestApi';
import { isApiConfigured } from '../../../lib/api';
import { mockManualUploadHistory } from '../mock';

interface ManualUploadJobHistoryProps {
  refreshTrigger?: number;
}

export default function ManualUploadJobHistory({ refreshTrigger = 0 }: ManualUploadJobHistoryProps) {
  const [jobs, setJobs] = useState<IngestJobItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(isApiConfigured);
  const [error, setError] = useState<string | null>(null);

  const handleRefresh = () => {
    if (!isApiConfigured) return;
    setIsLoading(true);
    setError(null);
    getIngestJobs({ job_type: 'unggah_manual', limit: 5 })
      .then((res) => setJobs(res.items || []))
      .catch((err) => {
        console.warn('Gagal memuat riwayat upload manual:', err);
        setError('Gagal memuat riwayat upload manual');
      })
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    if (!isApiConfigured) return;

    let mounted = true;
    getIngestJobs({ job_type: 'unggah_manual', limit: 5 })
      .then((res) => {
        if (!mounted) return;
        setJobs(res.items || []);
      })
      .catch((err) => {
        if (!mounted) return;
        console.warn('Gagal memuat riwayat upload manual:', err);
        setError('Gagal memuat riwayat upload manual');
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [refreshTrigger]);

  const formatDate = (isoStr: string | null | undefined): string => {
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

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-in fade-in duration-200">
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center space-x-3">
          <h3 className="text-lg font-bold text-gray-900">Riwayat Upload Manual Terakhir</h3>
          <span className="bg-gray-100 text-gray-600 text-xs font-medium px-2.5 py-1 rounded-full">
            {isApiConfigured ? `${jobs.length} unggahan terakhir` : 'Data contoh'}
          </span>
        </div>
        {isApiConfigured && (
          <button
            type="button"
            onClick={handleRefresh}
            disabled={isLoading}
            className="text-xs text-gray-500 hover:text-red-700 flex items-center transition-colors"
            title="Segarkan riwayat"
          >
            <RefreshCw size={14} className={`mr-1 ${isLoading ? 'animate-spin' : ''}`} />
            Segarkan
          </button>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-gray-100 text-xs font-bold text-gray-500 uppercase tracking-wider">
              <th className="py-3 px-4">Sumber / Berkas</th>
              <th className="py-3 px-4">Waktu</th>
              <th className="py-3 px-4">Total Berkas</th>
              <th className="py-3 px-4">Hasil (Sukses / Duplikat / Gagal)</th>
              <th className="py-3 px-4 text-right">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50 text-sm">
            {error ? (
              <tr>
                <td colSpan={5} className="py-8 text-center text-red-500 text-xs">
                  {error}
                </td>
              </tr>
            ) : isLoading ? (
              <tr>
                <td colSpan={5} className="py-8 text-center text-gray-500 text-xs">
                  <Loader2 size={18} className="animate-spin text-red-600 mx-auto mb-1.5" />
                  Memuat riwayat upload manual...
                </td>
              </tr>
            ) : !isApiConfigured ? (
              // Mode contoh (Mock)
              mockManualUploadHistory.map((item, idx) => (
                <tr key={idx} className="hover:bg-gray-50/50 transition-colors">
                  <td className="py-3.5 px-4">
                    <div className="flex items-center text-sm font-medium text-gray-900">
                      <FileText size={15} className="text-red-600 mr-2 shrink-0" />
                      <span className="font-semibold text-gray-900 truncate max-w-xs">{item.name}</span>
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5 ml-6">Ukuran: {item.size}</div>
                  </td>
                  <td className="py-3.5 px-4 text-xs text-gray-600">{item.time}</td>
                  <td className="py-3.5 px-4 text-xs text-gray-900 font-medium">{item.filesCount}</td>
                  <td className="py-3.5 px-4 text-xs font-semibold text-emerald-700">{item.newDocs}</td>
                  <td className="py-3.5 px-4 text-right">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full mr-1.5"></span>
                      {item.status}
                    </span>
                  </td>
                </tr>
              ))
            ) : jobs.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-8 text-center text-gray-500 text-xs">
                  Belum ada riwayat upload manual di server.
                </td>
              </tr>
            ) : (
              // Mode API nyata
              jobs.map((job) => {
                const totalFiles = (job.success_count || 0) + (job.duplicate_count || 0) + (job.failed_count || 0);
                const isFinished = job.status === 'selesai';
                const isFailed = job.status === 'gagal';

                return (
                  <tr key={job.id} className="hover:bg-gray-50/70 transition-colors">
                    <td className="py-3.5 px-4">
                      <div className="flex items-center text-sm font-medium text-gray-900">
                        <FileText size={15} className="text-red-600 mr-2 shrink-0" />
                        <span className="font-semibold text-gray-900 truncate max-w-sm" title={job.source_ref || '-'}>
                          {job.source_ref || `Unggahan Manual #${job.id}`}
                        </span>
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-xs text-gray-600 whitespace-nowrap">
                      {formatDate(job.started_at)}
                    </td>
                    <td className="py-3.5 px-4 text-xs text-gray-900 font-medium">
                      {totalFiles} berkas
                    </td>
                    <td className="py-3.5 px-4 text-xs">
                      <div className="flex items-center space-x-2">
                        <span className="text-emerald-700 font-medium" title="Berhasil">
                          {job.success_count} baru
                        </span>
                        <span>•</span>
                        <span className="text-amber-700 font-medium" title="Duplikat">
                          {job.duplicate_count} duplikat
                        </span>
                        {job.failed_count > 0 && (
                          <>
                            <span>•</span>
                            <span className="text-red-600 font-medium" title="Gagal">
                              {job.failed_count} gagal
                            </span>
                          </>
                        )}
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                          isFinished
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : isFailed
                            ? 'bg-red-50 text-red-700 border border-red-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
                            isFinished
                              ? 'bg-emerald-600'
                              : isFailed
                              ? 'bg-red-600'
                              : 'bg-amber-600'
                          }`}
                        ></span>
                        {job.status === 'selesai' ? 'Selesai' : job.status === 'gagal' ? 'Gagal' : 'Berjalan'}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
