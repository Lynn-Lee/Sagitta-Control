import { Space, Table } from 'antd'

import TableEmptyState from '@/components/common/TableEmptyState'
import { TruncatedCell } from '@/components/common/TruncatedCell'

import { compactSqlText, formatBytes, formatMetric } from '../../formatters'
import type { EnginePanelContext } from '../../types'
import { MetricCard } from '../MonitorStatus'

export function MssqlEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
        <MetricCard title="数据库数" value={metricGroups.databases?.total} />
        <MetricCard title="在线数据库" value={metricGroups.databases?.online} />
        <MetricCard title="总会话" value={metricGroups.sessions?.total} />
        <MetricCard title="用户会话" value={metricGroups.sessions?.user} />
        <MetricCard title="阻塞会话" value={(metricGroups.blocking_sessions || []).length} danger={(metricGroups.blocking_sessions || []).length > 0} />
        <MetricCard title="Deadlock" value={metricGroups.deadlocks?.deadlocks} danger={(metricGroups.deadlocks?.deadlocks || 0) > 0} />
        <MetricCard title="tempdb 内部对象" value={formatBytes(metricGroups.tempdb?.internal_object_bytes)} />
        <MetricCard title="缺失索引建议" value={(metricGroups.missing_indexes || []).length} />
      </div>
      <Table dataSource={metricGroups.waits || []} rowKey={(row: any, index) => `${row.wait_type || 'wait'}-${index}`} size="small" pagination={false} scroll={{ x: 900 }} columns={[
        { title: '等待类型', dataIndex: 'wait_type' },
        { title: '任务数', dataIndex: 'waiting_tasks_count', render: value => formatMetric(value) },
        { title: '等待时间', dataIndex: 'wait_time_ms', render: (value: any) => formatMetric(value, ' ms') },
        { title: '信号等待', dataIndex: 'signal_wait_time_ms', render: (value: any) => formatMetric(value, ' ms') },
      ]} locale={{ emptyText: <TableEmptyState title="暂无等待统计" /> }} />
      <Table dataSource={metricGroups.blocking_sessions || []} rowKey={(row: any, index) => `${row.session_id || 'blocking'}-${index}`} size="small" pagination={false} scroll={{ x: 980 }} columns={[
        { title: 'Session', dataIndex: 'session_id' },
        { title: 'Blocking', dataIndex: 'blocking_session_id' },
        { title: '等待', dataIndex: 'wait_type' },
        { title: 'SQL', dataIndex: 'sql_text', ellipsis: { showTitle: false }, render: (value: string) => <TruncatedCell value={compactSqlText(value)} tooltipValue={value} /> },
      ]} locale={{ emptyText: <TableEmptyState title="暂无阻塞会话" /> }} />
    </Space>
  )
}
