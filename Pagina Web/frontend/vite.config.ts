import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  css: {
    postcss: {},
  },
  server: {
    proxy: {
      '/api': {
        target: process.env.TICKIA_API_PROXY_TARGET || 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
    port: 5174,
    strictPort: true,
  },
});
