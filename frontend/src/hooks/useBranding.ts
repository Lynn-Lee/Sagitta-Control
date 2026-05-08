import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { brandingApi, DEFAULT_BRANDING } from '@/api/branding'

export function useBranding() {
  const query = useQuery({
    queryKey: ['public-branding'],
    queryFn: brandingApi.get,
    staleTime: 5 * 60_000,
  })

  const branding = {
    ...DEFAULT_BRANDING,
    ...(query.data || {}),
  }

  useEffect(() => {
    document.title = branding.platform_name === DEFAULT_BRANDING.platform_name
      ? `${branding.platform_name} - 矢准数据`
      : branding.platform_name
  }, [branding.platform_name])

  useEffect(() => {
    const favicon = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
    if (favicon) {
      favicon.href = branding.platform_logo_url || '/favicon.svg'
    }
  }, [branding.platform_logo_url])

  return {
    ...query,
    branding,
  }
}
