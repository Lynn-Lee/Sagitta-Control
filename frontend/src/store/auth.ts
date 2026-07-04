/**
 * 认证状态管理。
 * 浏览器登录态由后端 HttpOnly Cookie 承载，localStorage 只持久化用户展示状态。
 * 存储名称：'sagitta-control-auth'
 */
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export interface UserInfo {
  id: number
  username: string
  display_name: string
  email: string
  is_superuser: boolean
  totp_enabled: boolean
  permissions: string[]
  role?: string | null
  role_id?: number | null
  resource_groups: number[]
  user_groups?: number[]
  department?: string
  title?: string
  employee_id?: string
  tenant_id: number
  password_expiring_soon?: boolean
  days_until_password_expiry?: number
}

export type AuthProvider = 'local' | 'ldap' | 'sms' | 'dingtalk' | 'feishu' | 'wecom' | 'cas' | 'oidc'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: UserInfo | null
  isAuthenticated: boolean
  authProvider: AuthProvider | null
  setTokens: (access?: string | null, refresh?: string | null) => void
  setUser: (user: UserInfo) => void
  setAuthProvider: (provider: AuthProvider | null) => void
  logout: () => void
  hasPermission: (perm: string) => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      authProvider: null,

      setTokens: () => {
        set({ accessToken: null, refreshToken: null, isAuthenticated: true })
      },

      setUser: (user) => set({ user }),

      setAuthProvider: (provider) => set({ authProvider: provider }),

      logout: () => set({
        accessToken: null, refreshToken: null,
        user: null, isAuthenticated: false, authProvider: null,
      }),

      hasPermission: (perm: string) => {
        const { user } = get()
        if (!user) return false
        if (user.is_superuser) return true
        return user.permissions.includes(perm)
      },
    }),
    {
      name: 'sagitta-control-auth',
      storage: createJSONStorage(() => localStorage),
      version: 2,
      migrate: (persistedState) => ({
        ...(persistedState as Partial<AuthState>),
        accessToken: null,
        refreshToken: null,
      }),
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
        authProvider: state.authProvider,
      }),
    }
  )
)
