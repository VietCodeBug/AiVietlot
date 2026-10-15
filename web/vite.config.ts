import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [react(), tailwindcss(), VitePWA({
    registerType: 'prompt',
    includeAssets: ['favicon.svg', 'icon-192.png', 'icon-512.png'],
    manifest: {
      name: 'Mega Lab · Phòng thí nghiệm xác suất',
      short_name: 'Mega Lab',
      description: 'Lịch sử, thống kê và thí nghiệm xác suất Mega 6/45.',
      theme_color: '#153e35',
      background_color: '#f7f8f3',
      display: 'standalone',
      lang: 'vi',
      start_url: '/',
      icons: [
        { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
        { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
      ],
    },
    workbox: {
      globPatterns: ['**/*.{js,css,html,svg,png,woff2,ttf}'],
      navigateFallback: '/index.html',
      cleanupOutdatedCaches: true,
      // API responses, authentication and credentials never enter the SW cache.
      runtimeCaching: [],
      maximumFileSizeToCacheInBytes: 3_000_000,
    },
    devOptions: { enabled: false },
  })],
  test: { include: ['src/**/*.test.ts'], environment: 'node' },
  build: { chunkSizeWarningLimit: 700 },
})
