# CHECKLIST PERSIAPAN DEMO 8 OKTOBER 2026
> **HERO Backend — Kesiapan Demo Stakeholder & Mitra**  
> Target: Presentasi Demo Fase 1 (Ingest, Scanning, Ekstraksi, Koreksi, Search, & Dashboard)

---

## 📅 H-3 (Minggu, 5 Oktober 2026) — Kesiapan Infrastruktur & Lingkungan

- [ ] **1. Verifikasi VPS & Domain**
  - [ ] Domain `API_DOMAIN` terhubung dengan HTTPS Let's Encrypt aktif dan sertifikat valid.
  - [ ] Firewall VPS hanya membuka port 22, 80, 443 (port DB 5432 & backend 8000 tidak terbuka publik).
  - [ ] `curl -i https://<API_DOMAIN>/health` mengembalikan HTTP 200, `status="ok"`, `migrations_up_to_date=true`, `storage_writable=true`.
- [ ] **2. Kesiapan Swagger & Keamanan Dasar**
  - [ ] Basic Auth aktif pada `/docs`, `/redoc`, dan `/openapi.json`. Kredensial demo telah dicatat.
  - [ ] `CORS_ORIGINS` telah disesuaikan dengan domain Frontend Vercel.
- [ ] **3. Uji Coba Backup & Restore**
  - [ ] Eksekusi `./deploy/backup.sh` berhasil menghasilkan arsip DB dan storage.
  - [ ] Jadwal backup harian (`hero-backup-db.timer`, jam 03:00) aktif: `systemctl list-timers hero-backup-db.timer`.
  - [ ] Uji pemulihan lulus: `sudo ./deploy/restore-test.sh` menampilkan `HASIL: LULUS`.
- [ ] **4. Uji Integrasi Worker ML & API Internal**
  - [ ] Header `X-Internal-API-Key` terverifikasi dapat mengakses `/api/v1/internal/*`.

---

## 📅 H-1 (Selasa, 7 Oktober 2026) — Seeding & Validasi Data Nyata

- [ ] **1. Bersihkan Data Sisa Uji Coba (Demo Reset)**
  - [ ] Jalankan reset data bersih:
    ```bash
    python scripts/demo_reset.py --yes --i-understand-production
    ```
  - [ ] Verifikasi kategori hierarkis OJK (Perbankan, Pasar Modal, IKNB, Tata Kelola) dan user admin tetap ada.
- [ ] **2. Pengisian Data Sumber Nyata (Demo Seed)**
  - [ ] Siapkan konfigurasi `deploy/demo_sources.json` dengan:
    - 3 situs web resmi/statis (mis. JDIH ESDM, BPK, OJK publik).
    - 1 folder arsip regulasi lokal (`sources/internal_regulasi`).
    - 1 folder OneDrive regulasi internal (`sources/onedrive`).
  - [ ] Jalankan pengisian otomatis:
    ```bash
    python scripts/demo_seed.py --config deploy/demo_sources.json --base-url https://<API_DOMAIN>
    ```
- [ ] **3. Verifikasi Jumlah & Kualitas Dokumen Corpus**
  - [ ] `GET /dashboard/summary` menunjukkan total `corpus_documents >= 20` dari dokumen nyata.
  - [ ] Distribusi `by_regulation_type` dan `by_year` konsisten menjumlah ke total dokumen.
  - [ ] Dokumen PDF dapat dibuka dari browser via `/documents/{id}/pdf`.
- [ ] **4. Jalankan Smoke Test Validasi**
  - [ ] `python scripts/smoke_test.py https://<API_DOMAIN>` selesai dengan status `100% SUKSES`.
- [ ] **5. Buat Snapshot Backup Pra-Demo**
  - [ ] Jalankan `./deploy/backup.sh` dan simpan salinan berkas backup di laptop presenter sebagai arsip cadangan darurat.

---

## 🚀 HARI-H (Rabu, 8 Oktober 2026) — Alur Presentasi Demo

### 1. Pre-Flight Check (15 Menit Sebelum Presentasi)
- [ ] Akses `https://<API_DOMAIN>/health` -> status `ok`.
- [ ] Buka Frontend di Vercel, pastikan dashboard termuat cepat dan ringkasan metrik tampil benar.
- [ ] Pastikan koneksi internet presenter stabil.

### 2. Skenario Demo Utama (Live Showcase)
- [ ] **Skenario 1: Dashboard & Ringkasan Korpus**
  - [ ] Tampilkan total dokumen, grafik jenis regulasi, dan riwayat job ingest (`recent_jobs` dengan `processed_count` dan `skipped_count`).
- [ ] **Skenario 2: Pencarian Cepat Regulasi (Full-Text Search)**
  - [ ] Cari frasa hukum spesifik (mis. *"usaha perasuransian"*, *"tata kelola perbankan"*, *"larangan praktek monopoli"*).
  - [ ] Tunjukkan kecocokan highlight frasa, filter tahun, dan filter jenis regulasi.
- [ ] **Skenario 3: Detail Dokumen & Buka PDF Asli**
  - [ ] Klik salah satu dokumen hasil pencarian, buka tab PDF asli dan buktikan visual viewer berjalan mulus.
  - [ ] Tunjukkan ekstraksi pasal-pasal dan referensi peraturan terkait.
- [ ] **Skenario 4: Koreksi Metadata & Jejak Audit**
  - [ ] Lakukan pembaruan nomor / tanggal penetapan / status keberlakuan dokumen.
  - [ ] Tunjukkan entri riwayat koreksi tercatat di audit log.
- [ ] **Skenario 5: Pemindaian Situs Web & Seleksi Penarikan (Site Scan & Pull)**
  - [ ] Masuk ke menu Sumber / Scan, pilih salah satu situs sumber web.
  - [ ] Jalankan *Scan*, perlihatkan kandidat dokumen baru yang terdeteksi dengan status deduplikasi (*baru* vs *sudah_ada*).
  - [ ] Pilih (centang) 2 dokumen, klik *Tarik ke Knowledge Base*, perlihatkan progres penarikan selesai (100%) dan dokumen baru langsung masuk korpus.
- [ ] **Skenario 6: Antrian Kegagalan & Retry**
  - [ ] Perlihatkan log kegagalan parsing / URL tidak valid di menu antrian kegagalan.
  - [ ] Peragakan tombol *Retry* dengan override parameter.
- [ ] **Skenario 7: Proteksi Dokumen Non-Publik (NDA)**
  - [ ] Cari dokumen yang diklasifikasikan sebagai `non_publik`.
  - [ ] Tunjukkan metadata tetap dapat diidentifikasi, namun dokumen ditandai `restricted: true`, tautan PDF dinonaktifkan (`null`), dan akses unduh diblokir (403 Forbidden) demi kepatuhan NDA mitra.

### 3. Rencana Kontingensi (Plan B - Fallback Scenario)
- [ ] **Bila Situs Web Sumber Sedang Down / Timeout:**
  - [ ] Jelaskan bahwa HERO memiliki toleransi kegagalan dan antrean retry.
  - [ ] Gunakan data hasil scan sebelumnya yang sudah tersimpan di database dan riwayat job tarik yang sukses.
- [ ] **Bila Terjadi Masalah Jaringan di Lokasi Demo:**
  - [ ] Presenter dapat beralih ke rekaman/environment lokal Docker di laptop (`http://localhost:8000`).
