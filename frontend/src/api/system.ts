import apiClient from './client'

// ── 用户 ──────────────────────────────────────────────────────
export const userApi = {
  list: (params?: {
    page?: number
    page_size?: number
    search?: string
    is_active?: boolean
    role_ids?: number[]
    user_group_ids?: number[]
    departments?: string[]
    titles?: string[]
    statuses?: boolean[]
  }) =>
    apiClient.get('/system/users/', {
      params,
      paramsSerializer: { indexes: null },
    }).then(r => r.data),

  export: (params?: {
    export_format?: 'xlsx' | 'csv'
    search?: string
    is_active?: boolean
    role_ids?: number[]
    user_group_ids?: number[]
    departments?: string[]
    titles?: string[]
    statuses?: boolean[]
    user_ids?: number[]
  }) =>
    apiClient.get('/system/users/export/', {
      params,
      responseType: 'blob',
      paramsSerializer: { indexes: null },
    }).then(r => ({
      blob: r.data,
      contentDisposition: r.headers['content-disposition'] as string | undefined,
    })),

  downloadTemplate: (params?: { export_format?: 'xlsx' | 'csv' }) =>
    apiClient.get('/system/users/import-template/', { params, responseType: 'blob' }).then(r => ({
      blob: r.data,
      contentDisposition: r.headers['content-disposition'] as string | undefined,
    })),

  get: (id: number) =>
    apiClient.get(`/system/users/${id}/`).then(r => r.data),

  create: (data: {
    username: string; password: string; display_name?: string
    email?: string; phone?: string; is_superuser?: boolean
    role_id?: number; manager_id?: number
    employee_id?: string; department?: string; title?: string
    user_group_ids?: number[]
  }) => apiClient.post('/system/users/', data).then(r => r.data),

  update: (id: number, data: any) =>
    apiClient.put(`/system/users/${id}/`, data).then(r => r.data),

  delete: (id: number) =>
    apiClient.delete(`/system/users/${id}/`).then(r => r.data),

  import: (file: File, defaultPassword: string) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('default_password', defaultPassword)
    return apiClient.post('/system/users/import/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 5 * 60 * 1000,
    }).then(r => r.data)
  },

  grantPermissions: (id: number, permission_codes: string[]) =>
    apiClient.post(`/system/users/${id}/permissions/grant/`, { permission_codes }).then(r => r.data),

  revokePermissions: (id: number, permission_codes: string[]) =>
    apiClient.post(`/system/users/${id}/permissions/revoke/`, { permission_codes }).then(r => r.data),
}

// ── 资源组 ────────────────────────────────────────────────────
export const resourceGroupApi = {
  list: (params?: { page?: number; page_size?: number; search?: string }) =>
    apiClient.get('/system/resource-groups/', { params }).then(r => r.data),

  create: (data: {
    group_name: string
    group_name_cn?: string
    instance_ids?: number[]
    user_group_ids?: number[]
    is_active?: boolean
  }) =>
    apiClient.post('/system/resource-groups/', data).then(r => r.data),

  update: (id: number, data: any) =>
    apiClient.put(`/system/resource-groups/${id}/`, data).then(r => r.data),

  delete: (id: number) =>
    apiClient.delete(`/system/resource-groups/${id}/`).then(r => r.data),

  listMembers: (id: number) =>
    apiClient.get(`/system/resource-groups/${id}/members/`).then(r => r.data),

  updateMembers: (id: number, userIds: number[]) =>
    apiClient.post(`/system/resource-groups/${id}/members/`, { user_ids: userIds }).then(r => r.data),

  listUserGroups: (id: number) =>
    apiClient.get(`/system/resource-groups/${id}/user-groups/`).then(r => r.data),

  updateUserGroups: (id: number, userGroupIds: number[]) =>
    apiClient.put(`/system/resource-groups/${id}/user-groups/`, { user_group_ids: userGroupIds }).then(r => r.data),
}

// ── 权限列表 ──────────────────────────────────────────────────
export const permissionApi = {
  list: () => apiClient.get('/system/permissions/').then(r => r.data),
}

// ── 角色 ──────────────────────────────────────────────────────
export const roleApi = {
  list: (params?: { page?: number; page_size?: number; is_active?: boolean }) =>
    apiClient.get('/system/roles/', { params }).then(r => r.data),

  get: (id: number) =>
    apiClient.get(`/system/roles/${id}/`).then(r => r.data),

  create: (data: {
    name: string; name_cn?: string; description?: string; permission_codes?: string[]
  }) => apiClient.post('/system/roles/', data).then(r => r.data),

  update: (id: number, data: any) =>
    apiClient.put(`/system/roles/${id}/`, data).then(r => r.data),

  delete: (id: number) =>
    apiClient.delete(`/system/roles/${id}/`).then(r => r.data),
}

// ── 用户组 ────────────────────────────────────────────────────
export const userGroupApi = {
  list: (params?: {
    page?: number
    page_size?: number
    is_active?: boolean
    parent_id?: number
    search?: string
    leader_ids?: number[]
    parent_ids?: number[]
    resource_group_ids?: number[]
    statuses?: boolean[]
  }) =>
    apiClient.get('/system/user-groups/', {
      params,
      paramsSerializer: { indexes: null },
    }).then(r => r.data),

  export: (params?: {
    export_format?: 'xlsx' | 'csv'
    search?: string
    is_active?: boolean
    parent_id?: number
    group_ids?: number[]
    leader_ids?: number[]
    parent_ids?: number[]
    resource_group_ids?: number[]
    statuses?: boolean[]
  }) =>
    apiClient.get('/system/user-groups/export/', {
      params,
      responseType: 'blob',
      paramsSerializer: { indexes: null },
    }).then(r => ({
      blob: r.data,
      contentDisposition: r.headers['content-disposition'] as string | undefined,
    })),

  downloadTemplate: (params?: { export_format?: 'xlsx' | 'csv' }) =>
    apiClient.get('/system/user-groups/import-template/', { params, responseType: 'blob' }).then(r => ({
      blob: r.data,
      contentDisposition: r.headers['content-disposition'] as string | undefined,
    })),

  get: (id: number) =>
    apiClient.get(`/system/user-groups/${id}/`).then(r => r.data),

  create: (data: {
    name: string; name_cn?: string; description?: string
    leader_id?: number; parent_id?: number
    resource_group_ids?: number[]; member_ids?: number[]
  }) => apiClient.post('/system/user-groups/', data).then(r => r.data),

  update: (id: number, data: any) =>
    apiClient.put(`/system/user-groups/${id}/`, data).then(r => r.data),

  delete: (id: number) =>
    apiClient.delete(`/system/user-groups/${id}/`).then(r => r.data),

  import: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return apiClient.post('/system/user-groups/import/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
}

// ── 系统初始化 ────────────────────────────────────────────────
export const systemApi = {
  init: () => apiClient.post('/system/init/').then(r => r.data),
}
