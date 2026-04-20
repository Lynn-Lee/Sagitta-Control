import apiClient from './client'

export interface LoginPayload {
  username: string
  password: string
}

export interface TokenResp {
  access_token?: string | null
  refresh_token?: string | null
  token_type: string
  password_change_required?: boolean
  password_change_token?: string | null
  password_change_reasons?: string[]
  requires_2fa?: boolean
  two_fa_token?: string | null
}

export const authApi = {
  login: (data: LoginPayload) =>
    apiClient.post<TokenResp>('/auth/login/', data).then(r => r.data),

  refresh: (refresh_token: string) =>
    apiClient.post<TokenResp>('/auth/token/refresh/', { refresh_token }).then(r => r.data),

  logout: () =>
    apiClient.post('/auth/logout/').then(r => r.data),

  me: () =>
    apiClient.get('/auth/me/').then(r => r.data),

  ldapLogin: (username: string, password: string) =>
    apiClient.post<TokenResp>('/auth/ldap/', { username, password }).then(r => r.data),

  changePassword: (old_password: string, new_password: string) =>
    apiClient.post('/auth/password/change/', { old_password, new_password }).then(r => r.data),

  forceChangePassword: (password_change_token: string, new_password: string) =>
    apiClient.post('/auth/password/change-required/', {
      password_change_token,
      new_password,
    }).then(r => r.data),

  setup2fa: () =>
    apiClient.post('/auth/2fa/setup/').then(r => r.data),

  verify2fa: (totp_code: string) =>
    apiClient.post('/auth/2fa/verify/', { totp_code }).then(r => r.data),

  verifyLogin2fa: (two_fa_token: string, totp_code: string) =>
    apiClient.post<TokenResp>('/auth/2fa/login/verify/', { two_fa_token, totp_code }).then(r => r.data),

  disable2fa: (totp_code: string) =>
    apiClient.post('/auth/2fa/disable/', { totp_code }).then(r => r.data),
}
