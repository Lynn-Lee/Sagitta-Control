import { useMemo, useState } from 'react'
import { Card, Col, Row } from 'antd'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  DatabaseOutlined,
  FileDoneOutlined,
  FileTextOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
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
import PageHeader from '@/components/common/PageHeader'

import ChartCard from './ChartCard'
import DashboardIntro from './DashboardIntro'
import EmptyChart from './EmptyChart'
import MetricCard from './MetricCard'
import SmallRangeSelector from './SmallRangeSelector'
import {
  ARCHIVE_COLORS,
  buildTopChartData,
  DASHBOARD_AXIS_TICK_STYLE,
  DASHBOARD_BAR_CHART_MARGIN,
  DASHBOARD_CHART_MARGIN,
  DASHBOARD_CHART_HEIGHT,
  DASHBOARD_GRID_STROKE,
  DASHBOARD_LEGEND_PROPS,
  DASHBOARD_PANEL_STYLE,
  DASHBOARD_TOOLTIP_STYLE,
  WORKFLOW_TOP_COLORS,
} from '../helpers'
import type { ArchiveOverviewResponse, DashboardStatCard } from '../types'

export default function ArchiveDashboardPage() {
  const [archiveDays, setArchiveDays] = useState<number>(7)
  const [archiveDaysInput, setArchiveDaysInput] = useState<number>(7)
  const archiveRangeLabel = `近${archiveDays}天`

  const { data: archiveOverview } = useQuery<ArchiveOverviewResponse>({
    queryKey: ['dashboard-archive-overview', archiveDays],
    queryFn: () => apiClient.get(`/monitor/dashboard/archive-overview/?days=${archiveDays}`).then(r => r.data),
    refetchInterval: 60000,
  })

  const archiveTrendData = useMemo(() => {
    if (!archiveOverview?.trend?.dates) return []
    return archiveOverview.trend.dates.map((date, index) => ({
      date: date.slice(5),
      submit_count: archiveOverview.trend?.submit_count[index] ?? 0,
      success_count: archiveOverview.trend?.success_count[index] ?? 0,
      failed_count: archiveOverview.trend?.failed_count[index] ?? 0,
      canceled_count: archiveOverview.trend?.canceled_count[index] ?? 0,
      estimated_rows: archiveOverview.trend?.estimated_rows[index] ?? 0,
      processed_rows: archiveOverview.trend?.processed_rows[index] ?? 0,
      active_stock_count: archiveOverview.trend?.active_stock_count[index] ?? 0,
    }))
  }, [archiveOverview])

  const archiveCards: DashboardStatCard[] = [
    { title: `${archiveRangeLabel}提交归档数`, value: archiveOverview?.cards?.period_submit_count ?? 0, icon: <FileTextOutlined />, color: ARCHIVE_COLORS.submit },
    { title: '待审批归档数', value: archiveOverview?.cards?.pending_count ?? 0, icon: <LockOutlined />, color: ARCHIVE_COLORS.activeStock },
    { title: '已审批待执行数', value: archiveOverview?.cards?.approved_count ?? 0, icon: <CheckCircleOutlined />, color: ARCHIVE_COLORS.success },
    { title: '定时待执行数', value: archiveOverview?.cards?.scheduled_count ?? 0, icon: <ClockCircleOutlined />, color: ARCHIVE_COLORS.scheduled },
    { title: '执行中归档数', value: archiveOverview?.cards?.running_count ?? 0, icon: <ThunderboltOutlined />, color: ARCHIVE_COLORS.running },
    { title: '暂停中归档数', value: archiveOverview?.cards?.paused_count ?? 0, icon: <StopOutlined />, color: ARCHIVE_COLORS.canceled },
    { title: `${archiveRangeLabel}成功归档数`, value: archiveOverview?.cards?.success_count ?? 0, icon: <CheckCircleOutlined />, color: ARCHIVE_COLORS.success },
    { title: `${archiveRangeLabel}失败归档数`, value: archiveOverview?.cards?.failed_count ?? 0, icon: <CloseCircleOutlined />, color: ARCHIVE_COLORS.failed },
    { title: `${archiveRangeLabel}取消归档数`, value: archiveOverview?.cards?.canceled_count ?? 0, icon: <CloseCircleOutlined />, color: ARCHIVE_COLORS.canceled },
    { title: `${archiveRangeLabel}预估影响行数`, value: archiveOverview?.cards?.estimated_rows ?? 0, icon: <DatabaseOutlined />, color: ARCHIVE_COLORS.rows },
    { title: `${archiveRangeLabel}已处理行数`, value: archiveOverview?.cards?.processed_rows ?? 0, icon: <FileDoneOutlined />, color: ARCHIVE_COLORS.running },
    { title: '高风险活跃归档数', value: archiveOverview?.cards?.high_risk_active_count ?? 0, icon: <SafetyCertificateOutlined />, color: ARCHIVE_COLORS.risk },
  ]

  return (
    <div>
      <PageHeader title="数据归档概览" marginBottom={20} />

      <Card
        title="数据归档概览"
        style={{ ...DASHBOARD_PANEL_STYLE, marginTop: 20 }}
        extra={
          <SmallRangeSelector
            days={archiveDays}
            setDays={setArchiveDays}
            daysInput={archiveDaysInput}
            setDaysInput={setArchiveDaysInput}
            scopeLabel={archiveOverview?.scope?.label}
          />
        }
      >
        <DashboardIntro>
          统计当前用户可见的数据归档任务；处理行数按归档作业记录汇总，停止或取消只影响后续批次。
        </DashboardIntro>
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          {archiveCards.map(card => (
            <Col key={card.title} xs={24} sm={12} lg={8} xl={6}>
              <MetricCard {...card} />
            </Col>
          ))}
        </Row>

        <Row gutter={[16, 16]}>
          <Col xs={24} lg={16}>
            <ChartCard title="归档任务趋势">
              {archiveTrendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <LineChart data={archiveTrendData} margin={DASHBOARD_CHART_MARGIN}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis dataKey="date" tick={DASHBOARD_AXIS_TICK_STYLE} />
                    <YAxis tick={DASHBOARD_AXIS_TICK_STYLE} allowDecimals={false} />
                    <Tooltip contentStyle={DASHBOARD_TOOLTIP_STYLE} />
                    <Legend {...DASHBOARD_LEGEND_PROPS} />
                    <Line type="monotone" dataKey="submit_count" stroke={ARCHIVE_COLORS.submit} name="提交归档数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="success_count" stroke={ARCHIVE_COLORS.success} name="成功归档数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="failed_count" stroke={ARCHIVE_COLORS.failed} name="失败归档数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="canceled_count" stroke={ARCHIVE_COLORS.canceled} name="取消归档数" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无归档任务趋势数据" hint="提交或执行归档任务后会形成趋势。" />
              )}
            </ChartCard>
          </Col>
          <Col xs={24} lg={8}>
            <ChartCard title="归档提交用户 Top 10">
              {archiveOverview?.top_submitters?.length ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <BarChart data={buildTopChartData(archiveOverview.top_submitters, 'count')} layout="vertical" margin={DASHBOARD_BAR_CHART_MARGIN} barSize={18}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis type="number" tick={DASHBOARD_AXIS_TICK_STYLE} allowDecimals={false} />
                    <YAxis dataKey="display_name" type="category" width={92} tick={DASHBOARD_AXIS_TICK_STYLE} />
                    <Tooltip contentStyle={DASHBOARD_TOOLTIP_STYLE} />
                    <Bar dataKey="count" name="提交归档数" radius={[0, 6, 6, 0]} maxBarSize={18}>
                      {buildTopChartData(archiveOverview.top_submitters, 'count').map((_, index) => (
                        <Cell key={index} fill={WORKFLOW_TOP_COLORS[index % WORKFLOW_TOP_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无提交用户排行数据" hint="归档提交后会显示高频提交人。" />
              )}
            </ChartCard>
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} lg={16}>
            <ChartCard title="归档数据量趋势">
              {archiveTrendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <LineChart data={archiveTrendData} margin={DASHBOARD_CHART_MARGIN}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis dataKey="date" tick={DASHBOARD_AXIS_TICK_STYLE} />
                    <YAxis tick={DASHBOARD_AXIS_TICK_STYLE} allowDecimals={false} />
                    <Tooltip contentStyle={DASHBOARD_TOOLTIP_STYLE} />
                    <Legend {...DASHBOARD_LEGEND_PROPS} />
                    <Line type="monotone" dataKey="estimated_rows" stroke={ARCHIVE_COLORS.rows} name="预估影响行数" strokeWidth={2} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="processed_rows" stroke={ARCHIVE_COLORS.running} name="已处理行数" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无归档数据量趋势" hint="归档作业记录产生后会展示影响行数。" />
              )}
            </ChartCard>
          </Col>
          <Col xs={24} lg={8}>
            <ChartCard title="热点归档实例 Top 10">
              {archiveOverview?.top_instances?.length ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <BarChart data={buildTopChartData(archiveOverview.top_instances, 'count')} layout="vertical" margin={DASHBOARD_BAR_CHART_MARGIN} barSize={18}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis type="number" tick={DASHBOARD_AXIS_TICK_STYLE} allowDecimals={false} />
                    <YAxis dataKey="instance_name" type="category" width={92} tick={DASHBOARD_AXIS_TICK_STYLE} />
                    <Tooltip contentStyle={DASHBOARD_TOOLTIP_STYLE} />
                    <Bar dataKey="count" name="归档任务数" radius={[0, 6, 6, 0]} maxBarSize={18}>
                      {buildTopChartData(archiveOverview.top_instances, 'count').map((_, index) => (
                        <Cell key={index} fill={WORKFLOW_TOP_COLORS[index % WORKFLOW_TOP_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无归档实例排行数据" hint="归档任务关联实例后会显示热点排序。" />
              )}
            </ChartCard>
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} lg={16}>
            <ChartCard title="活跃归档库存趋势">
              {archiveTrendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <AreaChart data={archiveTrendData} margin={DASHBOARD_CHART_MARGIN}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis dataKey="date" tick={DASHBOARD_AXIS_TICK_STYLE} />
                    <YAxis tick={DASHBOARD_AXIS_TICK_STYLE} allowDecimals={false} />
                    <Tooltip formatter={(value: number | string) => [`${value}`, '截至当日结束活跃归档任务数']} contentStyle={DASHBOARD_TOOLTIP_STYLE} />
                    <Legend {...DASHBOARD_LEGEND_PROPS} />
                    <Area
                      type="monotone"
                      dataKey="active_stock_count"
                      stroke={ARCHIVE_COLORS.activeStock}
                      fill={ARCHIVE_COLORS.activeStock}
                      fillOpacity={0.16}
                      name="活跃归档库存"
                      strokeWidth={2}
                      dot={{ r: 2 }}
                      activeDot={{ r: 4 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无活跃归档库存数据" hint="活跃归档任务产生后会显示库存变化。" />
              )}
            </ChartCard>
          </Col>
          <Col xs={24} lg={8}>
            <ChartCard title="热点归档表 Top 10">
              {archiveOverview?.top_tables?.length ? (
                <ResponsiveContainer width="100%" height={DASHBOARD_CHART_HEIGHT}>
                  <BarChart data={buildTopChartData(archiveOverview.top_tables, 'estimated_rows')} layout="vertical" margin={DASHBOARD_BAR_CHART_MARGIN} barSize={18}>
                    <CartesianGrid strokeDasharray="3 3" stroke={DASHBOARD_GRID_STROKE} />
                    <XAxis type="number" tick={DASHBOARD_AXIS_TICK_STYLE} allowDecimals={false} />
                    <YAxis dataKey="source_label" type="category" width={108} tick={DASHBOARD_AXIS_TICK_STYLE} />
                    <Tooltip contentStyle={DASHBOARD_TOOLTIP_STYLE} />
                    <Bar dataKey="estimated_rows" name="预估影响行数" radius={[0, 6, 6, 0]} maxBarSize={18}>
                      {buildTopChartData(archiveOverview.top_tables, 'estimated_rows').map((_, index) => (
                        <Cell key={index} fill={WORKFLOW_TOP_COLORS[index % WORKFLOW_TOP_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart text="暂无归档表排行数据" hint="归档表产生影响行数后会显示排序。" />
              )}
            </ChartCard>
          </Col>
        </Row>
      </Card>
    </div>
  )
}
