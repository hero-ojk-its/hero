import React, { useState, useRef, useEffect } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { 
  ArrowLeft, 
  FileText, 
  Download, 
  Search, 
  Info, 
  Paperclip, 
  ExternalLink, 
  ShieldCheck, 
  Landmark, 
  Globe, 
  FolderOpen, 
  Cloud,
  ChevronLeft,
  ChevronRight,
  X,
  Minus,
  Plus,
  Copy,
  CheckCircle
} from 'lucide-react';
import { regulasiData } from '../data/regulasiData';
import type { RegulasiItem } from '../data/regulasiData';
import { 
  isApiConfigured, 
  apiFetch, 
  apiFetchBlob, 
  ApiError, 
  adaptDocumentToDetail 
} from '../lib/api';
import type { 
  DocumentItem, 
  AdaptedRegulasiDoc, 
  DocumentTextResponse 
} from '../lib/api';
import { LoadingState } from '../components/LoadingState';
import { ErrorState } from '../components/ErrorState';

// Garuda Pancasila SVG component
function GarudaEmblem() {
  return (
    <div className="flex justify-center mb-6">
      <svg width="68" height="68" viewBox="0 0 100 100" fill="none" className="text-gray-800">
        <circle cx="50" cy="50" r="46" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 2" />
        <path d="M50 15 L54 28 L68 28 L57 37 L61 50 L50 42 L39 50 L43 37 L32 28 L46 28 Z" fill="currentColor" opacity="0.85" />
        <path d="M30 46 C35 60 65 60 70 46 C66 72 34 72 30 46 Z" fill="currentColor" opacity="0.75" />
        <rect x="42" y="52" width="16" height="18" rx="2" fill="white" stroke="currentColor" strokeWidth="1.5" />
        <path d="M46 61 L54 61 M50 56 L50 66" stroke="currentColor" strokeWidth="1.5" />
        <path d="M25 76 Q50 82 75 76 Q50 86 25 76" fill="currentColor" />
        <text x="50" y="81" fontSize="3.8" textAnchor="middle" fill="white" fontWeight="bold" letterSpacing="0.8">BHINNEKA TUNGGAL IKA</text>
      </svg>
    </div>
  );
}

export default function DetailDokumen() {
  const location = useLocation();
  const navigate = useNavigate();
  const { id } = useParams();

  const stateRegulasi = location.state?.regulasi as (RegulasiItem | AdaptedRegulasiDoc) | undefined;

  // 1. State metadata dokumen
  const [fetchedDoc, setFetchedDoc] = useState<AdaptedRegulasiDoc | null>(null);
  const [loading, setLoading] = useState<boolean>(!stateRegulasi && isApiConfigured && Boolean(id));
  const [notFound, setNotFound] = useState<boolean>(false);
  const [apiError, setApiError] = useState<string | null>(null);

  // 2. State PDF asli (Blob URL, filename, status)
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [pdfFileName, setPdfFileName] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState<boolean>(isApiConfigured && Boolean(id));
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [pdfNotFound, setPdfNotFound] = useState<boolean>(false);
  const pdfBlobUrlRef = useRef<string | null>(null);

  // 3. State teks mentah dokumen
  const [textData, setTextData] = useState<DocumentTextResponse | null>(null);
  const [textLoading, setTextLoading] = useState<boolean>(isApiConfigured && Boolean(id));
  const [textError, setTextError] = useState<string | null>(null);
  const [textNotFound, setTextNotFound] = useState<boolean>(false);
  const [isCopied, setIsCopied] = useState<boolean>(false);

  // Memuat metadata, PDF, dan teks secara terpisah dan paralel saat ID berubah
  useEffect(() => {
    if (!isApiConfigured || !id) {
      setLoading(false);
      setPdfLoading(false);
      setTextLoading(false);
      return;
    }

    const controller = new AbortController();
    const signal = controller.signal;

    // 1. Ambil metadata jika belum ada dari state navigasi
    if (!stateRegulasi) {
      setLoading(true);
      setNotFound(false);
      setApiError(null);

      apiFetch<DocumentItem>(`/api/v1/documents/${id}`, { signal })
        .then((doc) => {
          if (!signal.aborted) {
            setFetchedDoc(adaptDocumentToDetail(doc));
            setLoading(false);
          }
        })
        .catch((err: unknown) => {
          if (signal.aborted) return;
          if (err instanceof DOMException && err.name === 'AbortError') return;
          if (err instanceof Error && err.name === 'AbortError') return;

          if (err instanceof ApiError && err.status === 404) {
            setNotFound(true);
          } else {
            setApiError(err instanceof Error ? err.message : 'Gagal memuat dokumen dari server');
          }
          setLoading(false);
        });
    }

    // 2. Ambil PDF Blob asli
    setPdfLoading(true);
    setPdfError(null);
    setPdfNotFound(false);
    setPdfBlobUrl(null);
    setPdfFileName(null);

    apiFetchBlob(`/api/v1/documents/${id}/pdf`, { signal })
      .then((blob) => {
        if (!signal.aborted) {
          const objectUrl = URL.createObjectURL(blob);
          pdfBlobUrlRef.current = objectUrl;
          setPdfBlobUrl(objectUrl);
          setPdfFileName(blob.filename || null);
          setPdfLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (signal.aborted) return;
        if (err instanceof DOMException && err.name === 'AbortError') return;
        if (err instanceof Error && err.name === 'AbortError') return;

        if (err instanceof ApiError && err.status === 404) {
          setPdfNotFound(true);
          setPdfError('Berkas PDF tidak ditemukan');
        } else {
          setPdfError(err instanceof Error ? err.message : 'Gagal memuat berkas PDF dari server');
        }
        setPdfLoading(false);
      });

    // 3. Ambil teks mentah dokumen
    setTextLoading(true);
    setTextError(null);
    setTextNotFound(false);
    setTextData(null);

    apiFetch<DocumentTextResponse>(`/api/v1/documents/${id}/text`, { signal })
      .then((res) => {
        if (!signal.aborted) {
          if (!res || !res.text || res.text.trim() === '') {
            setTextNotFound(true);
            setTextData(null);
          } else {
            setTextData(res);
          }
          setTextLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (signal.aborted) return;
        if (err instanceof DOMException && err.name === 'AbortError') return;
        if (err instanceof Error && err.name === 'AbortError') return;

        if (err instanceof ApiError && err.status === 404) {
          // Bila backend mengembalikan 404, tampilkan "Teks belum tersedia", bukan galat merah
          setTextNotFound(true);
          setTextError(null);
        } else {
          setTextError(err instanceof Error ? err.message : 'Gagal memuat teks dokumen dari server');
        }
        setTextLoading(false);
      });

    return () => {
      controller.abort();
      if (pdfBlobUrlRef.current) {
        URL.revokeObjectURL(pdfBlobUrlRef.current);
        pdfBlobUrlRef.current = null;
      }
    };
  }, [id, stateRegulasi]);

  // Handler retry terpisah untuk metadata
  const retryFetchMetadata = () => {
    if (!isApiConfigured || !id) return;
    setLoading(true);
    setNotFound(false);
    setApiError(null);

    apiFetch<DocumentItem>(`/api/v1/documents/${id}`)
      .then((doc) => {
        setFetchedDoc(adaptDocumentToDetail(doc));
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setApiError(err instanceof Error ? err.message : 'Gagal memuat dokumen dari server');
        }
        setLoading(false);
      });
  };

  // Handler retry terpisah untuk PDF
  const retryFetchPdf = () => {
    if (!isApiConfigured || !id) return;
    setPdfLoading(true);
    setPdfError(null);
    setPdfNotFound(false);

    apiFetchBlob(`/api/v1/documents/${id}/pdf`)
      .then((blob) => {
        if (pdfBlobUrlRef.current) {
          URL.revokeObjectURL(pdfBlobUrlRef.current);
        }
        const objectUrl = URL.createObjectURL(blob);
        pdfBlobUrlRef.current = objectUrl;
        setPdfBlobUrl(objectUrl);
        setPdfFileName(blob.filename || null);
        setPdfLoading(false);
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) {
          setPdfNotFound(true);
          setPdfError('Berkas PDF tidak ditemukan');
        } else {
          setPdfError(err instanceof Error ? err.message : 'Gagal memuat berkas PDF dari server');
        }
        setPdfLoading(false);
      });
  };

  // Handler retry terpisah untuk Teks
  const retryFetchText = () => {
    if (!isApiConfigured || !id) return;
    setTextLoading(true);
    setTextError(null);
    setTextNotFound(false);

    apiFetch<DocumentTextResponse>(`/api/v1/documents/${id}/text`)
      .then((res) => {
        if (!res || !res.text || res.text.trim() === '') {
          setTextNotFound(true);
          setTextData(null);
        } else {
          setTextData(res);
        }
        setTextLoading(false);
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) {
          setTextNotFound(true);
          setTextError(null);
        } else {
          setTextError(err instanceof Error ? err.message : 'Gagal memuat teks dokumen dari server');
        }
        setTextLoading(false);
      });
  };

  // Handler salin teks mentah
  const handleCopyText = async () => {
    if (!textData?.text) return;
    try {
      await navigator.clipboard.writeText(textData.text);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = textData.text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    }
  };

  // Retrieve regulation from location.state, fetched API, or fallback to mock data by id
  const regulasi = stateRegulasi || fetchedDoc || (
    !isApiConfigured
      ? (regulasiData.find((r) => r.id === Number(id)) || regulasiData[0])
      : null
  );

  const [showViewer, setShowViewer] = useState(false);
  const [zoom, setZoom] = useState(100);
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const totalPages = 6;
  const pageRefs = useRef<(HTMLDivElement | null)[]>([]);

  if (loading) {
    return (
      <div className="max-w-[1200px] mx-auto space-y-6">
        <div className="text-xs text-gray-500">
          Dashboard / Knowledge Base / <span className="font-semibold text-gray-900">Detail</span>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
          <LoadingState message="Memuat detail dokumen dari server..." />
        </div>
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="max-w-[1200px] mx-auto space-y-6">
        <div className="text-xs text-gray-500">
          Dashboard / Knowledge Base / <span className="font-semibold text-gray-900">Detail</span>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
          <h2 className="text-xl font-bold text-gray-900 mb-2">Dokumen tidak ditemukan</h2>
          <p className="text-sm text-gray-500 mb-6">
            Dokumen dengan ID {id} tidak ditemukan di sistem.
          </p>
          <button
            onClick={() => navigate('/knowledge')}
            className="inline-flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors cursor-pointer"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Kembali ke Knowledge Base</span>
          </button>
        </div>
      </div>
    );
  }

  if (apiError) {
    return (
      <div className="max-w-[1200px] mx-auto space-y-6">
        <div className="text-xs text-gray-500">
          Dashboard / Knowledge Base / <span className="font-semibold text-gray-900">Detail</span>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
          <ErrorState
            title="Gagal Memuat Dokumen"
            message={apiError}
            onRetry={retryFetchMetadata}
            retryText="Coba lagi"
          />
        </div>
      </div>
    );
  }

  if (!regulasi) {
    return (
      <div className="max-w-[1200px] mx-auto space-y-6">
        <div className="text-xs text-gray-500">
          Dashboard / Knowledge Base / <span className="font-semibold text-gray-900">Detail</span>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
          <h2 className="text-xl font-bold text-gray-900 mb-2">Dokumen tidak ditemukan</h2>
          <p className="text-sm text-gray-500 mb-6">Data dokumen tidak dapat ditemukan.</p>
          <button
            onClick={() => navigate('/knowledge')}
            className="inline-flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors cursor-pointer"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Kembali ke Knowledge Base</span>
          </button>
        </div>
      </div>
    );
  }

  // Nama file PDF: prioritaskan nama asli dari Content-Disposition backend, fallback ke nomor regulasi yang aman
  const resolvedFileName =
    pdfFileName ||
    `${(regulasi.nomor || 'dokumen').replace(/[/\\:*?"<>|.]/g, '_').trim()}.pdf`;

  const fileName = `${(regulasi.nomor || 'dokumen').replace(/[/.]/g, '_')}.pdf`;
  const pdfUrl = `/documents/${fileName}`;

  // Handler Buka PDF Asli di Tab Baru (WAJIB US-28)
  const handleOpenPdfNewTab = () => {
    if (isApiConfigured) {
      if (pdfBlobUrl) {
        window.open(pdfBlobUrl, '_blank');
      } else {
        apiFetchBlob(`/api/v1/documents/${id}/pdf`)
          .then((blob) => {
            const url = URL.createObjectURL(blob);
            window.open(url, '_blank');
          })
          .catch((err) => {
            alert('Gagal membuka berkas PDF: ' + (err instanceof Error ? err.message : String(err)));
          });
      }
    } else {
      window.open(pdfUrl, '_blank');
    }
  };

  // Handler Unduh Berkas PDF Asli
  const handleDownloadPdf = () => {
    if (isApiConfigured) {
      if (pdfBlobUrl) {
        const link = document.createElement('a');
        link.href = pdfBlobUrl;
        link.download = resolvedFileName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      } else {
        apiFetchBlob(`/api/v1/documents/${id}/pdf`)
          .then((blob) => {
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = blob.filename || resolvedFileName;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            setTimeout(() => URL.revokeObjectURL(url), 10000);
          })
          .catch((err) => {
            alert('Gagal mengunduh berkas PDF: ' + (err instanceof Error ? err.message : String(err)));
          });
      }
    } else {
      const link = document.createElement('a');
      link.href = pdfUrl;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  // Handle zoom
  const handleZoomIn = () => setZoom(prev => Math.min(175, prev + 25));
  const handleZoomOut = () => setZoom(prev => Math.max(75, prev - 25));
  const handleZoomReset = () => setZoom(100);

  // Handle page navigation
  const scrollToPage = (pageNum: number) => {
    const target = pageRefs.current[pageNum - 1];
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setCurrentPage(pageNum);
    }
  };

  const handlePrevPage = () => {
    if (currentPage > 1) {
      scrollToPage(currentPage - 1);
    }
  };

  const handleNextPage = () => {
    if (currentPage < totalPages) {
      scrollToPage(currentPage + 1);
    }
  };

  // Observe scroll to update active page number
  const handleViewerScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const container = e.currentTarget;
    const containerTop = container.scrollTop;
    const containerHeight = container.clientHeight;

    for (let i = 0; i < pageRefs.current.length; i++) {
      const el = pageRefs.current[i];
      if (el) {
        const offsetTop = el.offsetTop - container.offsetTop;
        if (containerTop + containerHeight / 3 >= offsetTop) {
          setCurrentPage(i + 1);
        }
      }
    }
  };

  // Helper to highlight matching text in PDF viewer
  const renderHighlightedText = (text: string) => {
    if (!searchQuery.trim()) return text;
    const regex = new RegExp(`(${searchQuery.trim()})`, 'gi');
    const parts = text.split(regex);
    return parts.map((part, index) => 
      regex.test(part) ? (
        <mark key={index} className="bg-yellow-300 text-gray-900 font-semibold px-0.5 rounded">
          {part}
        </mark>
      ) : part
    );
  };

  // Dynamic source badge and icon
  // Dynamic source badge and icon
  const getSourceDisplay = (sumber: string) => {
    const s = (sumber || '').toLowerCase();
    if (!sumber || s === '-') {
      return {
        label: '-',
        subLabel: '-',
        icon: <Info className="w-3.5 h-3.5 text-gray-500" />,
        badgeClass: 'bg-gray-50 text-gray-700 border-gray-200/60'
      };
    }
    if (s.includes('folder') || s.includes('lokal')) {
      return {
        label: 'Folder Lokal',
        subLabel: 'Folder Lokal Server',
        icon: <FolderOpen className="w-3.5 h-3.5 text-amber-700" />,
        badgeClass: 'bg-amber-50 text-amber-800 border-amber-200/60'
      };
    }
    if (s.includes('onedrive') || s.includes('cloud')) {
      return {
        label: 'OneDrive',
        subLabel: 'OneDrive Cloud Storage',
        icon: <Cloud className="w-3.5 h-3.5 text-sky-700" />,
        badgeClass: 'bg-sky-50 text-sky-800 border-sky-200/60'
      };
    }
    if (s.includes('scraping') || s.startsWith('http')) {
      return {
        label: s.startsWith('http') ? 'Situs Web' : 'Scraping Otomatis',
        subLabel: s.startsWith('http') ? sumber : 'Scraping Portal OJK',
        icon: <Globe className="w-3.5 h-3.5 text-blue-700" />,
        badgeClass: 'bg-blue-50 text-blue-800 border-blue-200/60'
      };
    }
    if (s.includes('upload') || s.includes('manual')) {
      return {
        label: 'Upload Manual',
        subLabel: 'Upload Manual Pengguna',
        icon: <Info className="w-3.5 h-3.5 text-red-700" />,
        badgeClass: 'bg-red-50 text-red-800 border-red-200/60'
      };
    }
    return {
      label: sumber,
      subLabel: sumber,
      icon: <Info className="w-3.5 h-3.5 text-gray-600" />,
      badgeClass: 'bg-gray-50 text-gray-700 border-gray-200/60'
    };
  };

  const sourceInfo = getSourceDisplay(regulasi.sumber);
  const statusColor = regulasi.status === 'Aktif' ? '#15803d' : regulasi.status === 'Diubah' ? '#b45309' : '#b91c1c';
  const statusBadge = regulasi.status === 'Aktif' 
    ? 'bg-green-50 text-green-700 border-green-200/60' 
    : regulasi.status === 'Diubah' 
    ? 'bg-amber-50 text-amber-700 border-amber-200/60' 
    : 'bg-red-50 text-red-700 border-red-200/60';

  const displayTanggalPublikasi = ('tanggalPublikasi' in regulasi && regulasi.tanggalPublikasi)
    ? regulasi.tanggalPublikasi
    : regulasi.tahun === '-'
    ? '-'
    : typeof regulasi.tahun === 'number'
    ? `12 ${regulasi.tahun === 2024 ? 'Maret' : 'Oktober'} ${regulasi.tahun}`
    : regulasi.tahun;

  const displayUkuran = ('ukuran' in regulasi && regulasi.ukuran && regulasi.ukuran !== '-')
    ? regulasi.ukuran
    : ('ukuran' in regulasi && regulasi.ukuran === '-' ? '-' : '2.4 MB');



  return (
    <>
      {/* ======================================================== */}
      {/* PDF VIEWER OVERLAY */}
      {/* ======================================================== */}
      {showViewer && (
        <div className="fixed inset-0 z-50 bg-[#383d41] flex flex-col font-sans animate-in fade-in duration-150">
          {/* Top Primary Toolbar */}
          <div className="bg-[#242729] text-white border-b border-gray-700 h-14 flex items-center justify-between px-4 shrink-0 shadow-md relative z-20">
            {/* Left: Back button & Document title */}
            <div className="flex items-center gap-3">
              <button 
                onClick={() => setShowViewer(false)}
                className="flex items-center gap-2 text-gray-200 hover:text-white hover:bg-white/10 px-3 py-1.5 rounded-lg transition-colors text-xs font-semibold cursor-pointer"
              >
                <ArrowLeft className="w-4 h-4" />
                Kembali ke Detail
              </button>
              <div className="h-4 w-px bg-gray-600 hidden sm:block"></div>
              <div className="hidden sm:flex items-center gap-2 text-xs font-semibold text-gray-200">
                <span className="px-1.5 py-0.5 rounded bg-red-600/80 text-[10px] font-bold tracking-wider uppercase text-white">PDF</span>
                <span className="truncate max-w-[280px] md:max-w-md">{resolvedFileName}</span>
              </div>
            </div>

            {/* Center: Controls (Zoom, Page Navigation) - Hanya di mode contoh */}
            {!isApiConfigured && (
              <div className="flex items-center gap-3">
                {/* Zoom Controls */}
                <div className="flex items-center bg-[#1e2022] rounded-lg p-0.5 border border-gray-700">
                  <button 
                    onClick={handleZoomOut} 
                    disabled={zoom <= 75}
                    className="p-1.5 text-gray-300 hover:text-white hover:bg-white/10 rounded transition-colors disabled:opacity-30 cursor-pointer" 
                    title="Perkecil (-25%)"
                  >
                    <Minus className="w-3.5 h-3.5" />
                  </button>
                  <button 
                    onClick={handleZoomReset} 
                    className="text-xs font-bold w-12 text-center text-gray-200 hover:text-white px-1 py-1 rounded transition-colors hover:bg-white/10 cursor-pointer"
                    title="Reset 100%"
                  >
                    {zoom}%
                  </button>
                  <button 
                    onClick={handleZoomIn} 
                    disabled={zoom >= 175}
                    className="p-1.5 text-gray-300 hover:text-white hover:bg-white/10 rounded transition-colors disabled:opacity-30 cursor-pointer" 
                    title="Perbesar (+25%)"
                  >
                    <Plus className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Page Navigation */}
                <div className="flex items-center bg-[#1e2022] rounded-lg p-0.5 border border-gray-700 text-xs text-gray-300">
                  <button 
                    onClick={handlePrevPage} 
                    disabled={currentPage <= 1}
                    className="p-1.5 text-gray-300 hover:text-white hover:bg-white/10 rounded transition-colors disabled:opacity-30 cursor-pointer" 
                    title="Halaman Sebelumnya"
                  >
                    <ChevronLeft className="w-3.5 h-3.5" />
                  </button>
                  <span className="px-2 font-medium text-gray-200 whitespace-nowrap">
                    Halaman <span className="font-bold text-white">{currentPage}</span> / {totalPages}
                  </span>
                  <button 
                    onClick={handleNextPage} 
                    disabled={currentPage >= totalPages}
                    className="p-1.5 text-gray-300 hover:text-white hover:bg-white/10 rounded transition-colors disabled:opacity-30 cursor-pointer" 
                    title="Halaman Selanjutnya"
                  >
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}

            {/* Right: Search, Buka di Tab Baru, Download, Close */}
            <div className="flex items-center gap-2">
              {!isApiConfigured && (
                <div className="relative hidden md:block">
                  <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-2.5" />
                  <input 
                    type="text" 
                    placeholder="Cari kata kunci (cth: Pasal 23)..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="bg-[#1e2022] border border-gray-700 text-white placeholder-gray-400 pl-8 pr-3 py-1.5 rounded-lg text-xs w-48 lg:w-56 focus:outline-none focus:border-red-500 transition-colors"
                  />
                  {searchQuery && (
                    <button 
                      onClick={() => setSearchQuery('')}
                      className="absolute right-2 top-2 text-gray-400 hover:text-white"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </div>
              )}

              {/* Buka PDF Asli di Tab Baru */}
              <button
                onClick={handleOpenPdfNewTab}
                disabled={isApiConfigured && (pdfNotFound || (!pdfBlobUrl && pdfLoading))}
                className="flex items-center gap-1.5 bg-gray-700 hover:bg-gray-600 text-white px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors disabled:opacity-40 cursor-pointer"
                title="Buka PDF Asli di Tab Baru"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Buka di Tab Baru</span>
              </button>

              {/* Download Button */}
              <button 
                onClick={handleDownloadPdf}
                disabled={isApiConfigured && (pdfNotFound || (!pdfBlobUrl && pdfLoading))}
                className="flex items-center gap-1.5 bg-[#B91C1C] hover:bg-[#a01818] text-white px-3 py-1.5 rounded-lg text-xs font-semibold shadow-sm transition-colors disabled:opacity-40 cursor-pointer"
                title="Download Dokumen PDF Asli"
              >
                <Download className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Unduh</span>
              </button>

              {/* Close Button */}
              <button 
                onClick={() => setShowViewer(false)}
                className="p-1.5 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors ml-1 cursor-pointer"
                title="Tutup Viewer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Mode API: Viewer PDF asli dalam <iframe> */}
          {isApiConfigured ? (
            <div className="flex-1 w-full h-[calc(100vh-3.5rem)] bg-[#525659] flex items-center justify-center overflow-hidden">
              {pdfLoading ? (
                <div className="bg-[#242729] p-8 rounded-xl border border-gray-700 text-white">
                  <LoadingState message="Memuat berkas PDF asli dari server..." />
                </div>
              ) : pdfNotFound ? (
                <div className="bg-[#242729] p-10 rounded-xl border border-gray-700 text-center max-w-md mx-4">
                  <FileText className="w-12 h-12 text-amber-500 mx-auto mb-3" />
                  <h3 className="text-base font-bold text-white mb-1">Berkas PDF tidak ditemukan</h3>
                  <p className="text-xs text-gray-400 mb-6">
                    Peladen tidak menemukan berkas fisik PDF untuk dokumen ini (HTTP 404).
                  </p>
                  <button
                    onClick={() => setShowViewer(false)}
                    className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer"
                  >
                    Kembali ke Detail
                  </button>
                </div>
              ) : pdfError ? (
                <div className="bg-[#242729] p-8 rounded-xl border border-gray-700 max-w-md mx-4">
                  <ErrorState
                    title="Gagal Memuat PDF"
                    message={pdfError}
                    onRetry={retryFetchPdf}
                    retryText="Coba lagi"
                  />
                </div>
              ) : pdfBlobUrl ? (
                <iframe
                  src={pdfBlobUrl}
                  className="w-full h-full border-0 bg-white"
                  title={`PDF Asli - ${resolvedFileName}`}
                />
              ) : null}
            </div>
          ) : (
            <>
              {/* Sub-toolbar notice when searching */}
              {searchQuery && (
                <div className="bg-[#1b1d1e] text-xs text-amber-300 px-6 py-1.5 flex items-center justify-between border-b border-gray-800">
                  <div className="flex items-center gap-2">
                    <Search className="w-3.5 h-3.5 text-amber-400" />
                    <span>Menampilkan hasil pencarian untuk: <strong>"{searchQuery}"</strong></span>
                  </div>
                  <button 
                    onClick={() => setSearchQuery('')}
                    className="text-gray-400 hover:text-white underline text-[11px]"
                  >
                    Reset pencarian
                  </button>
                </div>
              )}

              {/* PDF Pages Scroll Area */}
              <div 
                onScroll={handleViewerScroll}
                className="flex-1 overflow-y-auto overflow-x-auto p-4 sm:p-8 flex flex-col items-center gap-8 bg-[#494e52]"
              >
            {/* Dynamic Scaled Container */}
            <div 
              className="flex flex-col items-center gap-8 transition-transform duration-200 ease-out origin-top"
              style={{ transform: `scale(${zoom / 100})` }}
            >
              {/* ======================================================== */}
              {/* PAGE 1: SALINAN & JUDUL RESMI */}
              {/* ======================================================== */}
              <div 
                ref={el => { pageRefs.current[0] = el; }}
                className="bg-white text-gray-900 shadow-2xl rounded-sm w-[780px] min-h-[1100px] p-16 sm:p-20 flex flex-col justify-between ring-1 ring-black/10 select-text"
              >
                <div>
                  <GarudaEmblem />
                  <div className="text-center space-y-1 mb-8">
                    <h3 className="text-sm font-bold tracking-widest uppercase">OTORITAS JASA KEUANGAN</h3>
                    <h4 className="text-xs font-semibold tracking-wider uppercase text-gray-600">REPUBLIK INDONESIA</h4>
                    <p className="text-[11px] font-mono tracking-widest text-gray-400 uppercase pt-2">SALINAN</p>
                  </div>

                  <div className="text-center space-y-2 mb-8 border-b-2 border-gray-900 pb-6">
                    <h2 className="text-sm font-bold tracking-wide uppercase leading-snug">
                      {renderHighlightedText(`PERATURAN OTORITAS JASA KEUANGAN REPUBLIK INDONESIA`)}
                    </h2>
                    <p className="text-xs font-bold tracking-wider text-gray-800">
                      {renderHighlightedText(`NOMOR 11/POJK.03/2024`)}
                    </p>
                    <p className="text-xs font-semibold uppercase text-gray-600 pt-1">TENTANG</p>
                    <h1 className="text-sm font-extrabold uppercase leading-relaxed max-w-xl mx-auto text-gray-900">
                      {renderHighlightedText(regulasi.judul)}
                    </h1>
                  </div>

                  <div className="text-center font-bold text-xs uppercase tracking-wider mb-6">
                    DENGAN RAHMAT TUHAN YANG MAHA ESA<br />
                    DEWAN KOMISIONER OTORITAS JASA KEUANGAN,
                  </div>

                  <div className="space-y-4 text-xs leading-relaxed text-justify">
                    <div className="flex gap-4 items-start">
                      <span className="font-bold shrink-0 w-20">Menimbang:</span>
                      <div className="space-y-2">
                        <p>{renderHighlightedText('a. bahwa perkembangan teknologi informasi yang pesat di sektor jasa keuangan perbankan meningkatkan efisiensi operasional dan kualitas layanan nasabah, namun di sisi lain meningkatkan kompleksitas ancaman dan eksposur risiko ketahanan siber;')}</p>
                        <p>{renderHighlightedText('b. bahwa untuk menjaga stabilitas sistem perbankan nasional, melindungi kerahasiaan data nasabah, dan mencegah gangguan operasional akibat insiden siber, diperlukan tata kelola yang tangguh dan teruji;')}</p>
                        <p>{renderHighlightedText('c. bahwa berdasarkan pertimbangan sebagaimana dimaksud dalam huruf a dan huruf b, perlu menetapkan Peraturan Otoritas Jasa Keuangan tentang Penerapan Tata Kelola dan Ketahanan Siber;')}</p>
                      </div>
                    </div>

                    <div className="flex gap-4 items-start pt-2">
                      <span className="font-bold shrink-0 w-20">Mengingat:</span>
                      <div className="space-y-1.5">
                        <p>{renderHighlightedText('1. Undang-Undang Nomor 21 Tahun 2011 tentang Otoritas Jasa Keuangan;')}</p>
                        <p>{renderHighlightedText('2. Undang-Undang Nomor 4 Tahun 2023 tentang Pengembangan dan Penguatan Sektor Keuangan;')}</p>
                        <p>{renderHighlightedText('3. Undang-Undang Nomor 27 Tahun 2022 tentang Pelindungan Data Pribadi;')}</p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="pt-8 border-t border-gray-100 flex justify-between items-center text-[10px] text-gray-400 font-mono">
                  <span>JDIH OJK — Dokumen Regulasi HERO</span>
                  <span>Halaman 1 dari {totalPages}</span>
                </div>
              </div>

              {/* ======================================================== */}
              {/* PAGE 2: BAB I KETENTUAN UMUM */}
              {/* ======================================================== */}
              <div 
                ref={el => { pageRefs.current[1] = el; }}
                className="bg-white text-gray-900 shadow-2xl rounded-sm w-[780px] min-h-[1100px] p-16 sm:p-20 flex flex-col justify-between ring-1 ring-black/10 select-text"
              >
                <div>
                  <div className="text-center space-y-1 mb-8 border-b border-gray-200 pb-4">
                    <p className="text-[11px] font-mono tracking-widest text-gray-400 uppercase">SALINAN RESMI</p>
                    <h3 className="text-xs font-bold uppercase tracking-wider text-gray-800">MEMUTUSKAN:</h3>
                    <p className="text-xs text-gray-600 font-medium">Menetapkan: PERATURAN OTORITAS JASA KEUANGAN TENTANG KETAHANAN DAN KEAMANAN SIBER BAGI BANK UMUM.</p>
                  </div>

                  <div className="text-center font-bold text-xs uppercase tracking-wider mb-6">
                    BAB I<br />KETENTUAN UMUM
                  </div>

                  <div className="text-center font-bold text-xs mb-4">Pasal 1</div>
                  <div className="space-y-3 text-xs leading-relaxed text-justify">
                    <p className="font-semibold text-gray-700">Dalam Peraturan Otoritas Jasa Keuangan ini yang dimaksud dengan:</p>
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">1.</span>
                      <span>{renderHighlightedText('Bank adalah Bank Umum sebagaimana dimaksud dalam Undang-Undang tentang Perbankan, termasuk kantor cabang dari bank yang berkedudukan di luar negeri.')}</span>
                    </p>
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">2.</span>
                      <span>{renderHighlightedText('Teknologi Informasi adalah serangkaian perangkat keras, perangkat lunak, sistem jaringan, dan infrastruktur komunikasi data yang digunakan untuk memproses, menyimpan, dan mentransmisikan data perbankan.')}</span>
                    </p>
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">3.</span>
                      <span>{renderHighlightedText('Ketahanan Siber (Cyber Resilience) adalah kemampuan Bank untuk mengantisipasi, menahan, pulih kembali, dan beradaptasi dari gangguan, serangan, atau kondisi yang merugikan pada sistem teknologi informasi.')}</span>
                    </p>
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">4.</span>
                      <span>{renderHighlightedText('Insiden Siber adalah peristiwa atau kejadian keamanan informasi yang mengindikasikan adanya pelanggaran kebijakan keamanan siber, kegagalan perlindungan data, atau gangguan integritas sistem.')}</span>
                    </p>
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">5.</span>
                      <span>{renderHighlightedText('Manajemen Risiko Teknologi Informasi adalah serangkaian metodologi terstruktur untuk mengidentifikasi, mengukur, memantau, dan mengendalikan risiko yang timbul dari penggunaan TI.')}</span>
                    </p>
                  </div>

                  <div className="text-center font-bold text-xs mt-8 mb-4">Pasal 2</div>
                  <div className="space-y-3 text-xs leading-relaxed text-justify">
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(1)</span>
                      <span>{renderHighlightedText('Bank wajib menerapkan tata kelola teknologi informasi dan manajemen risiko siber secara komprehensif, efektif, dan proporsional dengan skala bisnis bank.')}</span>
                    </p>
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(2)</span>
                      <span>{renderHighlightedText('Penerapan tata kelola sebagaimana dimaksud pada ayat (1) mencakup pengawasan aktif Direksi dan Dewan Komisaris, kecukupan kebijakan prosedur, serta audit independen.')}</span>
                    </p>
                  </div>
                </div>

                <div className="pt-8 border-t border-gray-100 flex justify-between items-center text-[10px] text-gray-400 font-mono">
                  <span>JDIH OJK — Dokumen Regulasi HERO</span>
                  <span>Halaman 2 dari {totalPages}</span>
                </div>
              </div>

              {/* ======================================================== */}
              {/* PAGE 3: BAB II TATA KELOLA & DIREKSI */}
              {/* ======================================================== */}
              <div 
                ref={el => { pageRefs.current[2] = el; }}
                className="bg-white text-gray-900 shadow-2xl rounded-sm w-[780px] min-h-[1100px] p-16 sm:p-20 flex flex-col justify-between ring-1 ring-black/10 select-text"
              >
                <div>
                  <div className="text-center font-bold text-xs uppercase tracking-wider mb-6">
                    BAB II<br />TATA KELOLA DAN TANGGUNG JAWAB DIREKSI
                  </div>

                  <div className="text-center font-bold text-xs mb-4">Pasal 5</div>
                  <div className="space-y-3 text-xs leading-relaxed text-justify">
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(1)</span>
                      <span>{renderHighlightedText('Direksi bertanggung jawab penuh atas pelaksanaan kebijakan keamanan informasi dan ketahanan siber Bank.')}</span>
                    </p>
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(2)</span>
                      <span>{renderHighlightedText('Bank wajib membentuk Komite Pengarah Teknologi Informasi (IT Steering Committee) yang beranggotakan sekurang-kurangnya Direktur Utama dan Direktur yang membawahkan bidang TI.')}</span>
                    </p>
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(3)</span>
                      <span>{renderHighlightedText('Komite Pengarah TI sebagaimana dimaksud pada ayat (2) wajib melakukan evaluasi berkala terhadap efektivitas mitigasi risiko siber minimal 1 (satu) kali dalam 3 (tiga) bulan.')}</span>
                    </p>
                  </div>

                  <div className="text-center font-bold text-xs mt-8 mb-4">Pasal 8</div>
                  <div className="space-y-3 text-xs leading-relaxed text-justify">
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(1)</span>
                      <span>{renderHighlightedText('Bank wajib menunjuk pejabat eksekutif satu tingkat di bawah Direksi yang menjabat sebagai Chief Information Security Officer (CISO) atau penanggung jawab keamanan siber.')}</span>
                    </p>
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(2)</span>
                      <span>{renderHighlightedText('Pejabat CISO sebagaimana dimaksud pada ayat (1) wajib memiliki sertifikasi kompetensi di bidang keamanan informasi yang diakui secara nasional maupun internasional.')}</span>
                    </p>
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(3)</span>
                      <span>{renderHighlightedText('CISO beroperasi secara independen dari fungsi operasional teknologi informasi dan memiliki jalur pelaporan langsung kepada Direktur Utama.')}</span>
                    </p>
                  </div>
                </div>

                <div className="pt-8 border-t border-gray-100 flex justify-between items-center text-[10px] text-gray-400 font-mono">
                  <span>JDIH OJK — Dokumen Regulasi HERO</span>
                  <span>Halaman 3 dari {totalPages}</span>
                </div>
              </div>

              {/* ======================================================== */}
              {/* PAGE 4: BAB III MANAJEMEN RISIKO & PENGAMANAN SIBER */}
              {/* ======================================================== */}
              <div 
                ref={el => { pageRefs.current[3] = el; }}
                className="bg-white text-gray-900 shadow-2xl rounded-sm w-[780px] min-h-[1100px] p-16 sm:p-20 flex flex-col justify-between ring-1 ring-black/10 select-text"
              >
                <div>
                  <div className="text-center font-bold text-xs uppercase tracking-wider mb-6">
                    BAB III<br />MANAJEMEN RISIKO DAN PENGAMANAN SIBER
                  </div>

                  <div className="text-center font-bold text-xs mb-4">Pasal 15</div>
                  <div className="space-y-3 text-xs leading-relaxed text-justify">
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(1)</span>
                      <span>{renderHighlightedText('Bank wajib melakukan pengujian kerentanan (Vulnerability Assessment) secara berkala minimal 1 (satu) kali setiap 6 (enam) bulan terhadap seluruh aset kritis.')}</span>
                    </p>
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(2)</span>
                      <span>{renderHighlightedText('Uji penetrasi (Penetration Testing) wajib dilakukan oleh pihak ketiga independen minimal 1 (satu) kali dalam 1 (satu) tahun kalender.')}</span>
                    </p>
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(3)</span>
                      <span>{renderHighlightedText('Hasil uji penetrasi dan rencana tindak lanjut perbaikan wajib disampaikan kepada Otoritas Jasa Keuangan.')}</span>
                    </p>
                  </div>

                  <div className="text-center font-bold text-xs mt-8 mb-4">Pasal 18</div>
                  <div className="space-y-3 text-xs leading-relaxed text-justify">
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(1)</span>
                      <span>{renderHighlightedText('Bank wajib menerapkan enkripsi yang kuat (strong encryption) terhadap data sensitif nasabah, baik saat data transit (data-in-transit) maupun saat data tersimpan (data-at-rest).')}</span>
                    </p>
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(2)</span>
                      <span>{renderHighlightedText('Standar algoritma kriptografi yang digunakan harus memenuhi standar keamanan internasional yang belum terpecahkan.')}</span>
                    </p>
                  </div>
                </div>

                <div className="pt-8 border-t border-gray-100 flex justify-between items-center text-[10px] text-gray-400 font-mono">
                  <span>JDIH OJK — Dokumen Regulasi HERO</span>
                  <span>Halaman 4 dari {totalPages}</span>
                </div>
              </div>

              {/* ======================================================== */}
              {/* PAGE 5: BAB IV PASAL 23 - KETENTUAN UTAMA KROSS-CEK HERO */}
              {/* ======================================================== */}
              <div 
                ref={el => { pageRefs.current[4] = el; }}
                className="bg-white text-gray-900 shadow-2xl rounded-sm w-[780px] min-h-[1100px] p-16 sm:p-20 flex flex-col justify-between ring-2 ring-red-600/30 select-text"
              >
                <div>
                  <div className="text-center font-bold text-xs uppercase tracking-wider mb-6">
                    BAB IV<br />TANGGAP DARURAT DAN PENANGANAN INSIDEN SIBER
                  </div>

                  {/* Highlighted Pasal 23 */}
                  <div className="bg-red-50/50 p-4 rounded-lg border border-red-200/80 mb-6">
                    <div className="text-center font-bold text-sm text-red-900 mb-4">
                      {renderHighlightedText('Pasal 23')}
                    </div>
                    <div className="space-y-3.5 text-xs leading-relaxed text-justify text-gray-900">
                      <p className="flex gap-3">
                        <span className="font-bold shrink-0 text-red-800">(1)</span>
                        <span>{renderHighlightedText('Bank wajib memiliki dan menerapkan rencana aksi pemulihan insiden siber yang efektif dan teruji untuk meminimalkan dampak gangguan operasional.')}</span>
                      </p>
                      <p className="flex gap-3">
                        <span className="font-bold shrink-0 text-red-800">(2)</span>
                        <span>{renderHighlightedText('Pelaksanaan ketentuan sebagaimana dimaksud pada ayat (1) harus dilaporkan kepada Otoritas Jasa Keuangan secara berkala paling lambat akhir bulan berikutnya setelah triwulan berakhir.')}</span>
                      </p>
                      <p className="flex gap-3">
                        <span className="font-bold shrink-0 text-red-800">(3)</span>
                        <span>{renderHighlightedText('Dalam hal terjadi insiden siber yang berdampak signifikan, Bank wajib melaporkan insiden tersebut kepada Otoritas Jasa Keuangan dalam waktu 1x24 jam sejak insiden terdeteksi.')}</span>
                      </p>
                    </div>
                  </div>

                  <div className="text-center font-bold text-xs mt-6 mb-4">Pasal 24</div>
                  <div className="space-y-3 text-xs leading-relaxed text-justify">
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(1)</span>
                      <span>{renderHighlightedText('Bank wajib membentuk Computer Security Incident Response Team (CSIRT) internal atau bekerja sama dengan penyedia layanan CSIRT terakreditasi.')}</span>
                    </p>
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(2)</span>
                      <span>{renderHighlightedText('CSIRT Bank wajib berkoordinasi secara aktif dengan Otoritas Jasa Keuangan CSIRT (OJK-CSIRT) dalam hal pertukaran informasi ancaman siber (threat intelligence).')}</span>
                    </p>
                  </div>
                </div>

                <div className="pt-8 border-t border-gray-100 flex justify-between items-center text-[10px] text-gray-400 font-mono">
                  <span className="text-red-700 font-semibold">Pasal 23 — Verifikasi Regulasi HERO</span>
                  <span>Halaman 5 dari {totalPages}</span>
                </div>
              </div>

              {/* ======================================================== */}
              {/* PAGE 6: BAB V SANKSI & PENUTUP */}
              {/* ======================================================== */}
              <div 
                ref={el => { pageRefs.current[5] = el; }}
                className="bg-white text-gray-900 shadow-2xl rounded-sm w-[780px] min-h-[1100px] p-16 sm:p-20 flex flex-col justify-between ring-1 ring-black/10 select-text"
              >
                <div>
                  <div className="text-center font-bold text-xs uppercase tracking-wider mb-6">
                    BAB V<br />SANKSI ADMINISTRATIF DAN PENUTUP
                  </div>

                  <div className="text-center font-bold text-xs mb-4">Pasal 30</div>
                  <div className="space-y-3 text-xs leading-relaxed text-justify">
                    <p className="flex gap-3">
                      <span className="font-bold shrink-0">(1)</span>
                      <span>{renderHighlightedText('Bank yang melanggar ketentuan dalam Peraturan Otoritas Jasa Keuangan ini dikenai sanksi administratif berupa:')}</span>
                    </p>
                    <div className="pl-6 space-y-1">
                      <p>{renderHighlightedText('a. teguran tertulis;')}</p>
                      <p>{renderHighlightedText('b. denda finansial sesuai skala pelanggaran;')}</p>
                      <p>{renderHighlightedText('c. penurunan tingkat kesehatan Bank; atau')}</p>
                      <p>{renderHighlightedText('d. pembekuan kegiatan usaha perbankan tertentu.')}</p>
                    </div>
                  </div>

                  <div className="text-center font-bold text-xs mt-8 mb-4">Pasal 31</div>
                  <div className="space-y-3 text-xs leading-relaxed text-justify mb-12">
                    <p>{renderHighlightedText('Peraturan Otoritas Jasa Keuangan ini mulai berlaku pada tanggal diundangkan.')}</p>
                    <p>{renderHighlightedText('Agar setiap orang mengetahuinya, memerintahkan pengundangan Peraturan Otoritas Jasa Keuangan ini dengan penempatannya dalam Lembaran Negara Republik Indonesia.')}</p>
                  </div>

                  {/* Tanda Tangan Resmi */}
                  <div className="flex justify-end pt-4">
                    <div className="text-center w-72 space-y-1">
                      <p className="text-xs">Ditetapkan di Jakarta</p>
                      <p className="text-xs">pada tanggal 12 Maret 2024</p>
                      <p className="text-xs font-bold pt-2 uppercase">DEWAN KOMISIONER</p>
                      <p className="text-xs font-bold uppercase">OTORITAS JASA KEUANGAN,</p>
                      <p className="text-xs font-bold uppercase pb-16">KETUA,</p>
                      <div className="border-b border-gray-900 w-48 mx-auto"></div>
                      <p className="text-xs font-bold pt-1 uppercase">MAHENDRA SIREGAR</p>
                    </div>
                  </div>
                </div>

                <div className="pt-8 border-t border-gray-100 flex justify-between items-center text-[10px] text-gray-400 font-mono">
                  <span>JDIH OJK — Dokumen Regulasi HERO</span>
                  <span>Halaman 6 dari {totalPages}</span>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )}

      {/* ======================================================== */}
      {/* MAIN DETAIL DOKUMEN PAGE */}
      {/* ======================================================== */}
      <div className="max-w-[1200px] mx-auto space-y-6 pb-12 font-sans animate-in fade-in duration-200">
        {/* Breadcrumb and Back Button */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="text-xs text-gray-500 font-medium flex items-center gap-1.5 flex-wrap">
            <span>Dashboard</span>
            <span className="text-gray-300">/</span>
            <button 
              onClick={() => navigate('/knowledge')} 
              className="hover:text-red-700 hover:underline transition-colors font-medium text-gray-600"
            >
              Knowledge Base
            </button> 
            <span className="text-gray-300">/</span> 
            <span className="font-semibold text-gray-900">Detail Dokumen</span>
          </div>
          
          <button 
            onClick={() => navigate('/knowledge')} 
            className="flex items-center gap-1.5 text-gray-600 hover:text-red-700 font-semibold transition-colors text-xs group self-start sm:self-auto"
          >
            <ArrowLeft className="w-3.5 h-3.5 group-hover:-translate-x-1 transition-transform" />
            Kembali ke Knowledge Base
          </button>
        </div>

        {/* 1. Header Card (Nomor, Status, Judul, Metadata Singkat) */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-6 sm:p-7 space-y-3.5">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-extrabold text-gray-900 tracking-tight leading-none">
              {regulasi.nomor}
            </h1>
            <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border ${statusBadge}`}>
              <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: statusColor }}></span>
              {regulasi.status}
            </span>
          </div>

          <h2 className="text-base sm:text-lg text-gray-700 font-medium leading-relaxed">
            {regulasi.judul}
          </h2>

          <div className="flex items-center gap-2.5 text-xs text-gray-500 pt-1 flex-wrap font-medium">
            <span>{regulasi.nomor}</span>
            <span className="text-gray-300">•</span>
            <span>{displayTanggalPublikasi}</span>
            <span className="text-gray-300">•</span>
            <span className="font-semibold text-gray-700">{regulasi.kategori}</span>
            <span className="text-gray-300">•</span>
            <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[11px] font-semibold border ${sourceInfo.badgeClass}`}>
              {sourceInfo.icon}
              {sourceInfo.subLabel}
            </span>
          </div>
        </div>

        {/* 2. Informasi Dokumen (Structured Grid) */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-6 sm:p-7">
          <div className="flex items-center gap-2.5 mb-6 pb-4 border-b border-gray-100">
            <div className="p-1.5 bg-red-50 text-red-700 rounded-lg">
              <Info className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-gray-900 text-base">Informasi Dokumen</h3>
              <p className="text-xs text-gray-500 mt-0.5">Metadata lengkap regulasi yang terindeks di sistem HERO.</p>
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-y-7 gap-x-8">
            {/* Nomor Regulasi */}
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Nomor Regulasi</span>
              <p className="text-sm font-bold text-gray-900">{regulasi.nomor}</p>
            </div>

            {/* Metode Ingest / Sumber (Dynamic) */}
            <div className="flex flex-col gap-1.5 items-start">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Metode Ingest / Sumber</span>
              <div className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold border ${sourceInfo.badgeClass}`}>
                {sourceInfo.icon}
                <span>{sourceInfo.label}</span>
              </div>
            </div>

            {/* Status Keberlakuan */}
            <div className="flex flex-col gap-1.5 items-start">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Status Keberlakuan</span>
              <div className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border ${statusBadge}`}>
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: statusColor }}></span>
                <span>Berlaku Penuh ({regulasi.status})</span>
              </div>
            </div>

            {/* Jenis Regulasi */}
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Jenis Regulasi</span>
              <p className="text-sm font-medium text-gray-900">
                {regulasi.jenis === 'POJK' ? 'Peraturan Otoritas Jasa Keuangan (POJK)' : 
                 regulasi.jenis === 'SEOJK' ? 'Surat Edaran Otoritas Jasa Keuangan (SEOJK)' : 
                 regulasi.jenis === 'PDK' ? 'Peraturan Dewan Komisioner (PDK)' : regulasi.jenis}
              </p>
            </div>

            {/* Tanggal Publikasi */}
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Tanggal Publikasi</span>
              <p className="text-sm font-medium text-gray-900">{displayTanggalPublikasi}</p>
            </div>

            {/* Kategori Industri */}
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Kategori Industri</span>
              <div className="flex items-center gap-1.5 text-sm font-medium text-gray-900">
                <Landmark className="w-4 h-4 text-red-700 shrink-0" />
                <span>{regulasi.kategori}</span>
              </div>
            </div>
          </div>
        </div>

        {/* 3. Dokumen Asli (Buka Dokumen, Buka PDF Asli, & Unduh) */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-6 sm:p-7">
          <div className="flex items-center gap-2.5 mb-5 pb-4 border-b border-gray-100">
            <div className="p-1.5 bg-red-50 text-red-700 rounded-lg">
              <Paperclip className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-gray-900 text-base">Dokumen Asli</h3>
              <p className="text-xs text-gray-500 mt-0.5">Buka berkas PDF asli di browser atau unduh ke perangkat lokal.</p>
            </div>
          </div>
          
          <div className="bg-gray-50/80 rounded-xl p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 border border-gray-200">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-red-100 text-red-700 rounded-xl shrink-0">
                <FileText className="w-6 h-6" />
              </div>
              <div>
                <h4 className="font-bold text-gray-900 text-sm mb-1">{resolvedFileName}</h4>
                <p className="text-xs text-gray-500 font-medium flex items-center gap-2 flex-wrap">
                  <span>PDF Resmi OJK • {displayUkuran}</span>
                  {regulasi.sha256 && (
                    <span className="text-gray-400 font-mono text-[11px]">• SHA-256: {regulasi.sha256}</span>
                  )}
                  {isApiConfigured && pdfNotFound && (
                    <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-800 text-[11px] font-semibold border border-amber-200">
                      Berkas PDF tidak ditemukan
                    </span>
                  )}
                </p>
              </div>
            </div>
            
            <div className="flex items-center gap-2 sm:gap-3 shrink-0 flex-wrap">
              {/* Jika terjadi galat jaringan pada PDF di mode API */}
              {isApiConfigured && pdfError && !pdfNotFound ? (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-red-600 font-medium">Gagal memuat PDF</span>
                  <button
                    onClick={retryFetchPdf}
                    className="px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-700 text-xs font-semibold rounded-lg border border-red-200 transition-colors cursor-pointer"
                  >
                    Coba lagi
                  </button>
                </div>
              ) : (
                <>
                  {/* Tombol Lihat PDF / Buka Dokumen -> Buka Viewer Overlay */}
                  <button 
                    onClick={() => setShowViewer(true)}
                    disabled={isApiConfigured && pdfNotFound}
                    className={`flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg text-xs font-bold shadow-sm transition-colors cursor-pointer ${
                      isApiConfigured && pdfNotFound
                        ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                        : 'bg-[#B91C1C] hover:bg-[#a01818] text-white'
                    }`}
                    title="Lihat dokumen PDF di viewer"
                  >
                    <FileText className="w-4 h-4" />
                    <span>Lihat PDF</span>
                  </button>

                  {/* Tombol Buka PDF Asli -> Buka di tab baru (WAJIB US-28) */}
                  <button
                    onClick={handleOpenPdfNewTab}
                    disabled={isApiConfigured && (pdfNotFound || (!pdfBlobUrl && pdfLoading))}
                    className={`flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg text-xs font-bold shadow-sm border transition-colors cursor-pointer ${
                      isApiConfigured && (pdfNotFound || (!pdfBlobUrl && pdfLoading))
                        ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
                        : 'bg-white border-gray-300 hover:bg-gray-50 text-gray-700 hover:text-red-700'
                    }`}
                    title="Buka berkas PDF asli di tab baru"
                  >
                    <ExternalLink className="w-4 h-4" />
                    <span>Buka PDF Asli</span>
                  </button>
                  
                  {/* Tombol Unduh Berkas PDF */}
                  <button 
                    onClick={handleDownloadPdf}
                    disabled={isApiConfigured && (pdfNotFound || (!pdfBlobUrl && pdfLoading))}
                    className={`flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg text-xs font-bold shadow-sm border transition-colors cursor-pointer ${
                      isApiConfigured && (pdfNotFound || (!pdfBlobUrl && pdfLoading))
                        ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
                        : 'bg-white border-gray-300 hover:bg-gray-50 text-gray-700'
                    }`}
                    title="Unduh Berkas PDF"
                  >
                    <Download className="w-4 h-4" />
                    <span>Unduh</span>
                  </button>
                </>
              )}
            </div>
          </div>

          <div className="mt-4 flex items-center gap-2 text-xs text-gray-500 font-medium">
            <ShieldCheck className="w-4 h-4 text-green-600 shrink-0" />
            <span>Dokumen sumber yang tersimpan dalam Knowledge Base terindeks dan diverifikasi otomatis oleh HERO OJK.</span>
          </div>
        </div>

        {/* 4. Teks Dokumen (Teks Mentah Hasil Ekstraksi) */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-6 sm:p-7">
          <div className="flex items-center justify-between gap-3 mb-5 pb-4 border-b border-gray-100 flex-wrap">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 bg-red-50 text-red-700 rounded-lg">
                <FileText className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-bold text-gray-900 text-base">Teks Dokumen</h3>
                <p className="text-xs text-gray-500 mt-0.5">Teks mentah hasil ekstraksi dokumen regulasi.</p>
              </div>
            </div>

            {/* Tombol Salin Teks jika teks tersedia */}
            {textData?.text && (
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-gray-400 font-medium">
                  {textData.total_length || textData.text.length} karakter
                </span>
                <button
                  onClick={handleCopyText}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-xs font-semibold transition-colors cursor-pointer"
                  title="Salin teks mentah ke papan klip"
                >
                  {isCopied ? (
                    <>
                      <CheckCircle className="w-3.5 h-3.5 text-green-600" />
                      <span className="text-green-700">Tersalin!</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5 text-gray-600" />
                      <span>Salin Teks</span>
                    </>
                  )}
                </button>
              </div>
            )}
          </div>

          {/* Area Konten Teks Dokumen */}
          {!isApiConfigured ? (
            <div className="bg-gray-50/80 border border-gray-200 rounded-xl p-6 text-center text-gray-500">
              <FileText className="w-8 h-8 mx-auto mb-2 text-gray-400 stroke-1" />
              <p className="text-sm font-medium text-gray-600">Teks belum tersedia</p>
              <p className="text-xs text-gray-400 mt-1">
                Pada mode contoh, teks mentah hasil ekstraksi tidak dimuat dari server.
              </p>
            </div>
          ) : textLoading ? (
            <div className="p-8">
              <LoadingState message="Memuat teks mentah dokumen..." />
            </div>
          ) : textError ? (
            <div className="p-4">
              <ErrorState
                title="Gagal Memuat Teks Dokumen"
                message={textError}
                onRetry={retryFetchText}
                retryText="Coba lagi"
              />
            </div>
          ) : textNotFound || !textData?.text || textData.text.trim() === '' ? (
            <div className="bg-gray-50/80 border border-gray-200 rounded-xl p-6 text-center text-gray-500">
              <FileText className="w-8 h-8 mx-auto mb-2 text-gray-400 stroke-1" />
              <p className="text-sm font-medium text-gray-600">Teks belum tersedia</p>
              <p className="text-xs text-gray-400 mt-1">
                Dokumen ini belum memiliki teks hasil ekstraksi atau teks tidak ditemukan di server.
              </p>
            </div>
          ) : (
            <div className="max-h-96 overflow-y-auto bg-gray-50 rounded-xl p-4 sm:p-5 border border-gray-200 text-xs font-mono text-gray-800 leading-relaxed whitespace-pre-wrap select-text">
              {textData.text}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
