import { useMemo, useState } from 'react'
import { Card, Col, InputNumber, Row, Select, Statistic, Space, Typography } from 'antd'
import {
  FileTextOutlined,
  SearchOutlined,
  CloseCircleOutlined,
  LockOutlined, SafetyCertificateOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, BarChart, Bar, Cell, AreaChart, Area,
} from 'recharts'
import apiClient from '@/api/client'

const { Title, Text } = Typography
const { Option } = Select
const TOP_USER_COLORS = ['#1558A8', '#4C8DFF', '#13c2c2', '#52c41a', '#fa8c16', '#722ed1', '#eb2f96', '#2f54eb', '#7cb305', '#fa541c']
const DASHBOARD_CHART_HEIGHT = 300
const DASHBOARD_GRID_STROKE = 'rgba(0,0,0,0.06)'
const DASHBOARD_CARD_STYLE = { borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }
const DASHBOARD_GOVERNANCE_COLORS = {
  pendingStock: '#6F42C1',
  failure: '#E53935',
  masked: '#14B8A6',
  approved: '#52C41A',
  rejected: '#FA8C16',
}

export default function DashboardPage() {
  const [queryDays, setQueryDays] = useState<number>(7)
  const [queryDaysInput, setQueryDaysInput] = useState<number>(7)
  const { data: queryOverview } = useQuery({
    queryKey: ['dashboard-query-overview', queryDays],
    queryFn: () => apiClient.get(`/monitor/dashboard/query-overview/?days=${queryDays}`).then(r => r.data),
    refetchInterval: 60000,
  })

  const queryTrendData = useMemo(() => {
    if (!queryOverview?.trend?.dates) return []
    return queryOverview.trend.dates.map((date: string, index: number) => ({
      date: date.slice(5),
      query_count: queryOverview.trend.query_count[index] ?? 0,
      query_user_count: queryOverview.trend.query_user_count[index] ?? 0,
      failure_count: queryOverview.trend.failure_count[index] ?? 0,
      masked_count: queryOverview.trend.masked_count[index] ?? 0,
      approved_count: queryOverview.trend.approved_count[index] ?? 0,
      rejected_count: queryOverview.trend.rejected_count[index] ?? 0,
      pending_stock_count: queryOverview.trend.pending_stock_count[index] ?? 0,
    }))
  }, [queryOverview])
  const queryCards = [
    {
      title: `${queryDays}天查询次数`,
      value: queryOverview?.cards?.period_query_count ?? 0,
      icon: <SearchOutlined />,
      color: '#1558A8',
    },
    {
      title: `${queryDays}天查询用户数`,
      value: queryOverview?.cards?.period_query_user_count ?? 0,
      icon: <FileTextOutlined />,
      color: '#722ed1',
    },
    {
      title: `${queryDays}天失败次数`,
      value: queryOverview?.cards?.period_failure_count ?? 0,
      icon: <CloseCircleOutlined />,
      color: '#f5222d',
    },
    {
      title: `${queryDays}天命中脱敏次数`,
      value: queryOverview?.cards?.period_masked_count ?? 0,
      icon: <SafetyCertificateOutlined />,
      color: '#13c2c2',
    },
    {
      title: '待审批查询权限申请数',
      value: queryOverview?.cards?.pending_query_priv_apply_count ?? 0,
      icon: <LockOutlined />,
      color: '#fa8c16',
    },
    {
      title: `${queryDays}天已通过查询权限申请数`,
      value: queryOverview?.cards?.approved_query_priv_apply_count ?? 0,
      icon: <CheckCircleOutlined />,
      color: '#52c41a',
    },
    {
      title: `${queryDays}天已驳回查询权限申请数`,
      value: queryOverview?.cards?.rejected_query_priv_apply_count ?? 0,
      icon: <CloseCircleOutlined />,
      color: '#ff4d4f',
    },
  ]

  const pendingStockTooltipFormatter = (value: number | string) => [`${value}`, '截至当日结束待审批存量']
  const pendingStockLabelFormatter = (label: string | number) => `${label}`

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <Title level={2} style={{ margin: 0 }}>Dashboard</Title>
      </div>

      <Card
        title="在线查询概览"
        style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)', marginBottom: 20 }}
        extra={
          <Space size={8} align="center">
            <Text type="secondary" style={{ fontSize: 12 }}>
              {queryOverview?.scope?.label || '我的数据'}
            </Text>
            <Select value={queryDays} onChange={v => { setQueryDays(v); setQueryDaysInput(v) }}
              style={{ width: 80 }} size="small">
              {[7, 14, 30, 60].map(d => <Option key={d} value={d}>{d}天</Option>)}
            </Select>
            <Text type="secondary" style={{ fontSize: 12 }}>自定义</Text>
            <InputNumber
              min={1} max={365} value={queryDaysInput} size="small" style={{ width: 92 }}
              controls={{ upIcon: <span style={{ fontSize: 10, lineHeight: 1 }}>▲</span>, downIcon: <span style={{ fontSize: 10, lineHeight: 1 }}>▼</span> }}
              onChange={v => setQueryDaysInput(v || 7)}
              onPressEnter={() => setQueryDays(queryDaysInput)}
              onBlur={() => setQueryDays(queryDaysInput)}
              addonAfter="天"
            />
          </Space>
        }
      >
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          {queryCards.map(c => (
            <Col key={c.title} xs={24} sm={12} lg={8} xl={queryCards.length > 6 ? 6 : 4}>
              <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }} styles={{ body: { padding: '16px 18px' } }}>
                <Statistic
                  title={c.title}
                  value={c.value}
                  prefix={<span style={{ color: c.color, marginRight: 4 }}>{c.icon}</span>}
                  valueStyle={{ color: c.color, fontWeight: 600 }}
                />
              </Card>
            </Col>
          ))}
        </Row>

        <Row gutter={[16, 16]}>
          <Col xs={24} lg={16}>
            <Card
              title="查询趋势"
              style={DASHBOARD_CARD_STYLE}
              styles={{ body: { paddingTop: 12 } }}
            >
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
                <div style={{ height: DASHBOARD_CHART_HEIGHT, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#AEAEB2' }}>
                  暂无在线查询数据
                </div>
              )}
            </Card>
          </Col>

          <Col xs={24} lg={8}>
            <Card
              title="查询用户 Top 10"
              style={DASHBOARD_CARD_STYLE}
              styles={{ body: { paddingTop: 12 } }}
            >
              {queryOverview?.top_users?.length ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <BarChart
                    data={[...queryOverview.top_users].reverse()}
                    layout="vertical"
                    margin={{ top: 5, right: 16, left: 8, bottom: 5 }}
                    barSize={18}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                    <YAxis dataKey="display_name" type="category" width={72} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="query_count" name="查询次数" radius={[0, 6, 6, 0]} maxBarSize={18}>
                      {queryOverview.top_users.slice().reverse().map((_: unknown, index: number) => (
                        <Cell key={`cell-${index}`} fill={TOP_USER_COLORS[index % TOP_USER_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: DASHBOARD_CHART_HEIGHT, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#AEAEB2' }}>
                  暂无排行数据
                </div>
              )}
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} lg={16}>
            <Card
              title="治理趋势"
              style={DASHBOARD_CARD_STYLE}
              styles={{ body: { paddingTop: 12 } }}
            >
              {queryTrendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <LineChart data={queryTrendData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="failure_count" stroke={DASHBOARD_GOVERNANCE_COLORS.failure} name="失败次数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="masked_count" stroke={DASHBOARD_GOVERNANCE_COLORS.masked} name="命中脱敏次数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="approved_count" stroke={DASHBOARD_GOVERNANCE_COLORS.approved} name="已通过申请数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="rejected_count" stroke={DASHBOARD_GOVERNANCE_COLORS.rejected} name="已驳回申请数" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: DASHBOARD_CHART_HEIGHT, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#AEAEB2' }}>
                  暂无治理趋势数据
                </div>
              )}
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card
              title="待审批库存趋势"
              style={DASHBOARD_CARD_STYLE}
              styles={{ body: { paddingTop: 12 } }}
            >
              {queryTrendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <AreaChart data={queryTrendData} margin={{ top: 5, right: 16, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip formatter={pendingStockTooltipFormatter} labelFormatter={pendingStockLabelFormatter} />
                    <Legend />
                    <Area
                      type="monotone"
                      dataKey="pending_stock_count"
                      stroke={DASHBOARD_GOVERNANCE_COLORS.pendingStock}
                      fill={DASHBOARD_GOVERNANCE_COLORS.pendingStock}
                      fillOpacity={0.16}
                      name="待审批库存"
                      strokeWidth={2}
                      dot={{ r: 2 }}
                      activeDot={{ r: 4 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: DASHBOARD_CHART_HEIGHT, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#AEAEB2' }}>
                  暂无待审批库存数据
                </div>
              )}
            </Card>
          </Col>
        </Row>
      </Card>
    </div>
  )
}
