import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    // Configurable so two stores can be inspected side by side (e.g. the
    // isolated night-run store on 8420 and a real-store copy on 8421) without
    // editing this file and risking it being committed pointed somewhere odd.
    proxy: {
      '/api': process.env.HELICON_API || 'http://127.0.0.1:8420',
    },
  },
})
