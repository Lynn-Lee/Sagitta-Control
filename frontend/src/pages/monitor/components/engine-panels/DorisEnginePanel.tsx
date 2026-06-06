import { Descriptions, Space, Table } from 'antd'

import TableEmptyState from '@/components/common/TableEmptyState'

import type { EnginePanelContext } from '../../types'
import { MetricCard } from '../MonitorStatus'
import { stateSummaryText } from './shared'

export function DorisEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
  const cluster = metricGroups.cluster || {}
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
        <MetricCard title="当前查询" value={metricGroups.queries?.current} />
        <MetricCard title="FE 节点" value={cluster.frontends?.count} />
        <MetricCard title="BE 节点" value={cluster.backends?.count} />
        <MetricCard title="Load Job" value={metricGroups.load_jobs?.count} />
        <MetricCard title="Routine Load" value={metricGroups.routine_load_jobs?.count} />
        <MetricCard title="Compaction" value={metricGroups.compactions?.count} />
        <MetricCard title="Tablet 统计" value={metricGroups.tablets?.count} />
      </div>
      <Descriptions bordered size="small" column={isMobile ? 1 : 2}>
        <Descriptions.Item label="Load 状态">{stateSummaryText(metricGroups.load_jobs?.state_counts)}</Descriptions.Item>
        <Descriptions.Item label="Routine Load 状态">{stateSummaryText(metricGroups.routine_load_jobs?.state_counts)}</Descriptions.Item>
      </Descriptions>
      <Table dataSource={metricGroups.cluster?.backends?.rows || []} rowKey={(row: any, index) => `${row.BackendId || row.backend_id || index}`} size="small" pagination={false} scroll={{ x: 980 }} columns={[
        { title: 'Backend', dataIndex: 'BackendId', render: (_: any, row: any) => row.BackendId || row.backend_id || '-' },
        { title: 'Host', dataIndex: 'Host', render: (_: any, row: any) => row.Host || row.host || '-' },
        { title: 'Alive', dataIndex: 'Alive', render: (_: any, row: any) => String(row.Alive ?? row.alive ?? '-') },
        { title: '容量', dataIndex: 'TotalCapacity', render: (_: any, row: any) => row.TotalCapacity || row.total_capacity || '-' },
      ]} locale={{ emptyText: <TableEmptyState title="暂无 Backend 数据" /> }} />
    </Space>
  )
}
