import { AlertCircle } from 'lucide-react';

/** Senada dengan LABEL_REKOMENDASI di backend/app/services/analysis_export_service.py */
export const DRAFT_LABEL = 'Draft / Rekomendasi';
export const DRAFT_LABEL_KETERANGAN = 'Draft / Rekomendasi — hasil analisa otomatis, wajib diverifikasi analis.';

export interface DraftLabelProps {
  ukuran?: 'normal' | 'kecil';
  className?: string;
}

/**
 * Penanda wajib pada setiap blok keluaran analisa: sistem tidak mengambil keputusan.
 */
export function DraftLabel({ ukuran = 'normal', className = '' }: DraftLabelProps) {
  const kecil = ukuran === 'kecil';
  return (
    <span
      title={DRAFT_LABEL_KETERANGAN}
      className={`inline-flex items-center gap-1.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200 font-semibold shrink-0 ${
        kecil ? 'px-1.5 py-0 text-[10px]' : 'px-2.5 py-0.5 text-[11px]'
      } ${className}`}
    >
      <AlertCircle size={kecil ? 10 : 12} className="text-amber-600 shrink-0" />
      <span>{DRAFT_LABEL}</span>
    </span>
  );
}
