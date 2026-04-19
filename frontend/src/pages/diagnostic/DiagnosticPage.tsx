import { useState } from 'react'
import { Button, Card, Select, Space, Table, Tag, Typography, message, Popconfirm } from 'antd'
import { ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { instanceApi } from '@/api/instance'
import apiClient from '@/api/client'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Text } = Typography
const { Option } = Select

export default function DiagnosticPage() {
  const [instanceId, setInstanceId] = useState<number | undefined>()
  const [msgApi, msgCtx] = message.useMessage()
  const qc = useQueryClient()

  const { data: instanceData } = useQuery({
    queryKey: ['instances-for-diag'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })

  const { data: processData, isLoading, refetch } = useQuery({
    queryKey: ['processlist', instanceId],
    queryFn: () => apiClient.get(`/diagnostic/processlist/?instance_id=${instanceId}`).then(r => r.data),
    enabled: !!instanceId,
    refetchInterval: 5000,
  })

  const killMut = useMutation({
    mutationFn: (threadId: number) =>
      apiClient.post(`/diagnostic/kill/?instance_id=${instanceId}&thread_id=${threadId}`).then(r => r.data),
    onSuccess: () => { msgApi.success('会话已 Kill'); qc.invalidateQueries({ queryKey: ['processlist'] }) },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || 'Kill 失败'),
  })

  const cols = processData?.column_list ?? []
  const rows = (processData?.rows ?? []).map((row: any[], i: number) => ({
    key: i,
    ...Object.fromEntries(row.map((v, j) => [cols[j] || j, v])),
  }))

  const columns = [
    ...cols.slice(0, -1).map((col: string) => ({
      title: col, dataIndex: col, key: col, ellipsis: true,
      width: col.toLowerCase().includes('query') || col.toLowerCase().includes('info') ? 300 : 120,
    })),
    {
      title: '操作', key: 'action', width: 80,
      render: (_: any, row: any) => {
        const pid = row['pid'] || row['Id'] || row[cols[0]]
        return (
          <Popconfirm title={`确认 Kill 会话 ${pid}？`} onConfirm={() => killMut.mutate(pid)}
            okText="Kill" cancelText="取消">
            <Button size="small" danger icon={<StopOutlined />}>Kill</Button>
          </Popconfirm>
        )
      },
    },
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader title="会话管理" marginBottom={20} />
      <FilterCard marginBottom={16}>
        <Space>
          <Select placeholder="选择实例" style={{ width: 220 }} onChange={setInstanceId} showSearch optionFilterProp="label">
            {instanceData?.items?.map((i: any) => (
              <Option key={i.id} value={i.id} label={i.instance_name}>
                <Tag color="blue">{formatDbTypeLabel(i.db_type)}</Tag> {i.instance_name}
              </Option>
            ))}
          </Select>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()} disabled={!instanceId}>刷新（5s自动）</Button>
          <Text type="secondary" style={{ fontSize: 12 }}>共 {processData?.total ?? 0} 个活跃会话</Text>
        </Space>
      </FilterCard>
      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }} styles={{ body: { padding: 0 } }}>
        <Table dataSource={rows} columns={columns} loading={isLoading}
          size="small" tableLayout="fixed" scroll={{ x: 'max-content' }}
          locale={{ emptyText: <TableEmptyState title={instanceId ? '暂无活跃会话' : '请先选择实例'} /> }}
          pagination={{ pageSize: 50, showSizeChanger: false }} />
      </Card>
    </div>
  )
}
