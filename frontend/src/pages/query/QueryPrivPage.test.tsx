import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import QueryPrivPage from './QueryPrivPage'

vi.mock('react-router-dom', () => ({
  useLocation: () => ({ state: null }),
}))

vi.mock('@/store/auth', () => ({
  useAuthStore: () => ({ user: { id: 1, username: 'admin' } }),
}))

vi.mock('@/api/query', () => ({
  queryApi: {
    listPrivileges: vi.fn(),
    listApplies: vi.fn(),
    listAuditRecords: vi.fn(),
    listManagePrivileges: vi.fn(),
    applyPrivilege: vi.fn(),
    auditApply: vi.fn(),
    cancelApply: vi.fn(),
    revokePrivilege: vi.fn(),
    privilegeRiskPlan: vi.fn(),
  },
}))

vi.mock('@/api/approvalFlow', () => ({
  approvalFlowApi: {
    list: vi.fn(),
  },
}))

vi.mock('@/api/instance', () => ({
  instanceApi: {
    list: vi.fn(),
    listRegisteredDbs: vi.fn(),
  },
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useQuery: ({ queryKey }: { queryKey: string[] }) => {
    const key = queryKey[0]

    if (key === 'my-query-privs') {
      return { data: { items: [], total: 0 } }
    }

    if (key === 'query-priv-applies') {
      return {
        data: {
          total: 1,
          items: [{
            id: 9,
            title: '研发申请临时查询',
            instance_id: 1,
            instance_name: 'MySQL84-Test',
            applicant_name: 'Codex 申请人',
            applicant_username: 'codex',
            db_name: 'test',
            scope_type: 'database',
            table_name: '',
            limit_num: 100,
            valid_date: '2026-06-30',
            apply_reason: '验证',
            risk_level: 'low',
            current_node_name: '',
            approval_progress: '超级管理员',
            status: 0,
            can_cancel: true,
            can_audit: false,
            created_at: '2026-05-29T16:04:23',
          }],
        },
      }
    }

    if (key === 'query-priv-audit-records') {
      return {
        data: {
          total: 1,
          items: [{
            id: 10,
            title: '审批记录',
            instance_id: 1,
            instance_name: 'MySQL84-Test',
            applicant_name: 'Codex 申请人',
            applicant_username: 'codex',
            db_name: 'test',
            scope_type: 'database',
            table_name: '',
            limit_num: 100,
            valid_date: '2026-06-30',
            risk_level: 'low',
            current_node_name: '',
            approval_progress: '超级管理员',
            status: 1,
            acted_node_name: '超级管理员',
            acted_action: '通过',
            acted_at: '2026-06-12T09:22:23',
          }],
        },
      }
    }

    if (key === 'query-priv-manage' || key === 'query-priv-revoked') {
      return { data: { items: [], total: 0, scope: { mode: 'self', label: '我的权限' } } }
    }

    if (key === 'instances-for-priv') {
      return { data: { items: [{ id: 1, instance_name: 'MySQL84-Test', db_type: 'mysql' }] } }
    }

    if (key === 'approval-flows-for-query-priv') {
      return { data: { items: [] } }
    }

    return { data: undefined }
  },
}))

describe('QueryPrivPage', () => {
  it('renders online query permission timestamps as full date time', () => {
    render(<QueryPrivPage />)

    fireEvent.click(screen.getByRole('tab', { name: /申请记录/ }))
    expect(screen.getByText('2026-05-29 16:04:23')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /审批记录/ }))
    expect(screen.getByText('2026-06-12 09:22:23')).toBeInTheDocument()
  })
})
