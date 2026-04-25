import { useMemo, useState } from 'react'
import {
  Alert, Button, Col, Descriptions, Drawer, Form, Input, InputNumber, Modal,
  Progress, Row, Select, Space, Table, Tag, Typography, message,
} from 'antd'
import {
  CaretRightOutlined, ExperimentOutlined, PauseCircleOutlined, PlayCircleOutlined,
  ReloadOutlined, StopOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  archiveApi,
  type ArchiveActionResponse,
  type ArchiveEstimateResponse,
  type ArchiveJob,
  type ArchivePayload,
} from '@/api/archive'
import { approvalFlowApi } from '@/api/approvalFlow'
import { instanceApi } from '@/api/instance'
import PageHeader from '@/components/common/PageHeader'
import SectionCard from '@/components/common/SectionCard'
import SectionLoading from '@/components/common/SectionLoading'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Text, Paragraph } = Typography
const { Option } = Select

const STATUS_META: Record<string, { label: string; color: string }> = {
  pending_review: { label: '待审批', color: 'processing' },
  approved: { label: '已审批', color: 'success' },
  queued: { label: '队列中', color: 'default' },
  running: { label: '执行中', color: 'processing' },
  pausing: { label: '暂停中', color: 'warning' },
  paused: { label: '已暂停', color: 'warning' },
  canceling: { label: '取消中', color: 'warning' },
  canceled: { label: '已取消', color: 'default' },
  success: { label: '执行成功', color: 'success' },
  failed: { label: '执行失败', color: 'error' },
}

const fmtTime = (value?: string | null) => value ? new Date(value).toLocaleString('zh-CN') : '-'
const progressPercent = (job?: ArchiveJob) => {
  if (!job || !job.estimated_rows) return 0
  return Math.min(100, Math.round((job.processed_rows / job.estimated_rows) * 100))
}

export default function ArchivePage() {
  const [form] = Form.useForm<ArchivePayload>()
  const qc = useQueryClient()
  const [msgApi, msgCtx] = message.useMessage()
  const [mode, setMode] = useState<'purge' | 'dest'>('purge')
  const [srcInstanceId, setSrcInstanceId] = useState<number>()
  const [estimateResult, setEstimateResult] = useState<any>(null)
  const [selectedJobId, setSelectedJobId] = useState<number>()
  const [drawerOpen, setDrawerOpen] = useState(false)

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
      invalidateJobs()
      msgApi.success(res.msg || '归档作业已提交')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || '提交失败'),
  })
  const actionMut = useMutation<ArchiveActionResponse, unknown, { id: number; action: 'start' | 'pause' | 'resume' | 'cancel' }>({
    mutationFn: ({ id, action }: { id: number; action: 'start' | 'pause' | 'resume' | 'cancel' }) => archiveApi[action](id),
    onSuccess: (res) => {
      invalidateJobs()
      msgApi.success(res.msg || '操作成功')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || '操作失败'),
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
      Modal.confirm({
        title: '提交归档审批',
        content: (
          <Space direction="vertical" size={8}>
            <Text>归档作业提交后会先进入审批，审批通过后可启动后台执行。</Text>
            <Text type="secondary">暂停/取消将在当前批次完成后生效，已完成批次不会自动回滚。</Text>
          </Space>
        ),
        okText: '提交审批',
        onOk: () => submitMut.mutate(payload),
      })
    } catch { /* form validation */ }
  }

  const openJob = (job: ArchiveJob) => {
    setSelectedJobId(job.id)
    setDrawerOpen(true)
  }

  const renderStatus = (status: string) => {
    const meta = STATUS_META[status] || { label: status, color: 'default' }
    return <Tag color={meta.color}>{meta.label}</Tag>
  }

  const canStart = (job: ArchiveJob) => ['approved', 'paused'].includes(job.status)
  const canPause = (job: ArchiveJob) => ['queued', 'running'].includes(job.status)
  const canResume = (job: ArchiveJob) => job.status === 'paused'
  const canCancel = (job: ArchiveJob) =>
    ['pending_review', 'approved', 'queued', 'running', 'pausing', 'paused'].includes(job.status)

  const jobColumns = [
    {
      title: '作业',
      dataIndex: 'id',
      width: 110,
      render: (_: number, job: ArchiveJob) => <Button type="link" onClick={() => openJob(job)}>#{job.id}</Button>,
    },
    {
      title: '源表',
      key: 'source',
      render: (_: unknown, job: ArchiveJob) => (
        <Space direction="vertical" size={0}>
          <Text>{instanceMap.get(job.source_instance_id)?.instance_name || `实例#${job.source_instance_id}`}</Text>
          <Text type="secondary">{job.source_db}.{job.source_table}</Text>
        </Space>
      ),
    },
    {
      title: '模式',
      dataIndex: 'archive_mode',
      width: 90,
      render: (value: string) => <Tag color={value === 'dest' ? 'blue' : 'red'}>{value}</Tag>,
    },
    { title: '状态', dataIndex: 'status', width: 110, render: renderStatus },
    {
      title: '进度',
      width: 220,
      render: (_: unknown, job: ArchiveJob) => (
        <Progress percent={progressPercent(job)} size="small" format={() => `${job.processed_rows}/${job.estimated_rows}`} />
      ),
    },
    { title: '提交人', dataIndex: 'created_by', width: 110 },
    { title: '创建时间', dataIndex: 'created_at', width: 180, render: fmtTime },
    {
      title: '操作',
      width: 240,
      fixed: 'right' as const,
      render: (_: unknown, job: ArchiveJob) => (
        <Space size={4}>
          {canStart(job) && <Button size="small" icon={<PlayCircleOutlined />} loading={actionMut.isPending} onClick={() => actionMut.mutate({ id: job.id, action: 'start' })}>启动</Button>}
          {canPause(job) && <Button size="small" icon={<PauseCircleOutlined />} loading={actionMut.isPending} onClick={() => actionMut.mutate({ id: job.id, action: 'pause' })}>暂停</Button>}
          {canResume(job) && <Button size="small" icon={<CaretRightOutlined />} loading={actionMut.isPending} onClick={() => actionMut.mutate({ id: job.id, action: 'resume' })}>继续</Button>}
          {canCancel(job) && <Button size="small" danger icon={<StopOutlined />} loading={actionMut.isPending} onClick={() => actionMut.mutate({ id: job.id, action: 'cancel' })}>取消</Button>}
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
        message="小范围一次性删除可继续使用 SQL 工单模板；大批量历史清理建议使用数据归档。暂停/取消将在当前批次完成后生效。"
        style={{ marginBottom: 16 }}
      />

      <Row gutter={16}>
        <Col xs={24} xl={9}>
          <SectionCard title="提交归档申请">
            <Form<ArchivePayload>
              form={form}
              layout="vertical"
              initialValues={{ archive_mode: 'purge', batch_size: 1000, sleep_ms: 100 }}
            >
              <Form.Item name="source_instance_id" label="源实例" rules={[{ required: true }]}>
                <Select
                  placeholder="选择源实例"
                  showSearch
                  optionFilterProp="label"
                  onChange={(value) => { setSrcInstanceId(value); form.setFieldValue('source_db', undefined) }}
                >
                  {instances?.items?.map((item: any) => (
                    <Option key={item.id} value={item.id} label={item.instance_name}>
                      <Space><Tag color="blue">{formatDbTypeLabel(item.db_type)}</Tag>{item.instance_name}</Space>
                    </Option>
                  ))}
                </Select>
              </Form.Item>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item name="source_db" label="源数据库" rules={[{ required: true }]}>
                    <Select placeholder="选择数据库" disabled={!srcInstanceId} showSearch>
                      {srcDbs?.items?.map((db: any) => <Option key={db.db_name} value={db.db_name}>{db.db_name}</Option>)}
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="source_table" label="源表" rules={[{ required: true }]}>
                    <Input placeholder="order_logs" />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="condition" label="归档条件" rules={[{ required: true }]}>
                <Input.TextArea rows={3} placeholder="created_at < '2024-01-01'；MongoDB 填 JSON 条件" />
              </Form.Item>
              <Row gutter={12}>
                <Col span={8}>
                  <Form.Item name="archive_mode" label="模式">
                    <Select onChange={setMode}>
                      <Option value="purge">purge 删除</Option>
                      <Option value="dest">dest 迁移</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="batch_size" label="批次大小">
                    <InputNumber min={1} max={10000} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
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
                    <Col span={12}>
                      <Form.Item name="dest_db" label="目标数据库">
                        <Input placeholder="不填则同源库" />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
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
                <Input.TextArea rows={2} maxLength={500} placeholder="说明归档背景、业务范围和恢复方案" />
              </Form.Item>
              {estimateResult && (
                <Alert
                  type={estimateResult.count > 10000 ? 'warning' : 'info'}
                  showIcon
                  message={estimateResult.msg}
                  style={{ marginBottom: 16 }}
                />
              )}
              <Space>
                <Button icon={<ExperimentOutlined />} loading={estimateMut.isPending} onClick={handleEstimate}>估算影响</Button>
                <Button type="primary" icon={<PlayCircleOutlined />} loading={submitMut.isPending} onClick={handleSubmit}>提交审批</Button>
              </Space>
            </Form>
          </SectionCard>
        </Col>

        <Col xs={24} xl={15}>
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
                scroll={{ x: 1120 }}
              />
            )}
          </SectionCard>
        </Col>
      </Row>

      <Drawer
        title={selectedJob ? `归档作业 #${selectedJob.id}` : '归档作业'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={860}
      >
        {jobLoading || !selectedJob ? <SectionLoading text="加载作业详情中..." /> : (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="状态">{renderStatus(selectedJob.status)}</Descriptions.Item>
              <Descriptions.Item label="审批工单">
                {selectedJob.workflow_id ? <Link to={`/workflow/${selectedJob.workflow_id}`}>#{selectedJob.workflow_id}</Link> : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="源">{selectedJob.source_db}.{selectedJob.source_table}</Descriptions.Item>
              <Descriptions.Item label="模式"><Tag>{selectedJob.archive_mode}</Tag></Descriptions.Item>
              <Descriptions.Item label="目标">{selectedJob.archive_mode === 'dest' ? `${selectedJob.dest_db}.${selectedJob.dest_table}` : '-'}</Descriptions.Item>
              <Descriptions.Item label="批次">{selectedJob.current_batch}</Descriptions.Item>
              <Descriptions.Item label="估算行数">{selectedJob.estimated_rows}</Descriptions.Item>
              <Descriptions.Item label="已处理">{selectedJob.processed_rows}{selectedJob.row_count_is_estimated ? '（估算）' : ''}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{fmtTime(selectedJob.started_at)}</Descriptions.Item>
              <Descriptions.Item label="完成时间">{fmtTime(selectedJob.finished_at)}</Descriptions.Item>
              <Descriptions.Item label="条件" span={2}><Text code>{selectedJob.condition}</Text></Descriptions.Item>
              {selectedJob.error_message && <Descriptions.Item label="错误" span={2}><Text type="danger">{selectedJob.error_message}</Text></Descriptions.Item>}
            </Descriptions>
            {selectedJob.status === 'success' && (
              <Alert type="success" showIcon message="作业已完成；系统不提供完成后撤销，请按备份、归档目标或 binlog 回补方案恢复。" />
            )}
            <Progress percent={progressPercent(selectedJob)} />
            <Paragraph type="secondary">暂停/取消采用协作式机制，只会在当前批次完成后生效，已经完成的批次不会自动回滚。</Paragraph>
            <Table
              rowKey="id"
              columns={batchColumns}
              dataSource={selectedJob.batches || []}
              pagination={false}
              size="small"
              scroll={{ x: 820 }}
            />
          </Space>
        )}
      </Drawer>
    </div>
  )
}
