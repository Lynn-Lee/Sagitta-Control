import apiClient from '@/api/client'

export type Branding = {
  platform_name: string
  platform_logo_url: string
}

export const BRANDING_STORAGE_KEY = 'sagittadb:branding'
export const FALLBACK_DOCUMENT_TITLE = '数据管控平台'

export const DEFAULT_BRANDING: Branding = {
  platform_name: 'SagittaDB',
  platform_logo_url: '',
}

export function getBrandingTitle(branding: Branding) {
  return branding.platform_name || FALLBACK_DOCUMENT_TITLE
}

export function applyBrandingMeta(branding: Branding) {
  document.title = getBrandingTitle(branding)

  const favicon = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
  if (favicon) {
    favicon.href = branding.platform_logo_url || '/favicon.svg'
  }
}

export const brandingApi = {
  get: () => apiClient.get<Branding>('/system/branding/').then(r => r.data),
}
