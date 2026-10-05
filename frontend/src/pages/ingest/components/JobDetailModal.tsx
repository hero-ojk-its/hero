import { useState, useEffect } from 'react';
import { X, Clock, FileText, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import { getIngestJobDetail, type JobDetailResponse } from '../../../lib/ingestApi';
import { isApiConfigured } from '../../../lib/api';
import { getJenisJobIngestLabel, getJobStatusBadgeClass, getJenisKegagalanLabel } from '../labels';

interface JobDetailModalProps {
  jobId: number | null;
  onClose: () => void;
}

export default function JobDetailModal({ jobId, onClose }: JobDetailModalProps) {
  const [job, setJob] = useState<JobDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'documents' | 'failures'>('documents');

  useEffect(() => {
    if (!jobId) return;

    if (!isApiConfigured) {
      // Mock job detail
      setJob({
        id: jobId,
        job_type: 'unggah_manual',
        source_ref: 'sample_document.pdf',
        source_id: null,
        source: null,
        retry_of_failure_id: null,
        triggered_by: 'manual_upload',
        status: 'selesai',
        started_at: new Date().toISOString(),
        finished_at: new Date().toISOString(),
        duration_seconds: 1.25,
        success_count: 1,
        duplicate_count: 0,
        failed_count: 0,
        total_found: 1,
        processed_count: 1,
        skipped_count: 0,
        progress_percent: 100,
        documents: [
          { id: 101, title: 'Dokumen Regulasi Contoh', regulation_number: 'POJK 1/2026', document_role: 'corpus_eksisting' }
        ],
        failures: [],
      });
      return;
    }

    let isMounted = true;
    const controller = new AbortController();

    async function fetchDetail() {
      setLoading(true);
      setError(null);
      try {
        const data = await getIngestJobDetail(jobId!, controller.signal);
        if (isMounted) {
          setJob(data);
          if (data.documents.length === 0 && data.failures.length > 0) {
            setActiveTab('failures');
          }
        }
      } catch (err: unknown) {
        if (isMounted) {
          const msg = err instanceof Error ? err.message : String(err);
          setError(msg);
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchDetail();

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, [jobId]);

  if (!jobId) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-3xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between bg-gray-50/50">
          <div className="flex items-center space-x-3">
            <h2 className="text-lg font-bold text-gray-900">
              Detail Pekerjaan #{jobId}
            </h2>
            {job && (
              <span className={`px-2.5 py-0.5 rounded-full text-xs border font-medium ${getJobStatusBadgeClass(job.status)}`}>
                {job.status.toUpperCase()}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded-lg hover:bg-gray-100"
            title="Tutup"
          >
            <X size={20} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {loading && (
            <div className="py-12 flex flex-col items-center justify-center text-gray-500">
              <Clock className="animate-spin mb-3 text-red-700" size={32} />
              <p className="text-sm">Memuat detail pekerjaan...</p>
            </div>
          )}

          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              <p className="font-semibold">Gagal memuat detail pekerjaan</p>
              <p className="mt-1">{error}</p>
            </div>
          )}

          {job && !loading && (
            <>
              {/* Grid Metadata */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 bg-gray-50 p-4 rounded-lg border border-gray-100 text-xs">
                <div>
                  <span className="text-gray-500 block mb-0.5">Jenis Pekerjaan</span>
                  <span className="font-medium text-gray-900">{getJenisJobIngestLabel(job.job_type)}</span>
                </div>
                <div>
                  <span className="text-gray-500 block mb-0.5">Sumber / Target</span>
                  <span className="font-medium text-gray-900 truncate block" title={job.source_ref || job.source?.name || '-'}>
                    {job.source_ref || job.source?.name || '-'}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 block mb-0.5">Waktu Mulai</span>
                  <span className="font-medium text-gray-900">
                    {new Date(job.started_at).toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'medium' })}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 block mb-0.5">Waktu Selesai</span>
                  <span className="font-medium text-gray-900">
                    {job.finished_at
                      ? new Date(job.finished_at).toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'medium' })
                      : '-'}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 block mb-0.5">Durasi</span>
                  <span className="font-medium text-gray-900">
                    {job.duration_seconds !== null && job.duration_seconds !== undefined
                      ? `${job.duration_seconds.toFixed(2)} detik`
                      : '-'}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 block mb-0.5">Total Ditemukan</span>
                  <span className="font-medium text-gray-900">{job.total_found ?? job.processed_count ?? 0}</span>
                </div>
                <div>
                  <span className="text-gray-500 block mb-0.5">Dilewati</span>
                  <span className="font-medium text-gray-900">{job.skipped_count ?? 0}</span>
                </div>
                <div>
                  <span className="text-gray-500 block mb-0.5">Pemicu</span>
                  <span className="font-medium text-gray-900 capitalize">{job.triggered_by || 'Sistem'}</span>
                </div>
              </div>

              {/* Counters Summary */}
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-center">
                  <span className="text-2xl font-bold text-emerald-700">{job.success_count}</span>
                  <span className="block text-xs font-medium text-emerald-800 mt-0.5">Berhasil Masuk KB</span>
                </div>
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-center">
                  <span className="text-2xl font-bold text-amber-700">{job.duplicate_count}</span>
                  <span className="block text-xs font-medium text-amber-800 mt-0.5">Duplikat Terdeteksi</span>
                </div>
                <div className="bg-rose-50 border border-rose-200 rounded-lg p-3 text-center">
                  <span className="text-2xl font-bold text-rose-700">{job.failed_count}</span>
                  <span className="block text-xs font-medium text-rose-800 mt-0.5">Gagal Diproses</span>
                </div>
              </div>

              {/* Tabs for Documents and Failures */}
              <div>
                <div className="flex border-b border-gray-200 mb-4">
                  <button
                    type="button"
                    onClick={() => setActiveTab('documents')}
                    className={`pb-2 px-3 text-xs font-semibold border-b-2 transition-colors ${
                      activeTab === 'documents'
                        ? 'border-red-700 text-red-700'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    Dokumen Dihasilkan ({job.documents.length})
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveTab('failures')}
                    className={`pb-2 px-3 text-xs font-semibold border-b-2 transition-colors ${
                      activeTab === 'failures'
                        ? 'border-red-700 text-red-700'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    Kegagalan & Duplikat ({job.failures.length})
                  </button>
                </div>

                {activeTab === 'documents' && (
                  <div>
                    {job.documents.length === 0 ? (
                      <p className="text-xs text-gray-500 italic py-4 text-center">Tidak ada dokumen baru yang tersimpan.</p>
                    ) : (
                      <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                        {job.documents.map((doc) => (
                          <div
                            key={doc.id}
                            className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-100 hover:bg-gray-100/70 transition-colors"
                          >
                            <div className="flex items-center space-x-3 overflow-hidden">
                              <FileText size={18} className="text-emerald-600 flex-shrink-0" />
                              <div className="overflow-hidden">
                                <p className="text-xs font-semibold text-gray-900 truncate" title={doc.title}>
                                  {doc.title}
                                </p>
                                <p className="text-[11px] text-gray-500">
                                  ID #{doc.id} {doc.regulation_number ? `• ${doc.regulation_number}` : ''}
                                </p>
                              </div>
                            </div>
                            <Link
                              to={`/detail-dokumen?id=${doc.id}`}
                              target="_blank"
                              className="text-xs text-red-700 hover:text-red-800 flex items-center space-x-1 font-medium flex-shrink-0 ml-2"
                            >
                              <span>Buka Dokumen</span>
                              <ExternalLink size={12} />
                            </Link>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {activeTab === 'failures' && (
                  <div>
                    {job.failures.length === 0 ? (
                      <p className="text-xs text-gray-500 italic py-4 text-center">Tidak ada catatan kegagalan atau duplikat pada pekerjaan ini.</p>
                    ) : (
                      <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                        {job.failures.map((f) => (
                          <div
                            key={f.id}
                            className={`p-3 rounded-lg border text-xs ${
                              f.failure_type === 'duplikat'
                                ? 'bg-amber-50/50 border-amber-200'
                                : 'bg-rose-50/50 border-rose-200'
                            }`}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <span className="font-semibold text-gray-900">{f.original_filename}</span>
                              <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-white border">
                                {getJenisKegagalanLabel(f.failure_type)}
                              </span>
                            </div>
                            <p className="text-gray-600 text-[11px]">{f.message}</p>
                            {f.duplicate_of_document_id && (
                              <p className="mt-1 text-[11px] text-amber-800 font-medium">
                                Dokumen pembanding: #{f.duplicate_of_document_id}{' '}
                                {f.duplicate_of_document?.title ? `(${f.duplicate_of_document.title})` : ''}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t border-gray-200 bg-gray-50 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors shadow-sm"
          >
            Tutup
          </button>
        </div>
      </div>
    </div>
  );
}
