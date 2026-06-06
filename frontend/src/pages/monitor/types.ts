import type { ReactNode } from 'react'

export const TOP_SQL_WINDOW_OPTIONS = [5, 15, 30, 60, 180, 360, 720, 1440]
export const TOP_SQL_TIME_FORMAT = 'YYYY-MM-DD HH:mm:ss'

export interface MonitorSnapshot {
  collected_at?: string | null
  status: string
  error?: string
  missing_groups?: Record<string, string>
  is_up: boolean
  version?: string
  uptime_seconds?: number | null
  current_connections?: number | null
  active_sessions?: number | null
  max_connections?: number | null
  connection_usage?: number | null
  qps?: number | null
  tps?: number | null
  slow_queries?: number | null
  error_count?: number | null
  lock_waits?: number | null
  long_transactions?: number | null
  replication_lag_seconds?: number | null
  total_size_bytes?: number | null
  extra_metrics?: Record<string, any>
  metric_groups?: Record<string, any>
  health_score?: number
  risk_level?: string
  risk_label?: string
  risk_reasons?: string[]
}

export interface MonitorInstance {
  instance_id: number
  instance_name: string
  db_type: string
  is_active: boolean
  config_id?: number | null
  config_enabled: boolean
  collect_interval?: number | null
  capacity_collect_interval?: number | null
  retention_days?: number | null
  last_metric_collect_at?: string | null
  last_capacity_collect_at?: string | null
  last_collect_status: string
  last_collect_error?: string
  latest?: MonitorSnapshot | null
  health_score?: number
  risk_level?: string
  risk_label?: string
  risk_reasons?: string[]
}

export interface MonitorOverview {
  cards: Record<string, number>
  distributions: Record<string, Record<string, number>>
  items: MonitorInstance[]
}

export interface UnifiedCollectConfigItem {
  instance_id: number
  instance_name: string
  db_type: string
  native: {
    id?: number | null
    is_enabled: boolean
    collect_interval: number
    capacity_collect_interval: number
    retention_days: number
    last_metric_collect_at?: string | null
    last_capacity_collect_at?: string | null
    last_collect_status: string
    last_collect_error: string
  }
  session: {
    id?: number | null
    is_enabled: boolean
    collect_interval: number
    retention_days: number
    last_collect_at?: string | null
    last_collect_status: string
    last_collect_error: string
    last_collect_count: number
  }
  sql: {
    id?: number | null
    is_enabled: boolean
    threshold_ms: number
    collect_interval: number
    retention_days: number
    collect_limit: number
    last_collect_at?: string | null
    last_collect_status: string
    last_collect_error: string
    last_collect_count: number
    last_collect_sources: string[]
    last_collect_message: string
  }
}

export interface UnifiedCollectConfigListResponse {
  total: number
  items: UnifiedCollectConfigItem[]
}

export interface BulkCollectConfigResponse {
  total: number
  success: number
  failed: string[]
}

export type EnginePanelContext = {
  metricGroups: Record<string, any>
  isMobile: boolean
}

export type EngineDiagnosticPanel = {
  key: string
  label: ReactNode
  render: (context: EnginePanelContext) => ReactNode
}
