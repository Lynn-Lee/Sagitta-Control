import { useState } from 'react'
import { Button, Card, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Tag, Typography, message, Grid } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { instanceApi } from '@/api/instance'
import apiClient from '@/api/client'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'

const { Text } = Typography
const { Option } = Select
const { useBreakpoint } = Grid

const EXPORTER_TYPES = ['mysqld_exporter', 'postgres_exporter', 'redis_exporter', 'mongodb_exporter', 'elasticsearch_exporter', 'clickhouse_exporter']

export default function MonitorPage() {
  const qc = useQueryClient()
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const [modalOpen, setModalOpen] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form] = Form.useForm()
  const [msgApi, msgCtx] = message.useMessage()

  const { data: instanceData } = useQuery({ queryKey: ['instances-monitor'], queryFn: () => instanceApi.list({ page_size: 200 }) })
  const { data, isLoading } = useQuery({
    queryKey: ['monitor-configs'],
    queryFn: () => apiClient.get('/monitor/configs/').then(r => r.data),
  })

  const createMut = useMutation({
    mutationFn: (d: any) => apiClient.post('/monitor/configs/', d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['monitor-configs'] }); setModalOpen(false); msgApi.success('采集配置创建成功') },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '创建失败'),
  })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: any) => apiClient.put(`/monitor/configs/${id}/`, data).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['monitor-configs'] }); setModalOpen(false); msgApi.success('已更新') },
  })
  const deleteMut = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/monitor/configs/${id}/`).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['monitor-configs'] }); msgApi.success('已删除') },
  })

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      editId ? updateMut.mutate({ id: editId, data: values }) : createMut.mutate(values)
    } catch { /* validation */ }
  }

  const openCreate = () => { setEditId(null); form.resetFields(); setModalOpen(true) }
  const openEdit = (r: any) => { setEditId(r.id); form.setFieldsValue(r); setModalOpen(true) }

  const columns = [
    {
      title: '目标实例', key: 'instance', width: 200,
      render: (_: any, r: any) => (
        <Space direction="vertical" size={0}>
          <Space size={4}>
            <Tag color="blue" style={{ fontSize: 11 }}>ID:{r.instance_id}</Tag>
            <Text style={{ fontWeight: 500, fontSize: 13 }}>{r.instance_name}</Text>
          </Space>
          <Text type="secondary" style={{ fontSize: 11 }}>{r.exporter_type}</Text>
        </Space>
      ),
    },
    { title: 'Exporter 地址', dataIndex: 'exporter_url', width: 280, ellipsis: true },
    { title: '采集间隔', dataIndex: 'collect_interval', width: 100, render: (v: number) => `${v}s` },
    { title: '创建人', dataIndex: 'created_by', width: 120, render: (v: string) => v || <Text type="secondary">—</Text> },
    { title: '状态', dataIndex: 'is_enabled', width: 80, render: (v: boolean) => v ? <Tag color="success">启用</Tag> : <Tag>停用</Tag> },
    {
      title: '操作', width: 120,
      render: (_: any, r: any) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => deleteMut.mutate(r.id)} />
        </Space>
      ),
    },
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="可观测中心"
        marginBottom={20}
        actions={(
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}
            style={isMobile ? { width: '100%' } : undefined}>
            新建采集配置
          </Button>
        )}
      />
      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }} styles={{ body: { padding: 0 } }}>
        <Table dataSource={data?.items} columns={columns} rowKey="id" loading={isLoading}
          locale={{ emptyText: <TableEmptyState title="暂无采集配置" /> }}
          tableLayout="fixed"
          scroll={{ x: 920 }}
          pagination={{ total: data?.total, pageSize: 20, showSizeChanger: false }} />
      </Card>
      <Modal title={editId ? '编辑采集配置' : '新建采集配置'} open={modalOpen}
        maskClosable={false}
        onOk={handleSubmit} onCancel={() => setModalOpen(false)}
        confirmLoading={createMut.isPending || updateMut.isPending}>
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="instance_id" label="实例" rules={[{ required: true }]}>
            <Select placeholder="选择实例" disabled={!!editId}>
              {instanceData?.items?.map((i: any) => <Option key={i.id} value={i.id}>{i.instance_name}</Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="exporter_type" label="Exporter 类型" rules={[{ required: true }]}>
            <Select placeholder="选择类型">
              {EXPORTER_TYPES.map(t => <Option key={t} value={t}>{t}</Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="exporter_url" label="Exporter 地址" rules={[{ required: true }]}>
            <Input placeholder="http://db-host:9104/metrics" />
          </Form.Item>
          <Form.Item name="collect_interval" label="采集间隔（秒）" initialValue={60}>
            <InputNumber min={10} max={3600} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="is_enabled" label="启用采集" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
