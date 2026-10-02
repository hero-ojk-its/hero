# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.

## Menjalankan Frontend dan Backend

Untuk menghubungkan Frontend dengan Backend FastAPI:

1. **Konfigurasi Environment Variable**
   Salin berkas .env.example menjadi .env.local:
   `ash
   cp .env.example .env.local
   `
   Pastikan variabel VITE_API_BASE_URL mengarah ke alamat backend (default: http://localhost:8000):
   `env
   VITE_API_BASE_URL=http://localhost:8000
   `
   *Catatan: Bila VITE_API_BASE_URL kosong atau tidak ada, Frontend otomatis berjalan dalam mode contoh (data statis).*

2. **Menjalankan Backend**
   Jalankan server FastAPI (dari direktori backend):
   `ash
   uvicorn app.main:app --reload --port 8000
   `

3. **Menjalankan Frontend**
   Dari direktori rontend/:
   `ash
   npm install
   npm run dev
   `
   Buka peramban di http://localhost:5173.
