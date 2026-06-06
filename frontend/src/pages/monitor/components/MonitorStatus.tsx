/* eslint-disable react-refresh/only-export-components */
import { Statistic, Tag } from 'antd'

import type { MonitorInstance } from '../types'
import { formatMetric } from '../formatters'

const statusColor: Record<string, string> = {
  success: 'success',
  partial: 'warning',
  failed: 'error',
  pending: 'processing',
  not_configured: 'default',
  never: 'default',
  skipped: 'default',
}

const riskColor: Record<string, string> = {
  healthy: 'success',
  attention: 'processing',
  warning: 'warning',
  critical: 'error',
}

export function StatusTag({ status }: { status?: string }) {
  const value = status || 'not_configured'
  const label: Record<string, string> = {
    success: '正常',
    partial: '部分缺失',
    failed: '采集失败',
    pending: '待采集',
    not_configured: '未配置',
    never: '未采集',
    skipped: '已跳过',
  }
  return <Tag color={statusColor[value] || 'default'}>{label[value] || value}</Tag>
}

export function ConfigStatusTag({ row }: { row: Pick<MonitorInstance, 'config_id' | 'config_enabled'> }) {
  if (!row.config_id) return <Tag>未配置</Tag>
  return row.config_enabled ? <Tag color="success">已启用</Tag> : <Tag color="default">已停用</Tag>
}

export function RiskTag({ level, label }: { level?: string; label?: string }) {
  const value = level || 'attention'
  return <Tag color={riskColor[value] || 'default'}>{label || value}</Tag>
}

export function riskReasonText(row?: Pick<MonitorInstance, 'risk_reasons' | 'latest'> | null) {
  const reasons = row?.risk_reasons || row?.latest?.risk_reasons || []
  return reasons.length ? reasons.join('；') : '暂无明显风险'
}

export function MetricCard({ title, value, suffix, danger }: { title: string; value?: number | string | null; suffix?: string; danger?: boolean }) {
  return (
    <div style={{ border: '1px solid rgba(0,0,0,0.08)', borderRadius: 8, padding: 16, minHeight: 92 }}>
      <Statistic title={title} value={formatMetric(value, suffix)} valueStyle={{ fontSize: 20, color: danger ? '#cf1322' : undefined }} />
    </div>
  )
}
