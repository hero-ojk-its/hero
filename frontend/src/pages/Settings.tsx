import { Link } from 'react-router-dom';
import { History, Users } from 'lucide-react';

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

        <hr className="border-gray-100" />

        <div>
          <h3 className="font-semibold text-gray-800 mb-2">Administrasi Sistem</h3>
          <p className="text-sm text-gray-500 mb-4">Navigasi ke modul keamanan dan manajemen pengguna sistem.</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Link
              to="/audit-logs"
              className="p-4 border border-gray-200 rounded-lg hover:border-red-300 hover:bg-red-50/30 transition flex items-center space-x-3 group"
            >
              <div className="p-2.5 bg-red-100 text-red-700 rounded-lg group-hover:bg-red-200">
                <History size={18} />
              </div>
              <div>
                <h4 className="font-semibold text-gray-900 text-sm">Audit Log</h4>
                <p className="text-xs text-gray-500">Lihat jejak aktivitas dan riwayat sistem</p>
              </div>
            </Link>
            <Link
              to="/users"
              className="p-4 border border-gray-200 rounded-lg hover:border-red-300 hover:bg-red-50/30 transition flex items-center space-x-3 group"
            >
              <div className="p-2.5 bg-red-100 text-red-700 rounded-lg group-hover:bg-red-200">
                <Users size={18} />
              </div>
              <div>
                <h4 className="font-semibold text-gray-900 text-sm">Kelola Pengguna</h4>
                <p className="text-xs text-gray-500">Daftar akun dan hak akses pengguna</p>
              </div>
            </Link>
          </div>
        </div>
        
        <div className="pt-4">
          <button className="bg-ojk-red text-white px-6 py-2 rounded-lg hover:bg-rose-700 transition font-medium cursor-pointer">
            Simpan Pengaturan
          </button>
        </div>
      </div>
    </div>
  );
}
