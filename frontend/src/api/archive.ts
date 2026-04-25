import apiClient from './client'

export interface ArchiveJob {
  id: number
  workflow_id?: number | null
  celery_task_id?: string
  status: string
  archive_mode: 'purge' | 'dest'
  source_instance_id: number
  source_db: string
  source_table: string
  condition: string
  dest_instance_id?: number | null
  dest_db?: string
  dest_table?: string
  batch_size: number
  sleep_ms: number
  estimated_rows: number
  processed_rows: number
  current_batch: number
  row_count_is_estimated: boolean
  apply_reason?: string
  error_message?: string
  created_by: string
  created_by_id: number
  started_at?: string | null
  finished_at?: string | null
  created_at?: string | null
  batches?: ArchiveBatchLog[]
}

export interface ArchiveBatchLog {
  id: number
  batch_no: number
  status: string
  selected_rows: number
  inserted_rows: number
  deleted_rows: number
  message: string
  started_at?: string | null
  finished_at?: string | null
}

export interface ArchivePayload {
  source_instance_id: number
  source_db: string
  source_table: string
  condition: string
  archive_mode: 'purge' | 'dest'
  dest_instance_id?: number
  dest_db?: string
  dest_table?: string
  batch_size: number
  sleep_ms: number
  apply_reason?: string
  flow_id?: number
}

export interface ArchiveEstimateResponse {
  supported?: boolean
  msg: string
  count: number
  db_type?: string
}

export interface ArchiveActionResponse {
  success: boolean
  msg: string
  job_id: number
  workflow_id?: number | null
  status: string
  estimated_rows?: number
}

export const archiveApi = {
  support: () => apiClient.get('/archive/support/').then(r => r.data),
  estimate: (data: ArchivePayload) =>
    apiClient.post<ArchiveEstimateResponse>('/archive/estimate/', { ...data, dry_run: true }).then(r => r.data),
  submit: (data: ArchivePayload) =>
    apiClient.post<ArchiveActionResponse>('/archive/run/', { ...data, dry_run: false }).then(r => r.data),
  listJobs: (params?: { page?: number; page_size?: number }) =>
    apiClient.get<{ total: number; page: number; page_size: number; items: ArchiveJob[] }>('/archive/jobs/', { params }).then(r => r.data),
  getJob: (id: number) => apiClient.get<ArchiveJob>(`/archive/jobs/${id}/`).then(r => r.data),
  start: (id: number) => apiClient.post<ArchiveActionResponse>(`/archive/jobs/${id}/start/`).then(r => r.data),
  pause: (id: number) => apiClient.post<ArchiveActionResponse>(`/archive/jobs/${id}/pause/`).then(r => r.data),
  resume: (id: number) => apiClient.post<ArchiveActionResponse>(`/archive/jobs/${id}/resume/`).then(r => r.data),
  cancel: (id: number) => apiClient.post<ArchiveActionResponse>(`/archive/jobs/${id}/cancel/`).then(r => r.data),
}
