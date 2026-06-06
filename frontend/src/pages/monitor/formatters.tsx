import { Typography } from 'antd'

const { Text } = Typography

export function formatBytes(value?: number | null) {
  if (value === null || value === undefined) return '暂无数据'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let size = Number(value)
  let idx = 0
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024
    idx += 1
  }
  return `${size.toFixed(idx === 0 ? 0 : 2)} ${units[idx]}`
}

export function formatMetric(value?: number | string | null, suffix = '') {
  if (value === null || value === undefined || value === '') return '暂无数据'
  return `${value}${suffix}`
}

export function formatRateMetric(value?: number | string | null, suffix = '') {
  if (value === null || value === undefined || value === '') return '暂无数据'
  const numberValue = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numberValue)) return `${value}${suffix}`
  return `${numberValue.toFixed(2)}${suffix}`
}

export function formatPercent(value?: number | string | null) {
  if (value === null || value === undefined || value === '') return '暂无数据'
  const numberValue = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numberValue)) return String(value)
  const percent = numberValue <= 1 ? numberValue * 100 : numberValue
  return `${percent.toFixed(2)}%`
}

export function formatTrendTooltip(value: any, name: string, item?: any) {
  const dataKey = item?.dataKey
  if (dataKey === 'size_gb') return [value === null || value === undefined ? '暂无数据' : `${formatMetric(value)} GB`, '容量']
  if (dataKey === 'qps' || dataKey === 'tps') return [formatRateMetric(value), name]
  return [formatMetric(value), name]
}

export function formatTime(value?: string | null) {
  if (!value) return '暂无数据'
  return value.replace('T', ' ').slice(0, 19)
}

export function formatDurationSeconds(value?: number | null) {
  if (value === null || value === undefined) return '暂无数据'
  const totalSeconds = Math.max(0, Math.floor(Number(value)))
  const days = Math.floor(totalSeconds / 86400)
  const hours = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const parts: string[] = []
  if (days) parts.push(`${days}天`)
  if (hours) parts.push(`${hours}小时`)
  if (minutes && parts.length < 2) parts.push(`${minutes}分钟`)
  if (!parts.length) parts.push(`${seconds}秒`)
  return parts.slice(0, 2).join(' ')
}

export function formatWindowMinutes(value: number) {
  if (value < 60) return `${value} 分钟`
  if (value % 1440 === 0) return `${value / 1440} 天`
  if (value % 60 === 0) return `${value / 60} 小时`
  return `${value} 分钟`
}

export function topSqlHeader(title: string, unit?: string) {
  return (
    <span style={{ whiteSpace: 'nowrap' }}>
      {title}
      {unit ? <Text type="secondary"> ({unit})</Text> : null}
    </span>
  )
}

export function compactSqlText(value?: string | null, maxLength = 140) {
  const sql = (value || '').replace(/\s+/g, ' ').trim()
  if (!sql) return '-'
  if (sql.length <= maxLength) return sql
  return `${sql.slice(0, maxLength)}....`
}
