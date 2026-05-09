import apiClient from './client'

export type LicenseStatus = {
  status: 'trial' | 'licensed' | 'expired' | 'invalid' | string
  reason: string
  source: string
  is_trial: boolean
  project_code?: string
  project_name?: string
  license_id: string
  customer_id: string
  activation_customer_id?: string
  configured_customer_id?: string
  company_name: string
  edition: string
  features: string[]
  limits: Record<string, number | string>
  activation_id?: string
  remote_status?: string
  deployment_fingerprint?: string
  activation_deployment_fingerprint?: string
  last_online_check_at?: string | null
  issued_at?: string | null
  not_before?: string | null
  expires_at?: string | null
  days_remaining?: number | null
  needs_renewal?: boolean
  warning_level?: 'warning' | 'critical' | string
}

export type LicenseChallenge = {
  payload: Record<string, unknown>
  signature: string
}

export const licenseApi = {
  status: () => apiClient.get<LicenseStatus>('/system/license/status').then(r => r.data),

  import: (license: string | Record<string, unknown>) =>
    apiClient.post('/system/license/import', { license }).then(r => r.data),

  activate: (data: { activation_code: string; customer_id?: string }) =>
    apiClient.post('/system/license/activate', data).then(r => r.data),

  refresh: () => apiClient.post('/system/license/refresh').then(r => r.data),

  challenge: (data: { customer_id?: string }) =>
    apiClient.post<{ status: number; msg: string; data: LicenseChallenge }>('/system/license/challenge', data).then(r => r.data.data),
}
