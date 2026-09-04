/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiUrl = env.VITE_API_URL || 'http://localhost:8000';
  return {
    define: { __APP_VERSION__: JSON.stringify(process.env.npm_package_version || '1.0.0') },
    plugins: [
      react(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['icons/icon-192.png', 'icons/icon-512.png', 'icons/icon-maskable-512.png', 'icons/apple-touch-icon.png', 'favicon.ico', 'logo.png', 'mark.png', 'icon-cart.png', 'icon-product.png'],
        manifest: {
          name: 'PEPITO OS — Operador',
          short_name: 'PEPITO',
          description: 'App del operador de punto de venta: abrir, vender, ayuda y cerrar. Funciona sin señal.',
          lang: 'es-MX',
          start_url: '/',
          scope: '/',
          display: 'standalone',
          orientation: 'portrait',
          background_color: '#F8F2E5',
          theme_color: '#E8590C',
          categories: ['business', 'productivity'],
          icons: [
            { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' },
            { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' },
            { src: 'icons/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
          ],
        },
        workbox: {
          globPatterns: ['**/*.{js,css,html,png,svg,ico,woff2}'],
          navigateFallback: '/index.html',
          navigateFallbackDenylist: [/^\/v1\//],
          // La API nunca se cachea: el estado vive en IndexedDB y la cola.
          runtimeCaching: [
            {
              urlPattern: /\/v1\/.*/,
              handler: 'NetworkOnly',
            },
          ],
        },
        devOptions: { enabled: false },
      }),
    ],
    server: {
      port: 5173,
      proxy: {
        '/v1': { target: apiUrl, changeOrigin: true },
      },
    },
    preview: {
      port: 4173,
      proxy: {
        '/v1': { target: apiUrl, changeOrigin: true },
      },
    },
    test: {
      environment: 'node',
      setupFiles: ['./test/setup.ts'],
      include: ['test/**/*.test.ts'],
    },
  };
});
