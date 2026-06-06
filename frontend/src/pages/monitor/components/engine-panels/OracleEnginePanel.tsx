import { Descriptions, Progress, Space, Table } from 'antd'

import TableEmptyState from '@/components/common/TableEmptyState'

import { formatBytes, formatMetric, formatTime } from '../../formatters'
import type { EnginePanelContext } from '../../types'

export function OracleEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Descriptions bordered size="small" column={isMobile ? 1 : 2}>
        {Object.entries(metricGroups.fra || {}).map(([key, value]) => (
          <Descriptions.Item key={key} label={`FRA ${key}`}>{formatMetric(value as any)}</Descriptions.Item>
        ))}
        {Object.entries(metricGroups.archive || {}).map(([key, value]) => (
          <Descriptions.Item key={key} label={`Archive ${key}`}>{formatMetric(value as any)}</Descriptions.Item>
        ))}
      </Descriptions>
      <Table dataSource={metricGroups.tablespaces || []} rowKey={(row: any) => row.tablespace_name} size="small" pagination={false} columns={[
        { title: '表空间', dataIndex: 'tablespace_name' },
        { title: '使用率', dataIndex: 'used_pct', render: (value: number) => <Progress percent={Math.round(Number(value || 0))} size="small" /> },
        { title: '已用', dataIndex: 'used_bytes', render: formatBytes },
        { title: '总量', dataIndex: 'total_bytes', render: formatBytes },
        { title: 'Autoextend', dataIndex: 'autoextensible' },
      ]} />
      <Table dataSource={metricGroups.data_guard || []} rowKey={(row: any, index) => `${row.name}-${index}`} size="small" pagination={false} columns={[
        { title: 'Data Guard 指标', dataIndex: 'name' },
        { title: '值', dataIndex: 'value' },
        { title: '单位', dataIndex: 'unit' },
        { title: '计算时间', dataIndex: 'time_computed', render: formatTime },
      ]} locale={{ emptyText: <TableEmptyState title="暂无 Data Guard 数据" /> }} />
    </Space>
  )
}
