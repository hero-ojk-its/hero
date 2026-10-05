import { useState, useEffect } from 'react';
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
  User,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';

const STORAGE_KEY = 'hero_sidebar_collapsed';

function readCollapsed(): boolean {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null) return stored === 'true';
  } catch {
    // ignore
  }
  // Default: auto-collapse on narrow screen
  return typeof window !== 'undefined' && window.innerWidth < 768;
}

export default function DashboardLayout() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState<boolean>(readCollapsed);

  // Auto-collapse on narrow screen resize
  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth < 768) {
        setCollapsed(true);
      }
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // Persist preference
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(collapsed));
    } catch {
      // ignore
    }
  }, [collapsed]);

  const navItems = [
    { name: 'Dashboard', path: '/', icon: <LayoutGrid size={18} aria-hidden="true" /> },
    { name: 'Knowledge Base', path: '/knowledge', icon: <BookOpen size={18} aria-hidden="true" /> },
    { name: 'Ingest Dokumen', path: '/ingest', icon: <FilePlus size={18} aria-hidden="true" /> },
    { name: 'Analisa Regulasi', path: '/analisa', icon: <Search size={18} aria-hidden="true" /> },
    { name: 'Harmonisasi', path: '/harmonisasi', icon: <Scale size={18} aria-hidden="true" /> },
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
        <aside
          className={[
            'bg-white border-r border-gray-200 flex flex-col shrink-0 z-10 overflow-hidden',
            'transition-[width] duration-200 ease-in-out',
            'motion-reduce:transition-none',
            collapsed ? 'w-16' : 'w-48',
          ].join(' ')}
          aria-label="Navigasi utama"
        >
          {/* Toggle button */}
          <div className={`flex ${collapsed ? 'justify-center' : 'justify-end'} px-2 pt-3 pb-1 shrink-0`}>
            <button
              type="button"
              onClick={() => setCollapsed((c) => !c)}
              aria-label={collapsed ? 'Buka sidebar' : 'Ciutkan sidebar'}
              aria-expanded={!collapsed}
              className="p-1.5 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-600"
            >
              {collapsed
                ? <PanelLeftOpen size={18} aria-hidden="true" />
                : <PanelLeftClose size={18} aria-hidden="true" />
              }
            </button>
          </div>

          {/* Main nav */}
          <div className="py-1 flex-1 overflow-y-auto">
            <nav className="space-y-1 px-2" aria-label="Menu utama">
              {navItems.map((item) => {
                const isActive = location.pathname === item.path || (item.path !== '/' && location.pathname.startsWith(item.path));
                return (
                  <Link
                    key={item.name}
                    to={item.path}
                    title={collapsed ? item.name : undefined}
                    aria-label={item.name}
                    className={`relative flex items-center rounded-md transition-all overflow-hidden ${
                      collapsed ? 'justify-center px-0 py-2.5' : 'space-x-3 px-3 py-2.5'
                    } ${
                      isActive 
                        ? 'bg-red-50 text-red-700 font-semibold' 
                        : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900 font-medium'
                    }`}
                  >
                    {isActive && (
                      <div className="absolute left-0 top-0 bottom-0 w-1 bg-red-700 rounded-r-sm" />
                    )}
                    <span className={`shrink-0 ${isActive ? 'text-red-700' : 'text-gray-500'}`}>
                      {item.icon}
                    </span>
                    {!collapsed && (
                      <span className="text-sm truncate">{item.name}</span>
                    )}
                  </Link>
                );
              })
              }
            </nav>
          </div>
          
          {/* Bottom links */}
          <div className="p-2 space-y-1 shrink-0">
            <Link
              to="/settings"
              title={collapsed ? 'Pengaturan' : undefined}
              aria-label="Pengaturan"
              className={`relative flex items-center rounded-md transition-colors overflow-hidden ${
                collapsed ? 'justify-center px-0 py-2.5' : 'space-x-3 px-3 py-2.5'
              } ${
                location.pathname.startsWith('/settings')
                  ? 'bg-red-50 text-red-700 font-semibold' 
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900 font-medium'
              }`}
            >
              {location.pathname.startsWith('/settings') && (
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-red-700 rounded-r-sm" />
              )}
              <Settings size={18} className="shrink-0 text-gray-500" aria-hidden="true" />
              {!collapsed && <span className="text-sm">Pengaturan</span>}
            </Link>
            <button
              type="button"
              aria-label="Keluar"
              title={collapsed ? 'Keluar' : undefined}
              className={`w-full flex items-center rounded-md transition-colors text-gray-600 hover:bg-gray-50 hover:text-gray-900 font-medium overflow-hidden ${
                collapsed ? 'justify-center px-0 py-2.5' : 'space-x-3 px-3 py-2.5'
              }`}
            >
              <LogOut size={18} className="shrink-0 text-gray-500" aria-hidden="true" />
              {!collapsed && <span className="text-sm">Keluar</span>}
            </button>
          </div>
        </aside>

        {/* Page Content */}
        <main className="flex-1 overflow-auto min-w-0 p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
