export default function Settings() {
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">Pengaturan Sistem</h2>
      
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 space-y-6">
        <div>
          <h3 className="font-semibold text-gray-800 mb-2">Mode Pemrosesan Default</h3>
          <p className="text-sm text-gray-500 mb-4">Pilih mode yang akan digunakan secara otomatis pada seluruh fitur (Dapat diubah secara global di header).</p>
          
          <div className="flex space-x-4">
            <label className="flex items-center space-x-2 cursor-pointer">
              <input type="radio" name="mode" className="text-ojk-red focus:ring-ojk-red" defaultChecked />
              <span>Deterministik (Cepat & Kaku)</span>
            </label>
            <label className="flex items-center space-x-2 cursor-pointer">
              <input type="radio" name="mode" className="text-ojk-red focus:ring-ojk-red" />
              <span>AI-Assisted (Lambat & Natural)</span>
            </label>
          </div>
        </div>
        
        <hr className="border-gray-100" />
        
        <div>
          <h3 className="font-semibold text-gray-800 mb-2">Konfigurasi Folder Publik</h3>
          <p className="text-sm text-gray-500 mb-4">Atur path OneDrive atau folder lokal untuk ingest otomatis.</p>
          <input 
            type="text" 
            placeholder="C:\Users\Public\OneDrive - OJK\Peraturan..." 
            className="border border-gray-300 rounded-lg px-4 py-2 w-full max-w-xl"
          />
        </div>
        
        <div className="pt-4">
          <button className="bg-ojk-red text-white px-6 py-2 rounded-lg hover:bg-rose-700 transition font-medium">
            Simpan Pengaturan
          </button>
        </div>
      </div>
    </div>
  );
}
