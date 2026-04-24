import apiClient from './client'

export interface SessionItem {
  instance_id?: number | null
  instance_name: string
  db_type: string
  session_id: string
  serial: string
  username: string
  host: string
  program: string
  db_name: string
  command: string
  state: string
  time_seconds: number
  sql_id: string
  sql_text: string
  event: string
  blocking_session: string
  collected_at?: string | null
  source: string
  collect_error?: string
  raw?: Record<string, unknown>
}

export interface SessionListResponse {
  total: number
  items: SessionItem[]
  column_list: string[]
  rows: unknown[][]
}

export interface SessionHistoryResponse {
  total: number
  items: SessionItem[]
}

export const diagnosticApi = {
  processlist: (params: { instance_id: number; command_type?: string }) =>
    apiClient.get<SessionListResponse>('/diagnostic/processlist/', { params }).then(r => r.data),

  kill: (data: { instance_id: number; session_id: string; serial?: string }) =>
    apiClient.post('/diagnostic/kill/', data).then(r => r.data),

  history: (params: {
    instance_id?: number
    db_type?: string
    username?: string
    db_name?: string
    sql_keyword?: string
    date_start?: string
    date_end?: string
    min_seconds?: number
    page?: number
    page_size?: number
  }) =>
    apiClient.get<SessionHistoryResponse>('/diagnostic/sessions/history/', { params }).then(r => r.data),

  oracleAsh: (params: {
    instance_id: number
    source: 'ash' | 'awr'
    date_start?: string
    date_end?: string
    sql_keyword?: string
    page?: number
    page_size?: number
  }) =>
    apiClient.get<SessionHistoryResponse>('/diagnostic/sessions/oracle-ash/', { params }).then(r => r.data),
}
