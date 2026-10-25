import { ExternalLink, Info } from 'lucide-react';
import { normalisasiRingkasanAi, parsePasalRef } from '../../lib/analisaApi';
import type { MlAnalisaAiDetails, MlAnalisaAiSentence } from '../../lib/analisaApi';

export interface RingkasanAiPanelProps {
  ai: MlAnalisaAiDetails | null | undefined;
  ringkasanAi: string | MlAnalisaAiSentence[] | undefined;
  modeDipakai: 'deterministik' | 'ai' | undefined;
  onJumpToPasal: (pasal: string) => void;
}

/**
 * Narasi ringkasan AI per kalimat beserta rujukan pasalnya, atau alasan bila mode AI
 * diminta tetapi layanan memakai hasil deterministik (ai.status = 'deterministik').
 */
export default function RingkasanAiPanel({ ai, ringkasanAi, modeDipakai, onJumpToPasal }: RingkasanAiPanelProps) {
  if (modeDipakai === 'ai') {
    const kalimat = normalisasiRingkasanAi(ringkasanAi ?? ai?.ringkasan);
    if (kalimat.length === 0) return null;

    return (
      <div className="bg-white/90 rounded-lg p-3 border border-red-200/70 space-y-2 shadow-2xs">
        <span className="text-[10px] font-bold text-red-900 uppercase tracking-wider block">
          Narasi Ringkasan AI
        </span>
        <ul className="space-y-2">
          {kalimat.map((k, kIdx) => (
            <li key={kIdx} className="space-y-1">
              <p className="text-xs text-gray-800 leading-relaxed font-serif">{k.kalimat}</p>
              {k.rujukan.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[10px] font-medium text-gray-500">Rujukan:</span>
                  {k.rujukan.map((refStr, rIdx) => {
                    const isRecognized = parsePasalRef(refStr).pasalNum !== null;
                    return (
                      <button
                        key={rIdx}
                        type="button"
                        onClick={() => onJumpToPasal(refStr)}
                        className={`inline-flex items-center gap-1 font-mono text-[11px] font-semibold px-2 py-0.5 rounded transition ${
                          isRecognized
                            ? 'text-red-700 bg-red-50 hover:bg-red-100 hover:text-red-900 border border-red-200 cursor-pointer'
                            : 'text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-200 cursor-pointer'
                        }`}
                        title={isRecognized ? `Lompat ke ${refStr}` : `Telusuri rujukan "${refStr}"`}
                      >
                        <ExternalLink size={10} />
                        <span>{refStr}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (ai?.status === 'deterministik') {
    return (
      <div className="bg-amber-50/70 rounded-lg p-3 border border-amber-200 flex items-start gap-2 text-xs text-amber-900">
        <Info size={14} className="text-amber-600 shrink-0 mt-0.5" />
        <div className="space-y-0.5">
          <p className="font-semibold">Mode AI tidak dipakai — ringkasan di bawah adalah hasil Deterministik.</p>
          {typeof ai.alasan === 'string' && ai.alasan.trim() !== '' && (
            <p className="text-amber-800">Alasan: {ai.alasan}</p>
          )}
        </div>
      </div>
    );
  }

  return null;
}
