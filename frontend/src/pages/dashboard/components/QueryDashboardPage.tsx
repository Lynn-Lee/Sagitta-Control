import { useMemo, useState } from 'react'
import { Card, Col, Row, Statistic, Typography } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
  FileTextOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
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
import PageHeader from '@/components/common/PageHeader'

import EmptyChart from './EmptyChart'
import SmallRangeSelector from './SmallRangeSelector'
import {
  buildTopChartData,
  CHART_COLORS,
  DASHBOARD_CARD_STYLE,
  DASHBOARD_CHART_HEIGHT,
  DASHBOARD_GRID_STROKE,
  QUERY_GOVERNANCE_COLORS,
  TOP_USER_COLORS,
} from '../helpers'
import type { OverviewResponse } from '../types'

const { Text } = Typography

export default function QueryDashboardPage() {
  const [queryDays, setQueryDays] = useState<number>(7)
  const [queryDaysInput, setQueryDaysInput] = useState<number>(7)
  const queryRangeLabel = `近${queryDays}天`

  const { data: queryOverview } = useQuery<OverviewResponse>({
    queryKey: ['dashboard-query-overview', queryDays],
    queryFn: () => apiClient.get(`/monitor/dashboard/query-overview/?days=${queryDays}`).then(r => r.data),
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
      revoked_count: queryOverview.trend?.revoked_count[index] ?? 0,
      pending_stock_count: queryOverview.trend?.pending_stock_count[index] ?? 0,
    }))
  }, [queryOverview])

  const queryCards = [
    { title: `${queryRangeLabel}查询次数`, value: queryOverview?.cards?.period_query_count ?? 0, icon: <SearchOutlined />, color: CHART_COLORS.primary },
    { title: `${queryRangeLabel}查询用户数`, value: queryOverview?.cards?.period_query_user_count ?? 0, icon: <FileTextOutlined />, color: CHART_COLORS.purple },
    { title: `${queryRangeLabel}治理失败次数`, value: queryOverview?.cards?.period_failure_count ?? 0, icon: <CloseCircleOutlined />, color: CHART_COLORS.error },
    { title: `${queryRangeLabel}命中脱敏次数`, value: queryOverview?.cards?.period_masked_count ?? 0, icon: <SafetyCertificateOutlined />, color: CHART_COLORS.cyan },
    { title: '待审批查询权限申请数', value: queryOverview?.cards?.pending_query_priv_apply_count ?? 0, icon: <LockOutlined />, color: CHART_COLORS.warning },
    { title: `${queryRangeLabel}已通过查询权限申请数`, value: queryOverview?.cards?.approved_query_priv_apply_count ?? 0, icon: <CheckCircleOutlined />, color: CHART_COLORS.success },
    { title: `${queryRangeLabel}已驳回查询权限申请数`, value: queryOverview?.cards?.rejected_query_priv_apply_count ?? 0, icon: <CloseCircleOutlined />, color: CHART_COLORS.error },
    { title: `${queryRangeLabel}撤销查询权限数`, value: queryOverview?.cards?.revoked_query_privilege_count ?? 0, icon: <DeleteOutlined />, color: CHART_COLORS.gray },
  ]

  const pendingStockTooltipFormatter = (value: number | string) => [`${value}`, '截至当日结束待审批存量']

  return (
    <div>
      <PageHeader title="在线查询概览" marginBottom={20} />

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
          <Text type="secondary">
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
                    <Line type="monotone" dataKey="query_count" stroke={CHART_COLORS.primary} name="查询次数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="query_user_count" stroke={CHART_COLORS.purple} name="查询用户数" strokeWidth={2} dot={{ r: 2 }} />
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
                    <Line type="monotone" dataKey="revoked_count" stroke={QUERY_GOVERNANCE_COLORS.revoked} name="撤销权限数" strokeWidth={2} dot={{ r: 2 }} />
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
    </div>
  )
}
