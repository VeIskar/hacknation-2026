import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The browser calls /api/... on the same origin. In development Vite forwards it to
// the FastAPI process; in docker compose nginx does the same (frontend/nginx.conf).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': process.env.API_URL ?? 'http://localhost:8000',
    },
  },
})
