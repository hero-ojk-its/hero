import { BrowserRouter, Routes, Route } from 'react-router-dom';
import DashboardLayout from './layouts/DashboardLayout';
import Dashboard from './pages/Dashboard';
import IngestDokumen from './pages/IngestDokumen';
import KnowledgeBase from './pages/KnowledgeBase';
import DetailDokumen from './pages/DetailDokumen';
import Harmonisasi from './pages/Harmonisasi';
import Settings from './pages/Settings';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DashboardLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="ingest" element={<IngestDokumen />} />
          <Route path="knowledge" element={<KnowledgeBase />} />
          <Route path="knowledge/detail/:id" element={<DetailDokumen />} />
          <Route path="harmonisasi" element={<Harmonisasi />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
