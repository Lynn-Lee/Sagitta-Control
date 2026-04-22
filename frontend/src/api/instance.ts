import apiClient from './client'

export interface InstanceItem {
  id: number
  instance_name: string
  db_type: string
  host: string
  port: number
  db_name: string
  is_active: boolean
  remark: string
}

export interface InstanceDatabase {
  id: number
  db_name: string
  remark: string
  is_active: boolean
  sync_at: string | null
  db_name_label: string
}

export interface InstanceListResponse {
  total: number
  page: number
  page_size: number
  items: InstanceItem[]
}

export const instanceApi = {
  list: (params?: { search?: string; db_type?: string; page?: number; page_size?: number }) =>
    apiClient.get<InstanceListResponse>('/instances/', { params }).then(r => r.data),

  get: (id: number) =>
    apiClient.get(`/instances/${id}/`).then(r => r.data),

  create: (data: any) =>
    apiClient.post('/instances/', data).then(r => r.data),

  update: (id: number, data: any) =>
    apiClient.put(`/instances/${id}/`, data).then(r => r.data),

  delete: (id: number) =>
    apiClient.delete(`/instances/${id}/`).then(r => r.data),

  testConnection: (id: number) =>
    apiClient.post(`/instances/${id}/test/`).then(r => r.data),

  // 数据字典数据库列表：基于已注册库并带启用状态
  getDatabases: (id: number) =>
    apiClient.get<{ databases: InstanceDatabase[] }>(`/instances/${id}/databases/`).then(r => r.data),

  // ── 数据库注册管理（Pack C2）──────────────────────────────

  listRegisteredDbs: (instanceId: number, includeInactive = false) =>
    apiClient.get(`/instances/${instanceId}/db-list/`, {
      params: { include_inactive: includeInactive }
    }).then(r => r.data),

  addDb: (instanceId: number, dbName: string, remark = '') =>
    apiClient.post(`/instances/${instanceId}/db-list/`, {
      db_name: dbName, remark
    }).then(r => r.data),

  updateDb: (instanceId: number, idbId: number, data: { remark?: string; is_active?: boolean }) =>
    apiClient.put(`/instances/${instanceId}/db-list/${idbId}/`, data).then(r => r.data),

  deleteDb: (instanceId: number, idbId: number) =>
    apiClient.delete(`/instances/${instanceId}/db-list/${idbId}/`).then(r => r.data),

  syncDbs: (instanceId: number) =>
    apiClient.post(`/instances/${instanceId}/db-list/sync/`).then(r => r.data),
}
