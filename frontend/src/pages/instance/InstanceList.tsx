import { useState } from 'react'
import {
  Button, Card, Form, Input, InputNumber, Modal, Popconfirm,
  Select, Space, Table, Tabs, Tag, Tooltip, Typography, message, Switch, Alert, Grid,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ApiOutlined,
  ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined,
  DatabaseOutlined, SyncOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { instanceApi, type InstanceItem } from '@/api/instance'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Text } = Typography
const { Option } = Select
const { useBreakpoint } = Grid

const DB_TYPE_COLORS: Record<string, string> = {
  mysql: 'blue', pgsql: 'geekblue', oracle: 'red', mongo: 'green',
  redis: 'volcano', clickhouse: 'orange', elasticsearch: 'gold',
  opensearch: 'lime', mssql: 'cyan', cassandra: 'purple', doris: 'magenta', tidb: 'red',
}
const DB_TYPES = ['mysql', 'pgsql', 'oracle', 'mongo', 'redis',
  'clickhouse', 'elasticsearch', 'opensearch', 'mssql', 'cassandra', 'doris', 'tidb']

// ── 数据库管理子组件 ───────────────────────────────────────
function InstanceDatabasePanel({ instance }: { instance: InstanceItem }) {
  const qc = useQueryClient()
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [newDbName, setNewDbName] = useState('')
  const [newRemark, setNewRemark] = useState('')
  const [syncResult, setSyncResult] = useState<any>(null)
  const [msgApi, msgCtx] = message.useMessage()

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['instance-dbs', instance.id],
    queryFn: () => instanceApi.listRegisteredDbs(instance.id, true),
  })

  const addMut = useMutation({
    mutationFn: () => instanceApi.addDb(instance.id, newDbName, newRemark),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['instance-dbs', instance.id] })
      setAddModalOpen(false)
      setNewDbName(''); setNewRemark('')
      msgApi.success(`数据库 "${newDbName}" 添加成功`)
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '添加失败'),
  })

  const updateMut = useMutation({
    mutationFn: ({ idbId, data }: any) => instanceApi.updateDb(instance.id, idbId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['instance-dbs', instance.id] }),
  })

  const deleteMut = useMutation({
    mutationFn: (idbId: number) => instanceApi.deleteDb(instance.id, idbId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['instance-dbs', instance.id] })
      msgApi.success('已删除')
    },
  })

  const syncMut = useMutation({
    mutationFn: () => instanceApi.syncDbs(instance.id),
    onSuccess: (res) => {
      setSyncResult(res)
      qc.invalidateQueries({ queryKey: ['instance-dbs', instance.id] })
    },
    onError: (e: any) => setSyncResult({ success: false, message: e.response?.data?.msg || '同步失败' }),
  })

  const dbLabel = data?.items?.[0]?.db_name_label || '数据库'

  const columns: ColumnsType<any> = [
    {
      title: dbLabel + '名称', dataIndex: 'db_name', width: 360,
      render: (v: string, r: any) => (
        <Space size={6} style={{ display: 'inline-flex', flexWrap: 'nowrap', whiteSpace: 'nowrap' }}>
          <Tag color="blue" style={{ fontFamily: 'monospace' }}>{v}</Tag>
          {!r.is_active && <Tag color="default">已禁用</Tag>}
        </Space>
      ),
    },
    { title: '备注', dataIndex: 'remark', width: 120, ellipsis: true, align: 'left',
      render: (v: string) => v || <Text type="secondary">—</Text> },
    {
      title: '状态', dataIndex: 'is_active', width: 90,
      render: (v: boolean, r: any) => (
        <Switch size="small" checked={v}
          onChange={(checked) => updateMut.mutate({ idbId: r.id, data: { is_active: checked } })} />
      ),
    },
    {
      title: '同步时间', dataIndex: 'sync_at', width: 140,
      render: (v: string) => v
        ? <Text type="secondary" style={{ fontSize: 11 }}>{new Date(v).toLocaleString('zh-CN')}</Text>
        : <Text type="secondary" style={{ fontSize: 11 }}>手动添加</Text>,
    },
    {
      title: '操作', width: 80,
      render: (_: any, r: any) => (
        <Popconfirm title={`确认删除 "${r.db_name}"？`} onConfirm={() => deleteMut.mutate(r.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ]

  return (
    <div>
      {msgCtx}
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" size="small" icon={<PlusOutlined />}
          onClick={() => setAddModalOpen(true)}>
          手动添加{dbLabel}
        </Button>
        <Button size="small" icon={<SyncOutlined />} loading={syncMut.isPending}
          onClick={() => { setSyncResult(null); syncMut.mutate() }}>
          从实例自动同步
        </Button>
        <Button size="small" icon={<ReloadOutlined />} onClick={() => refetch()} />
        <Text type="secondary" style={{ fontSize: 12 }}>
          共 {data?.total ?? 0} 个{dbLabel}
        </Text>
      </Space>

      {syncResult && (
        <Alert
          type={syncResult.success ? 'success' : 'error'}
          message={syncResult.message}
          closable onClose={() => setSyncResult(null)}
          style={{ marginBottom: 12 }}
        />
      )}

      <Table
        dataSource={data?.items}
        columns={columns}
        rowKey="id"
        loading={isLoading}
        locale={{ emptyText: <TableEmptyState title="暂无实例数据" /> }}
        size="small"
        tableLayout="fixed"
        scroll={{ x: 820 }}
        pagination={{ pageSize: 20, showSizeChanger: false }}
      />

      <Modal title={`添加${dbLabel}`} open={addModalOpen}
        maskClosable={false}
        onOk={() => { if (newDbName.trim()) addMut.mutate() }}
        onCancel={() => { setAddModalOpen(false); setNewDbName(''); setNewRemark('') }}
        confirmLoading={addMut.isPending}>
        <Space direction="vertical" style={{ width: '100%', marginTop: 16 }}>
          <div>
            <Text>{dbLabel}名称 <Text type="danger">*</Text></Text>
            <Input
              style={{ marginTop: 4 }}
              placeholder={
                instance.db_type === 'oracle' ? '如：SCOTT、HR' :
                instance.db_type === 'redis' ? '如：0、1' :
                '如：mydb、order_db'
              }
              value={newDbName}
              onChange={e => setNewDbName(e.target.value)}
            />
          </div>
          <div>
            <Text>备注（可选）</Text>
            <Input style={{ marginTop: 4 }} placeholder="如：生产订单库"
              value={newRemark} onChange={e => setNewRemark(e.target.value)} />
          </div>
        </Space>
      </Modal>
    </div>
  )
}

// ── 主组件 ─────────────────────────────────────────────────
export default function InstanceList() {
  const qc = useQueryClient()
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const [modalOpen, setModalOpen] = useState(false)
  const [dbModalOpen, setDbModalOpen] = useState(false)
  const [selectedInstance, setSelectedInstance] = useState<InstanceItem | null>(null)
  const [editRecord, setEditRecord] = useState<InstanceItem | null>(null)
  const [search, setSearch] = useState('')
  const [testResults, setTestResults] = useState<Record<number, any>>({})
  const [form] = Form.useForm()
  const [msgApi, msgCtx] = message.useMessage()
  const selectedDbType = Form.useWatch('db_type', form)

  const { data, isLoading } = useQuery({
    queryKey: ['instances', search],
    queryFn: () => instanceApi.list({ search: search || undefined, page_size: 100 }),
  })

  const createMut = useMutation({
    mutationFn: instanceApi.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['instances'] }); setModalOpen(false); msgApi.success('实例创建成功') },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '创建失败'),
  })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: any) => instanceApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['instances'] }); setModalOpen(false); msgApi.success('已更新') },
  })
  const deleteMut = useMutation({
    mutationFn: instanceApi.delete,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['instances'] }); msgApi.success('实例已删除') },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || '删除失败'),
  })

  const handleTest = async (id: number) => {
    setTestResults(prev => ({ ...prev, [id]: { loading: true } }))
    try {
      const r = await instanceApi.testConnection(id)
      setTestResults(prev => ({ ...prev, [id]: r }))
    } catch (e: any) {
      setTestResults(prev => ({ ...prev, [id]: { success: false, message: e.response?.data?.detail || '连接失败' } }))
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      editRecord
        ? updateMut.mutate({ id: editRecord.id, data: values })
        : createMut.mutate(values)
    } catch { /* validation */ }
  }

  const openCreate = () => { setEditRecord(null); form.resetFields(); setModalOpen(true) }
  const openEdit = (r: InstanceItem) => { setEditRecord(r); form.setFieldsValue(r); setModalOpen(true) }
  const openDbManage = (r: InstanceItem) => { setSelectedInstance(r); setDbModalOpen(true) }

  const columns: ColumnsType<InstanceItem> = [
    { title: 'ID', dataIndex: 'id', width: 55 },
    {
      title: '实例名称', dataIndex: 'instance_name', width: 210,
      render: (v: string, r: InstanceItem) => (
        <Space direction="vertical" size={0}>
          <Text strong>{v}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>{r.host}:{r.port}</Text>
        </Space>
      ),
    },
    {
      title: '类型', dataIndex: 'db_type', width: 110,
      render: (v: string) => <Tag color={DB_TYPE_COLORS[v] || 'default'}>{formatDbTypeLabel(v)}</Tag>,
    },
    {
      title: '连接用户', dataIndex: 'user', width: 120,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    { title: '默认连接', dataIndex: 'db_name', width: 130,
      render: (v: string) => v || <Text type="secondary">—</Text> },
    {
      title: '备注', dataIndex: 'remark', width: 220, ellipsis: true,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    {
      title: '状态', dataIndex: 'is_active', width: 80,
      render: (v: boolean) => v ? <Tag color="success">正常</Tag> : <Tag>停用</Tag>,
    },
    {
      title: '连通性', key: 'test', width: 110,
      render: (_: any, r: InstanceItem) => {
        const tr = testResults[r.id]
        return (
          <Space size={4}>
            <Button size="small" icon={<ApiOutlined />} loading={tr?.loading}
              onClick={() => handleTest(r.id)}>测试</Button>
            {tr && !tr.loading && (
              tr.success
                ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
                : <Tooltip title={tr.message}><CloseCircleOutlined style={{ color: '#f5222d' }} /></Tooltip>
            )}
          </Space>
        )
      },
    },
    {
      title: '操作', width: 160,
      render: (_: any, r: InstanceItem) => (
        <Space size={4}>
          <Tooltip title="管理数据库">
            <Button size="small" icon={<DatabaseOutlined />} onClick={() => openDbManage(r)} />
          </Tooltip>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <Popconfirm title="确认删除此实例？" onConfirm={() => deleteMut.mutate(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="实例管理"
        actions={(
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}
          style={isMobile ? { width: '100%' } : undefined}>
            新建实例
          </Button>
        )}
      />

      <FilterCard>
        <Input.Search placeholder="搜索实例名称" allowClear style={{ width: isMobile ? '100%' : 260 }}
          onSearch={setSearch} onChange={e => !e.target.value && setSearch('')} />
      </FilterCard>

      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}
        styles={{ body: { padding: 0 } }}>
        <Table dataSource={data?.items} columns={columns} rowKey="id"
          loading={isLoading}
          locale={{ emptyText: <TableEmptyState title="暂无实例数据" /> }}
          tableLayout="fixed"
          scroll={{ x: 1080 }}
          pagination={{ total: data?.total, pageSize: 20, showSizeChanger: false }} />
      </Card>

      {/* 新建/编辑实例 Modal */}
      <Modal title={editRecord ? '编辑实例' : '新建实例'} open={modalOpen}
        maskClosable={false}
        onOk={handleSubmit} onCancel={() => setModalOpen(false)}
        confirmLoading={createMut.isPending || updateMut.isPending}
        width={560}>
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="instance_name" label="实例名称" rules={[{ required: true }]}>
            <Input placeholder="唯一标识，如 prod-mysql-01" disabled={!!editRecord} />
          </Form.Item>
          <Space style={{ width: '100%', display: 'flex' }}>
            <Form.Item name="db_type" label="数据库类型" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select placeholder="选择类型">
                {DB_TYPES.map(t => <Option key={t} value={t}><Tag color={DB_TYPE_COLORS[t]}>{formatDbTypeLabel(t)}</Tag></Option>)}
              </Select>
            </Form.Item>
            <Form.Item name="type" label="主从类型" initialValue="master" style={{ flex: 1 }}>
              <Select>
                <Option value="master">主库</Option>
                <Option value="slave">从库</Option>
              </Select>
            </Form.Item>
          </Space>
          <Space style={{ width: '100%', display: 'flex' }}>
            <Form.Item name="host" label="主机地址" rules={[{ required: true }]} style={{ flex: 2 }}>
              <Input placeholder="hostname 或 IP" />
            </Form.Item>
            <Form.Item name="port" label="端口" rules={[{ required: true }]} style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} min={1} max={65535} />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%', display: 'flex' }}>
            <Form.Item name="user" label="用户名" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Input autoComplete="off" />
            </Form.Item>
            <Form.Item name="password" label="密码" style={{ flex: 1 }}>
              <Input.Password autoComplete="new-password"
                placeholder={editRecord ? '不修改请留空' : ''} />
            </Form.Item>
          </Space>
          <Form.Item
            name="db_name"
            label={
              selectedDbType === 'oracle'
                ? 'Service Name / PDB（可选）'
                : '默认连接库（可选）'
            }
            extra={
              selectedDbType === 'oracle'
                ? 'Oracle 这里填写服务名或 PDB，如 FREEPDB1；实例下一级同步的是 Schema。'
                : selectedDbType === 'pgsql'
                  ? 'PostgreSQL 可填写默认连接数据库，如 postgres 或 testdb。'
                  : selectedDbType === 'mysql'
                    ? 'MySQL 一般可留空；如果需要默认连接某个库，也可以填写。'
                    : undefined
            }
          >
            <Input
              placeholder={
                selectedDbType === 'oracle'
                  ? '如 FREEPDB1'
                  : selectedDbType === 'pgsql'
                    ? '如 postgres'
                    : '部分数据库需要指定，如 postgres'
              }
            />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input placeholder="用途说明" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 数据库管理 Modal */}
      <Modal
        title={
          <Space>
            <DatabaseOutlined />
            <span>数据库管理</span>
            {selectedInstance && <Tag color={DB_TYPE_COLORS[selectedInstance.db_type]}>{selectedInstance.instance_name}</Tag>}
          </Space>
        }
        open={dbModalOpen}
        maskClosable={false}
        onCancel={() => setDbModalOpen(false)}
        footer={null}
        width={700}
      >
        {selectedInstance && <InstanceDatabasePanel instance={selectedInstance} />}
      </Modal>
    </div>
  )
}
