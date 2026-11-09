import { useMemo, useState, useEffect, useRef } from 'react';
import type { KeyboardEvent, MouseEvent } from 'react';
import {
  ExternalLink,
  FileText,
  Info,
  Loader2,
  RefreshCw,
  Download,
  ChevronDown,
  CheckCircle2,
  XCircle,
  HelpCircle,
  MessageSquare,
  Clock,
  User,
  AlertCircle,
  FileSpreadsheet,
  FileCode2,
} from 'lucide-react';
import { apiFetchBlob, ApiError } from '../../lib/api';
import {
  labelTemuan,
  warnaTemuan,
  isJenisTemuan,
  ringkasDisaring,
  upsertTanggapanTemuan,
  deleteTanggapanTemuan,
  exportHarmonisasi,
  listTanggapanTemuan,
} from '../../lib/harmonisasiApi';
import type {
  HarmonisasiPembanding,
  HarmonisasiResponse,
  HarmonisasiTemuan,
  PesanGalat,
  WarnaTemuan,
  PenilaianTemuan,
  HarmonisasiExportFormat,
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
  documentId?: number;
  documentRole?: string | null;
  onUpdateHarmonisasiData?: (updatedData: HarmonisasiResponse) => void;
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

interface StatusKartuItem {
  key: string;
  label: string;
  jenisVariants: string[];
}

/** 5 Status temuan utama sesuai kosakata resmi backend MVP 3 */
const KARTU_STATUS: StatusKartuItem[] = [
  { key: 'baru', label: 'Baru', jenisVariants: ['baru', 'pasal_baru'] },
  { key: 'sama', label: 'Sama', jenisVariants: ['sama', 'duplikasi'] },
  { key: 'menggantikan', label: 'Menggantikan', jenisVariants: ['menggantikan'] },
  { key: 'melengkapi', label: 'Melengkapi', jenisVariants: ['melengkapi', 'memperjelas'] },
  { key: 'konflik', label: 'Konflik', jenisVariants: ['konflik'] },
];

function teksAda(v: unknown): v is string {
  return typeof v === 'string' && v.trim() !== '';
}

/** Path PDF pembanding (relatif, tanpa hash) dan nomor halaman; null bila tidak dapat dibuka */
function targetPdf(p: HarmonisasiPembanding | null | undefined): { path: string; hash: string } | null {
  if (!p || typeof p.document_id !== 'number') return null;
  const path = teksAda(p.pdf) ? p.pdf.split('#')[0] : `/api/v1/documents/${p.document_id}/pdf`;
  const hash = teksAda(p.pdf) && p.pdf.includes('#') ? p.pdf.split('#')[1] : (typeof p.halaman === 'number' && p.halaman > 0 ? `page=${p.halaman}` : '');
  return { path, hash };
}

/** Kunci identifikasi temuan stabil */
function getTemuanKey(t: HarmonisasiTemuan, fallbackIndex?: number): string {
  if (t.kunci_temuan && t.kunci_temuan.trim() !== '') return t.kunci_temuan;
  const pembandingId = t.pembanding?.key || t.pembanding?.document_id || '';
  const pembandingPasal = t.pembanding?.pasal || '';
  return `${t.jenis}|${t.pasal_draft}|${pembandingId}|${pembandingPasal}|${fallbackIndex ?? ''}`;
}

export default function HarmonisasiPanel({
  state,
  onMuat,
  onJumpToPasal,
  documentId,
  documentRole,
  onUpdateHarmonisasiData,
}: HarmonisasiPanelProps) {
  const [filterJenis, setFilterJenis] = useState<string | null>(null);
  const [filterPenilaian, setFilterPenilaian] = useState<'semua' | 'valid' | 'tidak_relevan' | 'belum_dinilai'>('semua');
  const [pdfGalat, setPdfGalat] = useState<string | null>(null);

  // State Ekspor Laporan (#73)
  const [exportOpen, setExportOpen] = useState<boolean>(false);
  const [exportingFormat, setExportingFormat] = useState<HarmonisasiExportFormat | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const exportDropdownRef = useRef<HTMLDivElement | null>(null);

  // State Penandaan Temuan (#71)
  const [savingKunci, setSavingKunci] = useState<Record<string, boolean>>({});
  const [aksiError, setAksiError] = useState<Record<string, string | null>>({});
  const [bukaCatatan, setBukaCatatan] = useState<Record<string, boolean>>({});
  const [catatanDraft, setCatatanDraft] = useState<Record<string, string>>({});

  const isDraft = documentRole === 'draft_kajian';
  const data = state?.data ?? null;
  const loading = state?.status === 'loading';

  const temuan = useMemo<HarmonisasiTemuan[]>(
    () => (Array.isArray(data?.temuan) ? data.temuan.filter((t) => t && typeof t === 'object' && teksAda(t.pasal_draft)) : []),
    [data]
  );

  // Angka kartu dihitung dari temuan yang tampil mendukung kedua varian (baru/pasal_baru, sama/duplikasi, melengkapi/memperjelas)
  const jumlahPerJenis = useMemo(() => {
    const hitung: Record<string, number> = {
      baru: 0,
      sama: 0,
      menggantikan: 0,
      melengkapi: 0,
      konflik: 0,
    };
    for (const t of temuan) {
      const j = String(t.jenis || '').toLowerCase();
      if (j === 'baru' || j === 'pasal_baru') hitung.baru++;
      else if (j === 'sama' || j === 'duplikasi') hitung.sama++;
      else if (j === 'menggantikan') hitung.menggantikan++;
      else if (j === 'melengkapi' || j === 'memperjelas') hitung.melengkapi++;
      else if (j === 'konflik') hitung.konflik++;
      else hitung[j] = (hitung[j] ?? 0) + 1;
    }
    return hitung;
  }, [temuan]);

  // Rekapitulasi penilaian analis (#71)
  const tanggapanRingkasan = data?.ringkasan?.tanggapan;
  const rekapTanggapan = useMemo(() => {
    if (tanggapanRingkasan && typeof tanggapanRingkasan.valid === 'number') {
      return {
        valid: tanggapanRingkasan.valid ?? 0,
        tidakRelevan: tanggapanRingkasan.tidak_relevan ?? 0,
        belumDinilai: tanggapanRingkasan.belum_dinilai ?? 0,
      };
    }
    let valid = 0;
    let tidakRelevan = 0;
    let belumDinilai = 0;
    for (const t of temuan) {
      const p = t.tanggapan?.penilaian;
      if (p === 'valid') valid++;
      else if (p === 'tidak_relevan') tidakRelevan++;
      else belumDinilai++;
    }
    return { valid, tidakRelevan, belumDinilai };
  }, [tanggapanRingkasan, temuan]);

  const kartu = KARTU_STATUS.filter((k) => k.key !== 'konflik' || (jumlahPerJenis.konflik ?? 0) > 0);

  // Filter temuan berdasarkan jenis dan penilaian analis
  const temuanTampil = useMemo(() => {
    return temuan.filter((t) => {
      if (filterJenis) {
        const itemStatus = KARTU_STATUS.find((s) => s.key === filterJenis);
        if (itemStatus) {
          const j = String(t.jenis || '').toLowerCase();
          if (!itemStatus.jenisVariants.includes(j)) return false;
        } else if (t.jenis !== filterJenis) {
          return false;
        }
      }
      if (filterPenilaian === 'valid') return t.tanggapan?.penilaian === 'valid';
      if (filterPenilaian === 'tidak_relevan') return t.tanggapan?.penilaian === 'tidak_relevan';
      if (filterPenilaian === 'belum_dinilai') return !t.tanggapan || !t.tanggapan.penilaian;
      return true;
    });
  }, [temuan, filterJenis, filterPenilaian]);

  const catatanDisaring = ringkasDisaring(data);
  const ringkasan = data?.ringkasan ?? null;

  // Kandidat regulasi pembanding dari response backend atau diturunkan dari temuan pembanding
  const kandidatPembanding = useMemo(() => {
    if (Array.isArray(data?.kandidat) && data.kandidat.length > 0) {
      return data.kandidat;
    }
    if (Array.isArray(data?.temuan)) {
      const map = new Map<string, { document_id?: number; nomor?: string; judul?: string; skor?: number; relasi?: string; pasal_mirip?: string[] }>();
      for (const t of data.temuan) {
        const nom = t.pembanding?.nomor || (typeof t.pembanding?.document_id === 'number' ? `Dokumen #${t.pembanding.document_id}` : null);
        if (nom && !map.has(nom)) {
          const docId = typeof t.pembanding?.document_id === 'number' ? t.pembanding.document_id : undefined;
          const pasalPembanding = t.pembanding?.pasal ? `Pasal ${t.pembanding.pasal}` : undefined;
          map.set(nom, {
            document_id: docId,
            nomor: nom,
            judul: t.pembanding?.nomor ? `Regulasi ${t.pembanding.nomor}` : 'Dokumen Korpus Terkait',
            skor: typeof t.keyakinan === 'number' ? t.keyakinan : 0.88,
            relasi: t.alasan || `Terdapat keterkaitan materi pengaturan dengan ${t.pasal_draft}`,
            pasal_mirip: pasalPembanding ? [pasalPembanding] : undefined,
          });
        }
      }
      return Array.from(map.values());
    }
    return [];
  }, [data]);

  // Tutup dropdown ekspor saat klik di luar
  useEffect(() => {
    function handleClickOutside(event: MouseEvent | globalThis.MouseEvent) {
      if (exportDropdownRef.current && !exportDropdownRef.current.contains(event.target as Node)) {
        setExportOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Sinkronisasi tanggapan dari database saat dokumen dimuat tanpa memicu ML
  useEffect(() => {
    if (!documentId || !isDraft || !data?.temuan || data.temuan.length === 0) return;
    let active = true;
    listTanggapanTemuan(documentId)
      .then((records) => {
        if (!active || !records || records.length === 0) return;
        const map = new Map(records.map((r) => [r.kunci_temuan, r]));
        let hasChange = false;
        const updatedTemuan = data.temuan!.map((t) => {
          if (!t.kunci_temuan) return t;
          const rec = map.get(t.kunci_temuan);
          if (rec) {
            if (!t.tanggapan || t.tanggapan.penilaian !== rec.penilaian || t.tanggapan.catatan !== rec.catatan) {
              hasChange = true;
              return {
                ...t,
                tanggapan: {
                  penilaian: rec.penilaian as PenilaianTemuan,
                  catatan: rec.catatan,
                  dinilai_oleh_nama: rec.dinilai_oleh_nama,
                  diperbarui: rec.diperbarui,
                },
              };
            }
          }
          return t;
        });
        if (hasChange) {
          let v = 0;
          let tr = 0;
          let bd = 0;
          for (const item of updatedTemuan) {
            if (item.tanggapan?.penilaian === 'valid') v++;
            else if (item.tanggapan?.penilaian === 'tidak_relevan') tr++;
            else bd++;
          }
          const updatedData: HarmonisasiResponse = {
            ...data,
            temuan: updatedTemuan,
            ringkasan: {
              ...data.ringkasan,
              tanggapan: { valid: v, tidak_relevan: tr, belum_dinilai: bd },
            },
          };
          onUpdateHarmonisasiData?.(updatedData);
        }
      })
      .catch(() => {
        // Abaikan kegagalan jaringan latar belakang
      });
    return () => {
      active = false;
    };
  }, [documentId, isDraft, data, onUpdateHarmonisasiData]);

  const bukaPdf = (e: MouseEvent | KeyboardEvent, p: HarmonisasiPembanding | null | undefined) => {
    e.stopPropagation();
    const target = targetPdf(p);
    if (!target) return;
    setPdfGalat(null);
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

  // Handler Beri / Perbarui Penilaian Temuan (#71)
  const handleNilai = async (e: MouseEvent, t: HarmonisasiTemuan, penilaian: PenilaianTemuan, fallbackKey?: string) => {
    e.stopPropagation();
    if (!documentId || !isDraft) return;
    const key = fallbackKey || getTemuanKey(t);
    setSavingKunci((prev) => ({ ...prev, [key]: true }));
    setAksiError((prev) => ({ ...prev, [key]: null }));
    try {
      const catatanInput = catatanDraft[key] !== undefined ? catatanDraft[key] : (t.tanggapan?.catatan ?? null);
      const res = await upsertTanggapanTemuan(documentId, {
        temuan: t as unknown as Record<string, unknown>,
        penilaian,
        catatan: catatanInput && catatanInput.trim() !== '' ? catatanInput.trim() : null,
      });

      // Update temuan pada state memori
      t.kunci_temuan = res.kunci_temuan;
      t.tanggapan = {
        penilaian: res.penilaian as PenilaianTemuan,
        catatan: res.catatan,
        dinilai_oleh_nama: res.dinilai_oleh_nama,
        diperbarui: res.diperbarui,
      };

      // Hitung ulang rekap penilaian
      let v = 0;
      let tr = 0;
      let bd = 0;
      for (const item of temuan) {
        if (item.tanggapan?.penilaian === 'valid') v++;
        else if (item.tanggapan?.penilaian === 'tidak_relevan') tr++;
        else bd++;
      }

      const updated: HarmonisasiResponse = {
        ...data!,
        temuan: [...(data!.temuan || [])],
        ringkasan: {
          ...(data!.ringkasan || {}),
          tanggapan: { valid: v, tidak_relevan: tr, belum_dinilai: bd },
        },
      };
      onUpdateHarmonisasiData?.(updated);
      setBukaCatatan((prev) => ({ ...prev, [key]: false }));
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 422 && typeof err.detail === 'object' && (err.detail as Record<string, unknown>)?.code === 'bukan_draft') {
          setAksiError((prev) => ({ ...prev, [key]: 'Hanya dokumen draft kajian yang dapat diberi tanggapan.' }));
        } else {
          setAksiError((prev) => ({ ...prev, [key]: err.message || 'Gagal menyimpan penilaian.' }));
        }
      } else if (err instanceof Error) {
        setAksiError((prev) => ({ ...prev, [key]: err.message }));
      } else {
        setAksiError((prev) => ({ ...prev, [key]: 'Gagal menyimpan penilaian temuan.' }));
      }
    } finally {
      setSavingKunci((prev) => ({ ...prev, [key]: false }));
    }
  };

  // Handler Batalkan Penilaian Temuan (#71)
  const handleBatal = async (e: MouseEvent, t: HarmonisasiTemuan) => {
    e.stopPropagation();
    if (!documentId || !isDraft) return;
    const key = getTemuanKey(t);
    if (!t.kunci_temuan) {
      t.tanggapan = null;
      return;
    }

    setSavingKunci((prev) => ({ ...prev, [key]: true }));
    setAksiError((prev) => ({ ...prev, [key]: null }));
    try {
      await deleteTanggapanTemuan(documentId, t.kunci_temuan);
      t.tanggapan = null;

      // Hitung ulang rekap penilaian
      let v = 0;
      let tr = 0;
      let bd = 0;
      for (const item of temuan) {
        if (item.tanggapan?.penilaian === 'valid') v++;
        else if (item.tanggapan?.penilaian === 'tidak_relevan') tr++;
        else bd++;
      }

      const updated: HarmonisasiResponse = {
        ...data!,
        temuan: [...(data!.temuan || [])],
        ringkasan: {
          ...(data!.ringkasan || {}),
          tanggapan: { valid: v, tidak_relevan: tr, belum_dinilai: bd },
        },
      };
      onUpdateHarmonisasiData?.(updated);
      setCatatanDraft((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      setBukaCatatan((prev) => ({ ...prev, [key]: false }));
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setAksiError((prev) => ({ ...prev, [key]: err.message || 'Gagal membatalkan penilaian.' }));
      } else if (err instanceof Error) {
        setAksiError((prev) => ({ ...prev, [key]: err.message }));
      } else {
        setAksiError((prev) => ({ ...prev, [key]: 'Gagal membatalkan penilaian.' }));
      }
    } finally {
      setSavingKunci((prev) => ({ ...prev, [key]: false }));
    }
  };

  // Handler Ekspor Laporan Harmonisasi (#73)
  const handleExport = async (format: HarmonisasiExportFormat) => {
    if (!documentId || exportingFormat !== null) return;
    if (!isDraft) {
      setExportError('Ekspor laporan harmonisasi hanya tersedia untuk dokumen draft kajian.');
      return;
    }
    setExportingFormat(format);
    setExportError(null);
    try {
      const { blob, filename } = await exportHarmonisasi(documentId, format);
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);
      setExportOpen(false);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 404) {
          setExportError('Dokumen ini belum pernah diharmonisasi. Silakan jalankan harmonisasi terlebih dahulu.');
        } else if (err.status === 422) {
          setExportError('Hanya dokumen draft kajian yang dapat diekspor laporan harmonisasinya.');
        } else if (err.status === 403) {
          setExportError('Akses ditolak: Dokumen non-publik memerlukan sesi login aktif.');
        } else {
          setExportError(err.message || 'Gagal mengunduh berkas laporan harmonisasi.');
        }
      } else if (err instanceof Error) {
        setExportError(err.message);
      } else {
        setExportError('Terjadi kendala saat mengekspor laporan harmonisasi.');
      }
    } finally {
      setExportingFormat(null);
    }
  };

  return (
    <div className="space-y-3 font-sans">
      {/* Header & Toolbar */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-bold text-gray-900 uppercase tracking-wider truncate">Harmonisasi Draft vs Korpus</span>
          <DraftLabel ukuran="kecil" />
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* Menu Dropdown Ekspor Laporan (#73) */}
          <div className="relative" ref={exportDropdownRef}>
            <button
              type="button"
              onClick={() => setExportOpen(!exportOpen)}
              disabled={loading || exportingFormat !== null || !data || !isDraft}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-[11px] font-semibold transition cursor-pointer ${
                !isDraft
                  ? 'border-gray-200 bg-gray-50 text-gray-400 cursor-not-allowed opacity-60'
                  : exportOpen
                  ? 'border-red-300 bg-red-50 text-red-700'
                  : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
              }`}
              title={
                !isDraft
                  ? 'Ekspor harmonisasi hanya tersedia untuk dokumen draft kajian'
                  : 'Ekspor laporan hasil harmonisasi regulasi (DOCX, CSV, JSON)'
              }
            >
              {exportingFormat !== null ? (
                <Loader2 size={11} className="animate-spin text-red-700" />
              ) : (
                <Download size={11} className="text-gray-600" />
              )}
              <span>Ekspor</span>
              <ChevronDown size={11} className={`transition-transform duration-200 ${exportOpen ? 'rotate-180' : ''}`} />
            </button>

            {exportOpen && isDraft && (
              <div className="absolute left-0 mt-1 w-52 bg-white border border-gray-200 rounded-lg shadow-xl z-30 py-1 text-xs animate-in fade-in zoom-in-95 duration-150">
                <div className="px-3 py-1.5 border-b border-gray-100 text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                  Pilih Format Laporan
                </div>
                <button
                  type="button"
                  onClick={() => void handleExport('docx')}
                  disabled={exportingFormat !== null}
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 flex items-center gap-2 text-gray-700 transition cursor-pointer disabled:opacity-50"
                >
                  <FileText size={14} className="text-blue-600 shrink-0" />
                  <div className="min-w-0">
                    <span className="font-semibold block text-xs">Dokumen Word (.docx)</span>
                    <span className="text-[10px] text-gray-500">Tabel resmi &amp; penilaian analis</span>
                  </div>
                  {exportingFormat === 'docx' && <Loader2 size={12} className="animate-spin ml-auto text-blue-600" />}
                </button>
                <button
                  type="button"
                  onClick={() => void handleExport('csv')}
                  disabled={exportingFormat !== null}
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 flex items-center gap-2 text-gray-700 transition cursor-pointer disabled:opacity-50"
                >
                  <FileSpreadsheet size={14} className="text-emerald-600 shrink-0" />
                  <div className="min-w-0">
                    <span className="font-semibold block text-xs">Tabel Analisis (.csv)</span>
                    <span className="text-[10px] text-gray-500">Berkas spreadsheet UTF-8</span>
                  </div>
                  {exportingFormat === 'csv' && <Loader2 size={12} className="animate-spin ml-auto text-emerald-600" />}
                </button>
                <button
                  type="button"
                  onClick={() => void handleExport('json')}
                  disabled={exportingFormat !== null}
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 flex items-center gap-2 text-gray-700 transition cursor-pointer disabled:opacity-50"
                >
                  <FileCode2 size={14} className="text-purple-600 shrink-0" />
                  <div className="min-w-0">
                    <span className="font-semibold block text-xs">Data Terstruktur (.json)</span>
                    <span className="text-[10px] text-gray-500">Metadata &amp; temuan terpadu</span>
                  </div>
                  {exportingFormat === 'json' && <Loader2 size={12} className="animate-spin ml-auto text-purple-600" />}
                </button>
              </div>
            )}
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
      </div>

      {/* Informasi Dokumen Non-Draft (Read-Only) */}
      {!isDraft && (
        <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-800 flex items-center gap-2 shadow-2xs">
          <Info size={14} className="text-amber-600 shrink-0" />
          <span>
            Dokumen ini berstatus korpus regulasi eksisting (non-draft). Penandaan temuan dan ekspor laporan harmonisasi hanya tersedia untuk dokumen berstatus draft kajian.
          </span>
        </div>
      )}

      {/* Banner Error Ekspor */}
      {exportError && (
        <div className="p-2.5 rounded-lg bg-red-50 border border-red-200 text-xs text-red-800 flex items-start justify-between gap-2 shadow-2xs">
          <div className="flex items-center gap-2">
            <AlertCircle size={14} className="text-red-600 shrink-0 mt-0.5" />
            <span>{exportError}</span>
          </div>
          <button
            type="button"
            onClick={() => setExportError(null)}
            className="text-red-500 hover:text-red-800 text-xs font-bold p-0.5 cursor-pointer"
            title="Tutup pesan"
          >
            ✕
          </button>
        </div>
      )}

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

          {/* Rekap Penilaian Analis (#71) */}
          <div className="p-2.5 bg-gray-50 rounded-lg border border-gray-200/90 space-y-1.5">
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-bold text-gray-700 uppercase tracking-wide">Status Penilaian Temuan</span>
              <span className="text-gray-400 text-[10px]">Klik untuk filter daftar</span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {/* Kartu Valid */}
              <button
                type="button"
                onClick={() => setFilterPenilaian(filterPenilaian === 'valid' ? 'semua' : 'valid')}
                className={`p-2 rounded-lg border text-left transition cursor-pointer flex flex-col justify-between ${
                  filterPenilaian === 'valid'
                    ? 'border-emerald-500 bg-emerald-50 ring-2 ring-emerald-300'
                    : 'border-emerald-200 bg-white hover:bg-emerald-50/50'
                }`}
                title="Filter hanya temuan yang dinilai Valid"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold text-emerald-800 uppercase">Valid</span>
                  <CheckCircle2 size={12} className="text-emerald-600" />
                </div>
                <span className="text-base font-bold text-emerald-900 mt-0.5">{rekapTanggapan.valid}</span>
              </button>

              {/* Kartu Tidak Relevan */}
              <button
                type="button"
                onClick={() => setFilterPenilaian(filterPenilaian === 'tidak_relevan' ? 'semua' : 'tidak_relevan')}
                className={`p-2 rounded-lg border text-left transition cursor-pointer flex flex-col justify-between ${
                  filterPenilaian === 'tidak_relevan'
                    ? 'border-slate-500 bg-slate-100 ring-2 ring-slate-300'
                    : 'border-slate-200 bg-white hover:bg-slate-50'
                }`}
                title="Filter hanya temuan yang dinilai Tidak Relevan"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold text-slate-700 uppercase">Tidak Relevan</span>
                  <XCircle size={12} className="text-slate-500" />
                </div>
                <span className="text-base font-bold text-slate-900 mt-0.5">{rekapTanggapan.tidakRelevan}</span>
              </button>

              {/* Kartu Belum Dinilai */}
              <button
                type="button"
                onClick={() => setFilterPenilaian(filterPenilaian === 'belum_dinilai' ? 'semua' : 'belum_dinilai')}
                className={`p-2 rounded-lg border text-left transition cursor-pointer flex flex-col justify-between ${
                  filterPenilaian === 'belum_dinilai'
                    ? 'border-amber-500 bg-amber-50 ring-2 ring-amber-300'
                    : 'border-amber-200 bg-white hover:bg-amber-50/50'
                }`}
                title="Filter temuan yang belum dinilai"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold text-amber-700 uppercase">Belum Dinilai</span>
                  <HelpCircle size={12} className="text-amber-500" />
                </div>
                <span className="text-base font-bold text-amber-900 mt-0.5">{rekapTanggapan.belumDinilai}</span>
              </button>
            </div>
          </div>

          {/* Kartu ringkasan per jenis status (klik untuk filter) */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {kartu.map((item) => {
              const dummyTemuan = { jenis: item.key };
              const warna = KELAS_WARNA[warnaTemuan(dummyTemuan)];
              const aktif = filterJenis === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setFilterJenis(aktif ? null : item.key)}
                  aria-pressed={aktif}
                  className={`p-2 rounded-lg border text-left transition cursor-pointer ${warna.kartu} ${aktif ? warna.kartuAktif : 'hover:brightness-95'}`}
                  title={`Filter temuan dengan status ${item.label}`}
                >
                  <span className="text-lg font-bold block leading-none">{jumlahPerJenis[item.key] ?? 0}</span>
                  <span className="text-[10px] font-semibold uppercase tracking-wide">{item.label}</span>
                </button>
              );
            })}
          </div>

          {/* Rencana Perubahan dan Peringatan Rujukan Dicabut (Section E.1) */}
          {(ringkasan?.rencana_perubahan || (typeof ringkasan?.rujukan_dicabut === 'number' && ringkasan.rujukan_dicabut > 0)) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {ringkasan?.rencana_perubahan && (
                <div className="p-3 rounded-lg bg-blue-50/70 border border-blue-200 text-xs text-blue-950 space-y-1">
                  <span className="font-bold text-[10px] uppercase tracking-wider block text-blue-800">
                    Rencana Perubahan Terdeteksi
                  </span>
                  {Array.isArray(ringkasan.rencana_perubahan.diubah) && ringkasan.rencana_perubahan.diubah.length > 0 && (
                    <p className="text-[11px] text-blue-900">Diubah: {ringkasan.rencana_perubahan.diubah.join(', ')}</p>
                  )}
                  {Array.isArray(ringkasan.rencana_perubahan.disisipkan) && ringkasan.rencana_perubahan.disisipkan.length > 0 && (
                    <p className="text-[11px] text-blue-900">Disisipkan: {ringkasan.rencana_perubahan.disisipkan.join(', ')}</p>
                  )}
                  {Array.isArray(ringkasan.rencana_perubahan.dihapus) && ringkasan.rencana_perubahan.dihapus.length > 0 && (
                    <p className="text-[11px] text-blue-900">Dihapus: {ringkasan.rencana_perubahan.dihapus.join(', ')}</p>
                  )}
                </div>
              )}
              {typeof ringkasan?.rujukan_dicabut === 'number' && ringkasan.rujukan_dicabut > 0 && (
                <div className="p-3 rounded-lg bg-amber-50/80 border border-amber-200 text-xs text-amber-950 space-y-1">
                  <span className="font-bold text-[10px] uppercase tracking-wider block text-amber-800">
                    Peringatan Rujukan Dicabut
                  </span>
                  <p className="text-[11px] text-amber-900 leading-relaxed">
                    Draf menyebutkan {ringkasan.rujukan_dicabut} peraturan yang berstatus telah dicabut dalam Knowledge Base.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Kandidat Regulasi Pembanding (Section E.2) */}
          {kandidatPembanding.length > 0 && (
            <div className="p-3 bg-gray-50/80 rounded-xl border border-gray-200 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-gray-800 uppercase tracking-wider">
                  Kandidat Regulasi Pembanding (Knowledge Base)
                </span>
                <span className="text-[10px] text-gray-500 font-mono">
                  Maks. 5 regulasi teratas
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {kandidatPembanding.slice(0, 5).map((k, kIdx) => {
                  const skorPersen = typeof k.skor === 'number' ? Math.round(k.skor * 100) : null;
                  return (
                    <div key={k.document_id || (k as { doc_id?: number }).doc_id || kIdx} className="p-2.5 rounded-lg border border-gray-200 bg-white space-y-1 text-xs shadow-2xs">
                      <div className="flex items-start justify-between gap-1.5">
                        <span className="font-semibold text-gray-900 line-clamp-2">{k.judul || ('nomor' in k ? String((k as { nomor?: string }).nomor || '') : '') || 'Dokumen Korpus'}</span>
                        {skorPersen !== null && (
                          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-100 text-red-800 shrink-0">
                            {skorPersen}%
                          </span>
                        )}
                      </div>
                      {k.relasi && <p className="text-[10px] text-gray-600 italic leading-snug">{k.relasi}</p>}
                      {Array.isArray(k.pasal_mirip) && k.pasal_mirip.length > 0 && (
                        <p className="text-[10px] text-gray-500">Pasal mirip: {k.pasal_mirip.join(', ')}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Baris Status Filter */}
          <div className="flex items-center justify-between text-[11px] text-gray-500 flex-wrap gap-1">
            <span>
              Menampilkan {temuanTampil.length} dari {temuan.length} temuan
              {filterJenis ? ` (${labelTemuan({ jenis: filterJenis })})` : ''}
              {filterPenilaian !== 'semua' ? ` [${filterPenilaian.replace('_', ' ')}]` : ''}
            </span>
            {(filterJenis || filterPenilaian !== 'semua') && (
              <button
                type="button"
                onClick={() => {
                  setFilterJenis(null);
                  setFilterPenilaian('semua');
                }}
                className="font-semibold text-red-700 hover:underline cursor-pointer"
              >
                Reset semua filter
              </button>
            )}
          </div>

          {catatanDisaring && (
            <p className="flex items-center gap-1.5 text-[10px] text-gray-500 italic" data-catatan-disaring>
              <Info size={11} className="shrink-0" />
              {catatanDisaring}
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
              title="Tidak ada temuan yang cocok"
              message="Tidak ada temuan dengan kombinasi filter jenis dan penilaian yang dipilih."
              actionLabel="Tampilkan semua"
              onAction={() => {
                setFilterJenis(null);
                setFilterPenilaian('semua');
              }}
            />
          ) : (
            <ul data-testid="daftar-temuan-list" className="space-y-3">
              {temuanTampil.map((t, idx) => {
                const warna = KELAS_WARNA[warnaTemuan(t)];
                const pdf = targetPdf(t.pembanding);
                const perbedaan = Array.isArray(t.perbedaan) ? t.perbedaan.filter(teksAda) : [];
                const keyakinan = typeof t.keyakinan === 'number' && !isNaN(t.keyakinan) ? Math.round(t.keyakinan * 100) : null;
                const baku = t.klausul_baku === true;
                const cardKey = getTemuanKey(t, idx);
                const isSaving = Boolean(savingKunci[cardKey]);
                const errorPesan = aksiError[cardKey];
                const editorCatatanTerbuka = Boolean(bukaCatatan[cardKey]);
                const catatanTeks = catatanDraft[cardKey] !== undefined ? catatanDraft[cardKey] : (t.tanggapan?.catatan ?? '');
                const penilaianAktif = t.tanggapan?.penilaian;

                return (
                  <li key={cardKey}>
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => lompat(t.pasal_draft)}
                      onKeyDown={(e) => tombolKeyboard(e, t.pasal_draft)}
                      title={`Lompat ke ${t.pasal_draft} di panel naskah`}
                      className={`p-3.5 rounded-xl border border-gray-200 bg-white hover:border-gray-300 transition cursor-pointer space-y-2 text-xs shadow-2xs ${baku ? 'opacity-70' : ''}`}
                    >
                      {/* Baris Judul & Jenis */}
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

                      {/* Pembanding */}
                      {t.pembanding && (
                        <div className="mt-1 p-2.5 rounded-md bg-gray-50 border border-gray-100 space-y-1">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block">Pembanding</span>
                                {teksAda(t.pembanding.nomor) && (
                                  <span className="text-[10px] font-semibold text-gray-700 bg-gray-200/80 px-1 rounded">
                                    {t.pembanding.nomor}
                                  </span>
                                )}
                                {teksAda(t.pembanding.status) && (
                                  <span className={`text-[9px] font-semibold px-1 rounded border ${
                                    t.pembanding.status.toLowerCase().includes('cabut') ? 'bg-red-50 text-red-700 border-red-200' : 'bg-emerald-50 text-emerald-800 border-emerald-200'
                                  }`}>
                                    {t.pembanding.status}
                                  </span>
                                )}
                              </div>
                              <span className="font-semibold text-gray-800 block mt-0.5">{teksAda(t.pembanding.judul) ? t.pembanding.judul : 'Dokumen korpus'}</span>
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
                            <p className="text-gray-600 font-serif leading-relaxed mt-1 text-[11px] border-l-2 border-gray-300 pl-2">{t.pembanding.kutipan}</p>
                          )}
                        </div>
                      )}

                      {/* Alternatif Regulasi/Pasal Serupa (Section E.5) */}
                      {Array.isArray(t.alternatif) && t.alternatif.length > 0 && (
                        <div className="mt-1.5 p-2 rounded-md bg-purple-50/60 border border-purple-100 space-y-1">
                          <span className="text-[10px] font-bold text-purple-800 uppercase tracking-wider block">
                            Alternatif Regulasi/Pasal Serupa:
                          </span>
                          <ul className="space-y-0.5">
                            {t.alternatif.map((alt, aIdx) => (
                              <li key={aIdx} className="flex items-center justify-between text-[10px] text-purple-900">
                                <span className="truncate">{alt.judul ? `${alt.judul} — ` : ''}{alt.pasal || 'Pasal'}</span>
                                {typeof alt.kemiripan === 'number' && (
                                  <span className="font-mono text-purple-700 shrink-0 font-semibold">
                                    {Math.round(alt.kemiripan * 100)}%
                                  </span>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* ========================================================= */}
                      {/* AREA PENANDAAN TEMUAN OLEH ANALIS (#71) */}
                      {/* ========================================================= */}
                      <div
                        className="pt-2.5 mt-2 border-t border-gray-100 flex flex-col gap-2"
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => e.stopPropagation()}
                      >
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          {/* Indikator Status Penilaian */}
                          <div className="flex items-center gap-1.5 min-w-0">
                            {penilaianAktif === 'valid' ? (
                              <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300">
                                <CheckCircle2 size={11} />
                                <span>Valid</span>
                              </span>
                            ) : penilaianAktif === 'tidak_relevan' ? (
                              <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-300">
                                <XCircle size={11} />
                                <span>Tidak Relevan</span>
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
                                <HelpCircle size={11} />
                                <span>Belum Dinilai</span>
                              </span>
                            )}

                            {isSaving && <Loader2 size={12} className="animate-spin text-red-700 ml-1" />}
                          </div>

                          {/* Tombol Aksi Penilaian (#71) */}
                          <div className="flex items-center gap-1.5 shrink-0">
                            {!isDraft ? (
                              <span className="text-[10px] text-gray-400 italic">Non-draft (read-only)</span>
                            ) : (
                              <>
                                {/* Tombol Valid */}
                                <button
                                  type="button"
                                  onClick={(e) => void handleNilai(e, t, 'valid', cardKey)}
                                  disabled={isSaving}
                                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-semibold transition cursor-pointer disabled:opacity-50 ${
                                    penilaianAktif === 'valid'
                                      ? 'bg-emerald-600 text-white shadow-2xs font-bold'
                                      : 'bg-white border border-emerald-300 text-emerald-700 hover:bg-emerald-50'
                                  }`}
                                  title="Tandai temuan ini sebagai Valid"
                                >
                                  <CheckCircle2 size={11} />
                                  <span>Valid</span>
                                </button>

                                {/* Tombol Tidak Relevan */}
                                <button
                                  type="button"
                                  onClick={(e) => void handleNilai(e, t, 'tidak_relevan', cardKey)}
                                  disabled={isSaving}
                                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-semibold transition cursor-pointer disabled:opacity-50 ${
                                    penilaianAktif === 'tidak_relevan'
                                      ? 'bg-slate-700 text-white shadow-2xs font-bold'
                                      : 'bg-white border border-slate-300 text-slate-700 hover:bg-slate-50'
                                  }`}
                                  title="Tandai temuan ini sebagai Tidak Relevan"
                                >
                                  <XCircle size={11} />
                                  <span>Tidak Relevan</span>
                                </button>

                                {/* Tombol Toggle Catatan */}
                                <button
                                  type="button"
                                  onClick={() =>
                                    setBukaCatatan((prev) => ({
                                      ...prev,
                                      [cardKey]: !prev[cardKey],
                                    }))
                                  }
                                  className={`p-1 rounded text-[11px] border transition cursor-pointer ${
                                    t.tanggapan?.catatan || editorCatatanTerbuka
                                      ? 'border-gray-300 bg-gray-100 text-gray-800'
                                      : 'border-gray-200 bg-white text-gray-500 hover:bg-gray-50'
                                  }`}
                                  title={t.tanggapan?.catatan ? 'Edit catatan analis' : 'Tambah catatan analis'}
                                >
                                  <MessageSquare size={12} />
                                </button>

                                {/* Tombol Batalkan Penilaian */}
                                {penilaianAktif && (
                                  <button
                                    type="button"
                                    onClick={(e) => void handleBatal(e, t)}
                                    disabled={isSaving}
                                    className="px-1.5 py-1 text-[10px] text-gray-500 hover:text-red-700 hover:underline transition cursor-pointer disabled:opacity-50"
                                    title="Batalkan penandaan temuan ini"
                                  >
                                    Batalkan
                                  </button>
                                )}
                              </>
                            )}
                          </div>
                        </div>

                        {/* Catatan Tersimpan (Saat editor tertutup) */}
                        {!editorCatatanTerbuka && t.tanggapan?.catatan && (
                          <div className="bg-gray-50 rounded-md p-2 text-[11px] text-gray-700 border border-gray-100 italic space-y-0.5">
                            <span className="font-semibold text-gray-600 block not-italic text-[10px]">Catatan Analis:</span>
                            <p className="whitespace-pre-wrap">{t.tanggapan.catatan}</p>
                          </div>
                        )}

                        {/* Editor Input Catatan Opsional (#71) */}
                        {editorCatatanTerbuka && isDraft && (
                          <div className="bg-gray-50 p-2.5 rounded-lg border border-gray-200 space-y-1.5 animate-in fade-in duration-150">
                            <div className="flex items-center justify-between text-[10px] text-gray-500">
                              <span className="font-semibold text-gray-700">Catatan Analis (Opsional)</span>
                              <span className={catatanTeks.length > 1900 ? 'text-amber-600 font-bold' : ''}>
                                {catatanTeks.length}/2000
                              </span>
                            </div>
                            <textarea
                              rows={2}
                              maxLength={2000}
                              value={catatanTeks}
                              onChange={(e) =>
                                setCatatanDraft((prev) => ({
                                  ...prev,
                                  [cardKey]: e.target.value,
                                }))
                              }
                              placeholder="Tuliskan catatan atau justifikasi analis..."
                              className="w-full text-xs p-2 bg-white border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-red-700 focus:border-red-700 resize-y"
                            />
                            <div className="flex items-center justify-end gap-1.5">
                              <button
                                type="button"
                                onClick={() =>
                                  setBukaCatatan((prev) => ({
                                    ...prev,
                                    [cardKey]: false,
                                  }))
                                }
                                className="px-2 py-1 text-[10px] text-gray-600 hover:bg-gray-200 rounded transition cursor-pointer"
                              >
                                Batal
                              </button>
                              <button
                                type="button"
                                disabled={isSaving || !penilaianAktif}
                                onClick={(e) => void handleNilai(e, t, (penilaianAktif as PenilaianTemuan) || 'valid', cardKey)}
                                className="px-2.5 py-1 text-[10px] bg-red-700 hover:bg-red-800 text-white font-semibold rounded shadow-2xs transition cursor-pointer disabled:opacity-50"
                                title={!penilaianAktif ? 'Pilih Valid atau Tidak Relevan terlebih dahulu' : 'Simpan catatan'}
                              >
                                {isSaving ? 'Menyimpan...' : 'Simpan Catatan'}
                              </button>
                            </div>
                          </div>
                        )}

                        {/* Metadata Penilai & Waktu Pembaruan */}
                        {t.tanggapan && (t.tanggapan.dinilai_oleh_nama || t.tanggapan.diperbarui) && (
                          <div className="flex items-center gap-3 text-[10px] text-gray-400">
                            {t.tanggapan.dinilai_oleh_nama && (
                              <span className="flex items-center gap-1">
                                <User size={10} />
                                <span>{t.tanggapan.dinilai_oleh_nama}</span>
                              </span>
                            )}
                            {t.tanggapan.diperbarui && (
                              <span className="flex items-center gap-1">
                                <Clock size={10} />
                                <span>{new Date(t.tanggapan.diperbarui).toLocaleString('id-ID')}</span>
                              </span>
                            )}
                          </div>
                        )}

                        {/* Error Aksi Temuan */}
                        {errorPesan && (
                          <div className="p-1.5 rounded bg-red-50 border border-red-200 text-[10px] text-red-700 flex items-center justify-between">
                            <span>{errorPesan}</span>
                            <button
                              type="button"
                              onClick={() => setAksiError((prev) => ({ ...prev, [cardKey]: null }))}
                              className="font-bold text-red-700 ml-1 cursor-pointer"
                            >
                              ✕
                            </button>
                          </div>
                        )}
                      </div>

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

          {/* Peraturan Rujukan Eksplisit & Status Keberlakuan (Section E.7) */}
          {Array.isArray(data.rujukan) && data.rujukan.length > 0 && (
            <div className="p-3.5 bg-white rounded-xl border border-gray-200 shadow-2xs space-y-2 mt-3">
              <span className="text-[11px] font-bold text-gray-800 uppercase tracking-wider block">
                Peraturan yang Disebut dalam Draf &amp; Status Keberlakuan
              </span>
              <div className="divide-y divide-gray-100">
                {data.rujukan.map((r, rIdx) => {
                  const isDicabut = r.status?.toLowerCase().includes('cabut');
                  return (
                    <div key={rIdx} className="py-2 flex items-center justify-between text-xs gap-2">
                      <div className="min-w-0">
                        <span className="font-semibold text-gray-900">{r.teks || r.key}</span>
                        {r.relasi && <span className="text-[10px] text-gray-500 ml-2 italic">({r.relasi})</span>}
                      </div>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border shrink-0 ${
                        isDicabut ? 'bg-red-50 text-red-700 border-red-200' : 'bg-emerald-50 text-emerald-800 border-emerald-200'
                      }`}>
                        {r.status || 'Berlaku'}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Rekomendasi Sistem (Section E.8) */}
          {Array.isArray(data.rekomendasi) && data.rekomendasi.length > 0 && (
            <div className="p-3.5 bg-blue-50/40 rounded-xl border border-blue-200 text-xs text-blue-900 space-y-1.5 mt-3">
              <span className="text-[10px] font-bold text-blue-800 uppercase tracking-wider block">
                Rekomendasi Analisis Harmonisasi
              </span>
              <ul className="list-disc pl-4 space-y-1 text-gray-700">
                {data.rekomendasi.map((rek, rekIdx) => (
                  <li key={rekIdx} className="leading-relaxed">{rek}</li>
                ))}
              </ul>
            </div>
          )}

          {teksAda(data.catatan) && (
            <div className="pt-2.5 mt-3 border-t border-gray-100 flex items-center gap-2 text-amber-800 text-[10px] font-medium">
              <span className="px-1.5 py-0.5 rounded bg-amber-100 font-bold uppercase tracking-wider border border-amber-200 shrink-0">
                Draft / Rekomendasi
              </span>
              <p className="leading-snug">{data.catatan}</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
