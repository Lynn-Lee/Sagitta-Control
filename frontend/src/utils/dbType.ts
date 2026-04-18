export const DB_TYPE_LABELS: Record<string, string> = {
  mysql: 'MySQL',
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

export function formatDbTypeLabel(dbType?: string | null): string {
  if (!dbType) return '-'
  return DB_TYPE_LABELS[dbType.toLowerCase()] || dbType
}
