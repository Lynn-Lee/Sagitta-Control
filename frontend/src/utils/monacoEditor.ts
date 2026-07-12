import { loader } from '@monaco-editor/react'

// 用户部署镜像禁止依赖外部 CDN 且前端启用严格 CSP，Monaco 运行时改为前端镜像内自托管
export const MONACO_ASSET_BASE = '/monaco-editor/min/vs'

let configured = false

// 将 Monaco loader 指向自托管资源路径；幂等，重复调用只生效一次
export function configureMonacoEditor() {
  if (configured) return
  loader.config({ paths: { vs: MONACO_ASSET_BASE } })
  configured = true
}
