import { useEffect, useState } from 'react'
import {
  Alert, Button, Card, Divider, Form, Input,
  message, Space, Switch, Tabs, Typography, Grid, Tooltip, Upload,
} from 'antd'
import {
  ApiOutlined,
  GlobalOutlined,
  KeyOutlined,
  SaveOutlined,
  SendOutlined,
  UploadOutlined,
  UndoOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import PageHeader from '@/components/common/PageHeader'
import SectionLoading from '@/components/common/SectionLoading'
import TableEmptyState from '@/components/common/TableEmptyState'

const { Text } = Typography
const { useBreakpoint } = Grid

const tabLabelStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  whiteSpace: 'nowrap',
}

const CompactTabLabel = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <Tooltip title={title}>
    <span style={tabLabelStyle}>{children}</span>
  </Tooltip>
)

// 平台图标：与登录页保持一致，使用 public/icons/ 官方矢量图
const PlatformImg = ({ src, alt }: { src: string; alt: string }) => (
  <img src={src} alt={alt} width={14} height={14}
    style={{ objectFit: 'contain', verticalAlign: 'middle', marginRight: 5 }} />
)

const TabIcon = ({ children }: { children: React.ReactNode }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', marginRight: 5 }}>
    {children}
  </span>
)

const readFileAsDataUrl = (file: File) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => resolve(String(reader.result || ''))
  reader.onerror = reject
  reader.readAsDataURL(file)
})

const GROUP_LABEL: Record<string, React.ReactNode> = {
  basic:    <CompactTabLabel title="基础设置">⚙️ 基础</CompactTabLabel>,
  mail:     <CompactTabLabel title="邮件通知">📧 邮件</CompactTabLabel>,
  dingtalk: <CompactTabLabel title="钉钉通知"><PlatformImg src="/icons/dingtalk.svg" alt="钉钉" />钉钉</CompactTabLabel>,
  wecom:    <CompactTabLabel title="企业微信通知"><PlatformImg src="/icons/wecom.svg" alt="企微" />企微</CompactTabLabel>,
  feishu:   <CompactTabLabel title="飞书通知"><PlatformImg src="/icons/feishu.svg" alt="飞书" />飞书</CompactTabLabel>,
  ldap:     <CompactTabLabel title="LDAP 认证"><PlatformImg src="/icons/ldap.svg" alt="LDAP" />LDAP</CompactTabLabel>,
  cas:      <CompactTabLabel title="CAS SSO"><TabIcon><GlobalOutlined style={{ color: '#0f766e' }} /></TabIcon>CAS</CompactTabLabel>,
  oidc:     <CompactTabLabel title="OIDC SSO"><TabIcon><KeyOutlined style={{ color: '#2f80ed' }} /></TabIcon>OIDC</CompactTabLabel>,
  sms:      <CompactTabLabel title="短信验证码"><PlatformImg src="/icons/sms.svg" alt="短信" />短信</CompactTabLabel>,
  ai:       <CompactTabLabel title="AI 功能">🤖 AI</CompactTabLabel>,
}

function TestButton({
  label,
  icon,
  onTest,
}: {
  label: string
  icon?: React.ReactNode
  onTest: () => Promise<any>
}) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null)

  const handleTest = async () => {
    setLoading(true)
    setResult(null)
    try {
      const r = await onTest()
      setResult(r)
    } catch (e: any) {
      setResult({ success: false, message: e.response?.data?.detail || '请求失败' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Space direction="vertical" size={4}>
      <Button className="sagitta-action-btn sagitta-action-btn--inspect" icon={icon ?? <ApiOutlined />} loading={loading} onClick={handleTest} size="small">
        {label}
      </Button>
      {result && (
        <Alert type={result.success ? 'success' : 'error'} showIcon
          message={result.message} style={{ fontSize: 12, padding: '4px 8px' }} />
      )}
    </Space>
  )
}

function ConfigGroup({ group, items, form }: { group: string; items: any[]; form: any }) {
  return (
    <div>
      {items.map((item: any) => {
        const isBool = item.key.includes('enabled') || item.key === 'mail_use_ssl'
        const isSensitive = item.is_sensitive
        const isPasswordField = item.key.includes('password') || item.key.includes('secret') || item.key.includes('token') || item.key.includes('webhook')

        if (item.key === 'platform_logo_url') {
          return (
            <Form.Item
              key={item.key}
              label={item.description}
              extra="支持图片 URL 或上传 PNG/JPG/SVG。留空时使用默认 Logo。"
              style={{ marginBottom: 14 }}
            >
              <Form.Item name={item.key} noStyle>
                <Input.TextArea
                  placeholder="https://example.com/logo.png 或 data:image/png;base64,..."
                  autoSize={{ minRows: 2, maxRows: 4 }}
                />
              </Form.Item>
              <Space style={{ marginTop: 8, alignItems: 'center' }} wrap>
                <Upload
                  accept="image/png,image/jpeg,image/svg+xml,image/webp"
                  showUploadList={false}
                  beforeUpload={async (file) => {
                    if (!file.type.startsWith('image/')) {
                      message.error('请选择图片文件')
                      return Upload.LIST_IGNORE
                    }
                    if (file.size > 512 * 1024) {
                      message.error('Logo 图片建议不超过 512KB')
                      return Upload.LIST_IGNORE
                    }
                    const dataUrl = await readFileAsDataUrl(file)
                    form.setFieldValue(item.key, dataUrl)
                    return false
                  }}
                >
                  <Button className="sagitta-action-btn sagitta-action-btn--upload" icon={<UploadOutlined />}>选择图片</Button>
                </Upload>
                <Button className="sagitta-action-btn sagitta-action-btn--neutral" icon={<UndoOutlined />} onClick={() => form.setFieldValue(item.key, '')}>
                  恢复默认 Logo
                </Button>
                <Form.Item noStyle shouldUpdate={(prev, next) => prev[item.key] !== next[item.key]}>
                  {() => {
                    const logoUrl = form.getFieldValue(item.key)
                    return logoUrl ? (
                      <img
                        src={logoUrl}
                        alt="Logo 预览"
                        style={{ width: 40, height: 40, objectFit: 'contain', border: '1px solid #E5E6EB', borderRadius: 6, padding: 4 }}
                      />
                    ) : null
                  }}
                </Form.Item>
              </Space>
            </Form.Item>
          )
        }

        return (
          <Form.Item
            key={item.key}
            name={item.key}
            label={
              <Space size={4}>
                <span>{item.description}</span>
                {isSensitive && (
                  <Text style={{ fontSize: 10, color: '#fa8c16', border: '1px solid #fa8c16', borderRadius: 2, padding: '0 4px' }}>
                    加密存储
                  </Text>
                )}
              </Space>
            }
            valuePropName={isBool ? 'checked' : 'value'}
            style={{ marginBottom: 14 }}
          >
            {isBool ? (
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            ) : (isSensitive || isPasswordField) ? (
              <Input.Password
                placeholder={item.value === '******' ? '已保存（留空则不修改）' : ''}
                autoComplete="new-password"
              />
            ) : (
              <Input placeholder={item.description} />
            )}
          </Form.Item>
        )
      })}

      {/* 各渠道连通性测试 */}
      <Divider style={{ margin: '8px 0 16px' }} />
      {group === 'mail' && (
        <Form.Item label="发送测试邮件">
          <Space>
            <Form.Item name="_test_mail_to" noStyle>
              <Input placeholder="收件人邮箱" style={{ width: 220 }} />
            </Form.Item>
            <TestButton label="发送测试" onTest={async () => {
              const to = form.getFieldValue('_test_mail_to')
              if (!to) return { success: false, message: '请输入收件人邮箱' }
              return apiClient.post('/system/config/test/mail/', { to_email: to }).then(r => r.data)
            }} />
          </Space>
        </Form.Item>
      )}
      {group === 'dingtalk' && (
        <>
          <Form.Item label="连通性测试">
            <TestButton label="发送钉钉机器人测试消息" icon={<SendOutlined />} onTest={() =>
              apiClient.post('/system/config/test/dingtalk/').then(r => r.data)} />
          </Form.Item>
          <Form.Item label="精准通知测试" extra="填写系统用户 ID，将按该用户维护的钉钉/飞书/企微账号和邮箱尝试投递。">
            <Space>
              <Form.Item name="_test_notify_user_id_dingtalk" noStyle>
                <Input placeholder="用户 ID" style={{ width: 160 }} />
              </Form.Item>
              <TestButton label="发送到用户" icon={<SendOutlined />} onTest={async () => {
                const userId = Number(form.getFieldValue('_test_notify_user_id_dingtalk'))
                if (!userId) return { success: false, message: '请输入用户 ID' }
                return apiClient.post('/system/config/test/notify-user/', { user_id: userId }).then(r => r.data)
              }} />
            </Space>
          </Form.Item>
        </>
      )}
      {group === 'wecom' && (
        <>
          <Form.Item label="连通性测试">
            <TestButton label="发送企微机器人测试消息" icon={<SendOutlined />} onTest={() =>
              apiClient.post('/system/config/test/wecom/').then(r => r.data)} />
          </Form.Item>
          <Form.Item label="精准通知测试" extra="填写系统用户 ID，将按该用户维护的钉钉/飞书/企微账号和邮箱尝试投递。">
            <Space>
              <Form.Item name="_test_notify_user_id_wecom" noStyle>
                <Input placeholder="用户 ID" style={{ width: 160 }} />
              </Form.Item>
              <TestButton label="发送到用户" icon={<SendOutlined />} onTest={async () => {
                const userId = Number(form.getFieldValue('_test_notify_user_id_wecom'))
                if (!userId) return { success: false, message: '请输入用户 ID' }
                return apiClient.post('/system/config/test/notify-user/', { user_id: userId }).then(r => r.data)
              }} />
            </Space>
          </Form.Item>
        </>
      )}
      {group === 'feishu' && (
        <>
          <Form.Item label="连通性测试">
            <TestButton label="发送飞书机器人测试消息" icon={<SendOutlined />} onTest={() =>
              apiClient.post('/system/config/test/feishu/').then(r => r.data)} />
          </Form.Item>
          <Form.Item label="精准通知测试" extra="填写系统用户 ID，将按该用户维护的钉钉/飞书/企微账号和邮箱尝试投递。">
            <Space>
              <Form.Item name="_test_notify_user_id_feishu" noStyle>
                <Input placeholder="用户 ID" style={{ width: 160 }} />
              </Form.Item>
              <TestButton label="发送到用户" icon={<SendOutlined />} onTest={async () => {
                const userId = Number(form.getFieldValue('_test_notify_user_id_feishu'))
                if (!userId) return { success: false, message: '请输入用户 ID' }
                return apiClient.post('/system/config/test/notify-user/', { user_id: userId }).then(r => r.data)
              }} />
            </Space>
          </Form.Item>
        </>
      )}
      {group === 'ldap' && (
        <Form.Item label="连通性测试">
          <TestButton label="测试 LDAP 连接" onTest={() =>
            apiClient.post('/system/config/test/ldap/', {}).then(r => r.data)} />
        </Form.Item>
      )}
      {group === 'cas' && (
        <Form.Item label="连通性测试">
          <TestButton label="测试 CAS 连接" onTest={() =>
            apiClient.post('/system/config/test/cas/', {}).then(r => r.data)} />
        </Form.Item>
      )}
      {group === 'oidc' && (
        <Form.Item label="连通性测试">
          <TestButton label="测试 OIDC 连接" onTest={() =>
            apiClient.post('/system/config/test/oidc/', {}).then(r => r.data)} />
        </Form.Item>
      )}
    </div>
  )
}

export default function SystemConfig() {
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const [form] = Form.useForm()
  const [msgApi, msgCtx] = message.useMessage()
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['system-config'],
    queryFn: () => apiClient.get('/system/config/').then(r => r.data),
  })

  // 正确的表单回填：数据加载后统一 setFieldsValue
  useEffect(() => {
    if (!data?.configs) return
    const values: Record<string, any> = {}
    Object.values(data.configs).flat().forEach((item: any) => {
      const isBool = item.key.includes('enabled') || item.key === 'mail_use_ssl'
      if (isBool) {
        values[item.key] = item.value === 'true'
      } else if (item.value === '******') {
        // 敏感字段：已有保存值，显示为空（placeholder 提示），留空不覆盖
        values[item.key] = ''
      } else {
        values[item.key] = item.value || ''
      }
    })
    form.setFieldsValue(values)
  }, [data, form])

  const saveMut = useMutation({
    mutationFn: async (values: Record<string, any>) => {
      const updates: Record<string, string> = {}
      for (const [k, v] of Object.entries(values)) {
        if (k.startsWith('_')) continue  // 跳过测试用临时字段
        if (v === null || v === undefined) continue
        updates[k] = typeof v === 'boolean' ? (v ? 'true' : 'false') : String(v)
      }
      return apiClient.post('/system/config/', { updates }).then(r => r.data)
    },
    onSuccess: (res) => {
      msgApi.success(`已保存 ${res.count ?? ''} 个配置项`)
      qc.invalidateQueries({ queryKey: ['system-config'] })
      qc.invalidateQueries({ queryKey: ['public-branding'] })
    },
    onError: (e: any) => msgApi.error(e.response?.data?.detail || e.response?.data?.msg || '保存失败'),
  })

  const configs = data?.configs || {}
  const groups = data?.groups || {}

  const tabItems = Object.entries(groups).map(([key, label]) => ({
    key,
    label: GROUP_LABEL[key] ?? <CompactTabLabel title={label as string}>⚙️ {label as string}</CompactTabLabel>,
    children: (
      <div style={{ maxWidth: 760 }}>
        {configs[key]?.length ? (
          <ConfigGroup group={key} items={configs[key]} form={form} />
        ) : (
          <TableEmptyState title="暂无配置项" />
        )}
      </div>
    ),
  }))

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="系统配置"
        marginBottom={20}
        actions={(
          <Button type="primary" icon={<SaveOutlined />} loading={saveMut.isPending}
            onClick={() => form.validateFields().then(v => saveMut.mutate(v))}
            style={isMobile ? { width: '100%' } : undefined}>
            保存所有配置
          </Button>
        )}
      />

      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}>
        {isLoading ? (
          <SectionLoading text="加载配置中..." />
        ) : (
          <Form form={form} layout="vertical" style={{ width: '100%' }}>
            <Tabs
              className="system-config-tabs"
              items={tabItems}
              tabBarGutter={2}
            />
          </Form>
        )}
      </Card>
    </div>
  )
}
