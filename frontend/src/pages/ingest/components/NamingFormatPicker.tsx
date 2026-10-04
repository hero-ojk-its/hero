import { useState, useEffect, useRef } from 'react';
import { Plus, X, AlertTriangle, AlertCircle, FileText, Loader2 } from 'lucide-react';
import { 
  getNamingComponents, 
  previewNaming,
  type NamingComponentItem, 
  type NamingSampleInput 
} from '../../../lib/ingestApi';

interface NamingFormatPickerProps {
  value: string[];
  onChange: (format: string[]) => void;
  separator: string;
  onSeparatorChange: (sep: string) => void;
  sampleInput?: NamingSampleInput | null;
  documentId?: number | null;
  disabled?: boolean;
}

export default function NamingFormatPicker({
  value,
  onChange,
  separator,
  onSeparatorChange,
  sampleInput,
  documentId,
  disabled = false,
}: NamingFormatPickerProps) {
  const [components, setComponents] = useState<NamingComponentItem[]>([
    { key: 'nomor', label: 'Nomor' },
    { key: 'nama', label: 'Nama' },
    { key: 'tahun', label: 'Tahun' },
    { key: 'jenis', label: 'Jenis' },
    { key: 'bidang', label: 'Bidang' },
  ]);
  const [separators, setSeparators] = useState<string[]>([' ', '_', '-']);
  const [defaultFormat, setDefaultFormat] = useState<string[]>(['nomor', 'nama', 'tahun']);
  const [maxComponents, setMaxComponents] = useState<number>(8);

  const [previewFilename, setPreviewFilename] = useState<string>('');
  const [missingComponents, setMissingComponents] = useState<string[]>([]);
  const [isPreviewLoading, setIsPreviewLoading] = useState<boolean>(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const previewTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load naming components metadata from backend
  useEffect(() => {
    let mounted = true;
    getNamingComponents()
      .then((res) => {
        if (!mounted) return;
        if (res.components && res.components.length > 0) {
          setComponents(res.components);
        }
        if (res.separators && res.separators.length > 0) {
          setSeparators(res.separators);
        }
        if (res.default_format && res.default_format.length > 0) {
          setDefaultFormat(res.default_format);
        }
        if (res.max_components) {
          setMaxComponents(res.max_components);
        }
      })
      .catch((err) => {
        console.warn('Gagal memuat komponen penamaan dari API, menggunakan bawaan:', err);
      });

    return () => {
      mounted = false;
    };
  }, []);

  // Debounced live preview (300 ms)
  useEffect(() => {
    if (previewTimeoutRef.current) {
      clearTimeout(previewTimeoutRef.current);
    }

    const activeFormat = value.length > 0 ? value : defaultFormat;

    previewTimeoutRef.current = setTimeout(async () => {
      setIsPreviewLoading(true);
      setPreviewError(null);
      try {
        const fallbackSample: NamingSampleInput = sampleInput || {
          regulation_number: 'POJK 11/POJK.03/2024',
          title: 'Ketahanan dan Keamanan Siber Bank Umum',
          regulation_type: 'POJK',
          regulation_year: 2024,
          bidang: 'Perbankan',
        };

        const res = await previewNaming({
          naming_format: activeFormat,
          naming_separator: separator,
          sample: documentId ? null : fallbackSample,
          document_id: documentId || null,
        });

        setPreviewFilename(res.filename);
        setMissingComponents(res.missing_components || []);
        setPreviewError(null);
      } catch (err: unknown) {
        console.warn('Gagal memuat pratinjau penamaan:', err);
        setPreviewFilename('');
        setMissingComponents([]);
        const errorMsg =
          err instanceof Error && err.message
            ? err.message
            : 'Gagal memuat pratinjau nama berkas dari server.';
        setPreviewError(errorMsg);
      } finally {
        setIsPreviewLoading(false);
      }
    }, 300);

    return () => {
      if (previewTimeoutRef.current) {
        clearTimeout(previewTimeoutRef.current);
      }
    };
  }, [value, separator, sampleInput, documentId, defaultFormat]);

  const handleAddComponent = (key: string) => {
    if (disabled) return;
    if (value.includes(key)) return; // Tidak boleh duplikat komponen
    if (value.length >= maxComponents) return;
    onChange([...value, key]);
  };

  const handleRemoveComponent = (indexToRemove: number) => {
    if (disabled) return;
    onChange(value.filter((_, idx) => idx !== indexToRemove));
  };

  const handleClear = () => {
    if (disabled) return;
    onChange([]);
  };

  const handleSetDefault = () => {
    if (disabled) return;
    onChange([...defaultFormat]);
  };

  const getComponentLabel = (key: string): string => {
    const found = components.find((c) => c.key === key);
    return found ? found.label : key;
  };

  const separatorLabels: Record<string, string> = {
    ' ': 'Spasi (" ")',
    '_': 'Underscore ("_")',
    '-': 'Strip ("-")',
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-semibold text-gray-900">
          Format Nama Berkas Dinamis
        </label>
        <div className="flex items-center space-x-2 text-xs">
          <button
            type="button"
            onClick={handleSetDefault}
            disabled={disabled}
            className="text-red-700 hover:text-red-800 font-medium transition-colors disabled:opacity-50"
          >
            Gunakan Default
          </button>
          <span className="text-gray-300">•</span>
          <button
            type="button"
            onClick={handleClear}
            disabled={disabled || value.length === 0}
            className="text-gray-500 hover:text-red-600 font-medium transition-colors disabled:opacity-50"
          >
            Kosongkan
          </button>
        </div>
      </div>

      {/* Komponen yang Dipilih (Chips Bar) */}
      <div className="p-3 border border-gray-200 rounded-xl bg-gray-50/70 min-h-[48px] flex items-center flex-wrap gap-2">
        {value.length === 0 ? (
          <div className="flex items-center text-xs text-gray-500">
            <span className="font-medium mr-1.5 text-gray-700">Format Default Backend:</span>
            <span className="font-mono bg-white px-2 py-0.5 rounded border border-gray-200 text-gray-800">
              {defaultFormat.map(getComponentLabel).join(separator === ' ' ? ' ' : ` ${separator} `)}
            </span>
          </div>
        ) : (
          value.map((compKey, index) => (
            <div
              key={`${compKey}-${index}`}
              className="inline-flex items-center bg-white border border-gray-300 text-gray-800 px-2.5 py-1 rounded-lg text-xs font-semibold shadow-2xs group"
            >
              <span className="text-[10px] text-gray-400 font-mono mr-1.5">{index + 1}.</span>
              <span>{getComponentLabel(compKey)}</span>
              {!disabled && (
                <button
                  type="button"
                  onClick={() => handleRemoveComponent(index)}
                  className="ml-1.5 text-gray-400 hover:text-red-600 rounded p-0.5 transition-colors"
                >
                  <X size={12} />
                </button>
              )}
            </div>
          ))
        )}
      </div>

      {/* Tombol Pilihan Komponen & Pemisah */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
        {/* Pilihan Komponen */}
        <div>
          <span className="block text-xs font-medium text-gray-700 mb-1.5">
            Tambah Komponen Penamaan (Maks. {maxComponents}):
          </span>
          <div className="flex flex-wrap gap-1.5">
            {components.map((comp) => {
              const isSelected = value.includes(comp.key);
              return (
                <button
                  key={comp.key}
                  type="button"
                  disabled={disabled || isSelected || value.length >= maxComponents}
                  onClick={() => handleAddComponent(comp.key)}
                  className={`inline-flex items-center px-2.5 py-1 text-xs font-medium rounded-lg border transition-all ${
                    isSelected
                      ? 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
                      : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400 shadow-2xs'
                  }`}
                >
                  <Plus size={11} className="mr-1 text-gray-400" />
                  {comp.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Pilihan Pemisah (Separator) */}
        <div>
          <span className="block text-xs font-medium text-gray-700 mb-1.5">Karakter Pemisah:</span>
          <div className="flex items-center gap-1.5">
            {separators.map((sep) => {
              const isSepSelected = separator === sep;
              return (
                <button
                  key={sep}
                  type="button"
                  disabled={disabled}
                  onClick={() => onSeparatorChange(sep)}
                  className={`px-3 py-1 rounded-lg text-xs font-medium border transition-all ${
                    isSepSelected
                      ? 'border-red-600 bg-red-50 text-red-700 font-semibold ring-1 ring-red-600'
                      : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  {separatorLabels[sep] || `"${sep}"`}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Pratinjau Langsung (Live Preview) */}
      <div className="p-3 bg-white border border-gray-200 rounded-xl">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-semibold text-gray-700 flex items-center">
            <FileText size={13} className="mr-1 text-red-600" />
            Pratinjau Nama Berkas Standar:
          </span>
          {isPreviewLoading && (
            <span className="flex items-center text-[11px] text-gray-400 font-medium">
              <Loader2 size={11} className="animate-spin mr-1" />
              Menghitung...
            </span>
          )}
        </div>
        {previewError ? (
          <div className="p-2.5 bg-red-50 rounded-lg border border-red-200 text-xs text-red-700 flex items-start">
            <AlertCircle size={14} className="mr-1.5 mt-0.5 shrink-0 text-red-600" />
            <span>{previewError}</span>
          </div>
        ) : (
          <div className="p-2 bg-gray-50 rounded-lg border border-gray-200 text-xs font-mono text-gray-800 break-all select-all">
            {previewFilename || 'Memuat contoh nama berkas...'}
          </div>
        )}

        {!previewError && missingComponents.length > 0 && (
          <div className="flex items-center mt-2 text-[11px] text-amber-700 bg-amber-50 px-2.5 py-1.5 rounded-lg border border-amber-200">
            <AlertTriangle size={13} className="mr-1.5 shrink-0 text-amber-600" />
            <span>
              Komponen <span className="font-semibold">{missingComponents.map(getComponentLabel).join(', ')}</span> tidak ditemukan pada sampel ini dan akan diisi wildcard &quot;NA&quot;.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
