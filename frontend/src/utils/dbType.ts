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

export type EngineSupportStatus = 'ga' | 'validated_minimal' | 'experimental' | 'backlog'

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
    supportLabel: 'v1.0-GA 正式承诺',
    note: '覆盖实例管理、数据字典、在线查询、SQL 工单、归档和观测主链路。',
  },
  tidb: {
    status: 'ga',
    statusLabel: '正式支持',
    supportLabel: 'v1.0-GA 正式承诺',
    note: '按 MySQL 兼容协议接入，覆盖核心管控链路。',
  },
  pgsql: {
    status: 'ga',
    statusLabel: '正式支持',
    supportLabel: 'v1.0-GA 正式承诺',
    note: '覆盖实例管理、Schema/数据字典、在线查询、SQL 工单、归档和观测主链路。',
  },
  mongo: {
    status: 'ga',
    statusLabel: '正式支持',
    supportLabel: 'v1.0-GA 正式承诺',
    note: '覆盖连接、库表元数据、在线查询安全控制、归档和基础观测能力。',
  },
  redis: {
    status: 'ga',
    statusLabel: '正式支持',
    supportLabel: 'v1.0-GA 正式承诺',
    note: '覆盖连接、数据库编号注册、白名单查询控制和基础观测能力。',
  },
  clickhouse: {
    status: 'ga',
    statusLabel: '正式支持',
    supportLabel: 'v1.0-GA 正式承诺',
    note: '覆盖连接、元数据、在线查询、SQL 工单和观测主链路。',
  },
  starrocks: {
    status: 'ga',
    statusLabel: '正式支持',
    supportLabel: 'v1.0-GA 正式承诺',
    note: '覆盖连接、元数据、在线查询、SQL 工单和归档 purge 主链路。',
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
    note: '已有最小可用实现；正式接入前需在客户同构环境验证连接、元数据和执行链路。',
  },
  elasticsearch: {
    status: 'validated_minimal',
    statusLabel: '客户验证后交付',
    supportLabel: '最小可用',
    note: '覆盖连接、索引元数据、SQL API 只读查询和基础健康监控；正式交付前需在客户 ES 版本验证。',
  },
  opensearch: {
    status: 'validated_minimal',
    statusLabel: '客户验证后交付',
    supportLabel: '最小可用',
    note: '复用 Elasticsearch 适配入口；正式交付前需在目标 OpenSearch 版本验证 SQL API 兼容性。',
  },
  cassandra: {
    status: 'experimental',
    statusLabel: '待验证',
    supportLabel: '不作为 GA 承诺',
    note: '当前仅保留骨架能力，正式支持需单独立项。',
  },
  doris: {
    status: 'validated_minimal',
    statusLabel: '客户验证后交付',
    supportLabel: '最小可用',
    note: '覆盖 FE MySQL 协议连接、元数据、在线查询、SQL 工单基础审核和基础监控。',
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
