import { useState } from 'react'
import { Button, Card, Select, Space, Table, Tag, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { instanceApi } from '@/api/instance'
import apiClient from '@/api/client'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Text } = Typography
const { Option } = Select

export default function SlowlogPage() {
  const [instanceId, setInstanceId] = useState<number | undefined>()

  const { data: instanceData } = useQuery({
    queryKey: ['instances-for-slowlog'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['slowlog', instanceId],
    queryFn: () => apiClient.get(`/slowlog/?instance_id=${instanceId}&limit=50`).then(r => r.data),
    enabled: !!instanceId,
  })

  const items = data?.items ?? []
  const keys = items.length > 0 ? Object.keys(items[0]) : []

  const columns = keys.map(k => ({
    title: k, dataIndex: k, key: k, ellipsis: true,
    width: k.toLowerCase().includes('query') ? 400 : 140,
    render: (v: any) => v === null ? <Text type="secondary">NULL</Text> : String(v),
  }))

  return (
    <div>
      <PageHeader title="慢查询分析" marginBottom={20} />
      <FilterCard marginBottom={16}>
        <Space>
          <Select placeholder="选择实例" style={{ width: 220 }} onChange={setInstanceId} showSearch optionFilterProp="label">
            {instanceData?.items?.map((i: any) => (
              <Option key={i.id} value={i.id} label={i.instance_name}>
                <Tag color="blue">{formatDbTypeLabel(i.db_type)}</Tag> {i.instance_name}
              </Option>
            ))}
          </Select>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()} disabled={!instanceId}>刷新</Button>
          <Text type="secondary" style={{ fontSize: 12 }}>显示执行时间 &gt; 1s 的活跃查询，共 {data?.total ?? 0} 条</Text>
        </Space>
      </FilterCard>
      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }} styles={{ body: { padding: 0 } }}>
        <Table dataSource={items.map((r: any, i: number) => ({ key: i, ...r }))}
          columns={columns} loading={isLoading} size="small" tableLayout="fixed" scroll={{ x: 'max-content' }}
          locale={{ emptyText: <TableEmptyState title={instanceId ? '暂无慢查询数据' : '请先选择实例'} /> }}
          pagination={{ pageSize: 50, showSizeChanger: false }} />
      </Card>
    </div>
  )
}
