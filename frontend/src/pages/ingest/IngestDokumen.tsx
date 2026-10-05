import { Link, useSearchParams } from 'react-router-dom';
import { Globe, RefreshCw, UploadCloud, History } from 'lucide-react';
import ScrapingTab from './ScrapingTab';
import SyncTab from './SyncTab';
import UploadTab from './UploadTab';
import HistoryTab from './HistoryTab';

export default function IngestDokumen() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab');

  const activeTab: 'scraping' | 'sync' | 'upload' | 'riwayat' =
    tabParam === 'upload'
      ? 'upload'
      : tabParam === 'sync'
      ? 'sync'
      : tabParam === 'riwayat' || tabParam === 'history'
      ? 'riwayat'
      : 'scraping';

  const handleTabChange = (tab: 'scraping' | 'sync' | 'upload' | 'riwayat') => {
    setSearchParams(tab === 'scraping' ? {} : { tab });
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Breadcrumb & Header */}
      <div>
        <div className="flex items-center text-xs text-gray-500 mb-2">
          <Link to="/" className="hover:text-red-700 transition-colors">
            Dashboard
          </Link>
          <span className="mx-2 text-gray-300">/</span>
          <span className="text-gray-900 font-medium">Ingest Dokumen</span>
        </div>
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
              Ingest Dokumen Regulasi
            </h1>
            <p className="text-sm text-gray-600 mt-1">
              Pindai, sinkronisasi, dan unggah dokumen regulasi baru ke dalam Knowledge Base HERO.
            </p>
          </div>
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="flex space-x-6 border-b border-gray-200">
        <button
          type="button"
          onClick={() => handleTabChange('scraping')}
          className={`flex items-center pb-3 border-b-2 transition-colors text-sm ${
            activeTab === 'scraping'
              ? 'border-red-700 text-red-700 font-semibold'
              : 'border-transparent text-gray-500 hover:text-gray-700 font-medium'
          }`}
        >
          <Globe size={18} className="mr-2" />
          Scraping URL
        </button>

        <button
          type="button"
          onClick={() => handleTabChange('sync')}
          className={`flex items-center pb-3 border-b-2 transition-colors text-sm ${
            activeTab === 'sync'
              ? 'border-red-700 text-red-700 font-semibold'
              : 'border-transparent text-gray-500 hover:text-gray-700 font-medium'
          }`}
        >
          <RefreshCw size={18} className="mr-2" />
          Sinkronisasi OneDrive / Folder Lokal
        </button>

        <button
          type="button"
          onClick={() => handleTabChange('upload')}
          className={`flex items-center pb-3 border-b-2 transition-colors text-sm ${
            activeTab === 'upload'
              ? 'border-red-700 text-red-700 font-semibold'
              : 'border-transparent text-gray-500 hover:text-gray-700 font-medium'
          }`}
        >
          <UploadCloud size={18} className="mr-2" />
          Upload Manual
        </button>

        <button
          type="button"
          onClick={() => handleTabChange('riwayat')}
          className={`flex items-center pb-3 border-b-2 transition-colors text-sm ${
            activeTab === 'riwayat'
              ? 'border-red-700 text-red-700 font-semibold'
              : 'border-transparent text-gray-500 hover:text-gray-700 font-medium'
          }`}
        >
          <History size={18} className="mr-2" />
          Riwayat & Kegagalan
        </button>
      </div>

      {/* Tab Panels */}
      {activeTab === 'scraping' && <ScrapingTab />}
      {activeTab === 'sync' && <SyncTab />}
      {activeTab === 'upload' && <UploadTab />}
      {activeTab === 'riwayat' && <HistoryTab />}
    </div>
  );
}
