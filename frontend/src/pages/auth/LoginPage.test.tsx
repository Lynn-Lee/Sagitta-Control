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
      platform_name: 'Sagitta Control',
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
  it('uses the Sagitta Control precision governance slogan', async () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    expect(
      await screen.findByText('Sagitta Control · Aim at Data, Govern with Precision'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Sagitta Control v2.2.2 · Database Security Control Platform'),
    ).toBeInTheDocument()
  })

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
