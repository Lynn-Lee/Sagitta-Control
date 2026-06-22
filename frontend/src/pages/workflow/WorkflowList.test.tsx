import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import WorkflowList from './WorkflowList'

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@/store/auth', () => ({
  useAuthStore: () => ({ user: { id: 1, username: 'admin' } }),
}))

vi.mock('@/api/workflow', () => ({
  workflowApi: {
    list: vi.fn(),
    cancel: vi.fn(),
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
    const key = queryKey[0]

    if (key === 'instances-for-wf-filter') {
      return { data: { items: [{ id: 1, instance_name: 'MySQL84-Test', db_type: 'mysql' }] } }
    }

    if (key === 'workflow-scope-preview') {
      return { data: { scope: { mode: 'all', label: '全量数据' } } }
    }

    if (key === 'workflows') {
      return {
        data: {
          total: 1,
          items: [{
            id: 49,
            workflow_type_label: 'SQL 工单',
            workflow_name: 'Codex E2E 清理临时表 20260609173455',
            engineer_display: 'Codex 全链路申请人',
            instance_name: 'MySQL84-Test',
            db_name: 'test',
            risk_level: 'high',
            status: 0,
            status_desc: '待审核',
            audit_chain_text: '超级管理员',
            current_node_name: '超级管理员',
            created_at: '2026-06-12T09:22:23',
            can_cancel: false,
          }],
        },
        isLoading: false,
        refetch: vi.fn(),
      }
    }

    return { data: undefined, isLoading: false, refetch: vi.fn() }
  },
}))

describe('WorkflowList', () => {
  it('renders workflow names with compact table button styling', () => {
    render(<WorkflowList />)

    fireEvent.click(screen.getByRole('tab', { name: /工单视图/ }))
    expect(screen.getByRole('button', { name: /Codex E2E 清理临时表/ })).toHaveClass('sagitta-table-link-button')
    expect(screen.getByText('Codex 全链路申请人')).toHaveClass('sagitta-nowrap-cell')
    expect(screen.getByText('MySQL84-Test')).toHaveClass('sagitta-nowrap-cell')
    expect(screen.getByText('2026-06-12 09:22:23')).toBeInTheDocument()
  })
})
