import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const proxyTarget = process.env.VITE_PROXY_TARGET || "http://localhost:8000";
const proxy = {
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
};

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    proxy,
  },
  preview: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy,
  },
})
