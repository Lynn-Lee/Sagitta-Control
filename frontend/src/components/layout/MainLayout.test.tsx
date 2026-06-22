import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import MainLayout from './MainLayout'

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: { count: 0, items: [] } }),
  useMutation: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
  }),
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
    removeQueries: vi.fn(),
  }),
}))

vi.mock('@/store/auth', () => ({
  useAuthStore: (selector?: any) => {
    const state = {
      user: {
        id: 1,
        username: 'admin',
        display_name: '超级管理员',
        is_superuser: true,
        permissions: [],
      },
      authProvider: 'local',
      logout: vi.fn(),
      hasPermission: () => true,
    }
    return selector ? selector(state) : state
  },
}))

vi.mock('@/hooks/useBranding', () => ({
  useBranding: () => ({
    branding: {
      platform_name: 'Sagitta Control',
      platform_logo_url: '',
    },
  }),
}))

vi.mock('@/api/auth', () => ({
  authApi: {
    logout: vi.fn(),
  },
}))

vi.mock('@/components/auth/ChangePasswordModal', () => ({
  default: () => null,
}))

vi.mock('@/components/auth/ProfileSettingsModal', () => ({
  default: () => null,
}))

describe('MainLayout', () => {
  it('shows only the logo icon and Sagitta Control product name in the header brand', () => {
    render(
      <MemoryRouter>
        <MainLayout />
      </MemoryRouter>,
    )

    expect(screen.getByText('Sagitta Control')).toBeInTheDocument()
    expect(screen.queryByText('矢准数据库安全管控平台')).not.toBeInTheDocument()
    expect(screen.queryByText('矢 准 管 控')).not.toBeInTheDocument()
    expect(screen.getByTestId('header-brand')).toHaveAttribute(
      'style',
      expect.stringContaining('display: inline-flex'),
    )
    expect(screen.getByTestId('header-brand')).toHaveAttribute(
      'style',
      expect.stringContaining('align-items: center'),
    )
    expect(screen.getByTestId('header-left-actions')).toHaveAttribute(
      'style',
      expect.stringContaining('height: 100%'),
    )
    expect(screen.getByTestId('header-left-actions')).toHaveAttribute(
      'style',
      expect.stringContaining('align-items: center'),
    )
    expect(screen.getByTestId('header-right-actions')).toHaveAttribute(
      'style',
      expect.stringContaining('height: 100%'),
    )
    expect(screen.getByTestId('header-right-actions')).toHaveAttribute(
      'style',
      expect.stringContaining('align-items: center'),
    )
  })
})
