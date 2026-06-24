import { describe, expect, it, vi } from 'vitest'

import { runArchiveJobAction } from './archiveActions'
import { archiveApi } from '@/api/archive'

vi.mock('@/api/archive', () => ({
  archiveApi: {
    start: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    cancel: vi.fn(),
  },
}))

describe('runArchiveJobAction', () => {
  it('dispatches start with execute payload only to the start endpoint', async () => {
    const payload = { mode: 'scheduled' as const, scheduled_at: '2026-06-24T10:00:00.000Z' }
    vi.mocked(archiveApi.start).mockResolvedValueOnce({ success: true, msg: 'ok', job_id: 12, status: 'scheduled' })

    await runArchiveJobAction({ id: 12, action: 'start', payload })

    expect(archiveApi.start).toHaveBeenCalledWith(12, payload)
    expect(archiveApi.pause).not.toHaveBeenCalled()
    expect(archiveApi.resume).not.toHaveBeenCalled()
    expect(archiveApi.cancel).not.toHaveBeenCalled()
  })

  it('dispatches pause resume and cancel without leaking execute payload', async () => {
    vi.mocked(archiveApi.pause).mockResolvedValueOnce({ success: true, msg: 'paused', job_id: 12, status: 'paused' })
    vi.mocked(archiveApi.resume).mockResolvedValueOnce({ success: true, msg: 'running', job_id: 12, status: 'running' })
    vi.mocked(archiveApi.cancel).mockResolvedValueOnce({ success: true, msg: 'canceled', job_id: 12, status: 'canceled' })

    await runArchiveJobAction({ id: 12, action: 'pause', payload: { mode: 'external' } })
    await runArchiveJobAction({ id: 12, action: 'resume', payload: { mode: 'external' } })
    await runArchiveJobAction({ id: 12, action: 'cancel', payload: { mode: 'external' } })

    expect(archiveApi.pause).toHaveBeenCalledWith(12)
    expect(archiveApi.resume).toHaveBeenCalledWith(12)
    expect(archiveApi.cancel).toHaveBeenCalledWith(12)
  })
})
