import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import QueryHistoryPage from './QueryHistoryPage'

vi.mock('@/api/query', () => ({
  queryApi: {
    getLogs: vi.fn(),
    toggleFavorite: vi.fn(),
  },
}))

vi.mock('@/api/instance', () => ({
  instanceApi: {
    list: vi.fn(),
  },
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useQuery: ({ queryKey }: { queryKey: string[] }) => {
    if (queryKey[0] === 'query-history-instances') {
      return {
        data: {
          items: [{ id: 1, instance_name: 'MySQL-prod', db_type: 'mysql' }],
        },
      }
    }

    if (queryKey[0] === 'query-history') {
      return {
        data: {
          total: 1,
          page: 1,
          page_size: 50,
          items: [{
            id: 1,
            user_id: 7,
            username: 'alice',
            instance_id: 1,
            instance_name: 'MySQL-prod',
            db_type: 'mysql',
            db_name: 'analytics',
            sqllog: 'SELECT * FROM orders',
            operation_type: 'export',
            export_format: 'xlsx',
            effect_row: 25,
            cost_time_ms: 42,
            priv_check: true,
            hit_rule: false,
            masking: true,
            is_favorite: false,
            client_ip: '10.0.0.8',
            error: '',
            created_at: '2026-04-23T10:00:00Z',
          }],
        },
        isLoading: false,
        refetch: vi.fn(),
      }
    }

    return { data: undefined, isLoading: false, refetch: vi.fn() }
  },
}))

describe('QueryHistoryPage', () => {
  it('renders query history rows and filters', () => {
    render(<QueryHistoryPage />)

    expect(screen.getByText('查询历史')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('操作人')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('SQL 关键字')).toBeInTheDocument()
    expect(screen.getByText('alice')).toBeInTheDocument()
    expect(screen.getByText('MySQL-prod')).toBeInTheDocument()
    expect(screen.getByText('SELECT * FROM orders')).toBeInTheDocument()
    expect(screen.getByText('导出')).toBeInTheDocument()
    expect(screen.getByText('XLSX')).toBeInTheDocument()
    expect(screen.getByText('25')).toBeInTheDocument()
  })
})
