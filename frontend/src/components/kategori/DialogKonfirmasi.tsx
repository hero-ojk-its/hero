import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';

export interface DialogKonfirmasiProps {
  judul: string;
  children: ReactNode;
  labelLanjut: string;
  nada?: 'bahaya' | 'normal';
  /** Request sedang berjalan: tombol dikunci, Esc tidak menutup */
  sibuk?: boolean;
  /** Sembunyikan tombol lanjut (mis. setelah penolakan yang tidak bisa diulang) */
  tanpaLanjut?: boolean;
  onBatal: () => void;
  onLanjut: () => void;
}

export default function DialogKonfirmasi({
  judul, children, labelLanjut, nada = 'normal', sibuk = false, tanpaLanjut = false, onBatal, onLanjut,
}: DialogKonfirmasiProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !sibuk) onBatal();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onBatal, sibuk]);

  const warnaLanjut = nada === 'bahaya' ? 'bg-red-700 hover:bg-red-800' : 'bg-gray-900 hover:bg-gray-800';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="judul-dialog-kategori"
        className="w-full max-w-md rounded-xl bg-white shadow-xl border border-gray-200"
      >
        <div className="px-5 pt-5 flex items-start gap-3">
          <AlertTriangle size={20} className={nada === 'bahaya' ? 'text-red-600 shrink-0' : 'text-amber-500 shrink-0'} />
          <div className="space-y-2 min-w-0">
            <h2 id="judul-dialog-kategori" className="text-base font-bold text-gray-900">{judul}</h2>
            <div className="text-sm text-gray-600 space-y-2">{children}</div>
          </div>
        </div>
        <div className="mt-5 px-5 py-3 border-t border-gray-100 bg-gray-50/60 flex justify-end gap-2 rounded-b-xl">
          <button
            type="button"
            onClick={onBatal}
            disabled={sibuk}
            className="px-3.5 py-2 rounded-lg border border-gray-300 bg-white text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {tanpaLanjut ? 'Tutup' : 'Batal'}
          </button>
          {!tanpaLanjut && (
            <button
              type="button"
              onClick={onLanjut}
              disabled={sibuk}
              className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold text-white disabled:opacity-60 ${warnaLanjut}`}
            >
              {sibuk && <Loader2 size={12} className="animate-spin" />}
              {sibuk ? 'Memproses…' : labelLanjut}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
