import { useState } from 'react'
import { Alert, Button, Col, Divider, Form, Input, QRCode, Row, Space, Steps, Tag, Typography, message } from 'antd'
import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth'
import { authApi } from '@/api/auth'
import PageHeader from '@/components/common/PageHeader'
import SectionCard from '@/components/common/SectionCard'

const { Text } = Typography

export default function ProfilePage() {
  const { user } = useAuthStore()
  const [pwForm] = Form.useForm()
  const [totpStep, setTotpStep] = useState(0)
  const [totpUri, setTotpUri] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [disableCode, setDisableCode] = useState('')
  const [msgApi, msgCtx] = message.useMessage()

  // ── 修改密码 ──────────────────────────────────────────────
  const changePwMut = useMutation({
    mutationFn: (v: any) => authApi.changePassword(v.old_password, v.new_password),
    onSuccess: () => { msgApi.success('密码已修改，下次登录使用新密码'); pwForm.resetFields() },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '修改失败'),
  })

  // ── 2FA 设置 ──────────────────────────────────────────────
  const setup2faMut = useMutation({
    mutationFn: authApi.setup2fa,
    onSuccess: (data: any) => { setTotpUri(data.provisioning_uri); setTotpStep(1) },
    onError: (e: any) => msgApi.error(e.response?.data?.detail || '获取密钥失败'),
  })
  const verify2faMut = useMutation({
    mutationFn: (code: string) => authApi.verify2fa(code),
    onSuccess: () => { msgApi.success('2FA 已启用'); setTotpStep(2) },
    onError: (e: any) => msgApi.error(e.response?.data?.detail || '验证码错误'),
  })
  const disable2faMut = useMutation({
    mutationFn: (code: string) => authApi.disable2fa(code),
    onSuccess: () => { msgApi.success('2FA 已关闭'); setDisableCode('') },
    onError: (e: any) => msgApi.error(e.response?.data?.detail || '验证码错误'),
  })

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="个人设置"
        meta="查看账号信息、修改密码并管理二步验证"
        marginBottom={24}
      />

      <Row gutter={[20, 20]}>
        {/* 左列：个人信息 + 修改密码 */}
        <Col xs={24} md={12}>
          {/* 个人信息卡片 */}
          <SectionCard title={<Space><UserOutlined />基本信息</Space>} marginBottom={20}>
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text type="secondary">用户名</Text>
                <Text strong>{user?.username}</Text>
              </div>
              <Divider style={{ margin: '4px 0' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text type="secondary">显示名称</Text>
                <Text>{user?.display_name || '—'}</Text>
              </div>
              <Divider style={{ margin: '4px 0' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text type="secondary">邮箱</Text>
                <Text>{user?.email || '—'}</Text>
              </div>
              <Divider style={{ margin: '4px 0' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text type="secondary">角色</Text>
                <Tag color={user?.is_superuser ? 'red' : 'blue'}>
                  {user?.is_superuser ? '超级管理员' : (user?.role || '未分配角色')}
                </Tag>
              </div>
              <Divider style={{ margin: '4px 0' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text type="secondary">2FA 状态</Text>
                <Tag color={user?.totp_enabled ? 'success' : 'default'}>
                  {user?.totp_enabled ? '已开启' : '未开启'}
                </Tag>
              </div>
            </Space>
          </SectionCard>

          {/* 修改密码 */}
          <SectionCard title={<Space><LockOutlined />修改密码</Space>} marginBottom={0}>
            <Form form={pwForm} layout="vertical" onFinish={v => changePwMut.mutate(v)}>
              <Form.Item name="old_password" label="当前密码"
                rules={[{ required: true, message: '请输入当前密码' }]}>
                <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
              </Form.Item>
              <Form.Item name="new_password" label="新密码"
                rules={[{ required: true, min: 8, message: '新密码不能少于 8 位' }]}>
                <Input.Password prefix={<LockOutlined />} autoComplete="new-password" />
              </Form.Item>
              <Form.Item name="confirm_password" label="确认新密码"
                dependencies={['new_password']}
                rules={[
                  { required: true },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      if (!value || getFieldValue('new_password') === value) return Promise.resolve()
                      return Promise.reject('两次输入的密码不一致')
                    },
                  }),
                ]}>
                <Input.Password prefix={<LockOutlined />} autoComplete="new-password" />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={changePwMut.isPending} block>
                修改密码
              </Button>
            </Form>
          </SectionCard>
        </Col>

        {/* 右列：2FA 设置 */}
        <Col xs={24} md={12}>
          <SectionCard title={<Space><SafetyCertificateOutlined />二步验证（2FA）</Space>} marginBottom={0}>

            {user?.totp_enabled ? (
              // 已开启 2FA — 显示关闭入口
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Alert type="success" showIcon message="二步验证已开启" description="登录时需要输入 Authenticator 应用中的验证码" />
                <Divider>关闭 2FA</Divider>
                <Text type="secondary">输入当前 Authenticator 验证码以关闭 2FA：</Text>
                <Space>
                  <Input placeholder="6 位验证码" maxLength={6} style={{ width: 140 }}
                    value={disableCode} onChange={e => setDisableCode(e.target.value)} />
                  <Button danger loading={disable2faMut.isPending}
                    onClick={() => disable2faMut.mutate(disableCode)}>
                    关闭 2FA
                  </Button>
                </Space>
              </Space>
            ) : (
              // 未开启 2FA — 引导开启
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Alert type="info" showIcon
                  message="推荐开启二步验证"
                  description="开启后登录时需要额外输入 Google Authenticator / Authy 中的动态验证码，大幅提升账号安全性。" />

                <Steps current={totpStep} size="small" direction="vertical"
                  items={[
                    {
                      title: '生成密钥',
                      description: totpStep === 0 ? (
                        <Button type="primary" size="small" loading={setup2faMut.isPending}
                          onClick={() => setup2faMut.mutate(undefined)} style={{ marginTop: 8 }}>
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
                        </Space>
                      ) : totpStep > 1 ? '已扫描' : '待完成上一步',
                    },
                    {
                      title: '输入验证码确认',
                      description: totpStep === 1 ? (
                        <Space style={{ marginTop: 8 }}>
                          <Input placeholder="输入 6 位验证码" maxLength={6} style={{ width: 140 }}
                            value={totpCode} onChange={e => setTotpCode(e.target.value)} />
                          <Button type="primary" size="small" loading={verify2faMut.isPending}
                            onClick={() => verify2faMut.mutate(totpCode)}>
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
    </div>
  )
}
