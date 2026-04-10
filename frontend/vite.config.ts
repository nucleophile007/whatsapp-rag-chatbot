import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
const proxyTarget = process.env.VITE_PROXY_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: proxyTarget,
        changeOrigin: true,
      },
      "/chat": {
        target: proxyTarget,
        changeOrigin: true,
      },
      "/conversation": {
        target: proxyTarget,
        changeOrigin: true,
      },
      "/job-status": {
        target: proxyTarget,
        changeOrigin: true,
      },
      "/internal": {
        target: proxyTarget,
        changeOrigin: true,
      },
      "/ws": {
        target: proxyTarget.replace(/^http/i, "ws"),
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          query: ['@tanstack/react-query', 'axios'],
          flow: ['reactflow'],
          ui: ['lucide-react'],
        },
      },
    },
  },
})
