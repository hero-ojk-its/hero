# Direktori Sumber Folder Lokal (`sources/`)

Direktori ini digunakan sebagai akar folder lokal yang diizinkan (`LOCAL_SOURCE_ROOTS`) untuk pendaftaran sumber dokumen (`source_type = 'folder_lokal'`).

## Panduan Penggunaan:
1. **Lokal:** Buat subfolder di bawah `sources/` (misal `sources/regulasi_internal/` atau `sources/onedrive/`) dan letakkan berkas-berkas PDF di dalamnya. Daftarkan jalur relatif `./sources/...` atau jalur absolutnya.
2. **Docker:** Folder `./sources` di-mount ke `/app/sources:ro` di dalam container. Daftarkan jalur `/app/sources/...` saat mendaftarkan sumber melalui API pada container.
3. **OneDrive (Fase 1):** Sinkronkan folder OneDrive ke subfolder `sources/onedrive/`, lalu daftarkan folder tersebut sebagai Sumber Folder Lokal.
