import { loader } from '@monaco-editor/react'

export const MONACO_ASSET_BASE = '/monaco-editor/min/vs'

let configured = false

export function configureMonacoEditor() {
  if (configured) return
  loader.config({ paths: { vs: MONACO_ASSET_BASE } })
  configured = true
}
