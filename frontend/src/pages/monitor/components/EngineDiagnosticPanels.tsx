/* eslint-disable react-refresh/only-export-components */
import type { TabsProps } from 'antd'
import { Alert, Descriptions, Progress, Space, Table, Typography } from 'antd'

import TableEmptyState from '@/components/common/TableEmptyState'

import {
  compactSqlText,
  formatBytes,
  formatMetric,
  formatPercent,
  formatRateMetric,
  formatTime,
} from '../formatters'
import type { EngineDiagnosticPanel, EnginePanelContext } from '../types'
import { MetricCard } from './MonitorStatus'

const { Title } = Typography

const tokenUsageColumns = [
  { title: 'TiDB 节点', dataIndex: 'instance', width: 220 },
  { title: '活跃会话', dataIndex: 'active_sessions', width: 120, render: (value: any) => formatMetric(value) },
  { title: 'Sleep 会话', dataIndex: 'sleep_sessions', width: 120, render: (value: any) => formatMetric(value) },
  { title: '总会话', dataIndex: 'total_sessions', width: 110, render: (value: any) => formatMetric(value) },
  { title: 'Token Limit', dataIndex: 'token_limit', width: 120, render: (value: any) => formatMetric(value) },
  { title: 'Token 使用率', dataIndex: 'token_usage_pct', width: 130, render: (value: any) => formatMetric(value, '%') },
]

const clickHouseDiskColumns = [
  { title: '磁盘', dataIndex: 'name', width: 160 },
  { title: '路径', dataIndex: 'path', ellipsis: true },
  { title: '使用率', dataIndex: 'used_pct', width: 160, render: (value: number) => <Progress percent={Math.round(Number(value || 0))} size="small" /> },
  { title: '已用', dataIndex: 'used_space', width: 140, render: formatBytes },
  { title: '总量', dataIndex: 'total_space', width: 140, render: formatBytes },
  { title: '保留空间', dataIndex: 'keep_free_space', width: 140, render: formatBytes },
]

function TidbEnginePanel({ metricGroups }: EnginePanelContext) {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Title level={5} style={{ marginTop: 0 }}>TiDB Token 使用率</Title>
        <Table dataSource={metricGroups.token_usage || []} columns={tokenUsageColumns} rowKey={(row: any, index) => `${row.instance || 'token'}-${index}`} scroll={{ x: 820 }} pagination={false} locale={{ emptyText: <TableEmptyState title="暂无 Token 使用率数据" /> }} />
      </div>
    </Space>
  )
}

function OracleEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
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

function RedisEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
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

function ClickHouseEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
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

function stateSummaryText(value?: Record<string, number>) {
  if (!value || !Object.keys(value).length) return '暂无数据'
  return Object.entries(value).map(([key, count]) => `${key}: ${count}`).join(' / ')
}

function StarRocksEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
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

function DorisEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
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

function MssqlEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
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
        { title: 'SQL', dataIndex: 'sql_text', ellipsis: true, render: compactSqlText },
      ]} locale={{ emptyText: <TableEmptyState title="暂无阻塞会话" /> }} />
    </Space>
  )
}

function MongoEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
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

function ElasticsearchEnginePanel(context: EnginePanelContext) {
  return <SearchMetricsPanel {...context} />
}

function OpenSearchEnginePanel(context: EnginePanelContext) {
  return <SearchMetricsPanel {...context} />
}

function CassandraEnginePanel({ metricGroups, isMobile }: EnginePanelContext) {
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

const ENGINE_DIAGNOSTIC_PANELS: Record<string, EngineDiagnosticPanel[]> = {
  tidb: [{ key: 'tidb', label: 'TiDB 专属', render: context => <TidbEnginePanel {...context} /> }],
  oracle: [{ key: 'oracle', label: 'Oracle 专属', render: context => <OracleEnginePanel {...context} /> }],
  redis: [{ key: 'redis', label: 'Redis 专属', render: context => <RedisEnginePanel {...context} /> }],
  clickhouse: [{ key: 'clickhouse', label: 'ClickHouse 专属', render: context => <ClickHouseEnginePanel {...context} /> }],
  starrocks: [{ key: 'starrocks', label: 'StarRocks 专属', render: context => <StarRocksEnginePanel {...context} /> }],
  doris: [{ key: 'doris', label: 'Doris 专属', render: context => <DorisEnginePanel {...context} /> }],
  mssql: [{ key: 'mssql', label: 'MSSQL 专属', render: context => <MssqlEnginePanel {...context} /> }],
  mongo: [{ key: 'mongo', label: 'MongoDB 专属', render: context => <MongoEnginePanel {...context} /> }],
  mongodb: [{ key: 'mongo', label: 'MongoDB 专属', render: context => <MongoEnginePanel {...context} /> }],
  elasticsearch: [{ key: 'elasticsearch', label: 'Elasticsearch 专属', render: context => <ElasticsearchEnginePanel {...context} /> }],
  opensearch: [{ key: 'opensearch', label: 'OpenSearch 专属', render: context => <OpenSearchEnginePanel {...context} /> }],
  cassandra: [{ key: 'cassandra', label: 'Cassandra 专属', render: context => <CassandraEnginePanel {...context} /> }],
}

const GENERIC_WORKBENCH_TAB_KEYS = new Set([
  'overview',
  'trend',
  'databases',
  'tables',
  'sessions',
  'sql',
  'replication',
  'waits',
  'capacity-growth',
  'alerts',
  'diagnosis',
])

const ENGINE_DIAGNOSTIC_TAB_KEYS = new Set(
  Object.values(ENGINE_DIAGNOSTIC_PANELS).flatMap(panels => panels.map(panel => panel.key)),
)

export function firstEngineDiagnosticTabKey(dbType: string | undefined) {
  return ENGINE_DIAGNOSTIC_PANELS[(dbType || '').toLowerCase()]?.[0]?.key
}

export function resolveWorkbenchTabForDbType(tabKey: string | null | undefined, dbType: string | undefined) {
  const currentKey = tabKey || 'overview'
  if (GENERIC_WORKBENCH_TAB_KEYS.has(currentKey)) return currentKey
  const currentEngineTab = firstEngineDiagnosticTabKey(dbType)
  if (currentEngineTab === currentKey) return currentKey
  if (ENGINE_DIAGNOSTIC_TAB_KEYS.has(currentKey)) return currentEngineTab || 'overview'
  return 'overview'
}

export function getEngineDiagnosticTabs(dbType: string | undefined, context: EnginePanelContext): TabsProps['items'] {
  return (ENGINE_DIAGNOSTIC_PANELS[(dbType || '').toLowerCase()] || []).map(panel => ({
    key: panel.key,
    label: panel.label,
    children: panel.render(context),
  }))
}
