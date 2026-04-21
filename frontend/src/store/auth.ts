/**
 * 认证状态管理。
 * 使用 Zustand persist + localStorage 持久化 token。
 * storage name: 'sagittadb-auth'
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

export type AuthProvider = 'local' | 'ldap' | 'dingtalk' | 'feishu' | 'wecom' | 'cas'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: UserInfo | null
  isAuthenticated: boolean
  authProvider: AuthProvider | null
  setTokens: (access: string, refresh: string) => void
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

      setTokens: (access, refresh) => {
        set({ accessToken: access, refreshToken: refresh, isAuthenticated: true })
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
      name: 'sagittadb-auth',
      storage: createJSONStorage(() => localStorage),
    }
  )
)
