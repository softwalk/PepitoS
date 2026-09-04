/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiUrl = env.VITE_API_URL || 'http://localhost:8000';
  const proxy = { '/v1': { target: apiUrl, changeOrigin: true } };
  return {
    plugins: [react()],
    build: {
      rollupOptions: {
        output: {
          manualChunks: { vendor: ['react', 'react-dom', 'react-router-dom'], map: ['leaflet', 'react-leaflet'], charts: ['recharts'] },
        },
      },
    },
    server: { port: 5174, proxy },
    preview: { port: 4174, proxy },
    test: {
      environment: 'jsdom',
      setupFiles: ['./test/setup.ts'],
      include: ['test/**/*.test.{ts,tsx}'],
      css: false,
    },
  };
});
