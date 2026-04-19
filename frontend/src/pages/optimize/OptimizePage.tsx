import { useState } from 'react'
import { Button, Select, Space, Table, Tag, message } from 'antd'
import { BulbOutlined, PlayCircleOutlined } from '@ant-design/icons'
import Editor from '@monaco-editor/react'
import { useQuery } from '@tanstack/react-query'
import { instanceApi } from '@/api/instance'
import apiClient from '@/api/client'
import PageHeader from '@/components/common/PageHeader'
import SectionCard from '@/components/common/SectionCard'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Option } = Select

const LEVEL_COLOR: Record<string, string> = { error: 'error', warning: 'warning', info: 'processing', ok: 'success' }

export default function OptimizePage() {
  const [instanceId, setInstanceId] = useState<number | undefined>()
  const [dbName, setDbName] = useState<string>('')
  const [sql, setSql] = useState<string>('SELECT * FROM sql_users WHERE 1=1')
  const [advices, setAdvices] = useState<any[]>([])
  const [explainResult, setExplainResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [msgApi, msgCtx] = message.useMessage()

  const { data: instanceData } = useQuery({ queryKey: ['instances-optimize'], queryFn: () => instanceApi.list({ page_size: 200 }) })
  const { data: dbData } = useQuery({ queryKey: ['registered-dbs-optimize', instanceId], queryFn: () => instanceApi.listRegisteredDbs(instanceId!), enabled: !!instanceId })

  const handleAdvice = async () => {
    if (!instanceId) { msgApi.warning('请选择实例'); return }
    setLoading(true)
    try {
      const r = await apiClient.post('/optimize/advice/', { instance_id: instanceId, db_name: dbName, sql })
      setAdvices(r.data.advices || [])
    } catch (e: any) { msgApi.error(e.response?.data?.msg || '分析失败') }
    finally { setLoading(false) }
  }

  const handleExplain = async () => {
    if (!instanceId || !dbName) { msgApi.warning('请选择实例和数据库'); return }
    setLoading(true)
    try {
      const r = await apiClient.post('/optimize/explain/', { instance_id: instanceId, db_name: dbName, sql })
      setExplainResult(r.data)
    } catch (e: any) { msgApi.error(e.response?.data?.detail || 'EXPLAIN 失败') }
    finally { setLoading(false) }
  }

  const adviceCols = [
    { title: '级别', dataIndex: 'level', width: 90, render: (v: string) => <Tag color={LEVEL_COLOR[v]}>{v.toUpperCase()}</Tag> },
    { title: '规则', dataIndex: 'rule', width: 180 },
    { title: '建议', dataIndex: 'message', ellipsis: false },
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="SQL 优化"
        meta="分析 SQL 风险并生成优化建议与 EXPLAIN 结果"
        marginBottom={20}
      />
      <SectionCard bodyPadding="12px 16px">
        <Space wrap>
          <Select placeholder="选择实例" style={{ minWidth: 220, maxWidth: 360 }} onChange={(v) => { setInstanceId(v); setDbName('') }} showSearch optionFilterProp="label" popupMatchSelectWidth={false}>
            {instanceData?.items?.map((i: any) => <Option key={i.id} value={i.id} label={i.instance_name} title={i.instance_name}><Tag color="blue">{formatDbTypeLabel(i.db_type)}</Tag> {i.instance_name}</Option>)}
          </Select>
          <Select placeholder="选择数据库" style={{ minWidth: 160, maxWidth: 360 }} value={dbName || undefined} onChange={setDbName} disabled={!instanceId} showSearch popupMatchSelectWidth={false} optionFilterProp="children">
            {(dbData?.items || []).map((d: any) => (
              <Option key={d.db_name} value={d.db_name} title={d.db_name}>
                {d.db_name}{!d.is_active && <Tag color="default" style={{marginLeft: 4, fontSize: 10}}>已禁用</Tag>}
              </Option>
            ))}
          </Select>
          <Button icon={<BulbOutlined />} onClick={handleAdvice} loading={loading} disabled={!instanceId}>优化建议</Button>
          <Button icon={<PlayCircleOutlined />} onClick={handleExplain} loading={loading} disabled={!instanceId || !dbName}>EXPLAIN 分析</Button>
        </Space>
      </SectionCard>
      <SectionCard title="SQL 输入" bodyPadding={0}>
        <Editor height="180px" defaultLanguage="sql" value={sql} onChange={(v) => setSql(v || '')}
          options={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 13, minimap: { enabled: false }, padding: { top: 12 } }} />
      </SectionCard>
      {advices.length > 0 && (
        <SectionCard title="优化建议" bodyPadding={0}>
          <Table
            dataSource={advices.map((r, i) => ({ key: i, ...r }))}
            columns={adviceCols}
            size="small"
            tableLayout="fixed"
            scroll={{ x: 860 }}
            pagination={false}
            locale={{ emptyText: '暂无优化建议' }}
          />
        </SectionCard>
      )}
      {explainResult && (
        <SectionCard title={`EXPLAIN 结果（${formatDbTypeLabel(explainResult.db_type)}）`} bodyPadding={0} marginBottom={0}>
          <Table
            dataSource={(explainResult.rows || []).map((r: any[], i: number) => ({ key: i, ...Object.fromEntries((explainResult.column_list || []).map((c: string, j: number) => [c, r[j]])) }))}
            columns={(explainResult.column_list || []).map((c: string) => ({ title: c, dataIndex: c, key: c, ellipsis: true, width: 140 }))}
            size="small" tableLayout="fixed" scroll={{ x: 'max-content' }} pagination={false}
            locale={{ emptyText: '暂无 EXPLAIN 结果' }} />
        </SectionCard>
      )}
    </div>
  )
}
