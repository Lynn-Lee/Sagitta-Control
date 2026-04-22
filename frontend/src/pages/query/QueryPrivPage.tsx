import { useEffect, useState } from 'react'
import { Button, Card, DatePicker, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography, message, Tabs, Tooltip, Grid } from 'antd'
import { PlusOutlined, CheckOutlined, CloseOutlined, DeleteOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import { queryApi } from '@/api/query'
import { approvalFlowApi } from '@/api/approvalFlow'
import { instanceApi } from '@/api/instance'
import PageHeader from '@/components/common/PageHeader'
import { useAuthStore } from '@/store/auth'
import { formatDbTypeLabel } from '@/utils/dbType'
import dayjs from 'dayjs'

const { Text } = Typography
const { Option } = Select
const { useBreakpoint } = Grid

const STATUS_MAP: Record<number, { label: string; color: string }> = {
  0: { label: '待审核', color: 'processing' },
  1: { label: '已通过', color: 'success' },
  2: { label: '已驳回', color: 'error' },
  3: { label: '已取消', color: 'default' },
}

const SCOPE_META: Record<string, { label: string; color: string }> = {
  instance: { label: '实例级', color: 'volcano' },
  database: { label: '库级', color: 'blue' },
  table: { label: '表级', color: 'purple' },
}

export default function QueryPrivPage() {
  const { user } = useAuthStore()
  const qc = useQueryClient()
  const location = useLocation()
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const [applyModalOpen, setApplyModalOpen] = useState(false)
  const [applyForm] = Form.useForm()
  const [auditForm] = Form.useForm()
  const [instanceId, setInstanceId] = useState<number | undefined>()
  const [scopeType, setScopeType] = useState<'instance' | 'database' | 'table'>('database')
  const [auditModalOpen, setAuditModalOpen] = useState(false)
  const [auditTarget, setAuditTarget] = useState<any>(null)
  const [msgApi, msgCtx] = message.useMessage()

  useEffect(() => {
    const state = location.state as {
      openApply?: boolean
      instanceId?: number
      dbName?: string
      tableName?: string
      scopeType?: 'instance' | 'database' | 'table'
    } | null
    if (!state?.openApply) return
    const nextScope = state.scopeType || (state.tableName ? 'table' : state.dbName ? 'database' : 'instance')
    setInstanceId(state.instanceId)
    setScopeType(nextScope)
    setApplyModalOpen(true)
    applyForm.setFieldsValue({
      scope_type: nextScope,
      db_name: state.dbName || undefined,
      table_name: state.tableName || '',
    })
  }, [applyForm, location.state])

  // 我的权限列表
  const { data: privData } = useQuery({
    queryKey: ['my-query-privs', user?.id],
    queryFn: () => queryApi.listPrivileges(),
    refetchOnMount: 'always',
  })

  // 申请列表
  const { data: applyData } = useQuery({
    queryKey: ['query-priv-applies', user?.id],
    queryFn: () => queryApi.listApplies({ page_size: 50 }),
    refetchOnMount: 'always',
    refetchInterval: 5000,
  })

  const { data: auditData } = useQuery({
    queryKey: ['query-priv-audit-records', user?.id],
    queryFn: () => queryApi.listAuditRecords({ page_size: 50 }),
    refetchOnMount: 'always',
    refetchInterval: 5000,
  })
  const { data: manageData } = useQuery({
    queryKey: ['query-priv-manage', user?.id],
    queryFn: () => queryApi.listManagePrivileges({ page_size: 50, status: 'active' }),
    refetchOnMount: 'always',
    refetchInterval: 5000,
  })
  const { data: revokedData } = useQuery({
    queryKey: ['query-priv-revoked', user?.id],
    queryFn: () => queryApi.listManagePrivileges({ page_size: 50, status: 'revoked' }),
    refetchOnMount: 'always',
    refetchInterval: 5000,
  })
  const showManageTab = !!manageData?.scope && manageData.scope.mode !== 'self'

  // 实例、资源组
  const { data: instanceData } = useQuery({
    queryKey: ['instances-for-priv'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })
  const selectedInstance = (instanceData?.items || []).find((item: any) => item.id === instanceId)
  const isPgInstance = selectedInstance?.db_type === 'pgsql'
  const { data: flowData } = useQuery({
    queryKey: ['approval-flows-for-query-priv'],
    queryFn: () => approvalFlowApi.list(),
  })
  const { data: dbData } = useQuery({
    queryKey: ['registered-dbs-priv', instanceId],
    queryFn: () => instanceApi.listRegisteredDbs(instanceId!),
    enabled: !!instanceId,
  })
  const instanceNameMap = new Map<number, string>(
    (instanceData?.items ?? []).map((instance: any) => [instance.id, instance.instance_name]),
  )

  const applyMut = useMutation({
    mutationFn: queryApi.applyPrivilege,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['query-priv-applies'] })
      qc.invalidateQueries({ queryKey: ['query-priv-audit-records'] })
      setApplyModalOpen(false)
      msgApi.success('申请已提交')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '提交失败'),
  })

  const auditMut = useMutation({
    mutationFn: ({ apply_id, action, remark, valid_date }: any) => queryApi.auditApply(apply_id, { action, remark, valid_date }),
    onSuccess: (res: any) => {
      qc.invalidateQueries({ queryKey: ['query-priv-applies'] })
      qc.invalidateQueries({ queryKey: ['query-priv-audit-records'] })
      qc.invalidateQueries({ queryKey: ['my-query-privs'] })
      qc.invalidateQueries({ queryKey: ['query-priv-manage'] })
      qc.invalidateQueries({ queryKey: ['query-priv-revoked'] })
      setAuditModalOpen(false)
      setAuditTarget(null)
      auditForm.resetFields()
      msgApi.success(res?.msg || '审批完成')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '审批失败'),
  })

  const revokeMut = useMutation({
    mutationFn: ({ priv_id, reason }: { priv_id: number; reason?: string }) =>
      queryApi.revokePrivilege(priv_id, { reason }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-query-privs'] })
      qc.invalidateQueries({ queryKey: ['query-priv-manage'] })
      qc.invalidateQueries({ queryKey: ['query-priv-revoked'] })
      msgApi.success('权限已撤销')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '撤销失败'),
  })

  const handleApply = async () => {
    try {
      const values = await applyForm.validateFields()
      if (!instanceId) {
        msgApi.warning('请选择目标实例')
        return
      }
      applyMut.mutate({
        ...values,
        scope_type: values.scope_type,
        valid_date: values.valid_date.format('YYYY-MM-DD'),
        instance_id: instanceId,
        flow_id: values.flow_id,
        db_name: values.scope_type === 'instance' ? '' : values.db_name,
        table_name: values.scope_type === 'table' ? values.table_name : '',
        priv_type: values.scope_type === 'table' ? 2 : values.scope_type === 'database' ? 1 : 0,
      })
    } catch { /* validation */ }
  }

  const openAuditPassModal = (record: any) => {
    setAuditTarget(record)
    auditForm.setFieldsValue({
      valid_date: record.valid_date ? dayjs(record.valid_date) : undefined,
      remark: '',
    })
    setAuditModalOpen(true)
  }

  const handleAuditPass = async () => {
    if (!auditTarget) return
    const values = await auditForm.validateFields()
    auditMut.mutate({
      apply_id: auditTarget.id,
      action: 'pass',
      remark: values.remark,
      valid_date: values.valid_date?.format('YYYY-MM-DD'),
    })
  }

  const handleRevokePrivilege = (record: any) => {
    let reason = ''
    Modal.confirm({
      title: '撤销查询权限',
      content: (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text>确认撤销 {record.db_name}{record.table_name ? `.${record.table_name}` : ''} 的查询权限？</Text>
          <Input.TextArea
            rows={3}
            maxLength={500}
            showCount
            placeholder="撤销原因（可选）"
            onChange={e => { reason = e.target.value }}
          />
        </Space>
      ),
      okText: '撤销',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => revokeMut.mutateAsync({ priv_id: record.id, reason }),
    })
  }

  const privColumns = [
    {
      title: '目标实例', dataIndex: 'instance_id', width: 180,
      render: (instanceIdValue: number) => instanceNameMap.get(instanceIdValue) || `实例#${instanceIdValue}`,
    },
    { title: '数据库', dataIndex: 'db_name', width: 160, ellipsis: true },
    { title: '范围', dataIndex: 'scope_type', width: 90, render: (v: string) => <Tag color={SCOPE_META[v]?.color || 'default'}>{SCOPE_META[v]?.label || v}</Tag> },
    { title: '表名', dataIndex: 'table_name', width: 180, ellipsis: true, render: (v: string, r: any) => v || <Text type="secondary">{r.scope_type === 'instance' ? '全实例' : '全库'}</Text> },
    { title: '行数限制', dataIndex: 'limit_num', width: 90 },
    {
      title: '有效期', dataIndex: 'valid_date', width: 110,
      render: (v: string) => {
        const expiry = dayjs(v)
        const expired = expiry.endOf('day').isBefore(dayjs())
        const expiresToday = expiry.isSame(dayjs(), 'day')
        return (
          <Tag color={expired ? 'default' : expiresToday ? 'warning' : 'success'}>
            {v}
            {expired ? ' (已过期)' : expiresToday ? ' (今日到期)' : ''}
          </Tag>
        )
      },
    },
    {
      title: '操作',
      width: 90,
      render: (_: any, r: any) => (
        <Button
          size="small"
          danger
          icon={<DeleteOutlined />}
          loading={revokeMut.isPending}
          onClick={() => handleRevokePrivilege(r)}
        >
          撤销
        </Button>
      ),
    },
  ]

  const manageColumns = [
    { title: '用户', dataIndex: 'user_display', width: 130, render: (v: string, r: any) => v || r.username || `用户#${r.user_id}` },
    {
      title: '目标实例', dataIndex: 'instance_name', width: 180,
      render: (instanceName: string, r: any) => instanceName || instanceNameMap.get(r.instance_id) || `实例#${r.instance_id}`,
    },
    { title: '数据库', dataIndex: 'db_name', width: 160, ellipsis: true },
    { title: '范围', dataIndex: 'scope_type', width: 90, render: (v: string) => <Tag color={SCOPE_META[v]?.color || 'default'}>{SCOPE_META[v]?.label || v}</Tag> },
    { title: '表名', dataIndex: 'table_name', width: 180, ellipsis: true, render: (v: string, r: any) => v || <Text type="secondary">{r.scope_type === 'instance' ? '全实例' : '全库'}</Text> },
    { title: '行数限制', dataIndex: 'limit_num', width: 90 },
    { title: '有效期', dataIndex: 'valid_date', width: 120, render: (v: string) => <Tag color="success">{v}</Tag> },
    {
      title: '授权时间', dataIndex: 'created_at', width: 140,
      render: (v: string) => v ? dayjs(v).format('MM-DD HH:mm') : '—',
    },
    {
      title: '操作',
      width: 110,
      render: (_: any, r: any) => r.can_revoke ? (
        <Button
          size="small"
          danger
          icon={<DeleteOutlined />}
          loading={revokeMut.isPending}
          onClick={() => handleRevokePrivilege(r)}
        >
          撤销
        </Button>
      ) : <Text type="secondary">只读</Text>,
    },
  ]

  const revokedColumns = [
    ...manageColumns.filter((c: any) => c.title !== '操作'),
    {
      title: '撤销人', dataIndex: 'revoked_by_name', width: 130,
      render: (v: string) => v || '—',
    },
    {
      title: '撤销时间', dataIndex: 'revoked_at', width: 150,
      render: (v: string) => v ? dayjs(v).format('MM-DD HH:mm') : '—',
    },
    {
      title: '撤销原因', dataIndex: 'revoke_reason', width: 220, ellipsis: true,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
  ]

  const applyColumns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '标题', dataIndex: 'title', width: 220, ellipsis: true },
    {
      title: '目标实例', dataIndex: 'instance_name', width: 180,
      render: (instanceName: string, r: any) => instanceName || instanceNameMap.get(r.instance_id) || `实例#${r.instance_id}`,
    },
    { title: '申请人', dataIndex: 'applicant_name', width: 120, render: (v: string, r: any) => v || r.applicant_username || '—' },
    { title: '申请数据库', dataIndex: 'db_name', width: 150, ellipsis: true },
    { title: '范围', dataIndex: 'scope_type', width: 90, render: (v: string) => <Tag color={SCOPE_META[v]?.color || 'default'}>{SCOPE_META[v]?.label || v}</Tag> },
    { title: '表名', dataIndex: 'table_name', width: 180, ellipsis: true, render: (v: string, r: any) => v || <Text type="secondary">{r.scope_type === 'instance' ? '全实例' : '全库'}</Text> },
    { title: '行数限制', dataIndex: 'limit_num', width: 100 },
    { title: '有效期', dataIndex: 'valid_date', width: 120 },
    { title: '申请理由', dataIndex: 'apply_reason', width: 220, ellipsis: true },
    { title: '当前节点', dataIndex: 'current_node_name', width: 150, ellipsis: true, render: (v: string) => v || '—' },
    {
      title: '审批链路',
      dataIndex: 'approval_progress',
      width: 320,
      render: (v: string) => v ? (
        <Tooltip title={v} placement="topLeft">
          <Text
            ellipsis={{ tooltip: false }}
            style={{
              display: 'inline-block',
              maxWidth: 300,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {v}
          </Text>
        </Tooltip>
      ) : '—',
    },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: number) => <Tag color={STATUS_MAP[v]?.color}>{STATUS_MAP[v]?.label}</Tag>,
    },
    {
      title: '提交时间', dataIndex: 'created_at', width: 140,
      render: (v: string) => v ? dayjs(v).format('MM-DD HH:mm') : '—',
    },
    {
      title: '审批操作',
      width: 180,
      render: (_: any, r: any) => r.can_audit ? (
        <Space size={8} wrap>
          <Button
            size="small"
            type="primary"
            icon={<CheckOutlined />}
            onClick={() => openAuditPassModal(r)}
          >
            通过
          </Button>
          <Button
            size="small"
            danger
            icon={<CloseOutlined />}
            onClick={() => auditMut.mutate({ apply_id: r.id, action: 'reject' })}
          >
            驳回
          </Button>
        </Space>
      ) : <Text type="secondary">—</Text>,
    },
  ]

  const auditColumns = [
    ...applyColumns.filter((c: any) => !['申请理由', '提交时间'].includes(c.title)),
    {
      title: '最近审批节点', dataIndex: 'acted_node_name', width: 150,
      render: (v: string) => v || '—',
    },
    {
      title: '审批结果', dataIndex: 'acted_action', width: 100,
      render: (v: string) => v ? <Tag color={v === '通过' ? 'success' : 'error'}>{v}</Tag> : '待审批',
    },
    {
      title: '审批时间', dataIndex: 'acted_at', width: 170,
      render: (v: string) => v ? dayjs(v).format('MM-DD HH:mm') : '—',
    },
  ]

  const tabItems = [
    {
      key: 'privs',
      label: `我的权限（${privData?.items?.length ?? 0}）`,
      children: (
        <Table dataSource={privData?.items} columns={privColumns}
          rowKey="id" size="small" tableLayout="fixed" scroll={{ x: 950 }} pagination={{ pageSize: 20 }} />
      ),
    },
    {
      key: 'applies',
      label: `申请记录（${applyData?.total ?? 0}）`,
      children: (
        <Table dataSource={applyData?.items} columns={applyColumns as any}
          rowKey="id" size="small" tableLayout="fixed" scroll={{ x: 1840 }} pagination={{ pageSize: 20 }} />
      ),
    },
    {
      key: 'audit-records',
      label: `审批记录（${auditData?.total ?? 0}）`,
      children: (
        <Table
          dataSource={auditData?.items}
          columns={auditColumns as any}
          rowKey="id"
          size="small"
          tableLayout="fixed"
          scroll={{ x: 2100 }}
          pagination={{ pageSize: 20 }}
        />
      ),
    },
    ...(showManageTab ? [{
      key: 'manage',
      label: `权限视图（${manageData?.total ?? 0}）`,
      children: (
        <>
          <div style={{ padding: '0 0 12px 0' }}>
            <Tag color="blue">{manageData?.scope?.label || '统一视角'}</Tag>
          </div>
          <Table
            dataSource={manageData?.items}
            columns={manageColumns as any}
            rowKey="id"
            size="small"
            tableLayout="fixed"
            scroll={{ x: 1200 }}
            pagination={{ pageSize: 20 }}
          />
        </>
      ),
    }] : []),
    {
      key: 'revoked',
      label: `已撤销权限（${revokedData?.total ?? 0}）`,
      children: (
        <>
          <div style={{ padding: '0 0 12px 0' }}>
            <Tag color="blue">{revokedData?.scope?.label || '统一视角'}</Tag>
          </div>
          <Table
            dataSource={revokedData?.items}
            columns={revokedColumns as any}
            rowKey="id"
            size="small"
            tableLayout="fixed"
            scroll={{ x: 1540 }}
            pagination={{ pageSize: 20 }}
          />
        </>
      ),
    },
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="查询权限"
        marginBottom={20}
        actions={(
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { applyForm.resetFields(); setScopeType('database'); setApplyModalOpen(true) }}
            style={isMobile ? { width: '100%' } : undefined}>
            申请查询权限
          </Button>
        )}
      />

      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}>
        <Tabs items={tabItems} />
      </Card>

      <Modal title="申请查询权限" open={applyModalOpen}
        maskClosable={false}
        onOk={handleApply} onCancel={() => setApplyModalOpen(false)}
        confirmLoading={applyMut.isPending} width={520}>
        <Form form={applyForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="title" label="申请标题" rules={[{ required: true }]}>
            <Input placeholder="简明描述申请用途" />
          </Form.Item>
          <Form.Item label="目标实例" required>
            <Select placeholder="选择实例" value={instanceId} onChange={v => { setInstanceId(v); applyForm.setFieldValue('db_name', undefined); applyForm.setFieldValue('table_name', '') }} showSearch optionFilterProp="label"
              popupMatchSelectWidth={false} style={{ minWidth: 220 }}>
              {instanceData?.items?.map((i: any) => (
                <Option key={i.id} value={i.id} label={i.instance_name} title={i.instance_name}>
                  <Tag color="blue">{formatDbTypeLabel(i.db_type)}</Tag> {i.instance_name}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="scope_type" label="授权范围" initialValue="database" rules={[{ required: true }]}>
            <Select onChange={(v) => {
              setScopeType(v)
              if (v === 'instance') {
                applyForm.setFieldValue('db_name', undefined)
                applyForm.setFieldValue('table_name', '')
              }
              if (v === 'database') {
                applyForm.setFieldValue('table_name', '')
              }
            }}>
              <Option value="instance">实例级授权</Option>
              <Option value="database">库级授权</Option>
              <Option value="table">表级授权</Option>
            </Select>
          </Form.Item>
          <Form.Item>
            <Text type="secondary">
              查询权限审批通过后，将同时获得相同范围的数据字典查看权限。
            </Text>
          </Form.Item>
          <Form.Item name="flow_id" label="审批流" rules={[{ required: true, message: '请选择审批流' }]}>
            <Select placeholder="选择审批流模板">
              {(flowData?.items ?? []).map((flow: any) => (
                <Option key={flow.id} value={flow.id}>{flow.name}</Option>
              ))}
            </Select>
          </Form.Item>
          {scopeType !== 'instance' && (
            <Form.Item name="db_name" label="数据库" rules={[{ required: true }]}>
              <Select placeholder="选择数据库" showSearch disabled={!instanceId}
              popupMatchSelectWidth={false} style={{ minWidth: 180 }} optionFilterProp="children">
                {(dbData?.items || []).map((d: any) => (
                  <Option key={d.db_name} value={d.db_name} title={d.db_name}>
                    {d.db_name}{!d.is_active && <Tag color="default" style={{marginLeft: 4, fontSize: 10}}>已禁用</Tag>}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          )}
          {scopeType === 'table' && (
            <Form.Item
              name="table_name"
              label="表名"
              extra={isPgInstance ? 'PostgreSQL 非 public schema 表请填写 schema.table_name' : undefined}
              rules={[{ required: true, message: '请输入表名' }]}
            >
              <Input placeholder={isPgInstance ? '如 public.orders / tms.tk_order' : '如 orders / user_profile'} />
            </Form.Item>
          )}
          <Form.Item name="valid_date" label="有效期至" rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} disabledDate={d => d.isBefore(dayjs())} />
          </Form.Item>
          <Form.Item name="limit_num" label="行数限制" initialValue={100}>
            <InputNumber min={1} max={100000} style={{ width: '100%' }} addonAfter="行" />
          </Form.Item>
          <Form.Item name="apply_reason" label="申请理由">
            <Input.TextArea rows={3} placeholder="说明申请原因" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="审批查询权限"
        open={auditModalOpen}
        maskClosable={false}
        onOk={handleAuditPass}
        onCancel={() => { setAuditModalOpen(false); setAuditTarget(null); auditForm.resetFields() }}
        confirmLoading={auditMut.isPending}
        okText="通过"
        width={520}
      >
        <Form form={auditForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="申请有效期">
            <Input value={auditTarget?.valid_date || '—'} disabled />
          </Form.Item>
          <Form.Item
            name="valid_date"
            label="审批有效期至"
            rules={[{ required: true, message: '请选择审批后的有效期' }]}
            extra="可保持不变，也可缩短有效期；不能晚于申请有效期。"
          >
            <DatePicker
              style={{ width: '100%' }}
              disabledDate={d => {
                if (!d) return false
                const today = dayjs().startOf('day')
                const maxDate = auditTarget?.valid_date ? dayjs(auditTarget.valid_date).endOf('day') : undefined
                return d.isBefore(today) || (maxDate ? d.isAfter(maxDate) : false)
              }}
            />
          </Form.Item>
          <Form.Item name="remark" label="审批备注">
            <Input.TextArea rows={3} placeholder="可填写调整原因或审批意见" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
