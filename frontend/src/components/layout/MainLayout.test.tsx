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
      platform_name: 'SagittaDB',
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
  it('shows only the logo icon and English product name in the header brand', () => {
    render(
      <MemoryRouter>
        <MainLayout />
      </MemoryRouter>,
    )

    expect(screen.getByText('SagittaDB')).toBeInTheDocument()
    expect(screen.queryByText('矢准数据')).not.toBeInTheDocument()
  })
})
