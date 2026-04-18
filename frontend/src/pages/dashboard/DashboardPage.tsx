import { useMemo, useState } from 'react'
import { Card, Col, InputNumber, Row, Select, Space, Statistic, Typography } from 'antd'
import {
  AppstoreOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  DatabaseOutlined,
  FileDoneOutlined,
  FileTextOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  StopOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import apiClient from '@/api/client'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Title, Text } = Typography
const { Option } = Select

const RANGE_OPTIONS = [7, 14, 30, 60]
const DASHBOARD_CHART_HEIGHT = 300
const DASHBOARD_GRID_STROKE = 'rgba(0,0,0,0.06)'
const DASHBOARD_CARD_STYLE = { borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }
const TOP_USER_COLORS = ['#1558A8', '#4C8DFF', '#13c2c2', '#52c41a', '#fa8c16', '#722ed1', '#eb2f96', '#2f54eb', '#7cb305', '#fa541c']
const WORKFLOW_TOP_COLORS = ['#2F54EB', '#1890FF', '#13C2C2', '#52C41A', '#FA8C16', '#EB2F96', '#722ED1', '#A0D911', '#FA541C', '#1677FF']
const QUERY_GOVERNANCE_COLORS = {
  pendingStock: '#6F42C1',
  failure: '#E53935',
  masked: '#14B8A6',
  approved: '#52C41A',
  rejected: '#FA8C16',
}
const WORKFLOW_COLORS = {
  submit: '#1558A8',
  approved: '#52C41A',
  rejected: '#FA8C16',
  cancel: '#A0A0A0',
  executeFailed: '#E53935',
  queued: '#722ED1',
  running: '#1677FF',
  success: '#13C2C2',
  pendingStock: '#6F42C1',
}

type OverviewResponse = {
  scope?: { label?: string }
  cards?: Record<string, number>
  trend?: {
    dates: string[]
    query_count: number[]
    query_user_count: number[]
    failure_count: number[]
    masked_count: number[]
    approved_count: number[]
    rejected_count: number[]
    pending_stock_count: number[]
  }
  top_users?: Array<{ display_name: string; query_count: number }>
}

type WorkflowOverviewResponse = {
  scope?: { label?: string }
  cards?: Record<string, number>
  submit_trend?: {
    dates: string[]
    submit_count: number[]
    approved_count: number[]
  }
  governance_trend?: {
    dates: string[]
    rejected_count: number[]
    cancel_count: number[]
    execute_failed_count: number[]
  }
  execute_trend?: {
    dates: string[]
    queued_count: number[]
    running_count: number[]
    success_count: number[]
  }
  pending_stock_trend?: {
    dates: string[]
    pending_count: number[]
  }
  top_submitters?: Array<{ display_name: string; count: number }>
  top_instances?: Array<{ instance_name: string; count: number }>
  top_databases?: Array<{ db_name: string; count: number }>
  top_approvers?: Array<{ display_name: string; count: number }>
  top_execute_instances?: Array<{ instance_name: string; count: number }>
}

type InstanceOverviewResponse = {
  scope?: { label?: string }
  cards?: Record<string, number>
  instance_type_distribution?: Array<{ db_type: string; count: number }>
  instance_status_distribution?: Array<{ label: string; count: number }>
  database_status_distribution?: Array<{ label: string; count: number }>
}

function buildTopChartData<T extends Record<string, string | number>>(
  items: T[] | undefined,
  valueKey: keyof T,
) {
  return [...(items || [])].reverse().map(item => ({ ...item, [valueKey]: Number(item[valueKey] || 0) }))
}

function SmallRangeSelector({
  days,
  setDays,
  daysInput,
  setDaysInput,
  scopeLabel,
}: {
  days: number
  setDays: (value: number) => void
  daysInput: number
  setDaysInput: (value: number) => void
  scopeLabel?: string
}) {
  return (
    <Space size={8} align="center">
      <Text type="secondary" style={{ fontSize: 12 }}>
        {scopeLabel || '我的数据'}
      </Text>
      <Select
        value={days}
        onChange={value => {
          setDays(value)
          setDaysInput(value)
        }}
        style={{ width: 84 }}
        size="small"
      >
        {RANGE_OPTIONS.map(option => (
          <Option key={option} value={option}>
            {option}天
          </Option>
        ))}
      </Select>
      <Text type="secondary" style={{ fontSize: 12 }}>
        自定义
      </Text>
      <InputNumber
        min={1}
        max={365}
        value={daysInput}
        size="small"
        style={{ width: 92 }}
        controls={{
          upIcon: <span style={{ fontSize: 10, lineHeight: 1 }}>▲</span>,
          downIcon: <span style={{ fontSize: 10, lineHeight: 1 }}>▼</span>,
        }}
        onChange={value => setDaysInput(value || 7)}
        onPressEnter={() => setDays(daysInput)}
        onBlur={() => setDays(daysInput)}
        addonAfter="天"
      />
    </Space>
  )
}

function EmptyChart({ text }: { text: string }) {
  return (
    <div
      style={{
        height: DASHBOARD_CHART_HEIGHT,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#AEAEB2',
      }}
    >
      {text}
    </div>
  )
}

export default function DashboardPage() {
  const [queryDays, setQueryDays] = useState<number>(7)
  const [queryDaysInput, setQueryDaysInput] = useState<number>(7)
  const [workflowDays, setWorkflowDays] = useState<number>(7)
  const [workflowDaysInput, setWorkflowDaysInput] = useState<number>(7)

  const { data: queryOverview } = useQuery<OverviewResponse>({
    queryKey: ['dashboard-query-overview', queryDays],
    queryFn: () => apiClient.get(`/monitor/dashboard/query-overview/?days=${queryDays}`).then(r => r.data),
    refetchInterval: 60000,
  })

  const { data: workflowOverview } = useQuery<WorkflowOverviewResponse>({
    queryKey: ['dashboard-workflow-overview', workflowDays],
    queryFn: () => apiClient.get(`/monitor/dashboard/workflow-overview/?days=${workflowDays}`).then(r => r.data),
    refetchInterval: 60000,
  })

  const { data: instanceOverview } = useQuery<InstanceOverviewResponse>({
    queryKey: ['dashboard-instance-overview'],
    queryFn: () => apiClient.get('/monitor/dashboard/instance-overview/').then(r => r.data),
    refetchInterval: 60000,
  })

  const queryTrendData = useMemo(() => {
    if (!queryOverview?.trend?.dates) return []
    return queryOverview.trend.dates.map((date, index) => ({
      date: date.slice(5),
      query_count: queryOverview.trend?.query_count[index] ?? 0,
      query_user_count: queryOverview.trend?.query_user_count[index] ?? 0,
      failure_count: queryOverview.trend?.failure_count[index] ?? 0,
      masked_count: queryOverview.trend?.masked_count[index] ?? 0,
      approved_count: queryOverview.trend?.approved_count[index] ?? 0,
      rejected_count: queryOverview.trend?.rejected_count[index] ?? 0,
      pending_stock_count: queryOverview.trend?.pending_stock_count[index] ?? 0,
    }))
  }, [queryOverview])

  const workflowSubmitTrendData = useMemo(() => {
    if (!workflowOverview?.submit_trend?.dates) return []
    return workflowOverview.submit_trend.dates.map((date, index) => ({
      date: date.slice(5),
      submit_count: workflowOverview.submit_trend?.submit_count[index] ?? 0,
      approved_count: workflowOverview.submit_trend?.approved_count[index] ?? 0,
    }))
  }, [workflowOverview])

  const workflowGovernanceTrendData = useMemo(() => {
    if (!workflowOverview?.governance_trend?.dates) return []
    return workflowOverview.governance_trend.dates.map((date, index) => ({
      date: date.slice(5),
      rejected_count: workflowOverview.governance_trend?.rejected_count[index] ?? 0,
      cancel_count: workflowOverview.governance_trend?.cancel_count[index] ?? 0,
      execute_failed_count: workflowOverview.governance_trend?.execute_failed_count[index] ?? 0,
    }))
  }, [workflowOverview])

  const workflowExecuteTrendData = useMemo(() => {
    if (!workflowOverview?.execute_trend?.dates) return []
    return workflowOverview.execute_trend.dates.map((date, index) => ({
      date: date.slice(5),
      queued_count: workflowOverview.execute_trend?.queued_count[index] ?? 0,
      running_count: workflowOverview.execute_trend?.running_count[index] ?? 0,
      success_count: workflowOverview.execute_trend?.success_count[index] ?? 0,
    }))
  }, [workflowOverview])

  const workflowPendingStockData = useMemo(() => {
    if (!workflowOverview?.pending_stock_trend?.dates) return []
    return workflowOverview.pending_stock_trend.dates.map((date, index) => ({
      date: date.slice(5),
      pending_count: workflowOverview.pending_stock_trend?.pending_count[index] ?? 0,
    }))
  }, [workflowOverview])

  const queryCards = [
    { title: `${queryDays}天查询次数`, value: queryOverview?.cards?.period_query_count ?? 0, icon: <SearchOutlined />, color: '#1558A8' },
    { title: `${queryDays}天查询用户数`, value: queryOverview?.cards?.period_query_user_count ?? 0, icon: <FileTextOutlined />, color: '#722ed1' },
    { title: `${queryDays}天治理失败次数`, value: queryOverview?.cards?.period_failure_count ?? 0, icon: <CloseCircleOutlined />, color: '#f5222d' },
    { title: `${queryDays}天命中脱敏次数`, value: queryOverview?.cards?.period_masked_count ?? 0, icon: <SafetyCertificateOutlined />, color: '#13c2c2' },
    { title: '待审批查询权限申请数', value: queryOverview?.cards?.pending_query_priv_apply_count ?? 0, icon: <LockOutlined />, color: '#fa8c16' },
    { title: `${queryDays}天已通过查询权限申请数`, value: queryOverview?.cards?.approved_query_priv_apply_count ?? 0, icon: <CheckCircleOutlined />, color: '#52c41a' },
    { title: `${queryDays}天已驳回查询权限申请数`, value: queryOverview?.cards?.rejected_query_priv_apply_count ?? 0, icon: <CloseCircleOutlined />, color: '#ff4d4f' },
  ]

  const workflowCards = [
    { title: `${workflowDays}天提交工单数`, value: workflowOverview?.cards?.today_submit_count ?? 0, icon: <FileTextOutlined />, color: '#1558A8' },
    { title: `${workflowDays}天审批通过工单数`, value: workflowOverview?.cards?.today_approved_count ?? 0, icon: <CheckCircleOutlined />, color: '#52c41a' },
    { title: `${workflowDays}天审批驳回工单数`, value: workflowOverview?.cards?.today_rejected_count ?? 0, icon: <CloseCircleOutlined />, color: '#fa8c16' },
    { title: '待审批工单数', value: workflowOverview?.cards?.pending_count ?? 0, icon: <LockOutlined />, color: '#722ed1' },
    { title: '队列中工单数', value: workflowOverview?.cards?.queued_count ?? 0, icon: <ClockCircleOutlined />, color: '#722ed1' },
    { title: '执行中工单数', value: workflowOverview?.cards?.running_count ?? 0, icon: <ThunderboltOutlined />, color: '#1677FF' },
    { title: `${workflowDays}天执行成功工单数`, value: workflowOverview?.cards?.today_execute_success_count ?? 0, icon: <CheckCircleOutlined />, color: '#13C2C2' },
    { title: `${workflowDays}天执行失败工单数`, value: workflowOverview?.cards?.today_execute_failed_count ?? 0, icon: <CloseCircleOutlined />, color: '#E53935' },
    { title: `${workflowDays}天取消工单数`, value: workflowOverview?.cards?.today_cancel_count ?? 0, icon: <CloseCircleOutlined />, color: '#A0A0A0' },
    { title: `${workflowDays}天完成工单总数`, value: workflowOverview?.cards?.today_finished_count ?? 0, icon: <FileDoneOutlined />, color: '#2F54EB' },
  ]

  const instanceCards = [
    { title: '可见实例数', value: instanceOverview?.cards?.visible_instance_count ?? 0, icon: <DatabaseOutlined />, color: '#1558A8' },
    { title: '已同步库/Schema数', value: instanceOverview?.cards?.synced_database_count ?? 0, icon: <AppstoreOutlined />, color: '#1677FF' },
    { title: '已启用库/Schema数', value: instanceOverview?.cards?.enabled_database_count ?? 0, icon: <CheckCircleOutlined />, color: '#52C41A' },
    { title: '已禁用库/Schema数', value: instanceOverview?.cards?.disabled_database_count ?? 0, icon: <StopOutlined />, color: '#FA8C16' },
  ]

  const pendingStockTooltipFormatter = (value: number | string) => [`${value}`, '截至当日结束待审批存量']

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <Title level={2} style={{ margin: 0 }}>
          Dashboard
        </Title>
      </div>

      <Card
        title="在线查询概览"
        style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)', marginBottom: 20 }}
        extra={
          <SmallRangeSelector
            days={queryDays}
            setDays={setQueryDays}
            daysInput={queryDaysInput}
            setDaysInput={setQueryDaysInput}
            scopeLabel={queryOverview?.scope?.label}
          />
        }
      >
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            统计按当前用户可见的查询业务范围聚合；治理失败次数包含查询执行失败，以及查询权限申请/审批失败。
          </Text>
        </div>
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          {queryCards.map(card => (
            <Col key={card.title} xs={24} sm={12} lg={8} xl={6}>
              <Card style={DASHBOARD_CARD_STYLE} styles={{ body: { padding: '16px 18px' } }}>
                <Statistic
                  title={card.title}
                  value={card.value}
                  prefix={<span style={{ color: card.color, marginRight: 4 }}>{card.icon}</span>}
                  valueStyle={{ color: card.color, fontWeight: 600 }}
                />
              </Card>
            </Col>
          ))}
        </Row>

        <Row gutter={[16, 16]}>
          <Col xs={24} lg={16}>
            <Card title="查询趋势" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
              {queryTrendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <LineChart data={queryTrendData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="query_count" stroke="#1558A8" name="查询次数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="query_user_count" stroke="#722ed1" name="查询用户数" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无在线查询数据" />
              )}
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title="查询用户 Top 10" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
              {queryOverview?.top_users?.length ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <BarChart data={buildTopChartData(queryOverview.top_users, 'query_count')} layout="vertical" margin={{ top: 5, right: 16, left: 8, bottom: 5 }} barSize={18}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                    <YAxis dataKey="display_name" type="category" width={72} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="query_count" name="查询次数" radius={[0, 6, 6, 0]} maxBarSize={18}>
                      {buildTopChartData(queryOverview.top_users, 'query_count').map((_, index) => (
                        <Cell key={index} fill={TOP_USER_COLORS[index % TOP_USER_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无排行数据" />
              )}
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} lg={16}>
            <Card title="治理趋势" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
              {queryTrendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <LineChart data={queryTrendData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="failure_count" stroke={QUERY_GOVERNANCE_COLORS.failure} name="治理失败次数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="masked_count" stroke={QUERY_GOVERNANCE_COLORS.masked} name="命中脱敏次数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="approved_count" stroke={QUERY_GOVERNANCE_COLORS.approved} name="已通过申请数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="rejected_count" stroke={QUERY_GOVERNANCE_COLORS.rejected} name="已驳回申请数" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无治理趋势数据" />
              )}
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title="待审批库存趋势" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
              {queryTrendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <AreaChart data={queryTrendData} margin={{ top: 5, right: 16, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip formatter={pendingStockTooltipFormatter} />
                    <Legend />
                    <Area
                      type="monotone"
                      dataKey="pending_stock_count"
                      stroke={QUERY_GOVERNANCE_COLORS.pendingStock}
                      fill={QUERY_GOVERNANCE_COLORS.pendingStock}
                      fillOpacity={0.16}
                      name="待审批库存"
                      strokeWidth={2}
                      dot={{ r: 2 }}
                      activeDot={{ r: 4 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无待审批库存数据" />
              )}
            </Card>
          </Col>
        </Row>
      </Card>

      <Card
        title="SQL 工单概览"
        style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}
        extra={
          <SmallRangeSelector
            days={workflowDays}
            setDays={setWorkflowDays}
            daysInput={workflowDaysInput}
            setDaysInput={setWorkflowDaysInput}
            scopeLabel={workflowOverview?.scope?.label}
          />
        }
      >
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            统计按当前用户可见的工单业务范围聚合；审批相关排行展示的是当前范围内工单涉及的审批处理情况，不等同于当前登录人的个人审批工作量。
          </Text>
        </div>
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          {workflowCards.map(card => (
            <Col key={card.title} xs={24} sm={12} lg={8} xl={6}>
              <Card style={DASHBOARD_CARD_STYLE} styles={{ body: { padding: '16px 18px' } }}>
                <Statistic
                  title={card.title}
                  value={card.value}
                  prefix={<span style={{ color: card.color, marginRight: 4 }}>{card.icon}</span>}
                  valueStyle={{ color: card.color, fontWeight: 600 }}
                />
              </Card>
            </Col>
          ))}
        </Row>

        <Row gutter={[16, 16]}>
          <Col xs={24} lg={16}>
            <Card title="工单提交趋势" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
              {workflowSubmitTrendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <LineChart data={workflowSubmitTrendData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="submit_count" stroke={WORKFLOW_COLORS.submit} name="提交工单数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="approved_count" stroke={WORKFLOW_COLORS.approved} name="审批通过工单数" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无工单提交趋势数据" />
              )}
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title="工单提交用户 Top 10" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
              {workflowOverview?.top_submitters?.length ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <BarChart data={buildTopChartData(workflowOverview.top_submitters, 'count')} layout="vertical" margin={{ top: 5, right: 16, left: 8, bottom: 5 }} barSize={18}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                    <YAxis dataKey="display_name" type="category" width={72} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" name="提交工单数" radius={[0, 6, 6, 0]} maxBarSize={18}>
                      {buildTopChartData(workflowOverview.top_submitters, 'count').map((_, index) => (
                        <Cell key={index} fill={WORKFLOW_TOP_COLORS[index % WORKFLOW_TOP_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无排行数据" />
              )}
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} lg={16}>
            <Card title="工单治理趋势" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
              {workflowGovernanceTrendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <LineChart data={workflowGovernanceTrendData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="rejected_count" stroke={WORKFLOW_COLORS.rejected} name="审批驳回数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="cancel_count" stroke={WORKFLOW_COLORS.cancel} name="取消工单数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="execute_failed_count" stroke={WORKFLOW_COLORS.executeFailed} name="执行失败数" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无工单治理趋势数据" />
              )}
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title="热点实例 Top 10" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
              {workflowOverview?.top_instances?.length ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <BarChart data={buildTopChartData(workflowOverview.top_instances, 'count')} layout="vertical" margin={{ top: 5, right: 16, left: 8, bottom: 5 }} barSize={18}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                    <YAxis dataKey="instance_name" type="category" width={92} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" name="工单数" radius={[0, 6, 6, 0]} maxBarSize={18}>
                      {buildTopChartData(workflowOverview.top_instances, 'count').map((_, index) => (
                        <Cell key={index} fill={WORKFLOW_TOP_COLORS[index % WORKFLOW_TOP_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无实例排行数据" />
              )}
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} lg={16}>
            <Card title="执行趋势" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
              {workflowExecuteTrendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <LineChart data={workflowExecuteTrendData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="queued_count" stroke={WORKFLOW_COLORS.queued} name="队列中工单数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="running_count" stroke={WORKFLOW_COLORS.running} name="执行中工单数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="success_count" stroke={WORKFLOW_COLORS.success} name="执行成功工单数" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无执行趋势数据" />
              )}
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title="热点数据库 Top 10" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
              {workflowOverview?.top_databases?.length ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <BarChart data={buildTopChartData(workflowOverview.top_databases, 'count')} layout="vertical" margin={{ top: 5, right: 16, left: 8, bottom: 5 }} barSize={18}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                    <YAxis dataKey="db_name" type="category" width={92} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" name="工单数" radius={[0, 6, 6, 0]} maxBarSize={18}>
                      {buildTopChartData(workflowOverview.top_databases, 'count').map((_, index) => (
                        <Cell key={index} fill={WORKFLOW_TOP_COLORS[index % WORKFLOW_TOP_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无数据库排行数据" />
              )}
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} lg={16}>
            <Card title="待审批库存趋势" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
              {workflowPendingStockData.length > 0 ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <AreaChart data={workflowPendingStockData} margin={{ top: 5, right: 16, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip formatter={(value: number | string) => [`${value}`, '截至当日结束待审批工单存量']} />
                    <Legend />
                    <Area
                      type="monotone"
                      dataKey="pending_count"
                      stroke={WORKFLOW_COLORS.pendingStock}
                      fill={WORKFLOW_COLORS.pendingStock}
                      fillOpacity={0.16}
                      name="待审批库存"
                      strokeWidth={2}
                      dot={{ r: 2 }}
                      activeDot={{ r: 4 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无待审批库存数据" />
              )}
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title="工单相关审批人 Top 10" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
              {workflowOverview?.top_approvers?.length ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <BarChart data={buildTopChartData(workflowOverview.top_approvers, 'count')} layout="vertical" margin={{ top: 5, right: 16, left: 8, bottom: 5 }} barSize={18}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                    <YAxis dataKey="display_name" type="category" width={92} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" name="处理工单数" radius={[0, 6, 6, 0]} maxBarSize={18}>
                      {buildTopChartData(workflowOverview.top_approvers, 'count').map((_, index) => (
                        <Cell key={index} fill={WORKFLOW_TOP_COLORS[index % WORKFLOW_TOP_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无审批排行数据" />
              )}
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} lg={8} lg-offset={16}>
            <Card title="执行实例 Top 10" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
              {workflowOverview?.top_execute_instances?.length ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <BarChart data={buildTopChartData(workflowOverview.top_execute_instances, 'count')} layout="vertical" margin={{ top: 5, right: 16, left: 8, bottom: 5 }} barSize={18}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                    <YAxis dataKey="instance_name" type="category" width={92} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" name="执行工单数" radius={[0, 6, 6, 0]} maxBarSize={18}>
                      {buildTopChartData(workflowOverview.top_execute_instances, 'count').map((_, index) => (
                        <Cell key={index} fill={WORKFLOW_TOP_COLORS[index % WORKFLOW_TOP_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无执行实例排行数据" />
              )}
            </Card>
          </Col>
        </Row>
      </Card>

      <Card
        title="实例与库概览"
        style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)', marginTop: 20 }}
        extra={
          <Text type="secondary" style={{ fontSize: 12 }}>
            {instanceOverview?.scope?.label || '可见资源范围'}
          </Text>
        }
      >
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            统计当前用户权限范围内可见的实例，以及已同步到平台的库/Schema 数量；库/Schema 按已启用和已禁用分别汇总。
          </Text>
        </div>

        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          {instanceCards.map(card => (
            <Col key={card.title} xs={24} sm={12} lg={12} xl={6}>
              <Card style={DASHBOARD_CARD_STYLE} styles={{ body: { padding: '16px 18px' } }}>
                <Statistic
                  title={card.title}
                  value={card.value}
                  prefix={<span style={{ color: card.color, marginRight: 4 }}>{card.icon}</span>}
                  valueStyle={{ color: card.color, fontWeight: 600 }}
                />
              </Card>
            </Col>
          ))}
        </Row>

        <Row gutter={[16, 16]}>
          <Col xs={24} lg={14}>
            <Card title="实例类型分布" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
              {instanceOverview?.instance_type_distribution?.length ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <BarChart
                    data={buildTopChartData(instanceOverview.instance_type_distribution, 'count').map(item => ({
                      ...item,
                      label: formatDbTypeLabel(String(item.db_type || '')),
                    }))}
                    layout="vertical"
                    margin={{ top: 5, right: 16, left: 8, bottom: 5 }}
                    barSize={20}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                    <YAxis dataKey="label" type="category" width={108} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" name="实例数" radius={[0, 6, 6, 0]} maxBarSize={20}>
                      {buildTopChartData(instanceOverview.instance_type_distribution, 'count').map((_, index) => (
                        <Cell key={index} fill={WORKFLOW_TOP_COLORS[index % WORKFLOW_TOP_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无实例分布数据" />
              )}
            </Card>
          </Col>
          <Col xs={24} lg={10}>
            <Row gutter={[16, 16]}>
              <Col span={24}>
                <Card title="实例状态分布" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
                  {instanceOverview?.instance_status_distribution?.length ? (
                    <ResponsiveContainer width="100%" height={140}>
                      <BarChart
                        data={buildTopChartData(instanceOverview.instance_status_distribution, 'count')}
                        layout="vertical"
                        margin={{ top: 5, right: 16, left: 8, bottom: 5 }}
                        barSize={20}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                        <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                        <YAxis dataKey="label" type="category" width={92} tick={{ fontSize: 11 }} />
                        <Tooltip />
                        <Bar dataKey="count" name="实例数" radius={[0, 6, 6, 0]} maxBarSize={20}>
                          {buildTopChartData(instanceOverview.instance_status_distribution, 'count').map((item, index) => (
                            <Cell
                              key={index}
                              fill={String(item.label).includes('禁用') ? '#FA8C16' : '#52C41A'}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <EmptyChart text="暂无实例状态数据" />
                  )}
                </Card>
              </Col>
              <Col span={24}>
                <Card title="库/Schema 状态分布" style={DASHBOARD_CARD_STYLE} styles={{ body: { paddingTop: 12 } }}>
                  {instanceOverview?.database_status_distribution?.length ? (
                    <ResponsiveContainer width="100%" height={140}>
                      <BarChart
                        data={buildTopChartData(instanceOverview.database_status_distribution, 'count')}
                        layout="vertical"
                        margin={{ top: 5, right: 16, left: 8, bottom: 5 }}
                        barSize={20}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                        <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                        <YAxis dataKey="label" type="category" width={108} tick={{ fontSize: 11 }} />
                        <Tooltip />
                        <Bar dataKey="count" name="数量" radius={[0, 6, 6, 0]} maxBarSize={20}>
                          {buildTopChartData(instanceOverview.database_status_distribution, 'count').map((item, index) => (
                            <Cell
                              key={index}
                              fill={String(item.label).includes('禁用') ? '#FA8C16' : '#52C41A'}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <EmptyChart text="暂无库/Schema 状态数据" />
                  )}
                </Card>
              </Col>
            </Row>
          </Col>
        </Row>
      </Card>
    </div>
  )
}
