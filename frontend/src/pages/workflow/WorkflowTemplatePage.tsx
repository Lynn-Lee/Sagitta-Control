import { useMemo, useState } from 'react'
import {
  Badge,
  Button,
  Card,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import Editor from '@monaco-editor/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { approvalFlowApi, type ApprovalFlowListItem } from '@/api/approvalFlow'
import { instanceApi, type InstanceItem } from '@/api/instance'
import {
  type WorkflowTemplateCategory,
  type WorkflowTemplateItem,
  type WorkflowTemplatePayload,
  workflowTemplateApi,
} from '@/api/workflowTemplate'
import { useAuthStore } from '@/store/auth'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Title, Text, Paragraph } = Typography

type TemplateFormValues = WorkflowTemplatePayload

const normalizeTemplateText = (value?: string | null) =>
  (value || '')
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t')

const syntaxTypeOptions = [
  { value: 0, label: '未知' },
  { value: 1, label: 'DDL' },
  { value: 2, label: 'DML' },
]

export default function WorkflowTemplatePage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const canManageGlobal = Boolean(user?.is_superuser || user?.permissions?.some((p) => p === 'sql_review' || p === 'sql_execute'))

  const [search, setSearch] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewData, setPreviewData] = useState<WorkflowTemplateItem | null>(null)
  const [editId, setEditId] = useState<number | null>(null)
  const [sql, setSql] = useState('')
  const [form] = Form.useForm<TemplateFormValues>()
  const [msgApi, msgCtx] = message.useMessage()

  const { data: instances } = useQuery({
    queryKey: ['instances-for-workflow-template'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })

  const { data: categories } = useQuery({
    queryKey: ['workflow-template-categories'],
    queryFn: workflowTemplateApi.categories,
  })

  const { data: flows } = useQuery({
    queryKey: ['approval-flows-for-workflow-template'],
    queryFn: () => approvalFlowApi.list({ page_size: 200 }),
  })

  const { data, isLoading } = useQuery({
    queryKey: ['workflow-templates', search],
    queryFn: () => workflowTemplateApi.list({ search: search || undefined, page_size: 100 }),
  })

  const instanceItems = instances?.items || []
  const flowItems = flows?.items || []

  const instanceMap = useMemo(
    () => new Map<number, InstanceItem>(instanceItems.map((item) => [item.id, item])),
    [instanceItems],
  )

  const flowMap = useMemo(
    () => new Map<number, string>(flowItems.map((item: ApprovalFlowListItem) => [item.id, item.name])),
    [flowItems],
  )

  const categoryMap = useMemo(
    () => new Map<string, string>((categories?.items || []).map((item: WorkflowTemplateCategory) => [item.value, item.label])),
    [categories],
  )

  const invalidateList = () => qc.invalidateQueries({ queryKey: ['workflow-templates'] })
  const getErrorMessage = (error: unknown, fallback: string) =>
    ((error as { response?: { data?: { msg?: string } } })?.response?.data?.msg || fallback)

  const createMut = useMutation({
    mutationFn: workflowTemplateApi.create,
    onSuccess: () => {
      invalidateList()
      setModalOpen(false)
      msgApi.success('模板创建成功')
    },
    onError: (error: unknown) => msgApi.error(getErrorMessage(error, '创建失败')),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<WorkflowTemplatePayload> }) =>
      workflowTemplateApi.update(id, data),
    onSuccess: () => {
      invalidateList()
      setModalOpen(false)
      msgApi.success('模板已更新')
    },
    onError: (error: unknown) => msgApi.error(getErrorMessage(error, '更新失败')),
  })

  const deleteMut = useMutation({
    mutationFn: workflowTemplateApi.remove,
    onSuccess: () => {
      invalidateList()
      msgApi.success('模板已删除')
    },
    onError: (error: unknown) => msgApi.error(getErrorMessage(error, '删除失败')),
  })

  const useMut = useMutation<Awaited<ReturnType<typeof workflowTemplateApi.use>>, unknown, number>({
    mutationFn: workflowTemplateApi.use,
    onError: (error: unknown) => msgApi.error(getErrorMessage(error, '使用模板失败')),
  })

  const cloneMut = useMutation({
    mutationFn: workflowTemplateApi.clone,
    onSuccess: () => {
      invalidateList()
      msgApi.success('模板已复制到我的模板')
    },
    onError: (error: unknown) => msgApi.error(getErrorMessage(error, '复制失败')),
  })

  const openCreate = () => {
    setEditId(null)
    setSql('')
    form.resetFields()
    form.setFieldsValue({
      category: 'other',
      syntax_type: 0,
      is_active: true,
      visibility: canManageGlobal ? 'public' : 'private',
    })
    setModalOpen(true)
  }

  const openEdit = (record: WorkflowTemplateItem) => {
    setEditId(record.id)
    setSql(normalizeTemplateText(record.sql_content))
    form.setFieldsValue({
      template_name: record.template_name,
      category: record.category,
      description: record.description,
      scene_desc: record.scene_desc,
      risk_hint: record.risk_hint,
      rollback_hint: record.rollback_hint,
      instance_id: record.instance_id || undefined,
      db_name: record.db_name,
      flow_id: record.flow_id || undefined,
      syntax_type: record.syntax_type,
      is_active: record.is_active,
      visibility: record.visibility,
    })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (!sql.trim()) {
        msgApi.warning('SQL 模板不能为空')
        return
      }
      const payload: WorkflowTemplatePayload = {
        ...values,
        flow_id: values.flow_id || null,
        instance_id: values.instance_id || null,
        db_name: values.db_name || '',
        sql_content: sql,
      }
      if (editId) {
        updateMut.mutate({ id: editId, data: payload })
      } else {
        createMut.mutate(payload)
      }
    } catch {
      // validation error
    }
  }

  const handleUseTemplate = async (record: WorkflowTemplateItem) => {
    try {
      const res = await useMut.mutateAsync(record.id)
      const template = res.data
      navigate('/workflow/submit', {
        state: {
          template: {
            id: template.id,
            template_name: template.template_name,
            sql_content: normalizeTemplateText(template.sql_content),
            instance_id: template.instance_id,
            db_name: template.db_name,
            flow_id: template.flow_id,
            syntax_type: template.syntax_type,
            description: template.description,
            scene_desc: template.scene_desc,
            risk_hint: template.risk_hint,
            rollback_hint: template.rollback_hint,
          },
        },
      })
    } catch {
      // handled by mutation onError
    }
  }

  const columns = [
    {
      title: '模板名称',
      dataIndex: 'template_name',
      width: 220,
      render: (value: string, record: WorkflowTemplateItem) => (
        <Space direction="vertical" size={1}>
          <Text strong>{value}</Text>
          <Space size={6} wrap>
            <Tag color="blue">{categoryMap.get(record.category) || record.category}</Tag>
            {!record.is_active && <Tag>已停用</Tag>}
            {record.visibility === 'public' ? <Tag color="gold">全局模板</Tag> : <Tag>我的模板</Tag>}
          </Space>
        </Space>
      ),
    },
    {
      title: '适用场景',
      dataIndex: 'scene_desc',
      width: 220,
      ellipsis: true,
      render: (value: string) => value || <Text type="secondary">—</Text>,
    },
    {
      title: '默认实例/库',
      key: 'target',
      width: 240,
      render: (_: unknown, record: WorkflowTemplateItem) => {
        const instance = record.instance_id ? instanceMap.get(record.instance_id) : null
        return (
          <Space direction="vertical" size={0}>
            <Text>{instance ? instance.instance_name : '不指定实例'}</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {record.db_name || '不指定数据库'}
              {instance ? ` · ${formatDbTypeLabel(instance.db_type)}` : ''}
            </Text>
          </Space>
        )
      },
    },
    {
      title: '默认审批流',
      key: 'flow',
      width: 160,
      render: (_: unknown, record: WorkflowTemplateItem) =>
        record.flow_id ? flowMap.get(record.flow_id) || record.flow_name || `审批流#${record.flow_id}` : <Text type="secondary">不指定</Text>,
    },
    {
      title: 'SQL 预览',
      dataIndex: 'sql_content',
      width: 320,
      render: (value: string) => (
        <div
          style={{
            maxWidth: 300,
            overflow: 'hidden',
          }}
        >
          <Text
            code
            style={{
              display: 'block',
              fontSize: 12,
              color: '#1558A8',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              lineHeight: 1.45,
            }}
          >
            {(() => {
              const normalized = normalizeTemplateText(value)
              const previewLines = normalized.split('\n').slice(0, 3).join('\n')
              return `${previewLines}${normalized.split('\n').length > 3 || normalized.length > previewLines.length ? '\n...' : ''}`
            })()}
          </Text>
        </div>
      ),
    },
    {
      title: '创建人',
      dataIndex: 'created_by',
      width: 120,
      render: (value: string) => value || <Text type="secondary">—</Text>,
    },
    {
      title: '使用次数',
      dataIndex: 'use_count',
      width: 90,
      render: (value: number) => <Badge count={value} showZero color="#1558A8" />,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 170,
      render: (value: string) => value ? new Date(value).toLocaleString('zh-CN') : '—',
    },
    {
      title: '操作',
      width: 210,
      fixed: 'right' as const,
      render: (_: unknown, record: WorkflowTemplateItem) => (
        <Space size={4} wrap>
          <Button size="small" type="primary" icon={<CopyOutlined />} onClick={() => handleUseTemplate(record)}>
            使用
          </Button>
          <Button size="small" icon={<EyeOutlined />} onClick={() => { setPreviewData(record); setPreviewOpen(true) }}>
            预览
          </Button>
          <Button size="small" icon={<CopyOutlined />} onClick={() => cloneMut.mutate(record.id)}>
            复制
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          <Popconfirm title="确认删除此模板？" onConfirm={() => deleteMut.mutate(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      {msgCtx}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <Title level={2} style={{ margin: 0 }}>工单模板</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建模板</Button>
      </div>

      <Card
        style={{ marginBottom: 12, borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}
        styles={{ body: { padding: '12px 16px' } }}
      >
        <Input.Search
          placeholder="搜索模板名称或描述"
          allowClear
          style={{ width: 320 }}
          onSearch={setSearch}
          onChange={(e) => !e.target.value && setSearch('')}
        />
      </Card>

      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }} styles={{ body: { padding: 0 } }}>
        <Table
          dataSource={data?.items || []}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          tableLayout="fixed"
          scroll={{ x: 1700 }}
          pagination={{ total: data?.total, pageSize: 20, showSizeChanger: false }}
        />
      </Card>

      <Modal
        title={editId ? '编辑工单模板' : '新建工单模板'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={createMut.isPending || updateMut.isPending}
        width={820}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Space style={{ width: '100%', display: 'flex' }} align="start">
            <Form.Item name="template_name" label="模板名称" rules={[{ required: true }]} style={{ flex: 1.4 }}>
              <Input placeholder="如：清理 7 天前历史数据" />
            </Form.Item>
            <Form.Item name="category" label="模板分类" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select options={(categories?.items || []).map((item) => ({ value: item.value, label: item.label }))} />
            </Form.Item>
          </Space>

          <Form.Item name="description" label="模板描述">
            <Input placeholder="简要说明模板用途" />
          </Form.Item>
          <Form.Item name="scene_desc" label="适用场景">
            <Input.TextArea rows={2} placeholder="说明适合什么场景使用这份模板" />
          </Form.Item>

          <Space style={{ width: '100%', display: 'flex' }} align="start">
            <Form.Item name="instance_id" label="默认实例（可选）" style={{ flex: 1 }}>
              <Select placeholder="不指定" allowClear showSearch optionFilterProp="label">
                {instanceItems.map((instance) => (
                  <Select.Option key={instance.id} value={instance.id} label={instance.instance_name}>
                    <Tag color="blue">{formatDbTypeLabel(instance.db_type)}</Tag> {instance.instance_name}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item name="db_name" label="默认数据库（可选）" style={{ flex: 1 }}>
              <Input placeholder="不指定" />
            </Form.Item>
            <Form.Item name="flow_id" label="默认审批流（可选）" style={{ flex: 1 }}>
              <Select placeholder="不指定" allowClear>
                {flowItems.map((flow) => (
                  <Select.Option key={flow.id} value={flow.id}>{flow.name}</Select.Option>
                ))}
              </Select>
            </Form.Item>
          </Space>

          <Space style={{ width: '100%', display: 'flex' }} align="start">
            <Form.Item name="syntax_type" label="SQL 类型" style={{ flex: 1 }}>
              <Select options={syntaxTypeOptions} />
            </Form.Item>
            <Form.Item
              name="visibility"
              label="模板范围"
              style={{ flex: 1 }}
              tooltip={canManageGlobal ? '全局模板所有有权限用户可使用' : '当前账号仅支持个人模板'}
            >
              <Select disabled={!canManageGlobal}>
                {canManageGlobal && <Select.Option value="public">全局模板</Select.Option>}
                <Select.Option value="private">个人模板</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item name="is_active" label="启用状态" valuePropName="checked" style={{ flex: 1 }}>
              <Switch checkedChildren="启用" unCheckedChildren="停用" />
            </Form.Item>
          </Space>

          <Form.Item name="risk_hint" label="风险提示">
            <Input.TextArea rows={2} placeholder="说明执行风险、注意事项等" />
          </Form.Item>
          <Form.Item name="rollback_hint" label="回滚建议">
            <Input.TextArea rows={2} placeholder="说明回滚思路或回滚 SQL 建议" />
          </Form.Item>

          <Form.Item label={<span>SQL 模板 <span style={{ color: '#f5222d' }}>*</span></span>} required>
            <div style={{ border: '1px solid #d9d9d9', borderRadius: 6, overflow: 'hidden' }}>
              <Editor
                height="240px"
                defaultLanguage="sql"
                value={normalizeTemplateText(sql)}
                onChange={(value) => setSql(value || '')}
                options={{
                  fontFamily: '"JetBrains Mono", monospace',
                  fontSize: 13,
                  minimap: { enabled: false },
                  padding: { top: 8 },
                }}
              />
            </div>
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title="模板预览"
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        width={720}
      >
        {previewData && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Space wrap>
              <Title level={4} style={{ margin: 0 }}>{previewData.template_name}</Title>
              <Tag color="blue">{categoryMap.get(previewData.category) || previewData.category}</Tag>
              {previewData.visibility === 'public' ? <Tag color="gold">全局模板</Tag> : <Tag>个人模板</Tag>}
              {!previewData.is_active && <Tag>已停用</Tag>}
            </Space>
            <Paragraph type="secondary">{previewData.description || '暂无描述'}</Paragraph>
            <Card size="small" title="适用场景">
              <Paragraph style={{ marginBottom: 0 }}>{previewData.scene_desc || '—'}</Paragraph>
            </Card>
            <Card size="small" title="默认目标">
              <Paragraph style={{ marginBottom: 0 }}>
                实例：{previewData.instance_id ? instanceMap.get(previewData.instance_id)?.instance_name || `实例#${previewData.instance_id}` : '不指定'}
                <br />
                数据库：{previewData.db_name || '不指定'}
                <br />
                审批流：{previewData.flow_id ? flowMap.get(previewData.flow_id) || previewData.flow_name || `审批流#${previewData.flow_id}` : '不指定'}
              </Paragraph>
            </Card>
            <Card size="small" title="风险提示">
              <Paragraph style={{ marginBottom: 0 }}>{previewData.risk_hint || '—'}</Paragraph>
            </Card>
            <Card size="small" title="回滚建议">
              <Paragraph style={{ marginBottom: 0 }}>{previewData.rollback_hint || '—'}</Paragraph>
            </Card>
            <Card size="small" title="SQL 示例">
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {normalizeTemplateText(previewData.sql_content)}
              </pre>
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  )
}
