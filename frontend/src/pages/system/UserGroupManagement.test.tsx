import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import UserGroupManagement from './UserGroupManagement'

vi.mock('@/api/system', () => ({
  userGroupApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    export: vi.fn(),
    import: vi.fn(),
    downloadTemplate: vi.fn(),
  },
  userApi: {
    list: vi.fn(),
  },
  resourceGroupApi: {
    list: vi.fn(),
  },
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useQuery: ({ queryKey }: { queryKey: string[] }) => {
    const key = queryKey[0]
    if (key === 'user-groups') return { data: { total: 0, items: [] }, isLoading: false }
    if (key === 'all-users') return { data: { items: [{ id: 1, username: 'admin', display_name: '超级管理员' }] } }
    if (key === 'user-groups-options') return { data: { items: [] } }
    if (key === 'all-resource-groups') return { data: { items: [{ id: 1, group_name: 'dba', group_name_cn: 'DBA 组', is_active: true }] } }
    return { data: undefined, isLoading: false }
  },
}))

describe('UserGroupManagement', () => {
  it('keeps search and reset controls in a dedicated filter action group', () => {
    const { container } = render(<UserGroupManagement />)

    expect(container.querySelector('.sagitta-user-group-filter-grid')).toBeInTheDocument()
    const actions = container.querySelector('.sagitta-user-group-filter-actions')
    expect(actions).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /搜索/ }).closest('.sagitta-user-group-filter-actions')).toBe(actions)
    expect(screen.getByRole('button', { name: /重置筛选/ }).closest('.sagitta-user-group-filter-actions')).toBe(actions)
  })
})
