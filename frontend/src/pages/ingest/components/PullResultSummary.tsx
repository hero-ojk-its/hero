import { useState } from 'react';
import { 
  CheckCircle, 
  Download, 
  ExternalLink, 
  ArrowRight, 
  RotateCcw, 
  FileText, 
  Loader2
} from 'lucide-react';
import type { CandidateResponse } from '../../../lib/ingestApi';
import { downloadScanZip } from '../../../lib/ingestApi';
import { HASIL_TARIK_LABELS } from '../labels';

interface PullResultSummaryProps {
  scanId: number;
  destination: 'knowledge_base' | 'unduh_folder';
  candidates: CandidateResponse[];
  onReset: () => void;
}

export default function PullResultSummary({
  scanId,
  destination,
  candidates,
  onReset,
}: PullResultSummaryProps) {
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // Group candidate outcomes
  const pulledCandidates = candidates.filter((c) => Boolean(c.pull_outcome));
  const displayItems = pulledCandidates.length > 0 ? pulledCandidates : candidates.filter((c) => c.selected);

  const successCount = displayItems.filter(
    (c) => c.pull_outcome === 'berhasil' || c.pull_outcome === 'diunduh' || (!c.pull_outcome && c.selected)
  ).length;

  const duplicateCount = displayItems.filter((c) => c.pull_outcome === 'duplikat').length;
  const failedCount = displayItems.filter((c) => c.pull_outcome === 'gagal').length;

  const handleDownloadZip = async () => {
    setIsDownloading(true);
    setDownloadError(null);
    try {
      const blob = await downloadScanZip(scanId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = blob.filename || `hero-scan-${scanId}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setDownloadError(msg);
    } finally {
      setIsDownloading(false);
    }
  };

  const isZip = destination === 'unduh_folder';

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
      {/* Header Banner */}
      <div className="text-center py-6 border-b border-gray-100">
        <div className="w-14 h-14 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto mb-3 shadow-inner">
          <CheckCircle size={32} className="stroke-[2.5]" />
        </div>
        <h3 className="text-xl font-bold text-gray-900">Penarikan Dokumen Berhasil</h3>
        <p className="text-sm text-gray-600 mt-1 max-w-md mx-auto">
          {isZip
            ? 'Dokumen terpilih telah dipaketkan ke dalam berkas arsip ZIP sesuai format penamaan standar.'
            : 'Dokumen terpilih telah berhasil dimasukkan ke basis pengetahuan Knowledge Base HERO.'}
        </p>

        {isZip && (
          <div className="mt-4">
            <button
              type="button"
              onClick={handleDownloadZip}
              disabled={isDownloading}
              className="inline-flex items-center px-5 py-2.5 bg-red-700 hover:bg-red-800 text-white font-semibold text-sm rounded-lg shadow-sm transition-all disabled:opacity-50"
            >
              {isDownloading ? (
                <>
                  <Loader2 size={16} className="animate-spin mr-2" />
                  Mengunduh Berkas ZIP...
                </>
              ) : (
                <>
                  <Download size={16} className="mr-2" />
                  Unduh Berkas ZIP Sekarang
                </>
              )}
            </button>
            {downloadError && (
              <p className="mt-2 text-xs text-red-600 font-medium">{downloadError}</p>
            )}
          </div>
        )}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl border border-emerald-100 bg-emerald-50/40">
          <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wider block">
            {isZip ? 'Berhasil Diunduh' : 'Berhasil Masuk KB'}
          </span>
          <span className="text-2xl font-bold text-emerald-700 mt-1 block">{successCount}</span>
          <span className="text-xs text-emerald-600 mt-0.5 block">Dokumen regulasi</span>
        </div>

        <div className="p-4 rounded-xl border border-gray-200 bg-gray-50/70">
          <span className="text-xs font-semibold text-gray-600 uppercase tracking-wider block">
            Duplikat / Dilewati
          </span>
          <span className="text-2xl font-bold text-gray-700 mt-1 block">{duplicateCount}</span>
          <span className="text-xs text-gray-500 mt-0.5 block">Sudah ada di sistem</span>
        </div>

        <div className="p-4 rounded-xl border border-red-100 bg-red-50/40">
          <span className="text-xs font-semibold text-red-800 uppercase tracking-wider block">
            Gagal Diproses
          </span>
          <span className="text-2xl font-bold text-red-700 mt-1 block">{failedCount}</span>
          <span className="text-xs text-red-600 mt-0.5 block">Kesalahan ekstraksi</span>
        </div>
      </div>

      {/* Items List */}
      <div>
        <h4 className="text-sm font-bold text-gray-900 mb-3 flex items-center">
          <FileText size={16} className="text-red-700 mr-2" />
          Rincian Hasil Penarikan Berkas
        </h4>

        <div className="border border-gray-200 rounded-xl overflow-hidden divide-y divide-gray-100 max-h-[360px] overflow-y-auto">
          {displayItems.map((item) => {
            const outcome = item.pull_outcome || (isZip ? 'diunduh' : 'berhasil');
            const isSuccess = outcome === 'berhasil' || outcome === 'diunduh';
            const isDuplicate = outcome === 'duplikat';

            return (
              <div
                key={item.id}
                className="p-3.5 hover:bg-gray-50/50 transition-colors flex items-center justify-between gap-3 text-xs"
              >
                <div className="min-w-0 flex-1">
                  <div className="font-semibold text-gray-900 truncate">
                    {item.document_title || item.filename}
                  </div>
                  <div className="text-[11px] text-gray-500 font-mono truncate mt-0.5">
                    {item.filename}
                  </div>
                  {item.message && (
                    <div className="text-[11px] text-gray-600 mt-0.5">{item.message}</div>
                  )}
                </div>

                <div className="flex items-center space-x-3 shrink-0">
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                      isSuccess
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        : isDuplicate
                        ? 'bg-gray-100 text-gray-700 border-gray-200'
                        : 'bg-red-50 text-red-700 border-red-200'
                    }`}
                  >
                    {HASIL_TARIK_LABELS[outcome] || outcome}
                  </span>

                  {item.document_id ? (
                    <a
                      href={`#/knowledge/detail/${item.document_id}`}
                      className="inline-flex items-center text-xs font-semibold text-red-700 hover:text-red-800 transition-colors"
                    >
                      Lihat Dokumen <ExternalLink size={12} className="ml-1" />
                    </a>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer Navigation */}
      <div className="flex items-center justify-between pt-4 border-t border-gray-100">
        <button
          type="button"
          onClick={onReset}
          className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-lg text-xs font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <RotateCcw size={14} className="mr-1.5" />
          Pindai Sumber Lain
        </button>

        <a
          href="#/knowledge"
          className="inline-flex items-center px-5 py-2 bg-red-700 hover:bg-red-800 text-white font-semibold text-xs rounded-lg transition-colors shadow-sm"
        >
          Buka Knowledge Base <ArrowRight size={14} className="ml-1.5" />
        </a>
      </div>
    </div>
  );
}
