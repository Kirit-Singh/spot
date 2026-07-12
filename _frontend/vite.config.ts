/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The deployable entry is `02_page.html` (copied into spot-dist next to the
// unchanged `01_page.html`). `base: './'` keeps asset URLs relative so the bundle
// works from any document root. Assets are content-hashed under `assets/`.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    rollupOptions: {
      input: fileURLToPath(new URL('./02_page.html', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
    css: false,
  },
})
