import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import QueryPage from './QueryPage'
import { queryApi } from '@/api/query'

vi.mock('@monaco-editor/react', () => ({
  default: ({ value, onChange }: { value: string, onChange?: (value: string) => void }) => (
    <textarea
      data-testid="monaco-editor"
      value={value}
      onChange={(event) => onChange?.(event.currentTarget.value)}
    />
  ),
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
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders left table browser and bottom ddl preview tab', () => {
    render(<QueryPage />)

    expect(screen.getByText('SQL 编辑器')).toBeInTheDocument()
    expect(screen.getByText('表浏览器')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('搜索当前数据库下的表')).toBeInTheDocument()
    expect(screen.getByText('DDL 预览')).toBeInTheDocument()
    expect(screen.getByText('结果')).toBeInTheDocument()
    expect(screen.getByText('简化 DDL')).toBeInTheDocument()
    expect(screen.getByText('原始 DDL')).toBeInTheDocument()
    expect(screen.getByText('从左侧选择一张表后查看预览')).toBeInTheDocument()
  })

  it('shows backend query guard errors in the result panel', async () => {
    vi.mocked(queryApi.execute).mockRejectedValueOnce({
      response: {
        status: 400,
        data: { detail: 'SQL 语法错误：无法识别关键字 SSELECT' },
      },
    })

    const { container } = render(<QueryPage />)
    const selectors = container.querySelectorAll('.ant-select-selector')

    fireEvent.mouseDown(selectors[0])
    fireEvent.click((await within(document.body).findAllByText('MySQL-prod')).pop()!)

    await waitFor(() => expect(selectors[1]).not.toHaveAttribute('aria-disabled', 'true'))
    fireEvent.mouseDown(selectors[1])
    fireEvent.click((await within(document.body).findAllByText('demo_db')).pop()!)

    fireEvent.change(screen.getByTestId('monaco-editor'), {
      target: { value: 'sselect * from users' },
    })
    fireEvent.click(screen.getByRole('button', { name: /执行/ }))

    expect((await screen.findAllByText('执行失败')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('SQL 语法错误：无法识别关键字 SSELECT').length).toBeGreaterThan(0)
  })
})
