import { Card, Col, Row, Statistic, Typography } from 'antd'
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

import EmptyChart from './EmptyChart'
import {
  buildTopChartData,
  CHART_COLORS,
  DASHBOARD_CARD_STYLE,
  DASHBOARD_CHART_HEIGHT,
  DASHBOARD_GRID_STROKE,
  WORKFLOW_TOP_COLORS,
} from '../helpers'
import type { InstanceOverviewResponse } from '../types'

const { Text } = Typography

export default function InstanceDashboardPage() {
  const { data: instanceOverview } = useQuery<InstanceOverviewResponse>({
    queryKey: ['dashboard-instance-overview'],
    queryFn: () => apiClient.get('/monitor/dashboard/instance-overview/').then(r => r.data),
    refetchInterval: 60000,
  })

  const instanceCards = [
    { title: '可见实例数', value: instanceOverview?.cards?.visible_instance_count ?? 0, icon: <DatabaseOutlined />, color: CHART_COLORS.primary },
    { title: '已同步库/Schema数', value: instanceOverview?.cards?.synced_database_count ?? 0, icon: <AppstoreOutlined />, color: CHART_COLORS.primary },
    { title: '已启用库/Schema数', value: instanceOverview?.cards?.enabled_database_count ?? 0, icon: <CheckCircleOutlined />, color: CHART_COLORS.success },
    { title: '已禁用库/Schema数', value: instanceOverview?.cards?.disabled_database_count ?? 0, icon: <StopOutlined />, color: CHART_COLORS.warning },
  ]

  return (
    <div>
      <PageHeader title="实例与库概览" marginBottom={20} />

      <Card
        title="实例与库概览"
        style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)', marginTop: 20 }}
        extra={
          <Text type="secondary">
            {instanceOverview?.scope?.label || '可见资源范围'}
          </Text>
        }
      >
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary">
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
                              fill={String(item.label).includes('禁用') ? CHART_COLORS.warning : CHART_COLORS.success}
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
                              fill={String(item.label).includes('禁用') ? CHART_COLORS.warning : CHART_COLORS.success}
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
