import { useState } from 'react';
import { Layers, CheckCircle, Ban, ArrowRightLeft } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function Dashboard() {
  const [statDimension, setStatDimension] = useState('Kategori');

  const statData = {
    Kategori: [
      { label: 'Perbankan', value: 42, pct: '32.8%', param: 'kategori' },
      { label: 'Pasar Modal', value: 28, pct: '21.9%', param: 'kategori' },
      { label: 'Fintech', value: 22, pct: '17.2%', param: 'kategori' },
      { label: 'Asuransi', value: 18, pct: '14.1%', param: 'kategori' },
      { label: 'Tata Kelola IT & AI', value: 12, pct: '9.4%', param: 'kategori' },
      { label: 'Lainnya', value: 6, pct: '4.7%', param: 'kategori' },
    ],
    'Jenis Regulasi': [
      { label: 'POJK', value: 60, pct: '46.8%', param: 'jenis' },
      { label: 'SEOJK', value: 35, pct: '27.3%', param: 'jenis' },
      { label: 'PDK', value: 20, pct: '15.6%', param: 'jenis' },
      { label: 'SEDK', value: 13, pct: '10.3%', param: 'jenis' },
    ],
    Tahun: [
      { label: '2026', value: 35, pct: '27.3%', param: 'tahun' },
      { label: '2025', value: 31, pct: '24.2%', param: 'tahun' },
      { label: '2024', value: 28, pct: '21.8%', param: 'tahun' },
      { label: '2023', value: 20, pct: '15.6%', param: 'tahun' },
      { label: '2022', value: 14, pct: '11.1%', param: 'tahun' },
    ],
    Topik: [
      { label: 'Ketahanan Siber', value: 32, pct: '25.0%', param: 'topik' },
      { label: 'Tata Kelola', value: 28, pct: '21.8%', param: 'topik' },
      { label: 'AI', value: 24, pct: '18.7%', param: 'topik' },
      { label: 'Perlindungan Konsumen', value: 23, pct: '17.9%', param: 'topik' },
      { label: 'Manajemen Risiko', value: 21, pct: '16.6%', param: 'topik' },
    ]
  };

  const currentStats = statData[statDimension as keyof typeof statData];

  const subtitles = {
    Kategori: 'Sebaran cakupan regulasi per sektor industri',
    'Jenis Regulasi': 'Distribusi dokumen berdasarkan klasifikasi jenis peraturan',
    Tahun: 'Tren penerbitan regulasi dari waktu ke waktu',
    Topik: 'Fokus utama area pengaturan dan pengawasan'
  };
  return (
    <div className="max-w-[1200px] mx-auto space-y-6">
      {/* Header Section */}
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Selamat datang di HERO</h2>
        <p className="text-gray-500 mt-1 text-sm">Pantau kondisi regulasi dan aktivitas sistem dalam satu tempat.</p>
      </div>

      {/* Top 4 Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Card 1 */}
        <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col justify-between">
          <div className="flex justify-between items-start">
            <h3 className="text-[11px] font-bold text-gray-500 tracking-wider">TOTAL REGULASI</h3>
            <div className="text-gray-400 bg-gray-100/50 p-1.5 rounded-lg border border-gray-100">
              <Layers size={16} />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold text-gray-900">128</span>
            <p className="text-[11px] text-gray-500 mt-1 font-medium">Seluruh regulasi dalam sistem</p>
          </div>
        </div>
        
        {/* Card 2 */}
        <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col justify-between">
          <div className="flex justify-between items-start">
            <h3 className="text-[11px] font-bold text-gray-500 tracking-wider">REGULASI BERLAKU</h3>
            <div className="text-green-600 bg-green-50 p-1.5 rounded-lg border border-green-100">
              <CheckCircle size={16} />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold text-green-600">96</span>
            <p className="text-[11px] text-gray-500 mt-1 font-medium">Regulasi yang masih berlaku</p>
          </div>
        </div>

        {/* Card 3 */}
        <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col justify-between">
          <div className="flex justify-between items-start">
            <h3 className="text-[11px] font-bold text-gray-500 tracking-wider">DICABUT / TIDAK BERLAKU</h3>
            <div className="text-gray-500 bg-gray-100 p-1.5 rounded-lg border border-gray-200">
              <Ban size={16} />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold text-gray-900">12</span>
            <p className="text-[11px] text-gray-500 mt-1 font-medium">Regulasi tidak lagi berlaku</p>
          </div>
        </div>

        {/* Card 4 */}
        <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col justify-between">
          <div className="flex justify-between items-start">
            <h3 className="text-[11px] font-bold text-gray-500 tracking-wider">REGULASI DIUBAH</h3>
            <div className="text-amber-600 bg-amber-50 p-1.5 rounded-lg border border-amber-100">
              <ArrowRightLeft size={16} />
            </div>
          </div>
          <div className="mt-4">
            <span className="text-3xl font-bold text-amber-600">20</span>
            <p className="text-[11px] text-gray-500 mt-1 font-medium">Regulasi yang memiliki perubahan</p>
          </div>
        </div>
      </div>

      {/* Middle Row */}
      <div className="grid grid-cols-1 gap-4">
        {/* Statistik Regulasi (Adjustable Placeholder) */}
        <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6">
            <div>
              <h3 className="text-base font-bold text-gray-900">Statistik Regulasi</h3>
              <p className="text-xs text-gray-500 mt-1">{subtitles[statDimension as keyof typeof subtitles]}</p>
            </div>
            <div className="flex items-center space-x-3 mt-4 sm:mt-0">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Berdasarkan:</span>
              <select 
                value={statDimension}
                onChange={(e) => setStatDimension(e.target.value)}
                className="text-sm font-medium border-gray-300 rounded-lg focus:ring-[#B91C1C] focus:border-[#B91C1C] py-2 pl-3 pr-8 shadow-sm"
              >
                <option>Kategori</option>
                <option>Jenis Regulasi</option>
                <option>Tahun</option>
                <option>Topik</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2">
            {currentStats.map((item, idx) => (
              <Link key={idx} to={`/knowledge?${item.param}=${encodeURIComponent(item.label)}`} className="block group">
                <div className="space-y-2 p-3 -mx-3 rounded-lg hover:bg-red-50/50 transition-colors cursor-pointer border border-transparent hover:border-red-100">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-semibold text-gray-800 group-hover:text-[#B91C1C] transition-colors flex items-center">
                      {item.label}
                    </span>
                    <div className="flex items-center space-x-4">
                      <span className="font-bold text-gray-900 group-hover:text-[#B91C1C] transition-colors">{item.value}</span>
                      <span className="text-gray-500 text-xs w-10 text-right">{item.pct}</span>
                    </div>
                  </div>
                  <div className="w-full bg-gray-100 h-1.5 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-[#B91C1C] group-hover:bg-red-800 transition-colors rounded-full"
                      style={{ width: item.pct }}
                    />
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom Row */}
      <div className="pt-2">
        <h3 className="text-base font-bold text-gray-900">Ringkasan Aktivitas Sistem</h3>
        <p className="text-xs text-gray-500 mt-1 mb-4">Status pemrosesan alur kerja dan antrean telaah regulasi saat ini</p>
        
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col">
            <div className="flex justify-between items-center mb-3">
              <span className="text-sm font-semibold text-gray-800">Perlu Ditinjau</span>
              <div className="w-2.5 h-2.5 rounded-full bg-amber-500" />
            </div>
            <span className="text-3xl font-bold text-gray-900">24</span>
            <p className="text-[11px] text-gray-500 mt-2 font-medium">Menunggu telaah analis hukum</p>
          </div>

          <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col">
            <div className="flex justify-between items-center mb-3">
              <span className="text-sm font-semibold text-gray-800">Sedang Diproses</span>
              <div className="w-2.5 h-2.5 rounded-full bg-blue-700" />
            </div>
            <span className="text-3xl font-bold text-gray-900">20</span>
            <p className="text-[11px] text-gray-500 mt-2 font-medium">Dalam antrean ekstraksi & parsing</p>
          </div>

          <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col">
            <div className="flex justify-between items-center mb-3">
              <span className="text-sm font-semibold text-gray-800">Harmonisasi Aktif</span>
              <div className="w-2.5 h-2.5 rounded-full bg-green-600" />
            </div>
            <span className="text-3xl font-bold text-gray-900">20</span>
            <p className="text-[11px] text-gray-500 mt-2 font-medium">Komparasi pasal lintas regulasi</p>
          </div>

          <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex flex-col">
            <div className="flex justify-between items-center mb-3">
              <span className="text-sm font-semibold text-gray-800">Analisa Regulasi</span>
              <div className="w-2.5 h-2.5 rounded-full bg-red-700" />
            </div>
            <span className="text-3xl font-bold text-gray-900">12</span>
            <p className="text-[11px] text-gray-500 mt-2 font-medium">Telaah analisa & tanggapan regulasi</p>
          </div>
        </div>
      </div>
    </div>
  );
}
