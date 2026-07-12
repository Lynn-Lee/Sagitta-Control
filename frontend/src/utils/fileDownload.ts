// 通用文件下载工具：Content-Disposition 文件名解析与浏览器下载触发。
// 收敛自用户 / 用户组管理、在线查询导出等页面此前各自内联的重复实现。

// 从 Content-Disposition 响应头解析下载文件名，优先取 RFC 5987 的 UTF-8 编码形式。
export function extractFileName(contentDisposition?: string, fallback = 'download') {
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
