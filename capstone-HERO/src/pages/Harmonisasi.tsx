export default function Harmonisasi() {
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">Harmonisasi Draft vs Eksisting</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
          <h3 className="font-semibold mb-4 text-gray-700">Draft Baru</h3>
          <div className="border-2 border-dashed border-gray-300 rounded-lg h-40 flex items-center justify-center text-gray-500 cursor-pointer hover:bg-gray-50 transition">
            Klik atau Drag & Drop Draft Baru (PDF)
          </div>
        </div>

        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
          <h3 className="font-semibold mb-4 text-gray-700">Peraturan Eksisting</h3>
          <button className="w-full border border-gray-300 rounded-lg p-3 text-left text-gray-500 bg-gray-50">
            Pilih dari Knowledge Base...
          </button>
        </div>
      </div>

      <div className="flex justify-end">
        <button className="bg-ojk-red text-white px-6 py-2 rounded-lg hover:bg-rose-700 transition font-medium">
          Mulai Harmonisasi
        </button>
      </div>
    </div>
  );
}
