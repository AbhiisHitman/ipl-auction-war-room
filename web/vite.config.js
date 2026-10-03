import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// /api is proxied to the FastAPI service (uvicorn api.main:app --port 8000)
export default defineConfig({
  plugins: [react()],
  server: { port: 5180, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8000' } },
});
