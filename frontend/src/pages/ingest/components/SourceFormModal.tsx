import React, { useState } from 'react';
import { X, Globe, Cloud, Loader2, AlertCircle } from 'lucide-react';
import type { ScrapingSourceResponse, ScrapingSourceCreate, ScrapingSourceUpdate } from '../../../lib/ingestApi';
import { ApiError } from '../../../lib/api';

interface SourceFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: ScrapingSourceCreate | ScrapingSourceUpdate) => Promise<void>;
  initialData?: ScrapingSourceResponse | null;
  mode?: 'create' | 'edit';
}

export default function SourceFormModal({
  isOpen,
  onClose,
  onSubmit,
  initialData,
  mode = 'create',
}: SourceFormModalProps) {
  const [name, setName] = useState(initialData?.name || '');
  const [url, setUrl] = useState(initialData?.url || initialData?.address || '');
  const [sourceType, setSourceType] = useState<'situs_web' | 'onedrive_public'>(
    initialData?.source_type === 'onedrive_public' ? 'onedrive_public' : 'situs_web'
  );
  const [crawlDepth, setCrawlDepth] = useState<number>(initialData?.crawl_depth || 1);
  const [accessClassification, setAccessClassification] = useState<'publik' | 'non_publik'>(
    initialData?.default_access_classification === 'non_publik' ? 'non_publik' : 'publik'
  );
  const [isActive, setIsActive] = useState<boolean>(initialData?.is_active ?? true);

  const [urlError, setUrlError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setUrlError(null);
    setNameError(null);
    setGeneralError(null);

    // Client-side quick check
    if (!name.trim()) {
      setNameError('Nama sumber wajib diisi');
      return;
    }
    if (!url.trim()) {
      setUrlError('URL sumber wajib diisi');
      return;
    }

    setIsSubmitting(true);
    try {
      const payload: ScrapingSourceCreate = {
        name: name.trim(),
        url: url.trim(),
        source_type: sourceType,
        crawl_depth: crawlDepth,
        recursive: true,
        default_access_classification: accessClassification,
        default_document_role: 'corpus_eksisting',
        is_active: isActive,
      };

      await onSubmit(payload);
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        const msg = err.message || '';
        const detailStr = typeof err.detail === 'string' ? err.detail : '';
        const combined = `${msg} ${detailStr}`.toLowerCase();

        if (
          combined.includes('url') ||
          combined.includes('alamat') ||
          combined.includes('terdaftar') ||
          combined.includes('protokol')
        ) {
          setUrlError(err.message);
        } else if (combined.includes('nama') || combined.includes('name')) {
          setNameError(err.message);
        } else {
          setGeneralError(err.message);
        }
      } else {
        const errorMsg = err instanceof Error ? err.message : String(err);
        setGeneralError(errorMsg);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full overflow-hidden border border-gray-100 animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gray-50/50">
          <div>
            <h3 className="text-lg font-bold text-gray-900">
              {mode === 'edit' ? 'Ubah Sumber Regulasi' : 'Tambah Sumber Regulasi'}
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Daftarkan URL situs portal atau folder OneDrive publik sebagai target crawling.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {generalError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start text-xs text-red-700">
              <AlertCircle size={16} className="text-red-500 mr-2 shrink-0 mt-0.5" />
              <span>{generalError}</span>
            </div>
          )}

          {/* Nama Sumber */}
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-1">
              Nama Sumber <span className="text-red-600">*</span>
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (nameError) setNameError(null);
              }}
              placeholder="Contoh: JDIH Kementerian ESDM"
              className={`block w-full px-3.5 py-2.5 border rounded-lg text-sm transition-colors focus:outline-none focus:ring-2 ${
                nameError
                  ? 'border-red-300 focus:ring-red-500/20 focus:border-red-500 bg-red-50/30'
                  : 'border-gray-300 focus:ring-red-500/20 focus:border-red-500'
              }`}
            />
            {nameError && (
              <p className="mt-1.5 text-xs text-red-600 font-medium flex items-center">
                <AlertCircle size={12} className="mr-1 shrink-0" />
                {nameError}
              </p>
            )}
          </div>

          {/* Jenis Sumber */}
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-1.5">
              Jenis Sumber <span className="text-red-600">*</span>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setSourceType('situs_web')}
                className={`flex items-center justify-center p-3 rounded-lg border text-sm font-medium transition-all ${
                  sourceType === 'situs_web'
                    ? 'border-red-600 bg-red-50/50 text-red-700 ring-1 ring-red-600'
                    : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'
                }`}
              >
                <Globe size={16} className="mr-2 text-red-600" />
                Situs Web (HTML)
              </button>
              <button
                type="button"
                onClick={() => setSourceType('onedrive_public')}
                className={`flex items-center justify-center p-3 rounded-lg border text-sm font-medium transition-all ${
                  sourceType === 'onedrive_public'
                    ? 'border-red-600 bg-red-50/50 text-red-700 ring-1 ring-red-600'
                    : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'
                }`}
              >
                <Cloud size={16} className="mr-2 text-blue-600" />
                OneDrive Publik
              </button>
            </div>
          </div>

          {/* URL Sumber */}
          <div>
            <div className="flex justify-between mb-1">
              <label className="block text-sm font-medium text-gray-900">
                Alamat URL Sumber <span className="text-red-600">*</span>
              </label>
              <span className="text-xs text-gray-400">Harus diawali http:// atau https://</span>
            </div>
            <input
              type="text"
              required
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                if (urlError) setUrlError(null);
              }}
              placeholder={
                sourceType === 'situs_web'
                  ? 'https://jdih.esdm.go.id'
                  : 'https://oneojk-my.sharepoint.com/:f:/...'
              }
              className={`block w-full px-3.5 py-2.5 border rounded-lg text-sm transition-colors focus:outline-none focus:ring-2 font-mono ${
                urlError
                  ? 'border-red-400 focus:ring-red-500/20 focus:border-red-500 bg-red-50/40 text-red-900'
                  : 'border-gray-300 focus:ring-red-500/20 focus:border-red-500'
              }`}
            />
            {urlError && (
              <p className="mt-1.5 text-xs text-red-600 font-semibold flex items-start">
                <AlertCircle size={14} className="mr-1 shrink-0 mt-0.5" />
                <span>{urlError}</span>
              </p>
            )}
          </div>

          {/* Kedalaman Crawling & Klasifikasi Akses */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-900 mb-1">
                Kedalaman Crawling
              </label>
              <select
                value={crawlDepth}
                onChange={(e) => setCrawlDepth(Number(e.target.value))}
                className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-red-500/20 focus:border-red-500 bg-white"
              >
                <option value={1}>1 Level (Halaman Ini Saja)</option>
                <option value={2}>2 Level (Rekomendasi)</option>
                <option value={3}>3 Level (Pencarian Mendalam)</option>
                <option value={4}>4 Level (Sangat Dalam)</option>
                <option value={5}>5 Level (Maksimal)</option>
              </select>
              <p className="text-[11px] text-gray-500 mt-1">
                {crawlDepth === 1
                  ? 'Hanya memindai tautan PDF langsung pada halaman awal.'
                  : crawlDepth === 2
                  ? 'Menelusuri 1 tautan cabang di dalam situs (direkomendasikan).'
                  : 'Menelusuri sub-cabang bertingkat (proses lebih lama).'}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-900 mb-1">
                Klasifikasi Akses Default
              </label>
              <select
                value={accessClassification}
                onChange={(e) => setAccessClassification(e.target.value as 'publik' | 'non_publik')}
                className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-red-500/20 focus:border-red-500 bg-white"
              >
                <option value="publik">Publik (Terbuka)</option>
                <option value="non_publik">Non-Publik (Internal)</option>
              </select>
              <p className="text-[11px] text-gray-500 mt-1">
                Hak akses bawaan untuk dokumen hasil scraping.
              </p>
            </div>
          </div>

          {/* Status Aktif */}
          <div className="flex items-center justify-between pt-2 border-t border-gray-100">
            <div>
              <label className="text-sm font-medium text-gray-900 block">Status Sumber</label>
              <span className="text-xs text-gray-500">
                {isActive ? 'Aktif (tersedia untuk pemindaian)' : 'Nonaktif (disembunyikan dari pilihan)'}
              </span>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-red-700"></div>
            </label>
          </div>

          {/* Footer Actions */}
          <div className="flex items-center justify-end space-x-3 pt-4 border-t border-gray-100">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-5 py-2 text-sm font-semibold text-white bg-red-700 hover:bg-red-800 rounded-lg shadow-sm transition-colors flex items-center disabled:opacity-50"
            >
              {isSubmitting && <Loader2 size={16} className="animate-spin mr-2" />}
              {mode === 'edit' ? 'Simpan Perubahan' : 'Tambah Sumber'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
