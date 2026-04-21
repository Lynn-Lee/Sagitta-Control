import { useState } from 'react'
import {
  Button, Card, DatePicker, Input, InputNumber, Select,
  Space, Table, Tabs, Tag, Typography, Tooltip, Grid,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { workflowApi } from '@/api/workflow'
import { instanceApi } from '@/api/instance'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'
import { useAuthStore } from '@/store/auth'
import { formatDbTypeLabel } from '@/utils/dbType'
import dayjs from 'dayjs'

const { Text } = Typography
const { Option } = Select
const { RangePicker } = DatePicker
const { useBreakpoint } = Grid

const STATUS_COLOR: Record<number, string> = {
  0: 'processing', 1: 'error', 2: 'success', 3: 'warning',
  4: 'default', 5: 'processing', 6: 'success', 7: 'error', 8: 'default',
}

const renderWorkflowName = (navigate: ReturnType<typeof useNavigate>, maxWidth = 350) =>
  (name: string, r: any) => (
    <Tooltip title={name}>
      <a
        onClick={() => navigate(`/workflow/${r.id}`)}
        style={{
          fontWeight: 500,
          display: 'inline-block',
          maxWidth,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {name}
      </a>
    </Tooltip>
  )

const renderInstance = (_: unknown, r: any) => (
  <Text style={{ fontSize: 12, fontWeight: 500 }}>
    {r.instance_name || <Text type="secondary">ID:{r.instance_id}</Text>}
  </Text>
)

const renderDbName = (v?: string) =>
  v ? <Text style={{ fontSize: 12 }}>{v}</Text> : <Text type="secondary">—</Text>

const renderAuditChain = (v?: string, maxWidth = 420) => (
  <Tooltip title={v || '—'}>
    <Text
      style={{
        fontSize: 12,
        color: '#5f6470',
        display: 'inline-block',
        maxWidth,
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
      }}
    >
      {v || '—'}
    </Text>
  </Tooltip>
)

const renderCurrentNode = (v: string | undefined, r: any) => {
  const currentNode = r.status === 0 ? (v || '—') : '—'
  if (currentNode === '—') return <Text type="secondary">—</Text>
  return (
    <Tooltip title={currentNode}>
      <Tag
        color="processing"
        style={{
          maxWidth: 160,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          borderRadius: 999,
          fontWeight: 500,
          display: 'inline-block',
          textAlign: 'center',
        }}
      >
        {currentNode}
      </Tag>
    </Tooltip>
  )
}

const renderStatus = (s: number, r: any) => (
  <Tag
    color={STATUS_COLOR[s]}
    style={{
      minWidth: 72,
      textAlign: 'center',
      borderRadius: 999,
      fontWeight: 500,
    }}
  >
    {r.status_desc}
  </Tag>
)

const renderDate = (v?: string) => v ? dayjs(v).format('MM-DD HH:mm') : '—'

const EXECUTION_MODE_LABEL: Record<string, string> = {
  immediate: '立即',
  scheduled: '定时',
  external: '外部',
}

const renderExecutionInfo = (_: unknown, r: any) => {
  if (!r.execute_mode) return <Text type="secondary">待决策</Text>
  const color = r.execute_mode === 'external' ? 'purple' : r.execute_mode === 'scheduled' ? 'warning' : 'blue'
  return (
    <Space size={4} direction="vertical">
      <Tag color={color} style={{ width: 'fit-content', marginInlineEnd: 0 }}>
        {EXECUTION_MODE_LABEL[r.execute_mode] || r.execute_mode}
      </Tag>
      {r.scheduled_execute_at && <Text type="secondary" style={{ fontSize: 12 }}>{renderDate(r.scheduled_execute_at)}</Text>}
      {r.external_executed_at && <Text type="secondary" style={{ fontSize: 12 }}>{renderDate(r.external_executed_at)}</Text>}
    </Space>
  )
}

export default function WorkflowList() {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const [activeTab, setActiveTab] = useState<'mine' | 'audit' | 'execute' | 'scope'>('mine')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<number | undefined>()
  const [instanceFilter, setInstanceFilter] = useState<number | undefined>()
  const [engineerFilter, setEngineerFilter] = useState('')
  const [dbNameFilter, setDbNameFilter] = useState('')
  const [dateRange, setDateRange] = useState<[string, string] | null>(null)
  const [page, setPage] = useState(1)

  const { data: instanceData } = useQuery({
    queryKey: ['instances-for-wf-filter'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })

  const queryParams = {
    view: activeTab,
    search: search || undefined,
    status: statusFilter,
    instance_id: instanceFilter,
    engineer: engineerFilter || undefined,
    db_name: dbNameFilter || undefined,
    date_start: dateRange?.[0] || undefined,
    date_end: dateRange?.[1] || undefined,
    page,
    page_size: 20,
  }

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['workflows', queryParams],
    queryFn: () => workflowApi.list(queryParams),
  })
  const { data: scopePreview } = useQuery({
    queryKey: ['workflow-scope-preview', user?.id],
    queryFn: () => workflowApi.list({ view: 'scope', page: 1, page_size: 1 }),
  })
  const showScopeTab = !!scopePreview?.scope && scopePreview.scope.mode !== 'self'

  const handleReset = () => {
    setSearch(''); setStatusFilter(undefined); setInstanceFilter(undefined)
    setEngineerFilter(''); setDbNameFilter(''); setDateRange(null); setPage(1)
  }

  const idColumn: ColumnsType<any>[number] = {
    title: 'ID', dataIndex: 'id', width: 65,
    render: (id) => (
      <a onClick={() => navigate(`/workflow/${id}`)}
        style={{ fontFamily: 'monospace', color: '#1558A8' }}>#{id}</a>
    ),
  }

  const detailColumn: ColumnsType<any>[number] = {
    title: '操作', width: 88, fixed: 'right',
    render: (_, r) => (
      <Button size="small" type="link" onClick={() => navigate(`/workflow/${r.id}`)}>详情</Button>
    ),
  }

  const mineColumns: ColumnsType<any> = [
    idColumn,
    { title: '工单名称', dataIndex: 'workflow_name', width: 290, render: renderWorkflowName(navigate, 260) },
    { title: '目标实例', key: 'instance', width: 220, render: renderInstance },
    { title: '数据库', dataIndex: 'db_name', width: 150, ellipsis: true, render: renderDbName },
    { title: '状态', dataIndex: 'status', width: 110, align: 'center', render: renderStatus },
    { title: '审批链路', dataIndex: 'audit_chain_text', width: 320, ellipsis: true, render: (v) => renderAuditChain(v, 290) },
    { title: '当前节点', dataIndex: 'current_node_name', width: 180, align: 'center', ellipsis: true, render: renderCurrentNode },
    { title: '提交时间', dataIndex: 'created_at', width: 170, render: renderDate },
    detailColumn,
  ]

  const auditColumns: ColumnsType<any> = [
    idColumn,
    { title: '申请人', key: 'engineer', width: 140, render: (_, r) => r.engineer_display || r.engineer },
    { title: '工单名称', dataIndex: 'workflow_name', width: 255, render: renderWorkflowName(navigate, 225) },
    { title: '目标实例', key: 'instance', width: 210, render: renderInstance },
    { title: '数据库', dataIndex: 'db_name', width: 150, ellipsis: true, render: renderDbName },
    { title: '状态', dataIndex: 'status', width: 110, align: 'center', render: renderStatus },
    { title: '当前节点', dataIndex: 'current_node_name', width: 190, align: 'center', ellipsis: true, render: renderCurrentNode },
    { title: '审批链路', dataIndex: 'audit_chain_text', width: 320, ellipsis: true, render: (v) => renderAuditChain(v, 290) },
    { title: '提交时间', dataIndex: 'created_at', width: 170, render: renderDate },
    detailColumn,
  ]

  const executeColumns: ColumnsType<any> = [
    idColumn,
    { title: '工单名称', dataIndex: 'workflow_name', width: 340, render: renderWorkflowName(navigate, 310) },
    { title: '目标实例', key: 'instance', width: 220, render: renderInstance },
    { title: '数据库', dataIndex: 'db_name', width: 150, ellipsis: true, render: renderDbName },
    { title: '提交人', key: 'engineer', width: 140, render: (_, r) => r.engineer_display || r.engineer },
    { title: '状态', dataIndex: 'status', width: 110, align: 'center', render: renderStatus },
    { title: '执行方式', key: 'execute_mode', width: 130, render: renderExecutionInfo },
    {
      title: '完成时间',
      dataIndex: 'finish_time',
      width: 170,
      render: renderDate,
    },
    {
      title: '提交时间',
      dataIndex: 'created_at',
      width: 170,
      render: renderDate,
    },
    detailColumn,
  ]

  const columns =
    activeTab === 'audit'
      ? auditColumns
      : activeTab === 'execute'
        ? executeColumns
        : activeTab === 'scope'
          ? auditColumns
          : mineColumns

  const engineerPlaceholder =
    activeTab === 'audit' ? '申请人' : '提交人'

  const filterWidth = (desktopWidth: number) => (isMobile ? '100%' : desktopWidth)

  return (
    <div>
      <PageHeader
        title="SQL 工单"
        meta={`共 ${data?.total ?? 0} 个`}
        actions={(
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/workflow/submit')}
          style={isMobile ? { width: '100%' } : undefined}>
            提交工单
          </Button>
        )}
      />

      {/* 查询条件 */}
      <FilterCard>
        <Tabs
          activeKey={activeTab}
          onChange={(key) => {
            setActiveTab(key as 'mine' | 'audit' | 'execute' | 'scope')
            setPage(1)
          }}
          items={[
            { key: 'mine', label: '我的工单' },
            { key: 'audit', label: '审批记录' },
            { key: 'execute', label: '执行记录' },
            ...(showScopeTab ? [{ key: 'scope', label: `工单视图（${scopePreview?.scope?.label || '统一视角'}）` }] : []),
          ]}
          style={{ marginBottom: 8 }}
        />
        <Space wrap size={[8, 8]} style={{ display: 'flex' }}>
          <Input
            placeholder="工单名称"
            allowClear
            prefix={<SearchOutlined style={{ color: '#AEAEB2' }} />}
            style={{ width: filterWidth(180) }}
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
          />
          <Select
            placeholder="状态"
            allowClear
            style={{ width: filterWidth(120) }}
            value={statusFilter}
            onChange={v => { setStatusFilter(v); setPage(1) }}
          >
            <Option value={0}>待审核</Option>
            <Option value={1}>审批驳回</Option>
            <Option value={2}>审核通过</Option>
            <Option value={3}>定时执行</Option>
            <Option value={4}>队列中</Option>
            <Option value={5}>执行中</Option>
            <Option value={6}>执行成功</Option>
            <Option value={7}>执行异常</Option>
            <Option value={8}>已取消</Option>
          </Select>
          <Select
            placeholder="目标实例"
            allowClear
            style={{ width: filterWidth(190) }}
            value={instanceFilter}
            onChange={v => { setInstanceFilter(v); setPage(1) }}
            showSearch
            optionFilterProp="label"
          >
            {instanceData?.items?.map((i: any) => (
              <Option key={i.id} value={i.id} label={i.instance_name}>
                <Tag color="blue" style={{ fontSize: 11 }}>{formatDbTypeLabel(i.db_type)}</Tag>
                {i.instance_name}
              </Option>
            ))}
          </Select>
          <Input
            placeholder="数据库名"
            allowClear
            style={{ width: filterWidth(130) }}
            value={dbNameFilter}
            onChange={e => { setDbNameFilter(e.target.value); setPage(1) }}
          />
          <Input
            placeholder={engineerPlaceholder}
            allowClear
            style={{ width: filterWidth(110) }}
            value={engineerFilter}
            onChange={e => { setEngineerFilter(e.target.value); setPage(1) }}
          />
          <RangePicker
            style={{ width: filterWidth(230) }}
            onChange={(_, strs) => {
              setDateRange(strs[0] ? [strs[0], strs[1]] : null)
              setPage(1)
            }}
          />
          <Button onClick={handleReset} style={isMobile ? { width: '100%' } : undefined}>重置</Button>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()}
            style={isMobile ? { width: '100%' } : undefined}>刷新</Button>
        </Space>
      </FilterCard>

      <Card
        style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}
        styles={{ body: { padding: 0 } }}
      >
        <Table
          dataSource={data?.items}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          locale={{ emptyText: <TableEmptyState title="暂无工单数据" /> }}
          tableLayout="fixed"
          scroll={{ x: activeTab === 'audit' || activeTab === 'scope' ? 1680 : activeTab === 'execute' ? 1710 : 1540 }}
          pagination={{
            total: data?.total,
            current: page,
            pageSize: 20,
            onChange: p => setPage(p),
            showSizeChanger: false,
            showTotal: t => `共 ${t} 个工单`,
          }}
        />
      </Card>
    </div>
  )
}
