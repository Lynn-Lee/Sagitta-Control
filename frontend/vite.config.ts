import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

const apiTarget = process.env.VITE_DEV_PROXY_TARGET || 'http://localhost:8000'
const wsTarget = process.env.VITE_DEV_WS_TARGET || 'ws://localhost:8000'
const usePolling = process.env.CHOKIDAR_USEPOLLING === 'true'
const manualChunkGroups: Record<string, string[]> = {
  'react-vendor':  ['react', 'react-dom', 'react-router-dom'],
  'query-vendor':  ['@tanstack/react-query'],
  'chart-vendor':  ['recharts'],
  'monaco-vendor': ['@monaco-editor/react'],
}

function manualChunks(id: string) {
  if (!id.includes('node_modules')) return undefined
  for (const [chunkName, packages] of Object.entries(manualChunkGroups)) {
    if (packages.some(pkg => id.includes(`/node_modules/${pkg}/`))) {
      return chunkName
    }
  }
  return undefined
}

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
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
        passes: 2,
      },
      mangle: {
        safari10: true,
      },
      format: {
        comments: false,
      },
    },
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[hash].js',
        chunkFileNames: 'assets/[hash].js',
        assetFileNames: 'assets/[hash][extname]',
        manualChunks,
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
