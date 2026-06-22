import { useState } from 'react'
import {
  Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, message, Grid,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, SaveOutlined, CloseOutlined, SearchOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { roleApi, permissionApi } from '@/api/system'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'
import { renderTruncatedCell } from '@/components/common/renderTruncatedCell'
import { getTablePaginationConfig } from '@/utils/tablePagination'

const { useBreakpoint } = Grid

const RoleManagement: React.FC = () => {
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const [modalOpen, setModalOpen] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [form] = Form.useForm()
  const [messageApi, contextHolder] = message.useMessage()
  const qc = useQueryClient()

  const { data: rolesData, isLoading } = useQuery({
    queryKey: ['roles', search],
    queryFn: () => roleApi.list({ page: 1, page_size: 200 }),
  })

  const { data: permData } = useQuery({
    queryKey: ['permissions'],
    queryFn: permissionApi.list,
  })

  const allPerms = permData?.permissions ?? []
  const filtered = (rolesData?.items ?? []).filter((r: any) =>
    !search || r.name.includes(search) || r.name_cn?.includes(search),
  )

  const createMut = useMutation({
    mutationFn: (data: any) => roleApi.create(data),
    onSuccess: () => {
      messageApi.success('角色创建成功')
      qc.invalidateQueries({ queryKey: ['roles'] })
      setModalOpen(false)
      form.resetFields()
    },
    onError: (e: any) => messageApi.error(e.response?.data?.detail || '创建失败'),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => roleApi.update(id, data),
    onSuccess: () => {
      messageApi.success('角色已更新')
      qc.invalidateQueries({ queryKey: ['roles'] })
      setModalOpen(false)
      form.resetFields()
      setEditId(null)
    },
    onError: (e: any) => messageApi.error(e.response?.data?.detail || '更新失败'),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => roleApi.delete(id),
    onSuccess: () => {
      messageApi.success('角色已删除')
      qc.invalidateQueries({ queryKey: ['roles'] })
    },
    onError: (e: any) => messageApi.error(e.response?.data?.detail || '删除失败'),
  })

  const openCreate = () => {
    setEditId(null)
    form.resetFields()
    setModalOpen(true)
  }

  const openEdit = async (id: number) => {
    setEditId(id)
    const role = await roleApi.get(id)
    form.setFieldsValue({
      name_cn: role.name_cn,
      description: role.description,
      is_active: role.is_active,
      permission_codes: role.permissions,
    })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    if (editId) {
      updateMut.mutate({ id: editId, data: values })
    } else {
      createMut.mutate(values)
    }
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: '角色标识', dataIndex: 'name', width: 140, ellipsis: { showTitle: false }, render: renderTruncatedCell },
    { title: '中文名', dataIndex: 'name_cn', width: 140, ellipsis: { showTitle: false }, render: renderTruncatedCell },
    { title: '描述', dataIndex: 'description', width: 220, ellipsis: { showTitle: false }, render: renderTruncatedCell },
    {
      title: '内置', dataIndex: 'is_system', width: 80,
      render: (v: boolean) => v ? <Tag color="blue">内置</Tag> : <Tag>自定义</Tag>,
    },
    {
      title: '状态', dataIndex: 'is_active', width: 80,
      render: (v: boolean) => v ? <Tag color="green">启用</Tag> : <Tag color="red">停用</Tag>,
    },
    {
      title: '权限数', dataIndex: 'permissions', width: 100,
      render: (perms: string[]) => perms?.length ?? 0,
    },
    {
      title: '权限预览', dataIndex: 'permissions', width: 300,
      render: (perms: string[] = []) => {
        if (!perms.length) return <span style={{ color: '#999' }}>未配置</span>
        return (
          <Space wrap size={[4, 4]}>
            {perms.slice(0, 4).map((perm) => <Tag key={perm}>{perm}</Tag>)}
            {perms.length > 4 && <Tag>+{perms.length - 4}</Tag>}
          </Space>
        )
      },
    },
    {
      title: '操作', width: 160,
      render: (_: any, record: any) => (
        <Space>
          <Button className="sagitta-action-btn sagitta-action-btn--edit" icon={<EditOutlined />} onClick={() => openEdit(record.id)}>
            编辑
          </Button>
          {!record.is_system && (
            <Popconfirm title="确认删除此角色？" okText="删除" cancelText="取消" onConfirm={() => deleteMut.mutate(record.id)}>
              <Button className="sagitta-action-btn sagitta-action-btn--danger" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  // 按权限前缀分组，便于在界面中浏览
  const permOptions = allPerms.map((p: any) => ({
    label: `${p.codename}（${p.name}）`,
    value: p.codename,
  }))

  return (
    <>
      {contextHolder}
      <PageHeader
        title="角色管理"
        actions={(
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}
            style={isMobile ? { width: '100%' } : undefined}>新建角色</Button>
        )}
      />

      <FilterCard marginBottom={16}>
        <Input.Search
          placeholder="搜索角色标识或中文名"
          allowClear
          enterButton={<><SearchOutlined />搜索</>}
          onSearch={setSearch}
          style={{ width: isMobile ? '100%' : 400, maxWidth: '100%' }}
        />
      </FilterCard>

      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={filtered}
          loading={isLoading}
          locale={{ emptyText: <TableEmptyState title="暂无角色数据" /> }}
          tableLayout="fixed"
          scroll={{ x: 1180 }}
          pagination={getTablePaginationConfig({
            pageSize: 20,
            total: filtered.length,
            showTotal: t => `共 ${t} 个角色`,
          })}
          size="middle"
        />
      </Card>

      <Modal
        title={editId ? '编辑角色' : '新建角色'}
        open={modalOpen}
        maskClosable={false}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); form.resetFields(); setEditId(null) }}
        confirmLoading={createMut.isPending || updateMut.isPending}
        okText={editId ? '保存' : '创建'}
        cancelText="取消"
        okButtonProps={{ icon: <SaveOutlined /> }}
        cancelButtonProps={{ icon: <CloseOutlined /> }}
        width={640}
      >
        <Form form={form} layout="vertical">
          {!editId && (
            <Form.Item name="name" label="角色标识" rules={[{ required: true, min: 2, message: '至少2个字符' }]}>
              <Input placeholder="如 dba, developer" />
            </Form.Item>
          )}
          <Form.Item name="name_cn" label="中文名">
            <Input placeholder="如 全局DBA" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="角色用途说明" />
          </Form.Item>
          {editId && (
            <Form.Item name="is_active" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
          <Form.Item name="permission_codes" label="权限码">
            <Select
              mode="multiple"
              options={permOptions}
              placeholder="选择权限码"
              optionFilterProp="label"
              maxTagCount={5}
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

export default RoleManagement
