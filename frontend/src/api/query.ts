import apiClient from './client'

export interface QueryResult {
  column_list: string[]
  rows: any[][]
  affected_rows: number
  cost_time_ms: number
  is_masked: boolean
  error: string
}

export interface QueryAccessExplanation {
  instance_id: number
  db_name: string
  allowed: boolean
  reason: string
  layer: 'identity' | 'resource_scope' | 'data_scope'
}

export const queryApi = {
  execute: (data: {
    instance_id: number
    db_name: string
    sql: string
    limit_num?: number
  }) => apiClient.post<QueryResult>('/query/', data).then(r => r.data),

  explainAccess: (data: {
    instance_id: number
    db_name: string
    sql: string
    limit_num?: number
  }) => apiClient.post<QueryAccessExplanation>('/query/access-check/', data).then(r => r.data),

  exportResult: async (
    data: {
      instance_id: number
      db_name: string
      sql: string
      limit_num?: number
    },
    exportFormat: 'xlsx' | 'csv',
  ) => {
    const response = await apiClient.post('/query/export/', data, {
      params: { export_format: exportFormat },
      responseType: 'blob',
    })
    return {
      blob: response.data as Blob,
      contentDisposition: response.headers['content-disposition'] as string | undefined,
    }
  },

  getLogs: (params?: {
    instance_id?: number
    page?: number
    page_size?: number
  }) => apiClient.get('/query/logs/', { params }).then(r => r.data),

  toggleFavorite: (log_id: number) =>
    apiClient.post(`/query/logs/${log_id}/favorite/`).then(r => r.data),

  // 查询权限
  listPrivileges: (instance_id?: number) =>
    apiClient.get('/query/privileges/', { params: { instance_id } }).then(r => r.data),

  listManagePrivileges: (params?: {
    page?: number
    page_size?: number
    instance_id?: number
    user_id?: number
    db_name?: string
    status?: 'active' | 'revoked'
  }) => apiClient.get('/query/privileges/manage/', { params }).then(r => r.data),

  applyPrivilege: (data: {
    title: string
    instance_id: number
    group_id?: number
    flow_id?: number
    db_name: string
    table_name?: string
    scope_type?: 'database' | 'table'
    valid_date: string
    limit_num?: number
    priv_type?: number
    apply_reason?: string
  }) => apiClient.post('/query/privileges/apply/', data).then(r => r.data),

  listApplies: (params?: { status?: number; page?: number; page_size?: number }) =>
    apiClient.get('/query/privileges/applies/', { params }).then(r => r.data),

  listAuditRecords: (params?: { status?: number; page?: number; page_size?: number }) =>
    apiClient.get('/query/privileges/audit-records/', { params }).then(r => r.data),

  auditApply: (apply_id: number, data: { action: 'pass' | 'reject'; remark?: string; valid_date?: string }) =>
    apiClient.post('/query/privileges/audit/', data, { params: { apply_id } }).then(r => r.data),

  revokePrivilege: (priv_id: number, data?: { reason?: string }) =>
    apiClient.delete(`/query/privileges/${priv_id}/`, { data: data || {} }).then(r => r.data),
}
