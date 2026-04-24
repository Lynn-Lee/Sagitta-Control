import { useMemo, useState } from 'react'
import { Button, Card, DatePicker, Input, Modal, Select, Space, Table, Tag, Typography, message, Grid } from 'antd'
import { CopyOutlined, EyeOutlined, ReloadOutlined, StarFilled, StarOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { instanceApi } from '@/api/instance'
import { queryApi, type QueryLogItem } from '@/api/query'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Text } = Typography
const { Option } = Select
const { RangePicker } = DatePicker
const { useBreakpoint } = Grid

const OPERATION_LABEL: Record<string, string> = {
  execute: '查询',
  export: '导出',
}

const OPERATION_COLOR: Record<string, string> = {
  execute: 'blue',
  export: 'purple',
}

export default function QueryHistoryPage() {
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const queryClient = useQueryClient()
  const [msgApi, msgCtx] = message.useMessage()
  const [page, setPage] = useState(1)
  const [instanceId, setInstanceId] = useState<number | undefined>()
  const [username, setUsername] = useState('')
  const [dbName, setDbName] = useState('')
  const [operationType, setOperationType] = useState<'execute' | 'export' | undefined>()
  const [masking, setMasking] = useState<boolean | undefined>()
  const [sqlKeyword, setSqlKeyword] = useState('')
  const [dateRange, setDateRange] = useState<[string, string] | null>(null)
  const [sqlDetail, setSqlDetail] = useState<QueryLogItem | null>(null)

  const { data: instanceData } = useQuery({
    queryKey: ['query-history-instances'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })

  const params = useMemo(() => ({
    instance_id: instanceId,
    username: username || undefined,
    db_name: dbName || undefined,
    operation_type: operationType,
    masking,
    sql_keyword: sqlKeyword || undefined,
    date_start: dateRange?.[0],
    date_end: dateRange?.[1],
    page,
    page_size: 50,
  }), [dateRange, dbName, instanceId, masking, operationType, page, sqlKeyword, username])

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['query-history', params],
    queryFn: () => queryApi.getLogs(params),
  })

  const favoriteMut = useMutation({
    mutationFn: (logId: number) => queryApi.toggleFavorite(logId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['query-history'] })
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || '收藏失败'),
  })

  const resetFilters = () => {
    setInstanceId(undefined)
    setUsername('')
    setDbName('')
    setOperationType(undefined)
    setMasking(undefined)
    setSqlKeyword('')
    setDateRange(null)
    setPage(1)
  }

  const filterWidth = (desktopWidth: number) => (isMobile ? '100%' : desktopWidth)

  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 155,
      render: (v: string) => v ? dayjs(v).format('MM-DD HH:mm:ss') : '—',
    },
    {
      title: '操作人',
      dataIndex: 'username',
      width: 120,
      render: (v: string) => <Text strong>{v || '—'}</Text>,
    },
    {
      title: '操作',
      dataIndex: 'operation_type',
      width: 86,
      render: (v: string) => <Tag color={OPERATION_COLOR[v] || 'default'}>{OPERATION_LABEL[v] || v}</Tag>,
    },
    {
      title: '实例 / 数据库',
      key: 'target',
      width: 220,
      render: (_: unknown, row: QueryLogItem) => (
        <Space direction="vertical" size={0}>
          <Text strong ellipsis style={{ maxWidth: 190 }}>{row.instance_name || `#${row.instance_id || '-'}`}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {formatDbTypeLabel(row.db_type)} / {row.db_name || '—'}
          </Text>
        </Space>
      ),
    },
    {
      title: 'SQL 摘要',
      dataIndex: 'sqllog',
      width: 360,
      ellipsis: true,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: '行数',
      dataIndex: 'effect_row',
      width: 90,
      render: (v: number) => <Text>{v ?? 0}</Text>,
    },
    {
      title: '耗时',
      dataIndex: 'cost_time_ms',
      width: 90,
      render: (v: number) => <Text type="secondary">{v ?? 0}ms</Text>,
    },
    {
      title: '脱敏',
      dataIndex: 'masking',
      width: 86,
      render: (v: boolean) => v ? <Tag color="warning">已脱敏</Tag> : <Tag>未脱敏</Tag>,
    },
    {
      title: '格式',
      dataIndex: 'export_format',
      width: 80,
      render: (v: string, row: QueryLogItem) => row.operation_type === 'export'
        ? <Tag>{(v || 'file').toUpperCase()}</Tag>
        : <Text type="secondary">—</Text>,
    },
    {
      title: 'IP',
      dataIndex: 'client_ip',
      width: 130,
      render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{v || '—'}</Text>,
    },
    {
      title: '结果',
      dataIndex: 'error',
      width: 90,
      render: (v: string) => v ? <Tag color="error">失败</Tag> : <Tag color="success">成功</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right' as const,
      width: 128,
      render: (_: unknown, row: QueryLogItem) => (
        <Space size={4}>
          <Button icon={<EyeOutlined />} size="small" onClick={() => setSqlDetail(row)} />
          <Button
            icon={<CopyOutlined />}
            size="small"
            onClick={async () => {
              await navigator.clipboard.writeText(row.sqllog)
              msgApi.success('SQL 已复制')
            }}
          />
          <Button
            icon={row.is_favorite ? <StarFilled /> : <StarOutlined />}
            size="small"
            loading={favoriteMut.isPending}
            onClick={() => favoriteMut.mutate(row.id)}
          />
        </Space>
      ),
    },
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader title="查询历史" meta={`共 ${data?.total ?? 0} 条`} />

      <FilterCard>
        <Space wrap size={[8, 8]} style={{ display: 'flex' }}>
          <RangePicker
            value={dateRange ? [dayjs(dateRange[0]), dayjs(dateRange[1])] : null}
            style={{ width: filterWidth(320), minWidth: isMobile ? undefined : 320 }}
            onChange={(_, strs) => { setDateRange(strs[0] ? [strs[0], strs[1]] : null); setPage(1) }}
          />
          <Input
            placeholder="操作人"
            allowClear
            style={{ width: filterWidth(120) }}
            value={username}
            onChange={(e) => { setUsername(e.target.value); setPage(1) }}
          />
          <Select
            placeholder="实例"
            allowClear
            showSearch
            optionFilterProp="label"
            style={{ width: filterWidth(180) }}
            value={instanceId}
            onChange={(v) => { setInstanceId(v); setPage(1) }}
            options={(instanceData?.items || []).map((inst) => ({
              value: inst.id,
              label: `${inst.instance_name} (${formatDbTypeLabel(inst.db_type)})`,
            }))}
          />
          <Input
            placeholder="数据库"
            allowClear
            style={{ width: filterWidth(120) }}
            value={dbName}
            onChange={(e) => { setDbName(e.target.value); setPage(1) }}
          />
          <Select
            placeholder="操作类型"
            allowClear
            style={{ width: filterWidth(110) }}
            value={operationType}
            onChange={(v) => { setOperationType(v); setPage(1) }}
          >
            <Option value="execute">查询</Option>
            <Option value="export">导出</Option>
          </Select>
          <Select
            placeholder="脱敏"
            allowClear
            style={{ width: filterWidth(100) }}
            value={masking}
            onChange={(v) => { setMasking(v); setPage(1) }}
          >
            <Option value={true}>已脱敏</Option>
            <Option value={false}>未脱敏</Option>
          </Select>
          <Input
            placeholder="SQL 关键字"
            allowClear
            style={{ width: filterWidth(160) }}
            value={sqlKeyword}
            onChange={(e) => { setSqlKeyword(e.target.value); setPage(1) }}
          />
          <Button onClick={resetFilters} style={isMobile ? { width: '100%' } : undefined}>重置</Button>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()} style={isMobile ? { width: '100%' } : undefined}>刷新</Button>
        </Space>
      </FilterCard>

      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }} styles={{ body: { padding: 0 } }}>
        <Table
          dataSource={data?.items}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          locale={{ emptyText: <TableEmptyState title="暂无查询历史" /> }}
          size="small"
          tableLayout="fixed"
          scroll={{ x: 1600 }}
          pagination={{
            total: data?.total,
            current: page,
            pageSize: 50,
            onChange: (p) => setPage(p),
            showSizeChanger: false,
            showTotal: (t) => `共 ${t} 条记录`,
          }}
        />
      </Card>

      <Modal
        title="SQL 明细"
        open={!!sqlDetail}
        width={820}
        onCancel={() => setSqlDetail(null)}
        footer={[
          <Button key="copy" icon={<CopyOutlined />} onClick={async () => {
            if (!sqlDetail) return
            await navigator.clipboard.writeText(sqlDetail.sqllog)
            msgApi.success('SQL 已复制')
          }}>
            复制 SQL
          </Button>,
          <Button key="close" type="primary" onClick={() => setSqlDetail(null)}>关闭</Button>,
        ]}
      >
        {sqlDetail && (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Space wrap>
              <Tag color={OPERATION_COLOR[sqlDetail.operation_type] || 'default'}>
                {OPERATION_LABEL[sqlDetail.operation_type] || sqlDetail.operation_type}
              </Tag>
              <Tag>{sqlDetail.effect_row} 行</Tag>
              <Tag>{sqlDetail.cost_time_ms}ms</Tag>
              {sqlDetail.masking && <Tag color="warning">已脱敏</Tag>}
              {sqlDetail.error && <Tag color="error">失败</Tag>}
            </Space>
            {sqlDetail.error && <Text type="danger">{sqlDetail.error}</Text>}
            <pre style={{
              margin: 0,
              padding: 12,
              maxHeight: 420,
              overflow: 'auto',
              background: '#111827',
              color: '#e5e7eb',
              borderRadius: 8,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}>
              {sqlDetail.sqllog}
            </pre>
          </Space>
        )}
      </Modal>
    </div>
  )
}
