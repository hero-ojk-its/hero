import { useState } from 'react';
import { 
  Globe, 
  Cloud, 
  Plus, 
  Edit2, 
  Trash2, 
  CheckCircle2, 
  Clock, 
  Loader2, 
  Layers,
  Power,
  FolderOpen
} from 'lucide-react';
import type { ScrapingSourceResponse } from '../../../lib/ingestApi';
import { JENIS_SUMBER_LABELS } from '../labels';

interface SourcePickerProps {
  sources: ScrapingSourceResponse[];
  selectedSourceId: number | null;
  onSelectSource: (source: ScrapingSourceResponse) => void;
  onAddSourceClick: () => void;
  onEditSourceClick: (source: ScrapingSourceResponse) => void;
  onDeleteSourceClick: (source: ScrapingSourceResponse) => void;
  onToggleActiveClick: (source: ScrapingSourceResponse) => void;
  isLoading?: boolean;
}

export default function SourcePicker({
  sources,
  selectedSourceId,
  onSelectSource,
  onAddSourceClick,
  onEditSourceClick,
  onDeleteSourceClick,
  onToggleActiveClick,
  isLoading = false,
}: SourcePickerProps) {
  const [filterActiveOnly, setFilterActiveOnly] = useState(false);

  // Tab Scraping URL hanya menampilkan sumber situs_web dan onedrive_public (folder_lokal dikelola di Tab Sinkronisasi)
  const scrapingSources = sources.filter(
    (s) => s.source_type === 'situs_web' || s.source_type === 'onedrive_public'
  );

  const displayedSources = filterActiveOnly 
    ? scrapingSources.filter((s) => s.is_active) 
    : scrapingSources;

  const activeCount = scrapingSources.filter((s) => s.is_active).length;

  const formatDate = (isoStr: string | null | undefined): string => {
    if (!isoStr) return 'Belum pernah dijalankan';
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return isoStr;
      return d.toLocaleDateString('id-ID', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }) + ' WIB';
    } catch {
      return isoStr;
    }
  };

  const getSourceIcon = (sourceType: string) => {
    switch (sourceType) {
      case 'onedrive_public':
        return <Cloud size={18} />;
      case 'folder_lokal':
        return <FolderOpen size={18} />;
      case 'situs_web':
      default:
        return <Globe size={18} />;
    }
  };

  const getSourceIconBg = (sourceType: string, isSelected: boolean) => {
    if (isSelected) return 'bg-red-100 text-red-700';
    switch (sourceType) {
      case 'onedrive_public':
        return 'bg-blue-50 text-blue-600';
      case 'folder_lokal':
        return 'bg-amber-50 text-amber-600';
      case 'situs_web':
      default:
        return 'bg-red-50 text-red-600';
    }
  };

  const getSourceBadgeBg = (sourceType: string) => {
    switch (sourceType) {
      case 'onedrive_public':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case 'folder_lokal':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      case 'situs_web':
      default:
        return 'bg-red-50 text-red-700 border-red-200';
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <label className="block text-sm font-semibold text-gray-900">
            Pilih Sumber Regulasi Terdaftar <span className="text-red-600">*</span>
          </label>
          <p className="text-xs text-gray-500 mt-0.5">
            Pilih situs web portal atau OneDrive terdaftar untuk dipindai dokumennya.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {scrapingSources.length > 0 && (
            <label className="flex items-center text-xs text-gray-600 cursor-pointer mr-2 select-none">
              <input
                type="checkbox"
                checked={filterActiveOnly}
                onChange={(e) => setFilterActiveOnly(e.target.checked)}
                className="rounded border-gray-300 text-red-600 focus:ring-red-500 mr-1.5 h-3.5 w-3.5"
              />
              Hanya Aktif ({activeCount})
            </label>
          )}
          <button
            type="button"
            onClick={onAddSourceClick}
            className="inline-flex items-center px-3 py-1.5 text-xs font-semibold text-red-700 bg-red-50 hover:bg-red-100 border border-red-200 rounded-lg transition-colors shadow-sm"
          >
            <Plus size={14} className="mr-1" />
            Tambah Sumber
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center p-8 bg-gray-50 rounded-xl border border-gray-200">
          <Loader2 size={24} className="animate-spin text-red-600 mr-2" />
          <span className="text-sm text-gray-600 font-medium">Memuat daftar sumber...</span>
        </div>
      ) : displayedSources.length === 0 ? (
        <div className="text-center p-8 bg-gray-50/70 rounded-xl border-2 border-dashed border-gray-200">
          <Globe size={32} className="mx-auto text-gray-400 mb-2" />
          <p className="text-sm font-medium text-gray-700">Belum ada sumber terdaftar</p>
          <p className="text-xs text-gray-500 mt-1 max-w-sm mx-auto">
            Klik tombol &quot;Tambah Sumber&quot; di atas untuk mendaftarkan URL portal regulasi pertama Anda.
          </p>
          <button
            type="button"
            onClick={onAddSourceClick}
            className="mt-4 inline-flex items-center px-4 py-2 text-xs font-semibold text-white bg-red-700 hover:bg-red-800 rounded-lg transition-colors"
          >
            <Plus size={14} className="mr-1.5" />
            Daftarkan Sumber Baru
          </button>
        </div>
      ) : (
        <div className="space-y-2.5 max-h-[360px] overflow-y-auto pr-1">
          {displayedSources.map((source) => {
            const isSelected = selectedSourceId === source.id;

            return (
              <div
                key={source.id}
                onClick={() => onSelectSource(source)}
                className={`group relative p-4 rounded-xl border transition-all cursor-pointer ${
                  isSelected
                    ? 'border-red-600 bg-red-50/30 ring-1 ring-red-600 shadow-sm'
                    : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50/50'
                } ${!source.is_active ? 'opacity-70 bg-gray-50/60' : ''}`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-start space-x-3 min-w-0 flex-1">
                    <div
                      className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${getSourceIconBg(
                        source.source_type,
                        isSelected
                      )}`}
                    >
                      {getSourceIcon(source.source_type)}
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-bold text-sm text-gray-900 truncate">
                          {source.name}
                        </span>
                        <span
                          className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${getSourceBadgeBg(
                            source.source_type
                          )}`}
                        >
                          {JENIS_SUMBER_LABELS[source.source_type] || source.source_type}
                        </span>
                        {!source.is_active && (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 border border-gray-200">
                            Nonaktif
                          </span>
                        )}
                        <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-gray-50 text-gray-600 border border-gray-200 flex items-center">
                          <Layers size={10} className="mr-1" />
                          Kedalaman: {source.crawl_depth ?? 1}
                        </span>
                      </div>

                      <p className="text-xs text-gray-500 font-mono truncate mt-1">
                        {source.url || source.address}
                      </p>

                      <div className="flex items-center gap-4 text-[11px] text-gray-500 mt-2">
                        <span className="flex items-center">
                          <Clock size={12} className="mr-1 text-gray-400" />
                          Terakhir: {formatDate(source.last_run_at)}
                        </span>
                        {source.last_run_status && (
                          <span
                            className={`font-medium ${
                              source.last_run_status === 'selesai'
                                ? 'text-emerald-600'
                                : source.last_run_status === 'gagal'
                                ? 'text-red-600'
                                : 'text-amber-600'
                            }`}
                          >
                            • Status: {source.last_run_status}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Actions & Selection radio */}
                  <div className="flex items-center space-x-2 ml-4 shrink-0" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      title={source.is_active ? 'Nonaktifkan sumber' : 'Aktifkan sumber'}
                      onClick={() => onToggleActiveClick(source)}
                      className={`p-1.5 rounded-lg border text-xs transition-colors ${
                        source.is_active
                          ? 'border-gray-200 text-gray-500 hover:text-amber-700 hover:bg-amber-50 hover:border-amber-200'
                          : 'border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100'
                      }`}
                    >
                      <Power size={13} />
                    </button>
                    <button
                      type="button"
                      title="Ubah konfigurasi sumber"
                      onClick={() => onEditSourceClick(source)}
                      className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:text-gray-900 hover:bg-gray-100 transition-colors"
                    >
                      <Edit2 size={13} />
                    </button>
                    <button
                      type="button"
                      title="Hapus sumber"
                      onClick={() => onDeleteSourceClick(source)}
                      className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:text-red-700 hover:bg-red-50 hover:border-red-200 transition-colors"
                    >
                      <Trash2 size={13} />
                    </button>

                    <div
                      className={`w-5 h-5 rounded-full flex items-center justify-center ml-2 border transition-all ${
                        isSelected
                          ? 'border-red-600 bg-red-600 text-white'
                          : 'border-gray-300 bg-white'
                      }`}
                    >
                      {isSelected && <CheckCircle2 size={14} className="stroke-[3]" />}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
