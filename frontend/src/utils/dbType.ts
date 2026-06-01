export const DB_TYPE_LABELS: Record<string, string> = {
  mysql: 'MySQL',
  starrocks: 'StarRocks',
  postgres: 'PostgreSQL',
  pgsql: 'PostgreSQL',
  postgresql: 'PostgreSQL',
  oracle: 'Oracle',
  tidb: 'TiDB',
  doris: 'Doris',
  mssql: 'MSSQL',
  sqlserver: 'MSSQL',
  'sql-server': 'MSSQL',
  clickhouse: 'ClickHouse',
  'click-house': 'ClickHouse',
  mongo: 'MongoDB',
  mongodb: 'MongoDB',
  'mongo-db': 'MongoDB',
  cassandra: 'Cassandra',
  redis: 'Redis',
  es: 'Elasticsearch',
  elasticsearch: 'Elasticsearch',
  'elastic-search': 'Elasticsearch',
  opensearch: 'OpenSearch',
  'open-search': 'OpenSearch',
}

export type EngineSupportStatus = 'ga' | 'validated_minimal' | 'read_only_metadata' | 'experimental' | 'backlog'

export interface EngineSupportInfo {
  status: EngineSupportStatus
  statusLabel: string
  supportLabel: string
  note: string
}

export const ENGINE_SUPPORT: Record<string, EngineSupportInfo> = {
  mysql: {
    status: 'ga',
    statusLabel: '正式支持',
    supportLabel: 'v2.0 正式承诺',
    note: '覆盖实例管理、数据字典、在线查询、SQL 工单、归档和观测主链路。',
  },
  tidb: {
    status: 'ga',
    statusLabel: '正式支持',
    supportLabel: 'v2.0 正式承诺',
    note: '按 MySQL 兼容协议接入，覆盖核心管控链路。',
  },
  pgsql: {
    status: 'ga',
    statusLabel: '正式支持',
    supportLabel: 'v2.0 正式承诺',
    note: '覆盖实例管理、Schema/数据字典、在线查询、SQL 工单、归档和观测主链路。',
  },
  mongo: {
    status: 'ga',
    statusLabel: '正式支持',
    supportLabel: 'v2.0 正式承诺',
    note: '覆盖连接、库表元数据、在线查询安全控制、归档、currentOp、profiler 慢操作、ReplicaSet/Sharding、WiredTiger 和集合级观测。',
  },
  redis: {
    status: 'ga',
    statusLabel: '正式支持',
    supportLabel: 'v2.0 正式承诺',
    note: '覆盖连接、数据库编号注册、白名单查询控制和基础观测能力。',
  },
  clickhouse: {
    status: 'ga',
    statusLabel: '正式支持',
    supportLabel: 'v2.0 正式承诺',
    note: '覆盖连接、元数据、在线查询、SQL 工单和观测主链路。',
  },
  starrocks: {
    status: 'ga',
    statusLabel: '正式支持',
    supportLabel: 'v2.0 正式承诺',
    note: '覆盖连接、元数据、在线查询、SQL 工单、归档 purge、会话、执行计划、FE/BE/CN、Load、Compaction、Tablet 和资源组观测。',
  },
  oracle: {
    status: 'validated_minimal',
    statusLabel: '客户验证后交付',
    supportLabel: '最小可用',
    note: '已有最小可用实现；正式接入前需在客户同构环境验证驱动模式、元数据和执行链路。',
  },
  mssql: {
    status: 'validated_minimal',
    statusLabel: '客户验证后交付',
    supportLabel: '最小可用',
    note: '已有连接、元数据、查询、会话、SQL 活动、执行计划、waits、blocking、deadlock、tempdb、job 和缺失索引观测；正式接入前需客户同构验证。',
  },
  elasticsearch: {
    status: 'validated_minimal',
    statusLabel: '客户验证后交付',
    supportLabel: '最小可用',
    note: '覆盖连接、索引元数据、SQL API 只读查询、cluster/node/index/shard、heap/GC、thread pool、segment 和任务活动；正式交付前需在客户 ES 版本验证。',
  },
  opensearch: {
    status: 'validated_minimal',
    statusLabel: '客户验证后交付',
    supportLabel: '最小可用',
    note: '使用独立 OpenSearch 适配入口和 opensearch-py 客户端，覆盖 cluster/node/index/shard、heap/GC、thread pool、segment 和任务活动；正式交付前需验证 OpenSearch SQL API 兼容性。',
  },
  cassandra: {
    status: 'read_only_metadata',
    statusLabel: '只读/元数据边界',
    supportLabel: '只读/元数据边界',
    note: '覆盖连接、元数据、只读 SELECT、系统表健康、peer、容量估算和 compaction 历史；读写延迟、tombstone、SSTable、cache、thread pool 等深度指标需 JMX/sidecar。',
  },
  doris: {
    status: 'validated_minimal',
    statusLabel: '客户验证后交付',
    supportLabel: '最小可用',
    note: '覆盖 FE MySQL 协议连接、元数据、在线查询、SQL 工单基础审核、会话、执行计划、FE/BE、Compaction、Load Job、Tablet 和查询活动观测。',
  },
}

export const DB_TYPES = Object.keys(ENGINE_SUPPORT)

export function getEngineSupport(dbType?: string | null): EngineSupportInfo {
  return ENGINE_SUPPORT[(dbType || '').toLowerCase()] || {
    status: 'backlog',
    statusLabel: '暂不承诺',
    supportLabel: '未纳入支持矩阵',
    note: '该数据库类型未纳入当前版本支持矩阵。',
  }
}

export function isExperimentalDbType(dbType?: string | null): boolean {
  return getEngineSupport(dbType).status === 'experimental'
}

export function formatDbTypeLabel(dbType?: string | null): string {
  if (!dbType) return '-'
  return DB_TYPE_LABELS[dbType.toLowerCase()] || dbType
}
