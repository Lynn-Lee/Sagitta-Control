import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '../..')
const screenshotDir = resolve(repoRoot, 'docs/screenshots/user-manual')
const captureScript = resolve(import.meta.dirname, 'capture-user-manual-screenshots.mjs')

const expected = readdirSync(screenshotDir)
  .filter((name) => name.endsWith('.png'))
  .sort()

const script = readFileSync(captureScript, 'utf8')
const actual = [...script.matchAll(/\[\s*['"]([^'"]+\.png)['"]\s*,/g)]
  .map((match) => match[1])
  .sort()

const missing = expected.filter((name) => !actual.includes(name))
const extra = actual.filter((name) => !expected.includes(name))

if (missing.length || extra.length) {
  console.error('User manual screenshot manifest is out of sync.')
  if (missing.length) console.error(`Missing from capture script: ${missing.join(', ')}`)
  if (extra.length) console.error(`Extra in capture script: ${extra.join(', ')}`)
  process.exit(1)
}

if (actual.includes('20-license.png')) {
  console.error('20-license.png must not be captured for the public user manual.')
  process.exit(1)
}

console.log(`User manual screenshot manifest is in sync (${actual.length} screenshots).`)
