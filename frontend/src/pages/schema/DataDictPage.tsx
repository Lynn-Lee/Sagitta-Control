import { useMemo, useState } from 'react'
import {
  Button, Card, Col, Collapse, Divider, Input, Row, Select, Space, Spin, Table, Tag, Tooltip, Tree, Typography, message,
} from 'antd'
import {
  DatabaseOutlined, TableOutlined, FieldBinaryOutlined, KeyOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { instanceApi } from '@/api/instance'
import type { InstanceDatabase } from '@/api/instance'
import apiClient from '@/api/client'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import SectionLoading from '@/components/common/SectionLoading'
import TableEmptyState from '@/components/common/TableEmptyState'
import { useAuthStore } from '@/store/auth'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Text } = Typography
const { Option } = Select

function normalizeConstraintExpr(value?: string | null) {
  return String(value || '')
    .replace(/^CHECK\s*/i, '')
    .replace(/[()"`[\]]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toUpperCase()
}

function isColumnNotNullCheck(constraint: any) {
  if (constraint?.constraint_type !== 'CHECK') return false
  const columnNames = String(constraint?.column_names || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
  if (columnNames.length !== 1) return false
  const normalizedColumn = columnNames[0].replace(/["`[\]]/g, '').trim().toUpperCase()
  const normalizedClause = normalizeConstraintExpr(constraint?.check_clause)
  return normalizedClause === `${normalizedColumn} IS NOT NULL`
}

export default function DataDictPage() {
  const navigate = useNavigate()
  const user = useAuthStore((state) => state.user)
  const [instanceId, setInstanceId] = useState<number | undefined>()
  const [dbName, setDbName] = useState<string>('')
  const [selectedTable, setSelectedTable] = useState<string>('')
  const [tableKeyword, setTableKeyword] = useState('')
  const [, msgCtx] = message.useMessage()

  const { data: instances } = useQuery({
    queryKey: ['instances-for-dict'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })

  const { data: dbData, error: dbDataError } = useQuery({
    queryKey: ['registered-dbs-dict', instanceId],
    queryFn: () => instanceApi.getDatabases(instanceId!),
    enabled: !!instanceId,
  })

  const { data: tableData, isLoading: tableLoading, error: tableDataError } = useQuery({
    queryKey: ['tables-dict', instanceId, dbName],
    queryFn: () => apiClient.get(`/instances/${instanceId}/tables/`, { params: { db_name: dbName } }).then(r => r.data),
    enabled: !!instanceId && !!dbName,
  })

  const { data: columnData, isLoading: colLoading, error: columnDataError } = useQuery({
    queryKey: ['columns-dict', instanceId, dbName, selectedTable],
    queryFn: () => apiClient.get(`/instances/${instanceId}/columns/`, {
      params: { db_name: dbName, tb_name: selectedTable }
    }).then(r => r.data),
    enabled: !!instanceId && !!dbName && !!selectedTable,
  })

  const { data: constraintData, isLoading: constraintLoading, error: constraintDataError } = useQuery({
    queryKey: ['constraints-dict', instanceId, dbName, selectedTable],
    queryFn: () => apiClient.get(`/instances/${instanceId}/constraints/`, {
      params: { db_name: dbName, tb_name: selectedTable }
    }).then(r => r.data),
    enabled: !!instanceId && !!dbName && !!selectedTable,
  })

  const { data: indexData, isLoading: indexLoading, error: indexDataError } = useQuery({
    queryKey: ['indexes-dict', instanceId, dbName, selectedTable],
    queryFn: () => apiClient.get(`/instances/${instanceId}/indexes/`, {
      params: { db_name: dbName, tb_name: selectedTable }
    }).then(r => r.data),
    enabled: !!instanceId && !!dbName && !!selectedTable,
  })

  const tables: string[] = useMemo(() => tableData?.tables || [], [tableData])
  const columns: any[] = useMemo(() => columnData?.columns || [], [columnData])
  const constraints: any[] = useMemo(() => constraintData?.constraints || [], [constraintData])
  const indexes: any[] = useMemo(() => indexData?.indexes || [], [indexData])
  const dbAccessDenied = (dbDataError as any)?.response?.status === 403
  const objectAccessDenied = [tableDataError, columnDataError, constraintDataError, indexDataError]
    .some((error) => (error as any)?.response?.status === 403)
  const canSelectDisabledDb = !!user?.is_superuser || !!user?.permissions?.includes('query_all_instances')
  const visibleConstraints = useMemo(
    () => constraints.filter((constraint) => !isColumnNotNullCheck(constraint)),
    [constraints],
  )

  const renderNoWrapText = (
    value?: string | number | null,
    options?: { code?: boolean; placeholder?: string; fontSize?: number }
  ) => {
    const text = value === null || value === undefined || value === ''
      ? ''
      : String(value)
    if (!text) {
      return <Text type="secondary">{options?.placeholder || '—'}</Text>
    }

    const content = options?.code
      ? (
        <Text code style={{ fontSize: options?.fontSize || 12, whiteSpace: 'nowrap' }}>
          {text}
        </Text>
      )
      : (
        <Text style={{ fontSize: options?.fontSize || 12, whiteSpace: 'nowrap' }}>
          {text}
        </Text>
      )
    return (
      <Tooltip title={text}>
        <span style={{
          display: 'block',
          width: '100%',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {content}
        </span>
      </Tooltip>
    )
  }

  const renderEllipsisTag = (value?: string | number | null, color = 'default') => {
    const text = value === null || value === undefined || value === ''
      ? '—'
      : String(value)
    return (
      <Tooltip title={text}>
        <Tag color={color} style={{
          display: 'inline-block',
          maxWidth: '100%',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {text}
        </Tag>
      </Tooltip>
    )
  }

  const filteredTables = useMemo(() => {
    const keyword = tableKeyword.trim().toLowerCase()
    if (!keyword) return tables
    return tables.filter((tableName) => tableName.toLowerCase().includes(keyword))
  }, [tableKeyword, tables])

  const treeData = filteredTables.map(t => ({
    key: t, title: (
      <Space size={4}>
        <TableOutlined style={{ color: '#1558A8' }} />
        <Tooltip title={t}>
          <Text style={{
            fontSize: 13,
            display: 'inline-block',
            maxWidth: 180,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          >
            {t}
          </Text>
        </Tooltip>
      </Space>
    ),
    icon: null,
  }))

  const decoratedColumns = useMemo(() => {
    const badgeMap = new Map<string, Array<{ key: string; label: string; color: string; icon?: 'key'; tooltip?: string }>>()
    const pushBadge = (
      columnName: string,
      badge: { key: string; label: string; color: string; icon?: 'key'; tooltip?: string },
    ) => {
      if (!columnName) return
      const current = badgeMap.get(columnName) || []
      if (!current.some((item) => item.key === badge.key)) {
        current.push(badge)
        badgeMap.set(columnName, current)
      }
    }

    constraints.forEach((constraint) => {
      const columnNames = String(constraint.column_names || '')
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
      if (constraint.constraint_type === 'PRIMARY KEY' && columnNames.length === 1) {
        pushBadge(columnNames[0], { key: 'primary-key', label: '主键', color: 'red', icon: 'key' })
      }
      if (constraint.constraint_type === 'UNIQUE' && columnNames.length === 1) {
        pushBadge(columnNames[0], { key: 'unique', label: '唯一', color: 'gold' })
      }
      if (constraint.constraint_type === 'UNIQUE' && columnNames.length > 1) {
        const groupKey = `composite-unique:${columnNames.join('|')}`
        const tooltip = `参与联合唯一约束：${columnNames.join(', ')}`
        columnNames.forEach((columnName) => {
          pushBadge(columnName, {
            key: groupKey,
            label: '联合唯一',
            color: 'gold',
            tooltip,
          })
        })
      }
    })

    indexes.forEach((index) => {
      const columnNames = String(index.column_names || '')
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
      if (index.index_type === 'UNIQUE INDEX' && columnNames.length === 1) {
        pushBadge(columnNames[0], { key: 'unique-index', label: '唯一索引', color: 'gold' })
      }
      if (index.index_type === 'UNIQUE INDEX' && columnNames.length > 1) {
        const groupKey = `composite-unique:${columnNames.join('|')}`
        const tooltip = `参与联合唯一索引：${columnNames.join(', ')}`
        columnNames.forEach((columnName) => {
          pushBadge(columnName, {
            key: groupKey,
            label: '联合唯一',
            color: 'gold',
            tooltip,
          })
        })
      }
    })

    return columns.map((column, index) => {
      const badges = [...(badgeMap.get(column.column_name) || [])]
      const pushLocalBadge = (badge: { key: string; label: string; color: string; icon?: 'key'; tooltip?: string }) => {
        if (!badges.some((item) => item.key === badge.key)) {
          badges.push(badge)
        }
      }
      if (column.column_key === 'PRI') {
        pushLocalBadge({ key: 'primary-key', label: '主键', color: 'red', icon: 'key' })
      }
      if (column.column_key === 'UNI') {
        pushLocalBadge({ key: 'unique', label: '唯一', color: 'gold' })
      }
      const normalizedNullable = String(column.is_nullable || '').toUpperCase()
      if (normalizedNullable === 'NO' || normalizedNullable === 'N' || column.is_nullable === false) {
        badges.push({ key: 'not-null', label: '非空', color: 'volcano' })
      }
      const dedupedBadges = badges.filter(
        (badge, badgeIndex) => badges.findIndex((item) => item.key === badge.key) === badgeIndex,
      )
      return { key: index, ...column, badges: dedupedBadges }
    })
  }, [columns, constraints, indexes])

  const colTableCols = [
    { title: '列名', dataIndex: 'column_name', key: 'column_name', width: 220, ellipsis: true,
      render: (v: string) => renderNoWrapText(v, { code: true }) },
    { title: '数据类型', dataIndex: 'column_type', key: 'column_type', width: 170,
      render: (v: string) => renderEllipsisTag(v, 'geekblue') },
    { title: '可空', dataIndex: 'is_nullable', key: 'is_nullable', width: 70,
      render: (v: string | boolean) => {
        const nullable = v === 'YES' || v === true
        return <Tag color={nullable ? 'default' : 'red'}>{nullable ? 'YES' : 'NO'}</Tag>
      }},
    { title: '默认值', dataIndex: 'column_default', key: 'column_default', width: 180, ellipsis: true,
      render: (v: any) => v !== null && v !== undefined && v !== ''
        ? renderNoWrapText(String(v), { code: true, fontSize: 11 })
        : <Text type="secondary" style={{ fontSize: 11 }}>NULL</Text> },
    { title: '约束标记', dataIndex: 'badges', key: 'badges', width: 260,
      render: (badges: Array<{ key: string; label: string; color: string; icon?: 'key'; tooltip?: string }>) => (
        badges?.length ? (
          <Space size={[6, 6]} wrap>
            {badges.map((badge) => (
              <Tooltip key={badge.key} title={badge.tooltip}>
                <Tag color={badge.color} icon={badge.icon === 'key' ? <KeyOutlined /> : undefined}>
                  {badge.label}
                </Tag>
              </Tooltip>
            ))}
          </Space>
        ) : <Text type="secondary">—</Text>
      ) },
    { title: '注释', dataIndex: 'column_comment', key: 'column_comment', width: 560, ellipsis: true,
      render: (v: string) => renderNoWrapText(v) },
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
      render: (v: string) => renderEllipsisTag(v || '—', constraintTypeColors[v] || 'default'),
    },
    {
      title: '约束名称',
      dataIndex: 'constraint_name',
      key: 'constraint_name',
      width: 260,
      ellipsis: true,
      render: (v: string) => renderNoWrapText(v, { code: true }),
    },
    {
      title: '涉及列',
      dataIndex: 'column_names',
      key: 'column_names',
      width: 240,
      ellipsis: true,
      render: (v: string) => renderNoWrapText(v),
    },
    {
      title: '约束定义',
      dataIndex: 'check_clause',
      key: 'check_clause',
      width: 360,
      ellipsis: true,
      render: (v: string) => renderNoWrapText(v, { code: true }),
    },
    {
      title: '引用目标',
      key: 'reference',
      width: 260,
      render: (_: any, record: any) => (
        record.referenced_table_name
          ? (
            renderNoWrapText(
              `${record.referenced_table_name}${record.referenced_column_names ? ` (${record.referenced_column_names})` : ''}`,
            )
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
      render: (v: string) => renderEllipsisTag(v || '—', indexTypeColors[v] || 'default'),
    },
    {
      title: '索引名称',
      dataIndex: 'index_name',
      key: 'index_name',
      width: 220,
      render: (v: string) => renderNoWrapText(v, { code: true }),
    },
    {
      title: '索引列',
      dataIndex: 'column_names',
      key: 'column_names',
      width: 260,
      render: (v: string) => renderNoWrapText(v),
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
      render: (v: string) => renderNoWrapText(v),
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
            onChange={(v) => { setInstanceId(v); setDbName(''); setSelectedTable(''); setTableKeyword('') }}
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
            value={dbName || undefined} onChange={(v) => { setDbName(v); setSelectedTable(''); setTableKeyword('') }}
            disabled={!instanceId} showSearch optionFilterProp="children">
            {(dbData?.databases || []).map((dbItem: InstanceDatabase) => (
              <Option
                key={dbItem.db_name}
                value={dbItem.db_name}
                title={dbItem.db_name}
                disabled={!dbItem.is_active && !canSelectDisabledDb}
              >
                {dbItem.db_name}
                {!dbItem.is_active && <Tag color="default" style={{ marginLeft: 4, fontSize: 10 }}>已禁用</Tag>}
                {dbItem.remark ? <Text type="secondary" style={{ fontSize: 11 }}> ({dbItem.remark})</Text> : null}
              </Option>
            ))}
          </Select>
          {tableLoading && <Spin size="small" />}
          {tables.length > 0 && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              共 {tables.length} 张表
              {tableKeyword.trim() && `，匹配 ${filteredTables.length} 张`}
              {selectedTable && `，已选：${selectedTable}`}
            </Text>
          )}
        </Space>
      </FilterCard>

      {instanceId && dbAccessDenied && !dbName && (
        <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}>
          <div style={{ padding: '48px 0', textAlign: 'center' }}>
            <DatabaseOutlined style={{ fontSize: 40, color: '#8c8c8c', marginBottom: 12 }} />
            <div style={{ fontSize: 15, marginBottom: 8 }}>暂无数据字典访问权限</div>
            <Text type="secondary">
              该实例的数据字典需要先申请相同范围的查询权限，审批通过后会自动继承结构查看权限。
            </Text>
            <div style={{ marginTop: 16 }}>
              <Button
                type="primary"
                onClick={() => navigate('/query/privileges', {
                  state: {
                    openApply: true,
                    instanceId,
                    scopeType: 'instance',
                  },
                })}
              >
                申请查询权限
              </Button>
            </div>
          </div>
        </Card>
      )}

      {dbName && !objectAccessDenied && (
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
                  <>
                    <div style={{ padding: 12, borderBottom: '1px solid rgba(0,0,0,0.06)' }}>
                      <Input.Search
                        allowClear
                        placeholder="搜索表名关键字"
                        value={tableKeyword}
                        onChange={(e) => setTableKeyword(e.target.value)}
                      />
                    </div>
                    {filteredTables.length ? (
                      <Tree
                        treeData={treeData}
                        selectedKeys={selectedTable ? [selectedTable] : []}
                        onSelect={(keys) => setSelectedTable(keys[0] as string || '')}
                        style={{ padding: '8px 0' }}
                        blockNode
                      />
                    ) : (
                      <div style={{ padding: 24 }}>
                        <TableEmptyState title="没有匹配的表名" />
                      </div>
                    )}
                  </>
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
                    dataSource={decoratedColumns}
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
                    <Collapse
                      defaultActiveKey={['constraint-details']}
                      items={[
                        {
                          key: 'constraint-details',
                          label: (
                            <Space wrap>
                              <Text strong>约束详情</Text>
                              {visibleConstraints.length > 0 && <Tag>{visibleConstraints.length} 条</Tag>}
                            </Space>
                          ),
                          children: (
                            <Table
                              dataSource={visibleConstraints.map((item, i) => ({ key: `${item.constraint_name}-${i}`, ...item }))}
                              columns={constraintTableCols}
                              loading={constraintLoading}
                              locale={{ emptyText: <TableEmptyState title="当前表暂无可展示的约束信息" /> }}
                              size="small"
                              tableLayout="fixed"
                              scroll={{ x: 1240 }}
                              pagination={false}
                            />
                          ),
                        },
                      ]}
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
                      scroll={{ x: 980 }}
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

      {dbName && objectAccessDenied && (
        <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}>
          <div style={{ padding: '48px 0', textAlign: 'center' }}>
            <FieldBinaryOutlined style={{ fontSize: 40, color: '#8c8c8c', marginBottom: 12 }} />
            <div style={{ fontSize: 15, marginBottom: 8 }}>当前范围暂无数据字典访问权限</div>
            <Text type="secondary">
              你需要先申请该数据库或表的查询权限，审批通过后才能查看对应结构信息。
            </Text>
            <div style={{ marginTop: 16 }}>
              <Button
                type="primary"
                onClick={() => navigate('/query/privileges', {
                  state: {
                    openApply: true,
                    instanceId,
                    dbName,
                    tableName: selectedTable || undefined,
                    scopeType: selectedTable ? 'table' : 'database',
                  },
                })}
              >
                申请查询权限
              </Button>
            </div>
          </div>
        </Card>
      )}

      {!dbName && !dbAccessDenied && (
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
