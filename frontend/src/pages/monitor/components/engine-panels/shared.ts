export function stateSummaryText(value?: Record<string, number>) {
  if (!value || !Object.keys(value).length) return '暂无数据'
  return Object.entries(value).map(([key, count]) => `${key}: ${count}`).join(' / ')
}
