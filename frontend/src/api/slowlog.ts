import apiClient from './client'

export interface SlowQueryLogItem {
  id: number
  source: string
  instance_id?: number | null
  instance_name: string
  db_type: string
  db_name: string
  sql_text: string
  sql_fingerprint: string
  fingerprint_text: string
  duration_ms: number
  rows_examined: number
  rows_sent: number
  username: string
  client_host: string
  occurred_at: string
  analysis_tags: string[]
  collect_error: string
}

export interface SlowQueryLogListResponse {
  total: number
  page: number
  page_size: number
  items: SlowQueryLogItem[]
}

export interface SlowQueryTrendPoint {
  bucket: string
  count: number
  avg_duration_ms: number
  failed_count: number
}

export interface SlowQueryGroupStat {
  group_key: string
  group_name: string
  instance_id?: number | null
  instance_name: string
  db_type: string
  db_name: string
  total: number
  fingerprint_count: number
  database_count: number
  failed_count: number
  avg_duration_ms: number
  p95_duration_ms: number
  max_duration_ms: number
  last_seen_at?: string | null
}

export interface SlowQueryGroupTrend {
  group_key: string
  group_name: string
  points: SlowQueryTrendPoint[]
}

export interface SlowQueryOverviewResponse {
  total: number
  fingerprint_count: number
  instance_count: number
  failed_count: number
  avg_duration_ms: number
  p95_duration_ms: number
  max_duration_ms: number
  slowest?: SlowQueryLogItem | null
  unsupported_msg: string
  trends: SlowQueryTrendPoint[]
  source_distribution: SlowQueryDistributionItem[]
  instance_stats: SlowQueryGroupStat[]
  database_stats: SlowQueryGroupStat[]
  group_trends: SlowQueryGroupTrend[]
}

export interface SlowQueryFingerprintItem {
  sql_fingerprint: string
  fingerprint_text: string
  sample_sql: string
  instance_id?: number | null
  instance_name: string
  db_type: string
  db_name: string
  instance_count: number
  database_count: number
  count: number
  avg_duration_ms: number
  max_duration_ms: number
  p95_duration_ms: number
  rows_examined: number
  rows_sent: number
  analysis_tags: string[]
  last_seen_at?: string | null
}

export interface SlowQueryFingerprintListResponse {
  total: number
  items: SlowQueryFingerprintItem[]
}

export interface SlowQueryDistributionItem {
  name: string
  count: number
  avg_duration_ms: number
}

export interface SlowQueryRecommendation {
  severity: string
  title: string
  detail: string
}

export interface SlowQueryFingerprintDetailResponse {
  fingerprint: SlowQueryFingerprintItem
  trends: SlowQueryTrendPoint[]
  instance_distribution: SlowQueryDistributionItem[]
  database_distribution: SlowQueryDistributionItem[]
  user_distribution: SlowQueryDistributionItem[]
  source_distribution: SlowQueryDistributionItem[]
  recommendations: SlowQueryRecommendation[]
  samples: SlowQueryLogItem[]
}

export interface SlowQueryCollectResponse {
  instances: number
  saved: number
  failed: number
  unsupported: number
  msg: string
  errors: string[]
}

export interface SlowQueryConfigItem {
  id: number
  instance_id: number
  instance_name: string
  db_type: string
  is_enabled: boolean
  threshold_ms: number
  collect_interval: number
  retention_days: number
  collect_limit: number
  last_collect_at?: string | null
  last_collect_status: string
  last_collect_error: string
  last_collect_count: number
  created_by: string
}

export interface SlowQueryExplainResponse {
  supported: boolean
  db_type: string
  summary: SlowQueryRecommendation[]
  plan: Record<string, any>
  raw: any
  msg: string
}

export interface SlowQueryParams {
  instance_id?: number
  db_name?: string
  source?: string
  sql_keyword?: string
  username?: string
  tag?: string
  min_duration_ms?: number
  date_start?: string
  date_end?: string
  page?: number
  page_size?: number
  limit?: number
}

export interface SlowQueryTagOptionsResponse {
  items: Record<string, string[]>
}

export const slowlogApi = {
  configs: () =>
    apiClient.get<{ total: number; items: SlowQueryConfigItem[] }>('/sql-analysis/configs/').then(r => r.data),

  tagOptions: () =>
    apiClient.get<SlowQueryTagOptionsResponse>('/sql-analysis/tag-options/').then(r => r.data),

  saveConfig: (data: {
    instance_id: number
    is_enabled: boolean
    threshold_ms: number
    collect_interval: number
    retention_days: number
    collect_limit: number
  }) => apiClient.post('/sql-analysis/configs/', data).then(r => r.data),

  updateConfig: (id: number, data: Partial<SlowQueryConfigItem>) =>
    apiClient.put(`/sql-analysis/configs/${id}/`, data).then(r => r.data),

  overview: (params: SlowQueryParams) =>
    apiClient.get<SlowQueryOverviewResponse>('/sql-analysis/overview/', { params }).then(r => r.data),

  logs: (params: SlowQueryParams) =>
    apiClient.get<SlowQueryLogListResponse>('/sql-analysis/logs/', { params }).then(r => r.data),

  fingerprints: (params: SlowQueryParams) =>
    apiClient.get<SlowQueryFingerprintListResponse>('/sql-analysis/fingerprints/', { params }).then(r => r.data),

  samples: (fingerprint: string, limit = 20) =>
    apiClient.get<{ items: SlowQueryLogItem[] }>(`/sql-analysis/fingerprints/${fingerprint}/samples/`, { params: { limit } }).then(r => r.data),

  fingerprintDetail: (fingerprint: string, params?: { date_start?: string; date_end?: string }) =>
    apiClient.get<SlowQueryFingerprintDetailResponse>(`/sql-analysis/fingerprints/${fingerprint}/detail/`, { params }).then(r => r.data),

  explain: (data: { log_id?: number; instance_id?: number; db_name?: string; sql?: string }) =>
    apiClient.post<SlowQueryExplainResponse>('/sql-analysis/explain/', data).then(r => r.data),

  collect: (params: { instance_id?: number; limit?: number }) =>
    apiClient.post<SlowQueryCollectResponse>('/sql-analysis/collect/', null, { params }).then(r => r.data),

  realtime: (params: { instance_id: number; db_name?: string; limit?: number; min_seconds?: number }) =>
    apiClient.get('/sql-analysis/', { params }).then(r => r.data),
}
