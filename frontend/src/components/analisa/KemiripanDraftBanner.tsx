import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ChevronDown, ChevronRight, Copy, Info, Loader2, RefreshCw } from 'lucide-react';
import {
  formatPersen,
  formatTanggalUnggah,
  getKemiripanDraft,
  isSedangDiproses,
  pesanGalatKemiripan,
  potongJudul,
} from '../../lib/kemiripanApi';
import type { DraftKemiripanResponse, DraftMiripItem, PesanKemiripan } from '../../lib/kemiripanApi';
import { DraftLabel } from '../DraftLabel';

/** 409 (teks masih diekstrak): coba lagi tiap 3 detik, maksimal 10 kali */
const INTERVAL_POLLING_MS = 3000;
const MAKS_POLLING = 10;

type Keadaan =
  | { status: 'loading' }
  | { status: 'diproses'; percobaan: number }
  | { status: 'diproses_habis' }
  | { status: 'galat'; galat: PesanKemiripan }
  | { status: 'sukses'; data: DraftKemiripanResponse };

export interface KemiripanDraftBannerProps {
  documentId: number;
}

function namaDraft(d: DraftMiripItem): string {
  const judul = potongJudul(d.judul);
  return judul ? judul : `draft #${d.document_id}`;
}

/** Redaksi sesuai status draft_mirip; bagian tanggal dihilangkan bila diunggah kosong */
function kalimatMirip(d: DraftMiripItem): string {
  const nama = namaDraft(d);
  const tanggal = formatTanggalUnggah(d.diunggah);
  const sufiksTanggal = tanggal ? ` (${tanggal})` : '';
  return d.status === 'identik'
    ? `Identik dengan draft ${nama}${sufiksTanggal}: teks ${formatPersen(d.persen, { potong: true })}% sama`
    : `Mirip ${formatPersen(d.persen)}% dengan draft ${nama}${sufiksTanggal}`;
}

export default function KemiripanDraftBanner({ documentId }: KemiripanDraftBannerProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [keadaan, setKeadaan] = useState<Keadaan>({ status: 'loading' });
  const [putaran, setPutaran] = useState(0);
  const [daftarTerbuka, setDaftarTerbuka] = useState(false);
  const [perPasalTerbuka, setPerPasalTerbuka] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | null = null;
    let percobaan = 0;

    const jalankan = async () => {
      timer = null;
      try {
        const data = await getKemiripanDraft(documentId, { signal: controller.signal });
        if (!controller.signal.aborted) setKeadaan({ status: 'sukses', data });
      } catch (err: unknown) {
        if (controller.signal.aborted || (err instanceof Error && err.name === 'AbortError')) return;
        if (isSedangDiproses(err)) {
          if (percobaan < MAKS_POLLING) {
            percobaan += 1;
            setKeadaan({ status: 'diproses', percobaan });
            timer = setTimeout(() => void jalankan(), INTERVAL_POLLING_MS);
          } else {
            setKeadaan({ status: 'diproses_habis' });
          }
          return;
        }
        setKeadaan({ status: 'galat', galat: pesanGalatKemiripan(err) });
      }
    };

    // Ditunda satu tick: pada mount-unmount-mount StrictMode, cleanup membatalkan timer
    // sebelum request terkirim sehingga tidak ada fetch ganda.
    timer = setTimeout(() => void jalankan(), 0);

    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [documentId, putaran]);

  const cobaLagi = () => {
    setKeadaan({ status: 'loading' });
    setPutaran((p) => p + 1);
  };

  const bukaDraft = (id: number) => {
    const mode = searchParams.get('mode') === 'ai' ? 'ai' : 'deterministik';
    setSearchParams({ documentId: String(id), mode });
  };

  const wadah = 'rounded-xl border px-4 py-2.5 text-xs';

  if (keadaan.status === 'loading' || keadaan.status === 'diproses') {
    return (
      <div className={`${wadah} border-gray-200 bg-white text-gray-500 flex items-center gap-2`}>
        <Loader2 size={13} className="animate-spin text-gray-400 shrink-0" />
        <span>
          {keadaan.status === 'loading'
            ? 'Memeriksa kemiripan dengan draft lain…'
            : `Draft sedang diproses, memeriksa ulang kemiripan (percobaan ${keadaan.percobaan}/${MAKS_POLLING})…`}
        </span>
      </div>
    );
  }

  if (keadaan.status === 'diproses_habis') {
    return (
      <div className={`${wadah} border-gray-200 bg-white text-gray-600 flex items-center justify-between gap-2`}>
        <span>Draft sedang diproses. Kemiripan draft belum dapat dihitung.</span>
        <button type="button" onClick={cobaLagi} className="inline-flex items-center gap-1 font-semibold text-red-700 hover:underline cursor-pointer shrink-0">
          <RefreshCw size={11} /> Coba lagi
        </button>
      </div>
    );
  }

  if (keadaan.status === 'galat') {
    const { galat } = keadaan;
    return galat.jenis === 'netral' ? (
      <p className="px-1 text-[11px] text-gray-500 flex items-center gap-1.5">
        <Info size={12} className="shrink-0" /> {galat.pesan}
      </p>
    ) : (
      <div className={`${wadah} border-gray-200 bg-white text-gray-600 flex items-center justify-between gap-2`}>
        <span className="flex items-center gap-1.5">
          <Info size={12} className="text-gray-400 shrink-0" />
          <span><strong className="font-semibold text-gray-700">{galat.judul}.</strong> {galat.pesan}</span>
        </span>
        <button type="button" onClick={cobaLagi} className="inline-flex items-center gap-1 font-semibold text-red-700 hover:underline cursor-pointer shrink-0">
          <RefreshCw size={11} /> Coba lagi
        </button>
      </div>
    );
  }

  const { data } = keadaan;
  const ambang = formatPersen(data.ambang);
  const mirip = Array.isArray(data.draft_mirip) ? [...data.draft_mirip].sort((a, b) => b.persen - a.persen) : [];
  const teratas = mirip[0] ?? null;
  const lainnya = mirip.slice(1);
  const perPasal = data.per_pasal ?? null;
  const catatan = typeof data.catatan === 'string' && data.catatan.trim() !== '' ? data.catatan.trim() : null;

  // Tidak ada draft yang melewati ambang: teks netral kecil
  if (!teratas) {
    return (
      <p className="px-1 text-[11px] text-gray-500 flex items-center gap-1.5">
        <Info size={12} className="shrink-0" />
        {data.terdekat
          ? `Tidak ada draft yang mirip di atas ambang ${ambang}%. Draft terdekat: draft #${data.terdekat.document_id} (${formatPersen(data.terdekat.persen)}%).`
          : `Belum ada draft lain yang dapat dibandingkan (${data.dibandingkan ?? 0} draft diperiksa).`}
      </p>
    );
  }

  const identik = teratas.status === 'identik';
  const nadaBanner = identik ? 'border-red-200 bg-red-50/60 text-red-900' : 'border-amber-200 bg-amber-50/60 text-amber-900';
  const berubah = perPasal ? perPasal.pasal.filter((p) => p.status === 'berubah') : [];
  const baru = perPasal ? perPasal.pasal.filter((p) => p.status === 'baru').map((p) => p.pasal) : [];
  const dihapus = perPasal ? perPasal.pasal.filter((p) => p.status === 'dihapus').map((p) => p.pasal) : [];

  return (
    <div className={`${wadah} ${nadaBanner} space-y-2`}>
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
        <div className="flex items-start gap-2 min-w-0">
          <Copy size={14} className="shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="font-semibold leading-snug" title={teratas.judul}>{kalimatMirip(teratas)}</p>
            <p className="text-[10px] opacity-80">di atas ambang {ambang}%</p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <DraftLabel ukuran="kecil" />
          <button
            type="button"
            onClick={() => bukaDraft(teratas.document_id)}
            className="px-2.5 py-1 rounded-md bg-white border border-gray-200 font-semibold hover:bg-gray-50 transition cursor-pointer"
          >
            Buka hasil draft ini
          </button>
        </div>
      </div>

      {lainnya.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setDaftarTerbuka((v) => !v)}
            aria-expanded={daftarTerbuka}
            className="inline-flex items-center gap-1 text-[11px] font-semibold hover:underline cursor-pointer"
          >
            {daftarTerbuka ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {daftarTerbuka ? 'Sembunyikan' : 'Lihat'} {lainnya.length} draft mirip lainnya
          </button>
          {daftarTerbuka && (
            <ul className="mt-1.5 space-y-1">
              {lainnya.map((d) => (
                <li key={d.document_id} className="flex items-center justify-between gap-2 bg-white/60 rounded-md px-2 py-1">
                  <span className="min-w-0 truncate" title={d.judul}>{kalimatMirip(d)}</span>
                  <button type="button" onClick={() => bukaDraft(d.document_id)} className="text-[11px] font-semibold hover:underline cursor-pointer shrink-0">
                    Buka hasil draft ini
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {perPasal ? (
        <div>
          <button
            type="button"
            onClick={() => setPerPasalTerbuka((v) => !v)}
            aria-expanded={perPasalTerbuka}
            className="inline-flex items-center gap-1 text-[11px] font-semibold hover:underline cursor-pointer"
          >
            {perPasalTerbuka ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Rincian per pasal (dibandingkan dengan draft #{perPasal.dibanding_dengan})
          </button>
          {perPasalTerbuka && (
            <div className="mt-1.5 bg-white/70 rounded-md p-2 space-y-1.5 text-gray-700">
              <p className="text-[11px]">
                Sama <strong>{perPasal.ringkas.sama}</strong> · Berubah <strong>{perPasal.ringkas.berubah}</strong> · Baru{' '}
                <strong>{perPasal.ringkas.baru}</strong> · Dihapus <strong>{perPasal.ringkas.dihapus}</strong>
              </p>
              {berubah.length > 0 && (
                <ul className="text-[11px] space-y-0.5">
                  {berubah.map((p) => (
                    <li key={p.pasal} className="flex justify-between gap-2">
                      <span>{p.pasal}</span>
                      <span className="font-mono text-gray-500">{typeof p.persen === 'number' ? `${formatPersen(p.persen)}% sama` : 'berubah'}</span>
                    </li>
                  ))}
                </ul>
              )}
              {baru.length > 0 && <p className="text-[11px]">Pasal baru: {baru.join(', ')}</p>}
              {dihapus.length > 0 && <p className="text-[11px]">Pasal dihapus: {dihapus.join(', ')}</p>}
            </div>
          )}
        </div>
      ) : catatan ? (
        <p className="text-[11px] opacity-80 flex items-center gap-1.5">
          <Info size={11} className="shrink-0" /> {catatan}
        </p>
      ) : null}
    </div>
  );
}
