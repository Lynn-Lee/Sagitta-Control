import apiClient from './client'

export interface ApprovalFlowNode {
  id?: number
  order: number
  node_name: string
  approver_type: 'users' | 'manager' | 'any_reviewer'
  approver_ids: number[]
}

export interface ApprovalFlow {
  id: number
  name: string
  description: string
  is_active: boolean
  created_by: string
  created_at: string
  nodes: ApprovalFlowNode[]
}

export interface ApprovalFlowListItem {
  id: number
  name: string
  description: string
  is_active: boolean
  created_by: string
  created_at: string
  node_count: number
}

export interface ApprovalFlowListResponse {
  total: number
  page: number
  page_size: number
  items: ApprovalFlowListItem[]
}

export const approvalFlowApi = {
  list: (params?: { search?: string; page?: number; page_size?: number }) =>
    apiClient.get<ApprovalFlowListResponse>('/approval-flows/', { params }).then(r => r.data),

  get: (id: number) =>
    apiClient.get(`/approval-flows/${id}/`).then(r => r.data.data),

  create: (data: { name: string; description?: string; nodes: ApprovalFlowNode[] }) =>
    apiClient.post('/approval-flows/', data).then(r => r.data.data),

  update: (id: number, data: { name?: string; description?: string; nodes?: ApprovalFlowNode[] }) =>
    apiClient.put(`/approval-flows/${id}/`, data).then(r => r.data.data),

  deactivate: (id: number) =>
    apiClient.delete(`/approval-flows/${id}/`).then(r => r.data),
}
