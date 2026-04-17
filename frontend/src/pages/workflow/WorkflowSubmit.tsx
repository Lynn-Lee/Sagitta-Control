import { useState } from 'react'
import { Button, Card, Form, Input, Modal, Select, Space, Typography, message, Alert, Table, Tag } from 'antd'
import Editor from '@monaco-editor/react'
import { RobotOutlined } from '@ant-design/icons'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { instanceApi } from '@/api/instance'
import { approvalFlowApi } from '@/api/approvalFlow'
import { workflowApi } from '@/api/workflow'
import apiClient from '@/api/client'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Title, Text } = Typography
const { Option } = Select

export default function WorkflowSubmit() {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [sql, setSql] = useState('')
  const [instanceId, setInstanceId] = useState<number | undefined>()
  const [dbName, setDbName] = useState<string>('')
  const [checkResults, setCheckResults] = useState<any[]>([])
  const [checking, setChecking] = useState(false)
  const [aiInput, setAiInput] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [aiModalOpen, setAiModalOpen] = useState(false)
  const [aiError, setAiError] = useState('')

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
    } catch (e: any) {
      setAiError(e.response?.data?.msg || 'AI 生成失败，请检查配置')
    } finally { setAiLoading(false) }
  }
  const [msgApi, msgCtx] = message.useMessage()

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
  const submitMut = useMutation({
    mutationFn: workflowApi.create,
    onSuccess: (data: { data: { id: number } }) => {
      msgApi.success('工单提交成功')
      setTimeout(() => navigate(`/workflow/${data.data.id}`), 1000)
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '提交失败'),
  })

  const handleCheck = async () => {
    if (!instanceId || !dbName || !sql.trim()) {
      msgApi.warning('请先选择实例、数据库并输入 SQL')
      return
    }
    setChecking(true)
    try {
      const res = await workflowApi.check({ instance_id: instanceId, db_name: dbName, sql_content: sql })
      setCheckResults(res.data || [])
    } catch (e: any) {
      msgApi.error(e.response?.data?.msg || '预检查失败')
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
      submitMut.mutate({ ...values, sql_content: sql, instance_id: instanceId, db_name: dbName })
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
                {instanceData?.items?.map((i: any) => (
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
{(dbData?.items || []).map((d: any) => (
                    <Option key={d.db_name} value={d.db_name} title={d.db_name}>
                      {d.db_name}{!d.is_active && <Tag color="default" style={{marginLeft: 4, fontSize: 10}}>已禁用</Tag>}{d.remark ? <Text type="secondary" style={{fontSize:11}}> ({d.remark})</Text> : ''}
                    </Option>
                  ))}
              </Select>
            </Form.Item>
          </Space>
          <Form.Item name="flow_id" label="审批流" rules={[{ required: true, message: '请选择审批流' }]}>
            <Select placeholder="选择审批流模板">
              {(flowData?.items || flowData || []).map((flow: any) => (
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
