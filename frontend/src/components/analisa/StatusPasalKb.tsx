import { useMemo } from 'react';
import type { HarmonisasiPanelState } from './HarmonisasiPanel';
import { labelTemuan, type JenisTemuan } from '../../lib/harmonisasiApi';

/**
 * Definisi "analisa" Pak Faris (Weekly #7): status setiap pasal terhadap Knowledge Base —
 * Baru, Sama, Menggantikan, atau Melengkapi. Diambil dari hasil harmonisasi (angka dihitung dari
 * temuan yang tampil, yaitu setelah penyaringan akses).
 */
const URUTAN: JenisTemuan[] = ['pasal_baru', 'duplikasi', 'menggantikan', 'memperjelas'];

const GAYA: Record<string, string> = {
  pasal_baru: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  duplikasi: 'bg-gray-50 text-gray-700 border-gray-200',
  menggantikan: 'bg-amber-50 text-amber-800 border-amber-200',
  memperjelas: 'bg-sky-50 text-sky-800 border-sky-200',
  konflik: 'bg-red-50 text-red-800 border-red-200',
};

interface Props {
  state: HarmonisasiPanelState | null;
  onLihatPerPasal: () => void;
  onCobaLagi: () => void;
}

export default function StatusPasalKb({ state, onLihatPerPasal, onCobaLagi }: Props) {
  const hitung = useMemo(() => {
    const h: Record<string, number> = {};
    const temuan = Array.isArray(state?.data?.temuan) ? state!.data!.temuan! : [];
    for (const t of temuan) if (t && typeof t.jenis === 'string') h[t.jenis] = (h[t.jenis] ?? 0) + 1;
    return h;
  }, [state]);

  const total = Object.values(hitung).reduce((a, b) => a + b, 0);
  const jenis = [...URUTAN, ...((hitung.konflik ?? 0) > 0 ? (['konflik'] as JenisTemuan[]) : [])];

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3" data-testid="status-pasal-kb">
      <div className="flex items-center justify-between pb-1 border-b border-gray-100">
        <span className="text-[11px] font-bold text-gray-800 uppercase tracking-wider">Status pasal terhadap Knowledge Base</span>
        {state?.status === 'sukses' && total > 0 && (
          <button type="button" onClick={onLihatPerPasal} className="text-[10px] font-semibold text-red-700 hover:underline">
            Lihat per pasal →
          </button>
        )}
      </div>

      {(!state || state.status === 'loading') && !total && (
        <p className="text-gray-500">Membandingkan setiap pasal dengan Knowledge Base…</p>
      )}

      {state?.status === 'galat' && !total && (
        <div className="flex items-center justify-between gap-2">
          <p className="text-gray-600">{state.galat?.pesan ?? 'Status pasal belum dapat dihitung.'}</p>
          <button type="button" onClick={onCobaLagi} className="shrink-0 text-[10px] font-semibold text-red-700 hover:underline">
            Coba lagi
          </button>
        </div>
      )}

      {state?.status === 'sukses' && total === 0 && (
        <p className="text-gray-500">Tidak ada pasal yang dapat dibandingkan untuk dokumen ini.</p>
      )}

      {total > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {jenis.map((j) => (
            <div key={j} className={`rounded-lg border px-3 py-2 ${GAYA[j]}`}>
              <div className="text-lg font-bold leading-none">{hitung[j] ?? 0}</div>
              <div className="text-[10px] font-semibold uppercase tracking-wide mt-1">{labelTemuan({ jenis: j, badge: null })}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
