import { Button, Card, Descriptions, Space, Steps, Table, Tag, Typography, message, Popconfirm } from 'antd'
import { CheckOutlined, CloseOutlined, PlayCircleOutlined, StopOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, useNavigate } from 'react-router-dom'
import { workflowApi } from '@/api/workflow'
import { useAuthStore } from '@/store/auth'

const { Title, Text } = Typography

const STATUS_COLOR: Record<number, string> = {
  0: 'processing', 1: 'error', 2: 'success', 3: 'warning',
  4: 'default', 5: 'processing', 6: 'success', 7: 'error', 8: 'default',
}

export default function WorkflowDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [msgApi, msgCtx] = message.useMessage()
  const wfId = Number(id)
  const user = useAuthStore((s) => s.user)

  const { data: wf, isLoading } = useQuery({
    queryKey: ['workflow', wfId, user?.id ?? user?.username ?? 'anonymous'],
    queryFn: () => workflowApi.get(wfId),
    staleTime: 0,
    refetchOnMount: 'always',
    refetchOnWindowFocus: 'always',
    refetchInterval: (query) => (query.state.data?.status === 5 ? 2000 : false),
  })

  const auditMut = useMutation({
    mutationFn: ({ action, remark }: { action: 'pass' | 'reject'; remark?: string }) =>
      workflowApi.audit(wfId, { action, remark }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['workflow', wfId] }); msgApi.success('操作成功') },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '操作失败'),
  })
  const executeMut = useMutation({
    mutationFn: () => workflowApi.execute(wfId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['workflow', wfId] }); msgApi.success('已加入执行队列') },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '执行失败'),
  })
  const cancelMut = useMutation({
    mutationFn: () => workflowApi.cancel(wfId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['workflow', wfId] }); msgApi.success('工单已取消') },
  })

  if (isLoading || !wf) return <div style={{ padding: 40 }}>加载中...</div>

  const logColumns = [
    { title: '操作人', dataIndex: 'operator', width: 120 },
    { title: '操作', dataIndex: 'operation_type', width: 120 },
    { title: '备注', dataIndex: 'remark', width: 320, ellipsis: true },
    { title: '时间', dataIndex: 'created_at', width: 180, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
  ]

  return (
    <div>
      {msgCtx}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <Title level={2} style={{ margin: 0 }}>工单详情 #{wfId}</Title>
        <Space>
          {wf.can_audit && <>
            <Button type="primary" icon={<CheckOutlined />} loading={auditMut.isPending}
              onClick={() => auditMut.mutate({ action: 'pass' })}>审批通过</Button>
            <Button danger icon={<CloseOutlined />} loading={auditMut.isPending}
              onClick={() => auditMut.mutate({ action: 'reject', remark: '驳回' })}>驳回</Button>
          </>}
          {wf.can_execute && (
            <Popconfirm title="确认立即执行此工单？" onConfirm={() => executeMut.mutate()} okText="执行" cancelText="取消">
              <Button type="primary" icon={<PlayCircleOutlined />} loading={executeMut.isPending}>立即执行</Button>
            </Popconfirm>
          )}
          {wf.can_cancel && (
            <Popconfirm title="确认取消此工单？" onConfirm={() => cancelMut.mutate()} okText="取消工单" cancelText="返回">
              <Button icon={<StopOutlined />}>取消工单</Button>
            </Popconfirm>
          )}
          <Button onClick={() => navigate('/workflow')}>返回列表</Button>
        </Space>
      </div>

      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)', marginBottom: 16 }}>
        <Descriptions column={3} size="small">
          <Descriptions.Item label="工单名称">{wf.workflow_name}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={STATUS_COLOR[wf.status]}>{wf.status_desc}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="提交人">{wf.engineer_display || wf.engineer}</Descriptions.Item>
          <Descriptions.Item label="目标实例">
            <Space size={4}>
              <Text style={{ fontFamily: 'monospace', fontSize: 12 }}>ID:{wf.instance_id}</Text>
              {wf.instance_name && <Tag color="blue">{wf.instance_name}</Tag>}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="数据库">{wf.db_name}</Descriptions.Item>
          <Descriptions.Item label="资源组">{wf.group_name}</Descriptions.Item>
          <Descriptions.Item label="提交时间">{wf.created_at ? new Date(wf.created_at).toLocaleString('zh-CN') : '-'}</Descriptions.Item>
          <Descriptions.Item label="完成时间">{wf.finish_time ? new Date(wf.finish_time).toLocaleString('zh-CN') : '-'}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="SQL 内容" style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)', marginBottom: 16 }}
        styles={{ body: { padding: 0 } }}>
        <pre style={{ padding: 16, margin: 0, fontFamily: '"JetBrains Mono", monospace', fontSize: 13,
          background: '#1e1e1e', color: '#d4d4d4', borderRadius: '0 0 12px 12px', overflowX: 'auto',
          maxHeight: 400 }}>
          {wf.sql_content || '（无 SQL 内容）'}
        </pre>
      </Card>

      {wf.execute_result && (
        <Card title="执行结果" style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)', marginBottom: 16 }}>
          <pre style={{ margin: 0, fontSize: 13, fontFamily: 'monospace' }}>
            {typeof wf.execute_result === 'string' ? wf.execute_result : JSON.stringify(wf.execute_result, null, 2)}
          </pre>
        </Card>
      )}

      {wf.audit_logs?.length > 0 && (
        <Card title="审批日志" style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}
          styles={{ body: { padding: 0 } }}>
          <Table dataSource={wf.audit_logs} columns={logColumns} rowKey={(r, i) => String(i)}
            size="small" tableLayout="fixed" scroll={{ x: 760 }} pagination={false} />
        </Card>
      )}
    </div>
  )
}
