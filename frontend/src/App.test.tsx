import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const authMock = vi.hoisted(() => ({
  user: null as null | {
    is_superuser: boolean
    permissions: string[]
  },
  isAuthenticated: false,
}))

vi.mock('@/store/auth', () => ({
  useAuthStore: (selector?: any) => {
    const state = {
      user: authMock.user,
      isAuthenticated: authMock.isAuthenticated,
      hasPermission: (perm: string) => {
        if (!authMock.user) return false
        if (authMock.user.is_superuser) return true
        return authMock.user.permissions.includes(perm)
      },
    }
    return selector ? selector(state) : state
  },
}))

vi.mock('@/components/layout/MainLayout', async () => {
  const { Outlet } = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { default: () => <Outlet /> }
})

vi.mock('@/api/license', () => ({
  licenseApi: {
    status: vi.fn().mockResolvedValue({ status: 'licensed' }),
  },
}))

vi.mock('@/pages/system/LicensePage', () => ({
  default: () => <div>License Page</div>,
}))

describe('App routes', () => {
  afterEach(() => {
    authMock.user = null
    authMock.isAuthenticated = false
  })

  it('requires system_config_manage for the license page', async () => {
    authMock.isAuthenticated = true
    authMock.user = {
        is_superuser: false,
        permissions: ['menu_system'],
    }

    render(
      <MemoryRouter initialEntries={['/system/license']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByText('无权访问')).toBeInTheDocument()
    expect(screen.getByText('缺少页面权限：system_config_manage')).toBeInTheDocument()
    expect(screen.queryByText('License Page')).not.toBeInTheDocument()
  })

  it('allows superusers to open the license page', async () => {
    authMock.isAuthenticated = true
    authMock.user = {
        is_superuser: true,
        permissions: [],
    }

    render(
      <MemoryRouter initialEntries={['/system/license']}>
        <App />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('License Page')).toBeInTheDocument())
  })
})
