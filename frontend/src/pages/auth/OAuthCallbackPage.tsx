/**
 * OAuth2 回调页（/oauth/callback）
 * 后端完成 OAuth 认证后重定向到此页，读取 URL 参数中的 JWT 并完成登录。
 */
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Spin, Alert } from 'antd'
import { useAuthStore, type AuthProvider } from '@/store/auth'
import apiClient from '@/api/client'
import { getPostLoginPath } from '@/utils/postLogin'

export default function OAuthCallbackPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { setTokens, setUser, setAuthProvider } = useAuthStore()
  const [errMsg, setErrMsg] = useState('')

  useEffect(() => {
    const accessToken  = searchParams.get('access_token')
    const refreshToken = searchParams.get('refresh_token')
    const oauthError   = searchParams.get('oauth_error')
    const provider     = searchParams.get('provider') as AuthProvider | null

    if (oauthError) {
      setErrMsg(decodeURIComponent(oauthError))
      setTimeout(() => navigate('/login', { replace: true }), 3000)
      return
    }

    if (!accessToken || !refreshToken) {
      setErrMsg('登录回调参数缺失，3 秒后返回登录页')
      setTimeout(() => navigate('/login', { replace: true }), 3000)
      return
    }

    apiClient
      .get('/auth/me/', { headers: { Authorization: `Bearer ${accessToken}` } })
      .then(meRes => {
        setTokens(accessToken, refreshToken)
        setAuthProvider(provider)
        setUser(meRes.data)
        navigate(getPostLoginPath(meRes.data.permissions || []), { replace: true })
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
