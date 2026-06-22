import { useEffect, useMemo, useState } from 'react'
import {
  Alert, Button, Card, Drawer, Form, Grid, Modal,
  Space, Statistic, Table, Tag, Typography, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { BulbOutlined, EyeOutlined, LineChartOutlined, SearchOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { Line, LineChart, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from 'recharts'
import { instanceApi } from '@/api/instance'
import { optimizeApi, type OptimizeAnalyzeResponse } from '@/api/optimize'
import {
  slowlogApi,
  type SlowQueryCollectResponse,
  type SlowQueryExplainResponse,
  type SlowQueryFingerprintItem,
  type SlowQueryGroupStat,
  type SlowQueryLogItem,
  type SlowQueryParams,
} from '@/api/slowlog'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'
import { TruncatedCell } from '@/components/common/TruncatedCell'
import { renderTruncatedCell } from '@/components/common/renderTruncatedCell'
import { useAuthStore } from '@/store/auth'
import { formatDbTypeLabel } from '@/utils/dbType'
import {
  SOURCE_COLOR,
  TREND_COLORS,
  buildTrendRows,
  formatMs,
  formatTime,
  renderSourceTag,
  sourceLabel,
} from '../helpers'
import type { SqlInsightPanelProps } from '../types'
import DiagnosisPanel from './DiagnosisPanel'
import { SlowlogFilters } from './SlowlogFilters'
import { SlowlogTable } from './SlowlogTable'

const { Text, Paragraph } = Typography
const { useBreakpoint } = Grid

export function SqlInsightPanel({ embedded = false, instanceId: externalInstanceId }: SqlInsightPanelProps) {
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const queryClient = useQueryClient()
  const hasPermission = useAuthStore((s) => s.hasPermission)
  const canAnalyze = hasPermission('observability_sql_analyze')
  const canManageCollect = hasPermission('observability_collect_manage')
  const [msgApi, msgCtx] = message.useMessage()
  const [page, setPage] = useState(1)
  const [instanceId, setInstanceId] = useState<number | undefined>(externalInstanceId || undefined)
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
  const [explainResult, setExplainResult] = useState<SlowQueryExplainResponse | null>(null)

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
    if (!externalInstanceId) return
    setInstanceId(externalInstanceId)
    setDbName('')
    setPage(1)
    manualForm.setFieldValue('instance_id', externalInstanceId)
  }, [externalInstanceId, manualForm])

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

  const overview = overviewQuery.data
  const primaryStats = instanceId ? (overview?.database_stats || []) : (overview?.instance_stats || [])
  const primaryStatsTitle = instanceId ? '数据库 / Schema 统计' : '实例统计'
  const primaryStatsEmptyTitle = instanceId ? '暂无数据库 / Schema 统计' : '暂无实例统计'
  const groupTrendTitle = instanceId ? '数据库 / Schema 趋势' : '实例趋势'

  const collectMut = useMutation<SlowQueryCollectResponse>({
    mutationFn: () => slowlogApi.collect({ instance_id: instanceId, limit: 100 }),
    onSuccess: (data) => {
      msgApi.success(`采集完成：新增 ${data.saved} 条，失败 ${data.failed}`)
      queryClient.invalidateQueries({ queryKey: ['slowlog-overview'] })
      queryClient.invalidateQueries({ queryKey: ['slowlog-logs'] })
      queryClient.invalidateQueries({ queryKey: ['slowlog-fingerprints'] })
      queryClient.invalidateQueries({ queryKey: ['slowlog-configs'] })
      if (data.saved === 0) {
        Modal.info({
          title: '本次没有新增 SQL 样本',
          maskClosable: false,
          content: '请检查实例采集配置里的 SQL 阈值、最近 1 天时间范围、数据库统计/活动视图，以及平台查询历史中是否存在符合条件的记录。',
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
    setInstanceId(embedded ? externalInstanceId || undefined : undefined)
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
      // 明细数据加载期间先用当前行填充，保持抽屉响应及时。
      setDetailFingerprint(row.sql_fingerprint)
    }
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
      width: 150,
      render: renderSourceTag,
    },
    {
      title: '实例 / 数据库',
      key: 'target',
      width: 240,
      render: (_, row) => (
        <Space direction="vertical" size={0} style={{ minWidth: 0, width: '100%' }}>
          <TruncatedCell value={row.instance_name || `#${row.instance_id || '-'}`} strong />
          <Text type="secondary">{formatDbTypeLabel(row.db_type)} / {row.db_name || '—'}</Text>
        </Space>
      ),
    },
    {
      title: 'SQL 摘要',
      dataIndex: 'sql_text',
      width: 360,
      ellipsis: { showTitle: false },
      render: (v: string) => <TruncatedCell value={v} code />,
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
      title: 'Oracle Monitor',
      key: 'oracle_monitor',
      width: 210,
      render: (_, row) => {
        const raw = (row.raw || {}) as Record<string, any>
        const value = [
          raw.status ? `状态 ${raw.status}` : '',
          raw.sql_exec_id ? `Exec ${raw.sql_exec_id}` : '',
          raw.plan_hash_value ? `PHV ${raw.plan_hash_value}` : '',
        ].filter(Boolean).join(' / ')
        return <TruncatedCell value={value} />
      },
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
      width: 150,
      render: (_, row) => (
        <Space size={4}>
          <Button className="sagitta-action-btn sagitta-action-btn--inspect" icon={<EyeOutlined />} onClick={() => openLogDetail(row)}>
            查看
          </Button>
          <Button className="sagitta-action-btn sagitta-action-btn--inspect" icon={<BulbOutlined />} disabled={!canAnalyze} loading={diagnoseMut.isPending} onClick={() => openLogDetail(row, true)}>
            诊断
          </Button>
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
          <TruncatedCell value={row.group_name} strong style={{ maxWidth: 210 }} />
          <Text type="secondary">
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
          className="sagitta-action-btn sagitta-action-btn--inspect"
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
      ellipsis: { showTitle: false },
      render: (v: string) => <TruncatedCell value={v} code />,
    },
    {
      title: '实例 / 数据库',
      key: 'target',
      width: 240,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <TruncatedCell value={row.instance_name || `#${row.instance_id || '-'}`} strong style={{ maxWidth: 210 }} />
          <Text type="secondary">
            {formatDbTypeLabel(row.db_type)} / {row.db_name || '—'}
          </Text>
          {(row.instance_count > 1 || row.database_count > 1) && (
            <Text type="secondary">
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
      width: 210,
      render: (_, row) => (
        <Space size={4}>
          <Button className="sagitta-action-btn sagitta-action-btn--inspect" icon={<SearchOutlined />} onClick={() => setSampleFingerprint(row.sql_fingerprint)}>
            样本
          </Button>
          <Button className="sagitta-action-btn sagitta-action-btn--inspect" icon={<EyeOutlined />} onClick={() => openFingerprintDetail(row.sql_fingerprint, false, row)}>
            查看
          </Button>
          <Button className="sagitta-action-btn sagitta-action-btn--inspect" icon={<BulbOutlined />} disabled={!canAnalyze} loading={diagnoseMut.isPending} onClick={() => openFingerprintDetail(row.sql_fingerprint, true, row)}>
            诊断
          </Button>
        </Space>
      ),
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
    ellipsis: { showTitle: false },
    width: k.toLowerCase().includes('query') || k.toLowerCase().includes('info') ? 420 : 140,
    render: (v: any) => v === null ? <Text type="secondary">NULL</Text> : <TruncatedCell value={String(v)} />,
    })),
    {
      title: '操作',
      key: 'actions',
      fixed: 'right' as const,
      width: 110,
      render: (_: any, row: any) => (
        <Button
          className="sagitta-action-btn sagitta-action-btn--inspect"
          icon={<BulbOutlined />}
          disabled={!canAnalyze || !instanceId || !getRealtimeSql(row)}
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

  const renderDiagnosisPanel = (result?: OptimizeAnalyzeResponse | null) => (
    <DiagnosisPanel result={result} onCopySql={() => msgApi.success('SQL 已复制')} />
  )

  return (
    <div>
      {msgCtx}
      {!embedded && (
        <PageHeader
          title="SQL 洞察"
          meta={`共 ${overview?.total ?? 0} 条 SQL 样本，${overview?.fingerprint_count ?? 0} 个指纹`}
        />
      )}

      <SlowlogFilters
        embedded={embedded}
        dateRange={dateRange}
        instanceId={instanceId}
        dbName={dbName}
        source={source}
        sqlKeyword={sqlKeyword}
        username={username}
        tag={tag}
        minDurationMs={minDurationMs}
        instances={instanceData?.items || []}
        databases={dbData?.databases || []}
        selectedInstance={selectedInstance}
        tagSelectOptions={tagSelectOptions}
        tagOptionsLoading={tagOptionsQuery.isLoading}
        canManageCollect={canManageCollect}
        collectLoading={collectMut.isPending}
        filterWidth={filterWidth}
        onDateRangeChange={(value) => { setDateRange(value); setPage(1) }}
        onInstanceIdChange={(value) => { setInstanceId(value); setDbName(''); setPage(1) }}
        onDbNameChange={(value) => { setDbName(value); setPage(1) }}
        onSourceChange={(value) => { setSource(value); setPage(1) }}
        onSqlKeywordChange={(value) => { setSqlKeyword(value); setPage(1) }}
        onUsernameChange={(value) => { setUsername(value); setPage(1) }}
        onTagChange={(value) => { setTag(value); setPage(1) }}
        onMinDurationMsChange={(value) => { setMinDurationMs(value); setPage(1) }}
        onRefresh={() => { overviewQuery.refetch(); logQuery.refetch(); fingerprintQuery.refetch(); realtimeQuery.refetch() }}
        onCollect={() => collectMut.mutate()}
        onReset={resetFilters}
      />

      <SlowlogTable
        activeTab={activeTab}
        onActiveTabChange={setActiveTab}
        isMobile={isMobile}
        instanceId={instanceId}
        overview={overview}
        overviewLoading={overviewQuery.isLoading || overviewQuery.isFetching}
        primaryStats={primaryStats}
        primaryStatsTitle={primaryStatsTitle}
        primaryStatsEmptyTitle={primaryStatsEmptyTitle}
        groupTrendTitle={groupTrendTitle}
        groupStatColumns={groupStatColumns}
        commonColumns={commonColumns}
        fingerprintColumns={fingerprintColumns}
        realtimeColumns={realtimeColumns}
        logItems={logQuery.data?.items || []}
        logTotal={logQuery.data?.total || 0}
        logLoading={logQuery.isLoading || logQuery.isFetching}
        fingerprintItems={fingerprintQuery.data?.items || []}
        fingerprintLoading={fingerprintQuery.isLoading || fingerprintQuery.isFetching}
        realtimeItems={realtimeItems}
        realtimeLoading={realtimeQuery.isLoading || realtimeQuery.isFetching}
        page={page}
        onPageChange={setPage}
        renderGroupTrend={renderGroupTrend}
        manualForm={manualForm}
        runManualDiagnosis={runManualDiagnosis}
        filterWidth={filterWidth}
        instances={instanceData?.items || []}
        databases={dbData?.databases || []}
        canAnalyze={canAnalyze}
        manualDiagnosis={manualDiagnosis}
        manualDiagnosisLoading={manualDiagnoseMut.isPending}
        onClearManualDiagnosis={() => setManualDiagnosis(null)}
        renderDiagnosisPanel={renderDiagnosisPanel}
      />

      <Drawer
        title="SQL 详情"
        width={isMobile ? '100%' : 720}
        open={!!sqlDetail}
        maskClosable={false}
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
                disabled={!canAnalyze}
                loading={diagnoseMut.isPending}
                onClick={() => diagnoseMut.mutate({ log_id: sqlDetail.id })}
              >
                优化诊断
              </Button>
              <Button
                icon={<LineChartOutlined />}
                loading={explainMut.isPending}
                disabled={!canAnalyze || !['mysql', 'pgsql'].includes(sqlDetail.db_type)}
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
        maskClosable={false}
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
                    disabled={!canAnalyze}
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
                    <Line type="monotone" dataKey="count" name="次数" stroke="#165DFF" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="avg_duration_ms" name="平均耗时(ms)" stroke="#FF7D00" strokeWidth={2} dot={false} />
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
                        <TruncatedCell key={item.name} value={`${item.name}: ${item.count}`} style={{ maxWidth: 150 }} />
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
        maskClosable={false}
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
          scroll={{ x: 1560 }}
          pagination={false}
        />
      </Modal>
    </div>
  )
}
