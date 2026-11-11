import { Sparkles, Info } from 'lucide-react';
import { normalisasiRingkasanAi } from '../../lib/analisaApi';
import type { MlAnalisaAiDetails, MlAnalisaAiSentence } from '../../lib/analisaApi';

export interface RingkasanAiPanelProps {
  ai: MlAnalisaAiDetails | null | undefined;
  ringkasanAi: string | MlAnalisaAiSentence[] | undefined;
  modeDipakai: 'deterministik' | 'ai' | undefined;
  onJumpToPasal?: (pasal: string) => void;
}

/**
 * Narasi ringkasan eksekutif AI tanpa chip rujukan pasal teknis.
 * Ditampilkan sebagai prosa narasi yang mengalir dan mudah dipahami pengguna non-IT.
 */
export default function RingkasanAiPanel({ ai, ringkasanAi, modeDipakai }: RingkasanAiPanelProps) {
  if (modeDipakai === 'ai') {
    const kalimat = normalisasiRingkasanAi(ringkasanAi ?? ai?.ringkasan);
    if (kalimat.length === 0) return null;

    return (
      <div className="bg-purple-50/40 rounded-xl p-4 sm:p-5 border border-purple-200/80 space-y-3 shadow-2xs">
        <div className="flex items-center gap-1.5">
          <Sparkles size={14} className="text-purple-700" />
          <span className="text-xs font-bold text-purple-900 tracking-tight">
            Narasi Eksekutif AI
          </span>
        </div>
        <div className="text-sm font-normal text-gray-800 leading-relaxed font-sans space-y-2.5">
          {kalimat.map((k, kIdx) => (
            <p key={kIdx} className="leading-relaxed">
              {k.kalimat}
            </p>
          ))}
        </div>
      </div>
    );
  }

  if (ai?.status === 'deterministik') {
    return (
      <div className="bg-amber-50/70 rounded-xl p-3.5 border border-amber-200 flex items-start gap-2.5 text-xs text-amber-900 font-sans">
        <Info size={15} className="text-amber-600 shrink-0 mt-0.5" />
        <div className="space-y-0.5">
          <p className="font-semibold">Mode AI tidak dipakai — ringkasan di bawah adalah hasil Deterministik.</p>
          {typeof ai.alasan === 'string' && ai.alasan.trim() !== '' && (
            <p className="text-amber-800 leading-relaxed">Alasan: {ai.alasan}</p>
          )}
        </div>
      </div>
    );
  }

  return null;
}
