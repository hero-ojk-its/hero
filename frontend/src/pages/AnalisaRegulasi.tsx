import { Search, BookOpen } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function AnalisaRegulasi() {
  return (
    <div className="max-w-[1200px] mx-auto space-y-6">
      {/* Header Section */}
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Analisa Regulasi</h2>
        <p className="text-gray-500 mt-1 text-sm">
          Telaah mendalam dan analisis dampak regulasi sektor jasa keuangan.
        </p>
      </div>

      {/* Empty State / Segera Hadir Banner */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-12 flex flex-col items-center justify-center text-center my-4">
        <div className="p-4 bg-red-50 text-red-700 rounded-full mb-4 ring-8 ring-red-50/50">
          <Search className="w-8 h-8 text-red-700" />
        </div>
        <h3 className="text-lg font-bold text-gray-900 mb-2">Segera hadir — Fase 2</h3>
        <p className="text-sm text-gray-500 max-w-md mb-6 leading-relaxed">
          Fitur analisa regulasi mendalam dan telaah tanggapan regulasi sedang disiapkan untuk Fase 2.
        </p>
        <Link
          to="/knowledge"
          className="inline-flex items-center px-4 py-2 bg-red-700 hover:bg-red-800 text-white rounded-lg text-sm font-semibold transition-colors shadow-sm"
        >
          <BookOpen size={16} className="mr-2" />
          Kembali ke Knowledge Base
        </Link>
      </div>
    </div>
  );
}
