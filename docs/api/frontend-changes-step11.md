# Panduan Perubahan Frontend — Langkah 11 (Dukungan Integrasi & Data Uji Nyata)

**Target Pembaca:** Frontend Engineer (Personil_D) & Tim UI  
**Versi Backend:** `0.11.0` (Step 11)  
**Lingkungan Dev Frontend:** Vite + React (Port `5173`, Base Path `/hero/`)  
**Terkait Issue:** Integrasi UI Knowledge Base, Detail Dokumen, dan Dashboard (#88, #92, #95)

---

## 1. Ringkasan Perubahan Penting

Langkah 11 berfokus pada penyelesaian kendala integrasi frontend lintas origin (CORS), penanganan unduhan PDF dengan penamaan berkas standar yang aman terhadap karakter spasi/non-ASCII, pengisian metadata `status_keberlakuan` yang sebelumnya selalu bernilai `tidak_diketahui`, serta penyediaan data uji nyata yang kaya dan bervariasi langsung dari sumber resmi.

---

## 2. Pembaruan CORS & Header yang Di-expose

Frontend yang berjalan pada origin dev (seperti `http://localhost:5173` atau `http://127.0.0.1:5173`) kini diizinkan secara default dalam konfigurasi `.env.example`.

Selain itu, middleware CORS kini mengekspos header penting agar JavaScript / browser fetch API dapat membaca metadata berkas:

```http
Access-Control-Expose-Headers: Content-Disposition, Content-Length
```

### Cara Membaca Nama Berkas Asli di Frontend:
Saat frontend melakukan request unduhan atau fetch blob:
```typescript
const response = await fetch(`${API_BASE_URL}/documents/${id}/pdf?download=true`, {
  headers: {
    // Authorization jika diperlukan
  }
});

// Membaca header Content-Disposition yang kini sudah diekspos oleh CORS
const contentDisposition = response.headers.get('Content-Disposition');
let filename = 'dokumen.pdf';

if (contentDisposition) {
  // 1. Prioritaskan format RFC 5987 (filename*=UTF-8''...)
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match && utf8Match[1]) {
    filename = decodeURIComponent(utf8Match[1]);
  } else {
    // 2. Fallback ke format standar filename="..."
    const asciiMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
    if (asciiMatch && asciiMatch[1]) {
      filename = asciiMatch[1];
    }
  }
}
```

---

## 3. Endpoint Unduhan PDF (`GET /documents/{id}/pdf`)

Endpoint unduhan PDF telah diperbarui agar selalu mengirimkan header `Content-Disposition` dengan standar ganda:
1. `filename*=UTF-8''<percent-encoded>` sesuai RFC 5987 (aman untuk spasi, aksen, dan karakter khusus).
2. `filename="<ascii-safe>"` sebagai fallback untuk peramban web lawas.

### Parameter Query:
- `download=false` (default): Mengembalikan `Content-Disposition: inline; ...` untuk pratinjau di dalam browser/iframe.
- `download=true`: Mengembalikan `Content-Disposition: attachment; ...` untuk memicu unduhan berkas langsung ke komputer pengguna.

---

## 4. Metadata `status_keberlakuan` Kini Terisi dari Sumber Resmi

Sebelumnya, dokumen yang ditarik dari hasil pindai memiliki status keberlakuan `tidak_diketahui`, sehingga widget grafik dashboard ("Berlaku vs Dicabut") dan filter Status di halaman Knowledge Base tidak bermakna.

Backend kini otomatis mengekstrak status regulasi dari sumber:
- **JDIH OJK**: Dipetakan dari teks status halaman detail ("Berlaku Sejak Tanggal...", "Dicabut...", "Diubah...") dan kolom status DataTables API menjadi salah satu nilai enum:
  - `"berlaku"`
  - `"dicabut"`
  - `"diubah"`
  - `"tidak_diketahui"`
- **Regulasi OJK**: Jika situs tidak mencantumkan status keberlakuan eksplisit, bernilai `"tidak_diketahui"`.
- **OneDrive**: Bernilai `"tidak_diketahui"` (dokumen repositori berkas internal).

### Status Keberlakuan Diteruskan Saat Pull:
Saat kandidat ditarik (`POST /api/v1/scans/{scan_id}/pull`), nilai `status_keberlakuan` otomatis disalin ke entitas `Document` di Knowledge Base, dengan tetap menghormati aturan koreksi manual bila pengguna telah memperbarui metadata secara manual sebelumnya.

---

## 5. Menggunakan Data Uji Nyata untuk Integrasi Frontend

Backend menyediakan utilitas seeding otomatis dari 3 sumber resmi:
```bash
python scripts/seed_from_sources.py --per-source 15 --sources ojk,jdih,onedrive --naming-format nama,jenis,tahun --reset
```

### Hasil yang Tersedia di Database Lokal:
- **Total Dokumen:** ± 45 dokumen asli yang ter-ingest lengkap dengan file PDF di storage.
- **Variasi Sektor/Bidang:** Perbankan, Pasar Modal, PVML (Fintech/Leasing), EPK (Edukasi & Perlindungan Konsumen), ITSK (Inovasi Teknologi Sektor Keuangan), dll.
- **Variasi Jenis Regulasi:** POJK, SEOJK, PADK.
- **Variasi Status Keberlakuan:** Terdapat dokumen berstatus `berlaku`, `dicabut`, `diubah`, dan `tidak_diketahui` sehingga visualisasi grafik status di Dashboard langsung terisi data nyata.

### Endpoint untuk Menguji Tampilan Frontend:
1. `GET /api/v1/dashboard/summary`: Memuat metrik total dokumen, distribusi status keberlakuan, distribusi bidang, dan dokumen terbaru.
2. `GET /api/v1/documents?bidang=Perbankan`: Menguji filter sektor.
3. `GET /api/v1/documents?status_keberlakuan=berlaku`: Menguji filter status keberlakuan.
4. `GET /api/v1/documents/{id}/pdf`: Menguji pratinjau dan unduhan PDF dengan nama terstandarisasi.
