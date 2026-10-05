import { useState, useEffect } from 'react';
import { 
  X, 
  Loader2, 
  AlertCircle, 
  Search, 
  CheckCircle, 
  FileText, 
  Save 
} from 'lucide-react';
import { 
  updateDocumentMetadata, 
  updateDocumentStatus, 
  getCategories, 
  type UpdateMetadataIn, 
  type UpdateDocumentStatusIn, 
  type CategoryDetailResponse, 
  type StatusKeberlakuan, 
  type KlasifikasiAkses, 
  type PeranDokumen 
} from '../lib/ingestApi';
import { apiFetch, type DocumentItem } from '../lib/api';
import { 
  STATUS_KEBERLAKUAN_LABELS, 
  KLASIFIKASI_AKSES_LABELS, 
  PERAN_DOKUMEN_LABELS 
} from './ingest/labels';

// ============================================================================
// MODAL 1: Koreksi Metadata Dokumen (TC-10 / G06 / G07)
// ============================================================================

interface EditMetadataModalProps {
  isOpen: boolean;
  onClose: () => void;
  document: DocumentItem;
  onSuccess: (updated: DocumentItem) => void;
}

export function EditMetadataModal(props: EditMetadataModalProps) {
  if (!props.isOpen) return null;
  return <EditMetadataModalContent {...props} />;
}

function EditMetadataModalContent({
  onClose,
  document,
  onSuccess,
}: EditMetadataModalProps) {
  // Form States - diinisialisasi langsung dari data dokumen terkini
  const [title, setTitle] = useState(document.title || '');
  const [regulationNumber, setRegulationNumber] = useState(document.regulation_number || '');
  const [regulationType, setRegulationType] = useState(document.regulation_type || '');
  const [releaseDate, setReleaseDate] = useState(document.release_date || '');
  const [regulationYear, setRegulationYear] = useState(
    document.regulation_year !== null && document.regulation_year !== undefined
      ? String(document.regulation_year)
      : ''
  );
  const [bidang, setBidang] = useState(document.bidang || '');
  const [categoryId, setCategoryId] = useState<number | null>(document.category_id ?? null);
  const [accessClassification, setAccessClassification] = useState<KlasifikasiAkses>(
    (document.access_classification as KlasifikasiAkses) || 'publik'
  );
  const [documentRole, setDocumentRole] = useState<PeranDokumen>(
    (document.document_role as PeranDokumen) || 'corpus_eksisting'
  );

  // Categories & UI States
  const [categories, setCategories] = useState<CategoryDetailResponse[]>([]);
  const [isLoadingCategories, setIsLoadingCategories] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [apiError, setApiError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    getCategories()
      .then((cats) => {
        if (!mounted) return;
        setCategories(cats);
      })
      .catch((err) => console.warn('Gagal memuat kategori:', err))
      .finally(() => {
        if (mounted) setIsLoadingCategories(false);
      });

    return () => {
      mounted = false;
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setApiError(null);
    const errors: Record<string, string> = {};

    // Validasi ringan di klien: tahun harus 4 digit angka (G07)
    if (regulationYear.trim()) {
      if (!/^\d{4}$/.test(regulationYear.trim())) {
        errors.regulation_year = 'Tahun regulasi harus berupa 4 digit angka (contoh: 2024)';
      }
    }

    // Validasi format tanggal YYYY-MM-DD
    if (releaseDate.trim()) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(releaseDate.trim())) {
        errors.release_date = 'Format tanggal terbit harus YYYY-MM-DD (contoh: 2024-12-31)';
      }
    }

    if (Object.keys(errors).length > 0) {
      setValidationErrors(errors);
      return;
    }
    setValidationErrors({});

    // TC-10 / G06: Hitung diff, kirim HANYA field yang berubah
    const payload: UpdateMetadataIn = {};

    if (title.trim() !== (document.title || '')) {
      payload.title = title.trim() || null;
    }
    if (regulationNumber.trim() !== (document.regulation_number || '')) {
      payload.regulation_number = regulationNumber.trim() || null;
    }
    if (regulationType.trim() !== (document.regulation_type || '')) {
      payload.regulation_type = regulationType.trim() || null;
    }
    if (releaseDate.trim() !== (document.release_date || '')) {
      payload.release_date = releaseDate.trim() || null;
    }

    const initialYearStr =
      document.regulation_year !== null && document.regulation_year !== undefined
        ? String(document.regulation_year)
        : '';
    if (regulationYear.trim() !== initialYearStr) {
      payload.regulation_year = regulationYear.trim() ? Number(regulationYear.trim()) : null;
    }

    if (bidang.trim() !== (document.bidang || '')) {
      payload.bidang = bidang.trim() || null;
    }
    if (categoryId !== (document.category_id ?? null)) {
      payload.category_id = categoryId;
    }
    if (accessClassification !== (document.access_classification || 'publik')) {
      payload.access_classification = accessClassification;
    }
    if (documentRole !== (document.document_role || 'corpus_eksisting')) {
      payload.document_role = documentRole;
    }

    // Jika tidak ada perubahan, tutup modal tanpa memanggil API
    if (Object.keys(payload).length === 0) {
      onClose();
      return;
    }

    setIsSubmitting(true);
    try {
      const updatedDoc = await updateDocumentMetadata(document.id, payload);
      onSuccess(updatedDoc);
      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setApiError(msg || 'Gagal menyimpan perubahan metadata.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto animate-in fade-in duration-150">
      <div className="bg-white rounded-2xl shadow-xl border border-gray-200 w-full max-w-2xl my-8 overflow-hidden">
        {/* Header Modal */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gray-50/50">
          <div>
            <h3 className="text-base font-bold text-gray-900">Koreksi Metadata Dokumen</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              ID Dokumen: #{document.id} • Perubahan hanya akan dikirim untuk field yang dimodifikasi.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit}>
          <div className="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
            {apiError && (
              <div className="p-3.5 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-start gap-2">
                <AlertCircle size={16} className="text-red-600 shrink-0 mt-0.5" />
                <span>{apiError}</span>
              </div>
            )}

            {/* Judul Dokumen */}
            <div>
              <label className="block text-xs font-bold text-gray-700 mb-1 uppercase tracking-wider">
                Judul Dokumen
              </label>
              <textarea
                rows={2}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500 transition-colors"
                placeholder="Masukkan judul regulasi..."
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Nomor Regulasi */}
              <div>
                <label className="block text-xs font-bold text-gray-700 mb-1 uppercase tracking-wider">
                  Nomor Regulasi
                </label>
                <input
                  type="text"
                  value={regulationNumber}
                  onChange={(e) => setRegulationNumber(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500 transition-colors"
                  placeholder="Contoh: POJK 11/POJK.03/2024"
                />
              </div>

              {/* Jenis Regulasi */}
              <div>
                <label className="block text-xs font-bold text-gray-700 mb-1 uppercase tracking-wider">
                  Jenis Regulasi
                </label>
                <input
                  type="text"
                  value={regulationType}
                  onChange={(e) => setRegulationType(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500 transition-colors"
                  placeholder="Contoh: POJK, SEOJK, PADK"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Tanggal Terbit */}
              <div>
                <label className="block text-xs font-bold text-gray-700 mb-1 uppercase tracking-wider">
                  Tanggal Terbit (YYYY-MM-DD)
                </label>
                <input
                  type="text"
                  value={releaseDate}
                  onChange={(e) => {
                    setReleaseDate(e.target.value);
                    if (validationErrors.release_date) {
                      setValidationErrors((prev) => ({ ...prev, release_date: '' }));
                    }
                  }}
                  className={`w-full px-3 py-2 border rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500 transition-colors ${
                    validationErrors.release_date ? 'border-red-500 bg-red-50/30' : 'border-gray-300'
                  }`}
                  placeholder="2025-12-30"
                />
                {validationErrors.release_date && (
                  <p className="text-xs text-red-600 mt-1 font-semibold">{validationErrors.release_date}</p>
                )}
              </div>

              {/* Tahun Regulasi */}
              <div>
                <label className="block text-xs font-bold text-gray-700 mb-1 uppercase tracking-wider">
                  Tahun Regulasi
                </label>
                <input
                  type="text"
                  value={regulationYear}
                  onChange={(e) => {
                    setRegulationYear(e.target.value);
                    if (validationErrors.regulation_year) {
                      setValidationErrors((prev) => ({ ...prev, regulation_year: '' }));
                    }
                  }}
                  className={`w-full px-3 py-2 border rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500 transition-colors ${
                    validationErrors.regulation_year ? 'border-red-500 bg-red-50/30' : 'border-gray-300'
                  }`}
                  placeholder="2025"
                />
                {validationErrors.regulation_year && (
                  <p className="text-xs text-red-600 mt-1 font-semibold">{validationErrors.regulation_year}</p>
                )}
              </div>
            </div>

            {/* Bidang */}
            <div>
              <label className="block text-xs font-bold text-gray-700 mb-1 uppercase tracking-wider">
                Bidang / Sektor
              </label>
              <input
                type="text"
                value={bidang}
                onChange={(e) => setBidang(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500 transition-colors"
                placeholder="Contoh: Perbankan, PVML, Pasar Modal"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {/* Kategori */}
              <div>
                <label className="block text-xs font-bold text-gray-700 mb-1 uppercase tracking-wider">
                  Kategori
                </label>
                <select
                  disabled={isLoadingCategories}
                  value={categoryId ?? ''}
                  onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : null)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500 transition-colors"
                >
                  <option value="">(Tanpa Kategori)</option>
                  {categories.map((cat) => (
                    <option key={cat.id} value={cat.id}>
                      {cat.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Klasifikasi Akses */}
              <div>
                <label className="block text-xs font-bold text-gray-700 mb-1 uppercase tracking-wider">
                  Klasifikasi Akses
                </label>
                <select
                  value={accessClassification}
                  onChange={(e) => setAccessClassification(e.target.value as KlasifikasiAkses)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500 transition-colors"
                >
                  <option value="publik">{KLASIFIKASI_AKSES_LABELS.publik}</option>
                  <option value="non_publik">{KLASIFIKASI_AKSES_LABELS.non_publik}</option>
                </select>
              </div>

              {/* Peran Dokumen */}
              <div>
                <label className="block text-xs font-bold text-gray-700 mb-1 uppercase tracking-wider">
                  Peran Dokumen
                </label>
                <select
                  value={documentRole}
                  onChange={(e) => setDocumentRole(e.target.value as PeranDokumen)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500 transition-colors"
                >
                  <option value="corpus_eksisting">{PERAN_DOKUMEN_LABELS.corpus_eksisting}</option>
                  <option value="draft_kajian">{PERAN_DOKUMEN_LABELS.draft_kajian}</option>
                </select>
              </div>
            </div>
          </div>

          {/* Footer Modal */}
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50/50">
            <button
              type="button"
              disabled={isSubmitting}
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 text-gray-700 hover:bg-gray-100 text-xs font-semibold rounded-lg transition-colors cursor-pointer"
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-5 py-2 bg-red-700 hover:bg-red-800 text-white text-xs font-semibold rounded-lg shadow-sm transition-all flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
            >
              {isSubmitting ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Menyimpan...
                </>
              ) : (
                <>
                  <Save size={14} />
                  Simpan Perubahan
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ============================================================================
// MODAL 2: Ubah Status Keberlakuan (TC-20 / G08)
// ============================================================================

interface EditStatusModalProps {
  isOpen: boolean;
  onClose: () => void;
  document: DocumentItem;
  onSuccess: (newStatus: string, message: string, legalReferenceCreated: boolean) => void;
}

export function EditStatusModal(props: EditStatusModalProps) {
  if (!props.isOpen) return null;
  return <EditStatusModalContent {...props} />;
}

function EditStatusModalContent({
  onClose,
  document,
  onSuccess,
}: EditStatusModalProps) {
  const [selectedStatus, setSelectedStatus] = useState<StatusKeberlakuan>(
    (document.status_keberlakuan as StatusKeberlakuan) || 'berlaku'
  );

  // Search Revoking Document States
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<DocumentItem[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [selectedRevokingDoc, setSelectedRevokingDoc] = useState<{
    id: number;
    title: string;
    regulation_number?: string | null;
  } | null>(null);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  // Debounced search for revoking documents
  useEffect(() => {
    const q = searchQuery.trim();
    if (!q || (selectedStatus !== 'dicabut' && selectedStatus !== 'diubah')) {
      return;
    }

    let mounted = true;
    const timer = setTimeout(() => {
      setIsSearching(true);
      apiFetch<{ items: DocumentItem[] }>(
        `/api/v1/documents/?q=${encodeURIComponent(q)}&limit=10`
      )
        .then((res) => {
          if (!mounted) return;
          // Exclude self from revoking candidates
          const filtered = (res.items || []).filter((d) => d.id !== document.id);
          setSearchResults(filtered);
        })
        .catch((err) => console.warn('Gagal mencari dokumen pencabut:', err))
        .finally(() => {
          if (mounted) setIsSearching(false);
        });
    }, 300);

    return () => {
      mounted = false;
      clearTimeout(timer);
    };
  }, [searchQuery, selectedStatus, document.id]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setApiError(null);
    setIsSubmitting(true);

    try {
      const payload: UpdateDocumentStatusIn = {
        status_keberlakuan: selectedStatus,
        revoking_document_id:
          (selectedStatus === 'dicabut' || selectedStatus === 'diubah') && selectedRevokingDoc
            ? selectedRevokingDoc.id
            : null,
      };

      const res = await updateDocumentStatus(document.id, payload);
      onSuccess(res.status_keberlakuan, res.message, res.legal_reference_created);
      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setApiError(msg || 'Gagal memperbarui status dokumen.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const statusOptions: StatusKeberlakuan[] = ['berlaku', 'diubah', 'dicabut', 'tidak_diketahui'];
  const displayedSearchResults = searchQuery.trim() ? searchResults : [];

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto animate-in fade-in duration-150">
      <div className="bg-white rounded-2xl shadow-xl border border-gray-200 w-full max-w-lg my-8 overflow-hidden">
        {/* Header Modal */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gray-50/50">
          <div>
            <h3 className="text-base font-bold text-gray-900">Ubah Status Keberlakuan</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Dokumen #{document.id}: {document.regulation_number || document.title}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit}>
          <div className="p-6 space-y-5">
            {apiError && (
              <div className="p-3.5 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-start gap-2">
                <AlertCircle size={16} className="text-red-600 shrink-0 mt-0.5" />
                <span>{apiError}</span>
              </div>
            )}

            {/* Pilihan Status Keberlakuan */}
            <div>
              <label className="block text-xs font-bold text-gray-700 mb-2 uppercase tracking-wider">
                Status Keberlakuan Baru <span className="text-red-600">*</span>
              </label>
              <div className="grid grid-cols-2 gap-2.5">
                {statusOptions.map((st) => {
                  const isChecked = selectedStatus === st;
                  const label = STATUS_KEBERLAKUAN_LABELS[st] || st;

                  const colorClass =
                    st === 'berlaku'
                      ? 'border-emerald-500 bg-emerald-50/40 text-emerald-900'
                      : st === 'diubah'
                      ? 'border-amber-500 bg-amber-50/40 text-amber-900'
                      : st === 'dicabut'
                      ? 'border-red-500 bg-red-50/40 text-red-900'
                      : 'border-gray-400 bg-gray-50 text-gray-900';

                  return (
                    <label
                      key={st}
                      className={`flex items-center p-3 rounded-xl border-2 cursor-pointer transition-all ${
                        isChecked
                          ? `${colorClass} shadow-xs font-bold`
                          : 'border-gray-200 hover:border-gray-300 text-gray-700 bg-white'
                      }`}
                    >
                      <input
                        type="radio"
                        name="status_keberlakuan"
                        value={st}
                        checked={isChecked}
                        onChange={() => setSelectedStatus(st)}
                        className="mr-2 text-red-600 focus:ring-red-500"
                      />
                      <span className="text-sm">{label}</span>
                    </label>
                  );
                })}
              </div>
            </div>

            {/* Field Dokumen Pencabut / Pengubah (TC-20 / G08) */}
            {(selectedStatus === 'dicabut' || selectedStatus === 'diubah') && (
              <div className="pt-3 border-t border-gray-100 animate-in fade-in duration-200 space-y-2">
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider">
                  {selectedStatus === 'dicabut' ? 'Dicabut Oleh Dokumen' : 'Diubah Oleh Dokumen'} (Opsional)
                </label>
                <p className="text-xs text-gray-500">
                  Cari regulasi pengganti/pencabut untuk menghubungkan referensi hukum secara otomatis.
                </p>

                {selectedRevokingDoc ? (
                  <div className="p-3 bg-red-50/60 border border-red-200 rounded-xl flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 overflow-hidden">
                      <FileText size={18} className="text-red-700 shrink-0" />
                      <div className="text-xs truncate">
                        <span className="font-bold text-gray-900 block truncate">
                          {selectedRevokingDoc.regulation_number || `Dokumen #${selectedRevokingDoc.id}`}
                        </span>
                        <span className="text-gray-600 truncate block">
                          {selectedRevokingDoc.title}
                        </span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setSelectedRevokingDoc(null)}
                      className="p-1 text-gray-400 hover:text-red-700 rounded-md transition-colors shrink-0 cursor-pointer"
                      title="Hapus pilihan"
                    >
                      <X size={16} />
                    </button>
                  </div>
                ) : (
                  <div className="relative">
                    <div className="relative">
                      <Search
                        size={15}
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
                      />
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Ketik judul atau nomor dokumen..."
                        className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-xs bg-white focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
                      />
                      {isSearching && (
                        <Loader2
                          size={14}
                          className="animate-spin text-gray-400 absolute right-3 top-1/2 -translate-y-1/2"
                        />
                      )}
                    </div>

                    {/* Dropdown Hasil Pencarian Dokumen */}
                    {displayedSearchResults.length > 0 && (
                      <div className="absolute z-20 left-0 right-0 mt-1 max-h-48 overflow-y-auto bg-white border border-gray-200 rounded-xl shadow-lg divide-y divide-gray-50">
                        {displayedSearchResults.map((resDoc) => (
                          <div
                            key={resDoc.id}
                            onClick={() => {
                              setSelectedRevokingDoc({
                                id: resDoc.id,
                                title: resDoc.title,
                                regulation_number: resDoc.regulation_number,
                              });
                              setSearchQuery('');
                              setSearchResults([]);
                            }}
                            className="p-2.5 hover:bg-red-50/60 cursor-pointer transition-colors text-xs"
                          >
                            <div className="font-bold text-gray-900">
                              {resDoc.regulation_number || `Dokumen #${resDoc.id}`}
                            </div>
                            <div className="text-gray-500 line-clamp-1 mt-0.5">{resDoc.title}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer Modal */}
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50/50">
            <button
              type="button"
              disabled={isSubmitting}
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 text-gray-700 hover:bg-gray-100 text-xs font-semibold rounded-lg transition-colors cursor-pointer"
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-5 py-2 bg-red-700 hover:bg-red-800 text-white text-xs font-semibold rounded-lg shadow-sm transition-all flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
            >
              {isSubmitting ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Menyimpan Status...
                </>
              ) : (
                <>
                  <CheckCircle size={14} />
                  Simpan Status
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
