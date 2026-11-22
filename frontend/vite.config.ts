import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The browser calls /api/... on the same origin. In development Vite forwards it to
// the FastAPI process; in docker compose nginx does the same (frontend/nginx.conf).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        // Worker pdfjs to plik .mjs. nginx 1.27 nie zna tego rozszerzenia i podałby go jako
        // application/octet-stream, a przeglądarka nie uruchomi takiego modułu. Stąd nazwa .js.
        assetFileNames: (asset) =>
          asset.names.some((name) => name.endsWith('.mjs')) ? 'assets/[name]-[hash].js' : 'assets/[name]-[hash][extname]',
      },
    },
  },
  server: {
    proxy: {
      '/api': process.env.API_URL ?? 'http://localhost:8000',
    },
  },
})
