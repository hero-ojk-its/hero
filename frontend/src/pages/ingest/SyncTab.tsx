import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { 
  FolderOpen, 
  Folder, 
  Cloud, 
  Info, 
  ArrowRight, 
  ArrowLeft,
  Download,
  CheckCircle, 
  CheckCircle2, 
  Scan, 
  RefreshCw, 
  Clock, 
  Loader2, 
  Check, 
  X
} from 'lucide-react';
import { availableFolders, mockScrapedDocs } from './mock';

export default function SyncTab() {
  const [syncStep, setSyncStep] = useState<1 | 2 | 3 | 4>(1);
  const [sourceType, setSourceType] = useState<'folder' | 'onedrive'>('folder');
  const [folderPath, setFolderPath] = useState('/app/sources/peraturan_internal');
  const [isFolderModalOpen, setIsFolderModalOpen] = useState(false);
  const [tempSelectedFolder, setTempSelectedFolder] = useState('/app/sources/peraturan_internal');
  const [folderError, setFolderError] = useState('');
  const [accessClassification, setAccessClassification] = useState('Non-Publik');
  const [targetCategory, setTargetCategory] = useState('Perbankan');
  const [oneDriveNotice, setOneDriveNotice] = useState(false);
  const [isSyncScanning, setIsSyncScanning] = useState(false);
  const [syncScanProgress, setSyncScanProgress] = useState(0);
  const [syncProgress, setSyncProgress] = useState(0);

  const [selectedSyncDocs, setSelectedSyncDocs] = useState<string[]>(
    mockScrapedDocs.filter(d => d.active).map(d => d.num)
  );
  const [syncFilterTab, setSyncFilterTab] = useState<'all' | 'baru' | 'ada' | 'duplikat'>('all');

  const handleToggleSyncDoc = (num: string) => {
    setSelectedSyncDocs(prev => 
      prev.includes(num) ? prev.filter(n => n !== num) : [...prev, num]
    );
  };

  const handleToggleAllSync = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      setSelectedSyncDocs(mockScrapedDocs.filter(d => d.active).map(d => d.num));
    } else {
      setSelectedSyncDocs([]);
    }
  };

  const newDocsCount = mockScrapedDocs.filter((d) => d.active).length;
  const isAllSyncSelected = selectedSyncDocs.length === newDocsCount && newDocsCount > 0;

  const filteredSyncDocs = mockScrapedDocs.filter(doc => {
    if (syncFilterTab === 'baru') return doc.kbsStatus === 'Baru';
    if (syncFilterTab === 'ada') return doc.kbsStatus === 'Sudah Ada';
    if (syncFilterTab === 'duplikat') return doc.kbsStatus === 'Duplikat';
    return true;
  });


  // Effects for Sync
  useEffect(() => {
    if (!isSyncScanning) return;
    const interval = setInterval(() => {
      setSyncScanProgress(prev => {
        if (prev >= 100) {
          clearInterval(interval);
          setIsSyncScanning(false);
          setSyncStep(2);
          return 100;
        }
        return Math.min(100, prev + 20); 
      });
    }, 500);
    return () => clearInterval(interval);
  }, [isSyncScanning]);

  useEffect(() => {
    if (syncStep !== 3) return;
    const interval = setInterval(() => {
      setSyncProgress(prev => {
        if (prev >= 100) {
          clearInterval(interval);
          setTimeout(() => setSyncStep(4), 600);
          return 100;
        }
        return Math.min(100, prev + 20);
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [syncStep]);

  return (
    <div className="space-y-6">
          {syncStep === 1 && (
            <>
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="mb-6">
                  <h3 className="text-lg font-bold text-gray-900">Parameter Sinkronisasi</h3>
                  <p className="text-gray-600 text-sm mt-1">Pilih sumber dokumen untuk memindai file regulasi yang tersedia.</p>
                </div>

                <div className="space-y-6">
                  {/* SUMBER DOKUMEN */}
                  <div>
                    <label className="block text-xs font-bold text-gray-900 mb-3 uppercase tracking-wider">
                      Sumber Dokumen <span className="text-red-600">*</span>
                    </label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {/* Card 1: Folder Lokal (Aktif & Default) */}
                      <div 
                        className={`border-2 rounded-xl p-4 cursor-pointer flex items-start transition-all ${
                          sourceType === 'folder' 
                            ? 'bg-[#FDF2F2] border-[#B91C1C] shadow-sm' 
                            : 'bg-white border-gray-200 hover:border-gray-300'
                        }`}
                        onClick={() => {
                          setSourceType('folder');
                          setOneDriveNotice(false);
                        }}
                      >
                        <div className="mr-3.5 mt-0.5">
                          <div className={`w-4 h-4 rounded-full border flex items-center justify-center ${
                            sourceType === 'folder' ? 'border-[#B91C1C] bg-[#B91C1C]' : 'border-gray-300'
                          }`}>
                            {sourceType === 'folder' && <div className="w-1.5 h-1.5 bg-white rounded-full"></div>}
                          </div>
                        </div>
                        <FolderOpen size={24} className={`mr-3 mt-0.5 shrink-0 ${sourceType === 'folder' ? 'text-[#B91C1C]' : 'text-gray-500'}`} />
                        <div className="flex-1">
                          <div className="font-bold text-sm text-gray-900">Folder Lokal</div>
                          <div className="text-xs text-gray-500 mt-0.5">Penyimpanan Perangkat</div>
                        </div>
                      </div>
                      
                      {/* Card 2: OneDrive (Disabled tanpa teks "Segera tersedia") */}
                      <div 
                        className="border rounded-xl p-4 bg-gray-50/70 border-gray-200 opacity-75 cursor-pointer flex items-start transition-all hover:border-gray-300"
                        onClick={() => setOneDriveNotice(true)}
                      >
                        <div className="mr-3.5 mt-0.5">
                          <div className="w-4 h-4 rounded-full border border-gray-300 bg-white flex items-center justify-center">
                          </div>
                        </div>
                        <Cloud size={24} className="mr-3 mt-0.5 text-gray-400 shrink-0" />
                        <div className="flex-1">
                          <span className="font-bold text-sm text-gray-600">OneDrive</span>
                          <div className="text-xs text-gray-500 mt-0.5">Cloud Storage</div>
                        </div>
                      </div>
                    </div>

                    {/* Notifikasi Tooltip/Toast OneDrive */}
                    {oneDriveNotice && (
                      <div className="mt-3 p-3 bg-amber-50 border border-amber-200 text-amber-900 rounded-lg text-xs font-medium flex items-center justify-between animate-in fade-in duration-200">
                        <div className="flex items-center space-x-2">
                          <Info size={16} className="text-amber-600 shrink-0" />
                          <span>OneDrive direct connector belum tersedia pada fase ini.</span>
                        </div>
                        <button 
                          onClick={() => setOneDriveNotice(false)} 
                          className="text-amber-700 hover:text-amber-900 text-xs font-bold ml-3 px-2 py-0.5 rounded hover:bg-amber-100"
                        >
                          Tutup
                        </button>
                      </div>
                    )}
                  </div>

                  {/* FOLDER SUMBER (Saat Folder Lokal dipilih) */}
                  {sourceType === 'folder' && (
                    <div>
                      <div className="flex justify-between items-center mb-1.5">
                        <label className="block text-xs font-bold text-gray-900 uppercase tracking-wider">
                          Folder Sumber <span className="text-red-600">*</span>
                        </label>
                      </div>
                      
                      <div className="flex items-center gap-2">
                        <div className="relative flex-1">
                          <input 
                            type="text"
                            value={folderPath}
                            readOnly
                            onClick={() => {
                              setTempSelectedFolder(folderPath || availableFolders[0].path);
                              setIsFolderModalOpen(true);
                            }}
                            placeholder="/app/sources/peraturan_internal"
                            className={`block w-full px-3.5 py-2.5 bg-gray-50 border rounded-lg text-sm font-mono text-gray-900 transition-colors cursor-pointer hover:bg-gray-100/70 focus:outline-none ${
                              folderError ? 'border-red-500' : 'border-gray-300'
                            }`}
                          />
                        </div>
                        <button 
                          type="button"
                          onClick={() => {
                            setTempSelectedFolder(folderPath || availableFolders[0].path);
                            setIsFolderModalOpen(true);
                          }}
                          className="px-4 py-2.5 bg-white border border-gray-300 hover:border-gray-400 hover:bg-gray-50 text-gray-700 hover:text-gray-900 text-sm font-semibold rounded-lg flex items-center transition-colors shadow-sm shrink-0"
                        >
                          <FolderOpen size={16} className="mr-1.5 text-gray-500" />
                          {folderPath ? 'Ubah' : 'Pilih Folder'}
                        </button>
                      </div>

                      <p className="text-xs text-gray-500 mt-1.5">
                        Folder sumber harus berada di direktori <code className="bg-gray-100 px-1.5 py-0.5 rounded text-gray-700 font-mono text-xs">sources/</code> pada server/backend.
                      </p>
                      {folderError && (
                        <p className="text-xs text-red-600 font-semibold mt-1">
                          {folderError}
                        </p>
                      )}
                    </div>
                  )}

                  {/* KLASIFIKASI AKSES & KATEGORI TARGET KNOWLEDGE BASE */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <label className="block text-xs font-bold text-gray-900 mb-2 uppercase tracking-wider">
                        Klasifikasi Akses <span className="text-red-600">*</span>
                      </label>
                      <select 
                        value={accessClassification}
                        onChange={(e) => setAccessClassification(e.target.value)}
                        className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm text-gray-900 focus:ring-[#B91C1C] focus:border-[#B91C1C] bg-white font-medium"
                      >
                        <option value="Non-Publik">Non-Publik</option>
                        <option value="Publik">Publik</option>
                      </select>
                      <p className="text-xs text-gray-500 mt-1.5">Menentukan klasifikasi akses dokumen sebelum dipindai.</p>
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-gray-900 mb-2 uppercase tracking-wider">
                        Kategori Target Knowledge Base
                      </label>
                      <select 
                        value={targetCategory}
                        onChange={(e) => setTargetCategory(e.target.value)}
                        className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm text-gray-900 focus:ring-[#B91C1C] focus:border-[#B91C1C] bg-white font-medium"
                      >
                        <option value="Perbankan">Perbankan</option>
                        <option value="Pasar Modal">Pasar Modal</option>
                        <option value="Fintech">Fintech</option>
                        <option value="Asuransi">Asuransi</option>
                        <option value="Tata Kelola IT & AI">Tata Kelola IT & AI</option>
                        <option value="Lainnya">Lainnya</option>
                      </select>
                      <p className="text-xs text-gray-500 mt-1.5">Menentukan kategori dokumen yang akan digunakan di Knowledge Base.</p>
                    </div>
                  </div>

                  {/* INFO OTOMATIS */}
                  <div className="flex items-start p-4 bg-gray-50 border border-gray-200 rounded-lg">
                    <Info size={18} className="text-gray-600 mt-0.5 mr-3 shrink-0" />
                    <div>
                      <h4 className="text-sm font-bold text-gray-900">
                        Status regulasi dan pengecekan duplikasi akan dilakukan otomatis oleh sistem setelah pemindaian.
                      </h4>
                      <p className="text-xs text-gray-600 mt-1 leading-relaxed">
                        Sistem akan memeriksa dokumen PDF dan mencocokkannya dengan dokumen yang sudah ada untuk mencegah duplikasi.
                      </p>
                    </div>
                  </div>

                  {/* TOMBOL SCAN DOKUMEN */}
                  {!isSyncScanning && (
                    <div className="flex justify-end border-t border-gray-100 pt-6">
                      <button 
                        onClick={() => {
                          if (!folderPath.trim()) {
                            setFolderError('Folder sumber wajib diisi.');
                            return;
                          }
                          setFolderError('');
                          setIsSyncScanning(true);
                        }}
                        disabled={!folderPath.trim()}
                        className={`font-semibold px-6 py-2.5 rounded-lg flex items-center transition-colors shadow-sm ${
                          !folderPath.trim() 
                            ? 'bg-gray-300 text-gray-500 cursor-not-allowed' 
                            : 'bg-[#B91C1C] hover:bg-[#a01818] text-white cursor-pointer'
                        }`}
                      >
                        <Scan size={18} className="mr-2" />
                        Scan Dokumen
                      </button>
                    </div>
                  )}

                  {/* PROGRESS SCANNING */}
                  {isSyncScanning && (
                    <div className="mt-4 p-5 border border-[#B91C1C]/20 bg-[#FDF2F2] rounded-xl animate-in fade-in slide-in-from-top-4 duration-500">
                      <div className="flex justify-between items-center mb-3">
                        <div className="flex items-center text-sm font-semibold text-[#B91C1C]">
                          <Loader2 size={18} className="mr-2.5 animate-spin text-[#B91C1C]" />
                          Memindai Folder Sumber ({folderPath})...
                        </div>
                        <span className="text-sm font-bold text-[#B91C1C]">{syncScanProgress}%</span>
                      </div>
                      <div className="w-full bg-red-100 rounded-full h-2.5 mb-4">
                        <div className="bg-[#B91C1C] h-2.5 rounded-full transition-all duration-300 ease-out relative overflow-hidden" style={{ width: `${syncScanProgress}%` }}>
                          <div className="absolute inset-0 bg-white/20 animate-[shimmer_1.5s_infinite]"></div>
                        </div>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-2.5 gap-x-4 text-sm">
                        <div className={`flex items-center ${syncScanProgress >= 20 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                          {syncScanProgress >= 20 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : <Loader2 size={16} className="mr-2 animate-spin text-[#B91C1C]" />}
                          Mengakses direktori server
                        </div>
                        <div className={`flex items-center ${syncScanProgress >= 40 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                          {syncScanProgress >= 40 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : syncScanProgress >= 20 ? <Loader2 size={16} className="mr-2 animate-spin text-[#B91C1C]" /> : <Clock size={16} className="mr-2 text-gray-300" />}
                          Membaca file PDF pada folder
                        </div>
                        <div className={`flex items-center ${syncScanProgress >= 60 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                          {syncScanProgress >= 60 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : syncScanProgress >= 40 ? <Loader2 size={16} className="mr-2 animate-spin text-[#B91C1C]" /> : <Clock size={16} className="mr-2 text-gray-300" />}
                          Memeriksa dokumen regulasi
                        </div>
                        <div className={`flex items-center ${syncScanProgress >= 80 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                          {syncScanProgress >= 80 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : syncScanProgress >= 60 ? <Loader2 size={16} className="mr-2 animate-spin text-[#B91C1C]" /> : <Clock size={16} className="mr-2 text-gray-300" />}
                          Mencocokkan duplikasi dengan Knowledge Base
                        </div>
                        <div className={`flex items-center ${syncScanProgress >= 100 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                          {syncScanProgress >= 100 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : syncScanProgress >= 80 ? <Loader2 size={16} className="mr-2 animate-spin text-[#B91C1C]" /> : <Clock size={16} className="mr-2 text-gray-300" />}
                          Menyiapkan hasil pemindaian
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* RIWAYAT SINKRONISASI TERAKHIR */}
              {!isSyncScanning && (
                <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-in fade-in slide-in-from-bottom-2 duration-500 mt-6">
                  <div className="flex justify-between items-center mb-6">
                    <div className="flex items-center space-x-3">
                      <h3 className="text-lg font-bold text-gray-900">Riwayat Sinkronisasi Terakhir</h3>
                      <span className="text-gray-500 text-xs font-medium bg-gray-100 px-2.5 py-1 rounded-full">3 pemindaian terakhir</span>
                    </div>
                    <button className="text-sm font-semibold text-gray-700 flex items-center hover:text-[#B91C1C] transition-colors">
                      Buka Seluruh Riwayat <ArrowRight size={16} className="ml-1" />
                    </button>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-gray-100">
                          <th className="py-3 px-4 text-xs font-bold text-gray-700 uppercase tracking-wider">SUMBER</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-700 uppercase tracking-wider">WAKTU</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-700 uppercase tracking-wider">DOKUMEN DITEMUKAN</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-700 uppercase tracking-wider">DOKUMEN BARU</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-700 uppercase tracking-wider text-left">STATUS</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        <tr className="hover:bg-gray-50/50 transition-colors">
                          <td className="py-4 px-4">
                            <div className="flex items-center text-sm font-semibold text-gray-900">
                              <FolderOpen size={16} className="text-gray-500 mr-2 shrink-0" />
                              <span className="truncate">Folder Lokal — Regulasi Internal</span>
                            </div>
                            <div className="text-xs text-gray-400 font-mono mt-0.5 ml-6">/app/sources/peraturan_internal</div>
                          </td>
                          <td className="py-4 px-4 text-sm font-medium text-gray-600">Hari ini, 10:30 WIB</td>
                          <td className="py-4 px-4 text-sm text-gray-600 font-medium">12 dokumen</td>
                          <td className="py-4 px-4 text-sm font-bold text-green-700">5 baru</td>
                          <td className="py-4 px-4 text-left">
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-green-50 text-green-700 border border-green-200">
                              <span className="w-1.5 h-1.5 bg-green-500 rounded-full mr-1.5"></span>Berhasil
                            </span>
                          </td>
                        </tr>
                        <tr className="hover:bg-gray-50/50 transition-colors">
                          <td className="py-4 px-4">
                            <div className="flex items-center text-sm font-semibold text-gray-900">
                              <FolderOpen size={16} className="text-gray-500 mr-2 shrink-0" />
                              <span className="truncate">Folder Lokal — Regulasi Fintech</span>
                            </div>
                            <div className="text-xs text-gray-400 font-mono mt-0.5 ml-6">/app/sources/fintech_2026</div>
                          </td>
                          <td className="py-4 px-4 text-sm font-medium text-gray-600">Kemarin, 09:15 WIB</td>
                          <td className="py-4 px-4 text-sm text-gray-600 font-medium">8 dokumen</td>
                          <td className="py-4 px-4 text-sm font-bold text-green-700">3 baru</td>
                          <td className="py-4 px-4 text-left">
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-green-50 text-green-700 border border-green-200">
                              <span className="w-1.5 h-1.5 bg-green-500 rounded-full mr-1.5"></span>Berhasil
                            </span>
                          </td>
                        </tr>
                        <tr className="hover:bg-gray-50/50 transition-colors">
                          <td className="py-4 px-4">
                            <div className="flex items-center text-sm font-semibold text-gray-900">
                              <FolderOpen size={16} className="text-gray-500 mr-2 shrink-0" />
                              <span className="truncate">Folder Lokal — Tata Kelola IT & AI</span>
                            </div>
                            <div className="text-xs text-gray-400 font-mono mt-0.5 ml-6">/app/sources/it_governance</div>
                          </td>
                          <td className="py-4 px-4 text-sm font-medium text-gray-600">26 Sep 2026, 14:10 WIB</td>
                          <td className="py-4 px-4 text-sm text-gray-600 font-medium">6 dokumen</td>
                          <td className="py-4 px-4 text-sm font-medium text-gray-500">0 baru</td>
                          <td className="py-4 px-4 text-left">
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-green-50 text-green-700 border border-green-200">
                              <span className="w-1.5 h-1.5 bg-green-500 rounded-full mr-1.5"></span>Berhasil
                            </span>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Modal Pilih Folder Sumber (Compact & Lightweight) */}
              {isFolderModalOpen && (
                <div 
                  className="fixed inset-0 z-50 flex items-center justify-center bg-black/25 p-4 animate-in fade-in duration-150"
                  onClick={() => setIsFolderModalOpen(false)}
                >
                  <div 
                    className="bg-white rounded-xl shadow-xl border border-gray-200 w-full max-w-sm overflow-hidden animate-in zoom-in-95 duration-150 flex flex-col"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {/* Modal Header */}
                    <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
                      <h3 className="text-sm font-bold text-gray-900">Pilih Folder Sumber</h3>
                      <button
                        type="button"
                        onClick={() => setIsFolderModalOpen(false)}
                        className="text-gray-400 hover:text-gray-600 p-1 rounded-md hover:bg-gray-100 transition-colors"
                      >
                        <X size={16} />
                      </button>
                    </div>

                    {/* Modal Body */}
                    <div className="p-3.5 space-y-2">
                      <div className="text-xs text-gray-500 font-medium mb-1">
                        Folder yang tersedia:
                      </div>

                      <div className="space-y-2">
                        {availableFolders.map((f) => {
                          const isSelected = tempSelectedFolder === f.path;
                          return (
                            <div
                              key={f.path}
                              onClick={() => setTempSelectedFolder(f.path)}
                              className={`p-2.5 rounded-lg cursor-pointer border transition-all ${
                                isSelected
                                  ? 'border-[#B91C1C] bg-white ring-1 ring-[#B91C1C]/15 shadow-sm'
                                  : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50/50 bg-white'
                              }`}
                            >
                              <div className="flex items-center justify-between">
                                <div className="flex items-center space-x-2">
                                  <Folder size={15} className={isSelected ? 'text-[#B91C1C]' : 'text-gray-400'} />
                                  <span className={`text-sm font-semibold ${isSelected ? 'text-gray-900' : 'text-gray-800'}`}>
                                    {f.name}
                                  </span>
                                </div>
                                <span className="text-xs text-gray-400">
                                  {f.fileCount} file
                                </span>
                              </div>
                              <div className="flex items-center justify-between mt-1 pl-6">
                                <span className="text-xs text-gray-500 truncate mr-2">
                                  {f.description}
                                </span>
                                {isSelected && (
                                  <Check size={14} className="text-[#B91C1C] shrink-0" strokeWidth={2.5} />
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Modal Footer */}
                    <div className="px-4 py-2.5 bg-gray-50/80 border-t border-gray-100 flex items-center justify-end space-x-2">
                      <button
                        type="button"
                        onClick={() => setIsFolderModalOpen(false)}
                        className="px-3 py-1.5 border border-gray-300 text-gray-700 hover:bg-gray-100 text-xs font-semibold rounded-lg transition-colors bg-white"
                      >
                        Batal
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setFolderPath(tempSelectedFolder);
                          setFolderError('');
                          setIsFolderModalOpen(false);
                        }}
                        className="px-3.5 py-1.5 bg-[#B91C1C] hover:bg-[#a01818] text-white text-xs font-semibold rounded-lg transition-colors shadow-sm"
                      >
                        Pilih Folder
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}

          {syncStep === 2 && (
            <div className="animate-in fade-in duration-300">
              {/* TOP HEADER */}
              <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6 flex flex-col md:flex-row md:items-center justify-between shadow-sm">
                <div className="flex items-center space-x-4">
                  <span className="text-sm text-gray-500">Sumber Folder:</span>
                  <div className="flex items-center text-sm font-mono text-gray-800 bg-gray-50 border border-gray-200 rounded-md px-3 py-1.5 font-medium">
                    <FolderOpen size={15} className="mr-2 text-gray-500" />
                    {folderPath}
                  </div>
                </div>
                <div className="flex items-center space-x-4 mt-4 md:mt-0">
                  <div className="text-sm font-bold text-gray-900">Ditemukan 12 dokumen</div>
                  <div className="flex space-x-2">
                    <span className="flex items-center text-sm font-medium text-green-700 bg-green-50 border border-green-200 px-3 py-1 rounded-full">
                      <span className="w-1.5 h-1.5 rounded-full bg-green-500 mr-2"></span>
                      5 Baru
                    </span>
                    <span className="flex items-center text-sm font-medium text-gray-600 bg-gray-100 border border-gray-200 px-3 py-1 rounded-full">
                      <span className="w-1.5 h-1.5 rounded-full bg-gray-400 mr-2"></span>
                      6 Sudah Ada
                    </span>
                    <span className="flex items-center text-sm font-medium text-yellow-700 bg-yellow-50 border border-yellow-200 px-3 py-1 rounded-full">
                      <span className="w-1.5 h-1.5 rounded-full bg-yellow-500 mr-2"></span>
                      1 Duplikat
                    </span>
                  </div>
                </div>
              </div>

              {/* MAIN CONTENT AREA */}
              <div className="bg-white rounded-lg border border-gray-200 shadow-sm mb-6">
                {/* TABS & ACTIONS */}
                <div className="flex flex-col md:flex-row justify-between items-center border-b border-gray-200 px-6 pt-4 pb-0">
                  <div className="flex space-x-6">
                    <button 
                      onClick={() => setSyncFilterTab('all')}
                      className={`text-sm pb-4 border-b-2 transition-colors ${syncFilterTab === 'all' ? 'font-bold text-[#B91C1C] border-[#B91C1C]' : 'font-medium text-gray-500 border-transparent hover:text-gray-700'}`}
                    >
                      Semua (12)
                    </button>
                    <button 
                      onClick={() => setSyncFilterTab('baru')}
                      className={`text-sm pb-4 border-b-2 transition-colors ${syncFilterTab === 'baru' ? 'font-bold text-[#B91C1C] border-[#B91C1C]' : 'font-medium text-gray-500 border-transparent hover:text-gray-700'}`}
                    >
                      Baru (5)
                    </button>
                    <button 
                      onClick={() => setSyncFilterTab('ada')}
                      className={`text-sm pb-4 border-b-2 transition-colors ${syncFilterTab === 'ada' ? 'font-bold text-[#B91C1C] border-[#B91C1C]' : 'font-medium text-gray-500 border-transparent hover:text-gray-700'}`}
                    >
                      Sudah Ada (6)
                    </button>
                    <button 
                      onClick={() => setSyncFilterTab('duplikat')}
                      className={`text-sm pb-4 border-b-2 transition-colors ${syncFilterTab === 'duplikat' ? 'font-bold text-[#B91C1C] border-[#B91C1C]' : 'font-medium text-gray-500 border-transparent hover:text-gray-700'}`}
                    >
                      Duplikat (1)
                    </button>
                  </div>
                  <div className="flex items-center space-x-4 pb-4 md:pb-0 md:-mt-4">
                    <label className="flex items-center text-sm text-gray-700 font-medium cursor-pointer">
                      <input 
                        type="checkbox" 
                        checked={isAllSyncSelected}
                        onChange={handleToggleAllSync}
                        className="w-4 h-4 rounded border-gray-300 accent-[#B91C1C] mr-2" 
                      />
                      Pilih semua dokumen baru
                    </label>
                    <div className="h-4 w-px bg-gray-300"></div>
                    <div className="text-sm font-bold text-gray-900">{selectedSyncDocs.length} dokumen dipilih</div>
                  </div>
                </div>

                {/* TABLE */}
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead className="bg-white border-b border-gray-100">
                      <tr>
                        <th className="py-4 px-6 text-[11px] font-bold text-gray-500 uppercase tracking-wider w-10"></th>
                        <th className="py-4 px-6 text-[11px] font-bold text-gray-500 uppercase tracking-wider">DOKUMEN</th>
                        <th className="py-4 px-6 text-[11px] font-bold text-gray-500 uppercase tracking-wider">JENIS</th>
                        <th className="py-4 px-6 text-[11px] font-bold text-gray-500 uppercase tracking-wider">TAHUN</th>
                        <th className="py-4 px-6 text-[11px] font-bold text-gray-500 uppercase tracking-wider text-center">STATUS REGULASI</th>
                        <th className="py-4 px-6 text-[11px] font-bold text-gray-500 uppercase tracking-wider text-center">STATUS KBS</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {filteredSyncDocs.map((doc, idx) => (
                        <tr key={idx} className={doc.active ? 'bg-white' : 'bg-gray-50/50'}>
                          <td className="py-4 px-6 text-center">
                            <input 
                              type="checkbox" 
                              checked={selectedSyncDocs.includes(doc.num)}
                              onChange={() => handleToggleSyncDoc(doc.num)}
                              disabled={!doc.active}
                              className={`w-4 h-4 rounded border-gray-300 accent-[#B91C1C] ${!doc.active ? 'opacity-40' : 'cursor-pointer'}`} 
                            />
                          </td>
                          <td className="py-4 px-6">
                            <div className={`text-sm font-bold ${doc.active ? 'text-gray-800' : 'text-gray-400'}`}>{doc.title}</div>
                            <div className={`text-xs mt-1 ${doc.active ? 'text-gray-500' : 'text-gray-400'}`}>{doc.num}</div>
                          </td>
                          <td className="py-4 px-6">
                            <span className={`px-3 py-1 bg-gray-100 rounded-full text-xs font-semibold ${doc.active ? 'text-gray-600' : 'text-gray-400'}`}>{doc.type}</span>
                          </td>
                          <td className={`py-4 px-6 text-sm ${doc.active ? 'text-gray-600' : 'text-gray-400'}`}>{doc.year}</td>
                          <td className="py-4 px-6 text-center">
                            {doc.regStatus === 'Aktif' && (
                              <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium border ${doc.active ? 'bg-white border-green-200 text-green-700' : 'bg-white border-gray-200 text-green-700/50'}`}>
                                <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${doc.active ? 'bg-green-500' : 'bg-green-500/50'}`}></span>
                                Aktif
                              </span>
                            )}
                            {doc.regStatus === 'Diubah' && (
                              <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium border ${doc.active ? 'bg-white border-yellow-300 text-yellow-700' : 'bg-white border-gray-200 text-yellow-700/50'}`}>
                                <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${doc.active ? 'bg-yellow-500' : 'bg-yellow-500/50'}`}></span>
                                Diubah
                              </span>
                            )}
                            {doc.regStatus === 'Dicabut' && (
                              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium border bg-white border-gray-200 text-gray-500">
                                <span className="w-1.5 h-1.5 rounded-full mr-1.5 bg-gray-400"></span>
                                Dicabut
                              </span>
                            )}
                          </td>
                          <td className="py-4 px-6 text-center">
                            {doc.kbsStatus === 'Baru' && (
                              <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold border border-green-200 bg-white text-green-600">
                                Baru
                              </span>
                            )}
                            {doc.kbsStatus === 'Sudah Ada' && (
                              <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold border border-gray-200 bg-white text-gray-500">
                                Sudah Ada
                              </span>
                            )}
                            {doc.kbsStatus === 'Duplikat' && (
                              <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold border border-yellow-200 bg-white text-yellow-600">
                                Duplikat
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* BOTTOM BUTTONS */}
              <div className="flex items-center justify-between">
                <button 
                  onClick={() => setSyncStep(1)}
                  className="flex items-center text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
                >
                  <ArrowLeft size={16} className="mr-2" /> Kembali ke Parameter Scan
                </button>
                <button 
                  onClick={() => setSyncStep(3)}
                  disabled={selectedSyncDocs.length === 0}
                  className={`${selectedSyncDocs.length === 0 ? 'bg-gray-300 cursor-not-allowed text-gray-500' : 'bg-[#B91C1C] hover:bg-[#a01818] text-white'} font-medium px-6 py-2.5 rounded-md flex items-center transition-colors shadow-sm`}
                >
                  <Download size={18} className="mr-2" />
                  Download Dokumen Terpilih ({selectedSyncDocs.length})
                  <ArrowRight size={18} className="ml-2" />
                </button>
              </div>
            </div>
          )}

          {syncStep === 3 && (
            <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className="text-sm font-medium text-gray-500 mb-4 flex items-center space-x-2">
                <span>Dashboard</span> <span className="text-gray-400">&gt;</span> <span>Ingest Dokumen</span> <span className="text-gray-400">&gt;</span> <span>Sinkronisasi</span> <span className="text-gray-400">&gt;</span> <span className="text-gray-900 font-bold">Proses Ingest Dokumen</span>
              </div>
              <div className="mb-6">
                <h3 className="text-2xl font-bold text-gray-900 tracking-tight">Proses Ingest Dokumen</h3>
                <p className="text-gray-600 mt-1 text-sm">Memproses dan menambahkan dokumen ke Knowledge Base.</p>
              </div>

              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8 mb-6">
                <div className="flex flex-col lg:flex-row justify-between mb-8 pb-8 border-b border-gray-100 gap-6">
                  <div className="flex items-center space-x-12">
                    <div>
                      <div className="flex items-center space-x-3 mb-4">
                        <span className="text-gray-600 text-sm">Sumber Folder:</span>
                        <div className="flex items-center font-mono font-medium text-gray-900 text-sm">
                          <FolderOpen size={16} className="mr-2 text-gray-600" />
                          {folderPath}
                        </div>
                      </div>
                      <div className="flex items-center space-x-8 text-gray-600 text-sm">
                        <div className="flex items-center space-x-2">
                          <span>Target:</span> <span className="text-gray-900">Knowledge Base HERO (Sektor {targetCategory})</span>
                        </div>
                        <div className="text-gray-900">{selectedSyncDocs.length} Dokumen Dipilih</div>
                        <div className="font-bold text-gray-900">Sedang Berjalan</div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mb-8">
                  <div className="flex justify-between items-end mb-4">
                    <div className="flex items-center text-gray-600 font-medium">
                      <RefreshCw size={18} className="mr-3 text-gray-500 animate-spin" />
                      Memproses dan menambahkan dokumen ke Knowledge Base...
                    </div>
                    <div className="text-right">
                      <div className="text-xl font-bold text-gray-700">{syncProgress}%</div>
                      <div className="text-xs font-bold text-gray-500 uppercase tracking-wider">{Math.floor(syncProgress / 20)} DARI {selectedSyncDocs.length || 5} DOKUMEN SELESAI</div>
                    </div>
                  </div>
                  
                  <div className="w-full bg-gray-100 h-2 rounded-full overflow-hidden mb-8">
                    <div className="h-full bg-[#B91C1C] transition-all duration-500 ease-out" style={{ width: `${syncProgress}%` }}></div>
                  </div>
                  
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                      <thead className="border-b border-gray-200">
                        <tr>
                          <th className="py-3 px-4 text-xs font-bold text-gray-900 uppercase tracking-wider">DOKUMEN / NOMOR</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-900 uppercase tracking-wider">JENIS</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-900 uppercase tracking-wider">TAHUN</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-900 uppercase tracking-wider">STATUS</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {[
                          { title: 'POJK tentang Ketahanan dan Keamanan Siber Bank Umum', num: 'POJK No. 11/POJK.03/2024', type: 'POJK', year: '2024', threshold: 20 },
                          { title: 'SEOJK tentang Format Pelaporan Ketahanan Siber', num: 'SEOJK No. 14/SEOJK.03/2024', type: 'SEOJK', year: '2024', threshold: 40 },
                          { title: 'SEOJK tentang Mitigasi Risiko Penyelenggaraan Fintech P2P', num: 'SEOJK No. 29/SEOJK.05/2023', type: 'SEOJK', year: '2023', threshold: 60 },
                          { title: 'POJK tentang Manajemen Risiko Teknologi Informasi', num: 'POJK No. 05/POJK.03/2023', type: 'POJK', year: '2023', threshold: 80 },
                          { title: 'PDK tentang Perlindungan Konsumen Sektor Jasa Keuangan', num: 'PDK No. 08/PDK.07/2022', type: 'PDK', year: '2022', threshold: 100 }
                        ].map((doc, idx) => {
                          const isDone = syncProgress >= doc.threshold;
                          const isProcessing = syncProgress >= (doc.threshold - 20) && syncProgress < doc.threshold;

                          return (
                            <tr key={idx}>
                              <td className="py-4 px-4">
                                <div className="text-sm font-bold text-gray-700">{doc.title}</div>
                                <div className="text-sm text-gray-500 mt-1">{doc.num}</div>
                              </td>
                              <td className="py-4 px-4">
                                <span className="text-sm font-bold text-gray-700">{doc.type}</span>
                              </td>
                              <td className="py-4 px-4 text-sm text-gray-600">{doc.year}</td>
                              <td className="py-4 px-4">
                                {isDone ? (
                                  <div className="flex items-center text-sm font-medium text-green-600">
                                    <CheckCircle size={16} className="mr-2" />
                                    Selesai
                                  </div>
                                ) : isProcessing ? (
                                  <div className="flex items-center text-sm font-medium text-gray-500">
                                    <Loader2 size={16} className="mr-2 text-[#B91C1C] animate-spin" />
                                    Sedang Diproses
                                  </div>
                                ) : (
                                  <div className="flex items-center text-sm font-medium text-gray-400">
                                    <Clock size={16} className="mr-2 text-gray-400" />
                                    Menunggu
                                  </div>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
              
              <div className="flex items-start">
                <Info size={20} className="mr-2 text-gray-700 shrink-0" />
                <div className="text-sm text-gray-700 font-medium pt-0.5">
                  Proses ingest berlangsung secara otomatis. Dokumen akan ditambahkan ke Knowledge Base setelah proses selesai
                </div>
              </div>
            </div>
          )}

          {syncStep === 4 && (
            <div className="animate-in fade-in duration-300">
              <div className="text-sm font-medium text-gray-500 mb-4 flex items-center space-x-2">
                <span>Dashboard</span> <span className="text-gray-400">&gt;</span> <span>Ingest Dokumen</span> <span className="text-gray-400">&gt;</span> <span>Sinkronisasi</span> <span className="text-gray-400">&gt;</span> <span className="text-gray-900 font-bold">Dokumen Berhasil Ditambahkan</span>
              </div>
              <div className="mb-6">
                <h3 className="text-2xl font-bold text-gray-900 tracking-tight">Dokumen Berhasil Ditambahkan</h3>
                <p className="text-gray-600 mt-1 text-sm">5 dokumen berhasil ditambahkan ke Knowledge Base.</p>
              </div>

              <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
                <div className="flex items-start">
                  <div className="bg-green-100 rounded-full p-1 mr-3 shrink-0">
                    <CheckCircle2 size={20} className="text-green-600" />
                  </div>
                  <div>
                    <div className="font-bold text-green-800 text-sm mb-0.5">Proses Ingest Selesai</div>
                    <div className="text-sm text-green-700">
                      Seluruh dokumen telah berhasil diverifikasi dan disimpan ke repositori Knowledge Base HERO. Dokumen kini siap untuk dianalisis atau diharmonisasi.
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8 mb-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8 border-b border-gray-100 pb-8">
                  <div>
                    <div className="text-sm text-gray-500 mb-2">Sumber Folder</div>
                    <div className="flex items-center text-sm font-bold text-gray-900">
                      <FolderOpen size={16} className="mr-2 text-gray-500" />
                      {folderPath}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-500 mb-2">Target Knowledge Base</div>
                    <div className="text-sm font-bold text-gray-900">
                      HERO (Sektor {targetCategory})
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-500 mb-2">Status Pemrosesan</div>
                    <div className="flex items-center text-sm font-bold text-green-700">
                      <div className="w-2 h-2 bg-green-500 rounded-full mr-2"></div>
                      5 Dokumen Tersimpan
                    </div>
                  </div>
                </div>

                <div className="flex justify-between items-end mb-4">
                  <div className="text-sm font-bold text-gray-500 uppercase tracking-wider">DAFTAR DOKUMEN YANG DITAMBAHKAN</div>
                  <div className="text-sm text-gray-500">5 dari 5 berhasil diproses</div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead className="border-b border-gray-200">
                      <tr>
                        <th className="py-3 px-4 text-xs font-bold text-gray-900 uppercase tracking-wider">DOKUMEN / NOMOR</th>
                        <th className="py-3 px-4 text-xs font-bold text-gray-900 uppercase tracking-wider">JENIS</th>
                        <th className="py-3 px-4 text-xs font-bold text-gray-900 uppercase tracking-wider">TAHUN</th>
                        <th className="py-3 px-4 text-xs font-bold text-gray-900 uppercase tracking-wider">STATUS KBS</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {[
                        { title: 'POJK tentang Ketahanan dan Keamanan Siber Bank Umum', num: 'POJK No. 11/POJK.03/2024', type: 'POJK', year: '2024' },
                        { title: 'SEOJK tentang Format Pelaporan Ketahanan Siber', num: 'SEOJK No. 14/SEOJK.03/2024', type: 'SEOJK', year: '2024' },
                        { title: 'SEOJK tentang Mitigasi Risiko Penyelenggaraan Fintech P2P', num: 'SEOJK No. 29/SEOJK.05/2023', type: 'SEOJK', year: '2023' },
                        { title: 'POJK tentang Manajemen Risiko Teknologi Informasi', num: 'POJK No. 05/POJK.03/2023', type: 'POJK', year: '2023' },
                        { title: 'PDK tentang Perlindungan Konsumen Sektor Jasa Keuangan', num: 'PDK No. 08/PDK.07/2022', type: 'PDK', year: '2022' }
                      ].map((doc, idx) => (
                        <tr key={idx}>
                          <td className="py-4 px-4">
                            <div className="text-sm font-bold text-gray-700">{doc.title}</div>
                            <div className="text-sm text-gray-500 mt-1">{doc.num}</div>
                          </td>
                          <td className="py-4 px-4">
                            <span className="text-sm font-bold text-gray-700">{doc.type}</span>
                          </td>
                          <td className="py-4 px-4 text-sm text-gray-600">{doc.year}</td>
                          <td className="py-4 px-4 text-left">
                            <span className="inline-flex items-center px-3 py-1.5 rounded-full text-green-600 text-sm font-medium border border-green-200 bg-green-50">
                              <CheckCircle size={14} className="mr-1.5" />
                              Tersimpan di KBS
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="flex items-center text-sm text-gray-500 mb-8">
                <Clock size={18} className="mr-3 text-gray-400" />
                Dokumen telah sinkron dengan Knowledge Base dan dapat digunakan pada modul Analisa Regulasi dan Harmonisasi.
              </div>

              <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
                <button 
                  onClick={() => setSyncStep(1)}
                  className="w-full sm:w-auto px-6 py-2.5 border border-gray-300 text-gray-700 font-medium rounded-md hover:bg-gray-50 transition-colors flex items-center justify-center bg-white"
                >
                  <ArrowLeft size={16} className="mr-2" /> Sinkronisasi Dokumen Baru
                </button>
                <Link 
                  to="/knowledge"
                  className="w-full sm:w-auto bg-[#B91C1C] hover:bg-[#a01818] text-white font-medium px-6 py-2.5 rounded-md flex items-center justify-center transition-colors"
                >
                  Lihat Knowledge Base 
                  <ArrowRight size={16} className="ml-2" />
                </Link>
              </div>
            </div>
          )}
    </div>
  );
}
