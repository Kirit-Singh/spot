/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Hybrid MPA: four downstream stage pages are React HTML entries sharing ONE bundle.
// The Programs page (public/01_page.html) is the migrated hand-written Stage-1 page,
// copied verbatim from publicDir along with its data/. Entry point is /01_page.html.
// base: './' keeps asset URLs relative so the dist serves from any document root.
const entry = (name: string) => fileURLToPath(new URL(`./${name}.html`, import.meta.url))

export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        targets: entry('targets'),
        pathways: entry('pathways'),
        drugs: entry('drugs'),
        pksafety: entry('pksafety'),
        // Per-stage Methods (notebook) + Provenance (trace) routed views.
        '01_notebook': entry('01_notebook'),
        '01_trace': entry('01_trace'),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
    css: false,
  },
})
