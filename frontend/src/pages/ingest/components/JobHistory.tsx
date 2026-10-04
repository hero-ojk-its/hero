import { useState, useEffect } from 'react';
import { Globe, Loader2 } from 'lucide-react';
import { listScans, type ScanSessionResponse } from '../../../lib/ingestApi';
import { isApiConfigured } from '../../../lib/api';
import { mockScrapingHistory } from '../mock';
import { getStatusPindaiLabel } from '../labels';

interface JobHistoryProps {
  onSelectScan?: (scan: ScanSessionResponse) => void;
}

export default function JobHistory({ onSelectScan }: JobHistoryProps) {
  const [scans, setScans] = useState<ScanSessionResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(isApiConfigured);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isApiConfigured) return;

    let mounted = true;
    listScans({ limit: 5 })
      .then((res) => {
        if (!mounted) return;
        setScans(res.items || []);
      })
      .catch((err) => {
        if (!mounted) return;
        console.warn('Gagal memuat riwayat sesi pemindaian:', err);
        setError('Gagal memuat riwayat pemindaian');
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, []);

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
        <div>
          <h3 className="text-lg font-bold text-gray-900">Riwayat Scraping Terakhir</h3>
          <span className="bg-gray-100 text-gray-600 text-xs font-medium px-2.5 py-1 rounded-full">
            {isApiConfigured ? `${scans.length} pemindaian terakhir` : 'Data contoh'}
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-gray-100 text-xs font-bold text-gray-500 uppercase tracking-wider">
              <th className="py-3 px-4">Sumber URL</th>
              <th className="py-3 px-4">Waktu</th>
              <th className="py-3 px-4">Dokumen Ditemukan</th>
              <th className="py-3 px-4">Dokumen Baru</th>
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
                  Memuat riwayat pemindaian...
                </td>
              </tr>
            ) : !isApiConfigured ? (
              // Mode contoh (Mock)
              mockScrapingHistory.map((item, idx) => (
                <tr key={idx} className="hover:bg-gray-50/50 transition-colors">
                  <td className="py-3.5 px-4">
                    <div className="flex items-center text-sm font-medium text-gray-900">
                      <Globe size={14} className="text-gray-400 mr-2 shrink-0" />
                      <span className="truncate max-w-xs">{item.url}</span>
                    </div>
                  </td>
                  <td className="py-3.5 px-4 text-xs text-gray-600">{item.time}</td>
                  <td className="py-3.5 px-4 text-xs text-gray-900 font-medium">{item.totalDocs}</td>
                  <td className="py-3.5 px-4 text-xs font-semibold text-blue-700">{item.newDocs}</td>
                  <td className="py-3.5 px-4 text-right">
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                        item.status === 'Berhasil'
                          ? 'bg-gray-100 text-gray-700'
                          : 'bg-red-50 text-red-700'
                      }`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
                          item.status === 'Berhasil' ? 'bg-blue-600' : 'bg-red-600'
                        }`}
                      ></span>
                      {item.status}
                    </span>
                  </td>
                </tr>
              ))
            ) : scans.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-8 text-center text-gray-500 text-xs">
                  Belum ada riwayat pemindaian di server.
                </td>
              </tr>
            ) : (
              // Mode API nyata
              scans.map((scan) => {
                const totalFound = scan.candidates_summary?.total ?? 0;
                const newFound = scan.candidates_summary?.baru ?? 0;
                const isFinished = scan.status === 'selesai' || scan.status === 'siap_dipilih';
                const isFailed = scan.status === 'gagal';

                return (
                  <tr
                    key={scan.id}
                    onClick={() => onSelectScan?.(scan)}
                    className={`hover:bg-gray-50/70 transition-colors ${
                      onSelectScan ? 'cursor-pointer' : ''
                    }`}
                  >
                    <td className="py-3.5 px-4">
                      <div className="flex items-center text-xs font-medium text-gray-900">
                        <Globe size={14} className="text-gray-400 mr-2 shrink-0" />
                        <span className="truncate max-w-sm" title={scan.start_url}>
                          {scan.start_url}
                        </span>
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-xs text-gray-600 whitespace-nowrap">
                      {formatDate(scan.scanned_at || scan.created_at)}
                    </td>
                    <td className="py-3.5 px-4 text-xs text-gray-900 font-medium">
                      {totalFound} dokumen
                    </td>
                    <td className="py-3.5 px-4 text-xs font-semibold text-blue-700">
                      {newFound} baru
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
                        {getStatusPindaiLabel(scan.status)}
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
