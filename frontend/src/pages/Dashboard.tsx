import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Layers,
  CheckCircle,
  Ban,
  ArrowRightLeft,
  RefreshCw,
  ChevronRight,
  ExternalLink,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  apiFetch,
  isApiConfigured,
  type DashboardSummaryResponse,
  type CategoryNode,
} from '../lib/api';
import {
  getJenisJobIngestLabel,
  getJobStatusBadgeClass,
} from './ingest/labels';
import { LoadingState } from '../components/LoadingState';
import { ErrorState } from '../components/ErrorState';

// Data statis untuk mode contoh (fallback saat API tidak aktif)
const mockStatData = {
  Kategori: [
    { label: 'Perbankan', value: 42, pct: '32.8%', to: '/knowledge?kategori=Perbankan' },
    { label: 'Pasar Modal', value: 28, pct: '21.9%', to: '/knowledge?kategori=Pasar%20Modal' },
    { label: 'Fintech', value: 22, pct: '17.2%', to: '/knowledge?kategori=Fintech' },
    { label: 'Asuransi', value: 18, pct: '14.1%', to: '/knowledge?kategori=Asuransi' },
    { label: 'Tata Kelola IT & AI', value: 12, pct: '9.4%', to: '/knowledge?kategori=Tata%20Kelola%20IT%20%26%20AI' },
    { label: 'Lainnya', value: 6, pct: '4.7%', to: '/knowledge?kategori=Lainnya' },
  ],
  'Jenis Regulasi': [
    { label: 'POJK', value: 60, pct: '46.8%', to: '/knowledge?regulation_type=POJK' },
    { label: 'SEOJK', value: 35, pct: '27.3%', to: '/knowledge?regulation_type=SEOJK' },
    { label: 'PDK', value: 20, pct: '15.6%', to: '/knowledge?jenis=PDK' },
    { label: 'SEDK', value: 13, pct: '10.3%', to: '/knowledge?jenis=SEDK' },
  ],
  Tahun: [
    { label: '2026', value: 35, pct: '27.3%', to: '/knowledge?year=2026' },
    { label: '2025', value: 31, pct: '24.2%', to: '/knowledge?year=2025' },
    { label: '2024', value: 28, pct: '21.8%', to: '/knowledge?year=2024' },
    { label: '2023', value: 20, pct: '15.6%', to: '/knowledge?year=2023' },
    { label: '2022', value: 14, pct: '11.1%', to: '/knowledge?year=2022' },
  ],
  Topik: [
    { label: 'Ketahanan Siber', value: 32, pct: '25.0%', to: '/knowledge?topik=Ketahanan%20Siber' },
    { label: 'Tata Kelola', value: 28, pct: '21.8%', to: '/knowledge?topik=Tata%20Kelola' },
    { label: 'AI', value: 24, pct: '18.7%', to: '/knowledge?topik=AI' },
    { label: 'Perlindungan Konsumen', value: 23, pct: '17.9%', to: '/knowledge?topik=Perlindungan%20Konsumen' },
    { label: 'Manajemen Risiko', value: 21, pct: '16.6%', to: '/knowledge?topik=Manajemen%20Risiko' },
  ],
};

const subtitles = {
  Kategori: 'Sebaran cakupan regulasi per sektor industri',
  'Jenis Regulasi': 'Distribusi dokumen berdasarkan klasifikasi jenis peraturan',
  Tahun: 'Tren penerbitan regulasi dari waktu ke waktu',
  Topik: 'Fokus utama area pengaturan dan pengawasan',
};

export default function Dashboard() {
  const [statDimension, setStatDimension] = useState<string>('Kategori');

  // State API
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [categoriesTree, setCategoriesTree] = useState<CategoryNode[] | null>(null);
  const [loading, setLoading] = useState<boolean>(isApiConfigured);
  const [error, setError] = useState<string | null>(null);

  // Ambil data dashboard dari backend
  const fetchDashboardData = useCallback(async () => {
    if (!isApiConfigured) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const [sumData, catData] = await Promise.all([
        apiFetch<DashboardSummaryResponse>('/api/v1/dashboard/summary'),
        apiFetch<CategoryNode[]>('/api/v1/categories/tree').catch((err) => {
          console.warn('Gagal memuat categories tree:', err);
          return [] as CategoryNode[];
        }),
      ]);
      setSummary(sumData);
      setCategoriesTree(catData);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    const timer = setTimeout(() => {
      if (mounted) fetchDashboardData();
    }, 0);
    return () => {
      mounted = false;
      clearTimeout(timer);
    };
  }, [fetchDashboardData]);

  // Total dokumen KB untuk persentase
  const totalCorpus = summary?.kb?.corpus_documents ?? 0;

  // Hitung data statistik berdasarkan dimensi aktif
  const currentStats = useMemo(() => {
    if (!isApiConfigured || !summary) {
      return mockStatData[statDimension as keyof typeof mockStatData] || [];
    }

    const total = totalCorpus > 0 ? totalCorpus : 1;

    if (statDimension === 'Jenis Regulasi') {
      return (summary.kb.by_regulation_type || []).map((item) => {
        const pct = `${((item.count / total) * 100).toFixed(1)}%`;
        const to = item.regulation_type
          ? `/knowledge?regulation_type=${encodeURIComponent(item.regulation_type)}`
          : null;
        return {
          label: item.label || 'Belum diketahui',
          value: item.count,
          pct,
          to,
        };
      });
    }

    if (statDimension === 'Tahun') {
      return (summary.kb.by_year || []).map((item) => {
        const pct = `${((item.count / total) * 100).toFixed(1)}%`;
        const to =
          item.year !== null ? `/knowledge?year=${encodeURIComponent(String(item.year))}` : null;
        return {
          label: item.label || 'Belum diketahui',
          value: item.count,
          pct,
          to,
        };
      });
    }

    if (statDimension === 'Kategori') {
      // Ambil kategori tingkat atas dari categoriesTree
      const topCategories = (categoriesTree || [])
        .filter((c) => c.parent_id === null)
        .sort((a, b) => b.total_document_count - a.total_document_count);

      return topCategories.map((cat) => {
        const pct = `${((cat.total_document_count / total) * 100).toFixed(1)}%`;
        const to = `/knowledge?category_id=${cat.id}`;
        return {
          label: cat.name,
          value: cat.total_document_count,
          pct,
          to,
        };
      });
    }

    return [];
  }, [summary, categoriesTree, statDimension, totalCorpus]);

  // Daftar opsi dimensi: sembunyikan Topik bila API aktif
  const dimensionOptions = isApiConfigured
    ? ['Kategori', 'Jenis Regulasi', 'Tahun']
    : ['Kategori', 'Jenis Regulasi', 'Tahun', 'Topik'];

  // Fallback data jika dimensi saat ini tidak ada
  const activeDimension = dimensionOptions.includes(statDimension) ? statDimension : 'Kategori';

  return (
    <div className="max-w-[1200px] mx-auto space-y-6">
      {/* Header Section */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Selamat datang di HERO</h2>
          <p className="text-gray-500 mt-1 text-sm">
            Pantau kondisi regulasi dan aktivitas sistem dalam satu tempat.
          </p>
        </div>

        {isApiConfigured && (
          <button
            type="button"
            onClick={fetchDashboardData}
            disabled={loading}
            className="self-start sm:self-auto flex items-center px-3.5 py-2 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors shadow-sm disabled:opacity-50 cursor-pointer"
            title="Segarkan data dashboard"
          >
            <RefreshCw
              size={14}
              className={`mr-1.5 ${loading ? 'animate-spin text-red-700' : ''}`}
            />
            Segarkan
          </button>
        )}
      </div>

      {/* Loading State */}
      {loading && !summary && (
        <LoadingState message="Memuat ringkasan data dashboard..." className="my-8" />
      )}

      {/* Error State */}
      {error && !loading && (
        <ErrorState
          title="Gagal Memuat Ringkasan Dashboard"
          message={error}
          onRetry={fetchDashboardData}
          retryText="Coba lagi"
          className="my-4"
        />
      )}

      {/* Data Section (bila tidak error dan tidak sedang loading awal) */}
      {(!loading || summary) && !error && (
        <>
          {/* Top 4 Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Card 1: TOTAL REGULASI */}
            <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col justify-between">
              <div className="flex justify-between items-start">
                <h3 className="text-[11px] font-bold text-gray-500 tracking-wider uppercase">
                  TOTAL REGULASI
                </h3>
                <div className="text-gray-400 bg-gray-100/50 p-1.5 rounded-lg border border-gray-100">
                  <Layers size={16} />
                </div>
              </div>
              <div className="mt-4">
                <span className="text-3xl font-bold text-gray-900">
                  {isApiConfigured && summary ? summary.kb.corpus_documents : 128}
                </span>
                {isApiConfigured && summary ? (
                  <p className="text-[11px] text-gray-500 mt-1 font-medium">
                    Target Fase 1: ≥ {summary.kb.target_fase1} —{' '}
                    <span
                      className={
                        summary.kb.target_met
                          ? 'text-emerald-700 font-semibold'
                          : 'text-amber-700 font-semibold'
                      }
                    >
                      {summary.kb.target_met ? 'Tercapai' : 'Belum'}
                    </span>
                  </p>
                ) : (
                  <p className="text-[11px] text-gray-500 mt-1 font-medium">
                    Seluruh regulasi dalam sistem
                  </p>
                )}
              </div>
            </div>

            {/* Card 2: REGULASI BERLAKU */}
            <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col justify-between">
              <div className="flex justify-between items-start">
                <h3 className="text-[11px] font-bold text-gray-500 tracking-wider uppercase">
                  REGULASI BERLAKU
                </h3>
                <div className="text-green-600 bg-green-50 p-1.5 rounded-lg border border-green-100">
                  <CheckCircle size={16} />
                </div>
              </div>
              <div className="mt-4">
                <span className="text-3xl font-bold text-green-600">
                  {isApiConfigured && summary
                    ? summary.kb.by_status_keberlakuan.berlaku ?? 0
                    : 96}
                </span>
                <p className="text-[11px] text-gray-500 mt-1 font-medium">
                  Regulasi yang masih berlaku
                </p>
              </div>
            </div>

            {/* Card 3: DICABUT / TIDAK BERLAKU */}
            <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col justify-between">
              <div className="flex justify-between items-start">
                <h3 className="text-[11px] font-bold text-gray-500 tracking-wider uppercase">
                  DICABUT / TIDAK BERLAKU
                </h3>
                <div className="text-gray-500 bg-gray-100 p-1.5 rounded-lg border border-gray-200">
                  <Ban size={16} />
                </div>
              </div>
              <div className="mt-4">
                <span className="text-3xl font-bold text-gray-900">
                  {isApiConfigured && summary
                    ? summary.kb.by_status_keberlakuan.dicabut ?? 0
                    : 12}
                </span>
                <p className="text-[11px] text-gray-500 mt-1 font-medium">
                  Regulasi tidak lagi berlaku
                </p>
              </div>
            </div>

            {/* Card 4: REGULASI DIUBAH */}
            <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col justify-between">
              <div className="flex justify-between items-start">
                <h3 className="text-[11px] font-bold text-gray-500 tracking-wider uppercase">
                  REGULASI DIUBAH
                </h3>
                <div className="text-amber-600 bg-amber-50 p-1.5 rounded-lg border border-amber-100">
                  <ArrowRightLeft size={16} />
                </div>
              </div>
              <div className="mt-4">
                <span className="text-3xl font-bold text-amber-600">
                  {isApiConfigured && summary
                    ? summary.kb.by_status_keberlakuan.diubah ?? 0
                    : 20}
                </span>
                <p className="text-[11px] text-gray-500 mt-1 font-medium">
                  Regulasi yang memiliki perubahan
                </p>
              </div>
            </div>
          </div>

          {/* Baris kecil di bawah kartu: status belum diketahui */}
          {isApiConfigured && summary && (
            <div className="flex items-center justify-end px-1 -mt-2">
              <span className="text-xs text-gray-500">
                Status belum diketahui:{' '}
                <span className="font-semibold text-gray-700">
                  {summary.kb.by_status_keberlakuan.tidak_diketahui ?? 0}
                </span>{' '}
                dokumen
              </span>
            </div>
          )}

          {/* Middle Row: Statistik Regulasi */}
          <div className="grid grid-cols-1 gap-4">
            <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm">
              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6">
                <div>
                  <h3 className="text-base font-bold text-gray-900">Statistik Regulasi</h3>
                  <p className="text-xs text-gray-500 mt-1">
                    {subtitles[activeDimension as keyof typeof subtitles]}
                  </p>
                </div>
                <div className="flex items-center space-x-3 mt-4 sm:mt-0">
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Berdasarkan:
                  </span>
                  <select
                    value={activeDimension}
                    onChange={(e) => setStatDimension(e.target.value)}
                    className="text-sm font-medium border border-gray-300 rounded-lg focus:ring-red-600 focus:border-red-600 py-2 pl-3 pr-8 shadow-sm bg-white"
                  >
                    {dimensionOptions.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {currentStats.length === 0 ? (
                <div className="py-8 text-center text-xs text-gray-400">
                  Tidak ada data untuk dimensi ini.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2">
                  {currentStats.map((item, idx) => {
                    const rowContent = (
                      <div className="space-y-2 p-3 -mx-3 rounded-lg hover:bg-red-50/50 transition-colors border border-transparent hover:border-red-100">
                        <div className="flex items-center justify-between text-sm">
                          <span className="font-semibold text-gray-800 group-hover:text-red-700 transition-colors flex items-center">
                            {item.label}
                          </span>
                          <div className="flex items-center space-x-4">
                            <span className="font-bold text-gray-900 group-hover:text-red-700 transition-colors">
                              {item.value}
                            </span>
                            <span className="text-gray-500 text-xs w-12 text-right">
                              {item.pct}
                            </span>
                          </div>
                        </div>
                        <div className="w-full bg-gray-100 h-1.5 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-red-700 group-hover:bg-red-800 transition-colors rounded-full"
                            style={{ width: item.pct }}
                          />
                        </div>
                      </div>
                    );

                    if (item.to) {
                      return (
                        <Link key={idx} to={item.to} className="block group">
                          {rowContent}
                        </Link>
                      );
                    }

                    return (
                      <div key={idx} className="block cursor-default">
                        {rowContent}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Bottom Row: Ringkasan Aktivitas Sistem */}
          <div className="pt-2">
            <h3 className="text-base font-bold text-gray-900">Ringkasan Aktivitas Sistem</h3>
            <p className="text-xs text-gray-500 mt-1 mb-4">
              Status pemrosesan alur kerja dan antrean telaah regulasi saat ini
            </p>

            {isApiConfigured && summary ? (
              <>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  {/* Kartu 1: Perlu Ditinjau */}
                  <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col">
                    <div className="flex justify-between items-center mb-3">
                      <span className="text-sm font-semibold text-gray-800">Perlu Ditinjau</span>
                      <div className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                    </div>
                    <span className="text-3xl font-bold text-gray-900">
                      {summary.ingest.needs_review ?? 0}
                    </span>
                    <p className="text-[11px] text-gray-500 mt-2 font-medium">
                      Dokumen memerlukan peninjauan manual
                    </p>
                  </div>

                  {/* Kartu 2: Kegagalan Belum Ditangani (Link: /ingest?tab=riwayat) */}
                  <Link
                    to="/ingest?tab=riwayat"
                    className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col hover:border-red-200 hover:bg-red-50/20 transition-all group"
                  >
                    <div className="flex justify-between items-center mb-3">
                      <span className="text-sm font-semibold text-gray-800 group-hover:text-red-700 transition-colors">
                        Kegagalan Belum Ditangani
                      </span>
                      <div className="flex items-center space-x-1.5">
                        <div className="w-2.5 h-2.5 rounded-full bg-rose-600" />
                        <ExternalLink size={12} className="text-gray-400 group-hover:text-red-700" />
                      </div>
                    </div>
                    <span className="text-3xl font-bold text-rose-600">
                      {summary.ingest.open_failures ?? 0}
                    </span>
                    <p className="text-[11px] text-gray-500 mt-2 font-medium">
                      Antrean dokumen gagal diproses
                    </p>
                  </Link>

                  {/* Kartu 3: Pemindaian Aktif (Link: /ingest) */}
                  <Link
                    to="/ingest"
                    className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col hover:border-red-200 hover:bg-red-50/20 transition-all group"
                  >
                    <div className="flex justify-between items-center mb-3">
                      <span className="text-sm font-semibold text-gray-800 group-hover:text-red-700 transition-colors">
                        Pemindaian Aktif
                      </span>
                      <div className="flex items-center space-x-1.5">
                        <div className="w-2.5 h-2.5 rounded-full bg-blue-600" />
                        <ExternalLink size={12} className="text-gray-400 group-hover:text-red-700" />
                      </div>
                    </div>
                    <span className="text-3xl font-bold text-gray-900">
                      {summary.ingest.active_scans ?? 0}
                    </span>
                    <p className="text-[11px] text-gray-500 mt-2 font-medium">
                      Sesi scraping / pemindaian aktif
                    </p>
                  </Link>

                  {/* Kartu 4: Menunggu Ekstraksi */}
                  <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col">
                    <div className="flex justify-between items-center mb-3">
                      <span className="text-sm font-semibold text-gray-800">Menunggu Ekstraksi</span>
                      <div className="w-2.5 h-2.5 rounded-full bg-emerald-600" />
                    </div>
                    <span className="text-3xl font-bold text-gray-900">
                      {summary.kb.by_processing_status.diterima ?? 0}
                    </span>
                    <p className="text-[11px] text-gray-500 mt-2 font-medium">
                      Dokumen dalam antrean pemrosesan
                    </p>
                  </div>
                </div>

                {/* Job Terakhir (S-01 Elemen 2) */}
                <div className="mt-6 bg-white rounded-xl border border-gray-100 shadow-sm p-5">
                  <div className="flex items-center justify-between mb-4 pb-3 border-b border-gray-100">
                    <div>
                      <h4 className="text-sm font-bold text-gray-900">Job Terakhir</h4>
                      <p className="text-xs text-gray-500 mt-0.5">
                        Riwayat pemrosesan dan ingest dokumen terbaru di sistem
                      </p>
                    </div>
                    <Link
                      to="/ingest?tab=riwayat"
                      className="text-xs font-semibold text-red-700 hover:text-red-800 flex items-center hover:underline"
                    >
                      Lihat semua
                      <ChevronRight size={14} className="ml-0.5" />
                    </Link>
                  </div>

                  {(!summary.ingest.recent_jobs || summary.ingest.recent_jobs.length === 0) ? (
                    <div className="py-6 text-center text-xs text-gray-400">
                      Belum ada aktivitas job ingest yang tercatat.
                    </div>
                  ) : (
                    <div className="divide-y divide-gray-100">
                      {summary.ingest.recent_jobs.slice(0, 5).map((job) => (
                        <div
                          key={job.id}
                          className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs"
                        >
                          <div className="flex items-center space-x-3">
                            <span className="font-mono font-bold text-gray-700">#{job.id}</span>
                            <span className="font-semibold text-gray-900">
                              {getJenisJobIngestLabel(job.job_type)}
                            </span>
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${getJobStatusBadgeClass(
                                job.status
                              )}`}
                            >
                              {job.status.toUpperCase()}
                            </span>
                          </div>

                          <div className="flex items-center space-x-4 text-gray-500">
                            <div className="flex items-center space-x-1.5 font-medium">
                              <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[11px]">
                                {job.success_count} Berhasil
                              </span>
                              <span className="px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 text-[11px]">
                                {job.duplicate_count} Duplikat
                              </span>
                              <span className="px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 text-[11px]">
                                {job.failed_count} Gagal
                              </span>
                            </div>

                            <span className="text-gray-400 text-[11px] whitespace-nowrap">
                              {new Date(job.started_at).toLocaleString('id-ID', {
                                dateStyle: 'short',
                                timeStyle: 'short',
                              })}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            ) : (
              /* Mode Contoh (Fallback bila API tidak aktif) */
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col">
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-sm font-semibold text-gray-800">Perlu Ditinjau</span>
                    <div className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                  </div>
                  <span className="text-3xl font-bold text-gray-900">24</span>
                  <p className="text-[11px] text-gray-500 mt-2 font-medium">
                    Menunggu telaah analis hukum
                  </p>
                </div>

                <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col">
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-sm font-semibold text-gray-800">Sedang Diproses</span>
                    <div className="w-2.5 h-2.5 rounded-full bg-blue-700" />
                  </div>
                  <span className="text-3xl font-bold text-gray-900">20</span>
                  <p className="text-[11px] text-gray-500 mt-2 font-medium">
                    Dalam antrean ekstraksi & parsing
                  </p>
                </div>

                <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col">
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-sm font-semibold text-gray-800">Harmonisasi Aktif</span>
                    <div className="w-2.5 h-2.5 rounded-full bg-green-600" />
                  </div>
                  <span className="text-3xl font-bold text-gray-900">20</span>
                  <p className="text-[11px] text-gray-500 mt-2 font-medium">
                    Komparasi pasal lintas regulasi
                  </p>
                </div>

                <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col">
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-sm font-semibold text-gray-800">Analisa Regulasi</span>
                    <div className="w-2.5 h-2.5 rounded-full bg-red-700" />
                  </div>
                  <span className="text-3xl font-bold text-gray-900">12</span>
                  <p className="text-[11px] text-gray-500 mt-2 font-medium">
                    Telaah analisa & tanggapan regulasi
                  </p>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
