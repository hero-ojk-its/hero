import { Outlet, Link, useLocation } from 'react-router-dom';
import { 
  LayoutGrid, 
  BookOpen, 
  FilePlus, 
  Search, 
  Scale, 
  Settings,
  Bell,
  LogOut,
  User
} from 'lucide-react';

export default function DashboardLayout() {
  const location = useLocation();

  const navItems = [
    { name: 'Dashboard', path: '/', icon: <LayoutGrid size={18} /> },
    { name: 'Knowledge Base', path: '/knowledge', icon: <BookOpen size={18} /> },
    { name: 'Ingest Dokumen', path: '/ingest', icon: <FilePlus size={18} /> },
    { name: 'Analisa Regulasi', path: '/analisa', icon: <Search size={18} /> },
    { name: 'Harmonisasi', path: '/harmonisasi', icon: <Scale size={18} /> },
  ];

  return (
    <div className="fixed inset-0 flex flex-col bg-[#F9FAFB] font-sans overflow-hidden">
      {/* Top Header */}
      <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0 z-20">
        <div className="flex items-center w-auto shrink-0 pr-8">
          <h1 className="text-xl font-bold text-gray-900 tracking-tight">HERO<span className="text-red-700">.</span></h1>
          <span className="mx-3 text-gray-300 font-light">|</span>
          <span className="text-[11px] font-semibold text-gray-500 tracking-wider">REGULASI OTOMATIS OJK</span>
        </div>
        
        <div className="flex-1"></div>

        <div className="flex items-center space-x-6 shrink-0">
          <button className="relative text-gray-500 hover:text-gray-700 transition-colors">
            <Bell size={20} />
            <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-700 text-[9px] font-bold text-white ring-2 ring-white">
              3
            </span>
          </button>
          
          <div className="flex items-center space-x-3">
            <div className="flex flex-col text-right">
              <span className="text-sm font-bold text-gray-900 leading-tight">Raditya Pratama</span>
              <span className="text-[11px] text-gray-600 font-medium leading-tight">Analis Regulasi OJK</span>
            </div>
            <div className="h-9 w-9 rounded-full bg-red-800 flex items-center justify-center text-white shrink-0">
              <User size={18} />
            </div>
          </div>
        </div>
      </header>

      {/* Main Body */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* Sidebar */}
        <aside className="w-48 bg-white border-r border-gray-200 flex flex-col shrink-0 z-10 overflow-y-auto">
          <div className="py-4 flex-1">
            <nav className="space-y-1 px-2">
              {navItems.map((item) => {
                const isActive = location.pathname === item.path || (item.path !== '/' && location.pathname.startsWith(item.path));
                return (
                  <Link
                    key={item.name}
                    to={item.path}
                    className={`flex items-center space-x-3 px-3 py-2.5 rounded-md transition-all ${
                      isActive 
                        ? 'bg-red-50 text-red-700 font-semibold relative' 
                        : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900 font-medium'
                    }`}
                  >
                    {isActive && (
                      <div className="absolute left-0 top-0 bottom-0 w-1 bg-red-700 rounded-r-sm" />
                    )}
                    <span className={`${isActive ? 'text-red-700' : 'text-gray-500'}`}>
                      {item.icon}
                    </span>
                    <span className="text-sm">{item.name}</span>
                  </Link>
                );
              })}
            </nav>
          </div>
          
          <div className="p-4 space-y-1">
            <Link
              to="/settings"
              className={`flex items-center space-x-3 px-3 py-2.5 rounded-md transition-colors ${
                location.pathname.startsWith('/settings')
                  ? 'bg-red-50 text-red-700 font-semibold' 
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900 font-medium'
              }`}
            >
              <Settings size={18} className="text-gray-500" />
              <span className="text-sm">Pengaturan</span>
            </Link>
            <button
              className="w-full flex items-center space-x-3 px-3 py-2.5 rounded-md transition-colors text-gray-600 hover:bg-gray-50 hover:text-gray-900 font-medium"
            >
              <LogOut size={18} className="text-gray-500" />
              <span className="text-sm">Keluar</span>
            </button>
          </div>
        </aside>

        {/* Page Content */}
        <main className="flex-1 overflow-auto p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
