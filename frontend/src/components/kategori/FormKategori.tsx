import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { AlertTriangle, ChevronRight, Info, Loader2, RefreshCw } from 'lucide-react';
import {
  MAKS_ATURAN_KLASIFIKASI,
  MAKS_NAMA_KATEGORI,
  idDanTurunan,
  jalurTeks,
  validasiAturanKlasifikasi,
  validasiNamaKategori,
} from '../../lib/kategoriApi';
import type { CategoryTreeNode, KategoriTerindeks, PesanGalatKategori } from '../../lib/kategoriApi';

export interface IsianKategori {
  /** Nama sesuai isian (dipangkas); backend yang menyanitasi */
  nama: string;
  /** Nama setelah sanitasi versi klien, untuk keterangan */
  namaBersih: string;
  parentId: number | null;
  aturan: string | null;
}

export interface FormKategoriProps {
  mode: 'buat' | 'ubah';
  /** Kategori yang diubah (mode ubah) */
  node?: CategoryTreeNode;
  /** Induk awal (mode buat: node terpilih atau null untuk akar) */
  parentIdAwal: number | null;
  rata: KategoriTerindeks[];
  sibuk: boolean;
  galat: PesanGalatKategori | null;
  onCobaLagi?: () => void;
  onBatal: () => void;
  onKirim: (isian: IsianKategori) => void;
}

const AKAR = '';

export default function FormKategori({ mode, node, parentIdAwal, rata, sibuk, galat, onCobaLagi, onBatal, onKirim }: FormKategoriProps) {
  const [nama, setNama] = useState(node?.name ?? '');
  const [induk, setInduk] = useState<string>(parentIdAwal === null ? AKAR : String(parentIdAwal));
  const [aturan, setAturan] = useState(node?.classification_rule ?? '');
  const [lanjutanBuka, setLanjutanBuka] = useState(false);
  const [galatIsian, setGalatIsian] = useState<{ nama?: string; aturan?: string }>({});

  // Kategori tidak boleh dipindah ke dirinya sendiri atau turunannya
  const terlarang = useMemo(() => (node ? idDanTurunan(node) : new Set<number>()), [node]);
  const opsiInduk = rata.filter((r) => !terlarang.has(r.node.id));

  const vNama = validasiNamaKategori(nama);
  const panjangAturan = aturan.trim().length;

  const kirim = (e: FormEvent) => {
    e.preventDefault();
    const vAturan = validasiAturanKlasifikasi(aturan);
    const g: { nama?: string; aturan?: string } = {};
    if (!vNama.ok) g.nama = vNama.pesan;
    if (!vAturan.ok) {
      g.aturan = vAturan.pesan;
      setLanjutanBuka(true);
    }
    setGalatIsian(g);
    if (!vNama.ok || !vAturan.ok) return;
    onKirim({ nama: nama.trim(), namaBersih: vNama.nama, parentId: induk === AKAR ? null : Number(induk), aturan: vAturan.nilai });
  };

  return (
    <form onSubmit={kirim} className="space-y-4" data-form-kategori={mode} noValidate>
      <div>
        <h3 className="text-base font-bold text-gray-900">
          {mode === 'buat' ? 'Tambah kategori' : `Ubah kategori “${node?.name ?? ''}”`}
        </h3>
        {mode === 'ubah' && node && (
          <p className="text-[11px] text-gray-500 mt-0.5">
            {node.total_document_count} dokumen di kategori ini dan subkategorinya
          </p>
        )}
      </div>

      {mode === 'ubah' && node?.auto_created && (
        <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900" data-peringatan-otomatis>
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          <p>
            Kategori ini dibuat otomatis. Setelah diubah, nama lama bisa muncul lagi saat dokumen baru ditempatkan otomatis,
            dan dokumen yang kategorinya tidak dipilih manual bisa pindah balik saat metadatanya dikoreksi.
          </p>
        </div>
      )}

      <fieldset disabled={sibuk} className="space-y-4 disabled:opacity-70">
        <div>
          <label htmlFor="nama-kategori" className="block text-xs font-bold text-gray-700 mb-1">Nama</label>
          <input
            id="nama-kategori"
            value={nama}
            onChange={(e) => setNama(e.target.value)}
            maxLength={255}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
            placeholder="mis. Perbankan"
          />
          {galatIsian.nama ? (
            <p className="mt-1 text-[11px] text-red-700" data-galat-isian="nama">{galatIsian.nama}</p>
          ) : vNama.ok && vNama.disanitasi ? (
            <p className="mt-1 text-[11px] text-gray-500" data-pratinjau-nama>
              Akan disimpan sebagai “{vNama.nama}”. Karakter / \ : * ? &quot; &lt; &gt; | dibuang dan panjang maksimal {MAKS_NAMA_KATEGORI} karakter.
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="induk-kategori" className="block text-xs font-bold text-gray-700 mb-1">Induk</label>
          <select
            id="induk-kategori"
            value={induk}
            onChange={(e) => setInduk(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
          >
            <option value={AKAR}>(Akar — tanpa induk)</option>
            {opsiInduk.map((r) => (
              <option key={r.node.id} value={r.node.id}>{jalurTeks(r.path)}</option>
            ))}
          </select>
          {mode === 'ubah' && <p className="mt-1 text-[10px] text-gray-400">Kategori ini dan subkategorinya tidak bisa dipilih sebagai induk.</p>}
        </div>

        <div className="rounded-lg border border-gray-200">
          <button
            type="button"
            onClick={() => setLanjutanBuka((b) => !b)}
            aria-expanded={lanjutanBuka}
            className="w-full flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-gray-700"
            data-lanjutan
          >
            <ChevronRight size={13} className={`transition-transform ${lanjutanBuka ? 'rotate-90' : ''}`} />
            Lanjutan
            {aturan.trim() !== '' && !lanjutanBuka && <span className="font-normal text-gray-400">· ada aturan klasifikasi</span>}
          </button>
          {lanjutanBuka && (
            <div className="px-3 pb-3 space-y-1">
              <label htmlFor="aturan-kategori" className="block text-xs font-bold text-gray-700">Aturan klasifikasi (JSON objek)</label>
              <textarea
                id="aturan-kategori"
                value={aturan}
                onChange={(e) => setAturan(e.target.value)}
                rows={5}
                spellCheck={false}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs font-mono focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
                placeholder='{"kata_kunci": ["perbankan", "bank umum"]}'
              />
              <div className="flex items-start justify-between gap-2 text-[10px]">
                <span className="text-gray-500 flex items-start gap-1">
                  <Info size={11} className="shrink-0 mt-px" />
                  Disimpan untuk aturan klasifikasi mendatang; belum memengaruhi penempatan dokumen. Kosongkan untuk menghapus aturan.
                </span>
                <span className={`tabular-nums shrink-0 ${panjangAturan > MAKS_ATURAN_KLASIFIKASI ? 'text-red-700 font-semibold' : 'text-gray-400'}`} data-penghitung>
                  {panjangAturan}/{MAKS_ATURAN_KLASIFIKASI}
                </span>
              </div>
              {galatIsian.aturan && <p className="text-[11px] text-red-700" data-galat-isian="aturan">{galatIsian.aturan}</p>}
            </div>
          )}
        </div>
      </fieldset>

      {galat && (
        <div className="flex items-start justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800" data-galat-aksi>
          <span><strong>{galat.judul}.</strong> {galat.pesan}</span>
          {galat.bisaCobaLagi && onCobaLagi && (
            <button type="button" onClick={onCobaLagi} disabled={sibuk} className="inline-flex items-center gap-1 font-semibold hover:underline shrink-0">
              <RefreshCw size={11} /> Coba lagi
            </button>
          )}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onBatal}
          disabled={sibuk}
          className="px-3.5 py-2 rounded-lg border border-gray-300 bg-white text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          Batal
        </button>
        <button
          type="submit"
          disabled={sibuk}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-red-700 hover:bg-red-800 text-xs font-semibold text-white disabled:opacity-60"
          data-kirim
        >
          {sibuk && <Loader2 size={12} className="animate-spin" />}
          {sibuk ? 'Memproses…' : mode === 'buat' ? 'Buat kategori' : 'Simpan perubahan'}
        </button>
      </div>
    </form>
  );
}
