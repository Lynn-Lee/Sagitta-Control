/* eslint-disable react-refresh/only-export-components */
import { Tag, Tooltip } from 'antd'
import dayjs from 'dayjs'
import type { SlowQueryGroupTrend } from '@/api/slowlog'

export const SOURCE_OPTIONS = [
  { label: '平台历史', value: 'platform' },
  { label: 'MySQL 统计视图', value: 'mysql_slowlog' },
  { label: 'PostgreSQL 统计视图', value: 'pgsql_statements' },
  { label: 'Redis SLOWLOG', value: 'redis_slowlog' },
  { label: 'TiDB SQL 活动', value: 'tidb_statements' },
  { label: 'StarRocks SQL 活动', value: 'starrocks_queries' },
  { label: 'Doris SQL 活动', value: 'doris_queries' },
  { label: 'Oracle SQL Monitor', value: 'oracle_sql_monitor' },
  { label: 'Oracle AWR SQLStat', value: 'oracle_awr_sqlstat' },
  { label: 'Oracle Cursor Cache', value: 'oracle_cursor_cache' },
  { label: 'Oracle 会话/ASH', value: 'oracle_activity' },
  { label: '会话采样', value: 'session_history' },
]

export const SOURCE_COLOR: Record<string, string> = {
  platform: 'blue',
  platform_history: 'blue',
  mysql_slowlog: 'orange',
  pgsql_statements: 'green',
  redis_slowlog: 'red',
  tidb_statements: 'cyan',
  starrocks_queries: 'geekblue',
  doris_queries: 'magenta',
  oracle_sql_monitor: 'red',
  oracle_awr_sqlstat: 'gold',
  oracle_cursor_cache: 'lime',
  oracle_activity: 'volcano',
  session_history: 'purple',
}

const SOURCE_LABELS: Record<string, string> = Object.fromEntries(
  SOURCE_OPTIONS.map(item => [item.value, item.label]),
)
SOURCE_LABELS.platform_history = '平台历史'

export const RISK_COLOR = (value: number) => value >= 70 ? 'red' : value >= 35 ? 'gold' : 'green'

export const SEVERITY_COLOR: Record<string, string> = {
  critical: 'error',
  warning: 'warning',
  info: 'processing',
  ok: 'success',
}

export const TREND_COLORS = ['#165DFF', '#00B42A', '#FF7D00', '#C41D7F', '#6F42C1', '#08979C']

export const sourceLabel = (source: string) => SOURCE_LABELS[source] || source

export const formatTime = (value?: string | null) => value ? dayjs(value).format('MM-DD HH:mm:ss') : '—'

export const formatMs = (value?: number) => `${Number(value || 0).toLocaleString()} ms`

export const renderSourceTag = (source?: string) => {
  const value = source || ''
  const label = sourceLabel(value)
  return (
    <Tooltip title={label}>
      <Tag
        color={SOURCE_COLOR[value] || 'default'}
        style={{
          boxSizing: 'border-box',
          display: 'inline-block',
          marginInlineEnd: 0,
          maxWidth: '100%',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          verticalAlign: 'middle',
          whiteSpace: 'nowrap',
        }}
      >
        {label}
      </Tag>
    </Tooltip>
  )
}

export function buildTrendRows(groups: SlowQueryGroupTrend[], metric: 'count' | 'avg_duration_ms') {
  const buckets = Array.from(new Set(groups.flatMap(group => group.points.map(point => point.bucket)))).sort()
  return buckets.map(bucket => {
    const row: Record<string, string | number> = { bucket }
    groups.forEach(group => {
      row[group.group_key] = group.points.find(point => point.bucket === bucket)?.[metric] || 0
    })
    return row
  })
}
