import { useState } from 'react'
import {
  Alert, Button, Form, Input, InputNumber, Modal, Popconfirm,
  Select, Space, Switch, Table, Tag, Typography, message,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, EyeOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { instanceApi } from '@/api/instance'
import apiClient from '@/api/client'
import PageHeader from '@/components/common/PageHeader'
import SectionCard from '@/components/common/SectionCard'
import TableEmptyState from '@/components/common/TableEmptyState'

const { Text } = Typography
const { Option } = Select

const RULE_TYPE_COLORS: Record<string, string> = {
  email: 'blue', phone: 'green', card: 'orange', id_card: 'red',
  name: 'purple', address: 'cyan', regex: 'geekblue',
}

function PreviewPanel({ form }: { form: any }) {
  const [previewValue, setPreviewValue] = useState('13812345678')
  const [previewResult, setPreviewResult] = useState<{ original: string; masked: string } | null>(null)
  const [loading, setLoading] = useState(false)

  const handlePreview = async () => {
    const vals = form.getFieldsValue()
    setLoading(true)
    try {
      const r = await apiClient.post('/masking/preview/', {
        value: previewValue,
        rule_type: vals.rule_type,
        rule_regex: vals.rule_regex || '',
        rule_regex_replace: vals.rule_regex_replace || '***',
        hide_group: vals.hide_group || 0,
      })
      setPreviewResult(r.data)
    } catch (e: any) {
      message.error(e.response?.data?.detail || '预览失败')
    } finally { setLoading(false) }
  }

  return (
    <Form.Item label="实时预览">
      <Space>
        <Input value={previewValue} onChange={e => setPreviewValue(e.target.value)}
          style={{ width: 200 }} placeholder="输入测试数据" />
        <Button size="small" icon={<EyeOutlined />} loading={loading} onClick={handlePreview}>
          预览效果
        </Button>
      </Space>
      {previewResult && (
        <div style={{ marginTop: 8 }}>
          <Alert
            type="info" showIcon
            message={
              <Space>
                <span>原始值：<Text code>{previewResult.original}</Text></span>
                <span>→ 脱敏后：<Text code style={{ color: '#f5222d' }}>{previewResult.masked}</Text></span>
              </Space>
            }
          />
        </div>
      )}
    </Form.Item>
  )
}

export default function MaskingRulePage() {
  const qc = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [ruleType, setRuleType] = useState('phone')
  const [form] = Form.useForm()
  const [msgApi, msgCtx] = message.useMessage()

  const { data: ruleTypes } = useQuery({
    queryKey: ['masking-rule-types'],
    queryFn: () => apiClient.get('/masking/rule-types/').then(r => r.data.items),
  })
  const { data: instances } = useQuery({
    queryKey: ['instances-for-masking'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })
  const { data, isLoading } = useQuery({
    queryKey: ['masking-rules'],
    queryFn: () => apiClient.get('/masking/').then(r => r.data),
  })

  const createMut = useMutation({
    mutationFn: (d: any) => apiClient.post('/masking/', d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['masking-rules'] }); setModalOpen(false); msgApi.success('规则创建成功') },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '创建失败'),
  })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: any) => apiClient.put(`/masking/${id}/`, data).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['masking-rules'] }); setModalOpen(false); msgApi.success('已更新') },
  })
  const deleteMut = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/masking/${id}/`).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['masking-rules'] }); msgApi.success('已删除') },
  })

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      editId ? updateMut.mutate({ id: editId, data: values }) : createMut.mutate(values)
    } catch { /* validation */ }
  }

  const openCreate = () => {
    setEditId(null); setRuleType('phone')
    form.resetFields(); form.setFieldsValue({ rule_type: 'phone', db_name: '*', table_name: '*', is_active: true })
    setModalOpen(true)
  }
  const openEdit = (r: any) => {
    setEditId(r.id); setRuleType(r.rule_type); form.setFieldsValue(r); setModalOpen(true)
  }

  const columns = [
    { title: '规则名称', dataIndex: 'rule_name', width: 220, render: (v: string, r: any) => (
      <Space direction="vertical" size={0}>
        <Text strong>{v}</Text>
        {r.description && <Text type="secondary" style={{ fontSize: 11 }}>{r.description}</Text>}
      </Space>
    )},
    { title: '脱敏类型', dataIndex: 'rule_type', width: 100,
      render: (v: string) => <Tag color={RULE_TYPE_COLORS[v] || 'default'}>{v}</Tag> },
    { title: '适用范围', key: 'scope', width: 220, render: (_: any, r: any) => (
      <Space direction="vertical" size={0}>
        <Text style={{ fontSize: 12 }}>列名：<Text code style={{ fontSize: 11 }}>{r.column_name}</Text></Text>
        <Text style={{ fontSize: 11 }} type="secondary">
          {r.instance_id ? `实例ID:${r.instance_id} ` : '全部实例 '}
          库:{r.db_name} 表:{r.table_name}
        </Text>
      </Space>
    )},
    { title: '状态', dataIndex: 'is_active', width: 80,
      render: (v: boolean) => v ? <Tag color="success">启用</Tag> : <Tag>停用</Tag> },
    { title: '创建人', dataIndex: 'created_by', width: 110 },
    { title: '创建时间', dataIndex: 'created_at', width: 160,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
    { title: '操作', width: 110, render: (_: any, r: any) => (
      <Space>
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
        <Popconfirm title="确认删除此规则？" onConfirm={() => deleteMut.mutate(r.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      </Space>
    )},
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="数据脱敏规则"
        meta="规则生效于在线查询结果，支持手机号、邮箱、银行卡、身份证、姓名、地址和自定义正则"
        marginBottom={20}
        actions={<Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建规则</Button>}
      />

      <SectionCard bodyPadding={0} marginBottom={0}>
        <Table dataSource={data?.items} columns={columns} rowKey="id" loading={isLoading}
          locale={{ emptyText: <TableEmptyState title="暂无脱敏规则" /> }}
          tableLayout="fixed"
          scroll={{ x: 980 }}
          pagination={{ total: data?.total, pageSize: 20, showSizeChanger: false }} />
      </SectionCard>

      <Modal title={editId ? '编辑脱敏规则' : '新建脱敏规则'} open={modalOpen}
        maskClosable={false}
        onOk={handleSubmit} onCancel={() => setModalOpen(false)}
        confirmLoading={createMut.isPending || updateMut.isPending} width={560}>
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="rule_name" label="规则名称" rules={[{ required: true }]}>
            <Input placeholder="如：手机号脱敏" />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input placeholder="可选，说明此规则的用途" />
          </Form.Item>
          <Space style={{ width: '100%', display: 'flex' }}>
            <Form.Item name="rule_type" label="脱敏类型" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select onChange={(v) => setRuleType(v)}>
                {(ruleTypes || []).map((rt: any) => (
                  <Option key={rt.value} value={rt.value}>
                    <Tag color={RULE_TYPE_COLORS[rt.value]}>{rt.label}</Tag> {rt.desc}
                  </Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item name="is_active" label="启用" valuePropName="checked" style={{ width: 80 }}>
              <Switch />
            </Form.Item>
          </Space>

          {ruleType === 'regex' && (
            <>
              <Form.Item name="rule_regex" label="正则表达式" rules={[{ required: true }]}>
                <Input placeholder="如：(\d{3})\d{4,8}(\d{2})" />
              </Form.Item>
              <Space style={{ width: '100%', display: 'flex' }}>
                <Form.Item name="rule_regex_replace" label="替换字符串" style={{ flex: 1 }} initialValue="***">
                  <Input placeholder="如：$1****$2" />
                </Form.Item>
                <Form.Item name="hide_group" label="隐藏分组" style={{ flex: 1 }} initialValue={0}>
                  <InputNumber min={0} max={9} style={{ width: '100%' }} />
                </Form.Item>
              </Space>
            </>
          )}

          <Space style={{ width: '100%', display: 'flex' }}>
            <Form.Item name="instance_id" label="适用实例（可选）" style={{ flex: 1 }}>
              <Select placeholder="不选=全部实例" allowClear>
                {instances?.items?.map((i: any) => (
                  <Option key={i.id} value={i.id}>{i.instance_name}</Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item name="column_name" label="列名" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Input placeholder="如：phone，支持*通配" />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%', display: 'flex' }}>
            <Form.Item name="db_name" label="数据库名" initialValue="*" style={{ flex: 1 }}>
              <Input placeholder="* 表示所有数据库" />
            </Form.Item>
            <Form.Item name="table_name" label="表名" initialValue="*" style={{ flex: 1 }}>
              <Input placeholder="* 表示所有表" />
            </Form.Item>
          </Space>

          <PreviewPanel form={form} />
        </Form>
      </Modal>
    </div>
  )
}
