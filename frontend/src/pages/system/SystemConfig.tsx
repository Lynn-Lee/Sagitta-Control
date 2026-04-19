import { useEffect, useState } from 'react'
import {
  Alert, Button, Card, Divider, Form, Input,
  message, Space, Switch, Tabs, Typography, Grid,
} from 'antd'
import { ApiOutlined, SaveOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import PageHeader from '@/components/common/PageHeader'
import SectionLoading from '@/components/common/SectionLoading'
import TableEmptyState from '@/components/common/TableEmptyState'

const { Text } = Typography
const { useBreakpoint } = Grid

// 平台图标：与登录页保持一致，使用 public/icons/ 官方矢量图
const PlatformImg = ({ src, alt }: { src: string; alt: string }) => (
  <img src={src} alt={alt} width={14} height={14}
    style={{ objectFit: 'contain', verticalAlign: 'middle', marginRight: 5 }} />
)

const GROUP_LABEL: Record<string, React.ReactNode> = {
  basic:    <span>⚙️ 基础设置</span>,
  mail:     <span>📧 邮件通知</span>,
  dingtalk: <span><PlatformImg src="/icons/dingtalk.svg" alt="钉钉" />钉钉通知</span>,
  wecom:    <span><PlatformImg src="/icons/wecom.svg"    alt="企微" />企业微信通知</span>,
  feishu:   <span><PlatformImg src="/icons/feishu.svg"   alt="飞书" />飞书通知</span>,
  ldap:     <span><PlatformImg src="/icons/ldap.svg"     alt="LDAP" />LDAP 认证</span>,
  ai:       <span>🤖 AI 功能</span>,
  cas:      <span><PlatformImg src="/icons/cas.svg" alt="CAS" />CAS SSO</span>,
}

function TestButton({ label, onTest }: { label: string; onTest: () => Promise<any> }) {
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
      <Button icon={<ApiOutlined />} loading={loading} onClick={handleTest} size="small">
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
        <Form.Item label="连通性测试">
          <TestButton label="发送钉钉测试消息" onTest={() =>
            apiClient.post('/system/config/test/dingtalk/').then(r => r.data)} />
        </Form.Item>
      )}
      {group === 'wecom' && (
        <Form.Item label="连通性测试">
          <TestButton label="发送企微测试消息" onTest={() =>
            apiClient.post('/system/config/test/wecom/').then(r => r.data)} />
        </Form.Item>
      )}
      {group === 'feishu' && (
        <Form.Item label="连通性测试">
          <TestButton label="发送飞书测试消息" onTest={() =>
            apiClient.post('/system/config/test/feishu/').then(r => r.data)} />
        </Form.Item>
      )}
      {group === 'ldap' && (
        <Form.Item label="连通性测试">
          <TestButton label="测试 LDAP 连接" onTest={() =>
            apiClient.post('/system/config/test/ldap/', {}).then(r => r.data)} />
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
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '保存失败'),
  })

  const configs = data?.configs || {}
  const groups = data?.groups || {}

  const tabItems = Object.entries(groups).map(([key, label]) => ({
    key,
    label: GROUP_LABEL[key] ?? <span>⚙️ {label as string}</span>,
    children: configs[key]?.length ? (
      <ConfigGroup group={key} items={configs[key]} form={form} />
    ) : (
      <TableEmptyState title="暂无配置项" />
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
          <Form form={form} layout="vertical" style={{ maxWidth: 680 }}>
            <Tabs items={tabItems} tabBarGutter={4} />
          </Form>
        )}
      </Card>
    </div>
  )
}
