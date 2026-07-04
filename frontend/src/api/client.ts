import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/store/auth'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

const CSRF_COOKIE_NAME = 'csrf_token'
const CSRF_HEADER_NAME = 'X-CSRF-Token'
const UNSAFE_METHODS = new Set(['post', 'put', 'patch', 'delete'])

const AUTH_SUBMIT_PATHS = new Set([
  '/auth/login/',
  '/auth/login/form/',
  '/auth/ldap/',
  '/auth/sms/login/',
  '/auth/2fa/login/verify/',
  '/auth/password/change-required/',
  '/auth/oauth/exchange/',
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

const readCookie = (name: string) => {
  if (typeof document === 'undefined') return ''
  const prefix = `${name}=`
  return document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length) || ''
}

const csrfHeaders = () => {
  const token = readCookie(CSRF_COOKIE_NAME)
  return token ? { [CSRF_HEADER_NAME]: token } : {}
}

const attachCsrfHeader = (config: InternalAxiosRequestConfig) => {
  if (!UNSAFE_METHODS.has((config.method || 'get').toLowerCase())) {
    return
  }
  const token = readCookie(CSRF_COOKIE_NAME)
  if (token) {
    config.headers[CSRF_HEADER_NAME] = token
  }
}

// ─── 请求拦截器：Cookie 登录态下为写操作补充 CSRF Header ───────
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    attachCsrfHeader(config)
    return config
  },
  (error) => Promise.reject(error)
)

// ─── 响应拦截器：Token 自动刷新 ──────────────────────────────
let isRefreshing = false
let pendingQueue: Array<{
  resolve: () => void
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
      const { setTokens, logout } = useAuthStore.getState()

      if (isRefreshing) {
        // 等待刷新完成后重发请求
        return new Promise<void>((resolve, reject) => {
          pendingQueue.push({ resolve, reject })
        }).then(() => {
          return apiClient(originalRequest)
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      try {
        await axios.post(`${BASE_URL}/api/v1/auth/token/refresh/`, {}, {
          withCredentials: true,
          headers: csrfHeaders(),
        })
        setTokens()

        // 刷新成功，重发所有等待的请求
        pendingQueue.forEach(({ resolve }) => resolve())
        pendingQueue = []

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
