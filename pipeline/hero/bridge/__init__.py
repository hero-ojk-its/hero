"""Jembatan lapisan data HERO ↔ backend tim (FastAPI + Postgres/pgvector).

Pembagian tanggung jawab yang dijaga modul ini:

* **Backend** memegang kebenaran operasional: dokumen, kategori, sesi pindai,
  job ingest, pengguna, jejak audit. Frontend hanya bicara ke backend.
* **Lapisan data (paket ``hero``)** memegang algoritmanya: adapter scraping
  per sumber, OCR, parser identitas & struktur pasal, analisa, harmonisasi,
  vektor, graf.
* **Jembatan** menyambungkan keduanya lewat kontrak internal yang sudah
  ditulis backend — bukan dengan menulis ke basis datanya langsung. Tidak ada
  modul di sini yang mengimpor kode backend atau menyentuh tabelnya selain
  melalui HTTP (kecuali ``pg.py``, yang hanya *membaca* vektor dan dipakai
  benchmark).

Isi:

| Modul | Peran |
|---|---|
| ``config`` | blok ``bridge:`` di sources.yaml + rahasia dari ``.env`` |
| ``client`` | klien ``/api/v1/internal/*`` dengan retry yang benar |
| ``mapping`` | satu-satunya tempat yang tahu nama field backend |
| ``embed`` | vektor per pasal, termasuk penyesuaian dimensi ke kolom pgvector |
| ``state`` | buku besar lokal agar pengiriman ulang tidak menggandakan data |
| ``scan_worker`` | sesi pindai backend dilayani adapter HERO (mode push) |
| ``extract_worker`` | antrian ekstraksi: OCR → metadata → pasal → vektor |
| ``pg`` | pgvector: pencarian pasal di korpus backend & benchmark |
| ``ml_api`` | layanan analisa/harmonisasi/pencarian untuk layar Fase 2–3 |

Semua jalur di sini berjalan dalam Mode Deterministik: tanpa jaringan keluar
dan tanpa AI, kecuali embedding semantik yang memakai model lokal ONNX.
"""
from hero.bridge.client import BackendClient, BackendError
from hero.bridge.config import BridgeSettings, load_bridge_settings
from hero.bridge.embed import ArticleEmbedder, EmbedderUnavailable
from hero.bridge.extract_worker import ExtractionWorker
from hero.bridge.scan_worker import ScanWorker
from hero.bridge.state import BridgeState

__all__ = ["ArticleEmbedder", "BackendClient", "BackendError", "BridgeSettings", "BridgeState",
           "EmbedderUnavailable", "ExtractionWorker", "ScanWorker", "load_bridge_settings"]
