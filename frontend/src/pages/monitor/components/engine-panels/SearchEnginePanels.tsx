import { Descriptions, Space, Table } from 'antd'

import TableEmptyState from '@/components/common/TableEmptyState'

import { formatBytes, formatMetric, formatPercent } from '../../formatters'
import type { EnginePanelContext } from '../../types'
import { MetricCard } from '../MonitorStatus'
import { stateSummaryText } from './shared'

function SearchMetricsPanel({ metricGroups, isMobile }: EnginePanelContext) {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
        <MetricCard title="节点数" value={metricGroups.cluster?.nodes} />
        <MetricCard title="数据节点" value={metricGroups.cluster?.data_nodes} />
        <MetricCard title="索引数" value={metricGroups.indices?.count} />
        <MetricCard title="文档数" value={metricGroups.indices?.docs_count} />
        <MetricCard title="活跃分片" value={metricGroups.cluster?.active_shards} />
        <MetricCard title="未分配分片" value={metricGroups.cluster?.unassigned_shards} danger={(metricGroups.cluster?.unassigned_shards || 0) > 0} />
        <MetricCard title="Heap 使用率" value={formatPercent(metricGroups.nodes?.heap_usage)} />
        <MetricCard title="线程拒绝" value={metricGroups.thread_pool?.rejected} danger={(metricGroups.thread_pool?.rejected || 0) > 0} />
      </div>
      <Descriptions bordered size="small" column={isMobile ? 1 : 2}>
        <Descriptions.Item label="分片状态">{stateSummaryText(metricGroups.shards?.state_counts)}</Descriptions.Item>
        <Descriptions.Item label="Segment 数">{formatMetric(metricGroups.segments?.count)}</Descriptions.Item>
      </Descriptions>
      <Table dataSource={metricGroups.nodes?.rows || []} rowKey={(row: any) => row.node_id} size="small" pagination={false} scroll={{ x: 980 }} columns={[
        { title: '节点', dataIndex: 'name' },
        { title: 'Heap', dataIndex: 'heap_used_in_bytes', render: formatBytes },
        { title: 'Heap Max', dataIndex: 'heap_max_in_bytes', render: formatBytes },
        { title: 'Segments', dataIndex: 'segments_count', render: value => formatMetric(value) },
        { title: 'Search Active', dataIndex: 'search_query_current', render: value => formatMetric(value) },
        { title: 'Search Rejected', dataIndex: 'search_rejected', render: value => formatMetric(value) },
      ]} locale={{ emptyText: <TableEmptyState title="暂无节点指标" /> }} />
    </Space>
  )
}

export function ElasticsearchEnginePanel(context: EnginePanelContext) {
  return <SearchMetricsPanel {...context} />
}

export function OpenSearchEnginePanel(context: EnginePanelContext) {
  return <SearchMetricsPanel {...context} />
}
