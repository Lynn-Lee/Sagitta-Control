import { useState } from 'react'
import {
  Button, Card, Form, Input, Modal, Popconfirm,
  Select, Space, Switch, Table, Tag, Transfer, Typography, message, Grid,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, TeamOutlined, DatabaseOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { instanceApi } from '@/api/instance'
import { resourceGroupApi, userGroupApi } from '@/api/system'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Text } = Typography
const { useBreakpoint } = Grid

export default function ResourceGroupManagement() {
  const qc = useQueryClient()
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const [modalOpen, setModalOpen] = useState(false)
  const [memberModalOpen, setMemberModalOpen] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [editRecord, setEditRecord] = useState<any>(null)
  const [currentRg, setCurrentRg] = useState<any>(null)
  const [search, setSearch] = useState('')
  const [ugTargetKeys, setUgTargetKeys] = useState<string[]>([])
  const [savingMembers, setSavingMembers] = useState(false)
  const [form] = Form.useForm()
  const [msgApi, msgCtx] = message.useMessage()

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['resource-groups', search],
    queryFn: () => resourceGroupApi.list({ search: search || undefined, page_size: 100 }),
  })

  const { data: instanceData } = useQuery({
    queryKey: ['instances-for-resource-group'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })

  const { data: allGroups } = useQuery({
    queryKey: ['all-user-groups-for-rg'],
    queryFn: () => userGroupApi.list({ page: 1, page_size: 200 }),
    enabled: memberModalOpen || modalOpen,
  })

  const { data: currentMembers } = useQuery({
    queryKey: ['rg-members', currentRg?.id],
    queryFn: () => resourceGroupApi.listMembers(currentRg!.id),
    enabled: !!currentRg?.id && memberModalOpen,
  })

  const createMut = useMutation({
    mutationFn: resourceGroupApi.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['resource-groups'] }); setModalOpen(false); msgApi.success('资源组创建成功') },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '创建失败'),
  })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: any) => resourceGroupApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['resource-groups'] }); setModalOpen(false); msgApi.success('已更新') },
  })
  const deleteMut = useMutation({
    mutationFn: resourceGroupApi.delete,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['resource-groups'] }); msgApi.success('已删除') },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '删除失败'),
  })

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const payload = {
        ...values,
        user_group_ids: (values.user_group_ids ?? []).map(Number),
      }
      editId ? updateMut.mutate({ id: editId, data: payload }) : createMut.mutate(payload)
    } catch { /* validation */ }
  }

  const openCreate = () => {
    setEditId(null)
    setEditRecord(null)
    form.resetFields()
    form.setFieldsValue({ instance_ids: [], user_group_ids: [] })
    setModalOpen(true)
  }
  const openEdit = (r: any) => {
    setEditId(r.id)
    setEditRecord(r)
    form.setFieldsValue({
      ...r,
      instance_ids: (r.instances ?? []).map((inst: any) => inst.id),
      user_group_ids: (r.user_groups ?? []).map((group: any) => group.id),
    })
    setModalOpen(true)
  }
  const openMembers = async (r: any) => {
    setCurrentRg(r)
    try {
      const resp = await resourceGroupApi.listUserGroups(r.id)
      setUgTargetKeys((resp.items ?? []).map((ug: any) => String(ug.id)))
    } catch {
      setUgTargetKeys([])
    }
    setMemberModalOpen(true)
  }

  const ugTransferData = (allGroups?.items ?? []).map((g: any) => ({
    key: String(g.id),
    title: g.name_cn || g.name,
  }))

  const handleSaveMembers = async () => {
    try {
      setSavingMembers(true)
      await resourceGroupApi.updateUserGroups(currentRg.id, ugTargetKeys.map(Number))
      qc.invalidateQueries({ queryKey: ['resource-groups'] })
      qc.invalidateQueries({ queryKey: ['rg-members', currentRg?.id] })
      setMemberModalOpen(false)
      msgApi.success('用户组关联已更新')
      refetch()
    } catch (e: any) {
      msgApi.error(e.response?.data?.detail || e.response?.data?.msg || '更新失败')
    } finally {
      setSavingMembers(false)
    }
  }

  const dbTypeColor: Record<string, string> = {
    mysql: '#4479A1', pgsql: '#336791', postgresql: '#336791',
    oracle: '#F80000', mongodb: '#47A248', redis: '#DC382D',
    clickhouse: '#FFCC00', mssql: '#CC2927', elasticsearch: '#FEC514',
    cassandra: '#1287B1', doris: '#4A90D9', tidb: '#E2231A',
  }

  const mergedInstanceOptions = (() => {
    const activeInstances = instanceData?.items ?? []
    const currentInstances = editRecord?.instances ?? []
    const merged = new Map<number, any>()
    for (const inst of activeInstances) merged.set(inst.id, inst)
    for (const inst of currentInstances) merged.set(inst.id, inst)
    return Array.from(merged.values()).map((inst: any) => ({
      value: inst.id,
      label: `${inst.instance_name} (${formatDbTypeLabel(inst.db_type)} · ${inst.host}:${inst.port})${inst.is_active === false ? '（已停用）' : ''}`,
    }))
  })()

  const columns = [
    {
      title: '资源组', key: 'name', width: 220,
      render: (_: any, r: any) => (
        <Space direction="vertical" size={0}>
          <Text strong>{r.group_name}</Text>
          {r.group_name_cn && <Text type="secondary" style={{ fontSize: 12 }}>{r.group_name_cn}</Text>}
        </Space>
      ),
    },
    {
      title: '数据库实例', key: 'instances', width: 380,
      render: (_: any, r: any) => {
        const instances: any[] = r.instances ?? []
        if (!instances.length) return <Text type="secondary">未关联实例</Text>
        return (
          <Space wrap size={[4, 4]}>
            {instances.map((inst: any) => (
              <Tag key={inst.id} color={dbTypeColor[inst.db_type] || '#666'} style={{ fontSize: 12 }}>
                <DatabaseOutlined style={{ marginRight: 4 }} />
                {inst.instance_name}
                <Text type="secondary" style={{ fontSize: 11, marginLeft: 6, color: 'rgba(255,255,255,0.82)' }}>
                  {formatDbTypeLabel(inst.db_type)}
                </Text>
                <Text type="secondary" style={{ fontSize: 11, marginLeft: 4, color: 'rgba(255,255,255,0.7)' }}>
                  {inst.host}:{inst.port}
                </Text>
              </Tag>
            ))}
          </Space>
        )
      },
    },
    {
      title: '关联用户组', dataIndex: 'user_group_count', width: 260,
      render: (v: number, r: any) => (
        <Space direction="vertical" size={4}>
          <Button type="link" size="small" icon={<TeamOutlined />} onClick={() => openMembers(r)} style={{ padding: 0 }}>
            {v} 个
          </Button>
          {!!r.user_groups?.length && (
            <Space wrap size={[4, 4]}>
              {r.user_groups.map((group: any) => (
                <Tag key={group.id}>{group.name_cn || group.name}</Tag>
              ))}
            </Space>
          )}
        </Space>
      ),
    },
    {
      title: '状态', dataIndex: 'is_active', width: 96,
      render: (v: boolean) => v ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>,
    },
    {
      title: '操作', width: 110,
      render: (_: any, r: any) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <Popconfirm title="确认删除？"
            onConfirm={() => deleteMut.mutate(r.id)}>
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
        title="资源组管理"
        marginBottom={20}
        actions={(
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}
            style={isMobile ? { width: '100%' } : undefined}>新建资源组</Button>
        )}
      />

      <FilterCard>
        <Input.Search placeholder="搜索资源组名称" allowClear style={{ width: isMobile ? '100%' : 260 }}
          onSearch={setSearch} onChange={e => !e.target.value && setSearch('')} />
      </FilterCard>

      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}
        styles={{ body: { padding: 0 } }}>
        <Table dataSource={data?.items} columns={columns} rowKey="id" loading={isLoading}
          locale={{ emptyText: <TableEmptyState title="暂无资源组数据" /> }}
          tableLayout="fixed"
          scroll={{ x: 1080 }}
          pagination={{ total: data?.total, pageSize: 20, showSizeChanger: false }} />
      </Card>

      {/* 新建/编辑资源组 Modal */}
      <Modal title={editId ? '编辑资源组' : '新建资源组'} open={modalOpen}
        maskClosable={false}
        onOk={handleSubmit} onCancel={() => { setModalOpen(false); setEditRecord(null) }}
        confirmLoading={createMut.isPending || updateMut.isPending}>
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="group_name" label="资源组标识（英文）"
            rules={[{ required: true, message: '请输入资源组标识' }]}>
            <Input placeholder="如 production、dev" disabled={!!editId} />
          </Form.Item>
          <Form.Item name="group_name_cn" label="中文名称">
            <Input placeholder="如 生产环境、开发环境" />
          </Form.Item>
          <Form.Item
            name="instance_ids"
            label="关联数据库实例"
            extra="资源组负责管理实例访问范围；用户通过用户组间接获得这些实例的访问权。"
          >
            <Select
              mode="multiple"
              placeholder="选择要纳入资源组的数据库实例"
              optionFilterProp="label"
              showSearch
              options={mergedInstanceOptions}
            />
          </Form.Item>
          <Form.Item
            name="user_group_ids"
            label="关联用户组"
            extra="这里配置哪些用户组可以继承此资源组下的实例访问范围；后续也仍可通过列表中的“关联用户组”入口单独调整。"
          >
            <Select
              mode="multiple"
              placeholder="选择可继承此资源组实例范围的用户组"
              optionFilterProp="label"
              showSearch
              options={(allGroups?.items ?? []).map((group: any) => ({
                value: group.id,
                label: `${group.name_cn || group.name}${group.name_cn ? ` (${group.name})` : ''}`,
              }))}
            />
          </Form.Item>
          {editId && (
            <Form.Item name="is_active" label="状态" valuePropName="checked">
              <Switch checkedChildren="启用" unCheckedChildren="停用" />
            </Form.Item>
          )}
        </Form>
      </Modal>

      {/* 用户组关联 Modal */}
      <Modal
        title={`用户组管理 — ${currentRg?.group_name || ''}`}
        open={memberModalOpen}
        maskClosable={false}
        onOk={handleSaveMembers}
        onCancel={() => setMemberModalOpen(false)}
        confirmLoading={savingMembers}
        width={720}
        okText="保存关联"
      >
        <div style={{ marginTop: 16 }}>
          <div style={{ marginBottom: 24 }}>
            <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>关联用户组</Text>
            <Text type="secondary" style={{ fontSize: 13, display: 'block', marginBottom: 12 }}>
              这是 v2-lite 的间接授权链路：用户组关联后，组内所有成员自动获得此资源组下实例的访问权限：
            </Text>
            <Transfer
              dataSource={ugTransferData}
              titles={['可选用户组', '已关联']}
              targetKeys={ugTargetKeys}
              onChange={(next) => setUgTargetKeys(next as string[])}
              render={item => item.title}
              listStyle={{ width: 280, height: 280 }}
              showSearch
              filterOption={(val, item) =>
                (item.title ?? '').toLowerCase().includes(val.toLowerCase())
              }
            />
          </div>

          <div>
            <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>当前成员（通过用户组自动获取）</Text>
            <Text type="secondary" style={{ fontSize: 13, display: 'block', marginBottom: 12 }}>
              成员由关联的用户组自动产生，无需手动添加：
            </Text>
            <div style={{ maxHeight: 200, overflow: 'auto', border: '1px solid #f0f0f0', borderRadius: 6, padding: 12 }}>
              {currentMembers?.items?.length
                ? currentMembers.items.map((m: any) => (
                  <Tag key={m.id} style={{ marginBottom: 4 }}>{m.username}{m.display_name ? ` (${m.display_name})` : ''}</Tag>
                ))
                : <Text type="secondary">暂无成员</Text>}
            </div>
          </div>
        </div>
      </Modal>
    </div>
  )
}
