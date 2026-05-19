import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Local FastAPI service (see src/kb_mcp/web/config.py).
// Vite dev server proxies /api/* to it so the frontend speaks to the
// same origin and avoids CORS in development.
const API_PORT = Number(process.env.KB_WEB_PORT ?? 8765);

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${API_PORT}`,
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    target: 'es2022',
    sourcemap: true,
  },
});
