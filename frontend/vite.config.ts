import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { createReadStream, cpSync, existsSync, rmSync, statSync } from 'node:fs'
import { extname, join, normalize, relative, resolve } from 'node:path'

const monacoAssetBase = '/monaco-editor/min/vs'
const monacoSourceDir = resolve(__dirname, 'node_modules/monaco-editor/min/vs')
const monacoOutputDir = resolve(__dirname, 'dist/monaco-editor/min/vs')
const monacoMimeTypes: Record<string, string> = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.ttf': 'font/ttf',
  '.wasm': 'application/wasm',
}

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

function localMonacoAssetsPlugin() {
  return {
    name: 'local-monaco-assets',
    closeBundle() {
      if (!existsSync(monacoSourceDir)) {
        throw new Error(`Monaco editor assets not found: ${monacoSourceDir}`)
      }
      rmSync(monacoOutputDir, { recursive: true, force: true })
      cpSync(monacoSourceDir, monacoOutputDir, { recursive: true })
    },
    configureServer(server) {
      server.middlewares.use(monacoAssetBase, (req, res, next) => {
        const rawUrl = decodeURIComponent((req.url ?? '').split('?')[0] || '/')
        const requestPath = rawUrl.startsWith(monacoAssetBase)
          ? rawUrl.slice(monacoAssetBase.length) || '/'
          : rawUrl
        const candidate = normalize(join(monacoSourceDir, requestPath))
        const relativePath = relative(monacoSourceDir, candidate)
        if (relativePath.startsWith('..')) {
          res.statusCode = 403
          res.end('Forbidden')
          return
        }
        if (!existsSync(candidate) || !statSync(candidate).isFile()) {
          next()
          return
        }
        res.setHeader('Content-Type', monacoMimeTypes[extname(candidate)] ?? 'application/octet-stream')
        createReadStream(candidate).pipe(res)
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), localMonacoAssetsPlugin()],
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
