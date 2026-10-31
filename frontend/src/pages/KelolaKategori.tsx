import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, FolderPlus, FolderTree, Info, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { isApiConfigured } from '../lib/api';
import {
  MAKS_NAMA_KATEGORI,
  buatKategori,
  getPohonKategori,
  hapusKategori,
  jalurTeks,
  pesanGalatKategori,
  ratakanPohon,
  ubahKategori,
} from '../lib/kategoriApi';
import type { CategoryTreeNode, KategoriTerindeks, PesanGalatKategori, UbahKategoriBody } from '../lib/kategoriApi';
import PohonKategori from '../components/kategori/PohonKategori';
import DetailKategori from '../components/kategori/DetailKategori';
import FormKategori from '../components/kategori/FormKategori';
import type { IsianKategori } from '../components/kategori/FormKategori';
import DialogKonfirmasi from '../components/kategori/DialogKonfirmasi';
import HasilSimpan from '../components/kategori/HasilSimpan';
import type { HasilAksiKategori } from '../components/kategori/HasilSimpan';
import { LoadingState } from '../components/LoadingState';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';

type Keadaan =
  | { status: 'loading' }
  | { status: 'galat'; galat: PesanGalatKategori }
  | { status: 'sukses'; nodes: CategoryTreeNode[] };

type Mode = { jenis: 'lihat' } | { jenis: 'buat'; parentId: number | null } | { jenis: 'ubah' };

interface Konfirmasi {
  judul: string;
  isi: string[];
  lanjut: () => void;
}

interface DialogHapus {
  node: CategoryTreeNode;
  path: string[];
  galat: PesanGalatKategori | null;
}

/** Fungsi pemilih node setelah pohon dimuat ulang; null = lepas pilihan */
type PilihSetelahMuat = (rata: KategoriTerindeks[]) => number | null;

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

function leluhur(rata: KategoriTerindeks[], id: number): number[] {
  const induk = new Map(rata.map((r) => [r.node.id, r.node.parent_id]));
  const hasil: number[] = [];
  let p = induk.get(id) ?? null;
  while (p !== null && !hasil.includes(p)) {
    hasil.push(p);
    p = induk.get(p) ?? null;
  }
  return hasil;
}

function KelolaKategoriApi() {
  const [keadaan, setKeadaan] = useState<Keadaan>({ status: 'loading' });
  const [putaran, setPutaran] = useState(0);
  const [terpilihId, setTerpilihId] = useState<number | null>(null);
  const [terbuka, setTerbuka] = useState<Set<number>>(new Set());
  const sudahDimuat = useRef(false);
  const pilihSetelahMuat = useRef<PilihSetelahMuat | null>(null);

  const [mode, setMode] = useState<Mode>({ jenis: 'lihat' });
  const [sibuk, setSibuk] = useState(false);
  const [galatAksi, setGalatAksi] = useState<PesanGalatKategori | null>(null);
  const [hasil, setHasil] = useState<HasilAksiKategori | null>(null);
  const [konfirmasi, setKonfirmasi] = useState<Konfirmasi | null>(null);
  const [dialogHapus, setDialogHapus] = useState<DialogHapus | null>(null);
  const ulangiTerakhir = useRef<(() => void) | null>(null);
  const aksiController = useRef<AbortController | null>(null);
  useEffect(() => () => aksiController.current?.abort(), []);

  useEffect(() => {
    const controller = new AbortController();
    // Ditunda satu tick agar mount ganda StrictMode tidak mengirim request dua kali
    const timer = setTimeout(() => {
      getPohonKategori({ signal: controller.signal })
        .then((nodes) => {
          if (controller.signal.aborted) return;
          const rata = ratakanPohon(nodes);
          const ada = (id: number | null) => id !== null && rata.some((r) => r.node.id === id);
          const pilih = pilihSetelahMuat.current;
          pilihSetelahMuat.current = null;
          setKeadaan({ status: 'sukses', nodes });
          if (pilih) {
            const target = pilih(rata);
            setTerpilihId(ada(target) ? target : null);
            if (target !== null && ada(target)) setTerbuka((prev) => new Set([...prev, ...leluhur(rata, target)]));
          } else {
            // Pilihan yang sudah tidak ada (mis. dihapus di tempat lain) dilepas
            setTerpilihId((prev) => (ada(prev) ? prev : null));
          }
          if (!sudahDimuat.current) {
            sudahDimuat.current = true;
            setTerbuka((prev) => new Set([...prev, ...nodes.filter((n) => n.children.length > 0).map((n) => n.id)]));
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
  /** Setelah mutasi: pohon dimuat ulang tanpa mengosongkan tampilan */
  const segarkan = (pilih: PilihSetelahMuat) => {
    pilihSetelahMuat.current = pilih;
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

  const pilihNode = (id: number) => {
    setTerpilihId(id);
    setMode({ jenis: 'lihat' });
    setGalatAksi(null);
  };

  const bukaForm = (m: Mode) => {
    setMode(m);
    setGalatAksi(null);
    setHasil(null);
  };

  const mulaiAksi = () => {
    aksiController.current?.abort();
    const c = new AbortController();
    aksiController.current = c;
    setSibuk(true);
    setGalatAksi(null);
    return c;
  };

  // --- Buat --------------------------------------------------------------
  const kirimBuat = (isian: IsianKategori) => {
    const jalankan = async () => {
      const c = mulaiAksi();
      try {
        await buatKategori({ name: isian.nama, parent_id: isian.parentId, classification_rule: isian.aturan }, { signal: c.signal });
        if (c.signal.aborted) return;
        setHasil({
          judul: `Kategori “${isian.namaBersih}” dibuat`,
          catatanNama: isian.namaBersih !== isian.nama ? `Nama disimpan sebagai “${isian.namaBersih}” (karakter yang tidak diizinkan dibuang, maks. ${MAKS_NAMA_KATEGORI} karakter).` : null,
        });
        setMode({ jenis: 'lihat' });
        // Respons POST tidak dipakai (bentuknya tidak terdokumentasi): cari node baru di pohon segar
        segarkan((r) => r.find((x) => x.node.parent_id === isian.parentId && x.node.name === isian.namaBersih)?.node.id ?? null);
      } catch (err) {
        if (c.signal.aborted) return;
        setGalatAksi(pesanGalatKategori(err, 'buat'));
      } finally {
        if (!c.signal.aborted) setSibuk(false);
      }
    };
    ulangiTerakhir.current = () => void jalankan();
    void jalankan();
  };

  // --- Ubah --------------------------------------------------------------
  const kirimUbah = (node: CategoryTreeNode, isian: IsianKategori) => {
    // Hanya field yang berubah; parent_id yang tidak dikirim berbeda arti dengan null (pindah ke akar)
    const body: UbahKategoriBody = {};
    if (isian.nama !== node.name) body.name = isian.nama;
    if (isian.parentId !== node.parent_id) body.parent_id = isian.parentId;
    const aturanLama = node.classification_rule?.trim() ? node.classification_rule.trim() : null;
    if (isian.aturan !== aturanLama) body.classification_rule = isian.aturan;

    if (Object.keys(body).length === 0) {
      setGalatAksi({ judul: 'Tidak ada perubahan', pesan: 'Belum ada isian yang diubah.', bisaCobaLagi: false });
      return;
    }
    const pathBerubah = 'name' in body || 'parent_id' in body;

    const jalankan = async () => {
      setKonfirmasi(null);
      const c = mulaiAksi();
      try {
        const res = await ubahKategori(node.id, body, { signal: c.signal });
        if (c.signal.aborted) return;
        const namaTersimpan = res.kategori?.name || isian.namaBersih;
        setHasil({
          judul: `Kategori “${namaTersimpan}” disimpan`,
          catatanNama: 'name' in body && namaTersimpan !== isian.nama
            ? `Nama disimpan sebagai “${namaTersimpan}” (karakter yang tidak diizinkan dibuang, maks. ${MAKS_NAMA_KATEGORI} karakter).`
            : null,
          dokumenDipindah: pathBerubah ? res.dokumen_dipindah : undefined,
          dokumenGagal: res.dokumen_gagal,
        });
        setMode({ jenis: 'lihat' });
        segarkan(() => node.id);
      } catch (err) {
        if (c.signal.aborted) return;
        setGalatAksi(pesanGalatKategori(err, 'ubah'));
      } finally {
        if (!c.signal.aborted) setSibuk(false);
      }
    };
    ulangiTerakhir.current = () => void jalankan();

    const isi: string[] = [];
    if (pathBerubah && node.total_document_count > 0) {
      isi.push(`Berkas ${node.total_document_count} dokumen di kategori ini dan subkategorinya akan dipindahkan ke folder baru. Proses ini bisa memakan waktu.`);
    }
    if (node.auto_created) {
      isi.push('Kategori ini dibuat otomatis: nama lama bisa muncul lagi saat dokumen baru ditempatkan otomatis, dan dokumen yang kategorinya tidak dipilih manual bisa pindah balik saat metadatanya dikoreksi.');
    }
    if (isi.length === 0) {
      void jalankan();
      return;
    }
    setKonfirmasi({
      judul: pathBerubah && node.total_document_count > 0
        ? `${node.total_document_count} dokumen akan dipindahkan. Lanjutkan?`
        : 'Simpan perubahan kategori otomatis?',
      isi,
      lanjut: () => void jalankan(),
    });
  };

  // --- Hapus -------------------------------------------------------------
  const jalankanHapus = async (d: DialogHapus) => {
    const c = mulaiAksi();
    try {
      await hapusKategori(d.node.id, { signal: c.signal });
      if (c.signal.aborted) return;
      setDialogHapus(null);
      setHasil({ judul: `Kategori “${d.node.name}” dihapus` });
      setMode({ jenis: 'lihat' });
      segarkan(() => d.node.parent_id);
    } catch (err) {
      if (c.signal.aborted) return;
      setDialogHapus({ ...d, galat: pesanGalatKategori(err, 'hapus') });
    } finally {
      if (!c.signal.aborted) setSibuk(false);
    }
  };

  const tutupKonfirmasi = useCallback(() => setKonfirmasi(null), []);
  const tutupHapus = useCallback(() => setDialogHapus(null), []);

  const bisaHapus = (n: CategoryTreeNode) => n.children.length === 0 && n.jumlah_dokumen === 0;
  const alasanTakBisaHapus = (n: CategoryTreeNode) =>
    `Tidak bisa dihapus: masih ada ${n.children.length} subkategori dan ${n.jumlah_dokumen} dokumen. Pindahkan atau kosongkan dulu.`;

  const tombolSekunder =
    'inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-gray-300 bg-white text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed';

  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-2xl font-bold text-gray-900">
            <FolderTree size={22} className="text-red-700" /> Kelola Kategori
          </h2>
          <p className="text-gray-500 mt-1 text-sm">Atur hierarki folder kategori Knowledge Base.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/knowledge" className={tombolSekunder}>
            <ArrowLeft size={13} /> Kembali ke Knowledge Base
          </Link>
          <button type="button" onClick={muatUlang} disabled={keadaan.status === 'loading' || sibuk} className={tombolSekunder}>
            <RefreshCw size={13} className={keadaan.status === 'loading' ? 'animate-spin' : ''} /> Muat ulang
          </button>
          {nodes && (
            <button
              type="button"
              onClick={() => bukaForm({ jenis: 'buat', parentId: null })}
              disabled={sibuk}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-red-700 hover:bg-red-800 text-xs font-semibold text-white disabled:opacity-50"
            >
              <Plus size={13} /> Tambah kategori akar
            </button>
          )}
        </div>
      </div>

      {hasil && <HasilSimpan hasil={hasil} onTutup={() => setHasil(null)} />}

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
                  onPilih={pilihNode}
                  onBukaTutup={bukaTutup}
                  terkunci={sibuk}
                />
              </>
            )}
          </section>

          <section className="lg:col-span-2 bg-white p-5 rounded-xl border border-gray-200 shadow-sm lg:sticky lg:top-4" aria-label="Detail kategori">
            {mode.jenis === 'buat' ? (
              <FormKategori
                key={`buat-${mode.parentId ?? 'akar'}`}
                mode="buat"
                parentIdAwal={mode.parentId}
                rata={rata}
                sibuk={sibuk}
                galat={galatAksi}
                onCobaLagi={() => ulangiTerakhir.current?.()}
                onBatal={() => bukaForm({ jenis: 'lihat' })}
                onKirim={kirimBuat}
              />
            ) : mode.jenis === 'ubah' && terpilih ? (
              <FormKategori
                key={`ubah-${terpilih.node.id}`}
                mode="ubah"
                node={terpilih.node}
                parentIdAwal={terpilih.node.parent_id}
                rata={rata}
                sibuk={sibuk}
                galat={galatAksi}
                onCobaLagi={() => ulangiTerakhir.current?.()}
                onBatal={() => bukaForm({ jenis: 'lihat' })}
                onKirim={(isian) => kirimUbah(terpilih.node, isian)}
              />
            ) : terpilih ? (
              <DetailKategori
                item={terpilih}
                aksi={
                  <>
                    <button type="button" onClick={() => bukaForm({ jenis: 'ubah' })} disabled={sibuk} className={tombolSekunder}>
                      <Pencil size={13} /> Ubah
                    </button>
                    <button type="button" onClick={() => bukaForm({ jenis: 'buat', parentId: terpilih.node.id })} disabled={sibuk} className={tombolSekunder}>
                      <FolderPlus size={13} /> Tambah subkategori
                    </button>
                    <span title={bisaHapus(terpilih.node) ? undefined : alasanTakBisaHapus(terpilih.node)} className="inline-flex">
                      <button
                        type="button"
                        onClick={() => setDialogHapus({ node: terpilih.node, path: terpilih.path, galat: null })}
                        disabled={sibuk || !bisaHapus(terpilih.node)}
                        className={`${tombolSekunder} text-red-700`}
                        data-hapus
                      >
                        <Trash2 size={13} /> Hapus
                      </button>
                    </span>
                    {!bisaHapus(terpilih.node) && (
                      <p className="basis-full text-[10px] text-gray-500" data-alasan-tak-bisa-hapus>
                        {alasanTakBisaHapus(terpilih.node)}
                      </p>
                    )}
                  </>
                }
              />
            ) : (
              <p className="py-8 text-center text-sm text-gray-500">Pilih kategori di pohon untuk melihat detailnya.</p>
            )}
          </section>
        </div>
      )}

      {konfirmasi && (
        <DialogKonfirmasi judul={konfirmasi.judul} labelLanjut="Lanjutkan" onBatal={tutupKonfirmasi} onLanjut={konfirmasi.lanjut}>
          {konfirmasi.isi.map((t) => <p key={t}>{t}</p>)}
        </DialogKonfirmasi>
      )}

      {dialogHapus && (
        <DialogKonfirmasi
          judul={`Hapus kategori “${dialogHapus.node.name}”?`}
          labelLanjut={dialogHapus.galat?.bisaCobaLagi ? 'Coba lagi' : 'Hapus'}
          nada="bahaya"
          sibuk={sibuk}
          tanpaLanjut={!!dialogHapus.galat && !dialogHapus.galat.bisaCobaLagi}
          onBatal={tutupHapus}
          onLanjut={() => void jalankanHapus(dialogHapus)}
        >
          <p className="text-[11px] text-gray-500">{jalurTeks(dialogHapus.path)}</p>
          <p>Kategori akan dihapus permanen. Tindakan ini tidak dapat dibatalkan.</p>
          {dialogHapus.galat && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800" data-galat-hapus>
              <strong>{dialogHapus.galat.judul}.</strong> {dialogHapus.galat.pesan}
            </div>
          )}
        </DialogKonfirmasi>
      )}
    </>
  );
}
