import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, FolderTree, Info, RefreshCw } from 'lucide-react';
import { isApiConfigured } from '../lib/api';
import { getPohonKategori, pesanGalatKategori, ratakanPohon } from '../lib/kategoriApi';
import type { CategoryTreeNode, KategoriTerindeks, PesanGalatKategori } from '../lib/kategoriApi';
import PohonKategori from '../components/kategori/PohonKategori';
import DetailKategori from '../components/kategori/DetailKategori';
import { LoadingState } from '../components/LoadingState';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';

type Keadaan =
  | { status: 'loading' }
  | { status: 'galat'; galat: PesanGalatKategori }
  | { status: 'sukses'; nodes: CategoryTreeNode[] };

export default function KelolaKategori() {
  return (
    <div className="max-w-[1200px] mx-auto space-y-6">
      <div className="text-xs text-gray-500">
        <Link to="/" className="hover:underline">Dashboard</Link> /{' '}
        <Link to="/knowledge" className="hover:underline">Knowledge Base</Link> /{' '}
        <span className="font-semibold text-gray-900">Kelola Kategori</span>
      </div>
      {isApiConfigured ? (
        <KelolaKategoriApi />
      ) : (
        <EmptyState
          title="Kelola Kategori membutuhkan koneksi API"
          message="Mode contoh tidak memiliki data kategori yang bisa dikelola."
        />
      )}
    </div>
  );
}

function KelolaKategoriApi() {
  const [keadaan, setKeadaan] = useState<Keadaan>({ status: 'loading' });
  const [putaran, setPutaran] = useState(0);
  const [terpilihId, setTerpilihId] = useState<number | null>(null);
  const [terbuka, setTerbuka] = useState<Set<number>>(new Set());
  const sudahDimuat = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    // Ditunda satu tick agar mount ganda StrictMode tidak mengirim request dua kali
    const timer = setTimeout(() => {
      getPohonKategori({ signal: controller.signal })
        .then((nodes) => {
          if (controller.signal.aborted) return;
          const rata = ratakanPohon(nodes);
          setKeadaan({ status: 'sukses', nodes });
          // Pilihan yang sudah tidak ada (mis. dihapus di tempat lain) dilepas
          setTerpilihId((prev) => (prev !== null && rata.some((r) => r.node.id === prev) ? prev : null));
          if (!sudahDimuat.current) {
            sudahDimuat.current = true;
            setTerbuka(new Set(nodes.filter((n) => n.children.length > 0).map((n) => n.id)));
          }
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted || (err instanceof Error && err.name === 'AbortError')) return;
          setKeadaan({ status: 'galat', galat: pesanGalatKategori(err, 'muat') });
        });
    }, 0);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [putaran]);

  const muatUlang = () => {
    setKeadaan({ status: 'loading' });
    setPutaran((p) => p + 1);
  };

  const nodes = keadaan.status === 'sukses' ? keadaan.nodes : null;
  const rata = useMemo(() => (nodes ? ratakanPohon(nodes) : []), [nodes]);
  const terpilih: KategoriTerindeks | null = rata.find((r) => r.node.id === terpilihId) ?? null;

  const bukaTutup = (id: number) =>
    setTerbuka((prev) => {
      const s = new Set(prev);
      if (s.has(id)) s.delete(id);
      else s.add(id);
      return s;
    });

  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-2xl font-bold text-gray-900">
            <FolderTree size={22} className="text-red-700" /> Kelola Kategori
          </h2>
          <p className="text-gray-500 mt-1 text-sm">Atur hierarki folder kategori Knowledge Base.</p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/knowledge"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-gray-300 bg-white text-xs font-semibold text-gray-700 hover:bg-gray-50"
          >
            <ArrowLeft size={13} /> Kembali ke Knowledge Base
          </Link>
          <button
            type="button"
            onClick={muatUlang}
            disabled={keadaan.status === 'loading'}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-gray-300 bg-white text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw size={13} className={keadaan.status === 'loading' ? 'animate-spin' : ''} /> Muat ulang
          </button>
        </div>
      </div>

      {keadaan.status === 'loading' && <LoadingState message="Memuat pohon kategori..." className="my-8" />}

      {keadaan.status === 'galat' && (
        <ErrorState
          title={keadaan.galat.judul}
          message={keadaan.galat.pesan}
          onRetry={keadaan.galat.bisaCobaLagi ? muatUlang : undefined}
          retryText="Coba lagi"
        />
      )}

      {nodes && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-start">
          <section className="lg:col-span-3 bg-white p-4 rounded-xl border border-gray-200 shadow-sm" aria-label="Daftar kategori">
            {nodes.length === 0 ? (
              <EmptyState title="Belum ada kategori" message="Kategori dibuat otomatis saat dokumen ditempatkan, atau tambahkan secara manual." />
            ) : (
              <>
                <p className="mb-2 flex items-center gap-1 text-[11px] text-gray-500">
                  <Info size={11} /> Angka: dokumen langsung di kategori · total termasuk subkategori (hanya dokumen aktif).
                </p>
                <PohonKategori
                  nodes={nodes}
                  terpilihId={terpilihId}
                  terbuka={terbuka}
                  onPilih={setTerpilihId}
                  onBukaTutup={bukaTutup}
                />
              </>
            )}
          </section>

          <section className="lg:col-span-2 bg-white p-5 rounded-xl border border-gray-200 shadow-sm lg:sticky lg:top-4" aria-label="Detail kategori">
            {terpilih ? (
              <DetailKategori item={terpilih} />
            ) : (
              <p className="py-8 text-center text-sm text-gray-500">Pilih kategori di pohon untuk melihat detailnya.</p>
            )}
          </section>
        </div>
      )}
    </>
  );
}
