import { describe, expect, it } from 'vitest'

import { DB_TYPES, getEngineSupport, isExperimentalDbType } from './dbType'

describe('engine support matrix', () => {
  it('marks GA engines as formally supported', () => {
    expect(getEngineSupport('mysql').status).toBe('ga')
    expect(getEngineSupport('pgsql').status).toBe('ga')
    expect(getEngineSupport('starrocks').status).toBe('ga')
  })

  it('marks Oracle and MSSQL as customer-validated minimal support', () => {
    expect(getEngineSupport('oracle').status).toBe('validated_minimal')
    expect(getEngineSupport('mssql').status).toBe('validated_minimal')
  })

  it('marks Elasticsearch, OpenSearch, Doris, Oracle and MSSQL as customer-validated minimal support', () => {
    expect(getEngineSupport('elasticsearch').status).toBe('validated_minimal')
    expect(getEngineSupport('opensearch').status).toBe('validated_minimal')
    expect(getEngineSupport('doris').status).toBe('validated_minimal')
  })

  it('marks Cassandra as read-only metadata support', () => {
    expect(getEngineSupport('cassandra').status).toBe('read_only_metadata')
    expect(isExperimentalDbType('cassandra')).toBe(false)
    expect(isExperimentalDbType('elasticsearch')).toBe(false)
    expect(isExperimentalDbType('doris')).toBe(false)
  })

  it('keeps all selectable db types represented in the support matrix', () => {
    expect(DB_TYPES).toContain('mysql')
    expect(DB_TYPES).toContain('doris')
    expect(DB_TYPES.every((dbType) => getEngineSupport(dbType).status !== 'backlog')).toBe(true)
  })
})
