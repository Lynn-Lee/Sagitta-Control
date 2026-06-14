import type { ReactNode } from 'react'

export type DashboardStatCard = {
  title: string
  value: number
  icon: ReactNode
  color: string
}

export type OverviewResponse = {
  scope?: { label?: string }
  cards?: Record<string, number>
  trend?: {
    dates: string[]
    query_count: number[]
    query_user_count: number[]
    failure_count: number[]
    masked_count: number[]
    approved_count: number[]
    rejected_count: number[]
    revoked_count: number[]
    pending_stock_count: number[]
  }
  top_users?: Array<{ display_name: string; query_count: number }>
}

export type WorkflowOverviewResponse = {
  scope?: { label?: string }
  cards?: Record<string, number>
  submit_trend?: {
    dates: string[]
    submit_count: number[]
    approved_count: number[]
  }
  governance_trend?: {
    dates: string[]
    rejected_count: number[]
    cancel_count: number[]
    execute_failed_count: number[]
  }
  execute_trend?: {
    dates: string[]
    queued_count: number[]
    running_count: number[]
    success_count: number[]
  }
  pending_stock_trend?: {
    dates: string[]
    pending_count: number[]
  }
  top_submitters?: Array<{ display_name: string; count: number }>
  top_instances?: Array<{ instance_name: string; count: number }>
  top_databases?: Array<{ db_name: string; count: number }>
  top_approvers?: Array<{ display_name: string; count: number }>
  top_execute_instances?: Array<{ instance_name: string; count: number }>
}

export type ArchiveOverviewResponse = {
  scope?: { label?: string }
  cards?: Record<string, number>
  trend?: {
    dates: string[]
    submit_count: number[]
    success_count: number[]
    failed_count: number[]
    canceled_count: number[]
    estimated_rows: number[]
    processed_rows: number[]
    active_stock_count: number[]
  }
  top_submitters?: Array<{ display_name: string; count: number; estimated_rows: number }>
  top_instances?: Array<{ instance_name: string; count: number; estimated_rows: number }>
  top_tables?: Array<{ source_label: string; count: number; estimated_rows: number; processed_rows: number }>
}

export type InstanceOverviewResponse = {
  scope?: { label?: string }
  cards?: Record<string, number>
  instance_type_distribution?: Array<{ db_type: string; count: number }>
  instance_status_distribution?: Array<{ label: string; count: number }>
  database_status_distribution?: Array<{ label: string; count: number }>
}
