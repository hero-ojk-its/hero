import { 
  ExternalLink, 
  Search, 
  AlertCircle, 
  AlertTriangle,
  ChevronLeft, 
  ChevronRight, 
  Loader2, 
  Filter
} from 'lucide-react';
import type { 
  CandidateResponse, 
  ScanSummaryCount, 
  RejectedSelection 
} from '../../../lib/ingestApi';
import { formatFileSize } from '../../../lib/api';
import { 
  getMatchStatusLabel, 
  getStatusKeberlakuanLabel, 
  getStatusKeberlakuanBadgeClass, 
  getMatchStatusBadgeClass 
} from '../labels';

interface CandidateTableProps {
  candidates: CandidateResponse[];
  summary?: ScanSummaryCount | null;
  total: number;
  skip: number;
  limit: number;
  onPageChange: (newSkip: number) => void;
  activeMatchTab: string;
  onMatchTabChange: (tab: string) => void;
  docKindFilter: string;
  onDocKindFilterChange: (kind: string) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onToggleCandidate: (candidate: CandidateResponse) => void;
  onSelectAllNew: () => void;
  onSelectNone: () => void;
  isLoading?: boolean;
  isUpdatingSelection?: boolean;
  rejectedSelections?: RejectedSelection[];
}

export default function CandidateTable({
  candidates,
  summary,
  total,
  skip,
  limit,
  onPageChange,
  activeMatchTab,
  onMatchTabChange,
  docKindFilter,
  onDocKindFilterChange,
  searchQuery,
  onSearchChange,
  onToggleCandidate,
  onSelectAllNew,
  onSelectNone,
  isLoading = false,
  isUpdatingSelection = false,
  rejectedSelections = [],
}: CandidateTableProps) {
  const currentPage = Math.floor(skip / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  const totalCount = summary?.total ?? total;
  const baruCount = summary?.baru ?? 0;
  const sudahAdaCount = summary?.sudah_ada ?? 0;
  const mungkinAdaCount = summary?.mungkin_ada ?? 0;
  const terpilihCount = summary?.terpilih ?? 0;

  // Cek apakah seluruh kandidat baru di halaman ini terpilih
  const selectableOnPage = candidates.filter((c) => c.match_status !== 'sudah_ada');
  const allSelectedOnPage =
    selectableOnPage.length > 0 && selectableOnPage.every((c) => c.selected);

  return (
    <div className="space-y-4">
      {/* Rejected selection banner if any */}
      {rejectedSelections.length > 0 && (
        <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl flex items-start text-xs text-amber-800">
          <AlertTriangle size={16} className="text-amber-600 mr-2 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">Beberapa dokumen tidak dapat dicentang:</span>
            <ul className="list-disc list-inside mt-1 space-y-0.5">
              {rejectedSelections.map((rej) => (
                <li key={rej.id}>
                  Kandidat #{rej.id}: {rej.reason === 'sudah_ada' ? 'Dokumen sudah ada di Knowledge Base' : rej.reason}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Top Filter Tabs & Quick Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-gray-200">
        {/* Filter Tabs by Match Status */}
        <div className="flex items-center space-x-1 sm:space-x-2 overflow-x-auto pb-1 sm:pb-0">
          <button
            type="button"
            onClick={() => onMatchTabChange('all')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center ${
              activeMatchTab === 'all'
                ? 'bg-red-700 text-white shadow-xs'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Semua
            <span
              className={`ml-1.5 px-1.5 py-0.2 rounded-full text-[10px] ${
                activeMatchTab === 'all' ? 'bg-red-800 text-white' : 'bg-white text-gray-600'
              }`}
            >
              {totalCount}
            </span>
          </button>

          <button
            type="button"
            onClick={() => onMatchTabChange('baru')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center ${
              activeMatchTab === 'baru'
                ? 'bg-blue-600 text-white shadow-xs'
                : 'bg-blue-50 text-blue-700 hover:bg-blue-100'
            }`}
          >
            Baru
            <span
              className={`ml-1.5 px-1.5 py-0.2 rounded-full text-[10px] ${
                activeMatchTab === 'baru' ? 'bg-blue-700 text-white' : 'bg-white text-blue-700'
              }`}
            >
              {baruCount}
            </span>
          </button>

          <button
            type="button"
            onClick={() => onMatchTabChange('sudah_ada')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center ${
              activeMatchTab === 'sudah_ada'
                ? 'bg-gray-700 text-white shadow-xs'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Sudah Ada
            <span
              className={`ml-1.5 px-1.5 py-0.2 rounded-full text-[10px] ${
                activeMatchTab === 'sudah_ada' ? 'bg-gray-800 text-white' : 'bg-white text-gray-600'
              }`}
            >
              {sudahAdaCount}
            </span>
          </button>

          <button
            type="button"
            onClick={() => onMatchTabChange('mungkin_ada')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center ${
              activeMatchTab === 'mungkin_ada'
                ? 'bg-amber-600 text-white shadow-xs'
                : 'bg-amber-50 text-amber-700 hover:bg-amber-100'
            }`}
          >
            Mungkin Ada
            <span
              className={`ml-1.5 px-1.5 py-0.2 rounded-full text-[10px] ${
                activeMatchTab === 'mungkin_ada' ? 'bg-amber-700 text-white' : 'bg-white text-amber-700'
              }`}
            >
              {mungkinAdaCount}
            </span>
          </button>
        </div>

        {/* Quick Selection Buttons & Terpilih Counter */}
        <div className="flex items-center space-x-2 shrink-0">
          <span className="text-xs font-medium text-gray-600 mr-1">
            Terpilih: <strong className="text-gray-900">{terpilihCount}</strong> berkas
          </span>
          <button
            type="button"
            disabled={isUpdatingSelection || baruCount === 0}
            onClick={onSelectAllNew}
            className="px-2.5 py-1 text-xs font-semibold text-blue-700 bg-blue-50 border border-blue-200 hover:bg-blue-100 rounded-lg transition-colors disabled:opacity-50"
          >
            Pilih Semua Baru
          </button>
          <button
            type="button"
            disabled={isUpdatingSelection || terpilihCount === 0}
            onClick={onSelectNone}
            className="px-2.5 py-1 text-xs font-semibold text-gray-600 bg-gray-100 border border-gray-200 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50"
          >
            Hapus Centang
          </button>
        </div>
      </div>

      {/* Search & Doc Kind Filters */}
      <div className="flex flex-col sm:flex-row items-center gap-3">
        <div className="relative flex-1 w-full">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search size={14} className="text-gray-400" />
          </div>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Cari nama regulasi, nomor, atau topik..."
            className="block w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-xs focus:ring-2 focus:ring-red-500/20 focus:border-red-500 bg-white"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <label className="text-xs font-medium text-gray-600 shrink-0 flex items-center">
            <Filter size={13} className="mr-1 text-gray-400" />
            Jenis:
          </label>
          <select
            value={docKindFilter}
            onChange={(e) => onDocKindFilterChange(e.target.value)}
            className="py-1.5 px-2.5 border border-gray-300 rounded-lg text-xs bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
          >
            <option value="utama">Peraturan Utama</option>
            <option value="all">Semua Jenis Berkas</option>
            <option value="lampiran">Lampiran</option>
            <option value="perubahan">Perubahan</option>
            <option value="pencabutan">Pencabutan</option>
          </select>
        </div>
      </div>

      {/* Main Candidate Table */}
      <div className="border border-gray-200 rounded-xl overflow-hidden bg-white shadow-2xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-gray-50/80 border-b border-gray-200 text-gray-600 text-[11px] font-bold uppercase tracking-wider">
                <th className="py-3 px-3.5 w-10 text-center">
                  <input
                    type="checkbox"
                    checked={allSelectedOnPage}
                    disabled={isUpdatingSelection || selectableOnPage.length === 0}
                    onChange={(e) => {
                      if (e.target.checked) {
                        onSelectAllNew();
                      } else {
                        onSelectNone();
                      }
                    }}
                    className="rounded border-gray-300 text-red-600 focus:ring-red-500 h-3.5 w-3.5 cursor-pointer disabled:opacity-50"
                  />
                </th>
                <th className="py-3 px-3 min-w-[260px]">Judul Regulasi</th>
                <th className="py-3 px-3 min-w-[130px]">Nomor</th>
                <th className="py-3 px-3 w-20">Jenis</th>
                <th className="py-3 px-3 w-28">Bidang</th>
                <th className="py-3 px-3 w-24">Tanggal</th>
                <th className="py-3 px-3 w-24">Keberlakuan</th>
                <th className="py-3 px-3 w-20">Ukuran</th>
                <th className="py-3 px-3 w-28">Status KB</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 text-xs">
              {isLoading ? (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-gray-500">
                    <Loader2 size={24} className="animate-spin text-red-600 mx-auto mb-2" />
                    Memuat daftar kandidat...
                  </td>
                </tr>
              ) : candidates.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-10 text-center text-gray-500">
                    <AlertCircle size={24} className="text-gray-400 mx-auto mb-2" />
                    Tidak ada kandidat regulasi yang cocok dengan filter atau kata kunci.
                  </td>
                </tr>
              ) : (
                candidates.map((cand) => {
                  const isSudahAda = cand.match_status === 'sudah_ada';
                  const title = cand.document_title || cand.filename;

                  return (
                    <tr
                      key={cand.id}
                      className={`hover:bg-gray-50/80 transition-colors ${
                        cand.selected ? 'bg-red-50/20' : ''
                      } ${isSudahAda ? 'opacity-80 bg-gray-50/40' : ''}`}
                    >
                      {/* Checkbox */}
                      <td className="py-3 px-3.5 text-center">
                        <input
                          type="checkbox"
                          checked={cand.selected}
                          disabled={isSudahAda || isUpdatingSelection}
                          onChange={() => onToggleCandidate(cand)}
                          className="rounded border-gray-300 text-red-600 focus:ring-red-500 h-3.5 w-3.5 cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                        />
                      </td>

                      {/* Judul & Link */}
                      <td className="py-3 px-3">
                        <div className="font-semibold text-gray-900 line-clamp-2" title={title}>
                          {title}
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <a
                            href={cand.url || cand.detail_url || '#'}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center text-[11px] text-gray-500 hover:text-red-700 transition-colors font-mono"
                          >
                            <span className="truncate max-w-[220px]">{cand.filename}</span>
                            <ExternalLink size={10} className="ml-1 shrink-0" />
                          </a>

                          {cand.match_warning && (
                            <span className="inline-flex items-center text-[10px] text-amber-700 bg-amber-50 px-1.5 py-0.2 rounded border border-amber-200">
                              <AlertTriangle size={10} className="mr-0.5" />
                              {cand.match_warning}
                            </span>
                          )}
                        </div>

                        {/* Dokumen pembanding jika sudah ada */}
                        {isSudahAda && cand.match_document && (
                          <div className="mt-1 text-[11px] text-gray-500 bg-gray-100/80 px-2 py-0.5 rounded border border-gray-200 inline-block">
                            Sudah ada di KB:{' '}
                            <a
                              href={`#/knowledge/detail/${cand.match_document.id}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="font-medium text-red-700 hover:underline"
                            >
                              #{cand.match_document.id}{' '}
                              {cand.match_document.regulation_number || cand.match_document.title}
                            </a>
                          </div>
                        )}
                      </td>

                      {/* Nomor */}
                      <td className="py-3 px-3 text-gray-700 font-medium">
                        {cand.regulation_number || '-'}
                      </td>

                      {/* Jenis */}
                      <td className="py-3 px-3">
                        <span className="font-semibold text-gray-800">
                          {cand.regulation_type || '-'}
                        </span>
                      </td>

                      {/* Bidang */}
                      <td className="py-3 px-3 text-gray-600">
                        {cand.bidang || '-'}
                      </td>

                      {/* Tanggal / Tahun */}
                      <td className="py-3 px-3 text-gray-600 whitespace-nowrap">
                        {cand.release_date || (cand.regulation_year ? String(cand.regulation_year) : '-')}
                      </td>

                      {/* Status Keberlakuan */}
                      <td className="py-3 px-3 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${getStatusKeberlakuanBadgeClass(
                            cand.status_keberlakuan
                          )}`}
                        >
                          {getStatusKeberlakuanLabel(cand.status_keberlakuan)}
                        </span>
                      </td>

                      {/* Ukuran */}
                      <td className="py-3 px-3 text-gray-600 font-mono text-[11px] whitespace-nowrap">
                        {formatFileSize(cand.size_bytes)}
                      </td>

                      {/* Status KB */}
                      <td className="py-3 px-3 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${getMatchStatusBadgeClass(
                            cand.match_status
                          )}`}
                        >
                          {getMatchStatusLabel(cand.match_status)}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        <div className="flex items-center justify-between px-4 py-3 bg-gray-50/70 border-t border-gray-200 text-xs text-gray-600">
          <div>
            Menampilkan <span className="font-semibold text-gray-900">{candidates.length > 0 ? skip + 1 : 0}</span> sampai{' '}
            <span className="font-semibold text-gray-900">
              {Math.min(skip + candidates.length, total)}
            </span>{' '}
            dari <span className="font-semibold text-gray-900">{total}</span> berkas
          </div>

          <div className="flex items-center space-x-2">
            <button
              type="button"
              disabled={currentPage <= 1 || isLoading}
              onClick={() => onPageChange(Math.max(0, skip - limit))}
              className="p-1.5 rounded-lg border border-gray-300 bg-white hover:bg-gray-50 text-gray-700 disabled:opacity-40 transition-colors"
            >
              <ChevronLeft size={14} />
            </button>
            <span className="font-medium text-gray-700">
              Halaman {currentPage} dari {totalPages}
            </span>
            <button
              type="button"
              disabled={currentPage >= totalPages || isLoading}
              onClick={() => onPageChange(skip + limit)}
              className="p-1.5 rounded-lg border border-gray-300 bg-white hover:bg-gray-50 text-gray-700 disabled:opacity-40 transition-colors"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
