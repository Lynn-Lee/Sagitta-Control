import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const args = process.argv.slice(2)
const checkOnly = args.includes('--check')
const roots = args.filter((arg) => arg !== '--check')

if (roots.length === 0) {
  console.error('Usage: node scripts/scrub-sourcemap-directives.mjs [--check] <dir> [dir...]')
  process.exit(2)
}

const lineDirective = /^[ \t]*\/\/[#@][ \t]*sourceMappingURL=[^\r\n]*(?:\r?\n)?/gm
const blockDirective = /\/\*[#@][ \t]*sourceMappingURL=.*?\*\//gs
const checkLineDirective = /^[ \t]*\/\/[#@][ \t]*sourceMappingURL=/m
const checkBlockDirective = /\/\*[#@][ \t]*sourceMappingURL=.*?\*\//s

function walk(path) {
  const stat = statSync(path)
  if (stat.isDirectory()) {
    return readdirSync(path).flatMap((entry) => walk(join(path, entry)))
  }
  return stat.isFile() ? [path] : []
}

const changed = []
const offenders = []

for (const root of roots) {
  for (const file of walk(root)) {
    let text
    try {
      text = readFileSync(file, 'utf8')
    } catch {
      continue
    }

    if (checkLineDirective.test(text) || checkBlockDirective.test(text)) {
      offenders.push(file)
    }

    if (!checkOnly) {
      const next = text.replace(lineDirective, '').replace(blockDirective, '')
      if (next !== text) {
        writeFileSync(file, next)
        changed.push(file)
      }
    }
  }
}

if (checkOnly && offenders.length > 0) {
  console.error(`Sourcemap directives found:\n${offenders.join('\n')}`)
  process.exit(1)
}

if (!checkOnly && changed.length > 0) {
  console.log(`Removed sourcemap directives from ${changed.length} file(s).`)
}
