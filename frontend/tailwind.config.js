/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif'],
      },
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

