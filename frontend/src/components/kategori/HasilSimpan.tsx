import { Link } from 'react-router-dom';
import { AlertTriangle, CheckCircle, Info, X } from 'lucide-react';
import { alasanPenempatan } from '../../lib/labelStatus';
import type { AlasanPenempatan } from '../../lib/labelStatus';
import type { DokumenGagalPenempatan } from '../../lib/kategoriApi';

export interface HasilAksiKategori {
  judul: string;
  /** Keterangan bila nama tersimpan berbeda dari isian */
  catatanNama?: string | null;
  /** Hanya diisi bila ada relokasi dokumen */
  dokumenDipindah?: number;
  dokumenGagal?: DokumenGagalPenempatan[];
}

interface Kelompok {
  alasan: AlasanPenempatan;
  baris: Array<{ id: number; pesan: string | null }>;
}

function kelompokkan(gagal: DokumenGagalPenempatan[]): Kelompok[] {
  const per = new Map<string, Kelompok>();
  for (const g of gagal) {
    const a = alasanPenempatan(g.alasan);
    const k = per.get(a.kode) ?? { alasan: a, baris: [] };
    k.baris.push({ id: g.document_id, pesan: a.pesan });
    per.set(a.kode, k);
  }
  // Galat ditampilkan lebih dulu dari info
  return [...per.values()].sort((x, y) => (x.alasan.jenis === y.alasan.jenis ? 0 : x.alasan.jenis === 'gagal' ? -1 : 1));
}

export default function HasilSimpan({ hasil, onTutup }: { hasil: HasilAksiKategori; onTutup: () => void }) {
  const kelompok = kelompokkan(hasil.dokumenGagal ?? []);
  return (
    <div className="space-y-2" data-hasil-simpan role="status">
      <div className="flex items-start justify-between gap-3 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-900">
        <div className="space-y-0.5">
          <p className="flex items-center gap-1.5 font-semibold">
            <CheckCircle size={15} /> {hasil.judul}
            {typeof hasil.dokumenDipindah === 'number' && hasil.dokumenDipindah > 0 && (
              <span className="font-normal" data-dipindah> · {hasil.dokumenDipindah} dokumen dipindah</span>
            )}
          </p>
          {hasil.catatanNama && <p className="text-xs text-green-800" data-catatan-nama>{hasil.catatanNama}</p>}
        </div>
        <button type="button" onClick={onTutup} className="p-0.5 rounded text-green-700 hover:bg-green-100" aria-label="Tutup pemberitahuan">
          <X size={14} />
        </button>
      </div>

      {kelompok.map(({ alasan, baris }) => {
        const info = alasan.jenis === 'info';
        return (
          <div
            key={alasan.kode}
            className={`rounded-lg border px-4 py-3 text-xs ${info ? 'border-gray-200 bg-gray-50 text-gray-700' : 'border-amber-200 bg-amber-50 text-amber-900'}`}
            data-kelompok-gagal={alasan.kode}
            data-jenis={alasan.jenis}
          >
            <p className="flex items-center gap-1.5 font-semibold">
              {info ? <Info size={13} className="text-gray-500" /> : <AlertTriangle size={13} className="text-amber-600" />}
              {alasan.label} · {baris.length} dokumen
            </p>
            <p className="mt-0.5">{alasan.keterangan}</p>
            <ul className="mt-1.5 space-y-0.5">
              {baris.map((b) => (
                <li key={b.id}>
                  <Link to={`/knowledge/detail/${b.id}`} className="font-semibold underline underline-offset-2 hover:no-underline">
                    Dokumen #{b.id}
                  </Link>
                  {/* Pesan backend bersifat teknis (mis. "[Errno 13] ..."): disembunyikan di balik elemen lipat */}
                  {b.pesan && (
                    <details className="mt-0.5 ml-1" data-detail-teknis>
                      <summary className="cursor-pointer select-none text-[11px] opacity-70 hover:opacity-100">Detail teknis</summary>
                      <p className="mt-0.5 text-[11px] font-mono opacity-80 break-all">{b.pesan}</p>
                    </details>
                  )}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
