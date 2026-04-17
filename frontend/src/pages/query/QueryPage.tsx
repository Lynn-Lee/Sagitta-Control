import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import {
  Button, Card, Dropdown, InputNumber, Select, Space, Spin, Table, Tag, Typography, message, Alert,
} from 'antd'
import {
  PlayCircleOutlined, ClearOutlined, HistoryOutlined, ClockCircleOutlined, DownloadOutlined,
} from '@ant-design/icons'
import Editor from '@monaco-editor/react'
import { useQuery } from '@tanstack/react-query'
import { instanceApi } from '@/api/instance'
import { queryApi, type QueryAccessExplanation, type QueryResult } from '@/api/query'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Text } = Typography
const { Option } = Select

const EDITOR_OPTIONS = {
  fontFamily: '"JetBrains Mono", "Fira Code", Menlo, Consolas, monospace',
  fontSize: 13,
  lineHeight: 22,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  renderLineHighlight: 'line' as const,
  smoothScrolling: true,
  cursorBlinking: 'smooth' as const,
  padding: { top: 12, bottom: 12 },
  automaticLayout: true,
}

const FRONTEND_EXPORT_THRESHOLD = 5000

function triggerDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  window.URL.revokeObjectURL(url)
}

function extractFileName(contentDisposition?: string, fallback = 'query_result.xlsx') {
  if (!contentDisposition) return fallback
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1])
  const normalMatch = contentDisposition.match(/filename="?([^"]+)"?/i)
  return normalMatch?.[1] || fallback
}

function exportRowsAsCsv(headers: string[], rows: any[][], filename: string) {
  const lines = [
    headers,
    ...rows.map((row) => row.map((cell) => cell == null ? '' : String(cell))),
  ]
  const csv = lines
    .map((line) => line.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n')
  triggerDownload(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }), filename)
}

function exportRowsAsExcel(headers: string[], rows: any[][], filename: string) {
  const escapeHtml = (value: any) => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
  const table = `
    <table>
      <thead>
        <tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join('')}</tr>
      </thead>
      <tbody>
        ${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`).join('')}
      </tbody>
    </table>
  `
  const html = `
    <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel">
      <head><meta charset="UTF-8" /></head>
      <body>${table}</body>
    </html>
  `
  triggerDownload(new Blob([html], { type: 'application/vnd.ms-excel;charset=utf-8' }), filename)
}

export default function QueryPage() {
  const [instanceId, setInstanceId] = useState<number | undefined>()
  const [dbName, setDbName] = useState<string>('')
  const [sql, setSql] = useState<string>('')
  const [limitNum, setLimitNum] = useState<number>(100)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [accessExplanation, setAccessExplanation] = useState<QueryAccessExplanation | null>(null)
  const [executing, setExecuting] = useState(false)
  const [resultPage, setResultPage] = useState(1)
  const [resultPageSize, setResultPageSize] = useState(20)
  const [resultTableHeight, setResultTableHeight] = useState(460)
  const [msgApi, msgCtx] = message.useMessage()
  const resultCardRef = useRef<HTMLDivElement | null>(null)

  const { data: instanceData } = useQuery({
    queryKey: ['instances-for-query'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })

  const { data: dbData, isLoading: dbLoading } = useQuery({
    queryKey: ['registered-dbs', instanceId],
    queryFn: () => instanceApi.listRegisteredDbs(instanceId!),
    enabled: !!instanceId,
  })

  const handleExecute = useCallback(async () => {
    if (!instanceId) { msgApi.warning('请先选择实例'); return }
    if (!dbName) { msgApi.warning('请先选择数据库'); return }
    if (!sql.trim()) { msgApi.warning('SQL 不能为空'); return }

    setExecuting(true)
    setResult(null)
    setAccessExplanation(null)
    setResultPage(1)
    try {
      const res = await queryApi.execute({ instance_id: instanceId, db_name: dbName, sql, limit_num: limitNum })
      setResult(res)
      if (res.error) {
        msgApi.error(`执行失败：${res.error}`)
      } else {
        msgApi.success(`查询成功，${res.affected_rows} 行，耗时 ${res.cost_time_ms}ms`)
      }
    } catch (e: any) {
      const detail = e.response?.data?.msg || e.response?.data?.detail || '查询失败'
      if (e.response?.status === 403) {
        try {
          const explanation = await queryApi.explainAccess({
            instance_id: instanceId,
            db_name: dbName,
            sql,
            limit_num: limitNum,
          })
          setAccessExplanation(explanation)
          msgApi.error(explanation.reason || detail)
        } catch {
          msgApi.error(detail)
        }
      } else {
        msgApi.error(detail)
      }
    } finally {
      setExecuting(false)
    }
  }, [instanceId, dbName, sql, limitNum, msgApi])

  const resultColumns = [
    {
      title: 'row_num',
      dataIndex: '__rowNo',
      key: '__rowNo',
      width: 96,
      fixed: 'left' as const,
    },
    ...(
      result?.column_list.map((col, idx) => ({
        title: col,
        dataIndex: idx,
        key: col,
        ellipsis: true,
        width: 150,
        render: (v: any) => v === null ? <Text type="secondary" italic>NULL</Text> : String(v),
      })) ?? []
    ),
  ]

  const resultRows = result?.rows.map((row, i) => ({
    key: i,
    __rowNo: i + 1,
    ...Object.fromEntries(row.map((v: any, j: number) => [j, v])),
  })) ?? []

  const currentPageRows = useMemo(
    () => resultRows.slice((resultPage - 1) * resultPageSize, resultPage * resultPageSize),
    [resultRows, resultPage, resultPageSize],
  )

  const exportHeaders = useMemo(
    () => ['row_num', ...(result?.column_list ?? [])],
    [result?.column_list],
  )

  const toExportMatrix = (rows: typeof resultRows) => rows.map((row) => [
    row.__rowNo,
    ...(result?.column_list.map((_col, idx) => row[idx]) ?? []),
  ])

  const handleExport = async (scope: 'current' | 'all', format: 'csv' | 'excel') => {
    if (!resultRows.length) {
      msgApi.warning('当前没有可导出的查询结果')
      return
    }
    const dbPart = dbName || 'query_result'
    const exportLabel = scope === 'current' ? '当前页' : '全部结果'
    const exportFormat = format === 'csv' ? 'csv' : 'xlsx'

    if (scope === 'all' && resultRows.length > FRONTEND_EXPORT_THRESHOLD) {
      try {
        const { blob, contentDisposition } = await queryApi.exportResult(
          {
            instance_id: instanceId!,
            db_name: dbName,
            sql,
            limit_num: limitNum,
          },
          exportFormat,
        )
        triggerDownload(
          blob,
          extractFileName(contentDisposition, `${dbPart}_all_rows.${exportFormat}`),
        )
        msgApi.success(`已通过后端导出全部结果为 ${format === 'csv' ? 'CSV' : 'Excel'}`)
      } catch (e: any) {
        msgApi.error(e.response?.data?.msg || '导出失败')
      }
      return
    }

    const rows = scope === 'current' ? currentPageRows : resultRows
    const matrix = toExportMatrix(rows)
    const filePrefix = `${dbPart}_${scope === 'current' ? 'current_page' : 'all_rows'}`
    if (format === 'csv') {
      exportRowsAsCsv(exportHeaders, matrix, `${filePrefix}.csv`)
    } else {
      exportRowsAsExcel(exportHeaders, matrix, `${filePrefix}.xls`)
    }
    msgApi.success(`已导出${exportLabel}为${format === 'csv' ? ' CSV' : ' Excel'}`)
  }

  useEffect(() => {
    const updateResultHeight = () => {
      const viewportHeight = window.innerHeight
      const cardTop = resultCardRef.current?.getBoundingClientRect().top ?? 420
      const availableHeight = viewportHeight - cardTop - 88
      const nextHeight = Math.max(320, Math.min(760, availableHeight))
      setResultTableHeight(nextHeight)
    }

    updateResultHeight()
    window.addEventListener('resize', updateResultHeight)
    return () => window.removeEventListener('resize', updateResultHeight)
  }, [result, accessExplanation, executing])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {msgCtx}
      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}
        styles={{ body: { padding: '12px 16px' } }}>
        <Space wrap>
          <Select placeholder="选择实例" style={{ minWidth: 220, maxWidth: 360 }}
            popupMatchSelectWidth={false}
            onChange={(v) => { setInstanceId(v); setDbName('') }} showSearch optionFilterProp="label">
            {instanceData?.items?.map((inst: any) => (
              <Option key={inst.id} value={inst.id} label={inst.instance_name} style={{ whiteSpace: 'normal', wordBreak: 'break-all' }}>
                <Space>
                  <Tag color="blue" style={{ fontSize: 11 }}>{formatDbTypeLabel(inst.db_type)}</Tag>
                  {inst.instance_name}
                </Space>
              </Option>
            ))}
          </Select>
          <Select placeholder="选择数据库" style={{ minWidth: 180, maxWidth: 400 }} value={dbName || undefined}
            popupMatchSelectWidth={false}
            onChange={setDbName} loading={dbLoading} disabled={!instanceId} showSearch
            optionFilterProp="children">
            {(dbData?.items || []).map((d: any) => (
              <Option key={d.db_name} value={d.db_name} title={d.db_name}>
                {d.db_name}{!d.is_active && <Tag color="default" style={{marginLeft: 4, fontSize: 10}}>已禁用</Tag>}
              </Option>
            ))}
          </Select>
          <Space>
            <Text type="secondary" style={{ fontSize: 13 }}>行数上限</Text>
            <InputNumber min={1} max={100000} value={limitNum}
              onChange={(v) => v && setLimitNum(v)} style={{ width: 90 }} />
          </Space>
          <Button type="primary" icon={<PlayCircleOutlined />} loading={executing}
            onClick={handleExecute} disabled={!instanceId || !dbName}>
            执行
          </Button>
          <Button icon={<ClearOutlined />} onClick={() => { setSql(''); setResult(null) }}>清空</Button>
        </Space>
      </Card>

      <Card title="SQL 编辑器" style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}
        styles={{ body: { padding: 0 } }}>
        <Editor height="200px" defaultLanguage="sql" value={sql}
          onChange={(v) => setSql(v || '')} options={EDITOR_OPTIONS} />
      </Card>

      <div ref={resultCardRef}>
      <Card
        title={result ? (
          <Space>
            <HistoryOutlined /><span>查询结果</span>
            {result.error
              ? <Tag color="error">执行失败</Tag>
              : <><Tag color="success">{result.affected_rows} 行</Tag>
                  <Tag icon={<ClockCircleOutlined />}>{result.cost_time_ms}ms</Tag>
                  {result.is_masked && <Tag color="warning">已脱敏</Tag>}</>}
          </Space>
        ) : <Space><HistoryOutlined /><span>结果</span></Space>}
        extra={result && !result.error && resultRows.length ? (
          <Space size={8}>
            <Dropdown
              menu={{
                items: [
                  { key: 'current-csv', label: '导出当前页 CSV', onClick: () => handleExport('current', 'csv') },
                  { key: 'current-excel', label: '导出当前页 Excel', onClick: () => handleExport('current', 'excel') },
                ],
              }}
            >
              <Button icon={<DownloadOutlined />}>导出当前页</Button>
            </Dropdown>
            <Dropdown
              menu={{
                items: [
                  { key: 'all-csv', label: '导出全部结果 CSV', onClick: () => handleExport('all', 'csv') },
                  { key: 'all-excel', label: '导出全部结果 Excel', onClick: () => handleExport('all', 'excel') },
                ],
              }}
            >
              <Button icon={<DownloadOutlined />}>导出全部结果</Button>
            </Dropdown>
          </Space>
        ) : null}
        style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}
        styles={{ body: { padding: 0 } }}>
        {accessExplanation && !result && !executing && (
          <Alert
            type="warning"
            showIcon
            message="权限排查"
            description={`拒绝层级：${accessExplanation.layer}；原因：${accessExplanation.reason}`}
            style={{ margin: 16, borderRadius: 8 }}
          />
        )}
        {executing && <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spin tip="执行中..." /></div>}
        {result && !executing && (
          result.error
            ? <Alert type="error" showIcon message="执行失败" description={result.error} style={{ margin: 16, borderRadius: 8 }} />
            : <Table
                dataSource={resultRows}
                columns={resultColumns}
                size="small"
                scroll={{ x: 'max-content', y: resultTableHeight }}
                pagination={{
                  current: resultPage,
                  pageSize: resultPageSize,
                  total: resultRows.length,
                  showSizeChanger: true,
                  pageSizeOptions: ['20', '50', '100'],
                  onChange: (page, pageSize) => {
                    setResultPage(page)
                    setResultPageSize(pageSize)
                  },
                }} />
        )}
        {!result && !executing && !accessExplanation && (
          <div style={{ padding: 40, textAlign: 'center', color: '#AEAEB2' }}>选择实例和数据库，输入 SQL 后点击执行</div>
        )}
      </Card>
      </div>
    </div>
  )
}
