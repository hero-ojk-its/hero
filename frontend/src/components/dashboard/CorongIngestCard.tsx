import { useEffect, useState } from 'react';
import { Filter, Info, Loader2, RefreshCw } from 'lucide-react';
import {
  formatDihitungPada,
  getDashboardCorong,
  persenTerhadap,
  pesanGalatCorong,
} from '../../lib/corongApi';
import type { CorongBlok, CorongScan, DashboardCorongResponse, PesanGalatCorong } from '../../lib/corongApi';
import { formatKodeTakDikenal, labelAlasanGagal } from '../../lib/labelStatus';
import { JENIS_SUMBER_LABELS } from '../../pages/ingest/labels';

type Keadaan =
  | { status: 'loading' }
  | { status: 'galat'; galat: PesanGalatCorong }
  | { status: 'sukses'; data: DashboardCorongResponse };

/** 'total' | 'manual' | `sumber:<source_id>` */
type Pilihan = string;

interface BlokTerpilih {
  judul: string;
  blok: CorongBlok;
  /** null untuk unggah manual (tidak punya tahap scan) */
  scan: CorongScan | null;
  jenis: 'total' | 'sumber' | 'manual';
  sourceId: number | null;
}

const FORMAT_ANGKA = new Intl.NumberFormat('id-ID');
const FORMAT_PERSEN = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 1 });
const angka = (n: number) => FORMAT_ANGKA.format(n);

function labelJenisSumber(jenis: string): string {
  return JENIS_SUMBER_LABELS[jenis] ?? formatKodeTakDikenal(jenis);
}

function pilihBlok(data: DashboardCorongResponse, pilihan: Pilihan): BlokTerpilih {
  if (pilihan === 'manual') {
    return { judul: 'Unggah manual', blok: data.unggah_manual, scan: null, jenis: 'manual', sourceId: null };
  }
  if (pilihan.startsWith('sumber:')) {
    const id = Number(pilihan.slice('sumber:'.length));
    const s = data.sumber.find((x) => x.source_id === id);
    if (s) return { judul: s.nama, blok: s, scan: s.scan, jenis: 'sumber', sourceId: s.source_id };
  }
  return { judul: 'Total', blok: data.total, scan: data.total.scan, jenis: 'total', sourceId: null };
}

function kosong(b: BlokTerpilih): boolean {
  const g = Object.values(b.blok.gagal_per_alasan).reduce((n, x) => n + x, 0);
  return (b.scan?.ditemukan ?? 0) === 0 && b.blok.dokumen.di_kb === 0 && g === 0 && b.blok.pdf.terproteksi === 0;
}

interface LangkahProps {
  label: string;
  nilai: number;
  /** Persen terhadap tahap sebelumnya; undefined = tahap pertama */
  persen?: number | null;
  rincian?: string;
}

function Langkah({ label, nilai, persen, rincian }: LangkahProps) {
  const lebar = typeof persen === 'number' ? Math.min(100, Math.max(0, persen)) : 100;
  return (
    <li className="space-y-1" data-langkah={label}>
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="font-semibold text-gray-700">{label}</span>
        <span className="flex items-baseline gap-2">
          <span className="text-sm font-bold text-gray-900" data-nilai>{angka(nilai)}</span>
          {persen !== undefined && (
            <span className="text-[11px] font-mono text-gray-500 w-14 text-right" data-persen>
              {persen === null ? '–' : `${FORMAT_PERSEN.format(persen)}%`}
            </span>
          )}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
        <div className="h-full rounded-full bg-red-700/80" style={{ width: `${lebar}%` }} data-batang={lebar} />
      </div>
      {rincian && <p className="text-[10px] text-gray-500">{rincian}</p>}
    </li>
  );
}

function Rincian({ isi }: { isi: Array<[string, number]> }) {
  return (
    <div className="flex flex-wrap gap-1.5 pt-1">
      {isi.map(([label, nilai]) => (
        <span key={label} className="px-2 py-0.5 rounded-md bg-gray-50 border border-gray-200 text-[11px] text-gray-600">
          {label}: <strong className="text-gray-800">{angka(nilai)}</strong>
        </span>
      ))}
    </div>
  );
}

export default function CorongIngestCard() {
  const [keadaan, setKeadaan] = useState<Keadaan>({ status: 'loading' });
  const [putaran, setPutaran] = useState(0);
  const [pilihan, setPilihan] = useState<Pilihan>('total');

  useEffect(() => {
    const controller = new AbortController();
    // Ditunda satu tick: pada mount-unmount-mount StrictMode, cleanup membatalkan timer
    // sebelum request terkirim sehingga tidak ada fetch ganda.
    const timer = setTimeout(() => {
      getDashboardCorong({ signal: controller.signal })
        .then((data) => {
          if (!controller.signal.aborted) setKeadaan({ status: 'sukses', data });
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted || (err instanceof Error && err.name === 'AbortError')) return;
          setKeadaan({ status: 'galat', galat: pesanGalatCorong(err) });
        });
    }, 0);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [putaran]);

  const muatUlang = () => {
    setKeadaan({ status: 'loading' });
    setPutaran((p) => p + 1);
  };

  const data = keadaan.status === 'sukses' ? keadaan.data : null;
  const terpilih = data ? pilihBlok(data, pilihan) : null;
  const dihitung = data ? formatDihitungPada(data.dihitung_pada) : null;

  return (
    <section className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm space-y-4" aria-label="Corong ingest">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
        <div>
          <h3 className="text-base font-bold text-gray-900">Corong Ingest</h3>
          <p className="text-xs text-gray-500 mt-1">
            Dari pemindaian sumber sampai dokumen terbaca, terpecah pasal, dan tervektor
            {dihitung ? <> · Dihitung pada {dihitung}</> : null}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <label className="inline-flex items-center gap-1.5 text-xs text-gray-600">
              <Filter size={13} className="text-gray-400" />
              <span className="sr-only">Pilih sumber</span>
              <select
                value={pilihan}
                onChange={(e) => setPilihan(e.target.value)}
                className="bg-gray-50 border border-gray-300 rounded-lg px-2.5 py-1.5 text-xs text-gray-800 focus:ring-1 focus:ring-red-600 focus:outline-none max-w-[240px]"
                aria-label="Pilih sumber corong"
              >
                <option value="total">Total</option>
                {data.sumber.map((s) => (
                  <option key={s.source_id} value={`sumber:${s.source_id}`}>
                    {s.nama} · {labelJenisSumber(s.jenis)}
                  </option>
                ))}
                <option value="manual">Unggah manual</option>
              </select>
            </label>
          )}
          <button
            type="button"
            onClick={muatUlang}
            disabled={keadaan.status === 'loading'}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-300 bg-white text-xs font-semibold text-gray-700 hover:bg-gray-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw size={12} className={keadaan.status === 'loading' ? 'animate-spin' : ''} />
            Muat ulang
          </button>
        </div>
      </div>

      {keadaan.status === 'loading' && (
        <div className="flex items-center gap-2 py-8 justify-center text-xs text-gray-500">
          <Loader2 size={16} className="animate-spin text-red-700" />
          Menghitung corong ingest…
        </div>
      )}

      {keadaan.status === 'galat' && (
        <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-lg border border-gray-200 bg-gray-50 text-xs text-gray-600">
          <span className="flex items-center gap-1.5">
            <Info size={13} className="text-gray-400 shrink-0" />
            <span><strong className="text-gray-800">{keadaan.galat.judul}.</strong> {keadaan.galat.pesan}</span>
          </span>
          {keadaan.galat.bisaCobaLagi && (
            <button type="button" onClick={muatUlang} className="inline-flex items-center gap-1 font-semibold text-red-700 hover:underline shrink-0">
              <RefreshCw size={11} /> Coba lagi
            </button>
          )}
        </div>
      )}

      {terpilih && (kosong(terpilih) ? (
        <p className="py-8 text-center text-xs text-gray-500">
          Belum ada data ingest untuk {terpilih.jenis === 'total' ? 'ditampilkan' : terpilih.judul}.
        </p>
      ) : (
        <ResumeCorong terpilih={terpilih} jumlahSumber={data?.sumber.length ?? 0} />
      ))}
    </section>
  );
}

function ResumeCorong({ terpilih, jumlahSumber }: { terpilih: BlokTerpilih; jumlahSumber: number }) {
  const { blok, scan } = terpilih;
  const d = blok.dokumen;
  const pTerbaca = persenTerhadap(d.terbaca, d.di_kb);
  const pPasal = persenTerhadap(d.terpecah_pasal, d.terbaca);
  const pVektor = persenTerhadap(d.tervektor, d.terpecah_pasal);
  const pDitarik = scan ? persenTerhadap(scan.ditarik, scan.ditemukan) : null;
  const adaLebih100 = [pTerbaca, pPasal, pVektor, pDitarik].some((p) => typeof p === 'number' && p > 100);
  const alasan = Object.entries(blok.gagal_per_alasan).sort((a, b) => b[1] - a[1]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Kiri: rangkaian */}
      <div className="lg:col-span-2 space-y-5">
        {scan && (
          <div data-rangkaian="scan">
            <h4 className="text-[11px] font-bold text-gray-500 tracking-wider uppercase mb-2">Scan</h4>
            <ol className="space-y-2.5">
              <Langkah label="Ditemukan" nilai={scan.ditemukan} />
              <Langkah label="Ditarik" nilai={scan.ditarik} persen={pDitarik} />
            </ol>
            <Rincian isi={[
              ['Sudah ada di KB', scan.sudah_ada_di_kb],
              ['Duplikat', scan.duplikat],
              ['Gagal unduh', scan.gagal_unduh],
              ['Belum ditarik', scan.belum_ditarik],
            ]} />
          </div>
        )}

        <div data-rangkaian="dokumen">
          <h4 className="text-[11px] font-bold text-gray-500 tracking-wider uppercase mb-2">
            Dokumen <span className="normal-case font-medium">· persen terbaca {FORMAT_PERSEN.format(blok.persen_terbaca)}%</span>
          </h4>
          <ol className="space-y-2.5">
            <Langkah label="Di KB" nilai={d.di_kb} />
            <Langkah
              label="Terbaca"
              nilai={d.terbaca}
              persen={pTerbaca}
              rincian={`Teks langsung ${angka(d.terbaca_teks_langsung)} · OCR ${angka(d.terbaca_ocr)}`}
            />
            <Langkah label="Terpecah pasal" nilai={d.terpecah_pasal} persen={pPasal} />
            <Langkah label="Tervektor" nilai={d.tervektor} persen={pVektor} />
          </ol>
          <Rincian isi={[
            ['Menunggu ekstraksi', d.menunggu_ekstraksi],
            ['Gagal baca', d.gagal_baca],
            ['Perlu koreksi', d.perlu_koreksi],
          ]} />
        </div>

        <div className="space-y-1 text-[10px] text-gray-500">
          {adaLebih100 && (
            <p className="flex items-center gap-1"><Info size={11} /> Persen tiap tahap dihitung terpisah, bisa melebihi 100%.</p>
          )}
          {terpilih.jenis === 'total' && jumlahSumber > 0 && (
            <p className="flex items-center gap-1">
              <Info size={11} /> Jumlah semua sumber tidak sama dengan Total: satu dokumen bisa tercatat di beberapa sumber.
            </p>
          )}
        </div>
      </div>

      {/* Kanan: gagal per alasan + PDF */}
      <div className="space-y-5">
        <div data-panel="gagal">
          <h4 className="text-[11px] font-bold text-gray-500 tracking-wider uppercase mb-2">Gagal per alasan</h4>
          {alasan.length === 0 ? (
            <p className="text-xs text-gray-500">Tidak ada kegagalan aktif.</p>
          ) : (
            <ul className="space-y-1.5">
              {alasan.map(([kode, jumlah]) => (
                <li key={kode} className="flex items-center justify-between gap-2 text-xs" data-alasan={kode}>
                  <span className="text-gray-700">{labelAlasanGagal(kode)}</span>
                  <span className="font-bold text-gray-900" data-jumlah>{angka(jumlah)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div data-panel="pdf">
          <h4 className="text-[11px] font-bold text-gray-500 tracking-wider uppercase mb-2">PDF</h4>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
            {([
              ['Terproteksi', blok.pdf.terproteksi],
              ['Terproteksi terbaca', blok.pdf.terproteksi_terbaca],
              ['Belum diperiksa', blok.pdf.belum_diperiksa],
              ['Hasil pindai (OCR)', blok.pdf.hasil_pindai_ocr],
              ['OCR gagal', blok.pdf.ocr_gagal],
            ] as const).map(([label, nilai]) => (
              <div key={label} className="contents">
                <dt className="text-gray-600">{label}</dt>
                <dd className="text-right font-semibold text-gray-900">{angka(nilai)}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  );
}
