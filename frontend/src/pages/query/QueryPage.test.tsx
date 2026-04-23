import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import QueryPage from './QueryPage'

vi.mock('@monaco-editor/react', () => ({
  default: ({ value }: { value: string }) => <div data-testid="monaco-editor">{value}</div>,
}))

vi.mock('@/api/query', () => ({
  queryApi: {
    execute: vi.fn(),
    explainAccess: vi.fn(),
    exportResult: vi.fn(),
  },
}))

vi.mock('@/api/instance', () => ({
  instanceApi: {
    list: vi.fn(),
    getDatabases: vi.fn(),
    getTables: vi.fn(),
    getTableDdl: vi.fn(),
  },
}))

vi.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: string[] }) => {
    const key = queryKey[0]

    if (key === 'instances-for-query') {
      return {
        data: {
          items: [{ id: 1, instance_name: 'MySQL-prod', db_type: 'mysql' }],
        },
      }
    }

    if (key === 'registered-dbs') {
      return {
        data: {
          databases: [{ id: 1, db_name: 'demo_db', remark: '', is_active: true, sync_at: null, db_name_label: '数据库' }],
        },
        isLoading: false,
      }
    }

    if (key === 'tables-for-query') {
      return {
        data: {
          tables: ['users', 'orders'],
        },
        isLoading: false,
      }
    }

    if (key === 'table-ddl-for-query') {
      return {
        data: {
          table_name: 'users',
          ddl: 'CREATE TABLE `users` (\n  `id` bigint NOT NULL\n);',
          copyable_ddl: 'CREATE TABLE `users` (\n  `id` bigint NOT NULL\n);',
          raw_ddl: 'CREATE TABLE `demo`.`users` (\n  `id` bigint NOT NULL\n) ENGINE=InnoDB;',
          source: 'engine',
        },
        isLoading: false,
      }
    }

    return { data: undefined, isLoading: false }
  },
}))

describe('QueryPage', () => {
  it('renders left table browser and bottom ddl preview tab', () => {
    render(<QueryPage />)

    expect(screen.getByText('SQL 编辑器')).toBeInTheDocument()
    expect(screen.getByText('表浏览器')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('搜索当前数据库下的表')).toBeInTheDocument()
    expect(screen.getByText('DDL 预览')).toBeInTheDocument()
    expect(screen.getByText('结果')).toBeInTheDocument()
    expect(screen.getByText('可复制 DDL')).toBeInTheDocument()
    expect(screen.getByText('原始 DDL')).toBeInTheDocument()
    expect(screen.getByText('从左侧选择一张表，然后点击生成 DDL 或直接查看预览')).toBeInTheDocument()
  })
})
