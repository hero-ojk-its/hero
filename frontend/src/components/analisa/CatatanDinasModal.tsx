import { useState, useEffect } from 'react';
import type { FormEvent, MouseEvent } from 'react';
import {
  X,
  ScrollText,
  FileText,
  AlertCircle,
  Loader2,
  Info,
} from 'lucide-react';
import { ApiError } from '../../lib/api';
import { exportCatatanDinas } from '../../lib/harmonisasiApi';
import type {
  CatatanDinasExportPayload,
  CatatanDinasExportResult,
} from '../../lib/harmonisasiApi';

export interface CatatanDinasModalProps {
  isOpen: boolean;
  onClose: () => void;
  documentId: number;
  documentTitle?: string | null;
  runId?: number | null;
  belumDinilaiCount?: number;
  onSuccess: (result: CatatanDinasExportResult, format: 'docx' | 'pdf', pakaiAi: boolean) => void;
}

export default function CatatanDinasModal({
  isOpen,
  onClose,
  documentId,
  documentTitle,
  runId,
  belumDinilaiCount = 0,
  onSuccess,
}: CatatanDinasModalProps) {
  // Form state (seluruh field opsional mengikuti kontrak backend)
  const [format, setFormat] = useState<'docx' | 'pdf'>('docx');
  const [pakaiAi, setPakaiAi] = useState<boolean>(false);

  // Kop Catatan Dinas
  const [nomorCd, setNomorCd] = useState<string>('');
  const [tanggalCd, setTanggalCd] = useState<string>('');
  const [yth, setYth] = useState<string>('');
  const [dari, setDari] = useState<string>('');
  const [sifat, setSifat] = useState<string>('Biasa');
  const [lampiran, setLampiran] = useState<string>('');
  const [hal, setHal] = useState<string>('');

  // Rujukan Nota Dinas
  const [unitPeminta, setUnitPeminta] = useState<string>('');
  const [nomorNd, setNomorNd] = useState<string>('');
  const [tanggalNd, setTanggalNd] = useState<string>('');
  const [halNd, setHalNd] = useState<string>('');

  // Catatan Tambahan (Butir 4)
  const [catatanTambahan, setCatatanTambahan] = useState<string>('');

  // Penandatangan
  const [penandatanganJabatan, setPenandatanganJabatan] = useState<string>('');
  const [penandatanganNama, setPenandatanganNama] = useState<string>('');
  const [penandatanganNip, setPenandatanganNip] = useState<string>('');

  // Submission state
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Keyboard accessibility: Escape to close
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape' && !isSubmitting) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isSubmitting, onClose]);

  if (!isOpen) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage(null);

    const payload: CatatanDinasExportPayload = {
      format,
      run_id: runId ?? null,
      pakai_ai: pakaiAi,
      nomor_cd: nomorCd.trim() || null,
      tanggal: tanggalCd || null,
      yth: yth.trim() || null,
      dari: dari.trim() || null,
      sifat: sifat.trim() || null,
      lampiran: lampiran.trim() || null,
      hal: hal.trim() || null,
      unit_peminta: unitPeminta.trim() || null,
      nomor_nd: nomorNd.trim() || null,
      tanggal_nd: tanggalNd || null,
      hal_nd: halNd.trim() || null,
      catatan_tambahan: catatanTambahan.trim() || null,
      penandatangan_jabatan: penandatanganJabatan.trim() || null,
      penandatangan_nama: penandatanganNama.trim() || null,
      penandatangan_nip: penandatanganNip.trim() || null,
    };

    try {
      const result = await exportCatatanDinas(documentId, payload);

      // Pemicu unduhan berkas biner di browser
      const objectUrl = URL.createObjectURL(result.blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = result.filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);

      onSuccess(result, format, pakaiAi);
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        const detailObj = typeof err.detail === 'object' && err.detail !== null ? (err.detail as Record<string, unknown>) : null;
        const code = detailObj?.code;

        if (err.status === 401) {
          setErrorMessage('Sesi Anda telah berakhir. Silakan muat ulang halaman atau masuk kembali.');
        } else if (err.status === 403) {
          setErrorMessage('Akun Anda tidak memiliki izin untuk mengekspor naskah Catatan Dinas (memerlukan izin ANALISA_EKSPOR).');
        } else if (err.status === 404) {
          if (code === 'harmonisasi_belum_ada') {
            setErrorMessage('Dokumen ini belum pernah diharmonisasi. Silakan jalankan harmonisasi terlebih dahulu.');
          } else if (code === 'hasil_tidak_tersedia') {
            setErrorMessage('Hasil eksekusi harmonisasi tidak tersedia untuk dokumen ini.');
          } else {
            setErrorMessage(err.message || 'Dokumen atau hasil harmonisasi tidak ditemukan.');
          }
        } else if (err.status === 422) {
          if (code === 'bukan_draft') {
            setErrorMessage('Hanya dokumen draft kajian yang dapat diekspor ke format Catatan Dinas.');
          } else {
            setErrorMessage(err.message || 'Isian formulir tidak valid. Periksa kembali batas panjang teks.');
          }
        } else {
          setErrorMessage(err.message || `Gagal mengekspor Catatan Dinas (HTTP ${err.status}).`);
        }
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage('Terjadi kendala saat mengekspor Catatan Dinas.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs animate-in fade-in duration-200"
      onClick={(e: MouseEvent<HTMLDivElement>) => {
        if (e.target === e.currentTarget && !isSubmitting) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-cd-title"
        className="bg-white rounded-xl shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh] border border-gray-200"
      >
        {/* Header Modal */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-start justify-between gap-3 bg-gray-50/70 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-red-100 flex items-center justify-center text-red-700 shrink-0">
              <ScrollText size={20} />
            </div>
            <div>
              <h2 id="modal-cd-title" className="text-base font-bold text-gray-900">
                Ekspor Catatan Dinas
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Buat dokumen tanggapan berdasarkan hasil analisis harmonisasi regulasi.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded-lg hover:bg-gray-100 disabled:opacity-50 cursor-pointer"
            title="Tutup (Esc)"
            aria-label="Tutup"
          >
            <X size={18} />
          </button>
        </div>

        {/* Scrollable Form Body */}
        <form id="cd-export-form" onSubmit={handleSubmit} className="p-6 overflow-y-auto flex-1 space-y-5 text-xs text-gray-700">
          {/* Banner Peringatan Temuan Belum Dinilai */}
          {belumDinilaiCount > 0 && (
            <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 flex items-start gap-2 shadow-2xs">
              <Info size={16} className="text-amber-600 shrink-0 mt-0.5" />
              <div className="space-y-0.5 leading-relaxed">
                <span className="font-semibold block">Perhatian Rekap Penilaian:</span>
                <span>
                  Masih terdapat <strong>{belumDinilaiCount} temuan</strong> yang belum dinilai. Temuan tersebut tetap akan dimasukkan ke Catatan Dinas dengan status <em>Belum dinilai</em>. Anda tetap dapat melanjutkan ekspor.
                </span>
              </div>
            </div>
          )}

          {/* Banner Error Permintaan */}
          {errorMessage && (
            <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 flex items-start gap-2 shadow-2xs">
              <AlertCircle size={16} className="text-red-600 shrink-0 mt-0.5" />
              <div className="space-y-0.5 min-w-0">
                <span className="font-semibold block">Gagal Mengunduh Catatan Dinas:</span>
                <span className="break-words">{errorMessage}</span>
              </div>
            </div>
          )}

          {/* Bagian 1: Format Dokumen & Narasi Latar Belakang */}
          <div className="bg-gray-50/80 border border-gray-200 rounded-lg p-3.5 space-y-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <span className="font-bold text-gray-800 uppercase tracking-wider text-[11px] block">
                Format Dokumen
              </span>
              <div className="flex items-center gap-4">
                <label className="inline-flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="radio"
                    name="cd-format"
                    value="docx"
                    checked={format === 'docx'}
                    onChange={() => setFormat('docx')}
                    className="text-red-700 focus:ring-red-600"
                  />
                  <span className="font-semibold text-gray-900">Word (.docx)</span>
                  <span className="text-[10px] text-emerald-700 bg-emerald-50 px-1.5 py-0.2 rounded border border-emerald-200 font-medium">
                    Rekomendasi
                  </span>
                </label>
                <label className="inline-flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="radio"
                    name="cd-format"
                    value="pdf"
                    checked={format === 'pdf'}
                    onChange={() => setFormat('pdf')}
                    className="text-red-700 focus:ring-red-600"
                  />
                  <span className="font-semibold text-gray-900">PDF (.pdf)</span>
                </label>
              </div>
            </div>

            <div className="pt-2.5 border-t border-gray-200/60">
              <span className="font-bold text-gray-800 uppercase tracking-wider text-[11px] block mb-1.5">
                Narasi Latar Belakang
              </span>
              <label className="inline-flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={pakaiAi}
                  onChange={(e) => setPakaiAi(e.target.checked)}
                  className="rounded text-red-700 focus:ring-red-600 mt-0.5"
                />
                <div className="space-y-0.5">
                  <span className="font-semibold text-gray-900 block">
                    Gunakan hasil analisis AI untuk menyusun latar belakang
                  </span>
                  <p className="text-[11px] text-gray-500 leading-normal">
                    Jika diaktifkan dan hasil analisis AI tersedia, sistem akan menggunakan narasi AI untuk menjelaskan latar belakang regulasi. Jika tidak tersedia, sistem tetap membuat dokumen menggunakan ringkasan struktur regulasi secara otomatis.
                  </p>
                </div>
              </label>
            </div>
          </div>

          {/* Kelompok 1: Kop Naskah Catatan Dinas */}
          <div className="space-y-3">
            <div className="flex items-center justify-between border-b border-gray-100 pb-1.5">
              <span className="font-bold text-gray-800 uppercase tracking-wider text-[11px]">
                Kop Naskah Catatan Dinas
              </span>
              <span className="text-[10px] text-gray-400 italic">Semua field opsional (otomatis menggunakan nilai baku jika kosong)</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="font-semibold text-gray-700 block mb-1">Nomor Catatan Dinas</label>
                <input
                  type="text"
                  value={nomorCd}
                  onChange={(e) => setNomorCd(e.target.value)}
                  placeholder="Bawaan: CD-xx/…/xxxx"
                  maxLength={60}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none"
                />
              </div>

              <div>
                <label className="font-semibold text-gray-700 block mb-1">Tanggal Catatan Dinas</label>
                <input
                  type="date"
                  value={tanggalCd}
                  onChange={(e) => setTanggalCd(e.target.value)}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none"
                />
                <span className="text-[10px] text-gray-400 block mt-0.5">
                  Kosongkan bila ingin menggunakan tanda titik-titik (…).
                </span>
              </div>

              <div>
                <label className="font-semibold text-gray-700 block mb-1">Yth. (Tujuan)</label>
                <input
                  type="text"
                  value={yth}
                  onChange={(e) => setYth(e.target.value)}
                  placeholder="Bawaan: Kepala Departemen"
                  maxLength={200}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none"
                />
              </div>

              <div>
                <label className="font-semibold text-gray-700 block mb-1">Dari (Pengirim)</label>
                <input
                  type="text"
                  value={dari}
                  onChange={(e) => setDari(e.target.value)}
                  placeholder="Bawaan: Analis Eksekutif"
                  maxLength={200}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none"
                />
              </div>

              <div>
                <label className="font-semibold text-gray-700 block mb-1">Sifat Naskah Dinas</label>
                <select
                  value={sifat}
                  onChange={(e) => setSifat(e.target.value)}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none bg-white"
                >
                  <option value="Biasa">Biasa (Bawaan)</option>
                  <option value="Segera">Segera</option>
                  <option value="Sangat Segera">Sangat Segera</option>
                  <option value="Rahasia">Rahasia</option>
                </select>
              </div>

              <div>
                <label className="font-semibold text-gray-700 block mb-1">Lampiran</label>
                <input
                  type="text"
                  value={lampiran}
                  onChange={(e) => setLampiran(e.target.value)}
                  placeholder="Bawaan: -"
                  maxLength={120}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none"
                />
              </div>

              <div className="sm:col-span-2">
                <label className="font-semibold text-gray-700 block mb-1">Hal (Perihal)</label>
                <input
                  type="text"
                  value={hal}
                  onChange={(e) => setHal(e.target.value)}
                  placeholder={`Bawaan: Tanggapan atas ${documentTitle || 'draf regulasi'}`}
                  maxLength={300}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none"
                />
              </div>
            </div>
          </div>

          {/* Kelompok 2: Referensi Permintaan Tanggapan */}
          <div className="space-y-3 pt-1">
            <div className="flex items-center justify-between border-b border-gray-100 pb-1.5">
              <span className="font-bold text-gray-800 uppercase tracking-wider text-[11px]">
                Referensi Permintaan Tanggapan
              </span>
              <span className="text-[10px] text-gray-400 italic">Untuk Butir 2 (Riwayat Permintaan Tanggapan)</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="font-semibold text-gray-700 block mb-1">Unit Peminta</label>
                <input
                  type="text"
                  value={unitPeminta}
                  onChange={(e) => setUnitPeminta(e.target.value)}
                  placeholder="Misal: Departemen Pengaturan Perbankan"
                  maxLength={200}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none"
                />
              </div>

              <div>
                <label className="font-semibold text-gray-700 block mb-1">Nomor Nota Dinas</label>
                <input
                  type="text"
                  value={nomorNd}
                  onChange={(e) => setNomorNd(e.target.value)}
                  placeholder="Misal: ND-xx/…/xxxx"
                  maxLength={60}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none"
                />
              </div>

              <div>
                <label className="font-semibold text-gray-700 block mb-1">Tanggal Nota Dinas</label>
                <input
                  type="date"
                  value={tanggalNd}
                  onChange={(e) => setTanggalNd(e.target.value)}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none"
                />
              </div>

              <div>
                <label className="font-semibold text-gray-700 block mb-1">Hal Nota Dinas</label>
                <input
                  type="text"
                  value={halNd}
                  onChange={(e) => setHalNd(e.target.value)}
                  placeholder="Misal: Permohonan Tanggapan Draf..."
                  maxLength={300}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none"
                />
              </div>
            </div>
          </div>

          {/* Kelompok 3: Catatan Tambahan Analis */}
          <div className="space-y-2 pt-1">
            <div className="flex items-center justify-between border-b border-gray-100 pb-1.5">
              <span className="font-bold text-gray-800 uppercase tracking-wider text-[11px]">
                Catatan Tambahan Analis (Butir 4)
              </span>
              <span className={`text-[10px] font-mono ${catatanTambahan.length > 3800 ? 'text-amber-600 font-bold' : 'text-gray-400'}`}>
                {catatanTambahan.length.toLocaleString('id-ID')} / 4.000 karakter
              </span>
            </div>
            <textarea
              rows={3}
              value={catatanTambahan}
              onChange={(e) => setCatatanTambahan(e.target.value)}
              placeholder="Tuliskan catatan khusus atau rekomendasi tambahan bila diperlukan..."
              maxLength={4000}
              className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none leading-relaxed"
            />
            <span className="text-[10px] text-gray-400 block">
              Bila dikosongkan, Butir 4 (Catatan Tambahan) ditiadakan dan penomoran butir penutup otomatis menyesuaikan.
            </span>
          </div>

          {/* Kelompok 4: Penandatangan Naskah Dinas */}
          <div className="space-y-3 pt-1">
            <div className="flex items-center justify-between border-b border-gray-100 pb-1.5">
              <span className="font-bold text-gray-800 uppercase tracking-wider text-[11px]">
                Penandatangan Naskah Dinas
              </span>
              <span className="text-[10px] text-gray-400 italic">Dapat disunting manual di Word</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="font-semibold text-gray-700 block mb-1">Jabatan</label>
                <input
                  type="text"
                  value={penandatanganJabatan}
                  onChange={(e) => setPenandatanganJabatan(e.target.value)}
                  placeholder="Misal: Direktur Pengaturan"
                  maxLength={200}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none"
                />
              </div>

              <div>
                <label className="font-semibold text-gray-700 block mb-1">Nama Lengkap</label>
                <input
                  type="text"
                  value={penandatanganNama}
                  onChange={(e) => setPenandatanganNama(e.target.value)}
                  placeholder="Misal: Budi Santoso, S.H."
                  maxLength={200}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none"
                />
              </div>

              <div>
                <label className="font-semibold text-gray-700 block mb-1">NIP / NRP</label>
                <input
                  type="text"
                  value={penandatanganNip}
                  onChange={(e) => setPenandatanganNip(e.target.value)}
                  placeholder="Misal: 19780512..."
                  maxLength={30}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-md text-xs focus:ring-1 focus:ring-red-600 focus:border-red-600 outline-none"
                />
              </div>
            </div>
          </div>
        </form>

        {/* Modal Footer */}
        <div className="px-6 py-3.5 border-t border-gray-200 bg-gray-50/80 flex items-center justify-between gap-3 shrink-0">
          <span className="text-[11px] text-gray-500">
            Naskah dapat disunting lebih lanjut menggunakan Microsoft Word.
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-3.5 py-1.5 rounded-lg border border-gray-300 bg-white text-xs font-semibold text-gray-700 hover:bg-gray-50 transition cursor-pointer disabled:opacity-50"
            >
              Batal
            </button>
            <button
              type="submit"
              form="cd-export-form"
              disabled={isSubmitting}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold text-white bg-[#990000] hover:bg-[#7a0000] transition cursor-pointer disabled:opacity-60 shadow-xs"
            >
              {isSubmitting ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  <span>Menyiapkan Berkas…</span>
                </>
              ) : (
                <>
                  {format === 'pdf' ? <FileText size={14} /> : <ScrollText size={14} />}
                  <span>Unduh Catatan Dinas ({format.toUpperCase()})</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
