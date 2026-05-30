import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/store/auth'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

const AUTH_SUBMIT_PATHS = new Set([
  '/auth/login/',
  '/auth/ldap/',
  '/auth/sms/login/',
  '/auth/2fa/login/verify/',
  '/auth/password/change-required/',
])

const normalizeApiPath = (url?: string) => {
  if (!url) return ''
  try {
    const pathname = new URL(url, window.location.origin).pathname
    return pathname.replace(/^\/api\/v1/, '') || '/'
  } catch {
    return url.replace(/^\/api\/v1/, '')
  }
}

const isAuthSubmitRequest = (config?: InternalAxiosRequestConfig) => (
  AUTH_SUBMIT_PATHS.has(normalizeApiPath(config?.url))
)

// ─── 请求拦截器：自动注入 JWT ────────────────────────────────
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = useAuthStore.getState().accessToken
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// ─── 响应拦截器：Token 自动刷新 ──────────────────────────────
let isRefreshing = false
let pendingQueue: Array<{
  resolve: (token: string) => void
  reject: (error: unknown) => void
}> = []

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean
    }

    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !isAuthSubmitRequest(originalRequest)
    ) {
      const { refreshToken, setTokens, logout } = useAuthStore.getState()

      if (!refreshToken) {
        logout()
        window.location.href = '/login'
        return Promise.reject(error)
      }

      if (isRefreshing) {
        // 等待刷新完成后重发请求
        return new Promise((resolve, reject) => {
          pendingQueue.push({ resolve, reject })
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`
          return apiClient(originalRequest)
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      try {
        const response = await axios.post(`${BASE_URL}/api/v1/auth/token/refresh/`, {
          refresh_token: refreshToken,
        })
        const { access_token, refresh_token } = response.data
        setTokens(access_token, refresh_token)

        // 刷新成功，重发所有等待的请求
        pendingQueue.forEach(({ resolve }) => resolve(access_token))
        pendingQueue = []

        originalRequest.headers.Authorization = `Bearer ${access_token}`
        return apiClient(originalRequest)
      } catch (refreshError) {
        pendingQueue.forEach(({ reject }) => reject(refreshError))
        pendingQueue = []
        logout()
        window.location.href = '/login'
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    if (
      error.response?.status === 403 &&
      (error.response.data as any)?.code === 'LICENSE_REQUIRED' &&
      window.location.pathname !== '/system/license'
    ) {
      window.location.href = '/system/license'
    }

    return Promise.reject(error)
  }
)

export default apiClient
