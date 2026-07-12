import { describe, expect, it, vi } from 'vitest'

const config = vi.fn()

vi.mock('@monaco-editor/react', () => ({
  loader: { config },
}))

describe('configureMonacoEditor', () => {
  it('uses local monaco assets instead of the default CDN loader', async () => {
    const { configureMonacoEditor } = await import('./monacoEditor')

    configureMonacoEditor()
    configureMonacoEditor()

    expect(config).toHaveBeenCalledTimes(1)
    expect(config).toHaveBeenCalledWith({ paths: { vs: '/monaco-editor/min/vs' } })
  })
})
