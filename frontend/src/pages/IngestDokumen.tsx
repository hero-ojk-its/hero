import React, { useState, useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { 
  ArrowLeft, 
  Globe, 
  RefreshCw, 
  Link as LinkIcon, 
  CheckCircle2, 
  Info, 
  Scan, 
  ArrowRight,
  ExternalLink,
  Download,
  CheckCircle,
  Clock,
  Loader2,
  FolderOpen,
  Folder,
  Cloud,
  X,
  Check,
  UploadCloud,
  FileText,
  Plus
} from 'lucide-react';

const availableFolders = [
  { 
    name: 'peraturan_internal', 
    path: '/app/sources/peraturan_internal', 
    description: 'Regulasi internal perbankan & panduan OJK',
    fileCount: 12 
  },
  { 
    name: 'fintech_2026', 
    path: '/app/sources/fintech_2026', 
    description: 'Regulasi fintech P2P & inovasi digital',
    fileCount: 8 
  },
  { 
    name: 'it_governance', 
    path: '/app/sources/it_governance', 
    description: 'Tata kelola TI & ketahanan siber',
    fileCount: 6 
  }
];

const mockScrapedDocs = [
  { title: 'POJK tentang Ketahanan dan Keamanan Siber Bank Umum', num: 'POJK No. 11/POJK.03/2024', type: 'POJK', year: '2024', regStatus: 'Aktif', kbsStatus: 'Baru', active: true },
  { title: 'SEOJK tentang Format Pelaporan Ketahanan Siber', num: 'SEOJK No. 14/SEOJK.03/2024', type: 'SEOJK', year: '2024', regStatus: 'Aktif', kbsStatus: 'Baru', active: true },
  { title: 'SEOJK tentang Mitigasi Risiko Penyelenggaraan Fintech P2P', num: 'SEOJK No. 29/SEOJK.05/2023', type: 'SEOJK', year: '2023', regStatus: 'Diubah', kbsStatus: 'Baru', active: true },
  { title: 'POJK tentang Manajemen Risiko Teknologi Informasi', num: 'POJK No. 05/POJK.03/2023', type: 'POJK', year: '2023', regStatus: 'Aktif', kbsStatus: 'Baru', active: true },
  { title: 'PDK tentang Perlindungan Konsumen Sektor Jasa Keuangan', num: 'PDK No. 08/PDK.07/2022', type: 'PDK', year: '2022', regStatus: 'Aktif', kbsStatus: 'Baru', active: true },
  { title: 'POJK tentang Tata Kelola Teknologi Informasi', num: 'POJK No. 11/POJK.03/2022', type: 'POJK', year: '2023', regStatus: 'Aktif', kbsStatus: 'Sudah Ada', active: false },
  { title: 'POJK tentang Inovasi Keuangan Digital (Fintech Sandbox)', num: 'POJK No. 13/POJK.02/2018', type: 'POJK', year: '2018', regStatus: 'Aktif', kbsStatus: 'Sudah Ada', active: false },
  { title: 'SEOJK tentang Penyelenggaraan Layanan Perbankan Digital', num: 'SEOJK No. 21/SEOJK.03/2021', type: 'SEOJK', year: '2021', regStatus: 'Aktif', kbsStatus: 'Sudah Ada', active: false },
  { title: 'POJK tentang Penerapan Manajemen Risiko Terintegrasi bagi Konglomerasi Keuangan', num: 'POJK No. 45/POJK.03/2020', type: 'POJK', year: '2020', regStatus: 'Aktif', kbsStatus: 'Sudah Ada', active: false },
  { title: 'SEOJK tentang Standar Penerapan Tata Kelola TI Bank Umum', num: 'SEOJK No. 35/SEOJK.03/2017', type: 'SEOJK', year: '2017', regStatus: 'Diubah', kbsStatus: 'Sudah Ada', active: false },
  { title: 'POJK tentang Tata Cara Pemeriksaan Sektor Perbankan', num: 'POJK No. 03/POJK.03/2019', type: 'POJK', year: '2019', regStatus: 'Aktif', kbsStatus: 'Sudah Ada', active: false },
  { title: 'SEDK tentang Ketentuan Teknis Keamanan Informasi', num: 'SEDK No. 04/SEDK.03/2020', type: 'SEDK', year: '2020', regStatus: 'Dicabut', kbsStatus: 'Duplikat', active: false }
];

interface ManualFileItem {
  id: string;
  name: string;
  size: string;
  title: string;
  num: string;
  type: string;
  year: string;
  regStatus: 'Aktif' | 'Diubah' | 'Dicabut';
  kbsStatus: 'Baru' | 'Sudah Ada' | 'Duplikat';
  active: boolean;
}

const initialManualFiles: ManualFileItem[] = [
  {
    id: 'doc-m-1',
    name: 'POJK_No_12_POJK03_2024_Ketahanan_Siber.pdf',
    size: '2.8 MB',
    title: 'POJK tentang Ketahanan dan Keamanan Siber Bank Umum',
    num: 'POJK No. 12/POJK.03/2024',
    type: 'POJK',
    year: '2024',
    regStatus: 'Aktif',
    kbsStatus: 'Baru',
    active: true
  },
  {
    id: 'doc-m-2',
    name: 'SEOJK_No_15_SEOJK03_2024_Format_Pelaporan.pdf',
    size: '1.6 MB',
    title: 'SEOJK tentang Pedoman Tata Kelola dan Audit Siber',
    num: 'SEOJK No. 15/SEOJK.03/2024',
    type: 'SEOJK',
    year: '2024',
    regStatus: 'Aktif',
    kbsStatus: 'Baru',
    active: true
  },
  {
    id: 'doc-m-3',
    name: 'SEOJK_No_30_SEOJK05_2023_Mitigasi_Fintech.pdf',
    size: '3.1 MB',
    title: 'SEOJK tentang Mitigasi Risiko Penyelenggaraan Fintech P2P',
    num: 'SEOJK No. 30/SEOJK.05/2023',
    type: 'SEOJK',
    year: '2023',
    regStatus: 'Diubah',
    kbsStatus: 'Baru',
    active: true
  },
  {
    id: 'doc-m-4',
    name: 'POJK_No_11_POJK03_2022_Tata_Kelola_TI.pdf',
    size: '2.4 MB',
    title: 'POJK tentang Tata Kelola Teknologi Informasi',
    num: 'POJK No. 11/POJK.03/2022',
    type: 'POJK',
    year: '2022',
    regStatus: 'Aktif',
    kbsStatus: 'Sudah Ada',
    active: false
  },
  {
    id: 'doc-m-5',
    name: 'SEDK_No_04_SEDK03_2020_Keamanan_Info.pdf',
    size: '980 KB',
    title: 'SEDK tentang Ketentuan Teknis Keamanan Informasi',
    num: 'SEDK No. 04/SEDK.03/2020',
    type: 'SEDK',
    year: '2020',
    regStatus: 'Dicabut',
    kbsStatus: 'Duplikat',
    active: false
  }
];

const mockManualUploadHistory = [
  {
    name: 'POJK_No_12_POJK03_2024_Ketahanan_Siber.pdf',
    time: 'Hari ini, 15:20 WIB',
    size: '2.8 MB',
    filesCount: '1 dokumen',
    newDocs: '1 baru',
    status: 'Berhasil'
  },
  {
    name: 'Paket_Regulasi_Fintech_Q3_2025.zip (3 PDF)',
    time: 'Kemarin, 11:45 WIB',
    size: '7.5 MB',
    filesCount: '3 dokumen',
    newDocs: '2 baru',
    status: 'Berhasil'
  },
  {
    name: 'SE_Direksi_Tata_Kelola_Internal_2023.pdf',
    time: '28 Sep 2026, 09:15 WIB',
    size: '1.4 MB',
    filesCount: '1 dokumen',
    newDocs: '0 baru (sudah ada)',
    status: 'Berhasil'
  }
];

export default function IngestDokumen() {
  const [searchParams] = useSearchParams();
  const tabParam = searchParams.get('tab');
  const [activeTab, setActiveTab] = useState<'scraping' | 'sync' | 'upload'>(
    tabParam === 'upload' ? 'upload' : tabParam === 'sync' ? 'sync' : 'scraping'
  );
  
  // States for Scraping tab
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [downloadProgress, setDownloadProgress] = useState(0);
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const [fileNameFormat, setFileNameFormat] = useState<string[]>([]);
  
  const [selectedDocs, setSelectedDocs] = useState<string[]>(
    mockScrapedDocs.filter(d => d.active).map(d => d.num)
  );

  const handleToggleDoc = (num: string) => {
    setSelectedDocs(prev => 
      prev.includes(num) ? prev.filter(n => n !== num) : [...prev, num]
    );
  };

  const handleToggleAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      setSelectedDocs(mockScrapedDocs.filter(d => d.active).map(d => d.num));
    } else {
      setSelectedDocs([]);
    }
  };

  const newDocsCount = mockScrapedDocs.filter(d => d.active).length;
  const isAllSelected = selectedDocs.length === newDocsCount && newDocsCount > 0;
  const [scrapeFilterTab, setScrapeFilterTab] = useState<'all' | 'baru' | 'ada' | 'duplikat'>('all');

  const filteredScrapedDocs = mockScrapedDocs.filter(doc => {
    if (scrapeFilterTab === 'baru') return doc.kbsStatus === 'Baru';
    if (scrapeFilterTab === 'ada') return doc.kbsStatus === 'Sudah Ada';
    if (scrapeFilterTab === 'duplikat') return doc.kbsStatus === 'Duplikat';
    return true;
  });

  // States for Sync tab
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

  const isAllSyncSelected = selectedSyncDocs.length === newDocsCount && newDocsCount > 0;

  const filteredSyncDocs = mockScrapedDocs.filter(doc => {
    if (syncFilterTab === 'baru') return doc.kbsStatus === 'Baru';
    if (syncFilterTab === 'ada') return doc.kbsStatus === 'Sudah Ada';
    if (syncFilterTab === 'duplikat') return doc.kbsStatus === 'Duplikat';
    return true;
  });

  useEffect(() => {
    if (oneDriveNotice) {
      const timer = setTimeout(() => setOneDriveNotice(false), 4000);
      return () => clearTimeout(timer);
    }
  }, [oneDriveNotice]);

  const handleAddFormat = (type: string) => {
    setFileNameFormat(prev => [...prev, type]);
  };

  const handleClearFormat = () => {
    setFileNameFormat([]);
  };

  // Effects for Scraping URL
  useEffect(() => {
    if (isScanning) {
      const interval = setInterval(() => {
        setScanProgress(prev => {
          if (prev >= 100) {
            clearInterval(interval);
            setIsScanning(false);
            setStep(2);
            return 100;
          }
          return Math.min(100, prev + Math.floor(Math.random() * 15) + 10); 
        });
      }, 500);
      return () => clearInterval(interval);
    } else {
      setScanProgress(0);
    }
  }, [isScanning]);

  useEffect(() => {
    if (step === 3) {
      const interval = setInterval(() => {
        setDownloadProgress(prev => {
          if (prev >= 100) {
            clearInterval(interval);
            setTimeout(() => setStep(4), 600);
            return 100;
          }
          return Math.min(100, prev + 20);
        });
      }, 1000);
      return () => clearInterval(interval);
    } else {
      setDownloadProgress(0);
    }
  }, [step]);

  // Effects for Sync
  useEffect(() => {
    if (isSyncScanning) {
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
    } else {
      setSyncScanProgress(0);
    }
  }, [isSyncScanning]);

  useEffect(() => {
    if (syncStep === 3) {
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
    } else {
      setSyncProgress(0);
    }
  }, [syncStep]);

  // States for Manual Upload tab
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
    if (isUploadScanning) {
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
    } else {
      setUploadScanProgress(0);
    }
  }, [isUploadScanning]);

  useEffect(() => {
    if (uploadStep === 3) {
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
    } else {
      setUploadProgress(0);
    }
  }, [uploadStep]);

  return (
    <div className="space-y-6 pb-12">
      {/* Breadcrumb and Header */}
      <div className="flex justify-between items-start">
        <div>
          <div className="text-sm text-gray-500 mb-2">
            Dashboard <span className="mx-1">/</span> Ingest Dokumen <span className="mx-1">/</span>{' '}
            <span className="text-gray-900 font-medium">
              {activeTab === 'scraping' ? 'Scraping URL' : activeTab === 'sync' ? 'Sinkronisasi' : 'Upload Manual'}
            </span>
          </div>
          <h2 className="text-2xl font-bold text-gray-900 mb-1">Ingest Dokumen</h2>
          <p className="text-gray-600">Ambil dokumen regulasi dari sumber URL, sinkronisasi folder, atau unggah berkas secara manual, lalu tambahkan ke Knowledge Base.</p>
        </div>
        <Link to="/knowledge" className="flex items-center text-sm font-medium text-gray-600 hover:text-gray-900">
          <ArrowLeft size={16} className="mr-1" />
          Kembali ke Knowledge Base
        </Link>
      </div>

      {/* Tabs */}
      <div className="flex space-x-6 border-b border-gray-200">
        <button 
          onClick={() => setActiveTab('scraping')}
          className={`flex items-center pb-3 border-b-2 transition-colors ${activeTab === 'scraping' ? 'border-red-700 text-red-700 font-semibold' : 'border-transparent text-gray-500 hover:text-gray-700 font-medium'}`}
        >
          <Globe size={18} className="mr-2" />
          Scraping URL
        </button>
        <button 
          onClick={() => setActiveTab('sync')}
          className={`flex items-center pb-3 border-b-2 transition-colors ${activeTab === 'sync' ? 'border-red-700 text-red-700 font-semibold' : 'border-transparent text-gray-500 hover:text-gray-700 font-medium'}`}
        >
          <RefreshCw size={18} className="mr-2" />
          Sinkronisasi OneDrive / Folder Lokal
        </button>
        <button 
          onClick={() => setActiveTab('upload')}
          className={`flex items-center pb-3 border-b-2 transition-colors ${activeTab === 'upload' ? 'border-red-700 text-red-700 font-semibold' : 'border-transparent text-gray-500 hover:text-gray-700 font-medium'}`}
        >
          <UploadCloud size={18} className="mr-2" />
          Upload Manual
        </button>
      </div>

      {/* ======================================================== */}
      {/* TAB SCRAPING URL */}
      {/* ======================================================== */}
      {activeTab === 'scraping' && (
        <>
          {step === 1 && (
            <>
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="flex justify-between items-center mb-2">
                  <h3 className="text-lg font-bold text-gray-900">Parameter Scraping URL</h3>
                  <span className="inline-flex items-center bg-gray-100 text-gray-600 text-xs font-semibold px-2.5 py-1 rounded-full">
                    <span className="w-1.5 h-1.5 bg-red-700 rounded-full mr-1.5"></span>
                    Tahap 1: Konfigurasi Sumber
                  </span>
                </div>
                <p className="text-gray-600 text-sm mb-6">Masukkan URL sumber regulasi untuk memindai dokumen PDF yang tersedia.</p>

                <div className="space-y-6">
                  <div>
                    <div className="flex justify-between mb-1.5">
                      <label className="block text-sm font-medium text-gray-900">URL Sumber <span className="text-red-600">*</span></label>
                      <span className="text-xs text-gray-500">Protokol HTTPS JDIH / Portal Resmi</span>
                    </div>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <LinkIcon size={16} className="text-gray-400" />
                      </div>
                      <input 
                        type="text"
                        className="block w-full pl-10 pr-10 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-red-500 focus:border-red-500"
                        defaultValue="https://jdih.ojk.go.id/peraturan/sektor-perbankan"
                      />
                      <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                        <CheckCircle2 size={16} className="text-gray-400" />
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-6">
                    <div>
                      <label className="block text-sm font-medium text-gray-900 mb-1.5">Kedalaman Scraping</label>
                      <select className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm focus:ring-red-500 focus:border-red-500 bg-white">
                        <option>2 Level (Rekomendasi)</option>
                        <option>1 Level (Halaman Ini Saja)</option>
                        <option>3 Level (Dalam)</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-900 mb-1.5">Kategori Target Knowledge Base</label>
                      <select className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm focus:ring-red-500 focus:border-red-500 bg-white">
                        <option>Perbankan</option>
                        <option>Pasar Modal</option>
                        <option>IKNB</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-900 mb-1.5">Format Nama Berkas</label>
                    <div className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm bg-gray-50 text-gray-700 min-h-[42px] mb-3 flex items-center">
                      {fileNameFormat.length > 0 ? (
                        <span className="font-semibold">{fileNameFormat.join(' - ')}</span>
                      ) : (
                        <span className="text-gray-400">Pilih format nama berkas di bawah...</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <button type="button" onClick={() => handleAddFormat('Nama')} className="px-3 py-1.5 bg-white border border-gray-200 text-gray-700 text-sm font-medium rounded hover:bg-gray-50 transition-colors shadow-sm">Nama</button>
                      <button type="button" onClick={() => handleAddFormat('Tahun')} className="px-3 py-1.5 bg-white border border-gray-200 text-gray-700 text-sm font-medium rounded hover:bg-gray-50 transition-colors shadow-sm">Tahun</button>
                      <button type="button" onClick={() => handleAddFormat('Jenis')} className="px-3 py-1.5 bg-white border border-gray-200 text-gray-700 text-sm font-medium rounded hover:bg-gray-50 transition-colors shadow-sm">Jenis</button>
                      <button type="button" onClick={() => handleAddFormat('Bidang')} className="px-3 py-1.5 bg-white border border-gray-200 text-gray-700 text-sm font-medium rounded hover:bg-gray-50 transition-colors shadow-sm">Bidang</button>
                      <button type="button" onClick={handleClearFormat} className="px-3 py-1.5 text-red-600 text-sm font-medium hover:text-red-700 transition-colors ml-auto">Clear</button>
                    </div>
                  </div>

                  <div className="bg-[#F8F9FA] border border-gray-100 rounded-lg p-4 flex items-start">
                    <Info size={20} className="text-blue-600 mt-0.5 mr-3 shrink-0" />
                    <div>
                      <h4 className="text-sm font-semibold text-gray-900 mb-0.5">Status regulasi dan pengecekan duplikasi akan dilakukan otomatis setelah pemindaian.</h4>
                      <p className="text-sm text-gray-600">Sistem akan mendeteksi status naskah (Aktif, Diubah, Dicabut) serta memverifikasi duplikasi hash dokumen sebelum masuk ke antrean unduh.</p>
                    </div>
                  </div>

                  {!isScanning && (
                    <div className="flex justify-end pt-2">
                      <button 
                        onClick={() => setIsScanning(true)}
                        className="bg-[#B91C1C] hover:bg-red-800 text-white font-medium px-5 py-2.5 rounded-lg flex items-center transition-colors"
                      >
                        <Scan size={18} className="mr-2" />
                        Scan Dokumen
                      </button>
                    </div>
                  )}
                </div>

                {isScanning && (
                  <div className="mt-4 p-5 border border-blue-100 bg-blue-50/50 rounded-xl animate-in fade-in slide-in-from-top-4 duration-500">
                    <div className="flex justify-between items-center mb-3">
                      <div className="flex items-center text-sm font-semibold text-blue-800">
                        <Loader2 size={18} className="mr-2.5 animate-spin text-blue-600" />
                        Memindai Tautan (Kedalaman 2 Level)...
                      </div>
                      <span className="text-sm font-bold text-blue-600">{scanProgress}%</span>
                    </div>
                    <div className="w-full bg-blue-200/50 rounded-full h-2.5 mb-4">
                      <div className="bg-blue-600 h-2.5 rounded-full transition-all duration-300 ease-out relative overflow-hidden" style={{ width: `${scanProgress}%` }}>
                        <div className="absolute inset-0 bg-white/20 animate-[shimmer_1.5s_infinite]"></div>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-y-2.5 gap-x-4 text-sm">
                      <div className={`flex items-center ${scanProgress >= 20 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                        {scanProgress >= 20 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : <Loader2 size={16} className="mr-2 animate-spin text-blue-500" />}
                        Mengakses URL JDIH OJK
                      </div>
                      <div className={`flex items-center ${scanProgress >= 40 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                        {scanProgress >= 40 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : scanProgress >= 20 ? <Loader2 size={16} className="mr-2 animate-spin text-blue-500" /> : <Clock size={16} className="mr-2 text-gray-300" />}
                        Memindai halaman (Kedalaman 2 Level)
                      </div>
                      <div className={`flex items-center ${scanProgress >= 60 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                        {scanProgress >= 60 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : scanProgress >= 40 ? <Loader2 size={16} className="mr-2 animate-spin text-blue-500" /> : <Clock size={16} className="mr-2 text-gray-300" />}
                        Memeriksa metadata dokumen
                      </div>
                      <div className={`flex items-center ${scanProgress >= 80 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                        {scanProgress >= 80 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : scanProgress >= 60 ? <Loader2 size={16} className="mr-2 animate-spin text-blue-500" /> : <Clock size={16} className="mr-2 text-gray-300" />}
                        Memeriksa dokumen yang sudah ada
                      </div>
                      <div className={`flex items-center ${scanProgress >= 100 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                        {scanProgress >= 100 ? <CheckCircle size={16} className="mr-2 text-green-500" /> : scanProgress >= 80 ? <Loader2 size={16} className="mr-2 animate-spin text-blue-500" /> : <Clock size={16} className="mr-2 text-gray-300" />}
                        Memverifikasi duplikasi
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {!isScanning && (
                <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
                  <div className="flex justify-between items-center mb-6">
                    <div className="flex items-center space-x-3">
                      <h3 className="text-lg font-bold text-gray-900">Riwayat Scraping Terakhir</h3>
                      <span className="bg-gray-100 text-gray-600 text-xs font-medium px-2.5 py-1 rounded-full">3 pemindaian terakhir</span>
                    </div>
                    <button className="text-sm font-semibold text-red-700 flex items-center hover:text-red-800">
                      Buka Seluruh Riwayat <ArrowRight size={16} className="ml-1" />
                    </button>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-gray-100">
                          <th className="py-3 px-4 text-xs font-bold text-gray-500 uppercase tracking-wider">Sumber URL</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-500 uppercase tracking-wider">Waktu</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-500 uppercase tracking-wider">Dokumen Ditemukan</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-500 uppercase tracking-wider">Dokumen Baru</th>
                          <th className="py-3 px-4 text-xs font-bold text-gray-500 uppercase tracking-wider text-right">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        <tr className="hover:bg-gray-50/50 transition-colors">
                          <td className="py-4 px-4">
                            <div className="flex items-center text-sm font-medium text-gray-900">
                              <Globe size={14} className="text-gray-400 mr-2 shrink-0" />
                              <span className="truncate">jdih.ojk.go.id/peraturan/sektor-perbankan...</span>
                              <ExternalLink size={12} className="ml-1.5 text-gray-400" />
                            </div>
                          </td>
                          <td className="py-4 px-4 text-sm text-gray-600">Hari ini, 14:30 WIB</td>
                          <td className="py-4 px-4 text-sm text-gray-900 font-medium">12 dokumen</td>
                          <td className="py-4 px-4 text-sm font-semibold text-blue-700">5 baru</td>
                          <td className="py-4 px-4 text-right">
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-gray-100 text-gray-700"><span className="w-1.5 h-1.5 bg-blue-600 rounded-full mr-1.5"></span>Berhasil</span>
                          </td>
                        </tr>
                        <tr className="hover:bg-gray-50/50 transition-colors">
                          <td className="py-4 px-4">
                            <div className="flex items-center text-sm font-medium text-gray-900">
                              <Globe size={14} className="text-gray-400 mr-2 shrink-0" />
                              <span className="truncate">jdih.ojk.go.id/peraturan/pasar-modal-2024</span>
                              <ExternalLink size={12} className="ml-1.5 text-gray-400" />
                            </div>
                          </td>
                          <td className="py-4 px-4 text-sm text-gray-600">Kemarin, 09:15 WIB</td>
                          <td className="py-4 px-4 text-sm text-gray-900 font-medium">8 dokumen</td>
                          <td className="py-4 px-4 text-sm font-semibold text-blue-700">3 baru</td>
                          <td className="py-4 px-4 text-right">
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-gray-100 text-gray-700"><span className="w-1.5 h-1.5 bg-blue-600 rounded-full mr-1.5"></span>Berhasil</span>
                          </td>
                        </tr>
                        <tr className="hover:bg-gray-50/50 transition-colors">
                          <td className="py-4 px-4">
                            <div className="flex items-center text-sm font-medium text-gray-900">
                              <Globe size={14} className="text-gray-400 mr-2 shrink-0" />
                              <span className="truncate">ojk.go.id/id/kanal/fintech/regulasi-sandbox</span>
                              <ExternalLink size={12} className="ml-1.5 text-gray-400" />
                            </div>
                          </td>
                          <td className="py-4 px-4 text-sm text-gray-600">20 Sep 2026, 11:20 WIB</td>
                          <td className="py-4 px-4 text-sm text-gray-900 font-medium">0 dokumen</td>
                          <td className="py-4 px-4 text-sm font-medium text-gray-600">0</td>
                          <td className="py-4 px-4 text-right">
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-red-50 text-red-700"><span className="w-1.5 h-1.5 bg-red-600 rounded-full mr-1.5"></span>Gagal Terhubung</span>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}

          {step === 2 && (
            <div className="animate-in fade-in duration-300">
              {/* TOP HEADER */}
              <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6 flex flex-col md:flex-row md:items-center justify-between shadow-sm">
                <div className="flex items-center space-x-4">
                  <span className="text-sm text-gray-500">Sumber URL:</span>
                  <div className="flex items-center text-sm text-gray-700 bg-gray-50 border border-gray-200 rounded-md px-3 py-1.5">
                    <LinkIcon size={14} className="mr-2 text-gray-400" />
                    https://jdih.ojk.go.id/peraturan/sektor-perbankan
                    <ExternalLink size={14} className="ml-2 text-gray-400" />
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
                      onClick={() => setScrapeFilterTab('all')}
                      className={`text-sm pb-4 border-b-2 transition-colors ${scrapeFilterTab === 'all' ? 'font-bold text-[#B91C1C] border-[#B91C1C]' : 'font-medium text-gray-500 border-transparent hover:text-gray-700'}`}
                    >
                      Semua (12)
                    </button>
                    <button 
                      onClick={() => setScrapeFilterTab('baru')}
                      className={`text-sm pb-4 border-b-2 transition-colors ${scrapeFilterTab === 'baru' ? 'font-bold text-[#B91C1C] border-[#B91C1C]' : 'font-medium text-gray-500 border-transparent hover:text-gray-700'}`}
                    >
                      Baru (5)
                    </button>
                    <button 
                      onClick={() => setScrapeFilterTab('ada')}
                      className={`text-sm pb-4 border-b-2 transition-colors ${scrapeFilterTab === 'ada' ? 'font-bold text-[#B91C1C] border-[#B91C1C]' : 'font-medium text-gray-500 border-transparent hover:text-gray-700'}`}
                    >
                      Sudah Ada (6)
                    </button>
                    <button 
                      onClick={() => setScrapeFilterTab('duplikat')}
                      className={`text-sm pb-4 border-b-2 transition-colors ${scrapeFilterTab === 'duplikat' ? 'font-bold text-[#B91C1C] border-[#B91C1C]' : 'font-medium text-gray-500 border-transparent hover:text-gray-700'}`}
                    >
                      Duplikat (1)
                    </button>
                  </div>
                  <div className="flex items-center space-x-4 pb-4 md:pb-0 md:-mt-4">
                    <label className="flex items-center text-sm text-gray-700 font-medium cursor-pointer">
                      <input 
                        type="checkbox" 
                        checked={isAllSelected}
                        onChange={handleToggleAll}
                        className="w-4 h-4 rounded border-gray-300 accent-[#B91C1C] mr-2" 
                      />
                      Pilih semua dokumen baru
                    </label>
                    <div className="h-4 w-px bg-gray-300"></div>
                    <div className="text-sm font-bold text-gray-900">{selectedDocs.length} dokumen dipilih</div>
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
                      {filteredScrapedDocs.map((doc, idx) => (
                        <tr key={idx} className={doc.active ? 'bg-white' : 'bg-gray-50/50'}>
                          <td className="py-4 px-6 text-center">
                            <input 
                              type="checkbox" 
                              checked={selectedDocs.includes(doc.num)}
                              onChange={() => handleToggleDoc(doc.num)}
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
                  onClick={() => setStep(1)}
                  className="flex items-center text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
                >
                  <ArrowLeft size={16} className="mr-2" /> Kembali ke Parameter Scan
                </button>
                <button 
                  onClick={() => setStep(3)}
                  disabled={selectedDocs.length === 0}
                  className={`${selectedDocs.length === 0 ? 'bg-gray-300 cursor-not-allowed text-gray-500' : 'bg-[#B91C1C] hover:bg-[#a01818] text-white'} font-medium px-6 py-2.5 rounded-md flex items-center transition-colors shadow-sm`}
                >
                  <Download size={18} className="mr-2" />
                  Download Dokumen Terpilih ({selectedDocs.length})
                  <ArrowRight size={18} className="ml-2" />
                </button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className="text-sm font-medium text-gray-500 mb-4 flex items-center space-x-2">
                <span>Dashboard</span> <span className="text-gray-400">&gt;</span> <span>Ingest Dokumen</span> <span className="text-gray-400">&gt;</span> <span>Scraping URL</span> <span className="text-gray-400">&gt;</span> <span className="text-gray-900 font-bold">Proses Ingest Dokumen</span>
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
                        <span className="text-gray-600 text-sm">Sumber URL:</span>
                        <div className="flex items-center font-medium text-gray-900 text-sm">
                          <LinkIcon size={16} className="mr-2 text-gray-600" />
                          https://jdih.ojk.go.id/peraturan/sektor-perbankan
                          <ExternalLink size={14} className="ml-2 text-gray-600" />
                        </div>
                      </div>
                      <div className="flex items-center space-x-8 text-gray-600 text-sm">
                        <div className="flex items-center space-x-2">
                          <span>Target:</span> <span className="text-gray-900">Knowledge Base HERO (Sektor Perbankan)</span>
                        </div>
                        <div className="text-gray-900">{selectedDocs.length} Dokumen Dipilih</div>
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
                      <div className="text-xl font-bold text-gray-700">{downloadProgress}%</div>
                      <div className="text-xs font-bold text-gray-500 uppercase tracking-wider">{Math.floor(downloadProgress / 20)} DARI 5 DOKUMEN SELESAI</div>
                    </div>
                  </div>
                  
                  <div className="w-full bg-gray-100 h-2 rounded-full overflow-hidden mb-8">
                    <div className="h-full bg-[#B91C1C] transition-all duration-500 ease-out" style={{ width: `${downloadProgress}%` }}></div>
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
                          const isDone = downloadProgress >= doc.threshold;
                          const isProcessing = downloadProgress >= (doc.threshold - 20) && downloadProgress < doc.threshold;

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

          {step === 4 && (
            <div className="animate-in fade-in duration-300">
              <div className="text-sm font-medium text-gray-500 mb-4 flex items-center space-x-2">
                <span>Dashboard</span> <span className="text-gray-400">&gt;</span> <span>Ingest Dokumen</span> <span className="text-gray-400">&gt;</span> <span>Scraping URL</span> <span className="text-gray-400">&gt;</span> <span className="text-gray-900 font-bold">Dokumen Berhasil Ditambahkan</span>
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
                    <div className="text-sm text-gray-500 mb-2">Sumber URL</div>
                    <div className="flex items-center text-sm font-bold text-gray-900">
                      <LinkIcon size={16} className="mr-2 text-gray-500" />
                      https://jdih.ojk.go.id/peraturan/sektor-perbankan
                      <ExternalLink size={14} className="ml-2 text-gray-400" />
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-500 mb-2">Target Knowledge Base</div>
                    <div className="text-sm font-bold text-gray-900">
                      HERO (Sektor Perbankan)
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
                  onClick={() => setStep(1)}
                  className="w-full sm:w-auto px-6 py-2.5 border border-gray-300 text-gray-700 font-medium rounded-md hover:bg-gray-50 transition-colors flex items-center justify-center bg-white"
                >
                  <ArrowLeft size={16} className="mr-2" /> Scraping Dokumen Baru
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
      )}

      {/* ======================================================== */}
      {/* TAB SYNC FOLDER/ONEDRIVE */}
      {/* ======================================================== */}
      {activeTab === 'sync' && (
        <>
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
        </>
      )}

      {/* ======================================================== */}
      {/* TAB UPLOAD MANUAL (DRAG & DROP) */}
      {/* ======================================================== */}
      {activeTab === 'upload' && (
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
      )}
    </div>
  );
}
