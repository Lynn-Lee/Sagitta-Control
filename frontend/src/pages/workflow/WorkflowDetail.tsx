import { useState } from 'react'
import { Button, DatePicker, Descriptions, Form, Input, Modal, Popconfirm, Radio, Select, Space, Table, Tag, Typography, message } from 'antd'
import { CheckOutlined, CloseOutlined, PlayCircleOutlined, StopOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { workflowApi } from '@/api/workflow'
import PageHeader from '@/components/common/PageHeader'
import SectionCard from '@/components/common/SectionCard'
import SectionLoading from '@/components/common/SectionLoading'
import { useAuthStore } from '@/store/auth'

const { Title, Text } = Typography
const { TextArea } = Input

const STATUS_COLOR: Record<number, string> = {
  0: 'processing', 1: 'error', 2: 'success', 3: 'warning',
  4: 'default', 5: 'processing', 6: 'success', 7: 'error', 8: 'default',
}

export default function WorkflowDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [msgApi, msgCtx] = message.useMessage()
  const [executeModalOpen, setExecuteModalOpen] = useState(false)
  const [executeForm] = Form.useForm()
  const executeMode = Form.useWatch('mode', executeForm) || 'immediate'
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
    mutationFn: (payload: any) => workflowApi.execute(wfId, payload),
    onSuccess: (res: any) => {
      qc.invalidateQueries({ queryKey: ['workflow', wfId] })
      setExecuteModalOpen(false)
      executeForm.resetFields()
      msgApi.success(res?.msg || '执行处理已提交')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '执行失败'),
  })
  const cancelMut = useMutation({
    mutationFn: () => workflowApi.cancel(wfId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['workflow', wfId] }); msgApi.success('工单已取消') },
  })

  if (isLoading || !wf) return <SectionLoading text="加载工单详情中..." />

  const openExecuteModal = () => {
    executeForm.setFieldsValue({
      mode: 'immediate',
      external_status: 'success',
      external_executed_at: dayjs(),
    })
    setExecuteModalOpen(true)
  }

  const submitExecuteDecision = async () => {
    const values = await executeForm.validateFields()
    const payload: any = { mode: values.mode }
    if (values.mode === 'scheduled') {
      payload.scheduled_at = values.scheduled_at?.toISOString()
    }
    if (values.mode === 'external') {
      payload.external_executed_at = values.external_executed_at?.toISOString()
      payload.external_status = values.external_status
      payload.external_remark = values.external_remark
    }
    executeMut.mutate(payload)
  }

  const executionModeLabel: Record<string, string> = {
    immediate: '平台立即执行',
    scheduled: '平台定时执行',
    external: '外部已执行',
  }

  const logColumns = [
    { title: '操作人', dataIndex: 'operator', width: 120 },
    { title: '操作', dataIndex: 'operation_type', width: 120 },
    { title: '备注', dataIndex: 'remark', width: 320, ellipsis: true },
    { title: '时间', dataIndex: 'created_at', width: 180, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader
        title={`工单详情 #${wfId}`}
        actions={
          <Space wrap>
          {wf.can_audit && <>
            <Button type="primary" icon={<CheckOutlined />} loading={auditMut.isPending}
              onClick={() => auditMut.mutate({ action: 'pass' })}>审批通过</Button>
            <Button danger icon={<CloseOutlined />} loading={auditMut.isPending}
              onClick={() => auditMut.mutate({ action: 'reject', remark: '驳回' })}>驳回</Button>
          </>}
          {wf.can_execute && (
            <Button type="primary" icon={<PlayCircleOutlined />} loading={executeMut.isPending}
              onClick={openExecuteModal}>执行处理</Button>
          )}
          {wf.can_cancel && (
            <Popconfirm title="确认取消此工单？" onConfirm={() => cancelMut.mutate()} okText="取消工单" cancelText="返回">
              <Button icon={<StopOutlined />}>取消工单</Button>
            </Popconfirm>
          )}
          <Button onClick={() => navigate('/workflow')}>返回列表</Button>
          </Space>
        }
        marginBottom={20}
      />

      <SectionCard>
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
          <Descriptions.Item label="执行方式">
            {wf.execute_mode ? <Tag color="blue">{executionModeLabel[wf.execute_mode] || wf.execute_mode}</Tag> : <Text type="secondary">—</Text>}
          </Descriptions.Item>
          <Descriptions.Item label="预约执行时间">
            {wf.scheduled_execute_at ? new Date(wf.scheduled_execute_at).toLocaleString('zh-CN') : '—'}
          </Descriptions.Item>
          <Descriptions.Item label="执行决策人">{wf.executed_by_name || '—'}</Descriptions.Item>
          <Descriptions.Item label="外部执行时间">
            {wf.external_executed_at ? new Date(wf.external_executed_at).toLocaleString('zh-CN') : '—'}
          </Descriptions.Item>
          <Descriptions.Item label="外部执行结果">
            {wf.external_result_status
              ? <Tag color={wf.external_result_status === 'success' ? 'success' : 'error'}>{wf.external_result_status === 'success' ? '成功' : '失败'}</Tag>
              : <Text type="secondary">—</Text>}
          </Descriptions.Item>
          <Descriptions.Item label="完成时间">{wf.finish_time ? new Date(wf.finish_time).toLocaleString('zh-CN') : '-'}</Descriptions.Item>
          {wf.external_result_remark && (
            <Descriptions.Item label="外部执行备注" span={3}>{wf.external_result_remark}</Descriptions.Item>
          )}
        </Descriptions>
      </SectionCard>

      <SectionCard title="SQL 内容" bodyPadding={0}>
        <pre style={{ padding: 16, margin: 0, fontFamily: '"JetBrains Mono", monospace', fontSize: 13,
          background: '#1e1e1e', color: '#d4d4d4', borderRadius: '0 0 12px 12px', overflowX: 'auto',
          maxHeight: 400 }}>
          {wf.sql_content || '（无 SQL 内容）'}
        </pre>
      </SectionCard>

      {wf.execute_result && (
        <SectionCard title="执行结果">
          <pre style={{ margin: 0, fontSize: 13, fontFamily: 'monospace' }}>
            {typeof wf.execute_result === 'string' ? wf.execute_result : JSON.stringify(wf.execute_result, null, 2)}
          </pre>
        </SectionCard>
      )}

      {wf.audit_logs?.length > 0 && (
        <SectionCard title="审批日志" marginBottom={0} bodyPadding={0}>
          <Table dataSource={wf.audit_logs} columns={logColumns} rowKey={(r, i) => String(i)}
            size="small" tableLayout="fixed" scroll={{ x: 760 }} pagination={false} />
        </SectionCard>
      )}

      <Modal
        title="执行处理"
        open={executeModalOpen}
        onCancel={() => { setExecuteModalOpen(false); executeForm.resetFields() }}
        onOk={submitExecuteDecision}
        confirmLoading={executeMut.isPending}
        okText={executeMode === 'immediate' ? '立即执行' : executeMode === 'scheduled' ? '预约执行' : '登记结果'}
        cancelText="取消"
        destroyOnClose
      >
        <Form form={executeForm} layout="vertical" preserve={false} initialValues={{ mode: 'immediate', external_status: 'success' }}>
          <Form.Item name="mode" label="执行方式" rules={[{ required: true, message: '请选择执行方式' }]}>
            <Radio.Group optionType="button" buttonStyle="solid" style={{ width: '100%' }}>
              <Radio.Button value="immediate">立即执行</Radio.Button>
              <Radio.Button value="scheduled">定时执行</Radio.Button>
              <Radio.Button value="external">外部已执行</Radio.Button>
            </Radio.Group>
          </Form.Item>

          {executeMode === 'scheduled' && (
            <Form.Item name="scheduled_at" label="预约执行时间" rules={[{ required: true, message: '请选择预约执行时间' }]}>
              <DatePicker
                showTime
                style={{ width: '100%' }}
                disabledDate={(current) => !!current && current < dayjs().startOf('day')}
              />
            </Form.Item>
          )}

          {executeMode === 'external' && (
            <>
              <Form.Item name="external_executed_at" label="实际执行时间" rules={[{ required: true, message: '请选择实际执行时间' }]}>
                <DatePicker showTime style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="external_status" label="执行结果" rules={[{ required: true, message: '请选择执行结果' }]}>
                <Select
                  options={[
                    { value: 'success', label: '成功' },
                    { value: 'failed', label: '失败' },
                  ]}
                />
              </Form.Item>
              <Form.Item name="external_remark" label="执行备注" rules={[{ required: true, message: '请填写外部执行结果备注' }]}>
                <TextArea rows={4} maxLength={500} showCount placeholder="记录线下执行方式、影响范围、执行结果或失败原因" />
              </Form.Item>
            </>
          )}

          {executeMode === 'immediate' && (
            <Text type="secondary">确认后会把工单加入平台执行队列，由实例连接账号执行 SQL。</Text>
          )}
        </Form>
      </Modal>
    </div>
  )
}
