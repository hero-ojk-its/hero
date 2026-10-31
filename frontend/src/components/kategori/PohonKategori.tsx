import { ChevronRight, Folder, FolderOpen } from 'lucide-react';
import type { CategoryTreeNode } from '../../lib/kategoriApi';

export interface PohonKategoriProps {
  nodes: CategoryTreeNode[];
  terpilihId: number | null;
  terbuka: Set<number>;
  onPilih: (id: number) => void;
  onBukaTutup: (id: number) => void;
  /** Dikunci saat ada perubahan yang sedang diproses */
  terkunci?: boolean;
}

/** Pohon kategori yang bisa dibuka-tutup; jumlah dokumen langsung & total per node */
export default function PohonKategori(props: PohonKategoriProps) {
  return (
    <ul role="tree" aria-label="Pohon kategori" className="space-y-0.5">
      {props.nodes.map((n) => (
        <NodeKategori key={n.id} node={n} depth={0} {...props} />
      ))}
    </ul>
  );
}

function NodeKategori({ node, depth, ...p }: PohonKategoriProps & { node: CategoryTreeNode; depth: number }) {
  const punyaAnak = node.children.length > 0;
  const buka = punyaAnak && p.terbuka.has(node.id);
  const terpilih = p.terpilihId === node.id;

  return (
    <li role="treeitem" aria-expanded={punyaAnak ? buka : undefined} aria-selected={terpilih} data-kategori={node.id}>
      <div
        className={`flex items-center gap-1 rounded-lg pr-2 ${terpilih ? 'bg-red-50 ring-1 ring-red-200' : 'hover:bg-gray-50'}`}
        style={{ paddingLeft: `${4 + depth * 16}px` }}
      >
        {punyaAnak ? (
          <button
            type="button"
            onClick={() => p.onBukaTutup(node.id)}
            className="p-1 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100"
            aria-label={buka ? `Tutup ${node.name}` : `Buka ${node.name}`}
            data-buka-tutup
          >
            <ChevronRight size={14} className={`transition-transform ${buka ? 'rotate-90' : ''}`} />
          </button>
        ) : (
          <span className="w-[22px] shrink-0" />
        )}
        <button
          type="button"
          onClick={() => p.onPilih(node.id)}
          disabled={p.terkunci}
          className="flex-1 min-w-0 flex items-center justify-between gap-2 py-1.5 text-left text-sm disabled:cursor-not-allowed"
          data-pilih-kategori
        >
          <span className="flex items-center gap-1.5 min-w-0">
            {buka ? <FolderOpen size={15} className="text-amber-500 shrink-0" /> : <Folder size={15} className="text-amber-500 shrink-0" />}
            <span className={`truncate ${terpilih ? 'font-semibold text-red-800' : 'text-gray-800'}`}>{node.name}</span>
            {node.auto_created && (
              <span className="px-1.5 py-0.5 rounded bg-gray-100 border border-gray-200 text-[10px] font-medium text-gray-500 shrink-0" data-badge-otomatis>
                otomatis
              </span>
            )}
          </span>
          <span
            className="text-[11px] text-gray-500 shrink-0 tabular-nums"
            title="Dokumen langsung di kategori ini · total termasuk subkategori"
            data-jumlah
          >
            {node.jumlah_dokumen} langsung · {node.total_document_count} total
          </span>
        </button>
      </div>
      {buka && (
        <ul role="group" className="space-y-0.5">
          {node.children.map((c) => (
            <NodeKategori key={c.id} node={c} depth={depth + 1} {...p} />
          ))}
        </ul>
      )}
    </li>
  );
}
