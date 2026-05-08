import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  Row,
  Space,
  Statistic,
  Tag,
  Typography,
  message,
} from 'antd'
import { ReloadOutlined, SafetyCertificateOutlined, UploadOutlined } from '@ant-design/icons'
import { licenseApi, type LicenseStatus } from '@/api/license'

const { TextArea } = Input
const { Text } = Typography

const statusColor: Record<string, string> = {
  trial: 'gold',
  licensed: 'green',
  expired: 'red',
  invalid: 'red',
}

const statusLabel: Record<string, string> = {
  trial: '试用中',
  licensed: '正式授权',
  expired: '已过期',
  invalid: '无效',
}

function formatDate(value?: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

export default function LicensePage() {
  const [status, setStatus] = useState<LicenseStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [activating, setActivating] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [licenseText, setLicenseText] = useState('')
  const [activationCode, setActivationCode] = useState('')
  const [customerId, setCustomerId] = useState('')

  const loadStatus = useCallback(async () => {
    setLoading(true)
    try {
      const nextStatus = await licenseApi.status()
      setStatus(nextStatus)
      if (nextStatus.activation_customer_id && nextStatus.activation_customer_id !== 'trial') {
        setCustomerId((current) => current || nextStatus.activation_customer_id || '')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadStatus()
  }, [loadStatus])

  const alertType = useMemo(() => {
    if (!status) return 'info'
    if (status.status === 'licensed') return 'success'
    if (status.status === 'trial') return 'warning'
    return 'error'
  }, [status])

  const handleImport = async () => {
    if (!licenseText.trim()) {
      message.warning('请粘贴 License JSON')
      return
    }
    setImporting(true)
    try {
      let payload: string | Record<string, unknown> = licenseText
      try {
        payload = JSON.parse(licenseText)
      } catch {
        payload = licenseText
      }
      await licenseApi.import(payload)
      message.success('License 导入成功')
      setLicenseText('')
      await loadStatus()
    } catch (error: any) {
      message.error(error?.response?.data?.detail || 'License 导入失败')
    } finally {
      setImporting(false)
    }
  }

  const handleActivate = async () => {
    if (!activationCode.trim()) {
      message.warning('请输入激活码')
      return
    }
    setActivating(true)
    try {
      await licenseApi.activate({
        activation_code: activationCode.trim(),
        customer_id: customerId.trim() || undefined,
      })
      message.success('License 激活成功')
      setActivationCode('')
      await loadStatus()
    } catch (error: any) {
      message.error(error?.response?.data?.detail || 'License 激活失败')
    } finally {
      setActivating(false)
    }
  }

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await licenseApi.refresh()
      message.success('License 刷新成功')
      await loadStatus()
    } catch (error: any) {
      message.error(error?.response?.data?.detail || 'License 刷新失败')
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <SafetyCertificateOutlined style={{ fontSize: 22, color: '#165DFF' }} />
          <Typography.Title level={4} style={{ margin: 0 }}>授权管理</Typography.Title>
        </Space>
        <Button icon={<ReloadOutlined />} onClick={loadStatus} loading={loading}>刷新</Button>
      </Space>

      <Alert
        type={(status?.warning_level === 'critical' ? 'error' : status?.warning_level === 'warning' ? 'warning' : alertType) as any}
        showIcon
        style={{ marginBottom: 16 }}
        message={
          status?.needs_renewal
            ? `授权将在 ${status.days_remaining ?? 0} 天后到期`
            : status ? statusLabel[status.status] || status.status : '读取授权状态中'
        }
        description={status?.needs_renewal ? '请及时完成续期或联网刷新，避免到期后核心功能被限制。' : status?.reason || '正在检查当前部署的授权状态'}
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <Card loading={loading}>
            <Statistic
              title="剩余天数"
              value={status?.days_remaining ?? 0}
              suffix="天"
              valueStyle={{ color: status?.status === 'expired' ? '#cf1322' : undefined }}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card loading={loading}>
            <Statistic title="版本" value={status?.edition || '-'} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card loading={loading}>
            <Statistic title="来源" value={status?.source || '-'} />
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card title="当前授权" loading={loading}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="状态">
                <Tag color={statusColor[status?.status || ''] || 'default'}>
                  {status ? statusLabel[status.status] || status.status : '-'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="License ID">{status?.license_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="客户 ID">{status?.customer_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="激活客户 ID">{status?.activation_customer_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="客户名称">{status?.company_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="在线激活 ID">{status?.activation_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="远端状态">{status?.remote_status || '-'}</Descriptions.Item>
              <Descriptions.Item label="部署指纹">{status?.deployment_fingerprint || '-'}</Descriptions.Item>
              <Descriptions.Item label="最后联网校验">{formatDate(status?.last_online_check_at)}</Descriptions.Item>
              <Descriptions.Item label="签发时间">{formatDate(status?.issued_at)}</Descriptions.Item>
              <Descriptions.Item label="生效时间">{formatDate(status?.not_before)}</Descriptions.Item>
              <Descriptions.Item label="过期时间">{formatDate(status?.expires_at)}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title="权益与额度" loading={loading}>
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary">功能模块</Text>
              <div style={{ marginTop: 8 }}>
                {(status?.features || []).map((feature) => (
                  <Tag key={feature} color="blue" style={{ marginBottom: 6 }}>{feature}</Tag>
                ))}
                {!status?.features?.length && <Text type="secondary">-</Text>}
              </div>
            </div>
            <div>
              <Text type="secondary">额度限制</Text>
              <div style={{ marginTop: 8 }}>
                {Object.entries(status?.limits || {}).map(([key, value]) => (
                  <Tag key={key} color="purple" style={{ marginBottom: 6 }}>{key}: {String(value)}</Tag>
                ))}
                {!Object.keys(status?.limits || {}).length && <Text type="secondary">不限</Text>}
              </div>
            </div>
          </Card>
        </Col>

        <Col xs={24}>
          <Card title="在线激活与续期">
            <Form layout="vertical">
              <Row gutter={12}>
                <Col xs={24} md={10}>
                  <Form.Item label="激活码">
                    <Input
                      value={activationCode}
                      onChange={(event) => setActivationCode(event.target.value)}
                      placeholder="请输入授权激活码"
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item label="客户 ID">
                    <Input
                      value={customerId}
                      onChange={(event) => setCustomerId(event.target.value)}
                      placeholder="未填写时使用后端配置"
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={6}>
                  <Form.Item label=" ">
                    <Space>
                      <Button type="primary" onClick={handleActivate} loading={activating}>
                        在线激活
                      </Button>
                      <Button onClick={handleRefresh} loading={refreshing}>
                        联网刷新
                      </Button>
                    </Space>
                  </Form.Item>
                </Col>
              </Row>
            </Form>
          </Card>
        </Col>

        <Col xs={24}>
          <Card title="导入离线 License">
            <Form layout="vertical">
              <Form.Item label="License JSON">
                <TextArea
                  rows={10}
                  value={licenseText}
                  onChange={(event) => setLicenseText(event.target.value)}
                  placeholder='{"payload": {...}, "signature": "..."}'
                />
              </Form.Item>
              <Button type="primary" icon={<UploadOutlined />} onClick={handleImport} loading={importing}>
                导入 License
              </Button>
            </Form>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
