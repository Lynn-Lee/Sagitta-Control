// 用户组管理页的导入/导出纯工具：失败明细 CSV 生成。
// 通用的文件名解析 / 下载触发收敛到 @/utils/fileDownload，这里再导出以便页面单点引用。
import { triggerDownload } from '@/utils/fileDownload'

export { extractFileName, triggerDownload } from '@/utils/fileDownload'

export type ImportErrorRow = {
  row: number
  name: string
  error: string
  row_data?: Record<string, string>
}

export type ImportResult = {
  total: number
  created: number
  updated: number
  failed: number
  import_headers?: string[]
  errors: ImportErrorRow[]
}

export function downloadImportErrors(errors: ImportErrorRow[], importHeaders?: string[]) {
  const headers = (importHeaders && importHeaders.length ? importHeaders : ['name']).filter(Boolean)
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
    'user_groups_import_errors.csv',
  )
}
