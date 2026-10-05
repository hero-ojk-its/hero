import { useState, useEffect, useMemo } from 'react';
import {
  Search,
  FileText,
  Globe,
  Cloud,
  ChevronDown,
  CheckCircle,
  UploadCloud,
  FolderOpen,
  Folder,
  FolderTree,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';

import { regulasiData } from '../data/regulasiData';
import type { RegulasiItem } from '../data/regulasiData';
import {
  isApiConfigured,
  apiFetch,
  buildQueryString,
  adaptDocumentToDetail,
} from '../lib/api';
import { useFetch } from '../lib/useFetch';
import type {
  DocumentItem,
  DocumentsResponse,
  CategoryNode,
  DashboardSummaryResponse,
} from '../lib/api';
import { LoadingState } from '../components/LoadingState';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';

// Opsi statis untuk mode contoh (fallback regulasiData)
const fallbackFilterOptions: Record<string, string[]> = {
  Kategori: ['Semua Kategori', 'Perbankan', 'Pasar Modal', 'Fintech', 'Asuransi', 'Tata Kelola IT & AI', 'Lainnya'],
  Jenis: ['Semua Jenis', 'POJK', 'PDK', 'SEDK', 'SEOJK'],
  Tahun: ['Semua Tahun', '2026', '2025', '2024', '2023', '2022'],
  Bidang: ['Semua Bidang', 'Perbankan', 'Pasar Modal', 'Fintech', 'Asuransi', 'Tata Kelola IT & AI', 'Lainnya'],
  Status: ['Semua Status', 'Aktif', 'Diubah', 'Dicabut', 'Tidak diketahui'],
  Sumber: ['Semua Sumber', 'Scraping', 'Folder Lokal', 'OneDrive', 'Upload Manual'],
};


const statusOptions = [
  'Semua Status',
  'Aktif',
  'Diubah',
  'Dicabut',
  'Tidak diketahui',
];

interface FlatCategory {
  id: number;
  name: string;
  path: string;
  depth: number;
  count: number;
}

function flattenCategories(nodes: CategoryNode[], depth = 0, parentPath = ''): FlatCategory[] {
  const result: FlatCategory[] = [];
  for (const node of nodes) {
    const currentPath = parentPath ? `${parentPath} / ${node.name}` : node.name;
    result.push({
      id: node.id,
      name: node.name,
      path: currentPath,
      depth,
      count: node.total_document_count,
    });
    if (node.children && node.children.length > 0) {
      result.push(...flattenCategories(node.children, depth + 1, currentPath));
    }
  }
  return result;
}

const STATUS_REVERSE_MAP: Record<string, string> = {
  berlaku: 'Aktif',
  aktif: 'Aktif',
  diubah: 'Diubah',
  dicabut: 'Dicabut',
  tidak_diketahui: 'Tidak diketahui',
};

export default function KnowledgeBase() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const initialQ = searchParams.get('q') || '';
  const initialJenis = searchParams.get('regulation_type') || searchParams.get('jenis') || 'Semua Jenis';
  const initialTahun = searchParams.get('year') || searchParams.get('tahun') || 'Semua Tahun';
  const initialCategoryIdParam = searchParams.get('category_id') || searchParams.get('kategori');
  const initialStatusParam = searchParams.get('status_keberlakuan') || searchParams.get('status');

  const initialStatus = initialStatusParam
    ? STATUS_REVERSE_MAP[initialStatusParam.toLowerCase()] || initialStatusParam
    : 'Semua Status';

  const initialCategoryIdNum =
    initialCategoryIdParam && !isNaN(Number(initialCategoryIdParam)) ? Number(initialCategoryIdParam) : null;
  const initialCategoryName =
    initialCategoryIdParam && isNaN(Number(initialCategoryIdParam))
      ? initialCategoryIdParam
      : initialCategoryIdNum
      ? `Kategori #${initialCategoryIdNum}`
      : 'Semua Kategori';

  // Search input state (immediate and debounced 400ms)
  const [searchInput, setSearchInput] = useState(initialQ);
  const [debouncedQuery, setDebouncedQuery] = useState(initialQ);

  // Dropdown open state
  const [openFilter, setOpenFilter] = useState<string | null>(null);

  // Filter states
  const [selectedKategori, setSelectedKategori] = useState<{ id: number | null; name: string }>({
    id: initialCategoryIdNum,
    name: initialCategoryName,
  });
  const [selectedJenis, setSelectedJenis] = useState<string>(initialJenis);
  const [selectedTahun, setSelectedTahun] = useState<string>(initialTahun);
  const [selectedBidang, setSelectedBidang] = useState<string>('Semua Bidang');
  const [selectedStatus, setSelectedStatus] = useState<string>(initialStatus);
  const [selectedSumber, setSelectedSumber] = useState<string>('Semua Sumber'); // Dipakai di mode contoh

  // Paginasi
  const [currentPage, setCurrentPage] = useState<number>(1);
  const pageSize = 10;

  // Metadata filter dinamis dari API
  const [categoryNodes, setCategoryNodes] = useState<CategoryNode[] | null>(null);
  const [categoryError, setCategoryError] = useState<boolean>(false);

  const [summaryData, setSummaryData] = useState<DashboardSummaryResponse | null>(null);
  const [summaryError, setSummaryError] = useState<boolean>(false);

  // Debounce search input 400ms
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchInput);
      setCurrentPage(1);
    }, 400);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Muat dokumen dari Backend API menggunakan hook useFetch (otomatis menangani AbortController per request)
  const {
    data: apiDocuments,
    loading: docsLoading,
    error: docsFetchError,
    refetch: fetchDocuments,
  } = useFetch<DocumentsResponse>(
    (signal) => {
      const skip = (currentPage - 1) * pageSize;
      const params: Record<string, unknown> = {
        skip,
        limit: pageSize,
      };

      if (debouncedQuery.trim()) {
        params.q = debouncedQuery.trim();
      }
      if (selectedJenis !== 'Semua Jenis') {
        params.regulation_type = selectedJenis;
      }
      if (selectedTahun !== 'Semua Tahun') {
        params.year = Number(selectedTahun);
      }
      if (selectedBidang !== 'Semua Bidang') {
        params.bidang = selectedBidang;
      }
      if (selectedKategori.id !== null) {
        params.category_id = selectedKategori.id;
      }
      if (selectedStatus !== 'Semua Status') {
        const statusMap: Record<string, string> = {
          Aktif: 'berlaku',
          Diubah: 'diubah',
          Dicabut: 'dicabut',
          'Tidak diketahui': 'tidak_diketahui',
        };
        params.status_keberlakuan = statusMap[selectedStatus] || selectedStatus.toLowerCase();
      }

      const qs = buildQueryString(params);
      return apiFetch<DocumentsResponse>(`/api/v1/documents/${qs}`, { signal });
    },
    [
      currentPage,
      debouncedQuery,
      selectedJenis,
      selectedTahun,
      selectedBidang,
      selectedKategori,
      selectedStatus,
    ],
    isApiConfigured
  );

  const docsError = docsFetchError ? docsFetchError.message : null;

  // Muat Kategori dari GET /api/v1/categories/tree bila API aktif
  useEffect(() => {
    if (!isApiConfigured) return;

    const controller = new AbortController();
    let isMounted = true;
    apiFetch<CategoryNode[]>('/api/v1/categories/tree', { signal: controller.signal })
      .then((data) => {
        if (isMounted) {
          setCategoryNodes(data);
          setCategoryError(false);
        }
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        if (err instanceof Error && err.name === 'AbortError') return;
        if (isMounted) {
          setCategoryError(true);
        }
      });

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, []);

  // Muat Dashboard Summary dari GET /api/v1/dashboard/summary bila API aktif
  useEffect(() => {
    if (!isApiConfigured) return;

    const controller = new AbortController();
    let isMounted = true;
    apiFetch<DashboardSummaryResponse>('/api/v1/dashboard/summary', { signal: controller.signal })
      .then((data) => {
        if (isMounted) {
          setSummaryData(data);
          setSummaryError(false);
        }
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        if (err instanceof Error && err.name === 'AbortError') return;
        if (isMounted) {
          setSummaryError(true);
        }
      });

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, []);

  // Flat category list untuk dropdown navigasi folder kategori (spesifikasi S-06)
  const flatCategories = useMemo(() => {
    if (!categoryNodes) return [];
    return flattenCategories(categoryNodes);
  }, [categoryNodes]);

  // Opsi Jenis dinamis dari backend dashboard summary
  const jenisOptions = useMemo(() => {
    if (!isApiConfigured) return fallbackFilterOptions.Jenis;
    if (summaryData?.kb?.by_regulation_type) {
      const types = summaryData.kb.by_regulation_type
        .map((t) => t.regulation_type)
        .filter((t): t is string => Boolean(t));
      const unique = Array.from(new Set(types));
      return ['Semua Jenis', ...unique];
    }
    return ['Semua Jenis', 'POJK', 'SEOJK', 'UU', 'PP'];
  }, [summaryData]);

  // Opsi Tahun dinamis dari backend dashboard summary
  const tahunOptions = useMemo(() => {
    if (!isApiConfigured) return fallbackFilterOptions.Tahun;
    if (summaryData?.kb?.by_year) {
      const years = summaryData.kb.by_year
        .map((y) => (y.year !== null ? String(y.year) : null))
        .filter((y): y is string => Boolean(y));
      const unique = Array.from(new Set(years)).sort((a, b) => Number(b) - Number(a));
      return ['Semua Tahun', ...unique];
    }
    return ['Semua Tahun', '2026', '2025', '2024', '2023', '2022'];
  }, [summaryData]);

  // Opsi Bidang:
  // Catatan Keterbatasan Backend:
  // Kontrak OpenAPI Fase 1 (openapi-fase1.json) dan KONTRAK-API-FASE1.md tidak menyediakan
  // endpoint khusus master data bidang (dashboard/summary hanya menyediakan by_regulation_type dan by_year).
  // Sektor regulasi resmi yang disebutkan pada Alur 6 adalah: Perbankan, Pasar Modal, IKNB, dan BMKS.
  // Untuk mode API, opsi diambil dari daftar sektor resmi kontrak digabung nilai bidang aktual dari data dokumen.
  const bidangOptions = useMemo(() => {
    if (!isApiConfigured) return fallbackFilterOptions.Bidang;

    const contractSectors = ['Perbankan', 'Pasar Modal', 'IKNB', 'BMKS'];
    const fromLoadedData = (apiDocuments?.items || [])
      .map((item) => item.bidang)
      .filter((b): b is string => Boolean(b && b.trim() !== ''));

    const uniqueSectors = Array.from(new Set([...contractSectors, ...fromLoadedData]));
    return ['Semua Bidang', ...uniqueSectors];
  }, [apiDocuments]);

  // Tangani query param dari URL Dashboard (regulation_type, year, category_id, status_keberlakuan, q, topik, dll.)
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const qParam = params.get('q');
    const kategoriParam = params.get('category_id') || params.get('kategori');
    const jenisParam = params.get('regulation_type') || params.get('jenis');
    const tahunParam = params.get('year') || params.get('tahun');
    const statusParam = params.get('status_keberlakuan') || params.get('status');
    const topikParam = params.get('topik');

    queueMicrotask(() => {
      if (qParam !== null) {
        setSearchInput((prev) => (qParam !== prev ? qParam : prev));
        setDebouncedQuery((prev) => (qParam !== prev ? qParam : prev));
      }

      if (kategoriParam) {
        // Cocokkan ke kategori yang ada
        if (flatCategories.length > 0) {
          const found = flatCategories.find(
            (c) => c.name.toLowerCase() === kategoriParam.toLowerCase() || String(c.id) === kategoriParam
          );
          if (found) {
            setSelectedKategori({ id: found.id, name: found.name });
          } else {
            const num = Number(kategoriParam);
            setSelectedKategori({
              id: isNaN(num) ? null : num,
              name: isNaN(num) ? kategoriParam : `Kategori #${kategoriParam}`,
            });
          }
        } else {
          const num = Number(kategoriParam);
          setSelectedKategori({
            id: isNaN(num) ? null : num,
            name: isNaN(num) ? kategoriParam : `Kategori #${kategoriParam}`,
          });
        }
      }

      if (jenisParam) {
        setSelectedJenis((prev) => (jenisParam !== prev ? jenisParam : prev));
      }

      if (tahunParam) {
        setSelectedTahun((prev) => (tahunParam !== prev ? tahunParam : prev));
      }

      if (statusParam) {
        const mapped = STATUS_REVERSE_MAP[statusParam.toLowerCase()] || statusParam;
        setSelectedStatus((prev) => (mapped !== prev ? mapped : prev));
      }

      // Topik dari dashboard dipetakan ke bidang bila cocok, atau diabaikan tanpa error
      if (topikParam) {
        const matched = bidangOptions.find((b) => b.toLowerCase() === topikParam.toLowerCase());
        if (matched) {
          setSelectedBidang((prev) => (matched !== prev ? matched : prev));
        }
      }
    });
  }, [location.search, flatCategories, bidangOptions]);

  // Tutup dropdown jika klik di luar
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (!(e.target as Element).closest('.filter-dropdown-container')) {
        setOpenFilter(null);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  // Mode Contoh: Filter data statis regulasiData
  const mockFilteredData = useMemo(() => {
    if (isApiConfigured) return [];

    return regulasiData.filter((item) => {
      // Pencarian
      const q = debouncedQuery.toLowerCase();
      const matchSearch =
        !q ||
        item.judul.toLowerCase().includes(q) ||
        item.nomor.toLowerCase().includes(q) ||
        item.topik.toLowerCase().includes(q);

      // Kategori
      const matchKategori =
        selectedKategori.name === 'Semua Kategori' ||
        item.kategori.toLowerCase() === selectedKategori.name.toLowerCase();

      // Jenis
      const matchJenis =
        selectedJenis === 'Semua Jenis' ||
        item.jenis.toLowerCase() === selectedJenis.toLowerCase();

      // Tahun
      const matchTahun =
        selectedTahun === 'Semua Tahun' ||
        String(item.tahun) === selectedTahun;

      // Bidang (di data statis memakai properti topik/kategori)
      const matchBidang =
        selectedBidang === 'Semua Bidang' ||
        item.kategori.toLowerCase() === selectedBidang.toLowerCase() ||
        item.topik.toLowerCase() === selectedBidang.toLowerCase();

      // Status
      const matchStatus =
        selectedStatus === 'Semua Status' ||
        item.status.toLowerCase() === selectedStatus.toLowerCase();

      // Sumber
      const matchSumber =
        selectedSumber === 'Semua Sumber' ||
        item.sumber.toLowerCase() === selectedSumber.toLowerCase();

      return (
        matchSearch &&
        matchKategori &&
        matchJenis &&
        matchTahun &&
        matchBidang &&
        matchStatus &&
        matchSumber
      );
    });
  }, [
    debouncedQuery,
    selectedKategori,
    selectedJenis,
    selectedTahun,
    selectedBidang,
    selectedStatus,
    selectedSumber,
  ]);

  // Data yang akan ditampilkan di tabel
  const displayItems = useMemo(() => {
    if (isApiConfigured) {
      return apiDocuments?.items || [];
    }
    const startIndex = (currentPage - 1) * pageSize;
    return mockFilteredData.slice(startIndex, startIndex + pageSize);
  }, [apiDocuments, mockFilteredData, currentPage]);

  const totalDocuments = isApiConfigured
    ? apiDocuments?.total || 0
    : mockFilteredData.length;

  const totalPages = Math.max(1, Math.ceil(totalDocuments / pageSize));

  // Cek ketersediaan kolom sumber (hanya tampilkan jika ada di respons)
  const hasSumberColumn = useMemo(() => {
    if (!isApiConfigured) return true;
    return displayItems.some((item) => {
      const doc = item as DocumentItem;
      return Boolean(doc.source_url);
    });
  }, [displayItems]);

  // Reset Filter
  const handleResetFilters = () => {
    setSearchInput('');
    setDebouncedQuery('');
    setSelectedKategori({ id: null, name: 'Semua Kategori' });
    setSelectedJenis('Semua Jenis');
    setSelectedTahun('Semua Tahun');
    setSelectedBidang('Semua Bidang');
    setSelectedStatus('Semua Status');
    setSelectedSumber('Semua Sumber');
    setCurrentPage(1);
  };

  // Navigasi ke detail
  const handleRowClick = (item: DocumentItem | RegulasiItem) => {
    if (isApiConfigured) {
      const doc = item as DocumentItem;
      const adapted = adaptDocumentToDetail(doc);
      navigate(`/knowledge/detail/${doc.id}`, { state: { regulasi: adapted } });
    } else {
      navigate(`/knowledge/detail/${item.id}`, { state: { regulasi: item } });
    }
  };

  // Render Status Badge
  const renderStatusBadge = (statusValue: string) => {
    const s = (statusValue || '').toLowerCase();
    if (s === 'aktif' || s === 'berlaku') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-green-50 text-green-700 text-[11px] font-semibold border border-green-200/60">
          <span className="w-1.5 h-1.5 rounded-full bg-green-600"></span>
          Aktif
        </span>
      );
    }
    if (s === 'diubah') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-50 text-amber-700 text-[11px] font-semibold border border-amber-200/60">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
          Diubah
        </span>
      );
    }
    if (s === 'dicabut') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-red-50 text-red-700 text-[11px] font-semibold border border-red-200/60">
          <span className="w-1.5 h-1.5 rounded-full bg-red-600"></span>
          Dicabut
        </span>
      );
    }
    if (s === 'tidak diketahui' || s === 'tidak_diketahui') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-50 text-slate-700 text-[11px] font-semibold border border-slate-200/60">
          <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
          Tidak diketahui
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-gray-50 text-gray-700 text-[11px] font-semibold border border-gray-200/60">
        {statusValue}
      </span>
    );
  };

  // Render Pagination Text
  const paginationText = useMemo(() => {
    if (totalDocuments === 0) return 'Menampilkan 0 regulasi';
    const start = (currentPage - 1) * pageSize + 1;
    const end = Math.min(currentPage * pageSize, totalDocuments);
    return `Menampilkan ${start}-${end} dari ${totalDocuments} regulasi`;
  }, [currentPage, totalDocuments, pageSize]);

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
            {totalDocuments} dokumen
          </span>
          {!isApiConfigured && (
            <span className="bg-amber-50 text-amber-800 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border border-amber-200">
              Data contoh
            </span>
          )}
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
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="w-full pl-11 pr-4 py-3 bg-white border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-500 transition-colors placeholder-gray-400 shadow-sm"
            placeholder="Cari regulasi berdasarkan judul, nomor, atau bidang..."
          />
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 relative z-20">
          {/* Filter 1: Kategori (Tree / Navigasi Folder) */}
          <div className="relative filter-dropdown-container">
            <button
              onClick={() => setOpenFilter(openFilter === 'Kategori' ? null : 'Kategori')}
              disabled={categoryError}
              className={`flex items-center gap-2 px-3.5 py-2 bg-white border rounded-lg text-sm font-medium transition-colors shadow-sm ${
                categoryError
                  ? 'border-gray-200 bg-gray-100 text-gray-400 cursor-not-allowed'
                  : openFilter === 'Kategori'
                  ? 'border-red-500 text-red-700 ring-2 ring-red-500/20'
                  : 'border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400'
              }`}
            >
              <FolderTree className="w-4 h-4 text-gray-400" />
              <span>{selectedKategori.name}</span>
              {categoryError ? (
                <span className="text-[10px] text-red-500 font-normal">(Gagal)</span>
              ) : (
                <ChevronDown
                  className={`w-4 h-4 transition-transform ${
                    openFilter === 'Kategori' ? 'rotate-180 text-red-500' : 'text-gray-400'
                  }`}
                />
              )}
            </button>

            {openFilter === 'Kategori' && !categoryError && (
              <div className="absolute top-full left-0 mt-2 w-72 bg-white border border-gray-200 rounded-xl shadow-xl z-30 py-2 max-h-72 overflow-y-auto">
                <button
                  onClick={() => {
                    setSelectedKategori({ id: null, name: 'Semua Kategori' });
                    setOpenFilter(null);
                    setCurrentPage(1);
                  }}
                  className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center justify-between ${
                    selectedKategori.id === null ? 'bg-red-50 text-red-700 font-semibold' : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <span>Semua Kategori</span>
                  {selectedKategori.id === null && <CheckCircle className="w-4 h-4 text-red-600" />}
                </button>

                {isApiConfigured && flatCategories.length > 0 ? (
                  flatCategories.map((cat) => (
                    <button
                      key={cat.id}
                      onClick={() => {
                        setSelectedKategori({ id: cat.id, name: cat.name });
                        setOpenFilter(null);
                        setCurrentPage(1);
                      }}
                      style={{ paddingLeft: `${Math.max(16, 16 + cat.depth * 16)}px` }}
                      className={`w-full text-left pr-4 py-2 text-sm transition-colors flex items-center justify-between ${
                        selectedKategori.id === cat.id
                          ? 'bg-red-50 text-red-700 font-semibold'
                          : 'text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      <div className="flex items-center gap-1.5 truncate">
                        <Folder className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                        <span className="truncate">{cat.name}</span>
                        {cat.count > 0 && (
                          <span className="text-[10px] text-gray-400 shrink-0">({cat.count})</span>
                        )}
                      </div>
                      {selectedKategori.id === cat.id && <CheckCircle className="w-4 h-4 text-red-600 shrink-0" />}
                    </button>
                  ))
                ) : (
                  fallbackFilterOptions.Kategori.slice(1).map((catName) => (
                    <button
                      key={catName}
                      onClick={() => {
                        setSelectedKategori({ id: null, name: catName });
                        setOpenFilter(null);
                        setCurrentPage(1);
                      }}
                      className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center justify-between ${
                        selectedKategori.name === catName
                          ? 'bg-red-50 text-red-700 font-semibold'
                          : 'text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      <span>{catName}</span>
                      {selectedKategori.name === catName && <CheckCircle className="w-4 h-4 text-red-600" />}
                    </button>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Filter 2: Jenis */}
          <div className="relative filter-dropdown-container">
            <button
              onClick={() => setOpenFilter(openFilter === 'Jenis' ? null : 'Jenis')}
              disabled={summaryError}
              className={`flex items-center gap-2 px-3.5 py-2 bg-white border rounded-lg text-sm font-medium transition-colors shadow-sm ${
                summaryError
                  ? 'border-gray-200 bg-gray-100 text-gray-400 cursor-not-allowed'
                  : openFilter === 'Jenis'
                  ? 'border-red-500 text-red-700 ring-2 ring-red-500/20'
                  : 'border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400'
              }`}
            >
              <span>{selectedJenis}</span>
              {summaryError ? (
                <span className="text-[10px] text-red-500 font-normal">(Gagal)</span>
              ) : (
                <ChevronDown
                  className={`w-4 h-4 transition-transform ${
                    openFilter === 'Jenis' ? 'rotate-180 text-red-500' : 'text-gray-400'
                  }`}
                />
              )}
            </button>

            {openFilter === 'Jenis' && !summaryError && (
              <div className="absolute top-full left-0 mt-2 w-52 bg-white border border-gray-200 rounded-xl shadow-xl z-30 py-2 max-h-60 overflow-y-auto">
                {jenisOptions.map((option) => (
                  <button
                    key={option}
                    onClick={() => {
                      setSelectedJenis(option);
                      setOpenFilter(null);
                      setCurrentPage(1);
                    }}
                    className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center justify-between ${
                      selectedJenis === option ? 'bg-red-50 text-red-700 font-semibold' : 'text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    <span>{option}</span>
                    {selectedJenis === option && <CheckCircle className="w-4 h-4 text-red-600" />}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Filter 3: Tahun */}
          <div className="relative filter-dropdown-container">
            <button
              onClick={() => setOpenFilter(openFilter === 'Tahun' ? null : 'Tahun')}
              disabled={summaryError}
              className={`flex items-center gap-2 px-3.5 py-2 bg-white border rounded-lg text-sm font-medium transition-colors shadow-sm ${
                summaryError
                  ? 'border-gray-200 bg-gray-100 text-gray-400 cursor-not-allowed'
                  : openFilter === 'Tahun'
                  ? 'border-red-500 text-red-700 ring-2 ring-red-500/20'
                  : 'border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400'
              }`}
            >
              <span>{selectedTahun}</span>
              {summaryError ? (
                <span className="text-[10px] text-red-500 font-normal">(Gagal)</span>
              ) : (
                <ChevronDown
                  className={`w-4 h-4 transition-transform ${
                    openFilter === 'Tahun' ? 'rotate-180 text-red-500' : 'text-gray-400'
                  }`}
                />
              )}
            </button>

            {openFilter === 'Tahun' && !summaryError && (
              <div className="absolute top-full left-0 mt-2 w-48 bg-white border border-gray-200 rounded-xl shadow-xl z-30 py-2 max-h-60 overflow-y-auto">
                {tahunOptions.map((option) => (
                  <button
                    key={option}
                    onClick={() => {
                      setSelectedTahun(option);
                      setOpenFilter(null);
                      setCurrentPage(1);
                    }}
                    className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center justify-between ${
                      selectedTahun === option ? 'bg-red-50 text-red-700 font-semibold' : 'text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    <span>{option}</span>
                    {selectedTahun === option && <CheckCircle className="w-4 h-4 text-red-600" />}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Filter 4: Bidang (Menggantikan Topik) */}
          <div className="relative filter-dropdown-container">
            <button
              onClick={() => setOpenFilter(openFilter === 'Bidang' ? null : 'Bidang')}
              className={`flex items-center gap-2 px-3.5 py-2 bg-white border rounded-lg text-sm font-medium transition-colors shadow-sm ${
                openFilter === 'Bidang'
                  ? 'border-red-500 text-red-700 ring-2 ring-red-500/20'
                  : 'border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400'
              }`}
            >
              <span>{selectedBidang}</span>
              <ChevronDown
                className={`w-4 h-4 transition-transform ${
                  openFilter === 'Bidang' ? 'rotate-180 text-red-500' : 'text-gray-400'
                }`}
              />
            </button>

            {openFilter === 'Bidang' && (
              <div className="absolute top-full left-0 mt-2 w-56 bg-white border border-gray-200 rounded-xl shadow-xl z-30 py-2 max-h-60 overflow-y-auto">
                {bidangOptions.map((option) => (
                  <button
                    key={option}
                    onClick={() => {
                      setSelectedBidang(option);
                      setOpenFilter(null);
                      setCurrentPage(1);
                    }}
                    className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center justify-between ${
                      selectedBidang === option ? 'bg-red-50 text-red-700 font-semibold' : 'text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    <span>{option}</span>
                    {selectedBidang === option && <CheckCircle className="w-4 h-4 text-red-600" />}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Filter 5: Status */}
          <div className="relative filter-dropdown-container">
            <button
              onClick={() => setOpenFilter(openFilter === 'Status' ? null : 'Status')}
              className={`flex items-center gap-2 px-3.5 py-2 bg-white border rounded-lg text-sm font-medium transition-colors shadow-sm ${
                openFilter === 'Status'
                  ? 'border-red-500 text-red-700 ring-2 ring-red-500/20'
                  : 'border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400'
              }`}
            >
              <span>{selectedStatus}</span>
              <ChevronDown
                className={`w-4 h-4 transition-transform ${
                  openFilter === 'Status' ? 'rotate-180 text-red-500' : 'text-gray-400'
                }`}
              />
            </button>

            {openFilter === 'Status' && (
              <div className="absolute top-full left-0 mt-2 w-52 bg-white border border-gray-200 rounded-xl shadow-xl z-30 py-2 max-h-60 overflow-y-auto">
                {statusOptions.map((option) => (
                  <button
                    key={option}
                    onClick={() => {
                      setSelectedStatus(option);
                      setOpenFilter(null);
                      setCurrentPage(1);
                    }}
                    className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center justify-between ${
                      selectedStatus === option ? 'bg-red-50 text-red-700 font-semibold' : 'text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    <span>{option}</span>
                    {selectedStatus === option && <CheckCircle className="w-4 h-4 text-red-600" />}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Filter 6: Sumber (Hanya relevan di mode contoh bila ada) */}
          {!isApiConfigured && (
            <div className="relative filter-dropdown-container">
              <button
                onClick={() => setOpenFilter(openFilter === 'Sumber' ? null : 'Sumber')}
                className={`flex items-center gap-2 px-3.5 py-2 bg-white border rounded-lg text-sm font-medium transition-colors shadow-sm ${
                  openFilter === 'Sumber'
                    ? 'border-red-500 text-red-700 ring-2 ring-red-500/20'
                    : 'border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400'
                }`}
              >
                <span>{selectedSumber}</span>
                <ChevronDown
                  className={`w-4 h-4 transition-transform ${
                    openFilter === 'Sumber' ? 'rotate-180 text-red-500' : 'text-gray-400'
                  }`}
                />
              </button>

              {openFilter === 'Sumber' && (
                <div className="absolute top-full left-0 mt-2 w-52 bg-white border border-gray-200 rounded-xl shadow-xl z-30 py-2 max-h-60 overflow-y-auto">
                  {fallbackFilterOptions.Sumber.map((option) => (
                    <button
                      key={option}
                      onClick={() => {
                        setSelectedSumber(option);
                        setOpenFilter(null);
                        setCurrentPage(1);
                      }}
                      className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center justify-between ${
                        selectedSumber === option
                          ? 'bg-red-50 text-red-700 font-semibold'
                          : 'text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      <span>{option}</span>
                      {selectedSumber === option && <CheckCircle className="w-4 h-4 text-red-600" />}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Table Section */}
      <div className="space-y-4">
        {/* Table Header Controls */}
        <div className="flex justify-between items-center text-sm">
          <span className="text-gray-500">{paginationText}</span>
          <button
            onClick={handleResetFilters}
            className="text-gray-500 hover:text-gray-900 underline underline-offset-2 transition-colors cursor-pointer"
          >
            Reset Filter
          </button>
        </div>

        {/* Content Box (Table / Loading / Error / Empty) */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          {docsLoading ? (
            <LoadingState message="Memuat regulasi dari backend..." />
          ) : docsError ? (
            <ErrorState
              title="Gagal Memuat Regulasi"
              message={docsError}
              onRetry={fetchDocuments}
              retryText="Coba lagi"
            />
          ) : displayItems.length === 0 ? (
            <EmptyState
              title="Tidak ada regulasi yang cocok"
              message="Coba sesuaikan kata kunci pencarian atau reset filter yang dipilih."
              onAction={handleResetFilters}
              actionLabel="Reset Semua Filter"
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-gray-50/80 border-b border-gray-200">
                    <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Judul Regulasi</th>
                    <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Jenis</th>
                    <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Nomor</th>
                    <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Kategori</th>
                    <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Bidang</th>
                    <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Tahun</th>
                    <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Status</th>
                    {hasSumberColumn && (
                      <th className="px-3 py-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider">Sumber</th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {displayItems.map((item) => {
                    const isApiItem = isApiConfigured && 'title' in item;
                    const id = item.id;
                    const judul = isApiItem ? (item as DocumentItem).title : (item as RegulasiItem).judul;
                    const jenis = isApiItem
                      ? (item as DocumentItem).regulation_type || '-'
                      : (item as RegulasiItem).jenis;
                    // Tampilkan nomor apa adanya dari backend
                    const nomor = isApiItem
                      ? (item as DocumentItem).regulation_number || '-'
                      : (item as RegulasiItem).nomor;
                    const kategori = isApiItem
                      ? ((item as DocumentItem).category_path && (item as DocumentItem).category_path!.length > 0
                          ? (item as DocumentItem).category_path!.join(' / ')
                          : '-')
                      : (item as RegulasiItem).kategori;
                    const bidang = isApiItem
                      ? (item as DocumentItem).bidang || '-'
                      : (item as RegulasiItem).topik;
                    const docItem = item as DocumentItem;
                    const tahun = isApiItem
                      ? (docItem.release_date && !isNaN(new Date(docItem.release_date).getTime())
                          ? new Date(docItem.release_date).getFullYear()
                          : docItem.created_at && !isNaN(new Date(docItem.created_at).getTime())
                          ? new Date(docItem.created_at).getFullYear()
                          : '-')
                      : (item as RegulasiItem).tahun;
                    const status = isApiItem
                      ? (item as DocumentItem).status_keberlakuan
                      : (item as RegulasiItem).status;
                    const sumberVal = isApiItem
                      ? (item as DocumentItem).source_url || '-'
                      : (item as RegulasiItem).sumber;

                    return (
                      <tr
                        key={id}
                        onClick={() => handleRowClick(item)}
                        className="hover:bg-gray-50 group cursor-pointer transition-colors"
                      >
                        <td className="px-3 py-3">
                          <div className="flex items-start gap-3">
                            <div className="p-2 rounded-lg bg-red-50 text-red-600 border border-red-100 flex-shrink-0 group-hover:bg-red-100 transition-colors">
                              <FileText className="w-4 h-4" />
                            </div>
                            <span className="font-semibold text-gray-900 text-sm group-hover:text-red-700 transition-colors mt-1">
                              {judul}
                            </span>
                          </div>
                        </td>
                        <td className="px-3 py-3 whitespace-nowrap">
                          <span className="px-2.5 py-1 bg-gray-100 text-gray-700 text-xs font-bold rounded-md border border-gray-200/60">
                            {jenis}
                          </span>
                        </td>
                        <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-500 font-medium group-hover:text-gray-900">
                          {nomor}
                        </td>
                        <td className="px-3 py-3 text-sm text-gray-900 font-medium">
                          {kategori}
                        </td>
                        <td className="px-3 py-3">
                          <span className="px-2.5 py-1 bg-slate-50 text-slate-600 text-[11px] font-semibold border border-slate-200/60 rounded-md">
                            {bidang}
                          </span>
                        </td>
                        <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-500 font-medium">
                          {tahun}
                        </td>
                        <td className="px-3 py-3 whitespace-nowrap">
                          {renderStatusBadge(status)}
                        </td>
                        {hasSumberColumn && (
                          <td className="px-3 py-3 whitespace-nowrap">
                            <div className="flex items-center gap-2 text-gray-500 group-hover:text-gray-700 transition-colors">
                              {sumberVal.includes('Scraping') || sumberVal.startsWith('http') ? (
                                <Globe className="w-4 h-4 text-blue-500" />
                              ) : sumberVal.includes('Upload') ? (
                                <UploadCloud className="w-4 h-4 text-red-600" />
                              ) : sumberVal.includes('Folder') ? (
                                <FolderOpen className="w-4 h-4 text-amber-600" />
                              ) : (
                                <Cloud className="w-4 h-4 text-sky-500" />
                              )}
                              <span className="text-xs font-medium truncate max-w-[150px]">
                                {sumberVal}
                              </span>
                            </div>
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Pagination Section */}
        {totalDocuments > 0 && (
          <div className="flex flex-col sm:flex-row justify-between items-center py-2 text-sm text-gray-500 gap-3">
            <span>{paginationText}</span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-gray-500 hover:text-gray-900 font-medium transition-colors disabled:opacity-40 disabled:hover:text-gray-500 cursor-pointer"
              >
                <ChevronLeft className="w-4 h-4" />
                <span>Sebelumnya</span>
              </button>

              {/* Halaman dinamis */}
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                let pageNumber = i + 1;
                if (totalPages > 5 && currentPage > 3) {
                  pageNumber = currentPage - 3 + i;
                  if (pageNumber > totalPages) pageNumber = totalPages - 4 + i;
                }
                return (
                  <button
                    key={pageNumber}
                    onClick={() => setCurrentPage(pageNumber)}
                    className={`w-8 h-8 flex items-center justify-center rounded font-semibold transition-colors cursor-pointer ${
                      currentPage === pageNumber
                        ? 'bg-gray-900 text-white'
                        : 'hover:bg-gray-100 text-gray-700'
                    }`}
                  >
                    {pageNumber}
                  </button>
                );
              })}

              {totalPages > 5 && currentPage < totalPages - 2 && (
                <span className="w-8 h-8 flex items-center justify-center text-gray-400">...</span>
              )}

              {totalPages > 5 && currentPage < totalPages - 2 && (
                <button
                  onClick={() => setCurrentPage(totalPages)}
                  className={`w-8 h-8 flex items-center justify-center rounded font-semibold transition-colors cursor-pointer ${
                    currentPage === totalPages ? 'bg-gray-900 text-white' : 'hover:bg-gray-100 text-gray-700'
                  }`}
                >
                  {totalPages}
                </button>
              )}

              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-gray-900 font-semibold hover:bg-gray-50 rounded transition-colors ml-1 disabled:opacity-40 disabled:hover:bg-transparent cursor-pointer"
              >
                <span>Selanjutnya</span>
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
