import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import UserManagement from './UserManagement'

vi.mock('@/api/system', () => ({
  userApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    export: vi.fn(),
    import: vi.fn(),
    downloadTemplate: vi.fn(),
  },
  roleApi: {
    list: vi.fn(),
  },
  userGroupApi: {
    list: vi.fn(),
  },
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useQuery: ({ queryKey }: { queryKey: string[] }) => {
    const key = queryKey[0]
    if (key === 'users') return { data: { total: 0, items: [] }, isLoading: false }
    if (key === 'all-roles') return { data: { items: [{ id: 1, name: 'dba', name_cn: 'DBA' }] } }
    if (key === 'all-users-for-manager') return { data: { items: [] } }
    if (key === 'all-user-groups') return { data: { items: [{ id: 1, name: 'team', name_cn: '团队' }] } }
    return { data: undefined, isLoading: false }
  },
}))

describe('UserManagement', () => {
  it('uses a wrapping filter grid so all controls stay visible', () => {
    const { container } = render(<UserManagement />)

    expect(container.querySelector('.sagitta-user-filter-grid')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重置筛选/ })).toBeVisible()
  })
})
