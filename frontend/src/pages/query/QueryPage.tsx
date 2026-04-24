import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import {
  Alert, Button, Dropdown, Empty, Input, InputNumber, List, Segmented, Select, Space, Table, Tabs, Tag, Typography, message,
} from 'antd'
import {
  AppstoreOutlined, ClearOutlined, ClockCircleOutlined, CopyOutlined, DatabaseOutlined, DownloadOutlined, HistoryOutlined, PlayCircleOutlined, TableOutlined,
} from '@ant-design/icons'
import Editor from '@monaco-editor/react'
import { useQuery } from '@tanstack/react-query'
import { instanceApi } from '@/api/instance'
import { queryApi, type QueryAccessExplanation, type QueryResult } from '@/api/query'
import PageHeader from '@/components/common/PageHeader'
import SectionCard from '@/components/common/SectionCard'
import SectionLoading from '@/components/common/SectionLoading'
import TableEmptyState from '@/components/common/TableEmptyState'
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

export default function QueryPage() {
  const [instanceId, setInstanceId] = useState<number | undefined>()
  const [dbName, setDbName] = useState<string>('')
  const [sql, setSql] = useState<string>('')
  const [tableKeyword, setTableKeyword] = useState('')
  const [selectedTable, setSelectedTable] = useState('')
  const [limitNum, setLimitNum] = useState<number>(100)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [accessExplanation, setAccessExplanation] = useState<QueryAccessExplanation | null>(null)
  const [executing, setExecuting] = useState(false)
  const [activeBottomTab, setActiveBottomTab] = useState<'ddlPreview' | 'result'>('ddlPreview')
  const [ddlViewMode, setDdlViewMode] = useState<'copyable' | 'raw'>('copyable')
  const [resultPage, setResultPage] = useState(1)
  const [resultPageSize, setResultPageSize] = useState(20)
  const [resultTableHeight, setResultTableHeight] = useState(460)
  const [editorPanelHeight, setEditorPanelHeight] = useState(520)
  const [isNarrowLayout, setIsNarrowLayout] = useState(false)
  const [msgApi, msgCtx] = message.useMessage()
  const editorSectionRef = useRef<HTMLDivElement | null>(null)
  const resultCardRef = useRef<HTMLDivElement | null>(null)
  const editorRef = useRef<any>(null)

  const { data: instanceData } = useQuery({
    queryKey: ['instances-for-query'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })

  const { data: dbData, isLoading: dbLoading } = useQuery({
    queryKey: ['registered-dbs', instanceId],
    queryFn: () => instanceApi.getDatabases(instanceId!),
    enabled: !!instanceId,
  })

  const { data: tableData, isLoading: tablesLoading, error: tablesError } = useQuery({
    queryKey: ['tables-for-query', instanceId, dbName],
    queryFn: () => instanceApi.getTables(instanceId!, dbName),
    enabled: !!instanceId && !!dbName,
  })

  const { data: tableDdlData, isLoading: ddlLoading, error: ddlError } = useQuery({
    queryKey: ['table-ddl-for-query', instanceId, dbName, selectedTable],
    queryFn: () => instanceApi.getTableDdl(instanceId!, dbName, selectedTable),
    enabled: !!instanceId && !!dbName && !!selectedTable,
  })

  const allTables = useMemo(() => tableData?.tables ?? [], [tableData?.tables])
  const filteredTables = useMemo(() => {
    const keyword = tableKeyword.trim().toLowerCase()
    if (!keyword) return allTables
    return allTables.filter((tableName) => tableName.toLowerCase().includes(keyword))
  }, [allTables, tableKeyword])
  const tableAccessDenied = (tablesError as any)?.response?.status === 403
  const ddlAccessDenied = (ddlError as any)?.response?.status === 403
  const displayedDdl = useMemo(() => {
    if (!tableDdlData) return ''
    if (ddlViewMode === 'raw') return tableDdlData.raw_ddl || tableDdlData.ddl || ''
    return tableDdlData.copyable_ddl || tableDdlData.ddl || ''
  }, [ddlViewMode, tableDdlData])

  const insertTextAtCursor = useCallback((text: string) => {
    const editor = editorRef.current
    if (!editor) {
      setSql((prev) => `${prev}${text}`)
      return
    }
    const selection = editor.getSelection()
    if (!selection) {
      editor.setValue(`${editor.getValue()}${text}`)
    } else {
      editor.executeEdits('table-browser', [{ range: selection, text, forceMoveMarkers: true }])
    }
    editor.focus()
    setSql(editor.getValue())
  }, [])

  const handleInsertTableName = useCallback(() => {
    if (!selectedTable) return
    insertTextAtCursor(selectedTable)
    msgApi.success(`已插入表名 ${selectedTable}`)
  }, [insertTextAtCursor, msgApi, selectedTable])

  const handleGenerateDdl = useCallback(() => {
    if (!selectedTable) {
      msgApi.warning('请先选择一张表')
      return
    }
    setActiveBottomTab('ddlPreview')
  }, [msgApi, selectedTable])

  const handleCopyDdl = useCallback(async () => {
    if (!displayedDdl) return
    await navigator.clipboard.writeText(displayedDdl)
    msgApi.success('建表语句已复制')
  }, [displayedDdl, msgApi])

  const handleExecute = useCallback(async () => {
    if (!instanceId) { msgApi.warning('请先选择实例'); return }
    if (!dbName) { msgApi.warning('请先选择数据库'); return }
    if (!sql.trim()) { msgApi.warning('SQL 不能为空'); return }

    setActiveBottomTab('result')
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

  const resultRows = useMemo(
    () => result?.rows.map((row, i) => ({
      key: i,
      __rowNo: i + 1,
      ...Object.fromEntries(row.map((v: any, j: number) => [j, v])),
    })) ?? [],
    [result?.rows],
  )

  const currentPageRows = useMemo(
    () => resultRows.slice((resultPage - 1) * resultPageSize, resultPage * resultPageSize),
    [resultRows, resultPage, resultPageSize],
  )

  const handleExport = async (scope: 'current' | 'all', format: 'csv' | 'excel') => {
    if (!resultRows.length) {
      msgApi.warning('当前没有可导出的查询结果')
      return
    }
    const dbPart = dbName || 'query_result'
    const exportLabel = scope === 'current' ? '当前页' : '全部结果'
    const exportFormat = format === 'csv' ? 'csv' : 'xlsx'

    try {
      const isCurrentPage = scope === 'current'
      const { blob, contentDisposition } = await queryApi.exportResult(
        {
          instance_id: instanceId!,
          db_name: dbName,
          sql,
          limit_num: isCurrentPage ? resultPage * resultPageSize : limitNum,
          export_offset: isCurrentPage ? (resultPage - 1) * resultPageSize : undefined,
          export_limit: isCurrentPage ? resultPageSize : undefined,
        },
        exportFormat,
      )
      triggerDownload(
        blob,
        extractFileName(
          contentDisposition,
          `${dbPart}_${scope === 'current' ? 'current_page' : 'all_rows'}.${exportFormat}`,
        ),
      )
      msgApi.success(`已通过后端导出${exportLabel}为${format === 'csv' ? ' CSV' : ' Excel'}`)
    } catch (e: any) {
      msgApi.error(e.response?.data?.msg || e.response?.data?.detail || '导出失败')
    }
  }

  useEffect(() => {
    const updateEditorPanelHeight = () => {
      const viewportHeight = window.innerHeight
      const sectionTop = editorSectionRef.current?.getBoundingClientRect().top ?? 240
      const availableHeight = viewportHeight - sectionTop - 240
      const nextHeight = Math.max(420, Math.min(600, availableHeight))
      setEditorPanelHeight(nextHeight)
    }

    updateEditorPanelHeight()
    window.addEventListener('resize', updateEditorPanelHeight)
    return () => window.removeEventListener('resize', updateEditorPanelHeight)
  }, [])

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

  useEffect(() => {
    const updateLayout = () => setIsNarrowLayout(window.innerWidth < 1200)
    updateLayout()
    window.addEventListener('resize', updateLayout)
    return () => window.removeEventListener('resize', updateLayout)
  }, [])

  useEffect(() => {
    setDbName('')
    setSelectedTable('')
    setTableKeyword('')
  }, [instanceId])

  useEffect(() => {
    setSelectedTable('')
    setTableKeyword('')
  }, [dbName])

  useEffect(() => {
    if (selectedTable) {
      setActiveBottomTab('ddlPreview')
      setDdlViewMode('copyable')
    }
  }, [selectedTable])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {msgCtx}
      <PageHeader
        title="在线查询"
        meta="选择实例和数据库后执行 SQL，支持结果导出、权限排查和脱敏提示"
        marginBottom={4}
      />

      <SectionCard bodyPadding="12px 16px">
        <Space wrap>
          <Select placeholder="选择实例" style={{ minWidth: 220, maxWidth: 360 }}
            value={instanceId}
            popupMatchSelectWidth={false}
            onChange={setInstanceId} showSearch optionFilterProp="label">
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
            {(dbData?.databases || []).map((d: any) => (
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
      </SectionCard>

      <div ref={editorSectionRef}>
      <SectionCard title="查询工作台" bodyPadding={0}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: isNarrowLayout ? 'minmax(0, 1fr)' : '320px minmax(0, 1fr)',
          gap: 0,
        }}
        >
          <div style={{
            borderRight: isNarrowLayout ? 'none' : '1px solid rgba(5, 5, 5, 0.06)',
            display: 'flex',
            flexDirection: 'column',
            height: editorPanelHeight,
            minHeight: 320,
            overflow: 'hidden',
            background: '#fbfcfe',
          }}
          >
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
              padding: '14px 16px 12px',
              borderBottom: '1px solid rgba(5, 5, 5, 0.06)',
              background: 'linear-gradient(180deg, rgba(21, 88, 168, 0.04) 0%, rgba(21, 88, 168, 0.01) 100%)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <Space size={8}>
                  <AppstoreOutlined style={{ color: '#1558A8' }} />
                  <Text strong style={{ fontSize: 15 }}>表浏览器</Text>
                  {allTables.length > 0 && <Tag>{allTables.length}</Tag>}
                </Space>
                <Text type="secondary" style={{ fontSize: 12 }}>仅浏览表名</Text>
              </div>
              <Space size={8} wrap>
                <Button size="small" onClick={handleInsertTableName} disabled={!selectedTable}>
                  插入表名
                </Button>
                <Button
                  size="small"
                  type="primary"
                  onClick={handleGenerateDdl}
                  disabled={!selectedTable}
                  style={{ minWidth: 88, whiteSpace: 'nowrap' }}
                >
                  生成 DDL
                </Button>
              </Space>
            </div>
            <div style={{ padding: 12, borderBottom: '1px solid rgba(5, 5, 5, 0.06)' }}>
              <Input
                allowClear
                placeholder="搜索当前数据库下的表"
                value={tableKeyword}
                onChange={(e) => setTableKeyword(e.target.value)}
                disabled={!dbName || tableAccessDenied}
              />
            </div>
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
              {!dbName ? (
                <div style={{ padding: 24, height: '100%', boxSizing: 'border-box' }}>
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="先选择数据库" />
                </div>
              ) : tableAccessDenied ? (
                <div style={{ padding: 24, height: '100%', boxSizing: 'border-box' }}>
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="当前范围暂无表结构查看权限"
                  />
                </div>
              ) : (
                <div style={{ height: '100%', overflow: 'auto', padding: 8 }}>
                  <List<string>
                    loading={tablesLoading}
                    dataSource={filteredTables}
                    locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前数据库下没有可见表" /> }}
                    renderItem={(tableName) => (
                      <List.Item
                        onClick={() => setSelectedTable(tableName)}
                        style={{
                          cursor: 'pointer',
                          marginBottom: 8,
                          padding: '10px 12px',
                          borderRadius: 10,
                          border: selectedTable === tableName
                            ? '1px solid rgba(21, 88, 168, 0.28)'
                            : '1px solid rgba(0,0,0,0.06)',
                          background: selectedTable === tableName
                            ? 'linear-gradient(180deg, rgba(21, 88, 168, 0.10) 0%, rgba(21, 88, 168, 0.04) 100%)'
                            : '#FFFFFF',
                          boxShadow: selectedTable === tableName
                            ? '0 6px 18px rgba(21, 88, 168, 0.08)'
                            : 'none',
                          transition: 'all 0.18s ease',
                        }}
                      >
                        <Space size={8}>
                          <div style={{
                            width: 24,
                            height: 24,
                            borderRadius: 8,
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            background: selectedTable === tableName ? 'rgba(21, 88, 168, 0.12)' : '#F5F7FA',
                            color: selectedTable === tableName ? '#1558A8' : '#8c8c8c',
                            flexShrink: 0,
                          }}
                          >
                            <TableOutlined />
                          </div>
                          <Text
                            style={{
                              maxWidth: 210,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              color: selectedTable === tableName ? '#1558A8' : '#1F2329',
                              fontWeight: selectedTable === tableName ? 600 : 400,
                            }}
                          >
                            {tableName}
                          </Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                </div>
              )}
            </div>
          </div>
          <div style={{ minHeight: 320, background: '#ffffff' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '12px 16px 10px',
              borderBottom: '1px solid rgba(5, 5, 5, 0.06)',
              background: '#ffffff',
            }}
            >
              <Space size={8}>
                <Text strong style={{ fontSize: 15 }}>SQL 编辑器</Text>
                {selectedTable ? <Tag color="blue">{selectedTable}</Tag> : null}
              </Space>
              <Text type="secondary" style={{ fontSize: 12 }}>
                在这里编写和执行查询语句
              </Text>
            </div>
            <Editor
              height={`${editorPanelHeight}px`}
              defaultLanguage="sql"
              value={sql}
              onChange={(v) => setSql(v || '')}
              onMount={(editor) => { editorRef.current = editor }}
              options={EDITOR_OPTIONS}
            />
          </div>
        </div>
      </SectionCard>
      </div>

      <div ref={resultCardRef}>
      <SectionCard
        bodyPadding={0}
        marginBottom={0}
      >
        <Tabs
          activeKey={activeBottomTab}
          onChange={(key) => setActiveBottomTab(key as 'ddlPreview' | 'result')}
          style={{ padding: '0 16px 16px' }}
          tabBarStyle={{
            marginBottom: 12,
            paddingTop: 4,
            background: 'linear-gradient(180deg, rgba(21, 88, 168, 0.04) 0%, rgba(21, 88, 168, 0.01) 100%)',
            border: '1px solid rgba(21, 88, 168, 0.08)',
            borderRadius: 12,
            paddingLeft: 12,
            paddingRight: 12,
          }}
          items={[
            {
              key: 'ddlPreview',
              label: (
                <Space size={6}>
                  <DatabaseOutlined />
                  <span>DDL 预览</span>
                </Space>
              ),
              children: (
                <div style={{
                  minHeight: resultTableHeight,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 12,
                }}
                >
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 12,
                    paddingTop: 4,
                  }}
                  >
                    <Space size={8} wrap>
                      <DatabaseOutlined style={{ color: '#1558A8' }} />
                      <Text strong>{selectedTable || '未选择表'}</Text>
                      {tableDdlData?.source === 'generated' && <Tag color="gold">生成DDL</Tag>}
                    </Space>
                    <Space size={8} wrap>
                      <Segmented<'copyable' | 'raw'>
                        size="small"
                        value={ddlViewMode}
                        onChange={(value) => setDdlViewMode(value)}
                        options={[
                          { label: '可复制 DDL', value: 'copyable' },
                          { label: '原始 DDL', value: 'raw' },
                        ]}
                      />
                      {displayedDdl && (
                        <Button size="small" icon={<CopyOutlined />} onClick={handleCopyDdl}>
                          复制 DDL
                        </Button>
                      )}
                    </Space>
                  </div>
                  <div style={{
                    border: '1px solid rgba(0,0,0,0.08)',
                    borderRadius: 12,
                    background: '#FFFFFF',
                    padding: 12,
                    minHeight: 0,
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                  }}
                  >
                    {!selectedTable ? (
                      <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="从左侧选择一张表，然后点击生成 DDL 或直接查看预览" />
                      </div>
                    ) : ddlAccessDenied ? (
                      <Alert type="warning" showIcon message="当前表暂无结构查看权限" />
                    ) : ddlLoading ? (
                      <SectionLoading text="正在加载建表语句..." compact />
                    ) : (
                      <pre style={{
                        margin: 0,
                        padding: '14px 16px',
                        background: '#f6f8fb',
                        color: '#1f2937',
                        border: '1px solid rgba(21, 88, 168, 0.10)',
                        borderRadius: 10,
                        fontSize: 12,
                        lineHeight: 1.7,
                        fontFamily: 'var(--font-mono)',
                        whiteSpace: 'pre',
                        minHeight: 0,
                        height: '100%',
                        overflow: 'auto',
                        boxSizing: 'border-box',
                        flex: 1,
                      }}
                      >
                        {displayedDdl || '-- 暂无可展示的建表语句'}
                      </pre>
                    )}
                  </div>
                </div>
              ),
            },
            {
              key: 'result',
              label: result ? (
                <Space size={6}>
                  <HistoryOutlined />
                  <span>结果</span>
                  {result.error
                    ? <Tag color="error">执行失败</Tag>
                    : <>
                        <Tag color="success">{result.affected_rows} 行</Tag>
                        <Tag icon={<ClockCircleOutlined />}>{result.cost_time_ms}ms</Tag>
                        {result.is_masked && <Tag color="warning">已脱敏</Tag>}
                      </>}
                </Space>
              ) : (
                <Space size={6}>
                  <HistoryOutlined />
                  <span>结果</span>
                </Space>
              ),
              children: (
                <>
                  {result && !result.error && resultRows.length ? (
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
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
                    </div>
                  ) : null}
                  {accessExplanation && !result && !executing && (
                    <Alert
                      type="warning"
                      showIcon
                      message="权限排查"
                      description={`拒绝层级：${accessExplanation.layer}；原因：${accessExplanation.reason}`}
                      style={{ marginBottom: 16, borderRadius: 8 }}
                    />
                  )}
                  {executing && <SectionLoading text="执行中..." compact />}
                  {result && !executing && (
                    result.error
                      ? <Alert type="error" showIcon message="执行失败" description={result.error} style={{ marginBottom: 16, borderRadius: 8 }} />
                      : <Table
                          dataSource={currentPageRows}
                          columns={resultColumns}
                          size="small"
                          locale={{ emptyText: <TableEmptyState title="暂无查询结果" /> }}
                          scroll={{ x: 'max-content', y: resultTableHeight - 56 }}
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
                    <div style={{ minHeight: resultTableHeight, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <TableEmptyState title="选择实例和数据库，输入 SQL 后点击执行" />
                    </div>
                  )}
                </>
              ),
            },
          ]}
        />
      </SectionCard>
      </div>
    </div>
  )
}
