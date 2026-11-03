import { HashRouter, Routes, Route } from 'react-router-dom';
import DashboardLayout from './layouts/DashboardLayout';
import Dashboard from './pages/Dashboard';
import IngestDokumen from './pages/IngestDokumen';
import KnowledgeBase from './pages/KnowledgeBase';
import DetailDokumen from './pages/DetailDokumen';
import KelolaKategori from './pages/KelolaKategori';
import Harmonisasi from './pages/Harmonisasi';
import AnalisaRegulasi from './pages/AnalisaRegulasi';
import Settings from './pages/Settings';
import AuditLog from './pages/AuditLog';
import KelolaPengguna from './pages/KelolaPengguna';
import Login from './pages/Login';

function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/masuk" element={<Login />} />
        <Route path="/" element={<DashboardLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="ingest" element={<IngestDokumen />} />
          <Route path="knowledge" element={<KnowledgeBase />} />
          <Route path="knowledge/detail/:id" element={<DetailDokumen />} />
          <Route path="knowledge/kategori" element={<KelolaKategori />} />
          <Route path="analisa" element={<AnalisaRegulasi />} />
          <Route path="harmonisasi" element={<Harmonisasi />} />
          <Route path="settings" element={<Settings />} />
          <Route path="audit-log" element={<AuditLog />} />
          <Route path="audit-logs" element={<AuditLog />} />
          <Route path="users" element={<KelolaPengguna />} />
          <Route path="pengguna" element={<KelolaPengguna />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}

export default App;
