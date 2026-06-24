import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import apiClient from '@/api/client'
import { useMonitorMutations } from './useMonitorMutations'

vi.mock('@/api/client', () => ({
  default: {
    post: vi.fn(),
    put: vi.fn(),
  },
}))

describe('useMonitorMutations', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('sends monitor alert actions with expected payload and invalidates alert queries', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const msgApi = { success: vi.fn(), error: vi.fn(), warning: vi.fn() }
    vi.mocked(apiClient.post).mockResolvedValue({ data: { ok: true } })
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { result } = renderHook(
      () => useMonitorMutations({
        activeId: 16,
        alertRulesText: '{}',
        instances: [],
        queryClient,
        msgApi,
        closeConfig: vi.fn(),
      }),
      { wrapper },
    )

    result.current.changeAlertEvent.mutate({ id: 7, action: 'close' })

    await waitFor(() => expect(msgApi.success).toHaveBeenCalledWith('告警状态已更新'))
    expect(apiClient.post).toHaveBeenCalledWith('/monitor/alerts/events/7/close', { reason: '监控页面关闭' })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['monitor-alert-events', 16] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['native-monitor-alerts', 16] })
  })
})
