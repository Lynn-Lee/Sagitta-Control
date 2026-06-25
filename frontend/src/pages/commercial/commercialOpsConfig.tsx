import type { ReactNode } from 'react'
import {
  ExportOutlined,
  FileSearchOutlined,
  KeyOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from '@ant-design/icons'

export type ReportTypeConfig = {
  key: string
  label: string
  icon: ReactNode
  className: string
}

export const reportTypes: ReportTypeConfig[] = [
  { key: 'high_risk_operations', label: '高风险操作', icon: <WarningOutlined />, className: 'sagitta-action-btn--danger' },
  { key: 'query_export', label: '查询导出', icon: <ExportOutlined />, className: 'sagitta-action-btn--download' },
  { key: 'permission_changes', label: '权限变更', icon: <KeyOutlined />, className: 'sagitta-action-btn--inspect' },
  { key: 'license_operations', label: 'License 操作', icon: <SafetyCertificateOutlined />, className: 'sagitta-action-btn--manage' },
]

export const licenseStatusColor: Record<string, string> = {
  trial: 'gold',
  licensed: 'green',
  expired: 'red',
  invalid: 'red',
}

export const licenseStatusLabel: Record<string, string> = {
  trial: '试用中',
  licensed: '正式授权',
  expired: '已过期',
  invalid: '无效',
}

export const readinessColor: Record<string, string> = {
  ready: 'green',
  needs_configuration: 'orange',
  blocked: 'red',
}

export const supportLevelColor: Record<string, string> = {
  ga: 'green',
  validated_minimal: 'blue',
  read_only_metadata: 'gold',
  experimental: 'orange',
  backlog: 'default',
}

export const onboardingStatusColor: Record<string, string> = {
  done: 'green',
  blocked: 'red',
  todo: 'orange',
}

export const onboardingStatusLabel: Record<string, string> = {
  done: '已完成',
  blocked: '阻塞',
  todo: '待处理',
}

export const nowrapText = (value: unknown) => (
  <span style={{ whiteSpace: 'nowrap' }}>{String(value ?? '-')}</span>
)
