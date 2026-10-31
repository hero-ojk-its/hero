import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, Info, Loader2, RefreshCw, X } from 'lucide-react';
import { BATAS_DRILLDOWN, getKegagalanDrilldown, pesanGalatDrilldown } from '../../lib/corongApi';
import type { HasilDrilldown, PesanGalatCorong } from '../../lib/corongApi';
import { labelAlasanGagal } from '../../lib/labelStatus';
import { getFollowUpStatusBadgeClass, getFollowUpStatusLabel } from '../../pages/ingest/labels';

export interface DrilldownKegagalanModalProps {
  reasonCode: string;
  /** undefined/null = semua sumber (Total) */
  sourceId?: number | null;
  /** Nama cakupan untuk judul, mis. "Total" atau nama sumber */
  cakupan: string;
  onClose: () => void;
}

type Keadaan =
  | { status: 'loading' }
  | { status: 'galat'; galat: PesanGalatCorong }
  | { status: 'sukses'; hasil: HasilDrilldown };

const FORMAT_TANGGAL = new Intl.DateTimeFormat('id-ID', {
  timeZone: 'Asia/Jakarta', day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
});

function formatTanggal(iso: string | null | undefined): string {
  if (!iso) return '-';
  const t = new Date(iso);
  return Number.isNaN(t.getTime()) ? iso : `${FORMAT_TANGGAL.format(t)} WIB`;
}

/** Daftar kegagalan read-only untuk satu alasan; pengelolaan tetap di Antrean Kegagalan */
export default function DrilldownKegagalanModal({ reasonCode, sourceId, cakupan, onClose }: DrilldownKegagalanModalProps) {
  const [keadaan, setKeadaan] = useState<Keadaan>({ status: 'loading' });
  const [putaran, setPutaran] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    // Ditunda satu tick agar mount ganda StrictMode tidak mengirim request dua kali
    const timer = setTimeout(() => {
      getKegagalanDrilldown({ reasonCode, sourceId, signal: controller.signal })
        .then((hasil) => {
          if (!controller.signal.aborted) setKeadaan({ status: 'sukses', hasil });
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted || (err instanceof Error && err.name === 'AbortError')) return;
          setKeadaan({ status: 'galat', galat: pesanGalatDrilldown(err) });
        });
    }, 0);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [reasonCode, sourceId, putaran]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const cobaLagi = () => {
    setKeadaan({ status: 'loading' });
    setPutaran((p) => p + 1);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="judul-drilldown-kegagalan"
        className="bg-white rounded-xl shadow-xl w-full max-w-3xl overflow-hidden flex flex-col max-h-[90vh]"
      >
        <div className="px-6 py-4 border-b border-gray-200 flex items-start justify-between gap-3 bg-gray-50/50">
          <div>
            <h2 id="judul-drilldown-kegagalan" className="text-lg font-bold text-gray-900">
              {labelAlasanGagal(reasonCode)}
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {cakupan} · kegagalan belum ditangani dan diproses ulang
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded-lg hover:bg-gray-100"
            title="Tutup"
            aria-label="Tutup"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1 space-y-3">
          {keadaan.status === 'loading' && (
            <div className="py-10 flex items-center justify-center gap-2 text-sm text-gray-500">
              <Loader2 size={18} className="animate-spin text-red-700" />
              Memuat daftar kegagalan…
            </div>
          )}

          {keadaan.status === 'galat' && (
            <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-lg border border-gray-200 bg-gray-50 text-sm text-gray-600" data-galat-drilldown>
              <span className="flex items-center gap-1.5">
                <Info size={14} className="text-gray-400 shrink-0" />
                <span><strong className="text-gray-800">{keadaan.galat.judul}.</strong> {keadaan.galat.pesan}</span>
              </span>
              {keadaan.galat.bisaCobaLagi && (
                <button type="button" onClick={cobaLagi} className="inline-flex items-center gap-1 text-xs font-semibold text-red-700 hover:underline shrink-0">
                  <RefreshCw size={12} /> Coba lagi
                </button>
              )}
            </div>
          )}

          {keadaan.status === 'sukses' && (
            keadaan.hasil.items.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-500">
                Tidak ada kegagalan aktif dengan alasan ini. Data mungkin sudah ditangani sejak corong dihitung.
              </p>
            ) : (
              <>
                {keadaan.hasil.total > keadaan.hasil.items.length && (
                  <p className="text-xs text-gray-500" data-cakupan-daftar>
                    Menampilkan {keadaan.hasil.items.length} dari {keadaan.hasil.total} (maks. {BATAS_DRILLDOWN} per status tindak lanjut).
                  </p>
                )}
                <ul className="divide-y divide-gray-100 border border-gray-200 rounded-lg">
                  {keadaan.hasil.items.map((f) => (
                    <li key={f.id} className="px-4 py-3 space-y-1" data-kegagalan={f.id}>
                      <div className="flex items-start justify-between gap-3">
                        <span className="text-sm font-semibold text-gray-900 break-all">{f.original_filename || '-'}</span>
                        <span className={`px-2 py-0.5 rounded-full text-[11px] border shrink-0 ${getFollowUpStatusBadgeClass(f.follow_up_status)}`}>
                          {getFollowUpStatusLabel(f.follow_up_status)}
                        </span>
                      </div>
                      <p className="text-xs text-gray-600">
                        <span className="font-medium text-gray-700">{labelAlasanGagal(f.reason_code)}</span>
                        {f.message ? <> · {f.message}</> : null}
                      </p>
                      <p className="text-[11px] text-gray-400">{formatTanggal(f.created_at)}</p>
                    </li>
                  ))}
                </ul>
              </>
            )
          )}
        </div>

        <div className="px-6 py-3 border-t border-gray-200 flex justify-end bg-gray-50/50">
          <Link
            to="/ingest?tab=riwayat"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-red-700 hover:underline"
          >
            Kelola di Antrean Kegagalan <ExternalLink size={12} />
          </Link>
        </div>
      </div>
    </div>
  );
}
