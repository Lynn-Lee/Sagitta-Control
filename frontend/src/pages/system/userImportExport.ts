// 用户管理页的导入/导出纯工具：文件名解析、浏览器下载触发、失败明细 CSV 生成。
// 与 archive/archiveActions.ts 一致的抽取范式，将无 React 状态的逻辑从页面组件中分离。

export type ImportErrorRow = {
  row: number
  username: string
  error: string
  row_data?: Record<string, string>
}

export type ImportResult = {
  total: number
  created: number
  updated: number
  failed: number
  auto_created_user_groups?: number
  import_headers?: string[]
  errors: ImportErrorRow[]
}

export const IMPORT_DEFAULT_PASSWORD = 'Sagitta@2026A'

// 从 Content-Disposition 响应头解析下载文件名，优先取 RFC 5987 的 UTF-8 编码形式。
export function extractFileName(contentDisposition?: string, fallback = 'users_export.xlsx') {
  if (!contentDisposition) return fallback
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1])
  const normalMatch = contentDisposition.match(/filename="?([^"]+)"?/i)
  return normalMatch?.[1] || fallback
}

export function triggerDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  window.URL.revokeObjectURL(url)
}

export function downloadImportErrors(errors: ImportErrorRow[], importHeaders?: string[]) {
  const headers = (importHeaders && importHeaders.length ? importHeaders : ['username']).filter(Boolean)
  const lines = [
    ['source_row', ...headers, 'import_error'],
    ...errors.map((item) => [
      String(item.row),
      ...headers.map((header) => item.row_data?.[header] || ''),
      item.error || '',
    ]),
  ]
  const csv = lines
    .map((line) => line.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n')
  // 前置 UTF-8 BOM，保证 Excel 正确识别中文编码
  triggerDownload(
    new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }),
    'users_import_errors.csv',
  )
}
