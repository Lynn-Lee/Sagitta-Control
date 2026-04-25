import { useMemo, useState } from 'react'
import { Button, Card, DatePicker, Drawer, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tabs, Tag, Typography, message } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs, { type Dayjs } from 'dayjs'
import { diagnosticApi, type SessionCollectConfigItem, type SessionItem } from '@/api/diagnostic'
import { instanceApi, type InstanceItem } from '@/api/instance'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'
import { useAuthStore } from '@/store/auth'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Text } = Typography
const { RangePicker } = DatePicker

type HistorySource = 'platform' | 'ash' | 'awr'

const renderDate = (value?: string | null) => value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-'
const defaultHistoryRange = () => [dayjs().subtract(24, 'hour'), dayjs()] as [Dayjs, Dayjs]
const durationValue = (value?: number | null) => Number.isFinite(Number(value)) ? Number(value) : null
const stateDurationMs = (row: SessionItem) => {
  const stateMs = durationValue(row.state_duration_ms)
  if (stateMs !== null) return stateMs
  if (Number.isFinite(Number(row.duration_ms))) return Number(row.duration_ms)
  return Number(row.time_seconds || 0) * 1000
}
const renderDuration = (value?: number | null) => {
  const numeric = durationValue(value)
  return numeric === null ? '-' : numeric.toLocaleString()
}
const isIdleSession = (row: SessionItem) => {
  const command = row.command?.toLowerCase() || ''
  const state = row.state?.toLowerCase() || ''
  return command === 'sleep' || command === 'inactive' || state === 'idle' || state === 'inactive' || state === 'sleep'
}
const defaultHistoryFilters = () => {
  const range = defaultHistoryRange()
  return {
    date_start: range[0].toISOString(),
    date_end: range[1].toISOString(),
  }
}

export default function DiagnosticPage() {
  const [instanceId, setInstanceId] = useState<number | undefined>()
  const [historySource, setHistorySource] = useState<HistorySource>('platform')
  const [historyPage, setHistoryPage] = useState(1)
  const [historyPageSize, setHistoryPageSize] = useState(50)
  const [historyFilters, setHistoryFilters] = useState<any>(() => defaultHistoryFilters())
  const [hideIdle, setHideIdle] = useState(false)
  const [sqlDetail, setSqlDetail] = useState<SessionItem | null>(null)
  const [configModalOpen, setConfigModalOpen] = useState(false)
  const [editingConfig, setEditingConfig] = useState<SessionCollectConfigItem | null>(null)
  const [historyForm] = Form.useForm()
  const [configForm] = Form.useForm()
  const [msgApi, msgCtx] = message.useMessage()
  const qc = useQueryClient()
  const hasPermission = useAuthStore((s) => s.hasPermission)
  const canKill = hasPermission('process_kill')

  const { data: instanceData } = useQuery({
    queryKey: ['instances-for-diag'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })

  const { data: dbData } = useQuery({
    queryKey: ['diag-instance-databases', instanceId],
    queryFn: () => instanceApi.getDatabases(instanceId!),
    enabled: !!instanceId,
  })

  const selectedInstance = useMemo(
    () => instanceData?.items?.find((item: InstanceItem) => item.id === instanceId),
    [instanceData?.items, instanceId],
  )
  const isOracle = selectedInstance?.db_type === 'oracle'

  const { data: processData, isLoading: processLoading, refetch } = useQuery({
    queryKey: ['processlist', instanceId],
    queryFn: () => diagnosticApi.processlist({ instance_id: instanceId!, command_type: 'ALL' }),
    enabled: !!instanceId,
    refetchInterval: 5000,
  })

  const configQuery = useQuery({
    queryKey: ['session-collect-configs'],
    queryFn: () => diagnosticApi.listConfigs(),
  })

  const killMut = useMutation({
    mutationFn: (row: SessionItem) => diagnosticApi.kill({
      instance_id: instanceId!,
      session_id: row.session_id,
      serial: row.serial,
    }),
    onSuccess: () => {
      msgApi.success('会话已 Kill')
      qc.invalidateQueries({ queryKey: ['processlist'] })
    },
    onError: (e: any) => msgApi.error(e.response?.data?.detail || e.response?.data?.msg || 'Kill 失败'),
  })

  const configMut = useMutation({
    mutationFn: (values: { is_enabled: boolean; collect_interval: number; retention_days: number }) => {
      if (editingConfig) return diagnosticApi.updateConfig(editingConfig.id, values)
      if (!instanceId) throw new Error('请先选择实例')
      return diagnosticApi.upsertConfig({ instance_id: instanceId, ...values })
    },
    onSuccess: () => {
      msgApi.success('采集配置已保存')
      setConfigModalOpen(false)
      setEditingConfig(null)
      configForm.resetFields()
      qc.invalidateQueries({ queryKey: ['session-collect-configs'] })
    },
    onError: (e: any) => msgApi.error(e.response?.data?.detail || '保存采集配置失败'),
  })

  const historyQuery = useQuery({
    queryKey: ['session-history', instanceId, historySource, historyFilters, historyPage, historyPageSize],
    queryFn: () => {
      const params = {
        ...historyFilters,
        instance_id: instanceId,
        page: historyPage,
        page_size: historyPageSize,
      }
      if (historySource === 'platform') return diagnosticApi.history(params)
      return diagnosticApi.oracleAsh({
        instance_id: instanceId!,
        source: historySource,
        date_start: params.date_start,
        date_end: params.date_end,
        sql_keyword: params.sql_keyword,
        min_duration_ms: params.min_active_duration_ms ?? params.min_state_duration_ms ?? params.min_duration_ms,
        page: historyPage,
        page_size: historyPageSize,
      })
    },
    enabled: historySource === 'platform' || (!!instanceId && isOracle),
  })

  const onlineItems = useMemo(
    () => (processData?.items ?? []).filter(item => !hideIdle || !isIdleSession(item)),
    [hideIdle, processData?.items],
  )

  const sessionColumns: ColumnsType<SessionItem> = [
    { title: '会话ID', dataIndex: 'session_id', width: 110, fixed: 'left' },
    { title: 'Serial', dataIndex: 'serial', width: 90 },
    { title: '用户', dataIndex: 'username', width: 120, ellipsis: true },
    { title: '来源', dataIndex: 'host', width: 170, ellipsis: true },
    { title: '程序', dataIndex: 'program', width: 160, ellipsis: true },
    { title: '库/Schema', dataIndex: 'db_name', width: 130, ellipsis: true },
    { title: '命令', dataIndex: 'command', width: 100, render: (v) => v ? <Tag>{v}</Tag> : '-' },
    { title: '状态', dataIndex: 'state', width: 160, ellipsis: true },
    {
      title: '连接时长(ms)',
      dataIndex: 'connection_age_ms',
      width: 130,
      sorter: (a, b) => (durationValue(a.connection_age_ms) ?? -1) - (durationValue(b.connection_age_ms) ?? -1),
      render: renderDuration,
    },
    {
      title: '状态时长(ms)',
      dataIndex: 'state_duration_ms',
      width: 130,
      sorter: (a, b) => stateDurationMs(a) - stateDurationMs(b),
      render: (_: number, row) => renderDuration(row.state_duration_ms ?? row.duration_ms),
    },
    {
      title: '当前操作(ms)',
      dataIndex: 'active_duration_ms',
      width: 130,
      sorter: (a, b) => (durationValue(a.active_duration_ms) ?? -1) - (durationValue(b.active_duration_ms) ?? -1),
      render: renderDuration,
    },
    { title: '事务时长(ms)', dataIndex: 'transaction_age_ms', width: 130, render: renderDuration },
    { title: 'SQL ID', dataIndex: 'sql_id', width: 130, ellipsis: true },
    {
      title: 'SQL',
      dataIndex: 'sql_text',
      width: 300,
      ellipsis: true,
      render: (v: string, row) => v
        ? <Button type="link" size="small" onClick={() => setSqlDetail(row)}>{v}</Button>
        : <Text type="secondary">-</Text>,
    },
    { title: '等待事件', dataIndex: 'event', width: 180, ellipsis: true },
    { title: '阻塞会话', dataIndex: 'blocking_session', width: 110 },
    {
      title: '操作',
      key: 'action',
      width: 90,
      fixed: 'right',
      render: (_, row) => {
        if (!canKill || !row.session_id) return null
        if (row.db_type === 'oracle' && !row.serial) return null
        return (
          <Popconfirm
            title={`确认 Kill 会话 ${row.session_id}${row.serial ? `,${row.serial}` : ''}？`}
            onConfirm={() => killMut.mutate(row)}
            okText="Kill"
            cancelText="取消"
          >
            <Button size="small" danger icon={<StopOutlined />} loading={killMut.isPending}>Kill</Button>
          </Popconfirm>
        )
      },
    },
  ]

  const historyColumns: ColumnsType<SessionItem> = [
    { title: '采集时间', dataIndex: 'collected_at', width: 170, fixed: 'left', render: renderDate },
    { title: '实例', dataIndex: 'instance_name', width: 150, ellipsis: true },
    { title: '类型', dataIndex: 'db_type', width: 95, render: (v) => v ? <Tag color="blue">{formatDbTypeLabel(v)}</Tag> : '-' },
    ...sessionColumns.filter((col: any) => col.key !== 'action'),
    { title: '来源', dataIndex: 'source', width: 110, render: (v) => <Tag>{v}</Tag> },
    { title: '错误', dataIndex: 'collect_error', width: 220, ellipsis: true },
  ]

  const applyHistoryFilters = (values: any) => {
    const range = values.range as [Dayjs, Dayjs] | undefined
    const minConnectionAgeMs = values.min_connection_age_ms
    const minStateDurationMs = values.min_state_duration_ms
    const minActiveDurationMs = values.min_active_duration_ms
    setHistoryPage(1)
    setHistoryFilters({
      username: values.username || undefined,
      db_name: values.db_name || undefined,
      state: values.state || undefined,
      command: values.command || undefined,
      sql_keyword: values.sql_keyword || undefined,
      min_connection_age_ms: minConnectionAgeMs === undefined || minConnectionAgeMs === null ? undefined : Number(minConnectionAgeMs),
      min_state_duration_ms: minStateDurationMs === undefined || minStateDurationMs === null ? undefined : Number(minStateDurationMs),
      min_active_duration_ms: minActiveDurationMs === undefined || minActiveDurationMs === null ? undefined : Number(minActiveDurationMs),
      date_start: range?.[0]?.toISOString(),
      date_end: range?.[1]?.toISOString(),
    })
  }

  const resetHistoryFilters = () => {
    const range = defaultHistoryRange()
    historyForm.setFieldsValue({
      range,
      username: undefined,
      db_name: undefined,
      state: undefined,
      command: undefined,
      sql_keyword: undefined,
      min_connection_age_ms: undefined,
      min_state_duration_ms: undefined,
      min_active_duration_ms: undefined,
    })
    setHistoryPage(1)
    setHistoryFilters({
      date_start: range[0].toISOString(),
      date_end: range[1].toISOString(),
    })
  }

  const onHistoryTableChange = (pagination: TablePaginationConfig) => {
    setHistoryPage(pagination.current || 1)
    setHistoryPageSize(pagination.pageSize || 50)
  }

  const openConfigModal = (row?: SessionCollectConfigItem) => {
    const currentConfig = row || configQuery.data?.items.find(item => item.instance_id === instanceId)
    setEditingConfig(currentConfig || null)
    configForm.setFieldsValue({
      is_enabled: currentConfig?.is_enabled ?? true,
      collect_interval: currentConfig?.collect_interval ?? 60,
      retention_days: currentConfig?.retention_days ?? 30,
    })
    setConfigModalOpen(true)
  }

  const configColumns: ColumnsType<SessionCollectConfigItem> = [
    { title: '实例', dataIndex: 'instance_name', width: 180, ellipsis: true },
    { title: '类型', dataIndex: 'db_type', width: 100, render: (v) => <Tag color="blue">{formatDbTypeLabel(v)}</Tag> },
    { title: '启用', dataIndex: 'is_enabled', width: 90, render: (v) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag> },
    { title: '采样间隔', dataIndex: 'collect_interval', width: 120, render: (v) => `${v}s` },
    { title: '保留天数', dataIndex: 'retention_days', width: 110, render: (v) => `${v}天` },
    { title: '最近采集', dataIndex: 'last_collect_at', width: 170, render: renderDate },
    {
      title: '状态',
      dataIndex: 'last_collect_status',
      width: 120,
      render: (v) => {
        const color = v === 'success' ? 'green' : v === 'failed' ? 'red' : v === 'skipped' ? 'default' : 'blue'
        return <Tag color={color}>{v || 'never'}</Tag>
      },
    },
    { title: '最近条数', dataIndex: 'last_collect_count', width: 100 },
    { title: '错误', dataIndex: 'last_collect_error', width: 260, ellipsis: true },
    {
      title: '操作',
      key: 'action',
      width: 90,
      fixed: 'right',
      render: (_, row) => <Button size="small" disabled={!canKill} onClick={() => openConfigModal(row)}>编辑</Button>,
    },
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader title="会话管理" marginBottom={20} />

      <FilterCard marginBottom={16}>
        <Space wrap>
          <Select
            placeholder="选择实例"
            style={{ width: 260 }}
            onChange={(value) => {
              setInstanceId(value)
              setHistorySource('platform')
              historyForm.setFieldValue('db_name', undefined)
              setHistoryFilters((prev: any) => ({ ...prev, db_name: undefined }))
              setHistoryPage(1)
            }}
            showSearch
            optionFilterProp="label"
          >
            {instanceData?.items?.map((item: InstanceItem) => (
              <Select.Option key={item.id} value={item.id} label={item.instance_name}>
                <Tag color="blue">{formatDbTypeLabel(item.db_type)}</Tag> {item.instance_name}
              </Select.Option>
            ))}
          </Select>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()} disabled={!instanceId}>刷新</Button>
          <Text type="secondary" style={{ fontSize: 12 }}>
            在线 {processData?.total ?? 0} 个会话{hideIdle ? `，当前显示 ${onlineItems.length} 个非空闲会话` : ''}
          </Text>
          <Switch checked={hideIdle} onChange={setHideIdle} checkedChildren="隐藏空闲" unCheckedChildren="显示全部" />
        </Space>
      </FilterCard>

      <Tabs
        items={[
          {
            key: 'online',
            label: '在线会话',
            children: (
              <Card style={{ borderRadius: 8, border: '1px solid rgba(0,0,0,0.08)' }} styles={{ body: { padding: 0 } }}>
                <Table
                  rowKey={(row) => `${row.db_type}-${row.session_id}-${row.serial}`}
                  dataSource={onlineItems}
                  columns={sessionColumns}
                  loading={processLoading}
                  size="small"
                  tableLayout="fixed"
                  scroll={{ x: 2100 }}
                  locale={{ emptyText: <TableEmptyState title={instanceId ? '暂无会话' : '请先选择实例'} /> }}
                  pagination={{ pageSize: 50, showSizeChanger: false }}
                />
              </Card>
            ),
          },
          {
            key: 'history',
            label: '历史会话',
            children: (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <FilterCard>
                  <Form
                    form={historyForm}
                    onFinish={applyHistoryFilters}
                    initialValues={{ range: defaultHistoryRange() }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      overflowX: 'auto',
                      paddingBottom: 2,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    <Form.Item name="range" style={{ margin: 0, flex: '0 0 430px' }}>
                      <RangePicker
                        showTime
                        className="query-history-range-picker"
                        style={{ width: '100%' }}
                      />
                    </Form.Item>
                    <Form.Item name="username" style={{ margin: 0, flex: '0 0 120px' }}>
                      <Input placeholder="用户" allowClear style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="db_name" style={{ margin: 0, flex: '0 0 160px' }}>
                      <Select
                        placeholder="库/Schema"
                        allowClear
                        showSearch
                        optionFilterProp="label"
                        disabled={!instanceId}
                        style={{ width: '100%' }}
                        options={(dbData?.databases || [])
                          .filter(db => db.is_active)
                          .map(db => ({ value: db.db_name, label: db.db_name }))}
                      />
                    </Form.Item>
                    <Form.Item name="sql_keyword" style={{ margin: 0, flex: '0 0 180px' }}>
                      <Input placeholder="SQL 关键字" allowClear style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="state" style={{ margin: 0, flex: '0 0 120px' }}>
                      <Input placeholder="状态" allowClear style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="command" style={{ margin: 0, flex: '0 0 120px' }}>
                      <Input placeholder="命令" allowClear style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="min_connection_age_ms" style={{ margin: 0, flex: '0 0 150px' }}>
                      <InputNumber placeholder="最小连接时长(ms)" min={0} step={100} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="min_state_duration_ms" style={{ margin: 0, flex: '0 0 150px' }}>
                      <InputNumber placeholder="最小状态时长(ms)" min={0} step={100} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="min_active_duration_ms" style={{ margin: 0, flex: '0 0 150px' }}>
                      <InputNumber placeholder="最小操作时长(ms)" min={0} step={100} style={{ width: '100%' }} />
                    </Form.Item>
                    {isOracle && instanceId && (
                      <Form.Item style={{ margin: 0, flex: '0 0 140px' }}>
                        <Select value={historySource} onChange={setHistorySource} style={{ width: '100%' }}>
                          <Select.Option value="platform">平台采样快照</Select.Option>
                          <Select.Option value="ash">Oracle ASH 活跃采样</Select.Option>
                          <Select.Option value="awr">Oracle AWR 活跃采样</Select.Option>
                        </Select>
                      </Form.Item>
                    )}
                    <Form.Item style={{ margin: 0, flex: '0 0 auto' }}>
                      <Button type="primary" htmlType="submit">查询</Button>
                    </Form.Item>
                    <Form.Item style={{ margin: 0, flex: '0 0 auto' }}>
                      <Button onClick={resetHistoryFilters}>重置条件</Button>
                    </Form.Item>
                  </Form>
                </FilterCard>
                <Card style={{ borderRadius: 8, border: '1px solid rgba(0,0,0,0.08)' }} styles={{ body: { padding: 0 } }}>
                  <Table
                    rowKey={(row, idx) => `${row.source}-${row.instance_id}-${row.session_id}-${row.serial}-${row.collected_at}-${idx}`}
                    dataSource={historyQuery.data?.items ?? []}
                    columns={historyColumns}
                    loading={historyQuery.isLoading || historyQuery.isFetching}
                    size="small"
                    tableLayout="fixed"
                    scroll={{ x: 2450 }}
                    locale={{ emptyText: <TableEmptyState title="暂无历史会话" /> }}
                    pagination={{
                      current: historyPage,
                      pageSize: historyPageSize,
                      total: historyQuery.data?.total ?? 0,
                      showSizeChanger: true,
                    }}
                    onChange={onHistoryTableChange}
                  />
                </Card>
              </Space>
            ),
          },
          {
            key: 'config',
            label: '采集配置',
            children: (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <FilterCard>
                  <Space>
                    <Button
                      type="primary"
                      disabled={!instanceId || !canKill}
                      loading={configQuery.isLoading}
                      onClick={() => openConfigModal()}
                    >
                      为当前实例配置
                    </Button>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      未配置实例默认启用，采样间隔 60s，保留 30 天
                    </Text>
                  </Space>
                </FilterCard>
                <Card style={{ borderRadius: 8, border: '1px solid rgba(0,0,0,0.08)' }} styles={{ body: { padding: 0 } }}>
                  <Table
                    rowKey="id"
                    dataSource={configQuery.data?.items ?? []}
                    columns={configColumns}
                    loading={configQuery.isLoading || configQuery.isFetching}
                    size="small"
                    tableLayout="fixed"
                    scroll={{ x: 1350 }}
                    locale={{ emptyText: <TableEmptyState title="暂无采集配置" /> }}
                    pagination={{ pageSize: 50, showSizeChanger: false }}
                  />
                </Card>
              </Space>
            ),
          },
        ]}
      />

      <Drawer
        title="SQL 详情"
        open={!!sqlDetail}
        onClose={() => setSqlDetail(null)}
        width={720}
      >
        <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{sqlDetail?.sql_text}</pre>
      </Drawer>

      <Modal
        title={`配置采集：${editingConfig?.instance_name || selectedInstance?.instance_name || '当前实例'}`}
        open={configModalOpen}
        onCancel={() => {
          setConfigModalOpen(false)
          setEditingConfig(null)
          configForm.resetFields()
        }}
        onOk={() => configForm.submit()}
        confirmLoading={configMut.isPending}
        destroyOnClose
      >
        <Form
          form={configForm}
          layout="vertical"
          onFinish={(values) => configMut.mutate(values)}
          initialValues={{ is_enabled: true, collect_interval: 60, retention_days: 30 }}
        >
          <Form.Item name="is_enabled" label="启用采集" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            name="collect_interval"
            label="采样间隔（秒）"
            rules={[{ required: true, message: '请输入采样间隔' }]}
          >
            <InputNumber min={10} max={86400} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="retention_days"
            label="保留天数"
            rules={[{ required: true, message: '请输入保留天数' }]}
          >
            <InputNumber min={1} max={365} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
