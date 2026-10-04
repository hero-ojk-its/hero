import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { 
  UploadCloud, 
  FileText, 
  CheckCircle, 
  CheckCircle2, 
  AlertTriangle,
  AlertCircle,
  ArrowRight,
  ArrowLeft, 
  Loader2, 
  X, 
  Info,
  ExternalLink,
  BookOpen,
  FileCode,
  Lock,
  Globe
} from 'lucide-react';
import { 
  uploadManualPdf, 
  checkDuplicate, 
  calculateFileHash,
  getCategories,
  type CategoryDetailResponse,
  type IngestUploadResponse,
  type IngestItemDetailResponse
} from '../../lib/ingestApi';
import { isApiConfigured, ApiError } from '../../lib/api';
import NamingFormatPicker from './components/NamingFormatPicker';
import ManualUploadJobHistory from './components/ManualUploadJobHistory';

interface QueuedFileItem {
  id: string;
  file: File;
  name: string;
  size: number;
  sizeFormatted: string;
  hash: string | null;
  preCheckStatus: 'idle' | 'checking' | 'new' | 'duplicate' | 'unchecked';
  preCheckMessage?: string;
  existingDocumentId?: number | null;
  existingRegulationNumber?: string | null;
  // Execution status
  uploadStatus?: 'pending' | 'uploading' | 'success' | 'duplicate' | 'failed';
  uploadResult?: IngestItemDetailResponse;
  uploadError?: string;
}

export default function UploadTab() {
  // Step: 1 = Form & File Configuration, 2 = Uploading / Results
  const [uploadStep, setUploadStep] = useState<1 | 2>(1);
  const [isDragging, setIsDragging] = useState(false);
  const [queuedFiles, setQueuedFiles] = useState<QueuedFileItem[]>([]);
  const [clientErrors, setClientErrors] = useState<string[]>([]);

  // Peran Dokumen: Wajib dipilih sebelum unggah, TANPA nilai awal
  const [documentRole, setDocumentRole] = useState<'corpus_eksisting' | 'draft_kajian' | null>(null);

  // Parameter Tambahan
  const [accessClassification, setAccessClassification] = useState<'publik' | 'non_publik'>('publik');
  const [categoryId, setCategoryId] = useState<string>('');
  const [categories, setCategories] = useState<CategoryDetailResponse[]>([]);
  const [namingFormat, setNamingFormat] = useState<string[]>(['jenis', 'nomor', 'tahun']);
  const [namingSeparator, setNamingSeparator] = useState<string>('-');

  // Metadata Form (Hanya untuk 1 berkas)
  const [metaTitle, setMetaTitle] = useState('');
  const [metaRegulationNumber, setMetaRegulationNumber] = useState('');
  const [metaRegulationType, setMetaRegulationType] = useState('POJK');
  const [metaBidang, setMetaBidang] = useState('');
  const [metaReleaseDate, setMetaReleaseDate] = useState('');

  // Upload Execution State
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [completedCount, setCompletedCount] = useState(0);
  const [historyRefreshTrigger, setHistoryRefreshTrigger] = useState(0);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load Categories from Backend
  useEffect(() => {
    let mounted = true;
    if (isApiConfigured) {
      getCategories()
        .then((cats) => {
          if (mounted && cats) setCategories(cats);
        })
        .catch((err) => {
          console.warn('Gagal memuat kategori:', err);
        });
    }
    return () => {
      mounted = false;
    };
  }, []);

  // Pre-check duplicate for added files
  const runPreCheck = async (item: QueuedFileItem) => {
    // If not in secure context / crypto.subtle not available
    const isCryptoAvailable = typeof window !== 'undefined' && Boolean(window.crypto?.subtle);
    if (!isCryptoAvailable) {
      setQueuedFiles((prev) =>
        prev.map((f) =>
          f.id === item.id
            ? { ...f, preCheckStatus: 'unchecked', preCheckMessage: 'akan dicek saat unggah' }
            : f
        )
      );
      return;
    }

    setQueuedFiles((prev) =>
      prev.map((f) =>
        f.id === item.id ? { ...f, preCheckStatus: 'checking' } : f
      )
    );

    try {
      const hash = await calculateFileHash(item.file);
      if (!hash) {
        setQueuedFiles((prev) =>
          prev.map((f) =>
            f.id === item.id
              ? { ...f, hash: null, preCheckStatus: 'unchecked', preCheckMessage: 'akan dicek saat unggah' }
              : f
          )
        );
        return;
      }

      if (!isApiConfigured) {
        // Mode contoh (Mock)
        setQueuedFiles((prev) =>
          prev.map((f) =>
            f.id === item.id
              ? {
                  ...f,
                  hash,
                  preCheckStatus: item.name.toLowerCase().includes('duplikat') ? 'duplicate' : 'new',
                  existingDocumentId: item.name.toLowerCase().includes('duplikat') ? 101 : null,
                  preCheckMessage: item.name.toLowerCase().includes('duplikat')
                    ? 'Duplikat dari dokumen #101'
                    : 'Dokumen baru',
                }
              : f
          )
        );
        return;
      }

      const checkRes = await checkDuplicate({ file_hash: hash, file_size: item.size });
      setQueuedFiles((prev) =>
        prev.map((f) => {
          if (f.id !== item.id) return f;
          if (checkRes.is_duplicate) {
            return {
              ...f,
              hash,
              preCheckStatus: 'duplicate',
              existingDocumentId: checkRes.existing_document_id,
              existingRegulationNumber: checkRes.regulation_number,
              preCheckMessage: `Duplikat dari dokumen #${checkRes.existing_document_id || 'terdaftar'}`,
            };
          }
          return {
            ...f,
            hash,
            preCheckStatus: 'new',
            preCheckMessage: 'Dokumen baru',
          };
        })
      );
    } catch (err) {
      console.warn('Pra-cek duplikasi gagal:', err);
      setQueuedFiles((prev) =>
        prev.map((f) =>
          f.id === item.id
            ? { ...f, preCheckStatus: 'unchecked', preCheckMessage: 'akan dicek saat unggah' }
            : f
        )
      );
    }
  };

  // Handle files added via input or drag-drop
  const handleFilesAdded = (rawFiles: File[]) => {
    const newErrors: string[] = [];
    const validItems: QueuedFileItem[] = [];

    rawFiles.forEach((file) => {
      // Validasi Ekstensi PDF di sisi klien
      const isPdf = file.name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf';
      if (!isPdf) {
        newErrors.push(`Berkas "${file.name}" ditolak. Hanya berkas PDF yang diterima.`);
        return;
      }

      const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
      const sizeStr = file.size > 1024 * 1024 ? `${sizeMB} MB` : `${Math.max(1, Math.round(file.size / 1024))} KB`;

      const item: QueuedFileItem = {
        id: `file-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
        file,
        name: file.name,
        size: file.size,
        sizeFormatted: sizeStr,
        hash: null,
        preCheckStatus: 'idle',
      };
      validItems.push(item);
    });

    if (newErrors.length > 0) {
      setClientErrors((prev) => [...prev, ...newErrors]);
    }

    if (validItems.length > 0) {
      setQueuedFiles((prev) => {
        const updated = [...prev, ...validItems];
        // Jika berkas yang ada menjadi tepat 1, otomatis isi saran judul dari nama berkas jika masih kosong
        if (updated.length === 1 && !metaTitle) {
          setMetaTitle(updated[0].name.replace(/\.[^/.]+$/, '').replace(/[_-]/g, ' '));
        }
        return updated;
      });

      // Jalankan pra-cek duplikasi untuk berkas baru
      validItems.forEach((item) => runPreCheck(item));
    }
  };

  const handleRemoveFile = (id: string) => {
    setQueuedFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const handleClearAllFiles = () => {
    setQueuedFiles([]);
    setClientErrors([]);
  };

  const handleLoadSampleFiles = () => {
    // Mode contoh / simulasi
    const dummyFiles = [
      new File(['%PDF-1.4 dummy 1'], 'POJK_No_12_POJK03_2024_Ketahanan_Siber.pdf', { type: 'application/pdf' }),
      new File(['%PDF-1.4 dummy 2'], 'SEOJK_No_08_SEOJK03_2024_Pedoman_AI.pdf', { type: 'application/pdf' }),
      new File(['%PDF-1.4 dummy 3'], 'POJK_No_03_POJK03_2024_Duplikat.pdf', { type: 'application/pdf' }),
    ];
    handleFilesAdded(dummyFiles);
  };

  // Eksekusi Unggah Berkas: 1 request per berkas, paralel maksimal 2
  const handleStartUpload = async () => {
    if (queuedFiles.length === 0 || !documentRole) return;

    setIsUploading(true);
    setUploadStep(2);
    setCompletedCount(0);
    setUploadProgress(0);

    const totalFiles = queuedFiles.length;
    let finishedCount = 0;

    // Inisialisasi status upload
    setQueuedFiles((prev) =>
      prev.map((f) => ({
        ...f,
        uploadStatus: 'pending',
        uploadProgress: 0,
      }))
    );

    // Queue worker dengan concurrency maksimal 2
    const concurrency = 2;
    const itemsToUpload = [...queuedFiles];
    let currentIndex = 0;

    const processItem = async (item: QueuedFileItem) => {
      // Mark as uploading
      setQueuedFiles((prev) =>
        prev.map((f) => (f.id === item.id ? { ...f, uploadStatus: 'uploading' } : f))
      );

      if (!isApiConfigured) {
        // Mode contoh (Mock)
        await new Promise((r) => setTimeout(r, 800));
        const isDupe = item.name.toLowerCase().includes('duplikat');
        const mockDetail: IngestItemDetailResponse = {
          filename: item.name,
          status: isDupe ? 'duplicate' : 'success',
          document_id: isDupe ? undefined : 201 + Math.floor(Math.random() * 50),
          duplicate_of_document_id: isDupe ? 101 : undefined,
          title: item.name.replace(/\.[^/.]+$/, ''),
          regulation_number: isDupe ? 'POJK No. 3/POJK.03/2024' : 'POJK No. 12/POJK.03/2024',
          message: isDupe ? 'Dokumen duplikat terdeteksi di KBS' : 'Dokumen berhasil disimpan di Knowledge Base',
        };

        finishedCount++;
        setCompletedCount(finishedCount);
        setUploadProgress(Math.round((finishedCount / totalFiles) * 100));

        setQueuedFiles((prev) =>
          prev.map((f) =>
            f.id === item.id
              ? {
                  ...f,
                  uploadStatus: isDupe ? 'duplicate' : 'success',
                  uploadResult: mockDetail,
                }
              : f
          )
        );
        return;
      }

      // Mode API Nyata
      try {
        const formData = new FormData();
        formData.append('files', item.file);
        formData.append('access_classification', accessClassification);
        formData.append('document_role', documentRole);
        formData.append('job_type', 'unggah_manual');

        if (categoryId) {
          formData.append('category_id', categoryId);
        }
        if (namingFormat && namingFormat.length > 0) {
          formData.append('naming_format', namingFormat.join(','));
        }
        if (namingSeparator) {
          formData.append('naming_separator', namingSeparator);
        }

        // Metadata hanya jika tepat 1 berkas
        if (totalFiles === 1) {
          if (metaTitle.trim()) formData.append('title', metaTitle.trim());
          if (metaRegulationNumber.trim()) formData.append('regulation_number', metaRegulationNumber.trim());
          if (metaRegulationType.trim()) formData.append('regulation_type', metaRegulationType.trim());
          if (metaBidang.trim()) formData.append('bidang', metaBidang.trim());
          if (metaReleaseDate.trim()) formData.append('release_date', metaReleaseDate.trim());
        }

        const res: IngestUploadResponse = await uploadManualPdf(formData);
        const detail = res.details && res.details.length > 0 ? res.details[0] : null;

        finishedCount++;
        setCompletedCount(finishedCount);
        setUploadProgress(Math.round((finishedCount / totalFiles) * 100));

        if (!detail) {
          setQueuedFiles((prev) =>
            prev.map((f) =>
              f.id === item.id
                ? {
                    ...f,
                    uploadStatus: 'failed',
                    uploadError: 'Tidak ada rincian hasil dari peladen backend.',
                  }
                : f
            )
          );
        } else if (detail.status === 'success') {
          setQueuedFiles((prev) =>
            prev.map((f) =>
              f.id === item.id
                ? {
                    ...f,
                    uploadStatus: 'success',
                    uploadResult: detail,
                  }
                : f
            )
          );
        } else if (detail.status === 'duplicate') {
          setQueuedFiles((prev) =>
            prev.map((f) =>
              f.id === item.id
                ? {
                    ...f,
                    uploadStatus: 'duplicate',
                    uploadResult: detail,
                  }
                : f
            )
          );
        } else {
          setQueuedFiles((prev) =>
            prev.map((f) =>
              f.id === item.id
                ? {
                    ...f,
                    uploadStatus: 'failed',
                    uploadResult: detail,
                    uploadError: detail.error || detail.message || detail.reason_code || 'Gagal diproses di server',
                  }
                : f
            )
          );
        }
      } catch (err: unknown) {
        finishedCount++;
        setCompletedCount(finishedCount);
        setUploadProgress(Math.round((finishedCount / totalFiles) * 100));

        const errMsg =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
            ? err.message
            : 'Gagal menghubungi peladen saat mengunggah berkas.';

        setQueuedFiles((prev) =>
          prev.map((f) =>
            f.id === item.id
              ? {
                  ...f,
                  uploadStatus: 'failed',
                  uploadError: errMsg,
                }
              : f
          )
        );
      }
    };

    // Worker loop with concurrency limit
    const worker = async () => {
      while (currentIndex < itemsToUpload.length) {
        const item = itemsToUpload[currentIndex++];
        await processItem(item);
      }
    };

    const workers = Array.from({ length: Math.min(concurrency, itemsToUpload.length) }, () => worker());
    await Promise.all(workers);

    setIsUploading(false);
    setHistoryRefreshTrigger((prev) => prev + 1);
  };

  const handleResetForm = () => {
    setQueuedFiles([]);
    setClientErrors([]);
    setDocumentRole(null);
    setMetaTitle('');
    setMetaRegulationNumber('');
    setMetaBidang('');
    setMetaReleaseDate('');
    setUploadStep(1);
    setCompletedCount(0);
    setUploadProgress(0);
  };

  // Sample input for NamingFormatPicker live preview
  const sampleInput =
    queuedFiles.length === 1
      ? {
          title: metaTitle || queuedFiles[0].name.replace(/\.[^/.]+$/, ''),
          regulation_number: metaRegulationNumber || 'POJK-1-2026',
          regulation_type: metaRegulationType || 'POJK',
          bidang: metaBidang || 'Perbankan',
          year: metaReleaseDate ? metaReleaseDate.substring(0, 4) : '2026',
        }
      : null;

  const successCount = queuedFiles.filter((f) => f.uploadStatus === 'success').length;
  const duplicateCount = queuedFiles.filter((f) => f.uploadStatus === 'duplicate').length;
  const failedCount = queuedFiles.filter((f) => f.uploadStatus === 'failed').length;

  return (
    <div className="space-y-6">
      {/* ========================================================================= */}
      {/* TAHAP 1: KONFIGURASI & PEMILIHAN BERKAS                                   */}
      {/* ========================================================================= */}
      {uploadStep === 1 && (
        <>
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-in fade-in duration-300">
            <div className="flex justify-between items-center mb-2">
              <h3 className="text-lg font-bold text-gray-900">Upload Manual Dokumen Regulasi</h3>
              <span className="inline-flex items-center bg-gray-100 text-gray-600 text-xs font-semibold px-2.5 py-1 rounded-full">
                <span className="w-1.5 h-1.5 bg-red-700 rounded-full mr-1.5"></span>
                Tahap 1: Unggah & Konfigurasi Berkas
              </span>
            </div>
            <p className="text-gray-600 text-sm mb-6">
              Unggah berkas regulasi PDF secara langsung melalui drag & drop atau pemilih berkas untuk dipindai dan dimasukkan ke Knowledge Base.
            </p>

            <div className="space-y-6">
              {/* 1. PERAN DOKUMEN (WAJIB, TANPA NILAI AWAL) */}
              <div className="border border-gray-200 rounded-xl p-5 bg-gradient-to-br from-gray-50/70 to-white">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-bold text-gray-900 uppercase tracking-wider flex items-center">
                    Peran Dokumen <span className="text-red-600 ml-1">* (Wajib Dipilih Sebelum Unggah)</span>
                  </label>
                  {!documentRole && (
                    <span className="text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2.5 py-0.5 rounded-full flex items-center">
                      <AlertTriangle size={12} className="mr-1" /> Belum dipilih
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 mb-4">
                  Tentukan peran dokumen untuk mengatur penempatan dan fungsi naskah dalam Knowledge Base HERO.
                </p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Kartu: Peraturan Eksisting */}
                  <div
                    id="card-role-corpus-eksisting"
                    onClick={() => setDocumentRole('corpus_eksisting')}
                    className={`border-2 rounded-xl p-4 cursor-pointer transition-all flex items-start space-x-3.5 select-none ${
                      documentRole === 'corpus_eksisting'
                        ? 'border-red-600 bg-red-50/40 shadow-sm ring-2 ring-red-600/10'
                        : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50/80 bg-white'
                    }`}
                  >
                    <div
                      className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                        documentRole === 'corpus_eksisting'
                          ? 'bg-red-700 text-white'
                          : 'bg-gray-100 text-gray-500'
                      }`}
                    >
                      <BookOpen size={20} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-bold text-gray-900">Peraturan Eksisting</span>
                        <input
                          id="radio-role-corpus-eksisting"
                          type="radio"
                          name="document_role"
                          checked={documentRole === 'corpus_eksisting'}
                          onChange={() => setDocumentRole('corpus_eksisting')}
                          className="w-4 h-4 text-red-600 accent-red-600 cursor-pointer"
                        />
                      </div>
                      <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                        Regulasi yang berlaku, diubah, atau dicabut untuk korpus acuan hukum Knowledge Base.
                      </p>
                      <span className="inline-block mt-2 text-[10px] font-mono text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                        document_role: corpus_eksisting
                      </span>
                    </div>
                  </div>

                  {/* Kartu: Draft Peraturan Baru */}
                  <div
                    id="card-role-draft-kajian"
                    onClick={() => setDocumentRole('draft_kajian')}
                    className={`border-2 rounded-xl p-4 cursor-pointer transition-all flex items-start space-x-3.5 select-none ${
                      documentRole === 'draft_kajian'
                        ? 'border-red-600 bg-red-50/40 shadow-sm ring-2 ring-red-600/10'
                        : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50/80 bg-white'
                    }`}
                  >
                    <div
                      className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                        documentRole === 'draft_kajian'
                          ? 'bg-red-700 text-white'
                          : 'bg-gray-100 text-gray-500'
                      }`}
                    >
                      <FileCode size={20} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-bold text-gray-900">Draft Peraturan Baru</span>
                        <input
                          id="radio-role-draft-kajian"
                          type="radio"
                          name="document_role"
                          checked={documentRole === 'draft_kajian'}
                          onChange={() => setDocumentRole('draft_kajian')}
                          className="w-4 h-4 text-red-600 accent-red-600 cursor-pointer"
                        />
                      </div>
                      <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                        Rancangan peraturan perundang-undangan baru untuk keperluan telaah kajian dan harmonisasi.
                      </p>
                      <span className="inline-block mt-2 text-[10px] font-mono text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                        document_role: draft_kajian
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* 2. DRAG & DROP ZONE (HANYA BERKAS PDF) */}
              <div>
                <label className="block text-xs font-bold text-gray-900 mb-2 uppercase tracking-wider">
                  Area Unggah Berkas PDF <span className="text-red-600">*</span>
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
                      ? 'border-red-600 bg-red-50/60 ring-4 ring-red-600/10 scale-[1.005]'
                      : 'border-gray-300 hover:border-red-600 hover:bg-gray-50/70 bg-white'
                  }`}
                >
                  <input
                    type="file"
                    ref={fileInputRef}
                    className="hidden"
                    multiple
                    accept=".pdf,application/pdf"
                    onChange={(e) => {
                      if (e.target.files && e.target.files.length > 0) {
                        handleFilesAdded(Array.from(e.target.files));
                        e.target.value = '';
                      }
                    }}
                  />
                  <div className="w-14 h-14 mx-auto rounded-full bg-red-50 text-red-700 flex items-center justify-center mb-3">
                    <UploadCloud size={28} className={isDragging ? 'animate-bounce text-red-700' : 'text-red-700'} />
                  </div>
                  <div className="text-base font-bold text-gray-900 mb-1">
                    {isDragging ? 'Lepaskan berkas di sini untuk mengunggah' : 'Tarik & Lepaskan berkas regulasi ke sini'}
                  </div>
                  <p className="text-sm text-gray-500 mb-3">
                    atau <span className="text-red-700 font-semibold underline underline-offset-2">telusuri file</span> dari komputer Anda
                  </p>
                  <div className="inline-flex items-center gap-2 text-xs text-gray-500 bg-gray-50 px-3.5 py-1.5 rounded-full border border-gray-200">
                    <span className="font-semibold text-gray-700">Hanya berkas PDF yang diterima.</span>
                    <span>•</span>
                    <span>Maksimal 25MB per berkas</span>
                  </div>
                </div>
              </div>

              {/* CLIENT VALIDATION ERRORS BANNER */}
              {clientErrors.length > 0 && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-xs text-red-800 space-y-1">
                  <div className="flex items-center font-bold text-sm text-red-900 mb-1">
                    <AlertCircle size={16} className="mr-1.5 text-red-600 shrink-0" />
                    Berkas Ditolak di Sisi Klien
                  </div>
                  {clientErrors.map((err, idx) => (
                    <div key={idx} className="flex items-center justify-between">
                      <span>• {err}</span>
                    </div>
                  ))}
                  <div className="pt-1 text-right">
                    <button
                      type="button"
                      onClick={() => setClientErrors([])}
                      className="text-red-600 hover:text-red-800 font-semibold underline text-[11px]"
                    >
                      Tutup pesan
                    </button>
                  </div>
                </div>
              )}

              {/* 3. DAFTAR BERKAS TERPILIH & PRA-CEK DUPLIKASI */}
              {queuedFiles.length > 0 ? (
                <div>
                  <div className="flex justify-between items-center mb-2.5">
                    <div className="flex items-center space-x-2">
                      <label className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                        Berkas Terpilih ({queuedFiles.length})
                      </label>
                      <span className="text-xs text-gray-400">• Pra-cek duplikasi dihitung secara otomatis</span>
                    </div>
                    <div className="flex items-center space-x-3">
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="text-xs font-semibold text-red-700 hover:text-red-800 transition-colors"
                      >
                        + Tambah Berkas
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

                  <div className="border border-gray-200 rounded-xl divide-y divide-gray-100 max-h-72 overflow-y-auto bg-gray-50/40">
                    {queuedFiles.map((item) => (
                      <div key={item.id} className="p-3.5 bg-white flex items-center justify-between hover:bg-gray-50/80 transition-colors">
                        <div className="flex items-center space-x-3 min-w-0 pr-4">
                          <div className="w-9 h-9 rounded-lg bg-red-50 text-red-700 border border-red-100 flex items-center justify-center shrink-0">
                            <FileText size={18} />
                          </div>
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-gray-900 truncate max-w-md" title={item.name}>
                              {item.name}
                            </div>
                            <div className="flex items-center space-x-2 text-xs text-gray-500 mt-0.5">
                              <span>{item.sizeFormatted}</span>
                              {item.hash && (
                                <>
                                  <span>•</span>
                                  <span className="font-mono text-[11px] text-gray-400" title={item.hash}>
                                    SHA: {item.hash.substring(0, 10)}...
                                  </span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Status Pra-Cek Duplikasi */}
                        <div className="flex items-center space-x-3 shrink-0">
                          {item.preCheckStatus === 'checking' && (
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
                              <Loader2 size={12} className="mr-1.5 animate-spin" /> Memeriksa duplikasi...
                            </span>
                          )}
                          {item.preCheckStatus === 'new' && (
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                              <CheckCircle size={13} className="mr-1.5 text-emerald-600" />
                              Baru (Aman)
                            </span>
                          )}
                          {item.preCheckStatus === 'duplicate' && (
                            <span
                              className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200"
                              title={item.preCheckMessage || 'Dokumen duplikat terdeteksi'}
                            >
                              <AlertTriangle size={13} className="mr-1.5 text-amber-600" />
                              Duplikat dari dokumen #{item.existingDocumentId || 'KBS'}
                              {item.existingRegulationNumber ? ` (${item.existingRegulationNumber})` : ''}
                            </span>
                          )}
                          {item.preCheckStatus === 'unchecked' && (
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200">
                              Akan dicek saat unggah
                            </span>
                          )}

                          <button
                            type="button"
                            onClick={() => handleRemoveFile(item.id)}
                            className="text-gray-400 hover:text-red-600 p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
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
                    Belum ada berkas PDF yang dipilih. Anda dapat menarik berkas ke area di atas atau memuat contoh berkas simulasi.
                  </div>
                  <button
                    id="btn-load-sample"
                    type="button"
                    onClick={handleLoadSampleFiles}
                    className="px-3.5 py-1.5 bg-white border border-gray-300 hover:border-gray-400 text-gray-700 text-xs font-semibold rounded-lg shadow-sm hover:bg-gray-50 transition-colors shrink-0"
                  >
                    Muat Contoh Berkas (3 PDF)
                  </button>
                </div>
              )}

              {/* 4. FORMULIR METADATA DOKUMEN (HANYA BISA DIISI BILA 1 BERKAS) */}
              <div className={`border rounded-xl p-5 transition-all ${
                queuedFiles.length === 1 
                  ? 'bg-white border-gray-200' 
                  : 'bg-gray-50/70 border-gray-200 opacity-90'
              }`}>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-bold text-gray-900 uppercase tracking-wider flex items-center">
                    Metadata Dokumen 
                    <span className="ml-2 text-xs font-normal text-gray-500">
                      (Hanya dapat diisi manual jika mengunggah tepat 1 berkas)
                    </span>
                  </label>
                  {queuedFiles.length > 1 && (
                    <span className="text-xs font-semibold text-gray-600 bg-gray-200/80 px-2 py-0.5 rounded">
                      Form Dinonaktifkan ({queuedFiles.length} berkas)
                    </span>
                  )}
                </div>

                {queuedFiles.length > 1 ? (
                  <div className="p-3 bg-amber-50/80 border border-amber-200 rounded-lg text-xs text-amber-800 flex items-start mb-3">
                    <Info size={16} className="text-amber-600 mr-2 shrink-0 mt-0.5" />
                    <div>
                      <strong>Formulir metadata dinonaktifkan untuk unggahan jamak.</strong> Untuk unggahan lebih dari 1 berkas, metadata per-dokumen (judul, nomor, jenis, bidang, tanggal) akan diekstrak secara otomatis oleh sistem atau dapat disesuaikan pada tahap peninjauan.
                    </div>
                  </div>
                ) : queuedFiles.length === 0 ? (
                  <p className="text-xs text-gray-500 mb-4">
                    Pilih berkas PDF terlebih dahulu untuk mengaktifkan pengisian metadata dokumen tunggal.
                  </p>
                ) : (
                  <p className="text-xs text-gray-500 mb-4">
                    Lengkapi metadata awal untuk berkas yang diunggah. Metadata ini akan disimpan langsung ke Knowledge Base.
                  </p>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Judul Dokumen */}
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold text-gray-700 mb-1">
                      Judul Dokumen
                    </label>
                    <input
                      id="input-meta-title"
                      type="text"
                      disabled={queuedFiles.length !== 1}
                      value={metaTitle}
                      onChange={(e) => setMetaTitle(e.target.value)}
                      placeholder="Contoh: Penerapan Manajemen Risiko dalam Penggunaan Teknologi Informasi"
                      className="block w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:ring-red-600 focus:border-red-600 disabled:bg-gray-100 disabled:text-gray-400 placeholder-gray-400"
                    />
                  </div>

                  {/* Nomor Regulasi */}
                  <div>
                    <label className="block text-xs font-semibold text-gray-700 mb-1">
                      Nomor Regulasi
                    </label>
                    <input
                      id="input-meta-reg-num"
                      type="text"
                      disabled={queuedFiles.length !== 1}
                      value={metaRegulationNumber}
                      onChange={(e) => setMetaRegulationNumber(e.target.value)}
                      placeholder="Contoh: POJK-12-2024 atau PP-24-2005"
                      className="block w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:ring-red-600 focus:border-red-600 disabled:bg-gray-100 disabled:text-gray-400 placeholder-gray-400"
                    />
                  </div>

                  {/* Jenis Regulasi */}
                  <div>
                    <label className="block text-xs font-semibold text-gray-700 mb-1">
                      Jenis Regulasi
                    </label>
                    <select
                      id="select-meta-reg-type"
                      disabled={queuedFiles.length !== 1}
                      value={metaRegulationType}
                      onChange={(e) => setMetaRegulationType(e.target.value)}
                      className="block w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:ring-red-600 focus:border-red-600 disabled:bg-gray-100 disabled:text-gray-400 bg-white"
                    >
                      <option value="POJK">POJK (Peraturan Otoritas Jasa Keuangan)</option>
                      <option value="SEOJK">SEOJK (Surat Edaran OJK)</option>
                      <option value="UU">UU (Undang-Undang)</option>
                      <option value="PP">PP (Peraturan Pemerintah)</option>
                      <option value="Perpres">Perpres (Peraturan Presiden)</option>
                      <option value="Permen">Permen (Peraturan Menteri)</option>
                      <option value="PBI">PBI (Peraturan Bank Indonesia)</option>
                      <option value="Internal">Internal / Kajian Lainnya</option>
                    </select>
                  </div>

                  {/* Bidang / Sektor */}
                  <div>
                    <label className="block text-xs font-semibold text-gray-700 mb-1">
                      Bidang / Sektor
                    </label>
                    <input
                      id="input-meta-bidang"
                      type="text"
                      disabled={queuedFiles.length !== 1}
                      value={metaBidang}
                      onChange={(e) => setMetaBidang(e.target.value)}
                      placeholder="Contoh: Perbankan, Pasar Modal, Fintech"
                      className="block w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:ring-red-600 focus:border-red-600 disabled:bg-gray-100 disabled:text-gray-400 placeholder-gray-400"
                    />
                  </div>

                  {/* Tanggal Terbit */}
                  <div>
                    <label className="block text-xs font-semibold text-gray-700 mb-1">
                      Tanggal Terbit
                    </label>
                    <input
                      id="input-meta-release-date"
                      type="date"
                      disabled={queuedFiles.length !== 1}
                      value={metaReleaseDate}
                      onChange={(e) => setMetaReleaseDate(e.target.value)}
                      className="block w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:ring-red-600 focus:border-red-600 disabled:bg-gray-100 disabled:text-gray-400 bg-white"
                    />
                  </div>
                </div>
              </div>

              {/* 5. PENGATURAN AKSES & KATEGORI */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-2 uppercase tracking-wider flex items-center">
                    Klasifikasi Akses <span className="text-red-600 ml-1">* (Kepatuhan NDA)</span>
                  </label>
                  <select
                    value={accessClassification}
                    onChange={(e) => setAccessClassification(e.target.value as 'publik' | 'non_publik')}
                    className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm text-gray-900 focus:ring-red-600 focus:border-red-600 bg-white font-medium"
                  >
                    <option value="publik">Publik (Terbuka untuk umum)</option>
                    <option value="non_publik">Non-Publik (Kerahasiaan / Internal NDA)</option>
                  </select>
                  <p className="text-xs text-gray-500 mt-1.5 flex items-center">
                    {accessClassification === 'non_publik' ? (
                      <span className="text-amber-700 flex items-center">
                        <Lock size={12} className="mr-1 text-amber-600" />
                        Dokumen non-publik dilindungi aksesnya dan memerlukan autentikasi login.
                      </span>
                    ) : (
                      <span className="text-gray-500 flex items-center">
                        <Globe size={12} className="mr-1 text-gray-400" />
                        Dapat diakses secara umum di repositori Knowledge Base.
                      </span>
                    )}
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-2 uppercase tracking-wider">
                    Kategori Target Knowledge Base (Opsional)
                  </label>
                  <select
                    value={categoryId}
                    onChange={(e) => setCategoryId(e.target.value)}
                    className="block w-full py-2.5 px-3 border border-gray-300 rounded-lg text-sm text-gray-900 focus:ring-red-600 focus:border-red-600 bg-white font-medium"
                  >
                    <option value="">-- Tanpa Kategori Khusus (Kategori Default) --</option>
                    {categories.map((c) => (
                      <option key={c.id} value={String(c.id)}>
                        {c.name}
                      </option>
                    ))}
                    {categories.length === 0 && (
                      <>
                        <option value="perbankan">Perbankan</option>
                        <option value="pasar_modal">Pasar Modal</option>
                        <option value="fintech">Fintech</option>
                        <option value="asuransi">Asuransi</option>
                      </>
                    )}
                  </select>
                  <p className="text-xs text-gray-500 mt-1.5">
                    Menempatkan berkas pada klasifikasi folder atau sektor tertentu di Knowledge Base.
                  </p>
                </div>
              </div>

              {/* 6. FORMAT PENAMAAN BERKAS DINAMIS */}
              <div className="border border-gray-200 rounded-xl p-5 bg-white">
                <NamingFormatPicker
                  value={namingFormat}
                  onChange={setNamingFormat}
                  separator={namingSeparator}
                  onSeparatorChange={setNamingSeparator}
                  sampleInput={sampleInput}
                />
              </div>

              {/* PETUNJUK BILA PERAN BELUM DIPILIH & TOMBOL UNGGAH */}
              <div className="pt-2">
                {!documentRole && (
                  <div className="mb-3.5 p-3.5 bg-amber-50 border border-amber-200 rounded-xl flex items-center text-amber-800 text-xs font-medium animate-in fade-in duration-200">
                    <AlertTriangle size={18} className="text-amber-600 mr-2.5 shrink-0" />
                    <span>
                      <strong>Perhatian:</strong> Peran dokumen (Draft Peraturan Baru atau Peraturan Eksisting) wajib dipilih sebelum Anda dapat mengunggah berkas.
                    </span>
                  </div>
                )}

                <div className="flex items-center justify-between">
                  <div className="text-xs text-gray-500">
                    {queuedFiles.length > 0
                      ? `${queuedFiles.length} berkas PDF siap diunggah.`
                      : 'Pilih minimal 1 berkas PDF untuk mengunggah.'}
                  </div>

                  <button
                    id="btn-submit-upload"
                    type="button"
                    onClick={handleStartUpload}
                    disabled={queuedFiles.length === 0 || !documentRole || isUploading}
                    className={`font-semibold px-6 py-2.5 rounded-lg flex items-center transition-all shadow-sm ${
                      queuedFiles.length === 0 || !documentRole || isUploading
                        ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                        : 'bg-red-700 hover:bg-red-800 text-white cursor-pointer active:scale-95'
                    }`}
                  >
                    {isUploading ? (
                      <>
                        <Loader2 size={18} className="mr-2 animate-spin text-white" />
                        Mengunggah ({completedCount}/{queuedFiles.length})...
                      </>
                    ) : (
                      <>
                        <UploadCloud size={18} className="mr-2" />
                        Unggah Dokumen ke Knowledge Base ({queuedFiles.length})
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* RIWAYAT UPLOAD MANUAL TERAKHIR */}
          <ManualUploadJobHistory refreshTrigger={historyRefreshTrigger} />
        </>
      )}

      {/* ========================================================================= */}
      {/* TAHAP 2: PROGRES UNGGAH & RINGKASAN HASIL                                */}
      {/* ========================================================================= */}
      {uploadStep === 2 && (
        <div className="space-y-6 animate-in fade-in duration-300">
          {/* Header breadcrumb & title */}
          <div>
            <div className="text-sm font-medium text-gray-500 mb-2 flex items-center space-x-2">
              <span>Dashboard</span>
              <span className="text-gray-400">&gt;</span>
              <span>Ingest Dokumen</span>
              <span className="text-gray-400">&gt;</span>
              <span className="text-gray-900 font-bold">Hasil Upload Manual</span>
            </div>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h3 className="text-2xl font-bold text-gray-900 tracking-tight">
                  {isUploading ? 'Memproses Unggahan Dokumen' : 'Unggahan Selesai'}
                </h3>
                <p className="text-gray-600 mt-0.5 text-sm">
                  {isUploading
                    ? `Mengunggah berkas secara paralel (maksimal 2 bersamaan) ke Knowledge Base.`
                    : `Pemrosesan seluruh berkas telah selesai.`}
                </p>
              </div>

              {!isUploading && (
                <div className="flex items-center space-x-3">
                  <button
                    id="btn-reset-upload"
                    type="button"
                    onClick={handleResetForm}
                    className="px-4 py-2 border border-gray-300 bg-white hover:bg-gray-50 text-gray-700 text-xs font-semibold rounded-lg shadow-sm transition-colors flex items-center"
                  >
                    <ArrowLeft size={14} className="mr-1.5" />
                    Unggah Berkas Lain
                  </button>
                  <Link
                    to="/knowledge"
                    className="px-4 py-2 bg-red-700 hover:bg-red-800 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors flex items-center"
                  >
                    Buka Knowledge Base
                    <ArrowRight size={14} className="ml-1.5" />
                  </Link>
                </div>
              )}
            </div>
          </div>

          {/* Progress Bar & Status Cards */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <div className="flex justify-between items-center mb-3">
              <div className="flex items-center text-sm font-semibold text-gray-800">
                {isUploading ? (
                  <>
                    <Loader2 size={18} className="mr-2.5 animate-spin text-red-700" />
                    Sedang Memproses Berkas... ({completedCount} dari {queuedFiles.length} selesai)
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={18} className="mr-2 text-emerald-600" />
                    Seluruh Permintaan Selesai Diproses
                  </>
                )}
              </div>
              <span className="text-base font-bold text-gray-900">{uploadProgress}%</span>
            </div>

            <div className="w-full bg-gray-100 h-2.5 rounded-full overflow-hidden mb-6">
              <div
                className={`h-full transition-all duration-300 ease-out ${
                  failedCount > 0 && !isUploading && successCount === 0 ? 'bg-red-600' : 'bg-red-700'
                }`}
                style={{ width: `${uploadProgress}%` }}
              ></div>
            </div>

            {/* Statistik Ringkasan */}
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 pt-2">
              <div className="border border-gray-200 rounded-xl p-3.5 bg-gray-50">
                <div className="text-xs text-gray-500 font-medium">Total Berkas</div>
                <div className="text-xl font-bold text-gray-900 mt-1">{queuedFiles.length}</div>
              </div>
              <div className="border border-emerald-200 rounded-xl p-3.5 bg-emerald-50/50">
                <div className="text-xs text-emerald-700 font-medium">Berhasil Masuk KB</div>
                <div className="text-xl font-bold text-emerald-700 mt-1">{successCount}</div>
              </div>
              <div className="border border-amber-200 rounded-xl p-3.5 bg-amber-50/50">
                <div className="text-xs text-amber-700 font-medium">Duplikat Terdeteksi</div>
                <div className="text-xl font-bold text-amber-700 mt-1">{duplicateCount}</div>
              </div>
              <div className="border border-red-200 rounded-xl p-3.5 bg-red-50/50">
                <div className="text-xs text-red-700 font-medium">Gagal Diproses</div>
                <div className="text-xl font-bold text-red-700 mt-1">{failedCount}</div>
              </div>
            </div>
          </div>

          {/* TABEL HASIL PER BERKAS */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="p-4 border-b border-gray-100 flex items-center justify-between">
              <h4 className="font-bold text-sm text-gray-900">Rincian Hasil Pemrosesan Berkas</h4>
              <span className="text-xs text-gray-500">Maksimal 2 berkas diproses secara simultan</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-gray-100 text-xs font-bold text-gray-500 uppercase tracking-wider bg-gray-50/70">
                    <th className="py-3 px-4">Nama Berkas</th>
                    <th className="py-3 px-4">Ukuran</th>
                    <th className="py-3 px-4">Status Hasil</th>
                    <th className="py-3 px-4">Keterangan / Alasan</th>
                    <th className="py-3 px-4 text-right">Tautan / Aksi</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 text-sm">
                  {queuedFiles.map((item) => (
                    <tr key={item.id} className="hover:bg-gray-50/60 transition-colors">
                      <td className="py-3.5 px-4">
                        <div className="flex items-center text-sm font-medium text-gray-900">
                          <FileText size={16} className="text-red-700 mr-2 shrink-0" />
                          <span className="font-semibold text-gray-900">{item.name}</span>
                        </div>
                        {item.uploadResult?.title && (
                          <div className="text-xs text-gray-500 mt-0.5 ml-6">
                            Judul: {item.uploadResult.title}
                          </div>
                        )}
                        {item.uploadResult?.regulation_number && (
                          <div className="text-xs text-gray-400 mt-0.5 ml-6">
                            Nomor: {item.uploadResult.regulation_number}
                          </div>
                        )}
                      </td>

                      <td className="py-3.5 px-4 text-xs text-gray-600 whitespace-nowrap">
                        {item.sizeFormatted}
                      </td>

                      <td className="py-3.5 px-4">
                        {item.uploadStatus === 'pending' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                            Menunggu antrean
                          </span>
                        )}
                        {item.uploadStatus === 'uploading' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                            <Loader2 size={12} className="mr-1.5 animate-spin" />
                            Sedang memproses...
                          </span>
                        )}
                        {item.uploadStatus === 'success' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <CheckCircle size={13} className="mr-1.5 text-emerald-600" />
                            Berhasil
                          </span>
                        )}
                        {item.uploadStatus === 'duplicate' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                            <AlertTriangle size={13} className="mr-1.5 text-amber-600" />
                            Duplikat
                          </span>
                        )}
                        {item.uploadStatus === 'failed' && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
                            <AlertCircle size={13} className="mr-1.5 text-red-600" />
                            Gagal
                          </span>
                        )}
                      </td>

                      <td className="py-3.5 px-4 text-xs">
                        {item.uploadStatus === 'success' && (
                          <span className="text-emerald-700">
                            Dokumen berhasil disimpan ke Knowledge Base (ID: #{item.uploadResult?.document_id}).
                          </span>
                        )}
                        {item.uploadStatus === 'duplicate' && (
                          <span className="text-amber-800">
                            Duplikat dari dokumen #{item.uploadResult?.duplicate_of_document_id || 'terdaftar'}.
                            {item.uploadResult?.message ? ` ${item.uploadResult.message}` : ''}
                          </span>
                        )}
                        {item.uploadStatus === 'failed' && (
                          <span className="text-red-700 font-medium">
                            {item.uploadError || item.uploadResult?.error || item.uploadResult?.reason_code || 'Penolakan sistem peladen.'}
                          </span>
                        )}
                        {item.uploadStatus === 'uploading' && (
                          <span className="text-gray-400">Mengunggah ke backend & ekstraksi teks PDF...</span>
                        )}
                        {item.uploadStatus === 'pending' && (
                          <span className="text-gray-400">Menunggu slot pengerjaan paralel...</span>
                        )}
                      </td>

                      <td className="py-3.5 px-4 text-right">
                        {item.uploadStatus === 'success' && item.uploadResult?.document_id && (
                          <Link
                            to={`/documents/${item.uploadResult.document_id}`}
                            className="inline-flex items-center text-xs font-semibold text-red-700 hover:text-red-800 underline underline-offset-2"
                          >
                            Buka Dokumen #{item.uploadResult.document_id}
                            <ExternalLink size={12} className="ml-1" />
                          </Link>
                        )}
                        {item.uploadStatus === 'duplicate' && item.uploadResult?.duplicate_of_document_id && (
                          <Link
                            to={`/documents/${item.uploadResult.duplicate_of_document_id}`}
                            className="inline-flex items-center text-xs font-semibold text-amber-700 hover:text-amber-800 underline underline-offset-2"
                          >
                            Buka Pembanding #{item.uploadResult.duplicate_of_document_id}
                            <ExternalLink size={12} className="ml-1" />
                          </Link>
                        )}
                        {item.uploadStatus === 'failed' && (
                          <span className="text-xs text-gray-400">-</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* RIWAYAT DI TAHAP HASIL */}
          <ManualUploadJobHistory refreshTrigger={historyRefreshTrigger} />
        </div>
      )}
    </div>
  );
}
