import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// Disajikan GitHub Pages di https://hero-ojk-its.github.io/hero/
// VITE_BASE (opsional) menimpa base, mis. dari workflow GitHub Pages.
export default defineConfig({
  base: process.env.VITE_BASE ?? '/hero/',
  plugins: [react()],
})
