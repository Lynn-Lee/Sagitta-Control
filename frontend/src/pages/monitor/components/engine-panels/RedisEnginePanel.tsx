import { Descriptions, Space } from 'antd'

import { formatBytes, formatMetric, formatPercent, formatRateMetric } from '../../formatters'
import type { EnginePanelContext } from '../../types'
import { MetricCard } from '../MonitorStatus'

export function RedisEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
        <MetricCard title="内存使用率" value={formatPercent(metricGroups.memory?.memory_usage)} />
        <MetricCard title="已用内存" value={formatBytes(metricGroups.memory?.used_memory)} />
        <MetricCard title="缓存命中率" value={formatPercent(metricGroups.stats?.keyspace_hit_rate)} />
        <MetricCard title="Ops/sec" value={formatRateMetric(metricGroups.stats?.instantaneous_ops_per_sec)} />
        <MetricCard title="连接客户端" value={metricGroups.connections?.current} />
        <MetricCard title="阻塞客户端" value={metricGroups.connections?.blocked_clients} danger={(metricGroups.connections?.blocked_clients || 0) > 0} />
        <MetricCard title="Key 淘汰" value={metricGroups.stats?.evicted_keys} danger={(metricGroups.stats?.evicted_keys || 0) > 0} />
        <MetricCard title="拒绝连接" value={metricGroups.stats?.rejected_connections} danger={(metricGroups.stats?.rejected_connections || 0) > 0} />
      </div>
      <Descriptions bordered size="small" column={isMobile ? 1 : 3}>
        <Descriptions.Item label="角色">{formatMetric(metricGroups.replication?.role)}</Descriptions.Item>
        <Descriptions.Item label="从库数量">{formatMetric(metricGroups.replication?.connected_slaves)}</Descriptions.Item>
        <Descriptions.Item label="主从链路">{formatMetric(metricGroups.replication?.master_link_status || '不适用')}</Descriptions.Item>
        <Descriptions.Item label="总命令数">{formatMetric(metricGroups.stats?.total_commands_processed)}</Descriptions.Item>
        <Descriptions.Item label="命中次数">{formatMetric(metricGroups.stats?.keyspace_hits)}</Descriptions.Item>
        <Descriptions.Item label="未命中次数">{formatMetric(metricGroups.stats?.keyspace_misses)}</Descriptions.Item>
        <Descriptions.Item label="过期 Key">{formatMetric(metricGroups.stats?.expired_keys)}</Descriptions.Item>
        <Descriptions.Item label="内存碎片率">{formatMetric(metricGroups.memory?.mem_fragmentation_ratio)}</Descriptions.Item>
        <Descriptions.Item label="峰值内存">{formatBytes(metricGroups.memory?.used_memory_peak)}</Descriptions.Item>
      </Descriptions>
    </Space>
  )
}
