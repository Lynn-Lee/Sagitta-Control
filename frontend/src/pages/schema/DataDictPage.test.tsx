import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mockUseState } = vi.hoisted(() => ({
  mockUseState: vi.fn(),
}))

vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react')
  return {
    ...actual,
    useState: mockUseState,
  }
})

import DataDictPage from './DataDictPage'

vi.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: string[] }) => {
    const key = queryKey[0]

    if (key === 'instances-for-dict') {
      return {
        data: {
          items: [{ id: 1, instance_name: 'MySQL-tech', db_type: 'mysql' }],
        },
      }
    }

    if (key === 'registered-dbs-dict') {
      return {
        data: {
          items: [{ db_name: 'demo_db', is_active: true }],
        },
      }
    }

    if (key === 'tables-dict') {
      return {
        data: {
          tables: ['users'],
        },
        isLoading: false,
      }
    }

    if (key === 'columns-dict') {
      return {
        data: {
          columns: [
            {
              column_name: 'id',
              column_type: 'bigint(20)',
              is_nullable: 'NO',
              column_default: null,
              column_comment: '主键',
            },
            {
              column_name: 'email',
              column_type: 'varchar(128)',
              is_nullable: 'NO',
              column_default: '',
              column_comment: '邮箱',
            },
          ],
        },
        isLoading: false,
      }
    }

    if (key === 'constraints-dict') {
      return {
        data: {
          constraints: [
            {
              constraint_name: 'PRIMARY',
              constraint_type: 'PRIMARY KEY',
              column_names: 'id',
              referenced_table_name: '',
              referenced_column_names: '',
              check_clause: '',
            },
            {
              constraint_name: '2200_116924_10_not_null_with_a_very_long_constraint_name',
              constraint_type: 'CHECK',
              column_names: 'email',
              referenced_table_name: '',
              referenced_column_names: '',
              check_clause: 'CHECK ((email IS NOT NULL))',
            },
          ],
        },
        isLoading: false,
      }
    }

    if (key === 'indexes-dict') {
      return {
        data: {
          indexes: [
            {
              index_name: 'idx_users_email_status',
              index_type: 'INDEX',
              column_names: 'email, status',
              is_composite: 'YES',
              index_comment: '邮箱状态联合索引',
            },
          ],
        },
        isLoading: false,
      }
    }

    return { data: undefined, isLoading: false }
  },
}))

vi.mock('@/api/instance', () => ({
  instanceApi: {
    list: vi.fn(),
    listRegisteredDbs: vi.fn(),
  },
}))

vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn(),
  },
}))

describe('DataDictPage', () => {
  beforeEach(() => {
    mockUseState.mockReset()
    mockUseState
      .mockImplementationOnce(() => [1, vi.fn()])
      .mockImplementationOnce(() => ['demo_db', vi.fn()])
      .mockImplementationOnce(() => ['users', vi.fn()])
      .mockImplementationOnce(() => ['', vi.fn()])

    vi.spyOn(window, 'matchMedia').mockImplementation((query: string) => ({
      matches: query.includes('(min-width'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders columns, constraints and indexes for selected table', () => {
    render(<DataDictPage />)

    expect(screen.getByText('数据字典')).toBeInTheDocument()
    expect(screen.getAllByText('users').length).toBeGreaterThan(0)
    expect(screen.getByText('表约束')).toBeInTheDocument()
    expect(screen.getByText('索引信息')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('搜索表名关键字')).toBeInTheDocument()

    expect(screen.getByText('PRIMARY KEY')).toBeInTheDocument()
    expect(screen.getByText('CHECK')).toBeInTheDocument()
    expect(screen.getAllByText('约束定义').length).toBeGreaterThan(0)
    expect(screen.getByText('CHECK ((email IS NOT NULL))')).toBeInTheDocument()
    expect(screen.getByText('idx_users_email_status')).toBeInTheDocument()
    expect(screen.getByText('邮箱状态联合索引')).toBeInTheDocument()
    expect(screen.getByText('email, status')).toBeInTheDocument()
  })
})
