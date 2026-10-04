import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { 
  UploadCloud, 
  FileText, 
  CheckCircle, 
  CheckCircle2, 
  ArrowRight,
  ArrowLeft, 
  Download,
  Clock, 
  Loader2, 
  X, 
  Info,
  Scan,
  RefreshCw,
  Plus
} from 'lucide-react';
import { initialManualFiles, type ManualFileItem, mockManualUploadHistory } from './mock';

export default function UploadTab() {
  const [uploadStep, setUploadStep] = useState<1 | 2 | 3 | 4>(1);
  const [isDragging, setIsDragging] = useState(false);
  const [manualFiles, setManualFiles] = useState<ManualFileItem[]>(initialManualFiles);
  const [uploadAccessClassification, setUploadAccessClassification] = useState('Non-Publik');
  const [uploadTargetCategory, setUploadTargetCategory] = useState('Perbankan');
  const [uploadNotes, setUploadNotes] = useState('');
  const [isUploadScanning, setIsUploadScanning] = useState(false);
  const [uploadScanProgress, setUploadScanProgress] = useState(0);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [selectedUploadDocs, setSelectedUploadDocs] = useState<string[]>(
    initialManualFiles.filter(d => d.active).map(d => d.num)
  );
  const [uploadFilterTab, setUploadFilterTab] = useState<'all' | 'baru' | 'ada' | 'duplikat'>('all');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleToggleUploadDoc = (num: string) => {
    setSelectedUploadDocs(prev => 
      prev.includes(num) ? prev.filter(n => n !== num) : [...prev, num]
    );
  };

  const newUploadDocsCount = manualFiles.filter(d => d.active).length;
  const isAllUploadSelected = selectedUploadDocs.length === newUploadDocsCount && newUploadDocsCount > 0;

  const handleToggleAllUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      setSelectedUploadDocs(manualFiles.filter(d => d.active).map(d => d.num));
    } else {
      setSelectedUploadDocs([]);
    }
  };

  const filteredUploadDocs = manualFiles.filter(doc => {
    if (uploadFilterTab === 'baru') return doc.kbsStatus === 'Baru';
    if (uploadFilterTab === 'ada') return doc.kbsStatus === 'Sudah Ada';
    if (uploadFilterTab === 'duplikat') return doc.kbsStatus === 'Duplikat';
    return true;
  });

  const uploadBaruCount = manualFiles.filter(d => d.kbsStatus === 'Baru').length;
  const uploadAdaCount = manualFiles.filter(d => d.kbsStatus === 'Sudah Ada').length;
  const uploadDuplikatCount = manualFiles.filter(d => d.kbsStatus === 'Duplikat').length;

  const handleFilesAdded = (files: File[]) => {
    const formatted: ManualFileItem[] = files.map((file, idx) => {
      const name = file.name;
      const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
      const sizeStr = file.size > 1024 * 1024 ? `${sizeMB} MB` : `${Math.max(1, Math.round(file.size / 1024))} KB`;
      
      let type = 'POJK';
      if (name.toUpperCase().includes('SEOJK')) type = 'SEOJK';
      else if (name.toUpperCase().includes('SEDK')) type = 'SEDK';
      else if (name.toUpperCase().includes('PDK')) type = 'PDK';
      else if (name.toUpperCase().includes('SK') || name.toUpperCase().includes('INTERNAL')) type = 'Internal';

      const yearMatch = name.match(/20\d{2}/);
      const year = yearMatch ? yearMatch[0] : '2026';

      const titleClean = name.replace(/\.[^/.]+$/, '').replace(/[_-]/g, ' ');

      return {
        id: `upload-${Date.now()}-${idx}-${Math.random().toString(36).substr(2, 4)}`,
        name: file.name,
        size: sizeStr,
        title: titleClean,
        num: `${type} No. ${Math.floor(Math.random() * 30 + 1)}/${type}.03/${year}`,
        type: type,
        year: year,
        regStatus: 'Aktif',
        kbsStatus: 'Baru',
        active: true
      };
    });

    setManualFiles(prev => {
      const updated = [...prev, ...formatted];
      setSelectedUploadDocs(updated.filter(d => d.active).map(d => d.num));
      return updated;
    });
  };

  const handleRemoveFile = (id: string) => {
    setManualFiles(prev => {
      const updated = prev.filter(f => f.id !== id);
      setSelectedUploadDocs(prevSel => prevSel.filter(num => updated.some(f => f.num === num)));
      return updated;
    });
  };

  const handleClearAllFiles = () => {
    setManualFiles([]);
    setSelectedUploadDocs([]);
  };

  const handleLoadSampleFiles = () => {
    setManualFiles(initialManualFiles);
    setSelectedUploadDocs(initialManualFiles.filter(d => d.active).map(d => d.num));
  };


  // Effects for Manual Upload
  useEffect(() => {
    if (!isUploadScanning) return;
    const interval = setInterval(() => {
      setUploadScanProgress(prev => {
        if (prev >= 100) {
          clearInterval(interval);
          setIsUploadScanning(false);
          setUploadStep(2);
          return 100;
        }
        return Math.min(100, prev + 20);
      });
    }, 500);
    return () => clearInterval(interval);
  }, [isUploadScanning]);

  useEffect(() => {
    if (uploadStep !== 3) return;
    const interval = setInterval(() => {
      setUploadProgress(prev => {
        if (prev >= 100) {
          clearInterval(interval);
          setTimeout(() => setUploadStep(4), 600);
          return 100;
        }
        return Math.min(100, prev + 20);
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [uploadStep]);

  return (
    <div className="space-y-6">
        <>
          {uploadStep === 1 && (
            <>
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="flex justify-between items-center mb-2">
                  <h3 className="text-lg font-bold text-gray-900">Upload Manual Dokumen Regulasi</h3>
                  <span className="inline-flex items-center bg-gray-100 text-gray-600 text-xs font-semibold px-2.5 py-1 rounded-full">
                    <span className="w-1.5 h-1.5 bg-red-700 rounded-full mr-1.5"></span>
                    Tahap 1: Unggah & Konfigurasi Berkas
                  </span>
                </div>
                <p className="text-gray-600 text-sm mb-6">
                  Unggah berkas regulasi (PDF atau Word) secara langsung melalui drag & drop atau pemilih berkas untuk dipindai dan dimasukkan ke Knowledge Base.
                </p>

                <div className="space-y-6">
                  {/* DRAG & DROP ZONE */}
                  <div>
                    <label className="block text-xs font-bold text-gray-900 mb-2 uppercase tracking-wider">
                      Area Unggah Berkas <span className="text-red-600">*</span>
                    </label>

                    <div
                      onDragOver={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setIsDragging(true);
                      }}
                      onDragEnter={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setIsDragging(true);
                      }}
                      onDragLeave={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setIsDragging(false);
                      }}
                      onDrop={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setIsDragging(false);
                        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                          handleFilesAdded(Array.from(e.dataTransfer.files));
                        }
                      }}
                      onClick={() => fileInputRef.current?.click()}
                      className={`border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer select-none ${
                        isDragging 
                          ? 'border-[#B91C1C] bg-[#FDF2F2] ring-4 ring-[#B91C1C]/10 scale-[1.005]' 
                          : 'border-gray-300 hover:border-[#B91C1C] hover:bg-gray-50/70 bg-white'
                      }`}
                    >
                      <input 
                        type="file" 
                        ref={fileInputRef} 
                        className="hidden" 
                        multiple 
                        accept=".pdf,.doc,.docx"
                        onChange={(e) => {
                          if (e.target.files && e.target.files.length > 0) {
                            handleFilesAdded(Array.from(e.target.files));
                          }
                        }}
                      />
                      <div className="w-14 h-14 mx-auto rounded-full bg-red-50 text-[#B91C1C] flex items-center justify-center mb-3 transition-transform duration-200">
                        <UploadCloud size={28} className={isDragging ? 'animate-bounce text-[#B91C1C]' : 'text-[#B91C1C]'} />
                      </div>
                      <div className="text-base font-bold text-gray-900 mb-1">
                        {isDragging ? 'Lepaskan berkas di sini untuk mengunggah' : 'Tarik & Lepaskan berkas regulasi ke sini'}
                      </div>
                      <p className="text-sm text-gray-500 mb-3">
                        atau <span className="text-[#B91C1C] font-semibold underline underline-offset-2">telusuri file</span> dari komputer Anda
                      </p>
                      <div className="inline-flex items-center gap-2 text-xs text-gray-400 bg-gray-50 px-3 py-1.5 rounded-full border border-gray-200">
                        <span>Format: PDF, DOC, DOCX</span>
                        <span>•</span>
                        <span>Maksimal 25MB per berkas</span>
                      </div>
                    </div>
                  </div>

                  {/* DAFTAR BERKAS TERPILIH */}
                  {manualFiles.length > 0 ? (
                    <div>
                      <div className="flex justify-between items-center mb-2.5">
                        <div className="flex items-center space-x-2">
                          <label className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                            Berkas Terpilih ({manualFiles.length})
                          </label>
                          <span className="text-xs text-gray-400">• Siap untuk dipindai & diverifikasi</span>
                        </div>
                        <div className="flex items-center space-x-3">
                          <button
                            type="button"
                            onClick={() => fileInputRef.current?.click()}
                            className="text-xs font-semibold text-[#B91C1C] hover:text-red-800 flex items-center transition-colors"
                          >
                            <Plus size={14} className="mr-1" /> Tambah Berkas
                          </button>
                          <span className="text-gray-300">|</span>
                          <button
                            type="button"
                            onClick={handleClearAllFiles}
                            className="text-xs font-medium text-gray-500 hover:text-red-600 transition-colors"
                          >
                            Hapus Semua
                          </button>
                        </div>
                      </div>

                      <div className="border border-gray-200 rounded-xl divide-y divide-gray-100 max-h-64 overflow-y-auto bg-gray-50/50">
                        {manualFiles.map((file) => (
                          <div key={file.id} className="p-3 bg-white flex items-center justify-between hover:bg-gray-50/80 transition-colors">
                            <div className="flex items-center space-x-3 min-w-0 pr-4">
                              <div className="w-9 h-9 rounded-lg bg-red-50 text-[#B91C1C] border border-red-100 flex items-center justify-center shrink-0">
                                <FileText size={18} />
                              </div>
                              <div className="min-w-0">
                                <div className="text-sm font-semibold text-gray-900 truncate" title={file.name}>
                                  {file.name}
                                </div>
                                <div className="flex items-center space-x-2 text-xs text-gray-500 mt-0.5">
                                  <span>{file.size}</span>
                                  <span>•</span>
                                  <span className="text-gray-600 font-medium">{file.num}</span>
                                </div>
                              </div>
                            </div>
                            <div className="flex items-center space-x-3 shrink-0">
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                                Siap Verifikasi
                              </span>
                              <button
                                type="button"
                                onClick={() => handleRemoveFile(file.id)}
                                className="text-gray-400 hover:text-red-600 p-1 rounded hover:bg-gray-100 transition-colors"
                                title="Hapus berkas"
                              >
                                <X size={16} />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="p-4 bg-gray-50 border border-dashed border-gray-200 rounded-xl flex flex-col sm:flex-row items-center justify-between gap-3 text-center sm:text-left">
                      <div className="text-xs text-gray-500">
                        Belum ada berkas yang dipilih. Anda dapat mengunggah file PDF/Word atau memuat contoh berkas simulasi.
                      </div>
                      <button
                        type="button"
                        onClick={handleLoadSampleFiles}
                        className="px-3.5 py-1.5 bg-white border border-gray-300 hover:border-gray-400 text-gray-700 text-xs font-semibold rounded-lg shadow-sm hover:bg-gray-50 transition-colors shrink-0"
                      >
                        Muat Contoh Berkas (5 File)
                      </button>
                    </div>
                  )}

                  {/* PARAMETER CONFIGURATION */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <label className="block text-xs font-bold text-gray-900 mb-2 uppercase tracking-wider">
                        Klasifikasi Akses <span className="text-red-600">*</span>
                      </label>
                      <select 
                        value={uploadAccessClassification}
                        onChange={(e) => setUploadAccessClassification(e.target.value)}
                        className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm text-gray-900 focus:ring-[#B91C1C] focus:border-[#B91C1C] bg-white font-medium"
                      >
                        <option value="Non-Publik">Non-Publik</option>
                        <option value="Publik">Publik</option>
                      </select>
                      <p className="text-xs text-gray-500 mt-1.5">Menentukan hak akses naskah setelah disimpan ke Knowledge Base.</p>
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-gray-900 mb-2 uppercase tracking-wider">
                        Kategori Target Knowledge Base <span className="text-red-600">*</span>
                      </label>
                      <select 
                        value={uploadTargetCategory}
                        onChange={(e) => setUploadTargetCategory(e.target.value)}
                        className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm text-gray-900 focus:ring-[#B91C1C] focus:border-[#B91C1C] bg-white font-medium"
                      >
                        <option value="Perbankan">Perbankan</option>
                        <option value="Pasar Modal">Pasar Modal</option>
                        <option value="Fintech">Fintech</option>
                        <option value="Asuransi">Asuransi</option>
                        <option value="Tata Kelola IT & AI">Tata Kelola IT & AI</option>
                        <option value="Lainnya">Lainnya</option>
                      </select>
                      <p className="text-xs text-gray-500 mt-1.5">Menentukan kategori dokumen pada repositori Knowledge Base.</p>
                    </div>
                  </div>

                  {/* KETERANGAN OPSIONAL */}
                  <div>
                    <label className="block text-xs font-bold text-gray-900 mb-2 uppercase tracking-wider">
                      Catatan / Keterangan Sumber (Opsional)
                    </label>
                    <input 
                      type="text"
                      value={uploadNotes}
                      onChange={(e) => setUploadNotes(e.target.value)}
                      placeholder="Contoh: Draft regulasi internal perbankan / Dokumen rapat koordinasi OJK"
                      className="block w-full px-3.5 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 focus:ring-[#B91C1C] focus:border-[#B91C1C] placeholder-gray-400"
                    />
                  </div>

                  {/* INFO BOX OTOMATIS */}
                  <div className="bg-[#F8F9FA] border border-gray-100 rounded-lg p-4 flex items-start">
                    <Info size={20} className="text-blue-600 mt-0.5 mr-3 shrink-0" />
                    <div>
                      <h4 className="text-sm font-semibold text-gray-900 mb-0.5">
                        Status regulasi dan pengecekan duplikasi akan dilakukan otomatis setelah pemindaian berkas.
                      </h4>
                      <p className="text-sm text-gray-600">
                        Sistem akan membaca teks berkas, mendeteksi status naskah (Aktif, Diubah, Dicabut), dan memverifikasi hash SHA-256 dokumen terhadap Knowledge Base.
                      </p>
                    </div>
                  </div>

                  {/* TOMBOL SCAN & VERIFIKASI */}
                  {!isUploadScanning && (
                    <div className="flex justify-end pt-2">
                      <button 
                        onClick={() => {
                          if (manualFiles.length === 0) return;
                          setIsUploadScanning(true);
                        }}
                        disabled={manualFiles.length === 0}
                        className={`font-semibold px-6 py-2.5 rounded-lg flex items-center transition-colors shadow-sm ${
                          manualFiles.length === 0 
                            ? 'bg-gray-300 text-gray-500 cursor-not-allowed' 
                            : 'bg-[#B91C1C] hover:bg-red-800 text-white cursor-pointer'
                        }`}
                      >
                        <Scan size={18} className="mr-2" />
                        Verifikasi & Scan Berkas ({manualFiles.length})
                      </button>
                    </div>
                  )}
                </div>

                {/* PROGRESS PEMINDAIAN BERKAS */}
                {isUploadScanning && (
                  <div className="mt-4 p-5 border border-red-100 bg-[#FDF2F2] rounded-xl animate-in fade-in slide-in-from-top-4 duration-500">
                    <div className="flex justify-between items-center mb-3">
                      <div className="flex items-center text-sm font-semibold text-[#B91C1C]">
                        <Loader2 size={18} className="mr-2.5 animate-spin text-[#B91C1C]" />
                        Memindai & Memverifikasi {manualFiles.length} Berkas Unggahan...
                      </div>
                      <span className="text-sm font-bold text-[#B91C1C]">{uploadScanProgress}%</span>
                    </div>
                    <div className="w-full bg-red-100 rounded-full h-2.5 mb-4">
                      <div className="bg-[#B91C1C] h-2.5 rounded-full transition-all duration-300 ease-out relative overflow-hidden" style={{ width: `${uploadScanProgress}%` }}>
                        <div className="absolute inset-0 bg-white/20 animate-[shimmer_1.5s_infinite]"></div>
                      </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-2.5 gap-x-4 text-sm">
                      <div className={`flex items-center ${uploadScanProgress >= 20 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                        {uploadScanProgress >= 20 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : <Loader2 size={16} className="mr-2 animate-spin text-[#B91C1C]" />}
                        Mengunggah berkas ke antrean pemrosesan
                      </div>
                      <div className={`flex items-center ${uploadScanProgress >= 40 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                        {uploadScanProgress >= 40 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : uploadScanProgress >= 20 ? <Loader2 size={16} className="mr-2 animate-spin text-[#B91C1C]" /> : <Clock size={16} className="mr-2 text-gray-300" />}
                        Mengekstrak teks & metadata regulasi (PDF Parser)
                      </div>
                      <div className={`flex items-center ${uploadScanProgress >= 60 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                        {uploadScanProgress >= 60 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : uploadScanProgress >= 40 ? <Loader2 size={16} className="mr-2 animate-spin text-[#B91C1C]" /> : <Clock size={16} className="mr-2 text-gray-300" />}
                        Memeriksa kecocokan nomor dan status regulasi
                      </div>
                      <div className={`flex items-center ${uploadScanProgress >= 80 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                        {uploadScanProgress >= 80 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : uploadScanProgress >= 60 ? <Loader2 size={16} className="mr-2 animate-spin text-[#B91C1C]" /> : <Clock size={16} className="mr-2 text-gray-300" />}
                        Memverifikasi duplikasi hash SHA-256 di KBS
                      </div>
                      <div className={`flex items-center ${uploadScanProgress >= 100 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                        {uploadScanProgress >= 100 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : uploadScanProgress >= 80 ? <Loader2 size={16} className="mr-2 animate-spin text-[#B91C1C]" /> : <Clock size={16} className="mr-2 text-gray-300" />}
                        Menyiapkan hasil verifikasi dokumen
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* RIWAYAT UPLOAD MANUAL TERAKHIR */}
              {!isUploadScanning && (
                <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-in fade-in slide-in-from-bottom-2 duration-500 mt-6">
                  <div className="flex justify-between items-center mb-6">
                    <div className="flex items-center space-x-3">
                      <h3 className="text-lg font-bold text-gray-900">Riwayat Upload Manual Terakhir</h3>
                      <span className="bg-gray-100 text-gray-600 text-xs font-medium px-2.5 py-1 rounded-full">3 unggahan terakhir</span>
                    </div>
                    <button className="text-sm font-semibold text-red-700 flex items-center hover:text-red-800">
                      Buka Seluruh Riwayat <ArrowRight size={16} className="ml-1" />
                    </button>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-gray-100">
                          <th className="py-3 px-4 text-xs font-bold text-gray-500 uppercase tracking-wider">Sumber / Berkas</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-500 uppercase tracking-wider">Waktu</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-500 uppercase tracking-wider">Jumlah Dokumen</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-500 uppercase tracking-wider">Dokumen Baru</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-500 uppercase tracking-wider text-right">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {mockManualUploadHistory.map((item, idx) => (
                          <tr key={idx} className="hover:bg-gray-50/50 transition-colors">
                            <td className="py-4 px-4">
                              <div className="flex items-center text-sm font-medium text-gray-900">
                                <FileText size={15} className="text-red-600 mr-2 shrink-0" />
                                <span className="font-semibold text-gray-900">{item.name}</span>
                              </div>
                              <div className="text-xs text-gray-400 mt-0.5 ml-6">Ukuran: {item.size}</div>
                            </td>
                            <td className="py-4 px-4 text-sm text-gray-600">{item.time}</td>
                            <td className="py-4 px-4 text-sm text-gray-900 font-medium">{item.filesCount}</td>
                            <td className="py-4 px-4 text-sm font-semibold text-green-700">{item.newDocs}</td>
                            <td className="py-4 px-4 text-right">
                              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-green-50 text-green-700 border border-green-200">
                                <span className="w-1.5 h-1.5 bg-green-500 rounded-full mr-1.5"></span>{item.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}

          {uploadStep === 2 && (
            <div className="animate-in fade-in duration-300">
              {/* TOP HEADER */}
              <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6 flex flex-col md:flex-row md:items-center justify-between shadow-sm">
                <div className="flex items-center space-x-4">
                  <span className="text-sm text-gray-500">Sumber Dokumen:</span>
                  <div className="flex items-center text-sm text-gray-700 bg-gray-50 border border-gray-200 rounded-md px-3 py-1.5 font-medium">
                    <UploadCloud size={15} className="mr-2 text-red-700" />
                    Upload Manual ({manualFiles.length} Berkas Unggahan)
                  </div>
                </div>
                <div className="flex items-center space-x-4 mt-4 md:mt-0">
                  <div className="text-sm font-bold text-gray-900">Ditemukan {manualFiles.length} dokumen</div>
                  <div className="flex space-x-2">
                    <span className="flex items-center text-sm font-medium text-green-700 bg-green-50 border border-green-200 px-3 py-1 rounded-full">
                      <span className="w-1.5 h-1.5 rounded-full bg-green-500 mr-2"></span>
                      {uploadBaruCount} Baru
                    </span>
                    <span className="flex items-center text-sm font-medium text-gray-600 bg-gray-100 border border-gray-200 px-3 py-1 rounded-full">
                      <span className="w-1.5 h-1.5 rounded-full bg-gray-400 mr-2"></span>
                      {uploadAdaCount} Sudah Ada
                    </span>
                    <span className="flex items-center text-sm font-medium text-yellow-700 bg-yellow-50 border border-yellow-200 px-3 py-1 rounded-full">
                      <span className="w-1.5 h-1.5 rounded-full bg-yellow-500 mr-2"></span>
                      {uploadDuplikatCount} Duplikat
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
                      onClick={() => setUploadFilterTab('all')}
                      className={`text-sm pb-4 border-b-2 transition-colors ${uploadFilterTab === 'all' ? 'font-bold text-[#B91C1C] border-[#B91C1C]' : 'font-medium text-gray-500 border-transparent hover:text-gray-700'}`}
                    >
                      Semua ({manualFiles.length})
                    </button>
                    <button 
                      onClick={() => setUploadFilterTab('baru')}
                      className={`text-sm pb-4 border-b-2 transition-colors ${uploadFilterTab === 'baru' ? 'font-bold text-[#B91C1C] border-[#B91C1C]' : 'font-medium text-gray-500 border-transparent hover:text-gray-700'}`}
                    >
                      Baru ({uploadBaruCount})
                    </button>
                    <button 
                      onClick={() => setUploadFilterTab('ada')}
                      className={`text-sm pb-4 border-b-2 transition-colors ${uploadFilterTab === 'ada' ? 'font-bold text-[#B91C1C] border-[#B91C1C]' : 'font-medium text-gray-500 border-transparent hover:text-gray-700'}`}
                    >
                      Sudah Ada ({uploadAdaCount})
                    </button>
                    <button 
                      onClick={() => setUploadFilterTab('duplikat')}
                      className={`text-sm pb-4 border-b-2 transition-colors ${uploadFilterTab === 'duplikat' ? 'font-bold text-[#B91C1C] border-[#B91C1C]' : 'font-medium text-gray-500 border-transparent hover:text-gray-700'}`}
                    >
                      Duplikat ({uploadDuplikatCount})
                    </button>
                  </div>
                  <div className="flex items-center space-x-4 pb-4 md:pb-0 md:-mt-4">
                    <label className="flex items-center text-sm text-gray-700 font-medium cursor-pointer">
                      <input 
                        type="checkbox" 
                        checked={isAllUploadSelected}
                        onChange={handleToggleAllUpload}
                        className="w-4 h-4 rounded border-gray-300 accent-[#B91C1C] mr-2" 
                      />
                      Pilih semua dokumen baru
                    </label>
                    <div className="h-4 w-px bg-gray-300"></div>
                    <div className="text-sm font-bold text-gray-900">{selectedUploadDocs.length} dokumen dipilih</div>
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
                      {filteredUploadDocs.map((doc, idx) => (
                        <tr key={idx} className={doc.active ? 'bg-white' : 'bg-gray-50/50'}>
                          <td className="py-4 px-6 text-center">
                            <input 
                              type="checkbox" 
                              checked={selectedUploadDocs.includes(doc.num)}
                              onChange={() => handleToggleUploadDoc(doc.num)}
                              disabled={!doc.active}
                              className={`w-4 h-4 rounded border-gray-300 accent-[#B91C1C] ${!doc.active ? 'opacity-40' : 'cursor-pointer'}`} 
                            />
                          </td>
                          <td className="py-4 px-6">
                            <div className={`text-sm font-bold ${doc.active ? 'text-gray-800' : 'text-gray-400'}`}>{doc.title}</div>
                            <div className={`text-xs mt-1 ${doc.active ? 'text-gray-500' : 'text-gray-400'}`}>
                              <span className="font-mono text-gray-400 mr-1.5">{doc.name}</span> • {doc.num}
                            </div>
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
                  onClick={() => setUploadStep(1)}
                  className="flex items-center text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
                >
                  <ArrowLeft size={16} className="mr-2" /> Kembali ke Unggah Berkas
                </button>
                <button 
                  onClick={() => setUploadStep(3)}
                  disabled={selectedUploadDocs.length === 0}
                  className={`${selectedUploadDocs.length === 0 ? 'bg-gray-300 cursor-not-allowed text-gray-500' : 'bg-[#B91C1C] hover:bg-[#a01818] text-white'} font-medium px-6 py-2.5 rounded-md flex items-center transition-colors shadow-sm`}
                >
                  <Download size={18} className="mr-2" />
                  Ingest Dokumen Terpilih ({selectedUploadDocs.length})
                  <ArrowRight size={18} className="ml-2" />
                </button>
              </div>
            </div>
          )}

          {uploadStep === 3 && (
            <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className="text-sm font-medium text-gray-500 mb-4 flex items-center space-x-2">
                <span>Dashboard</span> <span className="text-gray-400">&gt;</span> <span>Ingest Dokumen</span> <span className="text-gray-400">&gt;</span> <span>Upload Manual</span> <span className="text-gray-400">&gt;</span> <span className="text-gray-900 font-bold">Proses Ingest Dokumen</span>
              </div>
              <div className="mb-6">
                <h3 className="text-2xl font-bold text-gray-900 tracking-tight">Proses Ingest Dokumen</h3>
                <p className="text-gray-600 mt-1 text-sm">Memproses dan menambahkan dokumen berkas manual ke Knowledge Base.</p>
              </div>

              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8 mb-6">
                <div className="flex flex-col lg:flex-row justify-between mb-8 pb-8 border-b border-gray-100 gap-6">
                  <div className="flex items-center space-x-12">
                    <div>
                      <div className="flex items-center space-x-3 mb-4">
                        <span className="text-gray-600 text-sm">Sumber Dokumen:</span>
                        <div className="flex items-center font-medium text-gray-900 text-sm">
                          <UploadCloud size={16} className="mr-2 text-red-700" />
                          Upload Manual ({selectedUploadDocs.length} Berkas Dipilih)
                        </div>
                      </div>
                      <div className="flex items-center space-x-8 text-gray-600 text-sm">
                        <div className="flex items-center space-x-2">
                          <span>Target:</span> <span className="text-gray-900">Knowledge Base HERO (Sektor {uploadTargetCategory})</span>
                        </div>
                        <div className="text-gray-900">{selectedUploadDocs.length} Dokumen Dipilih</div>
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
                      <div className="text-xl font-bold text-gray-700">{uploadProgress}%</div>
                      <div className="text-xs font-bold text-gray-500 uppercase tracking-wider">
                        {Math.min(selectedUploadDocs.length, Math.floor(uploadProgress / (100 / Math.max(1, selectedUploadDocs.length))))} DARI {selectedUploadDocs.length} DOKUMEN SELESAI
                      </div>
                    </div>
                  </div>
                  
                  <div className="w-full bg-gray-100 h-2 rounded-full overflow-hidden mb-8">
                    <div className="h-full bg-[#B91C1C] transition-all duration-500 ease-out" style={{ width: `${uploadProgress}%` }}></div>
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
                        {manualFiles.filter(d => selectedUploadDocs.includes(d.num)).map((doc, idx, arr) => {
                          const docThreshold = Math.round(((idx + 1) / Math.max(1, arr.length)) * 100);
                          const prevThreshold = Math.round((idx / Math.max(1, arr.length)) * 100);
                          const isDone = uploadProgress >= docThreshold;
                          const isProcessing = uploadProgress > prevThreshold && uploadProgress < docThreshold;

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

          {uploadStep === 4 && (
            <div className="animate-in fade-in duration-300">
              <div className="text-sm font-medium text-gray-500 mb-4 flex items-center space-x-2">
                <span>Dashboard</span> <span className="text-gray-400">&gt;</span> <span>Ingest Dokumen</span> <span className="text-gray-400">&gt;</span> <span>Upload Manual</span> <span className="text-gray-400">&gt;</span> <span className="text-gray-900 font-bold">Dokumen Berhasil Ditambahkan</span>
              </div>
              <div className="mb-6">
                <h3 className="text-2xl font-bold text-gray-900 tracking-tight">Dokumen Berhasil Ditambahkan</h3>
                <p className="text-gray-600 mt-1 text-sm">{selectedUploadDocs.length} dokumen berhasil ditambahkan ke Knowledge Base.</p>
              </div>

              <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
                <div className="flex items-start">
                  <div className="bg-green-100 rounded-full p-1 mr-3 shrink-0">
                    <CheckCircle2 size={20} className="text-green-600" />
                  </div>
                  <div>
                    <div className="font-bold text-green-800 text-sm mb-0.5">Proses Ingest Selesai</div>
                    <div className="text-sm text-green-700">
                      Seluruh dokumen hasil upload manual telah berhasil diverifikasi dan disimpan ke repositori Knowledge Base HERO. Dokumen kini siap untuk dianalisis atau diharmonisasi.
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8 mb-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8 border-b border-gray-100 pb-8">
                  <div>
                    <div className="text-sm text-gray-500 mb-2">Sumber Dokumen</div>
                    <div className="flex items-center text-sm font-bold text-gray-900">
                      <UploadCloud size={16} className="mr-2 text-red-700" />
                      Upload Manual ({selectedUploadDocs.length} Berkas)
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-500 mb-2">Target Knowledge Base</div>
                    <div className="text-sm font-bold text-gray-900">
                      HERO (Sektor {uploadTargetCategory})
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-500 mb-2">Status Pemrosesan</div>
                    <div className="flex items-center text-sm font-bold text-green-700">
                      <div className="w-2 h-2 bg-green-500 rounded-full mr-2"></div>
                      {selectedUploadDocs.length} Dokumen Tersimpan
                    </div>
                  </div>
                </div>

                <div className="flex justify-between items-end mb-4">
                  <div className="text-sm font-bold text-gray-500 uppercase tracking-wider">DAFTAR DOKUMEN YANG DITAMBAHKAN</div>
                  <div className="text-sm text-gray-500">{selectedUploadDocs.length} dari {selectedUploadDocs.length} berhasil diproses</div>
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
                      {manualFiles.filter(d => selectedUploadDocs.includes(d.num)).map((doc, idx) => (
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
                  onClick={() => {
                    setUploadStep(1);
                    setUploadProgress(0);
                  }}
                  className="w-full sm:w-auto px-6 py-2.5 border border-gray-300 text-gray-700 font-medium rounded-md hover:bg-gray-50 transition-colors flex items-center justify-center bg-white"
                >
                  <ArrowLeft size={16} className="mr-2" /> Unggah Dokumen Baru
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
        </>
    </div>
  );
}
