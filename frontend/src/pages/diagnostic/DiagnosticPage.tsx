import { useMemo, useState } from 'react'
import { Button, Card, DatePicker, Drawer, Form, Input, InputNumber, Popconfirm, Select, Space, Table, Tabs, Tag, Typography, message } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs, { type Dayjs } from 'dayjs'
import { diagnosticApi, type SessionItem } from '@/api/diagnostic'
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

export default function DiagnosticPage() {
  const [instanceId, setInstanceId] = useState<number | undefined>()
  const [historySource, setHistorySource] = useState<HistorySource>('platform')
  const [historyPage, setHistoryPage] = useState(1)
  const [historyPageSize, setHistoryPageSize] = useState(50)
  const [historyFilters, setHistoryFilters] = useState<any>({})
  const [sqlDetail, setSqlDetail] = useState<SessionItem | null>(null)
  const [msgApi, msgCtx] = message.useMessage()
  const qc = useQueryClient()
  const hasPermission = useAuthStore((s) => s.hasPermission)
  const canKill = hasPermission('process_kill')

  const { data: instanceData } = useQuery({
    queryKey: ['instances-for-diag'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
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
        page: historyPage,
        page_size: historyPageSize,
      })
    },
    enabled: historySource === 'platform' || (!!instanceId && isOracle),
  })

  const sessionColumns: ColumnsType<SessionItem> = [
    { title: '会话ID', dataIndex: 'session_id', width: 110, fixed: 'left' },
    { title: 'Serial', dataIndex: 'serial', width: 90 },
    { title: '用户', dataIndex: 'username', width: 120, ellipsis: true },
    { title: '来源', dataIndex: 'host', width: 170, ellipsis: true },
    { title: '程序', dataIndex: 'program', width: 160, ellipsis: true },
    { title: '库/Schema', dataIndex: 'db_name', width: 130, ellipsis: true },
    { title: '命令', dataIndex: 'command', width: 100, render: (v) => v ? <Tag>{v}</Tag> : '-' },
    { title: '状态', dataIndex: 'state', width: 160, ellipsis: true },
    { title: '耗时(s)', dataIndex: 'time_seconds', width: 95, sorter: (a, b) => a.time_seconds - b.time_seconds },
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
    setHistoryPage(1)
    setHistoryFilters({
      username: values.username || undefined,
      db_name: values.db_name || undefined,
      sql_keyword: values.sql_keyword || undefined,
      min_seconds: values.min_seconds,
      date_start: range?.[0]?.toISOString(),
      date_end: range?.[1]?.toISOString(),
    })
  }

  const onHistoryTableChange = (pagination: TablePaginationConfig) => {
    setHistoryPage(pagination.current || 1)
    setHistoryPageSize(pagination.pageSize || 50)
  }

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
            在线 {processData?.total ?? 0} 个会话
          </Text>
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
                  dataSource={processData?.items ?? []}
                  columns={sessionColumns}
                  loading={processLoading}
                  size="small"
                  tableLayout="fixed"
                  scroll={{ x: 2100 }}
                  locale={{ emptyText: <TableEmptyState title={instanceId ? '暂无活跃会话' : '请先选择实例'} /> }}
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
                  <Form layout="inline" onFinish={applyHistoryFilters}>
                    <Form.Item name="range">
                      <RangePicker
                        showTime
                        className="query-history-range-picker"
                        style={{ width: 430, minWidth: 430 }}
                      />
                    </Form.Item>
                    <Form.Item name="username">
                      <Input placeholder="用户" allowClear style={{ width: 120 }} />
                    </Form.Item>
                    <Form.Item name="db_name">
                      <Input placeholder="库/Schema" allowClear style={{ width: 130 }} />
                    </Form.Item>
                    <Form.Item name="sql_keyword">
                      <Input placeholder="SQL 关键字" allowClear style={{ width: 180 }} />
                    </Form.Item>
                    <Form.Item name="min_seconds">
                      <InputNumber placeholder="最小耗时(s)" min={0} style={{ width: 130 }} />
                    </Form.Item>
                    {isOracle && instanceId && (
                      <Form.Item>
                        <Select value={historySource} onChange={setHistorySource} style={{ width: 140 }}>
                          <Select.Option value="platform">平台采样</Select.Option>
                          <Select.Option value="ash">Oracle ASH</Select.Option>
                          <Select.Option value="awr">Oracle AWR</Select.Option>
                        </Select>
                      </Form.Item>
                    )}
                    <Form.Item>
                      <Button type="primary" htmlType="submit">查询</Button>
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
    </div>
  )
}
