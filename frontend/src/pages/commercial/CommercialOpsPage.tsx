import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Progress,
  Row,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  CheckCircleOutlined,
  CloudDownloadOutlined,
  FileDoneOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  ToolOutlined,
} from '@ant-design/icons'
import { commercialApi, type AlertEvent, type OnboardingStatus } from '@/api/commercial'
import TableEmptyState from '@/components/common/TableEmptyState'

const { Text, Paragraph } = Typography

const reportTypes = [
  { key: 'high_risk_operations', label: '高风险操作' },
  { key: 'query_export', label: '查询导出' },
  { key: 'permission_changes', label: '权限变更' },
  { key: 'license_operations', label: 'License 操作' },
]

const licenseStatusColor: Record<string, string> = {
  trial: 'gold',
  licensed: 'green',
  expired: 'red',
  invalid: 'red',
}

const licenseStatusLabel: Record<string, string> = {
  trial: '试用中',
  licensed: '正式授权',
  expired: '已过期',
  invalid: '无效',
}

export default function CommercialOpsPage() {
  const navigate = useNavigate()
  const [onboarding, setOnboarding] = useState<OnboardingStatus | null>(null)
  const [acceptanceRunId, setAcceptanceRunId] = useState<number | null>(null)
  const [diagnosticId, setDiagnosticId] = useState<number | null>(null)
  const [report, setReport] = useState<any>(null)
  const [matrix, setMatrix] = useState<any>(null)
  const [about, setAbout] = useState<any>(null)
  const [retention, setRetention] = useState<any>(null)
  const [alerts, setAlerts] = useState<AlertEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()
  const [retentionForm] = Form.useForm()

  const loadAll = async () => {
    setLoading(true)
    try {
      const [onboardingData, matrixData, alertData, aboutData, retentionData] = await Promise.all([
        commercialApi.onboardingStatus(),
        commercialApi.engineMatrix(),
        commercialApi.alertEvents({ page_size: 50 }),
        commercialApi.supportAbout(),
        commercialApi.retentionPolicy(),
      ])
      setOnboarding(onboardingData)
      setMatrix(matrixData)
      setAlerts(alertData.items || [])
      setAbout(aboutData)
      setRetention(retentionData)
      retentionForm.setFieldsValue(Object.fromEntries((retentionData.items || []).map((item: any) => [item.key, item.days])))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [])

  const createAcceptance = async () => {
    const values = form.getFieldsValue()
    const run = await commercialApi.createAcceptanceRun({
      instance_id: values.instance_id || undefined,
      db_name: values.db_name || '',
    })
    setAcceptanceRunId(run.id)
    message.success('验收报告已生成')
    await loadAll()
  }

  const createDiagnostic = async () => {
    const bundle = await commercialApi.createDiagnosticBundle()
    setDiagnosticId(bundle.id)
    message.success('诊断包已生成')
  }

  const loadReport = async (type: string) => {
    const data = await commercialApi.complianceReport(type)
    setReport(data)
  }

  const saveRetention = async () => {
    const values = retentionForm.getFieldsValue()
    const data = await commercialApi.updateRetentionPolicy(values)
    setRetention(data)
    retentionForm.setFieldsValue(Object.fromEntries((data.items || []).map((item: any) => [item.key, item.days])))
    message.success('保留策略已保存')
  }

  const cleanupRetention = async (category: string) => {
    const result = await commercialApi.cleanupRetention(category)
    message.success(`已清理 ${result.deleted || 0} 条过期数据`)
  }

  const handleAlertAction = async (id: number, action: 'ack' | 'silence' | 'close') => {
    if (action === 'ack') await commercialApi.ackAlert(id)
    if (action === 'silence') await commercialApi.silenceAlert(id, 60)
    if (action === 'close') await commercialApi.closeAlert(id, '交付与支持页面关闭')
    message.success('告警状态已更新')
    const data = await commercialApi.alertEvents({ page_size: 50 })
    setAlerts(data.items || [])
  }

  const downloadReport = async (kind: 'md' | 'json') => {
    if (!acceptanceRunId) return
    await commercialApi.downloadFile(
      `/system/delivery/acceptance-runs/${acceptanceRunId}/report.${kind}`,
      `acceptance-run-${acceptanceRunId}.${kind}`,
    )
  }

  const downloadDiagnostic = async () => {
    if (!diagnosticId) return
    await commercialApi.downloadFile(
      `/system/delivery/diagnostic-bundles/${diagnosticId}/download`,
      `diagnostic-bundle-${diagnosticId}.json`,
    )
  }

  return (
    <div>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <SafetyCertificateOutlined style={{ fontSize: 22, color: '#165DFF' }} />
          <Typography.Title level={4} style={{ margin: 0 }}>交付与支持</Typography.Title>
        </Space>
        <Button className="sagitta-action-btn sagitta-action-btn--refresh" icon={<ReloadOutlined />} loading={loading} onClick={loadAll}>刷新</Button>
      </Space>

      <Tabs
        items={[
          {
            key: 'onboarding',
            label: '实施交付',
            children: (
              <Row gutter={[16, 16]}>
                <Col span={24}>
                  <Card>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Text strong>实施进度</Text>
                      <Progress percent={onboarding ? Math.round((onboarding.completed_count / onboarding.total) * 100) : 0} />
                      <Row gutter={[12, 12]}>
                        {(onboarding?.steps || []).map(step => (
                          <Col xs={24} md={8} key={step.key}>
                            <Card size="small">
                              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                                <Space>
                                  <CheckCircleOutlined style={{ color: step.completed ? '#00A870' : '#A0AEC0' }} />
                                  <Text>{step.label}</Text>
                                </Space>
                                <Button size="small" disabled={step.completed} onClick={() => commercialApi.completeStep(step.key).then(setOnboarding)}>完成</Button>
                              </Space>
                            </Card>
                          </Col>
                        ))}
                      </Row>
                    </Space>
                  </Card>
                </Col>
                <Col span={24}>
                  <Card title="交付验收与诊断包">
                    <Form form={form} layout="inline">
                      <Form.Item name="instance_id" label="实例 ID">
                        <InputNumber min={1} placeholder="可选" />
                      </Form.Item>
                      <Form.Item name="db_name" label="数据库">
                        <Input placeholder="可选" />
                      </Form.Item>
                      <Form.Item>
                        <Button icon={<FileDoneOutlined />} type="primary" onClick={createAcceptance}>生成验收报告</Button>
                      </Form.Item>
                      <Form.Item>
                        <Button icon={<ToolOutlined />} onClick={createDiagnostic}>生成诊断包</Button>
                      </Form.Item>
                    </Form>
                    <Space style={{ marginTop: 16 }}>
                      {acceptanceRunId && (
                        <>
                          <Button icon={<CloudDownloadOutlined />} onClick={() => downloadReport('md')}>下载 Markdown</Button>
                          <Button icon={<CloudDownloadOutlined />} onClick={() => downloadReport('json')}>下载 JSON</Button>
                        </>
                      )}
                      {diagnosticId && (
                        <Button icon={<CloudDownloadOutlined />} onClick={downloadDiagnostic}>下载诊断包</Button>
                      )}
                    </Space>
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: 'compliance',
            label: '合规报表',
            children: (
              <Card>
                <Space wrap style={{ marginBottom: 16 }}>
                  {reportTypes.map(item => (
                    <Button key={item.key} onClick={() => loadReport(item.key)}>{item.label}</Button>
                  ))}
                </Space>
                {report ? (
                  <Alert
                    type="info"
                    showIcon
                    message={`${report.report_type}：${report.total} 条记录`}
                    description={<Paragraph style={{ whiteSpace: 'pre-wrap', maxHeight: 360, overflow: 'auto' }}>{report.markdown}</Paragraph>}
                  />
                ) : <TableEmptyState title="请选择一个报表类型" />}
                <Card size="small" title="保留策略" style={{ marginTop: 16 }}>
                  <Form form={retentionForm} layout="inline">
                    {(retention?.items || []).map((item: any) => (
                      <Form.Item key={item.key} name={item.key} label={item.label}>
                        <InputNumber min={1} max={3650} addonAfter="天" />
                      </Form.Item>
                    ))}
                    <Form.Item>
                      <Button type="primary" onClick={saveRetention}>保存</Button>
                    </Form.Item>
                  </Form>
                  <Space wrap style={{ marginTop: 12 }}>
                    {(retention?.items || []).map((item: any) => (
                      <Popconfirm
                        key={item.key}
                        title={`清理超过 ${item.days} 天的${item.label}？`}
                        onConfirm={() => cleanupRetention(item.key)}
                      >
                        <Button size="small">清理{item.label}</Button>
                      </Popconfirm>
                    ))}
                  </Space>
                </Card>
              </Card>
            ),
          },
          {
            key: 'alerts',
            label: '告警中心',
            children: (
              <Table
                dataSource={alerts}
                rowKey="id"
                pagination={false}
                locale={{ emptyText: <TableEmptyState title="暂无告警事件" /> }}
                columns={[
                  { title: '状态', dataIndex: 'status', render: value => <Tag>{value}</Tag> },
                  { title: '级别', dataIndex: 'severity', render: value => <Tag color={value === 'critical' ? 'red' : 'orange'}>{value}</Tag> },
                  { title: '实例', dataIndex: 'instance_name' },
                  { title: '规则', dataIndex: 'rule_key' },
                  { title: '详情', dataIndex: 'message' },
                  { title: '最近触发', dataIndex: 'last_seen_at' },
                  {
                    title: '操作',
                    width: 210,
                    render: (_, row) => (
                      <Space>
                        <Button size="small" onClick={() => handleAlertAction(row.id, 'ack')}>确认</Button>
                        <Button size="small" onClick={() => handleAlertAction(row.id, 'silence')}>静默</Button>
                        <Button size="small" danger onClick={() => handleAlertAction(row.id, 'close')}>关闭</Button>
                      </Space>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: 'support',
            label: '支持与关于',
            children: (
              <Space direction="vertical" style={{ width: '100%' }} size={16}>
                <Card title="支持与关于">
                  <Descriptions column={{ xs: 1, md: 2 }} size="small">
                    <Descriptions.Item label="版本">{about?.version || '-'}</Descriptions.Item>
                    <Descriptions.Item label="部署模式">{about?.deployment_mode || '-'}</Descriptions.Item>
                    <Descriptions.Item label="授权项目">{about ? `${about.project}（${about.project_code}）` : '-'}</Descriptions.Item>
                    <Descriptions.Item label="License">
                      <Space size={8} wrap>
                        <Tag color={licenseStatusColor[about?.license?.status || ''] || 'default'}>
                          {licenseStatusLabel[about?.license?.status || ''] || about?.license?.status || '-'}
                        </Tag>
                        <Button size="small" onClick={() => navigate('/system/license')}>前往授权管理</Button>
                      </Space>
                    </Descriptions.Item>
                    <Descriptions.Item label="支持邮箱">{about?.support?.email || '-'}</Descriptions.Item>
                    <Descriptions.Item label="授权中心">{about?.support?.license_server || '-'}</Descriptions.Item>
                  </Descriptions>
                  <Space wrap style={{ marginTop: 12 }}>
                    {(about?.docs || []).map((doc: any) => (
                      <Typography.Link key={doc.path} href={doc.path} target="_blank">{doc.label}</Typography.Link>
                    ))}
                  </Space>
                </Card>
                <Card title="引擎支持矩阵">
                  <Table
                    dataSource={matrix?.items || []}
                    rowKey="db_type"
                    pagination={false}
                    scroll={{ x: 1200 }}
                    columns={[
                      { title: '数据库', dataIndex: 'label', fixed: 'left', width: 150 },
                      { title: '支持等级', dataIndex: 'support_label', width: 170, render: value => <Tag color="blue">{value}</Tag> },
                      ...Object.entries(matrix?.capability_labels || {}).map(([key, label]) => ({
                        title: label as string,
                        width: 110,
                        render: (_: any, row: any) => row.capabilities?.[key] ? <Tag color="green">支持</Tag> : <Tag>不承诺</Tag>,
                      })),
                      { title: '验证要求', dataIndex: 'validation_required', width: 260 },
                    ]}
                  />
                </Card>
              </Space>
            ),
          },
        ]}
      />
    </div>
  )
}
