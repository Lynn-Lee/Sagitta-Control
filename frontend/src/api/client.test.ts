import type { AxiosAdapter, AxiosResponse } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import apiClient from './client'

const authMock = vi.hoisted(() => ({
  state: {
    accessToken: null as string | null,
    refreshToken: null as string | null,
    user: null,
    isAuthenticated: false,
    authProvider: null,
    setTokens: vi.fn(),
    logout: vi.fn(),
  },
}))

vi.mock('@/store/auth', () => ({
  useAuthStore: {
    getState: () => authMock.state,
  },
}))

const captureAdapter: AxiosAdapter = async (config): Promise<AxiosResponse> => ({
  data: { ok: true },
  status: 200,
  statusText: 'OK',
  headers: {},
  config,
})

const readHeader = (headers: any, name: string) => headers?.[name] ?? headers?.get?.(name)

describe('apiClient auth transport', () => {
  beforeEach(() => {
    authMock.state.accessToken = null
    authMock.state.refreshToken = null
    authMock.state.user = null
    authMock.state.isAuthenticated = false
    authMock.state.authProvider = null
    authMock.state.setTokens.mockClear()
    authMock.state.logout.mockClear()
    document.cookie = 'csrf_token=; Max-Age=0; path=/'
  })

  it('sends requests with credentials for HttpOnly auth cookies', () => {
    expect(apiClient.defaults.withCredentials).toBe(true)
  })

  it('adds X-CSRF-Token from the readable csrf cookie for unsafe requests', async () => {
    document.cookie = 'csrf_token=csrf-value; path=/'

    const response = await apiClient.post('/auth/logout/', {}, { adapter: captureAdapter })

    expect(readHeader(response.config.headers, 'X-CSRF-Token')).toBe('csrf-value')
  })

  it('does not mirror persisted tokens into Authorization headers', async () => {
    authMock.state.accessToken = 'old-access-token'
    authMock.state.refreshToken = 'old-refresh-token'

    const response = await apiClient.get('/auth/me/', { adapter: captureAdapter })

    expect(readHeader(response.config.headers, 'Authorization')).toBeUndefined()
  })
})
