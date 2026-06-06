import type { TabsProps } from 'antd'

import type { EngineDiagnosticPanel, EnginePanelContext } from '../types'
import { CassandraEnginePanel } from './engine-panels/CassandraEnginePanel'
import { ClickHouseEnginePanel } from './engine-panels/ClickHouseEnginePanel'
import { DorisEnginePanel } from './engine-panels/DorisEnginePanel'
import { ElasticsearchEnginePanel, OpenSearchEnginePanel } from './engine-panels/SearchEnginePanels'
import { MongoEnginePanel } from './engine-panels/MongoEnginePanel'
import { MssqlEnginePanel } from './engine-panels/MssqlEnginePanel'
import { OracleEnginePanel } from './engine-panels/OracleEnginePanel'
import { RedisEnginePanel } from './engine-panels/RedisEnginePanel'
import { StarRocksEnginePanel } from './engine-panels/StarRocksEnginePanel'
import { TidbEnginePanel } from './engine-panels/TidbEnginePanel'

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
