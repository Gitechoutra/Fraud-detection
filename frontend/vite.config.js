import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In development the app talks to Flask on :5000 (VITE_API_BASE_URL).
// In Docker it is served by Nginx, which proxies /api to the backend.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
  build: { chunkSizeWarningLimit: 1200 },
});
