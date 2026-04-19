import { useState } from 'react'
import {
  Card, Col, Divider, Row, Select, Space, Spin, Table, Tag, Tooltip, Tree, Typography, message,
} from 'antd'
import {
  DatabaseOutlined, TableOutlined, FieldBinaryOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { instanceApi } from '@/api/instance'
import apiClient from '@/api/client'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import SectionLoading from '@/components/common/SectionLoading'
import TableEmptyState from '@/components/common/TableEmptyState'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Text } = Typography
const { Option } = Select

export default function DataDictPage() {
  const [instanceId, setInstanceId] = useState<number | undefined>()
  const [dbName, setDbName] = useState<string>('')
  const [selectedTable, setSelectedTable] = useState<string>('')
  const [msgApi, msgCtx] = message.useMessage()

  const { data: instances } = useQuery({
    queryKey: ['instances-for-dict'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })

  const { data: dbData } = useQuery({
    queryKey: ['registered-dbs-dict', instanceId],
    queryFn: () => instanceApi.listRegisteredDbs(instanceId!),
    enabled: !!instanceId,
  })

  const { data: tableData, isLoading: tableLoading } = useQuery({
    queryKey: ['tables-dict', instanceId, dbName],
    queryFn: () => apiClient.get(`/instances/${instanceId}/tables/`, { params: { db_name: dbName } }).then(r => r.data),
    enabled: !!instanceId && !!dbName,
  })

  const { data: columnData, isLoading: colLoading } = useQuery({
    queryKey: ['columns-dict', instanceId, dbName, selectedTable],
    queryFn: () => apiClient.get(`/instances/${instanceId}/columns/`, {
      params: { db_name: dbName, tb_name: selectedTable }
    }).then(r => r.data),
    enabled: !!instanceId && !!dbName && !!selectedTable,
  })

  const { data: constraintData, isLoading: constraintLoading } = useQuery({
    queryKey: ['constraints-dict', instanceId, dbName, selectedTable],
    queryFn: () => apiClient.get(`/instances/${instanceId}/constraints/`, {
      params: { db_name: dbName, tb_name: selectedTable }
    }).then(r => r.data),
    enabled: !!instanceId && !!dbName && !!selectedTable,
  })

  const { data: indexData, isLoading: indexLoading } = useQuery({
    queryKey: ['indexes-dict', instanceId, dbName, selectedTable],
    queryFn: () => apiClient.get(`/instances/${instanceId}/indexes/`, {
      params: { db_name: dbName, tb_name: selectedTable }
    }).then(r => r.data),
    enabled: !!instanceId && !!dbName && !!selectedTable,
  })

  const tables: string[] = tableData?.tables || []
  const columns: any[] = columnData?.columns || []
  const constraints: any[] = constraintData?.constraints || []
  const indexes: any[] = indexData?.indexes || []

  const renderNoWrapText = (value: string, code = false) => {
    const content = code
      ? <Text code style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{value}</Text>
      : <Text style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{value}</Text>
    return (
      <Tooltip title={value}>
        {content}
      </Tooltip>
    )
  }

  const treeData = tables.map(t => ({
    key: t, title: (
      <Space size={4}>
        <TableOutlined style={{ color: '#1558A8' }} />
        <Text style={{ fontSize: 13 }}>{t}</Text>
      </Space>
    ),
    icon: null,
  }))

  const colTableCols = [
    { title: '列名', dataIndex: 'column_name', key: 'column_name', width: 220, ellipsis: true,
      render: (v: string) => renderNoWrapText(v, true) },
    { title: '数据类型', dataIndex: 'column_type', key: 'column_type', width: 170,
      render: (v: string) => (
        <Tooltip title={v}>
          <Tag color="geekblue" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>{v}</Tag>
        </Tooltip>
      ) },
    { title: '可空', dataIndex: 'is_nullable', key: 'is_nullable', width: 70,
      render: (v: string | boolean) => {
        const nullable = v === 'YES' || v === true
        return <Tag color={nullable ? 'default' : 'red'}>{nullable ? 'YES' : 'NO'}</Tag>
      }},
    { title: '默认值', dataIndex: 'column_default', key: 'column_default', width: 180, ellipsis: true,
      render: (v: any) => v !== null && v !== undefined
        ? (
          <Tooltip title={String(v)}>
            <Text
              code
              style={{
                fontSize: 11,
                whiteSpace: 'nowrap',
                wordBreak: 'normal',
                overflowWrap: 'normal',
              }}
            >
              {String(v)}
            </Text>
          </Tooltip>
        )
        : <Text type="secondary" style={{ fontSize: 11 }}>NULL</Text> },
    { title: '注释', dataIndex: 'column_comment', key: 'column_comment', width: 560, ellipsis: true,
      render: (v: string) => v
        ? renderNoWrapText(v)
        : <Text type="secondary">—</Text> },
  ]

  const constraintTypeColors: Record<string, string> = {
    'PRIMARY KEY': 'red',
    UNIQUE: 'gold',
    'FOREIGN KEY': 'blue',
    CHECK: 'purple',
  }

  const indexTypeColors: Record<string, string> = {
    'PRIMARY KEY INDEX': 'red',
    'UNIQUE INDEX': 'gold',
    INDEX: 'blue',
  }

  const constraintTableCols = [
    {
      title: '约束类型',
      dataIndex: 'constraint_type',
      key: 'constraint_type',
      width: 120,
      render: (v: string) => <Tag color={constraintTypeColors[v] || 'default'}>{v || '—'}</Tag>,
    },
    {
      title: '约束名称',
      dataIndex: 'constraint_name',
      key: 'constraint_name',
      width: 220,
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v || '—'}</Text>,
    },
    {
      title: '涉及列',
      dataIndex: 'column_names',
      key: 'column_names',
      width: 240,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    {
      title: '引用目标',
      key: 'reference',
      width: 260,
      render: (_: any, record: any) => (
        record.referenced_table_name
          ? (
            <Text style={{ fontSize: 12 }}>
              {record.referenced_table_name}
              {record.referenced_column_names ? ` (${record.referenced_column_names})` : ''}
            </Text>
          )
          : <Text type="secondary">—</Text>
      ),
    },
  ]

  const indexTableCols = [
    {
      title: '索引类型',
      dataIndex: 'index_type',
      key: 'index_type',
      width: 140,
      render: (v: string) => <Tag color={indexTypeColors[v] || 'default'}>{v || '—'}</Tag>,
    },
    {
      title: '索引名称',
      dataIndex: 'index_name',
      key: 'index_name',
      width: 220,
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v || '—'}</Text>,
    },
    {
      title: '索引列',
      dataIndex: 'column_names',
      key: 'column_names',
      width: 260,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    {
      title: '联合索引',
      dataIndex: 'is_composite',
      key: 'is_composite',
      width: 100,
      render: (v: string) => <Tag color={v === 'YES' ? 'processing' : 'default'}>{v === 'YES' ? '是' : '否'}</Tag>,
    },
    {
      title: '备注',
      dataIndex: 'index_comment',
      key: 'index_comment',
      width: 220,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader title="数据字典" marginBottom={20} />

      {/* 选择条件 */}
      <FilterCard marginBottom={16}>
        <Space wrap>
          <Select placeholder="选择实例" style={{ minWidth: 220, maxWidth: 360 }} value={instanceId}
            popupMatchSelectWidth={false}
            onChange={(v) => { setInstanceId(v); setDbName(''); setSelectedTable('') }}
            showSearch optionFilterProp="label">
            {instances?.items?.map((i: any) => (
              <Option key={i.id} value={i.id} label={i.instance_name} title={i.instance_name}>
                <Tag color="blue" style={{ fontSize: 11 }}>{formatDbTypeLabel(i.db_type)}</Tag>
                {i.instance_name}
              </Option>
            ))}
          </Select>
          <Select placeholder="选择数据库" style={{ minWidth: 160, maxWidth: 360 }}
            popupMatchSelectWidth={false}
            value={dbName || undefined} onChange={(v) => { setDbName(v); setSelectedTable('') }}
            disabled={!instanceId} showSearch optionFilterProp="children">
            {(dbData?.items || []).map((d: any) => (
              <Option key={d.db_name} value={d.db_name} title={d.db_name}>
                {d.db_name}{!d.is_active && <Tag color="default" style={{marginLeft: 4, fontSize: 10}}>已禁用</Tag>}
              </Option>
            ))}
          </Select>
          {tableLoading && <Spin size="small" />}
          {tables.length > 0 && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              共 {tables.length} 张表
              {selectedTable && `，已选：${selectedTable}`}
            </Text>
          )}
        </Space>
      </FilterCard>

      {dbName && (
        <Row gutter={16}>
          {/* 表列表 */}
          <Col xs={24} md={6}>
            <Card title={<Space><DatabaseOutlined />{dbName}</Space>}
              style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}
              styles={{ body: { padding: 0, maxHeight: 'calc(100vh - 320px)', overflowY: 'auto' } }}>
              {tableLoading ? (
                <SectionLoading text="加载表结构中..." compact />
              ) : (
                tables.length ? (
                  <Tree
                    treeData={treeData}
                    selectedKeys={selectedTable ? [selectedTable] : []}
                    onSelect={(keys) => setSelectedTable(keys[0] as string || '')}
                    style={{ padding: '8px 0' }}
                    blockNode
                  />
                ) : (
                  <div style={{ padding: 32 }}>
                    <TableEmptyState title="当前数据库下暂无表" />
                  </div>
                )
              )}
            </Card>
          </Col>

          {/* 列结构 */}
          <Col xs={24} md={18}>
            <Card
              title={selectedTable ? (
                <Space>
                  <FieldBinaryOutlined />
                  <Text>{selectedTable}</Text>
                  {columns.length > 0 && <Tag>{columns.length} 列</Tag>}
                </Space>
              ) : '请选择一张表查看字段详情'}
              style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}
              styles={{ body: { padding: 0 } }}>
              {selectedTable ? (
                <>
                  <Table
                    dataSource={columns.map((c, i) => ({ key: i, ...c }))}
                    columns={colTableCols}
                    loading={colLoading}
                    locale={{ emptyText: <TableEmptyState title="暂无字段信息" /> }}
                    size="small"
                    tableLayout="fixed"
                    scroll={{ x: 1200 }}
                    pagination={{ pageSize: 50, showSizeChanger: false }}
                  />

                  <div style={{ padding: '0 16px 16px' }}>
                    <Divider style={{ margin: '12px 0 16px' }} />
                    <Space style={{ marginBottom: 12 }} wrap>
                      <Text strong>表约束</Text>
                      {constraints.length > 0 && <Tag>{constraints.length} 条</Tag>}
                    </Space>
                    <Table
                      dataSource={constraints.map((item, i) => ({ key: `${item.constraint_name}-${i}`, ...item }))}
                      columns={constraintTableCols}
                      loading={constraintLoading}
                      locale={{ emptyText: <TableEmptyState title="当前表暂无可展示的约束信息" /> }}
                      size="small"
                      tableLayout="auto"
                      scroll={{ x: 860 }}
                      pagination={false}
                    />

                    <Divider style={{ margin: '16px 0' }} />
                    <Space style={{ marginBottom: 12 }} wrap>
                      <Text strong>索引信息</Text>
                      {indexes.length > 0 && <Tag>{indexes.length} 条</Tag>}
                    </Space>
                    <Table
                      dataSource={indexes.map((item, i) => ({ key: `${item.index_name}-${i}`, ...item }))}
                      columns={indexTableCols}
                      loading={indexLoading}
                      locale={{ emptyText: <TableEmptyState title="当前表暂无可展示的索引信息" /> }}
                      size="small"
                      tableLayout="auto"
                      scroll={{ x: 940 }}
                      pagination={false}
                    />
                  </div>
                </>
              ) : (
                <div style={{ padding: 60, textAlign: 'center', color: '#AEAEB2' }}>
                  <DatabaseOutlined style={{ fontSize: 40, marginBottom: 12 }} />
                  <div>从左侧选择一张表查看字段结构</div>
                </div>
              )}
            </Card>
          </Col>
        </Row>
      )}

      {!dbName && (
        <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}>
          <div style={{ padding: '60px 0', textAlign: 'center', color: '#AEAEB2' }}>
            <DatabaseOutlined style={{ fontSize: 48, marginBottom: 16 }} />
            <div style={{ fontSize: 15 }}>请先选择实例和数据库</div>
          </div>
        </Card>
      )}
    </div>
  )
}
