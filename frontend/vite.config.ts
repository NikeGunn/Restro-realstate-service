/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
  server: {
    port: 3000,
    host: true,
    // Same split as the prod ingress: the public listings site, sitemap and robots are
    // server-rendered by Django (SEO), everything else is this SPA.
    proxy: Object.fromEntries(
      ['/realestate/properties', '/sitemap.xml', '/robots.txt'].map((p) => [
        p,
        { target: process.env.VITE_BACKEND_ORIGIN || 'http://backend:8000', changeOrigin: false },
      ]),
    ),
  },
  build: {
    sourcemap: false, // Disable sourcemaps in production to prevent file paths from showing
    minify: 'esbuild',
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
})
