import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

const apiTarget = process.env.VITE_DEV_PROXY_TARGET || 'http://localhost:8000'
const wsTarget = process.env.VITE_DEV_WS_TARGET || 'ws://localhost:8000'
const usePolling = process.env.CHOKIDAR_USEPOLLING === 'true'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    watch: {
      usePolling,
    },
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/ws': {
        target: wsTarget,
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor':  ['react', 'react-dom', 'react-router-dom'],
          'antd-vendor':   ['antd', '@ant-design/icons', '@ant-design/pro-components'],
          'query-vendor':  ['@tanstack/react-query'],
          'chart-vendor':  ['recharts'],
          'monaco-vendor': ['@monaco-editor/react'],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
    css: true,
  },
})
