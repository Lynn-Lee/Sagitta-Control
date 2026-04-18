import apiClient from './client'

export type WorkflowTemplateVisibility = 'public' | 'private'

export interface WorkflowTemplateItem {
  id: number
  template_name: string
  category: string
  description: string
  scene_desc: string
  risk_hint: string
  rollback_hint: string
  instance_id: number | null
  db_name: string
  flow_id: number | null
  flow_name: string
  sql_content: string
  syntax_type: number
  is_active: boolean
  visibility: WorkflowTemplateVisibility
  created_by: string
  created_by_id: number
  use_count: number
  created_at: string
  updated_at: string
}

export interface WorkflowTemplateCategory {
  value: string
  label: string
}

export interface WorkflowTemplateListResponse {
  total: number
  page: number
  page_size: number
  items: WorkflowTemplateItem[]
}

export interface WorkflowTemplateCategoriesResponse {
  items: WorkflowTemplateCategory[]
}

export interface WorkflowTemplateUseResponse {
  status: number
  data: WorkflowTemplateItem
}

export interface WorkflowTemplatePayload {
  template_name: string
  category: string
  description?: string
  scene_desc?: string
  risk_hint?: string
  rollback_hint?: string
  instance_id?: number | null
  db_name?: string
  flow_id?: number | null
  sql_content: string
  syntax_type?: number
  is_active?: boolean
  visibility?: WorkflowTemplateVisibility
}

export const workflowTemplateApi = {
  list: (params?: {
    search?: string
    category?: string
    visibility?: WorkflowTemplateVisibility
    is_active?: boolean
    page?: number
    page_size?: number
  }) => apiClient.get<WorkflowTemplateListResponse>('/workflow-templates/', { params }).then((r) => r.data),

  categories: () =>
    apiClient.get<WorkflowTemplateCategoriesResponse>('/workflow-templates/categories/').then((r) => r.data),

  get: (id: number) =>
    apiClient.get<{ data: WorkflowTemplateItem }>(`/workflow-templates/${id}/`).then((r) => r.data.data),

  create: (data: WorkflowTemplatePayload) =>
    apiClient.post('/workflow-templates/', data).then((r) => r.data),

  update: (id: number, data: Partial<WorkflowTemplatePayload>) =>
    apiClient.put(`/workflow-templates/${id}/`, data).then((r) => r.data),

  remove: (id: number) =>
    apiClient.delete(`/workflow-templates/${id}/`).then((r) => r.data),

  use: (id: number) =>
    apiClient.post<WorkflowTemplateUseResponse>(`/workflow-templates/${id}/use/`).then((r) => r.data),

  clone: (id: number) =>
    apiClient.post(`/workflow-templates/${id}/clone/`).then((r) => r.data),
}
