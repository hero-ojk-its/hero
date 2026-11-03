import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ChevronRight,
  Download,
  Filter,
  Info,
  Loader2,
  RefreshCw,
  FileText,
  CheckCircle2,
  AlertTriangle,
  Layers,
  ArrowDownToLine,
  Database,
  Binary
} from 'lucide-react';
import {
  cekDukunganTanpaSumber,
  formatDihitungPada,
  getDashboardCorong,
  persenTerhadap,
  pesanGalatCorong,
  unduhCorongCsv,
} from '../../lib/corongApi';
import type { CorongBlok, CorongScan, DashboardCorongResponse, PesanGalatCorong } from '../../lib/corongApi';
import { formatKodeTakDikenal, labelAlasanGagal } from '../../lib/labelStatus';
import { JENIS_SUMBER_LABELS } from '../../pages/ingest/labels';
import DrilldownKegagalanModal from './DrilldownKegagalanModal';

interface Drilldown {
  reasonCode: string;
  sourceId: number | null;
  /** Unggah manual: ?tanpa_sumber=true (hanya bila backend mendukung) */
  tanpaSumber: boolean;
  cakupan: string;
}

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


export default function CorongIngestCard() {
  const [keadaan, setKeadaan] = useState<Keadaan>({ status: 'loading' });
  const [putaran, setPutaran] = useState(0);
  const [pilihan, setPilihan] = useState<Pilihan>('total');

  useEffect(() => {
    const controller = new AbortController();
    // Ditunda satu tick: pada mount-unmount-mount StrictMode, cleanup membatalkan timer
    // sebelum request terkirim sehingga tidak ada fetch ganda.
    const timer = setTimeout(() => {
      // Mount pertama memakai cache backend (60 detik); "Muat ulang" / "Coba lagi" meminta data segar
      getDashboardCorong({ signal: controller.signal, segar: putaran > 0 })
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

  const [drilldown, setDrilldown] = useState<Drilldown | null>(null);
  const tutupDrilldown = useCallback(() => setDrilldown(null), []);

  // null = belum diketahui; probe hanya saat tampilan "Unggah manual" punya kegagalan (hasil di-cache per sesi)
  const [dukungTanpaSumber, setDukungTanpaSumber] = useState<boolean | null>(null);
  const perluProbe =
    keadaan.status === 'sukses' && pilihan === 'manual' && Object.keys(keadaan.data.unggah_manual.gagal_per_alasan).length > 0;
  useEffect(() => {
    if (!perluProbe) return;
    let aktif = true;
    void cekDukunganTanpaSumber().then((ya) => {
      if (aktif) setDukungTanpaSumber(ya);
    });
    return () => {
      aktif = false;
    };
  }, [perluProbe]);

  const [mengunduhCsv, setMengunduhCsv] = useState(false);
  const [galatCsv, setGalatCsv] = useState<PesanGalatCorong | null>(null);
  const csvController = useRef<AbortController | null>(null);
  useEffect(() => () => csvController.current?.abort(), []);

  const unduhCsv = async () => {
    csvController.current?.abort();
    const controller = new AbortController();
    csvController.current = controller;
    setMengunduhCsv(true);
    setGalatCsv(null);
    try {
      const { blob, namaBerkas } = await unduhCorongCsv({ signal: controller.signal });
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = namaBerkas;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (err: unknown) {
      if (controller.signal.aborted || (err instanceof Error && err.name === 'AbortError')) return;
      setGalatCsv(pesanGalatCorong(err));
    } finally {
      if (!controller.signal.aborted) setMengunduhCsv(false);
    }
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
          {data && (
            <p className="text-[10px] text-gray-400 mt-0.5" data-catatan-cache>
              Data di-cache hingga 60 detik; "Muat ulang" menghitung ulang.
            </p>
          )}
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
          {data && (
            <button
              type="button"
              onClick={() => void unduhCsv()}
              disabled={mengunduhCsv}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-300 bg-white text-xs font-semibold text-gray-700 hover:bg-gray-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {mengunduhCsv ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
              {mengunduhCsv ? 'Mengunduh…' : 'Unduh CSV'}
            </button>
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

      {galatCsv && (
        <p className="flex items-center gap-1.5 text-xs text-red-700" data-galat-csv>
          <Info size={12} className="shrink-0" />
          Gagal mengunduh CSV: {galatCsv.pesan}
        </p>
      )}

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
        <ResumeCorong
          terpilih={terpilih}
          jumlahSumber={data?.sumber.length ?? 0}
          dukungTanpaSumber={dukungTanpaSumber === true}
          onPilihAlasan={(reasonCode) =>
            setDrilldown({
              reasonCode,
              sourceId: terpilih.sourceId,
              tanpaSumber: terpilih.jenis === 'manual',
              cakupan: terpilih.judul,
            })
          }
        />
      ))}

      {drilldown && (
        <DrilldownKegagalanModal
          reasonCode={drilldown.reasonCode}
          sourceId={drilldown.sourceId}
          tanpaSumber={drilldown.tanpaSumber}
          cakupan={drilldown.cakupan}
          onClose={tutupDrilldown}
        />
      )}
    </section>
  );
}

interface ResumeCorongProps {
  terpilih: BlokTerpilih;
  jumlahSumber: number;
  /** Backend terbukti mendukung ?tanpa_sumber=true (probe 422) */
  dukungTanpaSumber: boolean;
  onPilihAlasan: (reasonCode: string) => void;
}

function ResumeCorong({ terpilih, jumlahSumber, dukungTanpaSumber, onPilihAlasan }: ResumeCorongProps) {
  // Unggah manual hanya bisa ditelusuri bila backend mendukung tanpa_sumber (backend lama mengabaikannya)
  const bisaDitelusuri = terpilih.jenis !== 'manual' || dukungTanpaSumber;
  const { blok, scan } = terpilih;
  const d = blok.dokumen;
  const pTerbaca = persenTerhadap(d.terbaca, d.di_kb);
  const pPasal = persenTerhadap(d.terpecah_pasal, d.terbaca);
  const pVektor = persenTerhadap(d.tervektor, d.terpecah_pasal);
  const pDitarik = scan ? persenTerhadap(scan.ditarik, scan.ditemukan) : null;
  const adaLebih100 = [pTerbaca, pPasal, pVektor, pDitarik].some((p) => typeof p === 'number' && p > 100);
  const alasan = Object.entries(blok.gagal_per_alasan).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-6">
      {/* TIGA KELOMPOK MONITORING UTAMA */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 items-stretch">

        {/* =================================================================== */}
        {/* KELOMPOK 1: SUMBER & AKUISISI DOKUMEN */}
        {/* =================================================================== */}
        <div className="bg-gray-50/60 rounded-xl border border-gray-200/80 p-4 flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between pb-2 border-b border-gray-200/70">
              <span className="text-[11px] font-bold text-gray-700 tracking-wider uppercase flex items-center gap-1.5">
                <Layers size={13} className="text-gray-500" />
                1. Sumber & Akuisisi
              </span>
              {scan && typeof pDitarik === 'number' && (
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                  {FORMAT_PERSEN.format(pDitarik)}% Ditarik
                </span>
              )}
            </div>

            {scan ? (
              <div className="mt-3.5 space-y-3.5">
                {/* Metrik Utama yang Menonjol: Ditemukan & Ditarik */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-white p-3 rounded-lg border border-gray-200/90 shadow-2xs">
                    <span className="text-[11px] font-medium text-gray-500 block">Ditemukan</span>
                    <span className="text-2xl font-bold text-gray-900 tracking-tight mt-0.5 block" data-nilai>
                      {angka(scan.ditemukan)}
                    </span>
                    <span className="text-[10px] text-gray-400">Total terdeteksi</span>
                  </div>
                  <div className="bg-white p-3 rounded-lg border border-gray-200/90 shadow-2xs">
                    <span className="text-[11px] font-medium text-blue-700 block">Ditarik</span>
                    <span className="text-2xl font-bold text-blue-700 tracking-tight mt-0.5 block" data-nilai>
                      {angka(scan.ditarik)}
                    </span>
                    <span className="text-[10px] text-gray-400">Berhasil diunduh</span>
                  </div>
                </div>

                {/* Status Tambahan Akuisisi */}
                <div className="space-y-1.5 pt-1">
                  <div className="flex items-center justify-between text-xs px-2.5 py-1.5 rounded-md bg-white border border-gray-200/70">
                    <span className="text-gray-600 font-medium">Sudah ada di KB</span>
                    <span className="font-semibold text-gray-800">{angka(scan.sudah_ada_di_kb)}</span>
                  </div>
                  <div className="flex items-center justify-between text-xs px-2.5 py-1.5 rounded-md bg-white border border-gray-200/70">
                    <span className="text-gray-600 font-medium">Duplikat</span>
                    <span className="font-semibold text-gray-800">{angka(scan.duplikat)}</span>
                  </div>
                  <div className="flex items-center justify-between text-xs px-2.5 py-1.5 rounded-md bg-white border border-gray-200/70">
                    <span className="text-gray-600 font-medium">Belum ditarik</span>
                    <span className={`font-semibold ${scan.belum_ditarik > 0 ? 'text-amber-700' : 'text-gray-700'}`}>
                      {angka(scan.belum_ditarik)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs px-2.5 py-1.5 rounded-md bg-white border border-gray-200/70">
                    <span className="text-gray-600 font-medium">Gagal unduh</span>
                    <span className={`font-semibold ${scan.gagal_unduh > 0 ? 'text-rose-700' : 'text-gray-700'}`}>
                      {angka(scan.gagal_unduh)}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-4 p-4 rounded-lg bg-white border border-gray-200 text-center space-y-1.5">
                <ArrowDownToLine size={20} className="text-gray-400 mx-auto" />
                <p className="text-xs font-semibold text-gray-800">Unggah Manual Langsung</p>
                <p className="text-[11px] text-gray-500 leading-relaxed">
                  Dokumen dimasukkan langsung oleh analis tanpa melalui proses pemindaian crawler.
                </p>
                <div className="pt-2">
                  <span className="inline-block px-2.5 py-1 rounded-md bg-gray-100 text-gray-700 text-xs font-medium border border-gray-200">
                    {angka(d.di_kb)} Dokumen Masuk
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* =================================================================== */}
        {/* KELOMPOK 2: PENGOLAHAN DOKUMEN */}
        {/* =================================================================== */}
        <div className="bg-gray-50/60 rounded-xl border border-gray-200/80 p-4 flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between pb-2 border-b border-gray-200/70">
              <span className="text-[11px] font-bold text-gray-700 tracking-wider uppercase flex items-center gap-1.5">
                <Database size={13} className="text-gray-500" />
                2. Pengolahan Dokumen
              </span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                {FORMAT_PERSEN.format(blok.persen_terbaca)}% Terbaca
              </span>
            </div>

            <div className="mt-3.5 space-y-2.5">
              {/* Metrik 1: Di KB */}
              <div className="bg-white p-3 rounded-lg border border-gray-200/90 shadow-2xs flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-gray-700 block">Di Knowledge Base</span>
                  <span className="text-[11px] text-gray-500">Tersimpan di pangkalan data</span>
                </div>
                <span className="text-xl font-bold text-gray-900 tracking-tight" data-nilai>
                  {angka(d.di_kb)}
                </span>
              </div>

              {/* Metrik 2: Terbaca */}
              <div className="bg-white p-3 rounded-lg border border-gray-200/90 shadow-2xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-emerald-500" />
                    <span className="text-xs font-semibold text-gray-900">Terbaca</span>
                  </div>
                  <span className="text-xl font-bold text-emerald-700 tracking-tight" data-nilai>
                    {angka(d.terbaca)}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between text-[11px] text-gray-500 pt-1 border-t border-gray-100">
                  <span>Teks langsung: <strong className="text-gray-700">{angka(d.terbaca_teks_langsung)}</strong></span>
                  <span>OCR: <strong className="text-gray-700">{angka(d.terbaca_ocr)}</strong></span>
                </div>
              </div>

              {/* Metrik 3: Terpecah Pasal */}
              <div className="bg-white p-3 rounded-lg border border-gray-200/90 shadow-2xs flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-gray-700 block">Terpecah Pasal</span>
                  <span className="text-[11px] text-gray-500">Struktur batang tubuh siap</span>
                </div>
                <span className="text-xl font-bold text-gray-900 tracking-tight" data-nilai>
                  {angka(d.terpecah_pasal)}
                </span>
              </div>

              {/* Metrik 4: Tervektor */}
              <div className="bg-white p-3 rounded-lg border border-gray-200/90 shadow-2xs flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Binary size={14} className="text-indigo-600" />
                  <div>
                    <span className="text-xs font-semibold text-gray-900 block">Tervektor</span>
                    <span className="text-[11px] text-gray-500">Embedding semantik</span>
                  </div>
                </div>
                <span className="text-xl font-bold text-indigo-700 tracking-tight" data-nilai>
                  {angka(d.tervektor)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* =================================================================== */}
        {/* KELOMPOK 3: STATUS & PENGECUALIAN */}
        {/* =================================================================== */}
        <div className="bg-gray-50/60 rounded-xl border border-gray-200/80 p-4 flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between pb-2 border-b border-gray-200/70">
              <span className="text-[11px] font-bold text-gray-700 tracking-wider uppercase flex items-center gap-1.5">
                <AlertTriangle size={13} className="text-gray-500" />
                3. Status & Pengecualian
              </span>
              {alasan.length > 0 && (
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200">
                  {alasan.length} Kategori Galat
                </span>
              )}
            </div>

            <div className="mt-3.5 space-y-2">
              {/* Ringkasan Status Dokumen */}
              <div className="grid grid-cols-3 gap-2">
                <div className="bg-white p-2.5 rounded-lg border border-amber-200/80 shadow-2xs text-center">
                  <span className="text-[10px] font-medium text-amber-700 block truncate">Menunggu</span>
                  <span className="text-base font-bold text-amber-800 tracking-tight mt-0.5 block">
                    {angka(d.menunggu_ekstraksi)}
                  </span>
                </div>
                <div className="bg-white p-2.5 rounded-lg border border-amber-200/80 shadow-2xs text-center">
                  <span className="text-[10px] font-medium text-amber-700 block truncate">Koreksi</span>
                  <span className="text-base font-bold text-amber-800 tracking-tight mt-0.5 block">
                    {angka(d.perlu_koreksi)}
                  </span>
                </div>
                <div className="bg-white p-2.5 rounded-lg border border-rose-200/80 shadow-2xs text-center">
                  <span className="text-[10px] font-medium text-rose-700 block truncate">Gagal Baca</span>
                  <span className="text-base font-bold text-rose-800 tracking-tight mt-0.5 block">
                    {angka(d.gagal_baca)}
                  </span>
                </div>
              </div>

              {/* Rincian Gagal Per Alasan (Drilldown) */}
              <div className="pt-2">
                <span className="text-[11px] font-bold text-gray-500 tracking-wider uppercase block mb-1.5">
                  Gagal Per Alasan
                </span>
                {alasan.length === 0 ? (
                  <div className="p-3 bg-white rounded-lg border border-gray-200/70 text-center">
                    <CheckCircle2 size={16} className="text-emerald-600 mx-auto mb-1" />
                    <p className="text-xs font-semibold text-gray-800">Tidak ada kegagalan aktif</p>
                    <p className="text-[11px] text-gray-400">Seluruh dokumen terproses tanpa kendala</p>
                  </div>
                ) : (
                  <ul className="space-y-1.5 max-h-[160px] overflow-y-auto pr-1">
                    {alasan.map(([kode, jumlah]) => (
                      <li key={kode} data-alasan={kode}>
                        {bisaDitelusuri ? (
                          <button
                            type="button"
                            onClick={() => onPilihAlasan(kode)}
                            className="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg bg-white border border-gray-200 text-xs text-left hover:border-red-300 hover:bg-red-50/40 transition group cursor-pointer shadow-2xs"
                            title="Klik untuk meninjau rincian dokumen gagal"
                          >
                            <span className="text-gray-700 group-hover:text-red-800 truncate font-medium">
                              {labelAlasanGagal(kode)}
                            </span>
                            <span className="flex items-center gap-1 font-bold text-gray-900 group-hover:text-red-700 shrink-0" data-jumlah>
                              {angka(jumlah)}
                              <ChevronRight size={13} className="text-gray-400 group-hover:text-red-700" />
                            </span>
                          </button>
                        ) : (
                          <div className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg bg-white border border-gray-200 text-xs shadow-2xs">
                            <span className="text-gray-700 truncate font-medium">{labelAlasanGagal(kode)}</span>
                            <span className="font-bold text-gray-900 shrink-0" data-jumlah>{angka(jumlah)}</span>
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
                {!bisaDitelusuri && alasan.length > 0 && (
                  <p className="mt-2 text-[10px] text-gray-500" data-keterangan-manual>
                    Rincian kegagalan unggah manual dapat ditinjau langsung pada Antrean Kegagalan di tab Ingest.
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* =================================================================== */}
      {/* BAGIAN BAWAH: DETAIL PEMERIKSAAN PDF (INLINE) */}
      {/* =================================================================== */}
      <div className="bg-gray-50/70 border border-gray-200/80 rounded-xl p-4 space-y-3" data-panel="pdf">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-bold text-gray-800 tracking-tight flex items-center gap-1.5 uppercase">
            <FileText size={14} className="text-red-700" />
            Detail Pemeriksaan PDF
          </h4>
          <span className="text-[11px] text-gray-500 font-medium">
            Status inspeksi berkas & kesiapan OCR
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <div className="bg-white p-2.5 rounded-lg border border-gray-200/70 shadow-2xs">
            <span className="text-[11px] text-gray-500 block truncate">Terproteksi</span>
            <span className="text-lg font-bold text-gray-900 tracking-tight block mt-0.5">
              {angka(blok.pdf.terproteksi)}
            </span>
          </div>

          <div className="bg-white p-2.5 rounded-lg border border-gray-200/70 shadow-2xs">
            <span className="text-[11px] text-gray-500 block truncate">Terproteksi Terbaca</span>
            <span className={`text-lg font-bold tracking-tight block mt-0.5 ${blok.pdf.terproteksi_terbaca > 0 ? 'text-emerald-700' : 'text-gray-900'}`}>
              {angka(blok.pdf.terproteksi_terbaca)}
            </span>
          </div>

          <div className="bg-white p-2.5 rounded-lg border border-gray-200/70 shadow-2xs">
            <span className="text-[11px] text-gray-500 block truncate">Belum Diperiksa</span>
            <span className="text-lg font-bold text-gray-900 tracking-tight block mt-0.5">
              {angka(blok.pdf.belum_diperiksa)}
            </span>
          </div>

          <div className="bg-white p-2.5 rounded-lg border border-gray-200/70 shadow-2xs">
            <span className="text-[11px] text-gray-500 block truncate">Hasil Pindai (OCR)</span>
            <span className="text-lg font-bold text-blue-700 tracking-tight block mt-0.5">
              {angka(blok.pdf.hasil_pindai_ocr)}
            </span>
          </div>

          <div className="bg-white p-2.5 rounded-lg border border-gray-200/70 shadow-2xs">
            <span className="text-[11px] text-gray-500 block truncate">OCR Gagal</span>
            <span className={`text-lg font-bold tracking-tight block mt-0.5 ${blok.pdf.ocr_gagal > 0 ? 'text-rose-700' : 'text-gray-900'}`}>
              {angka(blok.pdf.ocr_gagal)}
            </span>
          </div>
        </div>
      </div>

      {/* CATATAN DAN KETERANGAN PERHITUNGAN */}
      <div className="space-y-1 text-[11px] text-gray-500 pt-1">
        {adaLebih100 && (
          <p className="flex items-center gap-1.5">
            <Info size={12} className="shrink-0 text-gray-400" />
            Persen tiap tahap dihitung terpisah, bisa melebihi 100%.
          </p>
        )}
        {terpilih.jenis === 'total' && jumlahSumber > 0 && (
          <p className="flex items-center gap-1.5">
            <Info size={12} className="shrink-0 text-gray-400" />
            Jumlah semua sumber tidak sama dengan Total: satu dokumen bisa tercatat di beberapa sumber.
          </p>
        )}
      </div>
    </div>
  );
}
