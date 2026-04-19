import { useState } from 'react'
import { Button, Form, Input, Alert, Divider, Tooltip, Tag, Modal, Typography } from 'antd'
import {
  UserOutlined, LockOutlined, EyeInvisibleOutlined, EyeTwoTone, ArrowLeftOutlined,
} from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import apiClient from '@/api/client'
import { authApi } from '@/api/auth'

// ── SagittaDB Logo ────────────────────────────────────────────
const SagittaLogo = () => (
  <svg viewBox="0 0 88 88" fill="none" width={80} height={80}>
    <path d="M44 8L79 28V60L44 80L9 60V28L44 8Z" fill="#165DFF"/>
    <path d="M30 38L44 24L58 38" stroke="white" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/>
    <line x1="44" y1="24" x2="44" y2="64" stroke="white" strokeWidth="4" strokeLinecap="round"/>
    <path d="M33 52H55" stroke="white" strokeWidth="3" strokeLinecap="round"/>
    <path d="M35 58H53" stroke="white" strokeWidth="2" strokeLinecap="round" opacity="0.5"/>
    <circle cx="44" cy="24" r="3.5" fill="white" opacity="0.85"/>
  </svg>
)

// ── 平台图标（官方矢量图） ─────────────────────────────────────
const PlatformIcon = ({ src, alt }: { src: string; alt: string }) => (
  <img
    src={src} alt={alt}
    width={24} height={24}
    style={{ objectFit: 'contain', display: 'block' }}
  />
)

// ── 第三方登录按钮 ──────────────────────────────────────────
const OAuthBtn = ({
  icon, label, color, loading, onClick,
}: { icon: React.ReactNode; label: string; color: string; loading?: boolean; onClick: () => void }) => (
  <Tooltip title={loading ? '正在跳转…' : `使用 ${label} 登录`} placement="top">
    <button onClick={onClick} disabled={loading} style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5,
      padding: '10px 6px', borderRadius: 10, cursor: loading ? 'not-allowed' : 'pointer',
      background: loading ? `${color}20` : 'rgba(255,255,255,0.04)',
      border: loading ? `1px solid ${color}60` : '1px solid rgba(255,255,255,0.08)',
      transition: 'all 0.2s',
      minWidth: 0,
      opacity: loading ? 0.7 : 1,
    }}
    onMouseEnter={e => {
      if (!loading) {
        (e.currentTarget as HTMLElement).style.background = `${color}18`
        ;(e.currentTarget as HTMLElement).style.borderColor = `${color}55`
      }
    }}
    onMouseLeave={e => {
      if (!loading) {
        (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.04)'
        ;(e.currentTarget as HTMLElement).style.borderColor = 'rgba(255,255,255,0.08)'
      }
    }}>
      {/* 图标区域：固定 24×24 容器，emoji 和 img 都居中 */}
      <span style={{ width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>
        {loading ? '⏳' : icon}
      </span>
      <span style={{
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10, color: loading ? color : 'rgba(255,255,255,0.4)',
        letterSpacing: '0.5px',
        whiteSpace: 'nowrap',
      }}>{label}</span>
    </button>
  </Tooltip>
)

// ── 主组件 ────────────────────────────────────────────────────
export default function LoginPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [loginForm] = Form.useForm()
  const [forcePwForm] = Form.useForm()
  const { setTokens, setUser } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [oauthLoading, setOauthLoading] = useState('')
  const [forceChangeMode, setForceChangeMode] = useState(false)
  const [forceChangeLoading, setForceChangeLoading] = useState(false)
  const [passwordChangeToken, setPasswordChangeToken] = useState('')
  const [passwordChangeReasons, setPasswordChangeReasons] = useState<string[]>([])
  const [pendingUsername, setPendingUsername] = useState('')
  const [error, setError] = useState(
    searchParams.get('oauth_error') ? decodeURIComponent(searchParams.get('oauth_error')!) : ''
  )

  const method = searchParams.get('method')
  const isLdap = method === 'ldap'

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

  const _doLogin = async (
    tokenData: { access_token?: string | null; refresh_token?: string | null; password_change_required?: boolean; password_change_token?: string | null; password_change_reasons?: string[] },
    username?: string,
  ) => {
    if (tokenData.password_change_required) {
      setPasswordChangeToken(tokenData.password_change_token || '')
      setPasswordChangeReasons(tokenData.password_change_reasons || [])
      setPendingUsername(username || '')
      setForceChangeMode(true)
      setError('')
      forcePwForm.resetFields()
      return
    }

    const { access_token, refresh_token } = tokenData
    if (!access_token || !refresh_token) {
      throw new Error('登录响应缺少 token')
    }
    const meRes = await apiClient.get('/auth/me/', {
      headers: { Authorization: `Bearer ${access_token}` },
    })
    setTokens(access_token, refresh_token)
    setUser(meRes.data)
    navigate('/dashboard', { replace: true })
  }

  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true)
    setError('')
    try {
      const tokenRes = await apiClient.post('/auth/login/', {
        username: values.username,
        password: values.password,
      })
      await _doLogin(tokenRes.data, values.username)
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
      await _doLogin(tokenData)
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
    setOauthLoading(type)
    setError('')
    try {
      const resp = await apiClient.get(`/auth/${type}/authorize/`)
      window.location.href = resp.data.url
    } catch (e: any) {
      setError(e.response?.data?.detail || `${type} 登录暂不可用，请联系管理员开启`)
      setOauthLoading('')
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
        content: resp.msg || '请使用新密码重新登录',
      })
    } catch (e: any) {
      setError(e.response?.data?.detail || e.response?.data?.msg || '密码修改失败')
    } finally {
      setForceChangeLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: '#0B1120',          /* 更深的午夜蓝，与各品牌色形成更强对比 */
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '32px 16px 24px',
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
            <SagittaLogo />
          </div>
          <div style={{
            fontFamily: "'Inter', sans-serif",
            fontWeight: 800, fontSize: 30,
            color: '#FFFFFF', letterSpacing: '-1px', lineHeight: 1,
          }}>
            SagittaDB
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
            SagittaDB · Aim at Data, Control with Precision
          </div>
        </div>

        {/* ── 错误提示 ── */}
        {error && (
          <Alert type="error" message={error} showIcon
            style={{
              marginBottom: 16, borderRadius: 8,
              background: 'rgba(245,63,63,0.1)',
              border: '1px solid rgba(245,63,63,0.3)',
            }} />
        )}

        {isLdap ? (
          /* ── LDAP 登录表单 ── */
          <>
            <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Button
                type="text" size="small" icon={<ArrowLeftOutlined />}
                style={{ color: 'rgba(255,255,255,0.45)', padding: 0 }}
                onClick={() => { setSearchParams({}); setError('') }}
              >
                返回
              </Button>
              <Tag style={{ borderRadius: 4, fontSize: 11, display: 'inline-flex', alignItems: 'center', gap: 4, background: 'rgba(94,124,224,0.15)', border: '1px solid rgba(94,124,224,0.4)', color: '#A5B4FC' }}>
                <img src="/icons/ldap.svg" width={13} height={13} style={{ objectFit: 'contain' }} alt="LDAP" />
                LDAP 认证
              </Tag>
            </div>
            <Form onFinish={handleLdapLogin} size="large" layout="vertical">
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
            ) : (
              <Form form={loginForm} onFinish={handleLogin} size="large" layout="vertical">
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
              display: 'grid',
              gridTemplateColumns: 'repeat(5, minmax(0, 1fr))',
              gap: 8,
            }}>
              {/* LDAP — 紫蓝 #5E7CE0 */}
              <OAuthBtn
                icon={<PlatformIcon src="/icons/ldap.svg" alt="LDAP" />}
                label="LDAP"  color="#5E7CE0"
                onClick={() => handleOAuth('ldap')}
              />
              {/* CAS — 统一认证服务 */}
              <OAuthBtn
                icon={<PlatformIcon src="/icons/cas.svg" alt="CAS" />}
                label="CAS"  color="#0590DF"
                loading={oauthLoading === 'cas'}
                onClick={() => handleOAuth('cas')}
              />
              {/* 钉钉 — 天蓝 #3AA2EB */}
              <OAuthBtn
                icon={<PlatformIcon src="/icons/dingtalk.svg" alt="钉钉" />}
                label="钉钉"  color="#3AA2EB"
                loading={oauthLoading === 'dingtalk'}
                onClick={() => handleOAuth('dingtalk')}
              />
              {/* 飞书 — 青绿 #00D6B9 */}
              <OAuthBtn
                icon={<PlatformIcon src="/icons/feishu.svg" alt="飞书" />}
                label="飞书"  color="#00D6B9"
                loading={oauthLoading === 'feishu'}
                onClick={() => handleOAuth('feishu')}
              />
              {/* 企微 — 钢蓝 #3970BA */}
              <OAuthBtn
                icon={<PlatformIcon src="/icons/wecom.svg" alt="企微" />}
                label="企微"  color="#3970BA"
                loading={oauthLoading === 'wecom'}
                onClick={() => handleOAuth('wecom')}
              />
            </div>
          </>
        )}
      </div>

      {/* 底部版本号 */}
      <div style={{
        position: 'relative',
        marginTop: 24,
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11, color: 'rgba(255,255,255,0.13)',
        letterSpacing: '1px', zIndex: 2, textAlign: 'center',
      }}>
        SagittaDB v2.0.0 · Full Engine Compatibility, End-to-End Observability
      </div>
    </div>
  )
}
