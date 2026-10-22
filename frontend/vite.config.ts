import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Backend: uvicorn app.main:app --port 8000 (run from backend/)
      '/api': {
        target: process.env.MEDIATRACE_API ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
