import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API runs on 127.0.0.1:8000 (docker compose or python -m aml_agent.api).
// The dev server proxies /api to it, so the browser never needs CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.API_URL ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
