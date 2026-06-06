import { Descriptions, Space, Table } from 'antd'

import TableEmptyState from '@/components/common/TableEmptyState'

import type { EnginePanelContext } from '../../types'
import { MetricCard } from '../MonitorStatus'
import { stateSummaryText } from './shared'

export function StarRocksEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
  const cluster = metricGroups.cluster || {}
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
        <MetricCard title="当前查询" value={metricGroups.queries?.current} />
        <MetricCard title="FE 节点" value={cluster.frontends?.count} />
        <MetricCard title="BE 节点" value={cluster.backends?.count} />
        <MetricCard title="CN 节点" value={cluster.compute_nodes?.count} />
        <MetricCard title="Load Job" value={metricGroups.load_jobs?.count} />
        <MetricCard title="Routine Load" value={metricGroups.routine_load_jobs?.count} />
        <MetricCard title="Compaction" value={metricGroups.compactions?.count} />
        <MetricCard title="资源组" value={metricGroups.resource_groups?.count} />
      </div>
      <Descriptions bordered size="small" column={isMobile ? 1 : 2}>
        <Descriptions.Item label="Load 状态">{stateSummaryText(metricGroups.load_jobs?.state_counts)}</Descriptions.Item>
        <Descriptions.Item label="Routine Load 状态">{stateSummaryText(metricGroups.routine_load_jobs?.state_counts)}</Descriptions.Item>
      </Descriptions>
      <Table dataSource={metricGroups.compactions?.rows || []} rowKey={(row: any, index) => `${row.TabletId || row.tablet_id || 'compaction'}-${index}`} size="small" pagination={false} scroll={{ x: 900 }} columns={[
        { title: 'Tablet', dataIndex: 'TabletId', render: (_: any, row: any) => row.TabletId || row.tablet_id || '-' },
        { title: '状态', dataIndex: 'State', render: (_: any, row: any) => row.State || row.state || '-' },
        { title: '类型', dataIndex: 'Type', render: (_: any, row: any) => row.Type || row.type || '-' },
        { title: '进度', dataIndex: 'Progress', render: (_: any, row: any) => row.Progress || row.progress || '-' },
      ]} locale={{ emptyText: <TableEmptyState title="暂无 Compaction 数据" /> }} />
    </Space>
  )
}
