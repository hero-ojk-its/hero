import type { ReactNode } from 'react';
import { Folder } from 'lucide-react';
import { jalurTeks } from '../../lib/kategoriApi';
import type { KategoriTerindeks } from '../../lib/kategoriApi';

export interface DetailKategoriProps {
  item: KategoriTerindeks;
  /** Tombol aksi (ubah, tambah subkategori, hapus) */
  aksi?: ReactNode;
}

export default function DetailKategori({ item, aksi }: DetailKategoriProps) {
  const { node, path } = item;
  return (
    <div className="space-y-4" data-detail-kategori={node.id}>
      <div>
        <p className="text-[11px] text-gray-500" data-jalur>{jalurTeks(path)}</p>
        <h3 className="mt-1 flex items-center gap-2 text-lg font-bold text-gray-900">
          <Folder size={18} className="text-amber-500" />
          {node.name}
          <span
            className={`px-2 py-0.5 rounded-full border text-[11px] font-semibold ${
              node.auto_created ? 'bg-gray-100 border-gray-200 text-gray-600' : 'bg-blue-50 border-blue-200 text-blue-700'
            }`}
            data-jenis-kategori
          >
            {node.auto_created ? 'Dibuat otomatis' : 'Dibuat / diubah pengguna'}
          </span>
        </h3>
      </div>

      <dl className="grid grid-cols-3 gap-3">
        {([
          ['Dokumen langsung', node.jumlah_dokumen, 'Dokumen aktif yang berada tepat di kategori ini'],
          ['Total dokumen', node.total_document_count, 'Termasuk dokumen di seluruh subkategori'],
          ['Subkategori', node.children.length, 'Subkategori langsung'],
        ] as const).map(([label, nilai, ket]) => (
          <div key={label} className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2" title={ket}>
            <dt className="text-[11px] font-semibold text-gray-500">{label}</dt>
            <dd className="text-xl font-bold text-gray-900" data-angka={label}>{nilai}</dd>
            <p className="text-[10px] text-gray-400 leading-tight">{ket}</p>
          </div>
        ))}
      </dl>

      <div>
        <h4 className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-1">Aturan klasifikasi</h4>
        {node.classification_rule ? (
          <pre className="max-h-40 overflow-auto rounded-lg border border-gray-200 bg-gray-50 p-2 text-[11px] font-mono text-gray-700 whitespace-pre-wrap break-all" data-aturan>
            {node.classification_rule}
          </pre>
        ) : (
          <p className="text-xs text-gray-500" data-aturan>Belum ada aturan.</p>
        )}
        <p className="mt-1 text-[10px] text-gray-400">
          Disimpan untuk aturan klasifikasi mendatang; belum memengaruhi penempatan dokumen.
        </p>
      </div>

      {aksi && <div className="flex flex-wrap gap-2 pt-1">{aksi}</div>}
    </div>
  );
}
