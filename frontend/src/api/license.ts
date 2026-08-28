import apiClient from './client'

export type LicenseStatus = {
  status: 'trial' | 'licensed' | 'community' | 'expired' | 'invalid' | string
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

export type LicenseInstanceAllocation = {
  status: string
  max_instances: number
  active_total: number
  enabled_total: number
  selectable: boolean
  instances: Array<{
    id: number
    instance_name: string
    db_type: string
    license_suspended: boolean
  }>
}

export type LicenseChallenge = {
  payload: Record<string, unknown>
  signature: string
}

export type LicenseFingerprintPreview = {
  project?: string
  product?: string
  project_code?: string
  project_name?: string
  customer_id: string
  deployment_fingerprint: string
}

export const licenseApi = {
  status: () => apiClient.get<LicenseStatus>('/system/license/status').then(r => r.data),

  deploymentFingerprint: (customerId?: string) =>
    apiClient
      .get<LicenseFingerprintPreview>(
        `/system/license/deployment-fingerprint${customerId ? `?customer_id=${encodeURIComponent(customerId)}` : ''}`,
      )
      .then(r => r.data),

  import: (license: string | Record<string, unknown>) =>
    apiClient.post('/system/license/import', { license }).then(r => r.data),

  sendTrialCode: (data: { contact_email: string; contact_phone?: string }) =>
    apiClient
      .post<{ status: number; msg: string; data: { sent: boolean; expires_in?: number } }>(
        '/system/license/trial/send-code',
        data,
      )
      .then(r => r.data.data),

  requestTrial: (data: {
    company_name: string
    contact_name: string
    contact_email: string
    contact_phone?: string
    verification_code: string
  }) => apiClient.post('/system/license/trial', data).then(r => r.data),

  instanceAllocation: () =>
    apiClient.get<LicenseInstanceAllocation>('/system/license/instance-allocation').then(r => r.data),

  updateInstanceAllocation: (instanceIds: number[]) =>
    apiClient
      .put<{ status: number; msg: string; data: LicenseInstanceAllocation }>(
        '/system/license/instance-allocation',
        { instance_ids: instanceIds },
      )
      .then(r => r.data.data),

  activate: (data: { activation_code: string; customer_id?: string }) =>
    apiClient.post('/system/license/activate', data).then(r => r.data),

  refresh: () => apiClient.post('/system/license/refresh').then(r => r.data),

  challenge: (data: { customer_id?: string }) =>
    apiClient.post<{ status: number; msg: string; data: LicenseChallenge }>('/system/license/challenge', data).then(r => r.data.data),
}
