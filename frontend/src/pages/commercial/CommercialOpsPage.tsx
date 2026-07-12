import { useCallback, useEffect, useRef, useState } from 'react'
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
  BellOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CloseOutlined,
  CopyOutlined,
  CloudDownloadOutlined,
  DeleteOutlined,
  FileDoneOutlined,
  FileSearchOutlined,
  PauseCircleOutlined,
  RightOutlined,
  ReloadOutlined,
  RocketOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
  SettingOutlined,
  ToolOutlined,
} from '@ant-design/icons'
import { commercialApi, type AlertEvent, type OnboardingStatus, type OnboardingStep, type ReadinessCheck, type SupportAbout } from '@/api/commercial'
import TableEmptyState from '@/components/common/TableEmptyState'
import { TruncatedCell } from '@/components/common/TruncatedCell'
import { formatDateTime } from '@/utils/datetime'
import {
  licenseStatusColor,
  licenseStatusLabel,
  nowrapText,
  onboardingStatusColor,
  onboardingStatusLabel,
  readinessColor,
  reportTypes,
  supportLevelColor,
} from './commercialOpsConfig'

const { Text, Paragraph } = Typography

export default function CommercialOpsPage() {
  const navigate = useNavigate()
  const [onboarding, setOnboarding] = useState<OnboardingStatus | null>(null)
  const [acceptanceRunId, setAcceptanceRunId] = useState<number | null>(null)
  const [diagnosticId, setDiagnosticId] = useState<number | null>(null)
  const [report, setReport] = useState<any>(null)
  const [matrix, setMatrix] = useState<any>(null)
  const [about, setAbout] = useState<SupportAbout | null>(null)
  const [retention, setRetention] = useState<any>(null)
  const [alerts, setAlerts] = useState<AlertEvent[]>([])
  const [activeTab, setActiveTab] = useState('onboarding')
  const [loading, setLoading] = useState(false)
  const [bootstrapping, setBootstrapping] = useState(false)
  const [bootstrapResult, setBootstrapResult] = useState<{ created: string[]; updated: string[]; skipped: string[] } | null>(null)
  const [form] = Form.useForm()
  const [retentionForm] = Form.useForm()
  const deliveryActionsRef = useRef<HTMLDivElement>(null)

  const loadAll = useCallback(async () => {
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
  }, [retentionForm])

  useEffect(() => {
    loadAll()
  }, [loadAll])

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

  const bootstrapTrial = async () => {
    setBootstrapping(true)
    try {
      const result = await commercialApi.bootstrapTrial()
      setBootstrapResult({
        created: result.created || [],
        updated: result.updated || [],
        skipped: result.skipped || [],
      })
      setOnboarding(result.onboarding)
      if (result.acceptance_run?.id) {
        setAcceptanceRunId(result.acceptance_run.id)
      }
      message.success('用户试用环境已初始化')
      await loadAll()
    } finally {
      setBootstrapping(false)
    }
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

  const handleAlertAction = async (id: number, action: 'ack' | 'silence' | 'resolve' | 'close') => {
    if (action === 'ack') await commercialApi.ackAlert(id)
    if (action === 'silence') await commercialApi.silenceAlert(id, 60)
    if (action === 'resolve') await commercialApi.resolveAlert(id)
    if (action === 'close') await commercialApi.closeAlert(id, '交付与支持页面关闭')
    message.success('告警状态已更新')
    const data = await commercialApi.alertEvents({ page_size: 50 })
    setAlerts(data.items || [])
  }

  const copyText = async (value: string, successText: string) => {
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
    } catch {
      const textarea = document.createElement('textarea')
      textarea.value = value
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      textarea.remove()
    }
    message.success(successText)
  }

  const goPath = (path: string) => {
    if (!path) return
    if (path === '/commercial') {
      setActiveTab('onboarding')
      window.setTimeout(() => {
        deliveryActionsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 0)
      return
    }
    navigate(path)
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

  const completeOnboardingStep = async (step: OnboardingStep) => {
    const next = await commercialApi.completeStep(step.key)
    setOnboarding(next)
    message.success(`${step.label} 已标记完成`)
  }

  const handleOnboardingStepAction = async (step: OnboardingStep) => {
    if (step.quick_action === 'trial_bootstrap') {
      await bootstrapTrial()
      return
    }
    if (step.quick_action === 'generate_acceptance') {
      await createAcceptance()
      return
    }
    goPath(step.path)
  }

  const renderReadinessAction = (item: ReadinessCheck) => (
    <Button className="sagitta-action-btn sagitta-action-btn--manage" icon={<RightOutlined />} onClick={() => goPath(item.path)}>
      去处理
    </Button>
  )

  const onboardingColumns = [
    {
      title: '阶段',
      width: 120,
      render: (_: unknown, row: OnboardingStep) => <Tag color={row.required ? 'red' : 'blue'}>{row.category || '实施步骤'}</Tag>,
    },
    {
      title: '检查项',
      width: 190,
      render: (_: unknown, row: OnboardingStep) => (
        <Space direction="vertical" size={2}>
          <Space size={6}>
            <CheckCircleOutlined style={{ color: row.completed ? '#00A870' : '#A0AEC0' }} />
            <Text strong>{row.label}</Text>
          </Space>
          <Text type="secondary">{row.required ? '上线必需' : '建议补齐'}</Text>
        </Space>
      ),
    },
    {
      title: '状态',
      width: 120,
      render: (_: unknown, row: OnboardingStep) => (
        <Space direction="vertical" size={2}>
          <Tag color={onboardingStatusColor[row.status] || 'default'}>{onboardingStatusLabel[row.status] || row.status}</Tag>
          <Text type="secondary">{row.detect_source || (row.auto_detected ? '自动检测' : '待配置')}</Text>
        </Space>
      ),
    },
    {
      title: '检测依据',
      width: 220,
      render: (_: unknown, row: OnboardingStep) => <Text>{row.evidence || row.reason}</Text>,
    },
    {
      title: '建议处理',
      render: (_: unknown, row: OnboardingStep) => (
        <Space direction="vertical" size={2}>
          <Text>{row.suggested_action || row.reason}</Text>
          {row.fix_hint && <Text type="secondary">{row.fix_hint}</Text>}
        </Space>
      ),
    },
    {
      title: '操作',
      width: 220,
      render: (_: unknown, row: OnboardingStep) => (
        <Space wrap>
          <Button
            className="sagitta-action-btn sagitta-action-btn--manage"
            icon={row.quick_action === 'trial_bootstrap' ? <RocketOutlined /> : row.quick_action === 'generate_acceptance' ? <FileDoneOutlined /> : <SettingOutlined />}
            loading={bootstrapping && row.quick_action === 'trial_bootstrap'}
            onClick={() => handleOnboardingStepAction(row)}
          >
            {row.action_label || '去处理'}
          </Button>
          <Button
            className="sagitta-action-btn sagitta-action-btn--success"
            icon={<CheckCircleOutlined />}
            disabled={row.completed}
            onClick={() => completeOnboardingStep(row)}
          >
            手动完成
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <SafetyCertificateOutlined style={{ fontSize: 22, color: '#165DFF' }} />
          <Typography.Title level={4} style={{ margin: 0 }}>交付与支持</Typography.Title>
        </Space>
        <Button className="sagitta-action-btn sagitta-action-btn--refresh" icon={<ReloadOutlined />} loading={loading} onClick={loadAll}>刷新</Button>
      </Space>

      <Row gutter={[16, 16]} align="stretch" style={{ marginBottom: 16 }}>
        <Col xs={24} lg={8} style={{ display: 'flex' }}>
          <Card style={{ width: '100%', minHeight: 196 }} styles={{ body: { height: '100%' } }}>
            <Space direction="vertical" size={10} style={{ width: '100%', height: '100%' }}>
              <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                <Text strong>推广就绪度</Text>
                <Tag color={readinessColor[about?.readiness?.status || ''] || 'default'}>
                  {about?.readiness?.conclusion || '-'}
                </Tag>
              </Space>
              <Progress
                percent={about?.readiness?.score || 0}
                status={about?.readiness?.status === 'blocked' ? 'exception' : 'normal'}
              />
              <Text type="secondary">{about?.readiness?.summary || '正在读取交付支持状态'}</Text>
            </Space>
          </Card>
        </Col>
        <Col xs={24} lg={8} style={{ display: 'flex' }}>
          <Card style={{ width: '100%', minHeight: 196 }} styles={{ body: { height: '100%' } }}>
            <Space direction="vertical" size={10} style={{ width: '100%', height: '100%' }}>
              <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                <Text strong>试用与授权</Text>
                <Tag color={licenseStatusColor[about?.license?.status || ''] || 'default'}>
                  {licenseStatusLabel[about?.license?.status || ''] || about?.license?.status || '-'}
                </Tag>
              </Space>
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="客户 ID">{about?.license?.activation_customer_id || about?.license?.customer_id || '-'}</Descriptions.Item>
                <Descriptions.Item label="剩余天数">{about?.license?.days_remaining ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="到期时间">{formatDateTime(about?.license?.expires_at, '-')}</Descriptions.Item>
              </Descriptions>
              <Space wrap>
                <Button className="sagitta-action-btn sagitta-action-btn--copy" icon={<CopyOutlined />} onClick={() => copyText(about?.license?.activation_deployment_fingerprint || about?.deployment_fingerprint || '', '部署指纹已复制')}>
                  复制正式指纹
                </Button>
                <Button className="sagitta-action-btn sagitta-action-btn--manage" icon={<SafetyCertificateOutlined />} onClick={() => navigate('/system/license')}>授权管理</Button>
              </Space>
            </Space>
          </Card>
        </Col>
        <Col xs={24} lg={8} style={{ display: 'flex' }}>
          <Card style={{ width: '100%', minHeight: 196 }} styles={{ body: { height: '100%' } }}>
            <Space direction="vertical" size={10} style={{ width: '100%', height: '100%' }}>
              <Text strong>客户环境用量</Text>
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="活跃用户">{about?.usage?.active_users ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="活跃实例">{about?.usage?.active_instances ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="采集失败">{about?.runtime?.failed_monitor_collect_configs ?? '-'}</Descriptions.Item>
              </Descriptions>
              <Space wrap>
                {Object.entries(about?.usage?.db_type_distribution || {}).map(([dbType, count]) => (
                  <Tag key={dbType} color="blue">{dbType}: {count}</Tag>
                ))}
                {!Object.keys(about?.usage?.db_type_distribution || {}).length && <Text type="secondary">暂无实例分布</Text>}
              </Space>
            </Space>
          </Card>
        </Col>
        {!!about?.readiness?.action_items?.length && (
          <Col span={24}>
            <Alert
              type={about.readiness.status === 'blocked' ? 'error' : 'warning'}
              showIcon
              message="推广前待处理项"
              description={(
                <Space direction="vertical" style={{ width: '100%' }}>
                  {about.readiness.action_items.map(item => (
                    <Space key={item.key} style={{ width: '100%', justifyContent: 'space-between' }} align="start">
                      <span>
                        <Text strong>{item.label}</Text>
                        <Tag color={item.blocking ? 'red' : 'orange'} style={{ marginLeft: 8 }}>
                          {item.blocking ? '阻塞' : '建议'}
                        </Tag>
                        <Text type="secondary">：{item.detail}</Text>
                      </span>
                      {renderReadinessAction(item)}
                    </Space>
                  ))}
                </Space>
              )}
            />
          </Col>
        )}
      </Row>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'onboarding',
            label: <Space size={6}><ToolOutlined />实施交付</Space>,
            children: (
              <Row gutter={[16, 16]}>
                <Col span={24}>
                  <Card>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Text strong>实施进度</Text>
                      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <Progress style={{ flex: 1 }} percent={onboarding ? Math.round((onboarding.completed_count / onboarding.total) * 100) : 0} />
                        <Button type="primary" icon={<RocketOutlined />} loading={bootstrapping} onClick={bootstrapTrial}>初始化试用环境</Button>
                      </Space>
                      {!!onboarding?.risk_items?.length && (
                        <Alert
                          type="error"
                          showIcon
                          message="上线阻塞项"
                          description={(
                            <Space direction="vertical" size={4}>
                              {onboarding.risk_items.map(step => (
                                <Text key={step.key}>{step.label}：{step.suggested_action || step.reason}</Text>
                              ))}
                            </Space>
                          )}
                        />
                      )}
                      {!onboarding?.risk_items?.length && !!onboarding?.next_actions?.length && (
                        <Alert
                          type="warning"
                          showIcon
                          message="建议补齐项"
                          description={(
                            <Space direction="vertical" size={4}>
                              {onboarding.next_actions.slice(0, 3).map(step => (
                                <Text key={step.key}>{step.label}：{step.suggested_action || step.reason}</Text>
                              ))}
                            </Space>
                          )}
                        />
                      )}
                      {bootstrapResult && (
                        <Alert
                          type="success"
                          showIcon
                          message="试用环境初始化完成"
                          description={
                            <Space direction="vertical" size={4}>
                              <Text>新增 {bootstrapResult.created.length} 项，更新 {bootstrapResult.updated.length} 项，跳过 {bootstrapResult.skipped.length} 项。</Text>
                              {!!bootstrapResult.created.length && <Text type="secondary">新增：{bootstrapResult.created.slice(0, 6).join('、')}</Text>}
                              {!!bootstrapResult.skipped.length && <Text type="secondary">跳过：{bootstrapResult.skipped.slice(0, 6).join('、')}</Text>}
                            </Space>
                          }
                        />
                      )}
                      <Table
                        dataSource={onboarding?.steps || []}
                        columns={onboardingColumns}
                        rowKey="key"
                        pagination={false}
                        scroll={{ x: 1080 }}
                        locale={{ emptyText: <TableEmptyState title="暂无实施步骤" /> }}
                      />
                    </Space>
                  </Card>
                </Col>
                <Col span={24}>
                  <div ref={deliveryActionsRef}>
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
                          <Button className="sagitta-action-btn sagitta-action-btn--manage" icon={<ToolOutlined />} onClick={createDiagnostic}>生成诊断包</Button>
                        </Form.Item>
                      </Form>
                      <Space style={{ marginTop: 16 }}>
                        {acceptanceRunId && (
                          <>
                            <Button className="sagitta-action-btn sagitta-action-btn--download" icon={<CloudDownloadOutlined />} onClick={() => downloadReport('md')}>下载 Markdown</Button>
                            <Button className="sagitta-action-btn sagitta-action-btn--download" icon={<CloudDownloadOutlined />} onClick={() => downloadReport('json')}>下载 JSON</Button>
                          </>
                        )}
                        {diagnosticId && (
                          <Button className="sagitta-action-btn sagitta-action-btn--download" icon={<CloudDownloadOutlined />} onClick={downloadDiagnostic}>下载诊断包</Button>
                        )}
                      </Space>
                    </Card>
                  </div>
                </Col>
              </Row>
            ),
          },
          {
            key: 'compliance',
            label: <Space size={6}><FileSearchOutlined />合规报表</Space>,
            children: (
              <Card>
                <Space wrap style={{ marginBottom: 16 }}>
                  {reportTypes.map(item => (
                    <Button key={item.key} className={`sagitta-action-btn ${item.className}`} icon={item.icon} onClick={() => loadReport(item.key)}>{item.label}</Button>
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
                      <Button type="primary" icon={<SaveOutlined />} onClick={saveRetention}>保存</Button>
                    </Form.Item>
                  </Form>
                  <Space wrap style={{ marginTop: 12 }}>
                    {(retention?.items || []).map((item: any) => (
                      <Popconfirm
                        key={item.key}
                        title={`清理超过 ${item.days} 天的${item.label}？`}
                        okText="清理"
                        cancelText="取消"
                        okButtonProps={{ danger: true, icon: <DeleteOutlined /> }}
                        cancelButtonProps={{ icon: <CloseOutlined /> }}
                        onConfirm={() => cleanupRetention(item.key)}
                      >
                        <Button className="sagitta-action-btn sagitta-action-btn--danger" icon={<DeleteOutlined />}>清理{item.label}</Button>
                      </Popconfirm>
                    ))}
                  </Space>
                </Card>
              </Card>
            ),
          },
          {
            key: 'alerts',
            label: <Space size={6}><BellOutlined />告警中心</Space>,
            children: (
              <Table
                dataSource={alerts}
                rowKey="id"
                pagination={false}
                tableLayout="fixed"
                scroll={{ x: 1180 }}
                locale={{ emptyText: <TableEmptyState title="暂无告警事件" /> }}
                columns={[
                  { title: '状态', dataIndex: 'status', width: 96, render: value => <Tag>{value}</Tag> },
                  { title: '级别', dataIndex: 'severity', width: 96, render: value => <Tag color={value === 'critical' ? 'red' : 'orange'}>{value}</Tag> },
                  { title: '实例', dataIndex: 'instance_name', width: 170, ellipsis: { showTitle: false }, render: value => <TruncatedCell value={value} /> },
                  { title: '规则', dataIndex: 'rule_key', width: 170, ellipsis: { showTitle: false }, render: value => <TruncatedCell value={value} /> },
                  { title: '详情', dataIndex: 'message', width: 360, ellipsis: { showTitle: false }, render: value => <TruncatedCell value={value} /> },
                  {
                    title: '最近触发',
                    dataIndex: 'last_seen_at',
                    width: 190,
                    render: value => nowrapText(formatDateTime(value, '-')),
                  },
                  {
                    title: '操作',
                    width: 280,
                    render: (_, row) => (
                      <Space>
                        {!['resolved', 'closed'].includes(row.status) && (
                          <Button className="sagitta-action-btn sagitta-action-btn--success" icon={<CheckCircleOutlined />} onClick={() => handleAlertAction(row.id, 'ack')}>确认</Button>
                        )}
                        {!['resolved', 'closed'].includes(row.status) && (
                          <Button className="sagitta-action-btn sagitta-action-btn--neutral" icon={<PauseCircleOutlined />} onClick={() => handleAlertAction(row.id, 'silence')}>静默</Button>
                        )}
                        {row.status !== 'closed' && (
                          <Button className="sagitta-action-btn sagitta-action-btn--inspect" icon={<ReloadOutlined />} onClick={() => handleAlertAction(row.id, 'resolve')}>恢复</Button>
                        )}
                        <Button className="sagitta-action-btn sagitta-action-btn--neutral" icon={<CloseCircleOutlined />} onClick={() => handleAlertAction(row.id, 'close')}>关闭</Button>
                      </Space>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: 'support',
            label: <Space size={6}><SafetyCertificateOutlined />支持与关于</Space>,
            children: (
              <Space direction="vertical" style={{ width: '100%' }} size={16}>
                <Card title="支持与关于">
                  <Descriptions column={{ xs: 1, md: 2 }} size="small">
                    <Descriptions.Item label="版本">{about?.version || '-'}</Descriptions.Item>
                    <Descriptions.Item label="部署模式">{about?.deployment_mode || '-'}</Descriptions.Item>
                    <Descriptions.Item label="授权项目">{about ? `${about.project}（${about.project_code}）` : '-'}</Descriptions.Item>
                    <Descriptions.Item label="运行状态">
                      <Tag color={about?.runtime?.health === 'ok' ? 'green' : 'orange'}>{about?.runtime?.health || '-'}</Tag>
                    </Descriptions.Item>
                    <Descriptions.Item label="License">
                      <Space size={8} wrap>
                        <Tag color={licenseStatusColor[about?.license?.status || ''] || 'default'}>
                          {licenseStatusLabel[about?.license?.status || ''] || about?.license?.status || '-'}
                        </Tag>
                        <Button className="sagitta-action-btn sagitta-action-btn--manage" icon={<SafetyCertificateOutlined />} onClick={() => navigate('/system/license')}>前往授权管理</Button>
                      </Space>
                    </Descriptions.Item>
                    <Descriptions.Item label="支持邮箱">{about?.support?.email || '-'}</Descriptions.Item>
                    <Descriptions.Item label="授权中心">{about?.support?.license_server || '-'}</Descriptions.Item>
                    <Descriptions.Item label="部署指纹" span={2}>
                      <Space wrap>
                        <Text code copyable={false}>{about?.license?.activation_deployment_fingerprint || about?.deployment_fingerprint || '-'}</Text>
                        <Button className="sagitta-action-btn sagitta-action-btn--copy" icon={<CopyOutlined />} onClick={() => copyText(about?.license?.activation_deployment_fingerprint || about?.deployment_fingerprint || '', '部署指纹已复制')}>复制</Button>
                      </Space>
                    </Descriptions.Item>
                  </Descriptions>
                </Card>
                <Card title="引擎支持矩阵">
                  <Table
                    dataSource={matrix?.items || []}
                    rowKey="db_type"
                    pagination={false}
                    scroll={{ x: 1700 }}
                    columns={[
                      { title: '数据库', dataIndex: 'label', fixed: 'left', width: 190, render: nowrapText },
                      {
                        title: '支持等级',
                        dataIndex: 'support_label',
                        width: 170,
                        render: (value, row: any) => <Tag color={supportLevelColor[row.support_level] || 'default'}>{value}</Tag>,
                      },
                      ...Object.entries(matrix?.capability_labels || {}).map(([key, label]) => ({
                        title: label as string,
                        width: 110,
                        render: (_: any, row: any) => row.capabilities?.[key] ? <Tag color="green">支持</Tag> : <Tag>不承诺</Tag>,
                      })),
                      { title: '交付口径', dataIndex: 'validation_required', width: 360, render: nowrapText },
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
