# Referensi `config/sources.yaml`

Seluruh perilaku HERO yang dapat diatur operator berada pada satu berkas ini.
Tidak ada situs yang ditemukan otomatis oleh sistem — daftar situs diinput
manual, sesuai URD 4.2.

## `storage`

| Kunci | Default | Keterangan |
|-------|---------|------------|
| `knowledge_base` | `data/knowledge_base` | Akar folder penyimpanan dokumen |
| `staging_dir` | `data/staging` | Area unduhan sementara sebelum dokumen difiling |
| `catalog_db` | `data/hero_catalog.db` | Katalog SQLite (metadata, teks, struktur, analisa) |

## `scraper`

| Kunci | Default | Keterangan |
|-------|---------|------------|
| `user_agent` | `HERO-RegulationBot/0.1 …` | Identitas klien; cantumkan kontak yang dapat dihubungi |
| `request_timeout` | `45` | Batas waktu per permintaan (detik) |
| `delay_seconds` | `1.0` | Jeda minimum antar permintaan — naikkan bila situs sumber lambat |
| `respect_robots` | `true` | Mematuhi `robots.txt`. Jangan dimatikan tanpa izin pengelola situs |
| `max_file_mb` | `80` | Batas ukuran unduhan; berkas lebih besar ditolak dengan alasan tercatat |
| `verify_tls` | `true` | Verifikasi sertifikat TLS |

## `ocr`

| Kunci | Default | Keterangan |
|-------|---------|------------|
| `enabled` | `true` | Matikan untuk memaksa mode text-layer saja |
| `languages` | `ind+eng` | Kode bahasa Tesseract; yang tidak terpasang diabaikan otomatis |
| `dpi` | `300` | Resolusi render sebelum OCR. 300 memadai untuk teks 10–12 pt |
| `min_chars_per_page` | `120` | Di bawah nilai ini, halaman dianggap citra dan di-OCR |
| `max_pages` | `60` | Anggaran OCR per dokumen; sisanya dilaporkan sebagai terpotong |

## `sites` — Jalur 1 (scraping)

```yaml
- name: "OJK — Regulasi"          # label pada laporan
  url: "https://ojk.go.id/id/regulasi/default.aspx"
  enabled: true
  adapter: auto          # auto | generic | jdih_ojk | ojk_sharepoint
  max_documents: 12      # batas dokumen per `hero scrape` (discover selalu semua)
  status_hint: null      # mis. "rancangan" — status tetap untuk semua dokumen situs ini
  category_hint: null    # bila diisi, mengesampingkan hasil klasifikasi otomatis

- name: "JDIH OJK — Register Peraturan"
  url: "https://jdih.ojk.go.id/Web/ViewPeraturan/Index?sektor=02&jenisPeraturan=01"
  adapter: jdih_ojk
  sektor: ["*"]          # "*" = semua sektor; kosong = pakai nilai di URL
  jenis_peraturan: ["*"] # "*" = semua jenis;  kosong = pakai nilai di URL

- name: "Situs lain"             # adapter generic: telusuri tautan HTML
  url: "https://…/peraturan"
  max_pages: 10          # total halaman yang dikunjungi (entry + hasil follow)
  follow_patterns: ["/peraturan/detail/"]
  include_patterns: []   # bila diisi, hanya PDF yang cocok yang diambil
  exclude_patterns: ["abstrak", "faq"]
```

`adapter: auto` memilih berdasarkan host: `jdih.ojk.go.id` → `jdih_ojk`
(grid JSON), `ojk.go.id/…/regulasi/` → `ojk_sharepoint` (pager *postback*
ASP.NET), selain itu `generic`. Pola pada adapter `generic` bersifat
*substring*, tidak peka huruf besar/kecil, diuji terhadap URL beserta teks
tautannya, terbatas pada host yang sama dan sedalam satu hop.

## `folders` — Jalur 3 (folder lokal / OneDrive tersinkron)

```yaml
- name: "OneDrive — Regulasi DPEA"
  path: "~/OneDrive - Otoritas Jasa Keuangan/Regulasi"
  enabled: true
  recursive: true
  category_hint: null
```

Folder OneDrive yang disinkronkan oleh aplikasi desktop cukup diperlakukan
sebagai path lokal. Berkas berukuran 0 byte dilewati dan dilaporkan — pada
OneDrive itu menandakan berkas *online-only* yang belum diunduh.

## `onedrive_shares` — Jalur 3b (share link publik)

```yaml
- name: "OneDrive publik — Peraturan"
  share_url: "https://1drv.ms/f/s!AbCdEfGh…"
  enabled: true
```

Menggunakan endpoint `/shares` tanpa autentikasi. Bila tautan ternyata
memerlukan login, run melaporkannya sebagai catatan sumber, bukan sebagai
kegagalan.
