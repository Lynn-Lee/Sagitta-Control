import { Card, Col, Row, Typography } from 'antd'
import {
  AppstoreOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import apiClient from '@/api/client'
import PageHeader from '@/components/common/PageHeader'
import { formatDbTypeLabel } from '@/utils/dbType'

import ChartCard from './ChartCard'
import DashboardIntro from './DashboardIntro'
import EmptyChart from './EmptyChart'
import MetricCard from './MetricCard'
import {
  buildTopChartData,
  DASHBOARD_AXIS_TICK_STYLE,
  DASHBOARD_BAR_CHART_MARGIN,
  CHART_COLORS,
  DASHBOARD_CHART_HEIGHT,
  DASHBOARD_GRID_STROKE,
  DASHBOARD_PANEL_STYLE,
  DASHBOARD_TOOLTIP_STYLE,
  WORKFLOW_TOP_COLORS,
} from '../helpers'
import type { DashboardStatCard, InstanceOverviewResponse } from '../types'

const { Text } = Typography

export default function InstanceDashboardPage() {
  const { data: instanceOverview } = useQuery<InstanceOverviewResponse>({
    queryKey: ['dashboard-instance-overview'],
    queryFn: () => apiClient.get('/monitor/dashboard/instance-overview/').then(r => r.data),
    refetchInterval: 60000,
  })

  const instanceCards: DashboardStatCard[] = [
    { title: '可见实例数', value: instanceOverview?.cards?.visible_instance_count ?? 0, icon: <DatabaseOutlined />, color: CHART_COLORS.primary },
    { title: '已同步库/Schema数', value: instanceOverview?.cards?.synced_database_count ?? 0, icon: <AppstoreOutlined />, color: CHART_COLORS.primary },
    { title: '已启用库/Schema数', value: instanceOverview?.cards?.enabled_database_count ?? 0, icon: <CheckCircleOutlined />, color: CHART_COLORS.success },
    { title: '已禁用库/Schema数', value: instanceOverview?.cards?.disabled_database_count ?? 0, icon: <StopOutlined />, color: CHART_COLORS.warning },
  ]

  const instanceTypeChartData = buildTopChartData(instanceOverview?.instance_type_distribution, 'count').map(item => ({
    ...item,
    label: formatDbTypeLabel(String(item.db_type || '')),
  }))
  const instanceTypeChartHeight = Math.max(DASHBOARD_CHART_HEIGHT, instanceTypeChartData.length * 28)

  return (
    <div>
      <PageHeader title="实例与库概览" marginBottom={20} />

      <Card
        title="实例与库概览"
        style={{ ...DASHBOARD_PANEL_STYLE, marginTop: 20 }}
        extra={
          <Text type="secondary">
            {instanceOverview?.scope?.label || '可见资源范围'}
          </Text>
        }
      >
        <DashboardIntro>
          统计当前用户权限范围内可见的实例，以及已同步到平台的库/Schema 数量；库/Schema 按已启用和已禁用分别汇总。
        </DashboardIntro>

        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          {instanceCards.map(card => (
            <Col key={card.title} xs={24} sm={12} lg={12} xl={6}>
              <MetricCard {...card} />
            </Col>
          ))}
        </Row>

        <Row gutter={[16, 16]}>
          <Col xs={24} lg={14}>
            <ChartCard title="实例类型分布">
              {instanceTypeChartData.length ? (
                <ResponsiveContainer width="100%" height={instanceTypeChartHeight}>
                  <BarChart
                    data={instanceTypeChartData}
                    layout="vertical"
                    margin={DASHBOARD_BAR_CHART_MARGIN}
                    barSize={18}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis type="number" tick={DASHBOARD_AXIS_TICK_STYLE} allowDecimals={false} />
                    <YAxis
                      dataKey="label"
                      type="category"
                      width={118}
                      interval={0}
                      minTickGap={0}
                      tick={DASHBOARD_AXIS_TICK_STYLE}
                      tickMargin={8}
                    />
                    <Tooltip contentStyle={DASHBOARD_TOOLTIP_STYLE} />
                    <Bar dataKey="count" name="实例数" radius={[0, 6, 6, 0]} maxBarSize={18}>
                      {instanceTypeChartData.map((_, index) => (
                        <Cell key={index} fill={WORKFLOW_TOP_COLORS[index % WORKFLOW_TOP_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无实例分布数据" hint="同步实例后会显示数据库类型构成。" />
              )}
            </ChartCard>
          </Col>
          <Col xs={24} lg={10}>
            <Row gutter={[16, 16]}>
              <Col span={24}>
                <ChartCard title="实例状态分布">
                  {instanceOverview?.instance_status_distribution?.length ? (
                    <ResponsiveContainer width="100%" height={140}>
                      <BarChart
                        data={buildTopChartData(instanceOverview.instance_status_distribution, 'count')}
                        layout="vertical"
                        margin={DASHBOARD_BAR_CHART_MARGIN}
                        barSize={20}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                        <XAxis type="number" tick={DASHBOARD_AXIS_TICK_STYLE} allowDecimals={false} />
                        <YAxis dataKey="label" type="category" width={92} tick={DASHBOARD_AXIS_TICK_STYLE} />
                        <Tooltip contentStyle={DASHBOARD_TOOLTIP_STYLE} />
                        <Bar dataKey="count" name="实例数" radius={[0, 6, 6, 0]} maxBarSize={20}>
                          {buildTopChartData(instanceOverview.instance_status_distribution, 'count').map((item, index) => (
                            <Cell
                              key={index}
                              fill={String(item.label).includes('禁用') ? CHART_COLORS.warning : CHART_COLORS.success}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <EmptyChart text="暂无实例状态数据" hint="启用或禁用实例后会展示状态占比。" height={140} />
                  )}
                </ChartCard>
              </Col>
              <Col span={24}>
                <ChartCard title="库/Schema 状态分布">
                  {instanceOverview?.database_status_distribution?.length ? (
                    <ResponsiveContainer width="100%" height={140}>
                      <BarChart
                        data={buildTopChartData(instanceOverview.database_status_distribution, 'count')}
                        layout="vertical"
                        margin={DASHBOARD_BAR_CHART_MARGIN}
                        barSize={20}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                        <XAxis type="number" tick={DASHBOARD_AXIS_TICK_STYLE} allowDecimals={false} />
                        <YAxis dataKey="label" type="category" width={108} tick={DASHBOARD_AXIS_TICK_STYLE} />
                        <Tooltip contentStyle={DASHBOARD_TOOLTIP_STYLE} />
                        <Bar dataKey="count" name="数量" radius={[0, 6, 6, 0]} maxBarSize={20}>
                          {buildTopChartData(instanceOverview.database_status_distribution, 'count').map((item, index) => (
                            <Cell
                              key={index}
                              fill={String(item.label).includes('禁用') ? CHART_COLORS.warning : CHART_COLORS.success}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <EmptyChart text="暂无库/Schema 状态数据" hint="同步库/Schema 后会展示启停状态。" height={140} />
                  )}
                </ChartCard>
              </Col>
            </Row>
          </Col>
        </Row>
      </Card>
    </div>
  )
}
