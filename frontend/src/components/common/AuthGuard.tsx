import { type ReactNode, useEffect } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import { licenseApi } from '@/api/license'

export default function AuthGuard({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    if (!isAuthenticated || location.pathname === '/system/license') return
    let cancelled = false
    licenseApi.status()
      .then((status) => {
        if (!cancelled && ['expired', 'invalid'].includes(status.status)) {
          navigate('/system/license', { replace: true })
        }
      })
      .catch(() => {
        // API 层 License 校验仍是最终权限来源。
      })
    return () => { cancelled = true }
  }, [isAuthenticated, location.pathname, navigate])

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}
