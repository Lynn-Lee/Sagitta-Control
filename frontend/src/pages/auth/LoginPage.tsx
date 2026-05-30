import { useEffect, useMemo, useState } from 'react'
import { Button, Form, Input, Alert, Divider, Tooltip, Modal, Space, message } from 'antd'
import {
  UserOutlined, LockOutlined, EyeInvisibleOutlined, EyeTwoTone, ArrowLeftOutlined, LoginOutlined, SaveOutlined,
  GlobalOutlined, KeyOutlined,
} from '@ant-design/icons'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuthStore, type AuthProvider } from '@/store/auth'
import apiClient from '@/api/client'
import { authApi } from '@/api/auth'
import { getPostLoginPath } from '@/utils/postLogin'
import BrandLogo from '@/components/common/BrandLogo'
import { useBranding } from '@/hooks/useBranding'

// ── 平台图标（官方矢量图） ─────────────────────────────────────
const OAUTH_PROVIDER_LABELS: Record<string, string> = {
  ldap: 'LDAP',
  cas: 'CAS',
  oidc: 'OIDC',
  sms: '短信验证码',
  dingtalk: '钉钉',
  feishu: '飞书',
  wecom: '企业微信',
}

type LoginMethod = 'ldap' | 'cas' | 'oidc' | 'sms' | 'dingtalk' | 'feishu' | 'wecom'

const DEFAULT_AUTH_METHODS: Record<LoginMethod, boolean> = {
  ldap: true,
  cas: true,
  oidc: false,
  sms: false,
  dingtalk: true,
  feishu: true,
  wecom: true,
}

const PlatformIcon = ({ src, alt, size = 18 }: { src: string; alt: string; size?: number }) => (
  <img
    src={src} alt={alt}
    width={size} height={size}
    style={{ objectFit: 'contain', display: 'block' }}
  />
)

const formatLoginError = (message: string) => message.replace(/CorpID\s*\/\s*AgentId/g, 'CorpID/AgentId')

// ── 第三方登录按钮 ──────────────────────────────────────────
const OAuthBtn = ({
  icon, label, color, loading, onClick,
}: { icon: React.ReactNode; label: string; color: string; loading?: boolean; onClick: () => void }) => (
  <Tooltip title={loading ? '正在跳转…' : `使用 ${label} 登录`} placement="top">
    <Button
      className="sagitta-oauth-btn"
      icon={icon}
      aria-label={`使用 ${label} 登录`}
      loading={loading}
      disabled={loading}
      onClick={onClick}
      style={{ '--oauth-color': color } as React.CSSProperties}
    />
  </Tooltip>
)

// ── 主组件 ────────────────────────────────────────────────────
export default function LoginPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [loginForm] = Form.useForm()
  const [smsForm] = Form.useForm()
  const [forcePwForm] = Form.useForm()
  const { setTokens, setUser, setAuthProvider, isAuthenticated, user } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [oauthLoading, setOauthLoading] = useState('')
  const [forceChangeMode, setForceChangeMode] = useState(false)
  const [twoFactorMode, setTwoFactorMode] = useState(false)
  const [twoFactorLoading, setTwoFactorLoading] = useState(false)
  const [twoFactorToken, setTwoFactorToken] = useState('')
  const [authMethods, setAuthMethods] = useState<Record<LoginMethod, boolean> | null>(null)
  const [smsSending, setSmsSending] = useState(false)
  const [smsLoginLoading, setSmsLoginLoading] = useState(false)
  const [smsCountdown, setSmsCountdown] = useState(0)
  const [forceChangeLoading, setForceChangeLoading] = useState(false)
  const [passwordChangeToken, setPasswordChangeToken] = useState('')
  const [passwordChangeReasons, setPasswordChangeReasons] = useState<string[]>([])
  const [pendingUsername, setPendingUsername] = useState('')
  const [pendingAuthProvider, setPendingAuthProvider] = useState<AuthProvider>('local')
  const [error, setError] = useState(
    searchParams.get('oauth_error') ? formatLoginError(decodeURIComponent(searchParams.get('oauth_error')!)) : ''
  )
  const { branding } = useBranding()

  const method = searchParams.get('method')
  const isLdap = method === 'ldap'
  const isSms = method === 'sms'
  const visibleLoginMethods = useMemo(
    () => authMethods ? (Object.keys(authMethods) as LoginMethod[]).filter((key) => authMethods[key]) : [],
    [authMethods],
  )

  useEffect(() => {
    let active = true
    apiClient
      .get('/system/auth-methods/')
      .then((res) => {
        if (!active) return
        setAuthMethods({ ...DEFAULT_AUTH_METHODS, ...res.data })
      })
      .catch(() => {
        if (active) setAuthMethods(DEFAULT_AUTH_METHODS)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (smsCountdown <= 0) return undefined
    const timer = window.setInterval(() => {
      setSmsCountdown((current) => Math.max(0, current - 1))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [smsCountdown])

  const passwordRules = [
    { required: true, message: '请输入新密码' },
    { min: 8, message: '密码长度不能少于 8 位' },
    { pattern: /[A-Z]/, message: '密码必须包含至少 1 个大写字母' },
    { pattern: /[a-z]/, message: '密码必须包含至少 1 个小写字母' },
    { pattern: /\d/, message: '密码必须包含至少 1 个数字' },
    { pattern: /[^A-Za-z0-9]/, message: '密码必须包含至少 1 个特殊字符' },
  ]
  const passwordRuleHints = [
    '至少 8 位',
    '必须包含至少 1 个数字',
    '必须包含至少 1 个大写字母',
    '必须包含至少 1 个小写字母',
    '必须包含至少 1 个特殊字符',
    '密码每 30 天必须修改一次',
  ]

  const finishLogin = async (
    access_token: string,
    refresh_token: string,
    provider: AuthProvider = 'local',
  ) => {
    setTokens(access_token, refresh_token)
    setAuthProvider(provider)
    const meRes = await apiClient.get('/auth/me/', {
      headers: { Authorization: `Bearer ${access_token}` },
    })
    setUser(meRes.data)
    const target = getPostLoginPath(meRes.data.permissions || [])
    navigate(target, { replace: true })
  }

  if (isAuthenticated && user) {
    return <Navigate to={getPostLoginPath(user.permissions || [])} replace />
  }

  const _doLogin = async (
    tokenData: {
      access_token?: string | null
      refresh_token?: string | null
      password_change_required?: boolean
      password_change_token?: string | null
      password_change_reasons?: string[]
      requires_2fa?: boolean
      two_fa_token?: string | null
    },
    username?: string,
    provider: AuthProvider = 'local',
  ) => {
    if (tokenData.password_change_required) {
      setPasswordChangeToken(tokenData.password_change_token || '')
      setPasswordChangeReasons(tokenData.password_change_reasons || [])
      setPendingUsername(username || '')
      setPendingAuthProvider(provider)
      setForceChangeMode(true)
      setTwoFactorMode(false)
      setTwoFactorToken('')
      setError('')
      forcePwForm.resetFields()
      return
    }

    if (tokenData.requires_2fa) {
      if (!tokenData.two_fa_token) {
        throw new Error('登录响应缺少二步验证凭证')
      }
      setTwoFactorToken(tokenData.two_fa_token)
      setPendingUsername(username || '')
      setPendingAuthProvider(provider)
      setTwoFactorMode(true)
      setForceChangeMode(false)
      setError('')
      loginForm.setFieldsValue({ username: username || '', password: '' })
      return
    }

    const { access_token, refresh_token } = tokenData
    if (!access_token || !refresh_token) {
      throw new Error('登录响应缺少 token')
    }
    await finishLogin(access_token, refresh_token, provider)
  }

  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true)
    setError('')
    try {
      const tokenRes = await apiClient.post('/auth/login/', {
        username: values.username,
        password: values.password,
      })
      await _doLogin(tokenRes.data, values.username, 'local')
    } catch (e: any) {
      setError(e.response?.data?.detail || '用户名或密码错误')
    } finally {
      setLoading(false)
    }
  }

  const handleLdapLogin = async (values: { username: string; password: string }) => {
    setLoading(true)
    setError('')
    try {
      const tokenData = await authApi.ldapLogin(values.username, values.password)
      await _doLogin(tokenData, values.username, 'ldap')
    } catch (e: any) {
      setError(e.response?.data?.detail || 'LDAP 认证失败')
    } finally {
      setLoading(false)
    }
  }

  const handleOAuth = async (type: string) => {
    if (type === 'ldap') {
      setSearchParams({ method: 'ldap' })
      setError('')
      return
    }
    if (type === 'sms') {
      setSearchParams({ method: 'sms' })
      setError('')
      return
    }
    setOauthLoading(type)
    setError('')
    try {
      const resp = await apiClient.get(`/auth/${type}/authorize/`)
      window.location.href = resp.data.url
    } catch (e: any) {
      setError(formatLoginError(e.response?.data?.detail || '企业登录跳转失败'))
      setOauthLoading('')
    }
  }

  const handleSendSmsCode = async () => {
    try {
      const { phone } = await smsForm.validateFields(['phone'])
      setSmsSending(true)
      setError('')
      const result = await authApi.sendSmsCode(phone)
      if (result.success === false) {
        setError(result.message || '短信验证码发送失败')
        return
      }
      message.success(result.message || '验证码已发送')
      setSmsCountdown(60)
    } catch (e: any) {
      if (e?.errorFields) return
      setError(e.response?.data?.detail || e.response?.data?.message || '短信验证码发送失败')
    } finally {
      setSmsSending(false)
    }
  }

  const handleSmsLogin = async (values: { phone: string; code: string }) => {
    setSmsLoginLoading(true)
    setError('')
    try {
      const tokenData = await authApi.smsLogin(values.phone, values.code)
      await _doLogin(tokenData, values.phone, 'sms')
    } catch (e: any) {
      setError(e.response?.data?.detail || '短信验证码登录失败')
    } finally {
      setSmsLoginLoading(false)
    }
  }

  const handleForceChangePassword = async (values: { new_password: string }) => {
    if (!passwordChangeToken) {
      setError('改密凭证已失效，请重新登录')
      setForceChangeMode(false)
      return
    }
    setForceChangeLoading(true)
    setError('')
    try {
      const resp = await authApi.forceChangePassword(passwordChangeToken, values.new_password)
      setForceChangeMode(false)
      setPasswordChangeToken('')
      setPasswordChangeReasons([])
      loginForm.setFieldsValue({ username: pendingUsername, password: '' })
      forcePwForm.resetFields()
      Modal.success({
        title: '密码修改成功',
        maskClosable: false,
        content: resp.msg || '请使用新密码重新登录',
      })
    } catch (e: any) {
      setError(e.response?.data?.detail || e.response?.data?.msg || '密码修改失败')
    } finally {
      setForceChangeLoading(false)
    }
  }

  const handleVerifyLogin2fa = async (values: { totp_code: string }) => {
    if (!twoFactorToken) {
      setError('二步验证凭证已失效，请重新输入账号密码登录')
      setTwoFactorMode(false)
      return
    }
    setTwoFactorLoading(true)
    setError('')
    try {
      const tokenData = await authApi.verifyLogin2fa(twoFactorToken, values.totp_code)
      setTwoFactorMode(false)
      setTwoFactorToken('')
      await _doLogin(tokenData, pendingUsername, pendingAuthProvider)
    } catch (e: any) {
      setError(e.response?.data?.detail || '二步验证失败')
    } finally {
      setTwoFactorLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: '#111A2E',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '32px 16px 88px',
      fontFamily: "'Inter', 'Noto Sans SC', sans-serif",
      position: 'relative',
      overflow: 'hidden',
    }}>

      {/* 背景光晕 — 靛紫主光 */}
      <div style={{
        position: 'absolute', width: 680, height: 680,
        background: 'radial-gradient(circle, rgba(79,70,229,0.20) 0%, transparent 68%)',
        top: '50%', left: '50%',
        transform: 'translate(-50%, -52%)',
        pointerEvents: 'none',
      }} />
      {/* 背景光晕 — 青绿副光（呼应飞书品牌色） */}
      <div style={{
        position: 'absolute', width: 420, height: 420,
        background: 'radial-gradient(circle, rgba(0,214,185,0.10) 0%, transparent 68%)',
        bottom: '8%', right: '12%',
        pointerEvents: 'none',
      }} />
      {/* 背景光晕 — 天蓝副光（呼应钉钉品牌色） */}
      <div style={{
        position: 'absolute', width: 320, height: 320,
        background: 'radial-gradient(circle, rgba(58,162,235,0.08) 0%, transparent 68%)',
        top: '10%', left: '10%',
        pointerEvents: 'none',
      }} />

      {/* 网格纹理 */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: `
          linear-gradient(rgba(79,70,229,0.035) 1px, transparent 1px),
          linear-gradient(90deg, rgba(79,70,229,0.035) 1px, transparent 1px)
        `,
        backgroundSize: '60px 60px',
        pointerEvents: 'none',
      }} />

      {/* 登录卡片 */}
      <div style={{
        position: 'relative', zIndex: 2,
        width: '100%',
        maxWidth: 420,
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(79,70,229,0.22)',
        borderRadius: 20,
        padding: '44px 40px 36px',
        backdropFilter: 'blur(24px)',
      }}>

        {/* ── Logo 区域 ── */}
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <div style={{
            display: 'inline-block',
            filter: 'drop-shadow(0 0 28px rgba(79,70,229,0.55))',
            marginBottom: 16,
          }}>
            <BrandLogo logoUrl={branding.platform_logo_url} size={80} color="#165DFF" />
          </div>
          <div style={{
            fontFamily: "'Inter', sans-serif",
            fontWeight: 800, fontSize: 30,
            color: '#FFFFFF', letterSpacing: 0, lineHeight: 1.12,
            overflowWrap: 'anywhere',
          }}>
            {branding.platform_name}
          </div>
          <div style={{
            fontFamily: "'Noto Sans SC', sans-serif",
            fontWeight: 500, fontSize: 13,
            color: '#818CF8',           /* 改为靛紫-200，与背景光晕一致 */
            letterSpacing: '7px', marginTop: 7, textAlign: 'center',
          }}>
            矢 准 数 据
          </div>
          <div style={{
            fontFamily: "'Inter', sans-serif",
            fontWeight: 300, fontSize: 11,
            color: 'rgba(255,255,255,0.25)',
            letterSpacing: '1.5px', marginTop: 12,
          }}>
            {branding.platform_name} · Aim at Data, Control with Precision
          </div>
        </div>

        {/* ── 错误提示 ── */}
        {error && (
          <Alert
            className="sagitta-login-error-alert"
            type="error"
            message={<span style={{ color: '#FEE2E2' }}>{error}</span>}
            showIcon
            style={{
              marginBottom: 16, borderRadius: 8,
              background: 'rgba(245,63,63,0.1)',
              border: '1px solid rgba(245,63,63,0.3)',
            }} />
        )}

        {isLdap ? (
          /* ── LDAP 登录表单 ── */
          <>
            <div className="sagitta-login-mode-header">
              <Tooltip title="返回账号密码登录" placement="top">
                <Button
                  className="sagitta-login-back-btn"
                  type="text"
                  icon={<ArrowLeftOutlined />}
                  aria-label="返回账号密码登录"
                  onClick={() => { setSearchParams({}); setError('') }}
                />
              </Tooltip>
              <div className="sagitta-login-mode-title">
                <span className="sagitta-login-mode-icon" style={{ '--mode-color': '#5E7CE0' } as React.CSSProperties}>
                  <PlatformIcon src="/icons/ldap.svg" alt="LDAP" size={20} />
                </span>
                <span>LDAP 认证</span>
              </div>
            </div>
            <Form className="sagitta-auth-form" onFinish={handleLdapLogin} size="large" layout="vertical">
              <Form.Item name="username" rules={[{ required: true, message: '请输入 LDAP 用户名' }]}
                style={{ marginBottom: 14 }}>
                <Input
                  prefix={<UserOutlined style={{ color: 'rgba(255,255,255,0.3)' }} />}
                  placeholder="LDAP 用户名"
                  style={{
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 8, color: '#FFFFFF', height: 46,
                  }}
                />
              </Form.Item>
              <Form.Item name="password" rules={[{ required: true, message: '请输入 LDAP 密码' }]}
                style={{ marginBottom: 22 }}>
                <Input.Password
                  prefix={<LockOutlined style={{ color: 'rgba(255,255,255,0.3)' }} />}
                  placeholder="LDAP 密码"
                  iconRender={v => v
                    ? <EyeTwoTone twoToneColor="#5E7CE0" />
                    : <EyeInvisibleOutlined style={{ color: 'rgba(255,255,255,0.3)' }} />
                  }
                  style={{
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 8, color: '#FFFFFF', height: 46,
                  }}
                />
              </Form.Item>
              <Form.Item style={{ marginBottom: 0 }}>
                <Button
                  type="primary" htmlType="submit" loading={loading} block
                  icon={<LoginOutlined />}
                  style={{
                    height: 46, borderRadius: 8,
                    background: '#5E7CE0', border: 'none',
                    fontWeight: 600, fontSize: 15, letterSpacing: '1px',
                    boxShadow: '0 4px 20px rgba(94,124,224,0.45)',
                  }}
                >
                  LDAP 登 录
                </Button>
              </Form.Item>
            </Form>
          </>
        ) : isSms ? (
          /* ── 短信验证码登录表单 ── */
          <>
            <div className="sagitta-login-mode-header">
              <Tooltip title="返回账号密码登录" placement="top">
                <Button
                  className="sagitta-login-back-btn"
                  type="text"
                  icon={<ArrowLeftOutlined />}
                  aria-label="返回账号密码登录"
                  onClick={() => { setSearchParams({}); setError('') }}
                />
              </Tooltip>
              <div className="sagitta-login-mode-title">
                <span className="sagitta-login-mode-icon" style={{ '--mode-color': '#1677FF' } as React.CSSProperties}>
                  <PlatformIcon src="/icons/sms.svg" alt="短信验证码" size={20} />
                </span>
                <span>短信验证码</span>
              </div>
            </div>
            <Form className="sagitta-auth-form" form={smsForm} onFinish={handleSmsLogin} size="large" layout="vertical">
              <Form.Item
                name="phone"
                rules={[
                  { required: true, message: '请输入手机号' },
                  { min: 6, message: '手机号格式不正确' },
                ]}
                style={{ marginBottom: 14 }}
              >
                <Input
                  prefix={<PlatformIcon src="/icons/sms.svg" alt="手机号" size={16} />}
                  placeholder="手机号"
                  inputMode="tel"
                  autoComplete="tel"
                  style={{
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 8, color: '#FFFFFF', height: 46,
                  }}
                />
              </Form.Item>
              <Form.Item style={{ marginBottom: 22 }}>
                <Space.Compact style={{ width: '100%' }}>
                  <Form.Item
                    name="code"
                    noStyle
                    rules={[
                      { required: true, message: '请输入短信验证码' },
                      { min: 4, message: '验证码格式不正确' },
                    ]}
                  >
                    <Input
                      prefix={<LockOutlined style={{ color: 'rgba(255,255,255,0.3)' }} />}
                      placeholder="短信验证码"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      style={{
                        background: 'rgba(255,255,255,0.06)',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: '8px 0 0 8px', color: '#FFFFFF', height: 46,
                      }}
                    />
                  </Form.Item>
                  <Button
                    loading={smsSending}
                    disabled={smsCountdown > 0}
                    onClick={handleSendSmsCode}
                    style={{
                      height: 46,
                      minWidth: 116,
                      color: '#FFFFFF',
                      borderColor: 'rgba(255,255,255,0.14)',
                      background: 'rgba(22,119,255,0.24)',
                    }}
                  >
                    {smsCountdown > 0 ? `${smsCountdown}s` : '获取验证码'}
                  </Button>
                </Space.Compact>
              </Form.Item>
              <Form.Item style={{ marginBottom: 0 }}>
                <Button
                  type="primary" htmlType="submit" loading={smsLoginLoading} block
                  icon={<LoginOutlined />}
                  style={{
                    height: 46, borderRadius: 8,
                    background: '#1677FF', border: 'none',
                    fontWeight: 600, fontSize: 15, letterSpacing: '1px',
                    boxShadow: '0 4px 20px rgba(22,119,255,0.42)',
                  }}
                >
                  短信登录
                </Button>
              </Form.Item>
            </Form>
          </>
        ) : (
          /* ── 本地登录表单 ── */
          <>
            {forceChangeMode ? (
              <>
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginBottom: 16 }}
                  message="首次登录安全校验"
                  description={`账号 ${pendingUsername || ''} 必须先完成密码修改，修改成功后请使用新密码重新登录。`}
                />
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 16 }}
                  message="新密码规则"
                  description={
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {passwordRuleHints.map(rule => <li key={rule}>{rule}</li>)}
                    </ul>
                  }
                />
                {passwordChangeReasons.length > 0 && (
                  <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message="当前密码触发原因"
                    description={
                      <ul style={{ margin: 0, paddingLeft: 18 }}>
                        {passwordChangeReasons.map(reason => <li key={reason}>{reason}</li>)}
                      </ul>
                    }
                  />
                )}
                <Form form={forcePwForm} onFinish={handleForceChangePassword} size="large" layout="vertical">
                  <Form.Item name="new_password" label="新密码" rules={passwordRules}
                    style={{ marginBottom: 14 }}>
                    <Input.Password
                      prefix={<LockOutlined style={{ color: 'rgba(255,255,255,0.3)' }} />}
                      placeholder="新密码"
                      autoComplete="new-password"
                    />
                  </Form.Item>
                  <Form.Item
                    name="confirm_password"
                    label="确认新密码"
                    dependencies={['new_password']}
                    style={{ marginBottom: 22 }}
                    rules={[
                      { required: true, message: '请再次输入新密码' },
                      ({ getFieldValue }) => ({
                        validator(_, value) {
                          if (!value || getFieldValue('new_password') === value) return Promise.resolve()
                          return Promise.reject(new Error('两次输入的密码不一致'))
                        },
                      }),
                    ]}
                  >
                    <Input.Password
                      prefix={<LockOutlined style={{ color: 'rgba(255,255,255,0.3)' }} />}
                      placeholder="确认新密码"
                      autoComplete="new-password"
                    />
                  </Form.Item>
                  <Form.Item style={{ marginBottom: 10 }}>
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={forceChangeLoading}
                      block
                      icon={<SaveOutlined />}
                      style={{
                        height: 46, borderRadius: 8,
                        background: '#165DFF', border: 'none',
                        fontWeight: 600, fontSize: 15, letterSpacing: '1px',
                        boxShadow: '0 4px 20px rgba(22,93,255,0.4)',
                      }}
                    >
                      修改密码并返回登录
                    </Button>
                  </Form.Item>
                  <Button
                    block
                    icon={<ArrowLeftOutlined />}
                    onClick={() => {
                      setForceChangeMode(false)
                      setPasswordChangeToken('')
                      setPasswordChangeReasons([])
                      forcePwForm.resetFields()
                    }}
                  >
                    返回登录
                  </Button>
                </Form>
              </>
            ) : twoFactorMode ? (
              <>
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 16 }}
                  message="需要完成二步验证"
                  description={`账号 ${pendingUsername || ''} 已开启 TOTP，请输入认证器中的 6 位验证码继续登录。`}
                />
                <Form onFinish={handleVerifyLogin2fa} size="large" layout="vertical">
                  <Form.Item
                    name="totp_code"
                    label="验证码"
                    rules={[
                      { required: true, message: '请输入 6 位验证码' },
                      { pattern: /^\d{6}$/, message: '验证码必须为 6 位数字' },
                    ]}
                    style={{ marginBottom: 22 }}
                  >
                    <Input
                      prefix={<LockOutlined style={{ color: 'rgba(255,255,255,0.3)' }} />}
                      placeholder="请输入 6 位验证码"
                      autoComplete="one-time-code"
                      inputMode="numeric"
                      maxLength={6}
                    />
                  </Form.Item>
                  <Form.Item style={{ marginBottom: 10 }}>
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={twoFactorLoading}
                      block
                      icon={<LoginOutlined />}
                      style={{
                        height: 46, borderRadius: 8,
                        background: '#165DFF', border: 'none',
                        fontWeight: 600, fontSize: 15, letterSpacing: '1px',
                        boxShadow: '0 4px 20px rgba(22,93,255,0.4)',
                      }}
                    >
                      验证并登录
                    </Button>
                  </Form.Item>
                  <Button
                    block
                    icon={<ArrowLeftOutlined />}
                    onClick={() => {
                      setTwoFactorMode(false)
                      setTwoFactorToken('')
                      setPendingUsername('')
                      setPendingAuthProvider('local')
                      setError('')
                    }}
                  >
                    返回登录
                  </Button>
                </Form>
              </>
            ) : (
              <Form className="sagitta-auth-form" form={loginForm} onFinish={handleLogin} size="large" layout="vertical">
                <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}
                  style={{ marginBottom: 14 }}>
                  <Input
                    prefix={<UserOutlined style={{ color: 'rgba(255,255,255,0.3)' }} />}
                    placeholder="用户名"
                    style={{
                      background: 'rgba(255,255,255,0.06)',
                      border: '1px solid rgba(255,255,255,0.1)',
                      borderRadius: 8, color: '#FFFFFF', height: 46,
                    }}
                  />
                </Form.Item>
                <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}
                  style={{ marginBottom: 22 }}>
                  <Input.Password
                    prefix={<LockOutlined style={{ color: 'rgba(255,255,255,0.3)' }} />}
                    placeholder="密码"
                    autoComplete="current-password"
                    iconRender={v => v
                      ? <EyeTwoTone twoToneColor="#165DFF" />
                      : <EyeInvisibleOutlined style={{ color: 'rgba(255,255,255,0.3)' }} />
                    }
                    style={{
                      background: 'rgba(255,255,255,0.06)',
                      border: '1px solid rgba(255,255,255,0.1)',
                      borderRadius: 8, color: '#FFFFFF', height: 46,
                    }}
                  />
                </Form.Item>
                <Form.Item style={{ marginBottom: 0 }}>
                  <Button
                    type="primary" htmlType="submit" loading={loading} block
                    icon={<LoginOutlined />}
                    style={{
                      height: 46, borderRadius: 8,
                      background: '#165DFF', border: 'none',
                      fontWeight: 600, fontSize: 15, letterSpacing: '1px',
                      boxShadow: '0 4px 20px rgba(22,93,255,0.4)',
                    }}
                  >
                    登 录
                  </Button>
                </Form.Item>
              </Form>
            )}

            {authMethods && visibleLoginMethods.length > 0 && (
              <>
                {/* ── 第三方登录 ── */}
                <Divider style={{
                  borderColor: 'rgba(255,255,255,0.07)',
                  color: 'rgba(255,255,255,0.22)',
                  fontSize: 11,
                  fontFamily: "'JetBrains Mono', monospace",
                  letterSpacing: '1px',
                  margin: '20px 0 16px',
                }}>
                  其他登录方式
                </Divider>

                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: visibleLoginMethods.length > 1 ? 'space-between' : 'center',
                  gap: visibleLoginMethods.length > 1 ? 'clamp(6px, 1.6vw, 12px)' : 0,
                  width: '100%',
                  flexWrap: 'nowrap',
                }}>
                  {authMethods.ldap && (
                    <OAuthBtn
                      icon={<PlatformIcon src="/icons/ldap.svg" alt="LDAP" />}
                      label={OAUTH_PROVIDER_LABELS.ldap} color="#5E7CE0"
                      onClick={() => handleOAuth('ldap')}
                    />
                  )}
                  {authMethods.cas && (
                    <OAuthBtn
                      icon={<GlobalOutlined />}
                      label={OAUTH_PROVIDER_LABELS.cas} color="#0F766E"
                      loading={oauthLoading === 'cas'}
                      onClick={() => handleOAuth('cas')}
                    />
                  )}
                  {authMethods.oidc && (
                    <OAuthBtn
                      icon={<KeyOutlined />}
                      label={OAUTH_PROVIDER_LABELS.oidc} color="#2F80ED"
                      loading={oauthLoading === 'oidc'}
                      onClick={() => handleOAuth('oidc')}
                    />
                  )}
                  {authMethods.sms && (
                    <OAuthBtn
                      icon={<PlatformIcon src="/icons/sms.svg" alt="短信验证码" />}
                      label={OAUTH_PROVIDER_LABELS.sms} color="#1677FF"
                      onClick={() => handleOAuth('sms')}
                    />
                  )}
                  {authMethods.dingtalk && (
                    <OAuthBtn
                      icon={<PlatformIcon src="/icons/dingtalk.svg" alt="钉钉" />}
                      label={OAUTH_PROVIDER_LABELS.dingtalk} color="#3AA2EB"
                      loading={oauthLoading === 'dingtalk'}
                      onClick={() => handleOAuth('dingtalk')}
                    />
                  )}
                  {authMethods.feishu && (
                    <OAuthBtn
                      icon={<PlatformIcon src="/icons/feishu.svg" alt="飞书" />}
                      label={OAUTH_PROVIDER_LABELS.feishu} color="#00D6B9"
                      loading={oauthLoading === 'feishu'}
                      onClick={() => handleOAuth('feishu')}
                    />
                  )}
                  {authMethods.wecom && (
                    <OAuthBtn
                      icon={<PlatformIcon src="/icons/wecom.svg" alt="企微" />}
                      label={OAUTH_PROVIDER_LABELS.wecom} color="#3970BA"
                      loading={oauthLoading === 'wecom'}
                      onClick={() => handleOAuth('wecom')}
                    />
                  )}
                </div>
              </>
            )}
          </>
        )}
      </div>

      {/* 底部信息 */}
      <div style={{
        position: 'absolute',
        bottom: 24,
        left: 16,
        right: 16,
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11, color: 'rgba(255,255,255,0.13)',
        letterSpacing: '1px', zIndex: 2, textAlign: 'center',
        lineHeight: 1.8,
      }}>
        <div>Copyright © 2026 Lynn-Lee. All rights reserved.</div>
        <div>{branding.platform_name} v2.2.0 · Full Engine Compatibility, End-to-End Observability</div>
      </div>
    </div>
  )
}
