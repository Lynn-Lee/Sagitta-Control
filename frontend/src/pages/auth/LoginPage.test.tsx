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
  it('uses the concise Sagitta Control precision governance slogan', async () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    const previousLongName = ['矢准', '数据', '库安全', '管控', '平台'].join('')

    expect(await screen.findByText('矢准管控')).toBeInTheDocument()
    expect(await screen.findByText('Aim at Data, Govern with Precision')).toBeInTheDocument()
    expect(screen.queryByText(previousLongName)).not.toBeInTheDocument()
    expect(screen.queryByText('Sagitta Control · Aim at Data, Govern with Precision')).not.toBeInTheDocument()
    expect(
      screen.getByText(
        'Sagitta Control v2.2.2 · Database Security Control Platform · Full Engine Compatibility, End-to-End Observability',
      ),
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
