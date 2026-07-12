export const DATE_TIME_DISPLAY_FORMAT = 'YYYY-MM-DD HH:mm:ss'

const pad2 = (value: string | undefined) => String(value || '0').padStart(2, '0').slice(0, 2)

function isValidDateTime(year: number, month: number, day: number, hour: number, minute: number, second: number) {
  const date = new Date(year, month - 1, day, hour, minute, second)
  return (
    date.getFullYear() === year &&
    date.getMonth() === month - 1 &&
    date.getDate() === day &&
    date.getHours() === hour &&
    date.getMinutes() === minute &&
    date.getSeconds() === second
  )
}

// 将后端多种来源的日期时间统一格式化为全站口径 YYYY-MM-DD HH:mm:ss；无法解析时回退占位符
export function formatDateTime(value?: string | null, fallback = '—') {
  const rawValue = String(value || '').trim()
  if (!rawValue) return fallback

  // 归一化：斜杠转连字符、ISO 的 T 转空格、去掉小数秒和时区后缀（Z 或 ±HH:mm），只保留本地日期时间
  const normalized = rawValue
    .replace(/\//g, '-')
    .replace('T', ' ')
    .replace(/\.\d+/, '')
    .replace(/Z$/, '')
    .replace(/[+-]\d{2}:?\d{2}$/, '')
    .trim()
  const [datePart = '', timePart = ''] = normalized.split(/\s+/)
  const dateMatch = datePart.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/)
  if (!dateMatch) return fallback

  const timeMatch = timePart.match(/^(\d{1,2})(?::(\d{1,2}))?(?::(\d{1,2}))?/)
  const year = Number(dateMatch[1])
  const month = Number(dateMatch[2])
  const day = Number(dateMatch[3])
  const hour = Number(timeMatch?.[1] || 0)
  const minute = Number(timeMatch?.[2] || 0)
  const second = Number(timeMatch?.[3] || 0)

  if (!isValidDateTime(year, month, day, hour, minute, second)) return fallback

  return [
    `${dateMatch[1]}-${pad2(dateMatch[2])}-${pad2(dateMatch[3])}`,
    `${pad2(timeMatch?.[1])}:${pad2(timeMatch?.[2])}:${pad2(timeMatch?.[3])}`,
  ].join(' ')
}
