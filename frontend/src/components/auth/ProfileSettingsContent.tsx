import { useEffect, useState } from 'react'
import { Alert, Button, Col, Divider, Form, Input, QRCode, Row, Space, Steps, Tag, Typography, message } from 'antd'
import { MailOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/store/auth'
import SectionCard from '@/components/common/SectionCard'

const { Text } = Typography

type ProfileFormValues = {
  display_name: string
  email?: string
}

type ProfileSettingsContentProps = {
  compact?: boolean
}

function getErrorMessage(error: any, fallback: string) {
  return error?.response?.data?.detail || error?.response?.data?.msg || fallback
}

export default function ProfileSettingsContent({ compact = false }: ProfileSettingsContentProps) {
  const { user, setUser } = useAuthStore()
  const [profileForm] = Form.useForm<ProfileFormValues>()
  const [totpStep, setTotpStep] = useState(0)
  const [totpUri, setTotpUri] = useState('')
  const [totpSecret, setTotpSecret] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [disableCode, setDisableCode] = useState('')
  const [msgApi, msgCtx] = message.useMessage()

  useEffect(() => {
    if (!user) return
    profileForm.setFieldsValue({
      display_name: user.display_name || user.username,
      email: user.email || '',
    })
  }, [profileForm, user])

  const refreshMe = async () => {
    const nextUser = await authApi.me()
    setUser(nextUser)
  }

  const updateProfileMut = useMutation({
    mutationFn: (values: ProfileFormValues) => authApi.updateProfile({
      display_name: values.display_name.trim(),
      email: values.email?.trim() || '',
    }),
    onSuccess: (nextUser) => {
      setUser(nextUser)
      msgApi.success('个人信息已更新')
    },
    onError: (error: any) => msgApi.error(getErrorMessage(error, '保存失败')),
  })

  const setup2faMut = useMutation({
    mutationFn: authApi.setup2fa,
    onSuccess: (data: any) => {
      setTotpUri(data.provisioning_uri)
      setTotpSecret(data.secret || '')
      setTotpStep(1)
    },
    onError: (error: any) => msgApi.error(getErrorMessage(error, '获取密钥失败')),
  })

  const verify2faMut = useMutation({
    mutationFn: (code: string) => authApi.verify2fa(code),
    onSuccess: async () => {
      await refreshMe()
      setTotpStep(2)
      setTotpCode('')
      msgApi.success('2FA 已启用')
    },
    onError: (error: any) => msgApi.error(getErrorMessage(error, '验证码错误')),
  })

  const disable2faMut = useMutation({
    mutationFn: (code: string) => authApi.disable2fa(code),
    onSuccess: async () => {
      await refreshMe()
      setDisableCode('')
      setTotpCode('')
      setTotpUri('')
      setTotpSecret('')
      setTotpStep(0)
      msgApi.success('2FA 已关闭')
    },
    onError: (error: any) => msgApi.error(getErrorMessage(error, '验证码错误')),
  })

  const content = (
    <Row gutter={compact ? [16, 16] : [20, 20]} justify={compact ? 'center' : undefined}>
        <Col xs={24} lg={compact ? 11 : 12} style={{ minWidth: 0 }}>
          <SectionCard title={<Space><UserOutlined />基本信息</Space>} marginBottom={0}>
            <Space direction="vertical" size={14} style={{ width: '100%' }}>
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                  <Text type="secondary">用户名</Text>
                  <Text strong>{user?.username}</Text>
                </div>
                <Divider style={{ margin: '2px 0' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                  <Text type="secondary">角色</Text>
                  <Tag color={user?.is_superuser ? 'red' : 'blue'}>
                    {user?.is_superuser ? '超级管理员' : (user?.role || '未分配角色')}
                  </Tag>
                </div>
                <Divider style={{ margin: '2px 0' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                  <Text type="secondary">2FA 状态</Text>
                  <Tag color={user?.totp_enabled ? 'success' : 'default'}>
                    {user?.totp_enabled ? '已开启' : '未开启'}
                  </Tag>
                </div>
                <Divider style={{ margin: '2px 0' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                  <Text type="secondary">密码有效期</Text>
                  <Tag color={user?.password_expiring_soon ? 'warning' : 'success'}>
                    {user?.password_expiring_soon
                      ? `${user?.days_until_password_expiry ?? 0} 天后到期`
                      : '正常'}
                  </Tag>
                </div>
              </Space>

              <Divider style={{ margin: '4px 0' }} />

              <Form form={profileForm} layout="vertical" onFinish={(values) => updateProfileMut.mutate(values)}>
                <Form.Item
                  name="display_name"
                  label="显示名称"
                  rules={[{ required: true, message: '请输入显示名称' }]}
                >
                  <Input prefix={<UserOutlined />} maxLength={50} />
                </Form.Item>
                <Form.Item name="email" label="邮箱">
                  <Input prefix={<MailOutlined />} maxLength={100} placeholder="可选" />
                </Form.Item>
                <Button type="primary" htmlType="submit" loading={updateProfileMut.isPending}>
                  保存个人信息
                </Button>
              </Form>
            </Space>
          </SectionCard>
        </Col>

        <Col xs={24} lg={compact ? 11 : 12} style={{ minWidth: 0 }}>
          <SectionCard title={<Space><SafetyCertificateOutlined />二步验证（2FA）</Space>} marginBottom={0}>
            {user?.totp_enabled ? (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Alert
                  type="success"
                  showIcon
                  message="二步验证已开启"
                  description="登录时需要额外输入 Authenticator 应用中的动态验证码。"
                />
                <Divider>关闭 2FA</Divider>
                <Text type="secondary">输入当前 Authenticator 验证码以关闭 2FA：</Text>
                <Space wrap>
                  <Input
                    placeholder="6 位验证码"
                    maxLength={6}
                    style={{ width: 148 }}
                    value={disableCode}
                    onChange={(event) => setDisableCode(event.target.value)}
                  />
                  <Button
                    danger
                    loading={disable2faMut.isPending}
                    disabled={disableCode.length < 6}
                    onClick={() => disable2faMut.mutate(disableCode)}
                  >
                    关闭 2FA
                  </Button>
                </Space>
              </Space>
            ) : (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Alert
                  type="info"
                  showIcon
                  message="推荐开启二步验证"
                  description="开启后登录时需要额外输入 Google Authenticator / Authy 中的动态验证码，大幅提升账号安全性。"
                />
                <Steps
                  current={totpStep}
                  size="small"
                  direction="vertical"
                  items={[
                    {
                      title: '生成密钥',
                      description: totpStep === 0 ? (
                        <Button
                          type="primary"
                          size="small"
                          loading={setup2faMut.isPending}
                          onClick={() => setup2faMut.mutate(undefined)}
                          style={{ marginTop: 8 }}
                        >
                          开始配置 2FA
                        </Button>
                      ) : '已生成',
                    },
                    {
                      title: '扫描二维码',
                      description: totpStep === 1 && totpUri ? (
                        <Space direction="vertical" size={8} style={{ marginTop: 8 }}>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            使用 Google Authenticator 或 Authy 扫描下方二维码：
                          </Text>
                          <QRCode value={totpUri} size={160} />
                          {totpSecret && (
                            <Text code copyable style={{ wordBreak: 'break-all' }}>
                              {totpSecret}
                            </Text>
                          )}
                        </Space>
                      ) : totpStep > 1 ? '已扫描' : '待完成上一步',
                    },
                    {
                      title: '输入验证码确认',
                      description: totpStep === 1 ? (
                        <Space style={{ marginTop: 8 }} wrap>
                          <Input
                            placeholder="输入 6 位验证码"
                            maxLength={6}
                            style={{ width: 148 }}
                            value={totpCode}
                            onChange={(event) => setTotpCode(event.target.value)}
                          />
                          <Button
                            type="primary"
                            size="small"
                            loading={verify2faMut.isPending}
                            disabled={totpCode.length < 6}
                            onClick={() => verify2faMut.mutate(totpCode)}
                          >
                            验证并启用
                          </Button>
                        </Space>
                      ) : totpStep === 2 ? (
                        <Alert type="success" showIcon message="2FA 已成功开启！" style={{ marginTop: 8 }} />
                      ) : '待完成',
                    },
                  ]}
                />
              </Space>
            )}
          </SectionCard>
        </Col>
      </Row>
  )

  return (
    <>
      {msgCtx}
      {compact ? (
        <div style={{ maxWidth: 900, margin: '0 auto', paddingInline: 8 }}>
          {content}
        </div>
      ) : content}
    </>
  )
}
