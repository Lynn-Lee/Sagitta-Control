import apiClient from './client'

export type OnboardingStatus = {
  steps: Array<{ key: string; label: string; path: string; completed: boolean; auto_detected: boolean }>
  completed_count: number
  total: number
  is_complete: boolean
}

export type AcceptanceRun = {
  id: number
  status: string
  options: Record<string, unknown>
  report_json: any
  created_by: string
  created_at: string
  completed_at?: string | null
}

export type AlertEvent = {
  id: number
  instance_id: number
  instance_name: string
  db_type: string
  rule_key: string
  severity: string
  status: string
  title: string
  message: string
  metric_value?: number | null
  threshold?: number | null
  first_seen_at?: string | null
  last_seen_at?: string | null
}

export type RetentionPolicy = {
  items: Array<{ key: string; label: string; days: number; default_days: number }>
}

export const commercialApi = {
  onboardingStatus: () => apiClient.get<OnboardingStatus>('/system/onboarding/status').then(r => r.data),
  completeStep: (step: string) => apiClient.post<OnboardingStatus>(`/system/onboarding/steps/${step}/complete`).then(r => r.data),
  createAcceptanceRun: (data: { instance_id?: number | null; db_name?: string }) =>
    apiClient.post<AcceptanceRun>('/system/delivery/acceptance-runs', data).then(r => r.data),
  createDiagnosticBundle: () =>
    apiClient.post<{ id: number; status: string }>('/system/delivery/diagnostic-bundles').then(r => r.data),
  complianceReport: (type: string) => apiClient.get(`/system/compliance/reports/${type}`).then(r => r.data),
  retentionPolicy: () => apiClient.get<RetentionPolicy>('/system/compliance/retention-policy').then(r => r.data),
  updateRetentionPolicy: (values: Record<string, number>) =>
    apiClient.put<RetentionPolicy>('/system/compliance/retention-policy', { values }).then(r => r.data),
  cleanupRetention: (category: string) =>
    apiClient.post('/system/compliance/retention-policy/cleanup', { category }).then(r => r.data),
  engineMatrix: () => apiClient.get('/system/support/engine-matrix').then(r => r.data),
  supportAbout: () => apiClient.get('/system/support/about').then(r => r.data),
  alertEvents: (params?: { status?: string; instance_id?: number; page?: number; page_size?: number }) =>
    apiClient.get<{ total: number; items: AlertEvent[] }>('/monitor/alerts/events', { params }).then(r => r.data),
  ackAlert: (id: number) => apiClient.post(`/monitor/alerts/events/${id}/ack`).then(r => r.data),
  silenceAlert: (id: number, minutes = 60) =>
    apiClient.post(`/monitor/alerts/events/${id}/silence`, { minutes }).then(r => r.data),
  closeAlert: (id: number, reason = '') =>
    apiClient.post(`/monitor/alerts/events/${id}/close`, { reason }).then(r => r.data),
  downloadFile: async (path: string, fallbackName: string) => {
    const response = await apiClient.get(path, { responseType: 'blob' })
    const disposition = response.headers['content-disposition'] || ''
    const match = disposition.match(/filename="?([^"]+)"?/)
    const filename = decodeURIComponent(match?.[1] || fallbackName)
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  },
}
