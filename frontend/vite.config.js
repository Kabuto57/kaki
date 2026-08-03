import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Dev-only proxy so the browser talks to one origin and CORS never comes
    // up locally. In production the frontend is served from a different host,
    // so VITE_API_URL is used instead and CORS_ORIGINS on the API must list it.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
