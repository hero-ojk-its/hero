import { useMemo, useState } from 'react';
import type { KeyboardEvent, MouseEvent } from 'react';
import { ExternalLink, FileText, Info, Loader2, RefreshCw } from 'lucide-react';
import { apiFetchBlob } from '../../lib/api';
import { labelTemuan, warnaTemuan, isJenisTemuan } from '../../lib/harmonisasiApi';
import type {
  HarmonisasiPembanding,
  HarmonisasiResponse,
  HarmonisasiTemuan,
  JenisTemuan,
  PesanGalat,
  WarnaTemuan,
} from '../../lib/harmonisasiApi';
import { DraftLabel } from '../DraftLabel';
import { ErrorState } from '../ErrorState';
import { EmptyState } from '../EmptyState';

/** null = harmonisasi belum dijalankan untuk dokumen ini */
export interface HarmonisasiPanelState {
  status: 'loading' | 'sukses' | 'galat';
  data: HarmonisasiResponse | null;
  galat: PesanGalat | null;
}

export interface HarmonisasiPanelProps {
  state: HarmonisasiPanelState | null;
  /** segar=true memaksa hitung ulang tanpa cache */
  onMuat: (segar: boolean) => void;
  onJumpToPasal: (pasal: string) => void;
}

const KELAS_WARNA: Record<WarnaTemuan, { badge: string; kartu: string; kartuAktif: string }> = {
  hijau: {
    badge: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    kartu: 'border-emerald-200 bg-emerald-50/50 text-emerald-900',
    kartuAktif: 'ring-2 ring-emerald-400',
  },
  biru: {
    badge: 'bg-blue-50 text-blue-800 border-blue-200',
    kartu: 'border-blue-200 bg-blue-50/50 text-blue-900',
    kartuAktif: 'ring-2 ring-blue-400',
  },
  amber: {
    badge: 'bg-amber-50 text-amber-800 border-amber-200',
    kartu: 'border-amber-200 bg-amber-50/50 text-amber-900',
    kartuAktif: 'ring-2 ring-amber-400',
  },
  merah: {
    badge: 'bg-red-50 text-red-800 border-red-200',
    kartu: 'border-red-200 bg-red-50/50 text-red-900',
    kartuAktif: 'ring-2 ring-red-400',
  },
  netral: {
    badge: 'bg-gray-100 text-gray-700 border-gray-200',
    kartu: 'border-gray-200 bg-gray-50 text-gray-800',
    kartuAktif: 'ring-2 ring-gray-400',
  },
};

/** Kartu ringkasan yang selalu tampil; konflik hanya tampil bila ada */
const KARTU_JENIS: JenisTemuan[] = ['pasal_baru', 'duplikasi', 'menggantikan', 'memperjelas'];

function teksAda(v: unknown): v is string {
  return typeof v === 'string' && v.trim() !== '';
}

/** Path PDF pembanding (relatif, tanpa hash) dan nomor halaman; null bila tidak dapat dibuka */
function targetPdf(p: HarmonisasiPembanding | null | undefined): { path: string; hash: string } | null {
  if (!p || !teksAda(p.pdf) || typeof p.document_id !== 'number') return null;
  const [path, hash] = p.pdf.split('#');
  const halaman = typeof p.halaman === 'number' && p.halaman > 0 ? `page=${p.halaman}` : '';
  return { path, hash: hash || halaman };
}

export default function HarmonisasiPanel({ state, onMuat, onJumpToPasal }: HarmonisasiPanelProps) {
  const [filterJenis, setFilterJenis] = useState<string | null>(null);
  const [pdfGalat, setPdfGalat] = useState<string | null>(null);

  const data = state?.data ?? null;
  const loading = state?.status === 'loading';
  const temuan = useMemo<HarmonisasiTemuan[]>(
    () => (Array.isArray(data?.temuan) ? data.temuan.filter((t) => t && typeof t === 'object' && teksAda(t.pasal_draft)) : []),
    [data]
  );

  // Angka kartu dihitung dari temuan yang tampil (bukan ringkasan.per_jenis, yang dihitung sebelum penyaringan akses)
  const jumlahPerJenis = useMemo(() => {
    const hitung: Record<string, number> = {};
    for (const t of temuan) hitung[t.jenis] = (hitung[t.jenis] ?? 0) + 1;
    return hitung;
  }, [temuan]);

  const kartu = [...KARTU_JENIS, ...((jumlahPerJenis.konflik ?? 0) > 0 ? (['konflik'] as JenisTemuan[]) : [])];
  const temuanTampil = filterJenis ? temuan.filter((t) => t.jenis === filterJenis) : temuan;
  const disaring = typeof data?.disaring_backend === 'number' ? data.disaring_backend : 0;
  const ringkasan = data?.ringkasan ?? null;

  const bukaPdf = (e: MouseEvent | KeyboardEvent, p: HarmonisasiPembanding | null | undefined) => {
    e.stopPropagation();
    const target = targetPdf(p);
    if (!target) return;
    setPdfGalat(null);
    // Tab dibuka saat klik agar tidak diblokir popup blocker, lalu diisi blob setelah unduhan selesai
    const tab = window.open('', '_blank');
    if (tab) tab.document.title = 'Memuat PDF…';
    apiFetchBlob(target.path)
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const tujuan = target.hash ? `${url}#${target.hash}` : url;
        if (tab && !tab.closed) tab.location.href = tujuan;
        else window.open(tujuan, '_blank');
        setTimeout(() => URL.revokeObjectURL(url), 60000);
      })
      .catch((err: unknown) => {
        if (tab && !tab.closed) tab.close();
        setPdfGalat(err instanceof Error && err.message ? `Gagal membuka PDF pembanding: ${err.message}` : 'Gagal membuka PDF pembanding.');
      });
  };

  const lompat = (pasal: string) => onJumpToPasal(pasal);
  const tombolKeyboard = (e: KeyboardEvent, pasal: string) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      lompat(pasal);
    }
  };

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-bold text-gray-900 uppercase tracking-wider truncate">Harmonisasi Draft vs Korpus</span>
          <DraftLabel ukuran="kecil" />
        </div>
        <button
          type="button"
          onClick={() => onMuat(true)}
          disabled={loading}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-gray-200 bg-white text-[11px] font-semibold text-gray-700 hover:bg-gray-50 transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
          title="Hitung ulang harmonisasi tanpa cache (segar=true)"
        >
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          <span>Hitung ulang</span>
        </button>
      </div>

      {/* Belum dijalankan */}
      {!state && (
        <EmptyState
          title="Harmonisasi belum dijalankan"
          message="Bandingkan draf ini dengan peraturan di Knowledge Base, per pasal."
          actionLabel="Jalankan harmonisasi"
          onAction={() => onMuat(false)}
        />
      )}

      {/* Loading pertama */}
      {loading && !data && (
        <div className="flex flex-col items-center justify-center gap-2 py-12 text-gray-500">
          <Loader2 size={22} className="animate-spin text-red-700" />
          <span className="text-xs font-medium">Membandingkan pasal draf dengan korpus…</span>
          <span className="text-[10px] text-gray-400">Proses ini bisa memakan waktu hingga dua menit.</span>
        </div>
      )}

      {/* Galat tanpa data */}
      {state?.status === 'galat' && !data && state.galat && (
        <ErrorState
          title={state.galat.judul}
          message={state.galat.pesan}
          retryText="Coba lagi"
          onRetry={() => onMuat(false)}
        />
      )}

      {data && (
        <>
          {loading && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-50 border border-gray-200 text-[11px] text-gray-600">
              <Loader2 size={12} className="animate-spin text-red-700" />
              <span>Menghitung ulang harmonisasi…</span>
            </div>
          )}
          {state?.status === 'galat' && state.galat && (
            <div className="px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-[11px] text-red-800">
              <strong>{state.galat.judul}.</strong> {state.galat.pesan} Hasil di bawah adalah hasil sebelumnya.
            </div>
          )}

          {/* Ringkasan korpus */}
          {ringkasan && (typeof ringkasan.pasal_draft === 'number' || typeof ringkasan.dokumen_korpus === 'number') && (
            <p className="text-[11px] text-gray-500">
              {ringkasan.pasal_draft ?? '-'} pasal draf dibandingkan dengan {ringkasan.pasal_korpus ?? '-'} pasal dari{' '}
              {ringkasan.dokumen_korpus ?? '-'} dokumen korpus.
            </p>
          )}

          {/* Kartu ringkasan per jenis (klik untuk filter) */}
          <div className="grid grid-cols-2 gap-2">
            {kartu.map((jenis) => {
              const warna = KELAS_WARNA[warnaTemuan({ jenis })];
              const aktif = filterJenis === jenis;
              return (
                <button
                  key={jenis}
                  type="button"
                  onClick={() => setFilterJenis(aktif ? null : jenis)}
                  aria-pressed={aktif}
                  className={`p-2 rounded-lg border text-left transition cursor-pointer ${warna.kartu} ${aktif ? warna.kartuAktif : 'hover:brightness-95'}`}
                >
                  <span className="text-lg font-bold block leading-none">{jumlahPerJenis[jenis] ?? 0}</span>
                  <span className="text-[10px] font-semibold uppercase tracking-wide">{labelTemuan({ jenis })}</span>
                </button>
              );
            })}
          </div>

          <div className="flex items-center justify-between text-[11px] text-gray-500">
            <span>
              {filterJenis ? `${temuanTampil.length} temuan ${labelTemuan({ jenis: filterJenis })}` : `${temuan.length} temuan`}
            </span>
            {filterJenis && (
              <button type="button" onClick={() => setFilterJenis(null)} className="font-semibold text-red-700 hover:underline cursor-pointer">
                Tampilkan semua
              </button>
            )}
          </div>

          {disaring > 0 && (
            <p className="flex items-center gap-1.5 text-[10px] text-gray-500 italic">
              <Info size={11} className="shrink-0" />
              {disaring} temuan disembunyikan karena tidak ada akses
            </p>
          )}

          {pdfGalat && (
            <div className="px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-[11px] text-red-800 flex justify-between gap-2">
              <span>{pdfGalat}</span>
              <button type="button" onClick={() => setPdfGalat(null)} className="font-bold cursor-pointer" title="Tutup">✕</button>
            </div>
          )}

          {/* Daftar temuan */}
          {temuan.length === 0 ? (
            <EmptyState
              title="Tidak ada temuan"
              message="Layanan analisa tidak menemukan pasal draf yang perlu dibandingkan dengan korpus yang dapat Anda akses."
            />
          ) : temuanTampil.length === 0 ? (
            <EmptyState
              title="Tidak ada temuan untuk jenis ini"
              message={`Tidak ada temuan berjenis ${filterJenis ? labelTemuan({ jenis: filterJenis }) : ''}.`}
              actionLabel="Tampilkan semua"
              onAction={() => setFilterJenis(null)}
            />
          ) : (
            <ul className="space-y-2.5">
              {temuanTampil.map((t, idx) => {
                const warna = KELAS_WARNA[warnaTemuan(t)];
                const pdf = targetPdf(t.pembanding);
                const perbedaan = Array.isArray(t.perbedaan) ? t.perbedaan.filter(teksAda) : [];
                const keyakinan = typeof t.keyakinan === 'number' && !isNaN(t.keyakinan) ? Math.round(t.keyakinan * 100) : null;
                const baku = t.klausul_baku === true;
                return (
                  <li key={`${t.pasal_draft}-${idx}`}>
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => lompat(t.pasal_draft)}
                      onKeyDown={(e) => tombolKeyboard(e, t.pasal_draft)}
                      title={`Lompat ke ${t.pasal_draft} di panel naskah`}
                      className={`p-3 rounded-lg border border-gray-200 bg-white hover:border-gray-300 transition cursor-pointer space-y-1.5 text-xs ${baku ? 'opacity-60' : ''}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="font-bold text-gray-900 truncate">{t.pasal_draft}</span>
                          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border shrink-0 ${warna.badge}`}>
                            {labelTemuan(t)}
                          </span>
                        </div>
                        {(keyakinan !== null || teksAda(t.tingkat)) && (
                          <span className="text-[10px] text-gray-500 font-mono shrink-0">
                            {keyakinan !== null ? `Keyakinan ${keyakinan}%` : ''}
                            {keyakinan !== null && teksAda(t.tingkat) ? ' · ' : ''}
                            {teksAda(t.tingkat) ? t.tingkat : ''}
                          </span>
                        )}
                      </div>

                      {baku && (
                        <p className="text-[10px] italic text-gray-500">
                          Klausul baku: redaksi serupa umum di banyak peraturan, keyakinan diturunkan.
                        </p>
                      )}
                      {teksAda(t.alasan) && <p className="text-gray-700 leading-relaxed">{t.alasan}</p>}
                      {teksAda(t.kutipan_draft) && (
                        <blockquote className="border-l-2 border-gray-300 pl-2 text-gray-600 italic font-serif">
                          {t.kutipan_draft}
                        </blockquote>
                      )}
                      {perbedaan.length > 0 && (
                        <ul className="list-disc pl-4 text-gray-700 space-y-0.5">
                          {perbedaan.map((p, pIdx) => <li key={pIdx}>{p}</li>)}
                        </ul>
                      )}

                      {t.pembanding && (
                        <div className="mt-1 p-2 rounded-md bg-gray-50 border border-gray-100 space-y-1">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block">Pembanding</span>
                              <span className="font-semibold text-gray-800 block">{teksAda(t.pembanding.judul) ? t.pembanding.judul : 'Dokumen korpus'}</span>
                              {(teksAda(t.pembanding.pasal) || typeof t.pembanding.halaman === 'number') && (
                                <span className="text-[10px] text-gray-500 font-mono">
                                  {teksAda(t.pembanding.pasal) ? `Pasal ${t.pembanding.pasal}` : ''}
                                  {typeof t.pembanding.halaman === 'number' ? ` · hal. ${t.pembanding.halaman}` : ''}
                                </span>
                              )}
                            </div>
                            {pdf && (
                              <button
                                type="button"
                                onClick={(e) => bukaPdf(e, t.pembanding)}
                                onKeyDown={(e) => e.stopPropagation()}
                                className="inline-flex items-center gap-1 text-[11px] font-semibold text-red-700 hover:underline shrink-0 cursor-pointer"
                                title="Buka PDF pembanding pada halaman terkait"
                              >
                                <ExternalLink size={11} />
                                <span>Buka PDF</span>
                              </button>
                            )}
                          </div>
                          {teksAda(t.pembanding.kutipan) && (
                            <p className="text-gray-600 font-serif leading-relaxed">{t.pembanding.kutipan}</p>
                          )}
                        </div>
                      )}

                      {!isJenisTemuan(t.jenis) && (
                        <p className="text-[10px] text-gray-400 flex items-center gap-1">
                          <FileText size={10} /> Jenis temuan tidak dikenal: {String(t.jenis)}
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          {teksAda(data.catatan) && (
            <p className="pt-2 border-t border-gray-100 text-[10px] font-semibold text-amber-800 leading-snug">{data.catatan}</p>
          )}
        </>
      )}
    </div>
  );
}
