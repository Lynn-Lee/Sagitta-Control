import { Space, Table, Typography } from 'antd'

import TableEmptyState from '@/components/common/TableEmptyState'

import { formatMetric } from '../../formatters'
import type { EnginePanelContext } from '../../types'

const { Title } = Typography

const tokenUsageColumns = [
  { title: 'TiDB 节点', dataIndex: 'instance', width: 220 },
  { title: '活跃会话', dataIndex: 'active_sessions', width: 120, render: (value: any) => formatMetric(value) },
  { title: 'Sleep 会话', dataIndex: 'sleep_sessions', width: 120, render: (value: any) => formatMetric(value) },
  { title: '总会话', dataIndex: 'total_sessions', width: 110, render: (value: any) => formatMetric(value) },
  { title: 'Token Limit', dataIndex: 'token_limit', width: 120, render: (value: any) => formatMetric(value) },
  { title: 'Token 使用率', dataIndex: 'token_usage_pct', width: 130, render: (value: any) => formatMetric(value, '%') },
]
export function TidbEnginePanel({ metricGroups }: EnginePanelContext) {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Title level={5} style={{ marginTop: 0 }}>TiDB Token 使用率</Title>
        <Table dataSource={metricGroups.token_usage || []} columns={tokenUsageColumns} rowKey={(row: any, index) => `${row.instance || 'token'}-${index}`} scroll={{ x: 820 }} pagination={false} locale={{ emptyText: <TableEmptyState title="暂无 Token 使用率数据" /> }} />
      </div>
    </Space>
  )
}
