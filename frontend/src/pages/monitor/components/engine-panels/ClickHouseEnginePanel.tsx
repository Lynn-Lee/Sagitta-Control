import { Descriptions, Progress, Space, Table } from 'antd'

import TableEmptyState from '@/components/common/TableEmptyState'
import { renderTruncatedCell } from '@/components/common/TruncatedCell'

import { formatBytes, formatMetric, formatPercent } from '../../formatters'
import type { EnginePanelContext } from '../../types'
import { MetricCard } from '../MonitorStatus'

const clickHouseDiskColumns = [
  { title: '磁盘', dataIndex: 'name', width: 160 },
  { title: '路径', dataIndex: 'path', ellipsis: { showTitle: false }, render: renderTruncatedCell },
  { title: '使用率', dataIndex: 'used_pct', width: 160, render: (value: number) => <Progress percent={Math.round(Number(value || 0))} size="small" /> },
  { title: '已用', dataIndex: 'used_space', width: 140, render: formatBytes },
  { title: '总量', dataIndex: 'total_space', width: 140, render: formatBytes },
  { title: '保留空间', dataIndex: 'keep_free_space', width: 140, render: formatBytes },
]
export function ClickHouseEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
        <MetricCard title="当前查询" value={metricGroups.queries?.active} />
        <MetricCard title="连接数" value={metricGroups.connections?.current} />
        <MetricCard title="内存使用率" value={formatPercent(metricGroups.memory?.memory_usage)} />
        <MetricCard title="已用内存" value={formatBytes(metricGroups.memory?.used_memory)} />
        <MetricCard title="总查询数" value={metricGroups.counters?.queries} />
        <MetricCard title="失败查询" value={metricGroups.counters?.errors} danger={(metricGroups.counters?.errors || 0) > 0} />
        <MetricCard title="延迟写入" value={metricGroups.queries?.delayed_inserts} danger={(metricGroups.queries?.delayed_inserts || 0) > 0} />
        <MetricCard title="拒绝写入" value={metricGroups.queries?.rejected_inserts} danger={(metricGroups.queries?.rejected_inserts || 0) > 0} />
      </div>
      <Table
        dataSource={metricGroups.disks || []}
        columns={clickHouseDiskColumns}
        rowKey={(row: any) => row.name}
        size="small"
        scroll={{ x: 980 }}
        pagination={false}
        locale={{ emptyText: <TableEmptyState title="暂无磁盘指标" /> }}
      />
      <Descriptions bordered size="small" column={isMobile ? 1 : 3}>
        <Descriptions.Item label="Select 查询">{formatMetric(metricGroups.counters?.select_queries)}</Descriptions.Item>
        <Descriptions.Item label="Insert 查询">{formatMetric(metricGroups.counters?.insert_queries)}</Descriptions.Item>
        <Descriptions.Item label="最大连接">{formatMetric(metricGroups.connections?.max_connections)}</Descriptions.Item>
        <Descriptions.Item label="可用内存">{formatBytes(metricGroups.memory?.available_memory)}</Descriptions.Item>
        <Descriptions.Item label="系统总内存">{formatBytes(metricGroups.memory?.total_memory)}</Descriptions.Item>
        <Descriptions.Item label="读操作计数">{formatMetric(metricGroups.counters?.read_ops)}</Descriptions.Item>
        <Descriptions.Item label="写操作计数">{formatMetric(metricGroups.counters?.write_ops)}</Descriptions.Item>
      </Descriptions>
    </Space>
  )
}
