import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import LoginPage from './LoginPage'

vi.mock('@/store/auth', () => ({
  useAuthStore: () => ({
    setTokens: vi.fn(),
    setUser: vi.fn(),
    setAuthProvider: vi.fn(),
    isAuthenticated: false,
    user: null,
  }),
}))

vi.mock('@/hooks/useBranding', () => ({
  useBranding: () => ({
    branding: {
      platform_name: 'SagittaDB',
      platform_logo_url: '',
    },
  }),
}))

vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn(),
  },
}))

vi.mock('@/api/auth', () => ({
  authApi: {
    ldapLogin: vi.fn(),
    sendSmsCode: vi.fn(),
    smsLogin: vi.fn(),
    forceChangePassword: vi.fn(),
    verifyLogin2fa: vi.fn(),
  },
}))

describe('LoginPage', () => {
  it('links the footer author name to the GitHub profile', async () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    const profileLink = await screen.findByRole('link', { name: 'Lynn-Lee' })

    expect(profileLink).toHaveAttribute('href', 'https://github.com/Lynn-Lee')
    expect(profileLink).toHaveAttribute('target', '_blank')
    expect(profileLink).toHaveAttribute('rel', 'noreferrer')
  })
})
