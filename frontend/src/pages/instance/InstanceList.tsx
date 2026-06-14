import { useState } from 'react'
import {
  Button, Form, Input, InputNumber, Modal, Popconfirm,
  Select, Space, Table, Tabs, Tag, Tooltip, Typography, message, Switch, Alert, Grid,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ApiOutlined,
  ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined,
  DatabaseOutlined, SyncOutlined, SearchOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { instanceApi, type InstanceItem } from '@/api/instance'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import SectionCard from '@/components/common/SectionCard'
import TableEmptyState from '@/components/common/TableEmptyState'
import { DB_TYPES, formatDbTypeLabel, getEngineSupport, isExperimentalDbType } from '@/utils/dbType'
import { getTablePaginationConfig } from '@/utils/tablePagination'

const { Text } = Typography
const { Option } = Select
const { useBreakpoint } = Grid

const DB_TYPE_COLORS: Record<string, string> = {
  mysql: 'blue', pgsql: 'geekblue', oracle: 'red', mongo: 'green',
  redis: 'volcano', clickhouse: 'orange', elasticsearch: 'gold',
  opensearch: 'lime', mssql: 'cyan', cassandra: 'purple', doris: 'magenta',
  tidb: 'red', starrocks: 'gold',
}

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
        ? <Text type="secondary">{new Date(v).toLocaleString('zh-CN')}</Text>
        : <Text type="secondary">手动添加</Text>,
    },
    {
      title: '操作', width: 90,
      render: (_: any, r: any) => (
        <Popconfirm
          title={`确认删除 "${r.db_name}"？`}
          okText="确定"
          cancelText="取消"
          onConfirm={() => deleteMut.mutate(r.id)}
        >
          <Button className="sagitta-action-btn sagitta-action-btn--danger" danger icon={<DeleteOutlined />}>
            删除
          </Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div>
      {msgCtx}
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" icon={<PlusOutlined />}
          onClick={() => setAddModalOpen(true)}>
          手动添加{dbLabel}
        </Button>
        <Button icon={<SyncOutlined />} loading={syncMut.isPending}
          onClick={() => { setSyncResult(null); syncMut.mutate() }}>
          从实例自动同步
        </Button>
        <Button className="sagitta-action-btn sagitta-action-btn--refresh" icon={<ReloadOutlined />} onClick={() => refetch()}>
          刷新
        </Button>
        <Text type="secondary">
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
        pagination={getTablePaginationConfig({
          pageSize: 20,
          total: data?.total,
          showTotal: t => `共 ${t} 个${dbLabel}`,
        })}
      />

      <Modal title={`添加${dbLabel}`} open={addModalOpen}
        maskClosable={false}
        onOk={() => { if (newDbName.trim()) addMut.mutate() }}
        onCancel={() => { setAddModalOpen(false); setNewDbName(''); setNewRemark('') }}
        okText="确定"
        cancelText="取消"
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
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [testResults, setTestResults] = useState<Record<number, any>>({})
  const [form] = Form.useForm()
  const [msgApi, msgCtx] = message.useMessage()
  const selectedDbType = Form.useWatch('db_type', form)

  const { data, isLoading } = useQuery({
    queryKey: ['instances', search, page, pageSize],
    queryFn: () => instanceApi.list({
      search: search || undefined,
      page,
      page_size: pageSize,
      include_inactive: true,
    }),
  })

  const createMut = useMutation({
    mutationFn: instanceApi.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['instances'] }); setModalOpen(false); msgApi.success('实例创建成功') },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '创建失败'),
  })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: any) => instanceApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['instances'] }); setModalOpen(false); msgApi.success('已更新') },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || '更新失败'),
  })
  const deleteMut = useMutation({
    mutationFn: instanceApi.delete,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['instances'] }); msgApi.success('实例已停用') },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || e.response?.data?.detail || '停用失败'),
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
    { title: 'ID', dataIndex: 'id', width: 64 },
    {
      title: '实例名称', dataIndex: 'instance_name', width: 260,
      render: (v: string, r: InstanceItem) => (
        <Space direction="vertical" size={0} style={{ maxWidth: 224 }}>
          <Text strong ellipsis={{ tooltip: v }} style={{ maxWidth: 224 }}>{v}</Text>
          <Text type="secondary" ellipsis={{ tooltip: `${r.host}:${r.port}` }} style={{ maxWidth: 224 }}>
            {r.host}:{r.port}
          </Text>
        </Space>
      ),
    },
    {
      title: '类型', dataIndex: 'db_type', width: 130,
      render: (v: string) => <Tag color={DB_TYPE_COLORS[v] || 'default'}>{formatDbTypeLabel(v)}</Tag>,
    },
    {
      title: '连接用户', dataIndex: 'user', width: 130, ellipsis: true,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    { title: '默认连接', dataIndex: 'db_name', width: 150, ellipsis: true,
      render: (v: string) => v || <Text type="secondary">—</Text> },
    {
      title: '备注', dataIndex: 'remark', width: 260, ellipsis: true,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    {
      title: '状态', dataIndex: 'is_active', width: 90,
      render: (v: boolean, r: InstanceItem) => (
        <Switch
          size="small"
          checked={v}
          checkedChildren="正常"
          unCheckedChildren="停用"
          loading={updateMut.isPending}
          onChange={(checked) => updateMut.mutate({ id: r.id, data: { is_active: checked } })}
        />
      ),
    },
    {
      title: '连通性', key: 'test', width: 110,
      render: (_: any, r: InstanceItem) => {
        const tr = testResults[r.id]
        return (
          <Space size={4}>
            <Button icon={<ApiOutlined />} loading={tr?.loading}
              onClick={() => handleTest(r.id)}>测试</Button>
            {tr && !tr.loading && (
              tr.success
                ? <CheckCircleOutlined style={{ color: '#00B42A' }} />
                : <Tooltip title={tr.message}><CloseCircleOutlined style={{ color: '#f5222d' }} /></Tooltip>
            )}
          </Space>
        )
      },
    },
    {
      title: '操作', width: 300, fixed: 'right',
      render: (_: any, r: InstanceItem) => (
        <Space size={6} style={{ whiteSpace: 'nowrap' }}>
          <Tooltip title="管理数据库">
            <Button className="sagitta-action-btn sagitta-action-btn--manage" icon={<DatabaseOutlined />} disabled={!r.is_active} onClick={() => openDbManage(r)}>
              数据库
            </Button>
          </Tooltip>
          <Button className="sagitta-action-btn sagitta-action-btn--edit" icon={<EditOutlined />} onClick={() => openEdit(r)}>
            编辑
          </Button>
          <Popconfirm
            title="确认停用此实例？"
            okText="确定"
            cancelText="取消"
            onConfirm={() => deleteMut.mutate(r.id)}
          >
            <Button className="sagitta-action-btn sagitta-action-btn--danger" danger icon={<DeleteOutlined />} disabled={!r.is_active}>
              停用
            </Button>
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
        description="统一维护数据库连接、引擎类型、默认库和可观测采集入口，支撑查询、工单、字典和审计等核心流程。"
        actions={(
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}
          style={isMobile ? { width: '100%' } : undefined}>
            新建实例
          </Button>
        )}
      />

      <FilterCard title="筛选实例">
        <Input.Search placeholder="搜索实例名称" allowClear style={{ width: isMobile ? '100%' : 260 }}
          enterButton={<><SearchOutlined />搜索</>}
          onSearch={(value) => { setSearch(value); setPage(1) }}
          onChange={e => { if (!e.target.value) { setSearch(''); setPage(1) } }} />
      </FilterCard>

      <SectionCard title="实例列表" extra={<Text type="secondary">共 {data?.total ?? 0} 个实例</Text>} bodyPadding={0} marginBottom={0}>
        <Table dataSource={data?.items} columns={columns} rowKey="id"
          loading={isLoading}
          locale={{ emptyText: <TableEmptyState title="暂无实例数据" tone={search ? 'filter' : 'setup'} /> }}
          tableLayout="fixed"
          scroll={{ x: 1480 }}
          pagination={getTablePaginationConfig({
            total: data?.total,
            current: page,
            pageSize,
            showTotal: t => `共 ${t} 个实例`,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPageSize !== pageSize ? 1 : nextPage)
              setPageSize(nextPageSize)
            },
          })} />
      </SectionCard>

      {/* 新建/编辑实例 Modal */}
      <Modal title={editRecord ? '编辑实例' : '新建实例'} open={modalOpen}
        maskClosable={false}
        onOk={handleSubmit} onCancel={() => setModalOpen(false)}
        okText={editRecord ? '保存' : '创建'}
        cancelText="取消"
        confirmLoading={createMut.isPending || updateMut.isPending}
        width={560}>
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="instance_name" label="实例名称" rules={[{ required: true, message: '请输入实例名称' }]}>
            <Input placeholder="唯一标识，如 prod-mysql-01" disabled={!!editRecord} />
          </Form.Item>
          <Space style={{ width: '100%', display: 'flex' }}>
            <Form.Item name="db_type" label="数据库类型" rules={[{ required: true, message: '请选择数据库类型' }]} style={{ flex: 1 }}>
              <Select placeholder="选择类型">
                {DB_TYPES.map(t => (
                  <Option key={t} value={t}>
                    <Space size={6}>
                      <Tag color={DB_TYPE_COLORS[t]}>{formatDbTypeLabel(t)}</Tag>
                      {isExperimentalDbType(t) && <Text type="secondary">待验证</Text>}
                    </Space>
                  </Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item name="type" label="主从类型" initialValue="master" style={{ flex: 1 }}>
              <Select>
                <Option value="master">主库</Option>
                <Option value="slave">从库</Option>
              </Select>
            </Form.Item>
          </Space>
          {selectedDbType && isExperimentalDbType(selectedDbType) && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
              message={`${formatDbTypeLabel(selectedDbType)} 引擎仍处于待真实环境验证状态`}
              description={getEngineSupport(selectedDbType).note}
            />
          )}
          <Space style={{ width: '100%', display: 'flex' }}>
            <Form.Item name="host" label="主机地址" rules={[{ required: true, message: '请输入主机地址' }]} style={{ flex: 2 }}>
              <Input placeholder="主机名或 IP" />
            </Form.Item>
            <Form.Item name="port" label="端口" rules={[{ required: true, message: '请输入端口' }]} style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} min={1} max={65535} />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%', display: 'flex' }}>
            <Form.Item name="user" label="用户名" rules={[{ required: true, message: '请输入用户名' }]} style={{ flex: 1 }}>
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
            {selectedInstance && (
              <Tag color={DB_TYPE_COLORS[selectedInstance.db_type]}>
                {formatDbTypeLabel(selectedInstance.db_type)} · {selectedInstance.instance_name}
              </Tag>
            )}
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
