import { archiveApi, type ArchiveActionResponse, type ArchiveExecutePayload } from '@/api/archive'

export type ArchiveJobAction = 'start' | 'pause' | 'resume' | 'cancel'

export type ArchiveJobActionRequest = {
  id: number
  action: ArchiveJobAction
  payload?: ArchiveExecutePayload
}

export function runArchiveJobAction({
  id,
  action,
  payload,
}: ArchiveJobActionRequest): Promise<ArchiveActionResponse> {
  if (action === 'start') return archiveApi.start(id, payload)
  if (action === 'pause') return archiveApi.pause(id)
  if (action === 'resume') return archiveApi.resume(id)
  return archiveApi.cancel(id)
}
