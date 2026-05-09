import { useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  applyBrandingMeta,
  brandingApi,
  BRANDING_STORAGE_KEY,
  DEFAULT_BRANDING,
} from '@/api/branding'

function getPreloadedBranding() {
  if (typeof window === 'undefined') return undefined
  return window.__SAGITTA_BRANDING__
}

export function useBranding() {
  const query = useQuery({
    queryKey: ['public-branding'],
    queryFn: () => window.__SAGITTA_BRANDING_PROMISE__ || brandingApi.get(),
    initialData: getPreloadedBranding,
    staleTime: 5 * 60_000,
  })

  const branding = useMemo(
    () => ({
      ...DEFAULT_BRANDING,
      ...(query.data || {}),
    }),
    [query.data],
  )

  useEffect(() => {
    applyBrandingMeta(branding)
    try {
      window.localStorage.setItem(BRANDING_STORAGE_KEY, JSON.stringify(branding))
    } catch {
      // localStorage 不可用时忽略；运行时品牌仍正常应用。
    }
  }, [branding])

  return {
    ...query,
    branding,
  }
}
