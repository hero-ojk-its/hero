/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ojk: {
          red: '#C2185B', // Sesuaikan warna merah marun referensi OJK
          gray: '#F3F4F6',
          darkGray: '#374151',
          white: '#FFFFFF',
        }
      }
    },
  },
  plugins: [],
}

