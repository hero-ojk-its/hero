import React, { useState, useEffect } from 'react';
import { Search, FileText, Globe, Cloud, ChevronDown, CheckCircle, UploadCloud, FolderOpen } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

import { regulasiData } from '../data/regulasiData';

const filterOptions: Record<string, string[]> = {
  Kategori: ['Semua Kategori', 'Perbankan', 'Pasar Modal', 'Fintech', 'Asuransi', 'Tata Kelola IT & AI', 'Lainnya'],
  Jenis: ['Semua Jenis', 'POJK', 'PDK', 'SEDK', 'SEOJK'],
  Tahun: ['Semua Tahun', '2026', '2025', '2024', '2023', '2022'],
  Topik: ['Semua Topik', 'Ketahanan Siber', 'Tata Kelola', 'AI', 'Perlindungan Konsumen', 'Manajemen Risiko'],
  Status: ['Semua Status', 'Aktif', 'Diubah', 'Dicabut', 'Tidak Berlaku'],
  Sumber: ['Semua Sumber', 'Scraping', 'Folder Lokal', 'OneDrive', 'Upload Manual']
};

export default function KnowledgeBase() {
  const location = useLocation();
  const navigate = useNavigate();
  
  // Filter states
  const [openFilter, setOpenFilter] = useState<string | null>(null);
  const [filters, setFilters] = useState<Record<string, string>>({
    Kategori: 'Semua Kategori',
    Jenis: 'Semua Jenis',
    Tahun: 'Semua Tahun',
    Topik: 'Semua Topik',
    Status: 'Semua Status',
    Sumber: 'Semua Sumber'
  });
  const [topikSearch, setTopikSearch] = useState('');

  // Read URL query params on mount
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const kategori = params.get('kategori');
    const jenis = params.get('jenis');
    const tahun = params.get('tahun');
    const topik = params.get('topik');

    setFilters(prev => {
      const newFilters = { ...prev };
      if (kategori && filterOptions.Kategori.includes(kategori)) newFilters.Kategori = kategori;
      if (jenis && filterOptions.Jenis.includes(jenis)) newFilters.Jenis = jenis;
      if (tahun && filterOptions.Tahun.includes(tahun)) newFilters.Tahun = tahun;
      if (topik && filterOptions.Topik.includes(topik)) newFilters.Topik = topik;
      return newFilters;
    });
  }, [location.search]);

  // Close dropdown on outside click
  React.useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (!(e.target as Element).closest('.filter-dropdown-container')) {
        setOpenFilter(null);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case 'Aktif':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-green-50 text-green-700 text-[11px] font-semibold border border-green-200/60">
            <span className="w-1.5 h-1.5 rounded-full bg-green-600"></span>
            Aktif
          </span>
        );
      case 'Diubah':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-50 text-amber-700 text-[11px] font-semibold border border-amber-200/60">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
            Diubah
          </span>
        );
      case 'Dicabut':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-red-50 text-red-700 text-[11px] font-semibold border border-red-200/60">
            <span className="w-1.5 h-1.5 rounded-full bg-red-600"></span>
            Dicabut
          </span>
        );
      default:
        return <span>{status}</span>;
    }
  };

  return (
    <div className="max-w-[1200px] mx-auto space-y-6 relative">
      {/* Breadcrumb */}
      <div className="text-xs text-gray-500">
        Dashboard / <span className="font-semibold text-gray-900">Knowledge Base</span>
      </div>

      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold text-gray-900">Knowledge Base</h2>
          <span className="bg-red-50 text-red-700 px-2.5 py-1 rounded-full text-xs font-semibold border border-red-100">
            128 dokumen
          </span>
        </div>
        <p className="text-gray-500 mt-2 text-sm">Kelola dan temukan regulasi yang tersimpan dalam sistem.</p>
      </div>

      {/* Search and Filters Container */}
      <div className="bg-gray-50 p-4 rounded-xl border border-gray-200 space-y-4">
        {/* Search Bar */}
        <div className="relative w-full">
          <div className="absolute inset-y-0 left-0 flex items-center pl-4 pointer-events-none">
            <Search className="w-5 h-5 text-gray-400" />
          </div>
          <input 
            type="text" 
            className="w-full pl-11 pr-4 py-3 bg-white border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-500 transition-colors placeholder-gray-400 shadow-sm"
            placeholder="Cari regulasi berdasarkan judul, nomor, atau topik..." 
          />
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 relative z-20">
          {Object.entries(filterOptions).map(([filterName, options]) => (
            <div key={filterName} className="relative filter-dropdown-container">
              <button 
                onClick={() => setOpenFilter(openFilter === filterName ? null : filterName)}
                className={`flex items-center gap-2 px-3.5 py-2 bg-white border rounded-lg text-sm font-medium transition-colors shadow-sm ${openFilter === filterName ? 'border-red-500 text-red-700 ring-2 ring-red-500/20' : 'border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400'}`}
              >
                {filters[filterName]}
                <ChevronDown className={`w-4 h-4 transition-transform ${openFilter === filterName ? 'rotate-180 text-red-500' : 'text-gray-400'}`} />
              </button>
              
              {openFilter === filterName && (
                <div className="absolute top-full left-0 mt-2 w-56 bg-white border border-gray-200 rounded-xl shadow-xl z-30 py-2 overflow-hidden">
                  {filterName === 'Topik' && (
                    <div className="px-3 pb-2 border-b border-gray-100 mb-2">
                      <div className="relative">
                        <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-gray-400" />
                        <input
                          type="text"
                          placeholder="Cari topik..."
                          value={topikSearch}
                          onChange={(e) => setTopikSearch(e.target.value)}
                          className="w-full pl-9 pr-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-red-500 focus:border-red-500"
                        />
                      </div>
                    </div>
                  )}
                  
                  <div className="max-h-60 overflow-y-auto [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-thumb]:bg-gray-200 [&::-webkit-scrollbar-thumb]:rounded-full hover:[&::-webkit-scrollbar-thumb]:bg-gray-300">
                    {options
                      .filter(opt => filterName === 'Topik' ? opt.toLowerCase().includes(topikSearch.toLowerCase()) : true)
                      .map((option, idx) => (
                      <button
                        key={idx}
                        onClick={() => {
                          setFilters({...filters, [filterName]: option});
                          setOpenFilter(null);
                          if (filterName === 'Topik') setTopikSearch('');
                        }}
                        className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center justify-between ${filters[filterName] === option ? 'bg-red-50 text-red-700 font-semibold' : 'text-gray-700 hover:bg-gray-50'}`}
                      >
                        {option}
                        {filters[filterName] === option && <CheckCircle className="w-4 h-4 text-red-600" />}
                      </button>
                    ))}
                    {filterName === 'Topik' && options.filter(opt => opt.toLowerCase().includes(topikSearch.toLowerCase())).length === 0 && (
                      <div className="px-4 py-3 text-xs text-gray-500 text-center">Topik tidak ditemukan</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Table Section */}
      <div className="space-y-4">
        {/* Table Header Controls */}
        <div className="flex justify-between items-center text-sm">
          <span className="text-gray-500">Menampilkan 128 dari 128 regulasi</span>
          <button className="text-gray-500 hover:text-gray-900 underline underline-offset-2 transition-colors">
            Reset Filter
          </button>
        </div>

        {/* Data Table */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-gray-50/80 border-b border-gray-200">
                  <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Judul Regulasi</th>
                  <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Jenis</th>
                  <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Nomor</th>
                  <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Kategori</th>
                  <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Topik</th>
                  <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Tahun</th>
                  <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Sumber</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {regulasiData.map((item) => (
                  <tr 
                    key={item.id} 
                    onClick={() => navigate(`/knowledge/detail/${item.id}`, { state: { regulasi: item } })}
                    className="hover:bg-gray-50 group cursor-pointer"
                  >
                    <td className="px-3 py-3">
                      <div className="flex items-start gap-3">
                        <div className="p-2 rounded-lg bg-red-50 text-red-600 border border-red-100 flex-shrink-0 group-hover:bg-red-100 transition-colors">
                          <FileText className="w-4 h-4" />
                        </div>
                        <span className="font-semibold text-gray-900 text-sm group-hover:text-red-700 transition-colors mt-1">
                          {item.judul}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap">
                      <span className="px-2.5 py-1 bg-gray-100 text-gray-700 text-xs font-bold rounded-md border border-gray-200/60">
                        {item.jenis}
                      </span>
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-500 font-medium group-hover:text-gray-900">
                      {item.nomor}
                    </td>
                    <td className="px-3 py-3 text-sm text-gray-900 font-medium">
                      {item.kategori}
                    </td>
                    <td className="px-3 py-3">
                      <span className="px-2.5 py-1 bg-slate-50 text-slate-600 text-[11px] font-semibold border border-slate-200/60 rounded-md">
                        {item.topik}
                      </span>
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-500 font-medium">
                      {item.tahun}
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap">
                      {renderStatusBadge(item.status)}
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap">
                      <div className="flex items-center gap-2 text-gray-500 group-hover:text-gray-700 transition-colors">
                        {item.sumber === 'Scraping' ? (
                          <Globe className="w-4 h-4 text-blue-500" />
                        ) : item.sumber === 'Upload Manual' ? (
                          <UploadCloud className="w-4 h-4 text-red-600" />
                        ) : item.sumber === 'Folder Lokal' ? (
                          <FolderOpen className="w-4 h-4 text-amber-600" />
                        ) : (
                          <Cloud className="w-4 h-4 text-sky-500" />
                        )}
                        <span className="text-xs font-medium">{item.sumber}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Pagination */}
        <div className="flex justify-between items-center py-2 text-sm text-gray-500">
          <span>Menampilkan 1-8 dari 128 regulasi</span>
          <div className="flex items-center gap-1">
            <button className="px-3 py-1.5 text-gray-500 hover:text-gray-900 font-medium transition-colors">
              Sebelumnya
            </button>
            <button className="w-8 h-8 flex items-center justify-center rounded bg-gray-900 text-white font-semibold">
              1
            </button>
            <button className="w-8 h-8 flex items-center justify-center rounded hover:bg-gray-100 font-medium text-gray-700 transition-colors">
              2
            </button>
            <button className="w-8 h-8 flex items-center justify-center rounded hover:bg-gray-100 font-medium text-gray-700 transition-colors">
              3
            </button>
            <span className="w-8 h-8 flex items-center justify-center text-gray-400">...</span>
            <button className="w-8 h-8 flex items-center justify-center rounded hover:bg-gray-100 font-medium text-gray-700 transition-colors">
              16
            </button>
            <button className="px-3 py-1.5 text-gray-900 font-semibold hover:bg-gray-50 rounded transition-colors ml-1">
              Selanjutnya
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
