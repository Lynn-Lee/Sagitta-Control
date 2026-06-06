import { useMemo, useState } from 'react'
import { Card, Col, Row, Statistic, Typography } from 'antd'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  FileDoneOutlined,
  FileTextOutlined,
  LockOutlined,
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

import EmptyChart from './EmptyChart'
import SmallRangeSelector from './SmallRangeSelector'
import {
  buildTopChartData,
  CHART_COLORS,
  DASHBOARD_CARD_STYLE,
  DASHBOARD_CHART_HEIGHT,
  DASHBOARD_GRID_STROKE,
  WORKFLOW_COLORS,
  WORKFLOW_TOP_COLORS,
} from '../helpers'
import type { WorkflowOverviewResponse } from '../types'

const { Text } = Typography

export default function WorkflowDashboardPage() {
  const [workflowDays, setWorkflowDays] = useState<number>(7)
  const [workflowDaysInput, setWorkflowDaysInput] = useState<number>(7)
  const workflowRangeLabel = `近${workflowDays}天`

  const { data: workflowOverview } = useQuery<WorkflowOverviewResponse>({
    queryKey: ['dashboard-workflow-overview', workflowDays],
    queryFn: () => apiClient.get(`/monitor/dashboard/workflow-overview/?days=${workflowDays}`).then(r => r.data),
    refetchInterval: 60000,
  })

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

  const workflowCards = [
    { title: `${workflowRangeLabel}提交工单数`, value: workflowOverview?.cards?.today_submit_count ?? 0, icon: <FileTextOutlined />, color: CHART_COLORS.primary },
    { title: `${workflowRangeLabel}审批通过工单数`, value: workflowOverview?.cards?.today_approved_count ?? 0, icon: <CheckCircleOutlined />, color: CHART_COLORS.success },
    { title: `${workflowRangeLabel}审批驳回工单数`, value: workflowOverview?.cards?.today_rejected_count ?? 0, icon: <CloseCircleOutlined />, color: CHART_COLORS.warning },
    { title: '待审批工单数', value: workflowOverview?.cards?.pending_count ?? 0, icon: <LockOutlined />, color: CHART_COLORS.purple },
    { title: '队列中工单数', value: workflowOverview?.cards?.queued_count ?? 0, icon: <ClockCircleOutlined />, color: CHART_COLORS.purple },
    { title: '执行中工单数', value: workflowOverview?.cards?.running_count ?? 0, icon: <ThunderboltOutlined />, color: CHART_COLORS.primary },
    { title: `${workflowRangeLabel}执行成功工单数`, value: workflowOverview?.cards?.today_execute_success_count ?? 0, icon: <CheckCircleOutlined />, color: CHART_COLORS.cyan },
    { title: `${workflowRangeLabel}执行失败工单数`, value: workflowOverview?.cards?.today_execute_failed_count ?? 0, icon: <CloseCircleOutlined />, color: CHART_COLORS.error },
    { title: `${workflowRangeLabel}取消工单数`, value: workflowOverview?.cards?.today_cancel_count ?? 0, icon: <CloseCircleOutlined />, color: CHART_COLORS.gray },
    { title: `${workflowRangeLabel}完成工单总数`, value: workflowOverview?.cards?.today_finished_count ?? 0, icon: <FileDoneOutlined />, color: CHART_COLORS.primaryDeep },
  ]

  return (
    <div>
      <PageHeader title="SQL 工单概览" marginBottom={20} />

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
          <Text type="secondary">
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
          <Col xs={24} lg={{ span: 8, offset: 16 }}>
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
    </div>
  )
}
