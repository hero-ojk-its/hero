# Kontrak Adapter Crawler HERO (Tim Data/ML)

Dokumen ini ditujukan untuk tim Data/ML (Fathir) yang akan mengembangkan crawler tingkat lanjut (penanganan JavaScript dinamis, SPA, anti-bot Cloudflare, autentikasi SharePoint DPEA, dll.).

HERO Backend menyediakan 2 opsi integrasi yang saling kompatibel:
- **Opsi A (Modul Python Terpasang):** Berjalan dalam runtime backend yang sama via plugin/adapter.
- **Opsi B (Layanan Mikro / Push Mode):** Crawler berjalan sebagai microservice independen dan berkomunikasi via API internal.

---

## 1. Batasan & Aturan Utama (Arsitektur §4.3, RA-06)

1. **Crawler Tidak Menyentuh Database:** Crawler dilarang mengimpor atau mengakses database backend (`app.database`, `app.models`, `app.services`, `app.routers`). Seluruh perbandingan duplikasi, status, dan penyimpanan dikelola oleh Backend.
2. **Perlindungan SSRF:** Semua URL yang dijelajahi dan ditarik wajib melalui validasi keamanan. Backend menolak alamat privat/loopback/link-local (seperti `127.0.0.1`, `10.0.0.0/8`, `169.254.169.254`, `::1`).
3. **Aturan Kedalaman & Paging:**
   - Kedalaman (*depth*) dihitung berdasarkan tingkat path/slash URL awal.
   - Halaman navigasi/paging (misal `?page=2`, `rel="next"`, angka pagination) **tidak menambah kedalaman**, namun tetap dihitung ke batas `max_pages`.

---

## 2. Opsi A: Adapter Modul Python (`external_module`)

### 2.1 Interface Protocol & Dataclass

Modul kustom wajib mengimplementasikan protokol `Crawler` dan memanfaatkan dataclass berikut dari `app.crawlers.base`:

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class PdfCandidate:
    url: str                 # URL kandidat (akan dinormalisasi)
    filename: str            # Nama berkas dari URL path / Content-Disposition
    size_bytes: int | None   # Ukuran berkas dalam bytes (bisa None bila tidak diketahui)
    found_on_page: str       # URL halaman tempat tautan ditemukan
    depth: int               # Kedalaman penemuan (1 = halaman awal/paging-nya)

@dataclass
class ScanResult:
    candidates: list[PdfCandidate]
    pages_visited: int
    errors: list[str]        # Pesan kesalahan/peringatan dalam Bahasa Indonesia
    truncated: bool          # True jika mencapai limit max_pages atau max_candidates

@dataclass
class FetchedFile:
    content: bytes
    filename: str
    final_url: str
    content_type: str | None

class CrawlerError(Exception): ...
class BlockedUrlError(CrawlerError): ...
class FetchTooLargeError(CrawlerError): ...

class Crawler(Protocol):
    name: str

    def scan(
        self,
        url: str,
        depth: int,
        *,
        max_pages: int,
        max_candidates: int,
        progress: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> ScanResult:
        """
        Menjelajahi halaman web dan mengumpulkan kandidat PDF.
        - progress(pages_visited, candidates_count) dipanggil secara berkala.
        - should_cancel() diperiksa tiap halaman untuk mendeteksi pembatalan.
        """
        ...

    def fetch(
        self,
        url: str,
        *,
        max_bytes: int,
    ) -> FetchedFile:
        """
        Mengunduh berkas PDF target.
        - Wajib melempar FetchTooLargeError bila ukuran melebihi max_bytes.
        """
        ...
```

### 2.2 Cara Mengaktifkan Modul

1. Pasang paket/modul Python Anda di environment backend.
2. Konfigurasikan file `.env`:
   ```env
   CRAWLER_BACKEND=external_module
   CRAWLER_MODULE=my_crawler_pkg.advanced_crawler:AdvancedSeleniumCrawler
   ```

---

## 3. Opsi B: Push Mode (Layanan Mikro Eksternal)

Dalam mode ini, backend HERO bertindak sebagai server antrean job, sedangkan worker crawler Data/ML melakukan polling/claiming job dan mengirimkan kandidat PDF secara bertahap.

Konfigurasi `.env`:
```env
CRAWLER_BACKEND=push
INTERNAL_API_KEY=hero-internal-secret-key-change-in-production
```

### 3.1 Mengambil Antrean Sesi (`claim`)

Worker crawler mengambil sesi pemindaian yang berstatus `antrian`.

**Request:**
`POST /api/v1/internal/scans/claim?limit=1`
**Header:** `X-Internal-API-Key: <INTERNAL_API_KEY>`

**Response (200 OK):**
```json
[
  {
    "scan_id": 1,
    "start_url": "https://jdih.esdm.go.id",
    "crawl_depth": 2,
    "max_pages": 100,
    "max_candidates": 2000
  }
]
```

### 3.2 Mengirimkan Kandidat Hasil Pindai (`candidates`)

Worker crawler dapat mengirimkan hasil secara bertahap (batch streaming) atau sekaligus saat selesai.

**Request:**
`POST /api/v1/internal/scans/{scan_id}/candidates`
**Header:** `X-Internal-API-Key: <INTERNAL_API_KEY>`

**Body (Batch Parsial, `done: false`):**
```json
{
  "candidates": [
    {
      "url": "https://jdih.esdm.go.id/storage/document/2026kmesdm365k.pdf",
      "filename": "2026kmesdm365k.pdf",
      "size_bytes": 879298,
      "found_on_page": "https://jdih.esdm.go.id",
      "depth": 1
    }
  ],
  "pages_visited": 10,
  "done": false,
  "truncated": false,
  "errors": []
}
```

**Body (Selesai, `done: true`):**
```json
{
  "candidates": [
    {
      "url": "https://jdih.esdm.go.id/storage/document/2026kmesdm369k.pdf",
      "filename": "2026kmesdm369k.pdf",
      "size_bytes": 7007305,
      "found_on_page": "https://jdih.esdm.go.id/page/2",
      "depth": 1
    }
  ],
  "pages_visited": 25,
  "done": true,
  "truncated": false,
  "errors": ["Halaman /private/ ditolak robots.txt"]
}
```

**Perilaku Backend:**
1. Backend melakukan normalisasi URL dan pemeriksaan SSRF untuk setiap kandidat yang masuk.
2. Kandidat disimpan dengan idempotensi berbasis `url_hash`.
3. Saat `done=true` diterima, backend secara otomatis menjalankan perbandingan duplikasi dengan Knowledge Base dan mengubah status sesi menjadi `siap_dipilih`.
4. Jika terjadi kegagalan fatal pada worker crawler, kirim `"error": "Pesan error kegagalan"` agar status sesi berubah menjadi `gagal`.
