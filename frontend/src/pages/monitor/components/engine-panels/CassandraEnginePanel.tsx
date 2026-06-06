import { Alert, Space, Table } from 'antd'

import TableEmptyState from '@/components/common/TableEmptyState'

import { formatBytes, formatMetric } from '../../formatters'
import type { EnginePanelContext } from '../../types'
import { MetricCard } from '../MonitorStatus'

export function CassandraEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
        <MetricCard title="Peer 节点" value={metricGroups.cluster?.peer_count} />
        <MetricCard title="估算分区数" value={metricGroups.tables?.estimated_partitions} />
        <MetricCard title="估算数据量" value={formatBytes(metricGroups.tables?.estimated_bytes)} />
        <MetricCard title="近期 Compaction" value={metricGroups.compactions?.recent_count} />
      </div>
      <Alert type="info" showIcon message="Cassandra/ScyllaDB 深度运行指标需要 JMX 或 sidecar 暴露；当前页面展示 CQL 系统表可采集指标。" />
      <Table dataSource={metricGroups.cluster?.peers || []} rowKey={(row: any, index) => `${row.peer || 'peer'}-${index}`} size="small" pagination={false} scroll={{ x: 760 }} columns={[
        { title: 'Peer', dataIndex: 'peer' },
        { title: 'Data Center', dataIndex: 'data_center' },
        { title: 'Rack', dataIndex: 'rack' },
        { title: '版本', dataIndex: 'release_version' },
      ]} locale={{ emptyText: <TableEmptyState title="暂无 Peer 数据" /> }} />
      <Table dataSource={metricGroups.tables?.rows || []} rowKey={(row: any, index) => `${row.keyspace_name || 'ks'}-${row.table_name || index}`} size="small" pagination={false} scroll={{ x: 900 }} columns={[
        { title: 'Keyspace', dataIndex: 'keyspace_name' },
        { title: 'Table', dataIndex: 'table_name' },
        { title: '平均分区大小', dataIndex: 'mean_partition_size', render: formatBytes },
        { title: '分区数', dataIndex: 'partitions_count', render: value => formatMetric(value) },
      ]} locale={{ emptyText: <TableEmptyState title="暂无容量估算数据" /> }} />
    </Space>
  )
}
