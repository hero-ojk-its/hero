# Kontrak Adapter Crawler & Web Scanning — HERO Backend (Langkah 10)

Dokumen ini mendefinisikan arsitektur, antarmuka standar (contract), mekanisme registrasi, dan panduan penambahan adapter crawler untuk pemindaian situs web regulasi dan penyimpanan cloud di HERO Backend.

---

## 1. Prinsip Desain Crawler

1. **Ringan & Cepat (Zero Headless Browser)**: Seluruh pemindaian berjalan melalui protokol HTTP murni (`httpx`) tanpa dependensi Playwright/Selenium, sehingga ramah sumber daya (RAM < 50MB, eksekusi dalam hitungan detik).
2. **Tanpa Unduh Penuh untuk Deteksi Ukuran**: Ukuran berkas dideteksi secara presisi melalui probe `HEAD` (Content-Length), fallback `GET Range: bytes=0-0` (Content-Range), atau metadata listing folder cloud (`size_source="listing"`).
3. **Deteksi Proteksi & Keamanan (WAF / Captcha / SSRF)**:
   - **SSRF Guard**: Memblokir IP privat/loopback/cloud metadata (`127.0.0.1`, `10.0.0.0/8`, `169.254.169.254`, `::1`) saat pemindaian publik.
   - **Captcha / WAF Marker**: Mendeteksi halaman tantangan Cloudflare (`cf-chl`, `cf-ray`, `503 Service Unavailable`), reCAPTCHA (`g-recaptcha`, `recaptcha/api.js`), hCaptcha, dan WAF blokir. Mengembalikan flag `blocked=True` dan kode error `terblokir_captcha` tanpa membuat server crash.
4. **Tahan Paging & Loop Detection**:
   - Mendeteksi pagination standar HTML (nomor urut, `Berikutnya` / `Next`, `Terakhir`).
   - Mendeteksi ASP.NET WebForms form postback (`__EVENTTARGET`, `__VIEWSTATE`, `__EVENTVALIDATION`).
   - Mencegah loop siklik tak hingga dengan pelacakan URL yang telah dikunjungi dan signature isi halaman (content hash).

---

## 2. Struktur Data Standar (Model Kontrak)

### 2.1 `PdfCandidate` (Kandidat Dokumen)

Setiap adapter **wajib** menghasilkan daftar `PdfCandidate` dengan skema terpadu berikut:

| Field | Tipe | Deskripsi | Contoh |
|---|---|---|---|
| `url` | `str` | URL absolut unduhan berkas PDF (ternormalisasi) | `https://ojk.go.id/.../POJK%2017.pdf` |
| `filename` | `str` | Nama berkas PDF | `POJK 17 Tahun 2023.pdf` |
| `size_bytes` | `Optional[int]` | Ukuran berkas dalam bytes (bila berhasil dideteksi) | `1048576` |
| `size_source` | `str` | Sumber perolehan ukuran: `head`, `range`, `listing`, `unknown` | `head` |
| `found_on_page` | `str` | Halaman di mana tautan ditemukan | `https://ojk.go.id/id/regulasi/Pages/...` |
| `depth` | `int` | Kedalaman penelusuran (1-indexed) | `1` |
| `document_title` | `Optional[str]` | Judul resmi dokumen/regulasi | `Penerapan Tata Kelola Bagi Bank Umum` |
| `detail_url` | `Optional[str]` | URL halaman detail regulasi | `https://ojk.go.id/id/regulasi/Pages/...` |
| `final_url` | `Optional[str]` | URL akhir setelah redirect | `https://ojk.go.id/.../POJK%2017.pdf` |
| `doc_kind` | `str` | Peran berkas: `utama`, `abstrak`, `faq`, `lampiran`, `lainnya` | `utama` |
| `regulation_number` | `Optional[str]` | Nomor regulasi resmi | `POJK 17/POJK.03/2023` |
| `regulation_type` | `Optional[str]` | Jenis regulasi ternormalisasi: `POJK`, `SEOJK`, `PADK`, dll. | `POJK` |
| `bidang` | `Optional[str]` | Bidang / Sektor regulasi | `Perbankan` |
| `sub_bidang` | `Optional[str]` | Sub bidang regulasi | `Bank Umum` |
| `release_date` | `Optional[date]` | Tanggal penetapan / berlakunya regulasi | `2023-09-14` |
| `source_path` | `Optional[str]` | Jalur folder relatif sumber (khusus OneDrive / struktur folder) | `perbankan/2023/POJK 17.pdf` |

### 2.2 `ScanResult` (Hasil Pemindaian)

| Field | Tipe | Deskripsi |
|---|---|---|
| `candidates` | `List[PdfCandidate]` | Daftar seluruh kandidat dokumen PDF yang ditemukan |
| `pages_visited` | `int` | Jumlah halaman HTML / endpoint API / folder yang dikunjungi |
| `errors` | `List[str]` | Daftar pesan error non-fatal atau peringatan saat pemindaian |
| `truncated` | `bool` | `true` jika pemindaian berhenti karena batas `max_pages` / `max_candidates` |
| `blocked` | `bool` | `true` jika pemindaian terdeteksi terblokir Captcha / WAF / Cloudflare |
| `stats` | `Dict[str, Any]` | Metrik: `regulations_found`, `pdfs_found`, `by_doc_kind`, `duration_seconds`, dll. |

---

## 3. Daftar Adapter Tersedia

### 3.1 `GenericHtmlCrawler` (`generic_html`)
- **Cocok untuk**: Situs web umum HTML statis / dinamis standar.
- **Fitur**: Paging link (`<a>`), recursive link follower dengan pembatas domain, redirect resolver hingga 10 hop, meta refresh handling, SSRF guard, dan deteksi proteksi Cloudflare/reCAPTCHA.

### 3.2 `SharepointPostbackCrawler` (`sharepoint_postback`)
- **Cocok untuk**: Portal Regulasi OJK (`https://ojk.go.id/id/regulasi/default.aspx`) dan situs ASP.NET WebForms SharePoint.
- **Fitur**:
  - Penanganan postback ASP.NET (`__doPostBack`) dengan ekstraksi token `__VIEWSTATE`, `__EVENTVALIDATION`, `__EVENTTARGET`.
  - Pengecualian otomatis tombol submit pencarian agar tidak memicu reset filter.
  - Parser halaman detail regulasi dengan penarikan multi-lampiran (dokumen regulasi utama, lembar abstrak, dan tanya jawab / FAQ) serta ekstraksi metadata tabel (Nomor, Jenis, Sektor, Sub-Sektor, Tanggal).

### 3.3 `JdihApiCrawler` (`jdih_api`)
- **Cocok untuk**: JDIH OJK (`https://jdih.ojk.go.id/`).
- **Fitur**:
  - Konsumsi langsung DataTables JSON API (`/Web/ViewPeraturanHome/ListDataPeraturan`).
  - Paging efisien berbasis parameter `iDisplayStart` dan `iDisplayLength`.
  - Ekstraksi metadata langsung dari kolom JSON (`Nomor`, `Bentuk/Jenis`, `Sektor`, `Tanggal Pengundangan`).
  - URL unduh langsung via `/Download/{guid}/{filename}` dengan probing HEAD.

### 3.4 `OneDriveShareCrawler` (`onedrive_share`)
- **Cocok untuk**: Tautan berbagi folder publik OneDrive / SharePoint (`https://oneojk-my.sharepoint.com/:f:/g/personal/...`).
- **Fitur**:
  - Inisialisasi guest auth session otomatis melalui tautan berbagi publik.
  - Penelusuran pohon folder secara rekursif via SharePoint REST API (`/_api/web/GetFolderByServerRelativeUrl(...)`).
  - Ekstraksi ukuran eksak langsung dari atribut listing (`Length`), jalur hierarki folder (`source_path`), dan pembuatan tautan unduhan langsung `/_layouts/15/download.aspx?SourceUrl=...`.

---

## 4. Mekanisme Registrasi dan Pemilihan Adapter

Adapter dipilih secara otomatis berdasarkan URL target (auto-detect) atau dapat ditentukan secara eksplisit melalui parameter `crawler_adapter`:

```python
from app.crawlers.registry import get_crawler, detect_crawler_adapter

# Auto-detect berdasarkan URL:
adapter_name = detect_crawler_adapter("https://ojk.go.id/id/regulasi/default.aspx")
# -> "sharepoint_postback"

# Inisialisasi instance crawler:
crawler = get_crawler(url="https://jdih.ojk.go.id/", adapter="jdih_api")
scan_result = crawler.scan("https://jdih.ojk.go.id/", depth=5, max_pages=10)
```

---

## 5. Panduan Menambahkan Adapter Baru

Untuk menambahkan adapter sumber regulasi baru (misal: Kementerian Keuangan, BI, Mahkamah Agung):

1. **Buat Berkas Adapter**: Buat modul di `app/crawlers/<nama_adapter>.py`.
2. **Implementasikan Antarmuka**:
   ```python
   class CustomPortalCrawler:
       name: str = "custom_portal"

       def __init__(self, user_agent: str = ..., delay_seconds: float = 0.5, allow_private: bool = False, head_for_size: bool = True):
           ...

       def scan(self, url: str, depth: int = 1, *, max_pages: int = 200, max_candidates: int = 5000, progress=None, should_cancel=None) -> ScanResult:
           ...
   ```
3. **Daftarkan di `app/crawlers/registry.py`**:
   Tambahkan kelas ke `CRAWLER_REGISTRY` dan tambahkan aturan pengenalan domain pada `detect_crawler_adapter`.
4. **Tulis Unit Test**: Tambahkan pengujian skenario berbasis fixture di `tests/test_crawler_robust.py`.
