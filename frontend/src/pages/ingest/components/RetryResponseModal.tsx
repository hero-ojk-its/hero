import { X, CheckCircle2, AlertTriangle, AlertCircle } from 'lucide-react';

export interface RetryModalData {
  isOpen: boolean;
  status: 'sukses' | 'gagal' | 'konflik';
  title: string;
  message: string;
  detail?: unknown;
  httpStatus?: number;
}

interface RetryResponseModalProps {
  data: RetryModalData | null;
  onClose: () => void;
}

export default function RetryResponseModal({ data, onClose }: RetryResponseModalProps) {
  if (!data || !data.isOpen) return null;

  const isSuccess = data.status === 'sukses';
  const isConflict = data.status === 'konflik';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg overflow-hidden flex flex-col">
        {/* Modal Header */}
        <div className={`px-6 py-4 border-b flex items-center justify-between ${
          isSuccess
            ? 'bg-emerald-50/70 border-emerald-200'
            : isConflict
            ? 'bg-amber-50/70 border-amber-200'
            : 'bg-rose-50/70 border-rose-200'
        }`}>
          <div className="flex items-center space-x-2.5">
            {isSuccess ? (
              <CheckCircle2 className="text-emerald-600 flex-shrink-0" size={22} />
            ) : isConflict ? (
              <AlertTriangle className="text-amber-600 flex-shrink-0" size={22} />
            ) : (
              <AlertCircle className="text-rose-600 flex-shrink-0" size={22} />
            )}
            <div>
              <h3 className="text-base font-bold text-gray-900 leading-tight">
                {data.title}
              </h3>
              {data.httpStatus && (
                <span className="text-[11px] font-mono font-medium text-gray-600">
                  HTTP Status: {data.httpStatus} {isConflict ? '(Conflict)' : ''}
                </span>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 p-1 rounded-lg hover:bg-white/60 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Content */}
        <div className="p-6 space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
              Respons Backend Apa Adanya:
            </p>
            <div className={`p-4 rounded-lg border text-sm leading-relaxed ${
              isSuccess
                ? 'bg-emerald-50/50 border-emerald-200 text-emerald-900 font-medium'
                : isConflict
                ? 'bg-amber-50/50 border-amber-200 text-amber-900 font-medium'
                : 'bg-rose-50/50 border-rose-200 text-rose-900 font-medium'
            }`}>
              {data.message}
            </div>
          </div>

          {Boolean(data.detail) && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Potongan Data Mentah (Payload):</p>
              <pre className="bg-gray-900 text-gray-100 p-3 rounded-lg text-xs font-mono overflow-x-auto max-h-48 border border-gray-800">
                {typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail, null, 2)}
              </pre>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t border-gray-200 bg-gray-50 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors shadow-sm"
          >
            Tutup
          </button>
        </div>
      </div>
    </div>
  );
}
