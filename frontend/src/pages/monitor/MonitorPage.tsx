import { useEffect, useMemo, useState } from 'react'
import type { MenuProps } from 'antd'
import { Alert, Button, Card, Descriptions, Dropdown, Form, Grid, Input, InputNumber, Modal, Progress, Select, Space, Statistic, Switch, Table, Tabs, Tag, Typography, message } from 'antd'
import { AlertOutlined, ApiOutlined, BarChartOutlined, DatabaseOutlined, DownOutlined, FieldTimeOutlined, PlayCircleOutlined, ReloadOutlined, SettingOutlined, StopOutlined, TableOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import apiClient from '@/api/client'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'
import { SessionInsightPanel } from '@/pages/diagnostic/DiagnosticPage'
import { SqlInsightPanel } from '@/pages/slowlog/SlowlogPage'
import { useAuthStore } from '@/store/auth'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Text } = Typography
const { Option } = Select
const { useBreakpoint } = Grid

interface MonitorSnapshot {
  collected_at?: string | null
  status: string
  error?: string
  missing_groups?: Record<string, string>
  is_up: boolean
  version?: string
  uptime_seconds?: number | null
  current_connections?: number | null
  active_sessions?: number | null
  max_connections?: number | null
  connection_usage?: number | null
  qps?: number | null
  tps?: number | null
  slow_queries?: number | null
  error_count?: number | null
  lock_waits?: number | null
  long_transactions?: number | null
  replication_lag_seconds?: number | null
  total_size_bytes?: number | null
  extra_metrics?: Record<string, any>
  health_score?: number
  risk_level?: string
  risk_label?: string
  risk_reasons?: string[]
}

interface MonitorInstance {
  instance_id: number
  instance_name: string
  db_type: string
  is_active: boolean
  config_id?: number | null
  config_enabled: boolean
  collect_interval?: number | null
  capacity_collect_interval?: number | null
  retention_days?: number | null
  last_metric_collect_at?: string | null
  last_capacity_collect_at?: string | null
  last_collect_status: string
  last_collect_error?: string
  latest?: MonitorSnapshot | null
  health_score?: number
  risk_level?: string
  risk_label?: string
  risk_reasons?: string[]
}

interface MonitorOverview {
  cards: Record<string, number>
  distributions: Record<string, Record<string, number>>
  items: MonitorInstance[]
}

interface UnifiedCollectConfigItem {
  instance_id: number
  instance_name: string
  db_type: string
  native: {
    id?: number | null
    is_enabled: boolean
    collect_interval: number
    capacity_collect_interval: number
    retention_days: number
    last_metric_collect_at?: string | null
    last_capacity_collect_at?: string | null
    last_collect_status: string
    last_collect_error: string
  }
  session: {
    id?: number | null
    is_enabled: boolean
    collect_interval: number
    retention_days: number
    last_collect_at?: string | null
    last_collect_status: string
    last_collect_error: string
    last_collect_count: number
  }
  sql: {
    id?: number | null
    is_enabled: boolean
    threshold_ms: number
    collect_interval: number
    retention_days: number
    collect_limit: number
    last_collect_at?: string | null
    last_collect_status: string
    last_collect_error: string
    last_collect_count: number
    last_collect_sources: string[]
    last_collect_message: string
  }
}

interface UnifiedCollectConfigListResponse {
  total: number
  items: UnifiedCollectConfigItem[]
}

interface BulkCollectConfigResponse {
  total: number
  success: number
  failed: string[]
}

const statusColor: Record<string, string> = {
  success: 'success',
  partial: 'warning',
  failed: 'error',
  pending: 'processing',
  not_configured: 'default',
  never: 'default',
  skipped: 'default',
}

const riskColor: Record<string, string> = {
  healthy: 'success',
  attention: 'processing',
  warning: 'warning',
  critical: 'error',
}

function formatBytes(value?: number | null) {
  if (value === null || value === undefined) return '暂无数据'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let size = Number(value)
  let idx = 0
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024
    idx += 1
  }
  return `${size.toFixed(idx === 0 ? 0 : 2)} ${units[idx]}`
}

function formatMetric(value?: number | string | null, suffix = '') {
  if (value === null || value === undefined || value === '') return '暂无数据'
  return `${value}${suffix}`
}

function formatTime(value?: string | null) {
  if (!value) return '暂无数据'
  return value.replace('T', ' ').slice(0, 19)
}

function formatDurationSeconds(value?: number | null) {
  if (value === null || value === undefined) return '暂无数据'
  const totalSeconds = Math.max(0, Math.floor(Number(value)))
  const days = Math.floor(totalSeconds / 86400)
  const hours = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const parts: string[] = []
  if (days) parts.push(`${days}天`)
  if (hours) parts.push(`${hours}小时`)
  if (minutes && parts.length < 2) parts.push(`${minutes}分钟`)
  if (!parts.length) parts.push(`${seconds}秒`)
  return parts.slice(0, 2).join(' ')
}

function StatusTag({ status }: { status?: string }) {
  const value = status || 'not_configured'
  const label: Record<string, string> = {
    success: '正常',
    partial: '部分缺失',
    failed: '采集失败',
    pending: '待采集',
    not_configured: '未配置',
    never: '未采集',
    skipped: '已跳过',
  }
  return <Tag color={statusColor[value] || 'default'}>{label[value] || value}</Tag>
}

function ConfigStatusTag({ row }: { row: Pick<MonitorInstance, 'config_id' | 'config_enabled'> }) {
  if (!row.config_id) return <Tag>未配置</Tag>
  return row.config_enabled ? <Tag color="success">已启用</Tag> : <Tag color="default">已停用</Tag>
}

function RiskTag({ level, label }: { level?: string; label?: string }) {
  const value = level || 'attention'
  return <Tag color={riskColor[value] || 'default'}>{label || value}</Tag>
}

function riskReasonText(row?: Pick<MonitorInstance, 'risk_reasons' | 'latest'> | null) {
  const reasons = row?.risk_reasons || row?.latest?.risk_reasons || []
  return reasons.length ? reasons.join('；') : '暂无明显风险'
}

function MetricCard({ title, value, suffix, danger }: { title: string; value?: number | string | null; suffix?: string; danger?: boolean }) {
  return (
    <div style={{ border: '1px solid rgba(0,0,0,0.08)', borderRadius: 8, padding: 16, minHeight: 92 }}>
      <Statistic title={title} value={formatMetric(value, suffix)} valueStyle={{ fontSize: 20, color: danger ? '#cf1322' : undefined }} />
    </div>
  )
}

export default function MonitorPage() {
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const hasPermission = useAuthStore((s) => s.hasPermission)
  const canManageConfig = hasPermission('observability_collect_manage')
  const canManageAlerts = hasPermission('observability_alert_manage')
  const canViewSessions = hasPermission('observability_session_view')
  const canViewSql = hasPermission('observability_sql_view')
  const [msgApi, msgCtx] = message.useMessage()
  const requestedView = searchParams.get('view')
  const requestedInstanceId = Number(searchParams.get('instance_id') || 0) || null
  const [mainTab, setMainTab] = useState(requestedView ? 'monitor' : 'instance-overview')
  const [workbenchTab, setWorkbenchTab] = useState(requestedView === 'sessions' ? 'sessions' : requestedView === 'sql' ? 'sql' : 'overview')
  const [selectedId, setSelectedId] = useState<number | null>(requestedInstanceId)
  const [dbTypeFilter, setDbTypeFilter] = useState<string | undefined>()
  const [riskFilter, setRiskFilter] = useState<string | undefined>()
  const [collectStatusFilter, setCollectStatusFilter] = useState<string | undefined>()
  const [trendHours, setTrendHours] = useState(24)
  const [alertRulesText, setAlertRulesText] = useState('{}')
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [configTarget, setConfigTarget] = useState<MonitorInstance | null>(null)
  const [configScope, setConfigScope] = useState<'single' | 'all'>('single')
  const [configOpen, setConfigOpen] = useState(false)
  const [tableDb, setTableDb] = useState<string | undefined>()
  const [tableSearch, setTableSearch] = useState('')
  const [tablePage, setTablePage] = useState(1)
  const [form] = Form.useForm()

  const { data, isLoading } = useQuery({
    queryKey: ['native-monitor-instances'],
    queryFn: () => apiClient.get('/monitor/native/instances/').then(r => r.data),
  })
  const { data: overview } = useQuery<MonitorOverview>({
    queryKey: ['native-monitor-overview'],
    queryFn: () => apiClient.get('/monitor/native/overview/').then(r => r.data),
  })
  const { data: collectConfigData } = useQuery<UnifiedCollectConfigListResponse>({
    queryKey: ['unified-collect-configs'],
    queryFn: () => apiClient.get('/monitor/native/collect-configs/').then(r => r.data),
  })
  const allInstances: MonitorInstance[] = useMemo(
    () => overview?.items || data?.items || [],
    [overview?.items, data?.items],
  )
  const collectConfigByInstance = useMemo(() => {
    const map = new Map<number, UnifiedCollectConfigItem>()
    ;(collectConfigData?.items || []).forEach(item => map.set(item.instance_id, item))
    return map
  }, [collectConfigData?.items])
  const instances = useMemo(() => allInstances.filter(item => {
    if (dbTypeFilter && item.db_type !== dbTypeFilter) return false
    if (riskFilter && item.risk_level !== riskFilter) return false
    if (collectStatusFilter && item.last_collect_status !== collectStatusFilter) return false
    return true
  }), [allInstances, dbTypeFilter, riskFilter, collectStatusFilter])
  const activeId = selectedId || instances[0]?.instance_id || null
  const active = instances.find(i => i.instance_id === activeId) || null

  const { data: detail } = useQuery({
    queryKey: ['native-monitor-detail', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: trendData } = useQuery({
    queryKey: ['native-monitor-trend', activeId, trendHours],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/trend/`, { params: { hours: trendHours } }).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: healthData } = useQuery({
    queryKey: ['native-monitor-health', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/health/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: topSqlData } = useQuery({
    queryKey: ['native-monitor-top-sql', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/top-sql/`).then(r => r.data),
    enabled: !!activeId && canViewSql,
  })
  const { data: waitsData } = useQuery({
    queryKey: ['native-monitor-waits', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/waits/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: growthData } = useQuery({
    queryKey: ['native-monitor-capacity-growth', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/capacity-growth/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: engineDetail } = useQuery({
    queryKey: ['native-monitor-engine-detail', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/engine-detail/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: alertRules } = useQuery({
    queryKey: ['native-monitor-alerts', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/alerts/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: dbCapacity } = useQuery({
    queryKey: ['native-monitor-db-capacity', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/databases/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: tableCapacity, isLoading: tableLoading } = useQuery({
    queryKey: ['native-monitor-table-capacity', activeId, tableDb, tableSearch, tablePage],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/tables/`, { params: { db_name: tableDb, search: tableSearch, page: tablePage, page_size: 100 } }).then(r => r.data),
    enabled: !!activeId,
  })
  const showOverviewActions = mainTab === 'instance-overview'

  useEffect(() => {
    if (requestedInstanceId) setSelectedId(requestedInstanceId)
    if (requestedView === 'sessions') {
      setMainTab('monitor')
      setWorkbenchTab('sessions')
    } else if (requestedView === 'sql') {
      setMainTab('monitor')
      setWorkbenchTab('sql')
    }
  }, [requestedInstanceId, requestedView])

  useEffect(() => {
    setAlertRulesText(JSON.stringify(alertRules?.rules || {}, null, 2))
  }, [alertRules?.rules])

  const invalidateCollectConfigQueries = (instanceId?: number | null) => {
    queryClient.invalidateQueries({ queryKey: ['unified-collect-configs'] })
    queryClient.invalidateQueries({ queryKey: ['native-monitor-instances'] })
    queryClient.invalidateQueries({ queryKey: ['native-monitor-overview'] })
    queryClient.invalidateQueries({ queryKey: ['session-collect-configs'] })
    queryClient.invalidateQueries({ queryKey: ['slowlog-configs'] })
    if (instanceId) {
      queryClient.invalidateQueries({ queryKey: ['native-monitor-detail', instanceId] })
    } else {
      queryClient.invalidateQueries({ queryKey: ['native-monitor-detail'] })
    }
  }

  const saveConfig = useMutation({
    mutationFn: ({ instanceId, values }: { instanceId: number; values: any }) => apiClient.put(`/monitor/native/instances/${instanceId}/collect-configs/`, values).then(r => r.data),
    onSuccess: (_data, variables) => {
      invalidateCollectConfigQueries(variables.instanceId)
      setConfigOpen(false)
      setConfigTarget(null)
      msgApi.success('采集配置已保存')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '保存失败'),
  })
  const saveAllConfig = useMutation<BulkCollectConfigResponse, any, any>({
    mutationFn: (values: any) => apiClient.put<BulkCollectConfigResponse>('/monitor/native/collect-configs/bulk/', values).then(r => r.data),
    onSuccess: (result) => {
      invalidateCollectConfigQueries()
      setConfigOpen(false)
      setConfigTarget(null)
      msgApi.success(`已配置 ${result.success}/${result.total} 个实例${result.failed?.length ? `，失败 ${result.failed.length} 个` : ''}`)
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '批量保存失败'),
  })
  const disableAllConfig = useMutation<BulkCollectConfigResponse, any, void>({
    mutationFn: () => apiClient.put<BulkCollectConfigResponse>('/monitor/native/collect-configs/bulk/', {
      native: {
        is_enabled: false,
        collect_interval: 60,
        capacity_collect_interval: 3600,
        retention_days: 30,
      },
      session: {
        is_enabled: false,
        collect_interval: 60,
        retention_days: 30,
      },
      sql: {
        is_enabled: false,
        threshold_ms: 1000,
        collect_interval: 300,
        retention_days: 30,
        collect_limit: 100,
      },
    }).then(r => r.data),
    onSuccess: (result) => {
      invalidateCollectConfigQueries()
      msgApi.success(`已关闭 ${result.success}/${result.total} 个实例采集${result.failed?.length ? `，失败 ${result.failed.length} 个` : ''}`)
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '批量关闭失败'),
  })
  const collectNow = useMutation({
    mutationFn: (instanceId: number) => apiClient.post(`/monitor/native/instances/${instanceId}/collect/`).then(r => r.data),
    onSuccess: (_data, instanceId) => {
      queryClient.invalidateQueries({ queryKey: ['native-monitor-instances'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-overview'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-detail', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-trend', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-db-capacity', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-table-capacity'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-health', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-top-sql', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-waits', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-capacity-growth', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-engine-detail', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['unified-collect-configs'] })
      msgApi.success('采集完成')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '采集失败'),
  })
  const collectAll = useMutation({
    mutationFn: async () => {
      let success = 0
      const failed: string[] = []
      for (const item of instances) {
        try {
          await apiClient.post(`/monitor/native/instances/${item.instance_id}/collect/`)
          success += 1
        } catch (error: any) {
          failed.push(`${item.instance_name}：${error.response?.data?.msg || '采集失败'}`)
        }
      }
      return { total: instances.length, success, failed }
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['native-monitor-instances'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-overview'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-detail'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-trend'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-db-capacity'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-table-capacity'] })
      if (result.failed.length) {
        msgApi.warning(`已采集 ${result.success}/${result.total} 个实例，${result.failed.length} 个失败`)
      } else {
        msgApi.success(`已采集全部 ${result.total} 个实例`)
      }
    },
  })
  const saveAlertRules = useMutation({
    mutationFn: async () => {
      const payload = JSON.parse(alertRulesText || '{}')
      return apiClient.put(`/monitor/native/instances/${activeId}/alerts/`, payload).then(r => r.data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['native-monitor-alerts', activeId] })
      msgApi.success('告警规则已保存')
    },
    onError: (e: any) => msgApi.error(e instanceof SyntaxError ? '告警规则 JSON 格式不正确' : e.response?.data?.msg || '保存告警规则失败'),
  })

  const latest: MonitorSnapshot | null = detail?.latest || active?.latest || null
  const dbItems = dbCapacity?.items || []
  const health = healthData || {
    health_score: active?.health_score ?? latest?.health_score ?? 0,
    risk_level: active?.risk_level || latest?.risk_level,
    risk_label: active?.risk_label || latest?.risk_label,
    risk_reasons: active?.risk_reasons || latest?.risk_reasons || [],
  }
  const dbTypeOptions = useMemo(() => Array.from(new Set(allInstances.map(item => item.db_type))).sort(), [allInstances])

  const trendRows = useMemo(() => (trendData?.items || []).map((row: any) => ({
    ...row,
    time: formatTime(row.collected_at).slice(5, 16),
    size_gb: row.total_size_bytes ? Number((row.total_size_bytes / 1024 / 1024 / 1024).toFixed(2)) : null,
  })), [trendData])

  const resetTableFilters = () => {
    setTableDb(undefined)
    setTableSearch('')
    setTablePage(1)
  }

  const selectInstance = (instanceId: number) => {
    setSelectedId(instanceId)
    resetTableFilters()
  }

  const showInstanceMonitor = (instanceId: number) => {
    selectInstance(instanceId)
    setMainTab('monitor')
    setWorkbenchTab('overview')
    setSearchParams({ instance_id: String(instanceId), view: 'overview' })
  }

  const openWorkbench = (instanceId: number, tab: string) => {
    selectInstance(instanceId)
    setMainTab('monitor')
    setWorkbenchTab(tab)
    setSearchParams({ instance_id: String(instanceId), view: tab === 'sql' ? 'sql' : tab === 'sessions' ? 'sessions' : tab })
  }

  const refreshMonitorData = async () => {
    if (isRefreshing) return
    setIsRefreshing(true)
    const minimumVisibleDelay = new Promise(resolve => setTimeout(resolve, 300))
    const refreshTasks = [
      queryClient.invalidateQueries({ queryKey: ['native-monitor-instances'] }),
      queryClient.invalidateQueries({ queryKey: ['native-monitor-overview'] }),
      queryClient.invalidateQueries({ queryKey: ['unified-collect-configs'] }),
    ]
    if (activeId) {
      refreshTasks.push(
        queryClient.invalidateQueries({ queryKey: ['native-monitor-detail', activeId] }),
        queryClient.invalidateQueries({ queryKey: ['native-monitor-trend', activeId] }),
        queryClient.invalidateQueries({ queryKey: ['native-monitor-db-capacity', activeId] }),
        queryClient.invalidateQueries({ queryKey: ['native-monitor-table-capacity'] }),
        queryClient.invalidateQueries({ queryKey: ['native-monitor-health', activeId] }),
        queryClient.invalidateQueries({ queryKey: ['native-monitor-top-sql', activeId] }),
        queryClient.invalidateQueries({ queryKey: ['native-monitor-waits', activeId] }),
        queryClient.invalidateQueries({ queryKey: ['native-monitor-capacity-growth', activeId] }),
        queryClient.invalidateQueries({ queryKey: ['native-monitor-engine-detail', activeId] }),
        queryClient.invalidateQueries({ queryKey: ['native-monitor-alerts', activeId] }),
      )
    }
    try {
      await Promise.all([Promise.all(refreshTasks), minimumVisibleDelay])
    } finally {
      setIsRefreshing(false)
    }
  }

  const openConfig = (target?: MonitorInstance | null) => {
    const item = target || active
    if (!item) return
    const cfg = collectConfigByInstance.get(item.instance_id)
    selectInstance(item.instance_id)
    setConfigTarget(item)
    setConfigScope('single')
    form.setFieldsValue({
      native: {
        is_enabled: cfg?.native?.is_enabled ?? item.config_enabled ?? false,
        collect_interval: cfg?.native?.collect_interval || item.collect_interval || 60,
        capacity_collect_interval: cfg?.native?.capacity_collect_interval || item.capacity_collect_interval || 3600,
        retention_days: cfg?.native?.retention_days || item.retention_days || 30,
      },
      session: {
        is_enabled: cfg?.session?.is_enabled ?? true,
        collect_interval: cfg?.session?.collect_interval || 60,
        retention_days: cfg?.session?.retention_days || 30,
      },
      sql: {
        is_enabled: cfg?.sql?.is_enabled ?? true,
        threshold_ms: cfg?.sql?.threshold_ms ?? 1000,
        collect_interval: cfg?.sql?.collect_interval || 300,
        retention_days: cfg?.sql?.retention_days || 30,
        collect_limit: cfg?.sql?.collect_limit || 100,
      },
    })
    setConfigOpen(true)
  }

  const openAllConfig = () => {
    setConfigScope('all')
    setConfigTarget(null)
    form.setFieldsValue({
      native: {
        is_enabled: true,
        collect_interval: 60,
        capacity_collect_interval: 3600,
        retention_days: 30,
      },
      session: {
        is_enabled: true,
        collect_interval: 60,
        retention_days: 30,
      },
      sql: {
        is_enabled: true,
        threshold_ms: 1000,
        collect_interval: 300,
        retention_days: 30,
        collect_limit: 100,
      },
    })
    setConfigOpen(true)
  }

  const triggerDisableAllConfig = () => {
    Modal.confirm({
      title: '关闭全部实例配置/采集',
      content: `将关闭当前列表中 ${instances.length} 个实例的指标、会话和 SQL 定时采集配置，已采集的历史数据不会被删除。`,
      okText: '关闭配置/采集',
      okButtonProps: { danger: true },
      cancelText: '取消',
      maskClosable: false,
      onOk: () => disableAllConfig.mutateAsync(),
    })
  }

  const triggerCollect = (instanceId?: number | null) => {
    if (!instanceId) return
    selectInstance(instanceId)
    collectNow.mutate(instanceId)
  }

  const triggerCollectAll = () => {
    Modal.confirm({
      title: '立即采集全部',
      content: `将按当前可见实例逐个手动触发一次采集，共 ${instances.length} 个实例。该操作不会改变实例的定时采集开关。`,
      okText: '开始采集',
      cancelText: '取消',
      maskClosable: false,
      onOk: () => collectAll.mutateAsync(),
    })
  }

  const bulkConfigItems: MenuProps['items'] = [
    {
      key: 'configure',
      icon: <SettingOutlined />,
      label: '批量配置/开启全部实例',
      onClick: openAllConfig,
    },
    {
      key: 'disable',
      icon: <StopOutlined />,
      danger: true,
      label: '关闭全部实例配置/采集',
      onClick: triggerDisableAllConfig,
    },
  ]

  const renderCollectOverview = (row: MonitorInstance) => {
    const cfg = collectConfigByInstance.get(row.instance_id)
    return (
      <Space direction="vertical" size={2}>
        <Space size={4} wrap>
          <Tag color={cfg?.native?.is_enabled ? 'success' : 'default'}>指标/容量</Tag>
          <StatusTag status={cfg?.native?.last_collect_status || row.last_collect_status} />
        </Space>
        <Space size={4} wrap>
          <Tag color={cfg?.session?.is_enabled ? 'success' : 'default'}>会话</Tag>
          <StatusTag status={cfg?.session?.last_collect_status || 'never'} />
        </Space>
        <Space size={4} wrap>
          <Tag color={cfg?.sql?.is_enabled ? 'success' : 'default'}>SQL</Tag>
          <StatusTag status={cfg?.sql?.last_collect_status || 'never'} />
        </Space>
      </Space>
    )
  }

  const columns = [
    {
      title: '实例',
      key: 'instance',
      fixed: 'left' as const,
      width: 220,
      render: (_: any, row: MonitorInstance) => (
        <Space direction="vertical" size={0}>
          <Button type="link" style={{ padding: 0, height: 22, fontWeight: 600 }} onClick={() => showInstanceMonitor(row.instance_id)}>
            {row.instance_name}
          </Button>
          <Space size={4}>
            <Tag>{formatDbTypeLabel(row.db_type)}</Tag>
            <Text type="secondary">ID:{row.instance_id}</Text>
          </Space>
        </Space>
      ),
    },
    {
      title: '健康分',
      width: 150,
      render: (_: any, row: MonitorInstance) => (
        <Space direction="vertical" size={2} style={{ width: '100%' }}>
          <Progress percent={row.health_score ?? row.latest?.health_score ?? 0} size="small" status={(row.risk_level || row.latest?.risk_level) === 'critical' ? 'exception' : undefined} />
          <RiskTag level={row.risk_level || row.latest?.risk_level} label={row.risk_label || row.latest?.risk_label} />
        </Space>
      ),
    },
    { title: '风险原因', width: 260, ellipsis: true, render: (_: any, row: MonitorInstance) => <Text ellipsis={{ tooltip: riskReasonText(row) }}>{riskReasonText(row)}</Text> },
    { title: '采集开关', width: 120, render: (_: any, row: MonitorInstance) => <ConfigStatusTag row={row} /> },
    { title: '采集状态', width: 120, render: (_: any, row: MonitorInstance) => <StatusTag status={row.last_collect_status} /> },
    { title: '连接使用率', width: 130, render: (_: any, row: MonitorInstance) => row.latest?.connection_usage !== null && row.latest?.connection_usage !== undefined ? <Progress percent={Math.round(row.latest.connection_usage * 100)} size="small" /> : <Text type="secondary">暂无数据</Text> },
    { title: 'QPS', width: 100, render: (_: any, row: MonitorInstance) => formatMetric(row.latest?.qps) },
    {
      title: '慢查询',
      width: 110,
      render: (_: any, row: MonitorInstance) => (
        <Button type="link" size="small" style={{ padding: 0 }} onClick={(event) => { event.stopPropagation(); openWorkbench(row.instance_id, 'sql') }}>
          {formatMetric(row.latest?.slow_queries)}
        </Button>
      ),
    },
    {
      title: '锁/长事务',
      width: 120,
      render: (_: any, row: MonitorInstance) => (
        <Button type="link" size="small" style={{ padding: 0 }} onClick={(event) => { event.stopPropagation(); openWorkbench(row.instance_id, 'sessions') }}>
          {formatMetric((row.latest?.lock_waits || 0) + (row.latest?.long_transactions || 0))}
        </Button>
      ),
    },
    { title: 'TPS', width: 100, render: (_: any, row: MonitorInstance) => formatMetric(row.latest?.tps) },
    { title: '容量', width: 130, render: (_: any, row: MonitorInstance) => formatBytes(row.latest?.total_size_bytes) },
    { title: '复制延迟', width: 110, render: (_: any, row: MonitorInstance) => formatMetric(row.latest?.replication_lag_seconds, 's') },
    { title: '最后采集', width: 180, render: (_: any, row: MonitorInstance) => formatTime(row.last_metric_collect_at) },
    { title: '采集配置', width: 190, render: (_: any, row: MonitorInstance) => renderCollectOverview(row) },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right' as const,
      width: 420,
      render: (_: any, row: MonitorInstance) => (
        <Space onClick={(event) => event.stopPropagation()}>
          <Button size="small" icon={<BarChartOutlined />} onClick={() => showInstanceMonitor(row.instance_id)}>查看监控</Button>
          {canViewSessions && <Button size="small" icon={<FieldTimeOutlined />} onClick={() => openWorkbench(row.instance_id, 'sessions')}>会话</Button>}
          {canViewSql && <Button size="small" icon={<AlertOutlined />} onClick={() => openWorkbench(row.instance_id, 'sql')}>SQL</Button>}
          {canManageConfig && <Button size="small" icon={<SettingOutlined />} onClick={() => openConfig(row)}>配置</Button>}
          {canManageConfig && <Button size="small" type="primary" icon={<PlayCircleOutlined />} disabled={collectAll.isPending} loading={collectNow.isPending && activeId === row.instance_id} onClick={() => triggerCollect(row.instance_id)}>立即采集指标</Button>}
        </Space>
      ),
    },
  ]

  const dbColumns = [
    { title: '库/Schema', dataIndex: 'db_name', fixed: 'left' as const, width: 180 },
    { title: '总大小', dataIndex: 'total_size_bytes', sorter: (a: any, b: any) => a.total_size_bytes - b.total_size_bytes, render: formatBytes },
    { title: '数据大小', dataIndex: 'data_size_bytes', render: formatBytes },
    { title: '索引大小', dataIndex: 'index_size_bytes', render: formatBytes },
    { title: '表数量', dataIndex: 'table_count' },
    { title: '行数估算', dataIndex: 'row_count' },
    { title: '采集时间', dataIndex: 'collected_at', render: formatTime },
  ]

  const tableColumns = [
    {
      title: '表',
      dataIndex: 'table_name',
      fixed: 'left' as const,
      width: 260,
      ellipsis: true,
      render: (value: string) => (
        <Text ellipsis={{ tooltip: value }} style={{ maxWidth: 230 }}>
          {value}
        </Text>
      ),
    },
    {
      title: '库/Schema',
      dataIndex: 'db_name',
      width: 200,
      ellipsis: true,
      render: (value: string) => (
        <Text ellipsis={{ tooltip: value }} style={{ maxWidth: 170 }}>
          {value}
        </Text>
      ),
    },
    { title: '总大小', dataIndex: 'total_size_bytes', sorter: (a: any, b: any) => a.total_size_bytes - b.total_size_bytes, render: formatBytes },
    { title: '数据大小', dataIndex: 'data_size_bytes', sorter: (a: any, b: any) => a.data_size_bytes - b.data_size_bytes, render: formatBytes },
    { title: '索引大小', dataIndex: 'index_size_bytes', sorter: (a: any, b: any) => a.index_size_bytes - b.index_size_bytes, render: formatBytes },
    { title: '行数估算', dataIndex: 'row_count', sorter: (a: any, b: any) => a.row_count - b.row_count },
    { title: '采集时间', dataIndex: 'collected_at', render: formatTime },
  ]

  const topSqlColumns = [
    { title: 'SQL/SQL_ID', width: 180, render: (_: any, row: any) => row.sql_id || row.source_ref || row.digest || '-' },
    { title: 'Schema', width: 140, render: (_: any, row: any) => row.schema_name || row.db_name || '-' },
    { title: '执行次数', width: 110, render: (_: any, row: any) => formatMetric(row.executions ?? row.count_star) },
    { title: '总耗时(ms)', width: 120, render: (_: any, row: any) => formatMetric(row.elapsed_time_ms ?? row.duration_ms) },
    { title: '平均耗时(ms)', width: 130, render: (_: any, row: any) => formatMetric(row.avg_elapsed_ms ?? row.avg_duration_ms) },
    { title: 'SQL 文本', render: (_: any, row: any) => <Text ellipsis={{ tooltip: row.sql_text || row.DIGEST_TEXT }}>{row.sql_text || row.DIGEST_TEXT || '-'}</Text> },
  ]

  const waitColumns = [
    { title: '事件/会话', width: 220, render: (_: any, row: any) => row.event || row.sid || row.session_id || '-' },
    { title: '等待类别', width: 140, render: (_: any, row: any) => row.wait_class || '-' },
    { title: '等待次数', width: 120, render: (_: any, row: any) => formatMetric(row.total_waits) },
    { title: '等待时间', width: 120, render: (_: any, row: any) => formatMetric(row.time_waited ?? row.seconds_in_wait) },
    { title: '阻塞源', width: 120, render: (_: any, row: any) => formatMetric(row.blocking_session) },
    { title: '用户', width: 140, render: (_: any, row: any) => row.username || '-' },
  ]

  const growthColumns = [
    { title: '库/Schema', dataIndex: 'db_name', width: 180 },
    { title: '增长量', dataIndex: 'growth_bytes', render: formatBytes },
    { title: '当前大小', dataIndex: 'latest_size_bytes', render: formatBytes },
    { title: '采集时间', dataIndex: 'collected_at', render: formatTime },
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="观测中心"
        marginBottom={20}
        actions={(
          <Space wrap style={isMobile ? { width: '100%' } : undefined}>
            <Button icon={<ReloadOutlined />} loading={isRefreshing} disabled={isRefreshing} onClick={refreshMonitorData}>
              {isRefreshing ? '刷新中' : '刷新'}
            </Button>
            {showOverviewActions && canManageConfig && (
              <Dropdown menu={{ items: bulkConfigItems }} disabled={!instances.length || saveAllConfig.isPending || disableAllConfig.isPending}>
                <Button icon={<SettingOutlined />} loading={saveAllConfig.isPending || disableAllConfig.isPending}>
                  配置全部实例 <DownOutlined />
                </Button>
              </Dropdown>
            )}
            {showOverviewActions && canManageConfig && <Button type="primary" icon={<PlayCircleOutlined />} disabled={!instances.length} loading={collectAll.isPending} onClick={triggerCollectAll}>立即采集全部指标</Button>}
          </Space>
        )}
      />

      <Tabs
        activeKey={mainTab}
        onChange={(key) => {
          setMainTab(key)
          if (key === 'instance-overview') {
            setSearchParams({})
          } else if (activeId) {
            setSearchParams({ instance_id: String(activeId), view: workbenchTab })
          }
        }}
        items={[
          {
            key: 'instance-overview',
            label: <span><DatabaseOutlined />舰队总览</span>,
            children: (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(8, minmax(0, 1fr))', gap: 12 }}>
                  <MetricCard title="实例总数" value={overview?.cards?.instance_total ?? allInstances.length} />
                  <MetricCard title="在线率" value={Math.round((overview?.cards?.online_rate || 0) * 100)} suffix="%" />
                  <MetricCard title="异常实例" value={overview?.cards?.abnormal_count ?? 0} danger={(overview?.cards?.abnormal_count || 0) > 0} />
                  <MetricCard title="采集失败" value={overview?.cards?.collect_failed_count ?? 0} danger={(overview?.cards?.collect_failed_count || 0) > 0} />
                  <MetricCard title="连接压力" value={overview?.cards?.high_connection_count ?? 0} danger={(overview?.cards?.high_connection_count || 0) > 0} />
                  <MetricCard title="容量风险" value={overview?.cards?.capacity_risk_count ?? 0} danger={(overview?.cards?.capacity_risk_count || 0) > 0} />
                  <MetricCard title="复制延迟" value={overview?.cards?.replication_lag_count ?? 0} danger={(overview?.cards?.replication_lag_count || 0) > 0} />
                  <MetricCard title="锁/长事务" value={overview?.cards?.lock_or_long_tx_count ?? 0} danger={(overview?.cards?.lock_or_long_tx_count || 0) > 0} />
                </div>
                <Card size="small" styles={{ body: { padding: 12 } }}>
                  <Space wrap>
                    <Select allowClear placeholder="数据库类型" style={{ width: 180 }} value={dbTypeFilter} onChange={setDbTypeFilter}>
                      {dbTypeOptions.map(type => <Option key={type} value={type}>{formatDbTypeLabel(type)}</Option>)}
                    </Select>
                    <Select allowClear placeholder="风险等级" style={{ width: 160 }} value={riskFilter} onChange={setRiskFilter}>
                      <Option value="critical">严重</Option>
                      <Option value="warning">警告</Option>
                      <Option value="attention">关注</Option>
                      <Option value="healthy">健康</Option>
                    </Select>
                    <Select allowClear placeholder="采集状态" style={{ width: 160 }} value={collectStatusFilter} onChange={setCollectStatusFilter}>
                      <Option value="success">正常</Option>
                      <Option value="partial">部分缺失</Option>
                      <Option value="failed">采集失败</Option>
                      <Option value="not_configured">未配置</Option>
                    </Select>
                  </Space>
                </Card>
                <Table
                  dataSource={instances}
                  columns={columns}
                  rowKey="instance_id"
                  loading={isLoading}
                  tableLayout="fixed"
                  scroll={{ x: 2230 }}
                  pagination={false}
                  rowClassName={(row) => row.instance_id === activeId ? 'ant-table-row-selected' : ''}
                  onRow={(row) => ({
                    onClick: () => showInstanceMonitor(row.instance_id),
                    style: { cursor: 'pointer' },
                  })}
                  locale={{ emptyText: <TableEmptyState title="暂无可监控实例" /> }}
                />
              </Space>
            ),
          },
          {
            key: 'monitor',
            label: <span><BarChartOutlined />实例诊断工作台</span>,
            children: activeId ? (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Space wrap align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Space wrap align="center">
                    <Select
                      showSearch
                      placeholder="选择实例"
                      style={{ width: isMobile ? '100%' : 320 }}
                      value={activeId}
                      optionFilterProp="label"
                      onChange={selectInstance}
                      options={instances.map(item => ({
                        value: item.instance_id,
                        label: item.instance_name,
                        children: `${item.instance_name} ${formatDbTypeLabel(item.db_type)}`,
                      }))}
                    />
                    <Tag>{formatDbTypeLabel(active?.db_type || detail?.instance?.db_type)}</Tag>
                    <ConfigStatusTag row={{ config_id: detail?.config?.id || active?.config_id, config_enabled: detail?.config?.is_enabled ?? active?.config_enabled }} />
                    <StatusTag status={detail?.config?.last_collect_status || active?.last_collect_status} />
                    <RiskTag level={health.risk_level} label={health.risk_label} />
                    <Text type="secondary">最后指标采集：{formatTime(detail?.config?.last_metric_collect_at || active?.last_metric_collect_at)}</Text>
                  </Space>
                </Space>

                {!detail?.config && (
                  <Alert
                    type="warning"
                    showIcon
                    message="该实例尚未启用原生监控采集"
                    description="保存采集配置或点击立即采集后，SagittaDB 会使用实例账号读取数据库原生监控指标。账号权限不足的指标会显示为空。"
                  />
                )}
                {latest?.error && <Alert type="error" showIcon message="最近采集失败" description={latest.error} />}

                <Tabs
                  activeKey={workbenchTab}
                  onChange={(key) => {
                    setWorkbenchTab(key)
                    if (activeId) {
                      const view = key === 'sessions' ? 'sessions' : key === 'sql' ? 'sql' : key
                      setSearchParams({ instance_id: String(activeId), view })
                    }
                  }}
                  items={[
                    {
                      key: 'overview',
                      label: <span><ApiOutlined />概览</span>,
                      children: (
                        <Space direction="vertical" size={16} style={{ width: '100%' }}>
                          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
                            <div style={{ border: '1px solid rgba(0,0,0,0.08)', borderRadius: 8, padding: 16, minHeight: 92 }}>
                              <Statistic title="健康评分" value={health.health_score ?? 0} suffix="/100" valueStyle={{ fontSize: 20 }} />
                              <Progress percent={health.health_score ?? 0} size="small" status={health.risk_level === 'critical' ? 'exception' : undefined} />
                            </div>
                            <MetricCard title="健康状态" value={latest?.is_up ? '在线' : '暂无数据'} />
                            <MetricCard title="当前连接" value={latest?.current_connections} />
                            <MetricCard title="QPS" value={latest?.qps} />
                            <MetricCard title="活跃会话" value={latest?.active_sessions} />
                            <MetricCard title="TPS" value={latest?.tps} />
                            <MetricCard title="实例容量" value={formatBytes(latest?.total_size_bytes)} />
                            <MetricCard title="当前慢查询" value={latest?.slow_queries} danger={(latest?.slow_queries || 0) > 0} />
                            <MetricCard title="锁等待会话" value={latest?.lock_waits} danger={(latest?.lock_waits || 0) > 0} />
                          </div>
                          <Alert type={health.risk_level === 'critical' ? 'error' : health.risk_level === 'warning' ? 'warning' : 'info'} showIcon message="风险摘要" description={(health.risk_reasons || []).join('；') || '暂无明显风险'} />
                          <Descriptions bordered size="small" column={isMobile ? 1 : 3}>
                            <Descriptions.Item label="数据库版本">{formatMetric(latest?.version)}</Descriptions.Item>
                            <Descriptions.Item label="运行时长">{formatDurationSeconds(latest?.uptime_seconds)}</Descriptions.Item>
                            <Descriptions.Item label="最大连接">{formatMetric(latest?.max_connections)}</Descriptions.Item>
                            <Descriptions.Item label="长事务">{formatMetric(latest?.long_transactions)}</Descriptions.Item>
                            <Descriptions.Item label="复制延迟">{formatMetric(latest?.replication_lag_seconds, 's')}</Descriptions.Item>
                            <Descriptions.Item label="采集时间">{formatTime(latest?.collected_at)}</Descriptions.Item>
                          </Descriptions>
                        </Space>
                      ),
                    },
                    {
                      key: 'trend',
                      label: <span><BarChartOutlined />性能</span>,
                      children: (
                        <Space direction="vertical" size={12} style={{ width: '100%' }}>
                          <Select value={trendHours} style={{ width: 160 }} onChange={setTrendHours}>
                            <Option value={1}>近 1 小时</Option>
                            <Option value={6}>近 6 小时</Option>
                            <Option value={24}>近 24 小时</Option>
                            <Option value={168}>近 7 天</Option>
                          </Select>
                          {trendRows.length ? (
                            <div style={{ height: 320 }}>
                              <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={trendRows}>
                                  <CartesianGrid strokeDasharray="3 3" />
                                  <XAxis dataKey="time" />
                                  <YAxis />
                                  <Tooltip formatter={(value: any, name: string) => name === 'size_gb' ? [`${value} GB`, '容量'] : [value, name]} />
                                  <Line type="monotone" dataKey="current_connections" name="连接数" stroke="#1677ff" dot={false} />
                                  <Line type="monotone" dataKey="qps" name="QPS" stroke="#52c41a" dot={false} />
                                  <Line type="monotone" dataKey="tps" name="TPS" stroke="#13c2c2" dot={false} />
                                  <Line type="monotone" dataKey="slow_queries" name="本次慢查询" stroke="#fa8c16" dot={false} />
                                  <Line type="monotone" dataKey="size_gb" name="容量GB" stroke="#722ed1" dot={false} />
                                </LineChart>
                              </ResponsiveContainer>
                            </div>
                          ) : <TableEmptyState title="暂无趋势数据" />}
                          <Descriptions bordered size="small" column={isMobile ? 1 : 3}>
                            {Object.entries(engineDetail?.metric_groups?.stats || {}).map(([key, value]) => (
                              <Descriptions.Item key={key} label={key}>{formatMetric(value as any)}</Descriptions.Item>
                            ))}
                          </Descriptions>
                        </Space>
                      ),
                    },
                    {
                      key: 'databases',
                      label: <span><DatabaseOutlined />库容量</span>,
                      children: <Table dataSource={dbItems} columns={dbColumns} rowKey="db_name" scroll={{ x: 980 }} pagination={false} locale={{ emptyText: <TableEmptyState title="暂无库容量数据" /> }} />,
                    },
                    {
                      key: 'tables',
                      label: <span><TableOutlined />表容量</span>,
                      children: (
                        <Space direction="vertical" style={{ width: '100%' }}>
                          <Space wrap>
                            <Select allowClear placeholder="库/Schema" style={{ width: 220 }} value={tableDb} onChange={(value) => { setTableDb(value); setTablePage(1) }}>
                              {dbItems.map((item: any) => <Option key={item.db_name} value={item.db_name}>{item.db_name}</Option>)}
                            </Select>
                            <Input.Search allowClear placeholder="搜索表名" style={{ width: 260 }} value={tableSearch} onChange={(event) => setTableSearch(event.target.value)} onSearch={(value) => { setTableSearch(value); setTablePage(1) }} />
                          </Space>
                          <Table dataSource={tableCapacity?.items || []} columns={tableColumns} rowKey={(row: any) => `${row.db_name}.${row.table_name}`} loading={tableLoading} scroll={{ x: 1180 }} pagination={{ total: tableCapacity?.total, pageSize: 100, current: tablePage, showSizeChanger: false, onChange: setTablePage }} locale={{ emptyText: <TableEmptyState title="暂无表容量数据" /> }} />
                        </Space>
                      ),
                    },
                    {
                      key: 'sessions',
                      label: <span><FieldTimeOutlined />会话洞察</span>,
                      disabled: !canViewSessions,
                      children: canViewSessions ? (
                        <Space direction="vertical" size={16} style={{ width: '100%' }}>
                          <Alert type="info" showIcon message="会话洞察" description="在线会话、阻塞链、历史会话和 Oracle ASH/AWR 均使用当前实例上下文。" />
                          <Table dataSource={waitsData?.blocking_sessions || []} columns={waitColumns} rowKey={(row: any, index) => `${row.sid || row.session_id || 'session'}-${index}`} scroll={{ x: 920 }} pagination={false} locale={{ emptyText: <TableEmptyState title="暂无阻塞会话" /> }} />
                          <SessionInsightPanel embedded instanceId={activeId} />
                        </Space>
                      ) : <TableEmptyState title="暂无会话洞察权限" />,
                    },
                    {
                      key: 'sql',
                      label: <span><AlertOutlined />SQL 洞察</span>,
                      disabled: !canViewSql,
                      children: canViewSql ? (
                        <Space direction="vertical" size={12} style={{ width: '100%' }}>
                          {topSqlData?.error && <Alert type="warning" showIcon message="Top SQL 采集受限" description={topSqlData.error} />}
                          <Table dataSource={topSqlData?.items || []} columns={topSqlColumns} rowKey={(row: any, index) => `${row.sql_id || row.source_ref || row.sql_text || 'sql'}-${index}`} scroll={{ x: 1100 }} pagination={{ pageSize: 10 }} locale={{ emptyText: <TableEmptyState title="暂无 Top SQL 数据" /> }} />
                          <SqlInsightPanel embedded instanceId={activeId} />
                        </Space>
                      ) : <TableEmptyState title="暂无 SQL 洞察权限" />,
                    },
                    {
                      key: 'replication',
                      label: '复制',
                      children: (
                        <Descriptions bordered size="small" column={isMobile ? 1 : 2}>
                          {Object.entries(engineDetail?.metric_groups?.replication || {}).map(([key, value]) => (
                            <Descriptions.Item key={key} label={key}>{formatMetric(value as any)}</Descriptions.Item>
                          ))}
                          {!Object.keys(engineDetail?.metric_groups?.replication || {}).length && (
                            <Descriptions.Item label="复制状态">暂无复制指标</Descriptions.Item>
                          )}
                        </Descriptions>
                      ),
                    },
                    {
                      key: 'waits',
                      label: '等待事件',
                      children: <Table dataSource={waitsData?.top_waits || []} columns={waitColumns} rowKey={(row: any, index) => `${row.event || 'wait'}-${index}`} scroll={{ x: 920 }} pagination={false} locale={{ emptyText: <TableEmptyState title="暂无等待事件数据" /> }} />,
                    },
                    {
                      key: 'capacity-growth',
                      label: '容量增长',
                      children: <Table dataSource={growthData?.top_databases || []} columns={growthColumns} rowKey="db_name" pagination={false} locale={{ emptyText: <TableEmptyState title="暂无容量增长数据" /> }} />,
                    },
                    ...((active?.db_type || detail?.instance?.db_type) === 'oracle' ? [
                      {
                        key: 'oracle',
                        label: 'Oracle 专属',
                        children: (
                          <Space direction="vertical" size={16} style={{ width: '100%' }}>
                            <Descriptions bordered size="small" column={isMobile ? 1 : 2}>
                              {Object.entries(engineDetail?.metric_groups?.fra || {}).map(([key, value]) => (
                                <Descriptions.Item key={key} label={`FRA ${key}`}>{formatMetric(value as any)}</Descriptions.Item>
                              ))}
                              {Object.entries(engineDetail?.metric_groups?.archive || {}).map(([key, value]) => (
                                <Descriptions.Item key={key} label={`Archive ${key}`}>{formatMetric(value as any)}</Descriptions.Item>
                              ))}
                            </Descriptions>
                            <Table dataSource={engineDetail?.metric_groups?.tablespaces || []} rowKey={(row: any) => row.tablespace_name} size="small" pagination={false} columns={[
                              { title: '表空间', dataIndex: 'tablespace_name' },
                              { title: '使用率', dataIndex: 'used_pct', render: (value: number) => <Progress percent={Math.round(Number(value || 0))} size="small" /> },
                              { title: '已用', dataIndex: 'used_bytes', render: formatBytes },
                              { title: '总量', dataIndex: 'total_bytes', render: formatBytes },
                              { title: 'Autoextend', dataIndex: 'autoextensible' },
                            ]} />
                            <Table dataSource={engineDetail?.metric_groups?.data_guard || []} rowKey={(row: any, index) => `${row.name}-${index}`} size="small" pagination={false} columns={[
                              { title: 'Data Guard 指标', dataIndex: 'name' },
                              { title: '值', dataIndex: 'value' },
                              { title: '单位', dataIndex: 'unit' },
                              { title: '计算时间', dataIndex: 'time_computed', render: formatTime },
                            ]} locale={{ emptyText: <TableEmptyState title="暂无 Data Guard 数据" /> }} />
                          </Space>
                        ),
                      },
                    ] : []),
                    {
                      key: 'alerts',
                      label: '告警',
                      children: (
                        <Space direction="vertical" size={12} style={{ width: '100%' }}>
                          <Alert
                            type="info"
                            showIcon
                            message="阈值告警一期"
                            description="规则以 JSON 保存到当前实例采集配置，支持 operator、threshold、duration_count、recover_notify、silence_minutes 等字段；后台采集与通知服务可按这些规则继续接入执行。"
                          />
                          <Descriptions bordered size="small" column={1}>
                            <Descriptions.Item label="默认规则">{JSON.stringify(alertRules?.defaults || {})}</Descriptions.Item>
                          </Descriptions>
                          <Input.TextArea
                            rows={10}
                            value={alertRulesText}
                            onChange={(event) => setAlertRulesText(event.target.value)}
                            disabled={!canManageAlerts}
                          />
                          {canManageAlerts && <Button type="primary" loading={saveAlertRules.isPending} onClick={() => saveAlertRules.mutate()}>保存告警规则</Button>}
                        </Space>
                      ),
                    },
                    {
                      key: 'diagnosis',
                      label: '采集诊断',
                      children: (
                        <Space direction="vertical" size={16} style={{ width: '100%' }}>
                          <Alert
                            type="info"
                            showIcon
                            message="指标缺失说明"
                            description="SagittaDB 使用实例配置账号采集监控数据。若账号缺少系统视图、性能视图或管理命令权限，对应指标会显示为空。请为监控账号授予数据库原生监控权限后重新采集。"
                          />
                          <Descriptions bordered size="small" column={1}>
                            <Descriptions.Item label="实例指标采集">{formatTime(detail?.config?.last_metric_collect_at)}</Descriptions.Item>
                            <Descriptions.Item label="容量采集">{formatTime(detail?.config?.last_capacity_collect_at)}</Descriptions.Item>
                            <Descriptions.Item label="采集状态"><StatusTag status={detail?.config?.last_collect_status} /></Descriptions.Item>
                            <Descriptions.Item label="采集错误">{detail?.config?.last_collect_error || latest?.error || '暂无'}</Descriptions.Item>
                            <Descriptions.Item label="缺失指标组">{Object.keys(latest?.missing_groups || {}).length ? JSON.stringify(latest?.missing_groups) : '暂无'}</Descriptions.Item>
                          </Descriptions>
                        </Space>
                      ),
                    },
                  ]}
                />
              </Space>
            ) : <TableEmptyState title="暂无可监控实例" />,
          },
        ]}
      />

      <Modal
        title={configScope === 'all' ? '统一采集配置 - 全部实例' : `统一采集配置 - ${configTarget?.instance_name || active?.instance_name || ''}`}
        open={configOpen}
        onCancel={() => {
          setConfigOpen(false)
          setConfigTarget(null)
        }}
        onOk={() => form.validateFields().then(values => {
          if (configScope === 'all') {
            saveAllConfig.mutate(values)
            return
          }
          const instanceId = configTarget?.instance_id || activeId
          if (instanceId) saveConfig.mutate({ instanceId, values })
        })}
        confirmLoading={saveConfig.isPending || saveAllConfig.isPending}
        maskClosable={false}
        width={720}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginTop: 8 }}
          message={configScope === 'all' ? '该配置将应用到全部可见实例' : '该配置仅作用于当前实例'}
          description={configScope === 'all' ? `保存后会为当前列表中的 ${instances.length} 个实例写入相同采集配置。手动立即采集指标不会改变这些开关。` : '保存后会同时更新当前实例的指标/容量、会话和 SQL 采集配置。手动立即采集指标不会改变这些开关。'}
        />
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Tabs
            items={[
              {
                key: 'native',
                label: '原生监控',
                children: (
                  <>
                    <Form.Item name={['native', 'is_enabled']} label="启用指标/容量采集" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name={['native', 'collect_interval']} label="实例指标采集间隔（秒）" rules={[{ required: true }]}>
                      <InputNumber min={10} max={3600} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={['native', 'capacity_collect_interval']} label="容量采集间隔（秒）" rules={[{ required: true }]}>
                      <InputNumber min={300} max={86400} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={['native', 'retention_days']} label="指标保留天数" rules={[{ required: true }]}>
                      <InputNumber min={1} max={365} style={{ width: '100%' }} />
                    </Form.Item>
                  </>
                ),
              },
              {
                key: 'session',
                label: '会话采集',
                children: (
                  <>
                    <Form.Item name={['session', 'is_enabled']} label="启用会话采集" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name={['session', 'collect_interval']} label="会话采样间隔（秒）" rules={[{ required: true }]}>
                      <InputNumber min={10} max={86400} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={['session', 'retention_days']} label="会话数据保留天数" rules={[{ required: true }]}>
                      <InputNumber min={1} max={365} style={{ width: '100%' }} />
                    </Form.Item>
                  </>
                ),
              },
              {
                key: 'sql',
                label: 'SQL 采集',
                children: (
                  <>
                    <Form.Item name={['sql', 'is_enabled']} label="启用 SQL 采集" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name={['sql', 'threshold_ms']} label="SQL 耗时阈值（ms）" rules={[{ required: true }]}>
                      <InputNumber min={0} max={3600000} step={500} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={['sql', 'collect_interval']} label="SQL 采集间隔（秒）" rules={[{ required: true }]}>
                      <InputNumber min={30} max={86400} step={30} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={['sql', 'retention_days']} label="SQL 数据保留天数" rules={[{ required: true }]}>
                      <InputNumber min={1} max={365} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={['sql', 'collect_limit']} label="单次采集上限" rules={[{ required: true }]}>
                      <InputNumber min={1} max={1000} style={{ width: '100%' }} />
                    </Form.Item>
                  </>
                ),
              },
            ]}
          />
        </Form>
      </Modal>
    </div>
  )
}
