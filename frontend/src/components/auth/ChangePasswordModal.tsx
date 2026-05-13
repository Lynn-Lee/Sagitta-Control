import { Alert, Form, Input, Modal, message } from 'antd'
import { LockOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/store/auth'

type ChangePasswordModalProps = {
  open: boolean
  onClose: () => void
}

type ChangePasswordValues = {
  old_password: string
  new_password: string
  confirm_password: string
}

const passwordRules = [
  { required: true, message: '请输入新密码' },
  { min: 8, message: '密码长度不能少于 8 位' },
  { pattern: /[A-Z]/, message: '密码必须包含至少 1 个大写字母' },
  { pattern: /[a-z]/, message: '密码必须包含至少 1 个小写字母' },
  { pattern: /\d/, message: '密码必须包含至少 1 个数字' },
  { pattern: /[^A-Za-z0-9]/, message: '密码必须包含至少 1 个特殊字符' },
]

function getErrorMessage(error: any, fallback: string) {
  return error?.response?.data?.detail || error?.response?.data?.msg || fallback
}

export default function ChangePasswordModal({ open, onClose }: ChangePasswordModalProps) {
  const [form] = Form.useForm<ChangePasswordValues>()
  const setUser = useAuthStore((state) => state.setUser)
  const [msgApi, msgCtx] = message.useMessage()

  const changePasswordMut = useMutation({
    mutationFn: (values: ChangePasswordValues) => authApi.changePassword(values.old_password, values.new_password),
    onSuccess: async () => {
      const nextUser = await authApi.me()
      setUser(nextUser)
      form.resetFields()
      onClose()
      msgApi.success('密码已修改，下次登录使用新密码')
    },
    onError: (error: any) => msgApi.error(getErrorMessage(error, '修改失败')),
  })

  return (
    <>
      {msgCtx}
      <Modal
        title="修改密码"
        open={open}
        maskClosable={false}
        onCancel={() => {
          form.resetFields()
          onClose()
        }}
        okText="修改密码"
        cancelText="取消"
        onOk={() => form.submit()}
        confirmLoading={changePasswordMut.isPending}
        destroyOnClose
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="修改成功后请使用新密码登录"
          description="密码至少 8 位，且需包含大小写字母、数字和特殊字符。"
        />
        <Form form={form} layout="vertical" onFinish={(values) => changePasswordMut.mutate(values)}>
          <Form.Item
            name="old_password"
            label="当前密码"
            rules={[{ required: true, message: '请输入当前密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
          </Form.Item>
          <Form.Item name="new_password" label="新密码" rules={passwordRules}>
            <Input.Password prefix={<LockOutlined />} autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label="确认新密码"
            dependencies={['new_password']}
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
            <Input.Password prefix={<LockOutlined />} autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
