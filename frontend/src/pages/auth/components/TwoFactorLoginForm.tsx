import { Alert, Button, Form, Input } from 'antd'
import { ArrowLeftOutlined, LockOutlined, LoginOutlined } from '@ant-design/icons'

// 登录二步验证（TOTP）子表单。纯展示：提交与返回登录的状态复位均由父组件通过回调注入。
// 从 LoginPage 的模式分支中抽离，降低页面体量。
export function TwoFactorLoginForm({
  pendingUsername,
  loading,
  onSubmit,
  onBack,
}: {
  pendingUsername: string
  loading: boolean
  onSubmit: (values: { totp_code: string }) => void
  onBack: () => void
}) {
  return (
    <>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="需要完成二步验证"
        description={`账号 ${pendingUsername || ''} 已开启 TOTP，请输入认证器中的 6 位验证码继续登录。`}
      />
      <Form onFinish={onSubmit} size="large" layout="vertical">
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
            loading={loading}
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
          onClick={onBack}
        >
          返回登录
        </Button>
      </Form>
    </>
  )
}
