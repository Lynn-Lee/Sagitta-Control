/**
 * OAuth2 回调页（/oauth/callback）
 * 后端完成 OAuth 认证后重定向到此页，使用一次性登录码换取 JWT 并完成登录。
 */
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Spin, Alert } from 'antd'
import { useAuthStore, type AuthProvider } from '@/store/auth'
import { authApi } from '@/api/auth'
import { getPostLoginPath } from '@/utils/postLogin'

export default function OAuthCallbackPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { setTokens, setUser, setAuthProvider } = useAuthStore()
  const [errMsg, setErrMsg] = useState('')

  useEffect(() => {
    const loginCode  = searchParams.get('login_code')
    const oauthError = searchParams.get('oauth_error')
    const provider   = searchParams.get('provider') as AuthProvider | null

    if (oauthError) {
      setErrMsg(decodeURIComponent(oauthError))
      setTimeout(() => navigate('/login', { replace: true }), 3000)
      return
    }

    if (!loginCode) {
      setErrMsg('登录回调参数缺失，3 秒后返回登录页')
      setTimeout(() => navigate('/login', { replace: true }), 3000)
      return
    }

    authApi
      .exchangeOAuthLoginCode(loginCode)
      .then(res => {
        // 账号已启用 TOTP：跳转登录页完成二步验证（与本地登录一致）。
        if (res.requires_2fa) {
          if (!res.two_fa_token) throw new Error('缺少二步验证凭证')
          navigate('/login', { replace: true, state: { twoFaToken: res.two_fa_token, provider } })
          return null
        }
        setTokens()
        setAuthProvider(provider)
        return authApi.me()
      })
      .then(meRes => {
        if (!meRes) return // 已跳转二步验证
        setUser(meRes)
        navigate(getPostLoginPath(meRes.permissions || []), { replace: true })
      })
      .catch(() => {
        setErrMsg('获取用户信息失败，3 秒后返回登录页')
        setTimeout(() => navigate('/login', { replace: true }), 3000)
      })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div style={{
      minHeight: '100vh',
      background: '#0F172A',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 20,
    }}>
      {errMsg ? (
        <Alert
          type="error"
          showIcon
          message={errMsg}
          style={{
            maxWidth: 420,
            borderRadius: 10,
            background: 'rgba(245,63,63,0.1)',
            border: '1px solid rgba(245,63,63,0.3)',
            color: '#fff',
          }}
        />
      ) : (
        <>
          <Spin size="large" />
          <div style={{
            color: 'rgba(255,255,255,0.45)',
            fontFamily: "'Inter', sans-serif",
            fontSize: 14,
            letterSpacing: '0.5px',
          }}>
            正在完成登录，请稍候…
          </div>
        </>
      )}
    </div>
  )
}
