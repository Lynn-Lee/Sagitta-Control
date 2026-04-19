import { useState } from 'react'
import { Button, Card, DatePicker, Input, Select, Space, Table, Tag, Typography, Grid } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'
import apiClient from '@/api/client'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'

const { Text } = Typography
const { Option } = Select
const { RangePicker } = DatePicker
const { useBreakpoint } = Grid

const RESULT_COLOR: Record<string, string> = { success: 'success', fail: 'error' }
const MODULE_COLOR: Record<string, string> = {
  auth: 'blue', workflow: 'purple', query: 'cyan', instance: 'orange',
  user: 'gold', system: 'red', monitor: 'green',
}

export default function AuditLog() {
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const [username, setUsername] = useState('')
  const [module, setModule] = useState<string | undefined>()
  const [action, setAction] = useState('')
  const [result, setResult] = useState<string | undefined>()
  const [dateRange, setDateRange] = useState<[string, string] | null>(null)
  const [page, setPage] = useState(1)

  const params = {
    username: username || undefined,
    module,
    action: action || undefined,
    result,
    date_start: dateRange?.[0] || undefined,
    date_end: dateRange?.[1] || undefined,
    page,
    page_size: 50,
  }

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['audit-logs', params],
    queryFn: () => apiClient.get('/system/audit-logs/', { params }).then(r => r.data),
  })

  const handleReset = () => {
    setUsername(''); setModule(undefined); setAction('')
    setResult(undefined); setDateRange(null); setPage(1)
  }

  const filterWidth = (desktopWidth: number) => (isMobile ? '100%' : desktopWidth)

  const columns = [
    {
      title: '时间', dataIndex: 'created_at', width: 155,
      render: (v: string) => v ? dayjs(v).format('MM-DD HH:mm:ss') : '—',
    },
    {
      title: '操作人', dataIndex: 'username', width: 110,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: '模块', dataIndex: 'module', width: 90,
      render: (v: string) => <Tag color={MODULE_COLOR[v] || 'default'}>{v}</Tag>,
    },
    { title: '操作', dataIndex: 'action', width: 180, ellipsis: true },
    { title: '详情', dataIndex: 'detail', width: 340, ellipsis: true },
    {
      title: 'IP', dataIndex: 'ip_address', width: 130,
      render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{v || '—'}</Text>,
    },
    {
      title: '结果', dataIndex: 'result', width: 80,
      render: (v: string) => (
        <Tag color={RESULT_COLOR[v] || 'default'}>
          {v === 'success' ? '成功' : '失败'}
        </Tag>
      ),
    },
  ]

  return (
    <div>
      <PageHeader title="审计日志" meta={`共 ${data?.total ?? 0} 条`} />

      <FilterCard>
        <Space wrap size={[8, 8]} style={{ display: 'flex' }}>
          <Input placeholder="操作人" allowClear style={{ width: filterWidth(120) }}
            value={username} onChange={e => { setUsername(e.target.value); setPage(1) }} />
          <Select placeholder="模块" allowClear style={{ width: filterWidth(110) }}
            value={module} onChange={v => { setModule(v); setPage(1) }}>
            {(data?.modules || ['auth','workflow','query','instance','user','system','monitor'])
              .map((m: string) => <Option key={m} value={m}>{m}</Option>)}
          </Select>
          <Input placeholder="操作类型" allowClear style={{ width: filterWidth(140) }}
            value={action} onChange={e => { setAction(e.target.value); setPage(1) }} />
          <Select placeholder="结果" allowClear style={{ width: filterWidth(90) }}
            value={result} onChange={v => { setResult(v); setPage(1) }}>
            <Option value="success">成功</Option>
            <Option value="fail">失败</Option>
          </Select>
          <RangePicker style={{ width: filterWidth(230) }}
            onChange={(_, strs) => { setDateRange(strs[0] ? [strs[0], strs[1]] : null); setPage(1) }} />
          <Button onClick={handleReset} style={isMobile ? { width: '100%' } : undefined}>重置</Button>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()}
            style={isMobile ? { width: '100%' } : undefined}>刷新</Button>
        </Space>
      </FilterCard>

      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}
        styles={{ body: { padding: 0 } }}>
        <Table
          dataSource={data?.items}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          locale={{ emptyText: <TableEmptyState title="暂无审计日志" /> }}
          size="small"
          tableLayout="fixed"
          scroll={{ x: 1100 }}
          pagination={{
            total: data?.total, current: page, pageSize: 50,
            onChange: p => setPage(p), showSizeChanger: false,
            showTotal: t => `共 ${t} 条记录`,
          }}
        />
      </Card>
    </div>
  )
}
