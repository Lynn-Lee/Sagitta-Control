import { Descriptions, Space, Table } from 'antd'

import TableEmptyState from '@/components/common/TableEmptyState'

import { formatBytes, formatMetric } from '../../formatters'
import type { EnginePanelContext } from '../../types'
import { MetricCard } from '../MonitorStatus'

export function MongoEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
        <MetricCard title="连接数" value={metricGroups.connections?.current} />
        <MetricCard title="可用连接" value={metricGroups.connections?.available} />
        <MetricCard title="集合数" value={metricGroups.database?.collections} />
        <MetricCard title="对象数" value={metricGroups.database?.objects} />
        <MetricCard title="数据大小" value={formatBytes(metricGroups.database?.data_size)} />
        <MetricCard title="索引大小" value={formatBytes(metricGroups.database?.index_size)} />
        <MetricCard title="Replica 成员" value={metricGroups.replication?.member_count} />
        <MetricCard title="Shard 数" value={metricGroups.sharding?.shard_count} />
      </div>
      <Descriptions bordered size="small" column={isMobile ? 1 : 3}>
        <Descriptions.Item label="副本集">{formatMetric(metricGroups.replication?.set_name)}</Descriptions.Item>
        <Descriptions.Item label="Primary">{String(metricGroups.replication?.is_primary ?? '暂无数据')}</Descriptions.Item>
        <Descriptions.Item label="复制延迟">{formatMetric(metricGroups.replication?.lag_seconds, ' s')}</Descriptions.Item>
        <Descriptions.Item label="WiredTiger Cache">{formatBytes(metricGroups.wired_tiger?.cache_bytes_current)}</Descriptions.Item>
        <Descriptions.Item label="WiredTiger Cache 上限">{formatBytes(metricGroups.wired_tiger?.cache_bytes_max)}</Descriptions.Item>
        <Descriptions.Item label="脏页字节">{formatBytes(metricGroups.wired_tiger?.dirty_bytes)}</Descriptions.Item>
      </Descriptions>
      <Table dataSource={metricGroups.collections || []} rowKey={(row: any) => row.name} size="small" pagination={false} scroll={{ x: 900 }} columns={[
        { title: '集合', dataIndex: 'name' },
        { title: '文档数', dataIndex: 'count', render: value => formatMetric(value) },
        { title: '数据大小', dataIndex: 'size', render: formatBytes },
        { title: '存储大小', dataIndex: 'storage_size', render: formatBytes },
        { title: '索引大小', dataIndex: 'index_size', render: formatBytes },
      ]} locale={{ emptyText: <TableEmptyState title="暂无集合指标" /> }} />
    </Space>
  )
}
