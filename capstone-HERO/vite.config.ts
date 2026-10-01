import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Disajikan GitHub Pages di https://hero-ojk-its.github.io/hero/
  base: '/hero/',
})
