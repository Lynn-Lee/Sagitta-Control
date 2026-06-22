import { useEffect, useMemo, useState } from 'react'
import { Button, Card, DatePicker, Drawer, Form, Input, InputNumber, Popconfirm, Select, Space, Switch, Table, Tabs, Tag, Tooltip, Typography, message } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { ClearOutlined, EyeOutlined, ReloadOutlined, SearchOutlined, StopOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs, { type Dayjs } from 'dayjs'
import { diagnosticApi, type SessionItem } from '@/api/diagnostic'
import { instanceApi, type InstanceItem } from '@/api/instance'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'
import { useAuthStore } from '@/store/auth'
import { formatDbTypeLabel } from '@/utils/dbType'
import { formatDateTime } from '@/utils/datetime'

const { Text } = Typography
const { RangePicker } = DatePicker

type HistorySource = 'platform' | 'ash' | 'awr'

const renderDate = (value?: string | null) => formatDateTime(value, '-')
const defaultHistoryRange = () => [dayjs().subtract(24, 'hour'), dayjs()] as [Dayjs, Dayjs]
const durationValue = (value?: number | string | null) => {
  if (value === null || value === undefined || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}
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
const renderBytes = (value?: number | string | null) => {
  const numeric = durationValue(value)
  if (numeric === null) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = numeric
  let idx = 0
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024
    idx += 1
  }
  return `${size.toFixed(idx === 0 ? 0 : 2)} ${units[idx]}`
}
const renderCommandTag = (value?: string | null) => {
  if (!value) return '-'
  return (
    <Tooltip title={value}>
      <Tag
        style={{
          display: 'inline-block',
          maxWidth: '100%',
          marginInlineEnd: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          verticalAlign: 'middle',
          whiteSpace: 'nowrap',
        }}
      >
        {value}
      </Tag>
    </Tooltip>
  )
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

type SessionInsightPanelProps = {
  embedded?: boolean
  instanceId?: number | null
}

export function SessionInsightPanel({ embedded = false, instanceId: externalInstanceId }: SessionInsightPanelProps) {
  const [instanceId, setInstanceId] = useState<number | undefined>(externalInstanceId || undefined)
  const [historySource, setHistorySource] = useState<HistorySource>('platform')
  const [historyPage, setHistoryPage] = useState(1)
  const [historyPageSize, setHistoryPageSize] = useState(50)
  const [historyFilters, setHistoryFilters] = useState<any>(() => defaultHistoryFilters())
  const [hideIdle, setHideIdle] = useState(false)
  const [sqlDetail, setSqlDetail] = useState<SessionItem | null>(null)
  const [historyForm] = Form.useForm()
  const [msgApi, msgCtx] = message.useMessage()
  const qc = useQueryClient()
  const hasPermission = useAuthStore((s) => s.hasPermission)
  const canKill = hasPermission('observability_session_kill')

  useEffect(() => {
    if (!externalInstanceId) return
    setInstanceId(externalInstanceId)
    setHistorySource('platform')
    historyForm.setFieldValue('db_name', undefined)
    setHistoryFilters((prev: any) => ({ ...prev, db_name: undefined }))
    setHistoryPage(1)
  }, [externalInstanceId, historyForm])

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
  const isTidb = selectedInstance?.db_type === 'tidb'

  const { data: processData, isLoading: processLoading, refetch } = useQuery({
    queryKey: ['processlist', instanceId],
    queryFn: () => diagnosticApi.processlist({ instance_id: instanceId!, command_type: 'ALL' }),
    enabled: !!instanceId,
    refetchInterval: 5000,
  })

  const killMut = useMutation({
    mutationFn: (row: SessionItem) => diagnosticApi.kill({
      instance_id: instanceId!,
      session_id: row.session_id,
      serial: row.serial,
    }),
    onSuccess: () => {
      msgApi.success('会话已终止')
      qc.invalidateQueries({ queryKey: ['processlist'] })
    },
    onError: (e: any) => msgApi.error(e.response?.data?.detail || e.response?.data?.msg || '终止失败'),
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
    ...(isOracle ? [
      { title: 'RAC', dataIndex: 'inst_id', width: 80, ellipsis: true },
      { title: 'OS PID', dataIndex: 'process_id', width: 100, ellipsis: true },
    ] as ColumnsType<SessionItem> : []),
    ...(isTidb ? [
      { title: 'TiDB 节点', dataIndex: 'tidb_instance', width: 190, ellipsis: true },
      { title: '资源组', dataIndex: 'resource_group', width: 110, ellipsis: true },
    ] as ColumnsType<SessionItem> : []),
    { title: '用户', dataIndex: 'username', width: 120, ellipsis: true },
    { title: '来源', dataIndex: 'host', width: 170, ellipsis: true },
    ...(isTidb ? [
      { title: 'TiDB 内存', dataIndex: 'mem_bytes', width: 110, render: renderBytes },
      { title: 'TiDB 磁盘', dataIndex: 'disk_bytes', width: 110, render: renderBytes },
      { title: 'TxnStart', dataIndex: 'txn_start', width: 170, ellipsis: true },
    ] as ColumnsType<SessionItem> : []),
    { title: '程序', dataIndex: 'program', width: 160, ellipsis: true },
    ...(isOracle ? [
      { title: '模块', dataIndex: 'module', width: 130, ellipsis: true },
      { title: '操作', dataIndex: 'action', width: 130, ellipsis: true },
    ] as ColumnsType<SessionItem> : []),
    { title: '库/Schema', dataIndex: 'db_name', width: 130, ellipsis: true },
    { title: '命令', dataIndex: 'command', width: 110, ellipsis: true, render: renderCommandTag },
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
        ? <Button className="sagitta-action-btn sagitta-action-btn--inspect" icon={<EyeOutlined />} onClick={() => setSqlDetail(row)}>{v}</Button>
        : <Text type="secondary">-</Text>,
    },
    { title: '等待事件', dataIndex: 'event', width: 180, ellipsis: true },
    ...(isOracle ? [
      { title: '等待类别', dataIndex: 'wait_class', width: 120, ellipsis: true },
      { title: '等待秒数', dataIndex: 'seconds_in_wait', width: 100, render: renderDuration },
      { title: '阻塞实例', dataIndex: 'blocking_instance', width: 100, ellipsis: true },
      { title: 'PGA Used', dataIndex: 'pga_used_mem', width: 110, render: renderBytes },
    ] as ColumnsType<SessionItem> : []),
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
            title={`确认终止会话 ${row.session_id}${row.serial ? `,${row.serial}` : ''}？`}
            onConfirm={() => killMut.mutate(row)}
            okText="终止"
            cancelText="取消"
          >
            <Button danger icon={<StopOutlined />} loading={killMut.isPending}>终止</Button>
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
  const sessionTableScrollX = isTidb ? 2800 : isOracle ? 3150 : 2100
  const historyTableScrollX = isTidb ? 3150 : isOracle ? 3500 : 2450

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

  return (
    <div>
      {msgCtx}
      {!embedded && <PageHeader title="会话洞察" marginBottom={20} />}

      <FilterCard marginBottom={16}>
        <Space wrap>
          {!embedded ? (
            <Select
              placeholder="选择实例"
              style={{ width: 260 }}
              value={instanceId}
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
          ) : (
            <Text strong>{selectedInstance ? `${selectedInstance.instance_name} / ${formatDbTypeLabel(selectedInstance.db_type)}` : '请选择实例'}</Text>
          )}
          <Button icon={<ReloadOutlined />} onClick={() => refetch()} disabled={!instanceId}>刷新</Button>
          <Text type="secondary">
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
                  scroll={{ x: sessionTableScrollX }}
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
                      <Button type="primary" icon={<SearchOutlined />} htmlType="submit">查询</Button>
                    </Form.Item>
                    <Form.Item style={{ margin: 0, flex: '0 0 auto' }}>
                      <Button className="sagitta-action-btn sagitta-action-btn--neutral" icon={<ClearOutlined />} onClick={resetHistoryFilters}>重置条件</Button>
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
                      scroll={{ x: historyTableScrollX }}
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
        ]}
      />

      <Drawer
        title="SQL 详情"
        open={!!sqlDetail}
        maskClosable={false}
        onClose={() => setSqlDetail(null)}
        width={720}
      >
        <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{sqlDetail?.sql_text}</pre>
      </Drawer>
    </div>
  )
}

export default function DiagnosticPage() {
  return <SessionInsightPanel />
}
