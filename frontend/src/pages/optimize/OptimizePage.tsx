import { useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Descriptions,
  Empty,
  Progress,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tree,
  Typography,
  message,
} from 'antd'
import {
  BulbOutlined,
  CopyOutlined,
  FileSearchOutlined,
  FormOutlined,
  HistoryOutlined,
} from '@ant-design/icons'
import Editor from '@monaco-editor/react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { instanceApi } from '@/api/instance'
import { optimizeApi, OptimizeAnalyzeResponse, OptimizeFinding, OptimizeRecommendation } from '@/api/optimize'
import { slowlogApi } from '@/api/slowlog'
import PageHeader from '@/components/common/PageHeader'
import SectionCard from '@/components/common/SectionCard'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Option } = Select
const { Paragraph, Text } = Typography

const SUPPORT_COLOR: Record<string, string> = {
  full: 'green',
  partial: 'gold',
  static_only: 'blue',
  unsupported: 'default',
}

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'error',
  warning: 'warning',
  info: 'processing',
  ok: 'success',
}

const SOURCE_LABEL: Record<string, string> = {
  manual: '手动 SQL',
  slowlog: '慢日志',
  fingerprint: 'SQL 指纹',
}

function getRecordValue(record: Record<string, any>, keys: string[]) {
  for (const key of keys) {
    if (record[key] !== undefined && record[key] !== null && record[key] !== '') return record[key]
    const matched = Object.keys(record).find(k => k.toLowerCase() === key.toLowerCase())
    if (matched && record[matched] !== undefined && record[matched] !== null && record[matched] !== '') return record[matched]
  }
  return undefined
}

function formatCellValue(value: any) {
  if (value === undefined || value === null || value === '') return '-'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function valuePreview(value: any) {
  if (value === undefined) return 'undefined'
  if (value === null) return 'null'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return `Array(${value.length})`
  return `Object(${Object.keys(value || {}).length})`
}

function buildTreeData(value: any, key = 'root', label = 'root'): any[] {
  if (value === null || typeof value !== 'object') {
    return [{
      key,
      title: (
        <Space size={6}>
          <Text code>{label}</Text>
          <Text>{valuePreview(value)}</Text>
        </Space>
      ),
    }]
  }

  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index), item])
    : Object.entries(value)

  return [{
    key,
    title: (
      <Space size={6}>
        <Text code>{label}</Text>
        <Text type="secondary">{valuePreview(value)}</Text>
      </Space>
    ),
    children: entries.slice(0, 200).map(([childKey, childValue]) => {
      const childPath = `${key}.${childKey}`
      if (childValue !== null && typeof childValue === 'object') {
        return buildTreeData(childValue, childPath, childKey)[0]
      }
      return {
        key: childPath,
        title: (
          <Space size={6}>
            <Text code>{childKey}</Text>
            <Text copyable={typeof childValue === 'string'}>{formatCellValue(childValue)}</Text>
          </Space>
        ),
      }
    }),
  }]
}

function buildWorkOrderText(result: OptimizeAnalyzeResponse) {
  const recs = result.recommendations
    .map(item => `${item.priority}. ${item.title}\n操作：${item.action}\n原因：${item.reason || '-'}\n风险：${item.risk || '-'}`)
    .join('\n\n')
  return `SQL 优化诊断\n\n风险评分：${result.risk_score}\n诊断结论：${result.summary}\n\nSQL：\n${result.sql}\n\n优化建议：\n${recs || '-'}`
}

export default function OptimizePage() {
  const [instanceId, setInstanceId] = useState<number | undefined>()
  const [dbName, setDbName] = useState<string>('')
  const [sql, setSql] = useState<string>('SELECT * FROM sql_users WHERE 1=1')
  const [logId, setLogId] = useState<number | undefined>()
  const [fingerprint, setFingerprint] = useState<string | undefined>()
  const [result, setResult] = useState<OptimizeAnalyzeResponse | null>(null)
  const [msgApi, msgCtx] = message.useMessage()

  const { data: instanceData } = useQuery({
    queryKey: ['instances-optimize-v2'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })
  const { data: dbData } = useQuery({
    queryKey: ['registered-dbs-optimize-v2', instanceId],
    queryFn: () => instanceApi.listRegisteredDbs(instanceId!),
    enabled: !!instanceId,
  })
  const { data: slowLogs } = useQuery({
    queryKey: ['optimize-slow-logs', instanceId],
    queryFn: () => slowlogApi.logs({ instance_id: instanceId, page: 1, page_size: 20 }),
    enabled: !!instanceId,
  })
  const { data: fingerprints } = useQuery({
    queryKey: ['optimize-fingerprints', instanceId],
    queryFn: () => slowlogApi.fingerprints({ instance_id: instanceId, limit: 30 }),
    enabled: !!instanceId,
  })

  const selectedInstance = useMemo(
    () => instanceData?.items?.find((item: any) => item.id === instanceId),
    [instanceData?.items, instanceId],
  )

  const analyzeMut = useMutation<OptimizeAnalyzeResponse, any>({
    mutationFn: async () => {
      if (logId) return optimizeApi.analyze({ log_id: logId })
      if (fingerprint) return optimizeApi.analyze({ fingerprint, instance_id: instanceId })
      if (!instanceId) throw new Error('请选择实例')
      return optimizeApi.analyze({ instance_id: instanceId, db_name: dbName, sql })
    },
    onSuccess: data => {
      setResult(data)
      if (data.msg) msgApi.info(data.msg)
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.message || '诊断失败'),
  })

  const findingCols = [
    {
      title: '级别',
      dataIndex: 'severity',
      width: 100,
      render: (v: string) => <Tag color={SEVERITY_COLOR[v]}>{v.toUpperCase()}</Tag>,
    },
    { title: '问题', dataIndex: 'title', width: 180 },
    { title: '说明', dataIndex: 'detail' },
    { title: '证据', dataIndex: 'evidence', width: 220, ellipsis: true },
    {
      title: '置信度',
      dataIndex: 'confidence',
      width: 100,
      render: (v: number) => `${Math.round((v || 0) * 100)}%`,
    },
  ]

  const recCols = [
    { title: '优先级', dataIndex: 'priority', width: 80 },
    { title: '类型', dataIndex: 'type', width: 110, render: (v: string) => <Tag>{v}</Tag> },
    { title: '建议', dataIndex: 'title', width: 180 },
    { title: '操作', dataIndex: 'action' },
    { title: '原因', dataIndex: 'reason' },
    { title: '风险', dataIndex: 'risk' },
  ]

  const indexCols = [
    {
      title: '表名',
      dataIndex: 'table_name',
      width: 190,
      render: (_: any, row: Record<string, any>) => <Text code>{formatCellValue(getRecordValue(row, ['table_name', 'TABLE_NAME']))}</Text>,
    },
    {
      title: '索引名',
      dataIndex: 'index_name',
      width: 220,
      render: (_: any, row: Record<string, any>) => <Text strong>{formatCellValue(getRecordValue(row, ['index_name', 'INDEX_NAME']))}</Text>,
    },
    {
      title: '类型',
      dataIndex: 'index_type',
      width: 150,
      render: (_: any, row: Record<string, any>) => <Tag>{formatCellValue(getRecordValue(row, ['index_type', 'INDEX_TYPE']))}</Tag>,
    },
    {
      title: '列',
      dataIndex: 'column_names',
      render: (_: any, row: Record<string, any>) => formatCellValue(getRecordValue(row, ['column_names', 'COLUMN_NAMES'])),
    },
    {
      title: '联合索引',
      dataIndex: 'is_composite',
      width: 110,
      render: (_: any, row: Record<string, any>) => {
        const value = formatCellValue(getRecordValue(row, ['is_composite', 'IS_COMPOSITE']))
        return <Tag color={value === 'YES' || value === '是' ? 'blue' : 'default'}>{value}</Tag>
      },
    },
    {
      title: '备注',
      dataIndex: 'index_comment',
      width: 180,
      ellipsis: true,
      render: (_: any, row: Record<string, any>) => formatCellValue(getRecordValue(row, ['index_comment', 'INDEX_COMMENT', 'index_definition'])),
    },
  ]

  const statisticsCols = [
    { title: '表名', dataIndex: 'table_name', width: 180, render: (v: string) => v ? <Text code>{v}</Text> : '-' },
    { title: '类型', dataIndex: 'kind', width: 160, render: (v: string) => <Tag>{v || 'statistics'}</Tag> },
    { title: '信息', dataIndex: 'message', render: (_: any, row: Record<string, any>) => formatCellValue(row.message || row.detail || row.value || row) },
  ]

  const rawPlanTabs = result ? [
    {
      key: 'tree',
      label: '结构化浏览',
      children: result.raw
        ? (
          <div style={{ maxHeight: 420, overflow: 'auto', padding: 16 }}>
            <Tree
              blockNode
              defaultExpandAll
              treeData={buildTreeData(result.raw)}
            />
          </div>
        )
        : <Empty description="暂无原始计划" style={{ padding: 32 }} />,
    },
    {
      key: 'json',
      label: 'JSON 原文',
      children: (
        <Paragraph code copyable style={{ whiteSpace: 'pre-wrap', maxHeight: 420, overflow: 'auto', margin: 0, padding: 16 }}>
          {JSON.stringify(result.raw ?? {}, null, 2)}
        </Paragraph>
      ),
    },
  ] : []

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="SQL 优化"
        meta="慢 SQL 诊断、执行计划分析与结构化优化建议"
        marginBottom={20}
      />

      <SectionCard bodyPadding="12px 16px">
        <Space wrap>
          <Select
            placeholder="选择实例"
            style={{ minWidth: 220, maxWidth: 360 }}
            value={instanceId}
            onChange={(v) => { setInstanceId(v); setDbName(''); setLogId(undefined); setFingerprint(undefined) }}
            showSearch
            optionFilterProp="label"
            popupMatchSelectWidth={false}
          >
            {instanceData?.items?.map((i: any) => (
              <Option key={i.id} value={i.id} label={i.instance_name} title={i.instance_name}>
                <Tag color="blue">{formatDbTypeLabel(i.db_type)}</Tag> {i.instance_name}
              </Option>
            ))}
          </Select>
          <Select
            placeholder="选择数据库"
            style={{ minWidth: 160, maxWidth: 360 }}
            value={dbName || undefined}
            onChange={setDbName}
            disabled={!instanceId || !!logId || !!fingerprint}
            showSearch
            popupMatchSelectWidth={false}
            optionFilterProp="children"
          >
            {(dbData?.items || []).map((d: any) => (
              <Option key={d.db_name} value={d.db_name} title={d.db_name}>
                {d.db_name}{!d.is_active && <Tag color="default" style={{ marginLeft: 4, fontSize: 10 }}>已禁用</Tag>}
              </Option>
            ))}
          </Select>
          <Select
            allowClear
            placeholder="从慢日志选择"
            style={{ minWidth: 260, maxWidth: 420 }}
            value={logId}
            onChange={(v) => { setLogId(v); setFingerprint(undefined) }}
            disabled={!instanceId}
            popupMatchSelectWidth={false}
          >
            {(slowLogs?.items || []).map(item => (
              <Option key={item.id} value={item.id} title={item.sql_text}>
                <HistoryOutlined /> #{item.id} {item.duration_ms}ms {item.db_name || '-'}
              </Option>
            ))}
          </Select>
          <Select
            allowClear
            placeholder="从 SQL 指纹选择"
            style={{ minWidth: 260, maxWidth: 420 }}
            value={fingerprint}
            onChange={(v) => { setFingerprint(v); setLogId(undefined) }}
            disabled={!instanceId}
            popupMatchSelectWidth={false}
          >
            {(fingerprints?.items || []).map(item => (
              <Option key={item.sql_fingerprint} value={item.sql_fingerprint} title={item.sample_sql}>
                <FileSearchOutlined /> {item.count}次 P95 {item.p95_duration_ms}ms
              </Option>
            ))}
          </Select>
          <Button
            type="primary"
            icon={<BulbOutlined />}
            onClick={() => analyzeMut.mutate()}
            loading={analyzeMut.isPending}
            disabled={!instanceId && !logId && !fingerprint}
          >
            开始诊断
          </Button>
        </Space>
      </SectionCard>

      {!logId && !fingerprint && (
        <SectionCard title="SQL 输入" bodyPadding={0}>
          <Editor
            height="190px"
            defaultLanguage="sql"
            value={sql}
            onChange={(v) => setSql(v || '')}
            options={{
              fontFamily: '"JetBrains Mono", monospace',
              fontSize: 13,
              minimap: { enabled: false },
              padding: { top: 12 },
            }}
          />
        </SectionCard>
      )}

      {!result && (
        <SectionCard bodyPadding="28px 16px" marginBottom={0}>
          <Empty description="选择实例后可手动输入 SQL，或从慢日志和 SQL 指纹发起诊断" />
        </SectionCard>
      )}

      {result && (
        <>
          <SectionCard title="诊断结论" bodyPadding="16px">
            {!result.supported && <Alert type="info" showIcon message={result.msg || '当前引擎不进入 SQL 优化主链路'} style={{ marginBottom: 12 }} />}
            <Space align="start" size={20} wrap>
              <Progress
                type="dashboard"
                percent={result.risk_score}
                size={118}
                status={result.risk_score >= 70 ? 'exception' : result.risk_score >= 35 ? 'normal' : 'success'}
              />
              <Space direction="vertical" size={10} style={{ maxWidth: 860 }}>
                <Space wrap>
                  <Tag color="blue">{formatDbTypeLabel(result.engine || selectedInstance?.db_type)}</Tag>
                  <Tag color={SUPPORT_COLOR[result.support_level]}>{result.support_level}</Tag>
                  <Tag>{SOURCE_LABEL[result.source]}</Tag>
                </Space>
                <Text strong>{result.summary}</Text>
                <Space wrap>
                  <Button
                    icon={<CopyOutlined />}
                    onClick={() => navigator.clipboard.writeText(buildWorkOrderText(result)).then(() => msgApi.success('已复制诊断内容'))}
                  >
                    复制建议
                  </Button>
                  <Button
                    icon={<FormOutlined />}
                    onClick={() => navigator.clipboard.writeText(buildWorkOrderText(result)).then(() => msgApi.success('已复制为工单描述'))}
                  >
                    复制为工单描述
                  </Button>
                </Space>
              </Space>
            </Space>
          </SectionCard>

          <SectionCard title="关键问题" bodyPadding={0}>
            <Table<OptimizeFinding>
              dataSource={result.findings.map((item, i) => ({ ...item, key: `${item.code}-${i}` }))}
              columns={findingCols}
              size="small"
              tableLayout="fixed"
              scroll={{ x: 920 }}
              pagination={false}
            />
          </SectionCard>

          <SectionCard title="优化建议" bodyPadding={0}>
            <Table<OptimizeRecommendation>
              dataSource={result.recommendations.map((item, i) => ({ ...item, key: `${item.priority}-${i}` }))}
              columns={recCols}
              size="small"
              tableLayout="fixed"
              scroll={{ x: 1200 }}
              pagination={false}
            />
          </SectionCard>

          <SectionCard title="执行计划摘要" bodyPadding="12px 16px">
            <Descriptions size="small" column={{ xs: 1, sm: 2, md: 3 }}>
              <Descriptions.Item label="格式">{result.plan?.format || '-'}</Descriptions.Item>
              <Descriptions.Item label="全表扫描">{result.plan?.summary?.full_scan ? '是' : '否'}</Descriptions.Item>
              <Descriptions.Item label="估算行数">{result.plan?.summary?.rows_estimate ?? 0}</Descriptions.Item>
              <Descriptions.Item label="最大成本">{result.plan?.summary?.max_cost ?? 0}</Descriptions.Item>
              <Descriptions.Item label="排序">{result.plan?.summary?.sort ? '是' : '否'}</Descriptions.Item>
              <Descriptions.Item label="临时表">{result.plan?.summary?.temporary ? '是' : '否'}</Descriptions.Item>
            </Descriptions>
          </SectionCard>

          <SectionCard title="元数据线索" bodyPadding="12px 16px">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Descriptions size="small" column={{ xs: 1, sm: 2, md: 4 }}>
                <Descriptions.Item label="涉及表">
                  <Space wrap size={[4, 4]}>
                    {(result.metadata?.tables || []).map(table => <Tag key={table}>{table}</Tag>)}
                    {!(result.metadata?.tables || []).length && <Text type="secondary">未识别到表名</Text>}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="索引数">{result.metadata?.indexes?.length || 0}</Descriptions.Item>
                <Descriptions.Item label="统计信息">{result.metadata?.statistics?.length || 0}</Descriptions.Item>
                <Descriptions.Item label="慢日志">{Object.keys(result.metadata?.slowlog || {}).length ? '已关联' : '未关联'}</Descriptions.Item>
              </Descriptions>

              <Table
                title={() => '索引信息'}
                dataSource={(result.metadata?.indexes || []).map((item, i) => ({ ...item, key: `${getRecordValue(item, ['table_name']) || 'table'}-${getRecordValue(item, ['index_name']) || i}` }))}
                columns={indexCols}
                size="small"
                tableLayout="fixed"
                scroll={{ x: 1040 }}
                pagination={false}
                locale={{ emptyText: '暂无索引元数据' }}
              />

              <Table
                title={() => '统计与采集提示'}
                dataSource={(result.metadata?.statistics || []).map((item, i) => ({ ...item, key: i }))}
                columns={statisticsCols}
                size="small"
                tableLayout="fixed"
                pagination={false}
                locale={{ emptyText: '暂无统计信息提示' }}
              />

              {!!Object.keys(result.metadata?.slowlog || {}).length && (
                <Descriptions title="慢日志画像" size="small" bordered column={{ xs: 1, sm: 2, md: 4 }}>
                  <Descriptions.Item label="来源">{formatCellValue(result.metadata.slowlog.source)}</Descriptions.Item>
                  <Descriptions.Item label="耗时">{formatCellValue(result.metadata.slowlog.duration_ms)} ms</Descriptions.Item>
                  <Descriptions.Item label="扫描行数">{formatCellValue(result.metadata.slowlog.rows_examined)}</Descriptions.Item>
                  <Descriptions.Item label="返回行数">{formatCellValue(result.metadata.slowlog.rows_sent)}</Descriptions.Item>
                  <Descriptions.Item label="发生时间" span={2}>{formatCellValue(result.metadata.slowlog.occurred_at)}</Descriptions.Item>
                  <Descriptions.Item label="标签" span={2}>
                    <Space wrap size={[4, 4]}>
                      {(result.metadata.slowlog.analysis_tags || []).map((tag: string) => <Tag key={tag}>{tag}</Tag>)}
                      {!(result.metadata.slowlog.analysis_tags || []).length && <Text type="secondary">-</Text>}
                    </Space>
                  </Descriptions.Item>
                </Descriptions>
              )}
            </Space>
          </SectionCard>

          <SectionCard title="原始计划" bodyPadding={0} marginBottom={0}>
            <Tabs items={rawPlanTabs} style={{ padding: '0 16px 8px' }} />
          </SectionCard>
        </>
      )}
    </div>
  )
}
