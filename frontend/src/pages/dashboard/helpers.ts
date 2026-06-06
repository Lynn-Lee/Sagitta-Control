export const RANGE_OPTIONS = [7, 14, 30, 60]

export const clampRangeDays = (value: number) => Math.min(365, Math.max(1, Number.isFinite(value) ? value : 1))

export const DASHBOARD_CHART_HEIGHT = 300
export const DASHBOARD_GRID_STROKE = 'rgba(0,0,0,0.06)'
export const DASHBOARD_CARD_STYLE = { borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }

export const CHART_COLORS = {
  primary: '#165DFF',
  primaryDeep: '#0E42C1',
  cyan: '#08979C',
  success: '#00B42A',
  warning: '#FF7D00',
  error: '#F53F3F',
  purple: '#6F42C1',
  gray: '#86909C',
  lime: '#7CB305',
  magenta: '#C41D7F',
}

export const TOP_USER_COLORS = [
  CHART_COLORS.primary,
  CHART_COLORS.primaryDeep,
  CHART_COLORS.cyan,
  CHART_COLORS.success,
  CHART_COLORS.warning,
  CHART_COLORS.purple,
  CHART_COLORS.magenta,
  CHART_COLORS.lime,
]

export const WORKFLOW_TOP_COLORS = TOP_USER_COLORS

export const QUERY_GOVERNANCE_COLORS = {
  pendingStock: CHART_COLORS.purple,
  failure: CHART_COLORS.error,
  masked: CHART_COLORS.cyan,
  approved: CHART_COLORS.success,
  rejected: CHART_COLORS.warning,
  revoked: CHART_COLORS.gray,
}

export const WORKFLOW_COLORS = {
  submit: CHART_COLORS.primary,
  approved: CHART_COLORS.success,
  rejected: CHART_COLORS.warning,
  cancel: CHART_COLORS.gray,
  executeFailed: CHART_COLORS.error,
  queued: CHART_COLORS.purple,
  running: CHART_COLORS.primary,
  success: CHART_COLORS.cyan,
  pendingStock: CHART_COLORS.purple,
}

export const ARCHIVE_COLORS = {
  submit: CHART_COLORS.primary,
  success: CHART_COLORS.success,
  failed: CHART_COLORS.error,
  canceled: CHART_COLORS.gray,
  scheduled: CHART_COLORS.purple,
  running: CHART_COLORS.primary,
  rows: CHART_COLORS.cyan,
  risk: CHART_COLORS.warning,
  activeStock: CHART_COLORS.purple,
}

export function buildTopChartData<T extends Record<string, string | number>>(
  items: T[] | undefined,
  valueKey: keyof T,
) {
  return [...(items || [])].reverse().map(item => ({ ...item, [valueKey]: Number(item[valueKey] || 0) }))
}
