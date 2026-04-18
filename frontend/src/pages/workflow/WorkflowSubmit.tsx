import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Empty, Form, Input, List, Modal, Select, Space, Switch, Typography, message, Alert, Table, Tag } from 'antd'
import Editor from '@monaco-editor/react'
import { CopyOutlined, RobotOutlined, SaveOutlined } from '@ant-design/icons'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { instanceApi, type InstanceDatabase, type InstanceItem } from '@/api/instance'
import { approvalFlowApi, type ApprovalFlowListItem } from '@/api/approvalFlow'
import { workflowApi } from '@/api/workflow'
import { useAuthStore } from '@/store/auth'
import apiClient from '@/api/client'
import { formatDbTypeLabel } from '@/utils/dbType'
import {
  workflowTemplateApi,
  type WorkflowTemplateCategory,
  type WorkflowTemplateItem,
} from '@/api/workflowTemplate'

const { Title, Text } = Typography
const { Option } = Select

type SubmitTemplateFormValues = {
  template_name: string
  category: string
  description?: string
  scene_desc?: string
  risk_hint?: string
  rollback_hint?: string
  instance_id?: number
  db_name?: string
  flow_id?: number
  sql_content: string
  syntax_type: number
  visibility: 'public' | 'private'
  is_active: boolean
}

const normalizeTemplateText = (value?: string | null) =>
  (value || '')
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t')

export default function WorkflowSubmit() {
  const navigate = useNavigate()
  const location = useLocation()
  const [form] = Form.useForm()
  const [templateForm] = Form.useForm()
  const user = useAuthStore((state) => state.user)
  const canManageGlobal =
    !!user?.is_superuser || !!user?.permissions?.some((perm) => perm === 'sql_review' || perm === 'sql_execute')
  const [sql, setSql] = useState('')
  const [instanceId, setInstanceId] = useState<number | undefined>()
  const [dbName, setDbName] = useState<string>('')
  const [syntaxType, setSyntaxType] = useState(0)
  const [checkResults, setCheckResults] = useState<Array<{ id: number; sql: string; errlevel: number; msg: string }>>([])
  const [checking, setChecking] = useState(false)
  const [aiInput, setAiInput] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [aiModalOpen, setAiModalOpen] = useState(false)
  const [aiError, setAiError] = useState('')
  const [templatePickerOpen, setTemplatePickerOpen] = useState(false)
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false)
  const [templateSearch, setTemplateSearch] = useState('')
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [prefilledTemplateId, setPrefilledTemplateId] = useState<number | null>(null)

  const handleAiGenerate = async () => {
    if (!aiInput.trim()) return
    setAiLoading(true); setAiError('')
    try {
      const r = await apiClient.post('/ai/text2sql/', {
        question: aiInput,
        instance_id: instanceId,
        db_name: dbName,
      })
      setSql(r.data.sql || '')
      setAiModalOpen(false)
      setAiInput('')
      msgApi.success('SQL 已生成，请检查后提交')
    } catch (error: unknown) {
      const err = error as { response?: { data?: { msg?: string } } }
      setAiError(err.response?.data?.msg || 'AI 生成失败，请检查配置')
    } finally { setAiLoading(false) }
  }
  const [msgApi, msgCtx] = message.useMessage()

  const templateState = (location.state as { template?: WorkflowTemplateItem } | null)?.template

  const { data: instanceData } = useQuery({
    queryKey: ['instances-for-workflow'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })
  const { data: dbData } = useQuery({
    queryKey: ['registered-databases', instanceId],
    queryFn: () => instanceApi.listRegisteredDbs(instanceId!),
    enabled: !!instanceId,
  })
  const { data: flowData } = useQuery({
    queryKey: ['approval-flows-for-workflow'],
    queryFn: () => approvalFlowApi.list(),
  })
  const { data: templateData, isLoading: templatesLoading } = useQuery({
    queryKey: ['workflow-templates-for-submit', templateSearch],
    queryFn: () =>
      workflowTemplateApi.list({
        search: templateSearch || undefined,
        is_active: true,
        page_size: 100,
      }),
  })
  const { data: templateCategoryData } = useQuery({
    queryKey: ['workflow-template-categories'],
    queryFn: workflowTemplateApi.categories,
  })
  const submitMut = useMutation({
    mutationFn: workflowApi.create,
    onSuccess: (data: { data: { id: number } }) => {
      msgApi.success('工单提交成功')
      setTimeout(() => navigate(`/workflow/${data.data.id}`), 1000)
    },
    onError: (error: unknown) => {
      const err = error as { response?: { data?: { msg?: string } } }
      msgApi.error(err.response?.data?.msg || '提交失败')
    },
  })
  const useTemplateMut = useMutation({
    mutationFn: (templateId: number) => workflowTemplateApi.use(templateId),
    onError: (error: unknown) => {
      const err = error as { response?: { data?: { msg?: string } } }
      msgApi.error(err.response?.data?.msg || '应用模板失败')
    },
  })
  const saveTemplateMut = useMutation({
    mutationFn: workflowTemplateApi.create,
    onSuccess: () => {
      msgApi.success('模板保存成功')
      setSaveTemplateOpen(false)
      templateForm.resetFields()
    },
    onError: (error: unknown) => {
      const err = error as { response?: { data?: { msg?: string } } }
      msgApi.error(err.response?.data?.msg || '模板保存失败')
    },
  })

  const instanceItems = instanceData?.items || []
  const dbItems = (dbData?.items || []) as InstanceDatabase[]
  const flowItems = (flowData?.items || []) as ApprovalFlowListItem[]
  const templateCategories = (templateCategoryData?.items || []) as WorkflowTemplateCategory[]
  const templateItems = (templateData?.items || []) as WorkflowTemplateItem[]
  const instanceMap = useMemo(
    () => new Map<number, InstanceItem>(instanceItems.map((item) => [item.id, item])),
    [instanceItems]
  )
  const flowMap = useMemo(
    () => new Map<number, string>(flowItems.map((item) => [item.id, item.name])),
    [flowItems]
  )
  const templateCategoryMap = useMemo(
    () => new Map<string, string>(templateCategories.map((item) => [item.value, item.label])),
    [templateCategories]
  )
  const selectedTemplate = useMemo(
    () => templateItems.find((template) => template.id === selectedTemplateId) || null,
    [selectedTemplateId, templateItems]
  )

  const applyTemplateToForm = (template: WorkflowTemplateItem) => {
    form.setFieldsValue({
      workflow_name: template.template_name,
      flow_id: template.flow_id || undefined,
    })
    setSql(normalizeTemplateText(template.sql_content))
    setInstanceId(template.instance_id || undefined)
    setDbName(template.db_name || '')
    setSyntaxType(template.syntax_type ?? 0)
  }

  useEffect(() => {
    if (templateState?.id && templateState.id !== prefilledTemplateId) {
      applyTemplateToForm(templateState)
      setPrefilledTemplateId(templateState.id)
      msgApi.success(`已载入模板：${templateState.template_name}`)
    }
  }, [templateState, prefilledTemplateId, form, msgApi])

  const handleOpenSaveTemplate = () => {
    const workflowName = form.getFieldValue('workflow_name') || ''
    const flowId = form.getFieldValue('flow_id')
    templateForm.setFieldsValue({
      template_name: workflowName,
      category: 'other',
      description: '',
      scene_desc: '',
      risk_hint: '',
      rollback_hint: '',
      instance_id: instanceId,
      db_name: dbName,
      flow_id: flowId,
      sql_content: sql,
      syntax_type: syntaxType,
      visibility: canManageGlobal ? 'public' : 'private',
      is_active: true,
    })
    setSaveTemplateOpen(true)
  }

  const handleApplySelectedTemplate = async () => {
    if (!selectedTemplate) {
      msgApi.warning('请先选择一个模板')
      return
    }
    await useTemplateMut.mutateAsync(selectedTemplate.id)
    applyTemplateToForm(selectedTemplate)
    setTemplatePickerOpen(false)
    msgApi.success(`已载入模板：${selectedTemplate.template_name}`)
  }

  const handleSaveTemplate = async () => {
    try {
      const values = await templateForm.validateFields()
      if (!values.instance_id || !values.db_name) {
        msgApi.warning('保存模板前请先选择实例和数据库')
        return
      }
      if (!values.sql_content?.trim()) {
        msgApi.warning('模板 SQL 内容不能为空')
        return
      }
      await saveTemplateMut.mutateAsync(values)
    } catch {
      // validation
    }
  }

  const handleCheck = async () => {
    if (!instanceId || !dbName || !sql.trim()) {
      msgApi.warning('请先选择实例、数据库并输入 SQL')
      return
    }
    setChecking(true)
    try {
      const res = await workflowApi.check({ instance_id: instanceId, db_name: dbName, sql_content: sql })
      setCheckResults(res.data || [])
    } catch (error: unknown) {
      const err = error as { response?: { data?: { msg?: string } } }
      msgApi.error(err.response?.data?.msg || '预检查失败')
    } finally {
      setChecking(false)
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (!instanceId || !dbName) {
        msgApi.warning('请先选择实例和数据库')
        return
      }
      if (!sql.trim()) { msgApi.warning('SQL 内容不能为空'); return }
      submitMut.mutate({
        ...values,
        sql_content: sql,
        instance_id: instanceId,
        db_name: dbName,
        syntax_type: syntaxType,
      })
    } catch { /* validation */ }
  }

  const checkColumns = [
    { title: '#', dataIndex: 'id', width: 50 },
    { title: 'SQL', dataIndex: 'sql', ellipsis: true },
    { title: '级别', dataIndex: 'errlevel', width: 80,
      render: (v: number) => v === 0 ? <Tag color="success">OK</Tag> : v === 1 ? <Tag color="warning">警告</Tag> : <Tag color="error">错误</Tag> },
    { title: '信息', dataIndex: 'msg', ellipsis: true },
  ]

  return (
    <div>
      {msgCtx}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <Title level={2} style={{ margin: 0 }}>提交 SQL 工单</Title>
        <Space>
          <Button icon={<CopyOutlined />} onClick={() => setTemplatePickerOpen(true)}>
            从模板创建
          </Button>
          <Button icon={<SaveOutlined />} onClick={handleOpenSaveTemplate}>
            保存为模板
          </Button>
        </Space>
      </div>
      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)', marginBottom: 16 }}>
        <Form form={form} layout="vertical">
          <Form.Item name="workflow_name" label="工单名称" rules={[{ required: true }]}>
            <Input placeholder="简明描述本次变更内容" />
          </Form.Item>
          <Space style={{ width: '100%', display: 'flex' }} align="start">
            <Form.Item label="实例" style={{ flex: 1 }} required>
              <Select placeholder="选择实例" onChange={(v) => { setInstanceId(v); setDbName('') }}
                showSearch optionFilterProp="label" popupMatchSelectWidth={false}>
                {instanceItems.map((i) => (
                  <Option key={i.id} value={i.id} label={i.instance_name} title={i.instance_name}>
                    <Tag color="blue">{formatDbTypeLabel(i.db_type)}</Tag> {i.instance_name}
                  </Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item label="数据库" style={{ flex: 1 }} required>
              <Select
                  placeholder={!instanceId ? "请先选择实例" : dbData?.items?.length === 0 ? "该实例暂无注册数据库，请在实例管理中添加" : "选择数据库"}
                  value={dbName || undefined}
                  onChange={setDbName}
                  disabled={!instanceId}
                  showSearch
                  popupMatchSelectWidth={false}
                  optionFilterProp="children"
                  notFoundContent={<Text type="secondary" style={{fontSize:12}}>暂无数据库，请在实例管理→数据库管理中添加</Text>}
                >
{dbItems.map((d) => (
                    <Option key={d.db_name} value={d.db_name} title={d.db_name}>
                      {d.db_name}{!d.is_active && <Tag color="default" style={{marginLeft: 4, fontSize: 10}}>已禁用</Tag>}{d.remark ? <Text type="secondary" style={{fontSize:11}}> ({d.remark})</Text> : ''}
                    </Option>
                  ))}
              </Select>
            </Form.Item>
          </Space>
          <Form.Item name="flow_id" label="审批流" rules={[{ required: true, message: '请选择审批流' }]}>
            <Select placeholder="选择审批流模板">
              {flowItems.map((flow) => (
                <Option key={flow.id} value={flow.id}>{flow.name}</Option>
              ))}
            </Select>
          </Form.Item>
          <Alert
            type="info"
            showIcon
            message="资源组已按你的用户组权限自动解析"
            description="提交工单时只需选择自己可访问的实例和数据库。系统会根据“用户组 → 资源组 → 实例”的权限链路自动绑定资源组。"
            style={{ marginTop: 4 }}
          />
        </Form>
      </Card>

      <Card title="SQL 内容" style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)', marginBottom: 16 }}
        styles={{ body: { padding: 0 } }}
        extra={
          <Space>
            <Button size="small" icon={<RobotOutlined />} onClick={() => setAiModalOpen(true)}>
              AI 生成 SQL
            </Button>
            <Button size="small" loading={checking} onClick={handleCheck}>SQL 预检查</Button>
          </Space>
        }>
        <Editor height="300px" defaultLanguage="sql" value={sql}
          onChange={(v) => setSql(v || '')}
          options={{ fontFamily: '"JetBrains Mono", Menlo, monospace', fontSize: 13, minimap: { enabled: false }, padding: { top: 12 } }} />
      </Card>

      {checkResults.length > 0 && (
        <Card title="预检查结果" style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)', marginBottom: 16 }}
          styles={{ body: { padding: 0 } }}>
          <Table dataSource={checkResults} columns={checkColumns} rowKey="id" size="small"
            tableLayout="fixed" scroll={{ x: 900 }} pagination={false} />
        </Card>
      )}

      <Space>
        <Button type="primary" loading={submitMut.isPending} onClick={handleSubmit}>提交工单</Button>
        <Button onClick={() => navigate('/workflow')}>取消</Button>
      </Space>


      <Modal
        title="从模板创建工单"
        open={templatePickerOpen}
        onOk={handleApplySelectedTemplate}
        onCancel={() => setTemplatePickerOpen(false)}
        okText="使用模板"
        okButtonProps={{ loading: useTemplateMut.isPending }}
        width={980}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          <Input.Search
            allowClear
            placeholder="搜索模板名称或描述"
            value={templateSearch}
            onChange={(e) => setTemplateSearch(e.target.value)}
          />
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.1fr) minmax(320px, 0.9fr)', gap: 16 }}>
            <div style={{ border: '1px solid rgba(0,0,0,0.08)', borderRadius: 12, minHeight: 420 }}>
              <List
                loading={templatesLoading}
                dataSource={templateItems}
                locale={{ emptyText: <Empty description="暂无可用模板" /> }}
                renderItem={(item) => {
                  const active = item.id === selectedTemplateId
                  return (
                    <List.Item
                      onClick={() => setSelectedTemplateId(item.id)}
                      style={{
                        cursor: 'pointer',
                        padding: 16,
                        background: active ? 'rgba(37,99,235,0.06)' : '#fff',
                        borderInlineStart: active ? '3px solid #2563eb' : '3px solid transparent',
                      }}
                    >
                      <Space direction="vertical" size={6} style={{ width: '100%' }}>
                        <Space wrap>
                          <Text strong>{item.template_name}</Text>
                          <Tag color="blue">{templateCategoryMap.get(item.category) || item.category}</Tag>
                          <Tag color={item.visibility === 'public' ? 'green' : 'default'}>
                            {item.visibility === 'public' ? '全局模板' : '个人模板'}
                          </Tag>
                        </Space>
                        {item.description ? <Text type="secondary">{item.description}</Text> : null}
                        <Space size={12} wrap>
                          {item.instance_id ? (
                            <Text type="secondary">
                              实例：{instanceMap.get(item.instance_id)?.instance_name || `实例#${item.instance_id}`}
                            </Text>
                          ) : null}
                          {item.db_name ? <Text type="secondary">数据库：{item.db_name}</Text> : null}
                          {(item.flow_id || item.flow_name) ? (
                            <Text type="secondary">
                              审批流：{item.flow_id ? flowMap.get(item.flow_id) || item.flow_name || `审批流#${item.flow_id}` : item.flow_name}
                            </Text>
                          ) : null}
                        </Space>
                      </Space>
                    </List.Item>
                  )
                }}
              />
            </div>
            <Card title="模板预览" size="small" style={{ borderRadius: 12 }}>
              {selectedTemplate ? (
                <Space direction="vertical" size={14} style={{ width: '100%' }}>
                  <Space wrap>
                    <Text strong style={{ fontSize: 16 }}>{selectedTemplate.template_name}</Text>
                    <Tag color={selectedTemplate.is_active ? 'success' : 'default'}>
                      {selectedTemplate.is_active ? '启用' : '停用'}
                    </Tag>
                  </Space>
                  {selectedTemplate.scene_desc ? (
                    <div>
                      <Text strong>适用场景</Text>
                      <div style={{ marginTop: 6 }}>
                        <Text type="secondary">{selectedTemplate.scene_desc}</Text>
                      </div>
                    </div>
                  ) : null}
                  <div>
                    <Text strong>默认配置</Text>
                    <div style={{ marginTop: 8 }}>
                      <Space direction="vertical" size={6}>
                        <Text>
                          实例：{selectedTemplate.instance_id ? instanceMap.get(selectedTemplate.instance_id)?.instance_name || `实例#${selectedTemplate.instance_id}` : '未指定'}
                        </Text>
                        <Text>数据库：{selectedTemplate.db_name || '未指定'}</Text>
                        <Text>
                          审批流：{selectedTemplate.flow_id ? flowMap.get(selectedTemplate.flow_id) || selectedTemplate.flow_name || `审批流#${selectedTemplate.flow_id}` : selectedTemplate.flow_name || '未指定'}
                        </Text>
                      </Space>
                    </div>
                  </div>
                  {selectedTemplate.risk_hint ? (
                    <Alert type="warning" showIcon message="风险提示" description={selectedTemplate.risk_hint} />
                  ) : null}
                  {selectedTemplate.rollback_hint ? (
                    <Alert type="info" showIcon message="回滚建议" description={selectedTemplate.rollback_hint} />
                  ) : null}
                  <div>
                    <Text strong>SQL 示例</Text>
                    <div
                      style={{
                        marginTop: 8,
                        maxHeight: 220,
                        overflow: 'auto',
                        padding: 12,
                        background: '#111827',
                        borderRadius: 12,
                      }}
                    >
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap', color: '#e5e7eb', fontSize: 12 }}>
                    {normalizeTemplateText(selectedTemplate.sql_content) || '-- 无 SQL 内容 --'}
                  </pre>
                    </div>
                  </div>
                </Space>
              ) : (
                <Empty description="选择左侧模板后查看预览" />
              )}
            </Card>
          </div>
        </Space>
      </Modal>

      <Modal
        title="保存当前工单为模板"
        open={saveTemplateOpen}
        onOk={handleSaveTemplate}
        onCancel={() => setSaveTemplateOpen(false)}
        okText="保存模板"
        okButtonProps={{ loading: saveTemplateMut.isPending }}
        width={760}
      >
        <Form<SubmitTemplateFormValues> form={templateForm} layout="vertical">
          <Form.Item name="template_name" label="模板名称" rules={[{ required: true, message: '请输入模板名称' }]}>
            <Input placeholder="例如：清理历史订单数据" />
          </Form.Item>
          <Space style={{ width: '100%', display: 'flex' }} align="start">
            <Form.Item
              name="category"
              label="模板分类"
              rules={[{ required: true, message: '请选择模板分类' }]}
              style={{ flex: 1 }}
            >
              <Select options={templateCategories.map((category) => ({ value: category.value, label: category.label }))} />
            </Form.Item>
            <Form.Item name="visibility" label="模板范围" style={{ flex: 1 }}>
              <Select disabled={!canManageGlobal}>
                {canManageGlobal ? <Option value="public">全局模板</Option> : null}
                <Option value="private">个人模板</Option>
              </Select>
            </Form.Item>
            <Form.Item name="is_active" label="启用状态" valuePropName="checked" style={{ width: 140 }}>
              <Switch checkedChildren="启用" unCheckedChildren="停用" />
            </Form.Item>
          </Space>
          <Form.Item name="description" label="模板描述">
            <Input.TextArea rows={2} placeholder="简要描述模板用途" />
          </Form.Item>
          <Form.Item name="scene_desc" label="适用场景">
            <Input.TextArea rows={2} placeholder="说明这个模板适合什么场景使用" />
          </Form.Item>
          <Space style={{ width: '100%', display: 'flex' }} align="start">
            <Form.Item name="instance_id" label="默认实例" style={{ flex: 1 }}>
              <Select allowClear placeholder="可选，默认带入工单实例">
                {instanceItems.map((instance) => (
                  <Option key={instance.id} value={instance.id}>
                    {instance.instance_name}
                  </Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item name="db_name" label="默认数据库" style={{ flex: 1 }}>
              <Input placeholder="可选，默认带入工单数据库" />
            </Form.Item>
            <Form.Item name="flow_id" label="默认审批流" style={{ flex: 1 }}>
              <Select allowClear placeholder="可选，默认带入审批流">
                {flowItems.map((flow) => (
                  <Option key={flow.id} value={flow.id}>
                    {flow.name}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Space>
          <Form.Item name="risk_hint" label="风险提示">
            <Input.TextArea rows={2} placeholder="例如：高峰期执行可能引发锁等待，请提前备份" />
          </Form.Item>
          <Form.Item name="rollback_hint" label="回滚建议">
            <Input.TextArea rows={2} placeholder="例如：执行前先备份目标数据；必要时回滚至备份表" />
          </Form.Item>
          <Form.Item name="sql_content" label="SQL 示例" rules={[{ required: true, message: 'SQL 示例不能为空' }]}>
            <Input.TextArea rows={8} placeholder="模板 SQL 会在提单时自动带入，可进一步修改" />
          </Form.Item>
          <Form.Item name="syntax_type" hidden>
            <Input type="hidden" />
          </Form.Item>
        </Form>
      </Modal>

      {/* AI Text2SQL Modal */}
      <Modal title={<Space><RobotOutlined />AI 自然语言生成 SQL</Space>}
        open={aiModalOpen} onOk={handleAiGenerate} onCancel={() => setAiModalOpen(false)}
        confirmLoading={aiLoading} okText="生成 SQL">
        <div style={{ marginTop: 16 }}>
          <div style={{ marginBottom: 8 }}>
            <Typography.Text>描述你想执行的操作：</Typography.Text>
          </div>
          <Input.TextArea rows={4} value={aiInput} onChange={e => setAiInput(e.target.value)}
            placeholder="如：查询最近7天每天的工单数量，按日期排序" />
          {aiError && <Alert type="error" message={aiError} style={{ marginTop: 8 }} showIcon />}
          <Alert type="info" showIcon style={{ marginTop: 12 }}
            message="AI 生成的 SQL 仅供参考，请务必检查后再提交" />
        </div>
      </Modal>
    </div>
  )
}
