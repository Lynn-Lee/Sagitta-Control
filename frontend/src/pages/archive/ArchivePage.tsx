import { useMemo, useState } from 'react'
import {
  Alert, Button, Col, DatePicker, Descriptions, Drawer, Form, Input, InputNumber, Modal,
  Progress, Radio, Row, Select, Space, Table, Tabs, Tag, Tooltip, Typography, message,
} from 'antd'
import {
  CaretRightOutlined, CheckOutlined, CloseOutlined, ExperimentOutlined, EyeOutlined,
  FileTextOutlined, PauseCircleOutlined, PlayCircleOutlined, ReloadOutlined, StopOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { Link } from 'react-router-dom'
import {
  archiveApi,
  type ArchiveActionResponse,
  type ArchiveExecutePayload,
  type ArchiveEstimateResponse,
  type ArchiveJob,
  type ArchivePayload,
} from '@/api/archive'
import { approvalFlowApi } from '@/api/approvalFlow'
import { instanceApi } from '@/api/instance'
import { workflowApi } from '@/api/workflow'
import PageHeader from '@/components/common/PageHeader'
import RiskPlanAlert from '@/components/common/RiskPlanAlert'
import SectionCard from '@/components/common/SectionCard'
import SectionLoading from '@/components/common/SectionLoading'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Text, Paragraph } = Typography
const { Option } = Select

const STATUS_META: Record<string, { label: string; color: string }> = {
  pending_review: { label: '待审批', color: 'processing' },
  approved: { label: '已审批', color: 'success' },
  scheduled: { label: '定时待执行', color: 'warning' },
  queued: { label: '队列中', color: 'default' },
  running: { label: '执行中', color: 'processing' },
  pausing: { label: '暂停中', color: 'warning' },
  paused: { label: '已暂停', color: 'warning' },
  canceling: { label: '取消中', color: 'warning' },
  canceled: { label: '已取消', color: 'default' },
  success: { label: '执行成功', color: 'success' },
  failed: { label: '执行失败', color: 'error' },
}

const fmtTime = (value?: string | null) => value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'
const displayJobNo = (job?: ArchiveJob) => job?.workflow_id || job?.id
const progressPercent = (job?: ArchiveJob) => {
  if (!job || !job.estimated_rows) return 0
  return Math.min(100, Math.round((job.processed_rows / job.estimated_rows) * 100))
}

const renderRiskTag = (level?: string, summary?: string) => {
  if (!level) return <Text type="secondary">—</Text>
  const meta = level === 'high'
    ? { color: 'error', label: '高风险' }
    : level === 'medium'
      ? { color: 'warning', label: '中风险' }
      : { color: 'success', label: '低风险' }
  const tag = <Tag color={meta.color}>{meta.label}</Tag>
  return summary ? <Tooltip title={summary}>{tag}</Tooltip> : tag
}

export default function ArchivePage() {
  const [form] = Form.useForm<ArchivePayload>()
  const [executeForm] = Form.useForm()
  const qc = useQueryClient()
  const [msgApi, msgCtx] = message.useMessage()
  const [mode, setMode] = useState<'purge' | 'dest'>('purge')
  const [srcInstanceId, setSrcInstanceId] = useState<number>()
  const [estimateResult, setEstimateResult] = useState<any>(null)
  const [riskChecking, setRiskChecking] = useState(false)
  const [selectedJobId, setSelectedJobId] = useState<number>()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('submit')
  const [drawerTab, setDrawerTab] = useState('summary')
  const [executeModalOpen, setExecuteModalOpen] = useState(false)
  const [executeTarget, setExecuteTarget] = useState<ArchiveJob | null>(null)
  const executeMode = Form.useWatch('mode', executeForm) || 'immediate'

  const { data: instances } = useQuery({
    queryKey: ['instances-for-archive'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })
  const { data: srcDbs } = useQuery({
    queryKey: ['src-dbs-archive', srcInstanceId],
    queryFn: () => instanceApi.listRegisteredDbs(srcInstanceId!),
    enabled: !!srcInstanceId,
  })
  const { data: flows } = useQuery({
    queryKey: ['approval-flows-for-archive'],
    queryFn: () => approvalFlowApi.list({ page_size: 100 }),
  })
  const { data: jobsData, isLoading: jobsLoading } = useQuery({
    queryKey: ['archive-jobs'],
    queryFn: () => archiveApi.listJobs({ page_size: 50 }),
    refetchInterval: 3000,
  })
  const { data: selectedJob, isLoading: jobLoading } = useQuery({
    queryKey: ['archive-job', selectedJobId],
    queryFn: () => archiveApi.getJob(selectedJobId!),
    enabled: !!selectedJobId && drawerOpen,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && ['queued', 'running', 'pausing', 'canceling'].includes(status) ? 2000 : false
    },
  })
  const { data: selectedWorkflow, isLoading: workflowLoading } = useQuery({
    queryKey: ['archive-workflow', selectedJob?.workflow_id],
    queryFn: () => workflowApi.get(selectedJob!.workflow_id!),
    enabled: drawerOpen && !!selectedJob?.workflow_id,
  })

  const instanceMap = useMemo<Map<number, any>>(
    () => new Map<number, any>((instances?.items || []).map((item: any) => [item.id, item])),
    [instances?.items],
  )

  const invalidateJobs = () => {
    qc.invalidateQueries({ queryKey: ['archive-jobs'] })
    if (selectedJobId) qc.invalidateQueries({ queryKey: ['archive-job', selectedJobId] })
  }

  const estimateMut = useMutation<ArchiveEstimateResponse, unknown, ArchivePayload>({
    mutationFn: (payload: ArchivePayload) => archiveApi.estimate(payload),
    onSuccess: (res) => {
      setEstimateResult(res)
      if (res.supported === false) msgApi.warning(res.msg)
      else msgApi.info(`估算完成：${res.msg}`)
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || '估算失败'),
  })
  const submitMut = useMutation<ArchiveActionResponse, unknown, ArchivePayload>({
    mutationFn: (payload: ArchivePayload) => archiveApi.submit(payload),
    onSuccess: (res) => {
      setEstimateResult(null)
      form.resetFields()
      setSrcInstanceId(undefined)
      setMode('purge')
      setActiveTab('records')
      invalidateJobs()
      msgApi.success(res.msg || '归档作业已提交')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || '提交失败'),
  })
  const actionMut = useMutation<ArchiveActionResponse, unknown, { id: number; action: 'start' | 'pause' | 'resume' | 'cancel'; payload?: ArchiveExecutePayload }>({
    mutationFn: ({ id, action, payload }: { id: number; action: 'start' | 'pause' | 'resume' | 'cancel'; payload?: ArchiveExecutePayload }) =>
      action === 'start' ? archiveApi.start(id, payload) : archiveApi[action](id),
    onSuccess: (res) => {
      invalidateJobs()
      setExecuteModalOpen(false)
      setExecuteTarget(null)
      msgApi.success(res.msg || '操作成功')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || '操作失败'),
  })
  const auditMut = useMutation({
    mutationFn: ({ workflowId, action, remark }: { workflowId: number; action: 'pass' | 'reject'; remark?: string }) =>
      workflowApi.audit(workflowId, { action, remark }),
    onSuccess: () => {
      invalidateJobs()
      if (selectedJob?.workflow_id) qc.invalidateQueries({ queryKey: ['archive-workflow', selectedJob.workflow_id] })
      msgApi.success('审批操作成功')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || '审批操作失败'),
  })

  const validatePayload = async () => form.validateFields()

  const handleEstimate = async () => {
    try {
      estimateMut.mutate(await validatePayload())
    } catch { /* form validation */ }
  }

  const handleSubmit = async () => {
    try {
      const payload = await validatePayload()
      setRiskChecking(true)
      const estimate = estimateResult?.risk_plan ? estimateResult : await archiveApi.estimate(payload)
      setEstimateResult(estimate)
      setRiskChecking(false)
      if (estimate.risk_plan?.requires_manual_remark && !payload.risk_remark?.trim()) {
        msgApi.warning('高风险归档/清理申请请填写恢复/验证说明后再提交')
        return
      }
      if (!estimate.risk_plan?.requires_confirmation) {
        submitMut.mutate(payload)
        return
      }
      Modal.confirm({
        title: '提交高风险归档审批？',
        width: 640,
        maskClosable: false,
        closable: true,
        content: (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            {estimate.risk_plan && <RiskPlanAlert plan={estimate.risk_plan} />}
            <Text>归档作业提交后会先进入审批，审批通过后可启动后台执行。</Text>
            {payload.risk_remark && (
              <div>
                <Text strong>恢复/验证说明：</Text>
                <div style={{ marginTop: 4 }}>{payload.risk_remark}</div>
              </div>
            )}
            <Text type="secondary">暂停/取消将在当前批次完成后生效，已完成批次不会自动回滚。</Text>
          </Space>
        ),
        okText: '提交审批',
        okButtonProps: { danger: true },
        onOk: () => submitMut.mutate(payload),
      })
    } catch {
      setRiskChecking(false)
    }
  }

  const openJob = (job: ArchiveJob, tab = 'summary') => {
    setSelectedJobId(job.id)
    setDrawerTab(tab)
    setDrawerOpen(true)
  }

  const openExecuteModal = (job: ArchiveJob) => {
    setExecuteTarget(job)
    executeForm.setFieldsValue({
      mode: 'immediate',
      external_status: 'success',
      external_executed_at: dayjs(),
    })
    setExecuteModalOpen(true)
  }

  const submitExecuteDecision = async () => {
    if (!executeTarget) return
    const values = await executeForm.validateFields()
    const payload: ArchiveExecutePayload = { mode: values.mode || 'immediate' }
    if (values.mode === 'scheduled') {
      payload.scheduled_at = values.scheduled_at?.toISOString()
    }
    if (values.mode === 'external') {
      payload.external_executed_at = values.external_executed_at?.toISOString()
      payload.external_status = values.external_status
      payload.external_remark = values.external_remark
    }
    await actionMut.mutateAsync({ id: executeTarget.id, action: 'start', payload })
  }

  const handleAuditPass = () => {
    if (!selectedJob?.workflow_id || !selectedWorkflow) return
    const submitPass = () => auditMut.mutateAsync({ workflowId: selectedJob.workflow_id!, action: 'pass' })
    if (selectedWorkflow.risk_plan?.level !== 'high') {
      submitPass()
      return
    }
    Modal.confirm({
      title: '确认通过高风险归档申请？',
      width: 640,
      maskClosable: false,
      closable: true,
      okText: '确认通过',
      cancelText: '返回检查',
      okButtonProps: { danger: true },
      content: (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <RiskPlanAlert plan={selectedWorkflow.risk_plan} />
          {selectedWorkflow.risk_remark && (
            <div>
              <Text strong>申请人恢复/验证说明：</Text>
              <div style={{ marginTop: 4 }}>{selectedWorkflow.risk_remark}</div>
            </div>
          )}
          <Text type="secondary">审批前请确认影响范围、备份方式和恢复路径可接受。</Text>
        </Space>
      ),
      onOk: submitPass,
    })
  }

  const handleAuditReject = () => {
    if (!selectedJob?.workflow_id) return
    let remark = '驳回'
    Modal.confirm({
      title: '驳回归档申请？',
      maskClosable: false,
      closable: true,
      okText: '确认驳回',
      cancelText: '返回',
      okButtonProps: { danger: true },
      content: (
        <Input.TextArea
          rows={4}
          defaultValue={remark}
          maxLength={500}
          showCount
          onChange={e => { remark = e.target.value || '驳回' }}
        />
      ),
      onOk: () => auditMut.mutateAsync({ workflowId: selectedJob.workflow_id!, action: 'reject', remark }),
    })
  }

  const renderStatus = (status: string) => {
    const meta = STATUS_META[status] || { label: status, color: 'default' }
    return <Tag color={meta.color}>{meta.label}</Tag>
  }

  const renderAuditNodeStatus = (status?: number) => {
    const meta: Record<number, { label: string; color: string }> = {
      0: { label: '待审批', color: 'processing' },
      1: { label: '已通过', color: 'success' },
      2: { label: '已驳回', color: 'error' },
      3: { label: '已取消', color: 'default' },
    }
    const item = meta[Number(status)] || { label: '未知', color: 'default' }
    return <Tag color={item.color}>{item.label}</Tag>
  }

  const canStart = (job: ArchiveJob) => ['approved', 'paused', 'scheduled'].includes(job.status) && !!job.can_execute
  const canPause = (job: ArchiveJob) => ['queued', 'running'].includes(job.status) && !!job.can_control
  const canResume = (job: ArchiveJob) => job.status === 'paused' && !!job.can_control
  const canCancelApplication = (job: ArchiveJob) => job.status === 'pending_review' && !!job.can_cancel
  const canCancelJobControl = (job: ArchiveJob) =>
    ['approved', 'scheduled', 'queued', 'running', 'pausing', 'paused'].includes(job.status) && !!job.can_control

  const jobColumns = [
    {
      title: '任务号',
      dataIndex: 'id',
      width: 105,
      render: (_: number, job: ArchiveJob) => <Button type="link" onClick={() => openJob(job)}>#{displayJobNo(job)}</Button>,
    },
    {
      title: '源表',
      key: 'source',
      width: 300,
      render: (_: unknown, job: ArchiveJob) => (
        <Space direction="vertical" size={2} style={{ maxWidth: 280 }}>
          <Space size={6} wrap>
            <Text strong>{instanceMap.get(job.source_instance_id)?.instance_name || `实例#${job.source_instance_id}`}</Text>
            <Tag color={job.archive_mode === 'dest' ? 'blue' : 'red'}>{job.archive_mode}</Tag>
            {renderRiskTag(job.risk_level, job.risk_summary)}
          </Space>
          <Text type="secondary" ellipsis={{ tooltip: `${job.source_db}.${job.source_table}` }}>
            {job.source_db}.{job.source_table}
          </Text>
        </Space>
      ),
    },
    { title: '状态', dataIndex: 'status', width: 110, render: renderStatus },
    {
      title: '进度',
      width: 240,
      render: (_: unknown, job: ArchiveJob) => (
        <Progress percent={progressPercent(job)} size="small" format={() => `${job.processed_rows}/${job.estimated_rows}`} />
      ),
    },
    { title: '提交人', dataIndex: 'created_by_display', width: 140, ellipsis: true, render: (v: string, job: ArchiveJob) => v || job.created_by || '-' },
    { title: '创建时间', dataIndex: 'created_at', width: 180, render: fmtTime },
    {
      title: '操作',
      width: 280,
      fixed: 'right' as const,
      render: (_: unknown, job: ArchiveJob) => (
        <Space direction="vertical" size={6}>
          {job.status === 'pending_review' && job.risk_level === 'high' && !job.can_audit && (
            <Text type="danger" style={{ fontSize: 12 }}>高风险待审批</Text>
          )}
          <Space size={4} wrap>
            <Button size="small" icon={<EyeOutlined />} onClick={() => openJob(job)}>查看详情</Button>
            {job.can_audit && (
              <Button size="small" type="primary" danger={job.risk_level === 'high'} icon={<CheckOutlined />} onClick={() => openJob(job, 'approval')}>
                审批处理
              </Button>
            )}
            {job.workflow_id && (
              <Link to={`/workflow/${job.workflow_id}`}>
                <Button size="small" icon={<FileTextOutlined />}>查看工单</Button>
              </Link>
            )}
            {canStart(job) && <Button size="small" type="primary" icon={<PlayCircleOutlined />} loading={actionMut.isPending} onClick={() => openExecuteModal(job)}>执行处理</Button>}
            {canPause(job) && <Button size="small" icon={<PauseCircleOutlined />} loading={actionMut.isPending} onClick={() => actionMut.mutate({ id: job.id, action: 'pause' })}>暂停</Button>}
            {canResume(job) && <Button size="small" icon={<CaretRightOutlined />} loading={actionMut.isPending} onClick={() => actionMut.mutate({ id: job.id, action: 'resume' })}>继续</Button>}
            {canCancelApplication(job) && (
              <Button
                size="small"
                danger
                icon={<StopOutlined />}
                loading={actionMut.isPending}
                onClick={() => {
                  Modal.confirm({
                    title: '撤回归档/清理申请？',
                    content: '撤回后该申请不会继续流转审批。',
                    maskClosable: false,
                    closable: true,
                    okText: '确认取消',
                    cancelText: '返回',
                    onOk: () => actionMut.mutateAsync({ id: job.id, action: 'cancel' }),
                  })
                }}
              >
                撤回申请
              </Button>
            )}
            {canCancelJobControl(job) && (
              <Button
                size="small"
                danger
                icon={<StopOutlined />}
                loading={actionMut.isPending}
                onClick={() => {
                  Modal.confirm({
                    title: job.status === 'scheduled' || job.status === 'approved' ? '取消执行？' : '停止归档作业？',
                    content: job.status === 'running' || job.status === 'pausing'
                      ? '停止后将在当前批次完成后生效，已完成批次不会自动回滚。'
                      : '取消后该归档作业不会继续进入平台执行。',
                    maskClosable: false,
                    closable: true,
                    okText: '确认',
                    cancelText: '返回',
                    onOk: () => actionMut.mutateAsync({ id: job.id, action: 'cancel' }),
                  })
                }}
              >
                {job.status === 'running' || job.status === 'pausing' ? '停止作业' : '取消执行'}
              </Button>
            )}
          </Space>
        </Space>
      ),
    },
  ]

  const batchColumns = [
    { title: '批次', dataIndex: 'batch_no', width: 80 },
    { title: '状态', dataIndex: 'status', width: 100, render: renderStatus },
    { title: '选中', dataIndex: 'selected_rows', width: 90 },
    { title: '插入', dataIndex: 'inserted_rows', width: 90 },
    { title: '删除', dataIndex: 'deleted_rows', width: 90 },
    { title: '信息', dataIndex: 'message', ellipsis: true },
    { title: '完成时间', dataIndex: 'finished_at', width: 180, render: fmtTime },
  ]

  const workflowLogColumns = [
    { title: '操作人', dataIndex: 'operator', width: 140, ellipsis: true },
    { title: '操作', dataIndex: 'operation_type', width: 120 },
    { title: '备注', dataIndex: 'remark', ellipsis: true },
    { title: '时间', dataIndex: 'created_at', width: 180, render: fmtTime },
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="数据归档"
        meta="标准化提交、审批和后台分批执行历史数据清理或迁移任务"
        marginBottom={20}
      />

      <Alert
        type="info"
        showIcon
        message="小范围一次性删除可继续使用 SQL 工单模板；大批量历史清理建议使用数据归档。暂停/停止将在当前批次完成后生效。"
        style={{ marginBottom: 16 }}
      />

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'submit',
            label: '提交任务',
            children: (
              <Row gutter={16}>
                <Col xs={24} xl={14}>
                  <SectionCard title="提交归档申请">
                    <Form<ArchivePayload>
                      form={form}
                      layout="vertical"
                      initialValues={{ archive_mode: 'purge', batch_size: 1000, sleep_ms: 100 }}
                      onValuesChange={(changed) => { if (!('risk_remark' in changed)) setEstimateResult(null) }}
                    >
                      <Form.Item name="source_instance_id" label="源实例" rules={[{ required: true }]}>
                        <Select
                          placeholder="选择源实例"
                          showSearch
                          optionFilterProp="label"
                          onChange={(value) => { setSrcInstanceId(value); setEstimateResult(null); form.setFieldValue('source_db', undefined) }}
                        >
                          {instances?.items?.map((item: any) => (
                            <Option key={item.id} value={item.id} label={item.instance_name}>
                              <Space><Tag color="blue">{formatDbTypeLabel(item.db_type)}</Tag>{item.instance_name}</Space>
                            </Option>
                          ))}
                        </Select>
                      </Form.Item>
                      <Row gutter={12}>
                        <Col xs={24} md={12}>
                          <Form.Item name="source_db" label="源数据库" rules={[{ required: true }]}>
                            <Select placeholder="选择数据库" disabled={!srcInstanceId} showSearch>
                              {srcDbs?.items?.map((db: any) => <Option key={db.db_name} value={db.db_name}>{db.db_name}</Option>)}
                            </Select>
                          </Form.Item>
                        </Col>
                        <Col xs={24} md={12}>
                          <Form.Item name="source_table" label="源表" rules={[{ required: true }]}>
                            <Input placeholder="order_logs" />
                          </Form.Item>
                        </Col>
                      </Row>
                      <Form.Item
                        name="condition"
                        label="归档条件"
                        extra="只填写 WHERE 后面的条件，无需填写完整 SQL"
                        rules={[{ required: true }]}
                      >
                        <Input.TextArea rows={5} placeholder="created_at < '2024-01-01'；MongoDB 填 JSON 条件" />
                      </Form.Item>
                      <Row gutter={12}>
                        <Col xs={24} md={8}>
                          <Form.Item name="archive_mode" label="模式">
                            <Select onChange={(value) => { setMode(value); setEstimateResult(null) }}>
                              <Option value="purge">purge 删除</Option>
                              <Option value="dest">dest 迁移</Option>
                            </Select>
                          </Form.Item>
                        </Col>
                        <Col xs={24} md={8}>
                          <Form.Item name="batch_size" label="批次大小">
                            <InputNumber min={1} max={10000} style={{ width: '100%' }} />
                          </Form.Item>
                        </Col>
                        <Col xs={24} md={8}>
                          <Form.Item name="sleep_ms" label="批次间隔(ms)">
                            <InputNumber min={0} max={10000} style={{ width: '100%' }} />
                          </Form.Item>
                        </Col>
                      </Row>
                      {mode === 'dest' && (
                        <>
                          <Form.Item name="dest_instance_id" label="目标实例" rules={[{ required: mode === 'dest' }]}>
                            <Select placeholder="选择目标实例" showSearch optionFilterProp="label">
                              {instances?.items?.map((item: any) => <Option key={item.id} value={item.id} label={item.instance_name}>{item.instance_name}</Option>)}
                            </Select>
                          </Form.Item>
                          <Row gutter={12}>
                            <Col xs={24} md={12}>
                              <Form.Item name="dest_db" label="目标数据库">
                                <Input placeholder="不填则同源库" />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item name="dest_table" label="目标表">
                                <Input placeholder="不填则同源表" />
                              </Form.Item>
                            </Col>
                          </Row>
                        </>
                      )}
                      <Form.Item name="flow_id" label="审批流">
                        <Select placeholder="不选则使用归档默认审批" allowClear>
                          {flows?.items?.map(flow => <Option key={flow.id} value={flow.id}>{flow.name}</Option>)}
                        </Select>
                      </Form.Item>
                      <Form.Item name="apply_reason" label="申请原因">
                        <Input.TextArea rows={3} maxLength={500} placeholder="说明归档背景、业务范围和恢复方案" />
                      </Form.Item>
                      {estimateResult?.risk_plan?.requires_manual_remark && (
                        <Form.Item
                          name="risk_remark"
                          label="恢复/验证说明"
                          rules={[{ required: true, message: '请填写高风险归档/清理申请的恢复/验证说明' }]}
                        >
                          <Input.TextArea rows={4} maxLength={500} placeholder="说明备份位置、验证方式、失败补偿和恢复路径" />
                        </Form.Item>
                      )}
                      <Space>
                        <Button icon={<ExperimentOutlined />} loading={estimateMut.isPending} onClick={handleEstimate}>估算影响</Button>
                        <Button type="primary" icon={<PlayCircleOutlined />} loading={submitMut.isPending || riskChecking} onClick={handleSubmit}>提交审批</Button>
                      </Space>
                    </Form>
                  </SectionCard>
                </Col>
                <Col xs={24} xl={10}>
                  <SectionCard title="影响评估">
                    {estimateResult ? (
                      <Space direction="vertical" size={12} style={{ width: '100%' }}>
                        <Alert
                          type={estimateResult.count > 10000 ? 'warning' : 'info'}
                          showIcon
                          message={estimateResult.msg}
                        />
                        <RiskPlanAlert plan={estimateResult.risk_plan} />
                      </Space>
                    ) : (
                      <Alert
                        type="info"
                        showIcon
                        message="填写归档条件后先估算影响，再提交审批。"
                        description="高风险任务会要求补充恢复/验证说明，审批通过后才能启动后台执行。"
                      />
                    )}
                  </SectionCard>
                </Col>
              </Row>
            ),
          },
          {
            key: 'records',
            label: '任务记录',
            children: (
              <SectionCard
                title="归档作业"
                extra={<Button icon={<ReloadOutlined />} onClick={invalidateJobs}>刷新</Button>}
                bodyPadding={0}
              >
                {jobsLoading ? <SectionLoading text="加载归档作业中..." compact /> : (
                  <Table
                    rowKey="id"
                    columns={jobColumns}
                    dataSource={jobsData?.items || []}
                    pagination={false}
                    tableLayout="fixed"
                    scroll={{ x: 1220 }}
                  />
                )}
              </SectionCard>
            ),
          },
        ]}
      />

      <Drawer
        title={selectedJob ? `归档任务 #${displayJobNo(selectedJob)}` : '归档任务'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={860}
      >
        {jobLoading || !selectedJob ? <SectionLoading text="加载作业详情中..." /> : (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Space wrap>
              {selectedJob.can_audit && (
                <>
                  <Button type="primary" danger={selectedJob.risk_level === 'high'} icon={<CheckOutlined />} loading={auditMut.isPending || workflowLoading} onClick={handleAuditPass}>
                    审批通过
                  </Button>
                  <Button danger icon={<CloseOutlined />} loading={auditMut.isPending || workflowLoading} onClick={handleAuditReject}>
                    驳回
                  </Button>
                </>
              )}
              {selectedJob.workflow_id && (
                <Link to={`/workflow/${selectedJob.workflow_id}`}>
                  <Button icon={<FileTextOutlined />}>查看关联工单</Button>
                </Link>
              )}
              {canStart(selectedJob) && (
                <Button type="primary" icon={<PlayCircleOutlined />} loading={actionMut.isPending} onClick={() => openExecuteModal(selectedJob)}>
                  执行处理
                </Button>
              )}
              {canPause(selectedJob) && (
                <Button icon={<PauseCircleOutlined />} loading={actionMut.isPending} onClick={() => actionMut.mutate({ id: selectedJob.id, action: 'pause' })}>
                  暂停
                </Button>
              )}
              {canResume(selectedJob) && (
                <Button icon={<CaretRightOutlined />} loading={actionMut.isPending} onClick={() => actionMut.mutate({ id: selectedJob.id, action: 'resume' })}>
                  继续
                </Button>
              )}
              {canCancelJobControl(selectedJob) && (
                <Button danger icon={<StopOutlined />} loading={actionMut.isPending} onClick={() => actionMut.mutate({ id: selectedJob.id, action: 'cancel' })}>
                  {selectedJob.status === 'running' || selectedJob.status === 'pausing' ? '停止作业' : '取消执行'}
                </Button>
              )}
            </Space>
            <Tabs
              activeKey={drawerTab}
              onChange={setDrawerTab}
              items={[
              {
                key: 'summary',
                label: '基础信息',
                children: (
                  <Space direction="vertical" size={16} style={{ width: '100%' }}>
                    {selectedJob.risk_plan && <RiskPlanAlert plan={selectedJob.risk_plan} />}
                    {selectedJob.status === 'success' && (
                      <Alert type="success" showIcon message="作业已完成；系统不提供完成后撤销，请按提交时的风险预案、备份或归档目标恢复。" />
                    )}
                    <Descriptions column={2} size="small" bordered>
                      <Descriptions.Item label="归档作业 ID">#{selectedJob.id}</Descriptions.Item>
                      <Descriptions.Item label="状态">{renderStatus(selectedJob.status)}</Descriptions.Item>
                      <Descriptions.Item label="审批工单">
                        {selectedJob.workflow_id ? <Link to={`/workflow/${selectedJob.workflow_id}`}>#{selectedJob.workflow_id}</Link> : '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="提交人">{selectedJob.created_by_display || selectedJob.created_by || '-'}</Descriptions.Item>
                      <Descriptions.Item label="创建时间">{fmtTime(selectedJob.created_at)}</Descriptions.Item>
                      <Descriptions.Item label="源">{selectedJob.source_db}.{selectedJob.source_table}</Descriptions.Item>
                      <Descriptions.Item label="模式"><Tag>{selectedJob.archive_mode}</Tag></Descriptions.Item>
                      <Descriptions.Item label="目标">{selectedJob.archive_mode === 'dest' ? `${selectedJob.dest_db}.${selectedJob.dest_table}` : '-'}</Descriptions.Item>
                      <Descriptions.Item label="批次">{selectedJob.current_batch}</Descriptions.Item>
                      <Descriptions.Item label="估算行数">{selectedJob.estimated_rows}</Descriptions.Item>
                      <Descriptions.Item label="已处理">{selectedJob.processed_rows}{selectedJob.row_count_is_estimated ? '（估算）' : ''}</Descriptions.Item>
                      <Descriptions.Item label="开始时间">{fmtTime(selectedJob.started_at)}</Descriptions.Item>
                      <Descriptions.Item label="完成时间">{fmtTime(selectedJob.finished_at)}</Descriptions.Item>
                      <Descriptions.Item label="条件" span={2}><Text code>{selectedJob.condition}</Text></Descriptions.Item>
                      {selectedJob.risk_summary && <Descriptions.Item label="风险摘要" span={2}>{selectedJob.risk_summary}</Descriptions.Item>}
                      {selectedJob.risk_remark && <Descriptions.Item label="风险说明" span={2}>{selectedJob.risk_remark}</Descriptions.Item>}
                      {selectedJob.error_message && <Descriptions.Item label="错误" span={2}><Text type="danger">{selectedJob.error_message}</Text></Descriptions.Item>}
                    </Descriptions>
                    <Progress percent={progressPercent(selectedJob)} />
                    <Paragraph type="secondary">暂停/停止采用协作式机制，只会在当前批次完成后生效，已经完成的批次不会自动回滚。</Paragraph>
                  </Space>
                ),
              },
              {
                key: 'approval',
                label: '审批记录',
                children: workflowLoading ? <SectionLoading text="加载审批记录中..." compact /> : (
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    {selectedWorkflow?.audit_info?.nodes?.length ? (
                      <Descriptions column={1} size="small" bordered>
                        {selectedWorkflow.audit_info.nodes.map((node: any, index: number) => (
                          <Descriptions.Item
                            key={`${node.node_name || 'node'}-${index}`}
                            label={`第 ${node.order ?? index + 1} 级`}
                          >
                            <Space wrap>
                              <Text strong>{node.node_name || '审批节点'}</Text>
                              {renderAuditNodeStatus(node.status)}
                              {node.operator && <Text type="secondary">操作人：{node.operator}</Text>}
                              {node.operate_time && <Text type="secondary">时间：{fmtTime(node.operate_time)}</Text>}
                            </Space>
                          </Descriptions.Item>
                        ))}
                      </Descriptions>
                    ) : null}
                    {selectedWorkflow?.audit_logs?.length ? (
                      <Table
                        rowKey={(_row, index) => String(index)}
                        columns={workflowLogColumns}
                        dataSource={selectedWorkflow.audit_logs}
                        pagination={false}
                        size="small"
                        tableLayout="fixed"
                        scroll={{ x: 760 }}
                      />
                    ) : (
                      <Alert type="info" showIcon message="暂无审批记录" />
                    )}
                  </Space>
                ),
              },
              {
                key: 'execution',
                label: '执行记录',
                children: (
                  <Table
                    rowKey="id"
                    columns={batchColumns}
                    dataSource={selectedJob.batches || []}
                    pagination={false}
                    size="small"
                    tableLayout="fixed"
                    scroll={{ x: 820 }}
                  />
                ),
              },
            ]}
            />
          </Space>
        )}
      </Drawer>

      <Modal
        title={executeTarget ? `执行处理 #${displayJobNo(executeTarget)}` : '执行处理'}
        open={executeModalOpen}
        onCancel={() => { setExecuteModalOpen(false); setExecuteTarget(null); executeForm.resetFields() }}
        onOk={submitExecuteDecision}
        confirmLoading={actionMut.isPending}
        okText={executeMode === 'immediate' ? '立即执行' : executeMode === 'scheduled' ? '预约执行' : '登记结果'}
        cancelText="取消"
        destroyOnClose
      >
        <Form form={executeForm} layout="vertical" preserve={false} initialValues={{ mode: 'immediate', external_status: 'success' }}>
          <Form.Item name="mode" label="执行方式" rules={[{ required: true, message: '请选择执行方式' }]}>
            <Radio.Group optionType="button" buttonStyle="solid" style={{ width: '100%' }}>
              <Radio.Button value="immediate">立即执行</Radio.Button>
              <Radio.Button value="scheduled">定时执行</Radio.Button>
              <Radio.Button value="external">外部已执行</Radio.Button>
            </Radio.Group>
          </Form.Item>

          {executeMode === 'scheduled' && (
            <Form.Item name="scheduled_at" label="预约执行时间" rules={[{ required: true, message: '请选择预约执行时间' }]}>
              <DatePicker
                showTime
                style={{ width: '100%' }}
                disabledDate={(current) => !!current && current < dayjs().startOf('day')}
              />
            </Form.Item>
          )}

          {executeMode === 'external' && (
            <>
              <Form.Item name="external_executed_at" label="实际执行时间" rules={[{ required: true, message: '请选择实际执行时间' }]}>
                <DatePicker showTime style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="external_status" label="执行结果" rules={[{ required: true, message: '请选择执行结果' }]}>
                <Select
                  options={[
                    { value: 'success', label: '成功' },
                    { value: 'failed', label: '失败' },
                  ]}
                />
              </Form.Item>
              <Form.Item name="external_remark" label="执行备注" rules={[{ required: true, message: '请填写外部执行结果备注' }]}>
                <Input.TextArea rows={4} maxLength={500} showCount placeholder="记录线下执行方式、影响范围、执行结果或失败原因" />
              </Form.Item>
            </>
          )}

          {executeMode === 'immediate' && (
            <Text type="secondary">确认后会把归档作业加入平台执行队列。执行中停止只会在当前批次完成后生效。</Text>
          )}
        </Form>
      </Modal>
    </div>
  )
}
