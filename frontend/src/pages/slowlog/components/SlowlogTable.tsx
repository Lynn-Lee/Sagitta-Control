import type { ReactNode } from 'react'
import { Alert, Button, Card, Form, Input, Select, Space, Statistic, Table, Tabs, Tag, Typography } from 'antd'
import type { FormInstance } from 'antd/es/form'
import type { ColumnsType } from 'antd/es/table'
import { BulbOutlined, ClearOutlined } from '@ant-design/icons'
import type { OptimizeAnalyzeResponse } from '@/api/optimize'
import type {
  SlowQueryFingerprintItem,
  SlowQueryGroupStat,
  SlowQueryLogItem,
  SlowQueryOverviewResponse,
} from '@/api/slowlog'
import TableEmptyState from '@/components/common/TableEmptyState'
import { SOURCE_COLOR, formatMs, sourceLabel } from '../helpers'
import type { SlowlogDatabaseOption, SlowlogInstanceOption } from '../types'

const { Text, Paragraph } = Typography

type SlowlogTableProps = {
  activeTab: string
  onActiveTabChange: (key: string) => void
  isMobile: boolean
  instanceId: number | undefined
  overview?: SlowQueryOverviewResponse
  overviewLoading: boolean
  primaryStats: SlowQueryGroupStat[]
  primaryStatsTitle: string
  primaryStatsEmptyTitle: string
  groupTrendTitle: string
  groupStatColumns: ColumnsType<SlowQueryGroupStat>
  commonColumns: ColumnsType<SlowQueryLogItem>
  fingerprintColumns: ColumnsType<SlowQueryFingerprintItem>
  realtimeColumns: ColumnsType<any>
  logItems: SlowQueryLogItem[]
  logTotal: number
  logLoading: boolean
  fingerprintItems: SlowQueryFingerprintItem[]
  fingerprintLoading: boolean
  realtimeItems: any[]
  realtimeLoading: boolean
  page: number
  onPageChange: (page: number) => void
  renderGroupTrend: (metric: 'count' | 'avg_duration_ms', title: string) => ReactNode
  manualForm: FormInstance
  runManualDiagnosis: (values: any) => void
  filterWidth: (width: number) => number | string
  instances: SlowlogInstanceOption[]
  databases: SlowlogDatabaseOption[]
  canAnalyze: boolean
  manualDiagnosis: OptimizeAnalyzeResponse | null
  manualDiagnosisLoading: boolean
  onClearManualDiagnosis: () => void
  renderDiagnosisPanel: (result?: OptimizeAnalyzeResponse | null) => ReactNode
}

export function SlowlogTable({
  activeTab,
  onActiveTabChange,
  isMobile,
  instanceId,
  overview,
  overviewLoading,
  primaryStats,
  primaryStatsTitle,
  primaryStatsEmptyTitle,
  groupTrendTitle,
  groupStatColumns,
  commonColumns,
  fingerprintColumns,
  realtimeColumns,
  logItems,
  logTotal,
  logLoading,
  fingerprintItems,
  fingerprintLoading,
  realtimeItems,
  realtimeLoading,
  page,
  onPageChange,
  renderGroupTrend,
  manualForm,
  runManualDiagnosis,
  filterWidth,
  instances,
  databases,
  canAnalyze,
  manualDiagnosis,
  manualDiagnosisLoading,
  onClearManualDiagnosis,
  renderDiagnosisPanel,
}: SlowlogTableProps) {
  return (
    <Tabs
      activeKey={activeTab}
      onChange={onActiveTabChange}
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
                  loading={overviewLoading}
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
                dataSource={logItems.map(row => ({ ...row, key: row.id }))}
                columns={commonColumns}
                loading={logLoading}
                size="small"
                tableLayout="fixed"
                scroll={{ x: 1660 }}
                locale={{ emptyText: <TableEmptyState title="暂无 SQL 样本" /> }}
                pagination={{
                  current: page,
                  pageSize: 50,
                  total: logTotal,
                  showSizeChanger: false,
                  onChange: onPageChange,
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
                dataSource={fingerprintItems.map(row => ({ ...row, key: row.sql_fingerprint }))}
                columns={fingerprintColumns}
                loading={fingerprintLoading}
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
                loading={realtimeLoading}
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
                        options={instances.map(inst => ({ value: inst.id, label: inst.instance_name }))}
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
                              options={(selected === instanceId ? databases : [])
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
                    <Button type="primary" icon={<BulbOutlined />} htmlType="submit" disabled={!canAnalyze} loading={manualDiagnosisLoading}>
                      开始诊断
                    </Button>
                    <Button className="sagitta-action-btn sagitta-action-btn--neutral" icon={<ClearOutlined />} onClick={() => { manualForm.resetFields(); onClearManualDiagnosis() }}>
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
      ]}
    />
  )
}
