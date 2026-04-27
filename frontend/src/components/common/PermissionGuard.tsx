import { type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { Result } from 'antd'
import { useAuthStore } from '@/store/auth'

interface PermissionGuardProps {
  permission?: string
  anyPermissions?: string[]
  children: ReactNode
  fallbackTo?: string
}

export default function PermissionGuard({
  permission,
  anyPermissions,
  children,
  fallbackTo = '/dashboard',
}: PermissionGuardProps) {
  const { isAuthenticated, hasPermission } = useAuthStore()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  const allowed = permission ? hasPermission(permission) : !!anyPermissions?.some((perm) => hasPermission(perm))

  if (!allowed) {
    return (
      <Result
        status="403"
        title="无权访问"
        subTitle={`缺少页面权限：${permission || anyPermissions?.join(' / ') || '-'}`}
      />
    )
  }

  return <>{children}</>
}
