import { gzipSync } from 'node:zlib'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const assetsDir = new URL('../dist/assets/', import.meta.url)

const limits = {
  jsKiB: Number(process.env.FRONTEND_MAX_JS_KIB || 600),
  jsGzipKiB: Number(process.env.FRONTEND_MAX_JS_GZIP_KIB || 220),
  cssKiB: Number(process.env.FRONTEND_MAX_CSS_KIB || 160),
  cssGzipKiB: Number(process.env.FRONTEND_MAX_CSS_GZIP_KIB || 60),
}

function kib(bytes) {
  return bytes / 1024
}

function fmt(value) {
  return `${value.toFixed(1)} KiB`
}

const files = readdirSync(assetsDir)
  .filter((name) => /\.(js|css)$/.test(name))
  .map((name) => {
    const path = join(assetsDir.pathname, name)
    const bytes = statSync(path).size
    const gzipBytes = gzipSync(readFileSync(path)).length
    return {
      name,
      type: name.endsWith('.css') ? 'css' : 'js',
      kib: kib(bytes),
      gzipKiB: kib(gzipBytes),
    }
  })
  .sort((a, b) => b.kib - a.kib)

const failures = []

for (const file of files) {
  const maxKiB = file.type === 'css' ? limits.cssKiB : limits.jsKiB
  const maxGzipKiB = file.type === 'css' ? limits.cssGzipKiB : limits.jsGzipKiB
  if (file.kib > maxKiB) {
    failures.push(`${file.name} raw ${fmt(file.kib)} exceeds ${fmt(maxKiB)}`)
  }
  if (file.gzipKiB > maxGzipKiB) {
    failures.push(`${file.name} gzip ${fmt(file.gzipKiB)} exceeds ${fmt(maxGzipKiB)}`)
  }
}

console.log('Frontend build budget check')
console.log(`Limits: JS <= ${fmt(limits.jsKiB)} raw / ${fmt(limits.jsGzipKiB)} gzip; CSS <= ${fmt(limits.cssKiB)} raw / ${fmt(limits.cssGzipKiB)} gzip`)
console.log('Largest assets:')
for (const file of files.slice(0, 10)) {
  console.log(`- ${file.name}: ${fmt(file.kib)} raw, ${fmt(file.gzipKiB)} gzip`)
}

if (failures.length) {
  console.error('\nBuild budget exceeded:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('Build budget passed.')
