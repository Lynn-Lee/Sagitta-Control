import apiClient from './client'

export type OptimizeSupportLevel = 'full' | 'partial' | 'static_only' | 'unsupported'
export type OptimizeSource = 'manual' | 'slowlog' | 'fingerprint'

export interface OptimizeFinding {
  severity: 'critical' | 'warning' | 'info' | 'ok'
  code: string
  title: string
  detail: string
  evidence: string
  confidence: number
}

export interface OptimizeRecommendation {
  priority: number
  type: string
  title: string
  action: string
  reason: string
  risk: string
  confidence: number
}

export interface OptimizeAnalyzeResponse {
  supported: boolean
  support_level: OptimizeSupportLevel
  engine: string
  source: OptimizeSource
  risk_score: number
  summary: string
  findings: OptimizeFinding[]
  recommendations: OptimizeRecommendation[]
  plan: {
    format: string
    summary: Record<string, any>
    operators: Record<string, any>[]
  }
  metadata: {
    tables: string[]
    indexes: Record<string, any>[]
    statistics: Record<string, any>[]
    slowlog: Record<string, any>
  }
  raw: any
  sql: string
  msg: string
}

export const optimizeApi = {
  analyze: (data: {
    log_id?: number
    fingerprint?: string
    instance_id?: number
    db_name?: string
    sql?: string
  }) => apiClient.post<OptimizeAnalyzeResponse>('/optimize/analyze/', data).then(r => r.data),
}

