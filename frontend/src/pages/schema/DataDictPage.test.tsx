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

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@/store/auth', () => ({
  useAuthStore: (selector: (state: any) => any) => selector({
    user: {
      id: 1,
      is_superuser: true,
      permissions: ['query_all_instances'],
    },
  }),
}))

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
          databases: [{ id: 1, db_name: 'demo_db', remark: '', is_active: true, sync_at: null, db_name_label: '数据库' }],
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
            {
              column_name: 'status',
              column_type: 'tinyint(1)',
              is_nullable: 'YES',
              column_default: '1',
              column_comment: '状态',
            },
            {
              column_name: 'tenant_id',
              column_type: 'bigint(20)',
              is_nullable: 'YES',
              column_default: null,
              column_comment: '租户',
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
            {
              constraint_name: 'uniq_users_email_status',
              constraint_type: 'UNIQUE',
              column_names: 'email, status',
              referenced_table_name: '',
              referenced_column_names: '',
              check_clause: '',
            },
            {
              constraint_name: 'ck_users_status',
              constraint_type: 'CHECK',
              column_names: 'status',
              referenced_table_name: '',
              referenced_column_names: '',
              check_clause: 'CHECK (status IN (0, 1))',
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
            {
              index_name: 'uniq_users_tenant_email',
              index_type: 'UNIQUE INDEX',
              column_names: 'email, status',
              is_composite: 'YES',
              index_comment: '邮箱状态联合唯一索引',
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
    expect(screen.getByText('约束详情')).toBeInTheDocument()
    expect(screen.getByText('索引信息')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('搜索表名关键字')).toBeInTheDocument()

    expect(screen.getAllByText('主键').length).toBeGreaterThan(0)
    expect(screen.getAllByText('非空').length).toBeGreaterThan(0)
    expect(screen.getAllByText('联合唯一').length).toBe(2)
    expect(screen.queryByText('CHECK ((email IS NOT NULL))')).not.toBeInTheDocument()
    expect(screen.getByText('ck_users_status')).toBeInTheDocument()
    expect(screen.getByText('CHECK (status IN (0, 1))')).toBeInTheDocument()
    expect(screen.getByText('idx_users_email_status')).toBeInTheDocument()
    expect(screen.getByText('邮箱状态联合索引')).toBeInTheDocument()
    expect(screen.getByText('uniq_users_tenant_email')).toBeInTheDocument()
    expect(screen.getAllByText('email, status').length).toBeGreaterThan(0)
  })
})
