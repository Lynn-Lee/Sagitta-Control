import { useEffect, useMemo, useState } from 'react'
import {
  Alert, Button, Card, DatePicker, Descriptions, Drawer, Form, Grid, Input, InputNumber, Modal, Progress, Select,
  Space, Statistic, Switch, Table, Tabs, Tag, Tooltip, Typography, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { BulbOutlined, CloudDownloadOutlined, CopyOutlined, EyeOutlined, LineChartOutlined, ReloadOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { Line, LineChart, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from 'recharts'
import { instanceApi } from '@/api/instance'
import { optimizeApi, type OptimizeAnalyzeResponse, type OptimizeFinding, type OptimizeRecommendation } from '@/api/optimize'
import {
  slowlogApi,
  type SlowQueryCollectResponse,
  type SlowQueryConfigItem,
  type SlowQueryExplainResponse,
  type SlowQueryFingerprintItem,
  type SlowQueryGroupStat,
  type SlowQueryGroupTrend,
  type SlowQueryLogItem,
  type SlowQueryParams,
} from '@/api/slowlog'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Text, Paragraph } = Typography
const { RangePicker } = DatePicker
const { useBreakpoint } = Grid

const SOURCE_OPTIONS = [
  { label: '平台查询', value: 'platform' },
  { label: 'MySQL 原生', value: 'mysql_slowlog' },
  { label: 'PG 统计', value: 'pgsql_statements' },
  { label: 'Redis SLOWLOG', value: 'redis_slowlog' },
  { label: '会话采样', value: 'session_history' },
]

const SOURCE_COLOR: Record<string, string> = {
  platform: 'blue',
  mysql_slowlog: 'orange',
  pgsql_statements: 'green',
  redis_slowlog: 'red',
  session_history: 'purple',
}

const RISK_COLOR = (value: number) => value >= 70 ? 'red' : value >= 35 ? 'gold' : 'green'
const SEVERITY_COLOR: Record<string, string> = {
  critical: 'error',
  warning: 'warning',
  info: 'processing',
  ok: 'success',
}

const sourceLabel = (source: string) => SOURCE_OPTIONS.find(i => i.value === source)?.label || source
const formatTime = (value?: string | null) => value ? dayjs(value).format('MM-DD HH:mm:ss') : '—'
const formatMs = (value?: number) => `${Number(value || 0).toLocaleString()} ms`
const TREND_COLORS = ['#1677ff', '#52c41a', '#fa8c16', '#eb2f96', '#722ed1', '#13c2c2']

function buildTrendRows(groups: SlowQueryGroupTrend[], metric: 'count' | 'avg_duration_ms') {
  const buckets = Array.from(new Set(groups.flatMap(group => group.points.map(point => point.bucket)))).sort()
  return buckets.map(bucket => {
    const row: Record<string, string | number> = { bucket }
    groups.forEach(group => {
      row[group.group_key] = group.points.find(point => point.bucket === bucket)?.[metric] || 0
    })
    return row
  })
}

export default function SlowlogPage() {
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const queryClient = useQueryClient()
  const [msgApi, msgCtx] = message.useMessage()
  const [page, setPage] = useState(1)
  const [instanceId, setInstanceId] = useState<number | undefined>()
  const [dbName, setDbName] = useState('')
  const [source, setSource] = useState<string | undefined>()
  const [sqlKeyword, setSqlKeyword] = useState('')
  const [username, setUsername] = useState('')
  const [tag, setTag] = useState<string | undefined>()
  const [activeTab, setActiveTab] = useState('overview')
  const [minDurationMs, setMinDurationMs] = useState(1000)
  const [dateRange, setDateRange] = useState<[string, string] | null>([
    dayjs().subtract(24, 'hour').toISOString(),
    dayjs().toISOString(),
  ])
  const [sqlDetail, setSqlDetail] = useState<SlowQueryLogItem | null>(null)
  const [sampleFingerprint, setSampleFingerprint] = useState<string | null>(null)
  const [detailFingerprint, setDetailFingerprint] = useState<string | null>(null)
  const [diagnosis, setDiagnosis] = useState<OptimizeAnalyzeResponse | null>(null)
  const [manualDiagnosis, setManualDiagnosis] = useState<OptimizeAnalyzeResponse | null>(null)
  const [manualForm] = Form.useForm()
  const [configOpen, setConfigOpen] = useState(false)
  const [editingConfig, setEditingConfig] = useState<SlowQueryConfigItem | null>(null)
  const [explainResult, setExplainResult] = useState<SlowQueryExplainResponse | null>(null)
  const [configForm] = Form.useForm()

  const filterWidth = (width: number) => (isMobile ? '100%' : width)

  const { data: instanceData } = useQuery({
    queryKey: ['slowlog-instances'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })

  const tagOptionsQuery = useQuery({
    queryKey: ['slowlog-tag-options'],
    queryFn: () => slowlogApi.tagOptions(),
  })

  const { data: dbData } = useQuery({
    queryKey: ['slowlog-instance-databases', instanceId],
    queryFn: () => instanceApi.getDatabases(instanceId!),
    enabled: !!instanceId,
  })

  const selectedInstance = instanceData?.items?.find(i => i.id === instanceId)
  const unsupportedNative = selectedInstance && !['mysql', 'pgsql', 'redis'].includes(selectedInstance.db_type)
  const selectedDbType = selectedInstance?.db_type?.toLowerCase() || ''
  const engineTagOptions = useMemo(
    () => selectedDbType ? (tagOptionsQuery.data?.items?.[selectedDbType] || []) : [],
    [selectedDbType, tagOptionsQuery.data?.items],
  )
  const tagSelectOptions = useMemo(
    () => engineTagOptions.map(item => ({ label: item, value: item })),
    [engineTagOptions],
  )

  useEffect(() => {
    if (!tag) return
    if (!instanceId || !engineTagOptions.includes(tag)) {
      setTag(undefined)
      setPage(1)
    }
  }, [engineTagOptions, instanceId, tag])

  const baseParams = useMemo<SlowQueryParams>(() => ({
    instance_id: instanceId,
    db_name: dbName || undefined,
    source,
    sql_keyword: sqlKeyword || undefined,
    username: username || undefined,
    tag,
    min_duration_ms: minDurationMs,
    date_start: dateRange?.[0],
    date_end: dateRange?.[1],
  }), [dateRange, dbName, instanceId, minDurationMs, source, sqlKeyword, tag, username])

  const overviewQuery = useQuery({
    queryKey: ['slowlog-overview', baseParams],
    queryFn: () => slowlogApi.overview(baseParams),
  })

  const logQuery = useQuery({
    queryKey: ['slowlog-logs', baseParams, page],
    queryFn: () => slowlogApi.logs({ ...baseParams, page, page_size: 50 }),
  })

  const fingerprintQuery = useQuery({
    queryKey: ['slowlog-fingerprints', baseParams],
    queryFn: () => slowlogApi.fingerprints({ ...baseParams, limit: 50 }),
  })

  const realtimeQuery = useQuery({
    queryKey: ['slowlog-realtime', instanceId],
    queryFn: () => slowlogApi.realtime({ instance_id: instanceId!, limit: 50, min_seconds: Math.max(1, Math.round(minDurationMs / 1000)) }),
    enabled: !!instanceId,
  })

  const sampleQuery = useQuery({
    queryKey: ['slowlog-samples', sampleFingerprint],
    queryFn: () => slowlogApi.samples(sampleFingerprint!, 20),
    enabled: !!sampleFingerprint,
  })

  const detailQuery = useQuery({
    queryKey: ['slowlog-fingerprint-detail', detailFingerprint, dateRange],
    queryFn: () => slowlogApi.fingerprintDetail(detailFingerprint!, {
      date_start: dateRange?.[0],
      date_end: dateRange?.[1],
    }),
    enabled: !!detailFingerprint,
  })

  const configQuery = useQuery({
    queryKey: ['slowlog-configs'],
    queryFn: () => slowlogApi.configs(),
  })

  const overview = overviewQuery.data
  const primaryStats = instanceId ? (overview?.database_stats || []) : (overview?.instance_stats || [])
  const primaryStatsTitle = instanceId ? '数据库 / Schema 统计' : '实例统计'
  const primaryStatsEmptyTitle = instanceId ? '暂无数据库 / Schema 统计' : '暂无实例统计'
  const groupTrendTitle = instanceId ? '数据库 / Schema 趋势' : '实例趋势'

  const collectMut = useMutation<SlowQueryCollectResponse>({
    mutationFn: () => slowlogApi.collect({ instance_id: instanceId, limit: 100 }),
    onSuccess: (data) => {
      msgApi.success(`采集完成：新增 ${data.saved} 条，失败 ${data.failed}，不支持 ${data.unsupported}`)
      queryClient.invalidateQueries({ queryKey: ['slowlog-overview'] })
      queryClient.invalidateQueries({ queryKey: ['slowlog-logs'] })
      queryClient.invalidateQueries({ queryKey: ['slowlog-fingerprints'] })
      queryClient.invalidateQueries({ queryKey: ['slowlog-configs'] })
      if (data.saved === 0) {
        Modal.info({
          title: '本次没有新增慢 SQL',
          maskClosable: false,
          content: '请检查实例采集配置里的慢 SQL 阈值、最近 1 天时间范围、数据库原生慢日志能力，以及平台查询历史中是否存在符合条件的记录。',
        })
      }
      if (data.errors?.length) {
        Modal.info({
          title: '采集提示',
          width: 'min(680px, calc(100vw - 32px))',
          maskClosable: false,
          content: (
            <Space direction="vertical" style={{ maxWidth: '100%', overflowX: 'auto' }}>
              {data.errors.slice(0, 8).map((item) => (
                <Text key={item} style={{ whiteSpace: 'nowrap' }}>
                  {item}
                </Text>
              ))}
            </Space>
          ),
        })
      }
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || '采集失败'),
  })

  const configUpdateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<SlowQueryConfigItem> }) => slowlogApi.updateConfig(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['slowlog-configs'] })
      msgApi.success('配置已更新')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || '更新失败'),
  })

  const explainMut = useMutation({
    mutationFn: (logId: number) => slowlogApi.explain({ log_id: logId }),
    onSuccess: setExplainResult,
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || '执行计划分析失败'),
  })

  const diagnoseMut = useMutation<OptimizeAnalyzeResponse, any, { log_id?: number; fingerprint?: string; instance_id?: number; db_name?: string; sql?: string }>({
    mutationFn: (data: { log_id?: number; fingerprint?: string; instance_id?: number; db_name?: string; sql?: string }) => optimizeApi.analyze(data),
    onSuccess: (data) => {
      setDiagnosis(data)
      if (data.msg) msgApi.info(data.msg)
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || e.message || '诊断失败'),
  })

  const manualDiagnoseMut = useMutation<OptimizeAnalyzeResponse, any, { instance_id: number; db_name?: string; sql: string }>({
    mutationFn: (data: { instance_id: number; db_name?: string; sql: string }) => optimizeApi.analyze(data),
    onSuccess: (data) => {
      setManualDiagnosis(data)
      if (data.msg) msgApi.info(data.msg)
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || e.message || '诊断失败'),
  })

  const resetFilters = () => {
    setInstanceId(undefined)
    setDbName('')
    setSource(undefined)
    setSqlKeyword('')
    setUsername('')
    setTag(undefined)
    setMinDurationMs(1000)
    setDateRange([dayjs().subtract(24, 'hour').toISOString(), dayjs().toISOString()])
    setPage(1)
  }

  const runManualDiagnosis = (values: any) => {
    manualDiagnoseMut.mutate({
      instance_id: values.instance_id,
      db_name: values.db_name || '',
      sql: values.sql,
    })
    setSqlDetail(null)
    setDetailFingerprint(null)
    setExplainResult(null)
    setDiagnosis(null)
  }

  const openLogDetail = (row: SlowQueryLogItem, withDiagnosis = false) => {
    setSqlDetail(row)
    setDetailFingerprint(null)
    setExplainResult(null)
    setDiagnosis(null)
    if (withDiagnosis) diagnoseMut.mutate({ log_id: row.id })
  }

  const openFingerprintDetail = (fingerprint: string, withDiagnosis = false, row?: SlowQueryFingerprintItem) => {
    setDetailFingerprint(fingerprint)
    setSqlDetail(null)
    setExplainResult(null)
    setDiagnosis(null)
    if (withDiagnosis) diagnoseMut.mutate({ fingerprint, instance_id: instanceId })
    if (row && !withDiagnosis) {
      // Keep the drawer responsive while detail data loads.
      setDetailFingerprint(row.sql_fingerprint)
    }
  }

  const openConfig = (record: SlowQueryConfigItem) => {
    setEditingConfig(record)
    configForm.setFieldsValue({
      is_enabled: record.is_enabled,
      threshold_ms: record.threshold_ms,
      collect_interval: record.collect_interval,
      retention_days: record.retention_days,
      collect_limit: record.collect_limit,
    })
    setConfigOpen(true)
  }

  const closeConfig = () => {
    setConfigOpen(false)
    setEditingConfig(null)
    configForm.resetFields()
  }

  const commonColumns: ColumnsType<SlowQueryLogItem> = [
    {
      title: '发生时间',
      dataIndex: 'occurred_at',
      width: 150,
      render: formatTime,
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 110,
      render: (v: string) => <Tag color={SOURCE_COLOR[v] || 'default'}>{sourceLabel(v)}</Tag>,
    },
    {
      title: '实例 / 数据库',
      key: 'target',
      width: 220,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Text strong ellipsis style={{ maxWidth: 190 }}>{row.instance_name || `#${row.instance_id || '-'}`}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{formatDbTypeLabel(row.db_type)} / {row.db_name || '—'}</Text>
        </Space>
      ),
    },
    {
      title: 'SQL 摘要',
      dataIndex: 'sql_text',
      width: 360,
      ellipsis: true,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 110,
      sorter: (a, b) => a.duration_ms - b.duration_ms,
      render: (v: number) => <Text strong type={v >= 10000 ? 'danger' : undefined}>{formatMs(v)}</Text>,
    },
    {
      title: '行数',
      key: 'rows',
      width: 130,
      render: (_, row) => <Text type="secondary">{row.rows_examined || 0} / {row.rows_sent || 0}</Text>,
    },
    {
      title: '标签',
      dataIndex: 'analysis_tags',
      width: 180,
      render: (tags: string[]) => (
        <Space size={4} wrap>
          {(tags || []).slice(0, 2).map(tag => <Tag key={tag}>{tag}</Tag>)}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 120,
      render: (_, row) => (
        <Space size={4}>
          <Button size="small" icon={<EyeOutlined />} onClick={() => openLogDetail(row)} />
          <Button size="small" icon={<BulbOutlined />} loading={diagnoseMut.isPending} onClick={() => openLogDetail(row, true)} />
        </Space>
      ),
    },
  ]

  const groupStatColumns: ColumnsType<SlowQueryGroupStat> = [
    {
      title: instanceId ? '数据库 / Schema' : '实例',
      key: 'target',
      width: 240,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Text strong ellipsis style={{ maxWidth: 210 }}>{row.group_name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {instanceId ? (row.instance_name || '当前实例') : formatDbTypeLabel(row.db_type)}
          </Text>
        </Space>
      ),
    },
    { title: '样本', dataIndex: 'total', width: 90, sorter: (a, b) => a.total - b.total },
    { title: '指纹', dataIndex: 'fingerprint_count', width: 90, sorter: (a, b) => a.fingerprint_count - b.fingerprint_count },
    ...(!instanceId ? [{ title: '库/Schema', dataIndex: 'database_count', width: 110, sorter: (a: SlowQueryGroupStat, b: SlowQueryGroupStat) => a.database_count - b.database_count }] : []),
    { title: '平均耗时', dataIndex: 'avg_duration_ms', width: 120, render: formatMs, sorter: (a, b) => a.avg_duration_ms - b.avg_duration_ms },
    { title: 'P95', dataIndex: 'p95_duration_ms', width: 110, render: formatMs, sorter: (a, b) => a.p95_duration_ms - b.p95_duration_ms },
    { title: '最高耗时', dataIndex: 'max_duration_ms', width: 120, render: (v: number) => <Text type={v >= 10000 ? 'danger' : undefined}>{formatMs(v)}</Text>, sorter: (a, b) => a.max_duration_ms - b.max_duration_ms },
    { title: '异常', dataIndex: 'failed_count', width: 90, sorter: (a, b) => a.failed_count - b.failed_count },
    { title: '最近出现', dataIndex: 'last_seen_at', width: 150, render: formatTime },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 110,
      render: (_, row) => (
        <Button
          size="small"
          icon={<SearchOutlined />}
          onClick={() => {
            if (instanceId) {
              setDbName(row.db_name || '')
            } else if (row.instance_id) {
              setInstanceId(row.instance_id)
              setDbName('')
            }
            setPage(1)
          }}
        >
          查看
        </Button>
      ),
    },
  ]

  const fingerprintColumns: ColumnsType<SlowQueryFingerprintItem> = [
    {
      title: 'SQL 指纹',
      dataIndex: 'fingerprint_text',
      width: 360,
      ellipsis: true,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: '实例 / 数据库',
      key: 'target',
      width: 240,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Text strong ellipsis style={{ maxWidth: 210 }}>{row.instance_name || `#${row.instance_id || '-'}`}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {formatDbTypeLabel(row.db_type)} / {row.db_name || '—'}
          </Text>
          {(row.instance_count > 1 || row.database_count > 1) && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              覆盖 {row.instance_count || 0} 实例 / {row.database_count || 0} 库
            </Text>
          )}
        </Space>
      ),
    },
    { title: '次数', dataIndex: 'count', width: 80, sorter: (a, b) => a.count - b.count },
    { title: '平均耗时', dataIndex: 'avg_duration_ms', width: 110, render: formatMs, sorter: (a, b) => a.avg_duration_ms - b.avg_duration_ms },
    { title: 'P95', dataIndex: 'p95_duration_ms', width: 110, render: formatMs },
    { title: '最大耗时', dataIndex: 'max_duration_ms', width: 110, render: formatMs },
    {
      title: '标签',
      dataIndex: 'analysis_tags',
      width: 190,
      render: (tags: string[]) => (
        <Space size={4} wrap>
          {(tags || []).slice(0, 3).map(tag => <Tag key={tag}>{tag}</Tag>)}
        </Space>
      ),
    },
    { title: '最后出现', dataIndex: 'last_seen_at', width: 150, render: formatTime },
    {
      title: '操作',
      key: 'sample',
      fixed: 'right',
      width: 140,
      render: (_, row) => (
        <Space size={4}>
          <Button size="small" icon={<SearchOutlined />} onClick={() => setSampleFingerprint(row.sql_fingerprint)} />
          <Button size="small" icon={<EyeOutlined />} onClick={() => openFingerprintDetail(row.sql_fingerprint, false, row)} />
          <Button size="small" icon={<BulbOutlined />} loading={diagnoseMut.isPending} onClick={() => openFingerprintDetail(row.sql_fingerprint, true, row)} />
        </Space>
      ),
    },
  ]

  const configColumns: ColumnsType<SlowQueryConfigItem> = [
    {
      title: '实例',
      key: 'instance',
      width: 220,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Text strong>{row.instance_name || `#${row.instance_id}`}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{formatDbTypeLabel(row.db_type)}</Text>
        </Space>
      ),
    },
    { title: '阈值', dataIndex: 'threshold_ms', width: 100, render: formatMs },
    { title: '间隔', dataIndex: 'collect_interval', width: 90, render: (v: number) => `${v}s` },
    { title: '保留', dataIndex: 'retention_days', width: 90, render: (v: number) => `${v}天` },
    { title: '上限', dataIndex: 'collect_limit', width: 90 },
    {
      title: '最近采集 / 错误',
      key: 'last_collect',
      width: 260,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Space size={4}>
            <Tag color={row.last_collect_status === 'success' ? 'success' : row.last_collect_status === 'failed' ? 'error' : 'default'}>
              {row.last_collect_status}
            </Tag>
            <Text type="secondary">{row.last_collect_count} 条</Text>
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>{formatTime(row.last_collect_at)}</Text>
          {row.last_collect_error && (
            <Tooltip title={row.last_collect_error}>
              <Text type="danger" ellipsis style={{ width: 230, display: 'block', fontSize: 12 }}>
                {row.last_collect_error}
              </Text>
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: '启用',
      dataIndex: 'is_enabled',
      width: 80,
      render: (v: boolean, row) => (
        <Switch
          size="small"
          checked={v}
          loading={configUpdateMut.isPending}
          onChange={(checked) => configUpdateMut.mutate({ id: row.id, data: { is_enabled: checked } })}
        />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 100,
      render: (_, row) => <Button size="small" icon={<SettingOutlined />} onClick={() => openConfig(row)}>编辑</Button>,
    },
  ]

  const realtimeItems = realtimeQuery.data?.items ?? []
  const realtimeKeys = realtimeItems.length ? Object.keys(realtimeItems[0]) : []
  const getRealtimeSql = (row: any) => row.query || row.Query || row.Info || row.info || row.sql_text || row.SQL_TEXT || ''
  const getRealtimeDb = (row: any) => row.db || row.DB || row.datname || row.db_name || row.DB_NAME || dbName
  const realtimeColumns = [
    ...realtimeKeys.map(k => ({
    title: k,
    dataIndex: k,
    key: k,
    ellipsis: true,
    width: k.toLowerCase().includes('query') || k.toLowerCase().includes('info') ? 420 : 140,
    render: (v: any) => v === null ? <Text type="secondary">NULL</Text> : String(v),
    })),
    {
      title: '操作',
      key: 'actions',
      fixed: 'right' as const,
      width: 110,
      render: (_: any, row: any) => (
        <Button
          size="small"
          icon={<BulbOutlined />}
          disabled={!instanceId || !getRealtimeSql(row)}
          loading={diagnoseMut.isPending}
          onClick={() => {
            setSqlDetail(null)
            setDetailFingerprint(null)
            diagnoseMut.mutate({ instance_id: instanceId, db_name: getRealtimeDb(row), sql: getRealtimeSql(row) })
          }}
        >
          诊断
        </Button>
      ),
    },
  ]

  const renderGroupTrend = (metric: 'count' | 'avg_duration_ms', title: string) => {
    const trends = overview?.group_trends || []
    const data = buildTrendRows(trends, metric)
    return (
      <Card title={title} loading={overviewQuery.isLoading}>
        <div style={{ height: 240 }}>
          {trends.length ? (
            <ResponsiveContainer>
              <LineChart data={data}>
                <XAxis dataKey="bucket" tick={{ fontSize: 11 }} minTickGap={24} />
                <YAxis tick={{ fontSize: 11 }} />
                <ChartTooltip />
                {trends.map((group, idx) => (
                  <Line
                    key={group.group_key}
                    type="monotone"
                    dataKey={group.group_key}
                    name={group.group_name}
                    stroke={TREND_COLORS[idx % TREND_COLORS.length]}
                    strokeWidth={2}
                    dot={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <TableEmptyState title="暂无趋势数据" />
          )}
        </div>
      </Card>
    )
  }

  const findingColumns: ColumnsType<OptimizeFinding> = [
    { title: '级别', dataIndex: 'severity', width: 92, render: (v: string) => <Tag color={SEVERITY_COLOR[v]}>{v?.toUpperCase()}</Tag> },
    { title: '问题', dataIndex: 'title', width: 170 },
    { title: '说明', dataIndex: 'detail' },
    { title: '证据', dataIndex: 'evidence', width: 180, ellipsis: true },
  ]

  const recColumns: ColumnsType<OptimizeRecommendation> = [
    { title: '优先级', dataIndex: 'priority', width: 80 },
    { title: '类型', dataIndex: 'type', width: 110, render: (v: string) => <Tag>{v}</Tag> },
    { title: '建议', dataIndex: 'title', width: 180 },
    { title: '操作', dataIndex: 'action' },
    { title: '原因', dataIndex: 'reason' },
  ]

  const renderDiagnosisPanel = (result?: OptimizeAnalyzeResponse | null) => result ? (
    <Card size="small" title="诊断结果">
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        {!result.supported && <Alert type="info" showIcon message={result.msg || '当前引擎不进入 SQL 优化主链路'} />}
        <Space align="start" size={16} wrap>
          <Progress
            type="dashboard"
            percent={result.risk_score}
            size={104}
            strokeColor={RISK_COLOR(result.risk_score)}
          />
          <Space direction="vertical" style={{ maxWidth: 620 }}>
            <Space wrap>
              <Tag color="blue">{formatDbTypeLabel(result.engine)}</Tag>
              <Tag>{result.support_level}</Tag>
              <Tag>{result.source === 'manual' ? '手工 SQL' : result.source === 'fingerprint' ? 'SQL 指纹' : 'SQL 样本'}</Tag>
            </Space>
            <Text strong>{result.summary}</Text>
            <Button
              size="small"
              icon={<CopyOutlined />}
              onClick={() => navigator.clipboard.writeText(result.sql).then(() => msgApi.success('SQL 已复制'))}
            >
              复制 SQL
            </Button>
          </Space>
        </Space>
        <Table<OptimizeFinding>
          title={() => '关键问题'}
          dataSource={(result.findings || []).map((item, i) => ({ ...item, key: `${item.code}-${i}` }))}
          columns={findingColumns}
          size="small"
          tableLayout="fixed"
          scroll={{ x: 760 }}
          pagination={false}
        />
        <Table<OptimizeRecommendation>
          title={() => '优化建议'}
          dataSource={(result.recommendations || []).map((item, i) => ({ ...item, key: `${item.priority}-${i}` }))}
          columns={recColumns}
          size="small"
          tableLayout="fixed"
          scroll={{ x: 980 }}
          pagination={false}
        />
        <Descriptions size="small" bordered column={{ xs: 1, sm: 2 }}>
          <Descriptions.Item label="全表扫描">{result.plan?.summary?.full_scan ? '是' : '否'}</Descriptions.Item>
          <Descriptions.Item label="估算行数">{result.plan?.summary?.rows_estimate ?? 0}</Descriptions.Item>
          <Descriptions.Item label="最大成本">{result.plan?.summary?.max_cost ?? 0}</Descriptions.Item>
          <Descriptions.Item label="临时表">{result.plan?.summary?.temporary ? '是' : '否'}</Descriptions.Item>
          <Descriptions.Item label="涉及表" span={2}>
            <Space wrap size={[4, 4]}>
              {(result.metadata?.tables || []).map(table => <Tag key={table}>{table}</Tag>)}
              {!(result.metadata?.tables || []).length && <Text type="secondary">未识别到表名</Text>}
            </Space>
          </Descriptions.Item>
        </Descriptions>
        {result.raw && (
          <Paragraph code copyable style={{ whiteSpace: 'pre-wrap', maxHeight: 260, overflow: 'auto' }}>
            {JSON.stringify(result.raw, null, 2)}
          </Paragraph>
        )}
      </Space>
    </Card>
  ) : null

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="SQL 分析"
        meta={`共 ${overview?.total ?? 0} 条 SQL 样本，${overview?.fingerprint_count ?? 0} 个指纹`}
      />

      <FilterCard marginBottom={16}>
        <Space wrap size={[8, 8]} style={{ display: 'flex' }}>
          <RangePicker
            showTime
            value={dateRange ? [dayjs(dateRange[0]), dayjs(dateRange[1])] : null}
            style={{ width: filterWidth(360) }}
            onChange={(_, strs) => { setDateRange(strs[0] ? [dayjs(strs[0]).toISOString(), dayjs(strs[1]).toISOString()] : null); setPage(1) }}
          />
          <Select
            placeholder="实例"
            allowClear
            showSearch
            optionFilterProp="label"
            style={{ width: filterWidth(210) }}
            value={instanceId}
            onChange={(v) => { setInstanceId(v); setDbName(''); setPage(1) }}
            onClear={() => setDbName('')}
            options={(instanceData?.items || []).map(inst => ({
              value: inst.id,
              label: inst.instance_name,
              children: inst.instance_name,
            }))}
          />
          <Select
            placeholder="数据库"
            allowClear
            showSearch
            optionFilterProp="label"
            disabled={!instanceId}
            style={{ width: filterWidth(150) }}
            value={dbName || undefined}
            onChange={(v) => { setDbName(v || ''); setPage(1) }}
            options={(dbData?.databases || [])
              .filter(db => db.is_active)
              .map(db => ({ value: db.db_name, label: db.db_name }))}
          />
          <Select placeholder="来源" allowClear style={{ width: filterWidth(140) }} value={source} onChange={(v) => { setSource(v); setPage(1) }} options={SOURCE_OPTIONS} />
          <Input placeholder="SQL 关键字" allowClear style={{ width: filterWidth(180) }} value={sqlKeyword} onChange={(e) => { setSqlKeyword(e.target.value); setPage(1) }} />
          <Input placeholder="用户" allowClear style={{ width: filterWidth(130) }} value={username} onChange={(e) => { setUsername(e.target.value); setPage(1) }} />
          <Select
            placeholder={instanceId ? '标签' : '先选实例'}
            allowClear
            disabled={!instanceId || !tagSelectOptions.length}
            loading={tagOptionsQuery.isLoading}
            style={{ width: filterWidth(150) }}
            value={tag}
            onChange={(v) => { setTag(v); setPage(1) }}
            options={tagSelectOptions}
          />
          <InputNumber min={0} step={500} addonAfter="ms" style={{ width: filterWidth(140) }} value={minDurationMs} onChange={(v) => { setMinDurationMs(Number(v || 0)); setPage(1) }} />
          <Button icon={<ReloadOutlined />} onClick={() => { overviewQuery.refetch(); logQuery.refetch(); fingerprintQuery.refetch(); realtimeQuery.refetch() }}>刷新</Button>
          <Button icon={<CloudDownloadOutlined />} type="primary" loading={collectMut.isPending} onClick={() => collectMut.mutate()}>立即采集一次</Button>
          <Button onClick={resetFilters}>重置</Button>
        </Space>
      </FilterCard>

      {unsupportedNative && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Text type="secondary">{formatDbTypeLabel(selectedInstance.db_type)} 当前仅支持平台查询历史和手工 SQL 诊断，暂不支持原生 SQL 采集。</Text>
        </Card>
      )}

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'overview',
            label: '总览',
            children: (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(6, 1fr)', gap: 12 }}>
                  <Card><Statistic title="SQL 样本" value={overview?.total || 0} /></Card>
                  <Card><Statistic title="SQL 指纹" value={overview?.fingerprint_count || 0} /></Card>
                  <Card><Statistic title="影响实例" value={overview?.instance_count || 0} /></Card>
                  <Card><Statistic title="平均耗时" value={overview?.avg_duration_ms || 0} suffix="ms" /></Card>
                  <Card><Statistic title="P95 耗时" value={overview?.p95_duration_ms || 0} suffix="ms" /></Card>
                  <Card><Statistic title="异常样本" value={overview?.failed_count || 0} /></Card>
                </div>
                <Card title={primaryStatsTitle} styles={{ body: { padding: 0 } }}>
                  <Table
                    dataSource={primaryStats.map(row => ({ ...row, key: row.group_key }))}
                    columns={groupStatColumns}
                    loading={overviewQuery.isLoading || overviewQuery.isFetching}
                    size="small"
                    tableLayout="fixed"
                    scroll={{ x: instanceId ? 1120 : 1230 }}
                    pagination={false}
                    locale={{ emptyText: <TableEmptyState title={primaryStatsEmptyTitle} /> }}
                  />
                </Card>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 16 }}>
                  {renderGroupTrend('count', `${groupTrendTitle}（数量）`)}
                  {renderGroupTrend('avg_duration_ms', `${groupTrendTitle}（平均耗时）`)}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'minmax(280px, 0.8fr) minmax(360px, 1.2fr)', gap: 16 }}>
                  <Card title="来源分布">
                    <Space wrap>
                      {(overview?.source_distribution || []).map(item => (
                        <Tag key={item.name} color={SOURCE_COLOR[item.name] || 'default'}>
                          {sourceLabel(item.name)} {item.count}
                        </Tag>
                      ))}
                      {!(overview?.source_distribution || []).length && <Text type="secondary">暂无来源数据</Text>}
                    </Space>
                  </Card>
                <Card title="最高耗时 SQL">
                  {overview?.slowest ? (
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Space wrap>
                        <Tag color={SOURCE_COLOR[overview.slowest.source] || 'default'}>{sourceLabel(overview.slowest.source)}</Tag>
                        <Text strong>{overview.slowest.instance_name}</Text>
                        <Text type="danger">{formatMs(overview.slowest.duration_ms)}</Text>
                      </Space>
                      <Paragraph code copyable ellipsis={{ rows: 3, expandable: true }}>{overview.slowest.sql_text}</Paragraph>
                    </Space>
                  ) : <TableEmptyState title="暂无 SQL 样本" />}
                </Card>
                </div>
              </Space>
            ),
          },
          {
            key: 'logs',
            label: 'SQL 样本（明细）',
            children: (
              <Card styles={{ body: { padding: 0 } }}>
                <Table
                  dataSource={(logQuery.data?.items || []).map(row => ({ ...row, key: row.id }))}
                  columns={commonColumns}
                  loading={logQuery.isLoading || logQuery.isFetching}
                  size="small"
                  tableLayout="fixed"
                  scroll={{ x: 1450 }}
                  locale={{ emptyText: <TableEmptyState title="暂无 SQL 样本" /> }}
                  pagination={{
                    current: page,
                    pageSize: 50,
                    total: logQuery.data?.total || 0,
                    showSizeChanger: false,
                    onChange: setPage,
                  }}
                />
              </Card>
            ),
          },
          {
            key: 'fingerprints',
            label: 'SQL 指纹（聚合）',
            children: (
              <Card styles={{ body: { padding: 0 } }}>
                <Table
                  dataSource={(fingerprintQuery.data?.items || []).map(row => ({ ...row, key: row.sql_fingerprint }))}
                  columns={fingerprintColumns}
                  loading={fingerprintQuery.isLoading || fingerprintQuery.isFetching}
                  size="small"
                  tableLayout="fixed"
                  scroll={{ x: 1490 }}
                  pagination={false}
                  locale={{ emptyText: <TableEmptyState title="暂无指纹聚合数据" /> }}
                />
              </Card>
            ),
          },
          {
            key: 'realtime',
            label: '实时 SQL',
            children: (
              <Card styles={{ body: { padding: 0 } }}>
                <Table
                  dataSource={realtimeItems.map((row: any, idx: number) => ({ key: idx, ...row }))}
                  columns={realtimeColumns}
                  loading={realtimeQuery.isLoading || realtimeQuery.isFetching}
                  size="small"
                  tableLayout="fixed"
                  scroll={{ x: 'max-content' }}
                  pagination={{ pageSize: 50, showSizeChanger: false }}
                  locale={{ emptyText: <TableEmptyState title={instanceId ? '暂无实时 SQL' : '请先选择实例'} /> }}
                />
              </Card>
            ),
          },
          {
            key: 'manual',
            label: '手工诊断',
            children: (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Card>
                  <Form form={manualForm} layout="vertical" onFinish={runManualDiagnosis}>
                    <Space style={{ width: '100%' }} align="start" wrap>
                      <Form.Item name="instance_id" label="实例" rules={[{ required: true, message: '请选择实例' }]} style={{ minWidth: filterWidth(260), flex: 1 }}>
                        <Select
                          showSearch
                          optionFilterProp="label"
                          placeholder="选择实例"
                          onChange={() => manualForm.setFieldValue('db_name', '')}
                          options={(instanceData?.items || []).map(inst => ({ value: inst.id, label: inst.instance_name }))}
                        />
                      </Form.Item>
                      <Form.Item noStyle shouldUpdate={(prev, curr) => prev.instance_id !== curr.instance_id}>
                        {({ getFieldValue }) => {
                          const selected = getFieldValue('instance_id')
                          return (
                            <Form.Item name="db_name" label="数据库/Schema" style={{ minWidth: filterWidth(220), flex: 1 }}>
                              <Select
                                allowClear
                                showSearch
                                disabled={!selected}
                                optionFilterProp="label"
                                placeholder="默认库"
                                options={(selected === instanceId ? (dbData?.databases || []) : [])
                                  .filter(db => db.is_active)
                                  .map(db => ({ value: db.db_name, label: db.db_name }))}
                              />
                            </Form.Item>
                          )
                        }}
                      </Form.Item>
                    </Space>
                    <Form.Item name="sql" label="SQL" rules={[{ required: true, message: '请输入 SQL' }]}>
                      <Input.TextArea rows={10} style={{ fontFamily: '"JetBrains Mono", monospace' }} />
                    </Form.Item>
                    <Space>
                      <Button type="primary" icon={<BulbOutlined />} htmlType="submit" loading={manualDiagnoseMut.isPending}>
                        开始诊断
                      </Button>
                      <Button onClick={() => { manualForm.resetFields(); setManualDiagnosis(null) }}>
                        清空
                      </Button>
                    </Space>
                  </Form>
                </Card>
                {manualDiagnosis && (
                  <Card size="small" title="SQL">
                    <Paragraph code copyable style={{ whiteSpace: 'pre-wrap' }}>{manualDiagnosis.sql}</Paragraph>
                  </Card>
                )}
                {renderDiagnosisPanel(manualDiagnosis)}
              </Space>
            ),
          },
          {
            key: 'configs',
            label: '采集配置',
            children: (
              <Card styles={{ body: { padding: 0 } }}>
                <Table
                  dataSource={(configQuery.data?.items || []).map(row => ({ ...row, key: row.id }))}
                  columns={configColumns}
                  loading={configQuery.isLoading || configQuery.isFetching}
                  size="small"
                  tableLayout="fixed"
                  scroll={{ x: 1020 }}
                  pagination={false}
                  locale={{ emptyText: <TableEmptyState title="暂无可见实例配置" /> }}
                />
              </Card>
            ),
          },
        ]}
      />

      <Drawer
        title="SQL 详情"
        width={isMobile ? '100%' : 720}
        open={!!sqlDetail}
        onClose={() => { setSqlDetail(null); setDiagnosis(null) }}
      >
        {sqlDetail && (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Space wrap>
              <Tag color={SOURCE_COLOR[sqlDetail.source] || 'default'}>{sourceLabel(sqlDetail.source)}</Tag>
              <Text>{sqlDetail.instance_name}</Text>
              <Text type="danger">{formatMs(sqlDetail.duration_ms)}</Text>
              {(sqlDetail.analysis_tags || []).map(tag => <Tag key={tag}>{tag}</Tag>)}
            </Space>
            <Space>
              <Button
                type="primary"
                icon={<BulbOutlined />}
                loading={diagnoseMut.isPending}
                onClick={() => diagnoseMut.mutate({ log_id: sqlDetail.id })}
              >
                优化诊断
              </Button>
              <Button
                icon={<LineChartOutlined />}
                loading={explainMut.isPending}
                disabled={!['mysql', 'pgsql'].includes(sqlDetail.db_type)}
                onClick={() => explainMut.mutate(sqlDetail.id)}
              >
                执行计划
              </Button>
            </Space>
            {renderDiagnosisPanel(diagnosis)}
            {explainResult && (
              <Card size="small" title="执行计划分析">
                {!explainResult.supported && <Alert type="info" showIcon message={explainResult.msg || '当前引擎暂不支持执行计划分析'} />}
                {explainResult.supported && explainResult.msg && <Alert type="warning" showIcon message={explainResult.msg} />}
                {explainResult.supported && !explainResult.msg && (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Space wrap>
                      <Tag color={explainResult.plan?.full_scan ? 'error' : 'success'}>全表扫描 {explainResult.plan?.full_scan ? '是' : '否'}</Tag>
                      <Tag>估算行数 {explainResult.plan?.rows_estimate || 0}</Tag>
                      <Tag>最大成本 {explainResult.plan?.max_cost || 0}</Tag>
                      {explainResult.plan?.filesort && <Tag color="warning">filesort</Tag>}
                      {explainResult.plan?.temporary && <Tag color="warning">temporary</Tag>}
                    </Space>
                    {(explainResult.summary || []).map(item => (
                      <Alert
                        key={`${item.title}-${item.detail}`}
                        type={item.severity === 'critical' ? 'error' : item.severity === 'warning' ? 'warning' : 'info'}
                        showIcon
                        message={item.title}
                        description={item.detail}
                      />
                    ))}
                    <Paragraph code copyable style={{ whiteSpace: 'pre-wrap', maxHeight: 260, overflow: 'auto' }}>
                      {JSON.stringify(explainResult.raw, null, 2)}
                    </Paragraph>
                  </Space>
                )}
              </Card>
            )}
            <Paragraph code copyable style={{ whiteSpace: 'pre-wrap' }}>{sqlDetail.sql_text}</Paragraph>
          </Space>
        )}
      </Drawer>

      <Drawer
        title="指纹详情"
        width={isMobile ? '100%' : 860}
        open={!!detailFingerprint}
        onClose={() => { setDetailFingerprint(null); setDiagnosis(null) }}
      >
        {detailQuery.data && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card size="small">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space wrap>
                  <Statistic title="次数" value={detailQuery.data.fingerprint.count} />
                  <Statistic title="平均耗时" value={detailQuery.data.fingerprint.avg_duration_ms} suffix="ms" />
                  <Statistic title="P95" value={detailQuery.data.fingerprint.p95_duration_ms} suffix="ms" />
                  <Statistic title="最大耗时" value={detailQuery.data.fingerprint.max_duration_ms} suffix="ms" />
                </Space>
                <Paragraph code copyable ellipsis={{ rows: 3, expandable: true }}>{detailQuery.data.fingerprint.sample_sql}</Paragraph>
                <Space>
                  <Button
                    type="primary"
                    icon={<BulbOutlined />}
                    loading={diagnoseMut.isPending}
                    onClick={() => diagnoseMut.mutate({ fingerprint: detailQuery.data.fingerprint.sql_fingerprint, instance_id: instanceId })}
                  >
                    优化诊断
                  </Button>
                </Space>
              </Space>
            </Card>
            {renderDiagnosisPanel(diagnosis)}
            <Card size="small" title="趋势">
              <div style={{ height: 220 }}>
                <ResponsiveContainer>
                  <LineChart data={detailQuery.data.trends}>
                    <XAxis dataKey="bucket" tick={{ fontSize: 11 }} minTickGap={24} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <ChartTooltip />
                    <Line type="monotone" dataKey="count" name="次数" stroke="#1677ff" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="avg_duration_ms" name="平均耗时(ms)" stroke="#fa8c16" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card size="small" title="优化建议">
              <Space direction="vertical" style={{ width: '100%' }}>
                {detailQuery.data.recommendations.map(item => (
                  <Alert
                    key={`${item.title}-${item.detail}`}
                    type={item.severity === 'critical' ? 'error' : item.severity === 'warning' ? 'warning' : 'info'}
                    showIcon
                    message={item.title}
                    description={item.detail}
                  />
                ))}
              </Space>
            </Card>
            <Card size="small" title="分布">
              <Space wrap align="start">
                {[
                  ['实例', detailQuery.data.instance_distribution],
                  ['数据库', detailQuery.data.database_distribution],
                  ['用户', detailQuery.data.user_distribution],
                  ['来源', detailQuery.data.source_distribution],
                ].map(([title, items]) => (
                  <Card key={title as string} size="small" title={title as string} style={{ width: 190 }}>
                    <Space direction="vertical" size={4}>
                      {(items as any[]).slice(0, 5).map(item => (
                        <Text key={item.name} ellipsis style={{ maxWidth: 150 }}>{item.name}: {item.count}</Text>
                      ))}
                    </Space>
                  </Card>
                ))}
              </Space>
            </Card>
          </Space>
        )}
      </Drawer>

      <Drawer
        title="SQL 诊断"
        width={isMobile ? '100%' : 860}
        open={!!diagnosis && !sqlDetail && !detailFingerprint}
        onClose={() => setDiagnosis(null)}
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card size="small" title="SQL">
            <Paragraph code copyable style={{ whiteSpace: 'pre-wrap' }}>{diagnosis?.sql}</Paragraph>
          </Card>
          {renderDiagnosisPanel(diagnosis)}
        </Space>
      </Drawer>

      <Modal
        title={editingConfig ? `编辑采集配置：${editingConfig.instance_name || `#${editingConfig.instance_id}`}` : '编辑采集配置'}
        open={configOpen}
        onCancel={closeConfig}
        onOk={async () => {
          const values = await configForm.validateFields()
          if (!editingConfig) return
          configUpdateMut.mutate({ id: editingConfig.id, data: values }, { onSuccess: closeConfig })
        }}
        confirmLoading={configUpdateMut.isPending}
        maskClosable={false}
      >
        <Form form={configForm} layout="vertical" style={{ marginTop: 16 }}>
          {editingConfig && (
            <Alert
              type="info"
              showIcon
              message={editingConfig.instance_name || `#${editingConfig.instance_id}`}
              description={formatDbTypeLabel(editingConfig.db_type)}
              style={{ marginBottom: 16 }}
            />
          )}
          <Form.Item name="is_enabled" label="启用采集" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="threshold_ms" label="SQL 耗时阈值（ms）" rules={[{ required: true }]}>
            <InputNumber min={0} max={3600000} step={500} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="collect_interval" label="采集间隔（秒）" rules={[{ required: true }]}>
            <InputNumber min={30} max={86400} step={30} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="retention_days" label="保留天数" rules={[{ required: true }]}>
            <InputNumber min={1} max={365} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="collect_limit" label="单次采集上限" rules={[{ required: true }]}>
            <InputNumber min={1} max={1000} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="指纹样例"
        width={860}
        open={!!sampleFingerprint}
        onCancel={() => setSampleFingerprint(null)}
        maskClosable={false}
        footer={null}
      >
        <Table
          dataSource={(sampleQuery.data?.items || []).map(row => ({ ...row, key: row.id }))}
          columns={commonColumns.filter(col => col.key !== 'actions')}
          loading={sampleQuery.isLoading}
          size="small"
          tableLayout="fixed"
          scroll={{ x: 1200 }}
          pagination={false}
        />
      </Modal>
    </div>
  )
}
