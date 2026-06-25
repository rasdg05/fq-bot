import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
  server: {
    proxy: {
      // During `npm run dev`, forward API calls to the FastAPI backend.
      '/api': 'http://localhost:8000',
    },
  },
})
