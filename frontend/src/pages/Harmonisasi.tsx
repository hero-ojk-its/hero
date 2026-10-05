import { AlertTriangle } from 'lucide-react';

export default function Harmonisasi() {
  return (
    <div className="space-y-6">
      {/* Banner Pratinjau Desain Fase 2 */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start space-x-3">
        <AlertTriangle className="text-amber-700 shrink-0 mt-0.5" size={20} />
        <div>
          <h4 className="text-sm font-bold text-amber-900">
            Pratinjau desain — fitur Fase 2, belum berfungsi
          </h4>
          <p className="text-xs text-amber-800 mt-0.5">
            Fitur harmonisasi dan komparasi draft vs peraturan eksisting saat ini dalam tahap pratinjau desain antarmuka dan akan diaktifkan pada Fase 2.
          </p>
        </div>
      </div>

      <h2 className="text-xl font-bold">Harmonisasi Draft vs Eksisting</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
          <h3 className="font-semibold mb-4 text-gray-700">Draft Baru</h3>
          <div className="border-2 border-dashed border-gray-300 rounded-lg h-40 flex items-center justify-center text-gray-500 cursor-not-allowed bg-gray-50/50">
            Klik atau Drag & Drop Draft Baru (PDF)
          </div>
        </div>

        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
          <h3 className="font-semibold mb-4 text-gray-700">Peraturan Eksisting</h3>
          <button disabled className="w-full border border-gray-300 rounded-lg p-3 text-left text-gray-400 bg-gray-50 cursor-not-allowed">
            Pilih dari Knowledge Base...
          </button>
        </div>
      </div>

      <div className="flex justify-end">
        <button
          disabled
          className="bg-gray-400 text-white px-6 py-2 rounded-lg cursor-not-allowed font-medium opacity-60 shadow-sm"
          title="Pratinjau desain — fitur Fase 2, belum berfungsi"
        >
          Mulai Harmonisasi
        </button>
      </div>
    </div>
  );
}
