import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { test } from 'vitest'

import { validateScreenshotCaptureConfig } from './capture-user-manual-screenshots.config.mjs'

test('requires credentials before overwriting authenticated user manual screenshots', () => {
  assert.throws(
    () => validateScreenshotCaptureConfig({ username: '', password: '', smokeOnly: false }),
    /E2E_USERNAME\/E2E_PASSWORD/,
  )
})

test('allows smoke mode without credentials', () => {
  assert.doesNotThrow(() => validateScreenshotCaptureConfig({ username: '', password: '', smokeOnly: true }))
})

test('allows screenshot overwrite when both credentials are supplied', () => {
  assert.doesNotThrow(() =>
    validateScreenshotCaptureConfig({ username: 'admin', password: 'Admin@2024!', smokeOnly: false }),
  )
})

test('reports missing credentials before loading browser dependencies', () => {
  const result = spawnSync(process.execPath, ['scripts/capture-user-manual-screenshots.mjs'], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      E2E_USERNAME: '',
      E2E_PASSWORD: '',
      E2E_SMOKE_ONLY: '',
    },
    encoding: 'utf8',
  })

  assert.notEqual(result.status, 0)
  assert.match(result.stderr, /E2E_USERNAME\/E2E_PASSWORD/)
  assert.doesNotMatch(result.stderr, /@playwright\/test/)
})
