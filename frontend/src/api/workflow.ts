import apiClient from './client'

export interface WorkflowItem {
  id: number
  workflow_name: string
  group_name: string
  instance_id: number
  instance_name: string
  db_name: string
  engineer: string
  engineer_display: string
  status: number
  status_desc: string
  created_at: string
  current_node_name?: string
  audit_chain_text?: string
}

export interface WorkflowCreateResponse {
  status: number
  msg: string
  data: {
    id: number
    workflow_name: string
  }
}

export interface WorkflowCheckResult {
  id: number
  sql: string
  errlevel: number
  msg: string
}

export interface WorkflowCheckResponse {
  status: number
  data: WorkflowCheckResult[]
}

export const workflowApi = {
  list: (params?: {
    view?: 'mine' | 'audit' | 'execute' | 'scope'
    status?: number
    instance_id?: number
    search?: string
    engineer?: string
    db_name?: string
    date_start?: string
    date_end?: string
    page?: number
    page_size?: number
  }) => apiClient.get('/workflow/', { params }).then(r => r.data),

  create: (data: {
    workflow_name: string; group_id?: number; flow_id?: number; instance_id: number
    db_name: string; sql_content: string; syntax_type?: number; is_backup?: boolean
  }) => apiClient.post<WorkflowCreateResponse>('/workflow/', data).then(r => r.data),

  get: (id: number) =>
    apiClient.get(`/workflow/${id}/`).then(r => r.data),

  audit: (id: number, data: { action: 'pass' | 'reject'; remark?: string }) =>
    apiClient.post(`/workflow/${id}/audit/`, data).then(r => r.data),

  execute: (id: number, data?: { mode?: string }) =>
    apiClient.post(`/workflow/${id}/execute/`, data || {}).then(r => r.data),

  cancel: (id: number) =>
    apiClient.post(`/workflow/${id}/cancel/`).then(r => r.data),

  getStatus: (id: number) =>
    apiClient.get(`/workflow/${id}/status/`).then(r => r.data),

  check: (data: { instance_id: number; db_name: string; sql_content: string }) =>
    apiClient.post<WorkflowCheckResponse>('/workflow/check/', data).then(r => r.data),

  pending: (params?: { page?: number; page_size?: number }) =>
    apiClient.get('/workflow/pending/', { params }).then(r => r.data),
}
