import { useMemo, useState } from 'react'
import { Alert, Button, Descriptions, Form, Grid, Input, InputNumber, Modal, Progress, Select, Space, Statistic, Switch, Table, Tabs, Tag, Typography, message } from 'antd'
import { ApiOutlined, BarChartOutlined, DatabaseOutlined, PlayCircleOutlined, ReloadOutlined, SettingOutlined, TableOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import apiClient from '@/api/client'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'
import { useAuthStore } from '@/store/auth'

const { Text } = Typography
const { Option } = Select
const { useBreakpoint } = Grid

interface MonitorSnapshot {
  collected_at?: string | null
  status: string
  error?: string
  missing_groups?: Record<string, string>
  is_up: boolean
  version?: string
  uptime_seconds?: number | null
  current_connections?: number | null
  active_sessions?: number | null
  max_connections?: number | null
  connection_usage?: number | null
  qps?: number | null
  tps?: number | null
  slow_queries?: number | null
  error_count?: number | null
  lock_waits?: number | null
  long_transactions?: number | null
  replication_lag_seconds?: number | null
  total_size_bytes?: number | null
}

interface MonitorInstance {
  instance_id: number
  instance_name: string
  db_type: string
  is_active: boolean
  config_id?: number | null
  config_enabled: boolean
  collect_interval?: number | null
  capacity_collect_interval?: number | null
  retention_days?: number | null
  last_metric_collect_at?: string | null
  last_capacity_collect_at?: string | null
  last_collect_status: string
  last_collect_error?: string
  latest?: MonitorSnapshot | null
}

const statusColor: Record<string, string> = {
  success: 'success',
  partial: 'warning',
  failed: 'error',
  pending: 'processing',
  not_configured: 'default',
}

function formatBytes(value?: number | null) {
  if (value === null || value === undefined) return '暂无数据'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let size = Number(value)
  let idx = 0
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024
    idx += 1
  }
  return `${size.toFixed(idx === 0 ? 0 : 2)} ${units[idx]}`
}

function formatMetric(value?: number | string | null, suffix = '') {
  if (value === null || value === undefined || value === '') return '暂无数据'
  return `${value}${suffix}`
}

function formatTime(value?: string | null) {
  if (!value) return '暂无数据'
  return value.replace('T', ' ').slice(0, 19)
}

function StatusTag({ status }: { status?: string }) {
  const value = status || 'not_configured'
  const label: Record<string, string> = {
    success: '正常',
    partial: '部分缺失',
    failed: '采集失败',
    pending: '待采集',
    not_configured: '未配置',
  }
  return <Tag color={statusColor[value] || 'default'}>{label[value] || value}</Tag>
}

function MetricCard({ title, value, suffix, danger }: { title: string; value?: number | string | null; suffix?: string; danger?: boolean }) {
  return (
    <div style={{ border: '1px solid rgba(0,0,0,0.08)', borderRadius: 8, padding: 16, minHeight: 92 }}>
      <Statistic title={title} value={formatMetric(value, suffix)} valueStyle={{ fontSize: 20, color: danger ? '#cf1322' : undefined }} />
    </div>
  )
}

export default function MonitorPage() {
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const queryClient = useQueryClient()
  const canManageConfig = useAuthStore((s) => s.hasPermission('monitor_config_manage'))
  const [msgApi, msgCtx] = message.useMessage()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [configTarget, setConfigTarget] = useState<MonitorInstance | null>(null)
  const [configOpen, setConfigOpen] = useState(false)
  const [tableDb, setTableDb] = useState<string | undefined>()
  const [tableSearch, setTableSearch] = useState('')
  const [tablePage, setTablePage] = useState(1)
  const [form] = Form.useForm()

  const { data, isLoading } = useQuery({
    queryKey: ['native-monitor-instances'],
    queryFn: () => apiClient.get('/monitor/native/instances/').then(r => r.data),
  })
  const instances: MonitorInstance[] = data?.items || []
  const activeId = selectedId || instances[0]?.instance_id || null
  const active = instances.find(i => i.instance_id === activeId) || null

  const { data: detail } = useQuery({
    queryKey: ['native-monitor-detail', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: trendData } = useQuery({
    queryKey: ['native-monitor-trend', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/trend/?hours=24`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: dbCapacity } = useQuery({
    queryKey: ['native-monitor-db-capacity', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/databases/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: tableCapacity, isLoading: tableLoading } = useQuery({
    queryKey: ['native-monitor-table-capacity', activeId, tableDb, tableSearch, tablePage],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/tables/`, { params: { db_name: tableDb, search: tableSearch, page: tablePage, page_size: 100 } }).then(r => r.data),
    enabled: !!activeId,
  })

  const saveConfig = useMutation({
    mutationFn: ({ instanceId, values }: { instanceId: number; values: any }) => apiClient.put(`/monitor/native/instances/${instanceId}/config/`, values).then(r => r.data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['native-monitor-instances'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-detail', variables.instanceId] })
      setConfigOpen(false)
      setConfigTarget(null)
      msgApi.success('监控采集配置已保存')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '保存失败'),
  })
  const collectNow = useMutation({
    mutationFn: (instanceId: number) => apiClient.post(`/monitor/native/instances/${instanceId}/collect/`).then(r => r.data),
    onSuccess: (_data, instanceId) => {
      queryClient.invalidateQueries({ queryKey: ['native-monitor-instances'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-detail', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-trend', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-db-capacity', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-table-capacity'] })
      msgApi.success('采集完成')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '采集失败'),
  })

  const latest: MonitorSnapshot | null = detail?.latest || active?.latest || null
  const dbItems = dbCapacity?.items || []

  const trendRows = useMemo(() => (trendData?.items || []).map((row: any) => ({
    ...row,
    time: formatTime(row.collected_at).slice(5, 16),
    size_gb: row.total_size_bytes ? Number((row.total_size_bytes / 1024 / 1024 / 1024).toFixed(2)) : null,
  })), [trendData])

  const openConfig = (target?: MonitorInstance | null) => {
    const item = target || active
    if (!item) return
    setSelectedId(item.instance_id)
    setConfigTarget(item)
    form.setFieldsValue({
      is_enabled: item.config_enabled ?? true,
      collect_interval: item.collect_interval || 60,
      capacity_collect_interval: item.capacity_collect_interval || 3600,
      retention_days: item.retention_days || 30,
    })
    setConfigOpen(true)
  }

  const triggerCollect = (instanceId?: number | null) => {
    if (!instanceId) return
    setSelectedId(instanceId)
    collectNow.mutate(instanceId)
  }

  const columns = [
    {
      title: '实例',
      key: 'instance',
      fixed: 'left' as const,
      width: 220,
      render: (_: any, row: MonitorInstance) => (
        <Space direction="vertical" size={0}>
          <Button type="link" style={{ padding: 0, height: 22, fontWeight: 600 }} onClick={() => setSelectedId(row.instance_id)}>
            {row.instance_name}
          </Button>
          <Space size={4}>
            <Tag>{row.db_type}</Tag>
            <Text type="secondary">ID:{row.instance_id}</Text>
          </Space>
        </Space>
      ),
    },
    { title: '健康', width: 110, render: (_: any, row: MonitorInstance) => row.latest?.is_up ? <Tag color="success">在线</Tag> : <Tag color="error">未知</Tag> },
    { title: '采集状态', width: 120, render: (_: any, row: MonitorInstance) => <StatusTag status={row.last_collect_status} /> },
    { title: '连接使用率', width: 130, render: (_: any, row: MonitorInstance) => row.latest?.connection_usage !== null && row.latest?.connection_usage !== undefined ? <Progress percent={Math.round(row.latest.connection_usage * 100)} size="small" /> : <Text type="secondary">暂无数据</Text> },
    { title: 'QPS', width: 100, render: (_: any, row: MonitorInstance) => formatMetric(row.latest?.qps) },
    { title: '慢查询', width: 100, render: (_: any, row: MonitorInstance) => formatMetric(row.latest?.slow_queries) },
    { title: '容量', width: 130, render: (_: any, row: MonitorInstance) => formatBytes(row.latest?.total_size_bytes) },
    { title: '最后采集', width: 180, render: (_: any, row: MonitorInstance) => formatTime(row.last_metric_collect_at) },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right' as const,
      width: 170,
      render: (_: any, row: MonitorInstance) => canManageConfig ? (
        <Space onClick={(event) => event.stopPropagation()}>
          <Button size="small" icon={<SettingOutlined />} onClick={() => openConfig(row)}>配置</Button>
          <Button size="small" type="primary" icon={<PlayCircleOutlined />} loading={collectNow.isPending && activeId === row.instance_id} onClick={() => triggerCollect(row.instance_id)}>采集</Button>
        </Space>
      ) : null,
    },
  ]

  const dbColumns = [
    { title: '库/Schema', dataIndex: 'db_name', fixed: 'left' as const, width: 180 },
    { title: '总大小', dataIndex: 'total_size_bytes', sorter: (a: any, b: any) => a.total_size_bytes - b.total_size_bytes, render: formatBytes },
    { title: '数据大小', dataIndex: 'data_size_bytes', render: formatBytes },
    { title: '索引大小', dataIndex: 'index_size_bytes', render: formatBytes },
    { title: '表数量', dataIndex: 'table_count' },
    { title: '行数估算', dataIndex: 'row_count' },
    { title: '采集时间', dataIndex: 'collected_at', render: formatTime },
  ]

  const tableColumns = [
    { title: '表', dataIndex: 'table_name', fixed: 'left' as const, width: 220 },
    { title: '库/Schema', dataIndex: 'db_name', width: 180 },
    { title: '总大小', dataIndex: 'total_size_bytes', sorter: (a: any, b: any) => a.total_size_bytes - b.total_size_bytes, render: formatBytes },
    { title: '数据大小', dataIndex: 'data_size_bytes', sorter: (a: any, b: any) => a.data_size_bytes - b.data_size_bytes, render: formatBytes },
    { title: '索引大小', dataIndex: 'index_size_bytes', sorter: (a: any, b: any) => a.index_size_bytes - b.index_size_bytes, render: formatBytes },
    { title: '行数估算', dataIndex: 'row_count', sorter: (a: any, b: any) => a.row_count - b.row_count },
    { title: '采集时间', dataIndex: 'collected_at', render: formatTime },
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="可观测中心"
        marginBottom={20}
        actions={(
          <Space wrap style={isMobile ? { width: '100%' } : undefined}>
            <Button icon={<ReloadOutlined />} onClick={() => queryClient.invalidateQueries({ queryKey: ['native-monitor-instances'] })}>刷新</Button>
            {canManageConfig && <Button icon={<SettingOutlined />} disabled={!activeId} onClick={() => openConfig(active)}>配置当前实例</Button>}
            {canManageConfig && <Button type="primary" icon={<PlayCircleOutlined />} disabled={!activeId} loading={collectNow.isPending} onClick={() => triggerCollect(activeId)}>采集当前实例</Button>}
          </Space>
        )}
      />

      <Table
        dataSource={instances}
        columns={columns}
        rowKey="instance_id"
        loading={isLoading}
        tableLayout="fixed"
        scroll={{ x: 1250 }}
        pagination={false}
        rowClassName={(row) => row.instance_id === activeId ? 'ant-table-row-selected' : ''}
        onRow={(row) => ({
          onClick: () => setSelectedId(row.instance_id),
          style: { cursor: 'pointer' },
        })}
        locale={{ emptyText: <TableEmptyState title="暂无可监控实例" /> }}
      />

      {activeId && (
        <div style={{ marginTop: 20 }}>
          <Space align="center" style={{ marginBottom: 12 }}>
            <DatabaseOutlined />
            <Text strong>{active?.instance_name || detail?.instance?.instance_name}</Text>
            <StatusTag status={detail?.config?.last_collect_status || active?.last_collect_status} />
            <Text type="secondary">最后指标采集：{formatTime(detail?.config?.last_metric_collect_at || active?.last_metric_collect_at)}</Text>
          </Space>

          {!detail?.config && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
              message="该实例尚未启用原生监控采集"
              description="保存采集配置或点击立即采集后，SagittaDB 会使用实例账号读取数据库原生监控指标。账号权限不足的指标会显示为空。"
            />
          )}
          {latest?.error && <Alert type="error" showIcon style={{ marginBottom: 16 }} message="最近采集失败" description={latest.error} />}

          <Tabs
            items={[
              {
                key: 'overview',
                label: <span><ApiOutlined />概览</span>,
                children: (
                  <Space direction="vertical" size={16} style={{ width: '100%' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
                      <MetricCard title="健康状态" value={latest?.is_up ? '在线' : '暂无数据'} />
                      <MetricCard title="当前连接" value={latest?.current_connections} />
                      <MetricCard title="QPS" value={latest?.qps} />
                      <MetricCard title="实例容量" value={formatBytes(latest?.total_size_bytes)} />
                      <MetricCard title="活跃会话" value={latest?.active_sessions} />
                      <MetricCard title="TPS" value={latest?.tps} />
                      <MetricCard title="慢查询" value={latest?.slow_queries} danger={(latest?.slow_queries || 0) > 0} />
                      <MetricCard title="锁等待" value={latest?.lock_waits} danger={(latest?.lock_waits || 0) > 0} />
                    </div>
                    <Descriptions bordered size="small" column={isMobile ? 1 : 3}>
                      <Descriptions.Item label="数据库版本">{formatMetric(latest?.version)}</Descriptions.Item>
                      <Descriptions.Item label="运行时长">{formatMetric(latest?.uptime_seconds, 's')}</Descriptions.Item>
                      <Descriptions.Item label="最大连接">{formatMetric(latest?.max_connections)}</Descriptions.Item>
                      <Descriptions.Item label="长事务">{formatMetric(latest?.long_transactions)}</Descriptions.Item>
                      <Descriptions.Item label="复制延迟">{formatMetric(latest?.replication_lag_seconds, 's')}</Descriptions.Item>
                      <Descriptions.Item label="采集时间">{formatTime(latest?.collected_at)}</Descriptions.Item>
                    </Descriptions>
                  </Space>
                ),
              },
              {
                key: 'trend',
                label: <span><BarChartOutlined />趋势</span>,
                children: trendRows.length ? (
                  <div style={{ height: 320 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={trendRows}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="time" />
                        <YAxis />
                        <Tooltip formatter={(value: any, name: string) => name === 'size_gb' ? [`${value} GB`, '容量'] : [value, name]} />
                        <Line type="monotone" dataKey="current_connections" name="连接数" stroke="#1677ff" dot={false} />
                        <Line type="monotone" dataKey="qps" name="QPS" stroke="#52c41a" dot={false} />
                        <Line type="monotone" dataKey="slow_queries" name="慢查询" stroke="#fa8c16" dot={false} />
                        <Line type="monotone" dataKey="size_gb" name="容量GB" stroke="#722ed1" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                ) : <TableEmptyState title="暂无趋势数据" />,
              },
              {
                key: 'databases',
                label: <span><DatabaseOutlined />库容量</span>,
                children: <Table dataSource={dbItems} columns={dbColumns} rowKey="db_name" scroll={{ x: 980 }} pagination={false} locale={{ emptyText: <TableEmptyState title="暂无库容量数据" /> }} />,
              },
              {
                key: 'tables',
                label: <span><TableOutlined />表容量</span>,
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Space wrap>
                      <Select allowClear placeholder="库/Schema" style={{ width: 220 }} value={tableDb} onChange={(value) => { setTableDb(value); setTablePage(1) }}>
                        {dbItems.map((item: any) => <Option key={item.db_name} value={item.db_name}>{item.db_name}</Option>)}
                      </Select>
                      <Input.Search allowClear placeholder="搜索表名" style={{ width: 260 }} onSearch={(value) => { setTableSearch(value); setTablePage(1) }} />
                    </Space>
                    <Table dataSource={tableCapacity?.items || []} columns={tableColumns} rowKey={(row: any) => `${row.db_name}.${row.table_name}`} loading={tableLoading} scroll={{ x: 1180 }} pagination={{ total: tableCapacity?.total, pageSize: 100, current: tablePage, showSizeChanger: false, onChange: setTablePage }} locale={{ emptyText: <TableEmptyState title="暂无表容量数据" /> }} />
                  </Space>
                ),
              },
              {
                key: 'diagnosis',
                label: '采集诊断',
                children: (
                  <Space direction="vertical" size={16} style={{ width: '100%' }}>
                    <Alert
                      type="info"
                      showIcon
                      message="指标缺失说明"
                      description="SagittaDB 使用实例配置账号采集监控数据。若账号缺少系统视图、性能视图或管理命令权限，对应指标会显示为空。请为监控账号授予数据库原生监控权限后重新采集。"
                    />
                    <Descriptions bordered size="small" column={1}>
                      <Descriptions.Item label="实例指标采集">{formatTime(detail?.config?.last_metric_collect_at)}</Descriptions.Item>
                      <Descriptions.Item label="容量采集">{formatTime(detail?.config?.last_capacity_collect_at)}</Descriptions.Item>
                      <Descriptions.Item label="采集状态"><StatusTag status={detail?.config?.last_collect_status} /></Descriptions.Item>
                      <Descriptions.Item label="采集错误">{detail?.config?.last_collect_error || latest?.error || '暂无'}</Descriptions.Item>
                      <Descriptions.Item label="缺失指标组">{Object.keys(latest?.missing_groups || {}).length ? JSON.stringify(latest?.missing_groups) : '暂无'}</Descriptions.Item>
                    </Descriptions>
                  </Space>
                ),
              },
            ]}
          />
        </div>
      )}

      <Modal
        title={`原生监控采集配置 - ${configTarget?.instance_name || active?.instance_name || ''}`}
        open={configOpen}
        onCancel={() => {
          setConfigOpen(false)
          setConfigTarget(null)
        }}
        onOk={() => form.validateFields().then(values => {
          const instanceId = configTarget?.instance_id || activeId
          if (instanceId) saveConfig.mutate({ instanceId, values })
        })}
        confirmLoading={saveConfig.isPending}
        maskClosable={false}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginTop: 8 }}
          message="该配置仅作用于当前实例"
          description="不同实例需要分别启用采集。保存后，SagittaDB 会使用该实例配置的账号读取该实例可见范围内的监控指标。"
        />
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="is_enabled" label="启用采集" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="collect_interval" label="实例指标采集间隔（秒）" rules={[{ required: true }]}>
            <InputNumber min={10} max={3600} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="capacity_collect_interval" label="容量采集间隔（秒）" rules={[{ required: true }]}>
            <InputNumber min={300} max={86400} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="retention_days" label="指标保留天数" rules={[{ required: true }]}>
            <InputNumber min={1} max={365} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
