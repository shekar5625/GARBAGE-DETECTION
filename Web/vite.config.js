import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The Flask API runs on :5000. Everything the app fetches goes through /api,
// which is proxied here in dev and rewritten to the bare Flask route. This is
// why no component ever contains a host or port — change FLASK below (or set
// VITE_API_TARGET) and the whole app follows.
const FLASK = process.env.VITE_API_TARGET || 'http://127.0.0.1:5000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: FLASK,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
