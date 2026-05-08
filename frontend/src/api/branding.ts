import apiClient from '@/api/client'

export type Branding = {
  platform_name: string
  platform_logo_url: string
}

export const DEFAULT_BRANDING: Branding = {
  platform_name: 'SagittaDB',
  platform_logo_url: '',
}

export const brandingApi = {
  get: () => apiClient.get<Branding>('/system/branding/').then(r => r.data),
}
