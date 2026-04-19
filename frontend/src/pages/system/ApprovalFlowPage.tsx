import { useState } from 'react'
import {
  Button, Card, Col, Drawer, Form, Input, Popconfirm,
  Row, Select, Space, Table, Tag, Tooltip, Typography, message, Grid,
} from 'antd'
import {
  PlusOutlined, EditOutlined, StopOutlined,
  ApartmentOutlined, HolderOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { approvalFlowApi, type ApprovalFlowNode } from '@/api/approvalFlow'
import { userApi } from '@/api/system'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'

const { Text } = Typography
const { useBreakpoint } = Grid

const APPROVER_TYPE_LABELS: Record<string, string> = {
  users:        '指定用户',
  manager:      '直属上级',
  any_reviewer: '任意审批员',
}

const APPROVER_TYPE_COLORS: Record<string, string> = {
  users:        'blue',
  manager:      'cyan',
  any_reviewer: 'orange',
}

export default function ApprovalFlowPage() {
  const qc = useQueryClient()
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const [drawerOpen, setDrawerOpen]   = useState(false)
  const [editId, setEditId]           = useState<number | null>(null)
  const [search, setSearch]           = useState('')
  const [form] = Form.useForm()
  const [msgApi, msgCtx] = message.useMessage()

  // ── Data queries ────────────────────────────────────────────
  const { data, isLoading } = useQuery({
    queryKey: ['approval-flows', search],
    queryFn: () => approvalFlowApi.list({ search: search || undefined, page_size: 100 }),
  })

  const { data: allUsers } = useQuery({
    queryKey: ['all-users-for-flow'],
    queryFn: () => userApi.list({ page_size: 200, is_active: true }),
    enabled: drawerOpen,
  })

  // ── Mutations ───────────────────────────────────────────────
  const createMut = useMutation({
    mutationFn: approvalFlowApi.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-flows'] })
      setDrawerOpen(false)
      msgApi.success('审批流已创建')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '创建失败'),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => approvalFlowApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-flows'] })
      setDrawerOpen(false)
      msgApi.success('审批流已更新')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '更新失败'),
  })

  const deactivateMut = useMutation({
    mutationFn: approvalFlowApi.deactivate,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-flows'] })
      msgApi.success('已停用')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '操作失败'),
  })

  // ── Handlers ────────────────────────────────────────────────
  const openCreate = () => {
    setEditId(null)
    form.resetFields()
    form.setFieldsValue({
      nodes: [{ order: 1, node_name: '一级审批', approver_type: 'any_reviewer', approver_ids: [] }],
    })
    setDrawerOpen(true)
  }

  const openEdit = async (id: number) => {
    const flow = await approvalFlowApi.get(id)
    setEditId(id)
    form.setFieldsValue({
      name:        flow.name,
      description: flow.description,
      nodes:       flow.nodes.map((n: ApprovalFlowNode) => ({
        order:         n.order,
        node_name:     n.node_name,
        approver_type: n.approver_type,
        approver_ids:  n.approver_ids,
      })),
    })
    setDrawerOpen(true)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      // Reassign order by array index to keep it sequential
      const nodes = (values.nodes || []).map((n: ApprovalFlowNode, i: number) => ({
        ...n,
        order: i + 1,
        approver_ids: n.approver_ids ?? [],
      }))
      const payload = { ...values, nodes }
      editId
        ? updateMut.mutate({ id: editId, data: payload })
        : createMut.mutate(payload)
    } catch { /* form validation */ }
  }

  // ── Table columns ────────────────────────────────────────────
  const columns = [
    {
      title: '审批流名称', key: 'name', width: 260,
      render: (_: unknown, r: any) => (
        <Space direction="vertical" size={0}>
          <Space>
            <ApartmentOutlined style={{ color: '#165DFF' }} />
            <Text strong>{r.name}</Text>
          </Space>
          {r.description && <Text type="secondary" style={{ fontSize: 12 }}>{r.description}</Text>}
        </Space>
      ),
    },
    {
      title: '审批节点数', dataIndex: 'node_count', key: 'node_count', width: 110,
      render: (v: number) => <Tag color="blue">{v} 级</Tag>,
    },
    {
      title: '节点类型', key: 'node_types', width: 260,
      render: (_: unknown, r: any) => {
        const nodes = r.nodes || []
        if (!nodes.length) return <Text type="secondary">未配置</Text>
        const labels = Array.from(new Set(nodes.map((n: ApprovalFlowNode) => APPROVER_TYPE_LABELS[n.approver_type] || n.approver_type)))
        return (
          <Space wrap size={[4, 4]}>
            {labels.map((label: string) => <Tag key={label}>{label}</Tag>)}
          </Space>
        )
      },
    },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => <Tag color={v ? 'success' : 'default'}>{v ? '启用' : '停用'}</Tag>,
    },
    {
      title: '创建人', dataIndex: 'created_by', key: 'created_by', width: 120,
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (value: string) => value ? new Date(value).toLocaleString('zh-CN') : '—',
    },
    {
      title: '操作', key: 'actions', width: 140,
      render: (_: unknown, r: any) => (
        <Space>
          <Tooltip title="编辑">
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r.id)} />
          </Tooltip>
          {r.is_active && (
            <Popconfirm
              title="停用后，已使用该审批流的工单不受影响，新工单将无法选择此流程。确认停用？"
              onConfirm={() => deactivateMut.mutate(r.id)}
              okText="停用" cancelText="取消" okButtonProps={{ danger: true }}
            >
              <Tooltip title="停用">
                <Button size="small" danger icon={<StopOutlined />} />
              </Tooltip>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const userOptions  = (allUsers?.items  || []).map((u: any) => ({ label: `${u.username}${u.display_name ? ` (${u.display_name})` : ''}`, value: u.id }))
  const isSaving = createMut.isPending || updateMut.isPending

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="审批流管理"
        actions={(
          <Space wrap size={[8, 8]} style={isMobile ? { display: 'flex', width: '100%' } : undefined}>
            <Input.Search
              placeholder="搜索审批流名称"
              allowClear
              style={{ width: isMobile ? '100%' : 220 }}
              onSearch={v => setSearch(v)}
              onChange={e => !e.target.value && setSearch('')}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}
              style={isMobile ? { width: '100%' } : undefined}>
              新建审批流
            </Button>
          </Space>
        )}
      />

      <Card bordered={false} bodyStyle={{ padding: 0 }}>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={data?.items || []}
          loading={isLoading}
          locale={{ emptyText: <TableEmptyState title="暂无审批流数据" /> }}
          tableLayout="fixed"
          scroll={{ x: 1100 }}
          pagination={{ pageSize: 20, showSizeChanger: false, showTotal: t => `共 ${t} 条` }}
        />
      </Card>

      {/* ── Create / Edit Drawer ── */}
      <Drawer
        title={editId ? '编辑审批流' : '新建审批流'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={640}
        footer={
          <Space style={{ float: 'right' }}>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" loading={isSaving} onClick={handleSubmit}>保存</Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name" label="审批流名称"
            rules={[{ required: true, message: '请输入名称' }, { max: 64 }]}
          >
            <Input placeholder="例如：DBA 二级审批流" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="可选" />
          </Form.Item>

          <Form.Item label="审批节点" style={{ marginBottom: 0 }}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
              节点按顺序逐级审批，所有节点通过后工单才会进入执行队列。
            </Text>
          </Form.Item>

          <Form.List name="nodes">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field, index) => (
                  <Card
                    key={field.key}
                    size="small"
                    style={{ marginBottom: 12, background: '#fafafa' }}
                    title={
                      <Space>
                        <HolderOutlined style={{ color: '#8c8c8c' }} />
                        <Text strong>第 {index + 1} 级审批节点</Text>
                      </Space>
                    }
                    extra={
                      fields.length > 1 && (
                        <Button
                          type="link" danger size="small"
                          onClick={() => remove(field.name)}
                        >
                          删除
                        </Button>
                      )
                    }
                  >
                    <Row gutter={12}>
                      <Col span={12}>
                        <Form.Item
                          {...field}
                          name={[field.name, 'node_name']}
                          label="节点名称"
                          rules={[{ required: true, message: '必填' }]}
                        >
                          <Input placeholder="例如：DBA 审批" />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item
                          {...field}
                          name={[field.name, 'approver_type']}
                          label="审批人类型"
                          rules={[{ required: true, message: '必填' }]}
                        >
                          <Select
                            options={Object.entries(APPROVER_TYPE_LABELS).map(([k, v]) => ({ value: k, label: v }))}
                            onChange={() => {
                              const nodes = form.getFieldValue('nodes')
                              nodes[index].approver_ids = []
                              form.setFieldsValue({ nodes })
                            }}
                          />
                        </Form.Item>
                      </Col>
                    </Row>

                    <Form.Item
                      noStyle
                      shouldUpdate={(prev, next) =>
                        prev.nodes?.[index]?.approver_type !== next.nodes?.[index]?.approver_type
                      }
                    >
                      {() => {
                        const type = form.getFieldValue(['nodes', index, 'approver_type'])
                        if (type === 'any_reviewer') {
                          return (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              拥有 <Tag color="orange">sql_review</Tag> 权限的任意用户均可审批
                            </Text>
                          )
                        }
                        if (type === 'manager') {
                          return (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              自动使用申请人的直属上级作为审批人
                            </Text>
                          )
                        }
                        return (
                          <Form.Item
                            {...field}
                            name={[field.name, 'approver_ids']}
                            label="指定审批用户"
                            rules={[{ required: true, type: 'array', min: 1, message: '请至少选择一项' }]}
                          >
                            <Select
                              mode="multiple"
                              allowClear
                              showSearch
                              optionFilterProp="label"
                              placeholder="选择用户"
                              options={userOptions}
                            />
                          </Form.Item>
                        )
                      }}
                    </Form.Item>

                    {/* Tag preview */}
                    <Form.Item
                      noStyle
                      shouldUpdate={(prev, next) =>
                        prev.nodes?.[index]?.approver_type !== next.nodes?.[index]?.approver_type
                      }
                    >
                      {() => {
                        const type = form.getFieldValue(['nodes', index, 'approver_type'])
                        return (
                          <Tag color={APPROVER_TYPE_COLORS[type] || 'default'} style={{ marginTop: 4 }}>
                            {APPROVER_TYPE_LABELS[type] || type}
                          </Tag>
                        )
                      }}
                    </Form.Item>
                  </Card>
                ))}

                <Button
                  type="dashed"
                  block
                  icon={<PlusOutlined />}
                  onClick={() =>
                    add({
                      order: fields.length + 1,
                      node_name: `第 ${fields.length + 1} 级审批`,
                      approver_type: 'any_reviewer',
                      approver_ids: [],
                    })
                  }
                >
                  添加审批节点
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Drawer>
    </div>
  )
}
